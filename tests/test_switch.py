"""Tests for BoolSettingEntity."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from homeassistant.helpers.entity import EntityCategory


def _make_switch(input_type="btn", input_idx=0, setting_key="setsLocalPriority", value=False):
    from custom_components.dsvdc4ha.switch import BoolSettingEntity
    return BoolSettingEntity(
        "sub1", 0, {"name": "MyDevice"},
        f"{input_type}_{input_idx}_{setting_key}",
        f"Test {setting_key}",
        value, input_type, input_idx, setting_key,
    )


def test_bool_setting_entity_hidden_by_default():
    from custom_components.dsvdc4ha.switch import BoolSettingEntity
    assert getattr(BoolSettingEntity, "__attr_entity_registry_visible_default") is False


def test_bool_setting_entity_config_category():
    ent = _make_switch()
    assert ent._attr_entity_category == EntityCategory.CONFIG


def test_bool_setting_entity_initial_false():
    ent = _make_switch(value=False)
    assert ent._attr_is_on is False


def test_bool_setting_entity_initial_true():
    ent = _make_switch(value=True)
    assert ent._attr_is_on is True


def test_bool_setting_entity_initial_none_is_false():
    ent = _make_switch(value=None)
    assert ent._attr_is_on is False


@pytest.mark.asyncio
async def test_turn_on_button_input():
    from custom_components.dsvdc4ha.switch import BoolSettingEntity
    ent = BoolSettingEntity(
        "sub1", 0, {"name": "MyDevice"},
        "btn_0_setsLocalPriority", "Test",
        False, "btn", 0, "setsLocalPriority",
    )
    ent.async_write_ha_state = MagicMock()

    mock_btn = MagicMock()
    mock_btn.apply_settings = MagicMock()
    mock_btn.push_settings = AsyncMock()
    mock_vdsd = MagicMock()
    mock_vdsd.button_inputs = {0: mock_btn}
    mock_device = MagicMock()
    mock_device.get_vdsd = MagicMock(return_value=mock_vdsd)
    mock_api = MagicMock()
    mock_api.get_device = MagicMock(return_value=mock_device)
    mock_api.force_reannounce_device = AsyncMock()
    mock_coordinator = MagicMock()
    mock_coordinator.api = mock_api
    ent.hass = MagicMock()
    ent.hass.data = {"dsvdc4ha": {"hub": mock_coordinator}}

    await ent.async_turn_on()
    mock_btn.apply_settings.assert_called_once_with({"setsLocalPriority": True})
    mock_btn.push_settings.assert_called_once()
    mock_api.force_reannounce_device.assert_awaited_once_with("sub1")
    assert ent._attr_is_on is True
    ent.async_write_ha_state.assert_called_once()


@pytest.mark.asyncio
async def test_turn_off_output():
    from custom_components.dsvdc4ha.switch import BoolSettingEntity
    ent = BoolSettingEntity(
        "sub1", 0, {"name": "MyDevice"},
        "out_pushChanges", "Push Changes",
        True, "out", None, "pushChanges",
    )
    ent.async_write_ha_state = MagicMock()

    mock_out = MagicMock()
    mock_out.apply_settings = MagicMock()
    mock_out.push_settings = AsyncMock()
    mock_vdsd = MagicMock()
    mock_vdsd.output = mock_out
    mock_device = MagicMock()
    mock_device.get_vdsd = MagicMock(return_value=mock_vdsd)
    mock_api = MagicMock()
    mock_api.get_device = MagicMock(return_value=mock_device)
    mock_api.force_reannounce_device = AsyncMock()
    mock_coordinator = MagicMock()
    mock_coordinator.api = mock_api
    ent.hass = MagicMock()
    ent.hass.data = {"dsvdc4ha": {"hub": mock_coordinator}}

    await ent.async_turn_off()
    mock_out.apply_settings.assert_called_once_with({"pushChanges": False})
    mock_out.push_settings.assert_called_once()
    mock_api.force_reannounce_device.assert_awaited_once_with("sub1")
    assert ent._attr_is_on is False


@pytest.mark.asyncio
async def test_turn_on_vdsd_prog_mode():
    from custom_components.dsvdc4ha.switch import BoolSettingEntity
    ent = BoolSettingEntity(
        "sub1", 0, {"name": "MyDevice"},
        "vdsd_progMode", "Programming Mode",
        False, "vdsd", None, "progMode",
    )
    ent.async_write_ha_state = MagicMock()

    mock_vdsd = MagicMock()
    mock_device = MagicMock()
    mock_device.get_vdsd = MagicMock(return_value=mock_vdsd)
    mock_api = MagicMock()
    mock_api.get_device = MagicMock(return_value=mock_device)
    mock_api.force_reannounce_device = AsyncMock()
    mock_coordinator = MagicMock()
    mock_coordinator.api = mock_api
    ent.hass = MagicMock()
    ent.hass.data = {"dsvdc4ha": {"hub": mock_coordinator}}

    await ent.async_turn_on()
    assert mock_vdsd.prog_mode is True
    mock_api.force_reannounce_device.assert_awaited_once_with("sub1")
    assert ent._attr_is_on is True


@pytest.mark.asyncio
async def test_vdc_active_switch_turn_off_calls_set_all_lifecycle():
    from custom_components.dsvdc4ha.switch import VdcActiveSwitchEntity
    from unittest.mock import MagicMock, AsyncMock
    from homeassistant.config_entries import ConfigEntry

    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test-entry"

    mock_api = MagicMock()
    mock_api.set_all_vdsds_lifecycle = AsyncMock()
    mock_coordinator = MagicMock()
    mock_coordinator.api = mock_api

    ent = VdcActiveSwitchEntity(entry, mock_coordinator)
    ent.async_write_ha_state = MagicMock()

    await ent.async_turn_off()
    from pydsvdcapi.enums import DeviceLifecycleState
    mock_api.set_all_vdsds_lifecycle.assert_awaited_once_with(DeviceLifecycleState.INACTIVE)
    assert ent._attr_is_on is False


@pytest.mark.asyncio
async def test_vdsd_active_switch_turn_off():
    from custom_components.dsvdc4ha.switch import VdsdActiveSwitchEntity

    ent = VdsdActiveSwitchEntity("sub1", 0, {"name": "Dev"}, True)
    ent.async_write_ha_state = MagicMock()

    mock_api = MagicMock()
    mock_api.set_vdsd_lifecycle = AsyncMock()
    mock_coordinator = MagicMock()
    mock_coordinator.api = mock_api
    ent.hass = MagicMock()
    ent.hass.data = {"dsvdc4ha": {"hub": mock_coordinator}}

    await ent.async_turn_off()
    from pydsvdcapi.enums import DeviceLifecycleState
    mock_api.set_vdsd_lifecycle.assert_awaited_once_with("sub1", 0, DeviceLifecycleState.INACTIVE)
    assert ent._attr_is_on is False
    ent.async_write_ha_state.assert_called_once()
