import logging
from datetime import UTC, datetime
from typing import Any
from xml.etree import ElementTree

import requests
from requests import RequestException

from .const import (
    API_DESCRIBE_STORED_QUERIES_URL,
    API_FINLAND_BBOX,
    API_GET_FEATURE_URL,
    API_GET_PARAMS_URL,
    API_STATIONS_QUERY_ID,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)

GML_ID = "{http://www.opengis.net/gml/3.2}id"
NAMESPACES = {
    "wfs": "http://www.opengis.net/wfs/2.0",
    "gml": "http://www.opengis.net/gml/3.2",
    "BsWfs": "http://xml.fmi.fi/schema/wfs/2.0",
    "target": "http://xml.fmi.fi/namespace/om/atmosphericfeatures/1.1",
    "ef": "http://inspire.ec.europa.eu/schemas/ef/4.0",
    "base": "http://inspire.ec.europa.eu/schemas/base/3.3",
    "omop": "http://inspire.ec.europa.eu/schemas/omop/2.9",
}

# STUK's radiation queries are not in FMI's parameter metadata.
STUK_UNITS = {"::air": "µBq/m³", "::external-radiation": "µSv/h"}


class FMIException(Exception):
    pass


def normalize_value(value: str, negative_as_zero: bool) -> str:
    # FMI reports "no measurable precipitation" as -1 rather than 0.
    if negative_as_zero:
        try:
            if float(value) == -1:
                return "0.0"
        except (TypeError, ValueError):
            pass
    return value


def _text(element: ElementTree.Element, path: str) -> str:
    found = element.find(path, NAMESPACES)
    if found is None or found.text is None:
        raise FMIException(f"FMI's response lacks {path}")
    return found.text.strip()


def _coords(element: ElementTree.Element | None) -> tuple[float | None, float | None]:
    parts = element.text.split() if element is not None and element.text else []
    return (float(parts[0]), float(parts[1])) if len(parts) > 1 else (None, None)


def _feature_url(lang: str, params: dict[str, Any]) -> str:
    url = API_GET_FEATURE_URL.replace("${lang}", lang)
    for key, value in params.items():
        if value is not None and value != "":
            url += f"&{key}={value}"
    return url


class FMISession:
    def __init__(self, timeout: int = 20):
        self._timeout = timeout

    def get_document(self, url: str) -> bytes:
        """Download a document as it is, such as the warning feed or one warning in it."""
        _LOGGER.debug(f"Downloading from FMI (url={url})")
        try:
            response = requests.get(url=url, headers={"User-Agent": USER_AGENT}, timeout=self._timeout)
        except RequestException as exception:
            raise FMIException(f"Communication error {exception}") from exception
        if response.status_code != 200:
            raise FMIException(f"{response.status_code} is not valid")
        return response.content

    def _xml(self, url: str) -> ElementTree.Element:
        try:
            return ElementTree.fromstring(self.get_document(url))
        except ElementTree.ParseError as exception:
            raise FMIException(f"FMI's response is not valid XML: {exception}") from exception

    def get_feature(self, lang: str, params: dict[str, Any], target_param: str, get_latest: bool, negative_as_zero: bool = False) -> Any:
        root = self._xml(_feature_url(lang, params))
        result = {
            "latitude": None,
            "longitude": None,
            "query_id": params["storedquery_id"],
            "parameter": target_param,
            "data": [],
        }

        for item in root.findall("./wfs:member/BsWfs:BsWfsElement", NAMESPACES):
            if result["latitude"] is None:
                result["latitude"], result["longitude"] = _coords(item.find("./BsWfs:Location/gml:Point/gml:pos", NAMESPACES))

            if _text(item, "./BsWfs:ParameterName").lower() != target_param.lower():
                continue

            value = _text(item, "./BsWfs:ParameterValue")
            if value == "NaN":
                continue

            time = datetime.fromisoformat(_text(item, "./BsWfs:Time"))
            if time.tzinfo is None:
                # FMI reports UTC; make it explicit so the values stay
                # comparable with timezone-aware datetimes downstream.
                time = time.replace(tzinfo=UTC)

            if get_latest and result["data"] and time <= result["data"][0]["time"]:
                continue
            if get_latest:
                result["data"] = []
            result["data"].append({"time": time, "value": normalize_value(value, negative_as_zero)})

        return result

    def list_stored_queries(self, lang: str, suffix: str | None = None) -> list[list[str]]:
        """Return [id, title] of the queries that take a station (fmisid), sorted by title."""
        root = self._xml(API_DESCRIBE_STORED_QUERIES_URL.replace("${lang}", lang))
        queries = [
            [item.attrib["id"], _text(item, "./wfs:Title")]
            for item in root.findall("./wfs:StoredQueryDescription", NAMESPACES)
            if (suffix is None or item.attrib["id"].endswith(suffix))
            and any(param.attrib.get("name") == "fmisid" for param in item.findall("./wfs:Parameter", NAMESPACES))
        ]
        return sorted(queries, key=lambda query: query[1])

    def list_parameters(self, lang: str, params: dict[str, Any]) -> list[str]:
        """Return the distinct parameter names a query actually reports.

        This is the same question the runtime coordinator asks when it filters
        the response, so what the config flow offers is exactly what a sensor
        will be able to read.
        """
        root = self._xml(_feature_url(lang, params))
        names = {item.text for item in root.findall("./wfs:member/BsWfs:BsWfsElement/BsWfs:ParameterName", NAMESPACES) if item.text}
        return sorted(names, key=str.lower)

    def list_stations_for_query(self, lang: str, query_id: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Return only the stations that actually serve a given stored query.

        The multipointcoverage twin of a query describes the locations it
        covers, which is exactly the set a sensor could read. Returns an empty
        list when the query has no such twin, so callers can fall back.
        """
        coverage_id = query_id.replace("::simple", "::multipointcoverage")
        if coverage_id == query_id:
            return []

        root = self._xml(_feature_url(lang, {**params, "storedquery_id": coverage_id, "bbox": API_FINLAND_BBOX}))

        regions = {}
        for location in root.findall(".//target:Location", NAMESPACES):
            identifier = location.find("./gml:identifier", NAMESPACES)
            region = location.find("./target:region", NAMESPACES)
            if identifier is not None and identifier.text:
                regions[identifier.text] = region.text if region is not None else None

        stations = []
        for point in root.findall(".//gml:MultiPoint/gml:pointMember/gml:Point", NAMESPACES):
            fmisid = point.attrib.get(GML_ID, "").removeprefix("point-")
            if not fmisid.isdigit():
                continue
            name = point.find("./gml:name", NAMESPACES)
            latitude, longitude = _coords(point.find("./gml:pos", NAMESPACES))
            stations.append(
                {
                    "id": fmisid,
                    "name": name.text if name is not None and name.text else fmisid,
                    "region": regions.get(fmisid),
                    "latitude": latitude,
                    "longitude": longitude,
                }
            )
        return stations

    def list_stations(self, lang: str) -> list[dict[str, Any]]:
        """Return the observation stations FMI currently lists as operational.

        Decommissioned stations are simply absent from this response rather
        than carrying an end date, so it doubles as a liveness check.
        """
        root = self._xml(_feature_url(lang, {"storedquery_id": API_STATIONS_QUERY_ID}))

        stations = []
        for facility in root.findall("./wfs:member/ef:EnvironmentalMonitoringFacility", NAMESPACES):
            identifier = facility.find(".//base:Identifier/base:localId", NAMESPACES)
            if identifier is None or identifier.text is None:
                continue
            # gml:name repeats as [station, -id, <optional WMO/ICAO codes>,
            # municipality, country], so the municipality is second from last.
            names = [name.text for name in facility.findall("./gml:name", NAMESPACES) if name.text]
            latitude, longitude = _coords(facility.find(".//ef:representativePoint/gml:Point/gml:pos", NAMESPACES))
            stations.append(
                {
                    "id": identifier.text,
                    "name": names[0] if names else identifier.text,
                    "region": names[-2] if len(names) > 2 else None,
                    "latitude": latitude,
                    "longitude": longitude,
                }
            )
        return stations

    def get_parameter_descriptions(self, lang: str, query_id: str) -> dict[str, tuple[str | None, str | None]]:
        """Return {parameter name: (label, unit)} for the query's property set."""
        kind = "forecast" if "forecast::" in query_id else "observation"
        root = self._xml(API_GET_PARAMS_URL.replace("${lang}", lang).replace("${property}", kind))

        result = {}
        for prop in root.findall("./omop:component/omop:ObservableProperty", NAMESPACES):
            name = prop.attrib.get(GML_ID)
            if name is None:
                continue
            label = prop.find("./omop:label", NAMESPACES)
            uom = prop.find("./omop:uom", NAMESPACES)
            unit = uom.attrib.get("uom") if uom is not None else None
            result[name] = (label.text if label is not None else None, unit.replace("degC", "°C") if unit is not None else None)
        return result

    def get_unit(self, lang: str, query_id: str, param_name: str) -> str | None:
        if query_id.startswith("stuk::"):
            return next((unit for key, unit in STUK_UNITS.items() if key in query_id), None)
        return self.get_parameter_descriptions(lang, query_id).get(param_name.lower(), (None, None))[1]
