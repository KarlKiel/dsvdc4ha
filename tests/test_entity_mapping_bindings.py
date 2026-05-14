"""Validate that all output channel defs have apply_expr/push_expr."""
from __future__ import annotations
import pytest
from custom_components.dsvdc4ha.entity_mapping import (
    ENTITY_MAPPING, needs_user_input, get_entity_mapping,
)


def _collect_channel_defs() -> list[tuple[str, str | None, int, dict]]:
    """Return (domain, device_class, ch_index, ch_dict) for every output channel def."""
    result = []
    for entry in ENTITY_MAPPING:
        o = entry.get("output")
        if not o:
            continue
        domain = entry["domain"]
        dc = entry["device_class"]
        for i, ch in enumerate(o.get("channels", [])):
            result.append((domain, dc, i, ch))
        for usage_channels in o.get("channels_by_usage", {}).values():
            for i, ch in enumerate(usage_channels):
                result.append((domain, dc, i, ch))
    return result


@pytest.mark.parametrize("domain,dc,ch_idx,ch", _collect_channel_defs())
def test_channel_has_apply_expr(domain, dc, ch_idx, ch):
    assert "apply_expr" in ch, (
        f"{domain}/{dc} ch{ch_idx} (channel_type={ch['channel_type']}) missing apply_expr"
    )
    assert isinstance(ch["apply_expr"], str) and ch["apply_expr"]


@pytest.mark.parametrize("domain,dc,ch_idx,ch", _collect_channel_defs())
def test_channel_has_push_expr(domain, dc, ch_idx, ch):
    assert "push_expr" in ch, (
        f"{domain}/{dc} ch{ch_idx} (channel_type={ch['channel_type']}) missing push_expr"
    )
    assert isinstance(ch["push_expr"], str) and ch["push_expr"]


def _mapping(domain, dc):
    return get_entity_mapping(domain, dc)


# --- Category A: bi_group choices ---
@pytest.mark.parametrize("domain,dc,expected_default", [
    ("binary_sensor", "carbon_monoxide", 6),
    ("binary_sensor", "cold", 3),
    ("binary_sensor", "gas", 6),
    ("binary_sensor", "heat", 3),
    ("binary_sensor", "light", 1),
    ("binary_sensor", "moisture", 6),
    ("binary_sensor", "motion", 1),
    ("binary_sensor", "opening", 8),
    ("binary_sensor", "sound", 8),
    ("event", "motion", 1),
])
def test_bi_group_choices_present(domain, dc, expected_default):
    m = _mapping(domain, dc)
    assert m is not None
    bi = m["binary_input"]
    assert "group_choices" in bi, f"{domain}/{dc} missing binary_input.group_choices"
    choices_values = [v for v, _ in bi["group_choices"]]
    assert bi["group"] in choices_values, "current default not in choices"
    assert bi["group"] == expected_default


def test_bi_group_moisture_limited_choices():
    m = _mapping("binary_sensor", "moisture")
    choices_values = [v for v, _ in m["binary_input"]["group_choices"]]
    assert sorted(choices_values) == sorted([6, 3, 8])


# --- Category B: sensor_function choices ---
def test_binary_sensor_none_sensor_function_choices_any():
    m = _mapping("binary_sensor", None)
    bi = m["binary_input"]
    assert bi.get("sensor_function_choices") == "any"
    assert bi["sensor_function"] == 0


def test_binary_sensor_moving_sensor_function_default_is_motion():
    m = _mapping("binary_sensor", "moving")
    bi = m["binary_input"]
    assert bi["sensor_function"] == 5, "moving default should be MOTION (5)"
    assert bi.get("sensor_function_choices") == "any"


# --- Category C: sensor_usage choices ---
@pytest.mark.parametrize("dc,expected_options_include", [
    ("aqi", [1, 2]),
    ("distance", [4, 5, 6]),
    ("duration", [4, 5, 6]),
    ("gas", [0, 1, 2, 4, 5, 6]),
    ("humidity", [0, 1, 2, 4, 5, 6]),
    ("illuminance", [0, 1, 2, 4, 5, 6]),
    ("moisture", [0, 1, 2, 4, 5, 6]),
    ("speed", [0, 1, 2, 4, 5, 6]),
    ("temperature", [0, 1, 2, 4, 5, 6]),
])
def test_sensor_usage_choices_present(dc, expected_options_include):
    m = _mapping("sensor", dc)
    assert m is not None
    s = m["sensor"]
    assert "sensor_usage_choices" in s, f"sensor/{dc} missing sensor_usage_choices"
    choices = s["sensor_usage_choices"]
    assert choices != "any"
    actual_values = [v for v, _ in choices]
    for v in expected_options_include:
        assert v in actual_values, f"sensor/{dc} choices missing {v}"
    assert s["sensor_usage"] in actual_values, f"sensor/{dc} default {s['sensor_usage']} not in choices"


def test_sensor_none_sensor_usage_choices_any():
    m = _mapping("sensor", None)
    assert m["sensor"]["sensor_usage_choices"] == "any"


# --- needs_user_input ---
def test_needs_user_input_sensor_usage_choices():
    m = _mapping("sensor", "temperature")
    assert needs_user_input(m)


def test_needs_user_input_bi_group_choices():
    m = _mapping("binary_sensor", "motion")
    assert needs_user_input(m)


def test_needs_user_input_sf_any():
    m = _mapping("binary_sensor", None)
    assert needs_user_input(m)
