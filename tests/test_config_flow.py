"""Setting up the integration, and the stale data settings shared by every sensor."""

from datetime import timedelta

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from test_no_data import FakeApi, _setup

from custom_components.fmi_open_data.const import CONF_LANG, CONF_NO_DATA_ISSUE, CONF_NO_DATA_ISSUE_HOURS, DOMAIN

pytestmark = pytest.mark.asyncio


async def test_setting_up_the_integration(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LANG: "fin"})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "FMI"
    assert result["data"] == {CONF_LANG: "fin"}
    assert result["options"] == {CONF_NO_DATA_ISSUE: True, CONF_NO_DATA_ISSUE_HOURS: 24}


async def test_the_integration_is_set_up_only_once(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LANG: "fin"})
    await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_changing_the_stale_data_settings_applies_to_the_sensors(hass: HomeAssistant, monkeypatch):
    entry = await _setup(hass, monkeypatch, FakeApi(age=timedelta(hours=30)), **{CONF_NO_DATA_ISSUE_HOURS: 24})
    stale_sensor = "binary_sensor.fmi_kaisaniemi_air_temperature_stale_data"
    assert hass.states.get(stale_sensor).state == "on"

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_NO_DATA_ISSUE: False, CONF_NO_DATA_ISSUE_HOURS: 120}
    )
    await hass.async_block_till_done()

    assert entry.options == {CONF_NO_DATA_ISSUE: False, CONF_NO_DATA_ISSUE_HOURS: 120}
    state = hass.states.get(stale_sensor)
    assert state.state == "off"
    assert state.attributes["no_data_issue_hours"] == 120
