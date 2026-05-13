"""Tests for listeners — push_expr evaluation."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from custom_components.dsvdc4ha.listeners import (
    seed_initial_values,
    setup_output_listeners,
)


@pytest.mark.asyncio
async def test_seed_initial_values_uses_push_expr():
    """seed_initial_values should eval push_expr for initial channel value."""
    hass = MagicMock()
    state = MagicMock()
    state.state = "open"
    state.attributes = {"current_position": 30}
    hass.states.get.return_value = state

    api = MagicMock()
    mock_device = MagicMock()
    mock_vdsd = MagicMock()
    mock_output = MagicMock()
    mock_ch = MagicMock()
    mock_ch.update_value = AsyncMock()
    mock_output.get_channel.return_value = mock_ch
    mock_vdsd.output = mock_output
    mock_device.get_vdsd.return_value = mock_vdsd
    api.get_device.return_value = mock_device

    await seed_initial_values(hass, api, "entry1", [{
        "output": {"channels": [{
            "dsIndex": 0,
            "channelType": 8,
            "read_entity": "cover.bedroom",
            "push_expr": "round(100-attrs.get('current_position',0),1)",
        }]},
    }])

    # current_position=30 → 100-30 = 70.0
    mock_ch.update_value.assert_awaited_once_with(70.0)


@pytest.mark.asyncio
async def test_seed_initial_values_fallback_float_state():
    """Without push_expr, seed uses float(state.state)."""
    hass = MagicMock()
    state = MagicMock()
    state.state = "42.5"
    state.attributes = {}
    hass.states.get.return_value = state

    api = MagicMock()
    mock_device = MagicMock()
    mock_vdsd = MagicMock()
    mock_output = MagicMock()
    mock_ch = MagicMock()
    mock_ch.update_value = AsyncMock()
    mock_output.get_channel.return_value = mock_ch
    mock_vdsd.output = mock_output
    mock_device.get_vdsd.return_value = mock_vdsd
    api.get_device.return_value = mock_device

    await seed_initial_values(hass, api, "entry1", [{
        "output": {"channels": [{
            "dsIndex": 0,
            "channelType": 19,
            "read_entity": "sensor.power",
        }]},
    }])

    mock_ch.update_value.assert_awaited_once_with(42.5)


def test_push_expr_state_change_fires_report():
    """State change with push_expr should call report_channel_value with eval'd value."""
    hass = MagicMock()
    hass.async_create_task = MagicMock()
    api = MagicMock()
    api.report_channel_value = AsyncMock()

    mock_device = MagicMock()
    mock_vdsd = MagicMock()
    mock_output = MagicMock()
    mock_ch = MagicMock()
    mock_output.get_channel.return_value = mock_ch
    mock_vdsd.output = mock_output
    mock_device.get_vdsd.return_value = mock_vdsd
    api.get_device.return_value = mock_device

    channels_data = [{"dsIndex": 0, "channelType": 8,
                      "read_entity": "cover.blind",
                      "push_expr": "round(100-attrs.get('current_position',0),1)"}]

    registered_cbs = []
    def _track(h, entity_id, cb):
        registered_cbs.append(cb)
        return lambda: None

    with patch("custom_components.dsvdc4ha.listeners.async_track_state_change_event",
               side_effect=_track):
        setup_output_listeners(hass, api, "entry1", [{"output": {"channels": channels_data}}])

    assert len(registered_cbs) == 1

    new_state = MagicMock()
    new_state.state = "open"
    new_state.attributes = {"current_position": 70}
    event = MagicMock()
    event.data = {"new_state": new_state}

    registered_cbs[0](event)

    hass.async_create_task.assert_called_once()
    api.report_channel_value.assert_called_once_with(mock_ch, 30.0)


def test_push_expr_fallback_to_float_state():
    """Without push_expr, state.state is cast to float."""
    hass = MagicMock()
    hass.async_create_task = MagicMock()
    api = MagicMock()
    api.report_channel_value = AsyncMock()

    mock_device = MagicMock()
    mock_vdsd = MagicMock()
    mock_output = MagicMock()
    mock_ch = MagicMock()
    mock_output.get_channel.return_value = mock_ch
    mock_vdsd.output = mock_output
    mock_device.get_vdsd.return_value = mock_vdsd
    api.get_device.return_value = mock_device

    channels_data = [{"dsIndex": 0, "channelType": 19, "read_entity": "switch.light"}]
    # no push_expr

    registered_cbs = []
    with patch("custom_components.dsvdc4ha.listeners.async_track_state_change_event",
               side_effect=lambda h, e, cb: (registered_cbs.append(cb), lambda: None)[1]):
        setup_output_listeners(hass, api, "entry1", [{"output": {"channels": channels_data}}])

    new_state = MagicMock()
    new_state.state = "75.0"
    new_state.attributes = {}
    event = MagicMock()
    event.data = {"new_state": new_state}
    registered_cbs[0](event)

    api.report_channel_value.assert_called_once_with(mock_ch, 75.0)
