"""A weather place: the forecast parser, the periods made from it, the weather entity and its subentry flow."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import place
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fmi_open_data.const import CONF_LANG, CONF_STRUCTURE, DOMAIN, STRUCTURE_VERSION
from custom_components.fmi_open_data.session import FMIException, FMINoData, FMISession
from custom_components.fmi_open_data.weather_coordinator import (
    PARAMETERS,
    condition_for,
    daily_forecast,
    hourly_forecast,
    twice_daily_forecast,
)

# A real response for Tampere, fetched at 2026-10-15T15:08Z: values up to 2026-10-25T00:00Z, NaN after that.
FORECAST = (Path(__file__).parent / "fixtures" / "fmi_forecast.xml").read_bytes()
NOW = "2026-10-15T15:30:00+00:00"
TAMPERE = {"latitude": 61.4981, "longitude": 23.7608}
ENTITY = "weather.saa"

# Every day code in FMI's SmartSymbol documentation.
SYMBOLS = [1, 2, 4, 6, 7, 9, 11, 14, 17, 21, 24, 27, *range(31, 40), *range(41, 50), *range(51, 60), 61, 64, 67, 71, 74, 77]


class FakeSession(FMISession):
    """Serves the fixture, or fails, and remembers what was asked."""

    def __init__(self, failing: bool = False, no_data: bool = False):
        super().__init__()
        self.failing = failing
        self.no_data = no_data
        self.urls: list[str] = []

    def get_document(self, url: str) -> bytes:
        self.urls.append(url)
        if self.no_data:
            raise FMINoData("FMI has no data for the request")
        if self.failing:
            raise FMIException("Timeout error")
        return FORECAST


@pytest.fixture
async def helsinki(hass: HomeAssistant):
    await hass.config.async_set_time_zone("Europe/Helsinki")


def _rows() -> list[dict]:
    rows = FakeSession().get_coverage("eng", {})
    return [row for row in rows if row["Temperature"] is not None]


def _row(time: str, symbol: float = 1, temperature: float = 5) -> dict:
    return {
        **dict.fromkeys(PARAMETERS),
        "time": datetime.fromisoformat(time),
        "SmartSymbol": symbol,
        "Temperature": temperature,
        "Precipitation1h": 0.1,
    }


def _hours(start: str, count: int) -> list[dict]:
    first = datetime.fromisoformat(start)
    return [_row((first + timedelta(hours=hour)).isoformat()) for hour in range(count)]


def _use(monkeypatch, session: FakeSession) -> None:
    monkeypatch.setattr("custom_components.fmi_open_data.weather_coordinator.FMISession", lambda *a, **kw: session)


async def _setup(hass: HomeAssistant, monkeypatch, session: FakeSession) -> MockConfigEntry:
    _use(monkeypatch, session)
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        data={CONF_LANG: "fin", CONF_STRUCTURE: STRUCTURE_VERSION},
        subentries_data=[place("Sää", TAMPERE["latitude"], TAMPERE["longitude"], weather=True, warning_types=[])],
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _forecast(hass: HomeAssistant, kind: str) -> list[dict]:
    response = await hass.services.async_call(
        "weather", "get_forecasts", {"entity_id": ENTITY, "type": kind}, blocking=True, return_response=True
    )
    return response[ENTITY]["forecast"]


def test_every_documented_symbol_has_a_condition():
    for code in SYMBOLS:
        assert condition_for(code) is not None, code
        assert condition_for(code + 100) is not None, code + 100


def test_conditions_by_day_and_night():
    assert condition_for(1) == "sunny"
    assert condition_for(101) == "clear-night"
    assert condition_for(107) == "cloudy"
    assert condition_for(39) == "pouring"
    assert condition_for(47) == "snowy-rainy"
    assert condition_for(158) == "snowy"
    assert condition_for(177) == "lightning-rainy"
    assert condition_for(None) is None


def test_an_unknown_symbol_leaves_the_condition_empty(caplog):
    assert condition_for(3) is None
    assert condition_for(103) is None
    assert condition_for(3) is None
    assert caplog.text.count("symbol 3 is not known") == 1
    assert caplog.text.count("symbol 103 is not known") == 1


def test_the_coverage_is_read_as_one_row_per_hour():
    rows = FakeSession().get_coverage("eng", {})

    assert len(rows) == 241
    assert rows[0] == {
        "time": datetime(2026, 10, 15, 15, tzinfo=UTC),
        "Temperature": 10.75,
        "FeelsLike": 6.831464,
        "DewPoint": 8.16,
        "Humidity": 83.9,
        "Pressure": 1019.7,
        "WindSpeedMS": 6.1,
        "WindDirection": 193.0,
        "HourlyMaximumGust": 9.9,
        "TotalCloudCover": 93.1,
        "Precipitation1h": 0.0,
        "PoP": 0.0,
        "SmartSymbol": 7.0,
    }
    assert rows[-1]["time"] == datetime(2026, 10, 25, 15, tzinfo=UTC)
    assert rows[-1]["Temperature"] is None


def test_a_value_that_is_not_a_number_is_refused():
    session = FakeSession()
    session.get_document = lambda url: FORECAST.replace(b"10.75 6.831464", b"10.75 x")
    with pytest.raises(FMIException, match="x as FeelsLike"):
        session.get_coverage("eng", {})


def test_a_place_outside_fmis_area_is_told_apart_from_a_failure(monkeypatch):
    responses = {
        "outside": SimpleNamespace(
            status_code=400, reason="Bad Request", content=b"<ExceptionText>No data available for &apos;0,0&apos;!</ExceptionText>"
        ),
        "broken": SimpleNamespace(status_code=400, reason="Bad Request", content=b"<ExceptionText>Invalid parameter</ExceptionText>"),
    }
    monkeypatch.setattr("custom_components.fmi_open_data.session.requests.get", lambda url, **kw: responses[url])

    with pytest.raises(FMINoData):
        FMISession().get_document("outside")
    with pytest.raises(FMIException) as failure:
        FMISession().get_document("broken")
    assert not isinstance(failure.value, FMINoData)


def test_a_response_with_values_missing_is_refused():
    session = FakeSession()
    session.get_document = lambda url: FORECAST.replace(b"10.75 6.831464", b"10.75")
    with pytest.raises(FMIException):
        session.get_coverage("eng", {})


async def test_the_hourly_forecast_starts_from_the_hour_under_way(hass: HomeAssistant, helsinki):
    forecast = hourly_forecast(_rows(), datetime.fromisoformat("2026-10-15T16:20:00+00:00"))

    assert forecast[0]["datetime"] == "2026-10-15T16:00:00+00:00"
    assert forecast[-1]["datetime"] == "2026-10-25T00:00:00+00:00"
    assert forecast[0]["is_daytime"] is False


async def test_days_take_their_condition_from_14_and_end_with_the_data(hass: HomeAssistant, helsinki):
    rows = _rows()
    forecast = daily_forecast(rows, datetime.fromisoformat(NOW))

    # Today from 18:00 on, then whole days up to the 24th: the 25th has no 14:00.
    assert [day["datetime"][:10] for day in forecast] == [f"2026-10-{day}" for day in range(15, 25)]
    assert forecast[0]["datetime"] == "2026-10-15T00:00:00+03:00"
    tomorrow = [row for row in rows if datetime(2026, 10, 15, 21, tzinfo=UTC) <= row["time"] < datetime(2026, 10, 16, 21, tzinfo=UTC)]
    at_14 = next(row for row in tomorrow if row["time"] == datetime(2026, 10, 16, 11, tzinfo=UTC))
    assert forecast[1]["condition"] == condition_for(at_14["SmartSymbol"])
    assert forecast[1]["native_wind_speed"] == at_14["WindSpeedMS"]
    assert forecast[1]["native_temperature"] == max(row["Temperature"] for row in tomorrow)
    assert forecast[1]["native_templow"] == min(row["Temperature"] for row in tomorrow)
    # Each row's precipitation fell in the hour before it, so the day's rain is in the rows from 01:00 to 00:00.
    rained = [row for row in rows if datetime(2026, 10, 15, 21, tzinfo=UTC) < row["time"] <= datetime(2026, 10, 16, 21, tzinfo=UTC)]
    assert forecast[1]["native_precipitation"] == round(sum(row["Precipitation1h"] for row in rained), 2)
    assert "is_daytime" not in forecast[1]


async def test_today_after_14_uses_its_nearest_hour(hass: HomeAssistant, helsinki):
    rows = _rows()
    forecast = daily_forecast(rows, datetime.fromisoformat(NOW))

    assert forecast[0]["condition"] == condition_for(rows[0]["SmartSymbol"])


async def test_halves_alternate_from_tonight_to_the_end_of_the_data(hass: HomeAssistant, helsinki):
    forecast = twice_daily_forecast(_rows(), datetime.fromisoformat(NOW))

    # The night of the 15th, then a day and a night each up to the night of the 24th, whose 02:00 is the last hour.
    assert len(forecast) == 19
    assert forecast[0]["datetime"] == "2026-10-15T18:00:00+03:00"
    assert forecast[1]["datetime"] == "2026-10-16T06:00:00+03:00"
    assert forecast[-1]["datetime"] == "2026-10-24T18:00:00+03:00"
    assert [half["is_daytime"] for half in forecast] == [index % 2 == 1 for index in range(19)]


async def test_a_night_half_takes_its_condition_from_02(hass: HomeAssistant, helsinki):
    rows = _hours("2026-10-15T15:00:00+00:00", 24)
    rows[8]["SmartSymbol"] = 177  # 2026-10-15T23:00Z is 02:00 in Helsinki
    forecast = twice_daily_forecast(rows, datetime.fromisoformat("2026-10-15T15:00:00+00:00"))

    assert forecast[0]["condition"] == "lightning-rainy"


async def test_14_stays_14_over_the_change_from_summer_time(hass: HomeAssistant, helsinki):
    # Summer time ends on 2026-10-25, so on the 26th 14:00 in Helsinki is 12:00 UTC, not 11:00.
    rows = _hours("2026-10-24T00:00:00+00:00", 72)
    by_time = {row["time"]: row for row in rows}
    by_time[datetime(2026, 10, 26, 11, tzinfo=UTC)]["SmartSymbol"] = 33
    by_time[datetime(2026, 10, 26, 12, tzinfo=UTC)]["SmartSymbol"] = 77
    forecast = daily_forecast(rows, datetime.fromisoformat("2026-10-24T00:00:00+00:00"))

    day = next(day for day in forecast if day["datetime"].startswith("2026-10-26"))
    assert day["datetime"] == "2026-10-26T00:00:00+02:00"
    assert day["condition"] == "lightning-rainy"


async def test_rain_counts_in_the_period_it_fell_in(hass: HomeAssistant, helsinki):
    rows = _hours("2026-10-15T15:00:00+00:00", 36)
    for row in rows:
        row["Precipitation1h"] = 0
    by_time = {row["time"]: row for row in rows}
    # The hour from 23:00 to midnight in Helsinki, and the one after it.
    by_time[datetime(2026, 10, 15, 21, tzinfo=UTC)]["Precipitation1h"] = 2.0
    by_time[datetime(2026, 10, 15, 22, tzinfo=UTC)]["Precipitation1h"] = 0.5
    forecast = daily_forecast(rows, datetime.fromisoformat("2026-10-15T15:00:00+00:00"))

    assert [day["native_precipitation"] for day in forecast[:2]] == [2.0, 0.5]


async def test_a_night_skipped_by_the_clocks_keeps_its_half(hass: HomeAssistant):
    # In Stockholm the clocks go from 02:00 to 03:00 on 2027-03-28, so that night has no 02:00.
    await hass.config.async_set_time_zone("Europe/Stockholm")
    rows = _hours("2027-03-27T12:00:00+00:00", 30)
    forecast = twice_daily_forecast(rows, datetime.fromisoformat("2027-03-27T12:00:00+00:00"))

    assert [half["datetime"] for half in forecast] == [
        "2027-03-27T06:00:00+01:00",
        "2027-03-27T18:00:00+01:00",
        "2027-03-28T06:00:00+02:00",
    ]


async def test_the_entity_shows_the_hour_under_way(hass: HomeAssistant, monkeypatch, freezer, helsinki, caplog):
    freezer.move_to(NOW)
    session = FakeSession()
    await _setup(hass, monkeypatch, session)

    # Every platform goes through the weather place's coordinator, and none may trip over it.
    assert "Error while setting up" not in caplog.text

    state = hass.states.get(ENTITY)
    assert state.state == "cloudy"
    assert state.attributes["temperature"] == 10.8
    assert state.attributes["humidity"] == 84
    assert state.attributes["wind_bearing"] == 193.0
    assert state.attributes["cloud_coverage"] == 93
    assert "latlon=61.4981,23.7608" in session.urls[0]
    assert "starttime=2026-10-15%2015:00:00" in session.urls[0]


async def test_the_entity_serves_every_kind_of_forecast(hass: HomeAssistant, monkeypatch, freezer, helsinki):
    freezer.move_to(NOW)
    await _setup(hass, monkeypatch, FakeSession())

    assert len(await _forecast(hass, "hourly")) == 226
    assert len(await _forecast(hass, "daily")) == 10
    assert len(await _forecast(hass, "twice_daily")) == 19


async def test_the_entity_is_unavailable_while_fmi_cannot_be_reached(hass: HomeAssistant, monkeypatch, freezer, helsinki):
    freezer.move_to(NOW)
    await _setup(hass, monkeypatch, FakeSession(failing=True))

    assert hass.states.get(ENTITY).state == "unavailable"


async def test_the_last_forecast_is_kept_for_a_while_when_fmi_fails(hass: HomeAssistant, monkeypatch, freezer, helsinki):
    freezer.move_to(NOW)
    session = FakeSession()
    entry = await _setup(hass, monkeypatch, session)
    [coordinator] = entry.runtime_data.coordinators
    session.failing = True

    freezer.tick(timedelta(hours=2))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).state != "unavailable"
    assert len(await _forecast(hass, "hourly")) == 224

    freezer.tick(timedelta(hours=1))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).state == "unavailable"
