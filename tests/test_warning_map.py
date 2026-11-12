"""The warning map: each area once, coloured by its highest level, as a map feed. The areas and warnings are made up."""

from datetime import datetime, timedelta, timezone

from conftest import warning_map
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from test_warning_entities import BOTHNIA, SEVERAL_AREAS, FakeApi

from custom_components.fmi_open_data.cap import CapAlert, CapArea, CapInfo
from custom_components.fmi_open_data.const import (
    CONF_HOURS_AHEAD,
    CONF_LABEL,
    CONF_LANG,
    CONF_STRUCTURE,
    CONF_WARNING_TYPES,
    DOMAIN,
    STRUCTURE_VERSION,
    SUBENTRY_WARNING_MAP,
    WARNING_TYPES,
)
from custom_components.fmi_open_data.warning_map import LATER_OPACITY, TEXTS, area_features, feed_attributes, next_change, simplified_ring

ZONE = timezone(timedelta(hours=2))
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=ZONE)
TYPES = frozenset(WARNING_TYPES)

SENSOR = "sensor.varoituskartta_warning_areas"


def square(south: float, west: float, size: float) -> list[tuple[float, float]]:
    north, east = south + size, west + size
    return [(south, west), (south, east), (north, east), (north, west), (south, west)]


REGION = CapArea("Korpimaa", {"ISO 3166-2": "FI-90"}, [square(62.0, 25.0, 2.0)])
TOWN = CapArea("Suvanto", {"FI-kuntanumero": "990"}, [square(62.5, 25.5, 0.3)])
SEA = CapArea("Ulkoselkä", {"METAREA": "B9X"}, [square(60.0, 20.0, 1.0)])


def alert(identifier: str, code: str, level: str, start: int, end: int, *areas: CapArea, references=()) -> CapAlert:
    """A warning from `start` to `end` hours after noon."""
    info = CapInfo(
        language="fi-FI",
        event_code=code,
        event={"trafficWeather": "Liikennesää", "wind": "Tuulivaroitus", "seaWind": "Tuulivaroitus merelle"}[code],
        severity="Moderate",
        onset=NOW + timedelta(hours=start),
        expires=NOW + timedelta(hours=end),
        headline="",
        description=f"{code} {identifier}",
        web="https://www.ilmatieteenlaitos.fi/varoitukset",
        parameters={"color": level},
        areas=list(areas),
    )
    return CapAlert(identifier, "Alert", list(references), [info])


def features(alerts: list[CapAlert], hours_ahead: float = 24, types=TYPES, now: datetime = NOW) -> dict[str, dict]:
    return {feature["id"]: feature for feature in area_features(alerts, types, "fin", hours_ahead, now, ZONE)}


def test_an_area_is_one_item_whatever_warns_it():
    result = features(
        [
            alert("a", "trafficWeather", "yellow", -2, 12, REGION, TOWN),
            alert("b", "wind", "orange", -1, 6, TOWN),
            alert("c", "trafficWeather", "yellow", 12, 36, TOWN),
        ]
    )

    assert list(result) == ["area:FI-90", "area:990"]
    town = result["area:990"]["properties"]
    assert town["name"] == "Suvanto"
    assert (town["level"], town["color"], town["active"]) == ("orange", "#ef6c00", True)
    assert "opacity" not in town
    assert town["subtitle"] == "Tuulivaroitus, Liikennesää"
    assert town["list"] == {"text": "Tuulivaroitus · voimassa pe 18.00 asti", "value": "Oranssi"}
    assert town["details"] == [
        {"label": "Liikennesää", "value": "pe 10.00 – la 0.00", "tag": {"text": "Keltainen", "tone": "neutral"}},
        {"label": "Tuulivaroitus", "value": "pe 11.00–18.00", "tag": {"text": "Oranssi", "tone": "item"}},
        {"label": "Liikennesää", "value": "la 0.00 – su 0.00", "tag": {"text": "Keltainen", "tone": "neutral"}},
    ]
    assert result["area:FI-90"]["properties"]["level"] == "yellow"


def test_a_higher_level_still_ahead_does_not_colour_an_area_with_a_warning_in_force():
    result = features([alert("a", "wind", "yellow", -1, 6, TOWN), alert("b", "wind", "red", 3, 9, TOWN)])

    town = result["area:990"]["properties"]
    assert (town["level"], town["active"]) == ("yellow", True)
    assert [row["tag"] for row in town["details"]] == [{"text": "Keltainen", "tone": "item"}, {"text": "Punainen", "tone": "neutral"}]


def test_an_area_with_only_warnings_ahead_stands_back():
    result = features([alert("a", "wind", "orange", 3, 9, TOWN)])

    town = result["area:990"]["properties"]
    assert (town["level"], town["active"], town["opacity"]) == ("orange", False, LATER_OPACITY)
    assert town["list"]["text"] == "Tuulivaroitus · alkaa pe 15.00"


def test_warnings_further_ahead_than_asked_are_left_out():
    alerts = [alert("a", "wind", "yellow", 30, 40, TOWN), alert("b", "seaWind", "yellow", 3, 9, SEA)]

    assert list(features(alerts)) == ["area:B9X"]
    assert list(features(alerts, hours_ahead=0)) == []
    assert set(features(alerts, hours_ahead=48)) == {"area:990", "area:B9X"}


def test_other_types_ended_and_replaced_warnings_are_left_out():
    alerts = [
        alert("old", "wind", "yellow", -5, 5, TOWN),
        alert("new", "wind", "orange", -5, 5, TOWN, references=["old"]),
        alert("over", "trafficWeather", "red", -5, -1, REGION),
        alert("sea", "seaWind", "yellow", -1, 5, SEA),
    ]

    result = features(alerts, types=frozenset({"wind", "trafficWeather"}))

    assert list(result) == ["area:990"]
    assert result["area:990"]["properties"]["level"] == "orange"
    assert len(result["area:990"]["properties"]["details"]) == 1


def test_the_feed_has_its_texts_in_english_too():
    assert TEXTS["eng"].keys() == TEXTS["fin"].keys()

    [feature] = area_features([alert("a", "wind", "orange", -1, 6, TOWN)], TYPES, "eng", 24, NOW, ZONE)

    assert feature["properties"]["list"] == {"text": "Tuulivaroitus · in force until Fri 18:00", "value": "Orange"}
    assert feature["properties"]["details"][0]["value"] == "Fri 11:00–18:00"
    assert [entry["label"] for entry in feed_attributes("eng")["legend"]] == ["Yellow", "Orange", "Red"]


def test_an_area_without_a_code_is_known_by_its_name():
    nameless = CapArea("Takamaa", {}, [square(64.0, 27.0, 0.5)])

    assert list(features([alert("a", "wind", "yellow", -1, 5, nameless)])) == ["area:Takamaa"]


def test_an_outline_keeps_its_corners_and_drops_what_bends_it_less_than_a_kilometre():
    # A square some 55 km a side, with a point 300 m off its south side and one 5 km off its north side.
    ring = simplified_ring(((62.0, 25.0), (61.9973, 25.5), (62.0, 26.0), (62.5, 26.0), (62.545, 25.5), (62.5, 25.0), (62.0, 25.0)))

    assert ring == ((25.0, 62.0), (26.0, 62.0), (26.0, 62.5), (25.5, 62.545), (25.0, 62.5), (25.0, 62.0))


def test_the_map_next_changes_when_a_warning_comes_into_view_starts_or_ends():
    alerts = [alert("a", "wind", "yellow", 30, 40, TOWN)]

    assert next_change(alerts, TYPES, "fin", 24, NOW) == NOW + timedelta(hours=6)
    assert next_change(alerts, TYPES, "fin", 24, NOW + timedelta(hours=7)) == NOW + timedelta(hours=30)
    assert next_change(alerts, TYPES, "fin", 24, NOW + timedelta(hours=31)) == NOW + timedelta(hours=40)
    assert next_change([], TYPES, "fin", 24, NOW) is None


async def _setup(hass: HomeAssistant, monkeypatch, api: FakeApi, *subentries) -> MockConfigEntry:
    await hass.config.async_set_time_zone("Europe/Helsinki")
    monkeypatch.setattr("custom_components.fmi_open_data.warning_coordinator.FMISession", lambda *a, **kw: api)
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, data={CONF_LANG: "fin", CONF_STRUCTURE: STRUCTURE_VERSION}, subentries_data=list(subentries)
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_the_sensor_is_a_map_feed_of_the_areas(hass: HomeAssistant, monkeypatch, freezer):
    # FMI's messages of 15 Sep 2026: sea wind warnings for eight sea areas between them, in force on the 16th.
    freezer.move_to("2026-09-16T12:00:00+03:00")
    await _setup(hass, monkeypatch, FakeApi([SEVERAL_AREAS, BOTHNIA]), warning_map())

    state = hass.states.get(SENSOR)
    assert state.state == "8"
    assert state.attributes["map_feed_version"] == 1
    assert state.attributes["feed_type"] == "weather"
    assert [entry["label"] for entry in state.attributes["legend"]] == ["Keltainen", "Oranssi", "Punainen"]
    collection = state.attributes["geojson"]
    assert len(collection["features"]) == 8
    gulf = next(feature for feature in collection["features"] if feature["properties"]["name"] == "Suomenlahden länsiosa")
    assert gulf["properties"]["kind"] == "weather.warning"
    assert gulf["geometry"]["type"] == "MultiPolygon"
    [[ring]] = gulf["geometry"]["coordinates"]
    assert ring[0] == ring[-1]
    # FMI draws its sea areas with a point every few kilometres, so little is left out of them.
    assert 4 <= len(ring) <= 114
    # Its second polygon is a triangle a few hundred metres across.
    bothnian = next(feature for feature in collection["features"] if feature["properties"]["name"] == "Selkämeren eteläosa")
    assert len(bothnian["geometry"]["coordinates"]) == 1


async def test_the_map_is_unavailable_while_the_feed_cannot_be_read(hass: HomeAssistant, monkeypatch, freezer):
    freezer.move_to("2026-09-16T12:00:00+03:00")
    api = FakeApi([SEVERAL_AREAS])
    entry = await _setup(hass, monkeypatch, api, warning_map())

    api.feed_down = True
    freezer.tick(60)
    for coordinator in entry.runtime_data.coordinators:
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(SENSOR).state == "unavailable"


async def test_adding_and_changing_a_map(hass: HomeAssistant, monkeypatch, freezer):
    freezer.move_to("2026-09-16T12:00:00+03:00")
    entry = await _setup(hass, monkeypatch, FakeApi([SEVERAL_AREAS]))
    subentries = hass.config_entries.subentries

    result = await subentries.async_init((entry.entry_id, SUBENTRY_WARNING_MAP), context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    form = {CONF_LABEL: "Varoituskartta", CONF_WARNING_TYPES: [], CONF_HOURS_AHEAD: 12}
    result = await subentries.async_configure(result["flow_id"], form)
    assert result["errors"] == {"base": "no_warning_types"}

    result = await subentries.async_configure(result["flow_id"], {**form, CONF_WARNING_TYPES: ["sea_wind", "wind"]})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    assert subentry.data == {CONF_LABEL: "Varoituskartta", CONF_WARNING_TYPES: ["seaWind", "wind"], CONF_HOURS_AHEAD: 12}
    assert hass.states.get(SENSOR).state == "5"

    result = await subentries.async_init(
        (entry.entry_id, SUBENTRY_WARNING_MAP), context={"source": SOURCE_RECONFIGURE, "subentry_id": subentry.subentry_id}
    )
    result = await subentries.async_configure(result["flow_id"], {**form, CONF_WARNING_TYPES: ["wind"]})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert hass.states.get(SENSOR).state == "0"
