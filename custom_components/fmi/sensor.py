import logging

from homeassistant.components.sensor import SensorStateClass, SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, CONF_LABEL, CONF_QUERY_ID, CONF_LANG, CONF_QUERY_LABEL, CONF_PARAMETER, \
    CONF_TARGET_TYPE, CONF_TARGET, CONF_FORECAST_HOURS, CONF_FORECAST_PAST_HOURS, CONF_FORECAST_STEP

_LOGGER = logging.getLogger(__name__)
ATTRIBUTION = "Data provided by Finnish Meteorological Institute (FMI)"

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
    }

    if "::forecast" in str(entry.data.get(CONF_QUERY_ID)):
        attributes[ATTR_FORECAST_HOURS] = entry.data.get(CONF_FORECAST_HOURS)
        attributes[ATTR_FORECAST_PAST_HOURS] = entry.data.get(CONF_FORECAST_PAST_HOURS)
        attributes[ATTR_FORECAST_STEP] = entry.data.get(CONF_FORECAST_STEP)

    return attributes


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]
    query_id = entry.data.get(CONF_QUERY_ID)
    label = entry.data.get(CONF_LABEL)

    sensor = FMIForecastSensor(coord, entry, label) if "::forecast" in query_id else FMISensor(coord, entry, label)
    async_add_entities([sensor], update_before_add=True)


class FMISensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator: DataUpdateCoordinator, entry: ConfigEntry, label: str):
        super().__init__(coordinator)
        self._attr_attribution = ATTRIBUTION
        self._attr_icon = "mdi:weather-cloudy"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_unique_id = f"fmi_{label}"
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
        self._attr_unique_id = f"fmi_{label}"
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
