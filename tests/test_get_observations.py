"""The get_observations action: what it asks FMI, what it returns, and how FMI's refusals reach the user."""

from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fmi_open_data.const import CONF_LANG, DOMAIN
from custom_components.fmi_open_data.session import FMIException, FMINoData, FMIRefused, FMISession

# A real response for Lappeenranta airport (fmisid 101237): seven hourly rows from 2026-10-15T10:00Z.
OBSERVATIONS = (Path(__file__).parent / "fixtures" / "fmi_observations.xml").read_bytes()
NOW = "2026-10-15T16:30:00+00:00"


class FakeSession(FMISession):
    def __init__(self, failure: FMIException | None = None):
        super().__init__()
        self.failure = failure
        self.urls: list[str] = []

    def get_document(self, url: str) -> bytes:
        self.urls.append(url)
        if self.failure is not None:
            raise self.failure
        return OBSERVATIONS

    def asked(self) -> dict[str, str]:
        return {key: values[0] for key, values in parse_qs(urlsplit(self.urls[-1]).query).items()}


@pytest.fixture
async def entry(hass: HomeAssistant) -> MockConfigEntry:
    await hass.config.async_set_time_zone("Europe/Helsinki")
    entry = MockConfigEntry(domain=DOMAIN, version=3, data={CONF_LANG: "fin"})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _use(monkeypatch, session: FakeSession) -> FakeSession:
    monkeypatch.setattr("custom_components.fmi_open_data.services.FMISession", lambda *a, **kw: session)
    return session


async def _call(hass: HomeAssistant, **data) -> dict:
    data = {"query": "fmi::observations::weather::hourly", "station": 101237, "parameters": ["TA_PT1H_AVG"], **data}
    return await hass.services.async_call(DOMAIN, "get_observations", data, blocking=True, return_response=True)


async def test_the_station_and_one_row_per_hour(hass: HomeAssistant, entry, monkeypatch, freezer):
    freezer.move_to(NOW)
    session = _use(monkeypatch, FakeSession())
    response = await _call(hass, parameters=["TA_PT1H_AVG", "PRA_PT1H_ACC", "WAWA_PT1H_RANK"])

    assert response["query"] == "fmi::observations::weather::hourly"
    assert response["station"] == {"fmisid": 101237, "name": "Lappeenranta lentoasema", "latitude": 61.0403, "longitude": 28.12916}
    assert len(response["observations"]) == 7
    assert response["observations"][0] == {
        "time": "2026-10-15T10:00:00+00:00",
        "TA_PT1H_AVG": 10.2,
        "PRA_PT1H_ACC": 0.0,
        "WAWA_PT1H_RANK": 0.0,
    }
    asked = session.asked()
    assert asked["storedquery_id"] == "fmi::observations::weather::hourly::multipointcoverage"
    assert asked["fmisid"] == "101237"
    assert asked["parameters"] == "TA_PT1H_AVG,PRA_PT1H_ACC,WAWA_PT1H_RANK"
    assert asked["starttime"] == "2026-10-14 16:30:00"
    assert asked["endtime"] == "2026-10-15 16:30:00"
    assert "timestep" not in asked


async def test_a_time_without_a_zone_is_local_and_a_format_suffix_is_ignored(hass: HomeAssistant, entry, monkeypatch):
    session = _use(monkeypatch, FakeSession())
    await _call(
        hass, query="fmi::observations::weather::hourly::simple", start="2026-10-01 00:00:00", end="2026-10-08T00:00:00+00:00", timestep=60
    )

    asked = session.asked()
    assert asked["storedquery_id"] == "fmi::observations::weather::hourly::multipointcoverage"
    assert asked["starttime"] == "2026-09-30 21:00:00"
    assert asked["endtime"] == "2026-10-08 00:00:00"
    assert asked["timestep"] == "60"


@pytest.mark.parametrize(
    ("data", "key"),
    [
        ({"query": "fmi::forecast::edited::weather::scandinavia::point"}, "not_an_observation_query"),
        ({"start": "2026-10-02T00:00:00+00:00", "end": "2026-10-01T00:00:00+00:00"}, "start_after_end"),
    ],
)
async def test_a_request_that_cannot_be_right_is_not_sent(hass: HomeAssistant, entry, monkeypatch, data: dict, key: str):
    session = _use(monkeypatch, FakeSession())
    with pytest.raises(ServiceValidationError) as error:
        await _call(hass, **data)

    assert error.value.translation_key == key
    assert not session.urls


async def test_fmis_own_reason_reaches_the_user(hass: HomeAssistant, entry, monkeypatch):
    _use(monkeypatch, FakeSession(FMIRefused("Too long time interval requested!")))
    with pytest.raises(ServiceValidationError) as error:
        await _call(hass)

    assert error.value.translation_key == "refused"
    assert error.value.translation_placeholders == {"message": "Too long time interval requested!"}


@pytest.mark.parametrize(
    ("failure", "kind", "key"),
    [
        (FMINoData("No data available for '0'!"), ServiceValidationError, "no_observations"),
        (FMIException("Timeout error"), HomeAssistantError, "connection_problem"),
    ],
)
async def test_no_data_and_no_connection(hass: HomeAssistant, entry, monkeypatch, failure, kind, key: str):
    _use(monkeypatch, FakeSession(failure))
    with pytest.raises(kind) as error:
        await _call(hass)

    assert error.value.translation_key == key


async def test_a_range_without_observations_is_an_empty_list(hass: HomeAssistant, entry, monkeypatch):
    # A daily query over part of a day: FMI answers 200 with nothing in it, not even the station.
    session = _use(monkeypatch, FakeSession())
    session.get_document = lambda url: (
        b'<wfs:FeatureCollection numberMatched="0" numberReturned="0" xmlns:wfs="http://www.opengis.net/wfs/2.0"></wfs:FeatureCollection>'
    )
    response = await _call(hass, query="fmi::observations::weather::daily", parameters=["tday"])

    assert response["station"] == {"fmisid": 101237}
    assert response["observations"] == []


@pytest.mark.parametrize(
    "data",
    [
        {"parameters": ["t2m#x"]},
        {"parameters": ["t2m&starttime=2000-01-01"]},
        {"query": "fmi::observations::weather::hourly&fmisid=1"},
        {"query": "observations"},
    ],
)
async def test_text_that_would_change_fmis_url_is_refused(hass: HomeAssistant, entry, monkeypatch, data: dict):
    session = _use(monkeypatch, FakeSession())
    with pytest.raises(vol.Invalid):
        await _call(hass, **data)
    assert not session.urls


async def test_the_action_needs_the_integration_loaded(hass: HomeAssistant, entry, monkeypatch):
    _use(monkeypatch, FakeSession())
    await hass.config_entries.async_unload(entry.entry_id)

    with pytest.raises(ServiceValidationError) as error:
        await _call(hass)
    assert error.value.translation_key == "not_loaded"


def test_fmis_reason_is_read_from_an_http_400(monkeypatch):
    responses = {
        # As FMI sends it: the reason, the limit and an echo of the request, with empty texts between them.
        "long": SimpleNamespace(
            status_code=400,
            content=b"<ExceptionText>Too long time interval requested!</ExceptionText><ExceptionText>\n</ExceptionText>"
            b"<ExceptionText>No more than 168.000000 hours allowed.</ExceptionText><ExceptionText>\n</ExceptionText>"
            b"<ExceptionText>URI: /wfs?fmisid=101237&amp;parameters=t2m</ExceptionText>",
        ),
        "bogus": SimpleNamespace(status_code=400, content=b"<ExceptionText>Unrecognized parameter &apos;Bogus&apos;</ExceptionText>"),
        "bare": SimpleNamespace(status_code=400, content=b"Bad Request"),
    }
    monkeypatch.setattr("custom_components.fmi_open_data.session.requests.get", lambda url, **kw: responses[url])

    for url, message in [
        ("long", "Too long time interval requested! No more than 168.000000 hours allowed."),
        ("bogus", "Unrecognized parameter 'Bogus'"),
        ("bare", "400 is not valid"),
    ]:
        with pytest.raises(FMIRefused) as refused:
            FMISession().get_document(url)
        assert str(refused.value) == message
        assert not isinstance(refused.value, FMINoData)
