"""The first setup of 4.0.0: sensor, warnings and weather subentries merged into stations and places.

Entities keep their entity ids, so their history and statistics stay. Their unique ids and subentries change.
"""

from datetime import timedelta

from conftest import FakeMetadata, place
from homeassistant.config_entries import ConfigEntryState, ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from test_no_data import ENTRY_DATA, FakeApi
from test_warning_entities import SEVERAL_AREAS, warnings_place
from test_warning_entities import FakeApi as FakeFeed
from test_weather import NOW, FakeSession

from custom_components.fmi_open_data.const import (
    CONF_LABEL,
    CONF_LANG,
    CONF_LOCATION,
    CONF_MEASUREMENTS,
    CONF_PARAMETER,
    CONF_QUERY_ID,
    CONF_STRUCTURE,
    CONF_TARGET,
    CONF_TARGET_TYPE,
    CONF_UNIT,
    CONF_WARNING_TYPES,
    CONF_WEATHER,
    DOMAIN,
    STRUCTURE_VERSION,
    SUBENTRY_PLACE,
    SUBENTRY_SENSOR,
    SUBENTRY_STATION,
    SUBENTRY_WEATHER,
)
from custom_components.fmi_open_data.session import FMIException

SUOMENLINNA = {"latitude": 60.146, "longitude": 24.988}


class FailingMetadata(FakeMetadata):
    def list_stations(self, lang):
        raise FMIException("Timeout error")


def sensor(label: str, **data) -> ConfigSubentryData:
    """A sensor subentry as it was before 4.0.0."""
    data = {**ENTRY_DATA, CONF_LABEL: label, **data}
    unique_id = f"{data[CONF_QUERY_ID]}_{data[CONF_TARGET_TYPE]}_{data[CONF_TARGET]}_{data[CONF_PARAMETER]}".lower()
    return ConfigSubentryData(data=data, subentry_type=SUBENTRY_SENSOR, title=label, unique_id=unique_id)


def weather_place(label: str) -> ConfigSubentryData:
    """A weather subentry as it was before 4.0.0."""
    return ConfigSubentryData(
        data={CONF_LOCATION: SUOMENLINNA, CONF_LABEL: label}, subentry_type=SUBENTRY_WEATHER, title=label, unique_id="weather_suomenlinna"
    )


async def _setup(hass: HomeAssistant, monkeypatch, entities: dict[str, list[tuple[str, str]]], *subentries, metadata=FakeMetadata):
    """Set up an entry of 3.x whose subentries had the given entities, by subentry title: (platform, entity id)."""
    monkeypatch.setattr("custom_components.fmi_open_data.structure.FMISession", metadata)
    monkeypatch.setattr("custom_components.fmi_open_data.query_coordinator.FMISession", lambda *a, **kw: FakeApi(timedelta(minutes=10)))
    monkeypatch.setattr("custom_components.fmi_open_data.warning_coordinator.FMISession", lambda *a, **kw: FakeFeed([SEVERAL_AREAS]))
    monkeypatch.setattr("custom_components.fmi_open_data.weather_coordinator.FMISession", lambda *a, **kw: FakeSession())
    entry = MockConfigEntry(domain=DOMAIN, version=3, data={CONF_LANG: "eng"}, subentries_data=list(subentries))
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    for subentry in entry.subentries.values():
        for platform, entity_id in entities.get(subentry.title, []):
            registry.async_get_or_create(
                platform,
                DOMAIN,
                subentry.subentry_id,
                config_entry=entry,
                config_subentry_id=subentry.subentry_id,
                suggested_object_id=entity_id.split(".")[1],
            )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _in(hass: HomeAssistant, entry: MockConfigEntry, entity_id: str):
    """The station or place an entity is in now, after checking its unique id belongs to it."""
    registered = er.async_get(hass).async_get(entity_id)
    assert registered is not None, entity_id
    subentry = entry.subentries[registered.config_subentry_id]
    assert registered.unique_id.startswith(subentry.subentry_id), entity_id
    return subentry


async def test_sensors_become_stations_and_places_a_place(hass: HomeAssistant, monkeypatch, freezer):
    freezer.move_to(NOW)
    entry = await _setup(
        hass,
        monkeypatch,
        {
            "Kaisaniemi temperature": [("sensor", "sensor.kaisaniemi_temperature"), ("binary_sensor", "binary_sensor.kaisaniemi_stale")],
            "Kaisaniemi wind": [("sensor", "sensor.kaisaniemi_wind")],
            "Kotka Be-7": [("sensor", "sensor.kotka_be_7")],
            "Varoitukset Suomenlinna": [("sensor", "sensor.varoitukset"), ("event", "event.varoitukset")],
            "Sää Suomenlinna": [("weather", "weather.saa")],
        },
        sensor("Kaisaniemi temperature", **{CONF_UNIT: "K"}),
        sensor("Kaisaniemi wind", **{CONF_PARAMETER: "ws_10min"}),
        sensor("Kotka Be-7", **{CONF_TARGET_TYPE: "place", CONF_TARGET: "Kotka", CONF_PARAMETER: "Be-7"}),
        warnings_place("Varoitukset Suomenlinna", SUOMENLINNA["latitude"], SUOMENLINNA["longitude"], 1000),
        weather_place("Sää Suomenlinna"),
    )

    assert entry.data[CONF_STRUCTURE] == STRUCTURE_VERSION
    subentries = {subentry.title: subentry for subentry in entry.subentries.values()}
    assert {title: subentry.subentry_type for title, subentry in subentries.items()} == {
        "Helsinki Kaisaniemi": SUBENTRY_STATION,
        "Kotka": SUBENTRY_STATION,
        "Varoitukset Suomenlinna": SUBENTRY_PLACE,
    }
    kaisaniemi = subentries["Helsinki Kaisaniemi"].data[CONF_MEASUREMENTS]
    # Named by the rules: FMI's description, or the parameter when it has none. A unit given stays.
    assert [(measurement[CONF_LABEL], measurement.get(CONF_UNIT)) for measurement in kaisaniemi] == [
        ("Air temperature", "K"),
        ("Wind speed", None),
    ]
    assert subentries["Kotka"].data[CONF_MEASUREMENTS][0][CONF_LABEL] == "Be-7"
    suomenlinna = subentries["Varoitukset Suomenlinna"].data
    assert (suomenlinna[CONF_WEATHER], suomenlinna[CONF_LOCATION]["radius"], len(suomenlinna[CONF_WARNING_TYPES])) == (True, 1000, 14)

    for entity_id, title in [
        ("sensor.kaisaniemi_temperature", "Helsinki Kaisaniemi"),
        ("binary_sensor.kaisaniemi_stale", "Helsinki Kaisaniemi"),
        ("sensor.kaisaniemi_wind", "Helsinki Kaisaniemi"),
        ("sensor.kotka_be_7", "Kotka"),
        ("sensor.varoitukset", "Varoitukset Suomenlinna"),
        ("event.varoitukset", "Varoitukset Suomenlinna"),
        ("weather.saa", "Varoitukset Suomenlinna"),
    ]:
        assert _in(hass, entry, entity_id).title == title
        assert hass.states.get(entity_id) is not None, entity_id

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert sorted(device.name for device in devices) == ["Helsinki Kaisaniemi", "Kotka", "Varoitukset Suomenlinna"]


async def test_two_warnings_places_at_one_point_follow_what_either_did(hass: HomeAssistant, monkeypatch):
    first = warnings_place("Varoitukset A", SUOMENLINNA["latitude"], SUOMENLINNA["longitude"], 3000)
    second = warnings_place("Varoitukset B", SUOMENLINNA["latitude"], SUOMENLINNA["longitude"], 1000)
    first["data"][CONF_WARNING_TYPES], second["data"][CONF_WARNING_TYPES] = ["wind"], ["seaWind", "rain"]
    second["unique_id"] = "warnings_b"
    entry = await _setup(
        hass,
        monkeypatch,
        {"Varoitukset A": [("sensor", "sensor.varoitukset_a")], "Varoitukset B": [("sensor", "sensor.varoitukset_b")]},
        first,
        second,
    )

    [place] = entry.subentries.values()
    assert place.data[CONF_WARNING_TYPES] == ["wind", "seaWind", "rain"]
    assert place.data[CONF_LOCATION]["radius"] == 3000
    # One place has one warning level: the first one's stays, the other is removed.
    assert _in(hass, entry, "sensor.varoitukset_a") is place
    assert er.async_get(hass).async_get("sensor.varoitukset_b") is None


async def test_restructuring_waits_for_fmi(hass: HomeAssistant, monkeypatch):
    entry = await _setup(hass, monkeypatch, {}, sensor("Kaisaniemi temperature"), metadata=FailingMetadata)

    assert entry.state is ConfigEntryState.SETUP_RETRY
    [subentry] = entry.subentries.values()
    assert subentry.subentry_type == SUBENTRY_SENSOR
    assert CONF_STRUCTURE not in entry.data


async def test_a_second_start_changes_nothing(hass: HomeAssistant, monkeypatch):
    entry = await _setup(
        hass, monkeypatch, {"Kaisaniemi temperature": [("sensor", "sensor.kaisaniemi_temperature")]}, sensor("Kaisaniemi temperature")
    )
    before = {subentry_id: (subentry.title, dict(subentry.data)) for subentry_id, subentry in entry.subentries.items()}
    unique_id = er.async_get(hass).async_get("sensor.kaisaniemi_temperature").unique_id

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert {subentry_id: (subentry.title, dict(subentry.data)) for subentry_id, subentry in entry.subentries.items()} == before
    assert er.async_get(hass).async_get("sensor.kaisaniemi_temperature").unique_id == unique_id


async def test_a_place_added_while_setup_waited_takes_in_the_old_one(hass: HomeAssistant, monkeypatch):
    # While FMI was down and setup retried, the user added a place at the old warnings place's point.
    new = place("Suomenlinna", SUOMENLINNA["latitude"], SUOMENLINNA["longitude"], 500, weather=False, warning_types=["rain"])
    old = warnings_place("Varoitukset Suomenlinna", SUOMENLINNA["latitude"], SUOMENLINNA["longitude"], 2000)
    old["data"][CONF_WARNING_TYPES] = ["wind"]
    entry = await _setup(hass, monkeypatch, {"Varoitukset Suomenlinna": [("sensor", "sensor.varoitukset")]}, new, old)

    assert entry.state is ConfigEntryState.LOADED
    [suomenlinna] = entry.subentries.values()
    assert suomenlinna.title == "Suomenlinna"
    assert suomenlinna.data[CONF_WARNING_TYPES] == ["wind", "rain"]
    assert suomenlinna.data[CONF_LOCATION]["radius"] == 2000
    assert _in(hass, entry, "sensor.varoitukset") is suomenlinna


async def test_a_point_is_written_as_the_flow_writes_it(hass: HomeAssistant, monkeypatch):
    entry = await _setup(
        hass,
        monkeypatch,
        {},
        sensor(
            "Mökin lämpötila",
            **{
                CONF_TARGET_TYPE: "latlon",
                CONF_TARGET: "61.23456, 27.65432",
                CONF_QUERY_ID: "fmi::forecast::harmonie::surface::point::simple",
            },
        ),
    )

    [cabin] = entry.subentries.values()
    assert (cabin.data[CONF_TARGET], cabin.unique_id) == ("61.2346,27.6543", "station_latlon_61.2346,27.6543")
