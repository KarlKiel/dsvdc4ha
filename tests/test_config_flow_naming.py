"""Tests for config flow naming features — config_entry_name, _count_artefacts, auto-naming."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from homeassistant.data_entry_flow import FlowResultType

from custom_components.dsvdc4ha.config_flow import VdsdSubentryFlowHandler


def _make_subentry_flow() -> VdsdSubentryFlowHandler:
    """Create a bare VdsdSubentryFlowHandler with hass and context set up."""
    flow = VdsdSubentryFlowHandler()
    flow.hass = MagicMock()
    flow.context = {"source": "user", "entry_id": "hub-entry-123"}
    return flow


# ---------------------------------------------------------------------------
# Test 1: async_step_config_entry_name stores entry_name and calls async_step_creation_mode
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_config_entry_name_step_stores_entry_name():
    """Verify that async_step_config_entry_name sets flow._entry_name and calls async_step_creation_mode."""
    flow = _make_subentry_flow()

    # Mock async_step_creation_mode to return a sentinel value
    sentinel = {"type": FlowResultType.FORM, "step_id": "creation_mode"}
    flow.async_step_creation_mode = AsyncMock(return_value=sentinel)

    result = await flow.async_step_config_entry_name({"entry_name": "My Physical Device"})

    assert flow._entry_name == "My Physical Device"
    flow.async_step_creation_mode.assert_awaited_once()
    assert result == sentinel


# ---------------------------------------------------------------------------
# Test 2: async_step_config_entry_name strips whitespace
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_config_entry_name_step_strips_whitespace():
    """Verify that async_step_config_entry_name strips leading/trailing whitespace."""
    flow = _make_subentry_flow()

    sentinel = {"type": FlowResultType.FORM, "step_id": "creation_mode"}
    flow.async_step_creation_mode = AsyncMock(return_value=sentinel)

    result = await flow.async_step_config_entry_name({"entry_name": "  Trimmed  "})

    assert flow._entry_name == "Trimmed"
    flow.async_step_creation_mode.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 3: async_step_config_entry_name shows form without input
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_config_entry_name_step_shows_form_without_input():
    """Verify that async_step_config_entry_name(None) returns a FORM result."""
    flow = _make_subentry_flow()

    result = await flow.async_step_config_entry_name(None)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "config_entry_name"


# ---------------------------------------------------------------------------
# Test 4: _count_artefacts with single sensor
# ---------------------------------------------------------------------------

def test_count_artefacts_single_sensor():
    """Verify _count_artefacts() == 1 when only one sensor exists."""
    flow = _make_subentry_flow()

    flow._current_sensors = [{"name": "Temperature"}]
    flow._current_buttons = []
    flow._current_binary_inputs = []
    flow._current_output = None

    count = flow._count_artefacts()

    assert count == 1


# ---------------------------------------------------------------------------
# Test 5: _count_artefacts with multiple artefact types
# ---------------------------------------------------------------------------

def test_count_artefacts_multiple():
    """Verify _count_artefacts() == 4 when one of each type exists."""
    flow = _make_subentry_flow()

    flow._current_buttons = [{"name": "Button1"}]
    flow._current_binary_inputs = [{"name": "BinaryInput1"}]
    flow._current_sensors = [{"name": "Sensor1"}]
    flow._current_output = {"name": "Output1"}

    count = flow._count_artefacts()

    assert count == 4


# ---------------------------------------------------------------------------
# Test 6: _count_artefacts does not count None output
# ---------------------------------------------------------------------------

def test_count_artefacts_no_output_not_counted():
    """Verify _count_artefacts() == 1 when output is None and one sensor exists."""
    flow = _make_subentry_flow()

    flow._current_sensors = [{"name": "Sensor1"}]
    flow._current_buttons = []
    flow._current_binary_inputs = []
    flow._current_output = None

    count = flow._count_artefacts()

    assert count == 1


# ---------------------------------------------------------------------------
# Test 7: _auto_apply_single_artefact_name with single sensor
# ---------------------------------------------------------------------------

def test_auto_apply_single_artefact_name_uses_sensor_name():
    """Verify _auto_apply_single_artefact_name uses sensor name when single artefact."""
    flow = _make_subentry_flow()

    # Set up current state: one sensor, rest empty
    flow._current_sensors = [{"name": "Temperature"}]
    flow._current_buttons = []
    flow._current_binary_inputs = []
    flow._current_output = None

    # Set up vdSD with initial values to be overwritten
    flow._current_vdsd = {"displayId": "old", "name": "old_name"}

    # Call the method
    flow._auto_apply_single_artefact_name()

    # Verify both name and displayId are set to sensor name
    assert flow._current_vdsd["name"] == "Temperature"
    assert flow._current_vdsd["displayId"] == "Temperature"


# ---------------------------------------------------------------------------
# Test 8: _auto_apply_single_artefact_name with single output
# ---------------------------------------------------------------------------

def test_auto_apply_single_artefact_name_uses_output_name():
    """Verify _auto_apply_single_artefact_name uses output name when single artefact."""
    flow = _make_subentry_flow()

    # Set up current state: one output, rest empty
    flow._current_sensors = []
    flow._current_buttons = []
    flow._current_binary_inputs = []
    flow._current_output = {"name": "Dimmer Light"}

    # Set up vdSD with initial values to be overwritten
    flow._current_vdsd = {"displayId": "old", "name": "old_name"}

    # Call the method
    flow._auto_apply_single_artefact_name()

    # Verify both name and displayId are set to output name
    assert flow._current_vdsd["name"] == "Dimmer Light"
    assert flow._current_vdsd["displayId"] == "Dimmer Light"


# ---------------------------------------------------------------------------
# Additional edge case tests
# ---------------------------------------------------------------------------

def test_auto_apply_single_artefact_name_with_button():
    """Verify _auto_apply_single_artefact_name uses button name when single artefact."""
    flow = _make_subentry_flow()

    # Set up current state: one button, rest empty
    flow._current_buttons = [{"name": "Power Button"}]
    flow._current_sensors = []
    flow._current_binary_inputs = []
    flow._current_output = None

    flow._current_vdsd = {"displayId": "old", "name": "old_name"}

    flow._auto_apply_single_artefact_name()

    assert flow._current_vdsd["name"] == "Power Button"
    assert flow._current_vdsd["displayId"] == "Power Button"


def test_auto_apply_single_artefact_name_with_binary_input():
    """Verify _auto_apply_single_artefact_name uses binary input name when single artefact."""
    flow = _make_subentry_flow()

    # Set up current state: one binary input, rest empty
    flow._current_binary_inputs = [{"name": "Motion Sensor"}]
    flow._current_buttons = []
    flow._current_sensors = []
    flow._current_output = None

    flow._current_vdsd = {"displayId": "old", "name": "old_name"}

    flow._auto_apply_single_artefact_name()

    assert flow._current_vdsd["name"] == "Motion Sensor"
    assert flow._current_vdsd["displayId"] == "Motion Sensor"


def test_auto_apply_single_artefact_name_empty_artefacts():
    """Verify _auto_apply_single_artefact_name does nothing when no artefacts exist."""
    flow = _make_subentry_flow()

    # Set up current state: all empty
    flow._current_buttons = []
    flow._current_sensors = []
    flow._current_binary_inputs = []
    flow._current_output = None

    flow._current_vdsd = {"displayId": "original", "name": "original_name"}

    flow._auto_apply_single_artefact_name()

    # Should not change since no artefact name was found
    assert flow._current_vdsd["name"] == "original_name"
    assert flow._current_vdsd["displayId"] == "original"


def test_count_artefacts_multiple_sensors():
    """Verify _count_artefacts counts all sensors."""
    flow = _make_subentry_flow()

    flow._current_sensors = [
        {"name": "Temperature"},
        {"name": "Humidity"},
        {"name": "Pressure"}
    ]
    flow._current_buttons = []
    flow._current_binary_inputs = []
    flow._current_output = None

    count = flow._count_artefacts()

    assert count == 3


def test_count_artefacts_multiple_buttons():
    """Verify _count_artefacts counts all buttons."""
    flow = _make_subentry_flow()

    flow._current_buttons = [
        {"name": "Button1"},
        {"name": "Button2"}
    ]
    flow._current_sensors = []
    flow._current_binary_inputs = []
    flow._current_output = None

    count = flow._count_artefacts()

    assert count == 2
