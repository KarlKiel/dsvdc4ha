# Directly Use pydsvdcapi Enums Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every raw integer literal in `entity_mapping.py` with the corresponding `pydsvdcapi` enum member (or named constant), so future pydsvdcapi enum changes are automatically reflected and invalid values produce import-time errors.

**Architecture:** `entity_mapping.py` is the single definition point for all dS protocol values. It imports pydsvdcapi enums directly and uses enum members (IntEnum, so backward-compatible with all code that reads integer values). `config_flow.py` retains its own enum-derived label dicts but drops hardcoded duplicate literals. A new validation test guards the contract.

**Tech Stack:** Python, pydsvdcapi 0.8.4 (enums.py + binary_input.py), pytest

---

## Field → Enum Reference Table

Use this table for every replacement. Deviations (e.g. JOKER=0 in SensorGroup vs JOKER=8 in BinaryInputGroup) are annotated.

| Component | Field | Enum / Constant | Notes |
|-----------|-------|-----------------|-------|
| vdSD | `primary_group` | `ColorGroup` | Only values 1–9; use BLUE (3) for all climate sub-types |
| `binary_input` | `sensor_function` | `BinaryInputType` | |
| `binary_input` | `group` | `BinaryInputGroup` | JOKER = **8** here |
| `binary_input` | `input_usage` | `BinaryInputUsage` | Only 4 members: UNDEFINED=0, ROOM_CLIMATE=1, OUTDOOR_CLIMATE=2, CLIMATE_SETTING=3 |
| `binary_input` | `input_type` | `INPUT_TYPE_DETECTS_CHANGES` | Plain int constant from `pydsvdcapi.binary_input`; value=1. Not an enum. |
| `sensor` | `sensor_type` | `SensorType` | |
| `sensor` | `sensor_usage` | `SensorUsage` | |
| `sensor` | `group` | `SensorGroup` | JOKER = **0** here (different from BinaryInputGroup!) |
| `output` | `function` | `OutputFunction` | |
| `output` | `output_usage` | `OutputUsage` | |
| `output` | `mode` | `OutputMode` | Auto-derived by pydsvdcapi from function if omitted; kept explicit here |
| `output` | `default_group` | `ColorClass` | Any value valid, including ≥ 64 (AWNINGS=65, APARTMENT_VENTILATION=64, APARTMENT_RECIRCULATION=69) |
| `output` | `active_group` | `ColorClass` | If value < 64, must also appear in `groups`; values ≥ 64 exempt |
| `output` | `groups` | `ColorClass` | **Values 1–63 only** — global app groups (≥ 64) are forbidden here |
| `output` | `channels[n].channel_type` | `OutputChannelType` | |
| `button` | `button_type` | `ButtonType` | |
| `button` | `group` | `ButtonGroup` | JOKER = **8** here |
| `button` | `function` | `ButtonFunction` (non-JOKER) or `ButtonFunctionJoker` (JOKER) | All current button entries use JOKER group → use `ButtonFunctionJoker` |
| `button` | `mode` | `ButtonMode` | |

**Do NOT use `ColorGroup` for output fields** (`default_group`, `active_group`, `groups`) — those use `ColorClass`. The two enums have overlapping integer values (e.g. BLACK=8 in ColorGroup, JOKER=8 in ColorClass) but different semantics.

---

## File Structure

- **Modify:** `custom_components/dsvdc4ha/entity_mapping.py` — add imports, replace integers, update choice tuples, derive `_CHANNEL_TYPE_NAMES` from enum
- **Modify:** `custom_components/dsvdc4ha/config_flow.py` — fix `_compute_auto_features` comparison, remove dead "any" sensor_usage blocks
- **Modify:** `tests/test_entity_mapping_bindings.py` — add enum validation test

---

## Task 1: Fix three invalid `input_usage` values

> **Already completed** on branch `directly-use-pydsvdcapi-instead-of-redefining-enums`:
> - `binary_sensor/moisture`: `input_usage: 6` → `0`
> - `binary_sensor/problem`: `input_usage: 4` → `0`
> - `binary_sensor/running`: `input_usage: 4` → `0`
>
> All three are now `BinaryInputUsage.UNDEFINED = 0`.

---

## Task 2: Add pydsvdcapi enum imports and derive `_CHANNEL_TYPE_NAMES` from enum

**Files:**
- Modify: `custom_components/dsvdc4ha/entity_mapping.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_entity_mapping_bindings.py`, add:

```python
def test_channel_type_names_matches_enum():
    from pydsvdcapi.enums import OutputChannelType
    import importlib.util, pathlib, sys
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/arne/Development/dsvdc4ha
.venv/bin/pytest tests/test_entity_mapping_bindings.py::test_channel_type_names_matches_enum -v
```

Expected: FAIL — current `_CHANNEL_TYPE_NAMES` omits several `OutputChannelType` members (e.g. TRANSPARENCY=11, AIR_LOUVER_POSITION=15, etc.)

- [ ] **Step 3: Replace the import block and `_CHANNEL_TYPE_NAMES` in entity_mapping.py**

Replace the existing header comment and dict at lines 1–27 with:

```python
"""Static mapping from HA entity types / device_classes to dS vdSD configuration."""
from __future__ import annotations

from typing import Any

from pydsvdcapi.enums import (
    BinaryInputGroup,
    BinaryInputType,
    BinaryInputUsage,
    ButtonFunction,
    ButtonFunctionJoker,
    ButtonGroup,
    ButtonMode,
    ButtonType,
    ColorClass,
    ColorGroup,
    OutputChannelType,
    OutputFunction,
    OutputMode,
    OutputUsage,
    SensorGroup,
    SensorType,
    SensorUsage,
)
from pydsvdcapi.binary_input import INPUT_TYPE_DETECTS_CHANGES

# ---------------------------------------------------------------------------
# Channel type name → OutputChannelType integer (derived from pydsvdcapi enum)
# ---------------------------------------------------------------------------
_CHANNEL_TYPE_NAMES: dict[str, int] = {m.name: m.value for m in OutputChannelType}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/pytest tests/test_entity_mapping_bindings.py::test_channel_type_names_matches_enum -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/entity_mapping.py tests/test_entity_mapping_bindings.py
git commit -m "feat: add pydsvdcapi enum imports and derive _CHANNEL_TYPE_NAMES from OutputChannelType"
```

---

## Task 3: Replace choice tuple integers with enum `.value` references

**Files:**
- Modify: `custom_components/dsvdc4ha/entity_mapping.py`

The reusable choice lists `_BI_GROUP_ALL`, `_BI_GROUP_MOISTURE`, `_BTN_GROUP_CHOICES`, `_SU_ROOM_OUTDOOR`, `_SU_DEVICE_LEVEL`, `_SU_GENERAL` use raw integers. Additionally, two inline `sensor_usage_choices` lists at the `distance` and `duration` entries use wrong labels ("Device Level Individual", "Device Level All" instead of "Device Last Run", "Device Average") and must be replaced with `_SU_DEVICE_LEVEL`.

- [ ] **Step 1: Write the failing test**

```python
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
        for v, lbl in sen.get("sensor_usage_choices", []):
            if isinstance(lbl, str):
                for bad in wrong_labels:
                    assert bad not in lbl, f"Wrong label in sensor_usage_choices: {lbl!r}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_entity_mapping_bindings.py::test_choice_tuples_use_valid_enum_values -v
```

Expected: FAIL — wrong labels in inline choices for `distance` and `duration` entries.

- [ ] **Step 3: Update choice tuple definitions**

Replace the choice list block (currently lines 30–52 after the import block shifts) with:

```python
# Reusable choice lists for binary_input.group_choices
_BI_GROUP_ALL: list[tuple[int, str]] = [
    (BinaryInputGroup.LIGHT.value,    "Light (1)"),
    (BinaryInputGroup.SHADOW.value,   "Shadow (2)"),
    (BinaryInputGroup.CLIMATE.value,  "Climate (3)"),
    (BinaryInputGroup.AUDIO.value,    "Audio (4)"),
    (BinaryInputGroup.VIDEO.value,    "Video (5)"),
    (BinaryInputGroup.SECURITY.value, "Security (6)"),
    (BinaryInputGroup.ACCESS.value,   "Access (7)"),
    (BinaryInputGroup.JOKER.value,    "Joker (8)"),
]
_BI_GROUP_MOISTURE: list[tuple[int, str]] = [
    (BinaryInputGroup.SECURITY.value, "Security (6)"),
    (BinaryInputGroup.CLIMATE.value,  "Climate (3)"),
    (BinaryInputGroup.JOKER.value,    "Joker (8)"),
]
# Reusable choice list for button.group_choices (Joker first = default pre-selection)
_BTN_GROUP_CHOICES: list[tuple[int, str]] = [
    (ButtonGroup.JOKER.value,  "Joker — App (8)"),
    (ButtonGroup.LIGHT.value,  "Yellow — Light / Room (1)"),
]
# Reusable choice lists for sensor.sensor_usage_choices
_SU_ROOM_OUTDOOR: list[tuple[int, str]] = [
    (SensorUsage.ROOM.value,    "Room (1)"),
    (SensorUsage.OUTDOOR.value, "Outdoor (2)"),
]
_SU_DEVICE_LEVEL: list[tuple[int, str]] = [
    (SensorUsage.DEVICE_LEVEL.value,    "Device Level (4)"),
    (SensorUsage.DEVICE_LAST_RUN.value, "Device Last Run (5)"),
    (SensorUsage.DEVICE_AVERAGE.value,  "Device Average (6)"),
]
_SU_GENERAL: list[tuple[int, str]] = [
    (SensorUsage.UNDEFINED.value,       "Undefined (0)"),
    (SensorUsage.ROOM.value,            "Room (1)"),
    (SensorUsage.OUTDOOR.value,         "Outdoor (2)"),
    (SensorUsage.DEVICE_LEVEL.value,    "Device Level (4)"),
    (SensorUsage.DEVICE_LAST_RUN.value, "Device Last Run (5)"),
    (SensorUsage.DEVICE_AVERAGE.value,  "Device Average (6)"),
]
```

Then find the two inline choices with wrong labels (search for `"Device Level Individual"`):
- In the `distance` sensor entry, replace:
  ```python
  "sensor_usage_choices": [(4, "Device Level (4)"), (5, "Device Level Individual (5)"), (6, "Device Level All (6)")],
  ```
  with:
  ```python
  "sensor_usage_choices": _SU_DEVICE_LEVEL,
  ```
- In the `duration` sensor entry, same replacement.

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/pytest tests/test_entity_mapping_bindings.py::test_choice_tuples_use_valid_enum_values -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/entity_mapping.py tests/test_entity_mapping_bindings.py
git commit -m "feat: replace choice tuple raw integers with enum .value references and fix wrong sensor_usage labels"
```

---

## Task 4: Replace all raw integer field values in ENTITY_MAPPING with enum members

**Files:**
- Modify: `custom_components/dsvdc4ha/entity_mapping.py`

This is the core replacement. Each integer field in every ENTITY_MAPPING entry must use an enum member.
Since `BinaryInputType`, `SensorType` etc. are `IntEnum`, the stored values remain integers at runtime — all existing code that reads them is unaffected.

- [ ] **Step 1: Write the failing validation test**

Add to `tests/test_entity_mapping_bindings.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_entity_mapping_bindings.py::test_all_enum_fields_are_valid_enum_members -v
```

Expected: PASS already (all values are now valid after Task 1 fixes), but this test will become the regression guard. If it passes now, mark it as baseline and continue to Task 4 Step 3.

- [ ] **Step 3: Replace raw integers in ENTITY_MAPPING**

Work through `entity_mapping.py` systematically by component type. Use search-and-replace guided by the Field → Enum table at the top of this plan.

**`primary_group` pattern:**
```python
# Before:
"primary_group": 1,
# After:
"primary_group": ColorGroup.YELLOW,

# Before:
"primary_group": 2,
# After:
"primary_group": ColorGroup.GREY,

# Before:
"primary_group": 3,
# After:
"primary_group": ColorGroup.BLUE,

# Before:
"primary_group": 7,
# After:
"primary_group": ColorGroup.GREEN,   # deprecated but still needed

# Before:
"primary_group": 8,
# After:
"primary_group": ColorGroup.BLACK,
```

**`binary_input` fields:**
```python
# sensor_function (BinaryInputType):
0  → BinaryInputType.GENERIC
1  → BinaryInputType.PRESENCE
2  → BinaryInputType.BRIGHTNESS
5  → BinaryInputType.MOTION
7  → BinaryInputType.SMOKE
11 → BinaryInputType.THERMOSTAT
12 → BinaryInputType.BATTERY_LOW
13 → BinaryInputType.WINDOW_OPEN
14 → BinaryInputType.DOOR_OPEN
16 → BinaryInputType.GARAGE_DOOR_OPEN
18 → BinaryInputType.FROST
22 → BinaryInputType.MALFUNCTION
23 → BinaryInputType.SERVICE

# group (BinaryInputGroup):
1 → BinaryInputGroup.LIGHT
3 → BinaryInputGroup.CLIMATE
6 → BinaryInputGroup.SECURITY
7 → BinaryInputGroup.ACCESS
8 → BinaryInputGroup.JOKER

# input_usage (BinaryInputUsage):
0 → BinaryInputUsage.UNDEFINED
1 → BinaryInputUsage.ROOM_CLIMATE
2 → BinaryInputUsage.OUTDOOR_CLIMATE

# input_type:
1 → INPUT_TYPE_DETECTS_CHANGES
```

**`sensor` fields:**
```python
# sensor_type (SensorType):
0  → SensorType.NONE
1  → SensorType.TEMPERATURE
2  → SensorType.HUMIDITY
3  → SensorType.ILLUMINATION
4  → SensorType.SUPPLY_VOLTAGE
5  → SensorType.CO_CONCENTRATION
8  → SensorType.PARTICLES_PM10
9  → SensorType.PARTICLES_PM2_5
10 → SensorType.PARTICLES_PM1
13 → SensorType.WIND_SPEED
14 → SensorType.ACTIVE_POWER
15 → SensorType.ELECTRIC_CURRENT
16 → SensorType.ENERGY_METER
17 → SensorType.APPARENT_POWER
18 → SensorType.AIR_PRESSURE
20 → SensorType.SOUND_PRESSURE_LEVEL
21 → SensorType.PRECIPITATION
22 → SensorType.CO2_CONCENTRATION
27 → SensorType.WATER_QUANTITY
29 → SensorType.LENGTH
30 → SensorType.MASS
31 → SensorType.DURATION
32 → SensorType.PERCENT
34 → SensorType.FREQUENCY

# sensor_usage (SensorUsage):
0 → SensorUsage.UNDEFINED
1 → SensorUsage.ROOM
2 → SensorUsage.OUTDOOR
4 → SensorUsage.DEVICE_LEVEL

# group (SensorGroup) — JOKER=0, not 8!
0 → SensorGroup.JOKER
```

**`output` fields:**
```python
# function (OutputFunction):
0   → OutputFunction.ON_OFF
1   → OutputFunction.DIMMER
2   → OutputFunction.POSITIONAL
3   → OutputFunction.DIMMER_COLOR_TEMP
4   → OutputFunction.FULL_COLOR_DIMMER
127 → OutputFunction.CUSTOM

# output_usage (OutputUsage):
1 → OutputUsage.ROOM
2 → OutputUsage.OUTDOORS

# mode (OutputMode):
1 → OutputMode.BINARY
2 → OutputMode.GRADUAL

# default_group (ColorClass) — NOT ColorGroup:
1  → ColorClass.LIGHTS
2  → ColorClass.BLINDS
3  → ColorClass.HEATING
7  → ColorClass.ACCESS
8  → ColorClass.JOKER
10 → ColorClass.VENTILATION
11 → ColorClass.WINDOW
65 → ColorClass.AWNINGS    # valid for default_group (informational); NOT valid in groups

# channels[n].channel_type (OutputChannelType):
1  → OutputChannelType.BRIGHTNESS
2  → OutputChannelType.HUE
3  → OutputChannelType.SATURATION
4  → OutputChannelType.COLOR_TEMPERATURE
5  → OutputChannelType.CIE_X
6  → OutputChannelType.CIE_Y
7  → OutputChannelType.SHADE_POSITION_OUTSIDE
8  → OutputChannelType.SHADE_POSITION_INDOOR
9  → OutputChannelType.SHADE_OPENING_ANGLE_OUTSIDE
10 → OutputChannelType.SHADE_OPENING_ANGLE_INDOOR
12 → OutputChannelType.AIR_FLOW_INTENSITY
13 → OutputChannelType.AIR_FLOW_DIRECTION
14 → OutputChannelType.AIR_FLAP_POSITION
18 → OutputChannelType.AUDIO_VOLUME
19 → OutputChannelType.POWER_STATE
23 → OutputChannelType.WATER_FLOW_RATE
24 → OutputChannelType.POWER_LEVEL
```

**`button` fields:**
```python
# button_type (ButtonType):
1 → ButtonType.SINGLE_PUSHBUTTON

# group (ButtonGroup):
8 → ButtonGroup.JOKER

# function — all current buttons have group=JOKER=8 → use ButtonFunctionJoker:
5  → ButtonFunctionJoker.DOOR_BELL
15 → ButtonFunctionJoker.APP

# mode (ButtonMode):
0 → ButtonMode.STANDARD
```

- [ ] **Step 4: Run validation test**

```bash
.venv/bin/pytest tests/test_entity_mapping_bindings.py::test_all_enum_fields_are_valid_enum_members -v
```

Expected: PASS. Also run the full test suite:

```bash
.venv/bin/pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/entity_mapping.py
git commit -m "feat: replace all raw integers in ENTITY_MAPPING with pydsvdcapi enum members"
```

---

## Task 5: Fix config_flow.py — remove dead "any" blocks and fix JOKER comparison

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py`

**Problem 1:** `_compute_auto_features` uses a hardcoded `grp != 8` to detect the Joker/Black button group. Should use `ButtonGroup.JOKER`.

**Problem 2:** Two places in `config_flow.py` (both the new-device and edit-device flows) check `suc == "any"` twice in a row for `sensor_usage`. The first block uses a hardcoded list with wrong labels ("Device Level Individual", "Device Level All"). The second block overrides it with `_SENSOR_USAGE_OPTIONS`. The first block is dead code and must be removed.

Locations (approximate line numbers — verify in file before editing):
- New-device flow: first dead `suc == "any"` block around line 1070–1082
- Edit-device flow: first dead `suc == "any"` block around line 1475–1487

- [ ] **Step 1: Write the failing test**

```python
def test_compute_auto_features_uses_enum_for_joker():
    """_compute_auto_features must use ButtonGroup.JOKER, not a hardcoded 8."""
    import ast, pathlib
    src = (pathlib.Path(__file__).parent.parent / "custom_components/dsvdc4ha/config_flow.py").read_text()
    tree = ast.parse(src)
    # Find all Compare nodes: look for literal 8 compared to 'grp'
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for comp in node.comparators:
                if isinstance(comp, ast.Constant) and comp.value == 8:
                    # Check if left side is 'grp'
                    if isinstance(node.left, ast.Name) and node.left.id == "grp":
                        raise AssertionError(
                            f"Line {node.lineno}: hardcoded 8 in grp comparison — use ButtonGroup.JOKER"
                        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_entity_mapping_bindings.py::test_compute_auto_features_uses_enum_for_joker -v
```

Expected: FAIL — hardcoded `grp != 8` found.

- [ ] **Step 3: Fix `_compute_auto_features`**

In `config_flow.py`, find (approximately line 544):
```python
grp = int(btn.get("group", 1))
if grp != 8:
```

Replace with:
```python
grp = int(btn.get("group", ButtonGroup.LIGHT))
if grp != ButtonGroup.JOKER:
```

`ButtonGroup` is already imported in config_flow.py (line 31).

- [ ] **Step 4: Remove dead "any" sensor_usage blocks**

Locate and remove the first `if suc == "any":` block in each flow (the one with the hardcoded wrong-label list). The second block (using `_SENSOR_USAGE_OPTIONS`) is correct and must stay.

In the **new-device flow**, remove the block that looks like:
```python
suc = sen.get("sensor_usage_choices")
if suc == "any":
    schema_dict[vol.Required("sensor_usage", default=str(sen["sensor_usage"]))] = (
        selector.SelectSelector(selector.SelectSelectorConfig(options=[
            selector.SelectOptionDict(value=str(v), label=lbl)
            for v, lbl in [
                (0, "Generic (0)"),
                (1, "Room (1)"),
                (2, "Outdoor (2)"),
                (4, "Device Level (4)"),
                (5, "Device Level Individual (5)"),
                (6, "Device Level All (6)"),
            ]
        ]))
    )
elif suc:
    schema_dict[vol.Required("sensor_usage", default=str(sen["sensor_usage"]))] = (
        selector.SelectSelector(selector.SelectSelectorConfig(options=[
            selector.SelectOptionDict(value=str(v), label=lbl)
            for v, lbl in suc
        ]))
    )
```

The `elif suc:` branch here handles explicit choice lists — keep only that branch, remove the `if suc == "any":` part. The second suc-check block already handles "any" correctly with `_SENSOR_USAGE_OPTIONS`.

Do the same for the identical block in the edit-device flow.

- [ ] **Step 5: Run tests**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all tests pass (including the new `test_compute_auto_features_uses_enum_for_joker`).

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py tests/test_entity_mapping_bindings.py
git commit -m "fix: replace hardcoded JOKER=8 with ButtonGroup.JOKER and remove dead sensor_usage expansion code"
```

---

## Self-Review

**Spec coverage:**
- ✅ All ENTITY_MAPPING integers replaced with enum members (Task 4)
- ✅ `_CHANNEL_TYPE_NAMES` derived from `OutputChannelType` enum — auto-updates with enum changes (Task 2)
- ✅ Choice tuples use `.value` references — labels consistent with enum names (Task 3)
- ✅ `config_flow.py` JOKER comparison uses enum (Task 5)
- ✅ Dead code with wrong labels removed (Task 5)
- ✅ Validation test guards all enum field values (Task 4)

**Edge cases documented:**
- `SensorGroup.JOKER = 0` (not 8) — distinct from `BinaryInputGroup.JOKER = 8` and `ButtonGroup.JOKER = 8`
- `output.default_group` uses `ColorClass` (not `ColorGroup`); values ≥ 64 are valid here
- `output.groups` uses `ColorClass` values **1–63 only**
- `input_type` is a plain int constant, not an enum member
- All current button entries have `group=JOKER`, so all use `ButtonFunctionJoker`; if a non-JOKER button entry is added later, it must use `ButtonFunction` instead

**Placeholder scan:** None found.

**Type consistency:** All tasks reference `ButtonFunctionJoker` consistently for button entries. Enum member names match between task 4's replacement table and the enum values listed in the reference table.
