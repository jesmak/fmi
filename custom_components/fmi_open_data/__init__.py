"""FMI data and weather warnings for Home Assistant.

One config entry holds the language and the stale data settings. Every station, with the measurements read there,
and every place, with its weather forecast and warnings, is a config subentry and a device. Each measurement, and
each place's forecast and warnings, has its own coordinator.
"""

import asyncio
import logging
from dataclasses import dataclass

import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_MEASUREMENTS,
    CONF_STRUCTURE,
    CONF_WARNING_TYPES,
    CONF_WEATHER,
    DOMAIN,
    STRUCTURE_VERSION,
    SUBENTRY_PLACE,
    SUBENTRY_STATION,
)
from .migration import CONF_MOVE_FROM, async_check_old_folder, async_move_old_entries
from .query_coordinator import FMIQueryCoordinator
from .services import async_setup_services
from .structure import async_restructure, device_info
from .warning_coordinator import FMIWarningsCoordinator, WarningFeed
from .weather_coordinator import FMIWeatherCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "event", "weather"]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# The platforms each kind of coordinator has entities on.
ENTITY_DOMAINS = {
    FMIQueryCoordinator: ("sensor", "binary_sensor"),
    FMIWarningsCoordinator: ("sensor", "event"),
    FMIWeatherCoordinator: ("weather",),
}


@dataclass
class FMIRuntimeData:
    coordinators: list[FMIQueryCoordinator | FMIWarningsCoordinator | FMIWeatherCoordinator]
    warning_feed: WarningFeed
    # By subentry id.
    devices: dict[str, DeviceInfo]


type FMIConfigEntry = ConfigEntry[FMIRuntimeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FMIConfigEntry) -> bool:
    if CONF_MOVE_FROM in entry.data:
        await async_move_old_entries(hass, entry)
    await async_check_old_folder(hass)
    if entry.data.get(CONF_STRUCTURE) != STRUCTURE_VERSION:
        await async_restructure(hass, entry)
    seen = _subentries(entry)

    feed = WarningFeed(hass)
    coordinators: list[FMIQueryCoordinator | FMIWarningsCoordinator | FMIWeatherCoordinator] = []

    for subentry in entry.subentries.values():
        if subentry.subentry_type == SUBENTRY_STATION:
            coordinators += [FMIQueryCoordinator(hass, entry, subentry, measurement) for measurement in subentry.data[CONF_MEASUREMENTS]]
        elif subentry.subentry_type == SUBENTRY_PLACE:
            if subentry.data.get(CONF_WARNING_TYPES):
                coordinators.append(FMIWarningsCoordinator(hass, entry, subentry, feed))
            if subentry.data.get(CONF_WEATHER):
                coordinators.append(FMIWeatherCoordinator(hass, entry, subentry))

    entry.runtime_data = FMIRuntimeData(
        coordinators, feed, {subentry_id: device_info(subentry) for subentry_id, subentry in entry.subentries.items()}
    )
    _remove_dropped_entities(hass, entry, coordinators)
    _remove_orphaned_issues(hass, coordinators)

    # A sensor that cannot be read becomes unavailable and keeps retrying; it
    # does not stop the others from being set up.
    await asyncio.gather(*(coordinator.async_refresh() for coordinator in coordinators))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Adding, changing or removing a subentry, or changing the settings, reloads everything.
    entry.async_on_unload(entry.add_update_listener(async_update_listener))
    # A flow can change several subentries in a row. The first change starts a reload at once, so this setup may
    # have begun before the rest, while no listener was there to hear them.
    if _subentries(entry) != seen:
        hass.config_entries.async_schedule_reload(entry.entry_id)

    return True


async def async_update_listener(hass: HomeAssistant, entry: FMIConfigEntry) -> None:
    hass.config_entries.async_schedule_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: FMIConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: FMIConfigEntry) -> None:
    # Repair issues are not persistent, but they would stay until a restart.
    for domain, issue_id in list(ir.async_get(hass).issues):
        if domain == DOMAIN:
            ir.async_delete_issue(hass, DOMAIN, issue_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Every entry of this domain is created at version 3, and a newer one means Home Assistant was downgraded.
    return entry.version <= 3


def _subentries(entry: FMIConfigEntry) -> dict[str, str]:
    return {subentry_id: repr((subentry.title, dict(subentry.data))) for subentry_id, subentry in entry.subentries.items()}


def _remove_dropped_entities(hass: HomeAssistant, entry: FMIConfigEntry, coordinators) -> None:
    """Remove the entities of measurements removed from a station, and of a place's forecast or warnings switched off.

    Only the entities of the entry's current subentries are looked at. Removing a subentry removes its own.
    """
    expected = {(domain, coordinator.unique_id) for coordinator in coordinators for domain in ENTITY_DOMAINS[type(coordinator)]}
    registry = er.async_get(hass)
    for registered in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registered.config_subentry_id in entry.subentries and (registered.domain, registered.unique_id) not in expected:
            registry.async_remove(registered.entity_id)


def _remove_orphaned_issues(hass: HomeAssistant, coordinators) -> None:
    """Drop no-data repair issues of measurements that no longer exist."""
    current = {coordinator.issue_id for coordinator in coordinators if isinstance(coordinator, FMIQueryCoordinator)}
    for domain, issue_id in list(ir.async_get(hass).issues):
        if domain == DOMAIN and issue_id.startswith("no_data_") and issue_id not in current:
            ir.async_delete_issue(hass, DOMAIN, issue_id)
