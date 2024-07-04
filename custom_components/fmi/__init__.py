from datetime import datetime, timedelta
import logging
from typing import Any

from dateutil.relativedelta import relativedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL, CONF_FORECAST_HOURS, CONF_FORECAST_PAST_HOURS, CONF_QUERY_ID, \
    CONF_LANG, CONF_FORECAST_STEP, CONF_TARGET, CONF_TARGET_TYPE, CONF_PARAMETER
from .session import FMISession

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    async def async_update_data():
        now = datetime.utcnow()
        query_id = str(entry.data[CONF_QUERY_ID])
        is_forecast = "::forecast" in query_id
        start_time = get_start_time(query_id, now, entry.data)
        end_time = now + timedelta(hours=entry.data[CONF_FORECAST_HOURS]) if is_forecast else None
        api = FMISession()
        params = {"starttime": start_time.strftime('%Y-%m-%d%%20%H:%M:%S') if start_time is not None else None,
                  "endtime": end_time.strftime('%Y-%m-%d%%20%H:%M:%S') if end_time is not None else None,
                  "timestep": entry.data.get(CONF_FORECAST_STEP), "storedquery_id": query_id,
                  entry.data[CONF_TARGET_TYPE]: entry.data[CONF_TARGET]}
        return await hass.async_add_executor_job(api.get_feature, entry.data[CONF_LANG], params,
                                                 entry.data[CONF_PARAMETER], is_forecast is False)

    coord = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=entry.unique_id or DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL),
    )

    await coord.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coord

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    return True


def get_start_time(query_id: str, now: datetime, data: dict[str, Any]):
    return now - timedelta(hours=data[CONF_FORECAST_PAST_HOURS]) if "::forecast" in query_id else \
        now.replace(minute=0, second=0) - relativedelta(hours=1) if "::hourly" in query_id else \
            now.replace(hour=0, minute=0, second=0) if "::daily" in query_id else \
                now.replace(day=1, hour=0, minute=0, second=0) if "::monthly" in query_id else \
                    now.replace(month=1, day=1, hour=0, minute=0, second=0) if "::yearly" in query_id else \
                        now - timedelta(hours=12) if not query_id.startswith("stuk::") else None


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_forward_entry_unload(entry, "sensor"):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
