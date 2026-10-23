"""Fetching one observation or forecast sensor, and noticing when its data goes stale."""

import logging
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    API_TIME_FORMAT,
    CONF_FORECAST_HOURS,
    CONF_FORECAST_PAST_HOURS,
    CONF_FORECAST_STEP,
    CONF_LABEL,
    CONF_LANG,
    CONF_NEGATIVE_AS_ZERO,
    CONF_NO_DATA_ISSUE,
    CONF_NO_DATA_ISSUE_HOURS,
    CONF_PARAMETER,
    CONF_QUERY_ID,
    CONF_TARGET,
    CONF_TARGET_TYPE,
    CONF_UNIT,
    DEFAULT_NO_DATA_ISSUE,
    DEFAULT_NO_DATA_ISSUE_HOURS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MINIMUM_STALE_HOURS,
    PERIODS,
    STUK_AIR_DAYS,
    STUK_AIR_QUERY_ID,
    STUK_AIR_SAMPLES_QUERY_ID,
    STUK_AIR_SCAN_INTERVAL,
)
from .session import FMIException, FMIRefused, FMISession, allowed_hours

_LOGGER = logging.getLogger(__name__)


def measurement_name(descriptions: Mapping[str, tuple[str | None, str | None]], lang: str, query_id: str, parameter: str) -> str:
    """A sensor's default name: FMI's description of the parameter, or the parameter itself, with the query's period."""
    described = descriptions.get(parameter.lower(), (None, None))[0]
    name = described or parameter
    period = next((names for key, names in PERIODS.items() if key in query_id), None)
    return f"{name}, {period.get(lang, period['eng'])}" if period else name


def build_unique_id(data: Mapping[str, Any]) -> str:
    """Identify a sensor of 3.x by what it measures, not by what it is called. Used when moving from before 4.0.0."""
    return "_".join([str(data[CONF_QUERY_ID]), str(data[CONF_TARGET_TYPE]), str(data[CONF_TARGET]), str(data[CONF_PARAMETER])]).lower()


def measurement_key(measurement: Mapping[str, Any]) -> str:
    """Identify a measurement within its station: the query and the parameter, never the name the user may change."""
    return f"{measurement[CONF_QUERY_ID]}_{measurement[CONF_PARAMETER]}".lower()


def station_unique_id(target_type: str, target: Any) -> str:
    """A station subentry's unique id, which is what stops the same station being added twice."""
    return f"station_{target_type}_{str(target).strip().lower()}"


def get_start_time(query_id: str, now: datetime, data: Mapping[str, Any]) -> datetime | None:
    # Aggregate queries have to reach back past the current period: the running
    # day/month/year is reported as NaN until it completes, and NaN values are
    # discarded, which otherwise leaves the sensor permanently empty.
    if "::forecast" in query_id:
        return now - timedelta(hours=data[CONF_FORECAST_PAST_HOURS])
    if "::hourly" in query_id:
        return now.replace(minute=0, second=0) - timedelta(hours=1)
    if "::daily" in query_id:
        return now.replace(hour=0, minute=0, second=0) - timedelta(days=2)
    if "::monthly" in query_id:
        months = now.year * 12 + now.month - 1 - 2
        return now.replace(year=months // 12, month=months % 12 + 1, day=1, hour=0, minute=0, second=0)
    if "::yearly" in query_id:
        return now.replace(year=now.year - 2, month=1, day=1, hour=0, minute=0, second=0)
    if query_id == STUK_AIR_QUERY_ID:
        return now - timedelta(days=STUK_AIR_DAYS)
    if query_id.startswith("stuk::"):
        return None
    return now - timedelta(hours=12)


def query_params(
    data: Mapping[str, Any], now: datetime, filter_parameter: bool = True, start_time: datetime | None = None
) -> dict[str, Any]:
    """The query a sensor makes, also used to try it out in the config flow."""
    query_id = str(data[CONF_QUERY_ID])
    is_forecast = "::forecast" in query_id
    if start_time is None:
        start_time = get_start_time(query_id, now, data)
    end_time = now + timedelta(hours=data[CONF_FORECAST_HOURS]) if is_forecast else None
    params = {
        "starttime": start_time.strftime(API_TIME_FORMAT) if start_time is not None else None,
        "endtime": end_time.strftime(API_TIME_FORMAT) if end_time is not None else None,
        "timestep": data.get(CONF_FORECAST_STEP) if is_forecast else None,
        # A STUK air measurement keeps the query it was added with, but is read from every sample in the window.
        "storedquery_id": STUK_AIR_SAMPLES_QUERY_ID if query_id == STUK_AIR_QUERY_ID else query_id,
        data[CONF_TARGET_TYPE]: data[CONF_TARGET],
    }
    if filter_parameter:
        # Ignored by queries that do not declare it (the STUK nuclide query
        # uses "nuclides"), which is harmless: get_feature filters anyway.
        params["parameters"] = data[CONF_PARAMETER]
    return params


def stale_after_hours(query_id: str, configured_hours: int) -> int:
    """The age in hours at which a sensor's data counts as stale.

    The setting is shared by every sensor, so it is raised for the queries whose
    newest value can legitimately be older: to a whole reporting period for the
    aggregate ones, and to six weeks for STUK's air samples.
    """
    minimum = max((hours for marker, hours in MINIMUM_STALE_HOURS.items() if marker in query_id), default=0)
    return max(configured_hours, minimum)


class FMIQueryCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """One measurement of a station: one parameter of one query at the station or forecast point."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, subentry: ConfigSubentry, measurement: Mapping[str, Any]):
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {subentry.title} {measurement[CONF_LABEL]}",
            update_interval=timedelta(
                minutes=STUK_AIR_SCAN_INTERVAL if measurement[CONF_QUERY_ID] == STUK_AIR_QUERY_ID else DEFAULT_SCAN_INTERVAL
            ),
        )
        self.subentry = subentry
        # What the queries need: the measurement with its station and the entry's language.
        self.measurement: dict[str, Any] = {
            CONF_LANG: entry.data[CONF_LANG],
            CONF_TARGET_TYPE: subentry.data[CONF_TARGET_TYPE],
            CONF_TARGET: subentry.data[CONF_TARGET],
            **measurement,
        }
        self.unique_id = f"{subentry.subentry_id}_{measurement_key(measurement)}"
        self.issue_id = f"no_data_{self.unique_id}"
        # Whether this outage has been looked into already, so the probe in
        # _async_report_no_data runs once per outage rather than once per update.
        self._reported = False
        # The unit comes from FMI's parameter metadata, which doesn't change, so it is
        # looked up once rather than with every poll. A unit the user gave wins, and needs no lookup.
        self._unit: str | None = measurement.get(CONF_UNIT)
        self._unit_known = self._unit is not None
        # The longest window FMI allows the query, from start to end, once it has refused a longer one. Learned rather
        # than listed, as each query has a limit of its own and FMI documents none of them.
        self._max_window: timedelta | None = None

    @property
    def stale_after_hours(self) -> int:
        configured = self.config_entry.options.get(CONF_NO_DATA_ISSUE_HOURS, DEFAULT_NO_DATA_ISSUE_HOURS)
        return stale_after_hours(str(self.measurement[CONF_QUERY_ID]), configured)

    def _params(self, now: datetime, filter_parameter: bool, start_time: datetime | None = None) -> dict[str, Any]:
        return query_params(self.measurement, now, filter_parameter, start_time)

    async def _async_update_data(self) -> dict[str, Any]:
        data = self.measurement
        now = dt_util.utcnow()
        is_forecast = "::forecast" in str(data[CONF_QUERY_ID])

        try:
            result = await self.hass.async_add_executor_job(
                FMISession().get_feature,
                data[CONF_LANG],
                self._params(now, True),
                data[CONF_PARAMETER],
                is_forecast is False,
                data.get(CONF_NEGATIVE_AS_ZERO, False),
            )
            if not self._unit_known:
                self._unit = await self.hass.async_add_executor_job(
                    FMISession().get_unit, data[CONF_LANG], str(data[CONF_QUERY_ID]), data[CONF_PARAMETER]
                )
                self._unit_known = True
        except FMIException as exception:
            raise UpdateFailed(f"Could not read {data[CONF_LABEL]} from FMI: {exception}") from exception

        result["unit"] = self._unit

        # Staleness is always worked out, because the stale data binary sensor
        # reports it; the repair issue is the part that can be switched off.
        stale = await self._async_is_stale(now, timedelta(hours=self.stale_after_hours), is_forecast, result)

        issue_enabled = self.config_entry.options.get(CONF_NO_DATA_ISSUE, DEFAULT_NO_DATA_ISSUE)
        if not stale:
            self._reported = False
        elif not self._reported:
            # Set whether or not the issue is wanted: it also spares the next
            # polls of this outage the wider stale check.
            self._reported = True
            if issue_enabled:
                await self._async_report_no_data(self._params(now, False))
        if not stale or not issue_enabled:
            # Also clears an issue raised before the user switched them off.
            ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)

        result["stale"] = stale
        return result

    async def _async_is_stale(self, now: datetime, grace: timedelta, is_forecast: bool, result: dict[str, Any]) -> bool:
        """Whether the newest value FMI holds for this sensor is older than the grace period, or than FMI lets the
        query reach back.

        When the poll came back empty but the wider query finds a value, that value goes into the result.

        The age comes from FMI's own timestamps rather than from how long this
        run of Home Assistant has been seeing empty updates, so it is not reset
        by a restart. Forecast values are stamped in the future, which makes
        their age negative until the last forecast point falls into the past.
        """
        data = self.measurement
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
        # ask again over as much of it as FMI allows before calling the sensor stale.
        window_start = get_start_time(str(data[CONF_QUERY_ID]), now, data)

        if window_start is None or window_start <= now - grace:
            return True

        # Data older than FMI lets the query reach can't be dated, so silence over all of that counts as stale too.
        try:
            try:
                widened = await self._async_read_since(now, now - self._reach(grace, is_forecast), is_forecast)
            except FMIRefused as exception:
                hours = allowed_hours(exception)
                if hours is None or self._max_window is not None:
                    raise
                # A minute short, as FMI measures the window by its own clock and refuses a minute over.
                self._max_window = timedelta(hours=hours, minutes=-1)
                widened = await self._async_read_since(now, now - self._reach(grace, is_forecast), is_forecast)
        except FMIException as exception:
            # Better to say nothing than to report an outage the network invented.
            _LOGGER.debug(f"Could not date the last data for {data[CONF_LABEL]}: {exception}")
            return False

        newest = max((item["time"] for item in widened["data"]), default=None)
        if newest is not None:
            # The poll window missed the latest value, which the wider query found. Show it.
            result.update(data=widened["data"], latitude=widened["latitude"], longitude=widened["longitude"])

        return newest is None or now - newest >= grace

    def _reach(self, grace: timedelta, is_forecast: bool) -> timedelta:
        """How far back the stale check asks: the grace period, within FMI's limit once it is known. FMI's limit is on
        the whole window, which for a forecast also runs its hours ahead."""
        if self._max_window is None:
            return grace
        ahead = timedelta(hours=self.measurement[CONF_FORECAST_HOURS]) if is_forecast else timedelta()
        return min(grace, self._max_window - ahead)

    async def _async_read_since(self, now: datetime, start_time: datetime, is_forecast: bool) -> dict[str, Any]:
        data = self.measurement
        return await self.hass.async_add_executor_job(
            FMISession().get_feature,
            data[CONF_LANG],
            self._params(now, True, start_time),
            data[CONF_PARAMETER],
            is_forecast is False,
            data.get(CONF_NEGATIVE_AS_ZERO, False),
        )

    async def _async_report_no_data(self, probe_params: dict[str, Any]) -> None:
        """Work out why a sensor is empty and raise a repair issue if it is broken.

        The polling query is filtered to a single parameter, so it cannot say what
        else the station offers. This unfiltered probe runs only on failure.
        """
        data = self.measurement
        parameter = data[CONF_PARAMETER]

        try:
            available = await self.hass.async_add_executor_job(FMISession().list_parameters, data[CONF_LANG], probe_params)
        except FMIException as exception:
            _LOGGER.warning(f"Could not determine why {data[CONF_LABEL]} has no data: {exception}")
            return

        placeholders = {
            # The station and the measurement, as the sensor is named.
            "label": f"{self.subentry.title} {data[CONF_LABEL]}",
            "parameter": parameter,
            "query_id": str(data[CONF_QUERY_ID]),
            "target_type": data[CONF_TARGET_TYPE],
            "target": data[CONF_TARGET],
        }

        if not available:
            translation_key = "no_data"
        elif parameter.lower() not in {name.lower() for name in available}:
            translation_key = "parameter_missing"
            placeholders["available"] = ", ".join(available)
        else:
            # The parameter is still served, there is just nothing to report yet.
            return

        _LOGGER.warning(f"{placeholders['label']}: no data ({translation_key}), available={available}")

        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self.issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=translation_key,
            translation_placeholders=placeholders,
        )
