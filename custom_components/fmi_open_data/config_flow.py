"""Config flow.

The config entry holds the language, and its options the stale data settings shared by every measurement.
Stations and places are subentries, added and changed from the integration page.

Adding measurements starts from what to measure: every parameter FMI's station queries have, in one searchable list.
Then a station for each one, offering only the stations that reported it, nearest first. Each measurement goes to
its station's subentry, an existing one or a new one, so one run can add to several stations.
"""

import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentry,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
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

from .catalogue import KIND_PLACE, KIND_POINT, KIND_STATIONS, Catalogue, Parameter, async_catalogue, distance_km
from .const import (
    CONF_FORECAST_HOURS,
    CONF_FORECAST_PAST_HOURS,
    CONF_FORECAST_STEP,
    CONF_LABEL,
    CONF_LANG,
    CONF_LOCATION,
    CONF_MEASUREMENTS,
    CONF_NEGATIVE_AS_ZERO,
    CONF_NO_DATA_ISSUE,
    CONF_NO_DATA_ISSUE_HOURS,
    CONF_PARAMETER,
    CONF_QUERY_ID,
    CONF_TARGET,
    CONF_TARGET_TYPE,
    CONF_UNIT,
    CONF_WARNING_TYPES,
    CONF_WEATHER,
    DEFAULT_NO_DATA_ISSUE,
    DEFAULT_NO_DATA_ISSUE_HOURS,
    DEFAULT_WARNINGS_RADIUS,
    DOMAIN,
    LANGUAGES,
    SUBENTRY_PLACE,
    SUBENTRY_STATION,
    WARNING_TYPE_KEYS,
)
from .migration import TITLE, VERSION, moved_entry, old_entries
from .query_coordinator import measurement_key, measurement_name, query_params, station_unique_id
from .session import FMIException, FMINoData, FMISession
from .structure import place_unique_id
from .weather_coordinator import async_get_forecast

_LOGGER = logging.getLogger(__name__)

CONF_PARAMETERS = "parameters"
CONF_STATION = "station"
CONF_SHOW_ALL = "show_all"
CONF_POINT = "point"
CONF_PLACE_NAME = "place_name"
CONF_PLACE = "place"
CONF_MEASUREMENT = "measurement"

# A forecast measurement's settings until the user changes them.
FORECAST_DEFAULTS = {CONF_FORECAST_HOURS: 36, CONF_FORECAST_PAST_HOURS: 5, CONF_FORECAST_STEP: 30}

STALE_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NO_DATA_ISSUE): cv.boolean,
        vol.Required(CONF_NO_DATA_ISSUE_HOURS): cv.positive_int,
    }
)

PLACE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LOCATION): LocationSelector(LocationSelectorConfig(radius=True, icon="mdi:map-marker")),
        vol.Required(CONF_LABEL): cv.string,
        vol.Required(CONF_WEATHER): cv.boolean,
        vol.Optional(CONF_WARNING_TYPES): SelectSelector(
            SelectSelectorConfig(
                options=list(WARNING_TYPE_KEYS.values()), multiple=True, translation_key=CONF_WARNING_TYPES, mode=SelectSelectorMode.LIST
            )
        ),
    }
)


def language_schema(default: str) -> vol.Schema:
    return vol.Schema({vol.Required(CONF_LANG, default=default): vol.All(cv.string, vol.In(LANGUAGES))})


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> str | None:
    """Read a measurement once as it would be read, and return the error to show, if any."""
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


def unique_id_taken(entry: ConfigEntry, unique_id: str, except_subentry_id: str | None = None) -> bool:
    return any(subentry.unique_id == unique_id and subentry.subentry_id != except_subentry_id for subentry in entry.subentries.values())


def new_measurement(parameter: Parameter, label: str) -> dict[str, Any]:
    measurement = {CONF_QUERY_ID: parameter.query_id, CONF_PARAMETER: parameter.name, CONF_LABEL: label, CONF_NEGATIVE_AS_ZERO: False}
    return {**measurement, **FORECAST_DEFAULTS} if "::forecast" in parameter.query_id else measurement


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
        """Change the language of FMI's texts."""
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
        return {SUBENTRY_STATION: StationSubentryFlow, SUBENTRY_PLACE: PlaceSubentryFlow}


class StaleDataOptionsFlow(OptionsFlow):
    """When data counts as stale, and whether a repair issue is raised. Shared by every measurement."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:

        if user_input is not None:
            return self.async_create_entry(data=user_input)

        values = {
            CONF_NO_DATA_ISSUE: DEFAULT_NO_DATA_ISSUE,
            CONF_NO_DATA_ISSUE_HOURS: DEFAULT_NO_DATA_ISSUE_HOURS,
            **self.config_entry.options,
        }
        return self.async_show_form(step_id="init", data_schema=self.add_suggested_values_to_schema(STALE_DATA_SCHEMA, values))


class StationSubentryFlow(ConfigSubentryFlow):
    """Measurements at stations: added from what to measure, and changed one station at a time."""

    def __init__(self):
        self.catalogue: Catalogue | None = None
        # The parameters chosen, and for each the station it is read at: (target type, target, station's name).
        self.chosen: list[Parameter] = []
        self.targets: list[tuple[str, str, str]] = []
        self.show_all = False
        # When adding to one station from its own reconfigure, the station is not asked.
        self.fixed_target: tuple[str, str, str] | None = None
        # The measurement whose settings are being changed.
        self.key: str | None = None

    @property
    def _lang(self) -> str:
        return self._get_entry().data[CONF_LANG]

    async def _async_catalogue(self) -> Catalogue | None:
        if self.catalogue is None:
            try:
                self.catalogue = await async_catalogue(self.hass, self._lang)
            except FMIException as exception:
                _LOGGER.warning(f"Could not read FMI's queries: {exception}")
        return self.catalogue

    def _parameters_form(self, parameters: list[Parameter], step_id: str, errors: dict[str, str] | None = None) -> SubentryFlowResult:
        options = [SelectOptionDict(value=parameter.value, label=parameter.label) for parameter in parameters]
        # An empty default, as Home Assistant would otherwise choose the first parameter for the user.
        schema = vol.Schema(
            {
                vol.Required(CONF_PARAMETERS, default=[]): SelectSelector(
                    SelectSelectorConfig(options=options, multiple=True, mode=SelectSelectorMode.DROPDOWN, sort=False)
                )
            }
        )
        return self.async_show_form(step_id=step_id, data_schema=schema, errors=errors or {})

    def _choose(self, user_input: dict[str, Any]) -> bool:
        self.chosen = [
            self.catalogue.parameters[value] for value in user_input.get(CONF_PARAMETERS) or [] if value in self.catalogue.parameters
        ]
        self.targets = []
        return bool(self.chosen)

    # ---------------- adding measurements ----------------

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """What to measure."""
        if await self._async_catalogue() is None:
            return self.async_abort(reason="cannot_connect")

        if user_input is not None:
            if self._choose(user_input):
                return await self._async_next_target()
            return self._parameters_form(list(self.catalogue.parameters.values()), "user", {"base": "no_parameters"})

        return self._parameters_form(list(self.catalogue.parameters.values()), "user")

    async def _async_next_target(self) -> SubentryFlowResult:
        if len(self.targets) == len(self.chosen):
            return await self.async_step_names()
        if self.fixed_target is not None:
            self.targets.append(self.fixed_target)
            return await self._async_next_target()
        parameter = self.chosen[len(self.targets)]
        # A parameter no station has reported lately, such as wave height while the buoys are ashore for the winter,
        # starts from every station of its query.
        self.show_all = not parameter.stations
        kind = parameter.kind
        if kind == KIND_STATIONS:
            return await self.async_step_station()
        if kind == KIND_POINT:
            return await self.async_step_point()
        return await self.async_step_named_place()

    def _placeholders(self) -> dict[str, str]:
        return {CONF_MEASUREMENT: self.chosen[len(self.targets)].label}

    async def async_step_station(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """The station for one parameter: those that reported it, nearest first, or every station of the query."""
        parameter = self.chosen[len(self.targets)]

        if user_input is not None and bool(user_input.get(CONF_SHOW_ALL)) == self.show_all:
            station = next(item for item in self.catalogue.stations[parameter.query_id] if item["id"] == user_input[CONF_STATION])
            self.targets.append((station["target_type"], station["id"], station["name"]))
            return await self._async_next_target()
        if user_input is not None:
            self.show_all = bool(user_input.get(CONF_SHOW_ALL))

        stations = self.catalogue.stations[parameter.query_id] if self.show_all else parameter.stations
        options = [
            SelectOptionDict(value=item["id"], label=f"{item['name']} · {round(distance_km(self.hass, item))} km") for item in stations
        ]
        # The station chosen for the previous parameter, when it has this one too, else the nearest.
        previous = next((target for target_type, target, _ in reversed(self.targets) if target_type in ("fmisid", "geoid")), None)
        default = previous if any(option["value"] == previous for option in options) else (options[0]["value"] if options else None)
        schema = vol.Schema(
            {
                vol.Required(CONF_STATION, **({"default": default} if default else {})): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN, sort=False)
                ),
                vol.Required(CONF_SHOW_ALL, default=self.show_all): cv.boolean,
            }
        )
        return self.async_show_form(step_id="station", data_schema=schema, description_placeholders=self._placeholders())

    async def async_step_point(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """The point for a forecast, and what to call it."""
        parameter = self.chosen[len(self.targets)]
        errors = {}

        if user_input is not None:
            point = user_input[CONF_POINT]
            target = f"{float(point['latitude']):.4f},{float(point['longitude']):.4f}"
            errors = await self._async_try(parameter, "latlon", target)
            if not errors:
                self.targets.append(("latlon", target, user_input[CONF_PLACE_NAME]))
                return await self._async_next_target()

        values = user_input or {
            CONF_POINT: {"latitude": self.hass.config.latitude, "longitude": self.hass.config.longitude},
            CONF_PLACE_NAME: self.hass.config.location_name,
        }
        schema = vol.Schema(
            {
                vol.Required(CONF_POINT): LocationSelector(LocationSelectorConfig(radius=False, icon="mdi:crosshairs-gps")),
                vol.Required(CONF_PLACE_NAME): cv.string,
            }
        )
        return self.async_show_form(
            step_id="point",
            data_schema=self.add_suggested_values_to_schema(schema, values),
            errors=errors,
            description_placeholders=self._placeholders(),
        )

    async def async_step_named_place(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """A place name, for a query that has parameters but no stations."""
        parameter = self.chosen[len(self.targets)]
        errors = {}

        if user_input is not None:
            place = user_input[CONF_PLACE].strip()
            errors = await self._async_try(parameter, "place", place)
            if not errors:
                self.targets.append(("place", place, place))
                return await self._async_next_target()

        schema = vol.Schema({vol.Required(CONF_PLACE): cv.string})
        return self.async_show_form(
            step_id="named_place",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or {}),
            errors=errors,
            description_placeholders=self._placeholders(),
        )

    async def _async_try(self, parameter: Parameter, target_type: str, target: str) -> dict[str, str]:
        """Read the parameter once at a place the user typed or picked, so that a typo shows here."""
        data = {CONF_LANG: self._lang, CONF_TARGET_TYPE: target_type, CONF_TARGET: target, **new_measurement(parameter, "")}
        error = await validate_input(self.hass, data)
        return {"base": error} if error else {}

    async def async_step_names(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """A name for each measurement, prefilled by the rules. The field says where it is read and what."""
        fields: list[tuple[str, Parameter, tuple[str, str, str]]] = []
        for parameter, target in zip(self.chosen, self.targets, strict=True):
            field = f"{target[2]} · {parameter.description or parameter.name}"
            while any(existing == field for existing, _, _ in fields):
                field += " ·"
            fields.append((field, parameter, target))

        if user_input is None:
            schema = vol.Schema({vol.Required(field, default=self._default_name(parameter)): cv.string for field, parameter, _ in fields})
            return self.async_show_form(step_id="names", data_schema=schema, last_step=True)

        measurements = [(target, new_measurement(parameter, user_input[field].strip())) for field, parameter, target in fields]
        if self.fixed_target is not None:
            return self._update_station(self._get_reconfigure_subentry(), [measurement for _, measurement in measurements])
        return self._add_to_stations(measurements)

    def _default_name(self, parameter: Parameter) -> str:
        descriptions = {parameter.name.lower(): (parameter.description, None)}
        return measurement_name(descriptions, self._lang, parameter.query_id, parameter.name)

    def _add_to_stations(self, measurements: list[tuple[tuple[str, str, str], dict[str, Any]]]) -> SubentryFlowResult:
        """Each measurement to its station: added to the station's subentry, or a new subentry for a new station."""
        entry = self._get_entry()
        by_station: dict[str, tuple[tuple[str, str, str], list[dict[str, Any]]]] = {}
        for target, measurement in measurements:
            by_station.setdefault(station_unique_id(target[0], target[1]), (target, []))[1].append(measurement)

        added = []
        for unique_id, ((target_type, target, title), new) in by_station.items():
            existing = next((subentry for subentry in entry.subentries.values() if subentry.unique_id == unique_id), None)
            have = {measurement_key(measurement) for measurement in existing.data[CONF_MEASUREMENTS]} if existing else set()
            new = [measurement for measurement in new if measurement_key(measurement) not in have]
            if not new:
                continue
            if existing is None:
                data = {CONF_TARGET_TYPE: target_type, CONF_TARGET: target, CONF_MEASUREMENTS: new}
                self.hass.config_entries.async_add_subentry(
                    entry, ConfigSubentry(data=data, subentry_type=SUBENTRY_STATION, title=title, unique_id=unique_id)
                )
            else:
                data = {**existing.data, CONF_MEASUREMENTS: [*existing.data[CONF_MEASUREMENTS], *new]}
                self.hass.config_entries.async_update_subentry(entry, existing, data=data)
            added.append(f"{title} ({len(new)})")

        if not added:
            return self.async_abort(reason="already_configured")
        return self.async_abort(reason="measurements_added", description_placeholders={"stations": ", ".join(added)})

    def _update_station(self, subentry: ConfigSubentry, new: list[dict[str, Any]]) -> SubentryFlowResult:
        have = {measurement_key(measurement) for measurement in subentry.data[CONF_MEASUREMENTS]}
        new = [measurement for measurement in new if measurement_key(measurement) not in have]
        if not new:
            return self.async_abort(reason="already_configured")
        data = {**subentry.data, CONF_MEASUREMENTS: [*subentry.data[CONF_MEASUREMENTS], *new]}
        return self.async_update_and_abort(self._get_entry(), subentry, data=data, reason="reconfigure_successful")

    # ---------------- changing a station ----------------

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Add measurements, change one's settings or remove some. The station itself is not changed."""
        return self.async_show_menu(step_id="reconfigure", menu_options=["add_measurements", "measurement", "remove_measurements"])

    async def async_step_add_measurements(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """What else to measure at this station: the parameters it has reported."""
        if await self._async_catalogue() is None:
            return self.async_abort(reason="cannot_connect")
        subentry = self._get_reconfigure_subentry()
        target_type, target = subentry.data[CONF_TARGET_TYPE], str(subentry.data[CONF_TARGET])
        self.fixed_target = (target_type, target, subentry.title)
        have = {measurement_key(measurement) for measurement in subentry.data[CONF_MEASUREMENTS]}

        def offered(parameter: Parameter) -> bool:
            if measurement_key({CONF_QUERY_ID: parameter.query_id, CONF_PARAMETER: parameter.name}) in have:
                return False
            if target_type in ("fmisid", "geoid"):
                return any(station["id"] == target for station in parameter.stations)
            return parameter.kind == (KIND_POINT if target_type == "latlon" else KIND_PLACE)

        parameters = [parameter for parameter in self.catalogue.parameters.values() if offered(parameter)]
        if user_input is not None:
            if self._choose(user_input):
                return await self._async_next_target()
            return self._parameters_form(parameters, "add_measurements", {"base": "no_parameters"})
        return self._parameters_form(parameters, "add_measurements")

    def _measurement_options(self) -> list[SelectOptionDict]:
        measurements = self._get_reconfigure_subentry().data[CONF_MEASUREMENTS]
        return [
            SelectOptionDict(value=measurement_key(measurement), label=f"{measurement[CONF_LABEL]} ({measurement[CONF_PARAMETER]})")
            for measurement in measurements
        ]

    async def async_step_measurement(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Which measurement's settings to change."""
        if user_input is not None:
            self.key = user_input[CONF_MEASUREMENT]
            return await self.async_step_settings()
        schema = vol.Schema(
            {vol.Required(CONF_MEASUREMENT): SelectSelector(SelectSelectorConfig(options=self._measurement_options(), sort=False))}
        )
        return self.async_show_form(step_id="measurement", data_schema=schema)

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """A measurement's unit, -1 as 0, and for a forecast, how much of it to show."""
        subentry = self._get_reconfigure_subentry()
        measurements = list(subentry.data[CONF_MEASUREMENTS])
        index = next(index for index, measurement in enumerate(measurements) if measurement_key(measurement) == self.key)
        measurement = measurements[index]

        if user_input is not None:
            # A unit left empty is not in the form's data, and then FMI's own applies again.
            measurements[index] = {**{key: value for key, value in measurement.items() if key != CONF_UNIT}, **user_input}
            return self.async_update_and_abort(
                self._get_entry(), subentry, data={**subentry.data, CONF_MEASUREMENTS: measurements}, reason="reconfigure_successful"
            )

        fields = {
            vol.Optional(CONF_UNIT): cv.string,
            vol.Required(CONF_NEGATIVE_AS_ZERO): cv.boolean,
        }
        if "::forecast" in str(measurement[CONF_QUERY_ID]):
            fields |= {vol.Required(key): cv.positive_int for key in FORECAST_DEFAULTS}
        schema = self.add_suggested_values_to_schema(vol.Schema(fields), {**FORECAST_DEFAULTS, CONF_NEGATIVE_AS_ZERO: False, **measurement})
        return self.async_show_form(
            step_id="settings", data_schema=schema, last_step=True, description_placeholders={CONF_MEASUREMENT: measurement[CONF_LABEL]}
        )

    async def async_step_remove_measurements(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Remove measurements, but not all of them: that is removing the station."""
        subentry = self._get_reconfigure_subentry()
        options = self._measurement_options()
        errors = {}

        if user_input is not None:
            removed = set(user_input.get(CONF_MEASUREMENTS) or [])
            if len(removed) >= len(options):
                errors = {"base": "keep_one"}
            else:
                measurements = [
                    measurement for measurement in subentry.data[CONF_MEASUREMENTS] if measurement_key(measurement) not in removed
                ]
                return self.async_update_and_abort(
                    self._get_entry(), subentry, data={**subentry.data, CONF_MEASUREMENTS: measurements}, reason="reconfigure_successful"
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_MEASUREMENTS, default=[]): SelectSelector(
                    SelectSelectorConfig(options=options, multiple=True, mode=SelectSelectorMode.LIST, sort=False)
                )
            }
        )
        return self.async_show_form(step_id="remove_measurements", data_schema=schema, errors=errors, last_step=True)


def place_from_form(user_input: dict[str, Any]) -> dict[str, Any]:
    """The form's lower-case warning type keys as FMI's warning types, which subentries store."""
    types_by_key = {key: warning_type for warning_type, key in WARNING_TYPE_KEYS.items()}
    location = user_input[CONF_LOCATION]
    return {
        CONF_LOCATION: {"latitude": location["latitude"], "longitude": location["longitude"], "radius": location.get("radius") or 0},
        CONF_LABEL: user_input[CONF_LABEL].strip(),
        CONF_WEATHER: user_input[CONF_WEATHER],
        CONF_WARNING_TYPES: [types_by_key.get(key, key) for key in user_input.get(CONF_WARNING_TYPES) or []],
    }


def place_for_form(data: dict[str, Any]) -> dict[str, Any]:
    return {**data, CONF_WARNING_TYPES: [WARNING_TYPE_KEYS.get(warning_type, warning_type) for warning_type in data[CONF_WARNING_TYPES]]}


class PlaceSubentryFlow(ConfigSubentryFlow):
    """A place on a map with its weather forecast, the warnings followed there, or both."""

    async def _async_errors(self, data: dict[str, Any]) -> dict[str, str]:
        if not data[CONF_WEATHER] and not data[CONF_WARNING_TYPES]:
            return {"base": "nothing_followed"}
        if data[CONF_WEATHER]:
            # The forecast is tried, so that a place FMI has nothing for is caught here.
            try:
                await async_get_forecast(self.hass, self._get_entry().data[CONF_LANG], data[CONF_LOCATION])
            except FMINoData:
                return {"base": "no_forecast"}
            except FMIException:
                return {"base": "connection_problem"}
        return {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        entry = self._get_entry()
        errors = {}

        if user_input is not None:
            data = place_from_form(user_input)
            unique_id = place_unique_id(data[CONF_LOCATION])
            if unique_id_taken(entry, unique_id):
                return self.async_abort(reason="already_configured")
            errors = await self._async_errors(data)
            if not errors:
                return self.async_create_entry(title=data[CONF_LABEL], data=data, unique_id=unique_id)

        values = user_input or {
            CONF_LOCATION: {
                "latitude": self.hass.config.latitude,
                "longitude": self.hass.config.longitude,
                "radius": DEFAULT_WARNINGS_RADIUS,
            },
            # The place's name, which names its device.
            CONF_LABEL: self.hass.config.location_name,
            CONF_WEATHER: True,
            CONF_WARNING_TYPES: list(WARNING_TYPE_KEYS.values()),
        }
        return self.async_show_form(step_id="user", data_schema=self.add_suggested_values_to_schema(PLACE_SCHEMA, values), errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Move the place, rename it, or change what is followed there."""
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        errors = {}

        if user_input is not None:
            data = place_from_form(user_input)
            unique_id = place_unique_id(data[CONF_LOCATION])
            if unique_id_taken(entry, unique_id, except_subentry_id=subentry.subentry_id):
                return self.async_abort(reason="already_configured")
            errors = await self._async_errors(data)
            if not errors:
                return self.async_update_and_abort(
                    entry, subentry, title=data[CONF_LABEL], data=data, unique_id=unique_id, reason="reconfigure_successful"
                )

        values = user_input or place_for_form(dict(subentry.data))
        return self.async_show_form(
            step_id="reconfigure", data_schema=self.add_suggested_values_to_schema(PLACE_SCHEMA, values), errors=errors
        )
