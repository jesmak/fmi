"""From the old `fmi` domain to `fmi_open_data`.

What matters to the user is that nothing they have built on the entities
breaks: entity IDs, and so history, dashboards and automations, stay the same.
"""

import json
from datetime import timedelta

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigEntryDisabler, ConfigEntryState, ConfigFlow, ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.entity import Entity
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockModule,
    MockPlatform,
    mock_config_flow,
    mock_integration,
    mock_platform,
)
from test_no_data import ENTRY_DATA
from test_no_data import FakeApi as QueryApi
from test_warning_entities import SEVERAL_AREAS, warnings_place
from test_warning_entities import FakeApi as WarningsApi

from custom_components.fmi_open_data.const import (
    CONF_LABEL,
    CONF_LANG,
    CONF_NO_DATA_ISSUE,
    CONF_NO_DATA_ISSUE_HOURS,
    CONF_TARGET,
    DOMAIN,
    SUBENTRY_SENSOR,
)
from custom_components.fmi_open_data.migration import OLD_DOMAIN, OLD_FOLDER_ISSUE
from custom_components.fmi_open_data.query_coordinator import build_unique_id

pytestmark = pytest.mark.asyncio

KAISANIEMI = {**ENTRY_DATA, CONF_LANG: "fin", CONF_NO_DATA_ISSUE: True, CONF_NO_DATA_ISSUE_HOURS: 120}
MANNERHEIMINTIE = {**KAISANIEMI, CONF_LABEL: "Mannerheimintie Air temperature", CONF_TARGET: "100742"}
# Set up before the stale data settings existed.
KATAJANOKKA = {**ENTRY_DATA, CONF_LABEL: "Katajanokka Air temperature", CONF_TARGET: "104053"}
SENSOR_DATA = {key: value for key, value in KAISANIEMI.items() if key not in (CONF_NO_DATA_ISSUE, CONF_NO_DATA_ISSUE_HOURS)}
# An entry of anand-p-r/fmi-hass-custom, which uses the same domain.
OTHER_FMI = {"name": "Kotona", "latitude": 60.1, "longitude": 24.9}


@pytest.fixture(autouse=True)
def fake_apis(monkeypatch):
    monkeypatch.setattr("custom_components.fmi_open_data.query_coordinator.FMISession", lambda *a, **kw: QueryApi(age=timedelta(hours=1)))
    monkeypatch.setattr("custom_components.fmi_open_data.warning_coordinator.FMISession", lambda *a, **kw: WarningsApi([SEVERAL_AREAS]))


def _register(
    hass: HomeAssistant, entry: MockConfigEntry, entity_id: str, unique_id: str, subentry_id: str | None = None, **kwargs
) -> None:
    domain, object_id = entity_id.split(".")
    er.async_get(hass).async_get_or_create(
        domain, OLD_DOMAIN, unique_id, config_entry=entry, config_subentry_id=subentry_id, suggested_object_id=object_id, **kwargs
    )


def _legacy_entry(hass: HomeAssistant, data: dict, unique_id: str, entities: list[str], disabled: bool = False) -> MockConfigEntry:
    """A 2.x entry, with its entities registered as 2.x left them: unique id = entry id."""
    entry = MockConfigEntry(
        domain=OLD_DOMAIN,
        version=2,
        title=data[CONF_LABEL],
        data=data,
        unique_id=unique_id,
        disabled_by=ConfigEntryDisabler.USER if disabled else None,
    )
    entry.add_to_hass(hass)
    for entity_id in entities:
        _register(hass, entry, entity_id, entry.entry_id, disabled_by=er.RegistryEntryDisabler.CONFIG_ENTRY if disabled else None)
    return entry


def _current_entry(hass: HomeAssistant, disabled: bool = False) -> MockConfigEntry:
    """A 3.x entry with a sensor and a warnings place, and their entities: unique id = subentry id."""
    entry = MockConfigEntry(
        domain=OLD_DOMAIN,
        version=3,
        title="FMI",
        data={CONF_LANG: "eng"},
        options={CONF_NO_DATA_ISSUE: False, CONF_NO_DATA_ISSUE_HOURS: 48},
        subentries_data=[
            ConfigSubentryData(
                data=SENSOR_DATA, subentry_type=SUBENTRY_SENSOR, title="Kaisaniemi Air temperature", unique_id=build_unique_id(KAISANIEMI)
            ),
            warnings_place("Varoitukset Suomenlinna", 60.145, 24.988),
        ],
        disabled_by=ConfigEntryDisabler.USER if disabled else None,
    )
    entry.add_to_hass(hass)
    sensor, warnings = entry.subentries.values()
    disabled_by = er.RegistryEntryDisabler.CONFIG_ENTRY if disabled else None
    _register(hass, entry, "sensor.temperature_outside", sensor.subentry_id, sensor.subentry_id, disabled_by=disabled_by)
    _register(
        hass,
        entry,
        "binary_sensor.fmi_kaisaniemi_air_temperature_stale_data",
        sensor.subentry_id,
        sensor.subentry_id,
        disabled_by=disabled_by,
    )
    _register(hass, entry, "sensor.fmi_varoitukset_suomenlinna", warnings.subentry_id, warnings.subentry_id, disabled_by=disabled_by)
    _register(hass, entry, "event.fmi_varoitukset_suomenlinna", warnings.subentry_id, warnings.subentry_id, disabled_by=disabled_by)
    return entry


async def _add(hass: HomeAssistant, choice: str | None = "move") -> dict:
    """Add the integration as a user would, choosing from the menu if there is one."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    if result["type"] is FlowResultType.MENU:
        assert result["menu_options"] == ["move", "new"]
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": choice})
    if result["type"] is FlowResultType.FORM:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LANG: "fin"})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    return result


def _moved(hass: HomeAssistant, entity_id: str, title: str) -> er.RegistryEntry:
    [entry] = hass.config_entries.async_entries(DOMAIN)
    [subentry] = [subentry for subentry in entry.subentries.values() if subentry.title == title]
    registered = er.async_get(hass).async_get(entity_id)
    assert registered is not None, entity_id
    assert (registered.platform, registered.config_entry_id, registered.config_subentry_id, registered.unique_id) == (
        DOMAIN,
        entry.entry_id,
        subentry.subentry_id,
        subentry.subentry_id,
    ), entity_id
    return registered


async def test_a_3x_entry_moves_with_its_sensors_and_warnings_places(hass: HomeAssistant):
    old = _current_entry(hass)
    [sensor, _] = old.subentries.values()
    ir.async_create_issue(
        hass, OLD_DOMAIN, f"no_data_{sensor.subentry_id}", is_fixable=False, severity=ir.IssueSeverity.WARNING, translation_key="no_data"
    )

    await _add(hass)

    [entry] = hass.config_entries.async_entries(DOMAIN)
    assert entry.state is ConfigEntryState.LOADED
    assert entry.version == 3
    assert entry.data == {CONF_LANG: "eng"}
    assert entry.options == {CONF_NO_DATA_ISSUE: False, CONF_NO_DATA_ISSUE_HOURS: 48}
    assert {(subentry.subentry_type, subentry.title, subentry.unique_id) for subentry in entry.subentries.values()} == {
        (subentry.subentry_type, subentry.title, subentry.unique_id) for subentry in old.subentries.values()
    }
    assert hass.config_entries.async_entries(OLD_DOMAIN) == []

    _moved(hass, "sensor.temperature_outside", "Kaisaniemi Air temperature")
    _moved(hass, "binary_sensor.fmi_kaisaniemi_air_temperature_stale_data", "Kaisaniemi Air temperature")
    _moved(hass, "sensor.fmi_varoitukset_suomenlinna", "Varoitukset Suomenlinna")
    _moved(hass, "event.fmi_varoitukset_suomenlinna", "Varoitukset Suomenlinna")
    # Nothing was registered a second time under a new entity ID.
    assert len(er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)) == 4
    assert hass.states.get("sensor.temperature_outside").state == "1.5"
    assert hass.states.get("sensor.fmi_varoitukset_suomenlinna") is not None
    assert ir.async_get(hass).async_get_issue(OLD_DOMAIN, f"no_data_{sensor.subentry_id}") is None


async def test_2x_entries_become_subentries_and_keep_their_entities(hass: HomeAssistant):
    kaisaniemi = _legacy_entry(
        hass,
        KAISANIEMI,
        build_unique_id(KAISANIEMI),
        # Renamed by the user at some point: the entity ID must not follow the name.
        ["sensor.temperature_outside", "binary_sensor.fmi_kaisaniemi_air_temperature_stale_data"],
    )
    _legacy_entry(hass, MANNERHEIMINTIE, build_unique_id(MANNERHEIMINTIE), ["sensor.fmi_mannerheimintie_air_temperature"], disabled=True)
    _legacy_entry(hass, KATAJANOKKA, build_unique_id(KATAJANOKKA), ["sensor.fmi_katajanokka_air_temperature"])
    ir.async_create_issue(
        hass, OLD_DOMAIN, f"no_data_{kaisaniemi.entry_id}", is_fixable=False, severity=ir.IssueSeverity.WARNING, translation_key="no_data"
    )

    await _add(hass)

    [entry] = hass.config_entries.async_entries(DOMAIN)
    assert entry.data == {CONF_LANG: "fin"}
    # The settings most sensors had.
    assert entry.options == {CONF_NO_DATA_ISSUE: True, CONF_NO_DATA_ISSUE_HOURS: 120}
    subentries = {subentry.title: subentry for subentry in entry.subentries.values()}
    assert set(subentries) == {"Kaisaniemi Air temperature", "Mannerheimintie Air temperature", "Katajanokka Air temperature"}
    assert subentries["Kaisaniemi Air temperature"].unique_id == build_unique_id(KAISANIEMI)
    assert CONF_NO_DATA_ISSUE_HOURS not in subentries["Kaisaniemi Air temperature"].data
    # Each sensor keeps its own language.
    assert subentries["Katajanokka Air temperature"].data[CONF_LANG] == "eng"
    assert hass.config_entries.async_entries(OLD_DOMAIN) == []

    _moved(hass, "sensor.temperature_outside", "Kaisaniemi Air temperature")
    _moved(hass, "binary_sensor.fmi_kaisaniemi_air_temperature_stale_data", "Kaisaniemi Air temperature")
    _moved(hass, "sensor.fmi_katajanokka_air_temperature", "Katajanokka Air temperature")
    # The user had turned this sensor off, and it stays off.
    assert _moved(hass, "sensor.fmi_mannerheimintie_air_temperature", "Mannerheimintie Air temperature").disabled_by is (
        er.RegistryEntryDisabler.USER
    )
    assert hass.states.get("sensor.temperature_outside").state == "1.5"
    assert ir.async_get(hass).async_get_issue(OLD_DOMAIN, f"no_data_{kaisaniemi.entry_id}") is None


async def test_two_entries_measuring_the_same_thing_become_one_subentry(hass: HomeAssistant):
    # 1.x told sensors apart by their label, so the same measurement could be added twice under two names.
    _legacy_entry(hass, KAISANIEMI, "fmi_kaisaniemi_air_temperature", ["sensor.fmi_kaisaniemi_air_temperature"])
    _legacy_entry(hass, {**KAISANIEMI, CONF_LABEL: "Helsinki temperature"}, "fmi_helsinki_temperature", ["sensor.fmi_helsinki_temperature"])

    await _add(hass)

    [entry] = hass.config_entries.async_entries(DOMAIN)
    assert len(entry.subentries) == 1
    _moved(hass, "sensor.fmi_kaisaniemi_air_temperature", "Kaisaniemi Air temperature")
    assert er.async_get(hass).async_get("sensor.fmi_helsinki_temperature") is None


async def test_an_entry_left_behind_by_an_interrupted_30_migration_moves_too(hass: HomeAssistant):
    # 3.0.0 could stop with the first entry still at version 2 but with its subentry
    # made and its entity moved onto it, and the twin not yet merged.
    first = MockConfigEntry(
        domain=OLD_DOMAIN,
        version=2,
        title=KAISANIEMI[CONF_LABEL],
        data=KAISANIEMI,
        unique_id=build_unique_id(KAISANIEMI),
        subentries_data=[
            ConfigSubentryData(
                data=SENSOR_DATA, subentry_type=SUBENTRY_SENSOR, title=KAISANIEMI[CONF_LABEL], unique_id=build_unique_id(KAISANIEMI)
            ),
        ],
    )
    first.add_to_hass(hass)
    [subentry] = first.subentries.values()
    _register(hass, first, "sensor.my_renamed_temperature", subentry.subentry_id, subentry.subentry_id)
    _legacy_entry(hass, {**KAISANIEMI, CONF_LABEL: "Helsinki temperature"}, "fmi_helsinki_temperature", ["sensor.fmi_helsinki_temperature"])

    await _add(hass)

    [entry] = hass.config_entries.async_entries(DOMAIN)
    assert len(entry.subentries) == 1
    _moved(hass, "sensor.my_renamed_temperature", "Kaisaniemi Air temperature")
    assert er.async_get(hass).async_get("sensor.fmi_helsinki_temperature") is None
    # No new sensor was made in place of the one that was kept.
    assert [
        item.entity_id for item in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id) if item.domain == "sensor"
    ] == ["sensor.my_renamed_temperature"]


async def test_the_move_works_while_the_old_folder_still_runs_the_old_entry(hass: HomeAssistant):
    # The old folder that HACS leaves behind sets the old entry up, so its entities are loaded.
    class OldSensor(Entity):
        def __init__(self, unique_id: str) -> None:
            self._attr_unique_id = unique_id

    async def setup_entry(hass, entry, async_add_entities):
        async_add_entities([OldSensor(subentry_id)], config_subentry_id=subentry_id)

    async def forward(hass, entry):
        await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
        return True

    async def unload(hass, entry):
        return await hass.config_entries.async_unload_platforms(entry, ["sensor"])

    class OldFlow(ConfigFlow):
        VERSION = 3

    mock_integration(hass, MockModule(OLD_DOMAIN, async_setup_entry=forward, async_unload_entry=unload))
    mock_platform(hass, f"{OLD_DOMAIN}.config_flow")
    mock_platform(hass, f"{OLD_DOMAIN}.sensor", MockPlatform(async_setup_entry=setup_entry))
    old = _current_entry(hass)
    subentry_id = next(iter(old.subentries))
    with mock_config_flow(OLD_DOMAIN, OldFlow):
        await hass.config_entries.async_setup(old.entry_id)
        await hass.async_block_till_done()
        assert old.state is ConfigEntryState.LOADED
        assert er.async_get(hass).async_get("sensor.temperature_outside").platform == OLD_DOMAIN

        await _add(hass)

    assert hass.config_entries.async_entries(OLD_DOMAIN) == []
    _moved(hass, "sensor.temperature_outside", "Kaisaniemi Air temperature")
    assert hass.states.get("sensor.temperature_outside").state == "1.5"


async def test_an_old_entry_still_being_set_up_is_moved_on_a_retry(hass: HomeAssistant):
    # At startup both domains are set up at once, and an entry being set up cannot be unloaded.
    old = _current_entry(hass)
    old._async_set_state(hass, ConfigEntryState.SETUP_IN_PROGRESS, None)

    await _add(hass)

    [entry] = hass.config_entries.async_entries(DOMAIN)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert er.async_get(hass).async_get("sensor.temperature_outside").platform == OLD_DOMAIN

    old._async_set_state(hass, ConfigEntryState.NOT_LOADED, None)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.data == {CONF_LANG: "eng"}
    assert hass.config_entries.async_entries(OLD_DOMAIN) == []
    _moved(hass, "sensor.temperature_outside", "Kaisaniemi Air temperature")
    _moved(hass, "event.fmi_varoitukset_suomenlinna", "Varoitukset Suomenlinna")


async def test_an_old_entity_without_a_subentry_does_not_stop_the_move(hass: HomeAssistant):
    old = _current_entry(hass)
    _register(hass, old, "sensor.leftover", "leftover")

    await _add(hass)

    [entry] = hass.config_entries.async_entries(DOMAIN)
    assert entry.state is ConfigEntryState.LOADED
    _moved(hass, "sensor.temperature_outside", "Kaisaniemi Air temperature")
    # It belonged to nothing that moved, so it went with the old entry.
    assert er.async_get(hass).async_get("sensor.leftover") is None


async def test_the_entities_of_a_disabled_3x_entry_stay_disabled(hass: HomeAssistant):
    _current_entry(hass, disabled=True)

    await _add(hass)

    for entity_id, title in [
        ("sensor.temperature_outside", "Kaisaniemi Air temperature"),
        ("event.fmi_varoitukset_suomenlinna", "Varoitukset Suomenlinna"),
    ]:
        assert _moved(hass, entity_id, title).disabled_by is er.RegistryEntryDisabler.USER
    assert hass.states.get("sensor.temperature_outside") is None


async def test_a_new_setup_beside_the_old_one_leaves_the_old_one_alone(hass: HomeAssistant):
    old = _current_entry(hass)

    result = await _add(hass, "new")

    assert result["data"] == {CONF_LANG: "fin"}
    [entry] = hass.config_entries.async_entries(DOMAIN)
    assert entry.subentries == {}
    assert hass.config_entries.async_entries(OLD_DOMAIN) == [old]
    assert er.async_get(hass).async_get("sensor.temperature_outside").platform == OLD_DOMAIN


async def test_an_entry_of_the_other_fmi_integration_is_not_offered_or_touched(hass: HomeAssistant):
    other = MockConfigEntry(domain=OLD_DOMAIN, version=1, title="Kotona", data=OTHER_FMI)
    other.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    _current_entry(hass)
    await _add(hass)

    assert hass.config_entries.async_entries(OLD_DOMAIN) == [other]


async def test_a_second_start_moves_nothing(hass: HomeAssistant):
    _current_entry(hass)
    await _add(hass)
    [entry] = hass.config_entries.async_entries(DOMAIN)
    before = {item.entity_id: item for item in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    after = {item.entity_id: item for item in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}
    assert after == before
    assert entry.data == {CONF_LANG: "eng"}


@pytest.mark.parametrize(
    ("documentation", "old_entry", "raised"),
    [
        ("https://github.com/jesmak/fmi", False, True),
        # Still in use by an old entry the user chose to keep.
        ("https://github.com/jesmak/fmi", True, False),
        ("https://github.com/anand-p-r/fmi-hass-custom", False, False),
        (None, False, False),
    ],
)
async def test_the_old_folder_issue(hass: HomeAssistant, tmp_path, documentation, old_entry, raised):
    hass.config.config_dir = str(tmp_path)
    if documentation is not None:
        folder = tmp_path / "custom_components" / OLD_DOMAIN
        folder.mkdir(parents=True)
        (folder / "manifest.json").write_text(json.dumps({"domain": OLD_DOMAIN, "documentation": documentation}))
    if old_entry:
        _current_entry(hass)

    await _add(hass, "new")

    issue = ir.async_get(hass).async_get_issue(DOMAIN, OLD_FOLDER_ISSUE)
    assert (issue is not None) == raised
    if raised:
        assert issue.translation_placeholders == {"path": str(tmp_path / "custom_components" / OLD_DOMAIN)}
