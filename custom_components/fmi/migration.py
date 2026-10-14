"""From one config entry per sensor (versions 1 and 2) to one entry with a subentry per sensor (version 3).

Every old entry becomes a subentry of a single FMI entry, and its entities move
with it. Entity IDs do not change, so history, statistics, dashboards and
automations keep working. Modelled on the migration in Home Assistant's own
OpenAI Conversation integration.
"""

import logging
from collections import Counter
from types import MappingProxyType

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from .const import (
    CONF_ENTRY_TYPE,
    CONF_LANG,
    CONF_NO_DATA_ISSUE,
    CONF_NO_DATA_ISSUE_HOURS,
    DEFAULT_NO_DATA_ISSUE,
    DEFAULT_NO_DATA_ISSUE_HOURS,
    DOMAIN,
    ENTRY_TYPE_WARNINGS,
    SUBENTRY_SENSOR,
    SUBENTRY_WARNINGS,
)
from .query_coordinator import build_unique_id
from .warning_coordinator import build_warnings_unique_id

_LOGGER = logging.getLogger(__name__)

VERSION = 3
TITLE = "FMI"


async def async_migrate_to_subentries(hass: HomeAssistant) -> None:
    # The enabled entries come first, so the entry that is kept is an enabled one.
    entries = sorted(hass.config_entries.async_entries(DOMAIN), key=lambda entry: entry.disabled_by is not None)
    old_entries = [entry for entry in entries if entry.version < VERSION]

    if not old_entries:
        return

    parent = next((entry for entry in entries if entry.version >= VERSION), old_entries[0])
    all_disabled = all(entry.disabled_by is not None for entry in entries)
    _LOGGER.info(f"Moving {len(old_entries)} FMI config entries into subentries of {parent.title}")

    registry = er.async_get(hass)

    for entry in old_entries:
        subentry = _subentry_for(entry)
        existing = next((item for item in parent.subentries.values() if item.unique_id == subentry.unique_id), None)

        if existing is not None:
            # A migration cut short left this entry behind after its subentry was
            # made, or two old entries measured the same thing. Either way its
            # entities belong with the subentry that is already there.
            subentry = existing
        else:
            hass.config_entries.async_add_subentry(parent, subentry)

        for registered in er.async_entries_for_config_entry(registry, entry.entry_id):
            disabled_by = registered.disabled_by
            if disabled_by is er.RegistryEntryDisabler.CONFIG_ENTRY and not all_disabled:
                # Moving to an enabled entry would clear this flag; the user had
                # the old entry disabled, so keep the entity disabled.
                disabled_by = er.RegistryEntryDisabler.USER
            registry.async_update_entity(
                registered.entity_id,
                config_entry_id=parent.entry_id,
                config_subentry_id=subentry.subentry_id,
                disabled_by=disabled_by,
                new_unique_id=subentry.subentry_id,
            )

        ir.async_delete_issue(hass, DOMAIN, f"no_data_{entry.entry_id}")

        if entry.entry_id != parent.entry_id:
            await hass.config_entries.async_remove(entry.entry_id)

    if parent.version < VERSION:
        # Last, because until now the parent's data was still that of its own sensor.
        hass.config_entries.async_update_entry(
            parent,
            title=TITLE,
            data={CONF_LANG: _most_common_language(old_entries)},
            options=_most_common_stale_data_settings(old_entries),
            unique_id=None,
            version=VERSION,
        )


def _subentry_for(entry: ConfigEntry) -> ConfigSubentry:
    data = dict(entry.data)
    is_warnings = data.pop(CONF_ENTRY_TYPE, None) == ENTRY_TYPE_WARNINGS
    # Stale data settings are shared by every sensor from now on.
    data.pop(CONF_NO_DATA_ISSUE, None)
    data.pop(CONF_NO_DATA_ISSUE_HOURS, None)

    return ConfigSubentry(
        data=MappingProxyType(data),
        subentry_type=SUBENTRY_WARNINGS if is_warnings else SUBENTRY_SENSOR,
        title=entry.title,
        unique_id=build_warnings_unique_id(data) if is_warnings else build_unique_id(data),
    )


def _most_common_language(entries: list[ConfigEntry]) -> str:
    # Each subentry keeps its own language; this is only the default for new ones.
    return Counter(entry.data[CONF_LANG] for entry in entries).most_common(1)[0][0]


def _most_common_stale_data_settings(entries: list[ConfigEntry]) -> dict:
    settings = Counter(
        (entry.data.get(CONF_NO_DATA_ISSUE, DEFAULT_NO_DATA_ISSUE), entry.data.get(CONF_NO_DATA_ISSUE_HOURS, DEFAULT_NO_DATA_ISSUE_HOURS))
        for entry in entries
        # Sensors set up before the settings existed say nothing about the user's choice.
        if CONF_NO_DATA_ISSUE_HOURS in entry.data
    )
    enabled, hours = settings.most_common(1)[0][0] if settings else (DEFAULT_NO_DATA_ISSUE, DEFAULT_NO_DATA_ISSUE_HOURS)
    return {CONF_NO_DATA_ISSUE: enabled, CONF_NO_DATA_ISSUE_HOURS: hours}
