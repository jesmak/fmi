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

from .cap import CapAlert, FMIWarning, WarningsFilter, parse_warning_feed, warning_changes, warnings_for
from .const import API_WARNINGS_FEED_URL, CONF_LANG, DOMAIN, WARNINGS_SCAN_INTERVAL
from .session import FMIException, FMISession

_LOGGER = logging.getLogger(__name__)

# Every place refreshes on the same schedule, so one download serves them all.
FEED_REUSE_TIME = timedelta(seconds=30)
# How long the last warnings are kept while FMI's feed cannot be read.
OUTAGE_GRACE = timedelta(hours=1)


class WarningFeed:
    """FMI's warning feed and the CAP messages in it, shared by every warnings subentry."""

    def __init__(self, hass: HomeAssistant):
        self._hass = hass
        self._alerts: list[CapAlert] = []
        # The feed is a few megabytes and changes a few times a day, so it is asked for only when it has changed.
        self._etag: str | None = None
        self._fetched_at: datetime | None = None
        self._lock = asyncio.Lock()

    async def async_alerts(self) -> list[CapAlert]:
        """The messages in the feed. Raises FMIException or ParseError when the feed cannot be read."""
        async with self._lock:
            now = dt_util.utcnow()
            if self._fetched_at is None or now - self._fetched_at >= FEED_REUSE_TIME:
                self._alerts, self._etag = await self._hass.async_add_executor_job(self._read)
                self._fetched_at = now
            return list(self._alerts)

    def _read(self) -> tuple[list[CapAlert], str | None]:
        changed = FMISession().get_changed_document(API_WARNINGS_FEED_URL, self._etag)
        if changed is None:
            return self._alerts, self._etag
        content, etag = changed
        return parse_warning_feed(content), etag


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
        # Since when FMI's feed has not been readable.
        self._down_since: datetime | None = None

    async def _async_update_data(self) -> WarningsData:
        now = dt_util.utcnow()
        try:
            alerts = await self._feed.async_alerts()
        except (FMIException, ParseError) as exception:
            if self._down_since is None:
                self._down_since = now
            if self.data is not None and now - self._down_since < OUTAGE_GRACE:
                _LOGGER.debug(f"Could not read FMI's warning feed, keeping the last warnings: {exception}")
                return WarningsData(self.data.warnings, [], self.data.updated)
            raise UpdateFailed(f"Could not read FMI's warning feed: {exception}") from exception
        self._down_since = None

        current = warnings_for(alerts, self.warnings_filter, now)
        # The first refresh only learns what is already in force: announcing
        # it as new would repeat on every restart of Home Assistant.
        changes = [] if self._previous is None else warning_changes(self._previous, current, now)
        self._previous = current

        return WarningsData(current, changes, now)
