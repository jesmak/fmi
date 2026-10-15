"""Diagnostics: what a bug report gets, and that no place a user follows ends up in it."""

import json
from datetime import timedelta

from conftest import place, station
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from test_no_data import FakeApi
from test_warning_entities import SEVERAL_AREAS
from test_warning_entities import FakeApi as FakeFeed
from test_weather import NOW, TAMPERE, FakeSession

from custom_components.fmi_open_data.const import CONF_LANG, CONF_STRUCTURE, DOMAIN, STRUCTURE_VERSION
from custom_components.fmi_open_data.diagnostics import async_get_config_entry_diagnostics
from custom_components.fmi_open_data.session import FMIException


class PlaceNameInErrors(FakeApi):
    """FMI's error for a point it has nothing for repeats the place."""

    def get_feature(self, lang, params, target_param, get_latest, negative_as_zero=False):
        if "latlon" in params:
            raise FMIException("No data available for 'Mökki'!")
        return super().get_feature(lang, params, target_param, get_latest, negative_as_zero)


MEASUREMENT = {"query_id": "fmi::observations::weather::simple", "parameter": "t2m", "label": "Ilman lämpötila", "negative_as_zero": False}


async def test_the_diagnostics_keep_stations_and_leave_places_out(hass: HomeAssistant, monkeypatch, freezer):
    freezer.move_to(NOW)
    await hass.config.async_set_time_zone("Europe/Helsinki")
    monkeypatch.setattr(
        "custom_components.fmi_open_data.query_coordinator.FMISession", lambda *a, **kw: PlaceNameInErrors(timedelta(minutes=10))
    )
    monkeypatch.setattr("custom_components.fmi_open_data.warning_coordinator.FMISession", lambda *a, **kw: FakeFeed([SEVERAL_AREAS]))
    monkeypatch.setattr("custom_components.fmi_open_data.weather_coordinator.FMISession", lambda *a, **kw: FakeSession())
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        data={CONF_LANG: "fin", CONF_STRUCTURE: STRUCTURE_VERSION},
        subentries_data=[
            station(MEASUREMENT),
            station(MEASUREMENT, title="Mökki", target_type="latlon", target="61.2345,27.6543"),
            place("Suomenlinna", 60.146, 24.988),
            place("Tampereen koti", TAMPERE["latitude"], TAMPERE["longitude"], weather=True, warning_types=[]),
        ],
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    text = json.dumps(diagnostics)

    for private in ["Mökki", "61.2345", "Suomenlinna", "60.146", "24.988", "Tampereen koti", "61.4981", "23.7608"]:
        assert private not in text, private

    kaisaniemi, cabin, warnings, weather = diagnostics["subentries"]
    assert kaisaniemi["title"] == "Helsinki Kaisaniemi"
    assert kaisaniemi["unique_id"] == "station_fmisid_100971"
    assert kaisaniemi["data"]["target"] == "100971"
    assert kaisaniemi["data"]["measurements"][0]["query_id"] == "fmi::observations::weather::simple"
    [coordinator] = kaisaniemi["coordinators"]
    assert coordinator["kind"] == "measurement"
    assert coordinator["measurement"] == "fmi::observations::weather::simple_t2m"
    assert coordinator["last_update_success"] is True
    assert coordinator["data"]["values"] == 1
    assert cabin["data"]["target"] == "**REDACTED**"
    assert cabin["coordinators"][0]["last_exception"] == "UpdateFailed"
    assert cabin["title"] == "**REDACTED**"
    assert warnings["coordinators"][0]["kind"] == "warnings"
    assert warnings["coordinators"][0]["data"]["warnings"] == []
    assert weather["coordinators"][0]["data"]["hours"] == 226
