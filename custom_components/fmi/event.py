"""The event entity of a warnings subentry: fires when FMI issues, updates or cancels a warning for the place."""

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .cap import EVENT_TYPES
from .const import ATTRIBUTION, CONF_LABEL
from .warning_coordinator import FMIWarningsCoordinator, WarningsData


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    for subentry_id, coordinator in entry.runtime_data.coordinators.items():
        if isinstance(coordinator, FMIWarningsCoordinator):
            async_add_entities([FMIWarningEvent(coordinator)], config_subentry_id=subentry_id)


class FMIWarningEvent(CoordinatorEntity[FMIWarningsCoordinator], EventEntity):
    _attr_attribution = ATTRIBUTION
    _attr_event_types = EVENT_TYPES
    _attr_icon = "mdi:alert-decagram"
    _attr_translation_key = "warning"

    def __init__(self, coordinator: FMIWarningsCoordinator):
        super().__init__(coordinator)
        self._attr_unique_id = coordinator.subentry.subentry_id
        self._attr_name = f"FMI {coordinator.subentry.data.get(CONF_LABEL, coordinator.subentry.title)}"
        self._handled: WarningsData | None = coordinator.data

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        # Listeners are also called after a failed refresh, with the old data;
        # its changes have been announced already.
        if data is None or data is self._handled:
            self.async_write_ha_state()
            return
        self._handled = data

        for event_type, warning in data.changes:
            self._trigger_event(event_type, warning.as_dict())
            self.async_write_ha_state()

        if not data.changes:
            self.async_write_ha_state()
