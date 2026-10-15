"""The diagnostic "stale data" binary sensor of observation and forecast sensors."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, CONF_LABEL
from .query_coordinator import FMIQueryCoordinator

ATTR_NO_DATA_ISSUE_HOURS = "no_data_issue_hours"


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    for coordinator in entry.runtime_data.coordinators:
        if isinstance(coordinator, FMIQueryCoordinator):
            async_add_entities([FMIStaleDataBinarySensor(coordinator)], config_subentry_id=coordinator.subentry.subentry_id)


class FMIStaleDataBinarySensor(CoordinatorEntity[FMIQueryCoordinator], BinarySensorEntity):
    """On while the newest value FMI holds for the sensor is older than the stale data limit.

    The repair issue tells a person that something is wrong; this tells
    automations, and it turns off by itself when data comes back. It works
    whether or not the repair issue is enabled.
    """

    _attr_attribution = ATTRIBUTION
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_translation_key = "stale_data"

    def __init__(self, coordinator: FMIQueryCoordinator):
        super().__init__(coordinator)
        self._attr_unique_id = coordinator.unique_id
        self._attr_device_info = coordinator.config_entry.runtime_data.devices[coordinator.subentry.subentry_id]
        self._attr_translation_placeholders = {"label": coordinator.measurement[CONF_LABEL]}
        self._attr_extra_state_attributes = {ATTR_NO_DATA_ISSUE_HOURS: coordinator.stale_after_hours}

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.get("stale") if self.coordinator.data else None
