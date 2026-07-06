# Multi-vdSD Device Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third device creation path "Create multi-vdSD device from HA device" to `VdsdSubentryFlowHandler` that automatically groups a HA device's entities into correctly-structured vdSDs using the existing entity mapping.

**Architecture:** A new pure module `device_grouper.py` holds the grouping algorithm (no HA imports, fully unit-testable). The config flow calls it from a new `async_step_device_picker` step, then cycles through per-entity choice screens and per-vdSD model_features screens before handing off to the existing `device_summary` step. The channel type label dict is moved to `entity_mapping.py` first so both `config_flow.py` and `device_grouper.py` can import it without a circular dependency.

**Tech Stack:** Python dataclasses, `homeassistant.helpers.entity_registry`, `homeassistant.helpers.device_registry`, `voluptuous`, HA `selector`, `pytest-asyncio`.

---

## File Structure

| File | Change |
|---|---|
| `custom_components/dsvdc4ha/entity_mapping.py` | Add `CHANNEL_TYPE_LABELS` export (moved from config_flow.py) |
| `custom_components/dsvdc4ha/device_grouper.py` | **New** — `EntityInfo`, `VdsdPlan`, `compute_vdsd_plan`, `resolve_vdsd_plan` |
| `custom_components/dsvdc4ha/config_flow.py` | Import `CHANNEL_TYPE_LABELS` from entity_mapping; add 6 state vars + 4 new `async_step_device_*` methods; extend `creation_mode` |
| `custom_components/dsvdc4ha/strings.json` | 4 new step entries |
| `custom_components/dsvdc4ha/translations/en.json` | Mirror strings.json additions |
| `tests/test_device_grouper.py` | **New** — 15 pure unit tests |
| `tests/test_config_flow.py` | 7 new integration tests |

---

## Task 1: Move `CHANNEL_TYPE_LABELS` to `entity_mapping.py`

`_CHANNEL_TYPE_LABELS` is currently a private dict in `config_flow.py`. Both `config_flow.py` and the new `device_grouper.py` need it; moving it to `entity_mapping.py` (which already holds `_CHANNEL_TYPE_NAMES`, the reverse mapping) avoids duplication and prevents a circular import.

**Files:**
- Modify: `custom_components/dsvdc4ha/entity_mapping.py`
- Modify: `custom_components/dsvdc4ha/config_flow.py`

- [ ] **Step 1: Add `CHANNEL_TYPE_LABELS` to `entity_mapping.py`**

  At the bottom of `entity_mapping.py` (after the `ENTITY_MAPPING` list, before the helper functions), add:

  ```python
  # Human-readable labels for OutputChannelType integer values.
  CHANNEL_TYPE_LABELS: dict[int, str] = {
      0: "Default (none / catch-all)",
      1: "Brightness",
      2: "Hue",
      3: "Saturation",
      4: "Color Temperature (mired, 100–1000)",
      5: "CIE X",
      6: "CIE Y",
      7: "Shade Position — Outside (0–100 %)",
      8: "Shade Position — Indoor (0–100 %)",
      9: "Shade Opening Angle — Outside",
      10: "Shade Opening Angle — Indoor",
      11: "Transparency",
      12: "Air Flow Intensity",
      13: "Air Flow Direction",
      14: "Air Flap Position",
      15: "Air Louver Position",
      16: "Heating Power",
      17: "Cooling Capacity",
      18: "Audio Volume",
      19: "Power State",
      20: "Fan Speed",
      21: "Ventilation AirFlowIntensity",
      22: "Ventilation AirFlowDirection",
      23: "Water Flow Rate",
      24: "Power Level",
  }
  ```

- [ ] **Step 2: Update `config_flow.py` to import from `entity_mapping`**

  In `config_flow.py`, find the import block that starts with:
  ```python
  from .entity_mapping import (
      SUPPORTED_DOMAINS,
      get_entity_mapping,
      needs_user_input,
  )
  ```

  Replace with:
  ```python
  from .entity_mapping import (
      CHANNEL_TYPE_LABELS as _CHANNEL_TYPE_LABELS,
      SUPPORTED_DOMAINS,
      get_entity_mapping,
      needs_user_input,
  )
  ```

  Then delete the `_CHANNEL_TYPE_LABELS: dict[int, str] = { ... }` block from `config_flow.py` (it starts at line ~289, the dict with keys 0–24).

- [ ] **Step 3: Run tests to confirm nothing broke**

  ```bash
  source .venv/bin/activate && pytest tests/ -q
  ```

  Expected: `40 passed`

- [ ] **Step 4: Commit**

  ```bash
  git add custom_components/dsvdc4ha/entity_mapping.py custom_components/dsvdc4ha/config_flow.py
  git commit -m "refactor: move CHANNEL_TYPE_LABELS to entity_mapping.py"
  ```

---

## Task 2: `device_grouper.py` — data structures and `compute_vdsd_plan`

**Files:**
- Create: `custom_components/dsvdc4ha/device_grouper.py`
- Create: `tests/test_device_grouper.py`

- [ ] **Step 1: Write failing tests for `compute_vdsd_plan`**

  Create `tests/test_device_grouper.py`:

  ```python
  """Unit tests for device_grouper — pure Python, no HA dependency."""
  from __future__ import annotations
  import pytest
  from custom_components.dsvdc4ha.device_grouper import (
      EntityInfo,
      VdsdPlan,
      compute_vdsd_plan,
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
  ```

- [ ] **Step 2: Run tests to confirm they fail**

  ```bash
  source .venv/bin/activate && pytest tests/test_device_grouper.py -v
  ```

  Expected: `ModuleNotFoundError: No module named 'custom_components.dsvdc4ha.device_grouper'`

- [ ] **Step 3: Create `device_grouper.py` with data structures and `compute_vdsd_plan`**

  Create `custom_components/dsvdc4ha/device_grouper.py`:

  ```python
  """Pure grouping logic for multi-vdSD device generation from a HA device."""
  from __future__ import annotations

  from dataclasses import dataclass, field
  from typing import Any

  from .entity_mapping import get_entity_mapping, needs_user_input

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
          elif "output" in m:
              outputs.append(entity)
          elif "binary_input" in m:
              binary_inputs.append(entity)
          elif "button" in m:
              buttons.append(entity)
          elif "sensor" in m:
              sensors.append(entity)
          else:
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
  ```

- [ ] **Step 4: Run tests — all grouping tests should pass**

  ```bash
  source .venv/bin/activate && pytest tests/test_device_grouper.py -v
  ```

  Expected: 13 tests pass (the `resolve_vdsd_plan` tests will still fail — they're added in Task 3).

- [ ] **Step 5: Commit**

  ```bash
  git add custom_components/dsvdc4ha/device_grouper.py tests/test_device_grouper.py
  git commit -m "feat: add device_grouper module with compute_vdsd_plan"
  ```

---

## Task 3: `device_grouper.py` — `resolve_vdsd_plan`

**Files:**
- Modify: `custom_components/dsvdc4ha/device_grouper.py`
- Modify: `tests/test_device_grouper.py`

- [ ] **Step 1: Write failing tests for `resolve_vdsd_plan`**

  Append to `tests/test_device_grouper.py`:

  ```python
  from custom_components.dsvdc4ha.device_grouper import resolve_vdsd_plan


  def _make_plan_with_output(entity_id: str, mapping: dict) -> VdsdPlan:
      entity = _entity(entity_id, mapping["domain"] if "domain" in mapping else "light",
                       mapping, entity_category=None)
      plan = VdsdPlan(primary_group=mapping["primary_group"], name="Test Plan",
                      output_entity=entity)
      return plan


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
  ```

- [ ] **Step 2: Run tests to confirm new tests fail**

  ```bash
  source .venv/bin/activate && pytest tests/test_device_grouper.py::test_resolve_basic_output -v
  ```

  Expected: `ImportError: cannot import name 'resolve_vdsd_plan'`

- [ ] **Step 3: Implement `resolve_vdsd_plan` in `device_grouper.py`**

  Add the following imports at the top of `device_grouper.py` (after `from .entity_mapping import ...`):

  ```python
  from .entity_mapping import CHANNEL_TYPE_LABELS
  ```

  Then append to `device_grouper.py`:

  ```python
  def resolve_vdsd_plan(
      plan: VdsdPlan,
      device_name: str,
      vendor_name: str,
      display_id: str,
      entity_states: dict[str, dict[str, Any]],
  ) -> dict[str, Any]:
      """Build the vdSD config dict from a VdsdPlan with resolved user_choices.

      entity_states maps entity_id → state attributes dict (for min_max_user lookups).
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
              "group": bi["group"],
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
              "sensorUsage": s["sensor_usage"],
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
              channels_def = channels_def + [{"channel_type": 10}]
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
              "onThreshold": 50,
              "channels": channels,
          }

      return vdsd
  ```

- [ ] **Step 4: Run all device_grouper tests**

  ```bash
  source .venv/bin/activate && pytest tests/test_device_grouper.py -v
  ```

  Expected: all 18 tests pass.

- [ ] **Step 5: Run full suite**

  ```bash
  source .venv/bin/activate && pytest tests/ -q
  ```

  Expected: 40 passed (existing) + 18 new = 58 passed.

- [ ] **Step 6: Commit**

  ```bash
  git add custom_components/dsvdc4ha/device_grouper.py tests/test_device_grouper.py
  git commit -m "feat: add resolve_vdsd_plan to device_grouper"
  ```

---

## Task 4: Config flow — `creation_mode` + state vars + `async_step_device_picker`

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py`
- Modify: `tests/test_config_flow.py`

- [ ] **Step 1: Write failing tests**

  Append to `tests/test_config_flow.py`:

  ```python
  # ---------------------------------------------------------------------------
  # VdsdSubentryFlowHandler — "from_ha_device" path tests
  # ---------------------------------------------------------------------------

  from unittest.mock import MagicMock, AsyncMock, patch
  from custom_components.dsvdc4ha.device_grouper import EntityInfo, VdsdPlan


  def _make_entity_info(entity_id: str, domain: str = "light") -> EntityInfo:
      return EntityInfo(
          entity_id=entity_id,
          friendly_name=entity_id,
          domain=domain,
          device_class=None,
          mapping={"primary_group": 1, "output": {
              "function": 3, "output_usage": 1, "groups": [1], "default_group": 1,
              "variable_ramp": True, "mode": 2, "channels": [{"channel_type": 1}],
          }},
          needs_choices=False,
          entity_category=None,
      )


  def _make_vdsd_plan(entity_id: str = "light.lamp") -> VdsdPlan:
      return VdsdPlan(
          primary_group=1,
          name="Lamp — Light",
          output_entity=_make_entity_info(entity_id),
      )


  @pytest.mark.asyncio
  async def test_creation_mode_from_ha_device_routes_to_device_picker():
      flow = _make_subentry_flow()
      result = await flow.async_step_creation_mode({"mode": "from_ha_device"})
      assert result["type"] == "form"
      assert result["step_id"] == "device_picker"


  @pytest.mark.asyncio
  async def test_device_picker_no_choices_routes_to_plan_summary():
      flow = _make_subentry_flow()
      plan = _make_vdsd_plan()
      plan.resolved_vdsd = {"primaryGroup": 1, "displayId": "M", "buttons": [],
                            "binary_inputs": [], "sensors": [], "output": None,
                            "name": "Lamp"}

      mock_dev_reg = MagicMock()
      mock_device = MagicMock()
      mock_device.name = "Lamp"
      mock_device.name_by_user = None
      mock_device.manufacturer = "Acme"
      mock_device.model = "LampModel"
      mock_dev_reg.async_get.return_value = mock_device

      mock_ent_reg = MagicMock()
      mock_entry = MagicMock()
      mock_entry.entity_id = "light.lamp"
      mock_entry.entity_category = None
      mock_ent_reg.entities.get_entries_for_device_id.return_value = [mock_entry]

      mock_state = MagicMock()
      mock_state.name = "Lamp"
      mock_state.attributes = {"device_class": None}
      flow.hass.states.get.return_value = mock_state

      with (
          patch("custom_components.dsvdc4ha.config_flow.dr.async_get",
                return_value=mock_dev_reg),
          patch("custom_components.dsvdc4ha.config_flow.er.async_get",
                return_value=mock_ent_reg),
          patch("custom_components.dsvdc4ha.config_flow.compute_vdsd_plan",
                return_value=([plan], [])),
      ):
          result = await flow.async_step_device_picker(
              {"device_id": "device-abc-123"}
          )

      assert result["type"] == "form"
      assert result["step_id"] == "device_plan_summary"


  @pytest.mark.asyncio
  async def test_device_picker_with_choices_routes_to_entity_user_input():
      flow = _make_subentry_flow()
      plan = _make_vdsd_plan()
      entity_with_choices = _make_entity_info("light.choosy")
      entity_with_choices.needs_choices = True

      plan.output_entity = entity_with_choices

      mock_dev_reg = MagicMock()
      mock_device = MagicMock()
      mock_device.name = "Lamp"
      mock_device.name_by_user = None
      mock_device.manufacturer = "Acme"
      mock_device.model = "LampModel"
      mock_dev_reg.async_get.return_value = mock_device

      mock_ent_reg = MagicMock()
      mock_entry = MagicMock()
      mock_entry.entity_id = "light.choosy"
      mock_entry.entity_category = None
      mock_ent_reg.entities.get_entries_for_device_id.return_value = [mock_entry]

      mock_state = MagicMock()
      mock_state.name = "Choosy"
      mock_state.attributes = {"device_class": None}
      flow.hass.states.get.return_value = mock_state

      with (
          patch("custom_components.dsvdc4ha.config_flow.dr.async_get",
                return_value=mock_dev_reg),
          patch("custom_components.dsvdc4ha.config_flow.er.async_get",
                return_value=mock_ent_reg),
          patch("custom_components.dsvdc4ha.config_flow.compute_vdsd_plan",
                return_value=([plan], [])),
      ):
          result = await flow.async_step_device_picker(
              {"device_id": "device-abc-123"}
          )

      assert result["type"] == "form"
      assert result["step_id"] == "device_entity_user_input"
  ```

- [ ] **Step 2: Run tests to confirm they fail**

  ```bash
  source .venv/bin/activate && pytest tests/test_config_flow.py::test_creation_mode_from_ha_device_routes_to_device_picker -v
  ```

  Expected: `FAILED` — `creation_mode` doesn't have `from_ha_device` option yet.

- [ ] **Step 3: Add imports and state vars to `config_flow.py`**

  At the top of `config_flow.py`, add to the existing `from .entity_mapping import (...)` block:

  ```python
  from .device_grouper import (
      EntityInfo as _EntityInfo,
      VdsdPlan,
      compute_vdsd_plan,
      resolve_vdsd_plan,
  )
  ```

  Also add top-level imports (after existing `from homeassistant import ...`):

  ```python
  from homeassistant.helpers import device_registry as dr
  from homeassistant.helpers import entity_registry as er
  ```

  In `VdsdSubentryFlowHandler.__init__`, append after the existing entity-flow state vars:

  ```python
  # "from_ha_device" path state
  self._ha_device_id: str = ""
  self._vdsd_plans: list[VdsdPlan] = []
  self._unsupported_entities: list[_EntityInfo] = []
  self._pending_choice_entities: list[tuple[_EntityInfo, int]] = []
  self._pending_choice_idx: int = 0
  self._pending_vdsd_idx: int = 0
  ```

- [ ] **Step 4: Add `from_ha_device` to `async_step_creation_mode`**

  In `async_step_creation_mode`, replace the selector options block:

  ```python
  schema = vol.Schema({
      vol.Required("mode", default="from_entity"): selector.SelectSelector(
          selector.SelectSelectorConfig(options=[
              selector.SelectOptionDict(value="from_entity", label="Create from entity"),
              selector.SelectOptionDict(value="from_ha_device",
                                        label="Create multi-vdSD device from HA device"),
              selector.SelectOptionDict(value="from_scratch", label="Create from scratch"),
          ])
      ),
  })
  ```

  And in the submit block, add before the `return await self.async_step_device_info()` fallback:

  ```python
  if mode == "from_ha_device":
      return await self.async_step_device_picker()
  ```

- [ ] **Step 5: Implement `async_step_device_picker`**

  Add the following method to `VdsdSubentryFlowHandler` (after `async_step_entity_channel_mapping`):

  ```python
  # ── "From HA device" creation path ────────────────────────────────────────

  async def async_step_device_picker(self, user_input: dict | None = None):
      """Select a HA device; derive and group all its entities into VdsdPlans."""
      if user_input is not None:
          device_id: str = user_input["device_id"]
          dev_reg = dr.async_get(self.hass)
          ent_reg = er.async_get(self.hass)

          device = dev_reg.async_get(device_id)
          self._ha_device_id = device_id
          self._device_name = (
              (device.name_by_user or device.name) if device else device_id
          )
          self._vendor_name = (device.manufacturer or "") if device else ""
          self._display_id = (device.model or "") if device else ""

          entities: list[_EntityInfo] = []
          for entry in ent_reg.entities.get_entries_for_device_id(device_id):
              state = self.hass.states.get(entry.entity_id)
              domain = entry.entity_id.split(".")[0]
              device_class: str | None = (
                  state.attributes.get("device_class") if state else None
              )
              mapping = get_entity_mapping(domain, device_class)
              cat = entry.entity_category
              cat_str = cat.value if cat is not None else None
              entity_info = _EntityInfo(
                  entity_id=entry.entity_id,
                  friendly_name=(state.name if state else entry.entity_id),
                  domain=domain,
                  device_class=device_class,
                  mapping=mapping,
                  needs_choices=needs_user_input(mapping) if mapping else False,
                  entity_category=cat_str,
              )
              entities.append(entity_info)

          self._vdsd_plans, self._unsupported_entities = compute_vdsd_plan(
              entities, self._device_name
          )
          # Build choice queue: (entity_info, plan_idx) for every entity needing input
          self._pending_choice_entities = []
          for plan_idx, plan in enumerate(self._vdsd_plans):
              for candidate in [
                  plan.output_entity,
                  plan.binary_input_entity,
                  plan.button_entity,
                  *plan.sensor_entities,
              ]:
                  if candidate is not None and candidate.needs_choices:
                      self._pending_choice_entities.append((candidate, plan_idx))
          self._pending_choice_idx = 0
          self._pending_vdsd_idx = 0

          if self._pending_choice_entities:
              return await self.async_step_device_entity_user_input()
          return await self.async_step_device_plan_summary()

      schema = vol.Schema({
          vol.Required("device_id"): selector.DeviceSelector(),
      })
      return self.async_show_form(step_id="device_picker", data_schema=schema)
  ```

- [ ] **Step 6: Run the three new tests**

  ```bash
  source .venv/bin/activate && pytest tests/test_config_flow.py -k "device_picker or from_ha_device" -v
  ```

  Expected: 3 passed.

- [ ] **Step 7: Run full suite**

  ```bash
  source .venv/bin/activate && pytest tests/ -q
  ```

  Expected: 58 + 3 = 61 passed.

- [ ] **Step 8: Commit**

  ```bash
  git add custom_components/dsvdc4ha/config_flow.py tests/test_config_flow.py
  git commit -m "feat: add device_picker step and from_ha_device creation mode"
  ```

---

## Task 5: Config flow — `async_step_device_entity_user_input` and `async_step_device_plan_summary`

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py`
- Modify: `tests/test_config_flow.py`

- [ ] **Step 1: Write failing tests**

  Append to `tests/test_config_flow.py`:

  ```python
  @pytest.mark.asyncio
  async def test_device_entity_user_input_cycles_and_routes_to_summary():
      """device_entity_user_input cycles through pending entities then goes to summary."""
      flow = _make_subentry_flow()
      plan = _make_vdsd_plan()
      entity1 = _make_entity_info("cover.blind", "cover")
      entity1.needs_choices = True
      entity1.mapping = {
          "primary_group": 2,
          "output": {
              "function": 2, "output_usage": 1, "groups": [2], "default_group": 2,
              "variable_ramp": False, "mode": 2,
              "output_usage_choices": [(1, "Indoor"), (2, "Outdoor")],
              "channels_by_usage": {1: [{"channel_type": 8}], 2: [{"channel_type": 7}]},
          },
      }
      flow._vdsd_plans = [plan]
      flow._pending_choice_entities = [(entity1, 0)]
      flow._pending_choice_idx = 0

      # Show form
      result = await flow.async_step_device_entity_user_input()
      assert result["type"] == "form"
      assert result["step_id"] == "device_entity_user_input"

      # Submit — last entity, routes to plan_summary
      with patch(
          "custom_components.dsvdc4ha.config_flow.resolve_vdsd_plan",
          return_value={"primaryGroup": 2, "buttons": [], "binary_inputs": [],
                        "sensors": [], "output": None, "displayId": "M", "name": "N"},
      ):
          result2 = await flow.async_step_device_entity_user_input(
              {"output_usage": "2"}
          )
      assert result2["step_id"] == "device_plan_summary"
      assert flow._vdsd_plans[0].user_choices.get("cover.blind", {}).get("output_usage") == "2"


  @pytest.mark.asyncio
  async def test_device_plan_summary_proceed_routes_to_model_features():
      flow = _make_subentry_flow()
      plan = _make_vdsd_plan()
      plan.resolved_vdsd = {
          "primaryGroup": 1, "displayId": "M", "name": "Lamp — Light",
          "buttons": [], "binary_inputs": [], "sensors": [], "output": None,
      }
      flow._vdsd_plans = [plan]
      flow._unsupported_entities = []
      flow._pending_vdsd_idx = 0

      result = await flow.async_step_device_plan_summary({"action": "proceed"})
      assert result["step_id"] == "device_model_features"


  @pytest.mark.asyncio
  async def test_device_plan_summary_cancel_routes_to_creation_mode():
      flow = _make_subentry_flow()
      flow._vdsd_plans = []
      flow._unsupported_entities = []
      result = await flow.async_step_device_plan_summary({"action": "cancel"})
      assert result["step_id"] == "creation_mode"
  ```

- [ ] **Step 2: Run tests to confirm they fail**

  ```bash
  source .venv/bin/activate && pytest tests/test_config_flow.py -k "device_entity_user_input or device_plan_summary" -v
  ```

  Expected: `AttributeError: 'VdsdSubentryFlowHandler' object has no attribute 'async_step_device_entity_user_input'`

- [ ] **Step 3: Implement `async_step_device_entity_user_input`**

  Add after `async_step_device_picker` in `config_flow.py`:

  ```python
  async def async_step_device_entity_user_input(self, user_input: dict | None = None):
      """Collect per-entity choices (one entity at a time) for the HA-device path."""
      entity_info, plan_idx = self._pending_choice_entities[self._pending_choice_idx]
      mapping = entity_info.mapping or {}

      if user_input is not None:
          self._vdsd_plans[plan_idx].user_choices[entity_info.entity_id] = dict(user_input)
          self._pending_choice_idx += 1
          if self._pending_choice_idx < len(self._pending_choice_entities):
              return await self.async_step_device_entity_user_input()
          return await self.async_step_device_plan_summary()

      # Build same schema as async_step_entity_user_input
      schema_dict: dict = {}
      bi = mapping.get("binary_input", {})
      sen = mapping.get("sensor", {})
      btn = mapping.get("button", {})
      out = mapping.get("output", {})

      if bi.get("sensor_function_choices"):
          schema_dict[vol.Required("sensor_function", default=str(bi["sensor_function"]))] = (
              selector.SelectSelector(selector.SelectSelectorConfig(options=[
                  selector.SelectOptionDict(value=str(v), label=lbl)
                  for v, lbl in bi["sensor_function_choices"]
              ]))
          )
      if btn.get("group_choices"):
          schema_dict[vol.Required("group", default=str(btn["group"]))] = (
              selector.SelectSelector(selector.SelectSelectorConfig(options=[
                  selector.SelectOptionDict(value=str(v), label=lbl)
                  for v, lbl in btn["group_choices"]
              ]))
          )
      stc = sen.get("sensor_type_choices")
      if stc == "any":
          schema_dict[vol.Required("sensor_type", default=str(sen["sensor_type"]))] = (
              selector.SelectSelector(selector.SelectSelectorConfig(options=_SENSOR_TYPE_OPTIONS))
          )
      elif stc:
          schema_dict[vol.Required("sensor_type", default=str(sen["sensor_type"]))] = (
              selector.SelectSelector(selector.SelectSelectorConfig(options=[
                  selector.SelectOptionDict(value=str(v), label=lbl)
                  for v, lbl in stc
              ]))
          )
      state = self.hass.states.get(entity_info.entity_id)
      attrs = state.attributes if state else {}
      if sen.get("min_max_user"):
          schema_dict[vol.Required("min", default=attrs.get("min", sen.get("min", 0)))] = (
              selector.NumberSelector(selector.NumberSelectorConfig(mode="box"))
          )
          schema_dict[vol.Required("max", default=attrs.get("max", sen.get("max", 100)))] = (
              selector.NumberSelector(selector.NumberSelectorConfig(mode="box"))
          )
          schema_dict[vol.Required("resolution", default=attrs.get("step", sen.get("resolution", 0.4)))] = (
              selector.NumberSelector(selector.NumberSelectorConfig(min=0, step=0.01, mode="box"))
          )
      if out.get("output_usage_choices"):
          schema_dict[vol.Required("output_usage", default=str(out["output_usage"]))] = (
              selector.SelectSelector(selector.SelectSelectorConfig(options=[
                  selector.SelectOptionDict(value=str(v), label=lbl)
                  for v, lbl in out["output_usage_choices"]
              ]))
          )
      if out.get("function_choices"):
          schema_dict[vol.Required("function", default=str(out["function"]))] = (
              selector.SelectSelector(selector.SelectSelectorConfig(options=[
                  selector.SelectOptionDict(value=str(v), label=lbl)
                  for v, lbl in out["function_choices"]
              ]))
          )
      if out.get("optional_tilt"):
          schema_dict[vol.Optional("has_tilt", default=False)] = selector.BooleanSelector()

      current = self._pending_choice_idx + 1
      total = len(self._pending_choice_entities)
      return self.async_show_form(
          step_id="device_entity_user_input",
          data_schema=vol.Schema(schema_dict),
          description_placeholders={
              "current": str(current),
              "total": str(total),
              "entity_name": entity_info.friendly_name,
              "domain": entity_info.domain,
          },
      )
  ```

- [ ] **Step 4: Implement `async_step_device_plan_summary`**

  Add after `async_step_device_entity_user_input`:

  ```python
  async def async_step_device_plan_summary(self, user_input: dict | None = None):
      """Show auto-generated vdSD plan; user proceeds or cancels."""
      if user_input is not None:
          if user_input.get("action") == "cancel":
              return await self.async_step_creation_mode()
          # Resolve all plans now (user_choices are all set)
          entity_states: dict[str, dict] = {}
          for plan in self._vdsd_plans:
              for e in [plan.output_entity, plan.binary_input_entity,
                        plan.button_entity, *plan.sensor_entities]:
                  if e is not None:
                      state = self.hass.states.get(e.entity_id)
                      entity_states[e.entity_id] = dict(state.attributes) if state else {}
          for plan in self._vdsd_plans:
              plan.resolved_vdsd = resolve_vdsd_plan(
                  plan, self._device_name, self._vendor_name,
                  self._display_id, entity_states,
              )
          self._pending_vdsd_idx = 0
          return await self.async_step_device_model_features()

      # Build summary text for description_placeholders
      lines: list[str] = []
      for i, plan in enumerate(self._vdsd_plans, 1):
          parts: list[str] = []
          if plan.output_entity:
              parts.append(f"output: {plan.output_entity.entity_id}")
          if plan.binary_input_entity:
              parts.append(f"binary input: {plan.binary_input_entity.entity_id}")
          if plan.button_entity:
              parts.append(f"button: {plan.button_entity.entity_id}")
          if plan.sensor_entities:
              parts.append(f"{len(plan.sensor_entities)} sensor(s)")
          lines.append(f"{i}. {plan.name} ({', '.join(parts)})")
      summary = "\n".join(lines) or "(no vdSDs)"

      unsupported_lines: list[str] = [
          f"• {e.entity_id}" for e in self._unsupported_entities
      ]
      unsupported = (
          "\n".join(unsupported_lines)
          if unsupported_lines
          else "(none — all entities mapped)"
      )

      schema = vol.Schema({
          vol.Required("action", default="proceed"): selector.SelectSelector(
              selector.SelectSelectorConfig(options=[
                  selector.SelectOptionDict(value="proceed", label="Proceed"),
                  selector.SelectOptionDict(value="cancel", label="Cancel"),
              ])
          ),
      })
      return self.async_show_form(
          step_id="device_plan_summary",
          data_schema=schema,
          description_placeholders={"summary": summary, "unsupported": unsupported},
      )
  ```

- [ ] **Step 5: Run the three new tests**

  ```bash
  source .venv/bin/activate && pytest tests/test_config_flow.py -k "device_entity_user_input or device_plan_summary" -v
  ```

  Expected: 3 passed.

- [ ] **Step 6: Run full suite**

  ```bash
  source .venv/bin/activate && pytest tests/ -q
  ```

  Expected: 64 passed.

- [ ] **Step 7: Commit**

  ```bash
  git add custom_components/dsvdc4ha/config_flow.py tests/test_config_flow.py
  git commit -m "feat: add device_entity_user_input and device_plan_summary steps"
  ```

---

## Task 6: Config flow — `async_step_device_model_features` + end-to-end test

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py`
- Modify: `tests/test_config_flow.py`

- [ ] **Step 1: Write failing tests**

  Append to `tests/test_config_flow.py`:

  ```python
  @pytest.mark.asyncio
  async def test_device_model_features_cycles_and_routes_to_device_summary():
      flow = _make_subentry_flow()
      plan1 = _make_vdsd_plan("light.a")
      plan1.resolved_vdsd = {
          "primaryGroup": 1, "displayId": "M", "name": "Device — Light",
          "buttons": [], "binary_inputs": [], "sensors": [],
          "output": {"function": 3, "channels": []},
          "identify_action": None,
      }
      plan2 = _make_vdsd_plan("light.b")
      plan2.resolved_vdsd = dict(plan1.resolved_vdsd)
      plan2.resolved_vdsd["name"] = "Device — Light 2"

      flow._vdsd_plans = [plan1, plan2]
      flow._pending_vdsd_idx = 0
      flow._device_name = "Device"

      # First plan: show form
      result = await flow.async_step_device_model_features()
      assert result["type"] == "form"
      assert result["step_id"] == "device_model_features"

      # First plan: submit
      result2 = await flow.async_step_device_model_features({"features": ["dontcare"]})
      assert result2["step_id"] == "device_model_features"  # second plan
      assert flow._pending_vdsd_idx == 1

      # Second plan: submit → routes to device_summary
      result3 = await flow.async_step_device_model_features({"features": []})
      assert result3["step_id"] == "device_summary"


  @pytest.mark.asyncio
  async def test_full_ha_device_flow_creates_entry():
      """End-to-end: light.lamp on a device → one vdSD subentry."""
      flow = _make_subentry_flow()
      flow._device_name = "My Lamp"
      flow._vendor_name = "Acme"
      flow._display_id = "LampModel"

      plan = _make_vdsd_plan("light.lamp")
      plan.resolved_vdsd = {
          "displayId": "LampModel",
          "primaryGroup": 1,
          "model": "LampModel",
          "vendorName": "Acme",
          "modelVersion": "1.0",
          "modelUID": "AcmeLampModel",
          "name": "My Lamp — Light",
          "active": True,
          "identify_action": None,
          "firmwareUpdate_action": None,
          "optional": {},
          "buttons": [],
          "binary_inputs": [],
          "sensors": [],
          "output": {"function": 3, "channels": [], "groups": [1],
                     "defaultGroup": 1, "activeGroup": 1, "variableRamp": True,
                     "mode": 2, "onThreshold": 50, "outputUsage": 1, "name": "Output"},
      }
      flow._vdsd_plans = [plan]
      flow._pending_vdsd_idx = 0

      await flow.async_step_device_model_features({"features": ["dontcare"]})
      result = await flow.async_step_device_summary({"action": "create", "confirm": True})

      assert result["type"] == "create_entry"
      assert result["title"] == "My Lamp"
      assert len(result["data"]["vdsds"]) == 1
      assert result["data"]["vdsds"][0]["displayId"] == "LampModel"
  ```

- [ ] **Step 2: Run tests to confirm they fail**

  ```bash
  source .venv/bin/activate && pytest tests/test_config_flow.py -k "device_model_features or full_ha_device" -v
  ```

  Expected: `AttributeError: 'VdsdSubentryFlowHandler' object has no attribute 'async_step_device_model_features'`

- [ ] **Step 3: Implement `async_step_device_model_features`**

  Add after `async_step_device_plan_summary` in `config_flow.py`:

  ```python
  async def async_step_device_model_features(self, user_input: dict | None = None):
      """Per-vdSD model features selection for the HA-device path."""
      plan = self._vdsd_plans[self._pending_vdsd_idx]
      vdsd = plan.resolved_vdsd or {}

      if user_input is not None:
          plan.model_features = user_input.get("features", [])
          vdsd["model_features"] = plan.model_features
          self._pending_vdsd_idx += 1
          if self._pending_vdsd_idx < len(self._vdsd_plans):
              return await self.async_step_device_model_features()
          # All plans done — assemble _vdsds and go to device_summary
          self._vdsds = [p.resolved_vdsd for p in self._vdsd_plans if p.resolved_vdsd]
          return await self.async_step_device_summary()

      auto_features = _compute_auto_features(
          primary_group=int(vdsd.get("primaryGroup", 1)),
          buttons=vdsd.get("buttons", []),
          binary_inputs=vdsd.get("binary_inputs", []),
          sensors=vdsd.get("sensors", []),
          output=vdsd.get("output"),
          has_identify=bool(vdsd.get("identify_action")),
      )
      options: list[selector.SelectOptionDict] = []
      for key, label in _AUTO_FEATURE_LABELS.items():
          options.append(selector.SelectOptionDict(value=key, label=label))
      for key, label in _OPTIONAL_FEATURE_LABELS.items():
          options.append(selector.SelectOptionDict(value=key, label=label))
      schema = vol.Schema({
          vol.Optional("features", default=sorted(auto_features)): selector.SelectSelector(
              selector.SelectSelectorConfig(options=options, multiple=True)
          ),
      })
      current = self._pending_vdsd_idx + 1
      total = len(self._vdsd_plans)
      return self.async_show_form(
          step_id="device_model_features",
          data_schema=schema,
          description_placeholders={
              "current": str(current),
              "total": str(total),
              "vdsd_name": plan.name,
          },
      )
  ```

- [ ] **Step 4: Run all new tests**

  ```bash
  source .venv/bin/activate && pytest tests/test_config_flow.py -k "device_model_features or full_ha_device" -v
  ```

  Expected: 2 passed.

- [ ] **Step 5: Run full suite**

  ```bash
  source .venv/bin/activate && pytest tests/ -q
  ```

  Expected: 66 passed.

- [ ] **Step 6: Commit**

  ```bash
  git add custom_components/dsvdc4ha/config_flow.py tests/test_config_flow.py
  git commit -m "feat: add device_model_features step; complete from_ha_device flow"
  ```

---

## Task 7: Strings and translation files

**Files:**
- Modify: `custom_components/dsvdc4ha/strings.json`
- Modify: `custom_components/dsvdc4ha/translations/en.json`

- [ ] **Step 1: Add `from_ha_device` option to `creation_mode` in `strings.json`**

  In `strings.json`, find `config_subentries.device.step.creation_mode.data.mode` and replace its parent step block:

  ```json
  "creation_mode": {
    "title": "Create vdSD",
    "description": "How would you like to create the virtual device (vdSD)?",
    "data": {
      "mode": "Creation method"
    }
  },
  ```

  The strings file doesn't need option labels (those are in the selector in code), so the step block stays unchanged. The new option label `"Create multi-vdSD device from HA device"` is defined directly in the selector in `config_flow.py`.

- [ ] **Step 2: Add four new step entries to `strings.json`**

  In `strings.json`, inside `config_subentries.device.step`, add after `creation_mode`:

  ```json
  "device_picker": {
    "title": "Select HA Device",
    "description": "Select the Home Assistant device to derive virtual dS devices from. All supported entities on this device will be automatically mapped to vdSDs.",
    "data": {
      "device_id": "Home Assistant device"
    }
  },
  "device_entity_user_input": {
    "title": "Entity Options ({current} of {total})",
    "description": "Entity: {entity_name} ({domain}). Some settings for this entity type require your input.",
    "data": {
      "sensor_function": "Binary input function",
      "group": "Button / input group",
      "sensor_type": "Sensor type",
      "min": "Minimum value",
      "max": "Maximum value",
      "resolution": "Resolution (LSB)",
      "output_usage": "Output usage (indoor / outdoor)",
      "function": "Output function",
      "has_tilt": "Device supports tilt / blade angle control"
    }
  },
  "device_plan_summary": {
    "title": "Device Plan Summary",
    "description": "The following vdSDs will be created:\n{summary}\n\nEntities without a dS mapping (manual creation required if needed):\n{unsupported}",
    "data": {
      "action": "Action"
    }
  },
  "device_model_features": {
    "title": "Model Features — {vdsd_name} ({current} of {total})",
    "description": "The following model features will be added to this vdSD. Auto-derived features are pre-selected; adjust as needed."
  }
  ```

- [ ] **Step 3: Mirror the same four step entries into `translations/en.json`**

  Add the identical JSON blocks to `translations/en.json` inside `config_subentries.device.step`.

- [ ] **Step 4: Run tests to verify JSON is valid and tests still pass**

  ```bash
  source .venv/bin/activate && python3 -c "import json; json.load(open('custom_components/dsvdc4ha/strings.json')); json.load(open('custom_components/dsvdc4ha/translations/en.json')); print('JSON valid')"
  pytest tests/ -q
  ```

  Expected: `JSON valid` then `66 passed`.

- [ ] **Step 5: Commit**

  ```bash
  git add custom_components/dsvdc4ha/strings.json custom_components/dsvdc4ha/translations/en.json
  git commit -m "feat: add UI strings for multi-vdSD device flow steps"
  ```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| Third `creation_mode` option `from_ha_device` | Task 4 |
| `device_picker` with `DeviceSelector` | Task 4 |
| Per-entity choice screens | Task 5 |
| `device_plan_summary` with summary text + unsupported list | Task 5 |
| `device_model_features` cycling | Task 6 |
| Routes to existing `device_summary` | Task 6 |
| `compute_vdsd_plan` Phase 1–5 | Task 2 |
| Output entity priority (tier + name + alphabetical) | Task 2 |
| `resolve_vdsd_plan` with channel auto-binding | Task 3 |
| `resolve_vdsd_plan` output_usage_choices | Task 3 |
| `resolve_vdsd_plan` min_max_user from entity_states | Task 3 |
| `CHANNEL_TYPE_LABELS` moved to entity_mapping | Task 1 |
| Plan naming with suffixes | Task 2 |
| Strings for all 4 new steps | Task 7 |
| 15 pure unit tests for device_grouper | Tasks 2–3 |
| 7 config flow integration tests | Tasks 4–6 |

All spec requirements covered. No placeholders detected. Type names consistent across all tasks (`VdsdPlan`, `EntityInfo`, `_EntityInfo` alias in config_flow, `compute_vdsd_plan`, `resolve_vdsd_plan`).
