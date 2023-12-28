from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, CONF_FMISID, CONF_STEP, CONF_SENSOR_TYPE, DEFAULT_SCAN_INTERVAL, SENSOR_CONFIGS, \
    CONF_FORECAST_HOURS, CONF_FORECAST_PAST_HOURS
from .session import FMISession

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    async def async_update_data():
        now = datetime.utcnow()
        conf = next((conf for conf in SENSOR_CONFIGS if conf["id"] == entry.data[CONF_SENSOR_TYPE]), None)
        start_time = now - timedelta(hours=entry.data[CONF_FORECAST_PAST_HOURS]) if conf["is_forecast"] is True else now - timedelta(hours=1)
        end_time = now + timedelta(hours=entry.data[CONF_FORECAST_HOURS]) if conf["is_forecast"] is True else now
        step = entry.data[CONF_STEP] if conf["is_forecast"] is True else 0
        api = FMISession(entry.data[CONF_FMISID], step)
        return await hass.async_add_executor_job(api.query, conf, start_time, end_time)

    coord = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=entry.unique_id or DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL),
    )

    await coord.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coord

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "sensor")
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_forward_entry_unload(entry, "sensor"):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
