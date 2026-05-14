"""Pure grouping logic for multi-vdSD device generation from a HA device."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .entity_mapping import CHANNEL_TYPE_LABELS


_GROUP_LABELS: dict[int, str] = {
    1: "Light",
    2: "Shadow",
    3: "Climate",
    4: "Audio",
    5: "Video",
    6: "Security",
    7: "Access",
    8: "Joker",
    9: "Cooling",
}


@dataclass
class EntityInfo:
    entity_id: str
    friendly_name: str
    domain: str
    device_class: str | None
    mapping: dict[str, Any] | None
    needs_choices: bool
    entity_category: str | None  # None | "config" | "diagnostic"


@dataclass
class VdsdPlan:
    primary_group: int
    name: str
    output_entity: EntityInfo | None = None
    binary_input_entity: EntityInfo | None = None
    button_entity: EntityInfo | None = None
    sensor_entities: list[EntityInfo] = field(default_factory=list)
    # keyed by entity_id to avoid conflicts when multiple entities have choices
    user_choices: dict[str, dict[str, Any]] = field(default_factory=dict)
    resolved_vdsd: dict[str, Any] | None = None
    model_features: list[str] | None = None


def _primary_entity_label(plan: VdsdPlan) -> str:
    """Return the friendly name of the plan's primary entity, or a group label fallback."""
    for entity in [plan.output_entity, plan.binary_input_entity, plan.button_entity]:
        if entity is not None:
            return entity.friendly_name
    if plan.sensor_entities:
        return plan.sensor_entities[0].friendly_name
    return _GROUP_LABELS.get(plan.primary_group, f"Group {plan.primary_group}")


def _assign_names(plans: list[VdsdPlan], device_name: str) -> None:
    label_counts: dict[str, int] = {}
    for plan in plans:
        label = _primary_entity_label(plan)
        label_counts[label] = label_counts.get(label, 0) + 1

    label_seen: dict[str, int] = {}
    for plan in plans:
        label = _primary_entity_label(plan)
        if label_counts[label] == 1:
            plan.name = f"{device_name} — {label}"
        else:
            label_seen[label] = label_seen.get(label, 0) + 1
            plan.name = f"{device_name} — {label} {label_seen[label]}"


def compute_vdsd_plan(
    entities: list[EntityInfo],
    device_name: str,
) -> tuple[list[VdsdPlan], list[EntityInfo]]:
    """Group entities into VdsdPlans. Returns (plans, unsupported)."""
    plans: list[VdsdPlan] = []
    unsupported: list[EntityInfo] = []

    outputs: list[EntityInfo] = []
    binary_inputs: list[EntityInfo] = []
    buttons: list[EntityInfo] = []
    sensors: list[EntityInfo] = []

    for entity in entities:
        m = entity.mapping
        if not m:
            unsupported.append(entity)
        else:
            classified = False
            if "output" in m:
                outputs.append(entity)
                classified = True
            if "binary_input" in m:
                binary_inputs.append(entity)
                classified = True
            if "button" in m:
                buttons.append(entity)
                classified = True
            if "sensor" in m:
                sensors.append(entity)
                classified = True
            if not classified:
                unsupported.append(entity)

    def _priority(e: EntityInfo) -> tuple[int, int, str]:
        cat = e.entity_category
        tier = 0 if cat is None else (1 if cat == "config" else 2)
        name_score = (
            0 if e.friendly_name == device_name
            or e.friendly_name.startswith(device_name)
            else 1
        )
        return (tier, name_score, e.entity_id)

    for entity in sorted(outputs, key=_priority):
        plans.append(VdsdPlan(
            primary_group=entity.mapping["primary_group"],
            name="",
            output_entity=entity,
        ))

    for entity in sorted(binary_inputs, key=lambda e: e.entity_id):
        pg = entity.mapping["primary_group"]
        target = next(
            (p for p in plans if p.primary_group == pg and p.binary_input_entity is None),
            None,
        )
        if target:
            target.binary_input_entity = entity
        else:
            plans.append(VdsdPlan(primary_group=pg, name="", binary_input_entity=entity))

    for entity in sorted(buttons, key=lambda e: e.entity_id):
        pg = entity.mapping["primary_group"]
        target = next(
            (p for p in plans if p.primary_group == pg and p.button_entity is None),
            None,
        )
        if target:
            target.button_entity = entity
        else:
            plans.append(VdsdPlan(primary_group=pg, name="", button_entity=entity))

    if sensors:
        if not plans:
            plans.append(VdsdPlan(primary_group=8, name=""))
        plans[0].sensor_entities.extend(sensors)

    _assign_names(plans, device_name)
    return plans, unsupported


_OUTPUT_ON_THRESHOLD = 50


def resolve_vdsd_plan(
    plan: VdsdPlan,
    device_name: str,  # noqa: ARG001 — part of public API; name is embedded in plan.name
    vendor_name: str,
    display_id: str,
    entity_states: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build the vdSD config dict from a VdsdPlan with resolved user_choices.

    entity_states maps entity_id -> state attributes dict (for min_max_user lookups).
    device_name is accepted for API symmetry with the call site in config_flow but is
    not used here — the name was already embedded in plan.name by compute_vdsd_plan.
    """
    vdsd: dict[str, Any] = {
        "displayId": display_id,
        "primaryGroup": plan.primary_group,
        "model": display_id,
        "vendorName": vendor_name,
        "modelVersion": "1.0",
        "modelUID": (vendor_name + display_id).replace(" ", ""),
        "name": plan.name,
        "active": True,
        "identify_action": None,
        "firmwareUpdate_action": None,
        "optional": {},
        "buttons": [],
        "binary_inputs": [],
        "sensors": [],
        "output": None,
    }

    if plan.binary_input_entity:
        e = plan.binary_input_entity
        choices = plan.user_choices.get(e.entity_id, {})
        bi = e.mapping["binary_input"]
        sf = int(choices.get("sensor_function", bi["sensor_function"]))
        vdsd["binary_inputs"] = [{
            "dsIndex": 0,
            "name": e.friendly_name,
            "group": int(choices.get("bi_group", bi["group"])),
            "sensorFunction": sf,
            "hardwiredFunction": sf,
            "updateInterval": bi["update_interval"],
            "inputType": bi["input_type"],
            "inputUsage": bi["input_usage"],
            "valueType": "boolean",
            "callback_entity": e.entity_id,
        }]

    if plan.button_entity:
        e = plan.button_entity
        choices = plan.user_choices.get(e.entity_id, {})
        b = e.mapping["button"]
        group = int(choices.get("group", b["group"]))
        if "group_choices" in b and "group" in choices:
            function = 15 if group == 8 else 5
        else:
            function = b["function"]
        vdsd["buttons"] = [{
            "dsIndex": 0,
            "name": e.friendly_name,
            "buttonType": b["button_type"],
            "buttonElementID": 0,
            "group": group,
            "function": function,
            "mode": b["mode"],
            "channel": 0,
            "supportsLocalKeyMode": b.get("supports_local_key_mode", False),
            "setsLocalPriority": False,
            "callsPresent": b.get("calls_present", False),
            "buttonID": 0,
            "callbackType": "detect_clicks",
            "callback_entity": e.entity_id,
        }]

    for idx, e in enumerate(plan.sensor_entities):
        choices = plan.user_choices.get(e.entity_id, {})
        s = e.mapping["sensor"]
        st = int(choices.get("sensor_type", s["sensor_type"]))
        attrs = entity_states.get(e.entity_id, {})
        if s.get("min_max_user"):
            sen_min = float(choices.get("min", attrs.get("min", s.get("min", 0.0))))
            sen_max = float(choices.get("max", attrs.get("max", s.get("max", 100.0))))
            sen_res = float(choices.get("resolution", attrs.get("step", s.get("resolution", 0.4))))
        else:
            sen_min = float(s.get("min", 0.0))
            sen_max = float(s.get("max", 100.0))
            sen_res = float(s.get("resolution", 0.4))
        vdsd["sensors"].append({
            "dsIndex": idx,
            "name": e.friendly_name,
            "group": s["group"],
            "sensorType": st,
            "sensorUsage": int(choices.get("sensor_usage", s["sensor_usage"])),
            "min": sen_min,
            "max": sen_max,
            "resolution": sen_res,
            "updateInterval": s["update_interval"],
            "aliveSignInterval": s["alive_sign_interval"],
            "minPushInterval": s["min_push_interval"],
            "changesOnlyInterval": s["changes_only_interval"],
            "callback_entity": e.entity_id,
        })

    if plan.output_entity:
        e = plan.output_entity
        choices = plan.user_choices.get(e.entity_id, {})
        o = e.mapping["output"]
        fn = int(choices.get("function", o["function"]))
        usage = int(choices.get("output_usage", o["output_usage"]))
        if "channels_by_usage" in o:
            channels_def = o["channels_by_usage"].get(usage, o.get("channels", []))
        else:
            channels_def = list(o.get("channels", []))
        if o.get("optional_tilt") and choices.get("has_tilt"):
            channels_def = channels_def + [{
                "channel_type": 10,
                "apply_expr": "{'domain':'cover','service':'set_cover_tilt_position','service_data':{'tilt_position':round(value)}}",
                "push_expr": "attrs.get('current_tilt_position',0)",
            }]
        mode = (1 if fn == 0 else 2) if "function_choices" in o else o["mode"]
        channels = [
            {
                "dsIndex": i,
                "channelType": ch["channel_type"],
                "name": CHANNEL_TYPE_LABELS.get(ch["channel_type"], f"Channel {i}"),
                "min": 0.0,
                "max": 100.0,
                "resolution": 0.4,
                "read_entity": e.entity_id,
                "write_action": None,
                **({"apply_expr": ch["apply_expr"]} if ch.get("apply_expr") else {}),
                **({"push_expr": ch["push_expr"]} if ch.get("push_expr") else {}),
            }
            for i, ch in enumerate(channels_def)
        ]
        vdsd["output"] = {
            "name": "Output",
            "groups": o["groups"],
            "defaultGroup": o["default_group"],
            "activeGroup": o["default_group"],
            "function": fn,
            "outputUsage": usage,
            "variableRamp": o["variable_ramp"],
            "mode": mode,
            "onThreshold": _OUTPUT_ON_THRESHOLD,
            "channels": channels,
        }

    return vdsd
