import logging
from datetime import datetime
from xml.etree import ElementTree
import requests
from requests import ConnectTimeout, RequestException
from .const import API_BASE_URL, USER_AGENT

_LOGGER = logging.getLogger(__name__)


class FMIException(Exception):
    """Base exception for FMI"""


class FMISession:
    _timeout: int
    _fmisid: int
    _step: int

    def __init__(self, fmisid: int, step: int, timeout=20):
        self._timeout = timeout
        self._fmisid = fmisid
        self._step = step

    def query(self, conf: dict[str, str], start_time: datetime, end_time: datetime) -> list[list[str | float]]:

        try:
            url = f"{API_BASE_URL}&storedquery_id={conf['query']}&starttime={start_time}&endtime={end_time}&fmisid={self._fmisid}"
            if conf["is_forecast"] is True:
                url += f"&timestep={self._step}"
            else:
                url += f"&parameters={conf['param']}"
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

                tree = ElementTree.fromstring(response.text)
                for item in tree.findall("./wfs:member/BsWfs:BsWfsElement", namespaces):
                    name = item.find("./BsWfs:ParameterName", namespaces).text
                    if name == conf['param']:
                        value = item.find("./BsWfs:ParameterValue", namespaces).text
                        if value == 'NaN':
                            continue
                        data.append([item.find("./BsWfs:Time", namespaces).text, value])

                return data

        except ConnectTimeout as exception:
            raise FMIException("Timeout error") from exception

        except RequestException as exception:
            raise FMIException(f"Communication error {exception}") from exception
