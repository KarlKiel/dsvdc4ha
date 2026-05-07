"""Config flow for dsvdc4ha."""
from __future__ import annotations

import asyncio
import logging
import socket
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigSubentryFlow, SubentryFlowResult
from homeassistant.core import callback
from homeassistant.helpers import selector as selector_module

from .api import (
    BinaryInputGroup,
    BinaryInputType,
    BinaryInputUsage,
    ButtonFunction,
    ButtonGroup,
    ButtonMode,
    ButtonType,
    ColorClass,
    ColorGroup,
    FUNCTION_CHANNELS,
    OutputChannelType,
    OutputFunction,
    OutputMode,
    OutputUsage,
    SensorGroup,
    SensorType,
    SensorUsage,
)

from .const import (
    CONF_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

selector = selector_module

# ---------------------------------------------------------------------------
# Explicit label dicts — sourced from pydsvdcapi enums.py inline comments
# and docstrings (https://github.com/KarlKiel/pydsvdcapi)
# ---------------------------------------------------------------------------

# ColorGroup: primaryGroup of a vdSD (device colour / functional category)
_COLOR_GROUP_LABELS: dict[int, str] = {
    1: "Yellow — Lights / Dimmers",
    2: "Grey — Shades / Blinds",
    3: "Blue — Climate (Heating, Cooling, Ventilation)",
    4: "Cyan — Audio",
    5: "Magenta — Video",
    6: "Red — Security",
    7: "Green — Access Control",
    8: "Black — Joker / Configurable",
    9: "White — Single Device / Appliance",
}

# ButtonGroup: group a button input controls (values 1–11, 48)
_BUTTON_GROUP_LABELS: dict[int, str] = {
    1: "1 — Yellow / Light",
    2: "2 — Grey / Shadow",
    3: "3 — Blue / Heating",
    4: "4 — Cyan / Audio",
    5: "5 — Magenta / Video",
    6: "6 — Red / Security",
    7: "7 — Green / Access",
    8: "8 — Black / Joker",
    9: "9 — Blue / Cooling",
    10: "10 — Blue / Ventilation",
    11: "11 — Blue / Window",
    48: "48 — Room Temperature Control",
}

# BinaryInputGroup: group a binary input belongs to (values 1–8, Joker=8)
_BINARY_INPUT_GROUP_LABELS: dict[int, str] = {
    1: "1 — Yellow / Light",
    2: "2 — Grey / Shadow",
    3: "3 — Blue / Climate",
    4: "4 — Cyan / Audio",
    5: "5 — Magenta / Video",
    6: "6 — Red / Security",
    7: "7 — Green / Access",
    8: "8 — Black / Joker",
}

# SensorGroup: group a sensor reading belongs to (values 0–7, Joker=0)
_SENSOR_GROUP_LABELS: dict[int, str] = {
    0: "0 — No group / Joker",
    1: "1 — Yellow / Light",
    2: "2 — Grey / Shadow",
    3: "3 — Blue / Climate",
    4: "4 — Cyan / Audio",
    5: "5 — Magenta / Video",
    6: "6 — Red / Security",
    7: "7 — Green / Access",
}

# ColorClass: dS Application Group ID for output defaultGroup / groups (values 1–12, 48)
_COLOR_CLASS_LABELS: dict[int, str] = {
    1: "1 — Lights (Yellow)",
    2: "2 — Blinds / Shades (Grey)",
    3: "3 — Heating (Blue)",
    4: "4 — Audio (Cyan)",
    5: "5 — Video (Magenta)",
    6: "6 — Security (Red)",
    7: "7 — Access (Green)",
    8: "8 — Joker / Configurable (Black)",
    9: "9 — Cooling (Blue)",
    10: "10 — Ventilation (Blue)",
    11: "11 — Window (Blue)",
    12: "12 — Recirculation / Fan-coil (Blue)",
    48: "48 — Temperature Control (Blue)",
}

_BUTTON_TYPE_LABELS: dict[int, str] = {
    0: "Undefined (unlimited elements)",
    1: "Single pushbutton (1 element)",
    2: "Two-way pushbutton (2 elements)",
    3: "Four-way navigation (4 elements)",
    4: "Four-way with center (5 elements)",
    5: "Eight-way with center (9 elements)",
    6: "On/Off switch (1 element)",
}

_BUTTON_FUNCTION_LABELS: dict[int, str] = {
    0: "Device",
    1: "Area 1",
    2: "Area 2",
    3: "Area 3",
    4: "Area 4",
    5: "Room",
    6: "Extended 1",
    7: "Extended 2",
    8: "Extended 3",
    9: "Extended 4",
    10: "Extended Area 1",
    11: "Extended Area 2",
    12: "Extended Area 3",
    13: "Extended Area 4",
    14: "Apartment",
    15: "App",
}

_BUTTON_MODE_LABELS: dict[int, str] = {
    0: "Standard (1-way pushbutton)",
    1: "Turbo (1-way)",
    2: "Switched / Toggle",
    5: "2-way Down, pair 1",
    6: "2-way Down, pair 2",
    7: "2-way Down, pair 3",
    8: "2-way Down, pair 4",
    9: "2-way Up, pair 1",
    10: "2-way Up, pair 2",
    11: "2-way Up, pair 3",
    12: "2-way Up, pair 4",
    13: "2-way",
    14: "1-way (explicit)",
    16: "AKM Standard (contact module)",
    17: "AKM Inverted (contact module)",
    18: "AKM On (rising edge)",
    19: "AKM On (falling edge)",
    20: "AKM Off (rising edge)",
    21: "AKM Off (falling edge)",
    22: "AKM Rising Edge",
    23: "AKM Falling Edge",
    65: "Heating Pushbutton (1-way)",
    255: "Deactivated",
}

_BINARY_INPUT_TYPE_LABELS: dict[int, str] = {
    0: "Generic",
    1: "Presence",
    2: "Brightness",
    3: "Presence in Darkness",
    4: "Twilight",
    5: "Motion",
    6: "Motion in Darkness",
    7: "Smoke",
    8: "Wind",
    9: "Rain",
    10: "Sun Radiation",
    11: "Thermostat",
    12: "Battery Low",
    13: "Window Open",
    14: "Door Open",
    15: "Window Tilted",
    16: "Garage Door Open",
    17: "Sun Protection",
    18: "Frost",
    19: "Heating System Enabled",
    20: "Heating Changeover",
    21: "Initialization",
    22: "Malfunction",
    23: "Service",
}

_BINARY_INPUT_USAGE_LABELS: dict[int, str] = {
    0: "Generic",
    1: "Room Climate",
    2: "Outdoor Climate",
    3: "Climate Setting",
}

_SENSOR_TYPE_LABELS: dict[int, str] = {
    0: "None",
    1: "Temperature",
    2: "Humidity",
    3: "Illumination",
    4: "Supply Voltage",
    5: "CO Concentration",
    6: "Radon Activity",
    7: "Gas Type",
    8: "Particles PM10",
    9: "Particles PM2.5",
    10: "Particles PM1",
    11: "Room Operating Panel",
    12: "Fan Speed",
    13: "Wind Speed",
    14: "Active Power",
    15: "Electric Current",
    16: "Energy Meter",
    17: "Apparent Power",
    18: "Air Pressure",
    19: "Wind Direction",
    20: "Sound Pressure Level",
    21: "Precipitation",
    22: "CO₂ Concentration",
    23: "Wind Gust Speed",
    24: "Wind Gust Direction",
    25: "Generated Active Power",
    26: "Generated Energy",
    27: "Water Quantity",
    28: "Water Flow Rate",
    29: "Length",
    30: "Mass",
    31: "Duration",
    32: "Percent",
    33: "Percent Speed",
    34: "Frequency",
}

_SENSOR_USAGE_LABELS: dict[int, str] = {
    1: "Room",
    2: "Outdoor",
    3: "User Interaction",
    4: "Device Level",
    5: "Device Last Run",
    6: "Device Average",
}

_OUTPUT_FUNCTION_LABELS: dict[int, str] = {
    0: "On / Off",
    1: "Dimmer",
    2: "Positional (shade, valve)",
    3: "Dimmer with Color Temperature",
    4: "Full Color Dimmer (RGB / HSV)",
    5: "Bipolar",
    6: "Internally Controlled",
    127: "Custom (no standard channels)",
}

# OutputMode: configurator UI hint (auto-derived by pydsvdcapi from function)
_OUTPUT_MODE_LABELS: dict[int, str] = {
    0: "Disabled",
    1: "Binary (on/off only)",
    2: "Gradual (continuous range)",
    127: "unspecified 'active'",
}

_OUTPUT_USAGE_LABELS: dict[int, str] = {
    0: "Undefined",
    1: "Room",
    2: "Outdoors",
    3: "User",
}

_CHANNEL_TYPE_LABELS: dict[int, str] = {
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
    20: "Air Louver (Auto)",
    21: "Air Flow (Auto)",
    22: "Water Temperature",
    23: "Water Flow Rate",
    24: "Power Level",
    25: "Video Station",
    26: "Video Input Source",
}

# ---------------------------------------------------------------------------
# SelectOptionDict lists built from label dicts
# ---------------------------------------------------------------------------

_COLOR_GROUP_OPTIONS = [
    selector.SelectOptionDict(value=str(g.value), label=_COLOR_GROUP_LABELS[g.value])
    for g in ColorGroup
]

# Per-input-type group selectors (different enums per the pydsvdcapi spec)
_BUTTON_GROUP_OPTIONS = [
    selector.SelectOptionDict(value=str(g.value), label=_BUTTON_GROUP_LABELS[g.value])
    for g in ButtonGroup
]

_BINARY_INPUT_GROUP_OPTIONS = [
    selector.SelectOptionDict(value=str(g.value), label=_BINARY_INPUT_GROUP_LABELS[g.value])
    for g in BinaryInputGroup
]

_SENSOR_GROUP_OPTIONS = [
    selector.SelectOptionDict(value=str(g.value), label=_SENSOR_GROUP_LABELS[g.value])
    for g in SensorGroup
]

# ColorClass options for output defaultGroup / groups (valid range 1–63)
_COLOR_CLASS_OPTIONS = [
    selector.SelectOptionDict(value=str(c.value), label=_COLOR_CLASS_LABELS[c.value])
    for c in ColorClass
    if c.value in _COLOR_CLASS_LABELS
]

_BUTTON_TYPE_OPTIONS = [
    selector.SelectOptionDict(value=str(t.value), label=_BUTTON_TYPE_LABELS[t.value])
    for t in ButtonType
]

_BUTTON_FUNCTION_OPTIONS = [
    selector.SelectOptionDict(value=str(f.value), label=_BUTTON_FUNCTION_LABELS[f.value])
    for f in ButtonFunction
]

_BUTTON_MODE_OPTIONS = [
    selector.SelectOptionDict(value=str(m.value), label=_BUTTON_MODE_LABELS[m.value])
    for m in ButtonMode
]

_BINARY_INPUT_TYPE_OPTIONS = [
    selector.SelectOptionDict(value=str(t.value), label=_BINARY_INPUT_TYPE_LABELS[t.value])
    for t in BinaryInputType
]

_BINARY_INPUT_USAGE_OPTIONS = [
    selector.SelectOptionDict(value=str(u.value), label=_BINARY_INPUT_USAGE_LABELS[u.value])
    for u in BinaryInputUsage
]

_INPUT_TYPE_OPTIONS = [
    selector.SelectOptionDict(value="0", label="Manual (no automatic detection)"),
    selector.SelectOptionDict(value="1", label="Detects changes (push at change)"),
    selector.SelectOptionDict(value="2", label="Polled (regular polling by DSS)"),
]

_SENSOR_TYPE_OPTIONS = [
    selector.SelectOptionDict(value=str(t.value), label=_SENSOR_TYPE_LABELS[t.value])
    for t in SensorType
]

_SENSOR_USAGE_OPTIONS = [
    selector.SelectOptionDict(value=str(u.value), label=_SENSOR_USAGE_LABELS[u.value])
    for u in SensorUsage
]

_OUTPUT_FUNCTION_OPTIONS = [
    selector.SelectOptionDict(value=str(f.value), label=_OUTPUT_FUNCTION_LABELS[f.value])
    for f in OutputFunction
]

_OUTPUT_MODE_OPTIONS = [
    selector.SelectOptionDict(value=str(m.value), label=_OUTPUT_MODE_LABELS[m.value])
    for m in OutputMode
]

_OUTPUT_USAGE_OPTIONS = [
    selector.SelectOptionDict(value=str(u.value), label=_OUTPUT_USAGE_LABELS[u.value])
    for u in OutputUsage
]

_CHANNEL_TYPE_OPTIONS = [
    selector.SelectOptionDict(value=str(c.value), label=_CHANNEL_TYPE_LABELS[c.value])
    for c in OutputChannelType
]

# OutputFunction values that require manual channel configuration
_MANUAL_CHANNEL_FUNCTIONS: set[int] = {
    f.value for f in OutputFunction if f.name in ("POSITIONAL", "BIPOLAR", "INTERNALLY_CONTROLLED", "CUSTOM")
}

# Number of button elements per ButtonType value
_BUTTON_ELEMENTS_BY_TYPE: dict[int, int] = {0: 1, 1: 1, 2: 2, 3: 4, 4: 5, 5: 9, 6: 1}

# ---------------------------------------------------------------------------
# Model features — labels, options, and auto-derive helper
# ---------------------------------------------------------------------------

# Human-readable labels for all auto-derivable model features.
# Sourced from pydsvdcapi docs/model-features-auto-assignment.md
_AUTO_FEATURE_LABELS: dict[str, str] = {
    "dontcare":                     "Per-scene 'retain current value' checkbox",
    "blink":                        "Per-scene blink effect checkbox",
    "transt":                       "Per-scene transition time (standard / slow)",
    "outvalue8":                    "8-bit output value slider",
    "outputchannels":               "Multi-channel colour output controls",
    "dimtimeconfig":                "Dim-time settings (up / down)",
    "outconfigswitch":              "Switch output threshold configuration",
    "impulseconfig":                "Impulse mode tab in device properties",
    "pwmvalue":                     "PWM-mode indicator in output values",
    "ventconfig":                   "Ventilation speed / flap configuration",
    "shadeprops":                   "Shade device properties (positional timing)",
    "shadeposition":                "16-bit position slider and up/down buttons",
    "shadebladeang":                "Blade angle input / slider",
    "motiontimefins":               "Blade motion timing in shade properties",
    "locationconfig":               "Direction / orientation dropdown",
    "operationlock":                "Ignore operation lock for weather alarms",
    "windprotectionconfigblind":    "Wind protection class — jalousie / blind",
    "windprotectionconfigawning":   "Wind protection class — awning / roller blind",
    "heatingprops":                 "Climate device properties (valve / PWM settings)",
    "heatinggroup":                 "Heating group dropdown",
    "valvetype":                    "Attached terminal device dropdown",
    "extendedvalvetypes":           "Extended valve type options",
    "fcu":                          "Fan coil unit profile",
    "temperatureoffset":            "Temperature offset adjustment",
    "consumption":                  "Energy monitoring / consumption events menu",
    "akmsensor":                    "AKM sensor function dropdown",
    "akminput":                     "AKM input behaviour dropdown",
    "akmdelay":                     "AKM turn-on / turn-off delay dropdowns",
    "pushbutton":                   "Push button type dropdown",
    "pushbadvanced":                "Per-preset click-type config and local priority",
    "pushbdisabled":                "Dialog for disabling unused buttons",
    "pushbarea":                    "Area push-button type option",
    "pushbdevice":                  "Device push-button type option",
    "pushbsensor":                  "Sensor-style button type option",
    "highlevel":                    "App button type option",
    "jokerconfig":                  "Colour group dropdown for Joker device",
    "identification":               "Identify menu entry (sends Notify to VDC)",
}

# Human-readable labels for 'not tested' optional features.
_OPTIONAL_FEATURE_LABELS: dict[str, str] = {
    "blinkconfig":                          "Blink behaviour configuration menu (not tested)",
    "customtransitiontime":                 "Per-scene custom transition time (not tested)",
    "consumptiontimer":                     "Consumption timer / run-time panel (not tested)",
    "outmodegeneric":                       "Output mode selector — generic values 0–6 (not tested)",
    "outmodeauto":                          "Output mode: add Auto option (not tested)",
    "jokertempcontrol":                     "Temperature-controlled output for Joker device (not tested)",
    "umvrelay":                             "Relay function dropdown (not tested)",
    "ftwtempcontrolventilationselect":      "FTW combined temperature + ventilation selector (not tested)",
    "setumr200config":                      "UMR200 hardware configuration (not tested)",
    "apartmentapplication":                 "Apartment application integration (not tested)",
    "customactivityconfig":                 "Custom activity / app configuration (not tested)",
}

_TRANST_CHANNEL_TYPES: frozenset[int] = frozenset(set(range(1, 13)) | set(range(14, 19)) | set(range(22, 25)))
_VENTILATION_CHANNEL_TYPES: frozenset[int] = frozenset({12, 13, 14, 15, 20, 21})


def _compute_auto_features(
    primary_group: int,
    buttons: list[dict],
    binary_inputs: list[dict],
    sensors: list[dict],
    output: dict | None,
    has_identify: bool,
) -> set[str]:
    """Mirror pydsvdcapi Vdsd.derive_model_features() without building a real Vdsd."""
    features: set[str] = set()
    ch_types: set[int] = set()

    if output is not None:
        features.add("dontcare")
        features.add("blink")
        fn = int(output.get("function", 0))
        ch_types = {int(ch["channelType"]) for ch in output.get("channels", [])}
        has_blade = bool(ch_types & {9, 10})

        if ch_types & _TRANST_CHANNEL_TYPES:
            features.add("transt")

        if primary_group == 2:  # GREY
            features.add("shadeprops")
            if fn == 2:  # POSITIONAL
                features.add("shadeposition")
                if has_blade:
                    features.add("shadebladeang")
                    features.add("motiontimefins")
        else:
            features.add("outvalue8")

        if {2, 3} <= ch_types or {1, 4} <= ch_types:
            features.add("outputchannels")

        if fn in {1, 3, 4}:  # DIMMER / DIMMER_COLOR_TEMP / FULL_COLOR_DIMMER
            features.add("dimtimeconfig")

        if fn == 0:  # ON_OFF
            features.add("outconfigswitch")
            features.add("impulseconfig")

        if primary_group == 3 and fn == 0:  # BLUE + ON_OFF
            features.add("pwmvalue")

        if 16 in ch_types:  # HEATING_POWER
            features.add("pwmvalue")

        if ch_types & _VENTILATION_CHANNEL_TYPES:
            features.add("ventconfig")

    sensor_types = {int(s["sensorType"]) for s in sensors}
    if sensor_types & {14, 15, 16, 17}:
        features.add("consumption")
    if 1 in sensor_types and primary_group == 3:
        features.add("temperatureoffset")

    if binary_inputs:
        features.add("akmsensor")
        features.add("akminput")
        features.add("akmdelay")

    if buttons:
        features.add("pushbutton")
        features.add("pushbadvanced")
        features.add("pushbdisabled")
        for btn in buttons:
            grp = int(btn.get("group", 1))
            if grp != 8:
                features.add("pushbarea")
                if btn.get("supportsLocalKeyMode", False):
                    features.add("pushbdevice")
            else:
                features.add("pushbsensor")
                features.add("highlevel")

    if primary_group == 3:  # BLUE
        features.add("heatingprops")
        features.add("heatinggroup")
        if output is not None:
            features.add("valvetype")
            features.add("extendedvalvetypes")
            if ch_types & _VENTILATION_CHANNEL_TYPES:
                features.add("fcu")

    if primary_group == 2 and output is not None:  # GREY
        features.add("locationconfig")
        features.add("operationlock")
        if ch_types & {9, 10}:
            features.add("windprotectionconfigblind")
        else:
            features.add("windprotectionconfigawning")

    if primary_group == 8:  # BLACK
        features.add("jokerconfig")

    if has_identify:
        features.add("identification")

    return features


def _port_is_available(port: int) -> bool:
    """Return True if the TCP port can be bound on the local machine."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("", port))
            return True
        except OSError:
            return False


def _existing_state_files(state_path: str) -> list[Path]:
    """Return a list of existing, parseable state files (primary + backup)."""
    import yaml  # noqa: PLC0415
    found = []
    for p in (Path(state_path), Path(state_path + ".bak")):
        if not p.exists():
            continue
        try:
            yaml.safe_load(p.read_text(errors="replace"))
            found.append(p)
        except (yaml.YAMLError, OSError):
            pass
    return found


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

HUB_SCHEMA = vol.Schema({
    vol.Required(CONF_PORT, default=8444): vol.All(vol.Coerce(int), vol.Range(min=1024, max=65535)),
})

DEVICE_INFO_SCHEMA = vol.Schema({
    vol.Required("name"): selector.TextSelector(),
    vol.Required("vendorName"): selector.TextSelector(),
    vol.Required("displayId"): selector.TextSelector(),
})


# ---------------------------------------------------------------------------
# Hub config flow
# ---------------------------------------------------------------------------

class DsvdcConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for the dSVDC hub."""

    VERSION = 1

    def __init__(self) -> None:
        self._pending_port: int = 0
        self._temp_coordinator: Any = None
        self._dss_connected: bool | None = None
        self._dss_wait_task: asyncio.Task | None = None

    async def async_step_user(self, user_input: dict | None = None):
        return await self.async_step_hub(user_input)

    async def async_step_hub(self, user_input: dict | None = None):
        """Collect the port number and verify it is available before proceeding."""
        errors: dict[str, str] = {}
        if user_input is not None:
            port = int(user_input[CONF_PORT])
            available = await asyncio.get_event_loop().run_in_executor(
                None, _port_is_available, port
            )
            if not available:
                errors[CONF_PORT] = "port_in_use"
            else:
                self._pending_port = port
                return await self.async_step_state_files()
        return self.async_show_form(step_id="hub", data_schema=HUB_SCHEMA, errors=errors)

    async def async_step_state_files(self, user_input: dict | None = None):
        """Ask what to do with existing state files, if any exist."""
        state_path = self.hass.config.path("dsvdc4ha", "host_state")
        existing = await asyncio.get_event_loop().run_in_executor(
            None, _existing_state_files, state_path
        )

        if user_input is not None:
            if user_input.get("action") == "delete":
                for p in existing:
                    try:
                        p.unlink()
                        _LOGGER.info("Deleted state file %s at user request", p)
                    except OSError:
                        _LOGGER.warning("Could not delete state file %s", p)
            return await self.async_step_wait_for_dss()

        if not existing:
            return await self.async_step_wait_for_dss()

        file_list = "\n".join(f"- `{p.name}`" for p in existing)
        schema = vol.Schema({
            vol.Required("action", default="keep"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value="keep", label="Use existing state (restore saved device configuration)"),
                        selector.SelectOptionDict(value="delete", label="Delete and start fresh"),
                    ]
                )
            ),
        })
        return self.async_show_form(
            step_id="state_files",
            data_schema=schema,
            description_placeholders={"files": file_list},
        )

    async def async_step_wait_for_dss(self, _user_input: dict | None = None):
        """Start the VdcHost and wait up to 2 minutes for a DSS to connect."""
        if self._dss_wait_task is not None and self._dss_wait_task.done():
            return self.async_show_progress_done(next_step_id="finalize_hub")

        if self._temp_coordinator is None:
            from .coordinator import HubCoordinator
            connected = asyncio.Event()
            self._temp_coordinator = HubCoordinator(self.hass, port=self._pending_port)
            try:
                await self._temp_coordinator.async_start(on_session_ready=connected.set)
            except Exception:
                _LOGGER.exception("VdcHost failed to start during hub setup (port %d)", self._pending_port)
                try:
                    await self._temp_coordinator.async_stop()
                except Exception:
                    pass
                self._temp_coordinator = None
                return self.async_abort(reason="cannot_connect")
            self._dss_wait_task = self.hass.async_create_task(self._wait_for_dss(connected))

        return self.async_show_progress(
            step_id="wait_for_dss",
            progress_action="wait_for_dss",
            progress_task=self._dss_wait_task,
        )

    async def async_step_finalize_hub(self, _user_input: dict | None = None):
        """Complete hub setup after DSS connection attempt."""
        if self._dss_connected:
            self.hass.data.setdefault(DOMAIN, {})["_pending_coordinator"] = self._temp_coordinator
            self._temp_coordinator = None
            return self.async_create_entry(
                title="dSVDC Hub",
                data={CONF_PORT: self._pending_port},
            )
        if self._temp_coordinator is not None:
            await self._temp_coordinator.async_stop()
            self._temp_coordinator = None
        return self.async_abort(reason="no_dss_found")

    async def _wait_for_dss(self, connected: asyncio.Event) -> None:
        """Background task: wait up to 2 min for the DSS hello handshake to complete."""
        try:
            await asyncio.wait_for(connected.wait(), timeout=120)
            self._dss_connected = True
        except asyncio.TimeoutError:
            self._dss_connected = False
        except asyncio.CancelledError:
            if self._temp_coordinator is not None:
                try:
                    await self._temp_coordinator.async_stop()
                except Exception:
                    pass
                self._temp_coordinator = None
            raise

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: config_entries.ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return supported subentry types (device wizard)."""
        return {"device": VdsdSubentryFlowHandler}


# ---------------------------------------------------------------------------
# Device subentry flow
# ---------------------------------------------------------------------------

class VdsdSubentryFlowHandler(ConfigSubentryFlow):
    """Multi-step wizard for adding a virtualDC device as a config subentry."""

    def __init__(self) -> None:
        self._device_name: str = ""
        self._vendor_name: str = ""
        self._display_id: str = ""
        self._vdsds: list[dict[str, Any]] = []
        self._current_vdsd: dict[str, Any] = {}
        self._current_buttons: list[dict[str, Any]] = []
        self._current_binary_inputs: list[dict[str, Any]] = []
        self._current_sensors: list[dict[str, Any]] = []
        self._current_output: dict[str, Any] | None = None
        self._current_channels: list[dict[str, Any]] = []
        self._current_button_element_idx: int = 0
        self._current_button_elements_total: int = 1
        self._current_button_type: int = 1
        self._optional_return_step: str = ""

    async def async_step_user(self, user_input: dict | None = None):
        return await self.async_step_device_info(user_input)

    async def async_step_device_info(self, user_input: dict | None = None):
        """Collect basic device identity."""
        if user_input is not None:
            self._device_name = user_input["name"]
            self._vendor_name = user_input["vendorName"]
            self._display_id = user_input["displayId"]
            return await self.async_step_vdsd_creation()
        return self.async_show_form(step_id="device_info", data_schema=DEVICE_INFO_SCHEMA)

    async def async_step_vdsd_creation(self, user_input: dict | None = None):
        """Collect vDSD-specific settings."""
        if user_input is not None:
            display_id = user_input["displayId"]
            primary_group = int(user_input["primaryGroup"])
            model_version = user_input["modelVersion"]
            self._current_vdsd = {
                "displayId": display_id,
                "primaryGroup": primary_group,
                "model": display_id,
                "vendorName": self._vendor_name,
                "modelVersion": model_version,
                "modelUID": f"{self._vendor_name}{model_version}".replace(" ", ""),
                "name": self._device_name,
                "active": True,
                "identify_action": user_input.get("identify_action"),
                "firmwareUpdate_action": user_input.get("firmwareUpdate_action"),
                "optional": {},
            }
            self._current_buttons = []
            self._current_binary_inputs = []
            self._current_sensors = []
            self._current_output = None
            self._current_channels = []
            return await self.async_step_vdsd_overview()
        schema = vol.Schema({
            vol.Required("displayId"): selector.TextSelector(),
            vol.Required("primaryGroup", default="1"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=_COLOR_GROUP_OPTIONS)
            ),
            vol.Required("modelVersion"): selector.TextSelector(),
            vol.Optional("identify_action"): selector.ActionSelector(),
            vol.Optional("firmwareUpdate_action"): selector.ActionSelector(),
        })
        return self.async_show_form(step_id="vdsd_creation", data_schema=schema)

    async def async_step_vdsd_overview(self, user_input: dict | None = None):
        """Show overview of the current vdSD with action buttons."""
        if user_input is not None:
            action = user_input.get("action", "next")
            if action == "optional_settings":
                self._optional_return_step = "vdsd_overview"
                return await self.async_step_optional_settings()
            if action == "add_button":
                self._current_button_element_idx = 0
                return await self.async_step_button()
            if action == "add_binary_input":
                return await self.async_step_binary_input()
            if action == "add_sensor":
                return await self.async_step_sensor()
            if action == "add_output":
                return await self.async_step_output()
            if action == "next":
                return await self.async_step_model_features()

        buttons_summary = [b["name"] for b in self._current_buttons]
        bi_summary = [b["name"] for b in self._current_binary_inputs]
        si_summary = [s["name"] for s in self._current_sensors]
        has_output = self._current_output is not None

        action_options = [
            selector.SelectOptionDict(value="optional_settings", label="Optional Settings"),
            selector.SelectOptionDict(value="add_button", label="Add Button"),
            selector.SelectOptionDict(value="add_binary_input", label="Add Binary Input"),
            selector.SelectOptionDict(value="add_sensor", label="Add Sensor"),
        ]
        if not has_output:
            action_options.append(
                selector.SelectOptionDict(value="add_output", label="Add Output")
            )
        action_options.append(selector.SelectOptionDict(value="next", label="Next →"))

        schema = vol.Schema({
            vol.Required("action", default="next"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=action_options)
            ),
        })
        description_placeholders = {
            "vdsd_name": self._current_vdsd.get("displayId", ""),
            "buttons": ", ".join(buttons_summary) or "none",
            "binary_inputs": ", ".join(bi_summary) or "none",
            "sensors": ", ".join(si_summary) or "none",
            "output": self._current_output.get("name", "") if has_output else "none",
        }
        return self.async_show_form(
            step_id="vdsd_overview",
            data_schema=schema,
            description_placeholders=description_placeholders,
        )

    async def async_step_optional_settings(self, user_input: dict | None = None):
        """Collect optional device metadata."""
        if user_input is not None:
            self._current_vdsd["optional"].update(
                {k: v for k, v in user_input.items() if v}
            )
            return_step = self._optional_return_step or "vdsd_overview"
            self._optional_return_step = ""
            return await getattr(self, f"async_step_{return_step}")()
        schema = vol.Schema({
            vol.Optional("hardwareVersion"): selector.TextSelector(),
            vol.Optional("hardwareGuid"): selector.TextSelector(),
            vol.Optional("vendorGuid"): selector.TextSelector(),
            vol.Optional("oemGuid"): selector.TextSelector(),
        })
        return self.async_show_form(step_id="optional_settings", data_schema=schema)

    async def async_step_model_features(self, user_input: dict | None = None):
        """Select model features, then finalise and save the current vdSD."""
        if user_input is not None:
            self._current_vdsd["model_features"] = user_input.get("features", [])
            self._current_vdsd["buttons"] = self._current_buttons
            self._current_vdsd["binary_inputs"] = self._current_binary_inputs
            self._current_vdsd["sensors"] = self._current_sensors
            self._current_vdsd["output"] = self._current_output
            self._vdsds.append(dict(self._current_vdsd))
            return await self.async_step_device_summary()

        auto_features = _compute_auto_features(
            primary_group=int(self._current_vdsd.get("primaryGroup", 1)),
            buttons=self._current_buttons,
            binary_inputs=self._current_binary_inputs,
            sensors=self._current_sensors,
            output=self._current_output,
            has_identify=bool(self._current_vdsd.get("identify_action")),
        )

        options: list[selector.SelectOptionDict] = []
        for key, label in _AUTO_FEATURE_LABELS.items():
            options.append(selector.SelectOptionDict(value=key, label=label))
        for key, label in _OPTIONAL_FEATURE_LABELS.items():
            options.append(selector.SelectOptionDict(value=key, label=label))

        schema = vol.Schema({
            vol.Optional("features", default=sorted(auto_features)): selector.SelectSelector(
                selector.SelectSelectorConfig(options=options, multiple=True)
            ),
        })
        return self.async_show_form(step_id="model_features", data_schema=schema)

    async def async_step_button(self, user_input: dict | None = None):
        """Collect button element configuration."""
        if user_input is not None:
            btn_type = int(user_input["buttonType"])
            element_idx = self._current_button_element_idx
            total = _BUTTON_ELEMENTS_BY_TYPE.get(btn_type, 1)

            btn_data = {
                "dsIndex": len(self._current_buttons),
                "name": user_input["name"],
                "buttonType": btn_type,
                "buttonElementID": element_idx,
                "group": int(user_input.get("group", 1)),
                "function": int(user_input.get("function", 0)),
                "mode": int(user_input.get("mode", 0)),
                "channel": int(user_input.get("channel", 0)),
                "supportsLocalKeyMode": bool(user_input.get("supportsLocalKeyMode", False)),
                "setsLocalPriority": bool(user_input.get("setsLocalPriority", False)),
                "callsPresent": bool(user_input.get("callsPresent", True)),
                "buttonID": 0,
                "callbackType": user_input.get("callbackType", "clickTypes"),
                "callback_entity": user_input.get("callback_entity"),
            }
            self._current_buttons.append(btn_data)

            if element_idx + 1 < total:
                self._current_button_element_idx += 1
                self._current_button_type = btn_type
                return await self.async_step_button()

            self._current_button_element_idx = 0
            return await self.async_step_vdsd_overview()

        schema = vol.Schema({
            vol.Required("name"): selector.TextSelector(),
            vol.Required("buttonType", default="1"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=_BUTTON_TYPE_OPTIONS)
            ),
            vol.Required("group", default="1"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=_BUTTON_GROUP_OPTIONS)
            ),
            vol.Required("function", default="0"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=_BUTTON_FUNCTION_OPTIONS)
            ),
            vol.Required("mode", default="0"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=_BUTTON_MODE_OPTIONS)
            ),
            vol.Optional("channel", default=0): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=255, mode="box")
            ),
            vol.Optional("supportsLocalKeyMode", default=False): selector.BooleanSelector(),
            vol.Optional("setsLocalPriority", default=False): selector.BooleanSelector(),
            vol.Optional("callsPresent", default=True): selector.BooleanSelector(),
            vol.Required("callbackType", default="clickTypes"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=[
                    selector.SelectOptionDict(value="clickTypes", label="Click types"),
                    selector.SelectOptionDict(value="actionIds", label="Scene / action IDs"),
                ])
            ),
            vol.Optional("callback_entity"): selector.EntitySelector(),
        })
        return self.async_show_form(step_id="button", data_schema=schema)

    async def async_step_binary_input(self, user_input: dict | None = None):
        """Collect binary input configuration."""
        if user_input is not None:
            self._current_binary_inputs.append({
                "dsIndex": len(self._current_binary_inputs),
                "name": user_input["name"],
                "group": int(user_input.get("group", 8)),
                "sensorFunction": int(user_input["sensorFunction"]),
                "hardwiredFunction": int(user_input.get("hardwiredFunction", 0)),
                "updateInterval": float(user_input.get("updateInterval", 0)),
                "inputType": int(user_input.get("inputType", 1)),
                "inputUsage": int(user_input.get("inputUsage", 0)),
                "valueType": user_input.get("valueType", "boolean"),
                "callback_entity": user_input.get("callback_entity"),
            })
            return await self.async_step_vdsd_overview()
        schema = vol.Schema({
            vol.Required("name"): selector.TextSelector(),
            vol.Required("group", default="8"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=_BINARY_INPUT_GROUP_OPTIONS)
            ),
            vol.Required("sensorFunction", default="0"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=_BINARY_INPUT_TYPE_OPTIONS)
            ),
            vol.Required("hardwiredFunction", default="0"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=_BINARY_INPUT_TYPE_OPTIONS)
            ),
            vol.Optional("updateInterval", default=0): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, mode="box")
            ),
            vol.Required("inputType", default="1"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=_INPUT_TYPE_OPTIONS)
            ),
            vol.Required("inputUsage", default="0"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=_BINARY_INPUT_USAGE_OPTIONS)
            ),
            vol.Required("valueType", default="boolean"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=[
                    selector.SelectOptionDict(value="boolean", label="Boolean (true / false)"),
                    selector.SelectOptionDict(value="integer", label="Integer (extended value)"),
                ])
            ),
            vol.Optional("callback_entity"): selector.EntitySelector(),
        })
        return self.async_show_form(step_id="binary_input", data_schema=schema)

    async def async_step_sensor(self, user_input: dict | None = None):
        """Collect sensor configuration."""
        if user_input is not None:
            self._current_sensors.append({
                "dsIndex": len(self._current_sensors),
                "name": user_input["name"],
                "group": int(user_input.get("group", 0)),
                "sensorType": int(user_input["sensorType"]),
                "sensorUsage": int(user_input.get("sensorUsage", 1)),
                "min": float(user_input["min"]),
                "max": float(user_input["max"]),
                "resolution": float(user_input["resolution"]),
                "updateInterval": float(user_input.get("updateInterval", 0)),
                "aliveSignInterval": float(user_input.get("aliveSignInterval", 0)),
                "minPushInterval": float(user_input.get("minPushInterval", 2.0)),
                "changesOnlyInterval": float(user_input.get("changesOnlyInterval", 0)),
                "callback_entity": user_input.get("callback_entity"),
            })
            return await self.async_step_vdsd_overview()
        schema = vol.Schema({
            vol.Required("name"): selector.TextSelector(),
            vol.Required("group", default="0"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=_SENSOR_GROUP_OPTIONS)
            ),
            vol.Required("sensorType", default="1"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=_SENSOR_TYPE_OPTIONS)
            ),
            vol.Required("sensorUsage", default="1"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=_SENSOR_USAGE_OPTIONS)
            ),
            vol.Required("min", default=0): selector.NumberSelector(
                selector.NumberSelectorConfig(mode="box")
            ),
            vol.Required("max", default=100): selector.NumberSelector(
                selector.NumberSelectorConfig(mode="box")
            ),
            vol.Required("resolution", default=0.1): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, mode="box", step=0.01)
            ),
            vol.Optional("updateInterval", default=0): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, mode="box")
            ),
            vol.Optional("aliveSignInterval", default=0): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, mode="box")
            ),
            vol.Optional("minPushInterval", default=2.0): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, mode="box", step=0.1)
            ),
            vol.Optional("changesOnlyInterval", default=0): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, mode="box")
            ),
            vol.Optional("callback_entity"): selector.EntitySelector(),
        })
        return self.async_show_form(step_id="sensor", data_schema=schema)

    async def async_step_output(self, user_input: dict | None = None):
        """Collect output configuration."""
        if user_input is not None:
            fn = int(user_input["function"])
            self._current_output = {
                "name": user_input["name"],
                "groups": [int(g) for g in user_input["groups"]],
                "defaultGroup": int(user_input["defaultGroup"]),
                "activeGroup": int(user_input["defaultGroup"]),
                "function": fn,
                "outputUsage": int(user_input.get("outputUsage", 0)),
                "variableRamp": bool(user_input.get("variableRamp", False)),
                "mode": int(user_input.get("mode", 127)),
                "onThreshold": 50,
            }
            self._current_channels = []
            if fn in _MANUAL_CHANNEL_FUNCTIONS:
                return await self.async_step_channel()
            for i, ct in enumerate(FUNCTION_CHANNELS.get(OutputFunction(fn), [])):
                self._current_channels.append({
                    "dsIndex": i,
                    "channelType": int(ct),
                    "name": _CHANNEL_TYPE_LABELS.get(int(ct), f"Channel {i}"),
                    "min": 0.0,
                    "max": 100.0,
                    "resolution": 0.4,
                })
            return await self.async_step_channel_mapping()
        schema = vol.Schema({
            vol.Required("name"): selector.TextSelector(),
            vol.Required("groups", default=["1"]): selector.SelectSelector(
                selector.SelectSelectorConfig(options=_COLOR_CLASS_OPTIONS, multiple=True)
            ),
            vol.Required("defaultGroup", default="1"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=_COLOR_CLASS_OPTIONS)
            ),
            vol.Required("function", default="0"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=_OUTPUT_FUNCTION_OPTIONS)
            ),
            vol.Required("outputUsage", default="0"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=_OUTPUT_USAGE_OPTIONS)
            ),
            vol.Optional("variableRamp", default=False): selector.BooleanSelector(),
            vol.Required("mode", default="127"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=_OUTPUT_MODE_OPTIONS)
            ),
        })
        return self.async_show_form(step_id="output", data_schema=schema)

    async def async_step_output_optional(self, user_input: dict | None = None):
        """Collect optional output settings."""
        if user_input is not None:
            if self._current_output:
                for k, v in user_input.items():
                    if v is not None and v != "":
                        self._current_output[k] = v
            return await self.async_step_output()
        schema = vol.Schema({
            vol.Optional("onThreshold", default=50): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=100, mode="box")
            ),
            vol.Optional("minBrightness"): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=100, mode="box")
            ),
            vol.Optional("maxPower"): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, mode="box")
            ),
            vol.Optional("activeCoolingMode", default=False): selector.BooleanSelector(),
        })
        return self.async_show_form(step_id="output_optional", data_schema=schema)

    async def async_step_channel(self, user_input: dict | None = None):
        """Collect channel configuration for manual-channel output functions."""
        if user_input is not None:
            self._current_channels.append({
                "dsIndex": len(self._current_channels),
                "channelType": int(user_input["channelType"]),
                "name": user_input.get("name", ""),
                "min": float(user_input.get("min", 0)),
                "max": float(user_input.get("max", 100)),
                "resolution": float(user_input.get("resolution", 0.4)),
            })
            action = user_input.get("action", "next")
            if action == "add_another":
                return await self.async_step_channel()
            return await self.async_step_channel_mapping()
        schema = vol.Schema({
            vol.Required("channelType", default="1"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=_CHANNEL_TYPE_OPTIONS)
            ),
            vol.Required("name"): selector.TextSelector(),
            vol.Required("min", default=0): selector.NumberSelector(
                selector.NumberSelectorConfig(mode="box")
            ),
            vol.Required("max", default=100): selector.NumberSelector(
                selector.NumberSelectorConfig(mode="box")
            ),
            vol.Required("resolution", default=0.4): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, step=0.01, mode="box")
            ),
            vol.Required("action", default="next"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=[
                    selector.SelectOptionDict(value="next", label="Done — go to channel mapping"),
                    selector.SelectOptionDict(value="add_another", label="Add another channel"),
                ])
            ),
        })
        return self.async_show_form(step_id="channel", data_schema=schema)

    async def async_step_channel_mapping(self, user_input: dict | None = None):
        """Map HA entities to output channels (read binding + write action)."""
        if user_input is not None:
            if self._current_output and self._current_channels:
                for ch in self._current_channels:
                    ch["read_entity"] = user_input.get(f"read_{ch['dsIndex']}")
                    ch["write_action"] = user_input.get(f"write_{ch['dsIndex']}")
                self._current_output["channels"] = self._current_channels
            elif self._current_output:
                self._current_output["channels"] = []
            return await self.async_step_vdsd_overview()

        schema_dict: dict = {}
        for ch in self._current_channels:
            schema_dict[vol.Optional(f"read_{ch['dsIndex']}")] = selector.EntitySelector()
            schema_dict[vol.Optional(f"write_{ch['dsIndex']}")] = selector.ActionSelector()
        if not schema_dict:
            if self._current_output:
                self._current_output["channels"] = []
            return await self.async_step_vdsd_overview()
        return self.async_show_form(
            step_id="channel_mapping", data_schema=vol.Schema(schema_dict)
        )

    async def async_step_device_summary(self, user_input: dict | None = None):
        """Show device summary; allow adding another vdSD or creating the subentry."""
        if user_input is not None and user_input.get("confirm"):
            action = user_input.get("action", "create")
            if action == "add_vdsd":
                return await self.async_step_vdsd_creation()
            return self.async_create_entry(
                title=self._device_name,
                data={
                    "name": self._device_name,
                    "vendorName": self._vendor_name,
                    "displayId": self._display_id,
                    "vdsds": self._vdsds,
                },
            )
        vdsd_summary = [
            f"{v['displayId']} (group {v['primaryGroup']})" for v in self._vdsds
        ]
        schema = vol.Schema({
            vol.Required("action", default="create"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=[
                    selector.SelectOptionDict(value="create", label="Create device"),
                    selector.SelectOptionDict(value="add_vdsd", label="Add another vdSD first"),
                ])
            ),
            vol.Required("confirm", default=False): selector.BooleanSelector(),
        })
        return self.async_show_form(
            step_id="device_summary",
            data_schema=schema,
            description_placeholders={
                "device_name": self._device_name,
                "vdsds": ", ".join(vdsd_summary),
            },
        )
