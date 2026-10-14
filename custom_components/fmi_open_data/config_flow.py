"""Config flow.

The config entry holds the language, and its options the stale data settings
shared by every sensor. Sensors and warnings places are subentries, added and
changed from the integration page.
"""

import logging
import re
from datetime import timedelta
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, ConfigSubentryFlow, OptionsFlow, SubentryFlowResult
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    LocationSelector,
    LocationSelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance

from .const import (
    API_TIME_FORMAT,
    CONF_FORECAST_HOURS,
    CONF_FORECAST_PAST_HOURS,
    CONF_FORECAST_STEP,
    CONF_LABEL,
    CONF_LANG,
    CONF_LOCATION,
    CONF_NEGATIVE_AS_ZERO,
    CONF_NO_DATA_ISSUE,
    CONF_NO_DATA_ISSUE_HOURS,
    CONF_PARAMETER,
    CONF_QUERY_ID,
    CONF_QUERY_LABEL,
    CONF_TARGET,
    CONF_TARGET_TYPE,
    CONF_WARNING_TYPES,
    DEFAULT_NO_DATA_ISSUE,
    DEFAULT_NO_DATA_ISSUE_HOURS,
    DEFAULT_WARNINGS_LABEL,
    DEFAULT_WARNINGS_RADIUS,
    DOMAIN,
    LANGUAGES,
    SUBENTRY_SENSOR,
    SUBENTRY_WARNINGS,
    WARNING_TYPE_KEYS,
)
from .migration import TITLE, VERSION, moved_entry, old_entries
from .query_coordinator import build_unique_id, get_start_time, query_params
from .session import FMIException, FMISession
from .warning_coordinator import build_warnings_unique_id

_LOGGER = logging.getLogger(__name__)

STALE_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NO_DATA_ISSUE): cv.boolean,
        vol.Required(CONF_NO_DATA_ISSUE_HOURS): cv.positive_int,
    }
)

WARNINGS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LOCATION): LocationSelector(LocationSelectorConfig(radius=True, icon="mdi:alert")),
        vol.Required(CONF_WARNING_TYPES): SelectSelector(
            SelectSelectorConfig(
                options=list(WARNING_TYPE_KEYS.values()), multiple=True, translation_key=CONF_WARNING_TYPES, mode=SelectSelectorMode.LIST
            )
        ),
        vol.Required(CONF_LABEL): cv.string,
    }
)


def language_schema(default: str) -> vol.Schema:
    return vol.Schema({vol.Required(CONF_LANG, default=default): vol.All(cv.string, vol.In(LANGUAGES))})


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> str | None:
    """Read the sensor once as it would be read, and return the error to show, if any."""
    query_id = str(data[CONF_QUERY_ID])
    try:
        result = await hass.async_add_executor_job(
            FMISession().get_feature,
            data[CONF_LANG],
            query_params(data, dt_util.utcnow()),
            data[CONF_PARAMETER],
            "::forecast" not in query_id,
            data.get(CONF_NEGATIVE_AS_ZERO, False),
        )
    except FMIException:
        return "connection_problem"
    return None if result["data"] else "no_data"


def warning_types_from_form(data: dict[str, Any]) -> dict[str, Any]:
    """The form's lower-case warning type keys as FMI's warning types, which subentries store."""
    types_by_key = {key: warning_type for warning_type, key in WARNING_TYPE_KEYS.items()}
    return {**data, CONF_WARNING_TYPES: [types_by_key.get(key, key) for key in data.get(CONF_WARNING_TYPES) or []]}


def warning_types_for_form(data: dict[str, Any]) -> dict[str, Any]:
    """Stored warning types as the form's lower-case keys."""
    return {**data, CONF_WARNING_TYPES: [WARNING_TYPE_KEYS.get(t, t) for t in data.get(CONF_WARNING_TYPES) or []]}


def validate_warnings_input(data: dict[str, Any]) -> dict[str, str]:
    if not data.get(CONF_WARNING_TYPES):
        return {CONF_WARNING_TYPES: "no_warning_types"}
    return {}


def unique_id_taken(entry: ConfigEntry, unique_id: str, except_subentry_id: str | None = None) -> bool:
    return any(subentry.unique_id == unique_id and subentry.subentry_id != except_subentry_id for subentry in entry.subentries.values())


class FMIConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = VERSION

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:

        if user_input is not None:
            return self.async_create_entry(
                title=TITLE,
                data=user_input,
                options={CONF_NO_DATA_ISSUE: DEFAULT_NO_DATA_ISSUE, CONF_NO_DATA_ISSUE_HOURS: DEFAULT_NO_DATA_ISSUE_HOURS},
            )

        if old_entries(self.hass):
            return await self.async_step_old_setup()
        return await self.async_step_new()

    async def async_step_old_setup(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The old `fmi` domain has a setup of this integration: move it, or set up a new one beside it."""
        return self.async_show_menu(step_id="old_setup", menu_options=["move", "new"])

    async def async_step_move(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Take over the setup of the old `fmi` domain. The new entry's setup moves the entities."""
        entries = old_entries(self.hass)
        if not entries:
            return await self.async_step_new()
        data, options, subentries = moved_entry(entries)
        return self.async_create_entry(title=TITLE, data=data, options=options, subentries=subentries)

    async def async_step_new(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """A new setup, beside the old one if there is one. The form is submitted to the user step."""
        default = "fin" if self.hass.config.language.startswith("fi") else "eng"
        return self.async_show_form(step_id="user", data_schema=language_schema(default))

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the default language for new sensors and warnings places."""
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            # The entry's update listener reloads it.
            self.hass.config_entries.async_update_entry(entry, data={**entry.data, **user_input})
            return self.async_abort(reason="reconfigure_successful")

        return self.async_show_form(step_id="reconfigure", data_schema=language_schema(entry.data[CONF_LANG]))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return StaleDataOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_SENSOR: SensorSubentryFlow, SUBENTRY_WARNINGS: WarningsSubentryFlow}


class StaleDataOptionsFlow(OptionsFlow):
    """When data counts as stale, and whether a repair issue is raised. Shared by every sensor."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:

        if user_input is not None:
            return self.async_create_entry(data=user_input)

        values = {
            CONF_NO_DATA_ISSUE: DEFAULT_NO_DATA_ISSUE,
            CONF_NO_DATA_ISSUE_HOURS: DEFAULT_NO_DATA_ISSUE_HOURS,
            **self.config_entry.options,
        }
        return self.async_show_form(step_id="init", data_schema=self.add_suggested_values_to_schema(STALE_DATA_SCHEMA, values))


class SensorSubentryFlow(ConfigSubentryFlow):
    """One parameter of one query at one station or forecast point."""

    def __init__(self):
        self.data: dict[str, Any] = {}
        self.queries: list[list[str]] | None = None
        self.param_schema: vol.Schema | None = None
        self.stations: list[dict[str, Any]] | None = None
        self.descriptions: dict[str, tuple[str, str]] | None = None

    async def _async_stations_for_query(self) -> list[dict[str, Any]]:
        """Stations that serve the chosen query, or all of them as a fallback.

        Forecast queries are interpolated to a point rather than tied to a
        station, so they have no station list of their own.
        """
        lang = self.data[CONF_LANG]
        query_id = str(self.data[CONF_QUERY_ID])
        api = FMISession()
        now = dt_util.utcnow()
        start_time = get_start_time(query_id, now, {CONF_FORECAST_PAST_HOURS: 1})
        params = {
            "starttime": start_time.strftime(API_TIME_FORMAT) if start_time is not None else None,
            "endtime": now.strftime(API_TIME_FORMAT),
        }

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

        def distance_to_home(station: dict[str, Any]) -> float:
            if station["latitude"] is None or station["longitude"] is None:
                return float("inf")
            metres = distance(self.hass.config.latitude, self.hass.config.longitude, station["latitude"], station["longitude"])
            return float("inf") if metres is None else metres

        options = []
        for station in sorted(stations, key=distance_to_home):
            label = station["name"]
            if station["region"] and station["region"] not in label:
                label = f"{label}, {station['region']}"
            away = distance_to_home(station)
            suffix = "" if away == float("inf") else f" - {round(away / 1000)} km"
            options.append(SelectOptionDict(value=station["id"], label=f"{label} ({station['id']}){suffix}"))

        return SelectSelector(SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN, custom_value=True, sort=False))

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

        params = {
            "starttime": start_time.strftime(API_TIME_FORMAT) if start_time is not None else None,
            "endtime": end_time.strftime(API_TIME_FORMAT) if end_time is not None else None,
            "storedquery_id": query_id,
            self.data[CONF_TARGET_TYPE]: self.data[CONF_TARGET],
        }

        api = FMISession()

        try:
            names = await self.hass.async_add_executor_job(api.list_parameters, self.data[CONF_LANG], params)
        except Exception as exception:  # noqa: BLE001 - degrade to a text field, never break the flow
            _LOGGER.warning(f"Could not list parameters for {query_id}: {exception}")
            return cv.string

        if not names:
            return cv.string

        try:
            self.descriptions = descriptions = await self.hass.async_add_executor_job(
                api.get_parameter_descriptions, self.data[CONF_LANG], query_id
            )
        except Exception:  # noqa: BLE001 - labels are cosmetic, fall back to bare names
            self.descriptions = descriptions = {}

        options = []
        for name in names:
            label, unit = descriptions.get(name.lower(), (None, None))
            text = name if label is None else f"{name} - {label}"
            options.append(SelectOptionDict(value=name, label=text if unit is None else f"{text} ({unit})"))

        # custom_value keeps a parameter that the probe window happened to miss reachable.
        return SelectSelector(SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN, custom_value=True, sort=False))

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

    async def _async_query_form(self, step_id: str, current: str | None = None) -> SubentryFlowResult:
        try:
            self.queries = await self.hass.async_add_executor_job(FMISession().list_stored_queries, self.data[CONF_LANG], "::simple")
        except FMIException as exception:
            _LOGGER.warning(f"Could not list FMI's queries: {exception}")
            return self.async_abort(reason="cannot_connect")
        choices = [f"{query[1]} ({query[0]})" for query in self.queries]
        default = next((choice for choice, query in zip(choices, self.queries, strict=True) if query[0] == current), None)
        schema = vol.Schema(
            {
                vol.Required(CONF_QUERY_LABEL, **({"default": default} if default else {})): vol.All(cv.string, vol.In(choices)),
            }
        )
        return self.async_show_form(step_id=step_id, data_schema=schema)

    def _choose_query(self, user_input: dict[str, Any]) -> None:
        query_id = next((query[0] for query in self.queries if str(user_input[CONF_QUERY_LABEL]) == f"{query[1]} ({query[0]})"), None)
        self.data.update(user_input, **{CONF_QUERY_ID: query_id})
        if "::forecast" not in str(query_id):
            # Left over when an existing forecast sensor is changed to read observations.
            for key in (CONF_FORECAST_HOURS, CONF_FORECAST_PAST_HOURS, CONF_FORECAST_STEP):
                self.data.pop(key, None)

    def _params_schema(self, parameter_selector, values: dict[str, Any]) -> vol.Schema:
        schema_params = {
            vol.Required(CONF_PARAMETER, **({"default": values[CONF_PARAMETER]} if values.get(CONF_PARAMETER) else {})): parameter_selector,
            vol.Required(CONF_NEGATIVE_AS_ZERO, default=values.get(CONF_NEGATIVE_AS_ZERO, False)): cv.boolean,
        }

        if "::forecast" in str(self.data[CONF_QUERY_ID]):
            schema_params[vol.Required(CONF_FORECAST_HOURS, default=values.get(CONF_FORECAST_HOURS, 36))] = cv.positive_int
            schema_params[vol.Required(CONF_FORECAST_PAST_HOURS, default=values.get(CONF_FORECAST_PAST_HOURS, 5))] = cv.positive_int
            schema_params[vol.Required(CONF_FORECAST_STEP, default=values.get(CONF_FORECAST_STEP, 30))] = cv.positive_int

        return vol.Schema(schema_params)

    async def _async_validated(self, user_input: dict[str, Any]) -> dict[str, str]:
        """Errors from test-reading the sensor with the chosen settings; empty when it works."""
        try:
            error = await validate_input(self.hass, {**self.data, **user_input})
        except Exception:
            _LOGGER.exception("Unexpected exception")
            error = "unknown"
        return {"base": error} if error else {}

    # ---------------- adding a sensor ----------------

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Choose the query. The language comes from the integration's settings."""
        if not self.data:
            self.data = {CONF_LANG: self._get_entry().data[CONF_LANG]}

        if user_input is None:
            return await self._async_query_form("user")

        self._choose_query(user_input)

        return await self.async_step_location()

    async def async_step_location(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:

        if user_input is None:
            schema = vol.Schema({vol.Required(CONF_TARGET): await self._async_build_target_selector()})
            return self.async_show_form(step_id="location", data_schema=schema)

        user_input[CONF_TARGET_TYPE] = self._target_type_for(user_input[CONF_TARGET])
        self.data.update(user_input)

        return await self.async_step_params()

    async def async_step_params(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:

        if user_input is None:
            self.param_schema = self._params_schema(await self._async_build_parameter_selector(), {})
            return self.async_show_form(
                step_id="params", data_schema=self.param_schema, description_placeholders=self._params_placeholders()
            )

        errors = await self._async_validated(user_input)

        if not errors:
            self.data.update(user_input)
            if unique_id_taken(self._get_entry(), build_unique_id(self.data)):
                return self.async_abort(reason="already_configured")
            return await self.async_step_name()

        return self.async_show_form(
            step_id="params", data_schema=self.param_schema, errors=errors, description_placeholders=self._params_placeholders()
        )

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

    async def async_step_name(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:

        if user_input is None:
            schema = vol.Schema({vol.Required(CONF_LABEL, default=self._default_label()): cv.string})
            return self.async_show_form(step_id="name", data_schema=schema, last_step=True)

        self.data.update(user_input)

        return self.async_create_entry(title=self.data[CONF_LABEL], data=self.data, unique_id=build_unique_id(self.data))

    # ---------------- changing a sensor ----------------

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Repoint an existing sensor at a different station, query or parameter.

        The name is not editable here: renaming is a plain entity rename and
        needs no flow of its own.
        """
        subentry = self._get_reconfigure_subentry()

        if user_input is None:
            self.data = dict(subentry.data)
            return await self._async_query_form("reconfigure", self.data.get(CONF_QUERY_ID))

        self._choose_query(user_input)

        return await self.async_step_reconfigure_location()

    async def async_step_reconfigure_location(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:

        if user_input is None:
            schema = vol.Schema(
                {
                    vol.Required(CONF_TARGET, default=self.data.get(CONF_TARGET)): await self._async_build_target_selector(),
                }
            )
            return self.async_show_form(step_id="reconfigure_location", data_schema=schema)

        user_input[CONF_TARGET_TYPE] = self._target_type_for(user_input[CONF_TARGET])
        self.data.update(user_input)

        return await self.async_step_reconfigure_params()

    async def async_step_reconfigure_params(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()

        if user_input is None:
            self.param_schema = self._params_schema(await self._async_build_parameter_selector(), self.data)
            return self.async_show_form(
                step_id="reconfigure_params",
                data_schema=self.param_schema,
                last_step=True,
                description_placeholders=self._params_placeholders(),
            )

        errors = await self._async_validated(user_input)

        if not errors:
            updated = {**self.data, **user_input}
            unique_id = build_unique_id(updated)

            if unique_id_taken(self._get_entry(), unique_id, except_subentry_id=subentry.subentry_id):
                return self.async_abort(reason="already_configured")

            return self.async_update_and_abort(self._get_entry(), subentry, data=updated, unique_id=unique_id)

        return self.async_show_form(
            step_id="reconfigure_params",
            data_schema=self.param_schema,
            last_step=True,
            errors=errors,
            description_placeholders=self._params_placeholders(),
        )


class WarningsSubentryFlow(ConfigSubentryFlow):
    """FMI's weather warnings for a place picked on a map."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        entry = self._get_entry()
        errors = {}

        if user_input is not None:
            errors = validate_warnings_input(user_input)

            if not errors:
                data = {**warning_types_from_form(user_input), CONF_LANG: entry.data[CONF_LANG]}
                unique_id = build_warnings_unique_id(data)
                if unique_id_taken(entry, unique_id):
                    return self.async_abort(reason="already_configured")
                return self.async_create_entry(title=data[CONF_LABEL], data=data, unique_id=unique_id)

        language = entry.data[CONF_LANG]
        values = user_input or {
            CONF_LOCATION: {
                "latitude": self.hass.config.latitude,
                "longitude": self.hass.config.longitude,
                "radius": DEFAULT_WARNINGS_RADIUS,
            },
            CONF_WARNING_TYPES: list(WARNING_TYPE_KEYS.values()),
            CONF_LABEL: DEFAULT_WARNINGS_LABEL.get(language, DEFAULT_WARNINGS_LABEL["eng"]),
        }

        return self.async_show_form(step_id="user", data_schema=self.add_suggested_values_to_schema(WARNINGS_SCHEMA, values), errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Move the place, or change its radius, warning types or name."""
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        errors = {}

        if user_input is not None:
            errors = validate_warnings_input(user_input)

            if not errors:
                updated = {**subentry.data, **warning_types_from_form(user_input)}
                unique_id = build_warnings_unique_id(updated)

                if unique_id_taken(entry, unique_id, except_subentry_id=subentry.subentry_id):
                    return self.async_abort(reason="already_configured")

                return self.async_update_and_abort(entry, subentry, title=updated[CONF_LABEL], data=updated, unique_id=unique_id)

        values = user_input or warning_types_for_form(dict(subentry.data))
        return self.async_show_form(
            step_id="reconfigure", data_schema=self.add_suggested_values_to_schema(WARNINGS_SCHEMA, values), errors=errors
        )
