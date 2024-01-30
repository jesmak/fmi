import logging
from datetime import datetime, timedelta
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback, HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import (DOMAIN, CONF_LABEL, CONF_LANG, CONF_QUERY_ID, CONF_QUERY_LABEL, CONF_FORECAST_HOURS, CONF_TARGET,
                    CONF_FORECAST_PAST_HOURS, CONF_FORECAST_STEP, LANGUAGES, CONF_PARAMETER, CONF_TARGET_TYPE,
                    TARGET_TYPES)
from .session import FMISession, FMIException

_LOGGER = logging.getLogger(__name__)

CONFIGURE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LANG): vol.All(cv.string, vol.In(LANGUAGES)),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, any]) -> str:
    try:
        now = datetime.utcnow()
        is_forecast = "::forecast" in str(data[CONF_QUERY_ID])
        start_time = now - timedelta(
            hours=data[CONF_FORECAST_PAST_HOURS]) if is_forecast is True else now - timedelta(hours=1)
        end_time = now + timedelta(hours=data[CONF_FORECAST_HOURS]) if is_forecast is True else now
        api = FMISession()
        params = {"starttime": start_time, "endtime": end_time, "timestep": data.get(CONF_FORECAST_STEP),
                  "storedquery_id": data[CONF_QUERY_ID], data[CONF_TARGET_TYPE]: data[CONF_TARGET],
                  "parameters": data[CONF_PARAMETER]}
        await hass.async_add_executor_job(api.get_feature, data[CONF_LANG], params, is_forecast is False)

    except FMIException:
        raise ConnectionProblem

    return data[CONF_LABEL]


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    data = None
    queries = None
    param_schema = None

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
                vol.Required(CONF_TARGET_TYPE): vol.All(cv.string, vol.In(TARGET_TYPES)),
                vol.Required(CONF_TARGET): cv.string,
            })

            return self.async_show_form(step_id="query", data_schema=schema, description_placeholders={
                "url": f"https://opendata.fmi.fi/wfs/{self.data[CONF_LANG]}?request=getFeature&storedquery_id=fmi::ef::stations"})

        user_input[CONF_QUERY_ID] = next(
            (query[0] for query in self.queries if str(user_input[CONF_QUERY_LABEL]).startswith(query[1])), None)
        self.data.update(user_input)

        return await self.async_step_params()

    async def async_step_params(self, user_input: dict[str, any] = None) -> FlowResult:

        if user_input is None:
            schema_params = {
                vol.Required(CONF_LABEL): cv.string,
                vol.Required(CONF_PARAMETER): cv.string
            }

            if "::forecast" in str(self.data[CONF_QUERY_ID]):
                schema_params[vol.Required(CONF_FORECAST_HOURS, default=36)] = cv.positive_int
                schema_params[vol.Required(CONF_FORECAST_PAST_HOURS, default=5)] = cv.positive_int
                schema_params[vol.Required(CONF_FORECAST_STEP, default=30)] = cv.positive_int

            self.param_schema = vol.Schema(schema_params)

            return self.async_show_form(step_id="params", data_schema=self.param_schema, last_step=True,
                                        description_placeholders={
                                            "url": f"https://opendata.fmi.fi/wfs/{self.data[CONF_LANG]}?request=getFeature&storedquery_id={self.data[CONF_QUERY_ID]}&starttime={(datetime.utcnow() - timedelta(hours=1)).strftime('%Y-%m-%d%%20%H:%M:%S')}&endtime={datetime.utcnow().strftime('%Y-%m-%d%%20%H:%M:%S')}&{self.data[CONF_TARGET_TYPE]}={self.data[CONF_TARGET]}",
                                            "param_url": f"https://opendata.fmi.fi/meta?observableProperty={'forecast' if '::forecast' in self.data[CONF_QUERY_ID] else 'observation'}&language={self.data[CONF_LANG]}",
                                        })

        await self.async_set_unique_id(f"fmi_{user_input[CONF_LABEL]}")
        self._abort_if_unique_id_configured()

        errors = {}

        try:
            all_data = self.data.copy()
            all_data.update(user_input)
            await validate_input(self.hass, all_data)
        except ConnectionProblem:
            errors["base"] = "connection_problem"
        except Exception:
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            self.data.update(user_input)
            return self.async_create_entry(title=self.data[CONF_LABEL], data=self.data)

        return self.async_show_form(step_id="params", data_schema=self.param_schema, last_step=True, errors=errors,
                                    description_placeholders={
                                        "url": f"https://opendata.fmi.fi/wfs/{self.data[CONF_LANG]}?request=getFeature&storedquery_id={self.data[CONF_QUERY_ID]}&starttime={(datetime.utcnow() - timedelta(hours=1)).strftime('%Y-%m-%d%%20%H:%M:%S')}&endtime={datetime.utcnow().strftime('%Y-%m-%d%%20%H:%M:%S')}&{self.data[CONF_TARGET_TYPE]}={self.data[CONF_TARGET]}",
                                        "param_url": f"https://opendata.fmi.fi/meta?observableProperty={'forecast' if '::forecast' in self.data[CONF_QUERY_ID] else 'observation'}&language={self.data[CONF_LANG]}",
                                    })

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry) if "::forecast" in config_entry.data[CONF_QUERY_ID] else None


class OptionsFlowHandler(config_entries.OptionsFlow):

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is None:
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_FORECAST_STEP,
                                     default=self._config_entry.data.get(CONF_FORECAST_STEP)): cv.positive_int,
                        vol.Required(CONF_FORECAST_HOURS,
                                     default=self._config_entry.data.get(CONF_FORECAST_HOURS)): cv.positive_int,
                        vol.Required(CONF_FORECAST_PAST_HOURS,
                                     default=self._config_entry.data.get(CONF_FORECAST_PAST_HOURS)): cv.positive_int,
                    })
            )

        user_input[CONF_LANG] = self._config_entry.data[CONF_LANG]
        user_input[CONF_QUERY_LABEL] = self._config_entry.data[CONF_QUERY_LABEL]
        user_input[CONF_QUERY_ID] = self._config_entry.data[CONF_QUERY_ID]
        user_input[CONF_PARAMETER] = self._config_entry.data[CONF_PARAMETER]
        user_input[CONF_TARGET] = self._config_entry.data[CONF_TARGET]
        user_input[CONF_TARGET_TYPE] = self._config_entry.data[CONF_TARGET_TYPE]
        user_input[CONF_LABEL] = self._config_entry.data[CONF_LABEL]

        self.hass.config_entries.async_update_entry(self._config_entry, data=user_input,
                                                    options=self._config_entry.options)
        return self.async_create_entry(title="", data={})


class ConnectionProblem(HomeAssistantError):
    """Error to indicate there is an issue with the connection"""
