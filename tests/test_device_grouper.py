"""Unit tests for device_grouper — pure Python, no HA dependency."""
from __future__ import annotations
import pytest
from custom_components.dsvdc4ha.device_grouper import (
    EntityInfo,
    VdsdPlan,
    compute_vdsd_plan,
    resolve_vdsd_plan,
)


def _entity(
    entity_id: str,
    domain: str,
    mapping: dict,
    device_class: str | None = None,
    friendly_name: str = "",
    entity_category: str | None = None,
    needs_choices: bool = False,
) -> EntityInfo:
    return EntityInfo(
        entity_id=entity_id,
        friendly_name=friendly_name or entity_id,
        domain=domain,
        device_class=device_class,
        mapping=mapping,
        needs_choices=needs_choices,
        entity_category=entity_category,
    )


_LIGHT_MAPPING = {
    "primary_group": 1,
    "output": {"function": 3, "output_usage": 1, "groups": [1], "default_group": 1,
               "variable_ramp": True, "mode": 2, "channels": [{"channel_type": 1}]},
}
_BINARY_MAPPING = {
    "primary_group": 8,
    "binary_input": {"sensor_function": 0, "group": 8, "input_usage": 0,
                     "input_type": 1, "update_interval": 1.0},
}
_BUTTON_MAPPING = {
    "primary_group": 8,
    "button": {"button_type": 1, "group": 8, "function": 15, "mode": 0,
               "calls_present": False, "supports_local_key_mode": False},
}
_SENSOR_MAPPING = {
    "primary_group": 8,
    "sensor": {"sensor_type": 9, "group": 0, "sensor_usage": 1, "min": 0.0,
               "max": 40.0, "resolution": 0.1, "update_interval": 0,
               "alive_sign_interval": 0, "min_push_interval": 2.0,
               "changes_only_interval": 0},
}
_COVER_MAPPING = {
    "primary_group": 2,
    "output": {"function": 2, "output_usage": 1, "groups": [2], "default_group": 2,
               "variable_ramp": False, "mode": 2, "channels": [{"channel_type": 7}]},
}


def test_single_output_entity():
    entities = [_entity("light.lamp", "light", _LIGHT_MAPPING)]
    plans, unsupported = compute_vdsd_plan(entities, "Lamp")
    assert len(plans) == 1
    assert plans[0].output_entity.entity_id == "light.lamp"
    assert plans[0].primary_group == 1
    assert unsupported == []


def test_two_outputs_same_group_get_separate_plans():
    entities = [
        _entity("light.lamp1", "light", _LIGHT_MAPPING),
        _entity("light.lamp2", "light", _LIGHT_MAPPING),
    ]
    plans, _ = compute_vdsd_plan(entities, "Device")
    assert len(plans) == 2
    assert all(p.output_entity is not None for p in plans)


def test_binary_input_same_group_attaches_to_output_plan():
    entities = [
        _entity("binary_sensor.motion", "binary_sensor", _BINARY_MAPPING),
        _entity("switch.relay", "switch", {
            "primary_group": 8,
            "output": {"function": 0, "output_usage": 1, "groups": [8],
                       "default_group": 8, "variable_ramp": False, "mode": 1,
                       "channels": [{"channel_type": 19}]},
        }),
    ]
    plans, _ = compute_vdsd_plan(entities, "Device")
    assert len(plans) == 1
    assert plans[0].output_entity.entity_id == "switch.relay"
    assert plans[0].binary_input_entity.entity_id == "binary_sensor.motion"


def test_binary_input_different_group_creates_new_plan():
    entities = [
        _entity("light.lamp", "light", _LIGHT_MAPPING),
        _entity("binary_sensor.motion", "binary_sensor", _BINARY_MAPPING),
    ]
    plans, _ = compute_vdsd_plan(entities, "Device")
    assert len(plans) == 2
    assert plans[0].output_entity.entity_id == "light.lamp"
    assert plans[1].binary_input_entity.entity_id == "binary_sensor.motion"
    assert plans[1].output_entity is None


def test_button_and_binary_input_attach_to_same_plan():
    base = {"primary_group": 8, "output": {"function": 0, "output_usage": 1,
            "groups": [8], "default_group": 8, "variable_ramp": False, "mode": 1,
            "channels": [{"channel_type": 19}]}}
    entities = [
        _entity("switch.relay", "switch", base),
        _entity("binary_sensor.window", "binary_sensor", _BINARY_MAPPING),
        _entity("event.button", "event", _BUTTON_MAPPING),
    ]
    plans, _ = compute_vdsd_plan(entities, "Device")
    assert len(plans) == 1
    assert plans[0].binary_input_entity is not None
    assert plans[0].button_entity is not None


def test_sensors_go_to_first_plan():
    entities = [
        _entity("light.lamp", "light", _LIGHT_MAPPING),
        _entity("sensor.temp", "sensor", _SENSOR_MAPPING),
    ]
    plans, _ = compute_vdsd_plan(entities, "Device")
    assert len(plans) == 1
    assert len(plans[0].sensor_entities) == 1
    assert plans[0].sensor_entities[0].entity_id == "sensor.temp"


def test_sensor_only_device_creates_joker_plan():
    entities = [_entity("sensor.temp", "sensor", _SENSOR_MAPPING)]
    plans, _ = compute_vdsd_plan(entities, "Device")
    assert len(plans) == 1
    assert plans[0].primary_group == 8
    assert plans[0].output_entity is None
    assert len(plans[0].sensor_entities) == 1


def test_unsupported_entity_goes_to_unsupported_list():
    entities = [
        _entity("light.lamp", "light", _LIGHT_MAPPING),
        _entity("weather.home", "weather", {}),
    ]
    # weather entity has empty mapping → no component key → unsupported
    plans, unsupported = compute_vdsd_plan(entities, "Device")
    assert len(plans) == 1
    assert len(unsupported) == 1
    assert unsupported[0].entity_id == "weather.home"


def test_priority_none_category_beats_config():
    config_light = _entity("light.display", "light", _LIGHT_MAPPING,
                            entity_category="config")
    main_light = _entity("light.main", "light", _LIGHT_MAPPING,
                         entity_category=None)
    plans, _ = compute_vdsd_plan([config_light, main_light], "Device")
    assert plans[0].output_entity.entity_id == "light.main"


def test_priority_name_match_tiebreaker():
    a = _entity("light.device_display", "light", _LIGHT_MAPPING,
                friendly_name="Device Display", entity_category=None)
    b = _entity("light.device", "light", _COVER_MAPPING,
                friendly_name="Device", entity_category=None)
    plans, _ = compute_vdsd_plan([a, b], "Device")
    assert plans[0].output_entity.entity_id == "light.device"


def test_priority_alphabetical_final_tiebreaker():
    a = _entity("light.zzz", "light", _LIGHT_MAPPING, entity_category=None,
                friendly_name="Other")
    b = _entity("light.aaa", "light", _LIGHT_MAPPING, entity_category=None,
                friendly_name="Other")
    plans, _ = compute_vdsd_plan([a, b], "Other")
    assert plans[0].output_entity.entity_id == "light.aaa"


def test_plan_naming_unique_groups():
    entities = [
        _entity("light.lamp", "light", _LIGHT_MAPPING, friendly_name="Living Room Lamp"),
        _entity("cover.blind", "cover", _COVER_MAPPING, friendly_name="Bedroom Blind"),
    ]
    plans, _ = compute_vdsd_plan(entities, "My Device")
    names = {p.name for p in plans}
    assert "Living Room Lamp" in names
    assert "Bedroom Blind" in names


def test_plan_naming_duplicate_entity_names_get_suffix():
    entities = [
        _entity("light.a", "light", _LIGHT_MAPPING, friendly_name="Lamp"),
        _entity("light.b", "light", _LIGHT_MAPPING, friendly_name="Lamp"),
    ]
    plans, _ = compute_vdsd_plan(entities, "My Device")
    names = [p.name for p in plans]
    assert "Lamp 1" in names
    assert "Lamp 2" in names


def test_dual_component_entity_contributes_both_output_and_binary_input():
    """Lock entity with both output and binary_input keys should set both fields."""
    lock_mapping = {
        "primary_group": 8,
        "output": {"function": 0, "output_usage": 1, "groups": [8], "default_group": 8,
                   "variable_ramp": False, "mode": 1, "channels": [{"channel_type": 19}]},
        "binary_input": {"sensor_function": 0, "group": 8, "input_usage": 0,
                         "input_type": 1, "update_interval": 1.0},
    }
    entities = [_entity("lock.front", "lock", lock_mapping)]
    plans, unsupported = compute_vdsd_plan(entities, "Lock")
    assert len(plans) == 1
    assert plans[0].output_entity.entity_id == "lock.front"
    assert plans[0].binary_input_entity.entity_id == "lock.front"
    assert unsupported == []


def test_resolve_basic_output():
    plan = VdsdPlan(
        primary_group=1, name="Lamp — Light",
        output_entity=_entity("light.lamp", "light", _LIGHT_MAPPING),
    )
    result = resolve_vdsd_plan(plan, "Lamp", "Acme", "LampModel", {})
    assert result["primaryGroup"] == 1
    assert result["name"] == "Lamp — Light"
    assert result["vendorName"] == "Acme"
    assert result["displayId"] == "LampModel"
    assert result["output"] is not None
    assert len(result["output"]["channels"]) == 1
    assert result["output"]["channels"][0]["read_entity"] == "light.lamp"
    assert result["output"]["channels"][0]["write_action"] is None


def test_resolve_output_usage_choices_applied():
    blind_mapping = {
        "primary_group": 2,
        "output": {
            "function": 2, "output_usage": 1, "groups": [2], "default_group": 2,
            "variable_ramp": False, "mode": 2,
            "output_usage_choices": [(1, "Indoor (1)"), (2, "Outdoor (2)")],
            "channels_by_usage": {
                1: [{"channel_type": 8}],
                2: [{"channel_type": 7}],
            },
        },
    }
    plan = VdsdPlan(
        primary_group=2, name="Blind — Shadow",
        output_entity=_entity("cover.blind", "cover", blind_mapping),
        user_choices={"cover.blind": {"output_usage": "2"}},
    )
    result = resolve_vdsd_plan(plan, "Blind", "Vendor", "BlindModel", {})
    assert result["output"]["channels"][0]["channelType"] == 7  # outdoor channel


def test_resolve_min_max_user_reads_entity_states():
    number_mapping = {
        "primary_group": 8,
        "sensor": {
            "sensor_type": 1, "group": 0, "sensor_usage": 1,
            "min": 0.0, "max": 100.0, "resolution": 1.0,
            "update_interval": 0, "alive_sign_interval": 0,
            "min_push_interval": 2.0, "changes_only_interval": 0,
            "min_max_user": True,
        },
    }
    plan = VdsdPlan(
        primary_group=8, name="Device — Joker",
        sensor_entities=[_entity("number.val", "number", number_mapping)],
    )
    entity_states = {"number.val": {"min": 10.0, "max": 50.0, "step": 0.5}}
    result = resolve_vdsd_plan(plan, "Device", "Vendor", "Model", entity_states)
    sensor = result["sensors"][0]
    assert sensor["min"] == 10.0
    assert sensor["max"] == 50.0
    assert sensor["resolution"] == 0.5


def test_resolve_binary_input_included():
    plan = VdsdPlan(
        primary_group=8, name="Device — Joker",
        binary_input_entity=_entity("binary_sensor.window", "binary_sensor",
                                    _BINARY_MAPPING),
    )
    result = resolve_vdsd_plan(plan, "Device", "V", "M", {})
    assert len(result["binary_inputs"]) == 1
    assert result["binary_inputs"][0]["callback_entity"] == "binary_sensor.window"


def test_resolve_button_included():
    plan = VdsdPlan(
        primary_group=8, name="Device — Joker",
        button_entity=_entity("event.btn", "event", _BUTTON_MAPPING),
    )
    result = resolve_vdsd_plan(plan, "Device", "V", "M", {})
    assert len(result["buttons"]) == 1
    assert result["buttons"][0]["callback_entity"] == "event.btn"


def test_resolve_vdsd_plan_copies_apply_expr_and_push_expr():
    """resolve_vdsd_plan copies apply_expr/push_expr from channel defs into channel data."""
    mapping = {
        "primary_group": 1,
        "output": {
            "function": 1, "output_usage": 1, "groups": [1], "default_group": 1,
            "variable_ramp": True, "mode": 2,
            "channels": [{
                "channel_type": 1,
                "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'brightness':round(value*2.55)}}",
                "push_expr": "round(attrs.get('brightness',0)/2.55,1)",
            }],
        },
    }
    e = _entity("light.lamp", "light", mapping)
    plan = VdsdPlan(primary_group=1, name="Test — Light", output_entity=e)

    vdsd = resolve_vdsd_plan(plan, "Test", "Vendor", "Model", {})

    channels = vdsd["output"]["channels"]
    assert len(channels) == 1
    assert channels[0]["apply_expr"] == "{'domain':'light','service':'turn_on','service_data':{'brightness':round(value*2.55)}}"
    assert channels[0]["push_expr"] == "round(attrs.get('brightness',0)/2.55,1)"


def test_resolve_vdsd_plan_optional_tilt_has_binding():
    """Optional tilt channel added via has_tilt includes apply_expr/push_expr."""
    mapping = {
        "primary_group": 3,
        "output": {
            "function": 2, "output_usage": 1, "groups": [3], "default_group": 3,
            "variable_ramp": True, "mode": 2, "optional_tilt": True,
            "channels": [{
                "channel_type": 8,
                "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(value)}}",
                "push_expr": "attrs.get('current_position',0)",
            }],
        },
    }
    e = _entity("cover.window", "cover", mapping)
    plan = VdsdPlan(
        primary_group=3, name="Test — Climate",
        output_entity=e,
        user_choices={"cover.window": {"has_tilt": True}},
    )

    vdsd = resolve_vdsd_plan(plan, "Test", "Vendor", "Model", {})

    channels = vdsd["output"]["channels"]
    assert len(channels) == 2
    tilt_ch = channels[1]
    assert tilt_ch["channelType"] == 10
    assert "apply_expr" in tilt_ch
    assert tilt_ch["apply_expr"] == "{'domain':'cover','service':'set_cover_tilt_position','service_data':{'tilt_position':round(value)}}"
    assert "push_expr" in tilt_ch
    assert tilt_ch["push_expr"] == "attrs.get('current_tilt_position',0)"


def test_resolve_vdsd_plan_channel_without_binding_stays_clean():
    """Channels without apply_expr/push_expr don't get those keys added."""
    mapping = {
        "primary_group": 1,
        "output": {
            "function": 1, "output_usage": 1, "groups": [1], "default_group": 1,
            "variable_ramp": True, "mode": 2,
            "channels": [{"channel_type": 1}],  # no binding
        },
    }
    e = _entity("light.lamp", "light", mapping)
    plan = VdsdPlan(primary_group=1, name="Test", output_entity=e)

    vdsd = resolve_vdsd_plan(plan, "Test", "Vendor", "Model", {})

    channels = vdsd["output"]["channels"]
    assert "apply_expr" not in channels[0]
    assert "push_expr" not in channels[0]


def test_resolve_bi_group_user_choice_applied():
    """bi_group user choice must override the mapping's group in binary_inputs."""
    mapping = {
        "primary_group": 8,
        "binary_input": {
            "sensor_function": 5,
            "group": 1,  # default Light
            "group_choices": [(1, "Light (1)"), (6, "Security (6)"), (8, "Joker (8)")],
            "input_usage": 1, "input_type": 1, "update_interval": 1.0,
        },
    }
    plan = VdsdPlan(
        primary_group=8, name="Motion — Binary",
        binary_input_entity=_entity("binary_sensor.motion", "binary_sensor", mapping),
        user_choices={"binary_sensor.motion": {"bi_group": "6"}},
    )
    result = resolve_vdsd_plan(plan, "Device", "Vendor", "Model", {})
    assert result["binary_inputs"][0]["group"] == 6


def test_resolve_bi_group_uses_mapping_default_when_no_choice():
    """Without user choice, resolve_vdsd_plan must use mapping's group value."""
    mapping = {
        "primary_group": 8,
        "binary_input": {
            "sensor_function": 5,
            "group": 1,
            "group_choices": [(1, "Light (1)"), (6, "Security (6)")],
            "input_usage": 1, "input_type": 1, "update_interval": 1.0,
        },
    }
    plan = VdsdPlan(
        primary_group=8, name="Motion — Binary",
        binary_input_entity=_entity("binary_sensor.motion", "binary_sensor", mapping),
    )
    result = resolve_vdsd_plan(plan, "Device", "Vendor", "Model", {})
    assert result["binary_inputs"][0]["group"] == 1


def test_resolve_sensor_usage_user_choice_applied():
    """sensor_usage user choice must override mapping's sensor_usage in sensors."""
    mapping = {
        "primary_group": 8,
        "sensor": {
            "sensor_type": 1, "group": 0,
            "sensor_usage": 0,  # default Undefined
            "sensor_usage_choices": [(0, "Undefined (0)"), (1, "Room (1)"), (2, "Outdoor (2)")],
            "min": -40.0, "max": 85.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0,
        },
    }
    plan = VdsdPlan(
        primary_group=8, name="Temp — Sensor",
        sensor_entities=[_entity("sensor.temperature", "sensor", mapping)],
        user_choices={"sensor.temperature": {"sensor_usage": "2"}},
    )
    result = resolve_vdsd_plan(plan, "Device", "Vendor", "Model", {})
    assert result["sensors"][0]["sensorUsage"] == 2


def test_resolve_sensor_usage_uses_mapping_default_when_no_choice():
    """Without user choice, resolve_vdsd_plan must use mapping's sensor_usage value."""
    mapping = {
        "primary_group": 8,
        "sensor": {
            "sensor_type": 1, "group": 0,
            "sensor_usage": 1,
            "sensor_usage_choices": [(1, "Room (1)"), (2, "Outdoor (2)")],
            "min": -40.0, "max": 85.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0,
        },
    }
    plan = VdsdPlan(
        primary_group=8, name="Temp — Sensor",
        sensor_entities=[_entity("sensor.temperature", "sensor", mapping)],
    )
    result = resolve_vdsd_plan(plan, "Device", "Vendor", "Model", {})
    assert result["sensors"][0]["sensorUsage"] == 1


def test_resolve_vdsd_plan_shadow_timing_forwarded():
    """Timing values from user_choices are written into the resolved output dict."""
    mapping = {
        "primary_group": 2,
        "output": {
            "function": 2, "output_usage": 0, "groups": [2], "default_group": 2,
            "variable_ramp": False, "mode": 2,
            "shadow_position_timing": True,
            "shadow_angle_timing": True,
            "channels": [{"channel_type": 8,
                          "apply_expr": "...", "push_expr": "..."}],
        },
    }
    e = _entity("cover.blind", "cover", mapping)
    plan = VdsdPlan(
        primary_group=2, name="Test — Cover",
        output_entity=e,
        user_choices={"cover.blind": {
            "openTime": 30.0,
            "closeTime": 25.0,
            "angleOpenTime": 5.0,
            "angleCloseTime": 4.0,
            "stopDelayTime": 1.5,
        }},
    )

    vdsd = resolve_vdsd_plan(plan, "Test", "Vendor", "Model", {})

    out = vdsd["output"]
    assert out.get("openTime") == 30.0
    assert out.get("closeTime") == 25.0
    assert out.get("angleOpenTime") == 5.0
    assert out.get("angleCloseTime") == 4.0
    assert out.get("stopDelayTime") == 1.5


def test_resolve_vdsd_plan_timing_absent_when_not_in_choices():
    """Timing keys not in user_choices do not appear in resolved output dict."""
    mapping = {
        "primary_group": 2,
        "output": {
            "function": 2, "output_usage": 0, "groups": [2], "default_group": 2,
            "variable_ramp": False, "mode": 2,
            "shadow_position_timing": True,
            "channels": [{"channel_type": 8,
                          "apply_expr": "...", "push_expr": "..."}],
        },
    }
    e = _entity("cover.shade", "cover", mapping)
    plan = VdsdPlan(primary_group=2, name="Test — Cover", output_entity=e)

    vdsd = resolve_vdsd_plan(plan, "Test", "Vendor", "Model", {})

    out = vdsd["output"]
    assert "openTime" not in out
    assert "closeTime" not in out
    assert "stopDelayTime" not in out
