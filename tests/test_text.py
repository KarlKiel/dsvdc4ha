"""Tests for TextSettingEntity."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from homeassistant.helpers.entity import EntityCategory


def _make_text(value="My Device"):
    from custom_components.dsvdc4ha.text import TextSettingEntity
    return TextSettingEntity(
        "sub1", 0, {"name": "MyDevice"},
        "vdsd_name", "vdSD Name",
        value,
    )


def test_text_entity_hidden_by_default():
    from custom_components.dsvdc4ha.text import TextSettingEntity
    assert getattr(TextSettingEntity, "__attr_entity_registry_visible_default") is False


def test_text_entity_config_category():
    ent = _make_text()
    assert ent._attr_entity_category == EntityCategory.CONFIG


def test_text_entity_initial_value():
    ent = _make_text(value="Living Room Light")
    assert ent._attr_native_value == "Living Room Light"


@pytest.mark.asyncio
async def test_set_value_updates_vdsd_name():
    from custom_components.dsvdc4ha.text import TextSettingEntity
    ent = TextSettingEntity(
        "sub1", 0, {"name": "MyDevice"},
        "vdsd_name", "vdSD Name",
        "Old Name",
    )
    ent.async_write_ha_state = MagicMock()

    mock_vdsd = MagicMock()
    mock_device = MagicMock()
    mock_device.get_vdsd = MagicMock(return_value=mock_vdsd)
    mock_api = MagicMock()
    mock_api.get_device = MagicMock(return_value=mock_device)
    mock_api.push_vdsd_changes = AsyncMock()
    mock_coordinator = MagicMock()
    mock_coordinator.api = mock_api
    ent.hass = MagicMock()
    ent.hass.data = {"dsvdc4ha": {"hub": mock_coordinator}}

    await ent.async_set_value("New Name")
    assert mock_vdsd.name == "New Name"
    mock_api.push_vdsd_changes.assert_awaited_once_with("sub1")
    assert ent._attr_native_value == "New Name"
    ent.async_write_ha_state.assert_called_once()


@pytest.mark.asyncio
async def test_set_value_no_coordinator():
    ent = _make_text(value="Old Name")
    ent.async_write_ha_state = MagicMock()
    ent.hass = MagicMock()
    ent.hass.data = {"dsvdc4ha": {"hub": None}}

    await ent.async_set_value("New Name")
    assert ent._attr_native_value == "Old Name"
    ent.async_write_ha_state.assert_not_called()
