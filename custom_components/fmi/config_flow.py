import logging
import re
from datetime import timedelta
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback, HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (SelectOptionDict, SelectSelector, SelectSelectorConfig,
                                            SelectSelectorMode)
from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance

from . import build_unique_id, get_start_time

from .const import (DOMAIN, CONF_LABEL, CONF_LANG, CONF_QUERY_ID, CONF_QUERY_LABEL, CONF_FORECAST_HOURS, CONF_TARGET,
                    CONF_FORECAST_PAST_HOURS, CONF_FORECAST_STEP, LANGUAGES, CONF_PARAMETER, CONF_TARGET_TYPE,
                    CONF_NEGATIVE_AS_ZERO, API_TIME_FORMAT)
from .session import FMISession, FMIException

_LOGGER = logging.getLogger(__name__)

CONFIGURE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LANG): vol.All(cv.string, vol.In(LANGUAGES)),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, any]) -> str:
    try:
        now = dt_util.utcnow()
        is_forecast = "::forecast" in str(data[CONF_QUERY_ID])
        start_time = now - timedelta(
            hours=data[CONF_FORECAST_PAST_HOURS]) if is_forecast is True else now - timedelta(hours=1)
        end_time = now + timedelta(hours=data[CONF_FORECAST_HOURS]) if is_forecast is True else now
        api = FMISession()
        params = {"starttime": start_time.strftime(API_TIME_FORMAT), "endtime": end_time.strftime(API_TIME_FORMAT),
                  "timestep": data.get(CONF_FORECAST_STEP),
                  "storedquery_id": data[CONF_QUERY_ID], data[CONF_TARGET_TYPE]: data[CONF_TARGET],
                  "parameters": data[CONF_PARAMETER]}
        await hass.async_add_executor_job(api.get_feature, data[CONF_LANG], params, data[CONF_PARAMETER],
                                          is_forecast is False, data.get(CONF_NEGATIVE_AS_ZERO, False))

    except FMIException:
        raise ConnectionProblem

    return data[CONF_LABEL]


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2
    data = None
    queries = None
    param_schema = None
    stations = None
    descriptions = None

    async def _async_stations_for_query(self) -> list[dict[str, any]]:
        """Stations that serve the chosen query, or all of them as a fallback.

        Forecast queries are interpolated to a point rather than tied to a
        station, so they have no station list of their own.
        """
        lang = self.data[CONF_LANG]
        query_id = str(self.data[CONF_QUERY_ID])
        api = FMISession()
        now = dt_util.utcnow()
        start_time = get_start_time(query_id, now, {CONF_FORECAST_PAST_HOURS: 1})
        params = {"starttime": start_time.strftime(API_TIME_FORMAT) if start_time is not None else None,
                  "endtime": now.strftime(API_TIME_FORMAT)}

        stations = await self.hass.async_add_executor_job(api.list_stations_for_query, lang, query_id, params)

        if stations:
            return stations

        _LOGGER.debug(f"No station list for {query_id}, offering every station")
        return await self.hass.async_add_executor_job(api.list_stations, lang)

    @staticmethod
    @callback
    def _target_type_for(value: str) -> str:
        """Work out which identifier the user gave, so they need not say."""
        text = str(value).strip()

        if re.fullmatch(r"-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?", text):
            return "latlon"

        return "fmisid" if text.isdigit() else "place"

    async def _async_build_target_selector(self):
        """Offer the stations that serve this query, nearest to home first.

        Falls back to a plain text field if the list cannot be fetched. The
        selector accepts custom values so place names and coordinates work too.
        """
        try:
            self.stations = stations = await self._async_stations_for_query()
        except Exception as exception:  # noqa: BLE001 - degrade to a text field, never break the flow
            _LOGGER.warning(f"Could not list stations: {exception}")
            return cv.string

        if not stations:
            return cv.string

        def distance_to_home(station: dict[str, any]) -> float:
            if station["latitude"] is None or station["longitude"] is None:
                return float("inf")
            metres = distance(self.hass.config.latitude, self.hass.config.longitude,
                              station["latitude"], station["longitude"])
            return float("inf") if metres is None else metres

        options = []
        for station in sorted(stations, key=distance_to_home):
            label = station["name"]
            if station["region"] and station["region"] not in label:
                label = f"{label}, {station['region']}"
            away = distance_to_home(station)
            suffix = "" if away == float("inf") else f" - {round(away / 1000)} km"
            options.append(SelectOptionDict(value=station["id"], label=f"{label} ({station['id']}){suffix}"))

        return SelectSelector(SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN,
                                                   custom_value=True, sort=False))


    async def _async_build_parameter_selector(self):
        """Offer the parameters the chosen query and station actually report.

        Falls back to a plain text field if the probe fails, so a station that
        cannot be reached does not dead-end the flow.
        """
        query_id = str(self.data[CONF_QUERY_ID])
        is_forecast = "::forecast" in query_id
        now = dt_util.utcnow()
        # A short window is enough to enumerate names; the aggregate queries reuse
        # the runtime start time so their parameters show up at all.
        start_time = get_start_time(query_id, now, {CONF_FORECAST_PAST_HOURS: 1})
        end_time = now + timedelta(hours=12) if is_forecast else None

        params = {"starttime": start_time.strftime(API_TIME_FORMAT) if start_time is not None else None,
                  "endtime": end_time.strftime(API_TIME_FORMAT) if end_time is not None else None,
                  "storedquery_id": query_id, self.data[CONF_TARGET_TYPE]: self.data[CONF_TARGET]}

        api = FMISession()

        try:
            names = await self.hass.async_add_executor_job(api.list_parameters, self.data[CONF_LANG], params)
        except Exception as exception:  # noqa: BLE001 - degrade to a text field, never break the flow
            _LOGGER.warning(f"Could not list parameters for {query_id}: {exception}")
            return cv.string

        if not names:
            return cv.string

        try:
            self.descriptions = descriptions = await self.hass.async_add_executor_job(api.get_parameter_descriptions,
                                                             self.data[CONF_LANG], query_id)
        except Exception:  # noqa: BLE001 - labels are cosmetic, fall back to bare names
            self.descriptions = descriptions = {}

        options = []
        for name in names:
            label, unit = descriptions.get(name.lower(), (None, None))
            text = name if label is None else f"{name} - {label}"
            options.append(SelectOptionDict(value=name, label=text if unit is None else f"{text} ({unit})"))

        # custom_value keeps a parameter that the probe window happened to miss reachable.
        return SelectSelector(SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN,
                                                   custom_value=True, sort=False))


    @callback
    def _params_placeholders(self) -> dict[str, str]:
        now = dt_util.utcnow()
        query_id = self.data[CONF_QUERY_ID]
        return {
            "url": f"https://opendata.fmi.fi/wfs/{self.data[CONF_LANG]}?request=getFeature"
                   f"&storedquery_id={query_id}"
                   f"&starttime={(now - timedelta(hours=1)).strftime(API_TIME_FORMAT)}"
                   f"&endtime={now.strftime(API_TIME_FORMAT)}"
                   f"&{self.data[CONF_TARGET_TYPE]}={self.data[CONF_TARGET]}",
        }

    async def async_step_user(self, user_input: dict[str, any] = None) -> FlowResult:

        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=CONFIGURE_SCHEMA)

        self.data = user_input
        return await self.async_step_query()

    async def async_step_query(self, user_input: dict[str, any] = None) -> FlowResult:

        if user_input is None:
            session = FMISession()
            self.queries = await self.hass.async_add_executor_job(session.list_stored_queries, self.data[CONF_LANG],
                                                                  "::simple")
            schema = vol.Schema({
                vol.Required(CONF_QUERY_LABEL): vol.All(cv.string,
                                                        vol.In([f"{query[1]} ({query[0]})" for query in self.queries])),
            })

            return self.async_show_form(step_id="query", data_schema=schema)

        user_input[CONF_QUERY_ID] = next(
            (query[0] for query in self.queries if str(user_input[CONF_QUERY_LABEL]).startswith(query[1])), None)
        self.data.update(user_input)

        return await self.async_step_location()

    async def async_step_location(self, user_input: dict[str, any] = None) -> FlowResult:

        if user_input is None:
            schema = vol.Schema({
                vol.Required(CONF_TARGET): await self._async_build_target_selector(),
            })

            return self.async_show_form(step_id="location", data_schema=schema)

        user_input[CONF_TARGET_TYPE] = self._target_type_for(user_input[CONF_TARGET])
        self.data.update(user_input)

        return await self.async_step_params()

    async def async_step_params(self, user_input: dict[str, any] = None) -> FlowResult:

        if user_input is None:
            schema_params = {
                vol.Required(CONF_PARAMETER): await self._async_build_parameter_selector(),
                vol.Required(CONF_NEGATIVE_AS_ZERO, default=False): cv.boolean
            }

            if "::forecast" in str(self.data[CONF_QUERY_ID]):
                schema_params[vol.Required(CONF_FORECAST_HOURS, default=36)] = cv.positive_int
                schema_params[vol.Required(CONF_FORECAST_PAST_HOURS, default=5)] = cv.positive_int
                schema_params[vol.Required(CONF_FORECAST_STEP, default=30)] = cv.positive_int

            self.param_schema = vol.Schema(schema_params)

            return self.async_show_form(step_id="params", data_schema=self.param_schema,
                                        description_placeholders=self._params_placeholders())

        errors = {}

        try:
            all_data = self.data.copy()
            all_data.update(user_input)
            all_data[CONF_LABEL] = ""
            await validate_input(self.hass, all_data)
        except ConnectionProblem:
            errors["base"] = "connection_problem"
        except Exception:
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            self.data.update(user_input)
            await self.async_set_unique_id(build_unique_id(self.data))
            self._abort_if_unique_id_configured()
            return await self.async_step_name()

        return self.async_show_form(step_id="params", data_schema=self.param_schema, errors=errors,
                                    description_placeholders=self._params_placeholders())

    @callback
    def _default_label(self) -> str:
        """Suggest a name from the station and parameter already chosen."""
        target = str(self.data.get(CONF_TARGET, ""))
        source = target

        if self.data.get(CONF_TARGET_TYPE) == "fmisid" and self.stations:
            station = next((item for item in self.stations if item["id"] == target), None)
            if station is not None:
                source = station["name"]

        parameter = str(self.data.get(CONF_PARAMETER, ""))
        described = (self.descriptions or {}).get(parameter.lower())
        measurement = described[0] if described and described[0] else parameter

        return f"{source} {measurement}".strip()

    async def async_step_name(self, user_input: dict[str, any] = None) -> FlowResult:

        if user_input is None:
            schema = vol.Schema({vol.Required(CONF_LABEL, default=self._default_label()): cv.string})
            return self.async_show_form(step_id="name", data_schema=schema, last_step=True)

        self.data.update(user_input)

        return self.async_create_entry(title=self.data[CONF_LABEL], data=self.data)

    async def async_step_reconfigure(self, user_input: dict[str, any] = None) -> FlowResult:
        """Repoint an existing sensor at a different station, query or parameter.

        The name is not editable here: entities are keyed on the config entry,
        so renaming is a plain entity rename and needs no flow of its own.
        """
        entry = self._get_reconfigure_entry()

        if user_input is None:
            self.data = dict(entry.data)
            session = FMISession()
            self.queries = await self.hass.async_add_executor_job(session.list_stored_queries,
                                                                  self.data[CONF_LANG], "::simple")
            choices = [f"{query[1]} ({query[0]})" for query in self.queries]
            current = next((choice for choice, query in zip(choices, self.queries)
                            if query[0] == self.data.get(CONF_QUERY_ID)), None)

            schema = vol.Schema({
                vol.Required(CONF_QUERY_LABEL, **({"default": current} if current else {})):
                    vol.All(cv.string, vol.In(choices)),
            })

            return self.async_show_form(step_id="reconfigure", data_schema=schema)

        user_input[CONF_QUERY_ID] = next(
            (query[0] for query in self.queries if str(user_input[CONF_QUERY_LABEL]).startswith(query[1])), None)
        self.data.update(user_input)

        return await self.async_step_reconfigure_location()

    async def async_step_reconfigure_location(self, user_input: dict[str, any] = None) -> FlowResult:

        if user_input is None:
            schema = vol.Schema({
                vol.Required(CONF_TARGET, default=self.data.get(CONF_TARGET)):
                    await self._async_build_target_selector(),
            })

            return self.async_show_form(step_id="reconfigure_location", data_schema=schema)

        user_input[CONF_TARGET_TYPE] = self._target_type_for(user_input[CONF_TARGET])
        self.data.update(user_input)

        return await self.async_step_reconfigure_params()

    async def async_step_reconfigure_params(self, user_input: dict[str, any] = None) -> FlowResult:
        entry = self._get_reconfigure_entry()

        if user_input is None:
            schema_params = {
                vol.Required(CONF_PARAMETER, default=self.data.get(CONF_PARAMETER)):
                    await self._async_build_parameter_selector(),
            }

            if "::forecast" in str(self.data[CONF_QUERY_ID]):
                schema_params[vol.Required(
                    CONF_FORECAST_HOURS, default=self.data.get(CONF_FORECAST_HOURS, 36))] = cv.positive_int
                schema_params[vol.Required(
                    CONF_FORECAST_PAST_HOURS, default=self.data.get(CONF_FORECAST_PAST_HOURS, 5))] = cv.positive_int
                schema_params[vol.Required(
                    CONF_FORECAST_STEP, default=self.data.get(CONF_FORECAST_STEP, 30))] = cv.positive_int

            schema_params[vol.Required(
                CONF_NEGATIVE_AS_ZERO,
                default=self.data.get(CONF_NEGATIVE_AS_ZERO, False))] = cv.boolean

            self.param_schema = vol.Schema(schema_params)

            return self.async_show_form(step_id="reconfigure_params", data_schema=self.param_schema,
                                        last_step=True, description_placeholders=self._params_placeholders())

        errors = {}

        try:
            await validate_input(self.hass, {**self.data, **user_input})
        except ConnectionProblem:
            errors["base"] = "connection_problem"
        except Exception:
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            updated = {**self.data, **user_input}
            unique_id = build_unique_id(updated)
            clash = self.hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, unique_id)

            if clash is not None and clash.entry_id != entry.entry_id:
                return self.async_abort(reason="already_configured")

            return self.async_update_reload_and_abort(entry, data=updated, unique_id=unique_id)

        return self.async_show_form(step_id="reconfigure_params", data_schema=self.param_schema,
                                    last_step=True, errors=errors,
                                    description_placeholders=self._params_placeholders())

class ConnectionProblem(HomeAssistantError):
    """Error to indicate there is an issue with the connection"""
