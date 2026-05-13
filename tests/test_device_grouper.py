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
        _entity("light.lamp", "light", _LIGHT_MAPPING),
        _entity("cover.blind", "cover", _COVER_MAPPING),
    ]
    plans, _ = compute_vdsd_plan(entities, "My Device")
    names = {p.name for p in plans}
    assert "My Device — Light" in names
    assert "My Device — Shadow" in names


def test_plan_naming_duplicate_groups_get_suffix():
    entities = [
        _entity("light.a", "light", _LIGHT_MAPPING),
        _entity("light.b", "light", _LIGHT_MAPPING),
    ]
    plans, _ = compute_vdsd_plan(entities, "My Device")
    names = [p.name for p in plans]
    assert "My Device — Light 1" in names
    assert "My Device — Light 2" in names


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
    result = resolve_vdsd_plan(plan, "Acme", "LampModel", {})
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
    result = resolve_vdsd_plan(plan, "Vendor", "BlindModel", {})
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
    result = resolve_vdsd_plan(plan, "Vendor", "Model", entity_states)
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
    result = resolve_vdsd_plan(plan, "V", "M", {})
    assert len(result["binary_inputs"]) == 1
    assert result["binary_inputs"][0]["callback_entity"] == "binary_sensor.window"


def test_resolve_button_included():
    plan = VdsdPlan(
        primary_group=8, name="Device — Joker",
        button_entity=_entity("event.btn", "event", _BUTTON_MAPPING),
    )
    result = resolve_vdsd_plan(plan, "V", "M", {})
    assert len(result["buttons"]) == 1
    assert result["buttons"][0]["callback_entity"] == "event.btn"
