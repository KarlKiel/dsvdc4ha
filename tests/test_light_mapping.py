"""Tests for light capability derivation and resolve_entity_mapping."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from unittest.mock import MagicMock
import pytest
from custom_components.dsvdc4ha.entity_mapping import _derive_light_output_config, resolve_entity_mapping
from pydsvdcapi.enums import OutputFunction, OutputMode, OutputChannelType

def _make_state(supported_color_modes, color_mode=None):
    state = MagicMock()
    state.state = "on"
    state.attributes = {
        "supported_color_modes": list(supported_color_modes),
        "color_mode": color_mode,
        "brightness": 128,
        "hs_color": (180.0, 50.0),
        "color_temp": 370,
        "xy_color": (0.3, 0.3),
    }
    return state

def test_derive_light_onoff():
    state = _make_state({"onoff"})
    result = _derive_light_output_config("light.test", state)
    o = result["output"]
    assert o["function"] == OutputFunction.ON_OFF
    assert o["mode"] == OutputMode.BINARY
    assert len(o["channels"]) == 1
    assert o["channels"][0]["channel_type"] == OutputChannelType.BRIGHTNESS
    assert result["model_uid"] == "ha-light-onoff"
    assert "apply_all_expr" in o

def test_derive_light_dimmer():
    result = _derive_light_output_config("light.test", _make_state({"brightness"}))
    o = result["output"]
    assert o["function"] == OutputFunction.DIMMER
    assert o["mode"] == OutputMode.GRADUAL
    assert len(o["channels"]) == 1
    assert result["model_uid"] == "ha-light-dimmer"

def test_derive_light_dimmer_white_mode():
    assert _derive_light_output_config("light.test", _make_state({"white"}))["output"]["function"] == OutputFunction.DIMMER

def test_derive_light_color_temp():
    result = _derive_light_output_config("light.test", _make_state({"color_temp"}))
    o = result["output"]
    assert o["function"] == OutputFunction.DIMMER_COLOR_TEMP
    assert len(o["channels"]) == 2
    ch_types = {ch["channel_type"] for ch in o["channels"]}
    assert ch_types == {OutputChannelType.BRIGHTNESS, OutputChannelType.COLOR_TEMPERATURE}
    assert result["model_uid"] == "ha-light-color-temp"

def test_derive_light_full_color_hs():
    result = _derive_light_output_config("light.test", _make_state({"hs", "color_temp"}))
    o = result["output"]
    assert o["function"] == OutputFunction.FULL_COLOR_DIMMER
    assert len(o["channels"]) == 6
    ch_types = {ch["channel_type"] for ch in o["channels"]}
    assert ch_types == {OutputChannelType.BRIGHTNESS, OutputChannelType.HUE, OutputChannelType.SATURATION, OutputChannelType.COLOR_TEMPERATURE, OutputChannelType.CIE_X, OutputChannelType.CIE_Y}
    assert result["model_uid"] == "ha-light-full-color"

def test_derive_light_full_color_rgbww():
    result = _derive_light_output_config("light.test", _make_state({"rgbww", "color_temp"}))
    assert result["output"]["function"] == OutputFunction.FULL_COLOR_DIMMER
    assert len(result["output"]["channels"]) == 6

def test_derive_light_full_color_rgb():
    assert _derive_light_output_config("light.test", _make_state({"rgb"}))["output"]["function"] == OutputFunction.FULL_COLOR_DIMMER

def test_derive_light_fallback_unavailable():
    result = _derive_light_output_config("light.test", None)
    assert result["output"]["function"] == OutputFunction.FULL_COLOR_DIMMER
    assert len(result["output"]["channels"]) == 6

def test_derive_light_fallback_empty_modes():
    assert _derive_light_output_config("light.test", _make_state([]))["output"]["function"] == OutputFunction.FULL_COLOR_DIMMER

def test_all_tiers_have_apply_all_expr():
    for modes in [{"onoff"}, {"brightness"}, {"color_temp"}, {"hs"}]:
        result = _derive_light_output_config("light.test", _make_state(modes))
        assert "apply_all_expr" in result["output"], f"Missing apply_all_expr for {modes}"

def test_all_tiers_channels_have_push_expr():
    for modes in [{"onoff"}, {"brightness"}, {"color_temp"}, {"hs"}]:
        for ch in _derive_light_output_config("light.test", _make_state(modes))["output"]["channels"]:
            assert "push_expr" in ch, f"Channel missing push_expr for {modes}: {ch}"

def test_all_channels_reference_entity():
    for ch in _derive_light_output_config("light.rgb_lamp", _make_state({"hs"}))["output"]["channels"]:
        assert ch.get("read_entity") == "light.rgb_lamp"

def test_resolve_entity_mapping_no_derive_fn():
    result = resolve_entity_mapping("switch.test", None, "switch", None)
    assert result is not None
    assert result["domain"] == "switch"
    assert "derive_fn" not in result

def test_resolve_entity_mapping_unsupported_domain():
    assert resolve_entity_mapping("media_player.tv", None, "media_player", None) is None

def test_resolve_entity_mapping_light_with_state():
    state = _make_state({"brightness"})
    result = resolve_entity_mapping("light.lamp", state, "light", None)
    assert result is not None
    assert result["output"]["function"] == OutputFunction.DIMMER
    assert "derive_fn" not in result

def test_resolve_entity_mapping_light_without_state():
    result = resolve_entity_mapping("light.lamp", None, "light", None)
    assert result is not None
    assert result["output"]["function"] == OutputFunction.FULL_COLOR_DIMMER


def test_full_color_channel_order_matches_pydsvdcapi():
    """FULL_COLOR_DIMMER channels must be in pydsvdcapi canonical order: BRIGHTNESS, CT, HUE, SAT, CIE_X, CIE_Y."""
    result = _derive_light_output_config("light.test", _make_state({"hs"}))
    channels = result["output"]["channels"]
    assert len(channels) == 6
    assert channels[0]["channel_type"] == OutputChannelType.BRIGHTNESS
    assert channels[1]["channel_type"] == OutputChannelType.COLOR_TEMPERATURE
    assert channels[2]["channel_type"] == OutputChannelType.HUE
    assert channels[3]["channel_type"] == OutputChannelType.SATURATION
    assert channels[4]["channel_type"] == OutputChannelType.CIE_X
    assert channels[5]["channel_type"] == OutputChannelType.CIE_Y


def test_brightness_push_expr_returns_zero_when_off():
    """BRIGHTNESS push_expr for DIMMER returns 0.0 when entity state is 'off'."""
    from custom_components.dsvdc4ha.listeners import eval_push as _eval_push
    result = _derive_light_output_config("light.test", _make_state({"brightness"}))
    expr = result["output"]["channels"][0]["push_expr"]
    state_off = MagicMock()
    state_off.state = "off"
    state_off.attributes = {"brightness": 200}
    assert _eval_push(expr, state_off) == 0.0


def test_brightness_push_expr_handles_none_brightness():
    """BRIGHTNESS push_expr treats None brightness as 0 (no crash, no TypeError)."""
    from custom_components.dsvdc4ha.listeners import eval_push as _eval_push
    result = _derive_light_output_config("light.test", _make_state({"brightness"}))
    expr = result["output"]["channels"][0]["push_expr"]
    state_none = MagicMock()
    state_none.state = "on"
    state_none.attributes = {"brightness": None}
    assert _eval_push(expr, state_none) == 0.0


def test_hs_push_expr_handles_none_hs_color():
    """HUE/SAT push_expr treats None hs_color as (0, 0) — both default to 0 (no color)."""
    from custom_components.dsvdc4ha.listeners import eval_push as _eval_push
    result = _derive_light_output_config("light.test", _make_state({"hs"}))
    channels = result["output"]["channels"]
    hue_ch = next(ch for ch in channels if ch["channel_type"] == OutputChannelType.HUE)
    sat_ch = next(ch for ch in channels if ch["channel_type"] == OutputChannelType.SATURATION)
    state_none = MagicMock()
    state_none.state = "on"
    state_none.attributes = {"hs_color": None, "color_mode": "hs"}
    assert _eval_push(hue_ch["push_expr"], state_none) == 0.0
    assert _eval_push(sat_ch["push_expr"], state_none) == 0.0


def test_xy_push_expr_handles_none_xy_color():
    """CIE_X/CIE_Y push_expr treats None xy_color as (0.3127, 0.3290) without crashing."""
    from custom_components.dsvdc4ha.listeners import eval_push as _eval_push
    result = _derive_light_output_config("light.test", _make_state({"hs"}))
    channels = result["output"]["channels"]
    cie_x = next(ch for ch in channels if ch["channel_type"] == OutputChannelType.CIE_X)
    state_none = MagicMock()
    state_none.state = "on"
    state_none.attributes = {"xy_color": None}
    val = _eval_push(cie_x["push_expr"], state_none)
    assert val == round(0.3127 * 10000, 1)
