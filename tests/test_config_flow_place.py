"""Adding and changing a place: its weather forecast, the warnings followed there, or both."""

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from test_warning_entities import SEVERAL_AREAS
from test_warning_entities import FakeApi as FakeFeed
from test_weather import NOW, TAMPERE, FakeSession

from custom_components.fmi_open_data.const import (
    CONF_LABEL,
    CONF_LANG,
    CONF_LOCATION,
    CONF_STRUCTURE,
    CONF_WARNING_TYPES,
    CONF_WEATHER,
    DOMAIN,
    STRUCTURE_VERSION,
    SUBENTRY_PLACE,
    WARNING_TYPE_KEYS,
)

HANKO = {"latitude": 59.823, "longitude": 22.968, "radius": 2000}
# The form uses lower-case keys for the warning types. Subentries store FMI's names for them.
FORM = {CONF_LOCATION: {**TAMPERE, "radius": 1000}, CONF_LABEL: "Tampere", CONF_WEATHER: True, CONF_WARNING_TYPES: ["wind", "sea_wind"]}


@pytest.fixture
async def entry(hass: HomeAssistant, monkeypatch, freezer) -> MockConfigEntry:
    freezer.move_to(NOW)
    await hass.config.async_set_time_zone("Europe/Helsinki")
    monkeypatch.setattr("custom_components.fmi_open_data.warning_coordinator.FMISession", lambda *a, **kw: FakeFeed([SEVERAL_AREAS]))
    monkeypatch.setattr("custom_components.fmi_open_data.weather_coordinator.FMISession", lambda *a, **kw: FakeSession())
    entry = MockConfigEntry(domain=DOMAIN, version=3, data={CONF_LANG: "fin", CONF_STRUCTURE: STRUCTURE_VERSION})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _add(hass: HomeAssistant, entry: MockConfigEntry, form: dict) -> dict:
    result = await hass.config_entries.subentries.async_init((entry.entry_id, SUBENTRY_PLACE), context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], form)
    await hass.async_block_till_done()
    return result


async def test_adding_a_place_with_its_forecast_and_warnings(hass: HomeAssistant, entry: MockConfigEntry):
    result = await _add(hass, entry, FORM)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    assert subentry.title == "Tampere"
    assert subentry.data[CONF_WARNING_TYPES] == ["wind", "seaWind"]
    assert subentry.unique_id == "place_61.4981_23.7608"
    [device] = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert device.name == "Tampere"
    assert hass.states.get("weather.tampere").state == "cloudy"
    assert hass.states.get("sensor.tampere_warning_level") is not None
    assert hass.states.get("event.tampere_warning") is not None


async def test_a_new_place_is_named_after_home_and_follows_everything(hass: HomeAssistant, entry: MockConfigEntry):
    result = await hass.config_entries.subentries.async_init((entry.entry_id, SUBENTRY_PLACE), context={"source": SOURCE_USER})

    suggested = {str(key): key.description["suggested_value"] for key in result["data_schema"].schema}
    assert suggested[CONF_LABEL] == hass.config.location_name
    assert suggested[CONF_WEATHER] is True
    assert suggested[CONF_WARNING_TYPES] == list(WARNING_TYPE_KEYS.values())


async def test_a_place_follows_something(hass: HomeAssistant, entry: MockConfigEntry):
    result = await _add(hass, entry, {**FORM, CONF_WEATHER: False, CONF_WARNING_TYPES: []})

    assert result["errors"] == {"base": "nothing_followed"}
    assert not entry.subentries


async def test_warnings_alone_need_no_forecast(hass: HomeAssistant, entry: MockConfigEntry, monkeypatch):
    monkeypatch.setattr("custom_components.fmi_open_data.weather_coordinator.FMISession", lambda *a, **kw: FakeSession(no_data=True))
    result = await _add(hass, entry, {**FORM, CONF_LOCATION: HANKO, CONF_WEATHER: False})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert hass.states.get("weather.tampere") is None


@pytest.mark.parametrize(
    ("session", "error"), [(FakeSession(no_data=True), "no_forecast"), (FakeSession(failing=True), "connection_problem")]
)
async def test_a_place_without_a_forecast_is_not_added(hass: HomeAssistant, entry: MockConfigEntry, monkeypatch, session, error):
    monkeypatch.setattr("custom_components.fmi_open_data.weather_coordinator.FMISession", lambda *a, **kw: session)
    result = await _add(hass, entry, FORM)

    assert result["errors"] == {"base": error}
    assert not entry.subentries


async def test_the_same_place_cannot_be_added_twice(hass: HomeAssistant, entry: MockConfigEntry):
    await _add(hass, entry, FORM)
    result = await _add(hass, entry, {**FORM, CONF_WEATHER: False})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_switching_the_forecast_off_removes_the_weather_entity(hass: HomeAssistant, entry: MockConfigEntry):
    await _add(hass, entry, FORM)
    [subentry] = entry.subentries.values()

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_PLACE), context={"source": SOURCE_RECONFIGURE, "subentry_id": subentry.subentry_id}
    )
    warning_types = next(key for key in result["data_schema"].schema if key == CONF_WARNING_TYPES)
    assert warning_types.description["suggested_value"] == ["wind", "sea_wind"]

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**FORM, CONF_LOCATION: {**TAMPERE, "radius": 5000}, CONF_WEATHER: False}
    )
    await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    assert entry.subentries[subentry.subentry_id].data[CONF_LOCATION]["radius"] == 5000
    assert er.async_get(hass).async_get("weather.tampere") is None
    assert hass.states.get("sensor.tampere_warning_level").attributes["radius"] == 5000
