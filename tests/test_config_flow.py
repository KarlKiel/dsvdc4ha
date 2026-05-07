"""Tests for config flows."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.data_entry_flow import FlowResultType
from custom_components.dsvdc4ha.const import DOMAIN, CONF_ENTRY_TYPE, CONF_PORT, ENTRY_TYPE_HUB
from custom_components.dsvdc4ha.config_flow import DsvdcConfigFlow


@pytest.mark.asyncio
async def test_hub_flow_shows_progress_waiting_for_dss():
    """Hub flow: port ok + no state files → SHOW_PROGRESS on wait_for_dss."""
    import asyncio
    flow = DsvdcConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config.path.return_value = "/tmp/dsvdc4ha/host_state"
    flow.context = {"source": "user"}
    flow._async_current_entries = MagicMock(return_value=[])
    mock_task = MagicMock(spec=asyncio.Task)
    mock_task.done.return_value = False
    flow.hass.async_create_task = lambda coro: (coro.close(), mock_task)[1]

    result = await flow.async_step_user(user_input=None)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "hub"

    mock_coordinator = AsyncMock()
    mock_coordinator.api = MagicMock()
    mock_coordinator.api.host = None

    with (
        patch("custom_components.dsvdc4ha.config_flow._port_is_available", return_value=True),
        patch("custom_components.dsvdc4ha.config_flow._existing_state_files", return_value=[]),
        patch("custom_components.dsvdc4ha.coordinator.HubCoordinator", return_value=mock_coordinator),
    ):
        result2 = await flow.async_step_hub(user_input={CONF_PORT: 9090})

    assert result2["type"] == FlowResultType.SHOW_PROGRESS
    assert result2.get("progress_action") == "wait_for_dss"


@pytest.mark.asyncio
async def test_hub_flow_port_in_use_shows_error():
    """Hub flow: port unavailable → re-show form with port_in_use error."""
    flow = DsvdcConfigFlow()
    flow.hass = MagicMock()
    flow.context = {"source": "user"}
    flow._async_current_entries = MagicMock(return_value=[])

    with patch("custom_components.dsvdc4ha.config_flow._port_is_available", return_value=False):
        result = await flow.async_step_hub(user_input={CONF_PORT: 9090})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "hub"
    assert result["errors"].get(CONF_PORT) == "port_in_use"


@pytest.mark.asyncio
async def test_hub_flow_state_files_found_shows_form():
    """Hub flow: port available + state files exist → show state_files form."""
    from pathlib import Path
    flow = DsvdcConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config.path.return_value = "/tmp/dsvdc4ha/host_state"
    flow.context = {"source": "user"}
    flow._async_current_entries = MagicMock(return_value=[])

    with (
        patch("custom_components.dsvdc4ha.config_flow._port_is_available", return_value=True),
        patch("custom_components.dsvdc4ha.config_flow._existing_state_files",
              return_value=[Path("/tmp/dsvdc4ha/host_state")]),
    ):
        result = await flow.async_step_hub(user_input={CONF_PORT: 9090})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "state_files"


@pytest.mark.asyncio
async def test_hub_flow_state_files_keep_advances_to_wait():
    """state_files step: keep → files untouched, advances to wait_for_dss."""
    import asyncio
    from pathlib import Path
    mock_path = MagicMock(spec=Path)
    mock_path.name = "host_state"
    mock_task = MagicMock(spec=asyncio.Task)
    mock_task.done.return_value = False
    mock_coordinator = AsyncMock()
    mock_coordinator.api = MagicMock()
    mock_coordinator.api.host = None

    flow = DsvdcConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config.path.return_value = "/tmp/dsvdc4ha/host_state"
    flow.hass.async_create_task = lambda coro: (coro.close(), mock_task)[1]
    flow.context = {"source": "user"}
    flow._async_current_entries = MagicMock(return_value=[])
    flow._pending_port = 9090

    with (
        patch("custom_components.dsvdc4ha.config_flow._existing_state_files", return_value=[mock_path]),
        patch("custom_components.dsvdc4ha.coordinator.HubCoordinator", return_value=mock_coordinator),
    ):
        result = await flow.async_step_state_files(user_input={"action": "keep"})

    mock_path.unlink.assert_not_called()
    assert result["type"] == FlowResultType.SHOW_PROGRESS
    assert result.get("progress_action") == "wait_for_dss"


@pytest.mark.asyncio
async def test_hub_flow_state_files_delete_removes_files():
    """state_files step: delete → files unlinked, advances to wait_for_dss."""
    import asyncio
    from pathlib import Path
    mock_path = MagicMock(spec=Path)
    mock_path.name = "host_state"
    mock_task = MagicMock(spec=asyncio.Task)
    mock_task.done.return_value = False
    mock_coordinator = AsyncMock()
    mock_coordinator.api = MagicMock()
    mock_coordinator.api.host = None

    flow = DsvdcConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config.path.return_value = "/tmp/dsvdc4ha/host_state"
    flow.hass.async_create_task = lambda coro: (coro.close(), mock_task)[1]
    flow.context = {"source": "user"}
    flow._async_current_entries = MagicMock(return_value=[])
    flow._pending_port = 9090

    with (
        patch("custom_components.dsvdc4ha.config_flow._existing_state_files", return_value=[mock_path]),
        patch("custom_components.dsvdc4ha.coordinator.HubCoordinator", return_value=mock_coordinator),
    ):
        result = await flow.async_step_state_files(user_input={"action": "delete"})

    mock_path.unlink.assert_called_once()
    assert result["type"] == FlowResultType.SHOW_PROGRESS


@pytest.mark.asyncio
async def test_finalize_hub_connected_creates_entry():
    """finalize_hub: DSS connected → hand off coordinator and create entry."""
    mock_coordinator = AsyncMock()

    flow = DsvdcConfigFlow()
    flow.hass = MagicMock()
    flow.hass.data = {DOMAIN: {}}
    flow.context = {"source": "user"}
    flow._pending_port = 9090
    flow._dss_connected = True
    flow._temp_coordinator = mock_coordinator

    result = await flow.async_step_finalize_hub()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PORT] == 9090
    assert flow.hass.data[DOMAIN].get("_pending_coordinator") is mock_coordinator
    assert flow._temp_coordinator is None


@pytest.mark.asyncio
async def test_finalize_hub_timeout_stops_coordinator_and_aborts():
    """finalize_hub: DSS timeout → stop coordinator and abort."""
    mock_coordinator = AsyncMock()

    flow = DsvdcConfigFlow()
    flow.hass = MagicMock()
    flow.context = {"source": "user"}
    flow._pending_port = 9090
    flow._dss_connected = False
    flow._temp_coordinator = mock_coordinator

    result = await flow.async_step_finalize_hub()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "no_dss_found"
    mock_coordinator.async_stop.assert_awaited_once()


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
