"""Each measurement's device class and unit, and the statistics recorded in FMI's spelling of a unit."""

from datetime import timedelta
from functools import partial

import pytest
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.components.recorder.statistics import async_import_statistics, get_metadata, validate_statistics
from homeassistant.components.sensor import SensorDeviceClass as D
from homeassistant.components.sensor import SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant.components.recorder.common import async_wait_recording_done, do_adhoc_statistics
from test_no_data import FakeApi, _setup

from custom_components.fmi_open_data.const import CONF_LABEL, CONF_PARAMETER
from custom_components.fmi_open_data.session import FMIException
from custom_components.fmi_open_data.units import sensor_class, state_class


@pytest.mark.parametrize(
    ("parameter", "fmi_unit", "device_class", "unit"),
    [
        # Parameters and units as FMI's metadata gives them.
        ("ta_pt1h_avg", "°C", D.TEMPERATURE, "°C"),
        ("tw_pt1h_avg", "°C", D.TEMPERATURE, "°C"),
        ("td_pt10m_avg", "°C", D.TEMPERATURE, "°C"),
        ("rh_pt1h_avg", "%", D.HUMIDITY, "%"),
        ("pa_pt1h_avg", "hPa", D.ATMOSPHERIC_PRESSURE, "hPa"),
        ("ws_10min", "m/s", D.WIND_SPEED, "m/s"),
        ("ws", "kt", D.WIND_SPEED, "kn"),
        ("wg_pt1h_max", "m/s", D.WIND_SPEED, "m/s"),
        ("wd_10min", "deg", D.WIND_DIRECTION, "°"),
        ("wd", "degrees", D.WIND_DIRECTION, "°"),
        ("pra_pt1h_acc", "mm", D.PRECIPITATION, "mm"),
        ("pri_pt1h_max", "mm/h", D.PRECIPITATION_INTENSITY, "mm/h"),
        ("glob_1min", "W/m2", D.IRRADIANCE, "W/m²"),
        ("sund_p1d_sum", "h", D.DURATION, "h"),
        ("snd_pt1m_avg", "cm", D.DISTANCE, "cm"),
        ("ice_pt1s_instant", "cm", D.DISTANCE, "cm"),
        ("sndice_pt1m_avg", "cm", D.DISTANCE, "cm"),
        ("wlev_pt1s_instant", "mm", D.DISTANCE, "mm"),
        ("sealevel", "cm", D.DISTANCE, "cm"),
        ("wavehs", "m", D.DISTANCE, "m"),
        ("vis_pt1m_avg", "m", D.DISTANCE, "m"),
        ("cloudceiling", "ft", D.DISTANCE, "ft"),
        ("pm25_pt1h_avg", "ug/m3", D.PM25, "μg/m³"),
        ("pm10_pt1h_avg", "ug/m3", D.PM10, "μg/m³"),
        ("no2_pt1h_avg", "ug/m3", D.NITROGEN_DIOXIDE, "μg/m³"),
        ("no_pt1h_avg", "ug/m3", D.NITROGEN_MONOXIDE, "μg/m³"),
        ("noconcentration", "ug/m3", D.NITROGEN_MONOXIDE, "μg/m³"),
        ("o3_pt1h_avg", "ug/m3", D.OZONE, "μg/m³"),
        ("so2_pt1h_avg", "ug/m3", D.SULPHUR_DIOXIDE, "μg/m³"),
        ("co_pt1h_avg", "ug/m3", D.CO, "μg/m³"),
        ("coconcentration", "ug/m3", D.CO, "μg/m³"),
        ("aqindex_pt1h_avg", "index", D.AQI, None),
        ("aqindex", "", D.AQI, None),
        # A unit Home Assistant doesn't take for the kind: no class, and the unit as it is.
        ("wd045p1m", "%", None, "%"),
        ("ws0p1m", "%", None, "%"),
        ("ndpr001p1m", "#", None, "#"),
        ("precipitation1h", "mm/h", None, "mm/h"),
        ("diff_p1d_sum", "kJ/m2", None, "kJ/m2"),
        ("swe_pt1m_avg", "kg/m2", None, "kg/m2"),
        ("tz_pt1s_acc", "s", None, "s"),
        ("modalwdi", "deg", None, "°"),
        ("iceconcentration", "%", None, "%"),
        # Not the measurement itself, though the kind's name says so.
        ("wd_pt10m_std", "deg", None, "°"),
        ("no2_exceed_pt1h_avg", "ug/m3", None, "μg/m³"),
        ("pm25_p1d_exceed_p1d_avg", "ug/m3", None, "μg/m³"),
        # The EMEP filters' compounds, and kinds Home Assistant has no class for.
        ("qno2_pt1s_avg", "ug/m3", None, "μg/m³"),
        ("qso2sair_pt1s_avg", "ugS/m3", None, "ugS/m3"),
        ("dr_pt10m_avg", "µSv/h", None, "µSv/h"),
        ("uvb_p1d_sum", "index", None, "index"),
        ("n_man", "1/8", None, "1/8"),
        ("dilma", "°C", None, "°C"),
        # A unit the user typed, with the micro sign rather than Home Assistant's mu.
        ("pm25_pt1h_avg", "µg/m³", D.PM25, "μg/m³"),
        # No unit at all, from FMI or the user.
        ("wlev_pt1s_instant", None, None, None),
    ],
)
def test_the_class_and_unit_of_a_parameter(parameter, fmi_unit, device_class, unit):
    assert sensor_class(parameter, fmi_unit) == (device_class, unit)


def test_a_direction_is_an_angle():
    assert state_class(D.WIND_DIRECTION) is SensorStateClass.MEASUREMENT_ANGLE
    assert state_class(D.TEMPERATURE) is SensorStateClass.MEASUREMENT
    assert state_class(None) is SensorStateClass.MEASUREMENT


class UnitApi(FakeApi):
    def __init__(self, unit: str | None):
        super().__init__(age=timedelta(minutes=5))
        self.unit = unit

    def get_unit(self, *args):
        return self.unit


PM25 = "sensor.helsinki_kaisaniemi_pm2_5"


def _old_statistics(hass: HomeAssistant, unit: str | None, statistic_id: str = PM25) -> None:
    """Long-term statistics as an earlier version recorded them, with FMI's own unit."""
    metadata = {
        "mean_type": StatisticMeanType.ARITHMETIC,
        "has_sum": False,
        "name": None,
        "source": "recorder",
        "statistic_id": statistic_id,
        "unit_class": None,
        "unit_of_measurement": unit,
    }
    start = dt_util.utcnow().replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    async_import_statistics(hass, metadata, [{"start": start, "mean": 5.0, "min": 4.0, "max": 6.0}])


async def _statistics_unit(hass: HomeAssistant, statistic_id: str = PM25) -> str | None:
    metadata = await get_instance(hass).async_add_executor_job(partial(get_metadata, hass, statistic_ids={statistic_id}))
    return metadata[statistic_id][1]["unit_of_measurement"]


async def _setup_pm25(hass: HomeAssistant, monkeypatch):
    await _setup(hass, monkeypatch, UnitApi("ug/m3"), **{CONF_PARAMETER: "pm25_pt1h_avg", CONF_LABEL: "PM2.5"})
    await async_wait_recording_done(hass)


async def test_statistics_in_fmis_spelling_get_home_assistants(recorder_mock, hass: HomeAssistant, monkeypatch):
    _old_statistics(hass, "ug/m3")
    await async_wait_recording_done(hass)

    await _setup_pm25(hass, monkeypatch)

    state = hass.states.get(PM25)
    assert (state.attributes["device_class"], state.attributes["unit_of_measurement"]) == ("pm25", "μg/m³")
    assert await _statistics_unit(hass) == "μg/m³"

    # The statistics go on: the recorder finds nothing wrong, and compiles the sensor's next period.
    now = dt_util.utcnow()
    do_adhoc_statistics(hass, start=now.replace(minute=now.minute - now.minute % 5, second=0, microsecond=0))
    await async_wait_recording_done(hass)
    issues = await get_instance(hass).async_add_executor_job(validate_statistics, hass)
    assert PM25 not in issues


async def test_an_index_loses_its_unit(recorder_mock, hass: HomeAssistant, monkeypatch):
    aqi = "sensor.helsinki_kaisaniemi_air_quality_index"
    _old_statistics(hass, "index", aqi)
    await async_wait_recording_done(hass)

    await _setup(hass, monkeypatch, UnitApi("index"), **{CONF_PARAMETER: "aqindex_pt1h_avg", CONF_LABEL: "Air quality index"})
    await async_wait_recording_done(hass)

    assert "unit_of_measurement" not in hass.states.get(aqi).attributes
    assert await _statistics_unit(hass, aqi) is None


async def test_statistics_in_another_unit_are_left_alone(recorder_mock, hass: HomeAssistant, monkeypatch):
    """Only FMI's own spelling is relabelled. Statistics in any other unit are the user's to sort out."""
    _old_statistics(hass, "mg/m³")
    await async_wait_recording_done(hass)

    await _setup_pm25(hass, monkeypatch)

    assert await _statistics_unit(hass) == "mg/m³"


async def test_a_sensor_without_statistics_gets_none(recorder_mock, hass: HomeAssistant, monkeypatch):
    await _setup_pm25(hass, monkeypatch)

    state = hass.states.get(PM25)
    assert (state.attributes["device_class"], state.attributes["unit_of_measurement"]) == ("pm25", "μg/m³")
    metadata = await get_instance(hass).async_add_executor_job(get_metadata, hass)
    assert PM25 not in metadata


async def test_the_unit_known_only_later_is_relabelled_then(recorder_mock, hass: HomeAssistant, monkeypatch):
    """FMI down at startup: the sensor has no unit until its first answer, and the statistics wait for it, once."""
    _old_statistics(hass, "ug/m3")
    await async_wait_recording_done(hass)
    api = UnitApi("ug/m3")
    api.get_feature = _down
    entry = await _setup(hass, monkeypatch, api, **{CONF_PARAMETER: "pm25_pt1h_avg", CONF_LABEL: "PM2.5"})
    await async_wait_recording_done(hass)
    assert await _statistics_unit(hass) == "ug/m3"

    del api.get_feature
    [coordinator] = entry.runtime_data.coordinators
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)

    assert await _statistics_unit(hass) == "μg/m³"

    # Statistics in FMI's spelling again are not the sensor's doing, and a later update leaves them be.
    _old_statistics(hass, "ug/m3")
    await async_wait_recording_done(hass)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)

    assert await _statistics_unit(hass) == "ug/m3"


def _down(*args, **kwargs):
    raise FMIException("FMI is down")
