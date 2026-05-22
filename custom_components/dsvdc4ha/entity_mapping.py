"""Static mapping from HA entity types / device_classes to dS vdSD configuration."""
from __future__ import annotations

from typing import Any, Callable

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

# Reusable choice lists for UI selectors.
# .value is used intentionally: config_flow passes these to SelectOptionDict as
# str(v), and downstream code compares them as plain ints. Storing enum members
# directly also works (IntEnum == int), but .value keeps the type annotation
# explicit and avoids any str() surprises across Python versions.
# Reusable choice lists for binary_input.group_choices
_BI_GROUP_ALL: list[tuple[int, str]] = [
    (BinaryInputGroup.LIGHT.value,    "Light (1)"),
    (BinaryInputGroup.SHADOW.value,   "Shadow (2)"),
    (BinaryInputGroup.HEATING.value,  "Heating (3)"),
    (BinaryInputGroup.AUDIO.value,    "Audio (4)"),
    (BinaryInputGroup.VIDEO.value,    "Video (5)"),
    (BinaryInputGroup.SECURITY.value, "Security (6)"),
    (BinaryInputGroup.ACCESS.value,   "Access (7)"),
    (BinaryInputGroup.JOKER.value,    "Joker (8)"),
]
_BI_GROUP_MOISTURE: list[tuple[int, str]] = [
    (BinaryInputGroup.SECURITY.value, "Security (6)"),
    (BinaryInputGroup.HEATING.value,  "Heating (3)"),
    (BinaryInputGroup.JOKER.value,    "Joker (8)"),
]
# Reusable choice list for binary_input.input_usage_choices
_BI_USAGE_ALL: list[tuple[int, str]] = [
    (BinaryInputUsage.UNDEFINED.value,       "Undefined (0)"),
    (BinaryInputUsage.ROOM_CLIMATE.value,    "Room Climate (1)"),
    (BinaryInputUsage.OUTDOOR_CLIMATE.value, "Outdoor Climate (2)"),
    (BinaryInputUsage.CLIMATE_SETTING.value, "Climate Setting (3)"),
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
    # USER_INTERACTION (3) intentionally omitted — not a valid room/device sensor context
    (SensorUsage.DEVICE_LEVEL.value,    "Device Level (4)"),
    (SensorUsage.DEVICE_LAST_RUN.value, "Device Last Run (5)"),
    (SensorUsage.DEVICE_AVERAGE.value,  "Device Average (6)"),
]

# ---------------------------------------------------------------------------
# Mapping entries
#
# Conventions
# -----------
# domain        : HA entity domain (lowercase, e.g. "light")
# device_class  : HA device_class attribute or None
# primary_group : dS primaryGroup integer
#
# binary_input / sensor / button / output
#   All numeric fields are the final integer values to pass to pydsvdcapi.
#   A "…_choices" sibling list  [(value, label), ...]  means the user must
#   pick one of those values; the main field holds the default.
#   Special flags:
#     min_max_user: True   → user must supply min/max/resolution
#     group_choices        → user picks the button group
#     output_usage_choices → user picks outputUsage
#     function_choices     → user picks output function
#     channels_by_usage    → {usage_int: [channel_defs]}  (cover/blind)
#     optional_tilt: True  → user is asked whether to add a tilt channel
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Light capability tier builders
# ---------------------------------------------------------------------------

def _onoff_output(entity_id: str) -> dict:
    return {
        "function": OutputFunction.ON_OFF,
        "default_group": ColorClass.LIGHTS,
        "output_usage": OutputUsage.ROOM,
        "variable_ramp": True,
        "mode": OutputMode.BINARY,
        "groups": [1],
        "apply_all_expr": "_light_apply(channel_updates, attrs)",
        "channels": [
            {
                "channel_type": OutputChannelType.BRIGHTNESS,
                "read_entity": entity_id,
                "push_expr": "100.0 if entity.state == 'on' else 0.0",
            }
        ],
    }


def _dimmer_output(entity_id: str) -> dict:
    return {
        "function": OutputFunction.DIMMER,
        "default_group": ColorClass.LIGHTS,
        "output_usage": OutputUsage.ROOM,
        "variable_ramp": True,
        "mode": OutputMode.GRADUAL,
        "groups": [1],
        "apply_all_expr": "_light_apply(channel_updates, attrs)",
        "channels": [
            {
                "channel_type": OutputChannelType.BRIGHTNESS,
                "read_entity": entity_id,
                "push_expr": "0.0 if entity.state == 'off' else round((attrs.get('brightness') or 0) / 2.55, 1)",
            }
        ],
    }


def _color_temp_dimmer_output(entity_id: str) -> dict:
    return {
        "function": OutputFunction.DIMMER_COLOR_TEMP,
        "default_group": ColorClass.LIGHTS,
        "output_usage": OutputUsage.ROOM,
        "variable_ramp": True,
        "mode": OutputMode.GRADUAL,
        "groups": [1],
        "apply_all_expr": "_light_apply(channel_updates, attrs)",
        "channels": [
            {
                "channel_type": OutputChannelType.BRIGHTNESS,
                "read_entity": entity_id,
                "push_expr": "0.0 if entity.state == 'off' else round((attrs.get('brightness') or 0) / 2.55, 1)",
            },
            {
                "channel_type": OutputChannelType.COLOR_TEMPERATURE,
                "read_entity": entity_id,
                "push_expr": "float(attrs.get('color_temp') or round(1_000_000 / max(attrs.get('color_temp_kelvin') or 2700, 1)))",
            },
        ],
    }


def _full_color_dimmer_output(entity_id: str) -> dict:
    return {
        "function": OutputFunction.FULL_COLOR_DIMMER,
        "default_group": ColorClass.LIGHTS,
        "output_usage": OutputUsage.ROOM,
        "variable_ramp": True,
        "mode": OutputMode.GRADUAL,
        "groups": [1],
        "apply_all_expr": "_light_apply(channel_updates, attrs)",
        "channels": [
            {
                "channel_type": OutputChannelType.BRIGHTNESS,
                "read_entity": entity_id,
                "push_expr": "0.0 if entity.state == 'off' else round((attrs.get('brightness') or 0) / 2.55, 1)",
            },
            {
                "channel_type": OutputChannelType.COLOR_TEMPERATURE,
                "read_entity": entity_id,
                "push_expr": "float(attrs.get('color_temp') or round(1_000_000 / max(attrs.get('color_temp_kelvin') or 2700, 1)))",
            },
            {
                "channel_type": OutputChannelType.HUE,
                "read_entity": entity_id,
                "push_expr": "(attrs.get('hs_color') or (0, 0))[0] if attrs.get('color_mode') in ('hs', 'rgb', 'rgbw', 'rgbww', 'xy') else 0.0",
            },
            {
                "channel_type": OutputChannelType.SATURATION,
                "read_entity": entity_id,
                "push_expr": "(attrs.get('hs_color') or (0, 0))[1] if attrs.get('color_mode') in ('hs', 'rgb', 'rgbw', 'rgbww', 'xy') else 0.0",
            },
            {
                "channel_type": OutputChannelType.CIE_X,
                "read_entity": entity_id,
                "push_expr": "round((attrs.get('xy_color') or (0.3127, 0.3290))[0] * 10000, 1)",
            },
            {
                "channel_type": OutputChannelType.CIE_Y,
                "read_entity": entity_id,
                "push_expr": "round((attrs.get('xy_color') or (0.3127, 0.3290))[1] * 10000, 1)",
            },
        ],
    }


def _derive_light_output_config(entity_id: str, state) -> dict:
    """Return the per-tier output config for a light entity based on supported_color_modes."""
    attrs = state.attributes if state else {}
    supported = set(attrs.get("supported_color_modes") or [])

    # Unavailable or unknown state: use full-color as the safest fallback
    if not state or not supported:
        return {"model": "HA Light (Full Color)", "model_uid": "ha-light-full-color",
                "output": _full_color_dimmer_output(entity_id)}
    if supported & {"hs", "xy", "rgb", "rgbw", "rgbww"}:
        return {"model": "HA Light (Full Color)", "model_uid": "ha-light-full-color",
                "output": _full_color_dimmer_output(entity_id)}
    if "color_temp" in supported:
        return {"model": "HA Light (Color Temp)", "model_uid": "ha-light-color-temp",
                "output": _color_temp_dimmer_output(entity_id)}
    if "brightness" in supported or "white" in supported:
        return {"model": "HA Light (Dimmer)", "model_uid": "ha-light-dimmer",
                "output": _dimmer_output(entity_id)}
    return {"model": "HA Light (On/Off)", "model_uid": "ha-light-onoff",
            "output": _onoff_output(entity_id)}


ENTITY_MAPPING: list[dict[str, Any]] = [
    # ── Binary Sensor ───────────────────────────────────────────────────────
    {
        "domain": "binary_sensor", "device_class": None, "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor",
        "model_uid": "ha-binary-sensor-none",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.GENERIC,
            "sensor_function_choices": "any",
            "group": BinaryInputGroup.JOKER, "input_usage": BinaryInputUsage.UNDEFINED,
            "input_usage_choices": _BI_USAGE_ALL,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "battery", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (battery)",
        "model_uid": "ha-binary-sensor-battery",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.BATTERY_LOW, "group": BinaryInputGroup.JOKER, "input_usage": BinaryInputUsage.UNDEFINED,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "battery_charging", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (battery_charging)",
        "model_uid": "ha-binary-sensor-battery_charging",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.GENERIC, "group": BinaryInputGroup.JOKER, "input_usage": BinaryInputUsage.UNDEFINED,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "carbon_monoxide", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (carbon_monoxide)",
        "model_uid": "ha-binary-sensor-carbon_monoxide",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.GENERIC, "group": BinaryInputGroup.SECURITY, "group_choices": _BI_GROUP_ALL,
            "input_usage": BinaryInputUsage.ROOM_CLIMATE, "input_usage_choices": _BI_USAGE_ALL,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "cold", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (cold)",
        "model_uid": "ha-binary-sensor-cold",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.FROST,
            "sensor_function_choices": [(BinaryInputType.FROST.value, "Frost (18)"), (BinaryInputType.GENERIC.value, "Generic (0)")],
            "group": BinaryInputGroup.HEATING, "group_choices": _BI_GROUP_ALL,
            "input_usage": BinaryInputUsage.OUTDOOR_CLIMATE, "input_usage_choices": _BI_USAGE_ALL,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "connectivity", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (connectivity)",
        "model_uid": "ha-binary-sensor-connectivity",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.SERVICE, "group": BinaryInputGroup.JOKER, "input_usage": BinaryInputUsage.UNDEFINED,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "door", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (door)",
        "model_uid": "ha-binary-sensor-door",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.DOOR_OPEN, "group": BinaryInputGroup.ACCESS,
            "input_usage": BinaryInputUsage.ROOM_CLIMATE, "input_usage_choices": _BI_USAGE_ALL,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "garage_door", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (garage_door)",
        "model_uid": "ha-binary-sensor-garage_door",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.GARAGE_DOOR_OPEN, "group": BinaryInputGroup.ACCESS, "input_usage": BinaryInputUsage.UNDEFINED,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "gas", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (gas)",
        "model_uid": "ha-binary-sensor-gas",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.GENERIC, "group": BinaryInputGroup.SECURITY, "group_choices": _BI_GROUP_ALL,
            "input_usage": BinaryInputUsage.ROOM_CLIMATE, "input_usage_choices": _BI_USAGE_ALL,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "heat", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (heat)",
        "model_uid": "ha-binary-sensor-heat",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.THERMOSTAT, "group": BinaryInputGroup.HEATING, "group_choices": _BI_GROUP_ALL,
            "input_usage": BinaryInputUsage.ROOM_CLIMATE, "input_usage_choices": _BI_USAGE_ALL,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "light", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (light)",
        "model_uid": "ha-binary-sensor-light",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.BRIGHTNESS, "group": BinaryInputGroup.LIGHT, "group_choices": _BI_GROUP_ALL,
            "input_usage": BinaryInputUsage.ROOM_CLIMATE, "input_usage_choices": _BI_USAGE_ALL,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "lock", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (lock)",
        "model_uid": "ha-binary-sensor-lock",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.DOOR_OPEN, "group": BinaryInputGroup.ACCESS, "input_usage": BinaryInputUsage.UNDEFINED,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "moisture", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (moisture)",
        "model_uid": "ha-binary-sensor-moisture",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.GENERIC, "group": BinaryInputGroup.SECURITY, "group_choices": _BI_GROUP_MOISTURE,
            "input_usage": BinaryInputUsage.ROOM_CLIMATE, "input_usage_choices": _BI_USAGE_ALL,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "motion", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (motion)",
        "model_uid": "ha-binary-sensor-motion",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.MOTION, "group": BinaryInputGroup.LIGHT, "group_choices": _BI_GROUP_ALL,
            "input_usage": BinaryInputUsage.ROOM_CLIMATE, "input_usage_choices": _BI_USAGE_ALL,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "moving", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (moving)",
        "model_uid": "ha-binary-sensor-moving",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.MOTION,
            "sensor_function_choices": [(BinaryInputType.MOTION.value, "Motion (5)"), (BinaryInputType.GENERIC.value, "Generic (0)")],
            "group": BinaryInputGroup.JOKER, "input_usage": BinaryInputUsage.ROOM_CLIMATE, "input_usage_choices": _BI_USAGE_ALL,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "occupancy", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (occupancy)",
        "model_uid": "ha-binary-sensor-occupancy",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.PRESENCE, "group": BinaryInputGroup.LIGHT,
            "input_usage": BinaryInputUsage.ROOM_CLIMATE, "input_usage_choices": _BI_USAGE_ALL,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "opening", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (opening)",
        "model_uid": "ha-binary-sensor-opening",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.GENERIC, "group": BinaryInputGroup.JOKER, "group_choices": _BI_GROUP_ALL,
            "input_usage": BinaryInputUsage.UNDEFINED, "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "plug", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (plug)",
        "model_uid": "ha-binary-sensor-plug",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.GENERIC, "group": BinaryInputGroup.JOKER, "input_usage": BinaryInputUsage.UNDEFINED,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "power", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (power)",
        "model_uid": "ha-binary-sensor-power",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.GENERIC, "group": BinaryInputGroup.JOKER, "input_usage": BinaryInputUsage.UNDEFINED,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "presence", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (presence)",
        "model_uid": "ha-binary-sensor-presence",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.PRESENCE, "group": BinaryInputGroup.LIGHT,
            "input_usage": BinaryInputUsage.ROOM_CLIMATE, "input_usage_choices": _BI_USAGE_ALL,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "problem", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (problem)",
        "model_uid": "ha-binary-sensor-problem",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.MALFUNCTION, "group": BinaryInputGroup.JOKER, "input_usage": BinaryInputUsage.UNDEFINED,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "running", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (running)",
        "model_uid": "ha-binary-sensor-running",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.GENERIC, "group": BinaryInputGroup.JOKER, "input_usage": BinaryInputUsage.UNDEFINED,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "safety", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (safety)",
        "model_uid": "ha-binary-sensor-safety",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.GENERIC, "group": BinaryInputGroup.SECURITY, "input_usage": BinaryInputUsage.UNDEFINED,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "smoke", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (smoke)",
        "model_uid": "ha-binary-sensor-smoke",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.SMOKE, "group": BinaryInputGroup.SECURITY, "input_usage": BinaryInputUsage.UNDEFINED,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "sound", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (sound)",
        "model_uid": "ha-binary-sensor-sound",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.GENERIC, "group": BinaryInputGroup.JOKER, "group_choices": _BI_GROUP_ALL,
            "input_usage": BinaryInputUsage.UNDEFINED, "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "tamper", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (tamper)",
        "model_uid": "ha-binary-sensor-tamper",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.SERVICE, "group": BinaryInputGroup.SECURITY, "input_usage": BinaryInputUsage.UNDEFINED,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "update", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (update)",
        "model_uid": "ha-binary-sensor-update",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.SERVICE, "group": BinaryInputGroup.JOKER, "input_usage": BinaryInputUsage.UNDEFINED,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "vibration", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (vibration)",
        "model_uid": "ha-binary-sensor-vibration",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.GENERIC, "group": BinaryInputGroup.JOKER, "input_usage": BinaryInputUsage.UNDEFINED,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "window", "primary_group": ColorGroup.BLACK,
        "model": "HA Binary Sensor (window)",
        "model_uid": "ha-binary-sensor-window",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.WINDOW_OPEN, "group": BinaryInputGroup.ACCESS,
            "input_usage": BinaryInputUsage.ROOM_CLIMATE, "input_usage_choices": _BI_USAGE_ALL,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    # ── Button ──────────────────────────────────────────────────────────────
    {
        "domain": "button", "device_class": None, "primary_group": ColorGroup.BLACK,
        "model": "HA Button",
        "model_uid": "ha-button-none",
        "vendor_name": "Home Assistant",
        "button": {
            "button_type": ButtonType.SINGLE_PUSHBUTTON,
            "group": ButtonGroup.JOKER,
            "group_choices": _BTN_GROUP_CHOICES,
            "function": ButtonFunctionJoker.APP,
            "mode": ButtonMode.STANDARD,
            "supports_local_key_mode": True,
            "calls_present": True,
        },
    },
    # ── Cover ────────────────────────────────────────────────────────────────
    {
        "domain": "cover", "device_class": "awning", "primary_group": ColorGroup.GREY,
        "model": "HA Cover (awning)",
        "model_uid": "ha-cover-awning",
        "vendor_name": "Home Assistant",
        "output": {
            "function": OutputFunction.POSITIONAL, "default_group": ColorClass.AWNINGS, "output_usage": 0,
            "variable_ramp": False, "mode": OutputMode.GRADUAL, "groups": [2],
            "channels": [{"channel_type": OutputChannelType.SHADE_POSITION_OUTSIDE,
                          "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(100-value)}}",
                          "push_expr": "round(100-attrs.get('current_position',0),1)"}],  # SHADE_POSITION_OUTSIDE
        },
    },
    {
        "domain": "cover", "device_class": "blind", "primary_group": ColorGroup.GREY,
        "model": "HA Cover (blind)",
        "model_uid": "ha-cover-blind",
        "vendor_name": "Home Assistant",
        "output": {
            "function": OutputFunction.POSITIONAL, "default_group": ColorClass.BLINDS, "output_usage": 0,
            "variable_ramp": False, "mode": OutputMode.GRADUAL, "groups": [2],
            "placement_choice": True,
            "channels": [
                {"channel_type": OutputChannelType.SHADE_POSITION_INDOOR,
                 "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(100-value)}}",
                 "push_expr": "round(100-attrs.get('current_position',0),1)"},
                {"channel_type": OutputChannelType.SHADE_OPENING_ANGLE_INDOOR,
                 "apply_expr": "{'domain':'cover','service':'set_cover_tilt_position','service_data':{'tilt_position':round(value)}}",
                 "push_expr": "attrs.get('current_tilt_position',0)"},
            ],
            "channels_outdoor": [
                {"channel_type": OutputChannelType.SHADE_POSITION_OUTSIDE,
                 "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(100-value)}}",
                 "push_expr": "round(100-attrs.get('current_position',0),1)"},
                {"channel_type": OutputChannelType.SHADE_OPENING_ANGLE_OUTSIDE,
                 "apply_expr": "{'domain':'cover','service':'set_cover_tilt_position','service_data':{'tilt_position':round(value)}}",
                 "push_expr": "attrs.get('current_tilt_position',0)"},
            ],
        },
    },
    {
        "domain": "cover", "device_class": "curtain", "primary_group": ColorGroup.GREY,
        "model": "HA Cover (curtain)",
        "model_uid": "ha-cover-curtain",
        "vendor_name": "Home Assistant",
        "output": {
            "function": OutputFunction.POSITIONAL, "default_group": ColorClass.BLINDS, "output_usage": 0,
            "variable_ramp": False, "mode": OutputMode.GRADUAL, "groups": [2],
            "placement_choice": True,
            "channels": [{"channel_type": OutputChannelType.SHADE_POSITION_INDOOR,
                          "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(value)}}",
                          "push_expr": "attrs.get('current_position',0)"}],
            "channels_outdoor": [{"channel_type": OutputChannelType.SHADE_POSITION_OUTSIDE,
                                   "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(value)}}",
                                   "push_expr": "attrs.get('current_position',0)"}],
        },
    },
    {
        "domain": "cover", "device_class": "damper", "primary_group": ColorGroup.BLUE,
        "model": "HA Cover (damper)",
        "model_uid": "ha-cover-damper",
        "vendor_name": "Home Assistant",
        "output": {
            "function": OutputFunction.POSITIONAL, "default_group": ColorClass.VENTILATION, "output_usage": 0,
            "variable_ramp": False, "mode": OutputMode.GRADUAL, "groups": [3],
            "channels": [{"channel_type": OutputChannelType.AIR_FLAP_POSITION,
                          "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(value)}}",
                          "push_expr": "attrs.get('current_position',0)"}],  # AIR_FLAP_POSITION
        },
    },
    {
        "domain": "cover", "device_class": "door", "primary_group": ColorGroup.GREEN,
        "model": "HA Cover (door)",
        "model_uid": "ha-cover-door",
        "vendor_name": "Home Assistant",
        "output": {
            "function": OutputFunction.ON_OFF, "default_group": ColorClass.ACCESS, "output_usage": 0,
            "variable_ramp": False, "mode": OutputMode.BINARY, "groups": [7],
            "channels": [{"channel_type": OutputChannelType.POWER_STATE,
                          "apply_expr": "{'domain':'cover','service':'open_cover' if value>=1 else 'close_cover','service_data':{}}",
                          "push_expr": "1 if entity.state in ('open','opening') else 0"}],  # POWER_STATE
        },
    },
    {
        "domain": "cover", "device_class": "garage", "primary_group": ColorGroup.GREEN,
        "model": "HA Cover (garage)",
        "model_uid": "ha-cover-garage",
        "vendor_name": "Home Assistant",
        "output": {
            "function": OutputFunction.ON_OFF, "default_group": ColorClass.ACCESS, "output_usage": 0,
            "variable_ramp": False, "mode": OutputMode.BINARY, "groups": [7],
            "channels": [{"channel_type": OutputChannelType.POWER_STATE,
                          "apply_expr": "{'domain':'cover','service':'open_cover' if value>=1 else 'close_cover','service_data':{}}",
                          "push_expr": "1 if entity.state in ('open','opening') else 0"}],  # POWER_STATE
        },
    },
    {
        "domain": "cover", "device_class": "gate", "primary_group": ColorGroup.GREEN,
        "model": "HA Cover (gate)",
        "model_uid": "ha-cover-gate",
        "vendor_name": "Home Assistant",
        "output": {
            "function": OutputFunction.POSITIONAL,
            "function_choices": [(OutputFunction.POSITIONAL.value, "Positional — supports position feedback (2)"), (OutputFunction.ON_OFF.value, "On/Off only (0)")],
            "default_group": ColorClass.ACCESS, "output_usage": 0,
            "variable_ramp": False, "mode": OutputMode.GRADUAL, "groups": [7],
            "channels": [{"channel_type": OutputChannelType.SHADE_POSITION_OUTSIDE,
                          "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(100-value)}}",
                          "push_expr": "round(100-attrs.get('current_position',0),1)"}],  # SHADE_POSITION_OUTSIDE
        },
    },
    {
        "domain": "cover", "device_class": "shade", "primary_group": ColorGroup.GREY,
        "model": "HA Cover (shade)",
        "model_uid": "ha-cover-shade",
        "vendor_name": "Home Assistant",
        "output": {
            "function": OutputFunction.POSITIONAL, "default_group": ColorClass.BLINDS, "output_usage": 0,
            "variable_ramp": False, "mode": OutputMode.GRADUAL, "groups": [2],
            "placement_choice": True,
            "channels": [{"channel_type": OutputChannelType.SHADE_POSITION_INDOOR,
                          "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(value)}}",
                          "push_expr": "attrs.get('current_position',0)"}],
            "channels_outdoor": [{"channel_type": OutputChannelType.SHADE_POSITION_OUTSIDE,
                                   "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(value)}}",
                                   "push_expr": "attrs.get('current_position',0)"}],
        },
    },
    {
        "domain": "cover", "device_class": "shutter", "primary_group": ColorGroup.GREY,
        "model": "HA Cover (shutter)",
        "model_uid": "ha-cover-shutter",
        "vendor_name": "Home Assistant",
        "output": {
            "function": OutputFunction.POSITIONAL, "default_group": ColorClass.BLINDS, "output_usage": 0,
            "variable_ramp": False, "mode": OutputMode.GRADUAL, "groups": [2],
            "channels": [
                {"channel_type": OutputChannelType.SHADE_POSITION_OUTSIDE,
                 "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(100-value)}}",
                 "push_expr": "round(100-attrs.get('current_position',0),1)"},
                {"channel_type": OutputChannelType.SHADE_OPENING_ANGLE_OUTSIDE,
                 "apply_expr": "{'domain':'cover','service':'set_cover_tilt_position','service_data':{'tilt_position':round(value)}}",
                 "push_expr": "attrs.get('current_tilt_position',0)"},
            ],
        },
    },
    {
        "domain": "cover", "device_class": "window", "primary_group": ColorGroup.BLUE,
        "model": "HA Cover (window)",
        "model_uid": "ha-cover-window",
        "vendor_name": "Home Assistant",
        "output": {
            "function": OutputFunction.POSITIONAL,
            "function_choices": [(OutputFunction.POSITIONAL.value, "Positional — supports position feedback (2)"), (OutputFunction.ON_OFF.value, "On/Off only (0)")],
            "default_group": ColorClass.WINDOW, "output_usage": 0,
            "variable_ramp": False, "mode": OutputMode.GRADUAL, "groups": [3],
            "placement_choice": True,
            "channels": [{"channel_type": OutputChannelType.SHADE_POSITION_INDOOR,
                          "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(value)}}",
                          "push_expr": "attrs.get('current_position',0)"}],
            "channels_outdoor": [{"channel_type": OutputChannelType.SHADE_POSITION_OUTSIDE,
                                   "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(value)}}",
                                   "push_expr": "attrs.get('current_position',0)"}],
            "optional_tilt": True,
        },
    },
    # ── Event ────────────────────────────────────────────────────────────────
    {
        "domain": "event", "device_class": "button", "primary_group": ColorGroup.BLACK,
        "model": "HA Event (button)",
        "model_uid": "ha-event-button",
        "vendor_name": "Home Assistant",
        "button": {
            "button_type": ButtonType.SINGLE_PUSHBUTTON,
            "group": ButtonGroup.JOKER,
            "group_choices": _BTN_GROUP_CHOICES,
            "function": ButtonFunctionJoker.APP,
            "mode": ButtonMode.STANDARD,
            "supports_local_key_mode": False,
            "calls_present": False,
        },
    },
    {
        "domain": "event", "device_class": "doorbell", "primary_group": ColorGroup.BLACK,
        "model": "HA Event (doorbell)",
        "model_uid": "ha-event-doorbell",
        "vendor_name": "Home Assistant",
        "button": {
            "button_type": ButtonType.SINGLE_PUSHBUTTON,
            "group": ButtonGroup.JOKER,
            "function": ButtonFunctionJoker.DOOR_BELL,
            "mode": ButtonMode.STANDARD,
            "supports_local_key_mode": False,
            "calls_present": False,
        },
    },
    {
        "domain": "event", "device_class": "motion", "primary_group": ColorGroup.BLACK,
        "model": "HA Event (motion)",
        "model_uid": "ha-event-motion",
        "vendor_name": "Home Assistant",
        "binary_input": {
            "sensor_function": BinaryInputType.MOTION, "group": BinaryInputGroup.LIGHT, "group_choices": _BI_GROUP_ALL,
            "input_usage": BinaryInputUsage.ROOM_CLIMATE, "input_usage_choices": _BI_USAGE_ALL,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    # ── Fan ──────────────────────────────────────────────────────────────────
    {
        "domain": "fan", "device_class": None, "primary_group": ColorGroup.BLUE,
        "model": "HA Fan",
        "model_uid": "ha-fan-none",
        "vendor_name": "Home Assistant",
        "output": {
            "function": OutputFunction.DIMMER, "default_group": ColorClass.VENTILATION, "output_usage": OutputUsage.ROOM,
            "variable_ramp": True, "mode": OutputMode.DEFAULT, "groups": [3],
            "channels": [
                {"channel_type": OutputChannelType.AIR_FLOW_INTENSITY,
                 "apply_expr": "{'domain':'fan','service':'set_percentage','service_data':{'percentage':round(value)}}",
                 "push_expr": "attrs.get('percentage',0) or 0"},
                {"channel_type": OutputChannelType.AIR_FLOW_DIRECTION,
                 "apply_expr": "{'domain':'fan','service':'set_direction','service_data':{'direction':'forward' if value<=1 else 'reverse'}}",
                 "push_expr": "0 if attrs.get('direction','forward')=='forward' else 2"},
            ],
        },
    },
    # ── Light ─────────────────────────────────────────────────────────────────
    {
        "domain": "light", "device_class": None, "primary_group": ColorGroup.YELLOW,
        "model": "HA Light",
        "model_uid": "ha-light",
        "vendor_name": "Home Assistant",
        "derive_fn": _derive_light_output_config,
    },
    # ── Lock ──────────────────────────────────────────────────────────────────
    {
        "domain": "lock", "device_class": None, "primary_group": ColorGroup.BLACK,
        "model": "HA Lock",
        "model_uid": "ha-lock-none",
        "vendor_name": "Home Assistant",
        "output": {
            "function": OutputFunction.CUSTOM, "default_group": ColorClass.JOKER, "output_usage": OutputUsage.ROOM,
            "variable_ramp": False, "mode": OutputMode.BINARY, "groups": [8],
            "channels": [{"channel_type": OutputChannelType.POWER_STATE,
                          "apply_expr": "{'domain':'lock','service':'lock' if value==0 else 'unlock','service_data':{}}",
                          "push_expr": "0 if entity.state=='locked' else 1"}],  # POWER_STATE
        },
        "binary_input": {
            "sensor_function": BinaryInputType.DOOR_OPEN, "group": BinaryInputGroup.ACCESS, "input_usage": BinaryInputUsage.UNDEFINED,
            "input_type": INPUT_TYPE_DETECTS_CHANGES, "update_interval": 1.0,
        },
    },
    # ── Number ────────────────────────────────────────────────────────────────
    {
        "domain": "number", "device_class": None, "primary_group": ColorGroup.BLACK,
        "model": "HA Number",
        "model_uid": "ha-number-none",
        "vendor_name": "Home Assistant",
        "output": {
            "function": OutputFunction.POSITIONAL, "default_group": ColorClass.JOKER, "output_usage": OutputUsage.ROOM,
            "variable_ramp": True, "mode": OutputMode.DEFAULT, "groups": [8],
            "channels": [{"channel_type": OutputChannelType.POWER_LEVEL,
                          "apply_expr": "{'domain':'number','service':'set_value','service_data':{'value':round(_denorm(value,float(attrs.get('min',0)),float(attrs.get('max',100))),2)}}",
                          "push_expr": "_norm(float(entity.state),float(attrs.get('min',0)),float(attrs.get('max',100)))"}],  # POWER_LEVEL
        },
    },
    # ── Sensor ────────────────────────────────────────────────────────────────
    {
        "domain": "sensor", "device_class": None, "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor",
        "model_uid": "ha-sensor-none",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.TEMPERATURE,
            "sensor_type_choices": "any",  # full SensorType selector
            "sensor_usage": SensorUsage.UNDEFINED,
            "sensor_usage_choices": "any",
            "min": 0.0, "max": 100.0, "resolution": 0.1,
            "min_max_user": True,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "apparent_power", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (apparent_power)",
        "model_uid": "ha-sensor-apparent_power",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.APPARENT_POWER, "sensor_usage": SensorUsage.DEVICE_LEVEL,
            "min": 0.0, "max": 10000.0, "resolution": 1.0,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "aqi", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (aqi)",
        "model_uid": "ha-sensor-aqi",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.NONE, "sensor_usage": SensorUsage.ROOM,
            "sensor_usage_choices": _SU_ROOM_OUTDOOR,
            "min": 0.0, "max": 500.0, "resolution": 1.0,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "atmospheric_pressure", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (atmospheric_pressure)",
        "model_uid": "ha-sensor-atmospheric_pressure",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.AIR_PRESSURE, "sensor_usage": SensorUsage.OUTDOOR,
            "min": 800.0, "max": 1100.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "battery", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (battery)",
        "model_uid": "ha-sensor-battery",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.PERCENT, "sensor_usage": SensorUsage.DEVICE_LEVEL,
            "min": 0.0, "max": 100.0, "resolution": 0.5,
            "update_interval": 60.0, "alive_sign_interval": 240.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "carbon_dioxide", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (carbon_dioxide)",
        "model_uid": "ha-sensor-carbon_dioxide",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.CO2_CONCENTRATION, "sensor_usage": SensorUsage.ROOM,
            "min": 0.0, "max": 5000.0, "resolution": 1.0,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "carbon_monoxide", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (carbon_monoxide)",
        "model_uid": "ha-sensor-carbon_monoxide",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.CO_CONCENTRATION, "sensor_usage": SensorUsage.ROOM,
            "min": 0.0, "max": 1000.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "current", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (current)",
        "model_uid": "ha-sensor-current",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.ELECTRIC_CURRENT, "sensor_usage": SensorUsage.DEVICE_LEVEL,
            "min": 0.0, "max": 100.0, "resolution": 0.01,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "distance", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (distance)",
        "model_uid": "ha-sensor-distance",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.LENGTH, "sensor_usage": SensorUsage.DEVICE_LEVEL,
            "sensor_usage_choices": _SU_DEVICE_LEVEL,
            "min": 0.0, "max": 1000.0, "resolution": 0.01,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "duration", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (duration)",
        "model_uid": "ha-sensor-duration",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.DURATION, "sensor_usage": SensorUsage.DEVICE_LEVEL,
            "sensor_usage_choices": _SU_DEVICE_LEVEL,
            "min": 0.0, "max": 86400.0, "resolution": 1.0,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "energy", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (energy)",
        "model_uid": "ha-sensor-energy",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.ENERGY_METER, "sensor_usage": SensorUsage.DEVICE_LEVEL,
            "min": 0.0, "max": 100000.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "frequency", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (frequency)",
        "model_uid": "ha-sensor-frequency",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.FREQUENCY, "sensor_usage": SensorUsage.DEVICE_LEVEL,
            "min": 0.0, "max": 1000.0, "resolution": 0.01,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "gas", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (gas)",
        "model_uid": "ha-sensor-gas",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.NONE,
            "sensor_type_choices": [(SensorType.NONE.value, "None / Generic (0)"), (SensorType.GAS_TYPE.value, "Gas Type (7)")],
            "sensor_usage": SensorUsage.UNDEFINED,
            "sensor_usage_choices": [(SensorUsage.UNDEFINED.value, "Generic (0)"), (SensorUsage.ROOM.value, "Room (1)"), (SensorUsage.OUTDOOR.value, "Outdoor (2)"), (SensorUsage.DEVICE_LEVEL.value, "Device Level (4)")],
            "min": 0.0, "max": 100.0, "resolution": 1.0,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "humidity", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (humidity)",
        "model_uid": "ha-sensor-humidity",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.HUMIDITY, "sensor_usage": SensorUsage.UNDEFINED,
            "sensor_usage_choices": [(SensorUsage.UNDEFINED.value, "Generic (0)"), (SensorUsage.ROOM.value, "Room (1)"), (SensorUsage.OUTDOOR.value, "Outdoor (2)"), (SensorUsage.DEVICE_LEVEL.value, "Device Level (4)")],
            "min": 0.0, "max": 100.0, "resolution": 0.5,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "illuminance", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (illuminance)",
        "model_uid": "ha-sensor-illuminance",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.ILLUMINATION, "sensor_usage": SensorUsage.UNDEFINED,
            "sensor_usage_choices": [(SensorUsage.UNDEFINED.value, "Generic (0)"), (SensorUsage.ROOM.value, "Room (1)"), (SensorUsage.OUTDOOR.value, "Outdoor (2)"), (SensorUsage.DEVICE_LEVEL.value, "Device Level (4)")],
            "min": 0.0, "max": 100000.0, "resolution": 1.0,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "moisture", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (moisture)",
        "model_uid": "ha-sensor-moisture",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.NONE, "sensor_usage": SensorUsage.UNDEFINED,
            "sensor_usage_choices": [(SensorUsage.UNDEFINED.value, "Generic (0)"), (SensorUsage.ROOM.value, "Room (1)"), (SensorUsage.OUTDOOR.value, "Outdoor (2)"), (SensorUsage.DEVICE_LEVEL.value, "Device Level (4)")],
            "min": 0.0, "max": 100.0, "resolution": 0.5,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "pm1", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (pm1)",
        "model_uid": "ha-sensor-pm1",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.PARTICLES_PM1, "sensor_usage": SensorUsage.ROOM,
            "min": 0.0, "max": 500.0, "resolution": 1.0,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "pm10", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (pm10)",
        "model_uid": "ha-sensor-pm10",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.PARTICLES_PM10, "sensor_usage": SensorUsage.ROOM,
            "min": 0.0, "max": 500.0, "resolution": 1.0,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "pm25", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (pm25)",
        "model_uid": "ha-sensor-pm25",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.PARTICLES_PM2_5, "sensor_usage": SensorUsage.ROOM,
            "min": 0.0, "max": 500.0, "resolution": 1.0,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "power", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (power)",
        "model_uid": "ha-sensor-power",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.ACTIVE_POWER, "sensor_usage": SensorUsage.DEVICE_LEVEL,
            "min": 0.0, "max": 10000.0, "resolution": 1.0,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "power_factor", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (power_factor)",
        "model_uid": "ha-sensor-power_factor",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.PERCENT, "sensor_usage": SensorUsage.DEVICE_LEVEL,
            "min": 0.0, "max": 100.0, "resolution": 0.5,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "precipitation", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (precipitation)",
        "model_uid": "ha-sensor-precipitation",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.PRECIPITATION, "sensor_usage": SensorUsage.OUTDOOR,
            "min": 0.0, "max": 200.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "sound_pressure", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (sound_pressure)",
        "model_uid": "ha-sensor-sound_pressure",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.SOUND_PRESSURE_LEVEL, "sensor_usage": SensorUsage.DEVICE_LEVEL,
            "min": 0.0, "max": 130.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "speed", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (speed)",
        "model_uid": "ha-sensor-speed",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.NONE, "sensor_usage": SensorUsage.UNDEFINED,
            "sensor_usage_choices": [(SensorUsage.UNDEFINED.value, "Generic (0)"), (SensorUsage.ROOM.value, "Room (1)"), (SensorUsage.OUTDOOR.value, "Outdoor (2)"), (SensorUsage.DEVICE_LEVEL.value, "Device Level (4)")],
            "min": 0.0, "max": 60.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "temperature", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (temperature)",
        "model_uid": "ha-sensor-temperature",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.TEMPERATURE, "sensor_usage": SensorUsage.UNDEFINED,
            "sensor_usage_choices": [(SensorUsage.UNDEFINED.value, "Generic (0)"), (SensorUsage.ROOM.value, "Room (1)"), (SensorUsage.OUTDOOR.value, "Outdoor (2)"), (SensorUsage.DEVICE_LEVEL.value, "Device Level (4)")],
            "min": -40.0, "max": 85.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "voltage", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (voltage)",
        "model_uid": "ha-sensor-voltage",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.SUPPLY_VOLTAGE, "sensor_usage": SensorUsage.DEVICE_LEVEL,
            "min": 0.0, "max": 500.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "water", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (water)",
        "model_uid": "ha-sensor-water",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.WATER_QUANTITY, "sensor_usage": SensorUsage.DEVICE_LEVEL,
            "min": 0.0, "max": 10000.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "weight", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (weight)",
        "model_uid": "ha-sensor-weight",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.MASS, "sensor_usage": SensorUsage.DEVICE_LEVEL,
            "min": 0.0, "max": 1000.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    {
        "domain": "sensor", "device_class": "wind_speed", "primary_group": ColorGroup.BLACK,
        "model": "HA Sensor (wind_speed)",
        "model_uid": "ha-sensor-wind_speed",
        "vendor_name": "Home Assistant",
        "sensor": {
            "sensor_type": SensorType.WIND_SPEED,
            "sensor_type_choices": [(SensorType.WIND_SPEED.value, "Wind Speed (13)"), (SensorType.WIND_GUST_SPEED.value, "Wind Gust Speed (23)")],
            "sensor_usage": SensorUsage.OUTDOOR,
            "min": 0.0, "max": 60.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": SensorGroup.JOKER,
        },
    },
    # ── Siren ────────────────────────────────────────────────────────────────
    {
        "domain": "siren", "device_class": None, "primary_group": ColorGroup.BLACK,
        "model": "HA Siren",
        "model_uid": "ha-siren-none",
        "vendor_name": "Home Assistant",
        "output": {
            "function": OutputFunction.CUSTOM, "default_group": ColorClass.JOKER, "output_usage": OutputUsage.ROOM,
            "variable_ramp": False, "mode": OutputMode.BINARY, "groups": [8],
            "channels": [
                {"channel_type": OutputChannelType.POWER_STATE,
                 "apply_expr": "{'domain':'siren','service':'turn_on' if value>=1 else 'turn_off','service_data':{}}",
                 "push_expr": "1 if entity.state=='on' else 0"},
                {"channel_type": OutputChannelType.AUDIO_VOLUME,
                 "apply_expr": "{'domain':'siren','service':'turn_on','service_data':{'volume_level':round(value/100,2)}}",
                 "push_expr": "round(attrs.get('volume_level',1)*100,1)"},
            ],
        },
    },
    # ── Switch ───────────────────────────────────────────────────────────────
    {
        "domain": "switch", "device_class": None, "primary_group": ColorGroup.BLACK,
        "model": "HA Switch",
        "model_uid": "ha-switch-none",
        "vendor_name": "Home Assistant",
        "output": {
            "function": OutputFunction.ON_OFF, "default_group": ColorClass.JOKER, "output_usage": OutputUsage.ROOM,
            "variable_ramp": False, "mode": OutputMode.BINARY, "groups": [8],
            "channels": [{"channel_type": OutputChannelType.POWER_STATE,
                          "apply_expr": "{'domain':'switch','service':'turn_on' if value>=1 else 'turn_off','service_data':{}}",
                          "push_expr": "1 if entity.state=='on' else 0"}],
        },
    },
    {
        "domain": "switch", "device_class": "outlet", "primary_group": ColorGroup.BLACK,
        "model": "HA Switch (outlet)",
        "model_uid": "ha-switch-outlet",
        "vendor_name": "Home Assistant",
        "output": {
            "function": OutputFunction.ON_OFF, "default_group": ColorClass.JOKER, "output_usage": OutputUsage.ROOM,
            "variable_ramp": False, "mode": OutputMode.BINARY, "groups": [8],
            "channels": [{"channel_type": OutputChannelType.POWER_STATE,
                          "apply_expr": "{'domain':'switch','service':'turn_on' if value>=1 else 'turn_off','service_data':{}}",
                          "push_expr": "1 if entity.state=='on' else 0"}],
        },
    },
    {
        "domain": "switch", "device_class": "switch", "primary_group": ColorGroup.BLACK,
        "model": "HA Switch (switch)",
        "model_uid": "ha-switch-switch",
        "vendor_name": "Home Assistant",
        "output": {
            "function": OutputFunction.ON_OFF, "default_group": ColorClass.JOKER, "output_usage": OutputUsage.ROOM,
            "variable_ramp": False, "mode": OutputMode.BINARY, "groups": [8],
            "channels": [{"channel_type": OutputChannelType.POWER_STATE,
                          "apply_expr": "{'domain':'switch','service':'turn_on' if value>=1 else 'turn_off','service_data':{}}",
                          "push_expr": "1 if entity.state=='on' else 0"}],
        },
    },
    # ── Valve ────────────────────────────────────────────────────────────────
    {
        "domain": "valve", "device_class": None, "primary_group": ColorGroup.BLUE,
        "model": "HA Valve",
        "model_uid": "ha-valve-none",
        "vendor_name": "Home Assistant",
        "output": {
            "function": OutputFunction.ON_OFF, "default_group": ColorClass.HEATING, "output_usage": OutputUsage.ROOM,
            "variable_ramp": False, "mode": OutputMode.BINARY, "groups": [3],
            "channels": [{"channel_type": OutputChannelType.POWER_STATE,
                          "apply_expr": "{'domain':'valve','service':'open_valve' if value>=1 else 'close_valve','service_data':{}}",
                          "push_expr": "1 if entity.state=='open' else 0"}],
        },
    },
    {
        "domain": "valve", "device_class": "gas", "primary_group": ColorGroup.BLUE,
        "model": "HA Valve (gas)",
        "model_uid": "ha-valve-gas",
        "vendor_name": "Home Assistant",
        "output": {
            "function": OutputFunction.ON_OFF, "default_group": ColorClass.HEATING, "output_usage": OutputUsage.ROOM,
            "variable_ramp": False, "mode": OutputMode.BINARY, "groups": [3],
            "channels": [{"channel_type": OutputChannelType.POWER_STATE,
                          "apply_expr": "{'domain':'valve','service':'open_valve' if value>=1 else 'close_valve','service_data':{}}",
                          "push_expr": "1 if entity.state=='open' else 0"}],
        },
    },
    {
        "domain": "valve", "device_class": "water", "primary_group": ColorGroup.BLUE,
        "model": "HA Valve (water)",
        "model_uid": "ha-valve-water",
        "vendor_name": "Home Assistant",
        "output": {
            "function": OutputFunction.POSITIONAL, "default_group": ColorClass.HEATING, "output_usage": OutputUsage.ROOM,
            "variable_ramp": True, "mode": OutputMode.DEFAULT, "groups": [3],
            "channels": [{"channel_type": OutputChannelType.WATER_FLOW_RATE,
                          "apply_expr": "{'domain':'valve','service':'set_valve_position','service_data':{'position':round(value)}}",
                          "push_expr": "attrs.get('current_position',0)"}],  # WATER_FLOW_RATE
        },
    },
    {
        "domain": "valve", "device_class": "water_heater", "primary_group": ColorGroup.BLUE,
        "model": "HA Valve (water_heater)",
        "model_uid": "ha-valve-water_heater",
        "vendor_name": "Home Assistant",
        "output": {
            "function": OutputFunction.POSITIONAL, "default_group": ColorClass.HEATING, "output_usage": OutputUsage.ROOM,
            "variable_ramp": True, "mode": OutputMode.DEFAULT, "groups": [3],
            "channels": [{"channel_type": OutputChannelType.WATER_FLOW_RATE,
                          "apply_expr": "{'domain':'valve','service':'set_valve_position','service_data':{'position':round(value)}}",
                          "push_expr": "attrs.get('current_position',0)"}],
        },
    },
]

# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

# Build fast-lookup index: (domain, device_class) → entry
_MAPPING_INDEX: dict[tuple[str, str | None], dict[str, Any]] = {
    (e["domain"], e["device_class"]): e for e in ENTITY_MAPPING
}

# Supported HA domains (for EntitySelector domain filter)
SUPPORTED_DOMAINS: list[str] = sorted({e["domain"] for e in ENTITY_MAPPING})


# Human-readable labels for OutputChannelType integer values.
CHANNEL_TYPE_LABELS: dict[int, str] = {
    0: "Default (none / catch-all)",
    1: "Brightness",
    2: "Hue",
    3: "Saturation",
    4: "Color Temperature (mired, 100–1000)",
    5: "CIE X",
    6: "CIE Y",
    7: "Shade Position — Outside (0–100 %)",
    8: "Shade Position — Indoor (0–100 %)",
    9: "Shade Opening Angle — Outside",
    10: "Shade Opening Angle — Indoor",
    11: "Transparency",
    12: "Air Flow Intensity",
    13: "Air Flow Direction",
    14: "Air Flap Position",
    15: "Air Louver Position",
    16: "Heating Power",
    17: "Cooling Capacity",
    18: "Audio Volume",
    19: "Power State",
    20: "Fan Speed",
    21: "Ventilation AirFlowIntensity",
    22: "Ventilation AirFlowDirection",
    23: "Water Flow Rate",
    24: "Power Level",
    25: "Video Station",
    26: "Video Input Source",
}


def get_entity_mapping(domain: str, device_class: str | None) -> dict[str, Any] | None:
    """Return the mapping entry for (domain, device_class), or None if unsupported."""
    entry = _MAPPING_INDEX.get((domain, device_class))
    if entry is None and device_class is not None:
        # Fall back to None device_class if the specific one isn't mapped
        entry = _MAPPING_INDEX.get((domain, None))
    return entry


def resolve_entity_mapping(
    entity_id: str,
    state,
    domain: str,
    device_class: str | None,
) -> dict[str, Any] | None:
    """Return the fully resolved mapping, calling derive_fn when present.

    derive_fn is called only at config time; the result is merged over the base
    entry. The returned dict contains no callables — safe to serialise.
    """
    mapping = get_entity_mapping(domain, device_class)
    if mapping is None:
        return None
    derive_fn = mapping.get("derive_fn")
    if derive_fn is None:
        return mapping
    derived = derive_fn(entity_id, state)
    return {k: v for k, v in {**mapping, **derived}.items() if k != "derive_fn"}


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
        ):
            return True
    return False
