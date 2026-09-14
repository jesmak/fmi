from datetime import datetime, timedelta
import logging
from typing import Any

from dateutil.relativedelta import relativedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL, CONF_FORECAST_HOURS, CONF_FORECAST_PAST_HOURS, CONF_QUERY_ID, \
    CONF_LANG, CONF_FORECAST_STEP, CONF_TARGET, CONF_TARGET_TYPE, CONF_PARAMETER, \
    CONF_NEGATIVE_AS_ZERO, CONF_NO_DATA_ISSUE, CONF_NO_DATA_ISSUE_HOURS, DEFAULT_NO_DATA_ISSUE, \
    DEFAULT_NO_DATA_ISSUE_HOURS, API_TIME_FORMAT, CONF_LABEL
from .session import FMISession, FMIException

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    issue_id = f"no_data_{entry.entry_id}"
    # Whether this outage has been looked into already, so the probe in
    # async_report_no_data runs once per outage rather than once per update.
    no_data = {"reported": False}

    def build_params(now: datetime, filter_parameter: bool, start_time: datetime | None = None) -> dict[str, Any]:
        query_id = str(entry.data[CONF_QUERY_ID])
        is_forecast = "::forecast" in query_id
        if start_time is None:
            start_time = get_start_time(query_id, now, entry.data)
        end_time = now + timedelta(hours=entry.data[CONF_FORECAST_HOURS]) if is_forecast else None
        params = {"starttime": start_time.strftime(API_TIME_FORMAT) if start_time is not None else None,
                  "endtime": end_time.strftime(API_TIME_FORMAT) if end_time is not None else None,
                  "timestep": entry.data.get(CONF_FORECAST_STEP), "storedquery_id": query_id,
                  entry.data[CONF_TARGET_TYPE]: entry.data[CONF_TARGET]}

        if filter_parameter:
            # Ignored by queries that do not declare it (the STUK nuclide query
            # uses "nuclides"), which is harmless: get_feature filters anyway.
            params["parameters"] = entry.data[CONF_PARAMETER]

        return params

    async def async_is_stale(now: datetime, grace: timedelta, is_forecast: bool, result: dict[str, Any]) -> bool:
        """Whether the newest value FMI holds for this sensor is older than the grace period.

        The age comes from FMI's own timestamps rather than from how long this
        run of Home Assistant has been seeing empty updates, so it is not reset
        by a restart. Forecast values are stamped in the future, which makes
        their age negative until the last forecast point falls into the past.
        """
        newest = max((item["time"] for item in result["data"]), default=None)

        if newest is not None:
            return now - newest >= grace

        if no_data["reported"]:
            # Already found to be stale, and the poll is still empty. Nothing
            # has changed, and dating it again would cost a query every poll
            # for as long as the outage lasts. Recovery shows up as data here.
            return True

        # An empty result only says that the poll window held nothing, and that
        # window is an hour for the hourly queries, so on its own it dates
        # nothing. Where the grace period reaches further back than the window,
        # ask again over the whole of it before calling the sensor stale.
        window_start = get_start_time(str(entry.data[CONF_QUERY_ID]), now, entry.data)

        if window_start is None or window_start <= now - grace:
            return True

        try:
            widened = await hass.async_add_executor_job(FMISession().get_feature, entry.data[CONF_LANG],
                                                        build_params(now, True, now - grace),
                                                        entry.data[CONF_PARAMETER], is_forecast is False,
                                                        entry.data.get(CONF_NEGATIVE_AS_ZERO, False))
        except FMIException as exception:
            # Better to say nothing than to report an outage the network invented.
            _LOGGER.debug(f"Could not date the last data for {entry.data[CONF_LABEL]}: {exception}")
            return False

        newest = max((item["time"] for item in widened["data"]), default=None)

        return newest is None or now - newest >= grace

    async def async_update_data():
        now = dt_util.utcnow()
        is_forecast = "::forecast" in str(entry.data[CONF_QUERY_ID])
        api = FMISession()
        result = await hass.async_add_executor_job(api.get_feature, entry.data[CONF_LANG],
                                                   build_params(now, True), entry.data[CONF_PARAMETER],
                                                   is_forecast is False,
                                                   entry.data.get(CONF_NEGATIVE_AS_ZERO, False))

        if entry.data.get(CONF_NO_DATA_ISSUE, DEFAULT_NO_DATA_ISSUE):
            grace = timedelta(hours=entry.data.get(CONF_NO_DATA_ISSUE_HOURS, DEFAULT_NO_DATA_ISSUE_HOURS))

            if not await async_is_stale(now, grace, is_forecast, result):
                no_data["reported"] = False
                ir.async_delete_issue(hass, DOMAIN, issue_id)
            elif not no_data["reported"]:
                no_data["reported"] = True
                await async_report_no_data(hass, entry, issue_id, build_params(now, False))

        return result

    coord = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=entry.unique_id or DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL),
    )

    await coord.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coord

    # The options flow writes the new forecast settings straight into entry.data,
    # so reload the entry to rebuild the coordinator and the sensor attributes.
    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    return True


async def async_report_no_data(hass: HomeAssistant, entry: ConfigEntry, issue_id: str,
                               probe_params: dict[str, Any]) -> None:
    """Work out why a sensor is empty and raise a repair issue if it is broken.

    The polling query is filtered to a single parameter, so it cannot say what
    else the station offers. This unfiltered probe runs only on failure.
    """
    parameter = entry.data[CONF_PARAMETER]

    try:
        available = await hass.async_add_executor_job(FMISession().list_parameters,
                                                      entry.data[CONF_LANG], probe_params)
    except FMIException as exception:
        _LOGGER.warning(f"Could not determine why {entry.data[CONF_LABEL]} has no data: {exception}")
        return

    placeholders = {"label": entry.data[CONF_LABEL], "parameter": parameter,
                    "query_id": str(entry.data[CONF_QUERY_ID]),
                    "target_type": entry.data[CONF_TARGET_TYPE], "target": entry.data[CONF_TARGET]}

    if not available:
        translation_key = "no_data"
    elif parameter.lower() not in {name.lower() for name in available}:
        translation_key = "parameter_missing"
        placeholders["available"] = ", ".join(available)
    else:
        # The parameter is still served, there is just nothing to report yet.
        return

    _LOGGER.warning(f"{entry.data[CONF_LABEL]}: no data ({translation_key}), available={available}")

    ir.async_create_issue(hass, DOMAIN, issue_id, is_fixable=False, severity=ir.IssueSeverity.WARNING,
                          translation_key=translation_key, translation_placeholders=placeholders)


async def async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def build_unique_id(data: dict[str, Any]) -> str:
    """Identify a sensor by what it measures, not by what it is called.

    The label is a display name the user may rename, so it must not be part of
    any identity. This is used for the config entry, which is what stops the
    same measurement being added twice; entities key off entry_id so that
    repointing a sensor keeps its history.
    """
    return "_".join([str(data[CONF_QUERY_ID]), str(data[CONF_TARGET_TYPE]),
                     str(data[CONF_TARGET]), str(data[CONF_PARAMETER])]).lower()


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Move off label-derived identifiers (version 1) so sensors can be renamed."""
    if entry.version > 1:
        return True

    registry = er.async_get(hass)
    old_unique_id = f"fmi_{entry.data[CONF_LABEL]}"

    for registered in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registered.unique_id != old_unique_id:
            continue
        if registry.async_get_entity_id(registered.domain, DOMAIN, entry.entry_id):
            _LOGGER.warning(f"Cannot migrate {registered.entity_id}: {entry.entry_id} already in use")
            continue
        _LOGGER.debug(f"Migrating {registered.entity_id} unique id to {entry.entry_id}")
        registry.async_update_entity(registered.entity_id, new_unique_id=entry.entry_id)

    hass.config_entries.async_update_entry(entry, unique_id=build_unique_id(entry.data), version=2)

    return True


def get_start_time(query_id: str, now: datetime, data: dict[str, Any]):
    # Aggregate queries have to reach back past the current period: the running
    # day/month/year is reported as NaN until it completes, and NaN values are
    # discarded, which otherwise leaves the sensor permanently empty.
    return now - timedelta(hours=data[CONF_FORECAST_PAST_HOURS]) if "::forecast" in query_id else \
        now.replace(minute=0, second=0) - relativedelta(hours=1) if "::hourly" in query_id else \
            now.replace(hour=0, minute=0, second=0) - relativedelta(days=2) if "::daily" in query_id else \
                now.replace(day=1, hour=0, minute=0, second=0) - relativedelta(months=2) if "::monthly" in query_id else \
                    now.replace(month=1, day=1, hour=0, minute=0, second=0) - relativedelta(years=2) if "::yearly" in query_id else \
                        now - timedelta(hours=12) if not query_id.startswith("stuk::") else None


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_forward_entry_unload(entry, "sensor"):
        hass.data[DOMAIN].pop(entry.entry_id)
        ir.async_delete_issue(hass, DOMAIN, f"no_data_{entry.entry_id}")

    return unload_ok
