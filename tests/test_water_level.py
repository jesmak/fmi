"""A water level sensor is a distance in FMI's own unit, and other sensors have no device class."""

from datetime import timedelta

from homeassistant.core import HomeAssistant
from test_no_data import FakeApi, _setup

from custom_components.fmi_open_data.const import CONF_LABEL, CONF_PARAMETER, CONF_QUERY_ID
from custom_components.fmi_open_data.session import FMISession


class WaterLevelApi(FakeApi):
    def get_unit(self, lang, query_id, param_name):
        return FMISession().get_unit(lang, query_id, param_name)


async def test_the_mareographs_water_level_is_a_distance_in_millimetres(hass: HomeAssistant, monkeypatch):
    await _setup(
        hass,
        monkeypatch,
        WaterLevelApi(timedelta(minutes=10)),
        **{
            CONF_LABEL: "Vedenkorkeus",
            CONF_QUERY_ID: "fmi::observations::mareograph::instant::simple",
            CONF_PARAMETER: "WLEVN2K_PT1S_INSTANT",
        },
    )

    state = hass.states.get("sensor.fmi_vedenkorkeus")
    assert state.attributes["device_class"] == "distance"
    assert state.attributes["unit_of_measurement"] == "mm"
    assert state.state == "1.5"


async def test_other_sensors_have_no_device_class(hass: HomeAssistant, monkeypatch):
    await _setup(hass, monkeypatch, FakeApi(timedelta(minutes=10)))

    state = hass.states.get("sensor.fmi_kaisaniemi_air_temperature")
    assert "device_class" not in state.attributes
    assert state.attributes["unit_of_measurement"] == "°C"
