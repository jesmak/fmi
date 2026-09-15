"""Adding and changing a warnings entry through the config flow."""
import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.fmi.const import (
    CONF_ENTRY_TYPE,
    CONF_LABEL,
    CONF_LOCATION,
    CONF_WARNING_TYPES,
    DOMAIN,
    ENTRY_TYPE_WARNINGS,
)
from test_warning_entities import SEVERAL_AREAS, FakeApi

pytestmark = pytest.mark.asyncio

HANKO = {"latitude": 59.823, "longitude": 22.968, "radius": 2000}
FORM = {CONF_LOCATION: HANKO, CONF_WARNING_TYPES: ["seaWind", "seaWaveHeight"], CONF_LABEL: "Varoitukset Hanko"}


@pytest.fixture(autouse=True)
def fake_feed(monkeypatch):
    monkeypatch.setattr("custom_components.fmi.warning_coordinator.FMISession", lambda *a, **kw: FakeApi([SEVERAL_AREAS]))


async def _warnings_form(hass: HomeAssistant) -> dict:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"language": "fin"})
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["query", "warnings"]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "warnings"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "warnings"
    return result


async def test_adding_a_warnings_entry(hass: HomeAssistant):
    result = await _warnings_form(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Varoitukset Hanko"
    assert result["data"][CONF_ENTRY_TYPE] == ENTRY_TYPE_WARNINGS
    assert result["data"][CONF_LOCATION] == HANKO
    assert hass.states.get("sensor.fmi_varoitukset_hanko") is not None
    assert hass.states.get("event.fmi_varoitukset_hanko") is not None


async def test_at_least_one_warning_type_is_needed(hass: HomeAssistant):
    result = await _warnings_form(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**FORM, CONF_WARNING_TYPES: []})

    assert result["errors"] == {CONF_WARNING_TYPES: "no_warning_types"}


async def test_the_same_place_and_types_cannot_be_added_twice(hass: HomeAssistant):
    result = await _warnings_form(hass)
    await hass.config_entries.flow.async_configure(result["flow_id"], FORM)
    await hass.async_block_till_done()

    result = await _warnings_form(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**FORM, CONF_LABEL: "Toinen"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfiguring_a_warnings_entry(hass: HomeAssistant):
    result = await _warnings_form(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM)
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure_warnings"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**FORM, CONF_LOCATION: {**HANKO, "radius": 5000}})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_LOCATION]["radius"] == 5000
    assert hass.states.get("sensor.fmi_varoitukset_hanko") is not None
