# Excel USER Field Gap Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every field marked USER in the Excel mapping `ha_vdsd_mapping.xlsx` shows a selection UI during entity/device creation, with the Excel-specified default pre-selected.

**Architecture:** Changes flow through three layers: (1) `entity_mapping.py` stores choice metadata alongside defaults, (2) `config_flow.py` reads that metadata to build form selectors in both entity and device user-input steps, and (3) `device_grouper.py` reads user_choices in `resolve_vdsd_plan` to apply them. Tests cover mapping correctness and resolve_vdsd_plan propagation.

**Tech Stack:** Python, Home Assistant config flow selectors, pytest.

---

## Background / Excel findings

Running the Excel (col 116 = `binarySettings.group`, col 117 = `sensorFunction (setting)`, col 125 = `sensorUsage`) against the codebase reveals three categories of gaps:

### Category A — Binary sensor `bi_group` marked USER (now hardcoded)
| domain / device_class | Excel bi_group | Notes |
|---|---|---|
| binary_sensor / carbon_monoxide | USER — default: SECURITY (6) | needs full BinaryInputGroup choices |
| binary_sensor / cold | USER — default: CLIMATE (3) | needs full BinaryInputGroup choices |
| binary_sensor / gas | USER — default: SECURITY (6) | |
| binary_sensor / heat | USER — default: CLIMATE (3) | |
| binary_sensor / light | USER — default: LIGHT (1) | |
| binary_sensor / moisture | USER — limited: SECURITY(6), CLIMATE(3), JOKER(8) | |
| binary_sensor / motion | USER — default: LIGHT (1) | |
| binary_sensor / opening | USER — default: JOKER (8) | |
| binary_sensor / sound | USER — default: JOKER (8) | |
| event / motion | USER — default: LIGHT (1) | (maps to binary_input) |

### Category B — Binary sensor `sensor_function` marked USER (missing or wrong)
| domain / device_class | Excel sensorFunction | Notes |
|---|---|---|
| binary_sensor / None | USER — default: APP_Mode (0) | needs full enum choices |
| binary_sensor / moving | USER — default: MOTION (5) | currently hardcoded to 0 (wrong!) |

### Category C — Sensor `sensorUsage` marked USER (no selector exists at all)
| domain / device_class | Excel sensorUsage options | Default (from current mapping) |
|---|---|---|
| sensor / None | USER — full SensorUsage enum | 0 (UNDEFINED) |
| sensor / aqi | USER: ROOM(1), OUTDOOR(2) | 1 (ROOM) |
| sensor / distance | USER: DEVICE_LEVEL(4,5,6) | 4 |
| sensor / duration | USER: DEVICE_LEVEL(4,5,6) | 4 |
| sensor / gas | USER: UNDEFINED(0),ROOM(1),OUTDOOR(2),DEVICE_LEVEL(4,5,6) | 0 |
| sensor / humidity | same as gas | 0 |
| sensor / illuminance | same as gas | 0 |
| sensor / moisture | same as gas | 0 |
| sensor / speed | same as gas | 0 |
| sensor / temperature | same as gas | 0 |

---

## File map

| File | What changes |
|---|---|
| `custom_components/dsvdc4ha/entity_mapping.py` | Add `group_choices`, `sensor_function_choices`, `sensor_usage_choices` keys; fix moving default; add `sensor_usage_choices` to `needs_user_input()` |
| `custom_components/dsvdc4ha/config_flow.py` | Add `bi.group_choices` + `sen.sensor_usage_choices` rendering to `async_step_entity_user_input` and `async_step_device_entity_user_input`; handle `"any"` sentinel for `sensor_function_choices`; apply `bi_group` + `sensor_usage` user input in `_build_entity_vdsd_and_continue` |
| `custom_components/dsvdc4ha/device_grouper.py` | Apply `choices.get("bi_group", bi["group"])` and `choices.get("sensor_usage", s["sensor_usage"])` in `resolve_vdsd_plan` |
| `tests/test_device_grouper.py` | Add resolve tests for bi_group and sensor_usage user choices |
| `tests/test_entity_mapping_bindings.py` | Add tests for needs_user_input on new choice types |

---

## Task 1: Update entity_mapping.py — add missing choice keys

**Files:**
- Modify: `custom_components/dsvdc4ha/entity_mapping.py`
- Test: `tests/test_entity_mapping_bindings.py`

### Helper constants to define at the TOP of the ENTITY_MAPPING list (after the existing `_CHANNEL_TYPE_NAMES` dict, before `ENTITY_MAPPING = [`):

```python
# Reusable choice lists for binary_input.group_choices
_BI_GROUP_ALL: list[tuple[int, str]] = [
    (1, "Light (1)"), (2, "Shadow (2)"), (3, "Climate (3)"),
    (4, "Audio (4)"), (5, "Video (5)"), (6, "Security (6)"),
    (7, "Access (7)"), (8, "Joker (8)"),
]
_BI_GROUP_MOISTURE: list[tuple[int, str]] = [
    (6, "Security (6)"), (3, "Climate (3)"), (8, "Joker (8)"),
]
# Reusable choice lists for sensor.sensor_usage_choices
_SU_ROOM_OUTDOOR: list[tuple[int, str]] = [
    (1, "Room (1)"), (2, "Outdoor (2)"),
]
_SU_DEVICE_LEVEL: list[tuple[int, str]] = [
    (4, "Device Level (4)"), (5, "Device Last Run (5)"), (6, "Device Average (6)"),
]
_SU_GENERAL: list[tuple[int, str]] = [
    (0, "Undefined (0)"), (1, "Room (1)"), (2, "Outdoor (2)"),
    (4, "Device Level (4)"), (5, "Device Last Run (5)"), (6, "Device Average (6)"),
]
```

- [ ] **Step 1: Write a failing test for the new choice keys**

In `tests/test_entity_mapping_bindings.py`, append:

```python
import pytest
from custom_components.dsvdc4ha.entity_mapping import (
    ENTITY_MAPPING, needs_user_input, get_entity_mapping,
)


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
    assert bi.get("sensor_function_choices") == "any"


# --- Category C: sensor_usage choices ---
@pytest.mark.parametrize("dc,expected_options_include", [
    ("aqi", [1, 2]),
    ("distance", [4, 5, 6]),
    ("duration", [4, 5, 6]),
    ("gas", [0, 1, 2, 4, 5, 6]),
    ("humidity", [0, 1, 2, 4, 5, 6]),
    ("illuminance", [0, 1, 2, 4, 5, 6]),
    ("moisture", [0, 1, 2, 4, 5, 6]),
    ("speed", [0, 1, 2, 4, 5, 6]),
    ("temperature", [0, 1, 2, 4, 5, 6]),
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
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd /home/arne/Development/dsvdc4ha && python -m pytest tests/test_entity_mapping_bindings.py -v 2>&1 | tail -30
```
Expected: multiple FAILED (KeyError or AssertionError on missing keys)

- [ ] **Step 3: Add helper constants to entity_mapping.py**

In `custom_components/dsvdc4ha/entity_mapping.py`, after the `_CHANNEL_TYPE_NAMES` dict (after line 27, before `# Mapping entries`), insert:

```python
# Reusable choice lists for binary_input.group_choices
_BI_GROUP_ALL: list[tuple[int, str]] = [
    (1, "Light (1)"), (2, "Shadow (2)"), (3, "Climate (3)"),
    (4, "Audio (4)"), (5, "Video (5)"), (6, "Security (6)"),
    (7, "Access (7)"), (8, "Joker (8)"),
]
_BI_GROUP_MOISTURE: list[tuple[int, str]] = [
    (6, "Security (6)"), (3, "Climate (3)"), (8, "Joker (8)"),
]
_SU_ROOM_OUTDOOR: list[tuple[int, str]] = [
    (1, "Room (1)"), (2, "Outdoor (2)"),
]
_SU_DEVICE_LEVEL: list[tuple[int, str]] = [
    (4, "Device Level (4)"), (5, "Device Last Run (5)"), (6, "Device Average (6)"),
]
_SU_GENERAL: list[tuple[int, str]] = [
    (0, "Undefined (0)"), (1, "Room (1)"), (2, "Outdoor (2)"),
    (4, "Device Level (4)"), (5, "Device Last Run (5)"), (6, "Device Average (6)"),
]
```

- [ ] **Step 4: Update binary_sensor/None entry (line 53)**

Change:
```python
    {
        "domain": "binary_sensor", "device_class": None, "primary_group": 8,
        "binary_input": {
            "sensor_function": 0, "group": 8, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```
To:
```python
    {
        "domain": "binary_sensor", "device_class": None, "primary_group": 8,
        "binary_input": {
            "sensor_function": 0,
            "sensor_function_choices": "any",
            "group": 8, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```

- [ ] **Step 5: Update binary_sensor/carbon_monoxide**

Change (currently `"group": 6`):
```python
    {
        "domain": "binary_sensor", "device_class": "carbon_monoxide", "primary_group": 8,
        "binary_input": {
            "sensor_function": 0, "group": 6, "input_usage": 1,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```
To:
```python
    {
        "domain": "binary_sensor", "device_class": "carbon_monoxide", "primary_group": 8,
        "binary_input": {
            "sensor_function": 0,
            "group": 6, "group_choices": _BI_GROUP_ALL, "input_usage": 1,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```

- [ ] **Step 6: Update binary_sensor/cold (add group_choices; sf_choices already present)**

Change:
```python
    {
        "domain": "binary_sensor", "device_class": "cold", "primary_group": 8,
        "binary_input": {
            "sensor_function": 18,
            "sensor_function_choices": [(18, "Frost (18)"), (0, "Generic (0)")],
            "group": 3, "input_usage": 2,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```
To:
```python
    {
        "domain": "binary_sensor", "device_class": "cold", "primary_group": 8,
        "binary_input": {
            "sensor_function": 18,
            "sensor_function_choices": [(18, "Frost (18)"), (0, "Generic (0)")],
            "group": 3, "group_choices": _BI_GROUP_ALL, "input_usage": 2,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```

- [ ] **Step 7: Update binary_sensor/gas**

Change (currently `"group": 6`):
```python
    {
        "domain": "binary_sensor", "device_class": "gas", "primary_group": 8,
        "binary_input": {
            "sensor_function": 0, "group": 6, "input_usage": 1,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```
To:
```python
    {
        "domain": "binary_sensor", "device_class": "gas", "primary_group": 8,
        "binary_input": {
            "sensor_function": 0,
            "group": 6, "group_choices": _BI_GROUP_ALL, "input_usage": 1,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```

- [ ] **Step 8: Update binary_sensor/heat**

Change (currently `"group": 3`):
```python
    {
        "domain": "binary_sensor", "device_class": "heat", "primary_group": 8,
        "binary_input": {
            "sensor_function": 11, "group": 3, "input_usage": 1,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```
To:
```python
    {
        "domain": "binary_sensor", "device_class": "heat", "primary_group": 8,
        "binary_input": {
            "sensor_function": 11,
            "group": 3, "group_choices": _BI_GROUP_ALL, "input_usage": 1,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```

- [ ] **Step 9: Update binary_sensor/light**

Change (currently `"group": 1`):
```python
    {
        "domain": "binary_sensor", "device_class": "light", "primary_group": 8,
        "binary_input": {
            "sensor_function": 2, "group": 1, "input_usage": 1,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```
To:
```python
    {
        "domain": "binary_sensor", "device_class": "light", "primary_group": 8,
        "binary_input": {
            "sensor_function": 2,
            "group": 1, "group_choices": _BI_GROUP_ALL, "input_usage": 1,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```

- [ ] **Step 10: Update binary_sensor/moisture (limited group choices, fix default to SECURITY)**

The Excel says `USER — SECURITY (6), CLIMATE (3) or JOKER (8)`. SECURITY(6) is listed first, which is the intended default (moisture = water leak → security context). The current mapping has `group=8` (JOKER) — this is a bug to fix.

Change:
```python
    {
        "domain": "binary_sensor", "device_class": "moisture", "primary_group": 8,
        "binary_input": {
            "sensor_function": 0, "group": 8, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```
To:
```python
    {
        "domain": "binary_sensor", "device_class": "moisture", "primary_group": 8,
        "binary_input": {
            "sensor_function": 0,
            "group": 6, "group_choices": _BI_GROUP_MOISTURE, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```

- [ ] **Step 11: Update binary_sensor/motion**

Change (currently `"group": 1`):
```python
    {
        "domain": "binary_sensor", "device_class": "motion", "primary_group": 8,
        "binary_input": {
            "sensor_function": 5, "group": 1, "input_usage": 1,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```
To:
```python
    {
        "domain": "binary_sensor", "device_class": "motion", "primary_group": 8,
        "binary_input": {
            "sensor_function": 5,
            "group": 1, "group_choices": _BI_GROUP_ALL, "input_usage": 1,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```

- [ ] **Step 12: Update binary_sensor/moving (fix sensor_function default + add sf_choices)**

Change (currently `"sensor_function": 0, "group": 8`):
```python
    {
        "domain": "binary_sensor", "device_class": "moving", "primary_group": 8,
        "binary_input": {
            "sensor_function": 0, "group": 8, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```
To:
```python
    {
        "domain": "binary_sensor", "device_class": "moving", "primary_group": 8,
        "binary_input": {
            "sensor_function": 5,
            "sensor_function_choices": "any",
            "group": 8, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```
(group stays 8/JOKER — Excel says `JOKER (8)` fixed, not USER)

- [ ] **Step 13: Update binary_sensor/opening**

Change (currently `"group": 8`):
```python
    {
        "domain": "binary_sensor", "device_class": "opening", "primary_group": 8,
        "binary_input": {
            "sensor_function": 0, "group": 8, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```
To:
```python
    {
        "domain": "binary_sensor", "device_class": "opening", "primary_group": 8,
        "binary_input": {
            "sensor_function": 0,
            "group": 8, "group_choices": _BI_GROUP_ALL, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```

- [ ] **Step 14: Update binary_sensor/sound**

Change (currently `"group": 8`):
```python
    {
        "domain": "binary_sensor", "device_class": "sound", "primary_group": 8,
        "binary_input": {
            "sensor_function": 0, "group": 8, "input_usage": 1,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```
To:
```python
    {
        "domain": "binary_sensor", "device_class": "sound", "primary_group": 8,
        "binary_input": {
            "sensor_function": 0,
            "group": 8, "group_choices": _BI_GROUP_ALL, "input_usage": 1,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```

- [ ] **Step 15: Update event/motion (maps to binary_input, needs group_choices)**

Change:
```python
    {
        "domain": "event", "device_class": "motion", "primary_group": 8,
        "binary_input": {
            "sensor_function": 5, "group": 1, "input_usage": 1,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```
To:
```python
    {
        "domain": "event", "device_class": "motion", "primary_group": 8,
        "binary_input": {
            "sensor_function": 5,
            "group": 1, "group_choices": _BI_GROUP_ALL, "input_usage": 1,
            "input_type": 1, "update_interval": 1.0,
        },
    },
```

- [ ] **Step 16: Update sensor/None (add sensor_usage_choices: "any")**

Change:
```python
    {
        "domain": "sensor", "device_class": None, "primary_group": 8,
        "sensor": {
            "sensor_type": 1,
            "sensor_type_choices": "any",  # full SensorType selector
            "sensor_usage": 0,
            "min": 0.0, "max": 100.0, "resolution": 0.1,
            "min_max_user": True,
            ...
        },
    },
```
To (add `"sensor_usage_choices": "any"` after `"sensor_usage": 0`):
```python
    {
        "domain": "sensor", "device_class": None, "primary_group": 8,
        "sensor": {
            "sensor_type": 1,
            "sensor_type_choices": "any",
            "sensor_usage": 0,
            "sensor_usage_choices": "any",
            "min": 0.0, "max": 100.0, "resolution": 0.1,
            "min_max_user": True,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
```

- [ ] **Step 17: Update sensor/aqi (sensor_usage_choices: limited room/outdoor)**

Change:
```python
    {
        "domain": "sensor", "device_class": "aqi", "primary_group": 8,
        "sensor": {
            "sensor_type": 0, "sensor_usage": 1,
            ...
        },
    },
```
To (add `"sensor_usage_choices": _SU_ROOM_OUTDOOR` after `"sensor_usage": 1`):
```python
    {
        "domain": "sensor", "device_class": "aqi", "primary_group": 8,
        "sensor": {
            "sensor_type": 0, "sensor_usage": 1,
            "sensor_usage_choices": _SU_ROOM_OUTDOOR,
            "min": 0.0, "max": 500.0, "resolution": 1.0,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
```

- [ ] **Step 18: Update sensor/distance and sensor/duration (device-level choices)**

For `distance`, change:
```python
    {
        "domain": "sensor", "device_class": "distance", "primary_group": 8,
        "sensor": {
            "sensor_type": 29, "sensor_usage": 4,
            ...
        },
    },
```
To:
```python
    {
        "domain": "sensor", "device_class": "distance", "primary_group": 8,
        "sensor": {
            "sensor_type": 29, "sensor_usage": 4,
            "sensor_usage_choices": _SU_DEVICE_LEVEL,
            "min": 0.0, "max": 1000.0, "resolution": 0.01,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
```

For `duration`, same change (sensor_usage=4, add `"sensor_usage_choices": _SU_DEVICE_LEVEL`).

- [ ] **Step 19: Update sensor/gas, humidity, illuminance, moisture, speed, temperature (general choices)**

For each of `gas`, `humidity`, `illuminance`, `moisture`, `speed`, `temperature`, add `"sensor_usage_choices": _SU_GENERAL` after the `sensor_usage` line. Example for `humidity`:

```python
    {
        "domain": "sensor", "device_class": "humidity", "primary_group": 8,
        "sensor": {
            "sensor_type": 2, "sensor_usage": 0,
            "sensor_usage_choices": _SU_GENERAL,
            "min": 0.0, "max": 100.0, "resolution": 0.5,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
```
Apply the same pattern for `gas` (sensor_usage=0), `illuminance` (sensor_usage=0), `moisture` (sensor_usage=0), `speed` (sensor_usage=0), `temperature` (sensor_usage=0).

- [ ] **Step 20: Add `sensor_usage_choices` check to `needs_user_input()`**

In `custom_components/dsvdc4ha/entity_mapping.py`, in the `needs_user_input()` function (currently around line 955), change:

```python
def needs_user_input(mapping: dict[str, Any]) -> bool:
    """Return True if this mapping entry requires extra user input beyond entity selection."""
    for component in ("binary_input", "sensor", "button", "output"):
        comp = mapping.get(component, {})
        if (
            comp.get("sensor_function_choices")
            or comp.get("group_choices")
            or comp.get("sensor_type_choices")
            or comp.get("output_usage_choices")
            or comp.get("function_choices")
            or comp.get("min_max_user")
            or comp.get("optional_tilt")
        ):
            return True
    return False
```
To:
```python
def needs_user_input(mapping: dict[str, Any]) -> bool:
    """Return True if this mapping entry requires extra user input beyond entity selection."""
    for component in ("binary_input", "sensor", "button", "output"):
        comp = mapping.get(component, {})
        if (
            comp.get("sensor_function_choices")
            or comp.get("group_choices")
            or comp.get("sensor_type_choices")
            or comp.get("sensor_usage_choices")
            or comp.get("output_usage_choices")
            or comp.get("function_choices")
            or comp.get("min_max_user")
            or comp.get("optional_tilt")
        ):
            return True
    return False
```

- [ ] **Step 21: Run tests**

```
cd /home/arne/Development/dsvdc4ha && python -m pytest tests/test_entity_mapping_bindings.py -v 2>&1 | tail -40
```
Expected: all tests PASS.

- [ ] **Step 22: Commit**

```bash
git add custom_components/dsvdc4ha/entity_mapping.py tests/test_entity_mapping_bindings.py
git commit -m "feat: add missing group/sensorFunction/sensorUsage choices to entity_mapping per Excel"
```

---

## Task 2: Update config_flow.py — schema builders and vdSD builder

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py`
- Test: `tests/test_config_flow.py`

### Context
There are three functions that need updating:

1. `async_step_entity_user_input` (around line 914) — entity flow form builder
2. `async_step_device_entity_user_input` (around line 1257) — device flow form builder
3. `_build_entity_vdsd_and_continue` (around line 993) — entity flow vdSD builder

Both form builders currently check `bi.get("sensor_function_choices")` as a list-of-tuples only. We need to add "any" sentinel handling. We also need to add `bi.group_choices` and `sen.sensor_usage_choices` blocks.

`_build_entity_vdsd_and_continue` currently hardcodes `"group": bi["group"]` and `"sensorUsage": s["sensor_usage"]` — both must read from `user_input`.

- [ ] **Step 1: Write failing tests for the config_flow changes**

In `tests/test_config_flow.py`, append:

```python
# ---------------------------------------------------------------------------
# entity user-input form — new choice types
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_entity_user_input_shows_bi_group_selector():
    """binary_sensor/motion mapping has group_choices → form must include bi_group field."""
    from custom_components.dsvdc4ha.entity_mapping import get_entity_mapping
    flow = VdsdSubentryFlowHandler()
    flow.hass = MagicMock()
    flow.hass.states.get.return_value = None
    flow._entity_mapping = get_entity_mapping("binary_sensor", "motion")
    flow._entity_id = "binary_sensor.test"
    flow._display_id = "Test"
    flow._vendor_name = "HA"
    flow._device_name = "Device"
    result = await flow.async_step_entity_user_input(user_input=None)
    assert result["type"] == FlowResultType.FORM
    assert "bi_group" in result["data_schema"].schema


@pytest.mark.asyncio
async def test_entity_user_input_shows_sensor_usage_selector():
    """sensor/temperature has sensor_usage_choices → form must include sensor_usage field."""
    from custom_components.dsvdc4ha.entity_mapping import get_entity_mapping
    flow = VdsdSubentryFlowHandler()
    flow.hass = MagicMock()
    flow.hass.states.get.return_value = None
    flow._entity_mapping = get_entity_mapping("sensor", "temperature")
    flow._entity_id = "sensor.test"
    flow._display_id = "Test"
    flow._vendor_name = "HA"
    flow._device_name = "Device"
    result = await flow.async_step_entity_user_input(user_input=None)
    assert result["type"] == FlowResultType.FORM
    assert "sensor_usage" in result["data_schema"].schema


@pytest.mark.asyncio
async def test_entity_user_input_sf_any_shows_selector():
    """binary_sensor/None has sensor_function_choices='any' → form includes sensor_function."""
    from custom_components.dsvdc4ha.entity_mapping import get_entity_mapping
    flow = VdsdSubentryFlowHandler()
    flow.hass = MagicMock()
    flow.hass.states.get.return_value = None
    flow._entity_mapping = get_entity_mapping("binary_sensor", None)
    flow._entity_id = "binary_sensor.test"
    flow._display_id = "Test"
    flow._vendor_name = "HA"
    flow._device_name = "Device"
    result = await flow.async_step_entity_user_input(user_input=None)
    assert result["type"] == FlowResultType.FORM
    assert "sensor_function" in result["data_schema"].schema


@pytest.mark.asyncio
async def test_build_entity_vdsd_bi_group_applied():
    """bi_group from user_input must be written to binary_inputs[0]['group']."""
    from unittest.mock import patch, AsyncMock as AM
    from custom_components.dsvdc4ha.entity_mapping import get_entity_mapping
    flow = VdsdSubentryFlowHandler()
    flow.hass = MagicMock()
    flow.hass.states.get.return_value = MagicMock(name="Test Motion", attributes={})
    flow._entity_mapping = get_entity_mapping("binary_sensor", "motion")
    flow._entity_id = "binary_sensor.motion"
    flow._display_id = "Test"
    flow._vendor_name = "HA"
    flow._device_name = "Device"
    # User picks Security (6) instead of default Light (1)
    with patch.object(flow, "async_step_model_features", new=AM(return_value={"type": "form"})):
        with patch.object(flow, "_resolve_entity_icon", new=AM(return_value=(None, None))):
            await flow._build_entity_vdsd_and_continue({"bi_group": "6"})
    assert flow._current_binary_inputs[0]["group"] == 6


@pytest.mark.asyncio
async def test_build_entity_vdsd_sensor_usage_applied():
    """sensor_usage from user_input must be written to sensors[0]['sensorUsage']."""
    from unittest.mock import patch, AsyncMock as AM
    from custom_components.dsvdc4ha.entity_mapping import get_entity_mapping
    flow = VdsdSubentryFlowHandler()
    flow.hass = MagicMock()
    flow.hass.states.get.return_value = MagicMock(name="Test Temp", attributes={})
    flow._entity_mapping = get_entity_mapping("sensor", "temperature")
    flow._entity_id = "sensor.temperature"
    flow._display_id = "Test"
    flow._vendor_name = "HA"
    flow._device_name = "Device"
    # User picks Outdoor (2) instead of default Undefined (0)
    with patch.object(flow, "async_step_model_features", new=AM(return_value={"type": "form"})):
        with patch.object(flow, "_resolve_entity_icon", new=AM(return_value=(None, None))):
            await flow._build_entity_vdsd_and_continue({"sensor_usage": "2"})
    assert flow._current_sensors[0]["sensorUsage"] == 2
```

- [ ] **Step 2: Run failing tests**

```
cd /home/arne/Development/dsvdc4ha && python -m pytest tests/test_config_flow.py::test_entity_user_input_shows_bi_group_selector tests/test_config_flow.py::test_entity_user_input_shows_sensor_usage_selector tests/test_config_flow.py::test_entity_user_input_sf_any_shows_selector tests/test_config_flow.py::test_build_entity_vdsd_bi_group_applied tests/test_config_flow.py::test_build_entity_vdsd_sensor_usage_applied -v 2>&1 | tail -30
```
Expected: FAILED (KeyError or assertion on missing schema key)

- [ ] **Step 3: Update `async_step_entity_user_input` — sensor_function_choices "any" + new choices**

In `custom_components/dsvdc4ha/config_flow.py`, find `async_step_entity_user_input` (around line 914).

Replace the existing `sensor_function_choices` block:
```python
        if bi.get("sensor_function_choices"):
            schema_dict[vol.Required("sensor_function", default=str(bi["sensor_function"]))] = (
                selector.SelectSelector(selector.SelectSelectorConfig(options=[
                    selector.SelectOptionDict(value=str(v), label=lbl)
                    for v, lbl in bi["sensor_function_choices"]
                ]))
            )
```
With:
```python
        sfc = bi.get("sensor_function_choices")
        if sfc == "any":
            schema_dict[vol.Required("sensor_function", default=str(bi["sensor_function"]))] = (
                selector.SelectSelector(selector.SelectSelectorConfig(options=_BINARY_INPUT_TYPE_OPTIONS))
            )
        elif sfc:
            schema_dict[vol.Required("sensor_function", default=str(bi["sensor_function"]))] = (
                selector.SelectSelector(selector.SelectSelectorConfig(options=[
                    selector.SelectOptionDict(value=str(v), label=lbl)
                    for v, lbl in sfc
                ]))
            )
```

Then, immediately after that block (before the `if btn.get("group_choices"):` block), add:
```python
        if bi.get("group_choices"):
            schema_dict[vol.Required("bi_group", default=str(bi["group"]))] = (
                selector.SelectSelector(selector.SelectSelectorConfig(options=[
                    selector.SelectOptionDict(value=str(v), label=lbl)
                    for v, lbl in bi["group_choices"]
                ]))
            )
```

Then after the existing `sen.get("min_max_user")` block (and before `out.get("output_usage_choices")`), add:
```python
        suc = sen.get("sensor_usage_choices")
        if suc == "any":
            schema_dict[vol.Required("sensor_usage", default=str(sen["sensor_usage"]))] = (
                selector.SelectSelector(selector.SelectSelectorConfig(options=_SENSOR_USAGE_OPTIONS))
            )
        elif suc:
            schema_dict[vol.Required("sensor_usage", default=str(sen["sensor_usage"]))] = (
                selector.SelectSelector(selector.SelectSelectorConfig(options=[
                    selector.SelectOptionDict(value=str(v), label=lbl)
                    for v, lbl in suc
                ]))
            )
```

- [ ] **Step 4: Apply same changes to `async_step_device_entity_user_input` (around line 1257)**

This function has an identical schema building block. Apply the exact same three changes:
1. Replace `sensor_function_choices` block with "any"-aware version
2. Add `bi.group_choices` block after it
3. Add `sensor_usage_choices` block after `min_max_user` block

The diff is identical — same code, different function name.

- [ ] **Step 5: Update `_build_entity_vdsd_and_continue` to apply bi_group and sensor_usage**

In `_build_entity_vdsd_and_continue` (around line 993), in the **Binary input** section, change:

```python
            vdsd["binary_inputs"] = [{
                "dsIndex": 0,
                "name": friendly_name,
                "group": bi["group"],
```
To:
```python
            vdsd["binary_inputs"] = [{
                "dsIndex": 0,
                "name": friendly_name,
                "group": int(user_input.get("bi_group", bi["group"])),
```

In the **Sensor** section, change:
```python
                "sensorType": st,
                "sensorUsage": s["sensor_usage"],
```
To:
```python
                "sensorType": st,
                "sensorUsage": int(user_input.get("sensor_usage", s["sensor_usage"])),
```

- [ ] **Step 6: Run all config_flow tests**

```
cd /home/arne/Development/dsvdc4ha && python -m pytest tests/test_config_flow.py -v 2>&1 | tail -40
```
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py tests/test_config_flow.py
git commit -m "feat: add bi_group and sensor_usage selectors to entity user-input steps"
```

---

## Task 3: Update device_grouper.py — apply new user choices in resolve_vdsd_plan

**Files:**
- Modify: `custom_components/dsvdc4ha/device_grouper.py`
- Test: `tests/test_device_grouper.py`

### Context
`resolve_vdsd_plan` in `device_grouper.py` is the equivalent of `_build_entity_vdsd_and_continue` for the "from HA device" creation path. It already reads `sensor_function` and `output_usage` from `plan.user_choices` but hardcodes `bi["group"]` and `s["sensor_usage"]`.

- [ ] **Step 1: Write failing tests**

In `tests/test_device_grouper.py`, append:

```python
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
```

- [ ] **Step 2: Run failing tests**

```
cd /home/arne/Development/dsvdc4ha && python -m pytest tests/test_device_grouper.py::test_resolve_bi_group_user_choice_applied tests/test_device_grouper.py::test_resolve_sensor_usage_user_choice_applied -v 2>&1 | tail -20
```
Expected: FAILED (assertion error — actual values are 1 and 0, not user-overridden values)

- [ ] **Step 3: Update resolve_vdsd_plan — binary_input group**

In `custom_components/dsvdc4ha/device_grouper.py`, in `resolve_vdsd_plan`, find the binary_input section (around line 190):

```python
    if plan.binary_input_entity:
        e = plan.binary_input_entity
        choices = plan.user_choices.get(e.entity_id, {})
        bi = e.mapping["binary_input"]
        sf = int(choices.get("sensor_function", bi["sensor_function"]))
        vdsd["binary_inputs"] = [{
            "dsIndex": 0,
            "name": e.friendly_name,
            "group": bi["group"],
```
Change `"group": bi["group"]` to `"group": int(choices.get("bi_group", bi["group"]))`:
```python
    if plan.binary_input_entity:
        e = plan.binary_input_entity
        choices = plan.user_choices.get(e.entity_id, {})
        bi = e.mapping["binary_input"]
        sf = int(choices.get("sensor_function", bi["sensor_function"]))
        vdsd["binary_inputs"] = [{
            "dsIndex": 0,
            "name": e.friendly_name,
            "group": int(choices.get("bi_group", bi["group"])),
```

- [ ] **Step 4: Update resolve_vdsd_plan — sensor usage**

In the sensor loop (around line 247), change:
```python
        vdsd["sensors"].append({
            ...
            "sensorType": st,
            "sensorUsage": s["sensor_usage"],
```
To:
```python
        vdsd["sensors"].append({
            ...
            "sensorType": st,
            "sensorUsage": int(choices.get("sensor_usage", s["sensor_usage"])),
```

- [ ] **Step 5: Run all device_grouper tests**

```
cd /home/arne/Development/dsvdc4ha && python -m pytest tests/test_device_grouper.py -v 2>&1 | tail -40
```
Expected: all tests PASS.

- [ ] **Step 6: Run full test suite**

```
cd /home/arne/Development/dsvdc4ha && python -m pytest tests/ -v 2>&1 | tail -50
```
Expected: all tests PASS. Fix any regressions before committing.

- [ ] **Step 7: Commit**

```bash
git add custom_components/dsvdc4ha/device_grouper.py tests/test_device_grouper.py
git commit -m "feat: apply bi_group and sensor_usage user choices in resolve_vdsd_plan"
```
