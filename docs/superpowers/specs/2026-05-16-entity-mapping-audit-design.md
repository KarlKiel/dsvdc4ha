# Entity Mapping Audit & Compliance Fix — Design

## Goal

Ensure every entity/device-class combination in `entity_mapping.py` produces vdSD property values that exactly match `documents/ha_vdsd_mapping.xlsx`. Add an audit script that can be run in CI to catch future drift between the xlsx (source of truth) and the code.

## Architecture

Three files change; one new script and one new test file are added.

| File | Role |
|------|------|
| `custom_components/dsvdc4ha/entity_mapping.py` | Add identity fields per entry; fix wrong numeric values; add `sensor_usage_choices` where xlsx says USER |
| `custom_components/dsvdc4ha/config_flow.py` | Use mapping identity fields instead of HA device info; fix `name`; add `hardwareGuid`; handle `sensor_usage_choices` in user-input step |
| `tools/audit_mapping.py` | New: reads xlsx, compares every checkable scalar against `ENTITY_MAPPING`, exits 1 on mismatch |
| `tests/test_entity_mapping.py` | New: imports `run_audit()` and asserts zero discrepancies |

## Tech stack

Python, openpyxl (already available — used by the xlsx file), Home Assistant config-flow pattern, pydsvdcapi `DsUidNamespace.VDC`.

---

## Section 1 — Identity fields in entity_mapping.py

Every entry in `ENTITY_MAPPING` gets three new string keys taken verbatim from the xlsx:

```python
{
    "domain": "binary_sensor", "device_class": "battery", "primary_group": 8,
    "model": "HA Binary Sensor (battery)",
    "model_uid": "ha-binary-sensor-battery",
    "vendor_name": "Home Assistant",
    "binary_input": { ... },
}
```

The xlsx values are always `"HA <Entity Type>"` / `"ha-<domain>-<device_class>"` / `"Home Assistant"` — no exceptions. These are used by `config_flow.py` in `_build_entity_vdsd_and_continue`.

---

## Section 2 — config_flow.py changes

### 2a — Identity fields

In `_build_entity_vdsd_and_continue` (around line 1002), replace:

```python
"model": self._display_id,
"vendorName": self._vendor_name,
"modelVersion": "1.0",
"modelUID": (self._vendor_name + self._display_id).replace(" ", ""),
```

with:

```python
"model": mapping["model"],
"vendorName": mapping["vendor_name"],
"modelVersion": "1.0",
"modelUID": mapping["model_uid"],
```

### 2b — name field

Replace:

```python
"name": f"{self._device_name} — {friendly_name}",
```

with:

```python
"name": friendly_name,
```

where `friendly_name` is already `state.name or entity_id.split(".")[-1]` (existing code, line 999).

### 2c — hardwareGuid

After computing `vdsd["modelUID"]`, look up the entity's `unique_id` and compute:

```python
import uuid as _uuid
_VDC_NS = _uuid.UUID("9888dd3d-b345-4109-b088-2673306d0c65")  # DsUidNamespace.VDC

ent_reg = er.async_get(self.hass)
entry = ent_reg.async_get(entity_id)
unique_id = entry.unique_id if entry else entity_id
vdsd["hardwareGuid"] = "uuid:" + str(_uuid.uuid5(_VDC_NS, unique_id))
```

Fallback: if the entity has no registry entry (rare edge case), use `entity_id` as the name in the UUID5 call — still deterministic and unique.

### 2d — sensor_usage_choices in user-input step

`needs_user_input()` in `entity_mapping.py` already checks several `…_choices` keys. Add:

```python
or comp.get("sensor_usage_choices")
```

In `async_step_entity_user_input`, after the `sensor_type_choices` block, add a parallel block for `sensor_usage_choices`:

```python
if s.get("sensor_usage_choices") == "any":
    schema_dict[vol.Required("sensor_usage", default=str(s["sensor_usage"]))] = (
        selector.SelectSelector(selector.SelectSelectorConfig(options=[
            selector.SelectOptionDict(value=str(v), label=lbl)
            for v, lbl in [
                (0, "Generic (0)"), (1, "Room (1)"), (2, "Outdoor (2)"),
                (4, "Device Level (4)"), (5, "Device Level Individual (5)"),
                (6, "Device Level All (6)"),
            ]
        ]))
    )
elif s.get("sensor_usage_choices"):
    schema_dict[vol.Required("sensor_usage", default=str(s["sensor_usage"]))] = (
        selector.SelectSelector(selector.SelectSelectorConfig(options=[
            selector.SelectOptionDict(value=str(v), label=lbl)
            for v, lbl in s["sensor_usage_choices"]
        ]))
    )
```

In `_build_entity_vdsd_and_continue`, change:

```python
"sensorUsage": s["sensor_usage"],
```

to:

```python
"sensorUsage": int(user_input.get("sensor_usage", s["sensor_usage"])),
```

---

## Section 3 — Value fixes in entity_mapping.py

All wrong values identified by comparing xlsx against code:

| Entry | Field | Was | Now |
|-------|-------|-----|-----|
| `binary_sensor/moving` | `sensor_function` | 0 | 5 |
| `binary_sensor/moving` | `sensor_function_choices` | — | `[(5,"Motion (5)"),(0,"Generic (0)")]` |
| `binary_sensor/problem` | `input_usage` | 0 | 4 |
| `binary_sensor/running` | `input_usage` | 0 | 4 |
| `binary_sensor/moisture` | `group` | 8 | 8 (kept as default) |
| `binary_sensor/moisture` | `group_choices` | — | `[(8,"Joker (8)"),(6,"Security (6)"),(3,"Climate (3)")]` |
| `sensor/battery` | `update_interval` | 30.0 | 60.0 |
| `sensor/battery` | `alive_sign_interval` | 120.0 | 240.0 |

---

## Section 4 — sensor_usage_choices per sensor type

10 sensor entries get a new `sensor_usage_choices` key:

| Sensor | `sensor_usage` (default) | `sensor_usage_choices` |
|--------|--------------------------|------------------------|
| `(none)` | 0 | `"any"` (full selector) |
| `aqi` | 1 | `[(1,"Room (1)"),(2,"Outdoor (2)")]` |
| `distance` | 4 | `[(4,"Device Level (4)"),(5,"Device Level Individual (5)"),(6,"Device Level All (6)")]` |
| `duration` | 4 | `[(4,"Device Level (4)"),(5,"Device Level Individual (5)"),(6,"Device Level All (6)")]` |
| `gas` | 0 | `[(0,"Generic (0)"),(1,"Room (1)"),(2,"Outdoor (2)"),(4,"Device Level (4)")]` |
| `humidity` | 0 | `[(0,"Generic (0)"),(1,"Room (1)"),(2,"Outdoor (2)"),(4,"Device Level (4)")]` |
| `illuminance` | 0 | `[(0,"Generic (0)"),(1,"Room (1)"),(2,"Outdoor (2)"),(4,"Device Level (4)")]` |
| `moisture` | 0 | `[(0,"Generic (0)"),(1,"Room (1)"),(2,"Outdoor (2)"),(4,"Device Level (4)")]` |
| `speed` | 0 | `[(0,"Generic (0)"),(1,"Room (1)"),(2,"Outdoor (2)"),(4,"Device Level (4)")]` |
| `temperature` | 0 | `[(0,"Generic (0)"),(1,"Room (1)"),(2,"Outdoor (2)"),(4,"Device Level (4)")]` |

Note: `distance` and `duration` omit Generic/Room/Outdoor because the xlsx explicitly restricts them to Device Level.

---

## Section 5 — tools/audit_mapping.py

### Interface

```python
def run_audit(
    xlsx_path: str = "documents/ha_vdsd_mapping.xlsx",
) -> list[dict]:
    """Return a list of discrepancy dicts, empty if everything matches.

    Each dict: {domain, device_class, component, field, expected, actual}
    """
```

### CLI

```
python tools/audit_mapping.py
```

Prints a table of discrepancies (if any) and exits 0 (clean) or 1 (discrepancies found).

### What it checks

For each xlsx row (skipping `— not applicable —` cells):

| Component | Fields checked |
|-----------|----------------|
| `binary_input` | `sensor_function` (setting col), `group` (binarySettings.group), `input_usage` (inputUsage) |
| `sensor` | `sensor_type` (sensorType), `sensor_usage` (sensorUsage — default only), `min`, `max`, `resolution`, `update_interval` (updateInterval), `alive_sign_interval` (aliveSignInterval), `min_push_interval` (minPushInterval) |
| `output` | `function` (OutputFunction), `default_group` (defaultGroup), `output_usage` (outputUsage), `variable_ramp` (variableRamp), `mode` (OutputMode) |
| `output channels` | `channel_type` per CH1–CH6 (channelType col) |
| `button` | `button_type` (buttonType), `group` (buttonSettings.group), `function` (buttonSettings.function), `mode` (buttonSettings.mode) |
| identity | `model`, `model_uid`, `vendor_name` |

### What it does NOT check

- Expression strings (`apply_expr`, `push_expr`) — xlsx format is informal prose
- `choices` lists — these are editorial additions not representable in the xlsx cells
- Fields marked "pydsvdcapi handled" — not our values to set

### xlsx parsing rules

- Rows 1–3 are headers/groups; data starts at row 4
- Skip rows where `HA Entity Type` is blank
- Skip the special row `"Binary Sensor / (as Button - to be defined how to select)"` — not yet implemented
- Values containing `"pydsvdcapi handled"` or `"— not applicable —"` are ignored
- `"USER"` prefix in a field means the default is the parenthesised number before it (e.g., `"USER — default: MOTION (5)"` → expected default = 5)
- Group/type labels are resolved via a fixed mapping table (e.g., `"JOKER (8)"` → 8)

---

## Section 6 — tests/test_entity_mapping.py

```python
from tools.audit_mapping import run_audit

def test_entity_mapping_matches_xlsx():
    discrepancies = run_audit()
    assert discrepancies == [], (
        f"{len(discrepancies)} mapping discrepancies found:\n"
        + "\n".join(
            f"  {d['domain']}/{d['device_class']} [{d['component']}.{d['field']}]: "
            f"expected={d['expected']!r} actual={d['actual']!r}"
            for d in discrepancies
        )
    )
```

The test must be able to import `tools.audit_mapping`. Add the repo root to `sys.path` at the top of the test file:

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
```

No new conftest needed.

---

## Error handling & edge cases

- **Entity has no unique_id**: fall back to `entity_id` as the UUID5 name; still deterministic
- **openpyxl not installed**: `audit_mapping.py` raises `ImportError` with a clear message; test is skipped with `pytest.importorskip("openpyxl")`
- **xlsx not found**: `run_audit()` raises `FileNotFoundError` with the expected path

---

## What is NOT in scope

- Fixing `apply_expr` / `push_expr` channel converter expressions (they were not flagged as wrong by the audit)
- The `Button/identify`, `Button/restart`, `Button/update`, `Event/(none)` rows (marked ⚠ DYNAMIC DEFINITIONS REQUIRED in xlsx — separate feature)
- The `Light/rgbw`, `Light/rgbww` rows (marked ⚠ NOT NATIVELY SUPPORTED)
- The `Weather/(none)` row (composite multi-sensor device — separate feature)
- The HA-device creation path in config_flow (it has its own identity fields entered by the user)
