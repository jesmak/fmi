"""A warnings place end to end: the level sensor, its attributes and the event entity."""

import logging
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from conftest import place
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

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
    """Stands in for FMISession: serves the feed with the fixtures' messages in it."""

    def __init__(self, urls: list[str]):
        self.urls = urls
        self.feed_down = False
        self.feed_requests = 0
        self.feeds_sent = 0

    def get_changed_document(self, url: str, etag: str | None) -> tuple[bytes, str] | None:
        assert url == API_WARNINGS_FEED_URL
        self.feed_requests += 1
        if self.feed_down:
            raise FMIException("FMI answered 503 Service Unavailable")
        current = f'W/"{"|".join(self.urls)}"'
        if etag == current:
            return None
        self.feeds_sent += 1
        return feed(*(DOCUMENTS[url] for url in self.urls)), current


def feed(*messages: bytes) -> bytes:
    """An Atom feed as FMI's, each entry holding its whole CAP message."""
    entries = "".join(f'<entry><content type="text/xml">{message.decode().split("?>", 1)[1]}</content></entry>' for message in messages)
    return f'<feed xmlns="http://www.w3.org/2005/Atom">{entries}</feed>'.encode()


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


async def test_a_short_outage_of_the_feed_keeps_the_warnings(hass: HomeAssistant, monkeypatch, freezer, caplog):
    freezer.move_to("2026-09-16T12:00:00+03:00")
    api = FakeApi([SEVERAL_AREAS])
    entry = await _setup(hass, monkeypatch, api)
    event_before = hass.states.get(EVENT).state
    caplog.clear()

    # The last warnings were worked out at 12:00. The outage runs until 12:59.
    api.feed_down = True
    await _refresh(hass, entry, freezer)
    freezer.tick(timedelta(minutes=57))
    await _refresh(hass, entry, freezer)
    assert hass.states.get(SENSOR).state == "yellow"
    assert hass.states.get(EVENT).state == event_before
    # The coordinator logs through the integration's own logger.
    ours = [record for record in caplog.records if record.name.startswith("custom_components.fmi_open_data")]
    assert not [record for record in ours if record.levelno >= logging.WARNING]

    api.feed_down = False
    await _refresh(hass, entry, freezer)
    assert hass.states.get(SENSOR).state == "yellow"
    assert hass.states.get(EVENT).state == event_before


async def test_a_warning_kept_through_an_outage_still_ends_on_time(hass: HomeAssistant, monkeypatch, freezer):
    freezer.move_to("2026-09-16T12:00:00+03:00")
    api = FakeApi([SEVERAL_AREAS])
    entry = await _setup(hass, monkeypatch, api)
    expires = hass.states.get(SENSOR).attributes["warnings"][0]["expires"]

    freezer.move_to(datetime.fromisoformat(expires) - timedelta(minutes=30))
    await _refresh(hass, entry, freezer)
    api.feed_down = True
    freezer.move_to(expires)
    await _refresh(hass, entry, freezer)

    state = hass.states.get(SENSOR)
    assert state.state == "none"
    assert state.attributes["active_warnings"] == 0
    assert hass.states.get(EVENT).state != "unavailable"


async def test_the_level_changes_when_a_warning_runs_out_between_reads_of_the_feed(hass: HomeAssistant, monkeypatch, freezer):
    freezer.move_to("2026-09-16T12:00:00+03:00")
    api = FakeApi([SEVERAL_AREAS])
    entry = await _setup(hass, monkeypatch, api)
    expires = datetime.fromisoformat(hass.states.get(SENSOR).attributes["warnings"][0]["expires"])
    freezer.move_to(expires - timedelta(minutes=2))
    await _refresh(hass, entry, freezer)
    assert hass.states.get(SENSOR).state != "none"
    requests = api.feed_requests

    freezer.move_to(expires)
    async_fire_time_changed(hass, expires)
    await hass.async_block_till_done()

    assert api.feed_requests == requests
    state = hass.states.get(SENSOR)
    assert state.state == "none"
    assert state.attributes["active_warnings"] == 0


async def test_an_outage_of_an_hour_makes_the_place_unavailable(hass: HomeAssistant, monkeypatch, freezer):
    freezer.move_to("2026-09-16T12:00:00+03:00")
    api = FakeApi([SEVERAL_AREAS])
    entry = await _setup(hass, monkeypatch, api)
    event_before = hass.states.get(EVENT).state

    api.feed_down = True
    await _refresh(hass, entry, freezer)
    freezer.tick(timedelta(hours=1))
    await _refresh(hass, entry, freezer)
    assert hass.states.get(SENSOR).state == "unavailable"
    assert hass.states.get(EVENT).state == "unavailable"

    # Back from the outage, a warning already known is not announced again.
    api.feed_down = False
    await _refresh(hass, entry, freezer)
    assert hass.states.get(SENSOR).state == "yellow"
    assert hass.states.get(EVENT).state == event_before


async def test_a_warning_issued_during_an_outage_is_announced_after_it(hass: HomeAssistant, monkeypatch, freezer):
    freezer.move_to("2026-09-16T12:00:00+03:00")
    api = FakeApi([])
    entry = await _setup(hass, monkeypatch, api)

    api.feed_down = True
    await _refresh(hass, entry, freezer)
    api.urls = [SEVERAL_AREAS]
    api.feed_down = False
    await _refresh(hass, entry, freezer)

    issued = hass.states.get(EVENT)
    assert issued.attributes["event_type"] == "issued"
    assert issued.attributes["type"] == "seaWind"


async def test_an_outage_after_a_good_read_gets_an_hour_of_its_own(hass: HomeAssistant, monkeypatch, freezer):
    freezer.move_to("2026-09-16T12:00:00+03:00")
    api = FakeApi([SEVERAL_AREAS])
    entry = await _setup(hass, monkeypatch, api)

    api.feed_down = True
    await _refresh(hass, entry, freezer)
    freezer.tick(timedelta(minutes=39))
    api.feed_down = False
    await _refresh(hass, entry, freezer)
    api.feed_down = True
    await _refresh(hass, entry, freezer)
    freezer.tick(timedelta(minutes=39))
    await _refresh(hass, entry, freezer)

    assert hass.states.get(SENSOR).state == "yellow"


# The feed at each refresh, as minutes after a read at 12:00 that found a yellow warning: "ok" is that feed again,
# "down" can't be read at all.
@pytest.mark.parametrize(
    ("refreshes", "expected"),
    [
        # An hour from the first failed read.
        ([(10, "down"), (60, "down")], "yellow"),
        ([(10, "down"), (70, "down")], "unavailable"),
        ([(10, "down"), (70, "down"), (80, "ok")], "yellow"),
        # A good read ends the hour, and the next outage gets one of its own.
        ([(10, "down"), (40, "ok"), (50, "down"), (100, "down")], "yellow"),
        ([(10, "down"), (40, "ok"), (50, "down"), (110, "down")], "unavailable"),
    ],
)
async def test_how_long_the_last_warnings_are_kept(hass: HomeAssistant, monkeypatch, freezer, refreshes, expected):
    freezer.move_to("2026-09-16T12:00:00+03:00")
    start = datetime.fromisoformat("2026-09-16T12:00:00+03:00")
    api = FakeApi([SEVERAL_AREAS])
    entry = await _setup(hass, monkeypatch, api)

    for minutes, state in refreshes:
        api.feed_down = state == "down"
        freezer.move_to(start + timedelta(minutes=minutes))
        for coordinator in entry.runtime_data.coordinators:
            await coordinator.async_refresh()
        await hass.async_block_till_done()

    assert hass.states.get(SENSOR).state == expected


async def test_a_feed_that_has_not_changed_is_not_downloaded_again(hass: HomeAssistant, monkeypatch, freezer):
    freezer.move_to("2026-09-16T12:00:00+03:00")
    api = FakeApi([SEVERAL_AREAS])
    entry = await _setup(hass, monkeypatch, api)

    await _refresh(hass, entry, freezer)
    assert (api.feed_requests, api.feeds_sent) == (2, 1)
    assert hass.states.get(SENSOR).state == "yellow"

    api.urls = []
    await _refresh(hass, entry, freezer)
    assert api.feeds_sent == 2
    assert hass.states.get(SENSOR).state == "none"


async def test_an_entry_without_its_message_makes_the_feed_unreadable(hass: HomeAssistant, monkeypatch, freezer):
    freezer.move_to("2026-09-16T12:00:00+03:00")
    api = FakeApi([SEVERAL_AREAS])
    entry = await _setup(hass, monkeypatch, api)

    # Without every message, a warning could look cancelled when it is not.
    monkeypatch.setattr(
        api, "get_changed_document", lambda url, etag: (b'<feed xmlns="http://www.w3.org/2005/Atom"><entry /></feed>', None)
    )
    await _refresh(hass, entry, freezer)
    assert hass.states.get(SENSOR).state == "yellow"

    freezer.tick(timedelta(hours=1))
    await _refresh(hass, entry, freezer)
    assert hass.states.get(SENSOR).state == "unavailable"


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
