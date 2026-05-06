"""Tests for config flows."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.data_entry_flow import FlowResultType
from custom_components.dsvdc4ha.const import DOMAIN, CONF_ENTRY_TYPE, CONF_PORT, ENTRY_TYPE_HUB
from custom_components.dsvdc4ha.config_flow import DsvdcConfigFlow


@pytest.mark.asyncio
async def test_hub_flow_creates_entry():
    """Test that the hub flow shows a form then creates an entry."""
    from custom_components.dsvdc4ha.config_flow import DsvdcConfigFlow

    flow = DsvdcConfigFlow()
    flow.hass = MagicMock()
    flow.context = {"source": "user"}
    flow._async_current_entries = MagicMock(return_value=[])

    # Step 1: no hub entry exists → show hub form
    result = await flow.async_step_user(user_input=None)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "hub"

    # Step 2: submit port → create entry
    result2 = await flow.async_step_hub(user_input={CONF_PORT: 9090})
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_PORT] == 9090
    assert result2["data"][CONF_ENTRY_TYPE] == ENTRY_TYPE_HUB


@pytest.mark.asyncio
async def test_hub_flow_routes_to_device_when_hub_exists():
    """Test that async_step_user routes to device_info when a hub entry exists."""
    from custom_components.dsvdc4ha.config_flow import DsvdcConfigFlow

    flow = DsvdcConfigFlow()
    flow.hass = MagicMock()
    flow.context = {"source": "user"}

    # Simulate an existing hub entry
    mock_hub_entry = MagicMock()
    mock_hub_entry.data = {CONF_ENTRY_TYPE: ENTRY_TYPE_HUB}
    flow._async_current_entries = MagicMock(return_value=[mock_hub_entry])

    result = await flow.async_step_user(user_input=None)
    # Should land on device_info form (stub)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "device_info"


@pytest.mark.asyncio
async def test_device_flow_device_info_to_vdsd_creation():
    """Test device_info step advances to vdsd_creation."""
    flow = DsvdcConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}
    flow._async_current_entries = MagicMock(return_value=[MagicMock(data={"entry_type": "hub"})])

    result = await flow.async_step_device_info()
    assert result["type"] == "form"
    assert result["step_id"] == "device_info"

    result2 = await flow.async_step_device_info(
        {"name": "Test Lamp", "vendorName": "Acme", "displayId": "LampV1"}
    )
    assert result2["step_id"] == "vdsd_creation"
    assert flow._device_name == "Test Lamp"
    assert flow._vendor_name == "Acme"


@pytest.mark.asyncio
async def test_vdsd_overview_shows_form_then_next():
    """Test vdsd_overview shows form and routes to model_features on next."""
    flow = DsvdcConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}
    flow._current_vdsd = {"displayId": "TestUnit", "optional": {}}
    flow._current_buttons = []
    flow._current_binary_inputs = []
    flow._current_sensors = []
    flow._current_output = None

    result = await flow.async_step_vdsd_overview()
    assert result["type"] == "form"
    assert result["step_id"] == "vdsd_overview"

    result2 = await flow.async_step_vdsd_overview({"action": "next"})
    assert result2["step_id"] == "model_features"


@pytest.mark.asyncio
async def test_vdsd_overview_optional_settings_returns():
    """Test that optional_settings navigates away and back."""
    flow = DsvdcConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}
    flow._current_vdsd = {"displayId": "TestUnit", "optional": {}}
    flow._current_buttons = []
    flow._current_binary_inputs = []
    flow._current_sensors = []
    flow._current_output = None

    # Go to optional settings from overview
    result = await flow.async_step_vdsd_overview({"action": "optional_settings"})
    assert result["step_id"] == "optional_settings"

    # Submit optional settings — should return to vdsd_overview
    result2 = await flow.async_step_optional_settings({"hardwareVersion": "1.0"})
    assert result2["step_id"] == "vdsd_overview"
