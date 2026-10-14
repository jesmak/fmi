"""Adding and changing a warnings place through its subentry flow."""

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from test_warning_entities import SEVERAL_AREAS, FakeApi

from custom_components.fmi_open_data.const import (
    CONF_LABEL,
    CONF_LANG,
    CONF_LOCATION,
    CONF_WARNING_TYPES,
    DOMAIN,
    SUBENTRY_WARNINGS,
)

pytestmark = pytest.mark.asyncio

HANKO = {"latitude": 59.823, "longitude": 22.968, "radius": 2000}
# The form uses lower-case keys for the warning types; subentries store FMI's names for them.
FORM = {CONF_LOCATION: HANKO, CONF_WARNING_TYPES: ["sea_wind", "sea_wave_height"], CONF_LABEL: "Varoitukset Hanko"}


@pytest.fixture(autouse=True)
def fake_feed(monkeypatch):
    monkeypatch.setattr("custom_components.fmi_open_data.warning_coordinator.FMISession", lambda *a, **kw: FakeApi([SEVERAL_AREAS]))


@pytest.fixture
async def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, version=3, data={CONF_LANG: "fin"})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _warnings_form(hass: HomeAssistant, entry: MockConfigEntry) -> dict:
    result = await hass.config_entries.subentries.async_init((entry.entry_id, SUBENTRY_WARNINGS), context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


async def _add(hass: HomeAssistant, entry: MockConfigEntry, form: dict) -> dict:
    result = await _warnings_form(hass, entry)
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], form)
    await hass.async_block_till_done()
    return result


async def test_adding_a_warnings_place(hass: HomeAssistant, entry: MockConfigEntry):
    result = await _add(hass, entry, FORM)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    assert subentry.title == "Varoitukset Hanko"
    assert subentry.subentry_type == SUBENTRY_WARNINGS
    assert subentry.data[CONF_LOCATION] == HANKO
    assert subentry.data[CONF_WARNING_TYPES] == ["seaWind", "seaWaveHeight"]
    # The language comes from the integration's settings.
    assert subentry.data[CONF_LANG] == "fin"
    assert hass.states.get("sensor.fmi_varoitukset_hanko") is not None
    assert hass.states.get("event.fmi_varoitukset_hanko") is not None


async def test_at_least_one_warning_type_is_needed(hass: HomeAssistant, entry: MockConfigEntry):
    result = await _warnings_form(hass, entry)
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {**FORM, CONF_WARNING_TYPES: []})

    assert result["errors"] == {CONF_WARNING_TYPES: "no_warning_types"}


async def test_the_same_place_and_types_cannot_be_added_twice(hass: HomeAssistant, entry: MockConfigEntry):
    await _add(hass, entry, FORM)
    result = await _add(hass, entry, {**FORM, CONF_LABEL: "Toinen"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(entry.subentries) == 1


async def test_reconfiguring_a_warnings_place(hass: HomeAssistant, entry: MockConfigEntry):
    await _add(hass, entry, FORM)
    [subentry] = entry.subentries.values()

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_WARNINGS), context={"source": SOURCE_RECONFIGURE, "subentry_id": subentry.subentry_id}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    warning_types = next(key for key in result["data_schema"].schema if key == CONF_WARNING_TYPES)
    assert warning_types.description["suggested_value"] == ["sea_wind", "sea_wave_height"]

    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {**FORM, CONF_LOCATION: {**HANKO, "radius": 5000}})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.subentries[subentry.subentry_id].data[CONF_LOCATION]["radius"] == 5000
    assert entry.subentries[subentry.subentry_id].data[CONF_WARNING_TYPES] == ["seaWind", "seaWaveHeight"]
    assert hass.states.get("sensor.fmi_varoitukset_hanko").attributes["radius"] == 5000
