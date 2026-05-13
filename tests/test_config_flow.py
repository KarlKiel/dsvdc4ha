"""Tests for config flows."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.data_entry_flow import FlowResultType
from custom_components.dsvdc4ha.const import (
    DOMAIN,
    CONF_ENTRY_TYPE,
    CONF_PORT,
    ENTRY_TYPE_HUB,
)
from custom_components.dsvdc4ha.config_flow import DsvdcConfigFlow, VdsdSubentryFlowHandler


# ---------------------------------------------------------------------------
# DsvdcConfigFlow — hub flow tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hub_flow_shows_progress_waiting_for_dss():
    """Hub flow: port ok + no state files → SHOW_PROGRESS on wait_for_dss."""
    import asyncio
    flow = DsvdcConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config.path.return_value = "/tmp/dsvdc4ha/host_state"
    flow.hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *args: fn(*args))
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
async def test_hub_flow_aborts_when_already_configured():
    """async_step_user aborts with already_configured when a hub entry exists."""
    flow = DsvdcConfigFlow()
    flow.hass = MagicMock()
    flow.context = {"source": "user"}

    mock_hub_entry = MagicMock()
    mock_hub_entry.data = {CONF_ENTRY_TYPE: ENTRY_TYPE_HUB}
    flow._async_current_entries = MagicMock(return_value=[mock_hub_entry])

    result = await flow.async_step_user(user_input=None)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_hub_flow_port_in_use_shows_error():
    """Hub flow: port unavailable → re-show form with port_in_use error."""
    flow = DsvdcConfigFlow()
    flow.hass = MagicMock()
    flow.hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *args: fn(*args))
    flow.context = {"source": "user"}

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
    flow.hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *args: fn(*args))
    flow.context = {"source": "user"}

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
    flow.hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *args: fn(*args))
    flow.hass.async_create_task = lambda coro: (coro.close(), mock_task)[1]
    flow.context = {"source": "user"}
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
    flow.hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *args: fn(*args))
    flow.hass.async_create_task = lambda coro: (coro.close(), mock_task)[1]
    flow.context = {"source": "user"}
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
    assert result["data"][CONF_ENTRY_TYPE] == ENTRY_TYPE_HUB
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


# ---------------------------------------------------------------------------
# VdsdSubentryFlowHandler tests
# ---------------------------------------------------------------------------

def _make_subentry_flow() -> VdsdSubentryFlowHandler:
    """Create a bare VdsdSubentryFlowHandler with hass and context set up."""
    flow = VdsdSubentryFlowHandler()
    flow.hass = MagicMock()
    flow.context = {"source": "user", "entry_id": "hub-entry-123"}
    return flow


@pytest.mark.asyncio
async def test_subentry_flow_user_routes_to_creation_mode():
    """VdsdSubentryFlowHandler.async_step_user routes to creation_mode."""
    flow = _make_subentry_flow()
    result = await flow.async_step_user(user_input=None)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "creation_mode"


@pytest.mark.asyncio
async def test_creation_mode_from_scratch_routes_to_device_info():
    """creation_mode: from_scratch → device_info."""
    flow = _make_subentry_flow()
    result = await flow.async_step_creation_mode(user_input={"mode": "from_scratch"})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "device_info"


@pytest.mark.asyncio
async def test_creation_mode_from_entity_routes_to_entity_picker():
    """creation_mode: from_entity → entity_picker."""
    flow = _make_subentry_flow()
    result = await flow.async_step_creation_mode(user_input={"mode": "from_entity"})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "entity_picker"


@pytest.mark.asyncio
async def test_device_info_step_advances_to_vdsd_creation():
    """device_info step advances to vdsd_creation."""
    flow = _make_subentry_flow()

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
    flow = _make_subentry_flow()
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
    flow = _make_subentry_flow()
    flow._current_vdsd = {"displayId": "TestUnit", "optional": {}}
    flow._current_buttons = []
    flow._current_binary_inputs = []
    flow._current_sensors = []
    flow._current_output = None

    result = await flow.async_step_vdsd_overview({"action": "optional_settings"})
    assert result["step_id"] == "optional_settings"

    result2 = await flow.async_step_optional_settings({"hardwareVersion": "1.0"})
    assert result2["step_id"] == "vdsd_overview"


@pytest.mark.asyncio
async def test_button_step_appends_button():
    """Button step appends button data and returns to vdsd_overview."""
    flow = _make_subentry_flow()
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
    flow = _make_subentry_flow()
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
    flow = _make_subentry_flow()
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
    assert result2["step_id"] in ("channel", "channel_mapping", "vdsd_overview")
    assert flow._current_output is not None
    assert flow._current_output["name"] == "Dimmer"


@pytest.mark.asyncio
async def test_full_device_subentry_flow_creates_entry():
    """Full device subentry flow without output creates subentry correctly."""
    flow = _make_subentry_flow()

    await flow.async_step_device_info(
        {"name": "Test Lamp", "vendorName": "Acme", "displayId": "LampV1"}
    )
    await flow.async_step_vdsd_creation(
        {"displayId": "LampUnit", "primaryGroup": "1", "modelVersion": "v1"}
    )
    await flow.async_step_vdsd_overview({"action": "next"})
    await flow.async_step_model_features({"features": []})
    result = await flow.async_step_device_summary({"action": "create", "confirm": True})

    assert result["type"] == "create_entry"
    assert result["title"] == "Test Lamp"
    data = result["data"]
    assert data["name"] == "Test Lamp"
    assert data["vendorName"] == "Acme"
    assert len(data["vdsds"]) == 1
    assert data["vdsds"][0]["displayId"] == "LampUnit"


# ---------------------------------------------------------------------------
# VdsdSubentryFlowHandler — "from_ha_device" path tests
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock, AsyncMock, patch
from custom_components.dsvdc4ha.device_grouper import EntityInfo, VdsdPlan


def _make_entity_info(entity_id: str, domain: str = "light") -> EntityInfo:
    return EntityInfo(
        entity_id=entity_id,
        friendly_name=entity_id,
        domain=domain,
        device_class=None,
        mapping={"primary_group": 1, "output": {
            "function": 3, "output_usage": 1, "groups": [1], "default_group": 1,
            "variable_ramp": True, "mode": 2, "channels": [{"channel_type": 1}],
        }},
        needs_choices=False,
        entity_category=None,
    )


def _make_vdsd_plan(entity_id: str = "light.lamp") -> VdsdPlan:
    return VdsdPlan(
        primary_group=1,
        name="Lamp — Light",
        output_entity=_make_entity_info(entity_id),
    )


@pytest.mark.asyncio
async def test_creation_mode_from_ha_device_routes_to_device_picker():
    flow = _make_subentry_flow()
    result = await flow.async_step_creation_mode({"mode": "from_ha_device"})
    assert result["type"] == "form"
    assert result["step_id"] == "device_picker"


@pytest.mark.asyncio
async def test_device_picker_no_choices_routes_to_plan_summary():
    flow = _make_subentry_flow()
    plan = _make_vdsd_plan()
    plan.resolved_vdsd = {"primaryGroup": 1, "displayId": "M", "buttons": [],
                          "binary_inputs": [], "sensors": [], "output": None,
                          "name": "Lamp"}

    mock_dev_reg = MagicMock()
    mock_device = MagicMock()
    mock_device.name = "Lamp"
    mock_device.name_by_user = None
    mock_device.manufacturer = "Acme"
    mock_device.model = "LampModel"
    mock_dev_reg.async_get.return_value = mock_device

    mock_ent_reg = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entity_id = "light.lamp"
    mock_entry.entity_category = None
    mock_ent_reg.entities.get_entries_for_device_id.return_value = [mock_entry]

    mock_state = MagicMock()
    mock_state.name = "Lamp"
    mock_state.attributes = {"device_class": None}
    flow.hass.states.get.return_value = mock_state

    with (
        patch("custom_components.dsvdc4ha.config_flow.dr.async_get",
              return_value=mock_dev_reg),
        patch("custom_components.dsvdc4ha.config_flow.er.async_get",
              return_value=mock_ent_reg),
        patch("custom_components.dsvdc4ha.config_flow.compute_vdsd_plan",
              return_value=([plan], [])),
    ):
        result = await flow.async_step_device_picker(
            {"device_id": "device-abc-123"}
        )

    assert result["type"] == "form"
    assert result["step_id"] == "device_plan_summary"


@pytest.mark.asyncio
async def test_device_picker_with_choices_routes_to_entity_user_input():
    flow = _make_subentry_flow()
    plan = _make_vdsd_plan()
    entity_with_choices = _make_entity_info("light.choosy")
    entity_with_choices.needs_choices = True

    plan.output_entity = entity_with_choices

    mock_dev_reg = MagicMock()
    mock_device = MagicMock()
    mock_device.name = "Lamp"
    mock_device.name_by_user = None
    mock_device.manufacturer = "Acme"
    mock_device.model = "LampModel"
    mock_dev_reg.async_get.return_value = mock_device

    mock_ent_reg = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entity_id = "light.choosy"
    mock_entry.entity_category = None
    mock_ent_reg.entities.get_entries_for_device_id.return_value = [mock_entry]

    mock_state = MagicMock()
    mock_state.name = "Choosy"
    mock_state.attributes = {"device_class": None}
    flow.hass.states.get.return_value = mock_state

    with (
        patch("custom_components.dsvdc4ha.config_flow.dr.async_get",
              return_value=mock_dev_reg),
        patch("custom_components.dsvdc4ha.config_flow.er.async_get",
              return_value=mock_ent_reg),
        patch("custom_components.dsvdc4ha.config_flow.compute_vdsd_plan",
              return_value=([plan], [])),
    ):
        result = await flow.async_step_device_picker(
            {"device_id": "device-abc-123"}
        )

    assert result["type"] == "form"
    assert result["step_id"] == "device_entity_user_input"


@pytest.mark.asyncio
async def test_device_entity_user_input_cycles_and_routes_to_summary():
    """device_entity_user_input cycles through pending entities then goes to summary."""
    flow = _make_subentry_flow()
    plan = _make_vdsd_plan()
    entity1 = _make_entity_info("cover.blind", "cover")
    entity1.needs_choices = True
    entity1.mapping = {
        "primary_group": 2,
        "output": {
            "function": 2, "output_usage": 1, "groups": [2], "default_group": 2,
            "variable_ramp": False, "mode": 2,
            "output_usage_choices": [(1, "Indoor"), (2, "Outdoor")],
            "channels_by_usage": {1: [{"channel_type": 8}], 2: [{"channel_type": 7}]},
        },
    }
    flow._vdsd_plans = [plan]
    flow._pending_choice_entities = [(entity1, 0)]
    flow._pending_choice_idx = 0

    # Show form
    result = await flow.async_step_device_entity_user_input()
    assert result["type"] == "form"
    assert result["step_id"] == "device_entity_user_input"

    # Submit — last entity, routes to plan_summary
    with patch(
        "custom_components.dsvdc4ha.config_flow.resolve_vdsd_plan",
        return_value={"primaryGroup": 2, "buttons": [], "binary_inputs": [],
                      "sensors": [], "output": None, "displayId": "M", "name": "N"},
    ):
        result2 = await flow.async_step_device_entity_user_input(
            {"output_usage": "2"}
        )
    assert result2["step_id"] == "device_plan_summary"
    assert flow._vdsd_plans[0].user_choices.get("cover.blind", {}).get("output_usage") == "2"


@pytest.mark.asyncio
async def test_device_plan_summary_proceed_routes_to_model_features():
    flow = _make_subentry_flow()
    plan = _make_vdsd_plan()
    plan.resolved_vdsd = {
        "primaryGroup": 1, "displayId": "M", "name": "Lamp — Light",
        "buttons": [], "binary_inputs": [], "sensors": [], "output": None,
    }
    flow._vdsd_plans = [plan]
    flow._unsupported_entities = []
    flow._pending_vdsd_idx = 0

    result = await flow.async_step_device_plan_summary({"action": "proceed"})
    assert result["step_id"] == "device_model_features"


@pytest.mark.asyncio
async def test_device_plan_summary_cancel_routes_to_creation_mode():
    flow = _make_subentry_flow()
    flow._vdsd_plans = []
    flow._unsupported_entities = []
    result = await flow.async_step_device_plan_summary({"action": "cancel"})
    assert result["step_id"] == "creation_mode"
