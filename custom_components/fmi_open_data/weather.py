"""The weather entity of a weather place: the hour under way, and hourly, daily and twice-daily forecasts."""

from typing import Any

from homeassistant.components.weather import Forecast, SingleCoordinatorWeatherEntity, WeatherEntityFeature
from homeassistant.const import UnitOfPrecipitationDepth, UnitOfPressure, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import ATTRIBUTION, CONF_LABEL
from .weather_coordinator import (
    FMIWeatherCoordinator,
    condition_for,
    current_row,
    daily_forecast,
    hourly_forecast,
    twice_daily_forecast,
)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    for subentry_id, coordinator in entry.runtime_data.coordinators.items():
        if isinstance(coordinator, FMIWeatherCoordinator):
            async_add_entities([FMIWeather(coordinator)], config_subentry_id=subentry_id)


class FMIWeather(SingleCoordinatorWeatherEntity[FMIWeatherCoordinator]):
    _attr_attribution = ATTRIBUTION
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_HOURLY | WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_TWICE_DAILY
    )

    def __init__(self, coordinator: FMIWeatherCoordinator):
        super().__init__(coordinator)
        self._attr_unique_id = coordinator.subentry.subentry_id
        self._attr_name = f"FMI {coordinator.subentry.data.get(CONF_LABEL, coordinator.subentry.title)}"

    def _now(self, key: str) -> Any:
        row = current_row(self.coordinator.data or [], dt_util.utcnow())
        return row[key] if row is not None else None

    @property
    def condition(self) -> str | None:
        return condition_for(self._now("SmartSymbol"))

    @property
    def native_temperature(self) -> float | None:
        return self._now("Temperature")

    @property
    def native_apparent_temperature(self) -> float | None:
        return self._now("FeelsLike")

    @property
    def native_dew_point(self) -> float | None:
        return self._now("DewPoint")

    @property
    def humidity(self) -> float | None:
        return self._now("Humidity")

    @property
    def native_pressure(self) -> float | None:
        return self._now("Pressure")

    @property
    def native_wind_speed(self) -> float | None:
        return self._now("WindSpeedMS")

    @property
    def wind_bearing(self) -> float | None:
        return self._now("WindDirection")

    @property
    def native_wind_gust_speed(self) -> float | None:
        return self._now("HourlyMaximumGust")

    @property
    def cloud_coverage(self) -> int | None:
        value = self._now("TotalCloudCover")
        return round(value) if value is not None else None

    @callback
    def _async_forecast_hourly(self) -> list[Forecast] | None:
        return hourly_forecast(self.coordinator.data or [], dt_util.utcnow())

    @callback
    def _async_forecast_daily(self) -> list[Forecast] | None:
        return daily_forecast(self.coordinator.data or [], dt_util.utcnow())

    @callback
    def _async_forecast_twice_daily(self) -> list[Forecast] | None:
        return twice_daily_forecast(self.coordinator.data or [], dt_util.utcnow())
