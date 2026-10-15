import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .cap import highest_level
from .const import (
    ATTRIBUTION,
    CONF_FORECAST_HOURS,
    CONF_FORECAST_PAST_HOURS,
    CONF_FORECAST_STEP,
    CONF_LABEL,
    CONF_LANG,
    CONF_LOCATION,
    CONF_NO_DATA_ISSUE,
    CONF_PARAMETER,
    CONF_QUERY_ID,
    CONF_QUERY_LABEL,
    CONF_TARGET,
    CONF_TARGET_TYPE,
    CONF_WARNING_TYPES,
    DEFAULT_NO_DATA_ISSUE,
    WARNING_LEVELS,
)
from .query_coordinator import FMIQueryCoordinator
from .session import WATER_LEVEL_UNITS
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


def get_query_name(data) -> str | None:
    # The config flow stores the label as "<title> (<query id>)"; the id is
    # already exposed separately, so keep only the title here.
    label = data.get(CONF_QUERY_LABEL)
    return label.removesuffix(f" ({data.get(CONF_QUERY_ID)})") if label is not None else None


def get_config_attributes(coordinator: FMIQueryCoordinator) -> dict:
    data = coordinator.subentry.data
    attributes = {
        ATTR_LABEL: data.get(CONF_LABEL),
        ATTR_LANGUAGE: data.get(CONF_LANG),
        ATTR_QUERY_ID: data.get(CONF_QUERY_ID),
        ATTR_QUERY_NAME: get_query_name(data),
        ATTR_PARAMETER: data.get(CONF_PARAMETER),
        ATTR_LOCATION_TYPE: data.get(CONF_TARGET_TYPE),
        ATTR_LOCATION_ID: data.get(CONF_TARGET),
        ATTR_NO_DATA_ISSUE: coordinator.config_entry.options.get(CONF_NO_DATA_ISSUE, DEFAULT_NO_DATA_ISSUE),
        ATTR_NO_DATA_ISSUE_HOURS: coordinator.stale_after_hours,
    }

    if "::forecast" in str(data.get(CONF_QUERY_ID)):
        attributes[ATTR_FORECAST_HOURS] = data.get(CONF_FORECAST_HOURS)
        attributes[ATTR_FORECAST_PAST_HOURS] = data.get(CONF_FORECAST_PAST_HOURS)
        attributes[ATTR_FORECAST_STEP] = data.get(CONF_FORECAST_STEP)

    return attributes


def get_warnings_config_attributes(coordinator: FMIWarningsCoordinator) -> dict:
    data = coordinator.subentry.data
    location = data[CONF_LOCATION]
    return {
        ATTR_LABEL: data.get(CONF_LABEL),
        ATTR_LANGUAGE: data.get(CONF_LANG),
        ATTR_LATITUDE: location.get("latitude"),
        ATTR_LONGITUDE: location.get("longitude"),
        ATTR_RADIUS: location.get("radius") or 0,
        ATTR_WARNING_TYPES: data.get(CONF_WARNING_TYPES),
    }


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    for subentry_id, coordinator in entry.runtime_data.coordinators.items():
        if isinstance(coordinator, FMIWarningsCoordinator):
            sensor = FMIWarningLevelSensor(coordinator)
        elif not isinstance(coordinator, FMIQueryCoordinator):
            continue
        elif "::forecast" in str(coordinator.subentry.data[CONF_QUERY_ID]):
            sensor = FMIForecastSensor(coordinator)
        else:
            sensor = FMISensor(coordinator)
        async_add_entities([sensor], config_subentry_id=subentry_id)


class FMIQuerySensor(CoordinatorEntity[FMIQueryCoordinator], SensorEntity):
    """What observation and forecast sensors have in common."""

    _attr_attribution = ATTRIBUTION
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: FMIQueryCoordinator):
        super().__init__(coordinator)
        data = coordinator.subentry.data
        self._attr_unique_id = coordinator.subentry.subentry_id
        self._attr_name = f"FMI {data.get(CONF_LABEL, coordinator.subentry.title)}"
        self._config_attributes = get_config_attributes(coordinator)

    @property
    def _values(self) -> list[dict]:
        return self.coordinator.data["data"] if self.coordinator.data else []

    @property
    def native_unit_of_measurement(self) -> str | None:
        return self.coordinator.data.get("unit") if self.coordinator.data else None

    @property
    def device_class(self) -> SensorDeviceClass | None:
        # A water level is a distance, so the user can pick the unit it is shown in.
        return SensorDeviceClass.DISTANCE if str(self.coordinator.subentry.data[CONF_PARAMETER]).lower() in WATER_LEVEL_UNITS else None

    def _location_attributes(self) -> dict:
        data = self.coordinator.data or {}
        return {ATTR_LATITUDE: data.get("latitude"), ATTR_LONGITUDE: data.get("longitude")}


class FMISensor(FMIQuerySensor):
    """The latest observed value."""

    _attr_icon = "mdi:weather-cloudy"

    @property
    def native_value(self):
        return self._values[0]["value"] if self._values else None

    @property
    def extra_state_attributes(self) -> dict:
        return {
            **self._location_attributes(),
            **self._config_attributes,
            ATTR_TIME: self._values[0]["time"] if self._values else None,
            ATTR_VALUE: self._values[0]["value"] if self._values else None,
        }


class FMIForecastSensor(FMIQuerySensor):
    """The next forecast value, with the whole forecast in the attributes."""

    _attr_icon = "mdi:weather-cloudy-clock"

    @property
    def native_value(self):
        now = dt_util.utcnow()
        return next((item["value"] for item in self._values if item["time"] > now), None)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            **self._location_attributes(),
            **self._config_attributes,
            ATTR_FORECAST: [{ATTR_TIME: item["time"], ATTR_VALUE: item["value"]} for item in self._values],
        }


class FMIWarningLevelSensor(CoordinatorEntity[FMIWarningsCoordinator], SensorEntity):
    """The highest warning level in force now for the place: none, yellow, orange or red.

    Every warning that concerns the place, in force or coming up in the next
    few days, is listed in the attributes.
    """

    # The warning texts are long and repeat on every refresh; history only needs the level.
    _unrecorded_attributes = frozenset({ATTR_WARNINGS})
    _attr_attribution = ATTRIBUTION
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_icon = "mdi:alert"
    _attr_options = WARNING_LEVELS
    _attr_translation_key = "warning_level"

    def __init__(self, coordinator: FMIWarningsCoordinator):
        super().__init__(coordinator)
        self._attr_unique_id = coordinator.subentry.subentry_id
        self._attr_name = f"FMI {coordinator.subentry.data.get(CONF_LABEL, coordinator.subentry.title)}"
        self._config_attributes = get_warnings_config_attributes(coordinator)

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data is None:
            return None
        return highest_level(self.coordinator.data.warnings, dt_util.utcnow())

    @property
    def extra_state_attributes(self) -> dict:
        now = dt_util.utcnow()
        warnings = (
            sorted(self.coordinator.data.warnings.values(), key=lambda warning: warning.onset or now) if self.coordinator.data else []
        )
        return {
            **self._config_attributes,
            ATTR_ACTIVE_WARNINGS: sum(1 for warning in warnings if warning.is_active(now)),
            ATTR_WARNINGS: [warning.as_dict() for warning in warnings],
        }
