"""The diagnostic stale data binary sensor of observation and forecast sensors.

It follows the same age check as the no-data repair issue, but works whether or
not the issue is enabled.
"""
from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant

from custom_components.fmi.const import CONF_NO_DATA_ISSUE, CONF_NO_DATA_ISSUE_HOURS, DOMAIN
from test_no_data import FakeApi, _issue, _setup

pytestmark = pytest.mark.asyncio

STALE_SENSOR = "binary_sensor.fmi_kaisaniemi_air_temperature_stale_data"


async def test_recent_data_is_not_stale(hass: HomeAssistant, monkeypatch):
    await _setup(hass, monkeypatch, FakeApi(age=timedelta(hours=1)))

    state = hass.states.get(STALE_SENSOR)
    assert state.state == "off"
    assert state.attributes["device_class"] == "problem"


async def test_old_data_is_stale(hass: HomeAssistant, monkeypatch):
    await _setup(hass, monkeypatch, FakeApi(age=timedelta(hours=30)), **{CONF_NO_DATA_ISSUE_HOURS: 24})

    assert hass.states.get(STALE_SENSOR).state == "on"


async def test_stale_data_is_reported_even_with_the_repair_issue_off(hass: HomeAssistant, monkeypatch):
    api = FakeApi(age=None, parameters=[])
    entry = await _setup(hass, monkeypatch, api, **{CONF_NO_DATA_ISSUE: False})

    assert hass.states.get(STALE_SENSOR).state == "on"
    assert _issue(hass, entry) is None


async def test_stale_turns_off_when_data_comes_back(hass: HomeAssistant, monkeypatch):
    api = FakeApi(age=None, parameters=[])
    entry = await _setup(hass, monkeypatch, api, **{CONF_NO_DATA_ISSUE_HOURS: 24})
    assert hass.states.get(STALE_SENSOR).state == "on"

    api.age = timedelta(minutes=10)
    await hass.data[DOMAIN][entry.entry_id].async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(STALE_SENSOR).state == "off"
