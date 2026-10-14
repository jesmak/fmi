"""The no-data repair issue: when it is raised, and when it is not.

The integration decides a sensor is broken from the age of the newest value FMI
holds for it, not from how many empty updates it has seen, so these tests drive
get_feature directly and move the timestamps around.
"""

from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fmi.const import (
    CONF_LABEL,
    CONF_LANG,
    CONF_NEGATIVE_AS_ZERO,
    CONF_NO_DATA_ISSUE,
    CONF_NO_DATA_ISSUE_HOURS,
    CONF_PARAMETER,
    CONF_QUERY_ID,
    CONF_TARGET,
    CONF_TARGET_TYPE,
    DOMAIN,
    SUBENTRY_SENSOR,
)
from custom_components.fmi.query_coordinator import FMIQueryCoordinator

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

    def __init__(self, age: timedelta | None, parameters: list[str] | None = None):
        self.age = age
        self.parameters = ["t2m", "ws_10min"] if parameters is None else parameters
        self.windows: list[str | None] = []
        self.unit_lookups = 0

    def get_feature(self, lang, params, target_param, get_latest, negative_as_zero=False):
        self.windows.append(params.get("starttime"))
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
    monkeypatch.setattr("custom_components.fmi.query_coordinator.FMISession", lambda *a, **kw: api)
    options = {key: value for key, value in overrides.items() if key in STALE_DATA_SETTINGS}
    data = {**ENTRY_DATA, **{key: value for key, value in overrides.items() if key not in STALE_DATA_SETTINGS}}
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_LANG: "eng"},
        options=options,
        version=3,
        subentries_data=[
            ConfigSubentryData(data=data, subentry_type=SUBENTRY_SENSOR, title=data[CONF_LABEL], unique_id="test"),
        ],
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _coordinator(entry: MockConfigEntry) -> FMIQueryCoordinator:
    return entry.runtime_data.coordinators[next(iter(entry.subentries))]


def _issue(hass: HomeAssistant, entry: MockConfigEntry):
    return ir.async_get(hass).async_get_issue(DOMAIN, f"no_data_{next(iter(entry.subentries))}")


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
    state = hass.states.get("sensor.fmi_kaisaniemi_air_temperature")
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
