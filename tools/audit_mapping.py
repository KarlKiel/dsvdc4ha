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

_SKIP_DOMAINS      = {"weather"}
_SKIP_ENTITY_NONE  = {"event"}
_SKIP_DC_FRAGMENTS = {"(as button", "rgbw", "rgbww"}
_SKIP_BTN_DC       = {"identify", "restart", "update"}


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
            raw = get(header)
            if raw is None or str(raw).strip() == "-":
                return
            exp = enum_value(ENUM_CLASS[enum_key], str(raw).strip())
            if exp is None:
                return
            if int(actual) != exp:
                _dis(domain, dc, component, field, exp, actual)

        def chk_user(component, field, header, has_choices: bool):
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
            raw_pc = get("output.placement_choice")
            if raw_pc is not None:
                exp_pc = str(raw_pc).strip().lower() == "yes"
                if bool(o.get("placement_choice")) != exp_pc:
                    _dis(domain, dc, "output", "placement_choice", exp_pc, o.get("placement_choice"))
            raw_spt = get("output.shadow_position_timing")
            if raw_spt is not None:
                exp_spt = str(raw_spt).strip().lower() == "yes"
                if bool(o.get("shadow_position_timing")) != exp_spt:
                    _dis(domain, dc, "output", "shadow_position_timing", exp_spt, o.get("shadow_position_timing"))
            raw_sat = get("output.shadow_angle_timing")
            if raw_sat is not None:
                exp_sat = str(raw_sat).strip().lower() == "yes"
                if bool(o.get("shadow_angle_timing")) != exp_sat:
                    _dis(domain, dc, "output", "shadow_angle_timing", exp_sat, o.get("shadow_angle_timing"))
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
            channels_outdoor = o.get("channels_outdoor") or []
            for i in range(6):
                raw_ct = get(f"output.ch{i}.channel_type_outdoor.VALUE")
                if raw_ct is None or str(raw_ct).strip() == "-":
                    break
                exp_ct = enum_value(ENUM_CLASS["OutputChannelType"], str(raw_ct).strip())
                if exp_ct is None:
                    continue
                actual_ct = channels_outdoor[i]["channel_type"] if i < len(channels_outdoor) else None
                if actual_ct is None or int(actual_ct) != exp_ct:
                    _dis(domain, dc, "output", f"channels_outdoor[{i}].channel_type", exp_ct, actual_ct)
            for timing_field in ("openTime", "closeTime", "angleOpenTime", "angleCloseTime", "stopDelayTime"):
                raw = get(f"output.{timing_field}")
                if raw is not None and str(raw).strip() not in ("-", ""):
                    try:
                        exp = float(raw)
                    except (ValueError, TypeError):
                        continue
                    actual = o.get(timing_field)
                    if actual is not None and abs(float(actual) - exp) > 1e-9:
                        _dis(domain, dc, "output", timing_field, exp, actual)

            # active_cooling_mode
            raw_acm = get("output.active_cooling_mode")
            if raw_acm is not None:
                exp_acm = str(raw_acm).strip().lower() == "yes"
                if bool(o.get("active_cooling_mode")) != exp_acm:
                    _dis(domain, dc, "output", "active_cooling_mode", exp_acm, o.get("active_cooling_mode"))
            # heating_system_capability
            chk_val("output", "heating_system_capability", "HeatingSystemCapability",
                    "output.heating_system_capability.VALUE",
                    o.get("heating_system_capability") if o.get("heating_system_capability") is not None else 0)
            # heating_system_type
            chk_val("output", "heating_system_type", "HeatingSystemType",
                    "output.heating_system_type.VALUE",
                    o.get("heating_system_type") if o.get("heating_system_type") is not None else 0)
            # dimmer timing (dS 8-bit format int; snake_case keys in entity_mapping)
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
