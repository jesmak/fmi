"""Diagnostics: what a bug report gets, and that no place a user follows ends up in it."""

import json
from datetime import timedelta

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from test_no_data import ENTRY_DATA, FakeApi
from test_warning_entities import SEVERAL_AREAS, warnings_place
from test_warning_entities import FakeApi as FakeFeed
from test_weather import NOW, TAMPERE, FakeSession

from custom_components.fmi_open_data.const import (
    CONF_LABEL,
    CONF_LANG,
    CONF_LOCATION,
    CONF_TARGET,
    CONF_TARGET_TYPE,
    DOMAIN,
    SUBENTRY_SENSOR,
    SUBENTRY_WEATHER,
)
from custom_components.fmi_open_data.diagnostics import async_get_config_entry_diagnostics

STATION = {**ENTRY_DATA, CONF_LABEL: "Ilman lämpötila Kumpula"}
COORDINATES = {**ENTRY_DATA, CONF_LABEL: "Lämpötila mökillä", CONF_TARGET_TYPE: "latlon", CONF_TARGET: "61.2345,27.6543"}


async def test_the_diagnostics_keep_stations_and_leave_places_out(hass: HomeAssistant, monkeypatch, freezer):
    freezer.move_to(NOW)
    await hass.config.async_set_time_zone("Europe/Helsinki")
    monkeypatch.setattr("custom_components.fmi_open_data.query_coordinator.FMISession", lambda *a, **kw: FakeApi(timedelta(minutes=10)))
    monkeypatch.setattr("custom_components.fmi_open_data.warning_coordinator.FMISession", lambda *a, **kw: FakeFeed([SEVERAL_AREAS]))
    monkeypatch.setattr("custom_components.fmi_open_data.weather_coordinator.FMISession", lambda *a, **kw: FakeSession())
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        data={CONF_LANG: "fin"},
        subentries_data=[
            ConfigSubentryData(data=STATION, subentry_type=SUBENTRY_SENSOR, title=STATION[CONF_LABEL], unique_id="station"),
            ConfigSubentryData(data=COORDINATES, subentry_type=SUBENTRY_SENSOR, title=COORDINATES[CONF_LABEL], unique_id="at_61.2345"),
            warnings_place("Varoitukset Suomenlinna", 60.146, 24.988),
            ConfigSubentryData(
                subentry_type=SUBENTRY_WEATHER,
                title="Sää Tampere",
                unique_id="weather_61.4981_23.7608",
                data={CONF_LOCATION: TAMPERE, CONF_LABEL: "Sää Tampere"},
            ),
        ],
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    text = json.dumps(diagnostics)

    for private in ["Kumpula", "mökillä", "61.2345", "Suomenlinna", "60.146", "24.988", "Tampere", "61.4981", "23.7608"]:
        assert private not in text, private

    station, coordinates, warnings, weather = diagnostics["subentries"]
    assert station["unique_id"] == "station"
    assert station["data"][CONF_TARGET] == "100971"
    assert station["data"]["query_id"] == "fmi::observations::weather::simple"
    assert station["coordinator"]["last_update_success"] is True
    assert station["coordinator"]["data"]["values"] == 1
    assert station["coordinator"]["data"]["unit"] == "°C"
    assert coordinates["data"][CONF_TARGET] == "**REDACTED**"
    assert coordinates["unique_id"] == "**REDACTED**"
    assert warnings["coordinator"]["data"]["warnings"] == []
    assert weather["coordinator"]["data"]["hours"] == 226
    assert weather["coordinator"]["data"]["first"] == "2026-10-15T15:00:00+00:00"
