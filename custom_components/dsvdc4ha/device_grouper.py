"""Pure grouping logic for multi-vdSD device generation from a HA device."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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


def _assign_names(plans: list[VdsdPlan], device_name: str) -> None:
    label_counts: dict[str, int] = {}
    for plan in plans:
        label = _GROUP_LABELS.get(plan.primary_group, f"Group {plan.primary_group}")
        label_counts[label] = label_counts.get(label, 0) + 1

    label_seen: dict[str, int] = {}
    for plan in plans:
        label = _GROUP_LABELS.get(plan.primary_group, f"Group {plan.primary_group}")
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
