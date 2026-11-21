"""Each measurement gets an icon by the kind of its parameter."""

import json
from pathlib import Path

import pytest

from custom_components.fmi_open_data.icons import _RULES, KIND_OTHER, parameter_kind

ICONS = Path(__file__).parent.parent / "custom_components" / "fmi_open_data" / "icons.json"


@pytest.mark.parametrize(
    ("parameter", "kind"),
    [
        ("TA_PT1H_AVG", "temperature"),
        ("t2m", "temperature"),
        ("Temperature", "temperature"),
        ("TW_PT1H_AVG", "water_temperature"),
        ("TWATER", "water_temperature"),
        ("TemperatureSea", "water_temperature"),
        ("TD_PT10M_AVG", "dew_point"),
        ("TS_PT1H_AVG", "ground_temperature"),
        ("RH_PT1H_AVG", "humidity"),
        ("PA_PT1H_AVG", "pressure"),
        ("WS_PT10M_AVG", "wind_speed"),
        ("WindSpeedMS", "wind_speed"),
        ("WG_PT1H_MAX", "wind_gust"),
        ("WGENL_PT1H_AVG", KIND_OTHER),
        ("WD_PT10M_AVG", "wind_direction"),
        ("PRA_PT1H_ACC", "precipitation"),
        ("rrday", "precipitation"),
        ("RRCODE_PT24H_RANK", KIND_OTHER),
        ("PRI_PT10M_AVG", "precipitation_intensity"),
        ("snow_aws", "snow"),
        ("SND_PT1M_INSTANT", "snow"),
        ("ICE_PT1S_INSTANT", "ice"),
        ("SNOW_ICE_PT1S_INSTANT", "ice"),
        ("SNDICE_PT1M_AVG", "snow_on_ice"),
        ("n_man", "cloud_cover"),
        ("CLHB_PT1M_INSTANT", "cloud_base"),
        ("VIS_PT1M_AVG", "visibility"),
        ("GLOB_PT1M_AVG", "solar_radiation"),
        ("UVB_U", "uv"),
        ("SUND_PT1H_SUM", "sunshine"),
        ("WLEVN2K_PT1S_INSTANT", "water_level"),
        ("SeaLevelN2000", "water_level"),
        ("WaveHs", "waves"),
        ("DR_PT10M_AVG", "radioactivity"),
        ("Cs-137", "radioactivity"),
        ("PM25_PT1H_AVG", "air_quality"),
        ("AQINDEX_PT1H_AVG", "air_quality"),
        ("TRSC_PT1H_AVG", "air_quality"),
        ("QBENZENE_PT1S_AVG", "air_quality"),
        ("IceConcentration", "ice"),
        ("MAGNX_PT10S_AVG", "magnetic_field"),
        ("KELI", KIND_OTHER),
    ],
)
def test_a_parameter_gets_the_kind_of_its_family(parameter: str, kind: str):
    assert parameter_kind(parameter) == kind


def test_every_kind_has_an_icon():
    sensors = json.loads(ICONS.read_text(encoding="utf-8"))["entity"]["sensor"]
    assert set(sensors) == {kind for kind, _ in _RULES} | {KIND_OTHER}
