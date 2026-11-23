"""Home Assistant's device class and unit for a measurement, by its parameter and FMI's unit.

A parameter's kind (icons.py) isn't enough on its own: FMI gives a wind direction's frequency in %, an exceedance of an
air quality limit in ug/m3, and the spread of the wind direction in degrees. So a device class is given only when the
unit is one Home Assistant accepts for it, which keeps any mismatch from logging a warning.
"""

import re
from functools import partial

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import STATISTIC_UNIT_TO_UNIT_CONVERTER, get_metadata
from homeassistant.components.sensor import DEVICE_CLASS_UNITS, SensorDeviceClass, SensorStateClass
from homeassistant.components.sensor.const import UNIT_CONVERTERS
from homeassistant.core import HomeAssistant

from .icons import parameter_kind

# FMI's spellings of units that Home Assistant spells otherwise. Home Assistant's micro is the Greek mu (U+03BC), not
# the micro sign (U+00B5), which a user may have typed as a unit of their own.
_UNITS = {
    "ug/m3": "μg/m³",
    "µg/m³": "μg/m³",
    "W/m2": "W/m²",
    "kt": "kn",
    "deg": "°",
    "degrees": "°",
}

_BY_KIND = {
    "temperature": SensorDeviceClass.TEMPERATURE,
    "dew_point": SensorDeviceClass.TEMPERATURE,
    "ground_temperature": SensorDeviceClass.TEMPERATURE,
    "water_temperature": SensorDeviceClass.TEMPERATURE,
    "humidity": SensorDeviceClass.HUMIDITY,
    "pressure": SensorDeviceClass.ATMOSPHERIC_PRESSURE,
    "wind_speed": SensorDeviceClass.WIND_SPEED,
    "wind_gust": SensorDeviceClass.WIND_SPEED,
    "wind_direction": SensorDeviceClass.WIND_DIRECTION,
    "precipitation": SensorDeviceClass.PRECIPITATION,
    "precipitation_intensity": SensorDeviceClass.PRECIPITATION_INTENSITY,
    "solar_radiation": SensorDeviceClass.IRRADIANCE,
    "sunshine": SensorDeviceClass.DURATION,
    # Lengths: by their unit only the heights of the waves, not their periods or directions.
    "snow": SensorDeviceClass.DISTANCE,
    "snow_on_ice": SensorDeviceClass.DISTANCE,
    "ice": SensorDeviceClass.DISTANCE,
    "water_level": SensorDeviceClass.DISTANCE,
    "waves": SensorDeviceClass.DISTANCE,
    "visibility": SensorDeviceClass.DISTANCE,
    "cloud_base": SensorDeviceClass.DISTANCE,
}

# The pollutants Home Assistant has a class for, from the urban air quality queries and the forecasts. The EMEP
# filters' compounds start with q and get none.
_AIR_QUALITY = [
    (SensorDeviceClass.AQI, r"aqindex"),
    (SensorDeviceClass.PM25, r"pm25"),
    (SensorDeviceClass.PM10, r"pm10"),
    (SensorDeviceClass.NITROGEN_DIOXIDE, r"no2"),
    (SensorDeviceClass.NITROGEN_MONOXIDE, r"no(_|concentration)"),
    (SensorDeviceClass.OZONE, r"o3"),
    (SensorDeviceClass.SULPHUR_DIOXIDE, r"so2"),
    (SensorDeviceClass.CO, r"co(_|concentration)"),
]
_AIR_QUALITY_COMPILED = [(device_class, re.compile(pattern)) for device_class, pattern in _AIR_QUALITY]


def _device_class(parameter: str) -> SensorDeviceClass | None:
    name = parameter.lower()
    kind = parameter_kind(name)
    if kind == "air_quality":
        # An exceedance of a limit is not a concentration.
        if "exceed" in name:
            return None
        return next((device_class for device_class, pattern in _AIR_QUALITY_COMPILED if pattern.match(name)), None)
    if kind == "wind_direction" and "_std" in name:
        # The spread of the direction, which an angle's average would garble.
        return None
    return _BY_KIND.get(kind)


def sensor_class(parameter: str, unit: str | None) -> tuple[SensorDeviceClass | None, str | None]:
    """The device class and Home Assistant's unit for the parameter in FMI's unit, or a unit the user gave."""
    unit = _UNITS.get(unit, unit) if unit else None
    device_class = _device_class(parameter)
    if device_class is SensorDeviceClass.AQI:
        # An index has no unit in Home Assistant, while FMI gives one as "index" or "".
        return device_class, None
    if device_class is None or unit not in DEVICE_CLASS_UNITS[device_class]:
        return None, unit
    return device_class, unit


def state_class(device_class: SensorDeviceClass | None) -> SensorStateClass:
    # Home Assistant takes a direction's statistics only as an angle, averaged around the circle.
    return SensorStateClass.MEASUREMENT_ANGLE if device_class is SensorDeviceClass.WIND_DIRECTION else SensorStateClass.MEASUREMENT


def _unit_class(device_class: SensorDeviceClass | None, unit: str | None) -> str | None:
    """The unit class the sensor recorder gives the statistics, by the same rule: the device class's, then the unit's."""
    if device_class and (converter := UNIT_CONVERTERS.get(device_class)) and unit in converter.VALID_UNITS:
        return converter.UNIT_CLASS
    if converter := STATISTIC_UNIT_TO_UNIT_CONVERTER.get(unit):
        return converter.UNIT_CLASS
    return None


async def async_relabel_statistics(
    hass: HomeAssistant, statistic_id: str, device_class: SensorDeviceClass | None, old_unit: str | None, new_unit: str | None
) -> None:
    """Statistics recorded in FMI's spelling of a unit get Home Assistant's.

    The values are the same, but without this the recorder takes the new spelling for a unit change it can't convert,
    and stops the sensor's statistics until the user fixes them in a repair.
    """
    if old_unit == new_unit or "recorder" not in hass.config.components:
        return
    instance = get_instance(hass)
    metadata = await instance.async_add_executor_job(partial(get_metadata, hass, statistic_ids={statistic_id}))
    if statistic_id in metadata and metadata[statistic_id][1]["unit_of_measurement"] == old_unit:
        # The recorder changes the unit only along with its class, and silently does nothing without one.
        instance.async_update_statistics_metadata(
            statistic_id, new_unit_class=_unit_class(device_class, new_unit), new_unit_of_measurement=new_unit
        )
