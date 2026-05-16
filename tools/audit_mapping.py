"""Audit ENTITY_MAPPING against the xlsx source of truth.

Usage:
    python tools/audit_mapping.py                    # use default xlsx path
    python tools/audit_mapping.py path/to/other.xlsx # override path
"""
from __future__ import annotations

import re
import sys
import pathlib

_REPO_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

try:
    import openpyxl
except ImportError as e:
    raise ImportError("openpyxl is required: pip install openpyxl") from e

import importlib.util as _ilu

def _load_entity_mapping():
    """Load entity_mapping.py directly, bypassing the HA-dependent package __init__."""
    _spec = _ilu.spec_from_file_location(
        "entity_mapping",
        _REPO_ROOT / "custom_components" / "dsvdc4ha" / "entity_mapping.py",
    )
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    return _mod

_em = _load_entity_mapping()
ENTITY_MAPPING = _em.ENTITY_MAPPING
_CHANNEL_TYPE_NAMES = _em._CHANNEL_TYPE_NAMES

COL_ENTITY     = 0
COL_DC         = 1
COL_NAME       = 5
COL_MODEL      = 6
COL_MODEL_UID  = 8
COL_VENDOR     = 12
COL_PG         = 18
COL_OUT_FUNC   = 21
COL_DEF_GRP    = 22
COL_OUT_USAGE  = 23
COL_VAR_RAMP   = 24
COL_OUT_MODE   = 28
_CH_BASE       = 44
COL_BTN_TYPE   = 96
COL_BTN_GRP    = 98
COL_BTN_FUNC   = 99
COL_BTN_MODE   = 100
COL_INPUT_USAGE = 113
COL_BIN_GRP    = 116
COL_SF_SETTING = 117
COL_SNS_TYPE   = 124
COL_SNS_USAGE  = 125
COL_SNS_MIN    = 126
COL_SNS_MAX    = 127
COL_SNS_RES    = 128
COL_UPD_INT    = 129
COL_ALIVE_INT  = 130
COL_MIN_PUSH   = 132

_CH_TYPE_COLS = [_CH_BASE + i * 8 for i in range(6)]

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

_SKIP_DC_FRAGMENTS = {"(as button", "rgbw", "rgbww"}
_SKIP_DOMAINS = {"weather"}
_SKIP_ENTITY_NONE = {"event"}
_SKIP_BTN_DC = {"identify", "restart", "update"}

_NA_TOKENS = {"— not applicable —", "- not applicable -"}


def _is_na(v) -> bool:
    return v is None or (isinstance(v, str) and (
        v.strip() in _NA_TOKENS
        or v.strip().lower().startswith("pydsvdcapi handled")
    ))


def _parse_scalar(raw):
    if _is_na(raw):
        return None
    s = str(raw).strip()
    if not s:
        return None
    if re.match(r"^USER\s*$", s, re.IGNORECASE):
        return None
    if re.match(r"^USER\s*[—–-]\s*specify", s, re.IGNORECASE):
        return None
    m = re.match(r"^USER\s*[—–-]\s*default\s*:\s*.+?\((-?\d+)\)", s, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.match(r"^USER\s*:\s*.+?\((-?\d+)\)", s, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.match(r"^USER\s*[—–-]\s*.+?\((-?\d+)\)", s, re.IGNORECASE)
    if m:
        return int(m.group(1))
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    if " or " in s.lower() and "depending" in s.lower():
        return None
    m = re.search(r"\((-?\d+)\)", s)
    if m:
        return int(m.group(1))
    if s.upper() in _CHANNEL_TYPE_NAMES:
        return _CHANNEL_TYPE_NAMES[s.upper()]
    try:
        f = float(s)
        return int(f) if f == int(f) else f
    except ValueError:
        pass
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    return s


def _build_mapping_index() -> dict[tuple, dict]:
    return {(e["domain"], e["device_class"]): e for e in ENTITY_MAPPING}


def run_audit(xlsx_path="documents/ha_vdsd_mapping.xlsx") -> dict:
    xlsx_path = pathlib.Path(xlsx_path)
    if not xlsx_path.exists():
        raise FileNotFoundError(f"xlsx not found: {xlsx_path}")

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
            continue

        raw_dc = row[COL_DC]
        dc_str = str(raw_dc).strip() if raw_dc else None
        dc = dc_str.lower().replace(" ", "_").replace("-", "_") if dc_str else None

        if domain in _SKIP_DOMAINS:
            continue
        if domain in _SKIP_ENTITY_NONE and dc is None:
            continue
        if dc is not None and any(frag in dc for frag in _SKIP_DC_FRAGMENTS):
            continue
        if domain == "button" and dc in _SKIP_BTN_DC:
            continue

        entry = mapping_idx.get((domain, dc))
        if entry is None:
            missing_entries.append({"domain": domain, "device_class": dc, "xlsx_row": row_idx})
            continue

        def chk(component, field, col, actual_val):
            exp = _parse_scalar(row[col] if col < len(row) else None)
            if exp is None:
                return
            if actual_val != exp:
                _dis(domain, dc, component, field, exp, actual_val)

        chk("identity", "model", COL_MODEL, entry.get("model"))
        chk("identity", "model_uid", COL_MODEL_UID, entry.get("model_uid"))
        chk("identity", "vendor_name", COL_VENDOR, entry.get("vendor_name"))

        if "binary_input" in entry:
            bi = entry["binary_input"]
            chk("binary_input", "sensor_function", COL_SF_SETTING, bi.get("sensor_function"))
            chk("binary_input", "group", COL_BIN_GRP, bi.get("group"))
            chk("binary_input", "input_usage", COL_INPUT_USAGE, bi.get("input_usage"))

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

        if "output" in entry:
            o = entry["output"]
            chk("output", "function", COL_OUT_FUNC, o.get("function"))
            chk("output", "default_group", COL_DEF_GRP, o.get("default_group"))
            chk("output", "output_usage", COL_OUT_USAGE, o.get("output_usage"))
            chk("output", "variable_ramp", COL_VAR_RAMP, o.get("variable_ramp"))
            chk("output", "mode", COL_OUT_MODE, o.get("mode"))
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

        if "button" in entry:
            b = entry["button"]
            chk("button", "button_type", COL_BTN_TYPE, b.get("button_type"))
            chk("button", "group", COL_BTN_GRP, b.get("group"))
            chk("button", "function", COL_BTN_FUNC, b.get("function"))
            chk("button", "mode", COL_BTN_MODE, b.get("mode"))

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

    if missing:
        print(f"\n✓  All checked fields match. ({len(missing)} missing entries reported above.)")
    else:
        print("\n✓  All checked fields match.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
