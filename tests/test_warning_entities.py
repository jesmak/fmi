"""A warnings place end to end: the level sensor, its attributes and the event entity."""

from datetime import timedelta
from pathlib import Path

import pytest
from conftest import place
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fmi_open_data.const import (
    API_WARNINGS_FEED_URL,
    CONF_LABEL,
    CONF_LANG,
    CONF_LOCATION,
    CONF_STRUCTURE,
    CONF_WARNING_TYPES,
    DOMAIN,
    STRUCTURE_VERSION,
    SUBENTRY_WARNINGS,
    WARNING_TYPES,
)
from custom_components.fmi_open_data.session import FMIException

pytestmark = pytest.mark.asyncio

FIXTURES = Path(__file__).parent / "fixtures"
SEVERAL_AREAS = "https://alerts.fmi.fi/cap/test/several-areas.xml"
BOTHNIA = "https://alerts.fmi.fi/cap/test/bothnia.xml"
DOCUMENTS = {
    SEVERAL_AREAS: (FIXTURES / "cap_sea_wind_several_areas.xml").read_bytes(),
    BOTHNIA: (FIXTURES / "cap_sea_wind_bothnia.xml").read_bytes(),
}

SENSOR = "sensor.varoitukset_suomenlinna_warning_level"
EVENT = "event.varoitukset_suomenlinna_warning"


class FakeApi:
    """Stands in for FMISession: serves the feed and the documents from the fixtures."""

    def __init__(self, urls: list[str]):
        self.urls = urls
        self.failing: set[str] = set()
        self.feed_requests = 0

    def get_document(self, url: str) -> bytes:
        if url == API_WARNINGS_FEED_URL:
            self.feed_requests += 1
            entries = "".join(f'<entry><link type="application/cap+xml" href="{u}" /></entry>' for u in self.urls)
            return f'<feed xmlns="http://www.w3.org/2005/Atom">{entries}</feed>'.encode()
        if url in self.failing:
            raise FMIException("Timeout error")
        return DOCUMENTS[url]


def warnings_place(label: str, latitude: float, longitude: float, radius: float = 0) -> ConfigSubentryData:
    """A warnings subentry as it was before 4.0.0."""
    location = {"latitude": latitude, "longitude": longitude, "radius": radius}
    return ConfigSubentryData(
        subentry_type=SUBENTRY_WARNINGS,
        title=label,
        unique_id=f"warnings_{label}",
        data={
            CONF_LANG: "fin",
            CONF_LABEL: label,
            CONF_LOCATION: location,
            CONF_WARNING_TYPES: WARNING_TYPES,
        },
    )


async def _setup(hass: HomeAssistant, monkeypatch, api: FakeApi, *places: ConfigSubentryData) -> MockConfigEntry:
    monkeypatch.setattr("custom_components.fmi_open_data.warning_coordinator.FMISession", lambda *a, **kw: api)
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        data={CONF_LANG: "fin", CONF_STRUCTURE: STRUCTURE_VERSION},
        subentries_data=list(places) or [place("Varoitukset Suomenlinna", 60.146, 24.988)],
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry, freezer) -> None:
    # The places share one download of the feed for a moment; step past it.
    freezer.tick(60)
    for coordinator in entry.runtime_data.coordinators:
        await coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_level_and_attributes_while_a_warning_is_in_force(hass: HomeAssistant, monkeypatch, freezer):
    freezer.move_to("2026-09-16T12:00:00+03:00")
    await _setup(hass, monkeypatch, FakeApi([SEVERAL_AREAS, BOTHNIA]))

    state = hass.states.get(SENSOR)
    assert state.state == "yellow"
    assert state.attributes["active_warnings"] == 1
    assert state.attributes["radius"] == 0
    [warning] = state.attributes["warnings"]
    assert warning["type"] == "seaWind"
    assert warning["areas"] == ["Suomenlahden länsiosa"]
    assert warning["parameters"]["windIntensity"] == 14


async def test_an_upcoming_warning_is_listed_before_it_starts(hass: HomeAssistant, monkeypatch, freezer):
    freezer.move_to("2026-09-15T12:00:00+03:00")
    await _setup(hass, monkeypatch, FakeApi([SEVERAL_AREAS]))

    state = hass.states.get(SENSOR)
    assert state.state == "none"
    assert state.attributes["active_warnings"] == 0
    assert len(state.attributes["warnings"]) == 1


async def test_warnings_already_in_force_at_startup_fire_no_event(hass: HomeAssistant, monkeypatch, freezer):
    freezer.move_to("2026-09-15T12:00:00+03:00")
    await _setup(hass, monkeypatch, FakeApi([SEVERAL_AREAS]))

    assert hass.states.get(EVENT).state == "unknown"


async def test_issued_and_cancelled_events(hass: HomeAssistant, monkeypatch, freezer):
    freezer.move_to("2026-09-15T12:00:00+03:00")
    api = FakeApi([BOTHNIA])
    entry = await _setup(hass, monkeypatch, api)
    assert hass.states.get(EVENT).state == "unknown"

    api.urls = [BOTHNIA, SEVERAL_AREAS]
    await _refresh(hass, entry, freezer)
    issued = hass.states.get(EVENT)
    assert issued.attributes["event_type"] == "issued"
    assert issued.attributes["type"] == "seaWind"
    assert issued.attributes["level"] == "yellow"

    api.urls = [BOTHNIA]
    await _refresh(hass, entry, freezer)
    cancelled = hass.states.get(EVENT)
    assert cancelled.attributes["event_type"] == "cancelled"
    assert cancelled.state != issued.state


async def test_a_warning_that_cannot_be_read_does_not_look_cancelled(hass: HomeAssistant, monkeypatch, freezer):
    freezer.move_to("2026-09-16T12:00:00+03:00")
    api = FakeApi([SEVERAL_AREAS])
    entry = await _setup(hass, monkeypatch, api)
    event_before = hass.states.get(EVENT).state

    api.urls = [SEVERAL_AREAS, BOTHNIA]
    api.failing.add(BOTHNIA)
    await _refresh(hass, entry, freezer)

    assert hass.states.get(SENSOR).state == "yellow"
    assert hass.states.get(EVENT).state == event_before


async def test_a_message_unreadable_for_an_hour_no_longer_holds_up_the_rest(hass: HomeAssistant, monkeypatch, freezer, caplog):
    freezer.move_to("2026-09-16T12:00:00+03:00")
    broken = "https://alerts.fmi.fi/cap/test/broken.xml"
    api = FakeApi([])
    entry = await _setup(hass, monkeypatch, api)
    before = hass.states.get(SENSOR).state

    api.urls = [SEVERAL_AREAS, broken]
    api.failing.add(broken)
    await _refresh(hass, entry, freezer)
    assert hass.states.get(SENSOR).state == before

    freezer.tick(timedelta(hours=1))
    await _refresh(hass, entry, freezer)
    await _refresh(hass, entry, freezer)

    assert hass.states.get(SENSOR).state == "yellow"
    assert caplog.text.count("unreadable for an hour") == 1


async def test_a_warning_whose_reissue_cannot_be_read_does_not_look_cancelled_after_an_hour(hass: HomeAssistant, monkeypatch, freezer):
    freezer.move_to("2026-09-16T12:00:00+03:00")
    reissue = "https://alerts.fmi.fi/cap/test/reissue.xml"
    api = FakeApi([SEVERAL_AREAS])
    entry = await _setup(hass, monkeypatch, api)
    event_before = hass.states.get(EVENT).state

    # FMI replaced the message with one that can't be read.
    api.urls = [reissue]
    api.failing.add(reissue)
    await _refresh(hass, entry, freezer)
    freezer.tick(timedelta(hours=1))
    await _refresh(hass, entry, freezer)
    await _refresh(hass, entry, freezer)

    assert hass.states.get(SENSOR).state == "yellow"
    assert hass.states.get(EVENT).state == event_before


async def test_places_share_one_download_of_the_feed(hass: HomeAssistant, monkeypatch, freezer):
    freezer.move_to("2026-09-16T12:00:00+03:00")
    api = FakeApi([SEVERAL_AREAS, BOTHNIA])
    await _setup(
        hass,
        monkeypatch,
        api,
        place("Varoitukset Suomenlinna", 60.146, 24.988),
        place("Varoitukset Hanko", 59.823, 22.968, 2000),
    )

    assert api.feed_requests == 1
    assert hass.states.get("sensor.varoitukset_suomenlinna_warning_level").state == "yellow"
    assert hass.states.get("sensor.varoitukset_hanko_warning_level") is not None
