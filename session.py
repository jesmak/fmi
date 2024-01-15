import logging
from typing import Any
from xml.etree import ElementTree
import requests
from dateutil.parser import isoparse
from requests import ConnectTimeout, RequestException
from .const import USER_AGENT, API_DESCRIBE_STORED_QUERIES_URL, API_GET_FEATURE_URL, API_GET_PARAMS_URL

_LOGGER = logging.getLogger(__name__)


class FMIException(Exception):
    """Base exception for FMI"""


class FMISession:
    _timeout: int

    def __init__(self, timeout=20):
        self._timeout = timeout

    def get_feature(self, lang: str, params: dict[str, str], target_param: str, get_latest: bool) -> Any:

        try:
            url = API_GET_FEATURE_URL.replace("${lang}", lang)
            for key in params.keys():
                if params[key] is not None and params[key] != "":
                    url += f"&{key}={params[key]}"

            _LOGGER.debug(f"Querying data from FMI API (url={url})")

            response = requests.get(
                url=url,
                headers={
                    "User-Agent": USER_AGENT
                },
                timeout=self._timeout,
            )

            if response.status_code != 200:
                raise FMIException(f"{response.status_code} is not valid")

            else:
                result = {"latitude": None, "longitude": None, "query_id": params["storedquery_id"],
                          "parameter": target_param, "unit": None, "data": []}

                namespaces = {
                    "wfs": "http://www.opengis.net/wfs/2.0",
                    "gml": "http://www.opengis.net/gml/3.2",
                    "BsWfs": "http://xml.fmi.fi/schema/wfs/2.0",
                    "xsi": "http://www.w3.org/2001/XMLSchema-instance"
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

                    time = isoparse(item.find("./BsWfs:Time", namespaces).text)
                    value = item.find("./BsWfs:ParameterValue", namespaces).text

                    if value != "NaN":
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
                headers={
                    "User-Agent": USER_AGENT
                },
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
                    "xsi": "http://www.w3.org/2001/XMLSchema-instance"
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

    def get_unit_type(self, param_name: str, lang: str, query_id: str) -> str:

        try:
            url = API_GET_PARAMS_URL.replace("${lang}", lang).replace("${property}",
                                                                      "forecast" if "forecast::" in query_id else "observation")
            response = requests.get(
                url=url,
                headers={
                    "User-Agent": USER_AGENT
                },
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
                    "omop": "http://inspire.ec.europa.eu/schemas/omop/2.9"
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
                        if prop.attrib['{http://www.opengis.net/gml/3.2}id'] == param_name.lower():
                            unit = prop.find("./omop:uom", namespaces).attrib["uom"]
                            break

                    if unit is not None:
                        unit = unit.replace("degC", "°C")

                return unit

        except ConnectTimeout as exception:
            raise FMIException("Timeout error") from exception

        except RequestException as exception:
            raise FMIException(f"Communication error {exception}") from exception
