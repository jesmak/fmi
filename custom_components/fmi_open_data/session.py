import html
import logging
import re
from datetime import UTC, datetime
from typing import Any
from xml.etree import ElementTree

import requests
from requests import RequestException

from .const import (
    API_DESCRIBE_STORED_QUERIES_URL,
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
    "gmlcov": "http://www.opengis.net/gmlcov/1.0",
    "swe": "http://www.opengis.net/swe/2.0",
}


class FMIException(Exception):
    pass


class FMIRefused(FMIException):
    """FMI answered HTTP 400. The message is FMI's own reason, such as "Too long time interval requested!", or its
    status line, "400 Bad Request", when it gives none."""


class FMINoData(FMIRefused):
    """FMI has nothing for the request, such as a forecast for a place outside its area."""


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


def _coverage_rows(root: ElementTree.Element) -> list[dict[str, Any]]:
    fields = [field.attrib["name"] for field in root.iter("{http://www.opengis.net/swe/2.0}field")]
    positions = _text(root, ".//gmlcov:positions").split() if fields else []
    values = _text(root, ".//gml:doubleOrNilReasonTupleList").split() if fields else []
    # A position is latitude, longitude and a Unix time; a tuple has one value per field.
    if len(positions) % 3 or len(values) != len(positions) // 3 * len(fields):
        raise FMIException("FMI's response has a different number of times and values")

    rows = []
    for index in range(len(positions) // 3):
        row: dict[str, Any] = {"time": datetime.fromtimestamp(int(positions[index * 3 + 2]), UTC)}
        for offset, name in enumerate(fields):
            value = values[index * len(fields) + offset]
            try:
                row[name] = None if value == "NaN" else float(value)
            except ValueError as exception:
                raise FMIException(f"FMI's response has {value} as {name}") from exception
        rows.append(row)
    return rows


def feature_url(lang: str, params: dict[str, Any]) -> str:
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
        status = f"{response.status_code} {response.reason or ''}".strip()
        if response.status_code == 400:
            # FMI explains itself in several ExceptionTexts, such as "Too long time interval requested!" and then the
            # limit, and ends with an echo of the request's URI, which is left out.
            texts = re.findall(r"<ExceptionText>([^<]*)", response.content.decode(errors="replace"))
            reasons = [html.unescape(text).strip() for text in texts]
            message = " ".join(reason for reason in reasons if reason and not reason.startswith("URI:")) or status
            raise (FMINoData if message.startswith("No data available") else FMIRefused)(message)
        if response.status_code != 200:
            raise FMIException(f"FMI answered {status}")
        return response.content

    def _xml(self, url: str) -> ElementTree.Element:
        try:
            return ElementTree.fromstring(self.get_document(url))
        except ElementTree.ParseError as exception:
            raise FMIException(f"FMI's response is not valid XML: {exception}") from exception

    def get_feature(self, lang: str, params: dict[str, Any], target_param: str, get_latest: bool, negative_as_zero: bool = False) -> Any:
        root = self._xml(feature_url(lang, params))
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

    def get_coverage(self, lang: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Return a multipointcoverage query's values for one place as one row per time.

        Each row has "time" and the parameters by name, with FMI's NaN as None.
        """
        return _coverage_rows(self._xml(feature_url(lang, params)))

    def get_observations(self, lang: str, params: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """Return one station's observations as get_coverage does, with the station's name and coordinates.

        The station is None when the response has no data at all.
        """
        root = self._xml(feature_url(lang, params))
        point = root.find(".//gml:MultiPoint//gml:Point", NAMESPACES)
        station = None
        if point is not None:
            name = point.find("./gml:name", NAMESPACES)
            latitude, longitude = _coords(point.find("./gml:pos", NAMESPACES))
            station = {"name": name.text if name is not None else None, "latitude": latitude, "longitude": longitude}
        return station, _coverage_rows(root)

    def get_station_coverage(self, lang: str, params: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
        """Return a multipointcoverage query's parameters, and its stations with the parameters each one reported.

        A station that does not measure a parameter reports nothing but NaN for it. Each station is a dict like
        list_stations gives, with "measured", the set of parameters it reported at least once. Its id is an fmisid
        for observations, and for a forecast at fixed points a geoid, which can be negative.
        """
        root = self._xml(feature_url(lang, params))
        fields = [field.attrib["name"] for field in root.iter("{http://www.opengis.net/swe/2.0}field")]
        stations: dict[tuple[str, str], dict[str, Any]] = {}
        for point in root.findall(".//gml:MultiPoint//gml:Point", NAMESPACES):
            fmisid = point.attrib.get(GML_ID, "").removeprefix("point-")
            position = point.find("./gml:pos", NAMESPACES)
            if not fmisid.removeprefix("-").isdigit() or position is None or not position.text:
                continue
            name = point.find("./gml:name", NAMESPACES)
            latitude, longitude = position.text.split()[:2]
            stations[(latitude, longitude)] = {
                "id": fmisid,
                "name": name.text if name is not None and name.text else fmisid,
                "latitude": float(latitude),
                "longitude": float(longitude),
                "measured": set(),
            }
        if not fields or not stations:
            return fields, list(stations.values())

        positions = _text(root, ".//gmlcov:positions").split()
        values = _text(root, ".//gml:doubleOrNilReasonTupleList").split()
        if len(positions) % 3 or len(values) != len(positions) // 3 * len(fields):
            raise FMIException("FMI's response has a different number of times and values")
        # A position is a station's latitude and longitude, written as in its point, and a Unix time.
        for index in range(len(positions) // 3):
            station = stations.get((positions[index * 3], positions[index * 3 + 1]))
            if station is None:
                continue
            for offset, name in enumerate(fields):
                if values[index * len(fields) + offset] != "NaN":
                    station["measured"].add(name)
        return fields, list(stations.values())

    def get_simple_coverage(self, lang: str, params: dict[str, Any]) -> tuple[list[str], dict[tuple[float, float], set[str]]]:
        """Return a ::simple query's parameters, and by position the parameters reported there.

        For the queries FMI publishes in no other form. The simple form says where a value is from by its coordinates
        only, not by the station's id.
        """
        root = self._xml(feature_url(lang, params))
        fields: list[str] = []
        measured: dict[tuple[float, float], set[str]] = {}
        for item in root.findall("./wfs:member/BsWfs:BsWfsElement", NAMESPACES):
            name = _text(item, "./BsWfs:ParameterName")
            if name not in fields:
                fields.append(name)
            latitude, longitude = _coords(item.find("./BsWfs:Location/gml:Point/gml:pos", NAMESPACES))
            if latitude is None or longitude is None:
                continue
            reported = measured.setdefault((latitude, longitude), set())
            if _text(item, "./BsWfs:ParameterValue") != "NaN":
                reported.add(name)
        return fields, measured

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
        root = self._xml(feature_url(lang, params))
        names = {item.text for item in root.findall("./wfs:member/BsWfs:BsWfsElement/BsWfs:ParameterName", NAMESPACES) if item.text}
        return sorted(names, key=str.lower)

    def list_stations(self, lang: str) -> list[dict[str, Any]]:
        """Return the observation stations FMI currently lists as operational.

        Decommissioned stations are simply absent from this response rather
        than carrying an end date, so it doubles as a liveness check.
        """
        root = self._xml(feature_url(lang, {"storedquery_id": API_STATIONS_QUERY_ID}))

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
        return self.get_parameter_descriptions(lang, query_id).get(param_name.lower(), (None, None))[1]
