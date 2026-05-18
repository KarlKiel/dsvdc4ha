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
