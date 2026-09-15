"""Fetching one observation or forecast sensor, and noticing when its data goes stale."""
import logging
from datetime import datetime, timedelta
from typing import Any

from dateutil.relativedelta import relativedelta
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (API_TIME_FORMAT, CONF_FORECAST_HOURS, CONF_FORECAST_PAST_HOURS, CONF_FORECAST_STEP, CONF_LABEL,
                    CONF_LANG, CONF_NEGATIVE_AS_ZERO, CONF_NO_DATA_ISSUE, CONF_NO_DATA_ISSUE_HOURS, CONF_PARAMETER,
                    CONF_QUERY_ID, CONF_TARGET, CONF_TARGET_TYPE, DEFAULT_NO_DATA_ISSUE, DEFAULT_NO_DATA_ISSUE_HOURS,
                    DEFAULT_SCAN_INTERVAL, DOMAIN, MINIMUM_STALE_HOURS)
from .session import FMISession, FMIException

_LOGGER = logging.getLogger(__name__)


def build_unique_id(data: dict[str, Any]) -> str:
    """Identify a sensor by what it measures, not by what it is called.

    The label is a display name the user may rename, so it must not be part of
    any identity. This is the subentry's unique id, which is what stops the
    same measurement being added twice.
    """
    return "_".join([str(data[CONF_QUERY_ID]), str(data[CONF_TARGET_TYPE]),
                     str(data[CONF_TARGET]), str(data[CONF_PARAMETER])]).lower()


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


def stale_after_hours(query_id: str, configured_hours: int) -> int:
    """The age in hours at which a sensor's data counts as stale.

    The setting is shared by every sensor, so for aggregate queries it is raised
    to a whole reporting period: their newest value can legitimately be that old.
    """
    minimum = max((hours for marker, hours in MINIMUM_STALE_HOURS.items() if marker in query_id), default=0)
    return max(configured_hours, minimum)


class FMIQueryCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """One sensor: one parameter of one query at one station or forecast point."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, subentry: ConfigSubentry):
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {subentry.title}",
            update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL),
        )
        self.subentry = subentry
        self.issue_id = f"no_data_{subentry.subentry_id}"
        # Whether this outage has been looked into already, so the probe in
        # _async_report_no_data runs once per outage rather than once per update.
        self._reported = False

    @property
    def stale_after_hours(self) -> int:
        configured = self.config_entry.options.get(CONF_NO_DATA_ISSUE_HOURS, DEFAULT_NO_DATA_ISSUE_HOURS)
        return stale_after_hours(str(self.subentry.data[CONF_QUERY_ID]), configured)

    def _params(self, now: datetime, filter_parameter: bool, start_time: datetime | None = None) -> dict[str, Any]:
        data = self.subentry.data
        query_id = str(data[CONF_QUERY_ID])
        is_forecast = "::forecast" in query_id
        if start_time is None:
            start_time = get_start_time(query_id, now, data)
        end_time = now + timedelta(hours=data[CONF_FORECAST_HOURS]) if is_forecast else None
        params = {"starttime": start_time.strftime(API_TIME_FORMAT) if start_time is not None else None,
                  "endtime": end_time.strftime(API_TIME_FORMAT) if end_time is not None else None,
                  "timestep": data.get(CONF_FORECAST_STEP), "storedquery_id": query_id,
                  data[CONF_TARGET_TYPE]: data[CONF_TARGET]}

        if filter_parameter:
            # Ignored by queries that do not declare it (the STUK nuclide query
            # uses "nuclides"), which is harmless: get_feature filters anyway.
            params["parameters"] = data[CONF_PARAMETER]

        return params

    async def _async_update_data(self) -> dict[str, Any]:
        data = self.subentry.data
        now = dt_util.utcnow()
        is_forecast = "::forecast" in str(data[CONF_QUERY_ID])

        try:
            result = await self.hass.async_add_executor_job(FMISession().get_feature, data[CONF_LANG],
                                                            self._params(now, True), data[CONF_PARAMETER],
                                                            is_forecast is False,
                                                            data.get(CONF_NEGATIVE_AS_ZERO, False))
        except FMIException as exception:
            raise UpdateFailed(f"Could not read {data[CONF_LABEL]} from FMI: {exception}") from exception

        # Staleness is always worked out, because the stale data binary sensor
        # reports it; the repair issue is the part that can be switched off.
        stale = await self._async_is_stale(now, timedelta(hours=self.stale_after_hours), is_forecast, result)

        if not stale:
            self._reported = False
            ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)
        elif not self._reported:
            self._reported = True
            if self.config_entry.options.get(CONF_NO_DATA_ISSUE, DEFAULT_NO_DATA_ISSUE):
                await self._async_report_no_data(self._params(now, False))

        result["stale"] = stale
        return result

    async def _async_is_stale(self, now: datetime, grace: timedelta, is_forecast: bool, result: dict[str, Any]) -> bool:
        """Whether the newest value FMI holds for this sensor is older than the grace period.

        The age comes from FMI's own timestamps rather than from how long this
        run of Home Assistant has been seeing empty updates, so it is not reset
        by a restart. Forecast values are stamped in the future, which makes
        their age negative until the last forecast point falls into the past.
        """
        data = self.subentry.data
        newest = max((item["time"] for item in result["data"]), default=None)

        if newest is not None:
            return now - newest >= grace

        if self._reported:
            # Already found to be stale, and the poll is still empty. Nothing
            # has changed, and dating it again would cost a query every poll
            # for as long as the outage lasts. Recovery shows up as data here.
            return True

        # An empty result only says that the poll window held nothing, and that
        # window is an hour for the hourly queries, so on its own it dates
        # nothing. Where the grace period reaches further back than the window,
        # ask again over the whole of it before calling the sensor stale.
        window_start = get_start_time(str(data[CONF_QUERY_ID]), now, data)

        if window_start is None or window_start <= now - grace:
            return True

        try:
            widened = await self.hass.async_add_executor_job(FMISession().get_feature, data[CONF_LANG],
                                                             self._params(now, True, now - grace),
                                                             data[CONF_PARAMETER], is_forecast is False,
                                                             data.get(CONF_NEGATIVE_AS_ZERO, False))
        except FMIException as exception:
            # Better to say nothing than to report an outage the network invented.
            _LOGGER.debug(f"Could not date the last data for {data[CONF_LABEL]}: {exception}")
            return False

        newest = max((item["time"] for item in widened["data"]), default=None)

        return newest is None or now - newest >= grace

    async def _async_report_no_data(self, probe_params: dict[str, Any]) -> None:
        """Work out why a sensor is empty and raise a repair issue if it is broken.

        The polling query is filtered to a single parameter, so it cannot say what
        else the station offers. This unfiltered probe runs only on failure.
        """
        data = self.subentry.data
        parameter = data[CONF_PARAMETER]

        try:
            available = await self.hass.async_add_executor_job(FMISession().list_parameters,
                                                               data[CONF_LANG], probe_params)
        except FMIException as exception:
            _LOGGER.warning(f"Could not determine why {data[CONF_LABEL]} has no data: {exception}")
            return

        placeholders = {"label": data[CONF_LABEL], "parameter": parameter,
                        "query_id": str(data[CONF_QUERY_ID]),
                        "target_type": data[CONF_TARGET_TYPE], "target": data[CONF_TARGET]}

        if not available:
            translation_key = "no_data"
        elif parameter.lower() not in {name.lower() for name in available}:
            translation_key = "parameter_missing"
            placeholders["available"] = ", ".join(available)
        else:
            # The parameter is still served, there is just nothing to report yet.
            return

        _LOGGER.warning(f"{data[CONF_LABEL]}: no data ({translation_key}), available={available}")

        ir.async_create_issue(self.hass, DOMAIN, self.issue_id, is_fixable=False,
                              severity=ir.IssueSeverity.WARNING, translation_key=translation_key,
                              translation_placeholders=placeholders)
