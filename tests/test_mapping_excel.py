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
