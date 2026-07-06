# Mapping Excel Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `tools/generate_mapping_excel.py` that writes `documents/ha_vdsd_mapping.xlsx` from `entity_mapping.py`, with per-property USER (yes/no) and VALUE (enum-name) dropdown columns, and update `tools/audit_mapping.py` to read this new format.

**Architecture:** A shared `tools/excel_schema.py` module defines the column list, enum options, and extractor functions. The generator reads `ENTITY_MAPPING` and writes one row per entry using openpyxl, with DataValidation dropdowns backed by a hidden `_lookups` sheet (required because several enums exceed Excel's 255-char inline formula limit). The updated audit tool uses the same schema to find columns by header name and validates VALUE (enum name → integer lookup) and USER (yes/no matches presence of `*_choices` in entity_mapping.py).

**Tech Stack:** Python, openpyxl, pydsvdcapi, pytest

---

## Column Schema

Every enum property gets two columns: `<prop>.USER` (dropdown: yes/no — whether the user picks this in the config flow) and `<prop>.VALUE` (dropdown: enum member names + `-` meaning not set). Numeric properties and boolean flags get a single VALUE column. The `-` sentinel means "this property doesn't apply to this entity/device_class combination."

| Header | Type | Dropdown | Notes |
|--------|------|----------|-------|
| `domain` | text | — | |
| `device_class` | text | — | |
| `model` | text | — | |
| `model_uid` | text | — | |
| `vendor_name` | text | — | |
| `primary_group.USER` | YesNo | yes/no | always "no" currently |
| `primary_group.VALUE` | enum | ColorGroup | |
| `bi.sensor_function.USER` | YesNo | yes/no | "yes" if `sensor_function_choices` set |
| `bi.sensor_function.VALUE` | enum | BinaryInputType | |
| `bi.group.USER` | YesNo | yes/no | "yes" if `group_choices` set |
| `bi.group.VALUE` | enum | BinaryInputGroup | |
| `bi.input_usage.USER` | YesNo | yes/no | "yes" if `input_usage_choices` set |
| `bi.input_usage.VALUE` | enum | BinaryInputUsage | |
| `sensor.sensor_type.USER` | YesNo | yes/no | "yes" if `sensor_type_choices` set |
| `sensor.sensor_type.VALUE` | enum | SensorType | |
| `sensor.sensor_usage.USER` | YesNo | yes/no | "yes" if `sensor_usage_choices` set |
| `sensor.sensor_usage.VALUE` | enum | SensorUsage | |
| `sensor.group.VALUE` | enum | SensorGroup | no USER — never user choice |
| `sensor.min` | float | — | |
| `sensor.max` | float | — | |
| `sensor.resolution` | float | — | |
| `sensor.update_interval` | float | — | |
| `sensor.alive_sign_interval` | float | — | |
| `sensor.min_push_interval` | float | — | |
| `sensor.min_max_user` | YesNo | yes/no | "yes" if `min_max_user=True` |
| `output.function.USER` | YesNo | yes/no | "yes" if `function_choices` set |
| `output.function.VALUE` | enum | OutputFunction | |
| `output.output_usage.USER` | YesNo | yes/no | "yes" if `output_usage_choices` set |
| `output.output_usage.VALUE` | enum | OutputUsage | |
| `output.mode.VALUE` | enum | OutputMode | no USER |
| `output.default_group.VALUE` | enum | ColorClass | no USER |
| `output.variable_ramp` | YesNo | yes/no | |
| `output.ch0.channel_type.VALUE` … `output.ch5.channel_type.VALUE` | enum | OutputChannelType | no USER — fixed per entry |
| `button.button_type.VALUE` | enum | ButtonType | no USER |
| `button.group.USER` | YesNo | yes/no | "yes" if `group_choices` set |
| `button.group.VALUE` | enum | ButtonGroup | |
| `button.function.VALUE` | enum | ButtonFunctionJoker | no USER |
| `button.mode.VALUE` | enum | ButtonMode | no USER |

**Out of scope:** `apply_expr`, `push_expr`, `channels_by_usage`, `optional_tilt` — these are code-level constructs, not scalar choices.

---

## File Structure

- **Create:** `tools/excel_schema.py` — column list, enum options, extractor lambdas (shared by generator + audit)
- **Create:** `tools/generate_mapping_excel.py` — reads entity_mapping.py, writes Excel with dropdowns
- **Modify:** `tools/audit_mapping.py` — replace hardcoded column indices with header-based lookup + USER checking
- **Create:** `tests/test_mapping_excel.py` — tests for generator and updated audit

---

## Task 1: Create `tools/excel_schema.py`

**Files:**
- Create: `tools/excel_schema.py`
- Test: `tests/test_mapping_excel.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_mapping_excel.py`:

```python
"""Tests for the mapping Excel generator and audit tool."""
from __future__ import annotations
import importlib.util, pathlib

_REPO = pathlib.Path(__file__).parent.parent


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, _REPO / relpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_schema_columns_have_correct_structure():
    schema = _load("excel_schema", "tools/excel_schema.py")
    assert len(schema.COLUMNS) > 30, "Expected at least 30 columns"
    headers = [h for h, _, _ in schema.COLUMNS]
    # Identity columns
    assert "domain" in headers
    assert "device_class" in headers
    assert "model" in headers
    # Enum columns
    assert "primary_group.VALUE" in headers
    assert "bi.sensor_function.USER" in headers
    assert "bi.sensor_function.VALUE" in headers
    assert "sensor.sensor_type.USER" in headers
    assert "output.function.VALUE" in headers
    assert "output.ch0.channel_type.VALUE" in headers
    assert "output.ch5.channel_type.VALUE" in headers
    assert "button.group.USER" in headers


def test_schema_enum_options_all_present():
    schema = _load("excel_schema", "tools/excel_schema.py")
    required = {
        "YesNo", "ColorGroup", "BinaryInputType", "BinaryInputGroup",
        "BinaryInputUsage", "SensorType", "SensorUsage", "SensorGroup",
        "OutputFunction", "OutputUsage", "OutputMode", "ColorClass",
        "OutputChannelType", "ButtonType", "ButtonGroup",
        "ButtonFunctionJoker", "ButtonMode",
    }
    assert required <= set(schema.ENUM_OPTIONS.keys())
    assert schema.ENUM_OPTIONS["YesNo"] == ["yes", "no"]
    assert "-" in schema.ENUM_OPTIONS["ColorGroup"]
    assert "BLACK" in schema.ENUM_OPTIONS["ColorGroup"]


def test_schema_extractors_on_known_entry():
    schema = _load("excel_schema", "tools/excel_schema.py")
    from custom_components.dsvdc4ha.entity_mapping import ENTITY_MAPPING
    col_map = {h: (h, ek, fn) for h, ek, fn in schema.COLUMNS}

    # binary_sensor/None: sensor_function_choices="any" → USER=yes, sensor_function=GENERIC
    entry = next(e for e in ENTITY_MAPPING if e["domain"] == "binary_sensor" and e["device_class"] is None)
    _, _, fn_user = col_map["bi.sensor_function.USER"]
    _, _, fn_val  = col_map["bi.sensor_function.VALUE"]
    assert fn_user(entry) == "yes"
    assert fn_val(entry) == "GENERIC"

    # binary_sensor/motion: no sensor_function_choices → USER=no, sensor_function=MOTION
    entry_m = next(e for e in ENTITY_MAPPING if e["domain"] == "binary_sensor" and e["device_class"] == "motion")
    assert fn_user(entry_m) == "no"
    assert fn_val(entry_m) == "MOTION"

    # sensor/temperature: sensor_usage_choices set → USER=yes
    entry_t = next(e for e in ENTITY_MAPPING if e["domain"] == "sensor" and e["device_class"] == "temperature")
    _, _, su_user = col_map["sensor.sensor_usage.USER"]
    assert su_user(entry_t) == "yes"

    # cover/awning: output.ch0.channel_type = SHADE_POSITION_OUTSIDE
    entry_a = next(e for e in ENTITY_MAPPING if e["domain"] == "cover" and e["device_class"] == "awning")
    _, _, ch0 = col_map["output.ch0.channel_type.VALUE"]
    assert ch0(entry_a) == "SHADE_POSITION_OUTSIDE"

    # cover/awning has no ch1 → "-"
    _, _, ch1 = col_map["output.ch1.channel_type.VALUE"]
    assert ch1(entry_a) == "-"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/arne/Development/dsvdc4ha
.venv/bin/pytest tests/test_mapping_excel.py -v 2>&1 | head -20
```

Expected: FAIL — `tools/excel_schema.py` not found.

- [ ] **Step 3: Create `tools/excel_schema.py`**

```python
"""Column schema for the HA-vdSD mapping Excel.

Shared by generate_mapping_excel.py and audit_mapping.py.
Each COLUMNS entry is (header: str, enum_key: str | None, extractor: callable).
  enum_key=None    → plain value (text/float), no dropdown
  enum_key="YesNo" → yes/no dropdown
  enum_key=<name>  → enum member name dropdown (key into ENUM_OPTIONS)
"""
from __future__ import annotations
import pathlib, sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from pydsvdcapi.enums import (
    BinaryInputGroup, BinaryInputType, BinaryInputUsage,
    ButtonFunctionJoker, ButtonGroup, ButtonMode, ButtonType,
    ColorClass, ColorGroup,
    OutputChannelType, OutputFunction, OutputMode, OutputUsage,
    SensorGroup, SensorType, SensorUsage,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def enum_name(enum_cls, value) -> str:
    """Return enum member name for an integer value, or '-' if None/unknown."""
    if value is None:
        return "-"
    try:
        return enum_cls(int(value)).name
    except (ValueError, TypeError):
        return "-"


def enum_value(enum_cls, name: str):
    """Return integer value for an enum member name, or None for '-'/blank."""
    s = (name or "").strip()
    if not s or s == "-":
        return None
    try:
        return enum_cls[s].value
    except KeyError:
        return None


def _sub(entry: dict, key: str) -> dict:
    return entry.get(key) or {}


def _has_choices(sub: dict, field: str) -> bool:
    """True if <field>_choices is present and truthy (including 'any')."""
    return bool(sub.get(field + "_choices"))


def _ch_type(entry: dict, i: int) -> str:
    channels = (_sub(entry, "output")).get("channels") or []
    if i < len(channels):
        return enum_name(OutputChannelType, channels[i].get("channel_type"))
    return "-"


# ---------------------------------------------------------------------------
# Dropdown option lists (written to hidden _lookups sheet in the Excel)
# ---------------------------------------------------------------------------

ENUM_OPTIONS: dict[str, list[str]] = {
    "YesNo":             ["yes", "no"],
    "ColorGroup":        ["-"] + [m.name for m in ColorGroup],
    "BinaryInputType":   ["-"] + [m.name for m in BinaryInputType],
    "BinaryInputGroup":  ["-"] + [m.name for m in BinaryInputGroup],
    "BinaryInputUsage":  ["-"] + [m.name for m in BinaryInputUsage],
    "SensorType":        ["-"] + [m.name for m in SensorType],
    "SensorUsage":       ["-"] + [m.name for m in SensorUsage],
    "SensorGroup":       ["-"] + [m.name for m in SensorGroup],
    "OutputFunction":    ["-"] + [m.name for m in OutputFunction],
    "OutputUsage":       ["-"] + [m.name for m in OutputUsage],
    "OutputMode":        ["-"] + [m.name for m in OutputMode],
    "ColorClass":        ["-"] + [m.name for m in ColorClass],
    "OutputChannelType": ["-"] + [m.name for m in OutputChannelType],
    "ButtonType":        ["-"] + [m.name for m in ButtonType],
    "ButtonGroup":       ["-"] + [m.name for m in ButtonGroup],
    "ButtonFunctionJoker": ["-"] + [m.name for m in ButtonFunctionJoker],
    "ButtonMode":        ["-"] + [m.name for m in ButtonMode],
}

ENUM_CLASS: dict[str, Any] = {
    "ColorGroup":        ColorGroup,
    "BinaryInputType":   BinaryInputType,
    "BinaryInputGroup":  BinaryInputGroup,
    "BinaryInputUsage":  BinaryInputUsage,
    "SensorType":        SensorType,
    "SensorUsage":       SensorUsage,
    "SensorGroup":       SensorGroup,
    "OutputFunction":    OutputFunction,
    "OutputUsage":       OutputUsage,
    "OutputMode":        OutputMode,
    "ColorClass":        ColorClass,
    "OutputChannelType": OutputChannelType,
    "ButtonType":        ButtonType,
    "ButtonGroup":       ButtonGroup,
    "ButtonFunctionJoker": ButtonFunctionJoker,
    "ButtonMode":        ButtonMode,
}

# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

def _build_columns() -> list[tuple[str, str | None, Any]]:
    cols: list[tuple[str, str | None, Any]] = [
        # Identity
        ("domain",       None, lambda e: e["domain"]),
        ("device_class", None, lambda e: e.get("device_class") or "-"),
        ("model",        None, lambda e: e.get("model") or "-"),
        ("model_uid",    None, lambda e: e.get("model_uid") or "-"),
        ("vendor_name",  None, lambda e: e.get("vendor_name") or "-"),

        # vdSD
        ("primary_group.USER",  "YesNo",      lambda e: "no"),
        ("primary_group.VALUE", "ColorGroup",  lambda e: enum_name(ColorGroup, e.get("primary_group"))),

        # binary_input
        ("bi.sensor_function.USER",  "YesNo",
         lambda e: "yes" if _has_choices(_sub(e, "binary_input"), "sensor_function") else "no"),
        ("bi.sensor_function.VALUE", "BinaryInputType",
         lambda e: enum_name(BinaryInputType, _sub(e, "binary_input").get("sensor_function"))),
        ("bi.group.USER",  "YesNo",
         lambda e: "yes" if _has_choices(_sub(e, "binary_input"), "group") else "no"),
        ("bi.group.VALUE", "BinaryInputGroup",
         lambda e: enum_name(BinaryInputGroup, _sub(e, "binary_input").get("group"))),
        ("bi.input_usage.USER",  "YesNo",
         lambda e: "yes" if _has_choices(_sub(e, "binary_input"), "input_usage") else "no"),
        ("bi.input_usage.VALUE", "BinaryInputUsage",
         lambda e: enum_name(BinaryInputUsage, _sub(e, "binary_input").get("input_usage"))),

        # sensor
        ("sensor.sensor_type.USER",  "YesNo",
         lambda e: "yes" if _has_choices(_sub(e, "sensor"), "sensor_type") else "no"),
        ("sensor.sensor_type.VALUE", "SensorType",
         lambda e: enum_name(SensorType, _sub(e, "sensor").get("sensor_type"))),
        ("sensor.sensor_usage.USER",  "YesNo",
         lambda e: "yes" if _has_choices(_sub(e, "sensor"), "sensor_usage") else "no"),
        ("sensor.sensor_usage.VALUE", "SensorUsage",
         lambda e: enum_name(SensorUsage, _sub(e, "sensor").get("sensor_usage"))),
        ("sensor.group.VALUE", "SensorGroup",
         lambda e: enum_name(SensorGroup, _sub(e, "sensor").get("group"))),
        ("sensor.min",                None, lambda e: _sub(e, "sensor").get("min")),
        ("sensor.max",                None, lambda e: _sub(e, "sensor").get("max")),
        ("sensor.resolution",         None, lambda e: _sub(e, "sensor").get("resolution")),
        ("sensor.update_interval",    None, lambda e: _sub(e, "sensor").get("update_interval")),
        ("sensor.alive_sign_interval",None, lambda e: _sub(e, "sensor").get("alive_sign_interval")),
        ("sensor.min_push_interval",  None, lambda e: _sub(e, "sensor").get("min_push_interval")),
        ("sensor.min_max_user", "YesNo",
         lambda e: "yes" if _sub(e, "sensor").get("min_max_user") else "no"),

        # output
        ("output.function.USER",  "YesNo",
         lambda e: "yes" if _has_choices(_sub(e, "output"), "function") else "no"),
        ("output.function.VALUE", "OutputFunction",
         lambda e: enum_name(OutputFunction, _sub(e, "output").get("function"))),
        ("output.output_usage.USER",  "YesNo",
         lambda e: "yes" if _has_choices(_sub(e, "output"), "output_usage") else "no"),
        ("output.output_usage.VALUE", "OutputUsage",
         lambda e: enum_name(OutputUsage, _sub(e, "output").get("output_usage"))),
        ("output.mode.VALUE",          "OutputMode",
         lambda e: enum_name(OutputMode, _sub(e, "output").get("mode"))),
        ("output.default_group.VALUE", "ColorClass",
         lambda e: enum_name(ColorClass, _sub(e, "output").get("default_group"))),
        ("output.variable_ramp", "YesNo",
         lambda e: "yes" if _sub(e, "output").get("variable_ramp") else "no"),
    ]
    # Channels 0-5
    for i in range(6):
        cols.append((
            f"output.ch{i}.channel_type.VALUE",
            "OutputChannelType",
            (lambda i: lambda e: _ch_type(e, i))(i),
        ))
    # button
    cols += [
        ("button.button_type.VALUE", "ButtonType",
         lambda e: enum_name(ButtonType, _sub(e, "button").get("button_type"))),
        ("button.group.USER",  "YesNo",
         lambda e: "yes" if _has_choices(_sub(e, "button"), "group") else "no"),
        ("button.group.VALUE", "ButtonGroup",
         lambda e: enum_name(ButtonGroup, _sub(e, "button").get("group"))),
        ("button.function.VALUE", "ButtonFunctionJoker",
         lambda e: enum_name(ButtonFunctionJoker, _sub(e, "button").get("function"))),
        ("button.mode.VALUE", "ButtonMode",
         lambda e: enum_name(ButtonMode, _sub(e, "button").get("mode"))),
    ]
    return cols


COLUMNS: list[tuple[str, str | None, Any]] = _build_columns()

# Convenience: header → 0-based index
HEADER_INDEX: dict[str, int] = {h: i for i, (h, _, _) in enumerate(COLUMNS)}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/pytest tests/test_mapping_excel.py::test_schema_columns_have_correct_structure \
                 tests/test_mapping_excel.py::test_schema_enum_options_all_present \
                 tests/test_mapping_excel.py::test_schema_extractors_on_known_entry -v
```

Expected: all 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/excel_schema.py tests/test_mapping_excel.py
git commit -m "feat: add excel_schema module with column definitions and extractors"
```

---

## Task 2: Create `tools/generate_mapping_excel.py`

**Files:**
- Create: `tools/generate_mapping_excel.py`
- Modify: `tests/test_mapping_excel.py` (add generator tests)

- [ ] **Step 1: Add failing tests to `tests/test_mapping_excel.py`**

Append to the existing file:

```python
def test_generate_creates_file_with_correct_shape(tmp_path):
    gen = _load("generate_mapping_excel", "tools/generate_mapping_excel.py")
    schema = _load("excel_schema", "tools/excel_schema.py")
    from custom_components.dsvdc4ha.entity_mapping import ENTITY_MAPPING
    import openpyxl

    out = tmp_path / "mapping.xlsx"
    gen.generate(output_path=out)

    wb = openpyxl.load_workbook(out, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    assert len(rows) == len(ENTITY_MAPPING) + 1  # header + data rows
    assert rows[0][0] == "domain"
    assert rows[0][1] == "device_class"
    assert len(rows[0]) == len(schema.COLUMNS)


def test_generate_writes_correct_enum_names(tmp_path):
    gen = _load("generate_mapping_excel", "tools/generate_mapping_excel.py")
    schema = _load("excel_schema", "tools/excel_schema.py")
    import openpyxl

    out = tmp_path / "mapping.xlsx"
    gen.generate(output_path=out)

    wb = openpyxl.load_workbook(out, read_only=True, data_only=True)
    ws = wb.active
    header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
    col_map = {v: i for i, v in enumerate(header_row) if v}

    rows = {
        (r[col_map["domain"]], r[col_map["device_class"]]): r
        for r in ws.iter_rows(min_row=2, values_only=True)
    }
    wb.close()

    # binary_sensor/None: sensor_function_choices="any" → USER=yes, VALUE=GENERIC
    row = rows[("binary_sensor", "-")]
    assert row[col_map["bi.sensor_function.USER"]] == "yes"
    assert row[col_map["bi.sensor_function.VALUE"]] == "GENERIC"
    assert row[col_map["bi.input_usage.USER"]] == "yes"
    assert row[col_map["bi.input_usage.VALUE"]] == "UNDEFINED"

    # binary_sensor/motion: no sensor_function_choices → USER=no, VALUE=MOTION
    row_m = rows[("binary_sensor", "motion")]
    assert row_m[col_map["bi.sensor_function.USER"]] == "no"
    assert row_m[col_map["bi.sensor_function.VALUE"]] == "MOTION"

    # cover/awning: ch0=SHADE_POSITION_OUTSIDE, ch1=-
    row_a = rows[("cover", "awning")]
    assert row_a[col_map["output.ch0.channel_type.VALUE"]] == "SHADE_POSITION_OUTSIDE"
    assert row_a[col_map["output.ch1.channel_type.VALUE"]] == "-"

    # sensor/temperature: sensor_usage_choices → USER=yes
    row_t = rows[("sensor", "temperature")]
    assert row_t[col_map["sensor.sensor_usage.USER"]] == "yes"

    # light/None: primary_group.USER always "no"
    row_l = rows[("light", "-")]
    assert row_l[col_map["primary_group.USER"]] == "no"


def test_generate_creates_lookups_sheet(tmp_path):
    gen = _load("generate_mapping_excel", "tools/generate_mapping_excel.py")
    import openpyxl

    out = tmp_path / "mapping.xlsx"
    gen.generate(output_path=out)

    wb = openpyxl.load_workbook(out, read_only=True)
    assert "_lookups" in wb.sheetnames
    # Hidden sheet has YesNo values in first column
    ws_lk = wb["_lookups"]
    first_col = [r[0].value for r in ws_lk.iter_rows(min_row=1, max_row=2)]
    assert "yes" in first_col
    wb.close()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_mapping_excel.py::test_generate_creates_file_with_correct_shape -v 2>&1 | head -10
```

Expected: FAIL — module not found.

- [ ] **Step 3: Create `tools/generate_mapping_excel.py`**

```python
"""Generate ha_vdsd_mapping.xlsx from entity_mapping.py and pydsvdcapi enums.

Usage:
    python tools/generate_mapping_excel.py
    python tools/generate_mapping_excel.py path/to/output.xlsx
"""
from __future__ import annotations
import importlib.util, pathlib, sys

_REPO_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

import openpyxl
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

from tools.excel_schema import COLUMNS, ENUM_OPTIONS


def _load_entity_mapping():
    spec = importlib.util.spec_from_file_location(
        "entity_mapping",
        _REPO_ROOT / "custom_components/dsvdc4ha/entity_mapping.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ENTITY_MAPPING


_FILL_HEADER = PatternFill("solid", fgColor="4472C4")   # blue
_FILL_USER   = PatternFill("solid", fgColor="E2EFDA")   # light green
_FONT_HEADER = Font(color="FFFFFF", bold=True)
_FONT_USER_H = Font(color="375623", bold=True)


def _write_lookups(wb: openpyxl.Workbook) -> dict[str, str]:
    """Create hidden _lookups sheet; return {enum_key: range_ref} for DataValidation."""
    ws = wb.create_sheet("_lookups")
    ws.sheet_state = "hidden"
    refs: dict[str, str] = {}
    for col_idx, (key, options) in enumerate(ENUM_OPTIONS.items(), 1):
        col_l = get_column_letter(col_idx)
        for row_idx, opt in enumerate(options, 1):
            ws.cell(row=row_idx, column=col_idx, value=opt)
        refs[key] = f"_lookups!${col_l}$1:${col_l}${len(options)}"
    return refs


def generate(
    entity_mapping=None,
    output_path: str | pathlib.Path = "documents/ha_vdsd_mapping.xlsx",
) -> pathlib.Path:
    """Generate the mapping Excel file. Pass entity_mapping to override (useful in tests)."""
    if entity_mapping is None:
        entity_mapping = _load_entity_mapping()
    output_path = pathlib.Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Mapping"

    lookup_refs = _write_lookups(wb)

    # Header row
    for col_idx, (header, enum_key, _) in enumerate(COLUMNS, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        if enum_key == "YesNo":
            cell.fill = _FILL_USER
            cell.font = _FONT_USER_H
        else:
            cell.fill = _FILL_HEADER
            cell.font = _FONT_HEADER
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[1].height = 36
    ws.freeze_panes = "C2"

    # Data rows
    n_rows = len(entity_mapping)
    for row_idx, entry in enumerate(entity_mapping, 2):
        for col_idx, (_, _, extractor) in enumerate(COLUMNS, 1):
            ws.cell(row=row_idx, column=col_idx, value=extractor(entry))

    # DataValidation dropdowns — one DV per column that has an enum_key
    for col_idx, (_, enum_key, _) in enumerate(COLUMNS, 1):
        if enum_key is None:
            continue
        col_l = get_column_letter(col_idx)
        dv = DataValidation(
            type="list",
            formula1=lookup_refs[enum_key],
            allow_blank=True,
            showErrorMessage=False,
        )
        dv.sqref = f"{col_l}2:{col_l}{n_rows + 1}"
        ws.add_data_validation(dv)

    # Column widths
    for col_idx, (header, _, _) in enumerate(COLUMNS, 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = max(len(header) + 2, 14)

    wb.save(output_path)
    print(f"✓ Generated {output_path} ({n_rows} rows, {len(COLUMNS)} columns)")
    return output_path


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    path = args[0] if args else "documents/ha_vdsd_mapping.xlsx"
    generate(output_path=path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_mapping_excel.py::test_generate_creates_file_with_correct_shape \
                 tests/test_mapping_excel.py::test_generate_writes_correct_enum_names \
                 tests/test_mapping_excel.py::test_generate_creates_lookups_sheet -v
```

Expected: all 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/generate_mapping_excel.py tests/test_mapping_excel.py
git commit -m "feat: add generate_mapping_excel.py to produce enum-name Excel with USER/VALUE dropdowns"
```

---

## Task 3: Update `tools/audit_mapping.py`

**Files:**
- Modify: `tools/audit_mapping.py`
- Modify: `tests/test_mapping_excel.py` (add audit tests)

The current audit reads hardcoded column index offsets and uses `_parse_scalar` to parse "USER — default: X(n)" style text. Replace the xlsx reading logic entirely: find columns by header name, parse VALUE cells as enum names, check USER yes/no against presence of `*_choices` in entity_mapping.py. The `run_audit()` signature, discrepancy/missing_entries return format, `_print_table()`, and `main()` are preserved.

- [ ] **Step 1: Add failing tests to `tests/test_mapping_excel.py`**

Append to the existing file:

```python
def test_audit_passes_on_freshly_generated_excel(tmp_path):
    gen   = _load("generate_mapping_excel", "tools/generate_mapping_excel.py")
    audit = _load("audit_mapping",          "tools/audit_mapping.py")

    out = tmp_path / "mapping.xlsx"
    gen.generate(output_path=out)

    result = audit.run_audit(str(out))
    assert result["discrepancies"] == [], (
        f"Unexpected discrepancies:\n" +
        "\n".join(str(d) for d in result["discrepancies"])
    )
    assert result["missing_entries"] == []


def test_audit_detects_wrong_value(tmp_path):
    import openpyxl
    gen   = _load("generate_mapping_excel", "tools/generate_mapping_excel.py")
    audit = _load("audit_mapping",          "tools/audit_mapping.py")
    schema = _load("excel_schema",          "tools/excel_schema.py")

    out = tmp_path / "mapping.xlsx"
    gen.generate(output_path=out)

    # Corrupt binary_sensor/motion: change bi.sensor_function.VALUE from MOTION → SMOKE
    wb = openpyxl.load_workbook(out)
    ws = wb.active
    sf_col = schema.HEADER_INDEX["bi.sensor_function.VALUE"] + 1  # 1-based
    for row in ws.iter_rows(min_row=2):
        if row[0].value == "binary_sensor" and row[1].value == "motion":
            row[sf_col - 1].value = "SMOKE"
            break
    wb.save(out)

    result = audit.run_audit(str(out))
    assert any(
        d["domain"] == "binary_sensor"
        and d["device_class"] == "motion"
        and d["field"] == "sensor_function"
        for d in result["discrepancies"]
    ), f"Expected discrepancy not in: {result['discrepancies']}"


def test_audit_detects_wrong_user_flag(tmp_path):
    import openpyxl
    gen   = _load("generate_mapping_excel", "tools/generate_mapping_excel.py")
    audit = _load("audit_mapping",          "tools/audit_mapping.py")
    schema = _load("excel_schema",          "tools/excel_schema.py")

    out = tmp_path / "mapping.xlsx"
    gen.generate(output_path=out)

    # Corrupt binary_sensor/motion: change bi.group.USER from "no" to "yes"
    # (motion has no group_choices, so "yes" is wrong)
    wb = openpyxl.load_workbook(out)
    ws = wb.active
    gu_col = schema.HEADER_INDEX["bi.group.USER"] + 1
    for row in ws.iter_rows(min_row=2):
        if row[0].value == "binary_sensor" and row[1].value == "motion":
            row[gu_col - 1].value = "yes"
            break
    wb.save(out)

    result = audit.run_audit(str(out))
    assert any(
        d["domain"] == "binary_sensor"
        and d["device_class"] == "motion"
        and "group" in d["field"]
        and "USER" in d["field"]
        for d in result["discrepancies"]
    ), f"Expected USER discrepancy not in: {result['discrepancies']}"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_mapping_excel.py::test_audit_passes_on_freshly_generated_excel -v 2>&1 | tail -10
```

Expected: FAIL — current audit can't read the new Excel format.

- [ ] **Step 3: Rewrite `tools/audit_mapping.py`**

Replace the full content of `tools/audit_mapping.py` with:

```python
"""Audit ENTITY_MAPPING against the generated ha_vdsd_mapping.xlsx.

Usage:
    python tools/audit_mapping.py                    # use default xlsx path
    python tools/audit_mapping.py path/to/other.xlsx # override path
"""
from __future__ import annotations
import pathlib, sys

_REPO_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

try:
    import openpyxl as _openpyxl
    _OPENPYXL_AVAILABLE = True
except ImportError:
    _OPENPYXL_AVAILABLE = False
    _openpyxl = None

import importlib.util

from tools.excel_schema import ENUM_CLASS, enum_value


def _load_entity_mapping():
    spec = importlib.util.spec_from_file_location(
        "entity_mapping",
        _REPO_ROOT / "custom_components" / "dsvdc4ha" / "entity_mapping.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_em = _load_entity_mapping()
ENTITY_MAPPING = _em.ENTITY_MAPPING

_SKIP_DOMAINS   = {"weather"}
_SKIP_ENTITY_NONE = {"event"}
_SKIP_DC_FRAGMENTS = {"(as button", "rgbw", "rgbww"}
_SKIP_BTN_DC    = {"identify", "restart", "update"}


def _build_mapping_index() -> dict[tuple, dict]:
    return {(e["domain"], e["device_class"]): e for e in ENTITY_MAPPING}


def run_audit(xlsx_path: str = "documents/ha_vdsd_mapping.xlsx") -> dict:
    if not _OPENPYXL_AVAILABLE:
        raise ImportError("openpyxl is required: pip install openpyxl")
    xlsx_path = pathlib.Path(xlsx_path)
    if not xlsx_path.exists():
        raise FileNotFoundError(f"xlsx not found: {xlsx_path}")

    wb = _openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.active

    mapping_idx = _build_mapping_index()
    discrepancies: list[dict] = []
    missing_entries: list[dict] = []
    col_map: dict[str, int] = {}  # header name → 0-based column index

    def _dis(domain, dc, component, field, expected, actual):
        discrepancies.append({
            "domain": domain, "device_class": dc,
            "component": component, "field": field,
            "expected": expected, "actual": actual,
        })

    for row_idx, row in enumerate(ws.iter_rows(min_row=1, values_only=True), 1):
        # First row builds column map
        if row_idx == 1:
            col_map = {
                str(v).strip(): i
                for i, v in enumerate(row)
                if v is not None
            }
            continue

        def get(header):
            idx = col_map.get(header)
            return row[idx] if idx is not None and idx < len(row) else None

        domain = str(get("domain") or "").strip()
        dc_raw = get("device_class")
        dc = None if (not dc_raw or str(dc_raw).strip() == "-") else str(dc_raw).strip()

        if not domain:
            continue
        if domain in _SKIP_DOMAINS:
            continue
        if domain in _SKIP_ENTITY_NONE and dc is None:
            continue
        if dc and any(frag in dc.lower() for frag in _SKIP_DC_FRAGMENTS):
            continue
        if domain == "button" and dc in _SKIP_BTN_DC:
            continue

        entry = mapping_idx.get((domain, dc))
        if entry is None:
            missing_entries.append({"domain": domain, "device_class": dc, "xlsx_row": row_idx})
            continue

        def chk_val(component, field, enum_key, header, actual):
            """Check VALUE column: parse enum name → integer, compare to actual."""
            raw = get(header)
            if raw is None or str(raw).strip() == "-":
                return
            exp = enum_value(ENUM_CLASS[enum_key], str(raw).strip())
            if exp is None:
                return
            if int(actual) != exp:
                _dis(domain, dc, component, field, exp, actual)

        def chk_user(component, field, header, has_choices: bool):
            """Check USER column: 'yes'/'no' must match has_choices."""
            raw = get(header)
            if raw is None:
                return
            expected = "yes" if has_choices else "no"
            if str(raw).strip().lower() != expected:
                _dis(domain, dc, component, f"{field}.USER", expected, str(raw).strip().lower())

        # Identity
        for field, header in [("model", "model"), ("model_uid", "model_uid"), ("vendor_name", "vendor_name")]:
            raw = get(header)
            if raw and str(raw).strip() not in ("-", ""):
                exp = str(raw).strip()
                actual = entry.get(field)
                if actual != exp:
                    _dis(domain, dc, "identity", field, exp, actual)

        # primary_group
        chk_val("vdsd", "primary_group", "ColorGroup", "primary_group.VALUE", entry.get("primary_group", 0))

        # binary_input
        if bi := entry.get("binary_input"):
            chk_val("binary_input", "sensor_function", "BinaryInputType",
                    "bi.sensor_function.VALUE", bi.get("sensor_function", 0))
            chk_user("binary_input", "sensor_function", "bi.sensor_function.USER",
                     bool(bi.get("sensor_function_choices")))
            chk_val("binary_input", "group", "BinaryInputGroup",
                    "bi.group.VALUE", bi.get("group", 0))
            chk_user("binary_input", "group", "bi.group.USER",
                     bool(bi.get("group_choices")))
            chk_val("binary_input", "input_usage", "BinaryInputUsage",
                    "bi.input_usage.VALUE", bi.get("input_usage", 0))
            chk_user("binary_input", "input_usage", "bi.input_usage.USER",
                     bool(bi.get("input_usage_choices")))

        # sensor
        if s := entry.get("sensor"):
            chk_val("sensor", "sensor_type", "SensorType",
                    "sensor.sensor_type.VALUE", s.get("sensor_type", 0))
            chk_user("sensor", "sensor_type", "sensor.sensor_type.USER",
                     bool(s.get("sensor_type_choices")))
            chk_val("sensor", "sensor_usage", "SensorUsage",
                    "sensor.sensor_usage.VALUE", s.get("sensor_usage", 0))
            chk_user("sensor", "sensor_usage", "sensor.sensor_usage.USER",
                     bool(s.get("sensor_usage_choices")))
            chk_val("sensor", "group", "SensorGroup",
                    "sensor.group.VALUE", s.get("group", 0))
            for field in ("min", "max", "resolution", "update_interval",
                          "alive_sign_interval", "min_push_interval"):
                raw = get(f"sensor.{field}")
                if raw is not None and str(raw).strip() not in ("-", ""):
                    try:
                        exp = float(raw)
                    except (ValueError, TypeError):
                        continue
                    actual = s.get(field)
                    if actual is not None and abs(float(actual) - exp) > 1e-9:
                        _dis(domain, dc, "sensor", field, exp, actual)
            chk_user("sensor", "min_max", "sensor.min_max_user",
                     bool(s.get("min_max_user")))

        # output
        if o := entry.get("output"):
            chk_val("output", "function", "OutputFunction",
                    "output.function.VALUE", o.get("function", 0))
            chk_user("output", "function", "output.function.USER",
                     bool(o.get("function_choices")))
            chk_val("output", "output_usage", "OutputUsage",
                    "output.output_usage.VALUE", o.get("output_usage", 0))
            chk_user("output", "output_usage", "output.output_usage.USER",
                     bool(o.get("output_usage_choices")))
            chk_val("output", "mode", "OutputMode",
                    "output.mode.VALUE", o.get("mode", 0))
            if o.get("default_group") is not None:
                chk_val("output", "default_group", "ColorClass",
                        "output.default_group.VALUE", o.get("default_group"))
            raw_vr = get("output.variable_ramp")
            if raw_vr is not None:
                exp_vr = str(raw_vr).strip().lower() == "yes"
                if bool(o.get("variable_ramp")) != exp_vr:
                    _dis(domain, dc, "output", "variable_ramp", exp_vr, o.get("variable_ramp"))
            channels = o.get("channels") or []
            for i in range(6):
                raw_ct = get(f"output.ch{i}.channel_type.VALUE")
                if raw_ct is None or str(raw_ct).strip() == "-":
                    break
                exp_ct = enum_value(ENUM_CLASS["OutputChannelType"], str(raw_ct).strip())
                if exp_ct is None:
                    continue
                actual_ct = channels[i]["channel_type"] if i < len(channels) else None
                if actual_ct is None or int(actual_ct) != exp_ct:
                    _dis(domain, dc, "output", f"channels[{i}].channel_type", exp_ct, actual_ct)

        # button
        if b := entry.get("button"):
            chk_val("button", "button_type", "ButtonType",
                    "button.button_type.VALUE", b.get("button_type", 0))
            chk_val("button", "group", "ButtonGroup",
                    "button.group.VALUE", b.get("group", 0))
            chk_user("button", "group", "button.group.USER",
                     bool(b.get("group_choices")))
            chk_val("button", "function", "ButtonFunctionJoker",
                    "button.function.VALUE", b.get("function", 0))
            chk_val("button", "mode", "ButtonMode",
                    "button.mode.VALUE", b.get("mode", 0))

    wb.close()
    return {"discrepancies": discrepancies, "missing_entries": missing_entries}


def _print_table(rows: list[dict], headers: list[str], keys: list[str]) -> None:
    if not rows:
        return
    widths = [len(h) for h in headers]
    for r in rows:
        for i, k in enumerate(keys):
            widths[i] = max(widths[i], len(str(r.get(k, ""))))
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print(fmt.format(*[str(r.get(k, "")) for k in keys]))


def main(argv=None) -> int:
    path = argv[0] if argv else "documents/ha_vdsd_mapping.xlsx"
    result = run_audit(path)
    discrepancies = result["discrepancies"]
    missing = result["missing_entries"]

    if missing:
        print(f"\n⚠  {len(missing)} xlsx row(s) have no ENTITY_MAPPING entry (non-blocking):")
        _print_table(missing, ["domain", "device_class", "xlsx_row"],
                     ["domain", "device_class", "xlsx_row"])

    if discrepancies:
        print(f"\n✗  {len(discrepancies)} discrepancy(ies) found:")
        _print_table(
            discrepancies,
            ["domain", "device_class", "component", "field", "expected", "actual"],
            ["domain", "device_class", "component", "field", "expected", "actual"],
        )
        return 1

    msg = f"({len(missing)} missing entries reported above.)" if missing else ""
    print(f"\n✓  All checked fields match. {msg}".rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run the audit tests**

```bash
.venv/bin/pytest tests/test_mapping_excel.py::test_audit_passes_on_freshly_generated_excel \
                 tests/test_mapping_excel.py::test_audit_detects_wrong_value \
                 tests/test_mapping_excel.py::test_audit_detects_wrong_user_flag -v
```

Expected: all 3 PASS.

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
.venv/bin/pytest tests/ -q 2>&1 | tail -5
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add tools/audit_mapping.py tests/test_mapping_excel.py
git commit -m "feat: rewrite audit_mapping.py to read new enum-name Excel format with USER/VALUE columns"
```

---

## Task 4: Generate the Excel and verify

**Files:** (no code changes — this task runs the generator and verifies the result)

- [ ] **Step 1: Generate the Excel**

```bash
cd /home/arne/Development/dsvdc4ha
.venv/bin/python tools/generate_mapping_excel.py
```

Expected output:
```
✓ Generated documents/ha_vdsd_mapping.xlsx (N rows, M columns)
```

where N = number of ENTITY_MAPPING entries and M = number of COLUMNS.

- [ ] **Step 2: Verify audit passes on the generated file**

```bash
.venv/bin/python tools/audit_mapping.py
```

Expected:
```
✓  All checked fields match.
```

If any discrepancies are reported, they indicate a bug in the generator (extractor functions returning wrong values). Fix by updating the extractor in `tools/excel_schema.py` — do NOT modify entity_mapping.py or the xlsx file.

- [ ] **Step 3: Open and inspect the Excel**

Open `documents/ha_vdsd_mapping.xlsx` in Excel/LibreOffice and verify:
- Row 1 has color-coded headers (blue for VALUE columns, green for USER columns)
- Clicking a VALUE cell shows the enum-name dropdown
- Clicking a USER cell shows yes/no dropdown
- `-` appears in inapplicable cells (e.g., binary_sensor rows have `-` in all output.* VALUE columns)

- [ ] **Step 4: Run all tests**

```bash
.venv/bin/pytest tests/ -q 2>&1 | tail -5
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add tools/generate_mapping_excel.py tools/excel_schema.py tools/audit_mapping.py
git commit -m "chore: add generated ha_vdsd_mapping.xlsx placeholder commit (file is gitignored)"
```

Note: `documents/ha_vdsd_mapping.xlsx` is gitignored so the file won't be committed. The commit message documents that generation was verified.

---

## Self-Review

**Spec coverage:**
- ✅ Generator creates Excel with USER/VALUE column pairs for every enum property (Tasks 1–2)
- ✅ VALUE dropdowns list all enum member names + `-` (Task 1: ENUM_OPTIONS)
- ✅ USER dropdowns show yes/no reflecting presence of `*_choices` in entity_mapping.py (Task 1: `_has_choices`)
- ✅ `-` used when property doesn't apply to an entity/device_class (Task 1: `enum_name` returns `-` for None)
- ✅ Hidden `_lookups` sheet backs all dropdowns (Task 2: `_write_lookups`)
- ✅ Audit reads new format by header name (Task 3)
- ✅ Audit validates VALUE (enum name → integer) against entity_mapping.py (Task 3: `chk_val`)
- ✅ Audit validates USER yes/no against presence of `*_choices` (Task 3: `chk_user`)
- ✅ Generator is re-runnable to pick up new pydsvdcapi enum members (enum options derived from enum at import time)
- ✅ Audit passes 0 discrepancies on freshly generated Excel (Task 4)
- ✅ Script kept in project at `tools/generate_mapping_excel.py` (spec: "kept in the project")

**Placeholder scan:** None found.

**Type consistency:** `enum_name` and `enum_value` are defined in `excel_schema.py` and used with the same signatures in both generator and audit. `ENUM_CLASS` dict keys match `ENUM_OPTIONS` keys throughout.

**Edge cases covered:**
- `device_class=None` entries: extractor returns `"-"`, stored as `"-"` in Excel; audit treats `"-"` as missing `device_class` (dc=None) for lookup
- `sensor_function_choices="any"` is truthy → USER=yes (correct: user has full choice)
- `sensor.min_max_user=True` → `sensor.min_max_user` column = "yes" (field name differs from `*_choices` pattern; handled separately)
- `output.variable_ramp` is boolean, not an enum → YesNo dropdown, not VALUE
- Channels beyond index 5 in entity_mapping.py would be silently omitted; current data has max 2 channels per entry
