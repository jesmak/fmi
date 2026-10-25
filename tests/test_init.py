"""Setting up: a change saved while setup runs."""

from __future__ import annotations

from types import MappingProxyType

import pytest
from conftest import place
from homeassistant.config_entries import ConfigEntryState, ConfigSubentry
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fmi_open_data.const import CONF_LANG, CONF_NO_DATA_ISSUE, CONF_STRUCTURE, DOMAIN, STRUCTURE_VERSION
from custom_components.fmi_open_data.migration import CONF_MOVE_FROM


@pytest.mark.parametrize("change", ["data", "options", "subentry"])
async def test_a_change_saved_while_setting_up_is_applied(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, change: str) -> None:
    entry = MockConfigEntry(domain=DOMAIN, version=3, data={CONF_LANG: "eng", CONF_STRUCTURE: STRUCTURE_VERSION})
    entry.add_to_hass(hass)
    added = place("Esimerkkilä", 61.0, 28.0, warning_types=[])
    subentry = ConfigSubentry(
        data=MappingProxyType(added["data"]), subentry_type=added["subentry_type"], title=added["title"], unique_id=added["unique_id"]
    )
    forward = hass.config_entries.async_forward_entry_setups
    setups = []

    async def save_while_setting_up(entry: MockConfigEntry, platforms) -> None:
        setups.append((entry.data[CONF_LANG], dict(entry.options), set(entry.subentries)))
        # Saved as a flow would save it, before setup has added its update listener.
        if len(setups) == 1:
            if change == "data":
                hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_LANG: "fin"})
            elif change == "options":
                hass.config_entries.async_update_entry(entry, options={CONF_NO_DATA_ISSUE: False})
            else:
                hass.config_entries.async_add_subentry(entry, subentry)
        await forward(entry, platforms)

    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", save_while_setting_up)
    # Not asserted: the reload may already be under way when the setup returns.
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert len(setups) == 2, "set up again with the change"
    assert setups[0] != setups[1], "the first setup saw the entry before the change"
    if change == "data":
        assert setups[-1][0] == "fin"
    elif change == "options":
        assert setups[-1][1] == {CONF_NO_DATA_ISSUE: False}
    else:
        assert subentry.subentry_id in entry.runtime_data.devices


@pytest.mark.parametrize("migration", ["restructure", "move"])
async def test_a_migration_at_setup_does_not_set_it_up_again(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, migration: str) -> None:
    # Each saves to the entry before its setup looks for changes, so not one of them. A move from no old entries still
    # makes the move's own save.
    data = {CONF_LANG: "eng"} if migration == "restructure" else {CONF_LANG: "eng", CONF_STRUCTURE: STRUCTURE_VERSION, CONF_MOVE_FROM: []}
    entry = MockConfigEntry(domain=DOMAIN, version=3, data=data)
    entry.add_to_hass(hass)
    forward = hass.config_entries.async_forward_entry_setups
    setups = []

    async def count_setups(entry: MockConfigEntry, platforms) -> None:
        setups.append(dict(entry.data))
        await forward(entry, platforms)

    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", count_setups)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert setups == [{CONF_LANG: "eng", CONF_STRUCTURE: STRUCTURE_VERSION}], "set up once, after the migration"
