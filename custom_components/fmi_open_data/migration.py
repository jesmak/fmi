"""From the old `fmi` domain to `fmi_open_data`.

Home Assistant runs nothing of a domain that has no config entry, so the move
cannot start by itself: the user adds FMI Open Data once, and the config flow
offers to move the old setup. The flow creates the new entry from the old
ones, and the new entry's setup moves the entities and removes the old
entries. Entity IDs do not change, so history, statistics, dashboards and
automations keep working.

The old entries are either the version 3 entry, with a subentry per sensor and
warnings place, or the one-entry-per-sensor entries of 1.x and 2.x. Entries of
anand-p-r/fmi-hass-custom, which also uses the `fmi` domain, are never touched.
"""

import json
import logging
from collections import Counter
from pathlib import Path

from homeassistant.config_entries import ConfigEntry, ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from .const import (
    CONF_LANG,
    CONF_NO_DATA_ISSUE,
    CONF_NO_DATA_ISSUE_HOURS,
    CONF_QUERY_ID,
    DEFAULT_NO_DATA_ISSUE,
    DEFAULT_NO_DATA_ISSUE_HOURS,
    DOMAIN,
    SUBENTRY_SENSOR,
)
from .query_coordinator import build_unique_id

_LOGGER = logging.getLogger(__name__)

VERSION = 3
TITLE = "FMI"
OLD_DOMAIN = "fmi"
# In the new entry's data until its setup has moved the old entries' entities.
CONF_MOVE_FROM = "move_from"
OLD_FOLDER_ISSUE = "old_folder"


def old_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    """This integration's entries under the old domain."""
    return [
        entry
        for entry in hass.config_entries.async_entries(OLD_DOMAIN)
        # anand-p-r's entries are version 1 with coordinates and no query.
        if CONF_QUERY_ID in entry.data or (entry.version >= VERSION and CONF_LANG in entry.data)
    ]


def moved_entry(entries: list[ConfigEntry]) -> tuple[dict, dict, list[ConfigSubentryData]]:
    """The data, options and subentries of a new entry holding everything the old entries have."""
    current = next((entry for entry in entries if entry.version >= VERSION), None)
    legacy = [entry for entry in entries if entry.version < VERSION]

    subentries = {}
    for entry in entries:
        # An entry left behind by an interrupted 3.0 migration can have subentries of its own.
        for subentry in entry.subentries.values():
            subentries.setdefault(
                subentry.unique_id,
                ConfigSubentryData(
                    data=dict(subentry.data), subentry_type=subentry.subentry_type, title=subentry.title, unique_id=subentry.unique_id
                ),
            )
        if entry.version < VERSION:
            # Two old entries can measure the same thing; the first one wins.
            subentries.setdefault(_unique_id_of(entry), _subentry_for(entry))

    if current is not None:
        data, options = {CONF_LANG: current.data[CONF_LANG]}, dict(current.options)
    else:
        data, options = {CONF_LANG: _most_common_language(legacy)}, _most_common_stale_data_settings(legacy)

    return {**data, CONF_MOVE_FROM: [entry.entry_id for entry in entries]}, options, list(subentries.values())


async def async_move_old_entries(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Move the old entries' entities to this entry's subentries, then remove the old entries."""
    registry = er.async_get(hass)
    subentries = {subentry.unique_id: subentry for subentry in entry.subentries.values()}

    for old_id in entry.data[CONF_MOVE_FROM]:
        old = hass.config_entries.async_get_entry(old_id)
        if old is None:
            continue
        # The old folder may still be there and have set the entry up, and the
        # registry refuses to move an entity that is loaded. An entry still being
        # set up at startup cannot be unloaded yet, so the move is retried later.
        if not old.state.recoverable or not await hass.config_entries.async_unload(old_id):
            raise ConfigEntryNotReady(f"The old FMI entry {old.title} could not be unloaded to move its sensors")

        for registered in er.async_entries_for_config_entry(registry, old_id):
            old_subentry = old.subentries.get(registered.config_subentry_id or "")
            if old_subentry is not None:
                subentry = subentries.get(old_subentry.unique_id)
            else:
                # Before 3.0 an entity belonged to its entry, which was one sensor.
                subentry = subentries.get(_unique_id_of(old)) if old.version < VERSION else None
            if subentry is None:
                _LOGGER.warning(f"{registered.entity_id} belongs to no FMI sensor and is removed with the old entry")
                continue
            if registry.async_get_entity_id(registered.domain, DOMAIN, subentry.subentry_id) is not None:
                # Two old entries measured the same thing, and the subentry already has
                # this entity from the first. The second copy has nothing to add.
                registry.async_remove(registered.entity_id)
                continue
            registry.async_update_entity_platform(
                registered.entity_id,
                DOMAIN,
                new_config_entry_id=entry.entry_id,
                new_config_subentry_id=subentry.subentry_id,
                new_unique_id=subentry.subentry_id,
            )
            if registered.disabled_by is er.RegistryEntryDisabler.CONFIG_ENTRY:
                # The user had the old entry disabled. Moving to an enabled entry
                # would clear this flag, so keep the entity disabled.
                registry.async_update_entity(registered.entity_id, disabled_by=er.RegistryEntryDisabler.USER)

        for issue_owner in [old_id, *old.subentries]:
            ir.async_delete_issue(hass, OLD_DOMAIN, f"no_data_{issue_owner}")
        await hass.config_entries.async_remove(old_id)

    hass.config_entries.async_update_entry(entry, data={key: value for key, value in entry.data.items() if key != CONF_MOVE_FROM})


async def async_check_old_folder(hass: HomeAssistant) -> None:
    """Ask the user to delete this integration's old folder once nothing uses it.

    HACS installs to the new domain's folder and leaves the old one behind. A
    folder named `fmi` may be anand-p-r's, so it is never deleted here.
    """
    path = Path(hass.config.path("custom_components", OLD_DOMAIN))
    ours = await hass.async_add_executor_job(_is_our_folder, path)

    if ours and not old_entries(hass):
        ir.async_create_issue(
            hass,
            DOMAIN,
            OLD_FOLDER_ISSUE,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=OLD_FOLDER_ISSUE,
            translation_placeholders={"path": str(path)},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, OLD_FOLDER_ISSUE)


def _is_our_folder(path: Path) -> bool:
    try:
        manifest = json.loads((path / "manifest.json").read_text())
    except (OSError, ValueError):
        return False
    return "jesmak/fmi" in manifest.get("documentation", "")


def _unique_id_of(entry: ConfigEntry) -> str:
    return build_unique_id(dict(entry.data))


def _subentry_for(entry: ConfigEntry) -> ConfigSubentryData:
    data = dict(entry.data)
    # Stale data settings are shared by every sensor from 3.0 on.
    data.pop(CONF_NO_DATA_ISSUE, None)
    data.pop(CONF_NO_DATA_ISSUE_HOURS, None)
    return ConfigSubentryData(data=data, subentry_type=SUBENTRY_SENSOR, title=entry.title, unique_id=build_unique_id(data))


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
