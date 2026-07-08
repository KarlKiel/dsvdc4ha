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
    from unittest.mock import patch
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

    mock_dev_reg = MagicMock()
    mock_dev_reg.async_get_device = MagicMock(return_value=None)
    ent.hass.config_entries.async_entries.return_value = []
    with patch("custom_components.dsvdc4ha.text.dr.async_get", return_value=mock_dev_reg):
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


@pytest.mark.asyncio
async def test_set_value_updates_ha_device_registry():
    """When async_set_value is called, it updates the HA device registry name."""
    from custom_components.dsvdc4ha.text import TextSettingEntity
    from unittest.mock import patch, MagicMock, AsyncMock
    from homeassistant.helpers import device_registry as dr

    ent = TextSettingEntity(
        "sub1", 0, {"name": "Old Name"},
        "vdsd_name", "Name", "Old Name",
    )
    ent.async_write_ha_state = MagicMock()

    mock_vdsd = MagicMock()
    mock_device_obj = MagicMock()
    mock_device_obj.get_vdsd = MagicMock(return_value=mock_vdsd)
    mock_api = MagicMock()
    mock_api.get_device = MagicMock(return_value=mock_device_obj)
    mock_api.push_vdsd_changes = AsyncMock()
    mock_coordinator = MagicMock()
    mock_coordinator.api = mock_api

    mock_ha_device = MagicMock()
    mock_ha_device.id = "ha-dev-id-1"
    mock_dev_reg = MagicMock()
    mock_dev_reg.async_get_device = MagicMock(return_value=mock_ha_device)
    mock_dev_reg.async_update_device = MagicMock()

    # Build a mock config_entries with one entry containing our subentry
    mock_subentry = MagicMock()
    mock_subentry.subentry_id = "sub1"
    mock_subentry.data = {"entry_name": "Physical Device", "vdsds": [{"name": "Old Name", "displayId": "Old Name"}]}
    mock_entry = MagicMock()
    mock_entry.subentries = {"sub1": mock_subentry}
    mock_config_entries = MagicMock()
    mock_config_entries.async_entries = MagicMock(return_value=[mock_entry])
    mock_config_entries.async_update_subentry = MagicMock()

    ent.hass = MagicMock()
    ent.hass.data = {"dsvdc4ha": {"hub": mock_coordinator}}
    ent.hass.config_entries = mock_config_entries

    with patch("custom_components.dsvdc4ha.text.dr.async_get", return_value=mock_dev_reg):
        await ent.async_set_value("New Name")

    # Device registry must be updated
    mock_dev_reg.async_update_device.assert_called_once_with("ha-dev-id-1", name="New Name")
    # Subentry must be persisted
    mock_config_entries.async_update_subentry.assert_called_once()
    # vdSD name and displayId both updated in persisted data
    call_args = mock_config_entries.async_update_subentry.call_args
    new_data = call_args.kwargs["data"]
    assert new_data["vdsds"][0]["name"] == "New Name"
    assert new_data["vdsds"][0]["displayId"] == "New Name"
