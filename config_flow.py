import logging
from datetime import datetime, timedelta

import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from .const import (DOMAIN, CONF_STEP, CONF_SENSOR_TYPE, SENSOR_TYPES, CONF_FMISID, SENSOR_CONFIGS, CONF_LABEL,
                    CONF_FORECAST_HOURS, CONF_FORECAST_PAST_HOURS)
from .session import FMIException, FMISession

_LOGGER = logging.getLogger(__name__)

CONFIGURE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LABEL): cv.string,
        vol.Required(CONF_SENSOR_TYPE): vol.All(cv.string, vol.In(SENSOR_TYPES)),
        vol.Required(CONF_FMISID): cv.positive_int,
    }
)

CONFIGURE_FORECAST_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_STEP, default=30): cv.positive_int,
        vol.Required(CONF_FORECAST_HOURS, default=48): cv.positive_int,
        vol.Required(CONF_FORECAST_PAST_HOURS, default=5): cv.positive_int,
    }
)

RECONFIGURE_FORECAST_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_STEP): cv.positive_int,
        vol.Required(CONF_FORECAST_HOURS): cv.positive_int,
        vol.Required(CONF_FORECAST_PAST_HOURS): cv.positive_int,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, any]) -> str:
    try:
        session = FMISession(data[CONF_FMISID], 0)
        now = datetime.utcnow()
        conf = next((conf for conf in SENSOR_CONFIGS if conf["id"] == data[CONF_SENSOR_TYPE]), None)
        start_time = now - timedelta(hours=5) if conf["is_forecast"] is True else now - timedelta(hours=1)
        end_time = now + timedelta(hours=36) if conf["is_forecast"] is True else now
        await hass.async_add_executor_job(session.query, conf, start_time, end_time)

    except FMIException:
        raise ConnectionProblem

    return data[CONF_LABEL]


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    data = None

    async def async_step_user(self, user_input: dict[str, any] = None) -> FlowResult:

        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=CONFIGURE_SCHEMA)

        await self.async_set_unique_id(
            f"fmi_{user_input[CONF_FMISID]}_{user_input[CONF_SENSOR_TYPE]}")
        self._abort_if_unique_id_configured()

        errors = {}

        try:
            info = await validate_input(self.hass, user_input)
        except ConnectionProblem:
            errors["base"] = "connection_problem"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            self.data = user_input
            conf = next((conf for conf in SENSOR_CONFIGS if conf["id"] == user_input[CONF_SENSOR_TYPE]), None)
            return await self.async_step_forecast() if conf["is_forecast"] is True else self.async_create_entry(
                title=info, data=user_input)

        return self.async_show_form(step_id="user", data_schema=CONFIGURE_SCHEMA, errors=errors)

    async def async_step_forecast(self, user_input: dict[str, any] = None) -> FlowResult:

        if user_input is None:
            return self.async_show_form(step_id="forecast", data_schema=CONFIGURE_FORECAST_SCHEMA)

        self.data.update(user_input)

        return self.async_create_entry(title=self.data[CONF_LABEL], data=self.data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        conf = next((conf for conf in SENSOR_CONFIGS if conf["id"] == config_entry.data[CONF_SENSOR_TYPE]), None)
        return OptionsFlowHandler(config_entry) if conf["is_forecast"] else None


class OptionsFlowHandler(config_entries.OptionsFlow):

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, any] = None) -> FlowResult:
        if user_input is None:
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_STEP, default=self._config_entry.data.get(CONF_STEP)): cv.positive_int,
                        vol.Required(CONF_FORECAST_HOURS,
                                     default=self._config_entry.data.get(CONF_FORECAST_HOURS)): cv.positive_int,
                        vol.Required(CONF_FORECAST_PAST_HOURS,
                                     default=self._config_entry.data.get(CONF_FORECAST_PAST_HOURS)): cv.positive_int,
                    })
            )

        errors = {}

        try:
            user_input[CONF_SENSOR_TYPE] = self._config_entry.data[CONF_SENSOR_TYPE]
            user_input[CONF_FMISID] = self._config_entry.data[CONF_FMISID]
            user_input[CONF_LABEL] = self._config_entry.data[CONF_LABEL]
            await validate_input(self.hass, user_input)
        except ConnectionProblem:
            errors["base"] = "connection_problem"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            self.hass.config_entries.async_update_entry(self._config_entry, data=user_input,
                                                        options=self._config_entry.options)
            return self.async_create_entry(title="", data={})

        return self.async_show_form(step_id="init", data_schema=RECONFIGURE_FORECAST_SCHEMA, errors=errors)


class ConnectionProblem(HomeAssistantError):
    """Error to indicate there is an issue with the connection"""
