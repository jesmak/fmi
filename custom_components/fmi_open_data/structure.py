"""Stations and places: the subentries of 4.0.0, their devices, and the move from the subentries before it.

A station subentry is one station, place name or forecast point with the measurements read there. A place subentry is
a place on a map with its weather forecast and the warnings followed there. Each is a device. Home Assistant gives a
device to one subentry only and puts its name in front of the names of the entities on it, so the device says where
and each entity what.

Before 4.0.0 a subentry was one sensor, one warnings place or one weather place. At the first setup of 4.0.0 they are
merged, sensors by their station and warnings and weather by their coordinates, and every measurement is named by the
rules. The entities move to their new subentry with new unique ids, so their entity ids, history and statistics stay.
"""

import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import (
    CONF_FORECAST_HOURS,
    CONF_FORECAST_PAST_HOURS,
    CONF_FORECAST_STEP,
    CONF_LABEL,
    CONF_LANG,
    CONF_LOCATION,
    CONF_MEASUREMENTS,
    CONF_NEGATIVE_AS_ZERO,
    CONF_PARAMETER,
    CONF_QUERY_ID,
    CONF_STRUCTURE,
    CONF_TARGET,
    CONF_TARGET_TYPE,
    CONF_UNIT,
    CONF_WARNING_TYPES,
    CONF_WEATHER,
    DOMAIN,
    STRUCTURE_VERSION,
    SUBENTRY_PLACE,
    SUBENTRY_SENSOR,
    SUBENTRY_STATION,
    SUBENTRY_WARNINGS,
    SUBENTRY_WEATHER,
    WARNING_TYPES,
)
from .query_coordinator import measurement_key, measurement_name, station_unique_id
from .session import FMIException, FMISession

_LOGGER = logging.getLogger(__name__)

MANUFACTURER = "Finnish Meteorological Institute"

# What a measurement keeps of a 3.x sensor subentry. The station goes to the station subentry, the language is the
# entry's, and the name is made again by the rules.
MEASUREMENT_FIELDS = (
    CONF_QUERY_ID,
    CONF_PARAMETER,
    CONF_NEGATIVE_AS_ZERO,
    CONF_UNIT,
    CONF_FORECAST_HOURS,
    CONF_FORECAST_PAST_HOURS,
    CONF_FORECAST_STEP,
)


def place_unique_id(location: Mapping[str, Any]) -> str:
    """A place subentry's unique id: the same place is the same subentry, whatever it follows."""
    return f"place_{float(location['latitude']):.4f}_{float(location['longitude']):.4f}"


def station_title(target_type: str, target: str, station_names: Mapping[str, str]) -> str:
    """A station's name, from FMI's station list. A place name or a point is its own name."""
    if target_type == "fmisid":
        return station_names.get(target) or f"FMI {target}"
    return target


def _merged(have: Mapping[str, Any], new: Mapping[str, Any]) -> dict[str, Any]:
    """A station or place that is there already, with what the old subentries add to it."""
    if CONF_MEASUREMENTS in have:
        keys = {measurement_key(measurement) for measurement in have[CONF_MEASUREMENTS]}
        added = [measurement for measurement in new[CONF_MEASUREMENTS] if measurement_key(measurement) not in keys]
        return {**have, CONF_MEASUREMENTS: [*have[CONF_MEASUREMENTS], *added]}
    followed = set(have[CONF_WARNING_TYPES]) | set(new[CONF_WARNING_TYPES])
    radius = max(have[CONF_LOCATION].get("radius") or 0, new[CONF_LOCATION]["radius"])
    return {
        **have,
        CONF_LOCATION: {**have[CONF_LOCATION], "radius": radius},
        CONF_WEATHER: have[CONF_WEATHER] or new[CONF_WEATHER],
        CONF_WARNING_TYPES: [warning_type for warning_type in WARNING_TYPES if warning_type in followed],
    }


def device_info(subentry: ConfigSubentry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, subentry.subentry_id)}, name=subentry.title, manufacturer=MANUFACTURER, entry_type=DeviceEntryType.SERVICE
    )


async def async_station_names(hass: HomeAssistant, lang: str) -> dict[str, str]:
    """FMI's station names by fmisid. Raises FMIException."""
    stations = await hass.async_add_executor_job(FMISession().list_stations, lang)
    return {station["id"]: station["name"] for station in stations}


async def async_restructure(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Merge the subentries from before 4.0.0 into stations and places, once.

    Until FMI's stations and parameters can be read, setup is retried rather than settling for names that would stay.
    """
    before = (SUBENTRY_SENSOR, SUBENTRY_WARNINGS, SUBENTRY_WEATHER)
    old = [subentry for subentry in entry.subentries.values() if subentry.subentry_type in before]
    sensors = [subentry for subentry in old if subentry.subentry_type == SUBENTRY_SENSOR]
    lang = entry.data[CONF_LANG]

    station_names: dict[str, str] = {}
    descriptions: dict[str, Mapping[str, tuple[str | None, str | None]]] = {}
    try:
        if any(sensor.data[CONF_TARGET_TYPE] == "fmisid" for sensor in sensors):
            station_names = await async_station_names(hass, lang)
        for sensor in sensors:
            query_id = str(sensor.data[CONF_QUERY_ID])
            if query_id not in descriptions:
                descriptions[query_id] = await hass.async_add_executor_job(FMISession().get_parameter_descriptions, lang, query_id)
    except FMIException as exception:
        raise ConfigEntryNotReady(f"Could not read FMI's stations and parameters to name the sensors: {exception}") from exception

    # By the new subentry's unique id: its data, its title, and the old subentries whose entities move to it, each with
    # the measurement the entity becomes, or None for a place.
    merged: dict[str, dict[str, Any]] = {}

    for sensor in sensors:
        target_type, target = sensor.data[CONF_TARGET_TYPE], str(sensor.data[CONF_TARGET]).strip()
        if target_type == "latlon":
            # As the flow writes a point, so that the same point is the same station.
            latitude, longitude = (float(part) for part in target.split(","))
            target = f"{latitude:.4f},{longitude:.4f}"
        station = merged.setdefault(
            station_unique_id(target_type, target),
            {
                "type": SUBENTRY_STATION,
                "data": {CONF_TARGET_TYPE: target_type, CONF_TARGET: target, CONF_MEASUREMENTS: []},
                "title": station_title(target_type, target, station_names),
                "moves": [],
            },
        )
        measurement = {field: sensor.data[field] for field in MEASUREMENT_FIELDS if field in sensor.data}
        query_id, parameter = str(measurement[CONF_QUERY_ID]), str(measurement[CONF_PARAMETER])
        measurement[CONF_LABEL] = measurement_name(descriptions[query_id], lang, query_id, parameter)
        key = measurement_key(measurement)
        if all(measurement_key(existing) != key for existing in station["data"][CONF_MEASUREMENTS]):
            station["data"][CONF_MEASUREMENTS].append(measurement)
        station["moves"].append((sensor.subentry_id, key))

    for subentry in old:
        if subentry.subentry_type == SUBENTRY_SENSOR:
            continue
        location = subentry.data[CONF_LOCATION]
        place = merged.setdefault(
            place_unique_id(location),
            {
                "type": SUBENTRY_PLACE,
                "data": {
                    CONF_LOCATION: {"latitude": location["latitude"], "longitude": location["longitude"], "radius": 0},
                    CONF_LABEL: subentry.data.get(CONF_LABEL, subentry.title),
                    CONF_WEATHER: False,
                    CONF_WARNING_TYPES: [],
                },
                "title": subentry.data.get(CONF_LABEL, subentry.title),
                "moves": [],
            },
        )
        data = place["data"]
        if subentry.subentry_type == SUBENTRY_WEATHER:
            data[CONF_WEATHER] = True
        else:
            # Two warnings places at the same point: the union of what they followed, as far out as either reached.
            followed = set(data[CONF_WARNING_TYPES]) | set(subentry.data[CONF_WARNING_TYPES])
            data[CONF_WARNING_TYPES] = [warning_type for warning_type in WARNING_TYPES if warning_type in followed]
            data[CONF_LOCATION]["radius"] = max(data[CONF_LOCATION]["radius"], location.get("radius") or 0)
        place["moves"].append((subentry.subentry_id, None))

    registry = er.async_get(hass)
    for unique_id, new in merged.items():
        # The station or place may be there already: added while setup waited for FMI.
        subentry = next((item for item in entry.subentries.values() if item.unique_id == unique_id), None)
        if subentry is None:
            subentry = ConfigSubentry(data=new["data"], subentry_type=new["type"], title=new["title"], unique_id=unique_id)
            hass.config_entries.async_add_subentry(entry, subentry)
        else:
            hass.config_entries.async_update_subentry(entry, subentry, data=_merged(subentry.data, new["data"]))
        taken = {
            (registered.domain, registered.unique_id)
            for registered in er.async_entries_for_config_entry(registry, entry.entry_id)
            if registered.config_subentry_id == subentry.subentry_id
        }
        for old_id, key in new["moves"]:
            new_unique_id = subentry.subentry_id if key is None else f"{subentry.subentry_id}_{key}"
            for registered in er.async_entries_for_config_entry(registry, entry.entry_id):
                if registered.config_subentry_id != old_id:
                    continue
                if (registered.domain, new_unique_id) in taken:
                    # Two old subentries made the same entity; the first one's stays.
                    _LOGGER.info(f"{registered.entity_id} repeats an entity of the same station or place and is removed")
                    registry.async_remove(registered.entity_id)
                    continue
                taken.add((registered.domain, new_unique_id))
                registry.async_update_entity(registered.entity_id, config_subentry_id=subentry.subentry_id, new_unique_id=new_unique_id)

    for subentry in old:
        ir.async_delete_issue(hass, DOMAIN, f"no_data_{subentry.subentry_id}")
        hass.config_entries.async_remove_subentry(entry, subentry.subentry_id)

    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_STRUCTURE: STRUCTURE_VERSION})
