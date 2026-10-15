"""Diagnostics for bug reports: the settings, every station and place, and how each refresh went.

Places are where the user lives, so their coordinates, names and unique ids are redacted, and so is a station that
is a place name or a point instead of a station. Station and query ids stay. They are public, and they are what a
bug report needs.
"""

from typing import Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant

from . import FMIConfigEntry
from .const import CONF_TARGET, CONF_TARGET_TYPE
from .query_coordinator import FMIQueryCoordinator, measurement_key
from .warning_coordinator import FMIWarningsCoordinator
from .weather_coordinator import FMIWeatherCoordinator

TO_REDACT = {"latitude", "longitude", "label"}


def _public(subentry: ConfigSubentry) -> bool:
    # A station by fmisid, or a forecast point by geoid, is one of FMI's own. A place name, a point or a place of the
    # user's own is where the user is.
    return subentry.data.get(CONF_TARGET_TYPE) in ("fmisid", "geoid")


def _subentry(subentry: ConfigSubentry) -> dict[str, Any]:
    # A station's title and unique id say which station it is. A place has its coordinates in its unique id.
    public = _public(subentry)
    data = async_redact_data(dict(subentry.data), TO_REDACT if public else TO_REDACT | {CONF_TARGET})
    return {
        "type": subentry.subentry_type,
        "title": subentry.title if public else REDACTED,
        "unique_id": subentry.unique_id if public else REDACTED,
        "data": data,
    }


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
        "kind": {FMIQueryCoordinator: "measurement", FMIWarningsCoordinator: "warnings", FMIWeatherCoordinator: "weather"}[
            type(coordinator)
        ],
        "measurement": measurement_key(coordinator.measurement) if isinstance(coordinator, FMIQueryCoordinator) else None,
        "last_update_success": coordinator.last_update_success,
        # FMI's message can repeat the place it was asked about.
        "last_exception": (repr(exception) if _public(coordinator.subentry) else type(exception).__name__)
        if (exception := coordinator.last_exception)
        else None,
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
            {
                **_subentry(subentry),
                "coordinators": [_coordinator(coordinator) for coordinator in coordinators if coordinator.subentry is subentry],
            }
            for subentry in entry.subentries.values()
        ],
    }
