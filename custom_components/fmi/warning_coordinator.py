"""Keeps a warnings entry up to date and works out what changed between refreshes."""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from xml.etree.ElementTree import ParseError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .cap import CapAlert, FMIWarning, WarningsFilter, parse_alert, parse_warning_feed, warning_changes, warnings_for
from .const import API_WARNINGS_FEED_URL, CONF_LABEL, DOMAIN, WARNINGS_SCAN_INTERVAL
from .session import FMISession, FMIException

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class WarningsData:
    # The warnings in force or coming up that concern the place, by identifier.
    warnings: dict[str, FMIWarning]
    # What happened since the previous refresh, as (event type, warning).
    changes: list[tuple[str, FMIWarning]]
    updated: datetime


class FMIWarningsCoordinator(DataUpdateCoordinator[WarningsData]):

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.data[CONF_LABEL]}",
            update_interval=timedelta(minutes=WARNINGS_SCAN_INTERVAL),
        )
        self.warnings_filter = WarningsFilter.from_entry_data(entry.data)
        # A CAP message never changes once published, so each is downloaded once, by address.
        self._alerts: dict[str, CapAlert] = {}
        self._previous: dict[str, FMIWarning] | None = None

    async def _async_update_data(self) -> WarningsData:
        api = FMISession()

        try:
            urls = parse_warning_feed(await self.hass.async_add_executor_job(api.get_document, API_WARNINGS_FEED_URL))
        except (FMIException, ParseError) as exception:
            raise UpdateFailed(f"Could not read FMI's warning feed: {exception}") from exception

        missing = False
        for url in urls:
            if url in self._alerts:
                continue
            try:
                self._alerts[url] = parse_alert(await self.hass.async_add_executor_job(api.get_document, url))
            except (FMIException, ParseError) as exception:
                _LOGGER.debug(f"Could not read warning {url}: {exception}")
                missing = True

        self._alerts = {url: alert for url, alert in self._alerts.items() if url in urls}

        if missing:
            # Without every message, a warning could look cancelled when it is not.
            # Keep what was known and try again at the next refresh.
            if self.data is None:
                raise UpdateFailed("Could not read all of FMI's warnings")
            return WarningsData(self.data.warnings, [], self.data.updated)

        now = dt_util.utcnow()
        current = warnings_for(self._alerts.values(), self.warnings_filter, now)
        # The first refresh only learns what is already in force: announcing
        # it as new would repeat on every restart of Home Assistant.
        changes = [] if self._previous is None else warning_changes(self._previous, current, now)
        self._previous = current

        return WarningsData(current, changes, now)
