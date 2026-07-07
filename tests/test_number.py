"""Tests for WritableSettingNumberEntity."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.components.number import NumberMode
from homeassistant.helpers.entity import EntityCategory


def _make_entity(input_type="bi", input_idx=0, setting_key="group", value=3):
    from custom_components.dsvdc4ha.number import WritableSettingNumberEntity
    return WritableSettingNumberEntity(
        "sub1", 0, {"name": "MyDevice"},
        f"{input_type}_{input_idx}_writable_{setting_key}",
        f"BI {input_idx} {setting_key}",
        value, input_type, input_idx, setting_key,
    )


def test_writable_setting_entity_hidden_by_default():
    from custom_components.dsvdc4ha.number import WritableSettingNumberEntity
    assert getattr(WritableSettingNumberEntity, "__attr_entity_registry_visible_default") is False


def test_writable_setting_entity_config_category():
    ent = _make_entity()
    assert ent._attr_entity_category == EntityCategory.CONFIG


def test_writable_setting_entity_mode_box():
    ent = _make_entity()
    assert ent._attr_mode == NumberMode.BOX


def test_writable_setting_entity_initial_value():
    ent = _make_entity(value=7)
    assert ent._attr_native_value == 7.0


def test_writable_setting_entity_known_range_group():
    ent = _make_entity(setting_key="group", value=0)
    assert ent._attr_native_min_value == 0
    assert ent._attr_native_max_value == 255
    assert ent._attr_native_step == 1


def test_writable_setting_entity_known_range_sensor_function():
    ent = _make_entity(setting_key="sensorFunction", value=0)
    assert ent._attr_native_max_value == 23


def test_writable_setting_entity_known_range_min_push_interval():
    from custom_components.dsvdc4ha.number import WritableSettingNumberEntity
    ent = WritableSettingNumberEntity(
        "sub1", 0, {"name": "MyDevice"},
        "si_0_writable_minPushInterval", "Sensor 0 minPushInterval",
        2.0, "si", 0, "minPushInterval",
    )
    assert ent._attr_native_max_value == 3600
    assert ent._attr_native_step == 0.1


def test_writable_setting_entity_bool_range():
    ent = _make_entity(setting_key="setsLocalPriority", value=0)
    assert ent._attr_native_min_value == 0
    assert ent._attr_native_max_value == 1
    assert ent._attr_native_step == 1


def test_writable_setting_entity_unknown_key_default_range():
    from custom_components.dsvdc4ha.number import WritableSettingNumberEntity
    ent = WritableSettingNumberEntity(
        "sub1", 0, {"name": "MyDevice"},
        "bi_0_writable_unknownKey", "BI 0 unknownKey",
        0, "bi", 0, "unknownKey",
    )
    assert ent._attr_native_min_value == 0
    assert ent._attr_native_max_value == 255
    assert ent._attr_native_step == 1


def _make_mock_env(input_type, input_idx, setting_key, value):
    """Create entity + mock HA/coordinator for async_set_native_value tests."""
    from custom_components.dsvdc4ha.number import WritableSettingNumberEntity

    ent = WritableSettingNumberEntity(
        "sub1", 0, {"name": "MyDevice"},
        f"{input_type}_{input_idx}_writable_{setting_key}",
        f"{input_type.upper()} {input_idx} {setting_key}",
        value, input_type, input_idx, setting_key,
    )
    ent.async_write_ha_state = MagicMock()

    mock_bi = MagicMock()
    mock_bi.apply_settings = MagicMock()
    mock_bi.push_settings = AsyncMock()
    mock_si = MagicMock()
    mock_si.apply_settings = MagicMock()
    mock_si.push_settings = AsyncMock()
    mock_btn = MagicMock()
    mock_btn.apply_settings = MagicMock()
    mock_btn.push_settings = AsyncMock()
    mock_out = MagicMock()
    mock_out.apply_settings = MagicMock()
    mock_out.push_settings = AsyncMock()

    mock_vdsd = MagicMock()
    mock_vdsd.binary_inputs = {0: mock_bi}
    mock_vdsd.sensor_inputs = {0: mock_si}
    mock_vdsd.button_inputs = {0: mock_btn}
    mock_vdsd.output = mock_out

    mock_device = MagicMock()
    mock_device.get_vdsd = MagicMock(return_value=mock_vdsd)

    mock_api = MagicMock()
    mock_api.get_device = MagicMock(return_value=mock_device)

    mock_coordinator = MagicMock()
    mock_coordinator.api = mock_api

    mock_hass = MagicMock()
    mock_hass.data = {"dsvdc4ha": {"hub": mock_coordinator}}
    ent.hass = mock_hass

    inputs = {"bi": mock_bi, "si": mock_si, "btn": mock_btn, "out": mock_out}
    return ent, inputs


@pytest.mark.asyncio
async def test_set_native_value_binary_input():
    ent, inputs = _make_mock_env("bi", 0, "group", 3)
    await ent.async_set_native_value(5.0)
    inputs["bi"].apply_settings.assert_called_once_with({"group": 5})
    inputs["bi"].push_settings.assert_called_once()
    assert ent._attr_native_value == 5.0
    ent.async_write_ha_state.assert_called_once()


@pytest.mark.asyncio
async def test_set_native_value_sensor_input():
    from custom_components.dsvdc4ha.number import WritableSettingNumberEntity
    ent = WritableSettingNumberEntity(
        "sub1", 0, {"name": "MyDevice"},
        "si_0_writable_minPushInterval", "Sensor 0 minPushInterval",
        2.0, "si", 0, "minPushInterval",
    )
    ent.async_write_ha_state = MagicMock()

    mock_si = MagicMock()
    mock_si.apply_settings = MagicMock()
    mock_si.push_settings = AsyncMock()

    mock_vdsd = MagicMock()
    mock_vdsd.sensor_inputs = {0: mock_si}
    mock_device = MagicMock()
    mock_device.get_vdsd = MagicMock(return_value=mock_vdsd)
    mock_api = MagicMock()
    mock_api.get_device = MagicMock(return_value=mock_device)
    mock_coordinator = MagicMock()
    mock_coordinator.api = mock_api
    ent.hass = MagicMock()
    ent.hass.data = {"dsvdc4ha": {"hub": mock_coordinator}}

    await ent.async_set_native_value(5.5)
    mock_si.apply_settings.assert_called_once_with({"minPushInterval": 5.5})
    mock_si.push_settings.assert_called_once()


@pytest.mark.asyncio
async def test_set_native_value_button_input():
    ent, inputs = _make_mock_env("btn", 0, "function", 0)
    await ent.async_set_native_value(3.0)
    inputs["btn"].apply_settings.assert_called_once_with({"function": 3})
    inputs["btn"].push_settings.assert_called_once()


@pytest.mark.asyncio
async def test_set_native_value_output():
    from custom_components.dsvdc4ha.number import WritableSettingNumberEntity
    ent = WritableSettingNumberEntity(
        "sub1", 0, {"name": "MyDevice"},
        "out_writable_mode", "Output mode",
        2, "out", None, "mode",
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

    await ent.async_set_native_value(1.0)
    mock_out.apply_settings.assert_called_once_with({"mode": 1})
    mock_out.push_settings.assert_called_once()


@pytest.mark.asyncio
async def test_set_native_value_no_coordinator():
    """set_native_value returns gracefully when coordinator is missing."""
    from custom_components.dsvdc4ha.number import WritableSettingNumberEntity

    ent = WritableSettingNumberEntity(
        "sub1", 0, {"name": "MyDevice"},
        "bi_0_writable_group", "BI 0 group",
        3, "bi", 0, "group",
    )
    ent.async_write_ha_state = MagicMock()
    ent.hass = MagicMock()
    ent.hass.data = {"dsvdc4ha": {"hub": None}}

    await ent.async_set_native_value(5.0)
    assert ent._attr_native_value == 3.0  # unchanged
    ent.async_write_ha_state.assert_not_called()
