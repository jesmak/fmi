"""Diagnostics for bug reports: the settings, every subentry and how its last refresh went.

Places are where the user lives, so their coordinates are redacted, and so are the names, which are often a
place's name, and a sensor's target unless it is a station. Station and query ids stay. They are public, and they
are what a bug report needs.
"""

from typing import Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant

from . import FMIConfigEntry
from .const import CONF_TARGET, CONF_TARGET_TYPE
from .query_coordinator import FMIQueryCoordinator
from .warning_coordinator import FMIWarningsCoordinator
from .weather_coordinator import FMIWeatherCoordinator

TO_REDACT = {"latitude", "longitude", "label"}


def _subentry(subentry: ConfigSubentry) -> dict[str, Any]:
    # A sensor's target is a station, a place name or coordinates, and its unique id contains the target.
    # Warnings and weather places have the place in their unique id.
    public = subentry.data.get(CONF_TARGET_TYPE) == "fmisid"
    data = async_redact_data(dict(subentry.data), TO_REDACT if public else TO_REDACT | {CONF_TARGET})
    return {"type": subentry.subentry_type, "title": REDACTED, "unique_id": subentry.unique_id if public else REDACTED, "data": data}


def _query_data(data: dict[str, Any]) -> dict[str, Any]:
    values = data.get("data") or []
    return {
        "unit": data.get("unit"),
        "stale": data.get("stale"),
        "values": len(values),
        "first": values[0]["time"].isoformat() if values else None,
        "last": values[-1]["time"].isoformat() if values else None,
        "last_value": values[-1]["value"] if values else None,
    }


def _coordinator(coordinator: FMIQueryCoordinator | FMIWarningsCoordinator | FMIWeatherCoordinator) -> dict[str, Any]:
    result: dict[str, Any] = {
        "last_update_success": coordinator.last_update_success,
        "last_exception": repr(coordinator.last_exception) if coordinator.last_exception else None,
        "update_interval": str(coordinator.update_interval),
    }
    data = coordinator.data
    if data is None:
        return result
    if isinstance(coordinator, FMIQueryCoordinator):
        result["data"] = _query_data(data)
    elif isinstance(coordinator, FMIWarningsCoordinator):
        # The warnings' areas would tell where the place is.
        result["data"] = {
            "updated": data.updated.isoformat(),
            "warnings": [
                {
                    "type": warning.type,
                    "level": warning.level,
                    "onset": warning.onset.isoformat() if warning.onset else None,
                    "expires": warning.expires.isoformat() if warning.expires else None,
                }
                for warning in data.warnings.values()
            ],
        }
    else:
        result["data"] = {
            "hours": len(data),
            "first": data[0]["time"].isoformat(),
            "last": data[-1]["time"].isoformat(),
            "first_hour": {key: value for key, value in data[0].items() if key != "time"},
        }
    return result


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: FMIConfigEntry) -> dict[str, Any]:
    coordinators = entry.runtime_data.coordinators
    return {
        "data": dict(entry.data),
        "options": dict(entry.options),
        "subentries": [
            {**_subentry(subentry), "coordinator": _coordinator(coordinators[subentry_id]) if subentry_id in coordinators else None}
            for subentry_id, subentry in entry.subentries.items()
        ],
    }
