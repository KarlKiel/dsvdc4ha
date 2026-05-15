"""Static mapping from HA entity types / device_classes to dS vdSD configuration."""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Channel type name → OutputChannelType integer (from pydsvdcapi)
# ---------------------------------------------------------------------------
_CHANNEL_TYPE_NAMES: dict[str, int] = {
    "BRIGHTNESS": 1,
    "HUE": 2,
    "SATURATION": 3,
    "COLOR_TEMPERATURE": 4,
    "CIE_X": 5,
    "CIE_Y": 6,
    "SHADE_POSITION_OUTSIDE": 7,
    "SHADE_POSITION_INDOOR": 8,
    "SHADE_OPENING_ANGLE_OUTSIDE": 9,
    "SHADE_OPENING_ANGLE_INDOOR": 10,
    "AIR_FLOW_INTENSITY": 12,
    "AIR_FLOW_DIRECTION": 13,
    "AIR_FLAP_POSITION": 14,
    "AUDIO_VOLUME": 18,
    "POWER_STATE": 19,
    "WATER_FLOW_RATE": 23,
    "POWER_LEVEL": 24,
}

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

ENTITY_MAPPING: list[dict[str, Any]] = [
    # ── Binary Sensor ───────────────────────────────────────────────────────
    {
        "domain": "binary_sensor", "device_class": None, "primary_group": 8,
        "binary_input": {
            "sensor_function": 0,
            "sensor_function_choices": "any",
            "group": 8, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "battery", "primary_group": 8,
        "binary_input": {
            "sensor_function": 12, "group": 8, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "battery_charging", "primary_group": 8,
        "binary_input": {
            "sensor_function": 0, "group": 8, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "carbon_monoxide", "primary_group": 8,
        "binary_input": {
            "sensor_function": 0, "group": 6, "group_choices": _BI_GROUP_ALL,
            "input_usage": 1, "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "cold", "primary_group": 8,
        "binary_input": {
            "sensor_function": 18,
            "sensor_function_choices": [(18, "Frost (18)"), (0, "Generic (0)")],
            "group": 3, "group_choices": _BI_GROUP_ALL,
            "input_usage": 2, "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "connectivity", "primary_group": 8,
        "binary_input": {
            "sensor_function": 23, "group": 8, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "door", "primary_group": 8,
        "binary_input": {
            "sensor_function": 14, "group": 7, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "garage_door", "primary_group": 8,
        "binary_input": {
            "sensor_function": 16, "group": 7, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "gas", "primary_group": 8,
        "binary_input": {
            "sensor_function": 0, "group": 6, "group_choices": _BI_GROUP_ALL,
            "input_usage": 1, "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "heat", "primary_group": 8,
        "binary_input": {
            "sensor_function": 11, "group": 3, "group_choices": _BI_GROUP_ALL,
            "input_usage": 1, "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "light", "primary_group": 8,
        "binary_input": {
            "sensor_function": 2, "group": 1, "group_choices": _BI_GROUP_ALL,
            "input_usage": 1, "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "lock", "primary_group": 8,
        "binary_input": {
            "sensor_function": 14, "group": 7, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "moisture", "primary_group": 8,
        "binary_input": {
            "sensor_function": 0, "group": 6, "group_choices": _BI_GROUP_MOISTURE,
            "input_usage": 0, "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "motion", "primary_group": 8,
        "binary_input": {
            "sensor_function": 5, "group": 1, "group_choices": _BI_GROUP_ALL,
            "input_usage": 1, "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "moving", "primary_group": 8,
        "binary_input": {
            "sensor_function": 5, "sensor_function_choices": "any",
            "group": 8, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "occupancy", "primary_group": 8,
        "binary_input": {
            "sensor_function": 1, "group": 1, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "opening", "primary_group": 8,
        "binary_input": {
            "sensor_function": 0, "group": 8, "group_choices": _BI_GROUP_ALL,
            "input_usage": 0, "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "plug", "primary_group": 8,
        "binary_input": {
            "sensor_function": 0, "group": 8, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "power", "primary_group": 8,
        "binary_input": {
            "sensor_function": 0, "group": 8, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "presence", "primary_group": 8,
        "binary_input": {
            "sensor_function": 1, "group": 1, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "problem", "primary_group": 8,
        "binary_input": {
            "sensor_function": 22, "group": 8, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "running", "primary_group": 8,
        "binary_input": {
            "sensor_function": 0, "group": 8, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "safety", "primary_group": 8,
        "binary_input": {
            "sensor_function": 0, "group": 6, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "smoke", "primary_group": 8,
        "binary_input": {
            "sensor_function": 7, "group": 6, "input_usage": 1,
            "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "sound", "primary_group": 8,
        "binary_input": {
            "sensor_function": 0, "group": 8, "group_choices": _BI_GROUP_ALL,
            "input_usage": 1, "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "tamper", "primary_group": 8,
        "binary_input": {
            "sensor_function": 23, "group": 6, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "update", "primary_group": 8,
        "binary_input": {
            "sensor_function": 23, "group": 8, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "vibration", "primary_group": 8,
        "binary_input": {
            "sensor_function": 0, "group": 8, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
    {
        "domain": "binary_sensor", "device_class": "window", "primary_group": 8,
        "binary_input": {
            "sensor_function": 13, "group": 7, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
    # ── Button ──────────────────────────────────────────────────────────────
    {
        "domain": "button", "device_class": None, "primary_group": 8,
        "button": {
            "button_type": 1,
            "group": 8,
            "function": 15,
            "mode": 0,
            "supports_local_key_mode": True,
            "calls_present": True,
        },
    },
    # ── Cover ────────────────────────────────────────────────────────────────
    {
        "domain": "cover", "device_class": "awning", "primary_group": 2,
        "output": {
            "function": 2, "default_group": 2, "output_usage": 2,
            "variable_ramp": True, "mode": 2, "groups": [2],
            "channels": [{"channel_type": 7,
                          "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(100-value)}}",
                          "push_expr": "round(100-attrs.get('current_position',0),1)"}],  # SHADE_POSITION_OUTSIDE
        },
    },
    {
        "domain": "cover", "device_class": "blind", "primary_group": 2,
        "output": {
            "function": 2, "default_group": 2,
            "output_usage": 1,
            "output_usage_choices": [(1, "Room / Indoor (1)"), (2, "Outdoors (2)")],
            "variable_ramp": True, "mode": 2, "groups": [2],
            # channels depend on outputUsage (resolved in builder)
            "channels": [
                {"channel_type": 8,
                 "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(100-value)}}",
                 "push_expr": "round(100-attrs.get('current_position',0),1)"},
                {"channel_type": 10,
                 "apply_expr": "{'domain':'cover','service':'set_cover_tilt_position','service_data':{'tilt_position':round(value)}}",
                 "push_expr": "attrs.get('current_tilt_position',0)"},
            ],  # default indoor
            "channels_by_usage": {
                1: [
                    {"channel_type": 8,
                     "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(100-value)}}",
                     "push_expr": "round(100-attrs.get('current_position',0),1)"},
                    {"channel_type": 10,
                     "apply_expr": "{'domain':'cover','service':'set_cover_tilt_position','service_data':{'tilt_position':round(value)}}",
                     "push_expr": "attrs.get('current_tilt_position',0)"},
                ],   # indoor
                2: [
                    {"channel_type": 7,
                     "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(100-value)}}",
                     "push_expr": "round(100-attrs.get('current_position',0),1)"},
                    {"channel_type": 9,
                     "apply_expr": "{'domain':'cover','service':'set_cover_tilt_position','service_data':{'tilt_position':round(value)}}",
                     "push_expr": "attrs.get('current_tilt_position',0)"},
                ],    # outdoor
            },
        },
    },
    {
        "domain": "cover", "device_class": "curtain", "primary_group": 2,
        "output": {
            "function": 2, "default_group": 2, "output_usage": 1,
            "variable_ramp": True, "mode": 2, "groups": [2],
            "channels": [{"channel_type": 8,
                          "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(value)}}",
                          "push_expr": "attrs.get('current_position',0)"}],  # SHADE_POSITION_INDOOR
        },
    },
    {
        "domain": "cover", "device_class": "damper", "primary_group": 3,
        "output": {
            "function": 2, "default_group": 3, "output_usage": 1,
            "variable_ramp": True, "mode": 2, "groups": [3],
            "channels": [{"channel_type": 14,
                          "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(value)}}",
                          "push_expr": "attrs.get('current_position',0)"}],  # AIR_FLAP_POSITION
        },
    },
    {
        "domain": "cover", "device_class": "door", "primary_group": 7,
        "output": {
            "function": 0, "default_group": 7, "output_usage": 2,
            "variable_ramp": False, "mode": 1, "groups": [7],
            "channels": [{"channel_type": 19,
                          "apply_expr": "{'domain':'cover','service':'open_cover' if value>=1 else 'close_cover','service_data':{}}",
                          "push_expr": "1 if entity.state in ('open','opening') else 0"}],  # POWER_STATE
        },
    },
    {
        "domain": "cover", "device_class": "garage", "primary_group": 7,
        "output": {
            "function": 0, "default_group": 7, "output_usage": 2,
            "variable_ramp": False, "mode": 1, "groups": [7],
            "channels": [{"channel_type": 19,
                          "apply_expr": "{'domain':'cover','service':'open_cover' if value>=1 else 'close_cover','service_data':{}}",
                          "push_expr": "1 if entity.state in ('open','opening') else 0"}],  # POWER_STATE
        },
    },
    {
        "domain": "cover", "device_class": "gate", "primary_group": 7,
        "output": {
            "function": 2,
            "function_choices": [(2, "Positional — supports position feedback (2)"), (0, "On/Off only (0)")],
            "default_group": 7, "output_usage": 2,
            "variable_ramp": False, "mode": 2, "groups": [7],
            "channels": [{"channel_type": 7,
                          "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(100-value)}}",
                          "push_expr": "round(100-attrs.get('current_position',0),1)"}],  # SHADE_POSITION_OUTSIDE
        },
    },
    {
        "domain": "cover", "device_class": "shade", "primary_group": 2,
        "output": {
            "function": 2, "default_group": 2, "output_usage": 1,
            "variable_ramp": True, "mode": 2, "groups": [2],
            "channels": [{"channel_type": 8,
                          "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(value)}}",
                          "push_expr": "attrs.get('current_position',0)"}],  # SHADE_POSITION_INDOOR
        },
    },
    {
        "domain": "cover", "device_class": "shutter", "primary_group": 2,
        "output": {
            "function": 2, "default_group": 2, "output_usage": 2,
            "variable_ramp": True, "mode": 2, "groups": [2],
            "channels": [
                {"channel_type": 7,
                 "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(100-value)}}",
                 "push_expr": "round(100-attrs.get('current_position',0),1)"},
                {"channel_type": 9,
                 "apply_expr": "{'domain':'cover','service':'set_cover_tilt_position','service_data':{'tilt_position':round(value)}}",
                 "push_expr": "attrs.get('current_tilt_position',0)"},
            ],
        },
    },
    {
        "domain": "cover", "device_class": "window", "primary_group": 3,
        "output": {
            "function": 2,
            "function_choices": [(2, "Positional — supports position feedback (2)"), (0, "On/Off only (0)")],
            "default_group": 3, "output_usage": 1,
            "variable_ramp": True, "mode": 2, "groups": [3],
            "channels": [{"channel_type": 8,
                          "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(value)}}",
                          "push_expr": "attrs.get('current_position',0)"}],  # SHADE_POSITION_INDOOR
            "optional_tilt": True,               # user asked for second channel
        },
    },
    # ── Event ────────────────────────────────────────────────────────────────
    {
        "domain": "event", "device_class": "button", "primary_group": 8,
        "button": {
            "button_type": 1,
            "group": 8,
            "function": 15,
            "mode": 0,
            "supports_local_key_mode": False,
            "calls_present": False,
        },
    },
    {
        "domain": "event", "device_class": "doorbell", "primary_group": 8,
        "button": {
            "button_type": 1,
            "group": 8,   # JOKER — fixed
            "function": 5,  # Room / Door Bell — fixed
            "mode": 0,
            "supports_local_key_mode": False,
            "calls_present": False,
        },
    },
    {
        "domain": "event", "device_class": "motion", "primary_group": 8,
        "binary_input": {
            "sensor_function": 5, "group": 1, "group_choices": _BI_GROUP_ALL,
            "input_usage": 1, "input_type": 1, "update_interval": 1.0,
        },
    },
    # ── Fan ──────────────────────────────────────────────────────────────────
    {
        "domain": "fan", "device_class": None, "primary_group": 3,
        "output": {
            "function": 1, "default_group": 3, "output_usage": 1,
            "variable_ramp": True, "mode": 2, "groups": [3],
            "channels": [
                {"channel_type": 12,
                 "apply_expr": "{'domain':'fan','service':'set_percentage','service_data':{'percentage':round(value)}}",
                 "push_expr": "attrs.get('percentage',0) or 0"},
                {"channel_type": 13,
                 "apply_expr": "{'domain':'fan','service':'set_direction','service_data':{'direction':'forward' if value<=1 else 'reverse'}}",
                 "push_expr": "0 if attrs.get('direction','forward')=='forward' else 2"},
            ],
        },
    },
    # ── Light ─────────────────────────────────────────────────────────────────
    {
        "domain": "light", "device_class": None, "primary_group": 1,
        "output": {
            "function": 0, "default_group": 1, "output_usage": 1,
            "variable_ramp": False, "mode": 1, "groups": [1],
            "channels": [{"channel_type": 1,
                          "apply_expr": "{'domain':'light','service':'turn_on' if value>50 else 'turn_off','service_data':{}}",
                          "push_expr": "100.0 if entity.state=='on' else 0.0"}],  # BRIGHTNESS
        },
    },
    {
        "domain": "light", "device_class": "brightness", "primary_group": 1,
        "output": {
            "function": 1, "default_group": 1, "output_usage": 1,
            "variable_ramp": True, "mode": 2, "groups": [1],
            "channels": [{"channel_type": 1,
                          "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'brightness':round(value*2.55)}}",
                          "push_expr": "round(attrs.get('brightness',0)/2.55,1)"}],
        },
    },
    {
        "domain": "light", "device_class": "color_temp", "primary_group": 1,
        "output": {
            "function": 3, "default_group": 1, "output_usage": 1,
            "variable_ramp": True, "mode": 2, "groups": [1],
            "channels": [
                {"channel_type": 1,
                 "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'brightness':round(value*2.55)}}",
                 "push_expr": "round(attrs.get('brightness',0)/2.55,1)"},
                {"channel_type": 4,
                 "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'color_temp':round(value)}}",
                 "push_expr": "attrs.get('color_temp',370)"},
            ],
        },
    },
    {
        "domain": "light", "device_class": "rgb", "primary_group": 1,
        "output": {
            "function": 4, "default_group": 1, "output_usage": 1,
            "variable_ramp": True, "mode": 2, "groups": [1],
            "channels": [
                {"channel_type": 1,
                 "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'brightness':round(value*2.55)}}",
                 "push_expr": "round(attrs.get('brightness',0)/2.55,1)"},
                {"channel_type": 2,
                 "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'hs_color':(value,attrs.get('hs_color',(0,100))[1])}}",
                 "push_expr": "attrs.get('hs_color',(0,0))[0]"},
                {"channel_type": 3,
                 "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'hs_color':(attrs.get('hs_color',(0,100))[0],value)}}",
                 "push_expr": "attrs.get('hs_color',(0,100))[1]"},
                {"channel_type": 4,
                 "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'color_temp':round(value)}}",
                 "push_expr": "attrs.get('color_temp',370)"},
                {"channel_type": 5,
                 "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'xy_color':(round(value/10000,4),attrs.get('xy_color',(0.3127,0.3290))[1])}}",
                 "push_expr": "round(attrs.get('xy_color',(0.3127,0.3290))[0]*10000,1)"},
                {"channel_type": 6,
                 "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'xy_color':(attrs.get('xy_color',(0.3127,0.3290))[0],round(value/10000,4))}}",
                 "push_expr": "round(attrs.get('xy_color',(0.3127,0.3290))[1]*10000,1)"},
            ],
        },
    },
    # ── Lock ──────────────────────────────────────────────────────────────────
    {
        "domain": "lock", "device_class": None, "primary_group": 8,
        "output": {
            "function": 127, "default_group": 8, "output_usage": 0,
            "variable_ramp": False, "mode": 1, "groups": [8],
            "channels": [{"channel_type": 19,
                          "apply_expr": "{'domain':'lock','service':'lock' if value==0 else 'unlock','service_data':{}}",
                          "push_expr": "0 if entity.state=='locked' else 1"}],  # POWER_STATE
        },
        "binary_input": {
            "sensor_function": 14, "group": 7, "input_usage": 0,
            "input_type": 1, "update_interval": 1.0,
        },
    },
    # ── Number ────────────────────────────────────────────────────────────────
    {
        "domain": "number", "device_class": None, "primary_group": 8,
        "output": {
            "function": 2, "default_group": 8, "output_usage": 0,
            "variable_ramp": True, "mode": 2, "groups": [8],
            "channels": [{"channel_type": 24,
                          "apply_expr": "{'domain':'number','service':'set_value','service_data':{'value':round(_denorm(value,float(attrs.get('min',0)),float(attrs.get('max',100))),2)}}",
                          "push_expr": "_norm(float(entity.state),float(attrs.get('min',0)),float(attrs.get('max',100)))"}],  # POWER_LEVEL
        },
    },
    # ── Sensor ────────────────────────────────────────────────────────────────
    {
        "domain": "sensor", "device_class": None, "primary_group": 8,
        "sensor": {
            "sensor_type": 1,
            "sensor_type_choices": "any",  # full SensorType selector
            "sensor_usage": 0,
            "sensor_usage_choices": "any",
            "min": 0.0, "max": 100.0, "resolution": 0.1,
            "min_max_user": True,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    {
        "domain": "sensor", "device_class": "apparent_power", "primary_group": 8,
        "sensor": {
            "sensor_type": 17, "sensor_usage": 4,
            "min": 0.0, "max": 10000.0, "resolution": 1.0,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
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
    {
        "domain": "sensor", "device_class": "atmospheric_pressure", "primary_group": 8,
        "sensor": {
            "sensor_type": 18, "sensor_usage": 2,
            "min": 800.0, "max": 1100.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    {
        "domain": "sensor", "device_class": "battery", "primary_group": 8,
        "sensor": {
            "sensor_type": 32, "sensor_usage": 4,
            "min": 0.0, "max": 100.0, "resolution": 0.5,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    {
        "domain": "sensor", "device_class": "carbon_dioxide", "primary_group": 8,
        "sensor": {
            "sensor_type": 22, "sensor_usage": 1,
            "min": 0.0, "max": 5000.0, "resolution": 1.0,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    {
        "domain": "sensor", "device_class": "carbon_monoxide", "primary_group": 8,
        "sensor": {
            "sensor_type": 5, "sensor_usage": 1,
            "min": 0.0, "max": 1000.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    {
        "domain": "sensor", "device_class": "current", "primary_group": 8,
        "sensor": {
            "sensor_type": 15, "sensor_usage": 4,
            "min": 0.0, "max": 100.0, "resolution": 0.01,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
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
    {
        "domain": "sensor", "device_class": "duration", "primary_group": 8,
        "sensor": {
            "sensor_type": 31, "sensor_usage": 4,
            "sensor_usage_choices": _SU_DEVICE_LEVEL,
            "min": 0.0, "max": 86400.0, "resolution": 1.0,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    {
        "domain": "sensor", "device_class": "energy", "primary_group": 8,
        "sensor": {
            "sensor_type": 16, "sensor_usage": 4,
            "min": 0.0, "max": 100000.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    {
        "domain": "sensor", "device_class": "frequency", "primary_group": 8,
        "sensor": {
            "sensor_type": 34, "sensor_usage": 4,
            "min": 0.0, "max": 1000.0, "resolution": 0.01,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    {
        "domain": "sensor", "device_class": "gas", "primary_group": 8,
        "sensor": {
            "sensor_type": 0,
            "sensor_type_choices": [(0, "None / Generic (0)"), (7, "Gas Type (7)")],
            "sensor_usage": 0,
            "sensor_usage_choices": _SU_GENERAL,
            "min": 0.0, "max": 100.0, "resolution": 1.0,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
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
    {
        "domain": "sensor", "device_class": "illuminance", "primary_group": 8,
        "sensor": {
            "sensor_type": 3, "sensor_usage": 0,
            "sensor_usage_choices": _SU_GENERAL,
            "min": 0.0, "max": 100000.0, "resolution": 1.0,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    {
        "domain": "sensor", "device_class": "moisture", "primary_group": 8,
        "sensor": {
            "sensor_type": 0, "sensor_usage": 0,
            "sensor_usage_choices": _SU_GENERAL,
            "min": 0.0, "max": 100.0, "resolution": 0.5,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    {
        "domain": "sensor", "device_class": "pm1", "primary_group": 8,
        "sensor": {
            "sensor_type": 10, "sensor_usage": 1,
            "min": 0.0, "max": 500.0, "resolution": 1.0,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    {
        "domain": "sensor", "device_class": "pm10", "primary_group": 8,
        "sensor": {
            "sensor_type": 8, "sensor_usage": 1,
            "min": 0.0, "max": 500.0, "resolution": 1.0,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    {
        "domain": "sensor", "device_class": "pm25", "primary_group": 8,
        "sensor": {
            "sensor_type": 9, "sensor_usage": 1,
            "min": 0.0, "max": 500.0, "resolution": 1.0,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    {
        "domain": "sensor", "device_class": "power", "primary_group": 8,
        "sensor": {
            "sensor_type": 14, "sensor_usage": 4,
            "min": 0.0, "max": 10000.0, "resolution": 1.0,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    {
        "domain": "sensor", "device_class": "power_factor", "primary_group": 8,
        "sensor": {
            "sensor_type": 32, "sensor_usage": 4,
            "min": 0.0, "max": 100.0, "resolution": 0.5,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    {
        "domain": "sensor", "device_class": "precipitation", "primary_group": 8,
        "sensor": {
            "sensor_type": 21, "sensor_usage": 2,
            "min": 0.0, "max": 200.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    {
        "domain": "sensor", "device_class": "sound_pressure", "primary_group": 8,
        "sensor": {
            "sensor_type": 20, "sensor_usage": 4,
            "min": 0.0, "max": 130.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    {
        "domain": "sensor", "device_class": "speed", "primary_group": 8,
        "sensor": {
            "sensor_type": 0, "sensor_usage": 0,
            "sensor_usage_choices": _SU_GENERAL,
            "min": 0.0, "max": 60.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    {
        "domain": "sensor", "device_class": "temperature", "primary_group": 8,
        "sensor": {
            "sensor_type": 1, "sensor_usage": 0,
            "sensor_usage_choices": _SU_GENERAL,
            "min": -40.0, "max": 85.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    {
        "domain": "sensor", "device_class": "voltage", "primary_group": 8,
        "sensor": {
            "sensor_type": 4, "sensor_usage": 4,
            "min": 0.0, "max": 500.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    {
        "domain": "sensor", "device_class": "water", "primary_group": 8,
        "sensor": {
            "sensor_type": 27, "sensor_usage": 4,
            "min": 0.0, "max": 10000.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    {
        "domain": "sensor", "device_class": "weight", "primary_group": 8,
        "sensor": {
            "sensor_type": 30, "sensor_usage": 4,
            "min": 0.0, "max": 1000.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    {
        "domain": "sensor", "device_class": "wind_speed", "primary_group": 8,
        "sensor": {
            "sensor_type": 13,
            "sensor_type_choices": [(13, "Wind Speed (13)"), (23, "Wind Gust Speed (23)")],
            "sensor_usage": 2,
            "min": 0.0, "max": 60.0, "resolution": 0.1,
            "update_interval": 30.0, "alive_sign_interval": 120.0,
            "min_push_interval": 2.0, "changes_only_interval": 0.0, "group": 0,
        },
    },
    # ── Siren ────────────────────────────────────────────────────────────────
    {
        "domain": "siren", "device_class": None, "primary_group": 8,
        "output": {
            "function": 127, "default_group": 8, "output_usage": 0,
            "variable_ramp": False, "mode": 1, "groups": [8],
            "channels": [
                {"channel_type": 19,
                 "apply_expr": "{'domain':'siren','service':'turn_on' if value>=1 else 'turn_off','service_data':{}}",
                 "push_expr": "1 if entity.state=='on' else 0"},
                {"channel_type": 18,
                 "apply_expr": "{'domain':'siren','service':'turn_on','service_data':{'volume_level':round(value/100,2)}}",
                 "push_expr": "round(attrs.get('volume_level',1)*100,1)"},
            ],
        },
    },
    # ── Switch ───────────────────────────────────────────────────────────────
    {
        "domain": "switch", "device_class": None, "primary_group": 8,
        "output": {
            "function": 0, "default_group": 8, "output_usage": 0,
            "variable_ramp": False, "mode": 1, "groups": [8],
            "channels": [{"channel_type": 19,
                          "apply_expr": "{'domain':'switch','service':'turn_on' if value>=1 else 'turn_off','service_data':{}}",
                          "push_expr": "1 if entity.state=='on' else 0"}],
        },
    },
    {
        "domain": "switch", "device_class": "outlet", "primary_group": 8,
        "output": {
            "function": 0, "default_group": 8, "output_usage": 0,
            "variable_ramp": False, "mode": 1, "groups": [8],
            "channels": [{"channel_type": 19,
                          "apply_expr": "{'domain':'switch','service':'turn_on' if value>=1 else 'turn_off','service_data':{}}",
                          "push_expr": "1 if entity.state=='on' else 0"}],
        },
    },
    {
        "domain": "switch", "device_class": "switch", "primary_group": 8,
        "output": {
            "function": 0, "default_group": 8, "output_usage": 0,
            "variable_ramp": False, "mode": 1, "groups": [8],
            "channels": [{"channel_type": 19,
                          "apply_expr": "{'domain':'switch','service':'turn_on' if value>=1 else 'turn_off','service_data':{}}",
                          "push_expr": "1 if entity.state=='on' else 0"}],
        },
    },
    # ── Valve ────────────────────────────────────────────────────────────────
    {
        "domain": "valve", "device_class": None, "primary_group": 3,
        "output": {
            "function": 0, "default_group": 3, "output_usage": 0,
            "variable_ramp": False, "mode": 1, "groups": [3],
            "channels": [{"channel_type": 19,
                          "apply_expr": "{'domain':'valve','service':'open_valve' if value>=1 else 'close_valve','service_data':{}}",
                          "push_expr": "1 if entity.state=='open' else 0"}],
        },
    },
    {
        "domain": "valve", "device_class": "gas", "primary_group": 3,
        "output": {
            "function": 0, "default_group": 3, "output_usage": 0,
            "variable_ramp": False, "mode": 1, "groups": [3],
            "channels": [{"channel_type": 19,
                          "apply_expr": "{'domain':'valve','service':'open_valve' if value>=1 else 'close_valve','service_data':{}}",
                          "push_expr": "1 if entity.state=='open' else 0"}],
        },
    },
    {
        "domain": "valve", "device_class": "water", "primary_group": 3,
        "output": {
            "function": 2, "default_group": 3, "output_usage": 0,
            "variable_ramp": True, "mode": 2, "groups": [3],
            "channels": [{"channel_type": 23,
                          "apply_expr": "{'domain':'valve','service':'set_valve_position','service_data':{'position':round(value)}}",
                          "push_expr": "attrs.get('current_position',0)"}],  # WATER_FLOW_RATE
        },
    },
    {
        "domain": "valve", "device_class": "water_heater", "primary_group": 3,
        "output": {
            "function": 2, "default_group": 3, "output_usage": 0,
            "variable_ramp": True, "mode": 2, "groups": [3],
            "channels": [{"channel_type": 23,
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
