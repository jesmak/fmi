"""From one config entry per sensor (2.x) to one entry with subentries (3.0).

What matters to the user is that nothing they have built on the entities
breaks: entity IDs, and so history, dashboards and automations, stay the same.
"""
from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryDisabler, ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fmi.const import (
    CONF_ENTRY_TYPE,
    CONF_LABEL,
    CONF_LANG,
    CONF_LOCATION,
    CONF_NO_DATA_ISSUE,
    CONF_NO_DATA_ISSUE_HOURS,
    CONF_TARGET,
    CONF_WARNING_TYPES,
    DOMAIN,
    ENTRY_TYPE_WARNINGS,
    SUBENTRY_SENSOR,
    SUBENTRY_WARNINGS,
    WARNING_TYPES,
)
from custom_components.fmi.query_coordinator import build_unique_id
from custom_components.fmi.warning_coordinator import build_warnings_unique_id
from test_no_data import ENTRY_DATA
from test_no_data import FakeApi as QueryApi
from test_warning_entities import SEVERAL_AREAS
from test_warning_entities import FakeApi as WarningsApi

pytestmark = pytest.mark.asyncio

KAISANIEMI = {**ENTRY_DATA, CONF_LANG: "fin", CONF_NO_DATA_ISSUE: True, CONF_NO_DATA_ISSUE_HOURS: 120}
MANNERHEIMINTIE = {**KAISANIEMI, CONF_LABEL: "Mannerheimintie Air temperature", CONF_TARGET: "100742"}
# Set up before the stale data settings existed.
KATAJANOKKA = {**ENTRY_DATA, CONF_LABEL: "Katajanokka Air temperature", CONF_TARGET: "104053"}
WARNINGS = {
    CONF_ENTRY_TYPE: ENTRY_TYPE_WARNINGS,
    CONF_LANG: "fin",
    CONF_LABEL: "Varoitukset Suomenlinna",
    CONF_LOCATION: {"latitude": 60.146, "longitude": 24.988, "radius": 0},
    CONF_WARNING_TYPES: WARNING_TYPES,
}


@pytest.fixture(autouse=True)
def fake_apis(monkeypatch):
    monkeypatch.setattr("custom_components.fmi.query_coordinator.FMISession",
                        lambda *a, **kw: QueryApi(age=timedelta(hours=1)))
    monkeypatch.setattr("custom_components.fmi.warning_coordinator.FMISession",
                        lambda *a, **kw: WarningsApi([SEVERAL_AREAS]))


def _old_entry(hass: HomeAssistant, data: dict, unique_id: str, entities: list[str],
               disabled: bool = False) -> MockConfigEntry:
    """A 2.x entry, with its entities registered as 2.x left them: unique id = entry id."""
    entry = MockConfigEntry(domain=DOMAIN, version=2, title=data[CONF_LABEL], data=data, unique_id=unique_id,
                            disabled_by=ConfigEntryDisabler.USER if disabled else None)
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    for entity_id in entities:
        domain, object_id = entity_id.split(".")
        registry.async_get_or_create(
            domain, DOMAIN, entry.entry_id, config_entry=entry, suggested_object_id=object_id,
            disabled_by=er.RegistryEntryDisabler.CONFIG_ENTRY if disabled else None)
    return entry


async def _start(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()


async def test_every_entry_becomes_a_subentry_and_keeps_its_entities(hass: HomeAssistant):
    kaisaniemi = _old_entry(hass, KAISANIEMI, build_unique_id(KAISANIEMI), [
        # Renamed by the user at some point: the entity ID must not follow the name.
        "sensor.temperature_outside",
        "binary_sensor.fmi_kaisaniemi_air_temperature_stale_data",
    ])
    _old_entry(hass, MANNERHEIMINTIE, build_unique_id(MANNERHEIMINTIE), [
        "sensor.fmi_mannerheimintie_air_temperature",
        "binary_sensor.fmi_mannerheimintie_air_temperature_stale_data",
    ], disabled=True)
    _old_entry(hass, KATAJANOKKA, build_unique_id(KATAJANOKKA), [
        "sensor.fmi_katajanokka_air_temperature",
        "binary_sensor.fmi_katajanokka_air_temperature_stale_data",
    ])
    _old_entry(hass, WARNINGS, build_warnings_unique_id(WARNINGS), [
        "sensor.fmi_varoitukset_suomenlinna",
        "event.fmi_varoitukset_suomenlinna",
    ])
    ir.async_create_issue(hass, DOMAIN, f"no_data_{kaisaniemi.entry_id}", is_fixable=False,
                          severity=ir.IssueSeverity.WARNING, translation_key="no_data")

    await _start(hass)

    [entry] = hass.config_entries.async_entries(DOMAIN)
    assert entry.version == 3
    assert entry.title == "FMI"
    assert entry.data == {CONF_LANG: "fin"}
    # The settings most sensors had.
    assert entry.options == {CONF_NO_DATA_ISSUE: True, CONF_NO_DATA_ISSUE_HOURS: 120}

    subentries = {subentry.title: subentry for subentry in entry.subentries.values()}
    assert set(subentries) == {"Kaisaniemi Air temperature", "Mannerheimintie Air temperature",
                               "Katajanokka Air temperature", "Varoitukset Suomenlinna"}
    assert subentries["Varoitukset Suomenlinna"].subentry_type == SUBENTRY_WARNINGS
    assert CONF_ENTRY_TYPE not in subentries["Varoitukset Suomenlinna"].data
    assert subentries["Kaisaniemi Air temperature"].subentry_type == SUBENTRY_SENSOR
    assert subentries["Kaisaniemi Air temperature"].unique_id == build_unique_id(KAISANIEMI)
    assert CONF_NO_DATA_ISSUE_HOURS not in subentries["Kaisaniemi Air temperature"].data
    # Each sensor keeps its own language.
    assert subentries["Katajanokka Air temperature"].data[CONF_LANG] == "eng"

    registry = er.async_get(hass)
    moved = {
        "sensor.temperature_outside": "Kaisaniemi Air temperature",
        "binary_sensor.fmi_kaisaniemi_air_temperature_stale_data": "Kaisaniemi Air temperature",
        "sensor.fmi_mannerheimintie_air_temperature": "Mannerheimintie Air temperature",
        "binary_sensor.fmi_mannerheimintie_air_temperature_stale_data": "Mannerheimintie Air temperature",
        "sensor.fmi_katajanokka_air_temperature": "Katajanokka Air temperature",
        "binary_sensor.fmi_katajanokka_air_temperature_stale_data": "Katajanokka Air temperature",
        "sensor.fmi_varoitukset_suomenlinna": "Varoitukset Suomenlinna",
        "event.fmi_varoitukset_suomenlinna": "Varoitukset Suomenlinna",
    }
    for entity_id, title in moved.items():
        registered = registry.async_get(entity_id)
        assert registered is not None, entity_id
        assert registered.config_entry_id == entry.entry_id
        assert registered.config_subentry_id == subentries[title].subentry_id
        assert registered.unique_id == subentries[title].subentry_id

    # Nothing was registered a second time under a new entity ID.
    assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == len(moved)
    assert hass.states.get("sensor.temperature_outside").state == "1.5"
    assert hass.states.get("sensor.fmi_varoitukset_suomenlinna") is not None
    # The user had turned this sensor off, and it stays off.
    assert registry.async_get("sensor.fmi_mannerheimintie_air_temperature").disabled_by \
        is er.RegistryEntryDisabler.USER
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"no_data_{kaisaniemi.entry_id}") is None


async def test_an_entry_left_behind_by_an_interrupted_migration_is_merged(hass: HomeAssistant):
    subentry_data = {key: value for key, value in KAISANIEMI.items()
                     if key not in (CONF_NO_DATA_ISSUE, CONF_NO_DATA_ISSUE_HOURS)}
    parent = MockConfigEntry(domain=DOMAIN, version=3, title="FMI", data={CONF_LANG: "fin"}, subentries_data=[
        ConfigSubentryData(data=subentry_data, subentry_type=SUBENTRY_SENSOR, title="Kaisaniemi Air temperature",
                           unique_id=build_unique_id(KAISANIEMI)),
    ])
    parent.add_to_hass(hass)
    _old_entry(hass, KAISANIEMI, build_unique_id(KAISANIEMI), ["sensor.temperature_outside"])

    await _start(hass)

    [entry] = hass.config_entries.async_entries(DOMAIN)
    assert entry.entry_id == parent.entry_id
    [subentry] = entry.subentries.values()
    assert er.async_get(hass).async_get("sensor.temperature_outside").config_subentry_id == subentry.subentry_id


async def test_a_current_entry_is_left_alone(hass: HomeAssistant):
    parent = MockConfigEntry(domain=DOMAIN, version=3, title="FMI", data={CONF_LANG: "eng"},
                             options={CONF_NO_DATA_ISSUE: False, CONF_NO_DATA_ISSUE_HOURS: 48})
    parent.add_to_hass(hass)

    await _start(hass)

    [entry] = hass.config_entries.async_entries(DOMAIN)
    assert entry.data == {CONF_LANG: "eng"}
    assert entry.options == {CONF_NO_DATA_ISSUE: False, CONF_NO_DATA_ISSUE_HOURS: 48}
