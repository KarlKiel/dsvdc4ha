# pydsvdcapi 0.8.9 Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire all new pydsvdcapi v0.8.9 Output/Channel/enum additions through the full
pipeline: entity_mapping → api.py → config_flow → Excel schema → audit.

**Architecture:** Every new Output() constructor parameter follows the same data path:
entity_mapping (static defaults) → config_flow (resolved into camelCase dict) → api.py
(passed to Output/OutputChannel constructors).  New enums must be added to the Excel
dropdown lists and audit checks.

**Tech Stack:** pydsvdcapi 0.8.9, Python 3.13, pytest, openpyxl

---

## What changed in pydsvdcapi v0.8.9

### New `Output()` constructor parameters (9 new, none removed)

> **All 9 new parameters are optional (default: `None`).** Pass `None` when not applicable — pydsvdcapi ignores `None` values in property trees.
>
> **dS 8-bit format note:** `dim_time_*` values are **NOT milliseconds**. They use the dS compact 8-bit encoding (integer). Do not label them in ms anywhere.

| Python param | camelCase config key | Type | Required? | Applicable device type |
|---|---|---|---|---|
| `active_cooling_mode` | `activeCoolingMode` | `bool \| None` | Optional | FCU / air-con / heat pump (devices that can actively cool) |
| `dim_time_up` | `dimTimeUp` | `int \| None` | Optional | **Dimmer/light outputs only**: DIMMER, DIMMER_COLOR_TEMP, FULL_COLOR_DIMMER |
| `dim_time_down` | `dimTimeDown` | `int \| None` | Optional | Dimmer/light outputs only |
| `dim_time_up_alt1` | `dimTimeUpAlt1` | `int \| None` | Optional | Dimmer/light outputs only |
| `dim_time_down_alt1` | `dimTimeDownAlt1` | `int \| None` | Optional | Dimmer/light outputs only |
| `dim_time_up_alt2` | `dimTimeUpAlt2` | `int \| None` | Optional | Dimmer/light outputs only |
| `dim_time_down_alt2` | `dimTimeDownAlt2` | `int \| None` | Optional | Dimmer/light outputs only |
| `heating_system_capability` | `heatingSystemCapability` | `HeatingSystemCapability \| None` | Optional | **Climate/heating actuator outputs only** (BLUE group: floor heating, radiators, etc.) |
| `heating_system_type` | `heatingSystemType` | `HeatingSystemType \| None` | Optional | Climate/heating actuator outputs only |

### Full Output() parameter reference (all params, required/optional, device applicability)

| Python param | Required? | Default | Applicable device type |
|---|---|---|---|
| `function` | **Required** | — | All outputs |
| `output_usage` | Optional | `UNDEFINED` | All outputs |
| `name` | Optional | `None` | All outputs |
| `default_group` | Optional | `None` | All outputs (use `ColorClass` values) |
| `variable_ramp` | Optional | `False` | All outputs; set `True` for dimmers |
| `max_power` | Optional | `-1.0` (undefined) | All outputs |
| `mode` | Optional | auto-derived from `function` | All outputs |
| `active_group` | Optional | `None` | All outputs |
| `groups` | Optional | empty set | All outputs |
| `push_changes` | Optional | `False` | All outputs |
| `on_threshold` | Optional | `None` | Dimmer outputs (min % to switch on non-dimmable lamps) |
| `min_brightness` | Optional | `None` | Dimmer outputs (min % hardware supports) |
| `active_cooling_mode` | Optional | `None` | **FCU / air-con / heat pump** (can actively cool) |
| `dim_time_up` | Optional | `None` | **Dimmer/light** (DIMMER, DIMMER_COLOR_TEMP, FULL_COLOR_DIMMER) — **dS 8-bit int** |
| `dim_time_down` | Optional | `None` | Dimmer/light — dS 8-bit int |
| `dim_time_up_alt1` | Optional | `None` | Dimmer/light — dS 8-bit int |
| `dim_time_down_alt1` | Optional | `None` | Dimmer/light — dS 8-bit int |
| `dim_time_up_alt2` | Optional | `None` | Dimmer/light — dS 8-bit int |
| `dim_time_down_alt2` | Optional | `None` | Dimmer/light — dS 8-bit int |
| `heating_system_capability` | Optional | `None` | **Climate/heating actuator** (BLUE group) |
| `heating_system_type` | Optional | `None` | Climate/heating actuator (BLUE group) |
| `open_time` | Optional | `None` | **Shadow/cover** (POSITIONAL function: shades, blinds, curtains) |
| `close_time` | Optional | `None` | Shadow/cover |
| `angle_open_time` | Optional | `None` | Shadow/cover with tilting slats (jalousie / venetian blinds) |
| `angle_close_time` | Optional | `None` | Shadow/cover with tilting slats |
| `stop_delay_time` | Optional | `None` | Shadow/cover |

### New enums
- `HeatingSystemCapability`: HEATING_ONLY(1), COOLING_ONLY(2), HEATING_AND_COOLING(3)
- `HeatingSystemType`: UNDEFINED(0), FLOOR_HEATING(1), RADIATOR(2), WALL_HEATING(3), CONVECTOR_PASSIVE(4), CONVECTOR_ACTIVE(5), FLOOR_HEATING_LOW_ENERGY(6)

### New `OutputChannelType`
- `FCU_OPERATION_MODE = 192` — already in CHANNEL_SPECS; needs entity_mapping entry

### New `OutputChannel` methods
- `set_uplink_converter(code: str | None)` — transform device→dS value in Python snippet
- `set_downlink_converter(code: str | None)` — transform dS→device value in Python snippet

### New `Vdsd()` constructor parameters (lower priority, out of scope)
- `prog_mode`, `current_config_id`, `configurations` — device management, not output/channel related

---

## File Structure

| File | What changes |
|---|---|
| `manifest.json` | version bump 0.8.8 → 0.8.9 |
| `api.py` | import new enums; pass 9 new Output params; wire channel converters |
| `tools/excel_schema.py` | import + register 2 new enums; add 9 output columns |
| `tools/audit_mapping.py` | add audit checks for new output fields |
| `config_flow.py` | add optional dim_time + heating_system UI in from-scratch flow |
| `entity_mapping.py` | no changes for now (no entity type currently uses new fields) |
| `tests/test_api.py` | extend `_add_output` tests for new parameters |

---

## Task 1: Version bump

**Files:** `manifest.json`

- [ ] Change `"pydsvdcapi==0.8.8"` to `"pydsvdcapi==0.8.9"` in requirements list

- [ ] Run tests
  ```
  .venv/bin/python -m pytest tests/ -q
  ```
  Expected: all 366 pass

- [ ] Commit
  ```bash
  git add custom_components/dsvdc4ha/manifest.json
  git commit -m "chore: bump pydsvdcapi requirement to 0.8.9"
  ```

---

## Task 2: Wire new Output parameters in api.py

**Files:** `api.py`

- [ ] Add imports at the top of api.py:
  ```python
  from pydsvdcapi.enums import (
      ...,
      HeatingSystemCapability,
      HeatingSystemType,
  )
  ```

- [ ] Extend `_add_output()` to pass all 9 new parameters:
  ```python
  output = Output(
      vdsd=vdsd,
      name=data["name"],
      function=OutputFunction(data["function"]),
      output_usage=OutputUsage(data.get("outputUsage", 0)),
      default_group=data["defaultGroup"],
      active_group=data["activeGroup"],
      groups=set(data["groups"]),
      variable_ramp=data.get("variableRamp", False),
      push_changes=True,
      mode=OutputMode(data["mode"]) if data.get("mode") is not None else None,
      on_threshold=data.get("onThreshold"),
      min_brightness=data.get("minBrightness"),
      max_power=data.get("maxPower"),
      active_cooling_mode=data.get("activeCoolingMode"),
      dim_time_up=data.get("dimTimeUp"),
      dim_time_down=data.get("dimTimeDown"),
      dim_time_up_alt1=data.get("dimTimeUpAlt1"),
      dim_time_down_alt1=data.get("dimTimeDownAlt1"),
      dim_time_up_alt2=data.get("dimTimeUpAlt2"),
      dim_time_down_alt2=data.get("dimTimeDownAlt2"),
      heating_system_capability=(
          HeatingSystemCapability(int(data["heatingSystemCapability"]))
          if data.get("heatingSystemCapability") is not None else None
      ),
      heating_system_type=(
          HeatingSystemType(int(data["heatingSystemType"]))
          if data.get("heatingSystemType") is not None else None
      ),
      open_time=data.get("openTime"),
      close_time=data.get("closeTime"),
      angle_open_time=data.get("angleOpenTime"),
      angle_close_time=data.get("angleCloseTime"),
      stop_delay_time=data.get("stopDelayTime"),
  )
  ```

- [ ] In the channel loop inside `_add_output()`, add converter wiring after `output.add_channel(...)`:
  ```python
  ch = output.channels[ds_index]
  if uc := ch_data.get("uplinkConverter"):
      ch.set_uplink_converter(uc)
  if dc := ch_data.get("downlinkConverter"):
      ch.set_downlink_converter(dc)
  ```

- [ ] Run tests:
  ```
  .venv/bin/python -m pytest tests/test_api.py -v
  ```
  Expected: all pass

- [ ] Commit:
  ```bash
  git add custom_components/dsvdc4ha/api.py
  git commit -m "feat: wire pydsvdcapi 0.8.9 new Output params and channel converters in api.py"
  ```

---

## Task 3: Update Excel schema

**Files:** `tools/excel_schema.py`

- [ ] Add import of new enums:
  ```python
  from pydsvdcapi.enums import (
      ...,
      HeatingSystemCapability,
      HeatingSystemType,
  )
  ```

- [ ] Add to `ENUM_OPTIONS` dict:
  ```python
  "HeatingSystemCapability": ["-"] + [m.name for m in HeatingSystemCapability],
  "HeatingSystemType":       ["-"] + [m.name for m in HeatingSystemType],
  ```

- [ ] Add to `ENUM_CLASS` dict:
  ```python
  "HeatingSystemCapability": HeatingSystemCapability,
  "HeatingSystemType":       HeatingSystemType,
  ```

- [ ] Add new columns in `_build_columns()` after the `shadow_angle_timing` entry
  (before button section):
  ```python
  # Output — active cooling / heating system (FCU / heat pump devices)
  ("output.active_cooling_mode", "YesNo",
   lambda e: "yes" if _sub(e, "output").get("active_cooling_mode") else "no"),
  ("output.heating_system_capability.VALUE", "HeatingSystemCapability",
   lambda e: enum_name(HeatingSystemCapability, _sub(e, "output").get("heating_system_capability"))),
  ("output.heating_system_type.VALUE", "HeatingSystemType",
   lambda e: enum_name(HeatingSystemType, _sub(e, "output").get("heating_system_type"))),
  # Output — dimmer timing (dS 8-bit format int; None = use dSS defaults)
  ("output.dimTimeUp",         None, lambda e: _sub(e, "output").get("dim_time_up")),
  ("output.dimTimeDown",       None, lambda e: _sub(e, "output").get("dim_time_down")),
  ("output.dimTimeUpAlt1",     None, lambda e: _sub(e, "output").get("dim_time_up_alt1")),
  ("output.dimTimeDownAlt1",   None, lambda e: _sub(e, "output").get("dim_time_down_alt1")),
  ("output.dimTimeUpAlt2",     None, lambda e: _sub(e, "output").get("dim_time_up_alt2")),
  ("output.dimTimeDownAlt2",   None, lambda e: _sub(e, "output").get("dim_time_down_alt2")),
  ```

- [ ] Run audit to confirm schema loads cleanly:
  ```
  .venv/bin/python tools/audit_mapping.py
  ```

- [ ] Run tests:
  ```
  .venv/bin/python -m pytest tests/test_mapping_excel.py -v
  ```

- [ ] Commit:
  ```bash
  git add tools/excel_schema.py
  git commit -m "feat: add HeatingSystem + dimmer-timing columns to Excel schema"
  ```

---

## Task 4: Update audit_mapping.py

**Files:** `tools/audit_mapping.py`

- [ ] Import new enums at top of file (they come from excel_schema.ENUM_CLASS, already extended in Task 3)

- [ ] In the `# output` section of `run_audit()`, after the existing `shadow_angle_timing` check,
  add checks:
  ```python
  # active_cooling_mode
  raw_acm = get("output.active_cooling_mode")
  if raw_acm is not None:
      exp_acm = str(raw_acm).strip().lower() == "yes"
      if bool(o.get("active_cooling_mode")) != exp_acm:
          _dis(domain, dc, "output", "active_cooling_mode", exp_acm, o.get("active_cooling_mode"))
  # heating_system_capability
  chk_val("output", "heating_system_capability", "HeatingSystemCapability",
          "output.heating_system_capability.VALUE",
          o.get("heating_system_capability", 0) if o.get("heating_system_capability") is not None else 0)
  # heating_system_type
  chk_val("output", "heating_system_type", "HeatingSystemType",
          "output.heating_system_type.VALUE",
          o.get("heating_system_type", 0) if o.get("heating_system_type") is not None else 0)
  # dimmer timing fields (numeric)
  for tf in ("dimTimeUp", "dimTimeDown", "dimTimeUpAlt1", "dimTimeDownAlt1",
             "dimTimeUpAlt2", "dimTimeDownAlt2"):
      raw_tf = get(f"output.{tf}")
      if raw_tf is not None and str(raw_tf).strip() not in ("-", ""):
          try:
              exp_tf = int(raw_tf)
          except (ValueError, TypeError):
              continue
          actual_tf = o.get(tf.replace("dim_time_", "dim_time_").replace("T", "_t")
                              .lower().replace("alt", "_alt"))
          # Note: entity_mapping uses underscore key, stored config uses camelCase
          # The audit checks entity_mapping values, so use underscore keys:
          map_key = "dim_time_" + tf[7].lower() + tf[8:]  # e.g. dimTimeUp -> dim_time_up
          # Simpler: just use the known mapping
          ...
  ```

  *Note: The dim_time fields in entity_mapping use snake_case (`dim_time_up`) while the stored
  config uses camelCase. The audit checks entity_mapping, so use the `_sub(e, "output")` pattern
  with snake_case keys. Add a helper for the key mapping.*

  Concrete implementation:
  ```python
  _DIM_FIELDS = [
      ("output.dimTimeUp",       "dim_time_up"),
      ("output.dimTimeDown",     "dim_time_down"),
      ("output.dimTimeUpAlt1",   "dim_time_up_alt1"),
      ("output.dimTimeDownAlt1", "dim_time_down_alt1"),
      ("output.dimTimeUpAlt2",   "dim_time_up_alt2"),
      ("output.dimTimeDownAlt2", "dim_time_down_alt2"),
  ]
  for col, key in _DIM_FIELDS:
      raw = get(col)
      if raw is not None and str(raw).strip() not in ("-", ""):
          try:
              exp = int(raw)
          except (ValueError, TypeError):
              continue
          actual = o.get(key)
          if actual is not None and actual != exp:
              _dis(domain, dc, "output", key, exp, actual)
  ```

- [ ] Run audit:
  ```
  .venv/bin/python tools/audit_mapping.py
  ```
  Expected: ✓ All checked fields match.

- [ ] Run tests:
  ```
  .venv/bin/python -m pytest tests/ -q
  ```

- [ ] Commit:
  ```bash
  git add tools/audit_mapping.py
  git commit -m "feat: audit new heating_system and dimmer-timing fields in audit_mapping.py"
  ```

---

## Task 5: Config flow — expose new fields in from-scratch output step

**Files:** `config_flow.py`

Context: `async_step_output_optional` is the from-scratch path that lets the user configure
optional output properties after choosing function/usage/mode. It already handles
`placement_choice` and timing fields for POSITIONAL outputs.

- [ ] Import `HeatingSystemCapability`, `HeatingSystemType` at top of `config_flow.py`

- [ ] In `async_step_output_optional()`, after existing timing-field blocks, add:
  ```python
  # Dim timing (relevant for DIMMER / DIMMER_COLOR_TEMP / FULL_COLOR_DIMMER outputs)
  fn = self._current_output.get("function", 0) if self._current_output else 0
  is_dimmer = fn in (
      OutputFunction.DIMMER.value,
      OutputFunction.DIMMER_COLOR_TEMP.value,
      OutputFunction.FULL_COLOR_DIMMER.value,
  )
  if is_dimmer:
      # dS 8-bit format: values 0-255 (compact encoding, NOT milliseconds)
      _ns_ds8 = selector.NumberSelectorConfig(min=0, max=255, step=1, mode="box")
      schema_dict[vol.Optional("dimTimeUp")]        = selector.NumberSelector(_ns_ds8)
      schema_dict[vol.Optional("dimTimeDown")]      = selector.NumberSelector(_ns_ds8)
      schema_dict[vol.Optional("dimTimeUpAlt1")]    = selector.NumberSelector(_ns_ds8)
      schema_dict[vol.Optional("dimTimeDownAlt1")]  = selector.NumberSelector(_ns_ds8)
      schema_dict[vol.Optional("dimTimeUpAlt2")]    = selector.NumberSelector(_ns_ds8)
      schema_dict[vol.Optional("dimTimeDownAlt2")]  = selector.NumberSelector(_ns_ds8)

  # Heating system parameters (relevant for HVAC/heating actuator outputs)
  schema_dict[vol.Optional("activeCoolingMode")] = selector.BooleanSelector()
  schema_dict[vol.Optional("heatingSystemCapability")] = selector.SelectSelector(
      selector.SelectSelectorConfig(options=[
          selector.SelectOptionDict(value="", label="(not specified)"),
          *[selector.SelectOptionDict(value=str(m.value), label=m.name)
            for m in HeatingSystemCapability],
      ])
  )
  schema_dict[vol.Optional("heatingSystemType")] = selector.SelectSelector(
      selector.SelectSelectorConfig(options=[
          selector.SelectOptionDict(value="", label="(not specified)"),
          *[selector.SelectOptionDict(value=str(m.value), label=m.name)
            for m in HeatingSystemType],
      ])
  )
  ```

- [ ] In `async_step_output_optional()`, when `user_input is not None`, collect new values:
  ```python
  # dim_time values are dS 8-bit format ints (0-255), not milliseconds
  for k in ("dimTimeUp", "dimTimeDown", "dimTimeUpAlt1", "dimTimeDownAlt1",
            "dimTimeUpAlt2", "dimTimeDownAlt2"):
      if k in user_input and user_input[k] is not None:
          self._current_output[k] = int(user_input[k])

  if user_input.get("activeCoolingMode"):
      self._current_output["activeCoolingMode"] = True

  cap = user_input.get("heatingSystemCapability")
  if cap:
      self._current_output["heatingSystemCapability"] = int(cap)

  htype = user_input.get("heatingSystemType")
  if htype:
      self._current_output["heatingSystemType"] = int(htype)
  ```

- [ ] Run tests:
  ```
  .venv/bin/python -m pytest tests/test_config_flow.py -v
  ```

- [ ] Commit:
  ```bash
  git add custom_components/dsvdc4ha/config_flow.py
  git commit -m "feat: add dim_time and heating_system fields to from-scratch output optional step"
  ```

---

## Task 6: Tests for api.py new output parameters

**Files:** `tests/test_api.py`

- [ ] Add test: new Output params are passed when present in config data:
  ```python
  def test_add_output_passes_heating_system_params():
      vdsd = _make_vdsd()
      data = _minimal_output_data()
      data["heatingSystemCapability"] = 3  # HEATING_AND_COOLING
      data["heatingSystemType"] = 1        # FLOOR_HEATING
      data["activeCoolingMode"] = True
      _add_output(vdsd, data)
      assert vdsd.output is not None
      from pydsvdcapi.enums import HeatingSystemCapability, HeatingSystemType
      assert vdsd.output.heating_system_capability == HeatingSystemCapability.HEATING_AND_COOLING
      assert vdsd.output.heating_system_type == HeatingSystemType.FLOOR_HEATING
      assert vdsd.output.active_cooling_mode is True

  def test_add_output_passes_dim_times():
      vdsd = _make_vdsd()
      data = _minimal_output_data()
      data["dimTimeUp"] = 400
      data["dimTimeDown"] = 600
      _add_output(vdsd, data)
      assert vdsd.output.dim_time_up == 400
      assert vdsd.output.dim_time_down == 600

  def test_add_output_wires_channel_converters():
      vdsd = _make_vdsd()
      data = _minimal_output_data()
      data["channels"][0]["uplinkConverter"] = "value = value * 100.0 / 255.0"
      data["channels"][0]["downlinkConverter"] = "value = int(round(value * 255.0 / 100.0))"
      _add_output(vdsd, data)
      ch = vdsd.output.channels[0]
      assert ch.uplink_converter_code == "value = value * 100.0 / 255.0"
      assert ch.downlink_converter_code == "value = int(round(value * 255.0 / 100.0))"
  ```

- [ ] Run:
  ```
  .venv/bin/python -m pytest tests/test_api.py -v -k "output"
  ```
  Expected: PASS

- [ ] Commit:
  ```bash
  git add tests/test_api.py
  git commit -m "test: add coverage for pydsvdcapi 0.8.9 new Output params and channel converters"
  ```

---

## Task 7: Regenerate Excel file

- [ ] Run generate_mapping_excel.py:
  ```
  .venv/bin/python tools/generate_mapping_excel.py
  ```

- [ ] Run audit to verify 0 discrepancies:
  ```
  .venv/bin/python tools/audit_mapping.py
  ```
  Expected: ✓ All checked fields match.

- [ ] Commit the new Excel:
  ```bash
  git add documents/ha_vdsd_mapping.xlsx
  git commit -m "chore: regenerate mapping Excel with pydsvdcapi 0.8.9 new columns"
  ```

---

## Task 8: Final check

- [ ] Run full test suite:
  ```
  .venv/bin/python -m pytest tests/ -q
  ```
  Expected: all tests pass, 0 failures

- [ ] Verify tests for new icon work:
  ```
  .venv/bin/python -m pytest tests/ -v -k "icon"
  ```

---

## Out of Scope (future work)

- FCU entity_mapping entry (FCU_OPERATION_MODE channel, active_cooling_mode=True, 
  heating_system_capability=HEATING_AND_COOLING) — significant new feature, separate PR
- Vdsd `prog_mode`, `current_config_id`, `configurations` — device management, not output/channel
- Device states/properties/events/actions — SingleDevice spec extensions
- `dim_time_*` in "from entity" light flow — low priority, only relevant for advanced tuning
