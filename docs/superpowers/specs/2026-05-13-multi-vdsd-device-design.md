# Multi-vdSD Device Generation from HA Device

**Date:** 2026-05-13
**Status:** Approved for implementation

---

## 1. Goal

Add a third device creation path to `VdsdSubentryFlowHandler`: **"Create multi-vdSD device from HA device"**. The user selects a HA device; the integration derives all its entities, groups them into vdSDs following the same rules as the manual wizard, and creates the full set of vdSDs in one flow. All vdSDs for the same HA device share the same dsUID device prefix (`subdevice_index` 0, 1, 2…), satisfying the dS "same physical device" requirement.

---

## 2. Architecture

The grouping logic is extracted into a new pure module `device_grouper.py` with no HA imports — it takes dataclass inputs and returns dataclass outputs. The config flow calls it and handles only UI state. This keeps `config_flow.py` from growing further and makes the algorithm independently testable with plain pytest.

```
VdsdSubentryFlowHandler  ──calls──►  device_grouper.compute_vdsd_plan()
       │                                      │
       │  (UI state machine)                  │  (pure Python, no HA)
       │                                      ▼
       │                             list[VdsdPlan]  +  list[EntityInfo] (unsupported)
       │
       ▼
   api.add_device(entry_id, vdsds_data)
       │
       └──► DsUid.from_name_in_space(entry_id, VDC, subdevice_index=0,1,2…)
             → same device prefix for all vdSDs  ✓
```

---

## 3. New Creation Mode Option

`async_step_creation_mode` gains a third selector option:

```
mode = "from_ha_device"  →  "Create multi-vdSD device from HA device"
```

Routes to `async_step_device_picker`.

---

## 4. Flow Sequence

```
creation_mode  ("from_ha_device")
  └─► device_picker
        │  (compute_vdsd_plan, build _pending_choice_entities)
        ├─► device_entity_user_input  ← repeating; one per entity with choice flags
        │         (cycles via _pending_choice_idx)
        └─► device_plan_summary
              │  (resolve_vdsd_plan for each VdsdPlan, auto-bind channels)
              └─► device_model_features  ← repeating; one per VdsdPlan
                        (cycles via _pending_vdsd_idx)
                    └─► device_summary  ← existing step, unchanged
                          └─► CREATE SUBENTRY
```

---

## 5. Grouping Algorithm (`device_grouper.py`)

### 5.1 Data structures

```python
@dataclass
class EntityInfo:
    entity_id: str
    friendly_name: str
    domain: str
    device_class: str | None
    mapping: dict[str, Any]          # from get_entity_mapping()
    needs_choices: bool               # from needs_user_input()
    entity_category: str | None      # None | "config" | "diagnostic"

@dataclass
class VdsdPlan:
    primary_group: int
    name: str                         # "{device_name} — {group_label}[suffix]"
    output_entity: EntityInfo | None = None
    binary_input_entity: EntityInfo | None = None
    button_entity: EntityInfo | None = None
    sensor_entities: list[EntityInfo] = field(default_factory=list)
    user_choices: dict[str, Any] = field(default_factory=dict)
    resolved_vdsd: dict[str, Any] | None = None   # filled by resolve_vdsd_plan()
    model_features: list[str] | None = None        # filled after model_features step
```

### 5.2 Primary group display labels

```python
_GROUP_LABELS: dict[int, str] = {
    1: "Light",    # YELLOW
    2: "Shadow",   # GREY
    3: "Climate",  # BLUE
    4: "Audio",    # CYAN
    5: "Video",    # MAGENTA
    6: "Security", # RED
    7: "Access",   # GREEN
    8: "Joker",    # BLACK
    9: "Cooling",  # WHITE
}
```

### 5.3 `compute_vdsd_plan(entities, device_name)`

```
Input:  list[EntityInfo], device_name: str
Output: tuple[list[VdsdPlan], list[EntityInfo]]  — (plans, unsupported)
```

**Phase 1 — Classify.** For each entity, `get_entity_mapping(domain, device_class)` → mapped or unsupported. Mapped entities are typed by their component key: `"output"`, `"binary_input"`, `"button"`, or `"sensor"`.

**Phase 2 — Outputs (one vdSD each), priority-ordered.**
Sort output entities by priority score (see §5.4), highest first. Each output entity creates one `VdsdPlan`. The first in the sorted list → `vdsd_plans[0]`.

**Phase 3 — Binary inputs.** For each `binary_input` entity (in entity_id order): find the first existing plan with the same `primary_group` that has no `binary_input_entity` yet. If found: attach. If not: create a new `VdsdPlan` (output=None, binary_input only).

**Phase 4 — Buttons.** Same search logic as Phase 3, independent of binary_input assignment. A plan can hold one button *and* one binary input simultaneously.

**Phase 5 — Sensors.** All sensor entities are appended to `vdsd_plans[0].sensor_entities` regardless of their primary_group. If no plans exist (device has only sensors): create a single new `VdsdPlan` with `primary_group=8` (Joker).

**Plan naming.** Collect group labels used. If a label appears once: `"{device_name} — {label}"`. If multiple plans share a label: `"{device_name} — {label} 1"`, `"… 2"`, etc.

### 5.4 Output entity priority

Only entities that generate a dS output are eligible. Priority is a 3-tuple sort key `(tier, name_score, entity_id)` — lowest value wins (standard ascending sort).

| Signal | Rule | Score |
|---|---|---|
| Entity category (Tier) | `entity_category = None` → 0; `"config"` → 1; `"diagnostic"` → 2 | Hard gate: tier 0 always beats tiers 1 and 2 |
| Name proximity | `friendly_name == device_name` or starts with it → 0; else → 1 | Tiebreaker within tier |
| entity_id | Alphabetical | Final deterministic tiebreaker |

Signal 1 is a hard tier, not additive — a `None`-category `light.coffee_machine_display` never beats a `None`-category `switch.coffee_machine` on domain grounds alone. Within the same tier, Signal 3 (name match) distinguishes the "main" entity from auxiliary ones with the same category.

### 5.5 `resolve_vdsd_plan(plan, entity_states)`

```
Input:  VdsdPlan (with user_choices filled), entity_states: dict[entity_id → attributes]
Output: dict  — the vdSD config dict in the same format as _build_entity_vdsd_and_continue()
```

Pure function. Applies `user_choices` to the mapping (same logic as `_build_entity_vdsd_and_continue`). Channel auto-binding:
- `read_entity` = entity_id of the output entity
- `write_action` = `None` (can be configured later via reconfiguration)
- For `min_max_user` entities: `min`/`max`/`resolution` read from `entity_states[entity_id]` attributes (`min`, `max`, `step`) with fallbacks (0, 100, 0.4).

---

## 6. New Config Flow Steps

### 6.1 `async_step_device_picker`

Form with a single `DeviceSelector`. On submit:
1. Fetch all entity registry entries for the device via `er.async_get(hass).entities.get_entries_for_device_id(device_id)`
2. For each entry: `state = hass.states.get(entity_id)`, read `device_class` from attributes, look up mapping
3. Build `list[EntityInfo]`; include `entity_category` from registry entry
4. Call `compute_vdsd_plan(entities, device_name)` → store `_vdsd_plans`, `_unsupported_entities`
5. Build `_pending_choice_entities = [(entity_info, plan_idx), ...]` — all entities with `needs_choices=True`, in plan order
6. Store `_device_name`, `_vendor_name` (manufacturer), `_display_id` (model) from device registry
7. Set `_pending_choice_idx = 0`, `_pending_vdsd_idx = 0`
8. Route: if `_pending_choice_entities` → `device_entity_user_input`; else → `device_plan_summary`

### 6.2 `async_step_device_entity_user_input`

Renders choice fields for `_pending_choice_entities[_pending_choice_idx]`. `description_placeholders` includes `{"current": N, "total": M, "entity_name": friendly_name, "domain": domain}` so the form header reads *"Entity 2 of 4: Bedroom Blind (cover)"*. For `min_max_user` entities, pre-fills defaults from entity state attributes.

On submit: stores choices into `_vdsd_plans[plan_idx].user_choices`, increments `_pending_choice_idx`. Re-enters same step if more pending, else → `device_plan_summary`.

### 6.3 `async_step_device_plan_summary`

Calls `resolve_vdsd_plan()` for each plan (materialises resolved_vdsd). Assembles a description placeholder with:
- Per-plan: name, primary_group label, entity breakdown, output channels
- Unsupported entity list with note about manual creation

`action` selector: `proceed` → `device_model_features`; `cancel` → `creation_mode`.

### 6.4 `async_step_device_model_features`

Derives model features from `_vdsd_plans[_pending_vdsd_idx].resolved_vdsd` using the same pattern as the existing `model_features` step: a temporary `Vdsd` object is constructed via `api._build_vdsd()`, `derive_model_features()` is called on it, and the result is used to build the feature checkbox list. The temporary object is discarded; the real Vdsd is created later by `add_device()`. `description_placeholders` includes `{"current": N, "total": M, "vdsd_name": plan.name}`.

On submit: saves feature list to `_vdsd_plans[_pending_vdsd_idx].model_features`, advances `_pending_vdsd_idx`. Re-enters same step if more plans remain, else → `device_summary`.

### 6.5 `device_summary` (existing, unchanged)

Assembles final entry data from all `_vdsd_plans[*].resolved_vdsd` in index order. Calls `async_create_entry` with `vdsds` list. `api.add_device(entry_id, vdsds_data)` assigns `subdevice_index` 0…N−1, producing the same physical device dsUID pattern.

---

## 7. New State Variables on `VdsdSubentryFlowHandler`

```python
# "from_ha_device" path
_ha_device_id: str
_vdsd_plans: list[VdsdPlan]
_unsupported_entities: list[EntityInfo]
_pending_choice_entities: list[tuple[EntityInfo, int]]  # (entity, plan_idx)
_pending_choice_idx: int
_pending_vdsd_idx: int
```

All initialised to empty/zero in `__init__`.

---

## 8. Strings

Five new step entries in `config_subentries.device.step` in `strings.json` / `en.json`:

| Step | Key fields |
|---|---|
| `device_picker` | `data.device_id` |
| `device_entity_user_input` | same data keys as `entity_user_input`; `description` with `{current}`, `{total}`, `{entity_name}`, `{domain}` |
| `device_plan_summary` | `data.action`; `description` with `{summary}`, `{unsupported}` |
| `device_model_features` | `description` with `{current}`, `{total}`, `{vdsd_name}` |
| (device_summary already exists) | — |

---

## 9. Testing

### `tests/test_device_grouper.py` (new — pure pytest, no HA)

| Test | What it verifies |
|---|---|
| single output entity | one VdsdPlan, output_entity set |
| two outputs same group | two VdsdPlans, each with one output |
| binary input same group as output | attaches to existing plan |
| binary input different group | creates new plan |
| button and binary input on same plan | both attach to same plan |
| sensor with existing plan | goes to plans[0] |
| sensor only device | one joker plan with sensors |
| priority: None-category beats CONFIG | None-category entity is plans[0] |
| priority: name-match tiebreaker | name-matching entity is plans[0] |
| priority: alphabetical final tiebreaker | deterministic ordering |
| unsupported entity | lands in unsupported list |
| resolve_vdsd_plan with output_usage_choices | channels match user choice |
| resolve_vdsd_plan with min_max_user | reads from entity_states attributes |
| plan naming: unique groups | no suffix |
| plan naming: duplicate groups | "Joker 1", "Joker 2" |

### Additions to `tests/test_config_flow.py`

| Test | What it verifies |
|---|---|
| device_picker routes to choice step | when choices needed |
| device_picker routes to summary | when no choices needed |
| device_entity_user_input cycles | advances idx, routes to summary at end |
| device_plan_summary proceed | routes to model_features |
| device_plan_summary cancel | routes to creation_mode |
| device_model_features cycles | advances idx, routes to device_summary at end |
| full end-to-end | light + binary_sensor → two vdSDs, correct entry data |

---

## 10. Files Changed

| File | Type | Description |
|---|---|---|
| `custom_components/dsvdc4ha/device_grouper.py` | **New** | EntityInfo, VdsdPlan, compute_vdsd_plan, resolve_vdsd_plan |
| `custom_components/dsvdc4ha/config_flow.py` | Modified | 6 state vars + 4 new async_step_device_* methods |
| `custom_components/dsvdc4ha/strings.json` | Modified | 4 new step strings under config_subentries.device.step |
| `custom_components/dsvdc4ha/translations/en.json` | Modified | Mirror of strings.json additions |
| `tests/test_device_grouper.py` | **New** | 15 unit tests for pure grouping logic |
| `tests/test_config_flow.py` | Modified | 7 integration tests for new flow steps |
