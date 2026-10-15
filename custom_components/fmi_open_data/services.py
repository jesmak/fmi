"""The get_observations action: one station's observations over a time range, straight from FMI."""

from datetime import datetime, timedelta
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util

from .const import API_TIME_FORMAT, CONF_LANG, DOMAIN
from .session import FMIException, FMINoData, FMIRefused, FMISession

SERVICE_GET_OBSERVATIONS = "get_observations"

ATTR_QUERY = "query"
ATTR_STATION = "station"
ATTR_PARAMETERS = "parameters"
ATTR_START = "start"
ATTR_END = "end"
ATTR_TIMESTEP = "timestep"

FORMATS = ("::multipointcoverage", "::simple", "::timevaluepair")

# The values go into FMI's URL as they are, so anything that would change its meaning (&, #, %) is refused.
GET_OBSERVATIONS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_QUERY): vol.All(cv.string, vol.Match(r"^\s*[\w-]+(::[\w-]+)+\s*$")),
        vol.Required(ATTR_STATION): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Required(ATTR_PARAMETERS): vol.All(cv.ensure_list, [vol.All(cv.string, vol.Match(r"^[\w.-]+$"))], vol.Length(min=1)),
        vol.Optional(ATTR_START): cv.datetime,
        vol.Optional(ATTR_END): cv.datetime,
        vol.Optional(ATTR_TIMESTEP): vol.All(vol.Coerce(int), vol.Range(min=1)),
    }
)


def _aware(value: datetime) -> datetime:
    """A time without a zone is Home Assistant's local time."""
    return value if value.tzinfo is not None else value.replace(tzinfo=dt_util.get_default_time_zone())


def _query_id(query: str) -> str:
    query = query.strip()
    for suffix in FORMATS:
        query = query.removesuffix(suffix)
    if "::observations::" not in query:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="not_an_observation_query", translation_placeholders={"query": query}
        )
    return f"{query}::multipointcoverage"


def async_setup_services(hass: HomeAssistant) -> None:
    async def async_get_observations(call: ServiceCall) -> ServiceResponse:
        entries = [entry for entry in hass.config_entries.async_entries(DOMAIN) if entry.state is ConfigEntryState.LOADED]
        if not entries:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_loaded")

        query_id = _query_id(call.data[ATTR_QUERY])
        end = _aware(call.data[ATTR_END]) if ATTR_END in call.data else dt_util.utcnow()
        start = _aware(call.data[ATTR_START]) if ATTR_START in call.data else end - timedelta(hours=24)
        if start >= end:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="start_after_end")

        params: dict[str, Any] = {
            "storedquery_id": query_id,
            "fmisid": call.data[ATTR_STATION],
            "parameters": ",".join(call.data[ATTR_PARAMETERS]),
            "starttime": dt_util.as_utc(start).strftime(API_TIME_FORMAT),
            "endtime": dt_util.as_utc(end).strftime(API_TIME_FORMAT),
            "timestep": call.data.get(ATTR_TIMESTEP),
        }
        try:
            station, rows = await hass.async_add_executor_job(FMISession().get_observations, entries[0].data[CONF_LANG], params)
        except FMINoData as exception:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_observations") from exception
        except FMIRefused as exception:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="refused", translation_placeholders={"message": str(exception)}
            ) from exception
        except FMIException as exception:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="connection_problem") from exception

        return {
            "query": query_id.removesuffix("::multipointcoverage"),
            # A range with no observations has no station in the response either.
            "station": {"fmisid": call.data[ATTR_STATION], **(station or {})},
            "observations": [{**row, "time": row["time"].isoformat()} for row in rows],
        }

    hass.services.async_register(
        DOMAIN, SERVICE_GET_OBSERVATIONS, async_get_observations, schema=GET_OBSERVATIONS_SCHEMA, supports_response=SupportsResponse.ONLY
    )
