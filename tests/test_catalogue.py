"""What can be measured: every station query's parameters, and the stations that reported each one."""

import pytest
from homeassistant.core import HomeAssistant

from custom_components.fmi_open_data.catalogue import KIND_PLACE, KIND_POINT, KIND_STATIONS, async_catalogue
from custom_components.fmi_open_data.session import FMIException, FMIRefused

KAISANIEMI = {"id": "100971", "name": "Helsinki Kaisaniemi", "latitude": 60.17523, "longitude": 24.94459}
HARMAJA = {"id": "100996", "name": "Helsinki Harmaja", "latitude": 60.10512, "longitude": 24.97539}
QUERIES = [
    ["fmi::observations::weather::simple", "Säähavainnot"],
    ["fmi::observations::weather::hourly::simple", "Säähavainnot"],
    ["fmi::forecast::harmonie::surface::point::simple", "Harmonie"],
    ["fmi::forecast::sealevel::point::simple", "Merivedenkorkeusennuste"],
    ["stuk::observations::air::radionuclide-activity-concentration::latest::simple", "Radioaktiivisuus"],
    ["fmi::observations::magnetometer::simple", "Magnetometri"],
    ["fmi::observations::surfacetemperature::simple", "Pintalämpötila"],
]
# Stations by position, as the ::simple form gives them: the sea buoy is in FMI's station list, the observatory is not.
BUOY = {"id": "134221", "name": "Suomenlahti aaltopoiju", "latitude": 59.96503, "longitude": 25.23542}


class FakeSession:
    requests: list[dict] = []

    def list_stored_queries(self, lang, suffix=None):
        return QUERIES

    def get_station_coverage(self, lang, params):
        FakeSession.requests.append(params)
        query_id = params["storedquery_id"]
        if "magnetometer" in query_id or "surfacetemperature" in query_id:
            raise FMIRefused(f"No handler for '{query_id}' found!")
        if "sealevel" in query_id:
            return ["SeaLevelN2000"], [
                {"id": "659169", "name": "Hamina", "latitude": 60.56, "longitude": 27.18, "measured": {"SeaLevelN2000"}}
            ]
        if "::forecast" in query_id:
            # FMI answers a point forecast for the named place nearest to the point asked.
            return ["Temperature"], [] if "bbox" in params else [{**KAISANIEMI, "id": "658225", "measured": {"Temperature"}}]
        if "stuk::" in query_id:
            return ["Be-7"], []
        if "::hourly" in query_id:
            return ["TA_PT1H_AVG", "TA_PT1H_MAX"], [{**KAISANIEMI, "measured": {"TA_PT1H_AVG", "TA_PT1H_MAX"}}]
        return ["t2m", "r_1h"], [{**HARMAJA, "measured": {"t2m"}}, {**KAISANIEMI, "measured": {"t2m", "r_1h"}}]

    def list_stations(self, lang):
        return [KAISANIEMI, HARMAJA, BUOY]

    def get_simple_coverage(self, lang, params):
        FakeSession.requests.append(params)
        if "surfacetemperature" in params["storedquery_id"]:
            return ["TWATER"], {(59.96503, 25.23542): {"TWATER"}, (60.0, 20.0): {"TWATER"}}
        return ["MAGNX_PT10S_AVG"], {(69.75, 27.01): {"MAGNX_PT10S_AVG"}}

    def get_parameter_descriptions(self, lang, query_id):
        # FMI gives a minimum and a mean the same description.
        return {"t2m": ("Ilman lämpötila", "°C"), "ta_pt1h_avg": ("Ilman lämpötila", "°C"), "ta_pt1h_max": ("Ilman lämpötila", "°C")}


async def _catalogue(hass: HomeAssistant, monkeypatch):
    hass.config.latitude, hass.config.longitude = 60.17, 24.94
    FakeSession.requests = []
    monkeypatch.setattr("custom_components.fmi_open_data.catalogue.FMISession", FakeSession)
    return await async_catalogue(hass, "fin")


async def test_every_parameter_with_the_stations_that_reported_it(hass: HomeAssistant, monkeypatch):
    catalogue = await _catalogue(hass, monkeypatch)

    parameters = {parameter.name: parameter for parameter in catalogue.parameters.values()}
    assert set(parameters) == {"t2m", "r_1h", "TA_PT1H_AVG", "TA_PT1H_MAX", "Temperature", "SeaLevelN2000", "Be-7", "TWATER"}
    assert [station["name"] for station in parameters["t2m"].stations] == ["Helsinki Kaisaniemi", "Helsinki Harmaja"]
    assert [station["name"] for station in parameters["r_1h"].stations] == ["Helsinki Kaisaniemi"]
    assert (parameters["t2m"].kind, parameters["Temperature"].kind, parameters["Be-7"].kind) == (KIND_STATIONS, KIND_POINT, KIND_PLACE)
    # Every station of the query, nearest first, for when the user wants them all.
    assert [station["id"] for station in catalogue.stations["fmi::observations::weather::simple"]] == ["100971", "100996"]


async def test_a_label_never_repeats_another(hass: HomeAssistant, monkeypatch):
    catalogue = await _catalogue(hass, monkeypatch)

    labels = {parameter.name: parameter.label for parameter in catalogue.parameters.values()}
    # Both queries are called Säähavainnot here, so every air temperature needs its parameter.
    assert labels["t2m"] == "Ilman lämpötila · Säähavainnot (t2m)"
    assert labels["TA_PT1H_AVG"] == "Ilman lämpötila · Säähavainnot (TA_PT1H_AVG)"
    assert labels["r_1h"] == "r_1h · Säähavainnot"


async def test_frequent_observations_are_read_for_the_last_hour_only(hass: HomeAssistant, monkeypatch):
    await _catalogue(hass, monkeypatch)

    windows = {params["storedquery_id"]: "starttime" in params for params in FakeSession.requests}
    assert windows["fmi::observations::weather::multipointcoverage"] is True
    assert windows["fmi::observations::weather::hourly::multipointcoverage"] is False
    assert windows["stuk::observations::air::radionuclide-activity-concentration::latest::multipointcoverage"] is False


async def test_the_catalogue_is_kept_for_an_hour(hass: HomeAssistant, monkeypatch, freezer):
    first = await _catalogue(hass, monkeypatch)
    requests = len(FakeSession.requests)

    freezer.tick(1800)
    assert await async_catalogue(hass, "fin") is first
    assert len(FakeSession.requests) == requests

    freezer.tick(1801)
    assert await async_catalogue(hass, "fin") is not first


async def test_without_fmis_queries_there_is_no_catalogue(hass: HomeAssistant, monkeypatch):
    class Down(FakeSession):
        def list_stored_queries(self, lang, suffix=None):
            raise FMIException("Timeout error")

    monkeypatch.setattr("custom_components.fmi_open_data.catalogue.FMISession", Down)
    with pytest.raises(FMIException):
        await async_catalogue(hass, "fin")


async def test_a_query_only_in_the_simple_form_is_read_station_by_station(hass: HomeAssistant, monkeypatch):
    catalogue = await _catalogue(hass, monkeypatch)

    [water] = [parameter for parameter in catalogue.parameters.values() if parameter.name == "TWATER"]
    # Recognised by its position in FMI's station list. A position that is no station there is left out.
    assert water.kind == KIND_STATIONS
    assert [station["name"] for station in water.stations] == ["Suomenlahti aaltopoiju"]
    # The magnetometer's observatory is not in the station list, so there is nothing to offer.
    assert not any("magnetometer" in parameter.query_id for parameter in catalogue.parameters.values())
    simple = next(params for params in FakeSession.requests if params["storedquery_id"] == "fmi::observations::surfacetemperature::simple")
    assert simple["timestep"] == 60


async def test_a_forecast_at_fixed_points_is_read_by_geoid(hass: HomeAssistant, monkeypatch):
    catalogue = await _catalogue(hass, monkeypatch)

    [sea_level] = [parameter for parameter in catalogue.parameters.values() if parameter.name == "SeaLevelN2000"]
    assert sea_level.kind == KIND_STATIONS
    assert [(station["name"], station["target_type"]) for station in sea_level.stations] == [("Hamina", "geoid")]
    # A model forecast stays a point for the user to choose, not the place FMI happened to answer for.
    [temperature] = [parameter for parameter in catalogue.parameters.values() if parameter.name == "Temperature"]
    assert (temperature.kind, temperature.stations) == (KIND_POINT, [])


async def test_a_catalogue_with_a_failed_query_is_not_kept(hass: HomeAssistant, monkeypatch):
    class Hiccup(FakeSession):
        def get_station_coverage(self, lang, params):
            if params["storedquery_id"] == "fmi::observations::weather::hourly::multipointcoverage":
                raise FMIException("Timeout error")
            return super().get_station_coverage(lang, params)

    hass.config.latitude, hass.config.longitude = 60.17, 24.94
    monkeypatch.setattr("custom_components.fmi_open_data.catalogue.FMISession", Hiccup)
    first = await async_catalogue(hass, "fin")
    assert not any(parameter.name == "TA_PT1H_AVG" for parameter in first.parameters.values())

    monkeypatch.setattr("custom_components.fmi_open_data.catalogue.FMISession", FakeSession)
    second = await async_catalogue(hass, "fin")
    assert any(parameter.name == "TA_PT1H_AVG" for parameter in second.parameters.values())
