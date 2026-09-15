"""Weather warnings: the shared warning feed, and keeping each place's warnings up to date."""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from xml.etree.ElementTree import ParseError

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .cap import CapAlert, FMIWarning, WarningsFilter, parse_alert, parse_warning_feed, warning_changes, warnings_for
from .const import API_WARNINGS_FEED_URL, CONF_LOCATION, CONF_WARNING_TYPES, DOMAIN, WARNINGS_SCAN_INTERVAL
from .session import FMISession, FMIException

_LOGGER = logging.getLogger(__name__)

# Every place refreshes on the same schedule, so one download serves them all.
FEED_REUSE_TIME = timedelta(seconds=30)


def build_warnings_unique_id(data: dict[str, Any]) -> str:
    """Identify a warnings subentry by the place, radius and warning types it follows."""
    location = data[CONF_LOCATION]
    return "_".join(["warnings", f"{float(location['latitude']):.4f}", f"{float(location['longitude']):.4f}",
                     str(round(float(location.get("radius") or 0))),
                     ",".join(sorted(data[CONF_WARNING_TYPES]))]).lower()


class WarningFeed:
    """FMI's warning feed and the CAP messages in it, shared by every warnings subentry."""

    def __init__(self, hass: HomeAssistant):
        self._hass = hass
        # A CAP message never changes once published, so each is downloaded once, by address.
        self._alerts: dict[str, CapAlert] = {}
        self._complete = False
        self._fetched_at: datetime | None = None
        self._lock = asyncio.Lock()

    async def async_alerts(self) -> tuple[list[CapAlert], bool]:
        """The messages in the feed, and whether every one of them could be read.

        Raises FMIException or ParseError when the feed itself cannot be read.
        """
        async with self._lock:
            now = dt_util.utcnow()
            if self._fetched_at is None or now - self._fetched_at >= FEED_REUSE_TIME:
                await self._async_download()
                self._fetched_at = now
            return list(self._alerts.values()), self._complete

    async def _async_download(self) -> None:
        api = FMISession()
        urls = parse_warning_feed(await self._hass.async_add_executor_job(api.get_document, API_WARNINGS_FEED_URL))

        complete = True
        for url in urls:
            if url in self._alerts:
                continue
            try:
                self._alerts[url] = parse_alert(await self._hass.async_add_executor_job(api.get_document, url))
            except (FMIException, ParseError) as exception:
                _LOGGER.debug(f"Could not read warning {url}: {exception}")
                complete = False

        self._alerts = {url: alert for url, alert in self._alerts.items() if url in urls}
        self._complete = complete


@dataclass(frozen=True)
class WarningsData:
    # The warnings in force or coming up that concern the place, by identifier.
    warnings: dict[str, FMIWarning]
    # What happened since the previous refresh, as (event type, warning).
    changes: list[tuple[str, FMIWarning]]
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
        self.warnings_filter = WarningsFilter.from_entry_data(subentry.data)
        self._feed = feed
        self._previous: dict[str, FMIWarning] | None = None

    async def _async_update_data(self) -> WarningsData:
        try:
            alerts, complete = await self._feed.async_alerts()
        except (FMIException, ParseError) as exception:
            raise UpdateFailed(f"Could not read FMI's warning feed: {exception}") from exception

        if not complete:
            # Without every message, a warning could look cancelled when it is not.
            # Keep what was known and try again at the next refresh.
            if self.data is None:
                raise UpdateFailed("Could not read all of FMI's warnings")
            return WarningsData(self.data.warnings, [], self.data.updated)

        now = dt_util.utcnow()
        current = warnings_for(alerts, self.warnings_filter, now)
        # The first refresh only learns what is already in force: announcing
        # it as new would repeat on every restart of Home Assistant.
        changes = [] if self._previous is None else warning_changes(self._previous, current, now)
        self._previous = current

        return WarningsData(current, changes, now)
