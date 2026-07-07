"""Tests for SelectableSettingEntity."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from homeassistant.helpers.entity import EntityCategory


def _make_select(input_type="bi", input_idx=0, setting_key="group", value=1):
    from custom_components.dsvdc4ha.select import SelectableSettingEntity, SETTING_OPTIONS
    options = SETTING_OPTIONS[(input_type, setting_key)]
    return SelectableSettingEntity(
        "sub1", 0, {"name": "MyDevice"},
        f"{input_type}_{input_idx}_{setting_key}",
        f"Test {setting_key}",
        value, input_type, input_idx, setting_key, options,
    )


def test_selectable_entity_hidden_by_default():
    from custom_components.dsvdc4ha.select import SelectableSettingEntity
    assert getattr(SelectableSettingEntity, "__attr_entity_registry_visible_default") is False


def test_selectable_entity_config_category():
    ent = _make_select()
    assert ent._attr_entity_category == EntityCategory.CONFIG


def test_selectable_entity_options_populated():
    ent = _make_select(input_type="bi", setting_key="group")
    assert "Light" in ent._attr_options
    assert "Joker" in ent._attr_options


def test_selectable_entity_current_option_from_value():
    ent = _make_select(input_type="bi", setting_key="group", value=8)
    assert ent._attr_current_option == "Joker"


def test_selectable_entity_unknown_value_gives_none():
    ent = _make_select(input_type="bi", setting_key="group", value=99)
    assert ent._attr_current_option is None


def test_selectable_entity_sensor_function_options():
    ent = _make_select(input_type="bi", setting_key="sensorFunction", value=0)
    assert ent._attr_current_option == "Generic"
    assert len(ent._attr_options) == 24  # 0..23


@pytest.mark.asyncio
async def test_select_option_binary_input():
    from custom_components.dsvdc4ha.select import SelectableSettingEntity, SETTING_OPTIONS
    options = SETTING_OPTIONS[("bi", "group")]
    ent = SelectableSettingEntity(
        "sub1", 0, {"name": "MyDevice"},
        "bi_0_group", "Test Group",
        1, "bi", 0, "group", options,
    )
    ent.async_write_ha_state = MagicMock()

    mock_bi = MagicMock()
    mock_bi.apply_settings = MagicMock()
    mock_bi.push_settings = AsyncMock()
    mock_vdsd = MagicMock()
    mock_vdsd.binary_inputs = {0: mock_bi}
    mock_device = MagicMock()
    mock_device.get_vdsd = MagicMock(return_value=mock_vdsd)
    mock_api = MagicMock()
    mock_api.get_device = MagicMock(return_value=mock_device)
    mock_coordinator = MagicMock()
    mock_coordinator.api = mock_api
    ent.hass = MagicMock()
    ent.hass.data = {"dsvdc4ha": {"hub": mock_coordinator}}

    await ent.async_select_option("Joker")
    mock_bi.apply_settings.assert_called_once_with({"group": 8})
    mock_bi.push_settings.assert_called_once()
    assert ent._attr_current_option == "Joker"
    ent.async_write_ha_state.assert_called_once()


@pytest.mark.asyncio
async def test_select_option_output_mode():
    from custom_components.dsvdc4ha.select import SelectableSettingEntity, SETTING_OPTIONS
    options = SETTING_OPTIONS[("out", "mode")]
    ent = SelectableSettingEntity(
        "sub1", 0, {"name": "MyDevice"},
        "out_mode", "Output Mode",
        0, "out", None, "mode", options,
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
    mock_coordinator = MagicMock()
    mock_coordinator.api = mock_api
    ent.hass = MagicMock()
    ent.hass.data = {"dsvdc4ha": {"hub": mock_coordinator}}

    await ent.async_select_option("Binary")
    mock_out.apply_settings.assert_called_once_with({"mode": 1})
    mock_out.push_settings.assert_called_once()


@pytest.mark.asyncio
async def test_select_option_invalid_ignored():
    ent = _make_select(input_type="bi", setting_key="group", value=1)
    ent.async_write_ha_state = MagicMock()
    ent.hass = MagicMock()
    ent.hass.data = {"dsvdc4ha": {"hub": None}}

    await ent.async_select_option("NotARealOption")
    ent.async_write_ha_state.assert_not_called()


@pytest.mark.asyncio
async def test_select_option_no_coordinator():
    ent = _make_select(input_type="bi", setting_key="group", value=1)
    ent.async_write_ha_state = MagicMock()
    ent.hass = MagicMock()
    ent.hass.data = {"dsvdc4ha": {"hub": None}}

    await ent.async_select_option("Light")
    ent.async_write_ha_state.assert_not_called()
    assert ent._attr_current_option == "Light"  # initial value was 1=Light
