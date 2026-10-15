"""A weather place: FMI's edited point forecast, hour by hour, and the daily and twice-daily periods made from it."""

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.weather import (
    ATTR_CONDITION_CLEAR_NIGHT,
    ATTR_CONDITION_CLOUDY,
    ATTR_CONDITION_FOG,
    ATTR_CONDITION_HAIL,
    ATTR_CONDITION_LIGHTNING_RAINY,
    ATTR_CONDITION_PARTLYCLOUDY,
    ATTR_CONDITION_POURING,
    ATTR_CONDITION_RAINY,
    ATTR_CONDITION_SNOWY,
    ATTR_CONDITION_SNOWY_RAINY,
    ATTR_CONDITION_SUNNY,
    Forecast,
)
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import API_FORECAST_QUERY_ID, API_TIME_FORMAT, CONF_LANG, CONF_LOCATION, DOMAIN, FORECAST_DAYS, WEATHER_SCAN_INTERVAL
from .session import FMIException, FMINoData, FMISession

_LOGGER = logging.getLogger(__name__)

PARAMETERS = [
    "Temperature",
    "FeelsLike",
    "DewPoint",
    "Humidity",
    "Pressure",
    "WindSpeedMS",
    "WindDirection",
    "HourlyMaximumGust",
    "TotalCloudCover",
    "Precipitation1h",
    "PoP",
    "SmartSymbol",
]

# FMI's SmartSymbol, https://github.com/fmidev/smartmet-engine-querydata/blob/master/docs/smartsymbol.md
# Day codes run from 1 to 77, and 100 is added when the sun is down.
CONDITIONS = {
    1: ATTR_CONDITION_SUNNY,
    2: ATTR_CONDITION_PARTLYCLOUDY,
    4: ATTR_CONDITION_PARTLYCLOUDY,
    6: ATTR_CONDITION_CLOUDY,
    7: ATTR_CONDITION_CLOUDY,
    9: ATTR_CONDITION_FOG,
    11: ATTR_CONDITION_RAINY,
    14: ATTR_CONDITION_SNOWY_RAINY,
    17: ATTR_CONDITION_SNOWY_RAINY,
    **dict.fromkeys([21, 24, 27, 31, 32, 34, 35, 37, 38], ATTR_CONDITION_RAINY),
    **dict.fromkeys([33, 36, 39], ATTR_CONDITION_POURING),
    **dict.fromkeys(range(41, 50), ATTR_CONDITION_SNOWY_RAINY),
    **dict.fromkeys(range(51, 60), ATTR_CONDITION_SNOWY),
    **dict.fromkeys([61, 64, 67], ATTR_CONDITION_HAIL),
    **dict.fromkeys([71, 74, 77], ATTR_CONDITION_LIGHTNING_RAINY),
}

# A period takes its condition and wind from one hour: 14:00 for a day and a daytime half, 02:00 for a night half.
DAY_REFERENCE = timedelta(hours=14)
HALF_REFERENCE = timedelta(hours=8)
# A forecast is still worth showing while FMI cannot be reached for a while.
KEEP_FORECAST = timedelta(hours=3)

_unknown_symbols: set[int] = set()


def build_weather_unique_id(data: dict[str, Any]) -> str:
    location = data[CONF_LOCATION]
    return f"weather_{float(location['latitude']):.4f}_{float(location['longitude']):.4f}"


def condition_for(symbol: float | None) -> str | None:
    if symbol is None:
        return None
    code = int(symbol)
    if code == 101:
        return ATTR_CONDITION_CLEAR_NIGHT
    condition = CONDITIONS.get(code % 100)
    if condition is None and code not in _unknown_symbols:
        _unknown_symbols.add(code)
        _LOGGER.warning(f"FMI's weather symbol {code} is not known, the condition is left empty")
    return condition


def current_row(rows: list[dict[str, Any]], now: datetime) -> dict[str, Any] | None:
    """The hour under way, or the first one if the forecast starts later."""
    started = [row for row in rows if row["time"] <= now]
    return started[-1] if started else (rows[0] if rows else None)


def hourly_forecast(rows: list[dict[str, Any]], now: datetime) -> list[Forecast]:
    first = current_row(rows, now)
    return [
        Forecast(
            datetime=row["time"].isoformat(),
            condition=condition_for(row["SmartSymbol"]),
            native_temperature=row["Temperature"],
            native_apparent_temperature=row["FeelsLike"],
            native_dew_point=row["DewPoint"],
            humidity=row["Humidity"],
            native_pressure=row["Pressure"],
            native_wind_speed=row["WindSpeedMS"],
            wind_bearing=row["WindDirection"],
            native_wind_gust_speed=row["HourlyMaximumGust"],
            cloud_coverage=_rounded(row["TotalCloudCover"]),
            native_precipitation=row["Precipitation1h"],
            precipitation_probability=_rounded(row["PoP"]),
            is_daytime=row["SmartSymbol"] is not None and row["SmartSymbol"] < 100,
        )
        for row in rows
        if first is not None and row["time"] >= first["time"]
    ]


def daily_forecast(rows: list[dict[str, Any]], now: datetime) -> list[Forecast]:
    def day(local: datetime) -> tuple[datetime, bool | None]:
        return local.replace(hour=0, minute=0, second=0, microsecond=0), None

    return _periods(rows, now, day, DAY_REFERENCE)


def twice_daily_forecast(rows: list[dict[str, Any]], now: datetime) -> list[Forecast]:
    def half(local: datetime) -> tuple[datetime, bool | None]:
        if 6 <= local.hour < 18:
            return local.replace(hour=6, minute=0, second=0, microsecond=0), True
        evening = local if local.hour >= 18 else local - timedelta(days=1)
        return evening.replace(hour=18, minute=0, second=0, microsecond=0), False

    return _periods(rows, now, half, HALF_REFERENCE)


def _periods(rows: list[dict[str, Any]], now: datetime, period_of, reference: timedelta) -> list[Forecast]:
    first = current_row(rows, now)
    groups: dict[datetime, list[dict[str, Any]]] = {}
    daytime: dict[datetime, bool | None] = {}
    precipitation: dict[datetime, float] = {}
    for row in rows:
        if first is None or row["time"] < first["time"]:
            continue
        # The local wall clock: adding hours to a local start below keeps 14:00 at 14:00 over a DST change.
        start, is_daytime = period_of(dt_util.as_local(row["time"]))
        groups.setdefault(start, []).append(row)
        daytime[start] = is_daytime
        # Precipitation1h is the hour that ends at the row's time, so it counts in the period of the hour before.
        if row["Precipitation1h"] is not None:
            rained_in, _ = period_of(dt_util.as_local(row["time"] - timedelta(hours=1)))
            precipitation[rained_in] = precipitation.get(rained_in, 0) + row["Precipitation1h"]

    forecast = []
    for index, (start, hours) in enumerate(groups.items()):
        target = start + reference
        ref = min(hours, key=lambda row: abs(row["time"] - target))
        # Only the end of the data lacks a later period's reference hour. Where the clocks skip it, the next hour serves.
        if index > 0 and abs(ref["time"] - target) > timedelta(hours=1):
            continue
        temperatures = [row["Temperature"] for row in hours if row["Temperature"] is not None]
        probabilities = [row["PoP"] for row in hours if row["PoP"] is not None]
        gusts = [row["HourlyMaximumGust"] for row in hours if row["HourlyMaximumGust"] is not None]
        entry = Forecast(
            datetime=start.isoformat(),
            condition=condition_for(ref["SmartSymbol"]),
            native_temperature=max(temperatures, default=None),
            native_templow=min(temperatures, default=None),
            native_precipitation=round(precipitation[start], 2) if start in precipitation else None,
            precipitation_probability=_rounded(max(probabilities, default=None)),
            native_wind_speed=ref["WindSpeedMS"],
            wind_bearing=ref["WindDirection"],
            native_wind_gust_speed=max(gusts, default=None),
        )
        if daytime[start] is not None:
            entry["is_daytime"] = daytime[start]
        forecast.append(entry)
    return forecast


def _rounded(value: float | None) -> int | None:
    return round(value) if value is not None else None


async def async_get_forecast(hass: HomeAssistant, lang: str, location: dict[str, Any]) -> list[dict[str, Any]]:
    """The forecast for a place from the hour under way, one row per hour.

    Raises FMINoData when FMI has no forecast for the place, FMIException when it cannot be read.
    """
    start = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    params = {
        "storedquery_id": API_FORECAST_QUERY_ID,
        "latlon": f"{float(location['latitude'])},{float(location['longitude'])}",
        "parameters": ",".join(PARAMETERS),
        "starttime": start.strftime(API_TIME_FORMAT),
        "endtime": (start + timedelta(days=FORECAST_DAYS)).strftime(API_TIME_FORMAT),
    }
    rows = await hass.async_add_executor_job(FMISession().get_coverage, lang, params)
    # Past the forecast's end every value is NaN.
    rows = [row for row in rows if row["Temperature"] is not None and row["SmartSymbol"] is not None]
    if not rows:
        raise FMINoData("FMI returned no forecast for the place")
    return rows


class FMIWeatherCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """The forecast for one place, as one row per hour from the hour under way."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, subentry: ConfigSubentry):
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {subentry.title}",
            update_interval=timedelta(minutes=WEATHER_SCAN_INTERVAL),
        )
        self.subentry = subentry
        self._fetched_at: datetime | None = None

    async def _async_update_data(self) -> list[dict[str, Any]]:
        try:
            rows = await async_get_forecast(self.hass, self.config_entry.data[CONF_LANG], self.subentry.data[CONF_LOCATION])
        except FMIException as exception:
            if self.data is not None and self._fetched_at is not None and dt_util.utcnow() - self._fetched_at < KEEP_FORECAST:
                _LOGGER.debug(f"Could not read FMI's forecast, keeping the previous one: {exception}")
                return self.data
            raise UpdateFailed(f"Could not read FMI's forecast: {exception}") from exception

        self._fetched_at = dt_util.utcnow()
        return rows
