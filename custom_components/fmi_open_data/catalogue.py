"""What can be measured: every station query's parameters, and for each parameter the stations that reported it.

The flow for adding measurements starts from what to measure, so it needs every parameter at once, and then offers
for each one only the stations that have it. Both come from FMI's own data: one coverage request per query over
Finland, where a station that does not measure a parameter reports only NaN for it. About 35 requests, all small
when the 10-minute observations are read for the last hour only, so the result is kept for an hour.

A forecast is not tied to stations, so its parameters are read at Home Assistant's own location and it asks for a
point instead. An observation query with parameters but no stations, such as STUK's air radionuclides, asks for a
place name. A few queries, such as the sea surface temperature, FMI publishes only in the ::simple form, which says
where a value is from by its coordinates alone. They are read for a short while and their stations recognised in
FMI's station list. A position that is not a station there is left out, and so is a query with no station left.
"""

import asyncio
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance

from .const import API_FINLAND_BBOX, API_TIME_FORMAT, DOMAIN
from .session import FMIException, FMIRefused, FMISession

_LOGGER = logging.getLogger(__name__)

KIND_STATIONS = "stations"
KIND_POINT = "point"
KIND_PLACE = "place"

KEEP = timedelta(hours=1)
# Queries of periods report over their own default window, and the latest values take no time at all. The others report
# every few minutes, and an hour is enough to see who measures what.
OWN_WINDOW = ("::hourly", "::daily", "::monthly", "::yearly", "::30year", "::latest")


@dataclass
class Parameter:
    query_id: str
    query_title: str
    name: str
    description: str | None
    kind: str
    # The stations that reported the parameter, for a query of stations.
    stations: list[dict[str, Any]] = field(default_factory=list)

    @property
    def value(self) -> str:
        return f"{self.query_id}|{self.name}"

    # FMI gives a minimum, maximum and mean the same description, and some queries the same title. A label that
    # repeats another gets the parameter, and if that is not enough, the query too.
    detail: str = ""

    @property
    def label(self) -> str:
        label = f"{self.description or self.name} · {self.query_title}"
        return f"{label} ({self.detail})" if self.detail else label


@dataclass
class Catalogue:
    # By Parameter.value, in the order they are offered: by name, the 30-year normals last.
    parameters: dict[str, Parameter]
    # Every station of a query, whether it reported the parameter or not, by query id.
    stations: dict[str, list[dict[str, Any]]]


def distance_km(hass: HomeAssistant, station: dict[str, Any]) -> float:
    metres = distance(hass.config.latitude, hass.config.longitude, station["latitude"], station["longitude"])
    return float("inf") if metres is None else metres / 1000


async def async_catalogue(hass: HomeAssistant, lang: str) -> Catalogue:
    """Raises FMIException when FMI's list of queries cannot be read. A query that fails is left out."""
    cache = hass.data.setdefault(DOMAIN, {}).setdefault("catalogue", {})
    now = dt_util.utcnow()
    if lang in cache and now - cache[lang][0] < KEEP:
        return cache[lang][1]

    queries = await hass.async_add_executor_job(FMISession().list_stored_queries, lang, "::simple")
    results = await asyncio.gather(*(_async_read(hass, lang, query_id, now) for query_id, _ in queries), return_exceptions=True)
    simple_only = [index for index, result in enumerate(results) if isinstance(result, FMIRefused)]
    if simple_only:
        try:
            known = await hass.async_add_executor_job(FMISession().list_stations, lang)
        except FMIException as exception:
            _LOGGER.debug(f"Could not read FMI's stations to recognise them in the ::simple queries: {exception}")
            known = []
        for index in simple_only:
            try:
                results[index] = await _async_read_simple(hass, lang, queries[index][0], now, known)
            except FMIException as exception:
                results[index] = exception

    descriptions: dict[str, dict[str, tuple[str | None, str | None]]] = {}
    parameters: list[Parameter] = []
    stations: dict[str, list[dict[str, Any]]] = {}
    for (query_id, title), result in zip(queries, results, strict=True):
        if isinstance(result, BaseException):
            _LOGGER.debug(f"Left {query_id} out of the parameters on offer: {result}")
            continue
        fields, query_stations = result
        if not fields:
            continue
        kind = KIND_STATIONS if query_stations else KIND_POINT if "::forecast" in query_id else KIND_PLACE
        metadata = "forecast" if "::forecast" in query_id else "observation"
        if metadata not in descriptions:
            try:
                descriptions[metadata] = await hass.async_add_executor_job(FMISession().get_parameter_descriptions, lang, query_id)
            except FMIException:
                descriptions[metadata] = {}
        # A forecast's fixed points are places by geoid, an observation's stations by fmisid.
        target_type = "geoid" if "::forecast" in query_id else "fmisid"
        query_stations = [{**station, "target_type": target_type} for station in query_stations]
        stations[query_id] = sorted(query_stations, key=lambda station: distance_km(hass, station))
        for name in fields:
            parameters.append(
                Parameter(
                    query_id=query_id,
                    query_title=title,
                    name=name,
                    description=descriptions[metadata].get(name.lower(), (None, None))[0],
                    kind=kind,
                    stations=[station for station in stations[query_id] if name in station["measured"]],
                )
            )

    for detail in (lambda parameter: parameter.name, lambda parameter: f"{parameter.name}, {parameter.query_id}"):
        labels = Counter(parameter.label for parameter in parameters)
        for parameter in parameters:
            if labels[parameter.label] > 1:
                parameter.detail = detail(parameter)
    parameters.sort(key=lambda parameter: ("::30year" in parameter.query_id, parameter.label.lower()))
    catalogue = Catalogue({parameter.value: parameter for parameter in parameters}, stations)
    # A query that failed for another reason than FMI refusing it, or having no data, may work in a moment.
    if not any(isinstance(result, BaseException) and not isinstance(result, FMIRefused) for result in results):
        cache[lang] = (now, catalogue)
    return catalogue


async def _async_read_simple(
    hass: HomeAssistant, lang: str, query_id: str, now: datetime, known: list[dict[str, Any]]
) -> tuple[list[str], list[dict[str, Any]]]:
    # The simple form repeats the time, the parameter and the position for every value: a month of daily values over
    # Finland is 5 MB, and an hour of the magnetometer's 10-second values 15 MB. A few values a station are enough to
    # see who measures what: hourly ones for three hours, daily ones for three days, monthly ones for two months.
    if "::monthly" in query_id or "::daily" in query_id:
        back, step = timedelta(days=62 if "::monthly" in query_id else 3), 1440
    else:
        back, step = timedelta(hours=3), 60
    params = {"storedquery_id": query_id, "bbox": API_FINLAND_BBOX, "starttime": (now - back).strftime(API_TIME_FORMAT), "timestep": step}
    fields, measured = await hass.async_add_executor_job(FMISession().get_simple_coverage, lang, params)

    stations_by_position = {
        (round(item["latitude"], 4), round(item["longitude"], 4)): item for item in known if item["latitude"] is not None
    }
    stations = []
    for (latitude, longitude), reported in measured.items():
        station = stations_by_position.get((round(latitude, 4), round(longitude, 4)))
        if station is not None:
            stations.append({**station, "measured": reported})
    return (fields, stations) if stations else ([], [])


async def _async_read(hass: HomeAssistant, lang: str, query_id: str, now: datetime) -> tuple[list[str], list[dict[str, Any]]]:
    params: dict[str, Any] = {"storedquery_id": query_id.replace("::simple", "::multipointcoverage"), "bbox": API_FINLAND_BBOX}
    if "::forecast" not in query_id:
        if not any(window in query_id for window in OWN_WINDOW):
            params["starttime"] = (now - timedelta(hours=1)).strftime(API_TIME_FORMAT)
        return await hass.async_add_executor_job(FMISession().get_station_coverage, lang, params)

    # Some forecasts are for stations, such as the sea level forecast at the mareographs. The rest are for any point,
    # and their parameters are read at Home Assistant's own location.
    params |= {"starttime": now.strftime(API_TIME_FORMAT), "endtime": (now + timedelta(hours=1)).strftime(API_TIME_FORMAT)}
    try:
        fields, stations = await hass.async_add_executor_job(FMISession().get_station_coverage, lang, params)
    except FMIRefused:
        fields, stations = [], []
    if stations:
        return fields, stations
    params = {**{key: value for key, value in params.items() if key != "bbox"}, "latlon": f"{hass.config.latitude},{hass.config.longitude}"}
    fields, _ = await hass.async_add_executor_job(FMISession().get_station_coverage, lang, params)
    # FMI answers for the named place nearest to the point, but the point is the user's to choose.
    return fields, []
