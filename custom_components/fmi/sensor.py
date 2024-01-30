import logging
from datetime import datetime

from homeassistant.components.sensor import SensorStateClass, SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity

from .const import DOMAIN, CONF_LABEL, CONF_QUERY_ID

_LOGGER = logging.getLogger(__name__)
ATTRIBUTION = "Data provided by Finnish Meteorological Institute (FMI)"

ATTR_LATITUDE = "latitude"
ATTR_LONGITUDE = "longitude"
ATTR_QUERY_ID = "query_id"
ATTR_PARAMETER = "parameter"
ATTR_FORECAST = "forecast"
ATTR_TIME = "time"
ATTR_VALUE = "value"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]
    query_id = entry.data.get(CONF_QUERY_ID)
    label = entry.data.get(CONF_LABEL)

    sensor = FMIForecastSensor(coord, label) if "::forecast" in query_id else FMISensor(coord, label)
    async_add_entities([sensor], update_before_add=True)


class FMISensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator: DataUpdateCoordinator, label: str):
        super().__init__(coordinator)
        _attr_attribution = ATTRIBUTION
        self._attr_icon = "mdi:weather-cloudy"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_unique_id = f"fmi_{label}"
        self._attr_name = f"FMI {label}"

        if coordinator.data["unit"] is not None:
            self._attr_native_unit_of_measurement = coordinator.data["unit"]

        self._attr_extra_state_attributes = {
            ATTR_LATITUDE: coordinator.data.get("latitude"),
            ATTR_LONGITUDE: coordinator.data.get("longitude"),
            ATTR_QUERY_ID: coordinator.data.get("query_id"),
            ATTR_PARAMETER: coordinator.data.get("parameter"),
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
    def __init__(self, coordinator: DataUpdateCoordinator, label: str):
        super().__init__(coordinator)
        _attr_attribution = ATTRIBUTION
        self._attr_icon = "mdi:weather-cloudy-clock"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_unique_id = f"fmi_{label}"
        self._attr_name = f"FMI {label}"

        if coordinator.data["unit"] is not None:
            self._attr_native_unit_of_measurement = coordinator.data["unit"]

        self._attr_extra_state_attributes = {
            ATTR_LATITUDE: coordinator.data.get("latitude"),
            ATTR_LONGITUDE: coordinator.data.get("longitude"),
            ATTR_QUERY_ID: coordinator.data.get("query_id"),
            ATTR_PARAMETER: coordinator.data.get("parameter"),
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
        now = datetime.utcnow()
        return next(
            (entry["value"] for entry in self.coordinator.data["data"] if entry["time"].replace(tzinfo=None) > now),
            None) if len(self.coordinator.data["data"]) > 0 else None
