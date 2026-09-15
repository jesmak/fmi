import logging

from homeassistant.components.sensor import SensorStateClass, SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity
from homeassistant.util import dt as dt_util

from .cap import highest_level
from .const import DOMAIN, CONF_LABEL, CONF_QUERY_ID, CONF_LANG, CONF_QUERY_LABEL, CONF_PARAMETER, \
    CONF_TARGET_TYPE, CONF_TARGET, CONF_FORECAST_HOURS, CONF_FORECAST_PAST_HOURS, CONF_FORECAST_STEP, \
    CONF_NO_DATA_ISSUE, CONF_NO_DATA_ISSUE_HOURS, DEFAULT_NO_DATA_ISSUE, DEFAULT_NO_DATA_ISSUE_HOURS, ATTRIBUTION, \
    CONF_ENTRY_TYPE, ENTRY_TYPE_WARNINGS, CONF_LOCATION, CONF_WARNING_TYPES, WARNING_LEVELS
from .warning_coordinator import FMIWarningsCoordinator

_LOGGER = logging.getLogger(__name__)

ATTR_LATITUDE = "latitude"
ATTR_LONGITUDE = "longitude"
ATTR_QUERY_ID = "query_id"
ATTR_PARAMETER = "parameter"
ATTR_FORECAST = "forecast"
ATTR_TIME = "time"
ATTR_VALUE = "value"
ATTR_LABEL = "label"
ATTR_LANGUAGE = "language"
ATTR_QUERY_NAME = "query_name"
ATTR_LOCATION_TYPE = "location_type"
ATTR_LOCATION_ID = "location_id"
ATTR_FORECAST_HOURS = "forecast_hours"
ATTR_FORECAST_PAST_HOURS = "forecast_past_hours"
ATTR_FORECAST_STEP = "forecast_step"
ATTR_NO_DATA_ISSUE = "no_data_issue"
ATTR_NO_DATA_ISSUE_HOURS = "no_data_issue_hours"
ATTR_RADIUS = "radius"
ATTR_WARNING_TYPES = "warning_types"
ATTR_ACTIVE_WARNINGS = "active_warnings"
ATTR_WARNINGS = "warnings"


def get_query_name(entry: ConfigEntry) -> str | None:
    # The config flow stores the label as "<title> (<query id>)"; the id is
    # already exposed separately, so keep only the title here.
    label = entry.data.get(CONF_QUERY_LABEL)
    return label.removesuffix(f" ({entry.data.get(CONF_QUERY_ID)})") if label is not None else None


def get_config_attributes(entry: ConfigEntry) -> dict:
    attributes = {
        ATTR_LABEL: entry.data.get(CONF_LABEL),
        ATTR_LANGUAGE: entry.data.get(CONF_LANG),
        ATTR_QUERY_ID: entry.data.get(CONF_QUERY_ID),
        ATTR_QUERY_NAME: get_query_name(entry),
        ATTR_PARAMETER: entry.data.get(CONF_PARAMETER),
        ATTR_LOCATION_TYPE: entry.data.get(CONF_TARGET_TYPE),
        ATTR_LOCATION_ID: entry.data.get(CONF_TARGET),
        ATTR_NO_DATA_ISSUE: entry.data.get(CONF_NO_DATA_ISSUE, DEFAULT_NO_DATA_ISSUE),
        ATTR_NO_DATA_ISSUE_HOURS: entry.data.get(CONF_NO_DATA_ISSUE_HOURS, DEFAULT_NO_DATA_ISSUE_HOURS),
    }

    if "::forecast" in str(entry.data.get(CONF_QUERY_ID)):
        attributes[ATTR_FORECAST_HOURS] = entry.data.get(CONF_FORECAST_HOURS)
        attributes[ATTR_FORECAST_PAST_HOURS] = entry.data.get(CONF_FORECAST_PAST_HOURS)
        attributes[ATTR_FORECAST_STEP] = entry.data.get(CONF_FORECAST_STEP)

    return attributes


def get_warnings_config_attributes(entry: ConfigEntry) -> dict:
    location = entry.data[CONF_LOCATION]
    return {
        ATTR_LABEL: entry.data.get(CONF_LABEL),
        ATTR_LANGUAGE: entry.data.get(CONF_LANG),
        ATTR_LATITUDE: location.get("latitude"),
        ATTR_LONGITUDE: location.get("longitude"),
        ATTR_RADIUS: location.get("radius") or 0,
        ATTR_WARNING_TYPES: entry.data.get(CONF_WARNING_TYPES),
    }


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]
    label = entry.data.get(CONF_LABEL)

    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_WARNINGS:
        async_add_entities([FMIWarningLevelSensor(coord, entry, label)])
        return

    query_id = entry.data.get(CONF_QUERY_ID)
    sensor = FMIForecastSensor(coord, entry, label) if "::forecast" in query_id else FMISensor(coord, entry, label)
    async_add_entities([sensor], update_before_add=True)


class FMISensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator: DataUpdateCoordinator, entry: ConfigEntry, label: str):
        super().__init__(coordinator)
        self._attr_attribution = ATTRIBUTION
        self._attr_icon = "mdi:weather-cloudy"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_unique_id = entry.entry_id
        self._attr_name = f"FMI {label}"

        if coordinator.data["unit"] is not None:
            self._attr_native_unit_of_measurement = coordinator.data["unit"]

        self._attr_extra_state_attributes = {
            ATTR_LATITUDE: coordinator.data.get("latitude"),
            ATTR_LONGITUDE: coordinator.data.get("longitude"),
            **get_config_attributes(entry),
            ATTR_TIME: coordinator.data["data"][0]["time"] if len(coordinator.data["data"]) > 0 else None,
            ATTR_VALUE: coordinator.data["data"][0]["value"] if len(coordinator.data["data"]) > 0 else None,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_extra_state_attributes[ATTR_TIME] = self.coordinator.data["data"][0]["time"] if len(
            self.coordinator.data["data"]) > 0 else None
        self._attr_extra_state_attributes[ATTR_VALUE] = self.coordinator.data["data"][0]["value"] if len(
            self.coordinator.data["data"]) > 0 else None
        self.async_write_ha_state()

    @property
    def native_value(self):
        return self.coordinator.data["data"][0]["value"] if len(self.coordinator.data["data"]) > 0 else None


class FMIForecastSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator: DataUpdateCoordinator, entry: ConfigEntry, label: str):
        super().__init__(coordinator)
        self._attr_attribution = ATTRIBUTION
        self._attr_icon = "mdi:weather-cloudy-clock"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_unique_id = entry.entry_id
        self._attr_name = f"FMI {label}"

        if coordinator.data["unit"] is not None:
            self._attr_native_unit_of_measurement = coordinator.data["unit"]

        self._attr_extra_state_attributes = {
            ATTR_LATITUDE: coordinator.data.get("latitude"),
            ATTR_LONGITUDE: coordinator.data.get("longitude"),
            **get_config_attributes(entry),
            ATTR_FORECAST: []
        }

        if len(coordinator.data["data"]) > 0:
            for entry in coordinator.data["data"]:
                self._attr_extra_state_attributes[ATTR_FORECAST].append(
                    {ATTR_TIME: entry["time"], ATTR_VALUE: entry["value"]})

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_extra_state_attributes[ATTR_FORECAST] = []

        if len(self.coordinator.data["data"]) > 0:
            for entry in self.coordinator.data["data"]:
                self._attr_extra_state_attributes[ATTR_FORECAST].append(
                    {ATTR_TIME: entry["time"], ATTR_VALUE: entry["value"]})

        self.async_write_ha_state()

    @property
    def native_value(self):
        now = dt_util.utcnow()
        return next(
            (entry["value"] for entry in self.coordinator.data["data"] if entry["time"] > now),
            None) if len(self.coordinator.data["data"]) > 0 else None


class FMIWarningLevelSensor(CoordinatorEntity[FMIWarningsCoordinator], SensorEntity):
    """The highest warning level in force now for the place: none, yellow, orange or red.

    Every warning that concerns the place, in force or coming up in the next
    few days, is listed in the attributes.
    """

    # The warning texts are long and repeat on every refresh; history only needs the level.
    _unrecorded_attributes = frozenset({ATTR_WARNINGS})
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = WARNING_LEVELS
    _attr_translation_key = "warning_level"

    def __init__(self, coordinator: FMIWarningsCoordinator, entry: ConfigEntry, label: str):
        super().__init__(coordinator)
        self._attr_attribution = ATTRIBUTION
        self._attr_icon = "mdi:alert"
        self._attr_unique_id = entry.entry_id
        self._attr_name = f"FMI {label}"
        self._config_attributes = get_warnings_config_attributes(entry)

    @property
    def native_value(self) -> str:
        return highest_level(self.coordinator.data.warnings, dt_util.utcnow())

    @property
    def extra_state_attributes(self) -> dict:
        now = dt_util.utcnow()
        warnings = sorted(self.coordinator.data.warnings.values(), key=lambda warning: warning.onset or now)
        return {
            **self._config_attributes,
            ATTR_ACTIVE_WARNINGS: sum(1 for warning in warnings if warning.is_active(now)),
            ATTR_WARNINGS: [warning.as_dict() for warning in warnings],
        }
