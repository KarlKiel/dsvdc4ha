# Shadow Motor Timing User Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add user-configurable shadow motor timing parameters (`openTime`, `closeTime`, `angleOpenTime`, `angleCloseTime`, `stopDelayTime`) to the config flow for cover devices that use positional/angle shadow channels, with the Excel spreadsheet as the source of truth for which devices need which fields.

**Architecture:** Two boolean flags (`shadow_position_timing`, `shadow_angle_timing`) are added to the `output` dict of relevant cover entries in `entity_mapping.py`. These flags drive both Excel column values (the "source of truth") and the conditional form fields shown in `async_step_entity_user_input` / `async_step_device_entity_user_input`. Collected values flow through `_build_entity_vdsd_and_continue()` (entity path) and `resolve_vdsd_plan()` (device path) into the output config dict as camelCase keys (`openTime`, `closeTime`, etc.), matching what `api.py` already passes to `pydsvdcapi.Output()`.

**Tech Stack:** Python/Home Assistant custom component, pydsvdcapi 0.8.8, voluptuous, HA selectors, openpyxl.

---

## File Map

| File | Change |
|------|--------|
| `custom_components/dsvdc4ha/entity_mapping.py` | Add `shadow_position_timing`/`shadow_angle_timing` flags to 7 cover output dicts; update `needs_user_input()` |
| `tools/excel_schema.py` | Add two YesNo columns before the timing value columns |
| `custom_components/dsvdc4ha/config_flow.py` | Add timing `NumberSelector` fields to both user-input form builders; write values in `_build_entity_vdsd_and_continue()` |
| `custom_components/dsvdc4ha/device_grouper.py` | Forward timing values from `user_choices` into resolved output dict |
| `tests/test_entity_mapping_bindings.py` | Tests for `needs_user_input()` with new flags |
| `tests/test_device_grouper.py` | Tests for `resolve_vdsd_plan()` forwarding timing values |
| `tests/test_config_flow.py` | Tests for form schema and value storage |
| `documents/ha_vdsd_mapping.xlsx` | Regenerated (run `python3 tools/generate_mapping_excel.py`) |

---

## Cover Device Timing Coverage

| device_class | position timing | angle timing | rationale |
|---|---|---|---|
| awning | ✓ | — | SHADE_POSITION_OUTSIDE only |
| blind | ✓ | ✓ | position + angle in both channel sets |
| curtain | ✓ | — | position only |
| damper | — | — | AIR_FLAP (climate, not shadow motor) |
| door | — | — | POWER_STATE (binary only) |
| garage | — | — | POWER_STATE (binary only) |
| gate | ✓ | — | SHADE_POSITION_OUTSIDE |
| shade | ✓ | — | position only |
| shutter | ✓ | ✓ | SHADE_POSITION_OUTSIDE + SHADE_OPENING_ANGLE_OUTSIDE |
| window | ✓ | ✓ | position + optional_tilt (show angle fields always, user can leave empty) |

---

## Task 1: Add timing flags to entity_mapping.py

**Files:**
- Modify: `custom_components/dsvdc4ha/entity_mapping.py:567-731` (cover entries)
- Modify: `custom_components/dsvdc4ha/entity_mapping.py:1387-1404` (`needs_user_input`)
- Test: `tests/test_entity_mapping_bindings.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_entity_mapping_bindings.py` after the existing `needs_user_input` tests (after line ~133):

```python
def test_needs_user_input_shadow_position_timing():
    m = {"output": {"shadow_position_timing": True}}
    assert needs_user_input(m)


def test_needs_user_input_shadow_angle_timing():
    m = {"output": {"shadow_angle_timing": True}}
    assert needs_user_input(m)


def test_needs_user_input_returns_false_without_flags():
    m = {"output": {"function": 0, "groups": [2]}}
    assert not needs_user_input(m)


def test_awning_output_has_shadow_position_timing():
    m = _mapping("cover", "awning")
    assert m["output"].get("shadow_position_timing") is True
    assert not m["output"].get("shadow_angle_timing")


def test_blind_output_has_both_shadow_timing_flags():
    m = _mapping("cover", "blind")
    assert m["output"].get("shadow_position_timing") is True
    assert m["output"].get("shadow_angle_timing") is True


def test_curtain_output_has_position_timing_only():
    m = _mapping("cover", "curtain")
    assert m["output"].get("shadow_position_timing") is True
    assert not m["output"].get("shadow_angle_timing")


def test_shutter_output_has_both_shadow_timing_flags():
    m = _mapping("cover", "shutter")
    assert m["output"].get("shadow_position_timing") is True
    assert m["output"].get("shadow_angle_timing") is True


def test_window_cover_output_has_both_shadow_timing_flags():
    m = _mapping("cover", "window")
    assert m["output"].get("shadow_position_timing") is True
    assert m["output"].get("shadow_angle_timing") is True


def test_door_output_has_no_shadow_timing_flags():
    m = _mapping("cover", "door")
    assert not m["output"].get("shadow_position_timing")
    assert not m["output"].get("shadow_angle_timing")


def test_damper_output_has_no_shadow_timing_flags():
    m = _mapping("cover", "damper")
    assert not m["output"].get("shadow_position_timing")
```

- [ ] **Step 2: Run tests to verify they fail**

```
source .venv/bin/activate && pytest tests/test_entity_mapping_bindings.py -x -q 2>&1 | tail -10
```

Expected: several failures with `AssertionError` (flags not present yet).

- [ ] **Step 3: Add flags to entity_mapping.py cover entries**

In `custom_components/dsvdc4ha/entity_mapping.py`, add the flags to each cover `output` dict:

**awning** (around line 571-577): add `"shadow_position_timing": True` to the `output` dict.

```python
        "output": {
            "function": OutputFunction.POSITIONAL, "default_group": ColorClass.AWNINGS, "output_usage": 0,
            "variable_ramp": False, "mode": OutputMode.GRADUAL, "groups": [2],
            "shadow_position_timing": True,
            "channels": [{"channel_type": OutputChannelType.SHADE_POSITION_OUTSIDE,
```

**blind** (around line 584-603): add both flags.

```python
        "output": {
            "function": OutputFunction.POSITIONAL, "default_group": ColorClass.BLINDS, "output_usage": 0,
            "variable_ramp": False, "mode": OutputMode.GRADUAL, "groups": [2],
            "placement_choice": True,
            "shadow_position_timing": True,
            "shadow_angle_timing": True,
            "channels": [
```

**curtain** (around line 611-620): add position timing only.

```python
        "output": {
            "function": OutputFunction.POSITIONAL, "default_group": ColorClass.BLINDS, "output_usage": 0,
            "variable_ramp": False, "mode": OutputMode.GRADUAL, "groups": [2],
            "placement_choice": True,
            "shadow_position_timing": True,
            "channels": [{"channel_type": OutputChannelType.SHADE_POSITION_INDOOR,
```

**gate** (around line 667-674): add position timing.

```python
        "output": {
            "function": OutputFunction.POSITIONAL,
            "function_choices": [(OutputFunction.POSITIONAL.value, "Positional — supports position feedback (2)"), (OutputFunction.ON_OFF.value, "On/Off only (0)")],
            "default_group": ColorClass.ACCESS, "output_usage": 0,
            "variable_ramp": False, "mode": OutputMode.GRADUAL, "groups": [7],
            "shadow_position_timing": True,
            "channels": [{"channel_type": OutputChannelType.SHADE_POSITION_OUTSIDE,
```

**shade** (around line 682-691): add position timing.

```python
        "output": {
            "function": OutputFunction.POSITIONAL, "default_group": ColorClass.BLINDS, "output_usage": 0,
            "variable_ramp": False, "mode": OutputMode.GRADUAL, "groups": [2],
            "placement_choice": True,
            "shadow_position_timing": True,
            "channels": [{"channel_type": OutputChannelType.SHADE_POSITION_INDOOR,
```

**shutter** (around line 699-709): add both flags.

```python
        "output": {
            "function": OutputFunction.POSITIONAL, "default_group": ColorClass.BLINDS, "output_usage": 0,
            "variable_ramp": False, "mode": OutputMode.GRADUAL, "groups": [2],
            "shadow_position_timing": True,
            "shadow_angle_timing": True,
            "channels": [
```

**window** (around line 717-729): add both flags.

```python
        "output": {
            "function": OutputFunction.POSITIONAL,
            "function_choices": [(OutputFunction.POSITIONAL.value, "Positional — supports position feedback (2)"), (OutputFunction.ON_OFF.value, "On/Off only (0)")],
            "default_group": ColorClass.WINDOW, "output_usage": 0,
            "variable_ramp": False, "mode": OutputMode.GRADUAL, "groups": [3],
            "placement_choice": True,
            "shadow_position_timing": True,
            "shadow_angle_timing": True,
            "channels": [{"channel_type": OutputChannelType.SHADE_POSITION_INDOOR,
```

- [ ] **Step 4: Update `needs_user_input()` in entity_mapping.py**

In `needs_user_input()` (around line 1387-1404), add the two new flags:

```python
def needs_user_input(mapping: dict[str, Any]) -> bool:
    """Return True if this mapping entry requires extra user input beyond entity selection."""
    for component in ("binary_input", "sensor", "button", "output"):
        comp = mapping.get(component, {})
        if (
            comp.get("sensor_function_choices")
            or comp.get("group_choices")
            or comp.get("input_usage_choices")
            or comp.get("sensor_type_choices")
            or comp.get("sensor_usage_choices")
            or comp.get("output_usage_choices")
            or comp.get("function_choices")
            or comp.get("min_max_user")
            or comp.get("optional_tilt")
            or comp.get("placement_choice")
            or comp.get("shadow_position_timing")
            or comp.get("shadow_angle_timing")
        ):
            return True
    return False
```

- [ ] **Step 5: Run tests to verify they pass**

```
source .venv/bin/activate && pytest tests/test_entity_mapping_bindings.py -x -q 2>&1 | tail -10
```

Expected: all pass.

- [ ] **Step 6: Run full test suite**

```
source .venv/bin/activate && pytest tests/ -x -q 2>&1 | tail -5
```

Expected: 340+ tests pass, 0 failures.

- [ ] **Step 7: Commit**

```bash
git add custom_components/dsvdc4ha/entity_mapping.py tests/test_entity_mapping_bindings.py
git commit -m "feat: add shadow_position_timing and shadow_angle_timing flags to cover output entries"
```

---

## Task 2: Add timing flag columns to excel_schema.py and regenerate Excel

**Files:**
- Modify: `tools/excel_schema.py` (add 2 YesNo columns)
- Modify: `documents/ha_vdsd_mapping.xlsx` (regenerated)
- Test: `tests/test_mapping_excel.py`

- [ ] **Step 1: Check existing test coverage**

Read `tests/test_mapping_excel.py` to understand what tests exist and what needs to be added:

```
source .venv/bin/activate && pytest tests/test_mapping_excel.py -v 2>&1 | tail -20
```

- [ ] **Step 2: Add failing tests for new columns**

In `tests/test_mapping_excel.py`, add tests verifying the new columns appear and have correct values:

```python
def test_shadow_position_timing_column_exists():
    """output.shadow_position_timing column is present in COLUMNS."""
    from tools.excel_schema import COLUMNS
    headers = [h for h, _, _ in COLUMNS]
    assert "output.shadow_position_timing" in headers


def test_shadow_angle_timing_column_exists():
    """output.shadow_angle_timing column is present in COLUMNS."""
    from tools.excel_schema import COLUMNS
    headers = [h for h, _, _ in COLUMNS]
    assert "output.shadow_angle_timing" in headers


def test_shadow_position_timing_is_yes_for_awning():
    """awning output has shadow_position_timing=True → column shows 'yes'."""
    from tools.excel_schema import COLUMNS
    from custom_components.dsvdc4ha.entity_mapping import ENTITY_MAPPING
    awning = next(e for e in ENTITY_MAPPING if e["domain"] == "cover" and e.get("device_class") == "awning")
    col = next((ext for h, _, ext in COLUMNS if h == "output.shadow_position_timing"), None)
    assert col is not None
    assert col(awning) == "yes"


def test_shadow_angle_timing_is_no_for_awning():
    """awning output does not have shadow_angle_timing → column shows 'no'."""
    from tools.excel_schema import COLUMNS
    from custom_components.dsvdc4ha.entity_mapping import ENTITY_MAPPING
    awning = next(e for e in ENTITY_MAPPING if e["domain"] == "cover" and e.get("device_class") == "awning")
    col = next((ext for h, _, ext in COLUMNS if h == "output.shadow_angle_timing"), None)
    assert col is not None
    assert col(awning) == "no"


def test_shadow_angle_timing_is_yes_for_blind():
    """blind output has shadow_angle_timing=True → column shows 'yes'."""
    from tools.excel_schema import COLUMNS
    from custom_components.dsvdc4ha.entity_mapping import ENTITY_MAPPING
    blind = next(e for e in ENTITY_MAPPING if e["domain"] == "cover" and e.get("device_class") == "blind")
    col = next((ext for h, _, ext in COLUMNS if h == "output.shadow_angle_timing"), None)
    assert col is not None
    assert col(blind) == "yes"
```

Run to verify they fail:

```
source .venv/bin/activate && pytest tests/test_mapping_excel.py -x -q 2>&1 | tail -10
```

- [ ] **Step 3: Add columns to excel_schema.py**

In `tools/excel_schema.py`, in `_build_columns()`, add two YesNo columns for the new flags **before** the `# Shadow motor timing` comment (i.e., after the outdoor channel columns, before `output.openTime`). This puts the flag columns next to each other, before the value columns.

Replace the section starting at the `# Shadow motor timing` comment:

```python
    # Shadow motor timing flags (source of truth for what to ask in config flow)
    cols += [
        ("output.shadow_position_timing", "YesNo",
         lambda e: "yes" if _sub(e, "output").get("shadow_position_timing") else "no"),
        ("output.shadow_angle_timing", "YesNo",
         lambda e: "yes" if _sub(e, "output").get("shadow_angle_timing") else "no"),
    ]
    # Shadow motor timing values (grey / cover devices — set by dSS at runtime)
    cols += [
        ("output.openTime",      None, lambda e: _sub(e, "output").get("openTime")),
        ("output.closeTime",     None, lambda e: _sub(e, "output").get("closeTime")),
        ("output.angleOpenTime", None, lambda e: _sub(e, "output").get("angleOpenTime")),
        ("output.angleCloseTime",None, lambda e: _sub(e, "output").get("angleCloseTime")),
        ("output.stopDelayTime", None, lambda e: _sub(e, "output").get("stopDelayTime")),
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

```
source .venv/bin/activate && pytest tests/test_mapping_excel.py -x -q 2>&1 | tail -10
```

Expected: all pass.

- [ ] **Step 5: Regenerate Excel**

```bash
source .venv/bin/activate && python3 tools/generate_mapping_excel.py
```

Expected: no errors, `documents/ha_vdsd_mapping.xlsx` updated (now 57 columns: 55 previous + 2 new flag columns).

- [ ] **Step 6: Verify audit passes**

```bash
source .venv/bin/activate && python3 tools/audit_mapping.py
```

Expected: `✓  All checked fields match.` (or only the expected missing entries warning).

- [ ] **Step 7: Run full test suite**

```
source .venv/bin/activate && pytest tests/ -x -q 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add tools/excel_schema.py documents/ha_vdsd_mapping.xlsx
git commit -m "feat: add shadow timing flag columns to Excel schema and regenerate spreadsheet"
```

---

## Task 3: Add timing fields to config flow forms and _build_entity_vdsd_and_continue()

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py:834-950` (`async_step_entity_user_input`)
- Modify: `custom_components/dsvdc4ha/config_flow.py:1223-1346` (`async_step_device_entity_user_input`)
- Modify: `custom_components/dsvdc4ha/config_flow.py:1047-1121` (`_build_entity_vdsd_and_continue`)
- Test: `tests/test_config_flow.py`

- [ ] **Step 1: Write failing tests**

Add the following tests to `tests/test_config_flow.py`:

```python
async def test_entity_user_input_form_shows_position_timing_for_awning():
    """async_step_entity_user_input shows openTime/closeTime/stopDelayTime for awning."""
    from custom_components.dsvdc4ha.entity_mapping import get_entity_mapping
    flow = _make_flow()
    flow._entity_mapping = get_entity_mapping("cover", "awning")
    result = await flow.async_step_entity_user_input(user_input=None)
    assert result["type"] == "form"
    schema_keys = [str(k) for k in result["data_schema"].schema.keys()]
    assert any("openTime" in k for k in schema_keys)
    assert any("closeTime" in k for k in schema_keys)
    assert any("stopDelayTime" in k for k in schema_keys)
    assert not any("angleOpenTime" in k for k in schema_keys)


async def test_entity_user_input_form_shows_angle_timing_for_blind():
    """async_step_entity_user_input shows angle timing fields for blind."""
    from custom_components.dsvdc4ha.entity_mapping import get_entity_mapping
    flow = _make_flow()
    flow._entity_mapping = get_entity_mapping("cover", "blind")
    result = await flow.async_step_entity_user_input(user_input=None)
    assert result["type"] == "form"
    schema_keys = [str(k) for k in result["data_schema"].schema.keys()]
    assert any("angleOpenTime" in k for k in schema_keys)
    assert any("angleCloseTime" in k for k in schema_keys)


async def test_build_entity_vdsd_stores_timing_values():
    """_build_entity_vdsd_and_continue writes timing user_input into output dict."""
    from custom_components.dsvdc4ha.entity_mapping import get_entity_mapping
    flow = _make_flow()
    flow._entity_id = "cover.my_blind"
    flow._entity_mapping = get_entity_mapping("cover", "awning")
    flow._display_id = "HA Cover (awning)"
    flow._vendor_name = ""
    flow._device_name = "My Blind"
    flow._vdsds = []
    flow._current_vdsd = {}
    flow._current_buttons = []
    flow._current_binary_inputs = []
    flow._current_sensors = []
    flow._current_output = None

    with patch("custom_components.dsvdc4ha.config_flow.er") as mock_er, \
         patch.object(flow, "_resolve_entity_icon", return_value=("", None)):
        mock_er.async_get.return_value.async_get.return_value = None
        result = await flow._build_entity_vdsd_and_continue({
            "openTime": 30.0,
            "closeTime": 25.0,
            "stopDelayTime": 2.0,
        })

    assert flow._current_output is not None
    assert flow._current_output.get("openTime") == 30.0
    assert flow._current_output.get("closeTime") == 25.0
    assert flow._current_output.get("stopDelayTime") == 2.0
    assert "angleOpenTime" not in flow._current_output


async def test_build_entity_vdsd_omits_absent_timing_values():
    """Timing values not in user_input are not added to output dict."""
    from custom_components.dsvdc4ha.entity_mapping import get_entity_mapping
    flow = _make_flow()
    flow._entity_id = "cover.my_awning"
    flow._entity_mapping = get_entity_mapping("cover", "awning")
    flow._display_id = "HA Cover (awning)"
    flow._vendor_name = ""
    flow._device_name = "My Awning"
    flow._vdsds = []
    flow._current_vdsd = {}
    flow._current_buttons = []
    flow._current_binary_inputs = []
    flow._current_sensors = []
    flow._current_output = None

    with patch("custom_components.dsvdc4ha.config_flow.er") as mock_er, \
         patch.object(flow, "_resolve_entity_icon", return_value=("", None)):
        mock_er.async_get.return_value.async_get.return_value = None
        await flow._build_entity_vdsd_and_continue({})  # no timing values

    assert flow._current_output is not None
    assert "openTime" not in flow._current_output
    assert "closeTime" not in flow._current_output
    assert "stopDelayTime" not in flow._current_output
```

Run to verify failures:

```
source .venv/bin/activate && pytest tests/test_config_flow.py -k "timing" -x -q 2>&1 | tail -10
```

Expected: failures (fields not in form, values not in output dict).

- [ ] **Step 2: Add timing fields to `async_step_entity_user_input`**

In `config_flow.py`, in `async_step_entity_user_input` (around line 939-950), add the following **after** the `placement_choice` block and **before** the `return self.async_show_form(...)`:

```python
        if out.get("shadow_position_timing"):
            schema_dict[vol.Optional("openTime")] = selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, step=0.1, mode="box", unit_of_measurement="s")
            )
            schema_dict[vol.Optional("closeTime")] = selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, step=0.1, mode="box", unit_of_measurement="s")
            )
            schema_dict[vol.Optional("stopDelayTime")] = selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, step=0.1, mode="box", unit_of_measurement="s")
            )
        if out.get("shadow_angle_timing"):
            schema_dict[vol.Optional("angleOpenTime")] = selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, step=0.1, mode="box", unit_of_measurement="s")
            )
            schema_dict[vol.Optional("angleCloseTime")] = selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, step=0.1, mode="box", unit_of_measurement="s")
            )
```

- [ ] **Step 3: Add timing fields to `async_step_device_entity_user_input`**

In `config_flow.py`, in `async_step_device_entity_user_input` (around line 1327-1346), add the same blocks **after** the `placement_choice` block and **before** `current = self._pending_choice_idx + 1`:

```python
        if out.get("shadow_position_timing"):
            schema_dict[vol.Optional("openTime")] = selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, step=0.1, mode="box", unit_of_measurement="s")
            )
            schema_dict[vol.Optional("closeTime")] = selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, step=0.1, mode="box", unit_of_measurement="s")
            )
            schema_dict[vol.Optional("stopDelayTime")] = selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, step=0.1, mode="box", unit_of_measurement="s")
            )
        if out.get("shadow_angle_timing"):
            schema_dict[vol.Optional("angleOpenTime")] = selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, step=0.1, mode="box", unit_of_measurement="s")
            )
            schema_dict[vol.Optional("angleCloseTime")] = selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, step=0.1, mode="box", unit_of_measurement="s")
            )
```

- [ ] **Step 4: Write timing values in `_build_entity_vdsd_and_continue()`**

In `config_flow.py`, in `_build_entity_vdsd_and_continue` (around line 1088-1100), update the `vdsd["output"] = {...}` block to include timing values. Add after the `**({"apply_all_expr": ...})` line:

```python
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
                **({"apply_all_expr": o["apply_all_expr"]} if o.get("apply_all_expr") else {}),
                **{
                    k: float(user_input[k])
                    for k in ("openTime", "closeTime", "angleOpenTime", "angleCloseTime", "stopDelayTime")
                    if k in user_input and user_input[k] is not None
                },
            }
```

- [ ] **Step 5: Run tests to verify they pass**

```
source .venv/bin/activate && pytest tests/test_config_flow.py -k "timing" -x -q 2>&1 | tail -10
```

Expected: all pass.

- [ ] **Step 6: Run full test suite**

```
source .venv/bin/activate && pytest tests/ -x -q 2>&1 | tail -5
```

Expected: all pass, 0 failures.

- [ ] **Step 7: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py tests/test_config_flow.py
git commit -m "feat: add shadow motor timing fields to entity user input forms and vdsd output builder"
```

---

## Task 4: Forward timing values in device_grouper.py

**Files:**
- Modify: `custom_components/dsvdc4ha/device_grouper.py:299-311` (`resolve_vdsd_plan` output section)
- Test: `tests/test_device_grouper.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_device_grouper.py`:

```python
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
```

Run to verify failures:

```
source .venv/bin/activate && pytest tests/test_device_grouper.py -k "timing" -x -q 2>&1 | tail -10
```

Expected: failures (timing values not present in output dict).

- [ ] **Step 2: Implement in resolve_vdsd_plan()**

In `device_grouper.py`, update the `vdsd["output"] = {...}` block (around line 299-311) to include timing values from choices:

```python
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
            **({"apply_all_expr": o["apply_all_expr"]} if o.get("apply_all_expr") else {}),
            **{
                k: float(choices[k])
                for k in ("openTime", "closeTime", "angleOpenTime", "angleCloseTime", "stopDelayTime")
                if k in choices and choices[k] is not None
            },
        }
```

- [ ] **Step 3: Run tests to verify they pass**

```
source .venv/bin/activate && pytest tests/test_device_grouper.py -k "timing" -x -q 2>&1 | tail -10
```

Expected: all pass.

- [ ] **Step 4: Run full test suite**

```
source .venv/bin/activate && pytest tests/ -x -q 2>&1 | tail -5
```

Expected: all pass, 0 failures.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/device_grouper.py tests/test_device_grouper.py
git commit -m "feat: forward shadow motor timing values from user_choices in resolve_vdsd_plan"
```

---

## Self-Review

**Spec coverage:**
- ✓ User input in flow for all grey devices that use shadow motor channels
- ✓ Excel as source of truth (flag columns drive what the form shows)
- ✓ entity path: `async_step_entity_user_input` + `_build_entity_vdsd_and_continue`
- ✓ device path: `async_step_device_entity_user_input` + `resolve_vdsd_plan`
- ✓ `needs_user_input()` gating updated
- ✓ Tests for all changes

**Placeholder scan:** No TBDs, all code shown.

**Type consistency:**
- Timing keys in all 4 locations: `"openTime"`, `"closeTime"`, `"angleOpenTime"`, `"angleCloseTime"`, `"stopDelayTime"` — consistent camelCase matching what `api.py` passes to `Output()`.
- Flags: `"shadow_position_timing"`, `"shadow_angle_timing"` — consistent snake_case matching HA conventions for internal keys.
