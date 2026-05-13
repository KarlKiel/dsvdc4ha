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


@pytest.mark.asyncio
async def test_apply_expr_calls_ha_service():
    """apply_expr is eval'd with channel value and correct HA service is called."""
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
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

    captured_callbacks = []
    api.set_channel_applied_callback.side_effect = lambda out, cb: captured_callbacks.append(cb)

    channels_data = [{"dsIndex": 0, "channelType": 8,
                      "read_entity": "cover.blind",
                      "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(100-value)}}"}]

    with patch("custom_components.dsvdc4ha.listeners.async_track_state_change_event",
               return_value=lambda: None):
        setup_output_listeners(hass, api, "entry1", [{"output": {"channels": channels_data}}])

    assert len(captured_callbacks) == 1
    # value=25 → position = round(100-25) = 75
    await captured_callbacks[0](mock_output, {8: 25.0})

    hass.services.async_call.assert_awaited_once_with(
        domain="cover",
        service="set_cover_position",
        service_data={"position": 75},
        blocking=False,
    )


@pytest.mark.asyncio
async def test_apply_expr_multi_channel_single_callback():
    """Two channels with apply_expr → ONE callback handles both."""
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    api = MagicMock()
    api.report_channel_value = AsyncMock()

    mock_device = MagicMock()
    mock_vdsd = MagicMock()
    mock_output = MagicMock()
    mock_output.get_channel.return_value = MagicMock()
    mock_vdsd.output = mock_output
    mock_device.get_vdsd.return_value = mock_vdsd
    api.get_device.return_value = mock_device

    captured_callbacks = []
    api.set_channel_applied_callback.side_effect = lambda out, cb: captured_callbacks.append(cb)

    channels_data = [
        {"dsIndex": 0, "channelType": 1, "read_entity": "light.rgb",
         "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'brightness':round(value*2.55)}}"},
        {"dsIndex": 1, "channelType": 2, "read_entity": "light.rgb",
         "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'hs_color':(value,50)}}"},
    ]

    with patch("custom_components.dsvdc4ha.listeners.async_track_state_change_event",
               return_value=lambda: None):
        setup_output_listeners(hass, api, "entry1", [{"output": {"channels": channels_data}}])

    # Must be exactly ONE callback registered
    assert len(captured_callbacks) == 1

    # Fire channel type 1 (brightness), value=100 → brightness=255
    await captured_callbacks[0](mock_output, {1: 100.0})
    assert hass.services.async_call.await_count == 1
    call0 = hass.services.async_call.call_args_list[0]
    assert call0.kwargs["service_data"] == {"brightness": 255}

    # Fire channel type 2 (hue), value=180
    await captured_callbacks[0](mock_output, {2: 180.0})
    assert hass.services.async_call.await_count == 2
    call1 = hass.services.async_call.call_args_list[1]
    assert call1.kwargs["service_data"] == {"hs_color": (180.0, 50)}
