import logging
from datetime import datetime

from homeassistant.components.sensor import SensorStateClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity

from .const import CONF_FMISID, CONF_SENSOR_TYPE, DOMAIN, SENSOR_CONFIGS, CONF_LABEL

_LOGGER = logging.getLogger(__name__)
ATTRIBUTION = "Data provided by Finnish Meteorological Institute (FMI)"

ATTR_LATEST_UPDATE = "latest_update"
ATTR_FMISID = "fmisid"
ATTR_SENSOR_TYPE = "sensor_type"
ATTR_FORECAST = "forecast"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]
    fmisid = entry.data.get(CONF_FMISID)
    label = entry.data.get(CONF_LABEL)
    conf = next((conf for conf in SENSOR_CONFIGS if conf["id"] == entry.data.get(CONF_SENSOR_TYPE)), None)
    sensor = FMIForecastSensor(coord, conf, fmisid, label) if conf["is_forecast"] else FMISensor(coord, conf, fmisid,
                                                                                                 label)
    async_add_entities([sensor], update_before_add=True)


class FMISensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator: DataUpdateCoordinator, conf: dict[str, str], fmisid: int, label: str):
        super().__init__(coordinator)
        _attr_attribution = ATTRIBUTION
        self._attr_icon = conf["icon"]
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_unique_id = f"fmi_{conf['id']}_{fmisid}"
        self._attr_name = f"FMI {label}"
        self._attr_translation_key = conf["id"]
        self._attr_native_unit_of_measurement = conf["unit"]
        self._fmisid = fmisid
        self._conf = conf

        self._attr_extra_state_attributes = {
            ATTR_SENSOR_TYPE: conf["id"],
            ATTR_LATEST_UPDATE: datetime.fromisoformat(coordinator.data[0][0].removesuffix('Z')) if len(
                coordinator.data) > 0 else None,
            ATTR_FMISID: fmisid
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_extra_state_attributes[ATTR_LATEST_UPDATE] = datetime.fromisoformat(
            self.coordinator.data[0][0].removesuffix('Z')) if len(self.coordinator.data) > 0 else None
        self.async_write_ha_state()

    @property
    def native_value(self):
        return self.coordinator.data[0][1] if len(self.coordinator.data) > 0 else None


class FMIForecastSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator: DataUpdateCoordinator, conf: dict[str, str], fmisid: int, label: str):
        super().__init__(coordinator)
        _attr_attribution = ATTRIBUTION
        self._attr_icon = conf["icon"]
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_unique_id = f"fmi_{conf['id']}_{fmisid}"
        self._attr_name = f"FMI {label}"
        self._attr_native_unit_of_measurement = conf["unit"]
        self._fmisid = fmisid
        self._conf = conf

        now = datetime.utcnow()
        time = next(
            (value[0] for value in self.coordinator.data if datetime.fromisoformat(value[0].removesuffix('Z')) > now),
            None) if len(self.coordinator.data) > 0 else None

        self._attr_extra_state_attributes = {
            ATTR_SENSOR_TYPE: conf["id"],
            ATTR_LATEST_UPDATE: time,
            ATTR_FMISID: fmisid,
            ATTR_FORECAST: self.coordinator.data
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        now = datetime.utcnow()
        time = next(
            (value[0] for value in self.coordinator.data if datetime.fromisoformat(value[0].removesuffix('Z')) > now),
            None) if len(self.coordinator.data) > 0 else None

        self._attr_extra_state_attributes[ATTR_LATEST_UPDATE] = time
        self._attr_extra_state_attributes[ATTR_FORECAST] = self.coordinator.data

        self.async_write_ha_state()

    @property
    def native_value(self):
        now = datetime.utcnow()
        value = next(
            (value[1] for value in self.coordinator.data if datetime.fromisoformat(value[0].removesuffix('Z')) > now),
            None) if len(self.coordinator.data) > 0 else None
        return value
