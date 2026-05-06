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


@pytest.mark.asyncio
async def test_button_step_appends_button():
    """Button step appends button data and returns to vdsd_overview."""
    flow = DsvdcConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}
    flow._current_vdsd = {"displayId": "Unit", "optional": {}}
    flow._current_buttons = []
    flow._current_binary_inputs = []
    flow._current_sensors = []
    flow._current_output = None
    flow._current_button_element_idx = 0

    result = await flow.async_step_button()
    assert result["step_id"] == "button"

    result2 = await flow.async_step_button({
        "name": "Main Button",
        "buttonType": "1",
        "group": "1",
        "function": "0",
        "mode": "0",
        "channel": "0",
        "supportsLocalKeyMode": False,
        "setsLocalPriority": False,
        "callsPresent": True,
        "callbackType": "clickTypes",
        "callback_entity": "sensor.my_button",
    })
    assert result2["step_id"] == "vdsd_overview"
    assert len(flow._current_buttons) == 1
    assert flow._current_buttons[0]["name"] == "Main Button"
    assert flow._current_buttons[0]["buttonElementID"] == 0


@pytest.mark.asyncio
async def test_binary_input_step_appends_and_returns():
    flow = DsvdcConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}
    flow._current_vdsd = {"displayId": "Unit", "optional": {}}
    flow._current_buttons = []
    flow._current_binary_inputs = []
    flow._current_sensors = []
    flow._current_output = None

    result = await flow.async_step_binary_input()
    assert result["step_id"] == "binary_input"

    result2 = await flow.async_step_binary_input({
        "name": "Window",
        "group": "8",
        "sensorFunction": "13",
        "hardwiredFunction": "0",
        "updateInterval": 0,
        "inputType": "1",
        "inputUsage": "0",
        "valueType": "boolean",
        "callback_entity": "binary_sensor.window",
    })
    assert result2["step_id"] == "vdsd_overview"
    assert len(flow._current_binary_inputs) == 1
    assert flow._current_binary_inputs[0]["name"] == "Window"


@pytest.mark.asyncio
async def test_output_step_stores_output():
    flow = DsvdcConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}
    flow._current_vdsd = {"displayId": "Unit", "optional": {}}
    flow._current_buttons = []
    flow._current_binary_inputs = []
    flow._current_sensors = []
    flow._current_output = None
    flow._current_channels = []

    result = await flow.async_step_output()
    assert result["step_id"] == "output"

    result2 = await flow.async_step_output({
        "name": "Dimmer",
        "groups": ["1"],
        "defaultGroup": "1",
        "function": "1",
        "outputUsage": "0",
        "variableRamp": False,
        "mode": "0",
    })
    # Function=1 (DIMMER) — not a manual channel function; no channels yet so auto-skips
    # channel_mapping → vdsd_overview
    assert result2["step_id"] in ("channel", "channel_mapping", "vdsd_overview")
    assert flow._current_output is not None
    assert flow._current_output["name"] == "Dimmer"


@pytest.mark.asyncio
async def test_full_device_flow_no_output_creates_entry():
    """Full device flow without output creates entry correctly."""
    flow = DsvdcConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}
    flow._async_current_entries = MagicMock(return_value=[MagicMock(data={"entry_type": "hub"})])

    # device_info
    await flow.async_step_device_info(
        {"name": "Test Lamp", "vendorName": "Acme", "displayId": "LampV1"}
    )
    # vdsd_creation
    await flow.async_step_vdsd_creation(
        {"displayId": "LampUnit", "primaryGroup": "1", "modelVersion": "v1"}
    )
    # vdsd_overview → next (no components)
    await flow.async_step_vdsd_overview({"action": "next"})
    # model_features → accept defaults
    await flow.async_step_model_features({"features": []})
    # device_summary → CREATE
    result = await flow.async_step_device_summary({"action": "create", "confirm": True})

    assert result["type"] == "create_entry"
    data = result["data"]
    assert data["entry_type"] == "device"
    assert data["name"] == "Test Lamp"
    assert data["vendorName"] == "Acme"
    assert len(data["vdsds"]) == 1
    assert data["vdsds"][0]["displayId"] == "LampUnit"
