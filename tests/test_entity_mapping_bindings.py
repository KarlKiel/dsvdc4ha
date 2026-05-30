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
    assert bi.get("sensor_function_choices") == [(5, "Motion (5)"), (0, "Generic (0)")]


# --- Category C: sensor_usage choices ---
@pytest.mark.parametrize("dc,expected_options_include", [
    ("aqi", [1, 2]),
    ("distance", [4, 5, 6]),
    ("duration", [4, 5, 6]),
    ("gas", [0, 1, 2, 4]),
    ("humidity", [0, 1, 2, 4]),
    ("illuminance", [0, 1, 2, 4]),
    ("moisture", [0, 1, 2, 4]),
    ("speed", [0, 1, 2, 4]),
    ("temperature", [0, 1, 2, 4]),
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


def test_needs_user_input_shadow_position_timing():
    m = {"output": {"shadow_position_timing": True}}
    assert needs_user_input(m)


def test_needs_user_input_shadow_angle_timing():
    m = {"output": {"shadow_angle_timing": True}}
    assert needs_user_input(m)


def test_needs_user_input_returns_false_without_flags():
    m = {"output": {"function": 0, "groups": [2]}}
    assert not needs_user_input(m)


def test_awning_output_has_shadow_position_timing():
    m = _mapping("cover", "awning")
    assert m["output"].get("shadow_position_timing") is True
    assert not m["output"].get("shadow_angle_timing")


def test_blind_output_has_both_shadow_timing_flags():
    m = _mapping("cover", "blind")
    assert m["output"].get("shadow_position_timing") is True
    assert m["output"].get("shadow_angle_timing") is True


def test_curtain_output_has_position_timing_only():
    m = _mapping("cover", "curtain")
    assert m["output"].get("shadow_position_timing") is True
    assert not m["output"].get("shadow_angle_timing")


def test_gate_output_has_shadow_position_timing_only():
    m = _mapping("cover", "gate")
    assert m["output"].get("shadow_position_timing") is True
    assert not m["output"].get("shadow_angle_timing")


def test_shade_output_has_shadow_position_timing_only():
    m = _mapping("cover", "shade")
    assert m["output"].get("shadow_position_timing") is True
    assert not m["output"].get("shadow_angle_timing")


def test_shutter_output_has_both_shadow_timing_flags():
    m = _mapping("cover", "shutter")
    assert m["output"].get("shadow_position_timing") is True
    assert m["output"].get("shadow_angle_timing") is True


def test_window_cover_output_has_both_shadow_timing_flags():
    m = _mapping("cover", "window")
    assert m["output"].get("shadow_position_timing") is True
    assert m["output"].get("shadow_angle_timing") is True


def test_door_output_has_no_shadow_timing_flags():
    m = _mapping("cover", "door")
    assert not m["output"].get("shadow_position_timing")
    assert not m["output"].get("shadow_angle_timing")


def test_damper_output_has_no_shadow_timing_flags():
    m = _mapping("cover", "damper")
    assert not m["output"].get("shadow_position_timing")
    assert not m["output"].get("shadow_angle_timing")


def test_channel_type_names_matches_enum():
    from pydsvdcapi.enums import OutputChannelType
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location(
        "entity_mapping",
        pathlib.Path(__file__).parent.parent / "custom_components/dsvdc4ha/entity_mapping.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name, val in mod._CHANNEL_TYPE_NAMES.items():
        assert hasattr(OutputChannelType, name), f"Unknown channel type name: {name}"
        assert OutputChannelType[name].value == val
    for member in OutputChannelType:
        assert member.name in mod._CHANNEL_TYPE_NAMES, f"Missing: {member.name}"


def test_choice_tuples_use_valid_enum_values():
    """All (value, label) choice tuples must reference valid enum members."""
    from pydsvdcapi.enums import BinaryInputGroup, ButtonGroup, SensorUsage
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location(
        "entity_mapping",
        pathlib.Path(__file__).parent.parent / "custom_components/dsvdc4ha/entity_mapping.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    bi_vals = {m.value for m in BinaryInputGroup}
    for v, _ in mod._BI_GROUP_ALL:
        assert v in bi_vals, f"_BI_GROUP_ALL invalid: {v}"
    for v, _ in mod._BI_GROUP_MOISTURE:
        assert v in bi_vals, f"_BI_GROUP_MOISTURE invalid: {v}"

    btn_vals = {m.value for m in ButtonGroup}
    for v, _ in mod._BTN_GROUP_CHOICES:
        assert v in btn_vals, f"_BTN_GROUP_CHOICES invalid: {v}"

    su_vals = {m.value for m in SensorUsage}
    for lst_name in ("_SU_ROOM_OUTDOOR", "_SU_DEVICE_LEVEL", "_SU_GENERAL"):
        for v, _ in getattr(mod, lst_name):
            assert v in su_vals, f"{lst_name} invalid: {v}"

    # Check inline choices in ENTITY_MAPPING sensor entries
    wrong_labels = {"Device Level Individual", "Device Level All"}
    for entry in mod.ENTITY_MAPPING:
        sen = entry.get("sensor", {})
        choices = sen.get("sensor_usage_choices", [])
        assert choices == "any" or isinstance(choices, list), (
            f"sensor_usage_choices must be 'any' or a list, got {type(choices)}"
        )
        if not isinstance(choices, list):
            continue
        for v, lbl in choices:
            if isinstance(lbl, str):
                for bad in wrong_labels:
                    assert bad not in lbl, f"Wrong label in sensor_usage_choices: {lbl!r}"


def test_all_enum_fields_are_valid_enum_members():
    """Every integer field in ENTITY_MAPPING must be a valid member of its enum."""
    from pydsvdcapi.enums import (
        BinaryInputGroup, BinaryInputType, BinaryInputUsage,
        ButtonFunctionJoker, ButtonGroup, ButtonMode, ButtonType,
        ColorClass, ColorGroup,
        OutputChannelType, OutputFunction, OutputMode, OutputUsage,
        SensorGroup, SensorType, SensorUsage,
    )
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location(
        "entity_mapping",
        pathlib.Path(__file__).parent.parent / "custom_components/dsvdc4ha/entity_mapping.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    _bi_type_vals  = {m.value for m in BinaryInputType}
    _bi_grp_vals   = {m.value for m in BinaryInputGroup}
    _bi_usage_vals = {m.value for m in BinaryInputUsage}
    _st_vals       = {m.value for m in SensorType}
    _su_vals       = {m.value for m in SensorUsage}
    _sg_vals       = {m.value for m in SensorGroup}
    _btn_type_vals = {m.value for m in ButtonType}
    _btn_grp_vals  = {m.value for m in ButtonGroup}
    _btn_func_vals = {m.value for m in ButtonFunctionJoker}
    _btn_mode_vals = {m.value for m in ButtonMode}
    _of_vals       = {m.value for m in OutputFunction}
    _ou_vals       = {m.value for m in OutputUsage}
    _om_vals       = {m.value for m in OutputMode}
    _cc_vals       = {m.value for m in ColorClass}
    _cg_vals       = {m.value for m in ColorGroup}
    _oct_vals      = {m.value for m in OutputChannelType}

    for entry in mod.ENTITY_MAPPING:
        key = f"{entry['domain']}/{entry.get('device_class')}"

        pg = entry.get("primary_group")
        if pg is not None:
            assert pg in _cg_vals, f"{key}: primary_group={pg} not in ColorGroup"

        if bi := entry.get("binary_input"):
            assert bi["sensor_function"] in _bi_type_vals,  f"{key}: binary_input.sensor_function invalid"
            assert bi["group"]            in _bi_grp_vals,   f"{key}: binary_input.group invalid"
            assert bi["input_usage"]      in _bi_usage_vals, f"{key}: binary_input.input_usage invalid"

        if s := entry.get("sensor"):
            assert s["sensor_type"]  in _st_vals, f"{key}: sensor.sensor_type invalid"
            assert s["sensor_usage"] in _su_vals, f"{key}: sensor.sensor_usage invalid"
            assert s["group"]        in _sg_vals, f"{key}: sensor.group invalid"

        if o := entry.get("output"):
            assert o["function"]      in _of_vals, f"{key}: output.function invalid"
            assert o["output_usage"]  in _ou_vals, f"{key}: output.output_usage invalid"
            assert o.get("mode", OutputMode.DISABLED) in _om_vals, f"{key}: output.mode invalid"
            dg = o.get("default_group")
            if dg is not None:
                assert dg in _cc_vals, f"{key}: output.default_group={dg} not in ColorClass"
            for i, ch in enumerate(o.get("channels", [])):
                ct = ch.get("channel_type")
                if ct is not None:
                    assert ct in _oct_vals, f"{key}: channels[{i}].channel_type={ct} invalid"

        if b := entry.get("button"):
            assert b["button_type"] in _btn_type_vals, f"{key}: button.button_type invalid"
            assert b["group"]       in _btn_grp_vals,  f"{key}: button.group invalid"
            assert b["function"]    in _btn_func_vals, f"{key}: button.function invalid (expect ButtonFunctionJoker since group=JOKER)"
            assert b.get("mode", ButtonMode.STANDARD) in _btn_mode_vals, f"{key}: button.mode invalid"


