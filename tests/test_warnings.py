"""Reading FMI's warning feed and deciding which warnings concern a place.

The fixtures are real messages from FMI's CAP feed on 15 Sep 2026: a yellow sea
wind warning for five sea areas, valid 16 Sep 9.00-21.00, and one for the Sea of
Bothnia and the Quark.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from custom_components.fmi.cap import (
    WarningsFilter,
    distance_to_outline_m,
    highest_level,
    parse_alert,
    parse_references,
    parse_warning_feed,
    point_in_polygon,
    warning_changes,
    warnings_for,
)
from custom_components.fmi.const import WARNING_TYPES

FIXTURES = Path(__file__).parent / "fixtures"
FINNISH_TIME = timezone(timedelta(hours=3))

SEVERAL_AREAS = parse_alert((FIXTURES / "cap_sea_wind_several_areas.xml").read_bytes())
BOTHNIA = parse_alert((FIXTURES / "cap_sea_wind_bothnia.xml").read_bytes())

BEFORE = datetime(2026, 9, 15, 12, 0, tzinfo=FINNISH_TIME)
DURING = datetime(2026, 9, 16, 12, 0, tzinfo=FINNISH_TIME)
AFTER = datetime(2026, 9, 16, 22, 0, tzinfo=FINNISH_TIME)

SUOMENLINNA = (60.146, 24.988)  # an island in the western Gulf of Finland
HELSINKI_CENTRE = (60.170, 24.941)  # the mainland, a couple of kilometres from the sea
NAGU = (60.19, 21.91)  # the Archipelago Sea


def place(position, radius=0, types=WARNING_TYPES, language="fin") -> WarningsFilter:
    return WarningsFilter(position[0], position[1], radius, frozenset(types), language)


def test_feed_lists_the_cap_documents():
    urls = parse_warning_feed((FIXTURES / "warnings_feed.xml").read_bytes())

    assert len(urls) == 4
    assert all(url.startswith("https://alerts.fmi.fi/cap/") and url.endswith(".xml") for url in urls)


def test_alert_is_parsed_in_every_language():
    assert SEVERAL_AREAS.msg_type == "Update"
    assert SEVERAL_AREAS.references

    english = SEVERAL_AREAS.info("eng")
    assert english.language == "en-GB"
    assert english.event_code == "seaWind"
    assert english.parameters["windIntensity"] == "14"
    assert english.parameters["color"] == "yellow"
    assert [area.geocodes.get("METAREA") for area in english.areas] == ["B5W", "B1N", "B4E", "B1S", "B7E"]
    assert all(area.polygons for area in english.areas)

    assert SEVERAL_AREAS.info("fin").headline.startswith("Keltainen tuulivaroitus merelle")


def test_references_are_identifiers():
    text = "sender,urn:oid:1,2026-09-15T08:00:00+03:00 sender,urn:oid:2,2026-09-15T09:00:00+03:00"

    assert parse_references(text) == ["urn:oid:1", "urn:oid:2"]
    assert parse_references("") == []


def test_geometry():
    square = [(60.0, 25.0), (60.0, 26.0), (61.0, 26.0), (61.0, 25.0)]

    assert point_in_polygon(60.5, 25.5, square)
    assert not point_in_polygon(60.5, 26.5, square)
    # 0.1 degrees of longitude at 60.5 N is about 5.5 km.
    assert 5000 < distance_to_outline_m(60.5, 26.1, square) < 6000


def test_an_island_is_inside_its_sea_area_and_the_mainland_is_not():
    [warning] = warnings_for([SEVERAL_AREAS, BOTHNIA], place(SUOMENLINNA), DURING).values()

    assert warning.areas == ("Suomenlahden länsiosa",)
    assert warnings_for([SEVERAL_AREAS], place(HELSINKI_CENTRE), DURING) == {}


def test_a_radius_reaches_a_nearby_sea_area():
    assert warnings_for([SEVERAL_AREAS], place(HELSINKI_CENTRE, radius=5000), DURING)


def test_warning_types_are_filtered():
    assert warnings_for([SEVERAL_AREAS], place(SUOMENLINNA, types=["wind", "rain"]), DURING) == {}


def test_warning_fields_are_in_the_entry_language():
    [warning] = warnings_for([SEVERAL_AREAS], place(NAGU, language="eng"), DURING).values()

    assert warning.type == "seaWind"
    assert warning.level == "yellow"
    assert warning.probability == 40
    assert warning.areas == ("Sea of Archipelago",)
    assert warning.impacts == "Possibly dangerous for recreational crafts and small boats."
    assert warning.parameters["windIntensity"] == 14
    assert warning.parameters["windIntensityUom"] == "m/s"
    assert warning.parameters["windDirection"] == 180
    assert "color" not in warning.parameters

    data = warning.as_dict()
    assert data["onset"] == "2026-09-16T09:00:00+03:00"
    assert data["expires"] == "2026-09-16T21:00:00+03:00"


def test_level_is_the_highest_in_force_now():
    warnings = warnings_for([SEVERAL_AREAS], place(SUOMENLINNA), BEFORE)
    [warning] = warnings.values()

    assert highest_level(warnings, BEFORE) == "none", "announced for tomorrow, not in force yet"
    assert highest_level(warnings, DURING) == "yellow"
    assert highest_level({**warnings, "orange": replace(warning, identifier="orange", level="orange")},
                         DURING) == "orange"


def test_expired_cancelled_and_replaced_messages_are_left_out():
    assert warnings_for([SEVERAL_AREAS], place(SUOMENLINNA), AFTER) == {}

    cancel = replace(SEVERAL_AREAS, identifier="cancel", msg_type="Cancel", references=[SEVERAL_AREAS.identifier])
    assert warnings_for([SEVERAL_AREAS, cancel], place(SUOMENLINNA), DURING) == {}

    newer = replace(SEVERAL_AREAS, identifier="newer", references=[SEVERAL_AREAS.identifier])
    assert list(warnings_for([SEVERAL_AREAS, newer], place(SUOMENLINNA), DURING)) == ["newer"]


def _warning(identifier: str, references=(), **changes):
    [base] = warnings_for([SEVERAL_AREAS], place(SUOMENLINNA), BEFORE).values()
    return replace(base, identifier=identifier, references=tuple(references), **changes)


def test_a_new_warning_is_issued():
    warning = _warning("a")

    assert warning_changes({}, {"a": warning}, BEFORE) == [("issued", warning)]


def test_an_unchanged_reissue_is_silent():
    assert warning_changes({"a": _warning("a")}, {"b": _warning("b", references=["a"])}, BEFORE) == []


def test_a_changed_reissue_is_updated():
    newer = _warning("b", references=["a"], level="orange")

    assert warning_changes({"a": _warning("a")}, {"b": newer}, BEFORE) == [("updated", newer)]


def test_a_reissue_is_recognised_without_its_reference():
    """If a refresh was missed, the reference may point to a version never seen."""
    assert warning_changes({"a": _warning("a")}, {"c": _warning("c", references=["b"])}, BEFORE) == []


def test_a_warning_removed_before_it_expires_is_cancelled():
    warning = _warning("a")

    assert warning_changes({"a": warning}, {}, BEFORE) == [("cancelled", warning)]


def test_a_warning_that_runs_out_ends_quietly():
    assert warning_changes({"a": _warning("a")}, {}, AFTER) == []
