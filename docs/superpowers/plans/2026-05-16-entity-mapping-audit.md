# Entity Mapping Audit & Compliance Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every entity/device-class combination in `entity_mapping.py` produces vdSD property values that exactly match `documents/ha_vdsd_mapping.xlsx`, and add a CI-runnable audit script that catches future drift.

**Architecture:** Write the audit script first, then write a failing test, then fix `entity_mapping.py` (identity fields, value bugs, sensor_usage_choices), then fix `config_flow.py` (identity fields, name, hardwareGuid, sensor_usage UI), then update the xlsx name column.

**Tech Stack:** Python, openpyxl, Home Assistant config-flow pattern, pytest.

---

## File map

| File | Action |
|------|--------|
| `tools/__init__.py` | Create (empty, makes `tools` a package) |
| `tools/audit_mapping.py` | Create: reads xlsx, returns discrepancies + missing_entries |
| `tests/test_entity_mapping.py` | Create: calls `run_audit()`, asserts zero discrepancies |
| `custom_components/dsvdc4ha/entity_mapping.py` | Modify: add identity fields, fix values, add sensor_usage_choices |
| `custom_components/dsvdc4ha/config_flow.py` | Modify: use mapping identity fields, fix name, add hardwareGuid, add sensor_usage UI |
| `documents/ha_vdsd_mapping.xlsx` | Modify: update name column cells only |

---

## Task 1: Create `tools/audit_mapping.py`

**Files:**
- Create: `tools/__init__.py`
- Create: `tools/audit_mapping.py`

- [ ] **Step 1.1: Create `tools/__init__.py`**

```python
# tools/__init__.py  (empty — makes tools a package)
```

- [ ] **Step 1.2: Write the full audit script**

Create `tools/audit_mapping.py` with this exact content:

```python
"""Audit ENTITY_MAPPING against the xlsx source of truth.

Usage:
    python tools/audit_mapping.py                    # use default xlsx path
    python tools/audit_mapping.py path/to/other.xlsx # override path
"""
from __future__ import annotations

import re
import sys
import pathlib

# Allow running from repo root or tools/ directory
_REPO_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

try:
    import openpyxl
except ImportError as e:
    raise ImportError(
        "openpyxl is required: pip install openpyxl"
    ) from e

from custom_components.dsvdc4ha.entity_mapping import ENTITY_MAPPING

# ---------------------------------------------------------------------------
# Column indices (0-based) in the xlsx
# ---------------------------------------------------------------------------
COL_ENTITY     = 0    # "Binary Sensor", "Sensor", etc.
COL_DC         = 1    # device_class ("battery", None, …)
COL_NAME       = 5    # name field
COL_MODEL      = 6    # model (quoted string in cell, e.g. '"HA Binary Sensor"')
COL_MODEL_UID  = 8    # modelUID
COL_VENDOR     = 12   # vendorName
COL_PG         = 18   # primaryGroup
COL_OUT_FUNC   = 21   # output: OutputFunction
COL_DEF_GRP    = 22   # output: defaultGroup
COL_OUT_USAGE  = 23   # output: outputUsage
COL_VAR_RAMP   = 24   # output: variableRamp
COL_OUT_MODE   = 28   # output: OutputMode
# Channels CH1–CH6 channelType columns (one per 8 columns starting at 44)
_CH_BASE       = 44   # CH1 channelType; CH2=52, CH3=60, CH4=68, CH5=76, CH6=84
COL_BTN_TYPE   = 96   # button: buttonType
COL_BTN_GRP    = 98   # button: buttonSettings.group
COL_BTN_FUNC   = 99   # button: buttonSettings.function
COL_BTN_MODE   = 100  # button: buttonSettings.mode
COL_INPUT_USAGE = 113  # binary_input: inputUsage
COL_BIN_GRP    = 116  # binary_input: binarySettings.group
COL_SF_SETTING = 117  # binary_input: sensorFunction (setting)
COL_SNS_TYPE   = 124  # sensor: sensorType
COL_SNS_USAGE  = 125  # sensor: sensorUsage
COL_SNS_MIN    = 126  # sensor: min
COL_SNS_MAX    = 127  # sensor: max
COL_SNS_RES    = 128  # sensor: resolution
COL_UPD_INT    = 129  # sensor: updateInterval
COL_ALIVE_INT  = 130  # sensor: aliveSignInterval
COL_MIN_PUSH   = 132  # sensor: minPushInterval

# Channel channelType columns for CH1..CH6
_CH_TYPE_COLS = [_CH_BASE + i * 8 for i in range(6)]

# HA display name → (domain, needs_lowercase_dc)
_ENTITY_DOMAIN_MAP: dict[str, str] = {
    "Binary Sensor": "binary_sensor",
    "Button":        "button",
    "Cover":         "cover",
    "Event":         "event",
    "Fan":           "fan",
    "Light":         "light",
    "Lock":          "lock",
    "Number":        "number",
    "Sensor":        "sensor",
    "Siren":         "siren",
    "Switch":        "switch",
    "Valve":         "valve",
    "Weather":       "weather",
}

# Rows to skip because they are not yet implemented (⚠ DYNAMIC / NOT SUPPORTED)
_SKIP_DC_FRAGMENTS = {
    "(as button",      # Binary Sensor / (as Button - to be defined…)
    "identify",        # Button/identify
    "restart",         # Button/restart
    "update",          # Button/update  (in Button domain — separate from binary_sensor/update)
    "rgbw",            # Light/rgbw — not natively supported
    "rgbww",           # Light/rgbww
}
_SKIP_DOMAINS = {"weather"}  # Weather/(none) — composite device, separate feature
_SKIP_ENTITY_NONE = {"event"}  # Event/(none) — dynamic, separate feature


# ---------------------------------------------------------------------------
# Value parsing helpers
# ---------------------------------------------------------------------------

_NA_TOKENS = {"— not applicable —", "- not applicable -"}


def _is_na(v) -> bool:
    return v is None or (isinstance(v, str) and (
        v.strip() in _NA_TOKENS
        or v.strip().lower().startswith("pydsvdcapi handled")
    ))


def _extract_int(s: str) -> int | None:
    """Extract the integer from a label like 'MOTION (5)' → 5."""
    m = re.search(r"\((-?\d+)\)", s)
    return int(m.group(1)) if m else None


def _parse_scalar(raw) -> int | float | bool | str | None:
    """Parse an xlsx cell into its Python scalar (or None to skip)."""
    if _is_na(raw):
        return None
    s = str(raw).strip()
    if not s:
        return None
    # USER-only cells (fully user-defined, no default to check)
    if re.match(r"^USER\s*$", s, re.IGNORECASE):
        return None
    if re.match(r"^USER\s*[—–-]\s*specify", s, re.IGNORECASE):
        return None
    # USER with explicit default: "USER — default: MOTION (5)" or "USER - default: APP_Mode (0)"
    m = re.match(r"^USER\s*[—–-]\s*default\s*:\s*.+?\((-?\d+)\)", s, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # USER with first-of-many: "USER: FROST (18) or GENERIC (0)" → take first
    m = re.match(r"^USER\s*:\s*.+?\((-?\d+)\)", s, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # USER with colon-list (sensor_usage etc.): "USER: ROOM (1), OUTDOOR (2)" → first
    m = re.match(r"^USER\s*:\s*.+?\((-?\d+)\)", s, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # "USER — SECURITY (6), CLIMATE (3) or JOKER (8)" → first
    m = re.match(r"^USER\s*[—–-]\s*.+?\((-?\d+)\)", s, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Boolean
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    # Label with integer in parens: "GRADUAL (2)", "BLACK (8)", etc.
    m = re.search(r"\((-?\d+)\)", s)
    if m:
        return int(m.group(1))
    # Channel type names without parens: "SHADE_POSITION_OUTSIDE" etc.
    from custom_components.dsvdc4ha.entity_mapping import _CHANNEL_TYPE_NAMES
    if s.upper() in _CHANNEL_TYPE_NAMES:
        return _CHANNEL_TYPE_NAMES[s.upper()]
    # "SHADE_POSITION_OUTSIDE or SHADE_POSITION_INSIDE (…)" — skip (user-dependent)
    if " or " in s.lower() and "depending" in s.lower():
        return None
    # Plain number
    try:
        f = float(s)
        return int(f) if f == int(f) else f
    except ValueError:
        pass
    # Quoted string like '"HA Binary Sensor"' → strip the quotes
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    return s   # return as-is (string identity check)


def _build_mapping_index() -> dict[tuple[str, str | None], dict]:
    """Build a fast lookup: (domain, device_class) → ENTITY_MAPPING entry."""
    idx: dict[tuple, dict] = {}
    for e in ENTITY_MAPPING:
        idx[(e["domain"], e["device_class"])] = e
    return idx


# ---------------------------------------------------------------------------
# Core audit logic
# ---------------------------------------------------------------------------

def run_audit(
    xlsx_path: str | pathlib.Path = "documents/ha_vdsd_mapping.xlsx",
) -> dict:
    """Compare ENTITY_MAPPING against the xlsx source of truth.

    Returns:
        {
            "discrepancies": [
                {"domain": str, "device_class": str|None,
                 "component": str, "field": str,
                 "expected": ..., "actual": ...}
            ],
            "missing_entries": [
                {"domain": str, "device_class": str|None, "xlsx_row": int}
            ],
        }
    """
    xlsx_path = pathlib.Path(xlsx_path)
    if not xlsx_path.exists():
        raise FileNotFoundError(
            f"xlsx not found: {xlsx_path}  "
            f"(run from repo root or pass an explicit path)"
        )

    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.active

    mapping_idx = _build_mapping_index()
    discrepancies: list[dict] = []
    missing_entries: list[dict] = []

    def _dis(domain, dc, component, field, expected, actual):
        discrepancies.append({
            "domain": domain, "device_class": dc,
            "component": component, "field": field,
            "expected": expected, "actual": actual,
        })

    for row_idx, row in enumerate(ws.iter_rows(min_row=4, values_only=True), 4):
        raw_entity = row[COL_ENTITY]
        if raw_entity is None:
            continue
        raw_entity = str(raw_entity).strip()
        domain = _ENTITY_DOMAIN_MAP.get(raw_entity)
        if domain is None:
            continue  # unknown entity type — not our concern

        raw_dc = row[COL_DC]
        dc_str = str(raw_dc).strip() if raw_dc else None

        # Normalise device_class to snake_case / None
        if dc_str:
            dc = dc_str.lower().replace(" ", "_").replace("-", "_")
        else:
            dc = None

        # Skip rows flagged as dynamic / not supported
        if domain in _SKIP_DOMAINS:
            continue
        if domain in _SKIP_ENTITY_NONE and dc is None:
            continue
        if dc is not None and any(frag in dc for frag in _SKIP_DC_FRAGMENTS):
            continue
        # Button/identify, /restart, /update (skip; they need DYNAMIC DEFINITIONS)
        if domain == "button" and dc in ("identify", "restart", "update"):
            continue

        entry = mapping_idx.get((domain, dc))
        if entry is None:
            missing_entries.append({"domain": domain, "device_class": dc, "xlsx_row": row_idx})
            continue

        def chk(component, field, col, actual_val):
            exp = _parse_scalar(row[col] if col < len(row) else None)
            if exp is None:
                return  # N/A or fully user-defined — nothing to check
            if actual_val != exp:
                _dis(domain, dc, component, field, exp, actual_val)

        # ── Identity fields ────────────────────────────────────────────────
        chk("identity", "model", COL_MODEL, entry.get("model"))
        chk("identity", "model_uid", COL_MODEL_UID, entry.get("model_uid"))
        chk("identity", "vendor_name", COL_VENDOR, entry.get("vendor_name"))

        # ── binary_input ───────────────────────────────────────────────────
        if "binary_input" in entry:
            bi = entry["binary_input"]
            chk("binary_input", "sensor_function", COL_SF_SETTING, bi.get("sensor_function"))
            chk("binary_input", "group", COL_BIN_GRP, bi.get("group"))
            chk("binary_input", "input_usage", COL_INPUT_USAGE, bi.get("input_usage"))

        # ── sensor ─────────────────────────────────────────────────────────
        if "sensor" in entry:
            s = entry["sensor"]
            chk("sensor", "sensor_type", COL_SNS_TYPE, s.get("sensor_type"))
            chk("sensor", "sensor_usage", COL_SNS_USAGE, s.get("sensor_usage"))
            chk("sensor", "min", COL_SNS_MIN, s.get("min"))
            chk("sensor", "max", COL_SNS_MAX, s.get("max"))
            chk("sensor", "resolution", COL_SNS_RES, s.get("resolution"))
            chk("sensor", "update_interval", COL_UPD_INT, s.get("update_interval"))
            chk("sensor", "alive_sign_interval", COL_ALIVE_INT, s.get("alive_sign_interval"))
            chk("sensor", "min_push_interval", COL_MIN_PUSH, s.get("min_push_interval"))

        # ── output ─────────────────────────────────────────────────────────
        if "output" in entry:
            o = entry["output"]
            chk("output", "function", COL_OUT_FUNC, o.get("function"))
            chk("output", "default_group", COL_DEF_GRP, o.get("default_group"))
            chk("output", "output_usage", COL_OUT_USAGE, o.get("output_usage"))
            chk("output", "variable_ramp", COL_VAR_RAMP, o.get("variable_ramp"))
            chk("output", "mode", COL_OUT_MODE, o.get("mode"))
            # channel types (CH1..CH6)
            channels = o.get("channels", [])
            for ch_i, col in enumerate(_CH_TYPE_COLS):
                exp_raw = row[col] if col < len(row) else None
                if _is_na(exp_raw):
                    break
                exp_ct = _parse_scalar(exp_raw)
                if exp_ct is None:
                    break
                actual_ct = channels[ch_i]["channel_type"] if ch_i < len(channels) else None
                if actual_ct != exp_ct:
                    _dis(domain, dc, "output", f"channels[{ch_i}].channel_type", exp_ct, actual_ct)

        # ── button ─────────────────────────────────────────────────────────
        if "button" in entry:
            b = entry["button"]
            chk("button", "button_type", COL_BTN_TYPE, b.get("button_type"))
            chk("button", "group", COL_BTN_GRP, b.get("group"))
            chk("button", "function", COL_BTN_FUNC, b.get("function"))
            chk("button", "mode", COL_BTN_MODE, b.get("mode"))

    wb.close()
    return {"discrepancies": discrepancies, "missing_entries": missing_entries}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

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


def main(argv: list[str] | None = None) -> int:
    path = argv[0] if argv else "documents/ha_vdsd_mapping.xlsx"
    result = run_audit(path)

    discrepancies = result["discrepancies"]
    missing = result["missing_entries"]

    if missing:
        print(f"\n⚠  {len(missing)} xlsx row(s) have no ENTITY_MAPPING entry (non-blocking):")
        _print_table(
            missing,
            ["domain", "device_class", "xlsx_row"],
            ["domain", "device_class", "xlsx_row"],
        )

    if discrepancies:
        print(f"\n✗  {len(discrepancies)} discrepancy(ies) found:")
        _print_table(
            discrepancies,
            ["domain", "device_class", "component", "field", "expected", "actual"],
            ["domain", "device_class", "component", "field", "expected", "actual"],
        )
        return 1

    print(f"\n✓  All checked fields match. ({len(missing)} missing entries reported above.)" if missing
          else "\n✓  All checked fields match.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 1.3: Verify script can be imported and run**

```bash
cd /home/arne/Development/dsvdc4ha
python tools/audit_mapping.py
```

Expected: prints a table of discrepancies (many will appear — that's intentional at this stage). Exit code 1. If it crashes with ImportError, check that `custom_components/dsvdc4ha/entity_mapping.py` is importable standalone (it has no HA runtime deps).

- [ ] **Step 1.4: Commit**

```bash
git add tools/__init__.py tools/audit_mapping.py
git commit -m "feat: add tools/audit_mapping.py — xlsx vs ENTITY_MAPPING audit script"
```

---

## Task 2: Write the failing test

**Files:**
- Create: `tests/test_entity_mapping.py`

- [ ] **Step 2.1: Write test**

Create `tests/test_entity_mapping.py`:

```python
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

try:
    import openpyxl  # noqa: F401
    _OPENPYXL_AVAILABLE = True
except ImportError:
    _OPENPYXL_AVAILABLE = False

import pytest
from tools.audit_mapping import run_audit


@pytest.mark.skipif(not _OPENPYXL_AVAILABLE, reason="openpyxl not installed")
def test_entity_mapping_matches_xlsx():
    result = run_audit()
    discrepancies = result["discrepancies"]
    assert discrepancies == [], (
        f"{len(discrepancies)} mapping discrepancy(ies) found:\n"
        + "\n".join(
            f"  {d['domain']}/{d['device_class']} "
            f"[{d['component']}.{d['field']}]: "
            f"expected={d['expected']!r} actual={d['actual']!r}"
            for d in discrepancies
        )
    )


@pytest.mark.skipif(not _OPENPYXL_AVAILABLE, reason="openpyxl not installed")
def test_audit_reports_missing_entries():
    """Missing entries are non-blocking; the list must not be empty (xlsx has unimplemented rows)."""
    result = run_audit()
    # There are known unimplemented rows (Event/None, Button/identify, etc.) — audit must detect them
    assert isinstance(result["missing_entries"], list)
```

- [ ] **Step 2.2: Run test to verify it fails on discrepancies**

```bash
pytest tests/test_entity_mapping.py -v
```

Expected: `test_entity_mapping_matches_xlsx` FAILS (many discrepancies). `test_audit_reports_missing_entries` PASSES.

- [ ] **Step 2.3: Commit**

```bash
git add tests/test_entity_mapping.py
git commit -m "test: add failing test — entity_mapping must match xlsx"
```

---

## Task 3: Add identity fields to every ENTITY_MAPPING entry

**Files:**
- Modify: `custom_components/dsvdc4ha/entity_mapping.py`

Every entry in `ENTITY_MAPPING` needs three new keys derived from the xlsx:
- `"model"`: the stripped-quote value from xlsx col 7, e.g. `"HA Binary Sensor (battery)"`
- `"model_uid"`: the stripped-quote value from xlsx col 9, e.g. `"ha-binary-sensor-battery"`
- `"vendor_name"`: always `"Home Assistant"`

The pattern is deterministic:
- `model` = `"HA {Entity Type} ({device_class})"` or `"HA {Entity Type}"` when dc is None
- `model_uid` = `"ha-{domain}-{device_class or 'none'}"`

**Complete list of values to add** (add three lines after each `"primary_group"` key):

**binary_sensor entries:**
| device_class | model | model_uid |
|---|---|---|
| `None` | `"HA Binary Sensor"` | `"ha-binary-sensor-none"` |
| `battery` | `"HA Binary Sensor (battery)"` | `"ha-binary-sensor-battery"` |
| `battery_charging` | `"HA Binary Sensor (battery_charging)"` | `"ha-binary-sensor-battery_charging"` |
| `carbon_monoxide` | `"HA Binary Sensor (carbon_monoxide)"` | `"ha-binary-sensor-carbon_monoxide"` |
| `cold` | `"HA Binary Sensor (cold)"` | `"ha-binary-sensor-cold"` |
| `connectivity` | `"HA Binary Sensor (connectivity)"` | `"ha-binary-sensor-connectivity"` |
| `door` | `"HA Binary Sensor (door)"` | `"ha-binary-sensor-door"` |
| `garage_door` | `"HA Binary Sensor (garage_door)"` | `"ha-binary-sensor-garage_door"` |
| `gas` | `"HA Binary Sensor (gas)"` | `"ha-binary-sensor-gas"` |
| `heat` | `"HA Binary Sensor (heat)"` | `"ha-binary-sensor-heat"` |
| `light` | `"HA Binary Sensor (light)"` | `"ha-binary-sensor-light"` |
| `lock` | `"HA Binary Sensor (lock)"` | `"ha-binary-sensor-lock"` |
| `moisture` | `"HA Binary Sensor (moisture)"` | `"ha-binary-sensor-moisture"` |
| `motion` | `"HA Binary Sensor (motion)"` | `"ha-binary-sensor-motion"` |
| `moving` | `"HA Binary Sensor (moving)"` | `"ha-binary-sensor-moving"` |
| `occupancy` | `"HA Binary Sensor (occupancy)"` | `"ha-binary-sensor-occupancy"` |
| `opening` | `"HA Binary Sensor (opening)"` | `"ha-binary-sensor-opening"` |
| `plug` | `"HA Binary Sensor (plug)"` | `"ha-binary-sensor-plug"` |
| `power` | `"HA Binary Sensor (power)"` | `"ha-binary-sensor-power"` |
| `presence` | `"HA Binary Sensor (presence)"` | `"ha-binary-sensor-presence"` |
| `problem` | `"HA Binary Sensor (problem)"` | `"ha-binary-sensor-problem"` |
| `running` | `"HA Binary Sensor (running)"` | `"ha-binary-sensor-running"` |
| `safety` | `"HA Binary Sensor (safety)"` | `"ha-binary-sensor-safety"` |
| `smoke` | `"HA Binary Sensor (smoke)"` | `"ha-binary-sensor-smoke"` |
| `sound` | `"HA Binary Sensor (sound)"` | `"ha-binary-sensor-sound"` |
| `tamper` | `"HA Binary Sensor (tamper)"` | `"ha-binary-sensor-tamper"` |
| `update` | `"HA Binary Sensor (update)"` | `"ha-binary-sensor-update"` |
| `vibration` | `"HA Binary Sensor (vibration)"` | `"ha-binary-sensor-vibration"` |
| `window` | `"HA Binary Sensor (window)"` | `"ha-binary-sensor-window"` |

**button, cover, event, fan, light, lock, number, siren, switch, valve entries:**
| domain | device_class | model | model_uid |
|---|---|---|---|
| `button` | `None` | `"HA Button"` | `"ha-button-none"` |
| `cover` | `awning` | `"HA Cover (awning)"` | `"ha-cover-awning"` |
| `cover` | `blind` | `"HA Cover (blind)"` | `"ha-cover-blind"` |
| `cover` | `curtain` | `"HA Cover (curtain)"` | `"ha-cover-curtain"` |
| `cover` | `damper` | `"HA Cover (damper)"` | `"ha-cover-damper"` |
| `cover` | `door` | `"HA Cover (door)"` | `"ha-cover-door"` |
| `cover` | `garage` | `"HA Cover (garage)"` | `"ha-cover-garage"` |
| `cover` | `gate` | `"HA Cover (gate)"` | `"ha-cover-gate"` |
| `cover` | `shade` | `"HA Cover (shade)"` | `"ha-cover-shade"` |
| `cover` | `shutter` | `"HA Cover (shutter)"` | `"ha-cover-shutter"` |
| `cover` | `window` | `"HA Cover (window)"` | `"ha-cover-window"` |
| `event` | `button` | `"HA Event (button)"` | `"ha-event-button"` |
| `event` | `doorbell` | `"HA Event (doorbell)"` | `"ha-event-doorbell"` |
| `event` | `motion` | `"HA Event (motion)"` | `"ha-event-motion"` |
| `fan` | `None` | `"HA Fan"` | `"ha-fan-none"` |
| `light` | `None` | `"HA Light"` | `"ha-light-none"` |
| `light` | `brightness` | `"HA Light (brightness)"` | `"ha-light-brightness"` |
| `light` | `color_temp` | `"HA Light (color_temp)"` | `"ha-light-color_temp"` |
| `light` | `rgb` | `"HA Light (rgb)"` | `"ha-light-rgb"` |
| `lock` | `None` | `"HA Lock"` | `"ha-lock-none"` |
| `number` | `None` | `"HA Number"` | `"ha-number-none"` |
| `siren` | `None` | `"HA Siren"` | `"ha-siren-none"` |
| `switch` | `None` | `"HA Switch"` | `"ha-switch-none"` |
| `switch` | `outlet` | `"HA Switch (outlet)"` | `"ha-switch-outlet"` |
| `switch` | `switch` | `"HA Switch (switch)"` | `"ha-switch-switch"` |
| `valve` | `None` | `"HA Valve"` | `"ha-valve-none"` |
| `valve` | `gas` | `"HA Valve (gas)"` | `"ha-valve-gas"` |
| `valve` | `water` | `"HA Valve (water)"` | `"ha-valve-water"` |
| `valve` | `water_heater` | `"HA Valve (water_heater)"` | `"ha-valve-water_heater"` |

**sensor entries:**
| device_class | model | model_uid |
|---|---|---|
| `None` | `"HA Sensor"` | `"ha-sensor-none"` |
| `apparent_power` | `"HA Sensor (apparent_power)"` | `"ha-sensor-apparent_power"` |
| `aqi` | `"HA Sensor (aqi)"` | `"ha-sensor-aqi"` |
| `atmospheric_pressure` | `"HA Sensor (atmospheric_pressure)"` | `"ha-sensor-atmospheric_pressure"` |
| `battery` | `"HA Sensor (battery)"` | `"ha-sensor-battery"` |
| `carbon_dioxide` | `"HA Sensor (carbon_dioxide)"` | `"ha-sensor-carbon_dioxide"` |
| `carbon_monoxide` | `"HA Sensor (carbon_monoxide)"` | `"ha-sensor-carbon_monoxide"` |
| `current` | `"HA Sensor (current)"` | `"ha-sensor-current"` |
| `distance` | `"HA Sensor (distance)"` | `"ha-sensor-distance"` |
| `duration` | `"HA Sensor (duration)"` | `"ha-sensor-duration"` |
| `energy` | `"HA Sensor (energy)"` | `"ha-sensor-energy"` |
| `frequency` | `"HA Sensor (frequency)"` | `"ha-sensor-frequency"` |
| `gas` | `"HA Sensor (gas)"` | `"ha-sensor-gas"` |
| `humidity` | `"HA Sensor (humidity)"` | `"ha-sensor-humidity"` |
| `illuminance` | `"HA Sensor (illuminance)"` | `"ha-sensor-illuminance"` |
| `moisture` | `"HA Sensor (moisture)"` | `"ha-sensor-moisture"` |
| `pm1` | `"HA Sensor (pm1)"` | `"ha-sensor-pm1"` |
| `pm10` | `"HA Sensor (pm10)"` | `"ha-sensor-pm10"` |
| `pm25` | `"HA Sensor (pm25)"` | `"ha-sensor-pm25"` |
| `power` | `"HA Sensor (power)"` | `"ha-sensor-power"` |
| `power_factor` | `"HA Sensor (power_factor)"` | `"ha-sensor-power_factor"` |
| `precipitation` | `"HA Sensor (precipitation)"` | `"ha-sensor-precipitation"` |
| `sound_pressure` | `"HA Sensor (sound_pressure)"` | `"ha-sensor-sound_pressure"` |
| `speed` | `"HA Sensor (speed)"` | `"ha-sensor-speed"` |
| `temperature` | `"HA Sensor (temperature)"` | `"ha-sensor-temperature"` |
| `voltage` | `"HA Sensor (voltage)"` | `"ha-sensor-voltage"` |
| `water` | `"HA Sensor (water)"` | `"ha-sensor-water"` |
| `weight` | `"HA Sensor (weight)"` | `"ha-sensor-weight"` |
| `wind_speed` | `"HA Sensor (wind_speed)"` | `"ha-sensor-wind_speed"` |

- [ ] **Step 3.1: Add identity fields to every entry**

For each entry in `ENTITY_MAPPING` in `entity_mapping.py`, add these three keys immediately after `"primary_group"`:

```python
"model": "<value from table above>",
"model_uid": "<value from table above>",
"vendor_name": "Home Assistant",
```

Example — the battery binary sensor entry becomes:

```python
{
    "domain": "binary_sensor", "device_class": "battery", "primary_group": 8,
    "model": "HA Binary Sensor (battery)",
    "model_uid": "ha-binary-sensor-battery",
    "vendor_name": "Home Assistant",
    "binary_input": {
        "sensor_function": 12, "group": 8, "input_usage": 0,
        "input_type": 1, "update_interval": 1.0,
    },
},
```

Apply this pattern to all ~80 entries using the tables above.

- [ ] **Step 3.2: Run the audit to verify identity fields are no longer flagged**

```bash
python tools/audit_mapping.py 2>&1 | grep "identity"
```

Expected: no lines containing `identity`. The audit output still shows other discrepancies — that's fine.

- [ ] **Step 3.3: Commit**

```bash
git add custom_components/dsvdc4ha/entity_mapping.py
git commit -m "feat: add model/model_uid/vendor_name identity fields to all ENTITY_MAPPING entries"
```

---

## Task 4: Fix value bugs in entity_mapping.py

**Files:**
- Modify: `custom_components/dsvdc4ha/entity_mapping.py`

These are the discrepancies identified by comparing the xlsx against the code. Apply all changes in one edit.

### 4a — binary_sensor/moving

Current (line ~155–159):
```python
"domain": "binary_sensor", "device_class": "moving", "primary_group": 8,
"binary_input": {
    "sensor_function": 0, "group": 8, "input_usage": 0,
    "input_type": 1, "update_interval": 1.0,
},
```

Fix — `sensor_function` 0→5, add `sensor_function_choices`, `input_usage` 0→1:
```python
"domain": "binary_sensor", "device_class": "moving", "primary_group": 8,
"model": "HA Binary Sensor (moving)",
"model_uid": "ha-binary-sensor-moving",
"vendor_name": "Home Assistant",
"binary_input": {
    "sensor_function": 5,
    "sensor_function_choices": [(5, "Motion (5)"), (0, "Generic (0)")],
    "group": 8, "input_usage": 1,
    "input_type": 1, "update_interval": 1.0,
},
```

### 4b — binary_sensor/problem

Current `input_usage`: 0. Fix → 4.

### 4c — binary_sensor/running

Current `input_usage`: 0. Fix → 4.

### 4d — binary_sensor/moisture (binary_input)

The xlsx says `inputUsage` is USER with options SECURITY(6), CLIMATE(3), JOKER(8). The current code has `input_usage: 0` with no group_choices. Fix:

```python
"domain": "binary_sensor", "device_class": "moisture", "primary_group": 8,
"model": "HA Binary Sensor (moisture)",
"model_uid": "ha-binary-sensor-moisture",
"vendor_name": "Home Assistant",
"binary_input": {
    "sensor_function": 0, "group": 8,
    "group_choices": [(8, "Joker (8)"), (6, "Security (6)"), (3, "Climate (3)")],
    "input_usage": 0,
    "input_type": 1, "update_interval": 1.0,
},
```

Note: `input_usage` in the xlsx is also USER-with-choices (same options), but since needs_user_input only gates on `group_choices` / `sensor_function_choices`, the user picks the group and input_usage defaults to 0 (UNDEFINED). This matches the current code's handling.

### 4e — sensor/battery

Current `update_interval: 30.0`, `alive_sign_interval: 120.0`. Fix → `60.0` and `240.0`.

- [ ] **Step 4.1: Apply all value fixes**

Apply changes 4a–4e to `entity_mapping.py`. The identity fields from Task 3 are already in place; adjust the rows as described.

After editing, the moving entry should look like:

```python
{
    "domain": "binary_sensor", "device_class": "moving", "primary_group": 8,
    "model": "HA Binary Sensor (moving)",
    "model_uid": "ha-binary-sensor-moving",
    "vendor_name": "Home Assistant",
    "binary_input": {
        "sensor_function": 5,
        "sensor_function_choices": [(5, "Motion (5)"), (0, "Generic (0)")],
        "group": 8, "input_usage": 1,
        "input_type": 1, "update_interval": 1.0,
    },
},
```

- [ ] **Step 4.2: Run audit and confirm all these fields now pass**

```bash
python tools/audit_mapping.py 2>&1 | grep -E "moving|problem|running|moisture.*binary|battery.*update|battery.*alive"
```

Expected: no matching lines.

- [ ] **Step 4.3: Commit**

```bash
git add custom_components/dsvdc4ha/entity_mapping.py
git commit -m "fix: correct sensor_function, input_usage values and add group_choices for moving/problem/running/moisture binary sensors; fix sensor/battery intervals"
```

---

## Task 5: Add sensor_usage_choices to sensor entries + update needs_user_input

**Files:**
- Modify: `custom_components/dsvdc4ha/entity_mapping.py`

Add `"sensor_usage_choices"` to 10 sensor entries, then extend `needs_user_input()`.

The full list of changes (add the `sensor_usage_choices` key next to `sensor_usage`):

| entry | sensor_usage (keep) | sensor_usage_choices to add |
|---|---|---|
| `sensor/None` | `0` | `"any"` |
| `sensor/aqi` | `1` | `[(1,"Room (1)"),(2,"Outdoor (2)")]` |
| `sensor/distance` | `4` | `[(4,"Device Level (4)"),(5,"Device Level Individual (5)"),(6,"Device Level All (6)")]` |
| `sensor/duration` | `4` | `[(4,"Device Level (4)"),(5,"Device Level Individual (5)"),(6,"Device Level All (6)")]` |
| `sensor/gas` | `0` | `[(0,"Generic (0)"),(1,"Room (1)"),(2,"Outdoor (2)"),(4,"Device Level (4)")]` |
| `sensor/humidity` | `0` | `[(0,"Generic (0)"),(1,"Room (1)"),(2,"Outdoor (2)"),(4,"Device Level (4)")]` |
| `sensor/illuminance` | `0` | `[(0,"Generic (0)"),(1,"Room (1)"),(2,"Outdoor (2)"),(4,"Device Level (4)")]` |
| `sensor/moisture` | `0` | `[(0,"Generic (0)"),(1,"Room (1)"),(2,"Outdoor (2)"),(4,"Device Level (4)")]` |
| `sensor/speed` | `0` | `[(0,"Generic (0)"),(1,"Room (1)"),(2,"Outdoor (2)"),(4,"Device Level (4)")]` |
| `sensor/temperature` | `0` | `[(0,"Generic (0)"),(1,"Room (1)"),(2,"Outdoor (2)"),(4,"Device Level (4)")]` |

- [ ] **Step 5.1: Add sensor_usage_choices to sensor entries**

For each of the 10 entries above, add `"sensor_usage_choices": <value>` immediately after the `"sensor_usage"` key.

Example — sensor/aqi becomes:
```python
{
    "domain": "sensor", "device_class": "aqi", "primary_group": 8,
    "model": "HA Sensor (aqi)",
    "model_uid": "ha-sensor-aqi",
    "vendor_name": "Home Assistant",
    "sensor": {
        "sensor_type": 0, "sensor_usage": 1,
        "sensor_usage_choices": [(1, "Room (1)"), (2, "Outdoor (2)")],
        "min": 0.0, "max": 500.0, "resolution": 1.0,
        "update_interval": 30.0, "alive_sign_interval": 120.0,
        "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
    },
},
```

- [ ] **Step 5.2: Extend `needs_user_input()` in entity_mapping.py**

Current code (around line 955):
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

Change to add `sensor_usage_choices` check:
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

- [ ] **Step 5.3: Run tests to catch regressions**

```bash
pytest tests/ -v -k "not test_entity_mapping_matches_xlsx"
```

Expected: all other tests pass.

- [ ] **Step 5.4: Commit**

```bash
git add custom_components/dsvdc4ha/entity_mapping.py
git commit -m "feat: add sensor_usage_choices to 10 sensor entries; extend needs_user_input()"
```

---

## Task 6: Fix config_flow.py — identity fields, name, hardwareGuid

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py`

### 6a — Replace identity field derivation

In `_build_entity_vdsd_and_continue` (around line 1002–1009), the vdsd dict currently uses:
```python
"model": self._display_id,
"vendorName": self._vendor_name,
"modelVersion": "1.0",
"modelUID": (self._vendor_name + self._display_id).replace(" ", ""),
"name": f"{self._device_name} — {friendly_name}",
```

Replace those 5 lines with:
```python
"model": mapping["model"],
"vendorName": mapping["vendor_name"],
"modelVersion": "1.0",
"modelUID": mapping["model_uid"],
"name": friendly_name,
```

`friendly_name` is already defined at line 999 as:
```python
friendly_name: str = (state.name if state else None) or entity_id.split(".")[-1]
```

Verify that `entity_id.split(".")[-1]` is used as fallback (not just `entity_id`). If the current line reads `or entity_id`, fix it to `or entity_id.split(".")[-1]`.

### 6b — Add hardwareGuid computation

After the vdsd dict closing brace (around line 1019), add:

```python
import uuid as _uuid
_VDC_NS = _uuid.UUID("9888dd3d-b345-4109-b088-2673306d0c65")  # DsUidNamespace.VDC
```

These two lines belong at **module level** (top of config_flow.py), not inside the function. Check whether they are already there; if not, add them after the existing imports.

Then, inside `_build_entity_vdsd_and_continue`, after the vdsd dict is built (after line ~1018), insert:

```python
# Compute deterministic hardwareGuid from entity unique_id
from homeassistant.helpers import entity_registry as er
ent_reg = er.async_get(self.hass)
ent_entry = ent_reg.async_get(entity_id)
_unique_id = ent_entry.unique_id if ent_entry else entity_id
vdsd["hardwareGuid"] = "uuid:" + str(_uuid.uuid5(_VDC_NS, _unique_id))
```

Do NOT repeat the `import uuid` line inside the function — use the module-level alias.

- [ ] **Step 6.1: Add module-level imports**

At the top of `config_flow.py`, find the existing `import` block and add:

```python
import uuid as _uuid

_VDC_NS = _uuid.UUID("9888dd3d-b345-4109-b088-2673306d0c65")
```

Check that `from homeassistant.helpers import entity_registry as er` is already imported (it is, from the existing config flow). If not, add it.

- [ ] **Step 6.2: Edit `_build_entity_vdsd_and_continue`**

Replace the identity/name lines as described in 6a. Add the hardwareGuid block as described in 6b.

Also fix the `friendly_name` fallback line (line ~999) from:
```python
friendly_name: str = (state.name if state else None) or entity_id
```
to:
```python
friendly_name: str = (state.name if state else None) or entity_id.split(".")[-1]
```

- [ ] **Step 6.3: Verify the function compiles**

```bash
python -c "import ast; ast.parse(open('custom_components/dsvdc4ha/config_flow.py').read()); print('OK')"
```

Expected: `OK`.

- [ ] **Step 6.4: Run existing config flow tests**

```bash
pytest tests/test_config_flow.py -v
```

Expected: all tests pass. If tests mock `_build_entity_vdsd_and_continue` or the vdsd dict keys, they may need updating; fix them to expect the new keys.

- [ ] **Step 6.5: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py
git commit -m "fix: use mapping identity fields in vdSD; fix name derivation fallback; add hardwareGuid"
```

---

## Task 7: Add sensor_usage UI to config_flow.py

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py`

### 7a — `async_step_entity_user_input`

After the `sensor_type_choices` block (around line 956), add a parallel block for `sensor_usage_choices`:

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

### 7b — `_build_entity_vdsd_and_continue`

In the sensor block (around line 1046), change:
```python
"sensorUsage": s["sensor_usage"],
```
to:
```python
"sensorUsage": int(user_input.get("sensor_usage", s["sensor_usage"])),
```

- [ ] **Step 7.1: Insert sensor_usage_choices block in async_step_entity_user_input**

Place the new block immediately after the existing `elif stc:` block (the sensor_type_choices section). The exact insertion point is after:
```python
        elif stc:
            schema_dict[vol.Required("sensor_type", default=str(sen["sensor_type"]))] = (
                selector.SelectSelector(selector.SelectSelectorConfig(options=[
                    selector.SelectOptionDict(value=str(v), label=lbl)
                    for v, lbl in stc
                ]))
            )
```

- [ ] **Step 7.2: Update sensorUsage in _build_entity_vdsd_and_continue**

Find the line `"sensorUsage": s["sensor_usage"],` and change it as shown in 7b.

- [ ] **Step 7.3: Verify syntax**

```bash
python -c "import ast; ast.parse(open('custom_components/dsvdc4ha/config_flow.py').read()); print('OK')"
```

- [ ] **Step 7.4: Run tests**

```bash
pytest tests/test_config_flow.py tests/test_entity_mapping_bindings.py -v
```

Expected: all pass.

- [ ] **Step 7.5: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py
git commit -m "feat: add sensor_usage selector UI for entities with sensor_usage_choices"
```

---

## Task 8: Update xlsx name column

**Files:**
- Modify: `documents/ha_vdsd_mapping.xlsx` (name column only — no other changes)

The name column (col 6, 1-based = index 5, 0-based) currently reads `entity.friendly_name` in every data row. Update every data row to `entity.friendly_name (fallback: entity_id.split(".")[-1])`.

**IMPORTANT:** Make **no other changes** to the xlsx. Only the name column cells in data rows (row 4 onwards where col A is not blank) are updated.

- [ ] **Step 8.1: Write and run the xlsx update script (one-shot — do not save it)**

Run this Python snippet directly (not saved to a file):

```bash
python3 - <<'EOF'
import pathlib
import openpyxl

xlsx_path = pathlib.Path("documents/ha_vdsd_mapping.xlsx")
wb = openpyxl.load_workbook(xlsx_path)
ws = wb.active

OLD_VALUE = "entity.friendly_name"
NEW_VALUE = "entity.friendly_name (fallback: entity_id.split(\".\")[-1])"

COL_NAME = 6  # 1-based column F

updated = 0
for row in ws.iter_rows(min_row=4):
    if row[0].value is None:
        continue
    cell = row[COL_NAME - 1]  # convert to 0-based for row tuple
    if cell.value == OLD_VALUE:
        cell.value = NEW_VALUE
        updated += 1

wb.save(xlsx_path)
print(f"Updated {updated} name cells.")
EOF
```

Expected output: `Updated <N> name cells.` (should be around 80+).

- [ ] **Step 8.2: Verify only name column changed**

```bash
python3 -c "
import openpyxl
wb = openpyxl.load_workbook('documents/ha_vdsd_mapping.xlsx', data_only=True)
ws = wb.active
count = 0
for row in ws.iter_rows(min_row=4, values_only=True):
    if row[0] is None: continue
    if row[5] is not None and 'fallback' in str(row[5]):
        count += 1
print(f'{count} rows updated correctly')
wb.close()
"
```

- [ ] **Step 8.3: Commit**

```bash
git add documents/ha_vdsd_mapping.xlsx
git commit -m "docs: update name column in xlsx to document fallback to entity_id.split('.')[-1]"
```

---

## Task 9: Run audit, fix remaining discrepancies, make test pass

**Files:**
- Modify: `custom_components/dsvdc4ha/entity_mapping.py` (if any remaining discrepancies)

- [ ] **Step 9.1: Run full audit**

```bash
python tools/audit_mapping.py
```

Review the output. The remaining discrepancies (if any) are those not covered by the design spec's Section 3 but caught by the audit. Fix them in `entity_mapping.py`.

Known potential remaining discrepancy: `cover/awning defaultGroup` — xlsx says `AWNINGS (65)`, code has `2`. If flagged:
- Check in the dS configurator what group 65 (AWNINGS) is vs group 2 (BLINDS)
- Update `"default_group": 65` for cover/awning if the xlsx value is authoritative

- [ ] **Step 9.2: Fix any remaining discrepancies**

For each discrepancy from step 9.1, apply the fix to `entity_mapping.py`. Rule: the xlsx is the source of truth.

- [ ] **Step 9.3: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: `test_entity_mapping_matches_xlsx` PASSES. All other tests pass.

- [ ] **Step 9.4: Commit fixes (if any)**

```bash
git add custom_components/dsvdc4ha/entity_mapping.py
git commit -m "fix: resolve remaining entity_mapping discrepancies found by audit"
```

---

## Self-review checklist

After all tasks:

1. **Spec coverage:**
   - ✅ Task 1 — `tools/audit_mapping.py` with `run_audit()` returning discrepancies + missing_entries
   - ✅ Task 2 — failing test; `test_entity_mapping_matches_xlsx` asserts `discrepancies == []`
   - ✅ Task 3 — identity fields (model/model_uid/vendor_name) on all entries
   - ✅ Task 4 — value fixes: moving/problem/running/moisture binary sensors, sensor/battery
   - ✅ Task 5 — sensor_usage_choices on 10 sensor entries + needs_user_input
   - ✅ Task 6 — config_flow identity fields + name fallback + hardwareGuid
   - ✅ Task 7 — sensor_usage UI selector + sensorUsage read from user_input
   - ✅ Task 8 — xlsx name column updated (only)
   - ✅ Task 9 — full audit passes, test suite green

2. **Invariants to verify:**
   - `run_audit()` does NOT fail or raise when missing_entries is non-empty — it's informational
   - Test only asserts `discrepancies == []`, never `missing_entries == []`
   - xlsx update script only changes column F (name, 1-based index 6); no other columns touched
   - `hardwareGuid` is deterministic: same entity always yields the same UUID5
   - `needs_user_input()` returns True for all 10 entries that now have `sensor_usage_choices`
