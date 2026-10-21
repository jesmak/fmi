"""A warnings place end to end: the level sensor, its attributes and the event entity."""

import logging
from datetime import datetime, timedelta
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
        self.feed_down = False
        self.feed_requests = 0

    def get_document(self, url: str) -> bytes:
        if url == API_WARNINGS_FEED_URL:
            self.feed_requests += 1
            if self.feed_down:
                raise FMIException("FMI answered 503 Service Unavailable")
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
    assert caplog.text.count("incomplete for an hour") == 1


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


async def test_an_outage_and_an_unreadable_message_after_it_share_one_hour(hass: HomeAssistant, monkeypatch, freezer):
    freezer.move_to("2026-09-16T12:00:00+03:00")
    broken = "https://alerts.fmi.fi/cap/test/broken.xml"
    api = FakeApi([])
    entry = await _setup(hass, monkeypatch, api)

    api.feed_down = True
    await _refresh(hass, entry, freezer)
    freezer.tick(timedelta(minutes=49))
    api.feed_down = False
    api.urls = [SEVERAL_AREAS, broken]
    api.failing.add(broken)
    await _refresh(hass, entry, freezer)
    assert hass.states.get(SENSOR).state == "none"

    freezer.tick(timedelta(minutes=10))
    await _refresh(hass, entry, freezer)

    assert hass.states.get(SENSOR).state == "yellow"
    assert hass.states.get(EVENT).attributes["event_type"] == "issued"


async def test_a_feed_failure_after_an_hour_of_unreadable_messages_keeps_the_rest(hass: HomeAssistant, monkeypatch, freezer):
    freezer.move_to("2026-09-16T12:00:00+03:00")
    broken = "https://alerts.fmi.fi/cap/test/broken.xml"
    api = FakeApi([])
    entry = await _setup(hass, monkeypatch, api)

    api.urls = [SEVERAL_AREAS, broken]
    api.failing.add(broken)
    await _refresh(hass, entry, freezer)
    freezer.tick(timedelta(hours=1))
    await _refresh(hass, entry, freezer)
    assert hass.states.get(SENSOR).state == "yellow"
    event_before = hass.states.get(EVENT).state

    api.feed_down = True
    await _refresh(hass, entry, freezer)
    assert hass.states.get(SENSOR).state == "yellow"
    assert hass.states.get(EVENT).state == event_before

    # An hour after the rest was last worked out, the place becomes unavailable.
    freezer.tick(timedelta(minutes=58))
    await _refresh(hass, entry, freezer)
    assert hass.states.get(SENSOR).state == "unavailable"


async def test_the_feed_back_after_a_long_outage_with_an_unreadable_message_shows_the_rest(
    hass: HomeAssistant, monkeypatch, freezer, caplog
):
    freezer.move_to("2026-09-16T12:00:00+03:00")
    broken = "https://alerts.fmi.fi/cap/test/broken.xml"
    api = FakeApi([])
    entry = await _setup(hass, monkeypatch, api)

    api.feed_down = True
    await _refresh(hass, entry, freezer)
    freezer.tick(timedelta(hours=1))
    await _refresh(hass, entry, freezer)
    assert hass.states.get(SENSOR).state == "unavailable"

    api.feed_down = False
    api.urls = [SEVERAL_AREAS, broken]
    api.failing.add(broken)
    await _refresh(hass, entry, freezer)
    await _refresh(hass, entry, freezer)

    assert hass.states.get(SENSOR).state == "yellow"
    assert hass.states.get(EVENT).attributes["event_type"] == "issued"
    assert caplog.text.count(f"incomplete for an hour, showing the rest: {broken}") == 1


BROKEN = "https://alerts.fmi.fi/cap/test/broken.xml"


# The feed at each refresh, as minutes after a complete read at 12:00 that found no warnings: "ok" is that feed again,
# "broken" has a yellow warning beside a message that can't be read, "down" can't be read at all. While held, the place
# shows the 12:00 read ("none"). Once a broken feed shows the rest, it shows the yellow warning.
@pytest.mark.parametrize(
    ("refreshes", "expected"),
    [
        # Outages: an hour from the first failed read.
        ([(10, "down"), (60, "down")], "none"),
        ([(10, "down"), (70, "down")], "unavailable"),
        ([(10, "down"), (70, "down"), (80, "ok")], "none"),
        # A good read ends the hour, and the next outage gets one of its own.
        ([(10, "down"), (40, "ok"), (50, "down"), (100, "down")], "none"),
        ([(10, "down"), (40, "ok"), (50, "down"), (110, "down")], "unavailable"),
        # Unreadable messages: an hour from the first, then the rest.
        ([(10, "broken"), (60, "broken")], "none"),
        ([(10, "broken"), (70, "broken")], "yellow"),
        # The feed failing while messages are unreadable is held to the same hour.
        ([(10, "broken"), (20, "broken"), (60, "down")], "none"),
        ([(10, "broken"), (20, "broken"), (70, "down")], "unavailable"),
        # The feed failing after the rest is shown gets an hour from when the rest was worked out.
        ([(10, "broken"), (70, "broken"), (80, "down"), (120, "down")], "yellow"),
        ([(10, "broken"), (70, "broken"), (80, "down"), (130, "down")], "unavailable"),
        # An outage and the unreadable messages after it share one hour.
        ([(10, "down"), (50, "broken"), (60, "broken")], "none"),
        ([(10, "down"), (50, "broken"), (70, "broken")], "yellow"),
        ([(10, "down"), (70, "down"), (80, "broken")], "yellow"),
    ],
)
async def test_how_long_the_last_warnings_are_kept(hass: HomeAssistant, monkeypatch, freezer, refreshes, expected):
    freezer.move_to("2026-09-16T12:00:00+03:00")
    start = datetime.fromisoformat("2026-09-16T12:00:00+03:00")
    api = FakeApi([])
    api.failing.add(BROKEN)
    entry = await _setup(hass, monkeypatch, api)

    for minutes, feed in refreshes:
        api.feed_down = feed == "down"
        api.urls = [SEVERAL_AREAS, BROKEN] if feed == "broken" else []
        freezer.move_to(start + timedelta(minutes=minutes))
        for coordinator in entry.runtime_data.coordinators:
            await coordinator.async_refresh()
        await hass.async_block_till_done()

    assert hass.states.get(SENSOR).state == expected


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
