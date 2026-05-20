"""Tests for listeners — push_expr evaluation."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from custom_components.dsvdc4ha.listeners import (
    _eval_push,
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


def _make_bi_vdsd(bi_obj):
    """Helper: build the API / device mock stack for a binary-input seed test."""
    api = MagicMock()
    device = MagicMock()
    vdsd = MagicMock()
    vdsd.output = None
    vdsd.get_binary_input.return_value = bi_obj
    device.get_vdsd.return_value = vdsd
    api.get_device.return_value = device
    return api


@pytest.mark.asyncio
async def test_seed_binary_input_on_state_seeds_true():
    """'on' state → update_value(True, session=None)."""
    bi = MagicMock()
    bi.update_value = AsyncMock()
    bi.update_extended_value = AsyncMock()

    hass = MagicMock()
    state = MagicMock()
    state.state = "on"
    hass.states.get.return_value = state

    vdsd_data = [{"binary_inputs": [{"dsIndex": 0, "callback_entity": "binary_sensor.motion",
                                      "valueType": "boolean"}]}]
    await seed_initial_values(hass, _make_bi_vdsd(bi), "e1", vdsd_data)
    bi.update_value.assert_awaited_once_with(True, session=None)
    bi.update_extended_value.assert_not_awaited()


@pytest.mark.asyncio
async def test_seed_binary_input_off_state_seeds_false():
    """'off' state → update_value(False, session=None)."""
    bi = MagicMock()
    bi.update_value = AsyncMock()

    hass = MagicMock()
    state = MagicMock()
    state.state = "off"
    hass.states.get.return_value = state

    vdsd_data = [{"binary_inputs": [{"dsIndex": 0, "callback_entity": "binary_sensor.door",
                                      "valueType": "boolean"}]}]
    await seed_initial_values(hass, _make_bi_vdsd(bi), "e1", vdsd_data)
    bi.update_value.assert_awaited_once_with(False, session=None)


@pytest.mark.asyncio
async def test_seed_binary_input_integer_type_uses_extended_value():
    """valueType='integer' → update_extended_value with int cast of state."""
    bi = MagicMock()
    bi.update_value = AsyncMock()
    bi.update_extended_value = AsyncMock()

    hass = MagicMock()
    state = MagicMock()
    state.state = "2"
    hass.states.get.return_value = state

    vdsd_data = [{"binary_inputs": [{"dsIndex": 0, "callback_entity": "sensor.handle",
                                      "valueType": "integer"}]}]
    await seed_initial_values(hass, _make_bi_vdsd(bi), "e1", vdsd_data)
    bi.update_extended_value.assert_awaited_once_with(2, session=None)
    bi.update_value.assert_not_awaited()


@pytest.mark.asyncio
async def test_seed_binary_input_skipped_when_state_unavailable():
    """'unavailable' state → binary input is NOT seeded (value stays unknown)."""
    bi = MagicMock()
    bi.update_value = AsyncMock()

    hass = MagicMock()
    state = MagicMock()
    state.state = "unavailable"
    hass.states.get.return_value = state

    vdsd_data = [{"binary_inputs": [{"dsIndex": 0, "callback_entity": "binary_sensor.door",
                                      "valueType": "boolean"}]}]
    await seed_initial_values(hass, _make_bi_vdsd(bi), "e1", vdsd_data)
    bi.update_value.assert_not_awaited()


@pytest.mark.asyncio
async def test_seed_binary_input_skipped_when_no_callback_entity():
    """No callback_entity → binary input is NOT seeded."""
    bi = MagicMock()
    bi.update_value = AsyncMock()

    hass = MagicMock()

    vdsd_data = [{"binary_inputs": [{"dsIndex": 0, "valueType": "boolean"}]}]
    await seed_initial_values(hass, _make_bi_vdsd(bi), "e1", vdsd_data)
    bi.update_value.assert_not_awaited()


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
        target={"entity_id": "cover.blind"},
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
    assert call0.kwargs["target"] == {"entity_id": "light.rgb"}

    # Fire channel type 2 (hue), value=180
    await captured_callbacks[0](mock_output, {2: 180.0})
    assert hass.services.async_call.await_count == 2
    call1 = hass.services.async_call.call_args_list[1]
    assert call1.kwargs["service_data"] == {"hs_color": (180.0, 50)}
    assert call1.kwargs["target"] == {"entity_id": "light.rgb"}


# ── _light_apply unit tests ──────────────────────────────────────────────────

from custom_components.dsvdc4ha.listeners import _light_apply


def test_light_apply_brightness_only():
    result = _light_apply({1: 50.0}, {})
    assert result["service"] == "turn_on"
    assert result["service_data"]["brightness"] == round(50.0 * 2.55)
    assert "hs_color" not in result["service_data"]
    assert "color_temp" not in result["service_data"]


def test_light_apply_brightness_zero_turns_off():
    result = _light_apply({1: 0.0}, {})
    assert result["service"] == "turn_off"
    assert result["service_data"] == {}


def test_light_apply_brightness_negative_turns_off():
    assert _light_apply({1: -1.0}, {})["service"] == "turn_off"


def test_light_apply_hs_both():
    result = _light_apply({2: 180.0, 3: 75.0}, {})
    assert result["service"] == "turn_on"
    assert result["service_data"]["hs_color"] == (180.0, 75.0)


def test_light_apply_hue_only_uses_current_sat_from_attrs():
    result = _light_apply({2: 200.0}, {"hs_color": (45.0, 90.0)})
    assert result["service_data"]["hs_color"] == (200.0, 90.0)


def test_light_apply_sat_only_uses_current_hue_from_attrs():
    result = _light_apply({3: 50.0}, {"hs_color": (45.0, 90.0)})
    assert result["service_data"]["hs_color"] == (45.0, 50.0)


def test_light_apply_ct_only():
    result = _light_apply({4: 370.0}, {})
    assert result["service"] == "turn_on"
    assert result["service_data"]["color_temp_kelvin"] == round(1_000_000 / 370)


def test_light_apply_brightness_and_ct():
    result = _light_apply({1: 80.0, 4: 300.0}, {})
    assert result["service_data"]["brightness"] == round(80.0 * 2.55)
    assert result["service_data"]["color_temp_kelvin"] == round(1_000_000 / 300)


def test_light_apply_brightness_and_hs():
    result = _light_apply({1: 60.0, 2: 120.0, 3: 80.0}, {})
    assert result["service_data"]["brightness"] == round(60.0 * 2.55)
    assert result["service_data"]["hs_color"] == (120.0, 80.0)


def test_light_apply_cie_priority_over_hs():
    attrs = {"xy_color": (0.3127, 0.3290), "hs_color": (45.0, 90.0)}
    result = _light_apply({2: 180.0, 3: 75.0, 5: 3127.0, 6: 3290.0}, attrs)
    assert "xy_color" in result["service_data"]
    assert "hs_color" not in result["service_data"]
    assert result["service_data"]["xy_color"] == (round(3127.0 / 10000, 4), round(3290.0 / 10000, 4))


def test_light_apply_cie_partial_uses_attrs():
    attrs = {"xy_color": (0.3127, 0.3290)}
    result = _light_apply({5: 2000.0}, attrs)
    assert "xy_color" in result["service_data"]
    assert result["service_data"]["xy_color"][0] == round(2000.0 / 10000, 4)
    assert result["service_data"]["xy_color"][1] == round(0.3290, 4)


def test_light_apply_empty_channel_updates():
    result = _light_apply({}, {})
    assert result["service"] == "turn_on"
    assert result["service_data"] == {}


@pytest.mark.asyncio
async def test_apply_all_expr_callback_fires_once():
    """apply_all_expr registers ONE callback; async_call called exactly once per DS scene."""
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.states = MagicMock()
    hass.states.get.return_value = None

    api = MagicMock()
    mock_device = MagicMock()
    mock_vdsd = MagicMock()
    mock_output = MagicMock()
    mock_output.get_channel.return_value = MagicMock()
    mock_vdsd.output = mock_output
    mock_device.get_vdsd.return_value = mock_vdsd
    api.get_device.return_value = mock_device

    captured = []
    api.set_channel_applied_callback.side_effect = lambda out, cb: captured.append(cb)

    channels_data = [
        {"dsIndex": 0, "channelType": 1, "read_entity": "light.rgb",
         "push_expr": "round(attrs.get('brightness', 0) / 2.55, 1)"},
        {"dsIndex": 1, "channelType": 2, "read_entity": "light.rgb",
         "push_expr": "attrs.get('hs_color', (0, 0))[0]"},
    ]
    output_data = {
        "channels": channels_data,
        "apply_all_expr": "_light_apply(channel_updates, attrs)",
    }

    with patch("custom_components.dsvdc4ha.listeners.async_track_state_change_event",
               return_value=lambda: None):
        setup_output_listeners(hass, api, "entry1", [{"output": output_data}])

    assert len(captured) == 1, "Expected exactly one callback registered"

    await captured[0](mock_output, {1: 80.0, 2: 180.0})

    assert hass.services.async_call.await_count == 1
    call_kwargs = hass.services.async_call.call_args.kwargs
    assert call_kwargs["domain"] == "light"
    assert call_kwargs["service"] == "turn_on"
    assert call_kwargs["target"] == {"entity_id": "light.rgb"}
    assert "entity_id" not in call_kwargs.get("service_data", {})


@pytest.mark.asyncio
async def test_apply_expr_injects_entity_id():
    """apply_expr callback injects read_entity as entity_id into service_data."""
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.states.get.return_value = None
    api = MagicMock()
    mock_device = MagicMock()
    mock_vdsd = MagicMock()
    mock_output = MagicMock()
    mock_output.get_channel.return_value = MagicMock()
    mock_vdsd.output = mock_output
    mock_device.get_vdsd.return_value = mock_vdsd
    api.get_device.return_value = mock_device
    captured = []
    api.set_channel_applied_callback.side_effect = lambda out, cb: captured.append(cb)

    channels_data = [{"dsIndex": 0, "channelType": 8,
                      "read_entity": "cover.blind",
                      "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(100-value)}}"}]
    with patch("custom_components.dsvdc4ha.listeners.async_track_state_change_event",
               return_value=lambda: None):
        setup_output_listeners(hass, api, "entry1", [{"output": {"channels": channels_data}}])

    await captured[0](mock_output, {8: 25.0})

    call_kw = hass.services.async_call.call_args.kwargs
    assert call_kw["target"] == {"entity_id": "cover.blind"}
    assert call_kw["service_data"]["position"] == 75
    assert "entity_id" not in call_kw["service_data"]


@pytest.mark.asyncio
async def test_apply_all_expr_injects_entity_id():
    """apply_all_expr callback injects read_entity as entity_id into service_data."""
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.states.get.return_value = None
    api = MagicMock()
    mock_device = MagicMock()
    mock_vdsd = MagicMock()
    mock_output = MagicMock()
    mock_output.get_channel.return_value = MagicMock()
    mock_vdsd.output = mock_output
    mock_device.get_vdsd.return_value = mock_vdsd
    api.get_device.return_value = mock_device
    captured = []
    api.set_channel_applied_callback.side_effect = lambda out, cb: captured.append(cb)

    channels_data = [{"dsIndex": 0, "channelType": 1, "read_entity": "light.bedroom",
                      "push_expr": "100.0 if entity.state == 'on' else 0.0"}]
    output_data = {"channels": channels_data,
                   "apply_all_expr": "_light_apply(channel_updates, attrs)"}
    with patch("custom_components.dsvdc4ha.listeners.async_track_state_change_event",
               return_value=lambda: None):
        setup_output_listeners(hass, api, "entry1", [{"output": output_data}])

    await captured[0](mock_output, {1: 80.0})

    call_kw = hass.services.async_call.call_args.kwargs
    assert call_kw["target"] == {"entity_id": "light.bedroom"}
    assert "entity_id" not in call_kw.get("service_data", {})


def test_light_apply_none_xy_color_in_attrs():
    """_light_apply does not crash when xy_color attr is None."""
    result = _light_apply({5: 3127.0}, {"xy_color": None})
    assert result["service"] == "turn_on"
    assert "xy_color" in result["service_data"]


def test_light_apply_none_hs_color_in_attrs():
    """_light_apply does not crash when hs_color attr is None."""
    result = _light_apply({2: 180.0}, {"hs_color": None})
    assert result["service"] == "turn_on"
    assert result["service_data"]["hs_color"][0] == 180.0


@pytest.mark.asyncio
async def test_apply_all_expr_does_not_affect_per_channel_path():
    """Outputs without apply_all_expr still use the existing per-channel expr path."""
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    api = MagicMock()
    mock_device = MagicMock()
    mock_vdsd = MagicMock()
    mock_output = MagicMock()
    mock_output.get_channel.return_value = MagicMock()
    mock_vdsd.output = mock_output
    mock_device.get_vdsd.return_value = mock_vdsd
    api.get_device.return_value = mock_device

    captured = []
    api.set_channel_applied_callback.side_effect = lambda out, cb: captured.append(cb)

    channels_data = [
        {"dsIndex": 0, "channelType": 19, "read_entity": "switch.test",
         "apply_expr": "{'domain':'switch','service':'turn_on' if value>=1 else 'turn_off','service_data':{}}",
         "push_expr": "1 if entity.state == 'on' else 0"},
    ]
    output_data = {"channels": channels_data}  # no apply_all_expr

    with patch("custom_components.dsvdc4ha.listeners.async_track_state_change_event",
               return_value=lambda: None):
        setup_output_listeners(hass, api, "entry1", [{"output": output_data}])

    assert len(captured) == 1

    state = MagicMock()
    state.state = "on"
    hass.states.get.return_value = state
    await captured[0](mock_output, {19: 1.0})
    assert hass.services.async_call.await_count == 1


def test_eval_push_old_format_brightness_none_returns_zero():
    """Old-format push_expr (attrs.get('brightness', 0)) must not crash when brightness=None.

    HA stores brightness=None in attributes when a light is off, and Python's
    dict.get(key, default) returns None (not default) when the key exists with
    value None.  The _eval_push None-filter is the fix — this test locks it in.
    """
    state = MagicMock()
    state.state = "off"
    state.attributes = {"brightness": None, "color_mode": "brightness"}

    # Old config entry format — does not guard against None
    old_expr = "round(attrs.get('brightness', 0) / 2.55, 1)"
    result = _eval_push(old_expr, state)
    assert result == 0.0


@pytest.mark.asyncio
async def test_apply_all_expr_brightness_zero_calls_turn_off():
    """When dSM sends brightness=0, _on_channel_applied_all must call light.turn_off."""
    from custom_components.dsvdc4ha.listeners import _light_apply  # noqa: PLC0415

    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    api = MagicMock()
    mock_device = MagicMock()
    mock_vdsd = MagicMock()
    mock_output = MagicMock()
    mock_output.get_channel.return_value = MagicMock()
    mock_vdsd.output = mock_output
    mock_device.get_vdsd.return_value = mock_vdsd
    api.get_device.return_value = mock_device

    captured = []
    api.set_channel_applied_callback.side_effect = lambda out, cb: captured.append(cb)

    output_data = {
        "apply_all_expr": "_light_apply(channel_updates, attrs)",
        "channels": [{"dsIndex": 0, "channelType": 1, "read_entity": "light.bedroom"}],
    }

    light_state = MagicMock()
    light_state.state = "on"
    light_state.attributes = {"brightness": 200, "color_mode": "brightness"}
    hass.states.get.return_value = light_state

    with patch("custom_components.dsvdc4ha.listeners.async_track_state_change_event",
               return_value=lambda: None):
        setup_output_listeners(hass, api, "entry1", [{"output": output_data}])

    assert len(captured) == 1

    # dSM sends brightness=0 → must fire turn_off
    await captured[0](mock_output, {1: 0.0})

    call_kw = hass.services.async_call.call_args.kwargs
    assert call_kw["service"] == "turn_off"
    assert call_kw["target"] == {"entity_id": "light.bedroom"}
