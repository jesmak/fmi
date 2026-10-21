"""Weather warnings: the shared warning feed, and keeping each place's warnings up to date."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from xml.etree.ElementTree import ParseError

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .cap import EVENT_CANCELLED, CapAlert, FMIWarning, WarningsFilter, parse_alert, parse_warning_feed, warning_changes, warnings_for
from .const import API_WARNINGS_FEED_URL, CONF_LANG, DOMAIN, WARNINGS_SCAN_INTERVAL
from .session import FMIException, FMISession

_LOGGER = logging.getLogger(__name__)

# Every place refreshes on the same schedule, so one download serves them all.
FEED_REUSE_TIME = timedelta(seconds=30)
# How long the last warnings are kept while FMI's feed, or some of the messages in it, cannot be read.
UNREADABLE_GRACE = timedelta(hours=1)


class WarningFeed:
    """FMI's warning feed and the CAP messages in it, shared by every warnings subentry."""

    def __init__(self, hass: HomeAssistant):
        self._hass = hass
        # A CAP message never changes once published, so each is downloaded once, by address.
        self._alerts: dict[str, CapAlert] = {}
        self._unreadable: list[str] = []
        self._fetched_at: datetime | None = None
        self._lock = asyncio.Lock()

    async def async_alerts(self) -> tuple[list[CapAlert], list[str]]:
        """The messages in the feed, and the addresses of those that could not be read.

        Raises FMIException or ParseError when the feed itself cannot be read.
        """
        async with self._lock:
            now = dt_util.utcnow()
            if self._fetched_at is None or now - self._fetched_at >= FEED_REUSE_TIME:
                await self._async_download()
                self._fetched_at = now
            return list(self._alerts.values()), list(self._unreadable)

    async def _async_download(self) -> None:
        api = FMISession()
        urls = parse_warning_feed(await self._hass.async_add_executor_job(api.get_document, API_WARNINGS_FEED_URL))

        unreadable = []
        for url in urls:
            if url in self._alerts:
                continue
            try:
                self._alerts[url] = parse_alert(await self._hass.async_add_executor_job(api.get_document, url))
            except (FMIException, ParseError) as exception:
                _LOGGER.debug(f"Could not read warning {url}: {exception}")
                unreadable.append(url)

        self._alerts = {url: alert for url, alert in self._alerts.items() if url in urls}
        self._unreadable = unreadable


@dataclass(frozen=True)
class WarningsData:
    # The warnings in force or coming up that concern the place, by identifier.
    warnings: dict[str, FMIWarning]
    # What happened since the previous refresh, as (event type, warning).
    changes: list[tuple[str, FMIWarning]]
    # When the warnings were last worked out from the feed. A refresh that keeps the last warnings keeps this too.
    updated: datetime


class FMIWarningsCoordinator(DataUpdateCoordinator[WarningsData]):
    """The warnings for one place."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, subentry: ConfigSubentry, feed: WarningFeed):
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {subentry.title}",
            update_interval=timedelta(minutes=WARNINGS_SCAN_INTERVAL),
        )
        self.subentry = subentry
        self.unique_id = subentry.subentry_id
        # The warnings' texts in the entry's language.
        self.warnings_filter = WarningsFilter.from_entry_data({**subentry.data, CONF_LANG: entry.data[CONF_LANG]})
        self._feed = feed
        self._previous: dict[str, FMIWarning] | None = None
        # Since when FMI's warnings have been incomplete: the feed or some of its messages could not be read.
        self._incomplete_since: datetime | None = None
        self._warned = False

    async def _async_update_data(self) -> WarningsData:
        now = dt_util.utcnow()
        try:
            alerts, unreadable = await self._feed.async_alerts()
        except (FMIException, ParseError) as exception:
            if self._incomplete_since is None:
                self._incomplete_since = now
            # The last warnings are kept while they were worked out less than an hour ago, or FMI's warnings have
            # been incomplete for less than an hour, so neither an outage nor unreadable messages shorten the other.
            if self.data is not None and now - max(self.data.updated, self._incomplete_since) < UNREADABLE_GRACE:
                _LOGGER.debug(f"Could not read FMI's warning feed, keeping the last warnings: {exception}")
                return WarningsData(self.data.warnings, [], self.data.updated)
            raise UpdateFailed(f"Could not read FMI's warning feed: {exception}") from exception

        if not unreadable:
            self._incomplete_since = None
            self._warned = False
        elif self._incomplete_since is None:
            self._incomplete_since = now

        if unreadable and now - self._incomplete_since < UNREADABLE_GRACE:
            # Without every message, a warning could look cancelled when it is not.
            # Keep what was known and try again at the next refresh.
            if self.data is None:
                raise UpdateFailed("Could not read all of FMI's warnings")
            return WarningsData(self.data.warnings, [], self.data.updated)

        if unreadable and not self._warned:
            self._warned = True
            _LOGGER.warning(f"FMI's warnings have been incomplete for an hour, showing the rest: {', '.join(unreadable)}")

        current = warnings_for(alerts, self.warnings_filter, now)
        # The first refresh only learns what is already in force: announcing
        # it as new would repeat on every restart of Home Assistant.
        changes = [] if self._previous is None else warning_changes(self._previous, current, now)
        if unreadable:
            # A warning that dropped out may have been reissued in a message that can't be
            # read. Keep it, and announce a cancellation only once every message is readable.
            current = {**{warning.identifier: warning for kind, warning in changes if kind == EVENT_CANCELLED}, **current}
            changes = [(kind, warning) for kind, warning in changes if kind != EVENT_CANCELLED]
        self._previous = current

        return WarningsData(current, changes, now)
