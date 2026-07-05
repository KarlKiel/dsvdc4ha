# Manual Callback Bindings Redesign Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current manual callback binding model with a structured, user-friendly "value mapping" system that lets users configure exactly how dS channel values map to HA service parameters, and how HA entity attribute values map back to dS channels — without requiring the user to write Python expressions.

**Architecture:** Instead of raw `push_expr` / `apply_expr` Python strings, the from-scratch flow uses a structured binding model: each binding is a `{source, transform, target}` triplet. The existing expression evaluator is kept for auto-generated bindings (entity mapping derived); manual bindings use the new structured model. A converter layer translates structured bindings → expressions at config-save time, keeping the runtime (listeners.py) unchanged.

**Tech Stack:** Python, Home Assistant config flow selectors, HA state/attribute model, existing pydsvdcapi channel type definitions.

**Prerequisite:** This plan assumes `docs/superpowers/plans/2026-06-22-known-issues.md` has been implemented (especially Task 6 — plug output fix).

---

## Background and Problem Statement

The current from-scratch (custom device) flow asks users to provide `read_entity` (for push_expr) and `write_action` (for apply_expr) per output channel and per input callback. This model is insufficient because:

1. **HA → dS direction (push):** The "value" pushed to dS comes from an entity's STATE, not its attributes. But many relevant values live in attributes (e.g., `brightness`, `color_temp`, `current_position`). Users have no way to specify "use the `brightness` attribute of this light entity, converted to 0-100%".

2. **dS → HA direction (apply):** The dS channel value arrives as a float. Users need to specify which HA service to call AND how to map that float to a service parameter. The current free-text "write action" approach is opaque and error-prone.

3. **Binary input, sensor, button callbacks:** These also suffer from missing mapping specificity — the user selects an entity, but can't control which attribute to read or how to transform the value.

## New Binding Model

Each binding is described as a structured dict stored in the config:

```python
# For push (HA → dS): how to read a value from HA into a dS channel
{
    "source_entity": "light.living_room",   # HA entity to watch
    "source_attribute": "brightness",        # None → use state; otherwise attribute name
    "transform": "scale_0_255_to_0_100",    # named transform from TRANSFORMS registry
    "channel_type": 1,                       # dS channel type (BRIGHTNESS=1)
}

# For apply (dS → HA): how to call an HA service when dS sends a value
{
    "target_entity": "light.living_room",    # HA entity to control
    "service": "light.turn_on",              # HA service
    "parameter": "brightness",               # service data key to receive the mapped value
    "transform": "scale_0_100_to_0_255",    # named transform from TRANSFORMS registry
    "channel_type": 1,                       # dS channel type that triggers this
}
```

At config-save time, these structured bindings are compiled to `push_expr` / `apply_expr` Python strings (compatible with the existing runtime in `listeners.py`). The runtime is not changed.

---

## File Structure

| Task | Files |
|------|-------|
| 1. Transform registry | `custom_components/dsvdc4ha/binding_transforms.py` (new) |
| 2. Binding compiler | `custom_components/dsvdc4ha/binding_compiler.py` (new) |
| 3. Push binding UI step | `custom_components/dsvdc4ha/config_flow.py` |
| 4. Apply binding UI step | `custom_components/dsvdc4ha/config_flow.py` |
| 5. Binary/sensor/button binding UI | `custom_components/dsvdc4ha/config_flow.py` |
| 6. Tests | `tests/test_binding_transforms.py`, `tests/test_binding_compiler.py` |

---

## Task 1: Transform Registry

Define the set of named transforms that the UI offers for value mapping.

**Files:**
- Create: `custom_components/dsvdc4ha/binding_transforms.py`

- [ ] **Step 1: Write failing test**

  Create `tests/test_binding_transforms.py`:
  
  ```python
  """Tests for the binding transform registry."""
  
  def test_transform_registry_has_passthrough():
      from custom_components.dsvdc4ha.binding_transforms import TRANSFORMS
      assert "passthrough" in TRANSFORMS
  
  def test_passthrough_transform():
      from custom_components.dsvdc4ha.binding_transforms import apply_transform
      assert apply_transform("passthrough", 42.0) == 42.0
  
  def test_scale_0_255_to_0_100():
      from custom_components.dsvdc4ha.binding_transforms import apply_transform
      result = apply_transform("scale_0_255_to_0_100", 255.0)
      assert abs(result - 100.0) < 0.1
      result = apply_transform("scale_0_255_to_0_100", 0.0)
      assert result == 0.0
  
  def test_scale_0_100_to_0_255():
      from custom_components.dsvdc4ha.binding_transforms import apply_transform
      result = apply_transform("scale_0_100_to_0_255", 100.0)
      assert abs(result - 255.0) < 0.5
  
  def test_bool_to_0_1():
      from custom_components.dsvdc4ha.binding_transforms import apply_transform
      assert apply_transform("bool_to_1_0", "on") == 1.0
      assert apply_transform("bool_to_1_0", "off") == 0.0
  
  def test_invert_0_100():
      from custom_components.dsvdc4ha.binding_transforms import apply_transform
      assert apply_transform("invert_0_100", 70.0) == 30.0
  ```

- [ ] **Step 2: Run tests to verify they fail**

  ```bash
  pytest tests/test_binding_transforms.py -v
  ```

- [ ] **Step 3: Create binding_transforms.py**

  ```python
  """Named value transforms for structured channel bindings."""
  from __future__ import annotations
  from typing import Any
  
  # Each transform: (label, push_expr_template, apply_expr_template)
  # push_expr_template: Python expression for HA→dS direction; `v` is the source value
  # apply_expr_template: Python expression for dS→HA direction; `v` is the dS channel value
  
  TRANSFORMS: dict[str, dict[str, str]] = {
      "passthrough": {
          "label": "Pass through (no conversion)",
          "push_expr": "float(v)",
          "apply_expr": "float(v)",
      },
      "scale_0_255_to_0_100": {
          "label": "HA brightness (0-255) → dS (0-100%)",
          "push_expr": "round(v / 2.55, 1)",
          "apply_expr": "round(v * 2.55)",
      },
      "scale_0_100_to_0_255": {
          "label": "dS percentage (0-100%) → HA (0-255)",
          "push_expr": "round(v * 2.55)",
          "apply_expr": "round(v / 2.55, 1)",
      },
      "bool_to_1_0": {
          "label": "HA on/off → dS 1/0",
          "push_expr": "1.0 if str(v).lower() in ('on','true','1') else 0.0",
          "apply_expr": "1.0 if v > 0 else 0.0",
      },
      "bool_to_100_0": {
          "label": "HA on/off → dS 100%/0%",
          "push_expr": "100.0 if str(v).lower() in ('on','true','1') else 0.0",
          "apply_expr": "100.0 if v > 0 else 0.0",
      },
      "invert_0_100": {
          "label": "Invert 0-100% (dS shade position vs. HA open position)",
          "push_expr": "round(100.0 - float(v), 1)",
          "apply_expr": "round(100.0 - float(v), 1)",
      },
      "mired_to_kelvin": {
          "label": "HA color_temp (mired) → dS color temperature (mired)",
          "push_expr": "float(v)",  # same unit, no conversion needed
          "apply_expr": "float(v)",
      },
      "kelvin_to_mired": {
          "label": "HA color_temp_kelvin (K) → dS color temperature (mired)",
          "push_expr": "round(1_000_000 / max(float(v), 1))",
          "apply_expr": "round(1_000_000 / max(float(v), 1))",
      },
      "hs_hue": {
          "label": "HA hs_color[0] → dS hue (0-360°)",
          "push_expr": "(v or (0, 0))[0]",  # v = hs_color tuple
          "apply_expr": "float(v)",
      },
      "hs_saturation": {
          "label": "HA hs_color[1] → dS saturation (0-100%)",
          "push_expr": "(v or (0, 0))[1]",
          "apply_expr": "float(v)",
      },
  }
  
  
  def apply_transform(name: str, value: Any) -> float:
      """Apply a transform by name. For testing and runtime use."""
      t = TRANSFORMS.get(name)
      if t is None:
          raise ValueError(f"Unknown transform: {name!r}")
      ctx = {"v": value, "__builtins__": {}, "round": round, "float": float, "str": str, "max": max}
      return float(eval(t["push_expr"], ctx))  # noqa: S307
  
  
  TRANSFORM_OPTIONS: list[dict] = [
      {"value": k, "label": v["label"]} for k, v in TRANSFORMS.items()
  ]
  ```

- [ ] **Step 4: Run tests to verify they pass**

  ```bash
  pytest tests/test_binding_transforms.py -v
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add custom_components/dsvdc4ha/binding_transforms.py tests/test_binding_transforms.py
  git commit -m "feat: add named transform registry for structured channel bindings"
  ```

---

## Task 2: Binding Compiler

Compile structured binding dicts to `push_expr` / `apply_expr` Python expression strings compatible with the existing `listeners.py` runtime.

**Files:**
- Create: `custom_components/dsvdc4ha/binding_compiler.py`
- Create: `tests/test_binding_compiler.py`

- [ ] **Step 1: Write failing tests**

  Create `tests/test_binding_compiler.py`:
  
  ```python
  """Tests for the binding compiler."""
  
  def test_compile_push_binding_from_state():
      """Push binding with source_attribute=None uses entity.state directly."""
      from custom_components.dsvdc4ha.binding_compiler import compile_push_binding
      push_expr = compile_push_binding({
          "source_attribute": None,
          "transform": "bool_to_1_0",
      })
      assert "entity.state" in push_expr
  
  def test_compile_push_binding_from_attribute():
      """Push binding with source_attribute uses attrs.get(attr)."""
      from custom_components.dsvdc4ha.binding_compiler import compile_push_binding
      push_expr = compile_push_binding({
          "source_attribute": "brightness",
          "transform": "scale_0_255_to_0_100",
      })
      assert "attrs.get('brightness')" in push_expr or "attrs['brightness']" in push_expr
  
  def test_compile_apply_binding_turn_on():
      """Apply binding produces a valid HA service call expression."""
      from custom_components.dsvdc4ha.binding_compiler import compile_apply_binding
      apply_expr = compile_apply_binding({
          "service": "light.turn_on",
          "parameter": "brightness",
          "transform": "scale_0_100_to_0_255",
      })
      assert "light" in apply_expr
      assert "brightness" in apply_expr
  
  def test_compile_apply_binding_with_no_parameter():
      """Apply binding with no parameter produces a plain on/off service call."""
      from custom_components.dsvdc4ha.binding_compiler import compile_apply_binding
      apply_expr = compile_apply_binding({
          "service": "switch.turn_on",
          "parameter": None,
          "transform": "bool_to_1_0",
      })
      assert "switch" in apply_expr
  ```

- [ ] **Step 2: Run tests to verify they fail**

  ```bash
  pytest tests/test_binding_compiler.py -v
  ```

- [ ] **Step 3: Create binding_compiler.py**

  ```python
  """Compile structured binding configs to push_expr / apply_expr strings."""
  from __future__ import annotations
  
  from .binding_transforms import TRANSFORMS
  
  
  def compile_push_binding(binding: dict) -> str:
      """Return a push_expr string for the given structured push binding.
  
      binding keys:
        source_attribute: str | None  — None = use entity.state; otherwise attrs key
        transform: str                — key in TRANSFORMS registry
      """
      t = TRANSFORMS.get(binding.get("transform", "passthrough"), TRANSFORMS["passthrough"])
      push_template = t["push_expr"]
  
      attr = binding.get("source_attribute")
      if attr is None:
          source = "entity.state"
      else:
          source = f"attrs.get('{attr}')"
  
      # Replace `v` in the push template with the actual source expression.
      # Templates use `v` as the raw source value placeholder.
      expr = push_template.replace("v", source)
      return expr
  
  
  def compile_apply_binding(binding: dict) -> str:
      """Return an apply_expr string for the given structured apply binding.
  
      binding keys:
        service: str        — HA service in 'domain.service' format
        parameter: str|None — service_data key to set; None = no data beyond entity_id
        transform: str      — key in TRANSFORMS registry (applied to the dS channel value)
      """
      t = TRANSFORMS.get(binding.get("transform", "passthrough"), TRANSFORMS["passthrough"])
      apply_template = t["apply_expr"]
  
      domain, service_name = (binding["service"] + ".x").split(".", 1)[0], binding["service"].split(".", 1)[1]
      parameter = binding.get("parameter")
  
      # Build the transformed-value expression (applied to `value` from listeners.py)
      transformed = apply_template.replace("v", "value")
  
      if parameter:
          service_data = f"{{'{parameter}': {transformed}}}"
      else:
          service_data = "{}"
  
      return f"{{'domain':'{domain}','service':'{service_name}','service_data':{service_data}}}"
  
  
  def compile_channel_binding(push_binding: dict, apply_binding: dict | None) -> dict:
      """Return a channel config dict with push_expr and optionally apply_expr.
  
      Used when building vdsd_data from the from-scratch config flow.
      """
      result: dict = {}
      result["push_expr"] = compile_push_binding(push_binding)
      if push_binding.get("source_entity"):
          result["read_entity"] = push_binding["source_entity"]
      if apply_binding:
          result["apply_expr"] = compile_apply_binding(apply_binding)
      return result
  ```

- [ ] **Step 4: Run tests to verify they pass**

  ```bash
  pytest tests/test_binding_compiler.py -v
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add custom_components/dsvdc4ha/binding_compiler.py tests/test_binding_compiler.py
  git commit -m "feat: add binding compiler to translate structured bindings to push/apply expressions"
  ```

---

## Task 3: Push Binding UI Step (HA → dS)

Replace the current "read entity" free-text channel binding step with a structured form that lets users pick:
1. Source entity to watch
2. Which attribute to read (or use the main state)
3. Which transform to apply

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py`
- Modify: `custom_components/dsvdc4ha/translations/en.json`

- [ ] **Step 1: Add push binding step**

  In `config_flow.py`, replace or augment `async_step_channel_mapping` with a push binding step:
  
  ```python
  async def async_step_channel_push_binding(self, user_input: dict | None = None):
      """Collect the HA→dS push binding for the current output channel."""
      if user_input is not None:
          ch = self._current_channels[self._channel_mapping_idx]
          from .binding_compiler import compile_push_binding
          source_attr = user_input.get("source_attribute") or None
          binding = {
              "source_entity": user_input.get("source_entity"),
              "source_attribute": source_attr,
              "transform": user_input.get("transform", "passthrough"),
          }
          ch["read_entity"] = binding["source_entity"]
          ch["push_expr"] = compile_push_binding(binding)
          # Advance to apply binding step for the same channel
          return await self.async_step_channel_apply_binding()
  
      ch = self._current_channels[self._channel_mapping_idx]
      ch_type = ch.get("channelType", 0)
      from .entity_mapping import CHANNEL_TYPE_LABELS
      ch_label = CHANNEL_TYPE_LABELS.get(ch_type, f"Channel {ch_type}")
  
      from .binding_transforms import TRANSFORM_OPTIONS
  
      # Build attribute choices dynamically based on selected entity (show common attributes)
      # For the initial show, offer a generic list; user can type custom attribute name too
      attr_options = [
          {"value": "", "label": "(use main entity state)"},
          {"value": "brightness", "label": "brightness"},
          {"value": "color_temp", "label": "color_temp (mired)"},
          {"value": "color_temp_kelvin", "label": "color_temp_kelvin (K)"},
          {"value": "current_position", "label": "current_position"},
          {"value": "current_tilt_position", "label": "current_tilt_position"},
          {"value": "hs_color", "label": "hs_color (tuple)"},
          {"value": "percentage", "label": "percentage"},
          {"value": "volume_level", "label": "volume_level"},
      ]
  
      schema = vol.Schema({
          vol.Required("source_entity"): selector.EntitySelector(),
          vol.Optional("source_attribute", default=""): selector.SelectSelector(
              selector.SelectSelectorConfig(options=attr_options, custom_value=True)
          ),
          vol.Required("transform", default="passthrough"): selector.SelectSelector(
              selector.SelectSelectorConfig(options=TRANSFORM_OPTIONS)
          ),
      })
      return self.async_show_form(
          step_id="channel_push_binding",
          data_schema=schema,
          description_placeholders={"channel": ch_label},
      )
  ```

- [ ] **Step 2: Add translation**

  In `translations/en.json`, add:
  
  ```json
  "channel_push_binding": {
    "title": "HA → dS Binding — {channel}",
    "description": "Configure how to read a value from Home Assistant and push it to the dS channel '{channel}'.",
    "data": {
      "source_entity": "Source entity (watched for changes)",
      "source_attribute": "Attribute to read (empty = use main state)",
      "transform": "Value transformation"
    }
  }
  ```

- [ ] **Step 3: Run tests**

  ```bash
  pytest tests/ -v
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add custom_components/dsvdc4ha/config_flow.py \
          custom_components/dsvdc4ha/translations/en.json
  git commit -m "feat: replace free-text channel binding with structured push binding UI"
  ```

---

## Task 4: Apply Binding UI Step (dS → HA)

Add a structured form for configuring the dS → HA direction per channel:
1. Target entity
2. HA service to call
3. Which service parameter receives the mapped value
4. Which transform to apply to the dS channel value

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py`
- Modify: `custom_components/dsvdc4ha/translations/en.json`

- [ ] **Step 1: Add apply binding step**

  ```python
  async def async_step_channel_apply_binding(self, user_input: dict | None = None):
      """Collect the dS→HA apply binding for the current output channel."""
      if user_input is not None:
          ch = self._current_channels[self._channel_mapping_idx]
          service_raw = user_input.get("service", "")
          if service_raw:
              from .binding_compiler import compile_apply_binding
              binding = {
                  "service": service_raw,
                  "parameter": user_input.get("parameter") or None,
                  "transform": user_input.get("transform", "passthrough"),
              }
              ch["apply_expr"] = compile_apply_binding(binding)
          # Advance to next channel or finish
          self._channel_mapping_idx += 1
          if self._channel_mapping_idx < len(self._current_channels):
              return await self.async_step_channel_push_binding()
          return await self.async_step_channel_mapping_done()
  
      ch = self._current_channels[self._channel_mapping_idx]
      ch_type = ch.get("channelType", 0)
      from .entity_mapping import CHANNEL_TYPE_LABELS
      ch_label = CHANNEL_TYPE_LABELS.get(ch_type, f"Channel {ch_type}")
  
      from .binding_transforms import TRANSFORM_OPTIONS
  
      # Common HA service options (user can also type a custom service)
      service_options = [
          {"value": "", "label": "(no dS→HA control for this channel)"},
          {"value": "light.turn_on", "label": "light.turn_on"},
          {"value": "light.turn_off", "label": "light.turn_off"},
          {"value": "switch.turn_on", "label": "switch.turn_on"},
          {"value": "switch.turn_off", "label": "switch.turn_off"},
          {"value": "cover.set_cover_position", "label": "cover.set_cover_position"},
          {"value": "cover.set_cover_tilt_position", "label": "cover.set_cover_tilt_position"},
          {"value": "fan.set_percentage", "label": "fan.set_percentage"},
          {"value": "number.set_value", "label": "number.set_value"},
          {"value": "climate.set_temperature", "label": "climate.set_temperature"},
      ]
  
      parameter_options = [
          {"value": "", "label": "(no parameter — value not passed)"},
          {"value": "brightness", "label": "brightness"},
          {"value": "color_temp_kelvin", "label": "color_temp_kelvin"},
          {"value": "position", "label": "position"},
          {"value": "tilt_position", "label": "tilt_position"},
          {"value": "percentage", "label": "percentage"},
          {"value": "value", "label": "value"},
          {"value": "temperature", "label": "temperature"},
          {"value": "volume_level", "label": "volume_level"},
      ]
  
      schema = vol.Schema({
          vol.Optional("service", default=""): selector.SelectSelector(
              selector.SelectSelectorConfig(options=service_options, custom_value=True)
          ),
          vol.Optional("parameter", default=""): selector.SelectSelector(
              selector.SelectSelectorConfig(options=parameter_options, custom_value=True)
          ),
          vol.Required("transform", default="passthrough"): selector.SelectSelector(
              selector.SelectSelectorConfig(options=TRANSFORM_OPTIONS)
          ),
      })
      return self.async_show_form(
          step_id="channel_apply_binding",
          data_schema=schema,
          description_placeholders={"channel": ch_label},
      )
  ```

- [ ] **Step 2: Add translation**

  In `translations/en.json`:
  
  ```json
  "channel_apply_binding": {
    "title": "dS → HA Binding — {channel}",
    "description": "Configure how to translate a dS channel value from '{channel}' into a Home Assistant action.",
    "data": {
      "service": "HA service to call (empty = no dS→HA control)",
      "parameter": "Service data parameter to pass the mapped value to",
      "transform": "Value transformation (applied to dS channel value)"
    }
  }
  ```

- [ ] **Step 3: Run tests**

  ```bash
  pytest tests/ -v
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add custom_components/dsvdc4ha/config_flow.py \
          custom_components/dsvdc4ha/translations/en.json
  git commit -m "feat: add structured apply (dS→HA) binding step to channel mapping flow"
  ```

---

## Task 5: Binary Input, Sensor, and Button Binding UI

Apply the same structured binding approach to non-output callback configurations.

**Binary Input push (HA→dS):**
- Source entity + attribute + transform → `callback_entity` + value derivation
- Binary inputs need a boolean output (on/off) — transforms that produce 0/1

**Sensor push (HA→dS):**
- Source entity + attribute + transform → float value sent to dSS

**Button/Event callbacks:**
- Click type or scene ID — let user choose between: pass-through from entity state, auto-detect clicks, or manual mapping

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py`
- Modify: `custom_components/dsvdc4ha/translations/en.json`

- [ ] **Step 1: Binary input binding step**

  In `config_flow.py`, add a structured binary input callback step:
  
  ```python
  async def async_step_binary_input_binding(self, user_input: dict | None = None):
      """Structured binding for binary input callback."""
      if user_input is not None:
          bi = self._current_binary_inputs[-1]  # the one just added
          binding_type = user_input.get("binding_type", "entity_state")
          if binding_type == "entity_state":
              bi["callback_entity"] = user_input.get("source_entity")
              # Standard boolean from state — listeners.py handles this natively
          elif binding_type == "entity_attribute":
              bi["callback_entity"] = user_input.get("source_entity")
              bi["value_attribute"] = user_input.get("source_attribute")
              bi["value_transform"] = user_input.get("transform", "passthrough")
          return await self.async_step_vdsd_overview()
  
      schema = vol.Schema({
          vol.Required("binding_type", default="entity_state"): selector.SelectSelector(
              selector.SelectSelectorConfig(options=[
                  {"value": "entity_state", "label": "Use entity on/off state"},
                  {"value": "entity_attribute", "label": "Use attribute value with transform"},
              ], mode=selector.SelectSelectorMode.LIST)
          ),
          vol.Optional("source_entity"): selector.EntitySelector(),
          vol.Optional("source_attribute", default=""): selector.TextSelector(),
          vol.Optional("transform", default="bool_to_1_0"): selector.SelectSelector(
              selector.SelectSelectorConfig(options=TRANSFORM_OPTIONS)
          ),
      })
      return self.async_show_form(step_id="binary_input_binding", data_schema=schema)
  ```

- [ ] **Step 2: Sensor binding step**

  ```python
  async def async_step_sensor_binding(self, user_input: dict | None = None):
      """Structured binding for sensor input callback."""
      if user_input is not None:
          si = self._current_sensors[-1]
          si["callback_entity"] = user_input.get("source_entity")
          if attr := user_input.get("source_attribute"):
              si["value_attribute"] = attr
          if transform := user_input.get("transform"):
              si["value_transform"] = transform
          return await self.async_step_vdsd_overview()
  
      from .binding_transforms import TRANSFORM_OPTIONS
      schema = vol.Schema({
          vol.Optional("source_entity"): selector.EntitySelector(),
          vol.Optional("source_attribute", default=""): selector.TextSelector(),
          vol.Optional("transform", default="passthrough"): selector.SelectSelector(
              selector.SelectSelectorConfig(options=TRANSFORM_OPTIONS)
          ),
      })
      return self.async_show_form(step_id="sensor_binding", data_schema=schema)
  ```

- [ ] **Step 3: Add translations**

  In `translations/en.json`:
  
  ```json
  "binary_input_binding": {
    "title": "Binary Input Binding",
    "description": "Configure how to derive an on/off value from Home Assistant for this binary input.",
    "data": {
      "binding_type": "Binding type",
      "source_entity": "Source entity",
      "source_attribute": "Attribute (empty = use state)",
      "transform": "Value transform"
    }
  },
  "sensor_binding": {
    "title": "Sensor Input Binding",
    "description": "Configure how to derive a numeric value from Home Assistant for this sensor input.",
    "data": {
      "source_entity": "Source entity",
      "source_attribute": "Attribute (empty = use state)",
      "transform": "Value transform"
    }
  }
  ```

- [ ] **Step 4: Update listeners.py to handle value_attribute**

  In `listeners.py`, in the binary input and sensor listener setup, respect `value_attribute` and `value_transform` if present:
  
  ```python
  # Binary input listener (in setup_input_listeners):
  value_attr = bi_data.get("value_attribute")
  value_transform_name = bi_data.get("value_transform")
  
  @callback
  def _on_binary_state(event: Event, _bi=bi, _is_bool=is_bool, _invert=invert_bi,
                        _attr=value_attr, _transform=value_transform_name) -> None:
      new_state = event.data.get("new_state")
      if not new_state or new_state.state in ("unknown", "unavailable"):
          return
      if _attr:
          raw = new_state.attributes.get(_attr)
      else:
          raw = new_state.state
      if _transform and _attr:
          from .binding_transforms import apply_transform
          try:
              val = apply_transform(_transform, raw)
              is_on = val > 0
          except Exception:
              return
      elif _is_bool:
          is_on = str(raw).lower() in ("on", "true", "1")
          if _invert:
              is_on = not is_on
      else:
          try:
              is_on = float(raw) > 0
          except (ValueError, TypeError):
              return
      hass.async_create_task(api.report_binary_value(_bi, is_on))
  ```

- [ ] **Step 5: Write tests**

  ```python
  # In tests/test_binding_compiler.py, add:
  
  def test_compile_push_binding_from_attribute_brightness():
      from custom_components.dsvdc4ha.binding_compiler import compile_push_binding
      expr = compile_push_binding({
          "source_attribute": "brightness",
          "transform": "scale_0_255_to_0_100",
      })
      # Evaluate with mock attrs
      ctx = {"attrs": {"brightness": 128}, "entity": None, "round": round, "float": float, "__builtins__": {}}
      result = eval(expr, ctx)  # noqa: S307
      assert abs(result - 50.0) < 1.0
  ```

- [ ] **Step 6: Run tests**

  ```bash
  pytest tests/ -v
  ```

- [ ] **Step 7: Commit**

  ```bash
  git add custom_components/dsvdc4ha/config_flow.py \
          custom_components/dsvdc4ha/listeners.py \
          custom_components/dsvdc4ha/translations/en.json \
          tests/test_binding_compiler.py
  git commit -m "feat: add structured binding UI for binary input and sensor callbacks"
  ```

---

## Self-Review

**Spec coverage check:**
- ✅ Output channel push binding (HA attribute → dS): Task 3
- ✅ Output channel apply binding (dS value → HA service + parameter): Task 4
- ✅ Binary input binding with attribute support: Task 5
- ✅ Sensor input binding with attribute support: Task 5
- ✅ Transform registry with common conversions: Task 1
- ✅ Compiler that converts structured → expression strings: Task 2
- ⚠️ Button callback binding: partially addressed (binding_type selection); full click-type mapping from event/state is deferred — listeners.py `detect_clicks` mode handles the common case

**No placeholders:** All code blocks are complete.

**Type consistency:** `TRANSFORMS["key"]["push_expr"]` and `"apply_expr"` string templates are used consistently. `compile_push_binding` and `compile_apply_binding` return `str` in all cases.
