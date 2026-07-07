"""Tests for DSS→HA name propagation in _create_property_entities."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


def _make_mock_vdsd(name="Device"):
    vdsd = MagicMock()
    vdsd.name = name
    vdsd.zone_id = 0
    vdsd.prog_mode = None
    vdsd.active = True
    vdsd.binary_inputs = {}
    vdsd.sensor_inputs = {}
    vdsd.button_inputs = {}
    vdsd.output = None
    vdsd.get_properties = MagicMock(return_value={})
    vdsd.on_settings_changed = None
    return vdsd


def _make_mock_env(vdsd_name="Device"):
    mock_hass = MagicMock()

    mock_vdsd = _make_mock_vdsd(name=vdsd_name)
    mock_device = MagicMock()
    mock_device.get_vdsd = MagicMock(return_value=mock_vdsd)
    mock_api = MagicMock()
    mock_api.get_device = MagicMock(return_value=mock_device)

    mock_subentry = MagicMock()
    mock_subentry.subentry_id = "sub1"
    mock_subentry.data = {
        "entry_name": "Physical Device",
        "vdsds": [{"name": vdsd_name, "displayId": vdsd_name}],
    }
    mock_entry = MagicMock()
    mock_entry.subentries = {"sub1": mock_subentry}
    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])
    mock_hass.config_entries.async_update_subentry = MagicMock()

    mock_ha_device = MagicMock()
    mock_ha_device.id = "ha-dev-1"
    mock_dev_reg = MagicMock()
    mock_dev_reg.async_get_device = MagicMock(return_value=mock_ha_device)
    mock_dev_reg.async_update_device = MagicMock()

    return mock_hass, mock_api, mock_subentry, mock_entry, mock_vdsd, mock_dev_reg, mock_ha_device


@pytest.mark.asyncio
async def test_dss_name_change_updates_device_registry_and_subentry():
    """When DSS pushes a name change, device registry and subentry are updated."""
    from custom_components.dsvdc4ha.__init__ import _create_property_entities
    from custom_components.dsvdc4ha.text import TextSettingEntity

    mock_hass, mock_api, mock_subentry, mock_entry, mock_vdsd, mock_dev_reg, mock_ha_device = (
        _make_mock_env("OldName")
    )

    # Stub out add_* callables — we only need add_text to trigger name entity creation
    add_text = MagicMock()
    add_switch = MagicMock()

    # Patch async_write_ha_state at class level so entities don't need hass set
    with patch.object(TextSettingEntity, "async_write_ha_state", MagicMock()), \
         patch(
             "custom_components.dsvdc4ha.__init__.dr.async_get",
             return_value=mock_dev_reg,
         ):
        _create_property_entities(
            mock_api,
            mock_subentry,
            add_sensor=None,
            add_number=None,
            add_select=None,
            add_switch=add_switch,
            add_text=add_text,
            hass=mock_hass,
        )

        # The callback must have been registered
        assert mock_vdsd.on_settings_changed is not None, (
            "on_settings_changed was not set — callback not registered"
        )

        # Fire the callback with a name change
        cb = mock_vdsd.on_settings_changed
        await cb(mock_vdsd, {"name": "New Name"})

    # Device registry must be updated with the new name
    mock_dev_reg.async_update_device.assert_called_once_with("ha-dev-1", name="New Name")

    # Subentry data must be persisted
    mock_hass.config_entries.async_update_subentry.assert_called_once()

    # Verify the persisted data contains the new name
    call_args = mock_hass.config_entries.async_update_subentry.call_args
    new_data = call_args.kwargs["data"]
    assert new_data["vdsds"][0]["name"] == "New Name"
    assert new_data["vdsds"][0]["displayId"] == "New Name"


@pytest.mark.asyncio
async def test_dss_name_change_no_hass_does_not_crash():
    """When hass=None (old call sites), name callback still updates the text entity."""
    from custom_components.dsvdc4ha.__init__ import _create_property_entities
    from custom_components.dsvdc4ha.text import TextSettingEntity

    mock_vdsd = _make_mock_vdsd(name="Device")
    mock_device = MagicMock()
    mock_device.get_vdsd = MagicMock(return_value=mock_vdsd)
    mock_api = MagicMock()
    mock_api.get_device = MagicMock(return_value=mock_device)

    mock_subentry = MagicMock()
    mock_subentry.subentry_id = "sub1"
    mock_subentry.data = {"vdsds": [{"name": "Device", "displayId": "Device"}]}

    add_text = MagicMock()
    add_switch = MagicMock()

    # Patch async_write_ha_state at class level so entities don't need hass set
    with patch.object(TextSettingEntity, "async_write_ha_state", MagicMock()):
        # hass=None — should not raise
        _create_property_entities(
            mock_api,
            mock_subentry,
            add_sensor=None,
            add_number=None,
            add_select=None,
            add_switch=add_switch,
            add_text=add_text,
            hass=None,
        )

        assert mock_vdsd.on_settings_changed is not None
        cb = mock_vdsd.on_settings_changed
        # Must not raise even without hass
        await cb(mock_vdsd, {"name": "Updated Name"})
