import logging
from datetime import UTC, datetime
from typing import Any
from xml.etree import ElementTree

import requests
from requests import ConnectTimeout, RequestException

from .const import (
    API_DESCRIBE_STORED_QUERIES_URL,
    API_FINLAND_BBOX,
    API_GET_FEATURE_URL,
    API_GET_PARAMS_URL,
    API_STATIONS_QUERY_ID,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)


class FMIException(Exception):
    """Base exception for FMI"""


def normalize_value(value: str, negative_as_zero: bool) -> str:
    # FMI reports "no measurable precipitation" as -1 rather than 0.
    if negative_as_zero:
        try:
            if float(value) == -1:
                return "0.0"
        except (TypeError, ValueError):
            pass
    return value


class FMISession:
    _timeout: int

    def __init__(self, timeout=20):
        self._timeout = timeout

    def get_document(self, url: str) -> bytes:
        """Download a document as it is, such as the warning feed or one warning in it."""

        try:
            _LOGGER.debug(f"Downloading from FMI (url={url})")

            response = requests.get(
                url=url,
                headers={"User-Agent": USER_AGENT},
                timeout=self._timeout,
            )

            if response.status_code != 200:
                raise FMIException(f"{response.status_code} is not valid")

            return response.content

        except ConnectTimeout as exception:
            raise FMIException("Timeout error") from exception

        except RequestException as exception:
            raise FMIException(f"Communication error {exception}") from exception

    def get_feature(self, lang: str, params: dict[str, str], target_param: str, get_latest: bool, negative_as_zero: bool = False) -> Any:

        try:
            url = API_GET_FEATURE_URL.replace("${lang}", lang)
            for key in params.keys():
                if params[key] is not None and params[key] != "":
                    url += f"&{key}={params[key]}"

            _LOGGER.debug(f"Querying data from FMI API (url={url})")

            response = requests.get(
                url=url,
                headers={"User-Agent": USER_AGENT},
                timeout=self._timeout,
            )

            if response.status_code != 200:
                raise FMIException(f"{response.status_code} is not valid")

            else:
                result = {
                    "latitude": None,
                    "longitude": None,
                    "query_id": params["storedquery_id"],
                    "parameter": target_param,
                    "unit": None,
                    "data": [],
                }

                namespaces = {
                    "wfs": "http://www.opengis.net/wfs/2.0",
                    "gml": "http://www.opengis.net/gml/3.2",
                    "BsWfs": "http://xml.fmi.fi/schema/wfs/2.0",
                    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
                }

                tree = ElementTree.fromstring(response.text)

                for item in tree.findall("./wfs:member/BsWfs:BsWfsElement", namespaces):
                    if result["latitude"] is None or result["longitude"] is None:
                        coords = item.find("./BsWfs:Location/gml:Point/gml:pos", namespaces).text.rstrip().split(" ")
                        result["latitude"] = coords[0]
                        result["longitude"] = coords[1]

                    name = item.find("./BsWfs:ParameterName", namespaces).text

                    if name.lower() != target_param.lower():
                        continue

                    time = datetime.fromisoformat(item.find("./BsWfs:Time", namespaces).text)
                    if time.tzinfo is None:
                        # FMI reports UTC; make it explicit so the values stay
                        # comparable with timezone-aware datetimes downstream.
                        time = time.replace(tzinfo=UTC)
                    value = item.find("./BsWfs:ParameterValue", namespaces).text

                    if value != "NaN":
                        value = normalize_value(value, negative_as_zero)
                        if get_latest and (len(result["data"]) == 0 or time > result["data"][0]["time"]):
                            result["data"] = []
                        result["data"].append({"time": time, "value": value})

                result["unit"] = self.get_unit_type(target_param, lang, params["storedquery_id"])

                return result

        except ConnectTimeout as exception:
            raise FMIException("Timeout error") from exception

        except RequestException as exception:
            raise FMIException(f"Communication error {exception}") from exception

    def list_stored_queries(self, lang: str, suffix: str = None) -> list[list[str]]:

        try:
            url = API_DESCRIBE_STORED_QUERIES_URL.replace("${lang}", lang)
            response = requests.get(
                url=url,
                headers={"User-Agent": USER_AGENT},
                timeout=self._timeout,
            )

            if response.status_code != 200:
                raise FMIException(f"{response.status_code} is not valid")

            else:
                data = []

                namespaces = {
                    "wfs": "http://www.opengis.net/wfs/2.0",
                    "gml": "http://www.opengis.net/gml/3.2",
                    "BsWfs": "http://xml.fmi.fi/schema/wfs/2.0",
                    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
                }

                root = ElementTree.fromstring(response.text)
                for item in root.findall("./wfs:StoredQueryDescription", namespaces):
                    if suffix is None or item.attrib["id"].endswith(suffix):
                        for param in item.findall("./wfs:Parameter", namespaces):
                            if param.attrib["name"] == "fmisid":
                                data.append([item.attrib["id"], item.find("./wfs:Title", namespaces).text])
                                break

                def sort_query(val: list):
                    return val[1]

                data.sort(key=sort_query)

                return data

        except ConnectTimeout as exception:
            raise FMIException("Timeout error") from exception

        except RequestException as exception:
            raise FMIException(f"Communication error {exception}") from exception

    def list_parameters(self, lang: str, params: dict[str, str]) -> list[str]:
        """Return the distinct parameter names a query actually reports.

        This is the same question the runtime coordinator asks when it filters
        the response, so what the config flow offers is exactly what a sensor
        will be able to read.
        """

        try:
            url = API_GET_FEATURE_URL.replace("${lang}", lang)
            for key in params.keys():
                if params[key] is not None and params[key] != "":
                    url += f"&{key}={params[key]}"

            _LOGGER.debug(f"Listing available parameters from FMI API (url={url})")

            response = requests.get(
                url=url,
                headers={"User-Agent": USER_AGENT},
                timeout=self._timeout,
            )

            if response.status_code != 200:
                raise FMIException(f"{response.status_code} is not valid")

            namespaces = {
                "wfs": "http://www.opengis.net/wfs/2.0",
                "gml": "http://www.opengis.net/gml/3.2",
                "BsWfs": "http://xml.fmi.fi/schema/wfs/2.0",
                "xsi": "http://www.w3.org/2001/XMLSchema-instance",
            }

            tree = ElementTree.fromstring(response.text)
            names = {
                item.text
                for item in tree.findall("./wfs:member/BsWfs:BsWfsElement/BsWfs:ParameterName", namespaces)
                if item.text is not None
            }

            return sorted(names, key=str.lower)

        except ConnectTimeout as exception:
            raise FMIException("Timeout error") from exception

        except RequestException as exception:
            raise FMIException(f"Communication error {exception}") from exception

    def list_stations_for_query(self, lang: str, query_id: str, params: dict[str, str]) -> list[dict[str, Any]]:
        """Return only the stations that actually serve a given stored query.

        The multipointcoverage twin of a query describes the locations it
        covers, which is exactly the set a sensor could read. Returns an empty
        list when the query has no such twin, so callers can fall back.
        """

        coverage_id = query_id.replace("::simple", "::multipointcoverage")

        if coverage_id == query_id:
            return []

        try:
            url = API_GET_FEATURE_URL.replace("${lang}", lang)
            for key in params.keys():
                if params[key] is not None and params[key] != "":
                    url += f"&{key}={params[key]}"
            url += f"&storedquery_id={coverage_id}&bbox={API_FINLAND_BBOX}"

            _LOGGER.debug(f"Listing stations for query from FMI API (url={url})")

            response = requests.get(
                url=url,
                headers={"User-Agent": USER_AGENT},
                timeout=self._timeout,
            )

            if response.status_code != 200:
                raise FMIException(f"{response.status_code} is not valid")

            namespaces = {"gml": "http://www.opengis.net/gml/3.2", "target": "http://xml.fmi.fi/namespace/om/atmosphericfeatures/1.1"}

            root = ElementTree.fromstring(response.text)

            regions = {}
            for location in root.findall(".//target:Location", namespaces):
                identifier = location.find("./gml:identifier", namespaces)
                region = location.find("./target:region", namespaces)
                if identifier is not None and identifier.text:
                    regions[identifier.text] = region.text if region is not None else None

            stations = []
            for point in root.findall(".//gml:MultiPoint/gml:pointMember/gml:Point", namespaces):
                identifier = point.attrib.get("{http://www.opengis.net/gml/3.2}id", "")
                fmisid = identifier.removeprefix("point-")
                name = point.find("./gml:name", namespaces)
                position = point.find("./gml:pos", namespaces)
                coords = position.text.rstrip().split(" ") if position is not None and position.text else []

                if not fmisid.isdigit():
                    continue

                stations.append(
                    {
                        "id": fmisid,
                        "name": name.text if name is not None and name.text else fmisid,
                        "region": regions.get(fmisid),
                        "latitude": float(coords[0]) if len(coords) > 1 else None,
                        "longitude": float(coords[1]) if len(coords) > 1 else None,
                    }
                )

            return stations

        except ConnectTimeout as exception:
            raise FMIException("Timeout error") from exception

        except RequestException as exception:
            raise FMIException(f"Communication error {exception}") from exception

    def list_stations(self, lang: str) -> list[dict[str, Any]]:
        """Return the observation stations FMI currently lists as operational.

        Decommissioned stations are simply absent from this response rather
        than carrying an end date, so it doubles as a liveness check.
        """

        try:
            url = f"{API_GET_FEATURE_URL.replace('${lang}', lang)}&storedquery_id={API_STATIONS_QUERY_ID}"

            _LOGGER.debug(f"Listing stations from FMI API (url={url})")

            response = requests.get(
                url=url,
                headers={"User-Agent": USER_AGENT},
                timeout=self._timeout,
            )

            if response.status_code != 200:
                raise FMIException(f"{response.status_code} is not valid")

            namespaces = {
                "wfs": "http://www.opengis.net/wfs/2.0",
                "gml": "http://www.opengis.net/gml/3.2",
                "ef": "http://inspire.ec.europa.eu/schemas/ef/4.0",
                "base": "http://inspire.ec.europa.eu/schemas/base/3.3",
            }

            stations = []
            root = ElementTree.fromstring(response.text)

            for facility in root.findall("./wfs:member/ef:EnvironmentalMonitoringFacility", namespaces):
                identifier = facility.find(".//base:Identifier/base:localId", namespaces)
                position = facility.find(".//ef:representativePoint/gml:Point/gml:pos", namespaces)

                if identifier is None or identifier.text is None:
                    continue

                # gml:name repeats as [station, -id, <optional WMO/ICAO codes>,
                # municipality, country], so the municipality is second from last.
                names = [name.text for name in facility.findall("./gml:name", namespaces) if name.text]
                coords = position.text.rstrip().split(" ") if position is not None and position.text else []

                stations.append(
                    {
                        "id": identifier.text,
                        "name": names[0] if names else identifier.text,
                        "region": names[-2] if len(names) > 2 else None,
                        "latitude": float(coords[0]) if len(coords) > 1 else None,
                        "longitude": float(coords[1]) if len(coords) > 1 else None,
                    }
                )

            return stations

        except ConnectTimeout as exception:
            raise FMIException("Timeout error") from exception

        except RequestException as exception:
            raise FMIException(f"Communication error {exception}") from exception

    def get_parameter_descriptions(self, lang: str, query_id: str) -> dict[str, tuple[str, str]]:
        """Return {parameter name: (label, unit)} for the query's property set."""

        try:
            url = API_GET_PARAMS_URL.replace("${lang}", lang).replace(
                "${property}", "forecast" if "forecast::" in query_id else "observation"
            )

            response = requests.get(
                url=url,
                headers={"User-Agent": USER_AGENT},
                timeout=self._timeout,
            )

            if response.status_code != 200:
                raise FMIException(f"{response.status_code} is not valid")

            namespaces = {"gml": "http://www.opengis.net/gml/3.2", "omop": "http://inspire.ec.europa.eu/schemas/omop/2.9"}

            result = {}
            root = ElementTree.fromstring(response.text)

            for component in root.findall("./omop:component", namespaces):
                prop = component.find("./omop:ObservableProperty", namespaces)
                name = prop.attrib.get("{http://www.opengis.net/gml/3.2}id")

                if name is None:
                    continue

                label = prop.find("./omop:label", namespaces)
                uom = prop.find("./omop:uom", namespaces)
                unit = uom.attrib.get("uom") if uom is not None else None

                result[name] = (label.text if label is not None else None, unit.replace("degC", "°C") if unit is not None else None)

            return result

        except ConnectTimeout as exception:
            raise FMIException("Timeout error") from exception

        except RequestException as exception:
            raise FMIException(f"Communication error {exception}") from exception

    def get_unit_type(self, param_name: str, lang: str, query_id: str) -> str:

        try:
            url = API_GET_PARAMS_URL.replace("${lang}", lang).replace(
                "${property}", "forecast" if "forecast::" in query_id else "observation"
            )
            response = requests.get(
                url=url,
                headers={"User-Agent": USER_AGENT},
                timeout=self._timeout,
            )

            if response.status_code != 200:
                raise FMIException(f"{response.status_code} is not valid")

            else:
                namespaces = {
                    "wfs": "http://www.opengis.net/wfs/2.0",
                    "gml": "http://www.opengis.net/gml/3.2",
                    "BsWfs": "http://xml.fmi.fi/schema/wfs/2.0",
                    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
                    "omop": "http://inspire.ec.europa.eu/schemas/omop/2.9",
                }

                unit = None

                if query_id.startswith("stuk::"):
                    if "::air" in query_id:
                        unit = "µBq/m³"
                    elif "::external-radiation" in query_id:
                        unit = "µSv/h"

                else:
                    root = ElementTree.fromstring(response.text)
                    for component in root.findall("./omop:component", namespaces):
                        prop = component.find("./omop:ObservableProperty", namespaces)
                        if prop.attrib["{http://www.opengis.net/gml/3.2}id"] == param_name.lower():
                            unit = prop.find("./omop:uom", namespaces).attrib["uom"]
                            break

                    if unit is not None:
                        unit = unit.replace("degC", "°C")

                return unit

        except ConnectTimeout as exception:
            raise FMIException("Timeout error") from exception

        except RequestException as exception:
            raise FMIException(f"Communication error {exception}") from exception
