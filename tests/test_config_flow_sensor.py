"""Adding and changing a sensor through its subentry flow."""

from datetime import timedelta

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER, ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fmi_open_data.const import (
    CONF_FORECAST_HOURS,
    CONF_FORECAST_PAST_HOURS,
    CONF_FORECAST_STEP,
    CONF_LABEL,
    CONF_LANG,
    CONF_NEGATIVE_AS_ZERO,
    CONF_PARAMETER,
    CONF_QUERY_ID,
    CONF_QUERY_LABEL,
    CONF_TARGET,
    CONF_TARGET_TYPE,
    DOMAIN,
    SUBENTRY_SENSOR,
)
from custom_components.fmi_open_data.query_coordinator import build_unique_id
from custom_components.fmi_open_data.session import FMIException

pytestmark = pytest.mark.asyncio

OBSERVATIONS = ["fmi::observations::weather::simple", "Instantaneous Weather Observations"]
FORECAST = ["fmi::forecast::harmonie::surface::point::simple", "Harmonie Surface Point Weather Forecast"]
FORECAST_SENSOR = {
    CONF_LANG: "eng",
    CONF_LABEL: "Kaisaniemi forecast",
    CONF_QUERY_ID: FORECAST[0],
    CONF_QUERY_LABEL: f"{FORECAST[1]} ({FORECAST[0]})",
    CONF_TARGET: "100971",
    CONF_TARGET_TYPE: "fmisid",
    CONF_PARAMETER: "temperature",
    CONF_NEGATIVE_AS_ZERO: False,
    CONF_FORECAST_HOURS: 36,
    CONF_FORECAST_PAST_HOURS: 5,
    CONF_FORECAST_STEP: 30,
}


def _label(query: list[str]) -> str:
    return f"{query[1]} ({query[0]})"


class FakeApi:
    """Stands in for FMISession in the flow and in the sensors it sets up."""

    def __init__(self):
        self.queries_down = False
        self.feature_down = False
        self.has_data = True
        self.feature_params: list[dict] = []

    def list_stored_queries(self, lang, suffix=None):
        if self.queries_down:
            raise FMIException("503 is not valid")
        return [FORECAST, OBSERVATIONS]

    def list_stations_for_query(self, lang, query_id, params):
        return [{"id": "100971", "name": "Helsinki Kaisaniemi", "region": "Helsinki", "latitude": 60.175, "longitude": 24.945}]

    def list_parameters(self, lang, params):
        return ["t2m"]

    def get_parameter_descriptions(self, lang, query_id):
        return {"t2m": ("Air temperature", "°C")}

    def get_feature(self, lang, params, target_param, get_latest, negative_as_zero=False):
        self.feature_params.append(params)
        if self.feature_down:
            raise FMIException("Communication error")
        data = [{"time": dt_util.utcnow() - timedelta(minutes=10), "value": "6.8"}] if self.has_data else []
        return {"latitude": 60.175, "longitude": 24.945, "query_id": params["storedquery_id"], "parameter": target_param, "data": data}

    def get_unit(self, lang, query_id, param_name):
        return "°C"


@pytest.fixture
def api(monkeypatch) -> FakeApi:
    api = FakeApi()
    monkeypatch.setattr("custom_components.fmi_open_data.config_flow.FMISession", lambda *a, **kw: api)
    monkeypatch.setattr("custom_components.fmi_open_data.query_coordinator.FMISession", lambda *a, **kw: api)
    return api


async def _entry(hass: HomeAssistant, subentries: list[ConfigSubentryData] | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, version=3, data={CONF_LANG: "eng"}, subentries_data=subentries or [])
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _to_params(hass: HomeAssistant, entry: MockConfigEntry) -> dict:
    result = await hass.config_entries.subentries.async_init((entry.entry_id, SUBENTRY_SENSOR), context={"source": SOURCE_USER})
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {CONF_QUERY_LABEL: _label(OBSERVATIONS)})
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {CONF_TARGET: "100971"})
    assert result["step_id"] == "params"
    return result


async def test_adding_a_sensor(hass: HomeAssistant, api: FakeApi):
    entry = await _entry(hass)

    result = await _to_params(hass, entry)
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {CONF_PARAMETER: "t2m", CONF_NEGATIVE_AS_ZERO: False})
    assert result["step_id"] == "name"
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {CONF_LABEL: "Helsinki Kaisaniemi Air temperature"})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    assert subentry.data[CONF_QUERY_ID] == OBSERVATIONS[0]
    assert subentry.data[CONF_TARGET_TYPE] == "fmisid"
    # The flow tried the sensor with the same query the sensor makes.
    assert api.feature_params[0]["parameters"] == "t2m"
    assert api.feature_params[0]["timestep"] is None


async def test_a_sensor_without_data_is_not_added(hass: HomeAssistant, api: FakeApi):
    entry = await _entry(hass)
    api.has_data = False

    result = await _to_params(hass, entry)
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {CONF_PARAMETER: "t2m", CONF_NEGATIVE_AS_ZERO: False})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_data"}


async def test_fmi_down_while_trying_the_sensor(hass: HomeAssistant, api: FakeApi):
    entry = await _entry(hass)
    api.feature_down = True

    result = await _to_params(hass, entry)
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {CONF_PARAMETER: "t2m", CONF_NEGATIVE_AS_ZERO: False})

    assert result["errors"] == {"base": "connection_problem"}


async def test_fmi_down_while_listing_queries(hass: HomeAssistant, api: FakeApi):
    entry = await _entry(hass)
    api.queries_down = True

    result = await hass.config_entries.subentries.async_init((entry.entry_id, SUBENTRY_SENSOR), context={"source": SOURCE_USER})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_a_forecast_sensor_changed_to_observations_loses_its_forecast_settings(hass: HomeAssistant, api: FakeApi):
    entry = await _entry(
        hass,
        [
            ConfigSubentryData(
                data=FORECAST_SENSOR,
                subentry_type=SUBENTRY_SENSOR,
                title=FORECAST_SENSOR[CONF_LABEL],
                unique_id=build_unique_id(FORECAST_SENSOR),
            )
        ],
    )
    [subentry] = entry.subentries.values()

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_SENSOR), context={"source": SOURCE_RECONFIGURE, "subentry_id": subentry.subentry_id}
    )
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {CONF_QUERY_LABEL: _label(OBSERVATIONS)})
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {CONF_TARGET: "100971"})
    api.feature_params.clear()
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {CONF_PARAMETER: "t2m", CONF_NEGATIVE_AS_ZERO: False})
    await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    data = entry.subentries[subentry.subentry_id].data
    assert data[CONF_QUERY_ID] == OBSERVATIONS[0]
    assert not {CONF_FORECAST_HOURS, CONF_FORECAST_PAST_HOURS, CONF_FORECAST_STEP} & set(data)
    assert all(params["timestep"] is None for params in api.feature_params)
