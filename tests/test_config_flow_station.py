"""Adding measurements from what to measure, and changing a station's measurements."""

from datetime import timedelta

import pytest
from conftest import station
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from test_no_data import FakeApi

from custom_components.fmi_open_data.catalogue import KIND_PLACE, KIND_POINT, KIND_STATIONS, Catalogue, Parameter
from custom_components.fmi_open_data.const import (
    CONF_LABEL,
    CONF_LANG,
    CONF_MEASUREMENTS,
    CONF_STRUCTURE,
    CONF_TARGET,
    CONF_TARGET_TYPE,
    CONF_UNIT,
    DOMAIN,
    STRUCTURE_VERSION,
    SUBENTRY_STATION,
)
from custom_components.fmi_open_data.session import FMIException

WEATHER = "fmi::observations::weather::simple"
FORECAST = "fmi::forecast::harmonie::surface::point::simple"
STUK = "stuk::observations::air::radionuclide-activity-concentration::latest::simple"
KAISANIEMI = {"target_type": "fmisid", "id": "100971", "name": "Helsinki Kaisaniemi", "latitude": 60.17523, "longitude": 24.94459}
KUMPULA = {"target_type": "fmisid", "id": "101004", "name": "Helsinki Kumpula", "latitude": 60.20307, "longitude": 24.96131}
MALMI = {"target_type": "fmisid", "id": "101009", "name": "Helsinki Malmi lentokenttä", "latitude": 60.25299, "longitude": 25.04549}
T2M = Parameter(WEATHER, "Hetkelliset säähavaintoarvot", "t2m", "Ilman lämpötila", KIND_STATIONS, [KAISANIEMI, KUMPULA])
RAIN = Parameter(WEATHER, "Hetkelliset säähavaintoarvot", "r_1h", "Sademäärä", KIND_STATIONS, [KUMPULA, KAISANIEMI])
TEMPERATURE = Parameter(FORECAST, "Harmonie-ennuste", "Temperature", "Lämpötila", KIND_POINT)
BE7 = Parameter(STUK, "Ulkoilman radioaktiivisuus", "Be-7", None, KIND_PLACE)
# Reported by no station lately, as wave height while the buoys are ashore for the winter.
WAVES = Parameter(WEATHER, "Hetkelliset säähavaintoarvot", "WaveHs", "Aallonkorkeus", KIND_STATIONS, [])
CATALOGUE = Catalogue(
    {parameter.value: parameter for parameter in (T2M, RAIN, TEMPERATURE, BE7, WAVES)},
    {WEATHER: [KAISANIEMI, KUMPULA, MALMI], FORECAST: [], STUK: []},
)
T2M_AT_KAISANIEMI = {"query_id": WEATHER, "parameter": "t2m", "label": "Ilman lämpötila", "negative_as_zero": False}


class FakeTry:
    """Stands in for FMISession where the flow reads a measurement once at a place the user gave."""

    data = True

    def get_feature(self, lang, params, target_param, get_latest, negative_as_zero=False):
        return {"data": [{"time": None, "value": "1"}] if FakeTry.data else []}


@pytest.fixture
async def entry(hass: HomeAssistant, monkeypatch) -> MockConfigEntry:
    hass.config.latitude, hass.config.longitude, hass.config.location_name = 60.17, 24.94, "Koti"

    async def catalogue(hass, lang):
        return CATALOGUE

    FakeTry.data = True
    monkeypatch.setattr("custom_components.fmi_open_data.config_flow.async_catalogue", catalogue)
    monkeypatch.setattr("custom_components.fmi_open_data.config_flow.FMISession", FakeTry)
    monkeypatch.setattr("custom_components.fmi_open_data.query_coordinator.FMISession", lambda *a, **kw: FakeApi(timedelta(minutes=10)))
    entry = MockConfigEntry(domain=DOMAIN, version=3, data={CONF_LANG: "fin", CONF_STRUCTURE: STRUCTURE_VERSION})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _start(hass: HomeAssistant, entry: MockConfigEntry, *parameters: Parameter) -> dict:
    result = await hass.config_entries.subentries.async_init((entry.entry_id, SUBENTRY_STATION), context={"source": SOURCE_USER})
    assert result["step_id"] == "user"
    return await hass.config_entries.subentries.async_configure(result["flow_id"], {"parameters": [p.value for p in parameters]})


async def _configure(hass: HomeAssistant, result: dict, data: dict) -> dict:
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], data)
    await hass.async_block_till_done()
    return result


def _options(result: dict, field: str) -> list[str]:
    key = next(key for key in result["data_schema"].schema if key == field)
    return [option["value"] for option in result["data_schema"].schema[key].config["options"]]


def _default(result: dict, field: str):
    return next(key for key in result["data_schema"].schema if key == field).default()


def _names(result: dict) -> dict[str, str]:
    return {str(key): key.default() for key in result["data_schema"].schema}


async def test_the_parameters_start_empty_and_one_is_needed(hass: HomeAssistant, entry: MockConfigEntry):
    result = await hass.config_entries.subentries.async_init((entry.entry_id, SUBENTRY_STATION), context={"source": SOURCE_USER})
    assert _default(result, "parameters") == []
    assert _options(result, "parameters") == [T2M.value, RAIN.value, TEMPERATURE.value, BE7.value, WAVES.value]

    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"parameters": []})
    assert result["errors"] == {"base": "no_parameters"}


async def test_each_measurement_goes_to_its_own_station(hass: HomeAssistant, entry: MockConfigEntry):
    result = await _start(hass, entry, T2M, RAIN)

    # Only the stations that reported the parameter, nearest first.
    assert result["step_id"] == "station"
    assert _options(result, "station") == ["100971", "101004"]
    result = await _configure(hass, result, {"station": "100971", "show_all": False})

    # The station of the previous measurement is suggested when it has this one too.
    assert _default(result, "station") == "100971"
    result = await _configure(hass, result, {"station": "101004", "show_all": False})

    assert result["step_id"] == "names"
    assert _names(result) == {"Helsinki Kaisaniemi · Ilman lämpötila": "Ilman lämpötila", "Helsinki Kumpula · Sademäärä": "Sademäärä"}
    result = await _configure(
        hass, result, {"Helsinki Kaisaniemi · Ilman lämpötila": "Lämpötila", "Helsinki Kumpula · Sademäärä": "Sademäärä"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "measurements_added"
    assert result["description_placeholders"] == {"stations": "Helsinki Kaisaniemi (1), Helsinki Kumpula (1)"}
    stations = {subentry.title: subentry for subentry in entry.subentries.values()}
    assert set(stations) == {"Helsinki Kaisaniemi", "Helsinki Kumpula"}
    assert stations["Helsinki Kaisaniemi"].unique_id == "station_fmisid_100971"
    assert [measurement[CONF_LABEL] for measurement in stations["Helsinki Kaisaniemi"].data[CONF_MEASUREMENTS]] == ["Lämpötila"]
    assert hass.states.get("sensor.helsinki_kaisaniemi_lampotila").name == "Helsinki Kaisaniemi Lämpötila"
    assert hass.states.get("sensor.helsinki_kumpula_sademaara") is not None


async def test_a_measurement_joins_a_station_already_there(hass: HomeAssistant, entry: MockConfigEntry):
    hass.config_entries.async_add_subentry(entry, _subentry(station(T2M_AT_KAISANIEMI)))
    await hass.async_block_till_done()

    result = await _start(hass, entry, RAIN)
    result = await _configure(hass, result, {"station": "100971", "show_all": False})
    result = await _configure(hass, result, {"Helsinki Kaisaniemi · Sademäärä": "Sademäärä"})

    assert result["reason"] == "measurements_added"
    [kaisaniemi] = entry.subentries.values()
    assert [measurement["parameter"] for measurement in kaisaniemi.data[CONF_MEASUREMENTS]] == ["t2m", "r_1h"]


async def test_a_measurement_already_there_is_not_added_again(hass: HomeAssistant, entry: MockConfigEntry):
    hass.config_entries.async_add_subentry(entry, _subentry(station(T2M_AT_KAISANIEMI)))
    await hass.async_block_till_done()

    result = await _start(hass, entry, T2M)
    result = await _configure(hass, result, {"station": "100971", "show_all": False})
    result = await _configure(hass, result, {"Helsinki Kaisaniemi · Ilman lämpötila": "Ilman lämpötila"})

    assert result["reason"] == "already_configured"


async def test_every_station_of_the_query_on_request(hass: HomeAssistant, entry: MockConfigEntry):
    result = await _start(hass, entry, T2M)
    result = await _configure(hass, result, {"station": "100971", "show_all": True})

    assert result["step_id"] == "station"
    assert _options(result, "station") == ["100971", "101004", "101009"]
    result = await _configure(hass, result, {"station": "101009", "show_all": True})
    assert result["step_id"] == "names"


async def test_a_forecast_asks_for_a_point_and_its_name(hass: HomeAssistant, entry: MockConfigEntry):
    result = await _start(hass, entry, TEMPERATURE)
    assert result["step_id"] == "point"

    result = await _configure(hass, result, {"point": {"latitude": 61.23456, "longitude": 27.65432}, "place_name": "Mökki"})
    result = await _configure(hass, result, {"Mökki · Lämpötila": "Lämpötila"})

    [cabin] = entry.subentries.values()
    assert cabin.title == "Mökki"
    assert (cabin.data[CONF_TARGET_TYPE], cabin.data[CONF_TARGET]) == ("latlon", "61.2346,27.6543")
    assert cabin.data[CONF_MEASUREMENTS][0]["forecast_hours"] == 36


async def test_a_place_name_is_tried_before_it_is_taken(hass: HomeAssistant, entry: MockConfigEntry):
    result = await _start(hass, entry, BE7)
    assert result["step_id"] == "named_place"

    FakeTry.data = False
    result = await _configure(hass, result, {"place": "Kotkka"})
    assert result["errors"] == {"base": "no_data"}

    FakeTry.data = True
    result = await _configure(hass, result, {"place": "Kotka"})
    result = await _configure(hass, result, {"Kotka · Be-7": "Be-7"})

    [kotka] = entry.subentries.values()
    assert (kotka.title, kotka.unique_id) == ("Kotka", "station_place_kotka")


async def test_fmi_down_while_reading_the_catalogue(hass: HomeAssistant, entry: MockConfigEntry, monkeypatch):
    async def down(hass, lang):
        raise FMIException("Timeout error")

    monkeypatch.setattr("custom_components.fmi_open_data.config_flow.async_catalogue", down)
    result = await hass.config_entries.subentries.async_init((entry.entry_id, SUBENTRY_STATION), context={"source": SOURCE_USER})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


def _subentry(data):
    from homeassistant.config_entries import ConfigSubentry

    return ConfigSubentry(data=data["data"], subentry_type=data["subentry_type"], title=data["title"], unique_id=data["unique_id"])


async def _reconfigure(hass: HomeAssistant, entry: MockConfigEntry, option: str) -> dict:
    hass.config_entries.async_add_subentry(entry, _subentry(station(T2M_AT_KAISANIEMI, {**T2M_AT_KAISANIEMI, "parameter": "ws_10min"})))
    await hass.async_block_till_done()
    [subentry] = entry.subentries.values()
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_STATION), context={"source": SOURCE_RECONFIGURE, "subentry_id": subentry.subentry_id}
    )
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.subentries.async_configure(result["flow_id"], {"next_step_id": option})


async def test_adding_to_a_station_offers_what_it_measures(hass: HomeAssistant, entry: MockConfigEntry):
    result = await _reconfigure(hass, entry, "add_measurements")

    # Air temperature is there already, and the forecast and STUK are not read at a station.
    assert _options(result, "parameters") == [RAIN.value]
    result = await _configure(hass, result, {"parameters": [RAIN.value]})
    result = await _configure(hass, result, {"Helsinki Kaisaniemi · Sademäärä": "Sademäärä"})

    assert result["reason"] == "reconfigure_successful"
    [subentry] = entry.subentries.values()
    assert [measurement["parameter"] for measurement in subentry.data[CONF_MEASUREMENTS]] == ["t2m", "ws_10min", "r_1h"]


async def test_a_measurements_unit(hass: HomeAssistant, entry: MockConfigEntry):
    result = await _reconfigure(hass, entry, "measurement")
    result = await _configure(hass, result, {"measurement": f"{WEATHER}_t2m"})
    assert result["step_id"] == "settings"
    result = await _configure(hass, result, {CONF_UNIT: "K", "negative_as_zero": True})

    assert result["reason"] == "reconfigure_successful"
    [subentry] = entry.subentries.values()
    assert subentry.data[CONF_MEASUREMENTS][0][CONF_UNIT] == "K"
    assert subentry.data[CONF_MEASUREMENTS][0]["negative_as_zero"] is True
    assert hass.states.get("sensor.helsinki_kaisaniemi_ilman_lampotila").attributes["unit_of_measurement"] == "K"


async def test_removing_a_measurement_removes_its_entities(hass: HomeAssistant, entry: MockConfigEntry):
    result = await _reconfigure(hass, entry, "remove_measurements")
    result = await _configure(hass, result, {CONF_MEASUREMENTS: [f"{WEATHER}_t2m", f"{WEATHER}_ws_10min"]})
    assert result["errors"] == {"base": "keep_one"}

    result = await _configure(hass, result, {CONF_MEASUREMENTS: [f"{WEATHER}_ws_10min"]})

    assert result["reason"] == "reconfigure_successful"
    [subentry] = entry.subentries.values()
    assert [measurement["parameter"] for measurement in subentry.data[CONF_MEASUREMENTS]] == ["t2m"]
    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert {entity.unique_id for entity in entities} == {f"{subentry.subentry_id}_{WEATHER}_t2m"}


async def test_a_parameter_no_station_reported_lately_starts_from_every_station(hass: HomeAssistant, entry: MockConfigEntry):
    result = await _start(hass, entry, WAVES)

    assert result["step_id"] == "station"
    assert _default(result, "show_all") is True
    assert _options(result, "station") == ["100971", "101004", "101009"]
