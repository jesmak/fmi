import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

# What setup reads from FMI to name the devices and, once, the sensors. Made up, but shaped like FMI's answers.
STATIONS = [{"id": "100971", "name": "Helsinki Kaisaniemi", "region": "Helsinki", "latitude": 60.17523, "longitude": 24.94459}]
DESCRIPTIONS = {"t2m": ("Air temperature", "°C"), "ws_10min": ("Wind speed", "m/s")}


class FakeMetadata:
    """Stands in for FMISession where setup uses it: the station list and the parameters' descriptions."""

    def list_stations(self, lang):
        return STATIONS

    def get_parameter_descriptions(self, lang, query_id):
        return DESCRIPTIONS


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/fmi_open_data during tests."""
    yield


@pytest.fixture(autouse=True)
def fake_metadata(monkeypatch):
    monkeypatch.setattr("custom_components.fmi_open_data.structure.FMISession", FakeMetadata)


def station(*measurements: dict, title: str = "Helsinki Kaisaniemi", target_type: str = "fmisid", target: str = "100971"):
    """A station subentry of 4.0.0 with the given measurements."""
    from homeassistant.config_entries import ConfigSubentryData

    from custom_components.fmi_open_data.const import CONF_MEASUREMENTS, CONF_TARGET, CONF_TARGET_TYPE, SUBENTRY_STATION
    from custom_components.fmi_open_data.query_coordinator import station_unique_id

    return ConfigSubentryData(
        data={CONF_TARGET_TYPE: target_type, CONF_TARGET: target, CONF_MEASUREMENTS: list(measurements)},
        subentry_type=SUBENTRY_STATION,
        title=title,
        unique_id=station_unique_id(target_type, target),
    )


def place(label: str, latitude: float, longitude: float, radius: float = 0, weather: bool = False, warning_types=None):
    """A place subentry of 4.0.0. It follows every warning type unless told otherwise."""
    from homeassistant.config_entries import ConfigSubentryData

    from custom_components.fmi_open_data.const import (
        CONF_LABEL,
        CONF_LOCATION,
        CONF_WARNING_TYPES,
        CONF_WEATHER,
        SUBENTRY_PLACE,
        WARNING_TYPES,
    )
    from custom_components.fmi_open_data.structure import place_unique_id

    location = {"latitude": latitude, "longitude": longitude, "radius": radius}
    return ConfigSubentryData(
        data={
            CONF_LOCATION: location,
            CONF_LABEL: label,
            CONF_WEATHER: weather,
            CONF_WARNING_TYPES: WARNING_TYPES if warning_types is None else warning_types,
        },
        subentry_type=SUBENTRY_PLACE,
        title=label,
        unique_id=place_unique_id(location),
    )
