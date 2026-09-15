"""The diagnostic "stale data" binary sensor of observation and forecast sensors."""
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import (ATTRIBUTION, CONF_LABEL, CONF_LANG, CONF_NO_DATA_ISSUE_HOURS, DEFAULT_NO_DATA_ISSUE_HOURS, DOMAIN,
                    STALE_DATA_SUFFIX)

ATTR_NO_DATA_ISSUE_HOURS = "no_data_issue_hours"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([FMIStaleDataBinarySensor(hass.data[DOMAIN][entry.entry_id], entry)])


class FMIStaleDataBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """On while the newest value FMI holds for the sensor is older than no_data_issue_hours.

    The repair issue tells a person that something is wrong; this tells
    automations, and it turns off by itself when data comes back. It works
    whether or not the repair issue is enabled.
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DataUpdateCoordinator, entry: ConfigEntry):
        super().__init__(coordinator)
        suffix = STALE_DATA_SUFFIX.get(entry.data.get(CONF_LANG), STALE_DATA_SUFFIX["eng"])
        self._attr_attribution = ATTRIBUTION
        self._attr_unique_id = entry.entry_id
        self._attr_name = f"FMI {entry.data[CONF_LABEL]} {suffix}"
        self._attr_extra_state_attributes = {
            ATTR_NO_DATA_ISSUE_HOURS: entry.data.get(CONF_NO_DATA_ISSUE_HOURS, DEFAULT_NO_DATA_ISSUE_HOURS),
        }

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.get("stale")
