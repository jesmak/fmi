"""The no-data repair issue: when it is raised, and when it is not.

The integration decides a sensor is broken from the age of the newest value FMI
holds for it, not from how many empty updates it has seen, so these tests drive
get_feature directly and move the timestamps around.
"""

from datetime import timedelta

import pytest
from conftest import station
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fmi_open_data.const import (
    CONF_FORECAST_HOURS,
    CONF_FORECAST_PAST_HOURS,
    CONF_FORECAST_STEP,
    CONF_LABEL,
    CONF_LANG,
    CONF_NEGATIVE_AS_ZERO,
    CONF_NO_DATA_ISSUE,
    CONF_NO_DATA_ISSUE_HOURS,
    CONF_PARAMETER,
    CONF_QUERY_ID,
    CONF_STRUCTURE,
    CONF_TARGET,
    CONF_TARGET_TYPE,
    DOMAIN,
    STRUCTURE_VERSION,
)
from custom_components.fmi_open_data.query_coordinator import FMIQueryCoordinator
from custom_components.fmi_open_data.session import FMIRefused

# The harness has no asyncio_mode config of its own, so mark the module.
pytestmark = pytest.mark.asyncio

OBSERVATION_QUERY = "fmi::observations::weather::simple"
ENTRY_DATA = {
    CONF_LABEL: "Kaisaniemi Air temperature",
    CONF_LANG: "eng",
    CONF_QUERY_ID: OBSERVATION_QUERY,
    CONF_PARAMETER: "t2m",
    CONF_TARGET_TYPE: "fmisid",
    CONF_TARGET: "100971",
    CONF_NEGATIVE_AS_ZERO: False,
}


class FakeApi:
    """Stands in for FMISession, answering from an age rather than from XML.

    Records every query window it is asked for so the tests can tell the plain
    poll apart from the widened one the staleness check falls back to.
    """

    def __init__(
        self,
        age: timedelta | None,
        parameters: list[str] | None = None,
        max_window: timedelta | None = None,
        says_limit: bool = True,
    ):
        self.age = age
        self.parameters = ["t2m", "ws_10min"] if parameters is None else parameters
        # FMI refuses a longer window, and says how long it allows unless says_limit is off.
        self.max_window = max_window
        self.says_limit = says_limit
        self.windows: list[str | None] = []
        self.refusals = 0
        self.unit_lookups = 0

    def get_feature(self, lang, params, target_param, get_latest, negative_as_zero=False):
        self.windows.append(params.get("starttime"))
        start = params.get("starttime")
        # FMI measures the whole window, from its start to its end, which for a forecast lies ahead.
        end = _parse(params["endtime"]) if params.get("endtime") else dt_util.utcnow()
        if self.max_window is not None and start is not None and end - _parse(start) > self.max_window:
            self.refusals += 1
            hours = self.max_window.total_seconds() / 3600
            raise FMIRefused(
                f"Too long time interval requested! No more than {hours:f} hours allowed." if self.says_limit else "400 Bad Request"
            )
        result = {
            # FMI sends the station's coordinates only along with values.
            "latitude": None,
            "longitude": None,
            "query_id": params["storedquery_id"],
            "parameter": target_param,
            "data": [],
        }

        if self.age is None:
            return result

        time = dt_util.utcnow() - self.age
        # Mimic the real window filter: a value only comes back if it falls
        # inside the window the caller asked for.
        start = params.get("starttime")
        if start is not None and time < _parse(start):
            return result

        result.update(latitude=60.1, longitude=24.9)
        result["data"].append({"time": time, "value": "1.5"})
        return result

    def list_parameters(self, lang, params):
        return self.parameters

    def get_unit(self, *args):
        self.unit_lookups += 1
        return "°C"


def _parse(stamp: str):
    from datetime import UTC, datetime

    return datetime.strptime(stamp.replace("%20", " "), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


# Shared by every sensor, so they are options of the config entry rather than sensor data.
STALE_DATA_SETTINGS = (CONF_NO_DATA_ISSUE, CONF_NO_DATA_ISSUE_HOURS)


async def _setup(hass: HomeAssistant, monkeypatch, api: FakeApi, **overrides) -> MockConfigEntry:
    monkeypatch.setattr("custom_components.fmi_open_data.query_coordinator.FMISession", lambda *a, **kw: api)
    options = {key: value for key, value in overrides.items() if key in STALE_DATA_SETTINGS}
    data = {
        **ENTRY_DATA,
        CONF_LABEL: "Air temperature",
        **{key: value for key, value in overrides.items() if key not in STALE_DATA_SETTINGS},
    }
    measurement = {key: value for key, value in data.items() if key not in (CONF_LANG, CONF_TARGET_TYPE, CONF_TARGET)}
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_LANG: "eng", CONF_STRUCTURE: STRUCTURE_VERSION},
        options=options,
        version=3,
        subentries_data=[station(measurement, target_type=data[CONF_TARGET_TYPE], target=data[CONF_TARGET])],
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _coordinator(entry: MockConfigEntry) -> FMIQueryCoordinator:
    [coordinator] = entry.runtime_data.coordinators
    return coordinator


def _issue(hass: HomeAssistant, entry: MockConfigEntry):
    return ir.async_get(hass).async_get_issue(DOMAIN, _coordinator(entry).issue_id)


async def test_recent_observation_raises_nothing(hass: HomeAssistant, monkeypatch):
    api = FakeApi(age=timedelta(hours=1))
    entry = await _setup(hass, monkeypatch, api)

    assert _issue(hass, entry) is None


async def test_stale_observation_inside_the_poll_window_is_reported(hass: HomeAssistant, monkeypatch):
    """The case the old empty-update counter could never see.

    The poll window reaches back 12 hours, so a station quiet for 30 hours used
    to keep returning its last value and never looked broken.
    """
    api = FakeApi(age=timedelta(hours=30), parameters=["ws_10min"])
    entry = await _setup(hass, monkeypatch, api, **{CONF_NO_DATA_ISSUE_HOURS: 24})

    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.translation_key == "parameter_missing"


async def test_data_just_outside_the_poll_window_is_not_reported(hass: HomeAssistant, monkeypatch):
    """An empty poll is not proof of an outage; the widened query dates it."""
    api = FakeApi(age=timedelta(hours=13))
    entry = await _setup(hass, monkeypatch, api, **{CONF_NO_DATA_ISSUE_HOURS: 24})

    assert _issue(hass, entry) is None
    # The plain 12 h poll came back empty, so a second, wider window was asked for.
    assert len(api.windows) > 1
    # And the value it found is shown rather than nothing.
    state = hass.states.get("sensor.helsinki_kaisaniemi_air_temperature")
    assert state.state == "1.5"
    assert state.attributes["latitude"] is not None


async def test_silence_beyond_the_grace_period_is_reported(hass: HomeAssistant, monkeypatch):
    api = FakeApi(age=None, parameters=[])
    entry = await _setup(hass, monkeypatch, api, **{CONF_NO_DATA_ISSUE_HOURS: 24})

    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.translation_key == "no_data"


async def test_short_grace_period_reports_sooner(hass: HomeAssistant, monkeypatch):
    api = FakeApi(age=timedelta(hours=3), parameters=["ws_10min"])
    entry = await _setup(hass, monkeypatch, api, **{CONF_NO_DATA_ISSUE_HOURS: 2})

    assert _issue(hass, entry) is not None


async def test_disabled_reports_nothing(hass: HomeAssistant, monkeypatch):
    api = FakeApi(age=None, parameters=[])
    entry = await _setup(hass, monkeypatch, api, **{CONF_NO_DATA_ISSUE: False})

    assert _issue(hass, entry) is None


async def test_issue_clears_when_data_comes_back(hass: HomeAssistant, monkeypatch):
    api = FakeApi(age=None, parameters=[])
    entry = await _setup(hass, monkeypatch, api, **{CONF_NO_DATA_ISSUE_HOURS: 24})
    assert _issue(hass, entry) is not None

    api.age = timedelta(minutes=10)
    await _coordinator(entry).async_refresh()
    await hass.async_block_till_done()

    assert _issue(hass, entry) is None


async def test_probe_runs_once_per_outage(hass: HomeAssistant, monkeypatch):
    """The unfiltered probe is expensive, so a continuing outage must not re-run it."""
    api = FakeApi(age=None, parameters=[])
    entry = await _setup(hass, monkeypatch, api, **{CONF_NO_DATA_ISSUE_HOURS: 24})
    calls = len(api.windows)

    await _coordinator(entry).async_refresh()
    await hass.async_block_till_done()

    # One more plain poll only: no widened query, no second probe.
    assert len(api.windows) == calls + 1, api.windows


async def test_the_unit_is_looked_up_once(hass: HomeAssistant, monkeypatch):
    api = FakeApi(age=timedelta(hours=1))
    entry = await _setup(hass, monkeypatch, api)

    await _coordinator(entry).async_refresh()
    await hass.async_block_till_done()

    assert api.unit_lookups == 1
    assert _coordinator(entry).data["unit"] == "°C"


async def test_switching_the_issues_off_clears_one_already_raised(hass: HomeAssistant, monkeypatch):
    api = FakeApi(age=None, parameters=[])
    entry = await _setup(hass, monkeypatch, api, **{CONF_NO_DATA_ISSUE_HOURS: 24})
    assert _issue(hass, entry) is not None

    hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_NO_DATA_ISSUE: False})
    await hass.async_block_till_done()

    assert _issue(hass, entry) is None


async def test_with_the_issues_off_an_outage_costs_one_query_per_poll(hass: HomeAssistant, monkeypatch):
    api = FakeApi(age=None, parameters=[])
    entry = await _setup(hass, monkeypatch, api, **{CONF_NO_DATA_ISSUE: False, CONF_NO_DATA_ISSUE_HOURS: 24})
    calls = len(api.windows)

    await _coordinator(entry).async_refresh()
    await _coordinator(entry).async_refresh()
    await hass.async_block_till_done()

    assert len(api.windows) == calls + 2, api.windows


SENSOR = "sensor.helsinki_kaisaniemi_air_temperature"
STALE_SENSOR = "binary_sensor.helsinki_kaisaniemi_air_temperature_stale_data"
WEEK = timedelta(hours=168)


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await _coordinator(entry).async_refresh()
    await hass.async_block_till_done()


# FMI lets the 10-minute observations reach back a week. A stale limit below that is checked as it is. Above it, the
# check learns FMI's limit from its refusal and goes no further: data older than FMI shows can't be dated, so a week of
# silence counts as stale. A refusal that doesn't say the limit dates nothing, and says nothing.
@pytest.mark.parametrize(
    ("limit_hours", "says_limit", "age", "stale", "shown", "refusals"),
    [
        (100, True, timedelta(hours=50), "off", "1.5", 0),
        (100, True, None, "on", "unknown", 0),
        (200, True, timedelta(hours=100), "off", "1.5", 1),
        (200, True, timedelta(hours=180), "on", "unknown", 1),
        (200, True, timedelta(hours=300), "on", "unknown", 1),
        (200, True, None, "on", "unknown", 1),
        (200, False, timedelta(hours=100), "off", "unknown", 1),
        (200, False, None, "off", "unknown", 1),
    ],
)
async def test_the_stale_check_reaches_back_only_as_far_as_fmi_allows(
    hass: HomeAssistant,
    monkeypatch,
    limit_hours: int,
    says_limit: bool,
    age: timedelta | None,
    stale: str,
    shown: str,
    refusals: int,
):
    api = FakeApi(age=age, max_window=WEEK, says_limit=says_limit)
    entry = await _setup(hass, monkeypatch, api, **{CONF_NO_DATA_ISSUE_HOURS: limit_hours})

    assert hass.states.get(STALE_SENSOR).state == stale
    assert hass.states.get(SENSOR).state == shown
    assert api.refusals == refusals
    # The station still lists the parameter, so a stale sensor is all there is to it.
    assert _issue(hass, entry) is None


async def test_fmis_limit_is_asked_for_once(hass: HomeAssistant, monkeypatch):
    api = FakeApi(age=timedelta(hours=100), max_window=WEEK)
    entry = await _setup(hass, monkeypatch, api, **{CONF_NO_DATA_ISSUE_HOURS: 200})

    await _refresh(hass, entry)

    assert api.refusals == 1
    assert hass.states.get(SENSOR).state == "1.5"


async def test_the_learned_limit_serves_the_next_outage(hass: HomeAssistant, monkeypatch):
    api = FakeApi(age=timedelta(hours=100), max_window=WEEK)
    entry = await _setup(hass, monkeypatch, api, **{CONF_NO_DATA_ISSUE_HOURS: 200})
    api.age = timedelta(minutes=10)
    await _refresh(hass, entry)
    assert hass.states.get(STALE_SENSOR).state == "off"

    api.age = None
    await _refresh(hass, entry)

    assert hass.states.get(STALE_SENSOR).state == "on"
    assert api.refusals == 1


async def test_a_learned_limit_refused_again_says_nothing(hass: HomeAssistant, monkeypatch):
    """FMI lowering its limit later is not learned again, and costs one refusal a poll rather than a loop."""
    api = FakeApi(age=timedelta(hours=100), max_window=WEEK)
    entry = await _setup(hass, monkeypatch, api, **{CONF_NO_DATA_ISSUE_HOURS: 200})
    api.max_window = timedelta(hours=72)
    api.age = None

    await _refresh(hass, entry)

    assert hass.states.get(STALE_SENSOR).state == "off"
    assert api.refusals == 2


# A forecast's window also runs its 36 hours ahead, and FMI's limit is on the whole of it, so with a week's limit the
# check reaches back only about 132 hours. The sensor shows only what lies ahead, so a past value found stays unshown.
@pytest.mark.parametrize(
    ("age", "stale"),
    [
        (timedelta(hours=100), "off"),
        (timedelta(hours=150), "on"),
        (None, "on"),
    ],
)
async def test_a_forecast_leaves_room_for_the_hours_ahead(hass: HomeAssistant, monkeypatch, age: timedelta | None, stale: str):
    api = FakeApi(age=age, max_window=WEEK)
    entry = await _setup(
        hass,
        monkeypatch,
        api,
        **{
            CONF_QUERY_ID: "fmi::forecast::harmonie::surface::point::simple",
            CONF_FORECAST_HOURS: 36,
            CONF_FORECAST_PAST_HOURS: 5,
            CONF_FORECAST_STEP: 30,
            CONF_NO_DATA_ISSUE_HOURS: 200,
        },
    )

    assert hass.states.get(STALE_SENSOR).state == stale
    assert hass.states.get(SENSOR).state == "unknown"
    assert api.refusals == 1
    assert _issue(hass, entry) is None
