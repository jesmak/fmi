"""FMI data and weather warnings for Home Assistant.

One config entry holds the language and the stale data settings. Every sensor,
and every place whose warnings are followed, is a config subentry with its own
coordinator.
"""

import asyncio
import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, SUBENTRY_SENSOR, SUBENTRY_WARNINGS
from .migration import async_migrate_to_subentries
from .query_coordinator import FMIQueryCoordinator
from .warning_coordinator import FMIWarningsCoordinator, WarningFeed

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "event"]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class FMIRuntimeData:
    # By subentry id.
    coordinators: dict[str, FMIQueryCoordinator | FMIWarningsCoordinator]
    warning_feed: WarningFeed


type FMIConfigEntry = ConfigEntry[FMIRuntimeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    # Runs before any entry is set up, so the old one-entry-per-sensor entries
    # are merged before Home Assistant would try to set them up one by one.
    await async_migrate_to_subentries(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FMIConfigEntry) -> bool:
    feed = WarningFeed(hass)
    coordinators = {}

    for subentry in entry.subentries.values():
        if subentry.subentry_type == SUBENTRY_SENSOR:
            coordinators[subentry.subentry_id] = FMIQueryCoordinator(hass, entry, subentry)
        elif subentry.subentry_type == SUBENTRY_WARNINGS:
            coordinators[subentry.subentry_id] = FMIWarningsCoordinator(hass, entry, subentry, feed)

    entry.runtime_data = FMIRuntimeData(coordinators, feed)
    _remove_orphaned_issues(hass, entry)

    # A sensor that cannot be read becomes unavailable and keeps retrying; it
    # does not stop the others from being set up.
    await asyncio.gather(*(coordinator.async_refresh() for coordinator in coordinators.values()))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Adding, changing or removing a subentry, or changing the settings, reloads everything.
    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    return True


async def async_update_listener(hass: HomeAssistant, entry: FMIConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: FMIConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: FMIConfigEntry) -> None:
    # Repair issues are not persistent, but they would stay until a restart.
    for domain, issue_id in list(ir.async_get(hass).issues):
        if domain == DOMAIN:
            ir.async_delete_issue(hass, DOMAIN, issue_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Entries from before 3.0 are merged into one in async_setup, which runs first.
    # A newer version than this means Home Assistant was downgraded.
    return entry.version <= 3


def _remove_orphaned_issues(hass: HomeAssistant, entry: FMIConfigEntry) -> None:
    """Drop no-data repair issues of sensors that no longer exist."""
    registry = ir.async_get(hass)
    for domain, issue_id in list(registry.issues):
        if domain == DOMAIN and issue_id.startswith("no_data_") and issue_id.removeprefix("no_data_") not in entry.subentries:
            ir.async_delete_issue(hass, DOMAIN, issue_id)
