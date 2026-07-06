"""Config flow for dsvdc4ha."""
from __future__ import annotations

import asyncio
import base64
import logging
import re
import socket
from pathlib import Path
from typing import Any

try:
    import cairosvg as _cairosvg
except (ImportError, OSError):
    _cairosvg = None

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigSubentryFlow
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector as selector_module
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    derive_model_features_for_config,
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
    HeatingSystemCapability,
    HeatingSystemType,
    OutputChannelType,
    OutputFunction,
    OutputMode,
    OutputUsage,
    SensorGroup,
    SensorType,
    SensorUsage,
)

from .const import (
    CONF_ENTRY_TYPE,
    CONF_PORT,
    DOMAIN,
    ENTRY_TYPE_HUB,
)
from ._icon_utils import MDI_DOMAIN_ICONS, bundled_icon_b64
from .device_grouper import (
    EntityInfo as _EntityInfo,
    VdsdPlan,
    compute_vdsd_plan,
    resolve_vdsd_plan,
)
from .entity_mapping import (
    CHANNEL_TYPE_LABELS as _CHANNEL_TYPE_LABELS,
    SUPPORTED_DOMAINS,
    resolve_entity_mapping,
    needs_user_input,
)
from .binding_compiler import compile_apply_binding, compile_push_binding
from .binding_transforms import TRANSFORM_OPTIONS

_LOGGER = logging.getLogger(__name__)

selector = selector_module

import uuid as _uuid

_VDC_NS = _uuid.UUID("9888dd3d-b345-4109-b088-2673306d0c65")  # DsUidNamespace.VDC

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

# ButtonGroup: group a button input controls (values 1–12, 48)
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
    12: "12 — Blue / Recirculation",
    48: "48 — Room Temperature Control",
}

# BinaryInputGroup: group a binary input belongs to (values 1–8, 10, 12, Joker=8)
_BINARY_INPUT_GROUP_LABELS: dict[int, str] = {
    1: "1 — Yellow / Light",
    2: "2 — Grey / Shadow",
    3: "3 — Blue / Heating",
    4: "4 — Cyan / Audio",
    5: "5 — Magenta / Video",
    6: "6 — Red / Security",
    7: "7 — Green / Access",
    8: "8 — Black / Joker",
    10: "10 — Blue / Ventilation",
    12: "12 — Blue / Recirculation",
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
    if u.value in _SENSOR_USAGE_LABELS
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

_COVER_PLACEMENT_OPTIONS = [
    selector.SelectOptionDict(value="indoor", label="Indoor (room-facing)"),
    selector.SelectOptionDict(value="outdoor", label="Outdoor (weather-exposed)"),
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

_OPTIONAL_FEATURE_LABELS: dict[str, str] = {
    "blinkconfig":                      "Blink behaviour configuration menu (not tested)",
    "customtransitiontime":             "Per-scene custom transition time (not tested)",
    "consumptiontimer":                 "Consumption timer / run-time panel (not tested)",
    "outmodegeneric":                   "Output mode selector — generic values 0–6 (not tested)",
    "outmodeauto":                      "Output mode: add Auto option (not tested)",
    "jokertempcontrol":                 "Temperature-controlled output for Joker device (not tested)",
    "umvrelay":                         "Relay function dropdown (not tested)",
    "ftwtempcontrolventilationselect":  "FTW combined temperature + ventilation selector (not tested)",
    "setumr200config":                  "UMR200 hardware configuration (not tested)",
    "apartmentapplication":             "Apartment application integration (not tested)",
    "customactivityconfig":             "Custom activity / app configuration (not tested)",
}


def _select(options: list, *, multiple: bool = False) -> selector.SelectSelector:
    """Return a SelectSelector using LIST mode for ≤5 options, DROPDOWN for more."""
    mode = (
        selector.SelectSelectorMode.LIST
        if len(options) <= 5
        else selector.SelectSelectorMode.DROPDOWN
    )
    cfg = selector.SelectSelectorConfig(options=options, mode=mode, multiple=multiple)
    return selector.SelectSelector(cfg)


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
# Hub config flow — handles only hub setup
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
        """Route to hub setup; abort if a hub entry already exists."""
        existing = [
            e for e in self._async_current_entries()
            if e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_HUB
        ]
        if existing:
            return self.async_abort(reason="already_configured")
        return await self.async_step_hub(user_input)

    async def async_step_hub(self, user_input: dict | None = None):
        """Collect the port number and verify it is available before proceeding."""
        errors: dict[str, str] = {}
        if user_input is not None:
            port = int(user_input[CONF_PORT])
            available = await self.hass.async_add_executor_job(_port_is_available, port)
            if not available:
                errors[CONF_PORT] = "port_in_use"
            else:
                self._pending_port = port
                return await self.async_step_state_files()
        return self.async_show_form(step_id="hub", data_schema=HUB_SCHEMA, errors=errors)

    async def async_step_state_files(self, user_input: dict | None = None):
        """Ask what to do with existing state files, if any exist."""
        state_path = self.hass.config.path("dsvdc4ha", "host_state")
        existing = await self.hass.async_add_executor_job(_existing_state_files, state_path)

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
                data={CONF_ENTRY_TYPE: ENTRY_TYPE_HUB, CONF_PORT: self._pending_port},
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
# MDI icon resolution helpers
# ---------------------------------------------------------------------------

_MDI_SVG_CACHE: dict[str, bytes] = {}


def _mdi_icon_name_for(state: Any, entity_id: str) -> str | None:
    """Return the MDI icon slug for an entity state, or None if not resolvable."""
    icon: str | None = state.attributes.get("icon")
    if icon and icon.startswith("mdi:"):
        return icon[4:]
    domain = entity_id.split(".")[0]
    device_class: str | None = state.attributes.get("device_class")
    if device_class:
        result = MDI_DOMAIN_ICONS.get(f"{domain}.{device_class}")
        if result:
            return result
    return MDI_DOMAIN_ICONS.get(domain)


async def _fetch_mdi_icon_b64(hass: Any, icon_slug: str) -> str | None:
    """Fetch MDI SVG from CDN, render to 16x16 PNG, return base64 string or None."""
    import aiohttp

    if _cairosvg is None:
        return None

    if not isinstance(icon_slug, str) or not re.fullmatch(r'[a-z0-9\-]+', icon_slug):
        return None

    svg_bytes = _MDI_SVG_CACHE.get(icon_slug)
    if svg_bytes is None:
        try:
            url = f"https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/{icon_slug}.svg"
            session = async_get_clientsession(hass)
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return None
                svg_bytes = await resp.read()
            _MDI_SVG_CACHE[icon_slug] = svg_bytes
        except Exception:
            _LOGGER.debug("Failed to fetch MDI icon %s", icon_slug, exc_info=True)
            return None

    try:
        def _svg_to_png(svg: bytes) -> bytes:
            return _cairosvg.svg2png(bytestring=svg, output_width=16, output_height=16)

        png_bytes = await hass.async_add_executor_job(_svg_to_png, svg_bytes)
        return base64.b64encode(png_bytes).decode()
    except Exception:
        _LOGGER.debug("Failed to render MDI icon %s to PNG", icon_slug, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Device subentry flow — handles both "from entity" and "from scratch" paths
# ---------------------------------------------------------------------------

_OPTIONAL_RETURN_STEPS: frozenset[str] = frozenset({"vdsd_overview"})


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
        self._channel_mapping_idx: int = 0
        self._current_button_element_idx: int = 0
        self._current_button_elements_total: int = 1
        self._current_button_type: int = 1
        self._optional_return_step: str = ""
        # Entity-flow state
        self._entity_id: str = ""
        self._entity_mapping: dict[str, Any] | None = None
        # "from_ha_device" path state
        self._ha_device_id: str = ""
        self._device_entities: list[_EntityInfo] = []
        self._selected_entity_ids: list[str] | None = None
        self._vdsd_plans: list[VdsdPlan] = []
        self._unsupported_entities: list[_EntityInfo] = []
        self._pending_choice_entities: list[tuple[_EntityInfo, int]] = []
        self._pending_choice_idx: int = 0
        self._pending_vdsd_idx: int = 0
        self._pending_name_confirm_idx: int = 0
        self._creation_mode: str = "from_entity"

    async def _resolve_entity_icon(self, entity_id: str) -> tuple[str, str | None]:
        """Return (icon_name, base64_16x16_png_or_None) for an entity.

        icon_name is entity_id with dots replaced by underscores.
        Tries entity_picture first, then MDI icon attribute, then domain fallback.
        Returns None for b64 on any failure.
        """
        import base64
        import io

        icon_name = entity_id.replace(".", "_")
        state = self.hass.states.get(entity_id)
        if state is None:
            return icon_name, None

        # Path 1: entity_picture (camera snapshots, custom pictures)
        picture_url: str | None = state.attributes.get("entity_picture")
        if picture_url:
            try:
                from PIL import Image
                import aiohttp

                if not (picture_url.startswith("http") or picture_url.startswith("//")):
                    api_cfg = getattr(self.hass.config, "api", None)
                    base = str(api_cfg.base_url).rstrip("/") if api_cfg else "http://localhost:8123"
                    picture_url = f"{base}{picture_url}"

                session = async_get_clientsession(self.hass)
                async with session.get(
                    picture_url, timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        raw = await resp.read()

                        def _resize(data: bytes) -> bytes:
                            img = Image.open(io.BytesIO(data)).convert("RGBA").resize(
                                (16, 16), Image.LANCZOS
                            )
                            out = io.BytesIO()
                            img.save(out, format="PNG")
                            return out.getvalue()

                        resized = await self.hass.async_add_executor_job(_resize, raw)
                        return icon_name, base64.b64encode(resized).decode()
            except Exception:
                _LOGGER.debug("Failed to resolve icon for %s from entity_picture", entity_id, exc_info=True)

        # Path 2: MDI icon — CDN+cairosvg first, bundled PNG fallback
        mdi_name = _mdi_icon_name_for(state, entity_id)
        if mdi_name is None:
            return icon_name, None

        b64 = await _fetch_mdi_icon_b64(self.hass, mdi_name)
        if b64 is None:
            b64 = bundled_icon_b64(mdi_name)
        return icon_name, b64

    async def async_step_user(self, user_input: dict | None = None):
        return await self.async_step_creation_mode(user_input)

    # ── Creation mode ─────────────────────────────────────────────────────────

    async def async_step_creation_mode(self, user_input: dict | None = None):
        """Choose between creating a vdSD from an existing HA entity or from scratch."""
        if user_input is not None:
            mode = user_input.get("mode", "from_scratch")
            self._creation_mode = mode
            if mode == "from_entity":
                return await self.async_step_entity_picker()
            if mode == "from_ha_device":
                return await self.async_step_device_picker()
            return await self.async_step_device_info()
        schema = vol.Schema({
            vol.Required("mode", default="from_entity"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=[
                    selector.SelectOptionDict(value="from_entity",
                                              label="Create device based on HA entities (recommended)"),
                    selector.SelectOptionDict(value="from_ha_device",
                                              label="Create device based on HA device"),
                    selector.SelectOptionDict(value="from_scratch",
                                              label="Create device from scratch (BETA)"),
                ])
            ),
        })
        return self.async_show_form(step_id="creation_mode", data_schema=schema)

    # ── Entity-based creation path ─────────────────────────────────────────────

    async def async_step_entity_picker(self, user_input: dict | None = None):
        """Select the HA entity to derive a vdSD from."""
        errors: dict[str, str] = {}
        if user_input is not None:
            entity_id: str = user_input["entity_id"]
            state = self.hass.states.get(entity_id)
            if state is None:
                errors["entity_id"] = "entity_not_found"
            else:
                domain = entity_id.split(".")[0]
                device_class: str | None = state.attributes.get("device_class")
                mapping = resolve_entity_mapping(entity_id, state, domain, device_class)
                if mapping is None:
                    errors["entity_id"] = "entity_not_supported"
                else:
                    self._entity_id = entity_id
                    self._entity_mapping = mapping
                    # Auto-populate device fields from HA device / entity info
                    friendly_name: str = state.name or entity_id
                    manufacturer: str = ""
                    model: str = ""
                    try:
                        ent_reg = er.async_get(self.hass)
                        dev_reg = dr.async_get(self.hass)
                        entry = ent_reg.async_get(entity_id)
                        if entry and entry.device_id:
                            device = dev_reg.async_get(entry.device_id)
                            if device:
                                friendly_name = device.name_by_user or device.name or friendly_name
                                manufacturer = device.manufacturer or ""
                                model = device.model or ""
                    except Exception:
                        pass
                    if not self._vdsds:
                        self._device_name = friendly_name
                        self._vendor_name = manufacturer
                        self._display_id = model or domain.title()
                    if needs_user_input(mapping):
                        return await self.async_step_entity_user_input()
                    return await self._build_entity_vdsd_and_continue({})

        schema = vol.Schema({
            vol.Required("entity_id"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=SUPPORTED_DOMAINS)
            ),
        })
        return self.async_show_form(
            step_id="entity_picker",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_entity_user_input(self, user_input: dict | None = None):
        """Collect the extra choices required by this entity's mapping."""
        mapping = self._entity_mapping
        if mapping is None:
            return await self.async_step_creation_mode()

        if user_input is not None:
            return await self._build_entity_vdsd_and_continue(user_input)

        schema_dict: dict = {}
        bi = mapping.get("binary_input", {})
        sen = mapping.get("sensor", {})
        btn = mapping.get("button", {})
        out = mapping.get("output", {})

        sfc = bi.get("sensor_function_choices")
        if sfc == "any":
            schema_dict[vol.Required("sensor_function", default=str(bi["sensor_function"]))] = (
                selector.SelectSelector(selector.SelectSelectorConfig(options=_BINARY_INPUT_TYPE_OPTIONS))
            )
        elif sfc:
            schema_dict[vol.Required("sensor_function", default=str(bi["sensor_function"]))] = (
                _select([selector.SelectOptionDict(value=str(v), label=lbl) for v, lbl in sfc])
            )

        if btn.get("group_choices"):
            schema_dict[vol.Required("group", default=str(btn["group"]))] = (
                _select([selector.SelectOptionDict(value=str(v), label=lbl) for v, lbl in btn["group_choices"]])
            )

        if bi.get("group_choices"):
            schema_dict[vol.Required("bi_group", default=str(bi["group"]))] = (
                _select([selector.SelectOptionDict(value=str(v), label=lbl) for v, lbl in bi["group_choices"]])
            )

        if bi.get("input_usage_choices"):
            schema_dict[vol.Required("input_usage", default=str(bi["input_usage"]))] = (
                _select([selector.SelectOptionDict(value=str(v), label=lbl) for v, lbl in bi["input_usage_choices"]])
            )

        stc = sen.get("sensor_type_choices")
        if stc == "any":
            schema_dict[vol.Required("sensor_type", default=str(sen["sensor_type"]))] = (
                selector.SelectSelector(selector.SelectSelectorConfig(options=_SENSOR_TYPE_OPTIONS))
            )
        elif stc:
            schema_dict[vol.Required("sensor_type", default=str(sen["sensor_type"]))] = (
                selector.SelectSelector(selector.SelectSelectorConfig(options=[
                    selector.SelectOptionDict(value=str(v), label=lbl)
                    for v, lbl in stc
                ]))
            )

        if sen.get("min_max_user"):
            schema_dict[vol.Required("min", default=sen["min"])] = selector.NumberSelector(
                selector.NumberSelectorConfig(mode="box")
            )
            schema_dict[vol.Required("max", default=sen["max"])] = selector.NumberSelector(
                selector.NumberSelectorConfig(mode="box")
            )
            schema_dict[vol.Required("resolution", default=sen["resolution"])] = selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, step=0.01, mode="box")
            )

        suc = sen.get("sensor_usage_choices")
        if suc == "any":
            schema_dict[vol.Required("sensor_usage", default=str(sen["sensor_usage"]))] = (
                selector.SelectSelector(selector.SelectSelectorConfig(options=_SENSOR_USAGE_OPTIONS))
            )
        elif suc:
            schema_dict[vol.Required("sensor_usage", default=str(sen["sensor_usage"]))] = (
                _select([selector.SelectOptionDict(value=str(v), label=lbl) for v, lbl in suc])
            )

        if out.get("output_usage_choices"):
            schema_dict[vol.Required("output_usage", default=str(out["output_usage"]))] = (
                _select([selector.SelectOptionDict(value=str(v), label=lbl) for v, lbl in out["output_usage_choices"]])
            )

        if out.get("function_choices"):
            schema_dict[vol.Required("function", default=str(out["function"]))] = (
                _select([selector.SelectOptionDict(value=str(v), label=lbl) for v, lbl in out["function_choices"]])
            )

        if out.get("optional_tilt"):
            schema_dict[vol.Optional("has_tilt", default=False)] = selector.BooleanSelector()

        if out.get("placement_choice"):
            schema_dict[vol.Required("cover_placement", default="indoor")] = (
                selector.SelectSelector(selector.SelectSelectorConfig(options=_COVER_PLACEMENT_OPTIONS))
            )

        def _timing_field(key: str):
            v = out.get(key)
            return vol.Optional(key, default=v) if v is not None else vol.Optional(key)

        if out.get("shadow_position_timing"):
            _ns = selector.NumberSelectorConfig(min=0, step=0.1, mode="box", unit_of_measurement="s")
            schema_dict[_timing_field("openTime")]      = selector.NumberSelector(_ns)
            schema_dict[_timing_field("closeTime")]     = selector.NumberSelector(_ns)
            schema_dict[_timing_field("stopDelayTime")] = selector.NumberSelector(_ns)
        if out.get("shadow_angle_timing"):
            _ns = selector.NumberSelectorConfig(min=0, step=0.1, mode="box", unit_of_measurement="s")
            schema_dict[_timing_field("angleOpenTime")]  = selector.NumberSelector(_ns)
            schema_dict[_timing_field("angleCloseTime")] = selector.NumberSelector(_ns)

        return self.async_show_form(
            step_id="entity_user_input",
            data_schema=vol.Schema(schema_dict),
        )

    async def _build_entity_vdsd_and_continue(self, user_input: dict) -> Any:
        """Build the vdSD data dict from the mapping + user choices, then continue."""
        mapping = self._entity_mapping
        if mapping is None:
            return await self.async_step_creation_mode()
        entity_id = self._entity_id
        state = self.hass.states.get(entity_id)
        friendly_name: str = (state.name if state else None) or entity_id.split(".")[-1]

        pg = mapping["primary_group"]
        vdsd: dict[str, Any] = {
            "displayId": self._display_id,      # model/type name (e.g. "Occhio Lunanova")
            "primaryGroup": pg,
            "model": mapping["model"],
            "vendorName": mapping["vendor_name"],
            "modelVersion": "1.0",
            "modelUID": mapping["model_uid"],
            "name": friendly_name,
            "identify_action": None,
            "firmwareUpdate_action": None,
            "optional": {},
            "buttons": [],
            "binary_inputs": [],
            "sensors": [],
            "output": None,
        }

        # Compute deterministic hardwareGuid from entity unique_id
        ent_entry = er.async_get(self.hass).async_get(entity_id)
        _unique_id = str(ent_entry.unique_id) if ent_entry else entity_id
        vdsd["hardwareGuid"] = "uuid:" + str(_uuid.uuid5(_VDC_NS, _unique_id))

        # Binary input -------------------------------------------------------
        if "binary_input" in mapping:
            bi = mapping["binary_input"]
            sf = int(user_input.get("sensor_function", bi["sensor_function"]))
            vdsd["binary_inputs"] = [{
                "dsIndex": 0,
                "name": friendly_name,
                "group": int(user_input.get("bi_group", bi["group"])),
                "sensorFunction": sf,
                "hardwiredFunction": sf,
                "updateInterval": bi["update_interval"],
                "inputType": bi["input_type"],
                "inputUsage": int(user_input.get("input_usage", bi["input_usage"])),
                "valueType": "boolean",
                "callback_entity": entity_id,
            }]

        # Sensor -------------------------------------------------------------
        if "sensor" in mapping:
            s = mapping["sensor"]
            st = int(user_input.get("sensor_type", s["sensor_type"]))
            vdsd["sensors"] = [{
                "dsIndex": 0,
                "name": friendly_name,
                "group": s["group"],
                "sensorType": st,
                "sensorUsage": int(user_input.get("sensor_usage", s["sensor_usage"])),
                "min": float(user_input.get("min", s["min"])),
                "max": float(user_input.get("max", s["max"])),
                "resolution": float(user_input.get("resolution", s["resolution"])),
                "updateInterval": s["update_interval"],
                "aliveSignInterval": s["alive_sign_interval"],
                "minPushInterval": s["min_push_interval"],
                "changesOnlyInterval": s["changes_only_interval"],
                "callback_entity": entity_id,
            }]

        # Button -------------------------------------------------------------
        if "button" in mapping:
            b = mapping["button"]
            group = int(user_input.get("group", b["group"]))
            # Auto-derive function from group when user picked one
            if "group_choices" in b and "group" in user_input:
                function = 15 if group == 8 else 5  # APP for Joker, Room for others
            else:
                function = b["function"]
            vdsd["buttons"] = [{
                "dsIndex": 0,
                "name": friendly_name,
                "buttonType": b["button_type"],
                "buttonElementID": 0,
                "group": group,
                "function": function,
                "mode": b["mode"],
                "channel": 0,
                "supportsLocalKeyMode": b.get("supports_local_key_mode", False),
                "setsLocalPriority": False,
                "callsPresent": b.get("calls_present", False),
                "buttonID": 0,
                "callbackType": "detect_clicks",
                "callback_entity": entity_id,
            }]

        # Output -------------------------------------------------------------
        if "output" in mapping:
            o = mapping["output"]
            fn = int(user_input.get("function", o["function"]))
            usage = int(user_input.get("output_usage", o["output_usage"]))

            # Resolve channels: outdoor placement overrides the default indoor set
            placement = user_input.get("cover_placement", "indoor")
            if o.get("placement_choice") and placement == "outdoor":
                channels_def = list(o["channels_outdoor"])
            elif "channels_by_usage" in o:
                channels_def = o["channels_by_usage"].get(usage, o["channels"])
            else:
                channels_def = list(o["channels"])

            # Optional tilt channel — use outdoor angle channel when outdoor-facing
            if o.get("optional_tilt") and user_input.get("has_tilt"):
                tilt_ch = 9 if placement == "outdoor" else 10
                channels_def = channels_def + [{
                    "channel_type": tilt_ch,
                    "apply_expr": "{'domain':'cover','service':'set_cover_tilt_position','service_data':{'tilt_position':round(value)}}",
                    "push_expr": "attrs.get('current_tilt_position',0)",
                }]

            # Mode derived from function when function was a user choice
            if "function_choices" in o:
                mode = 1 if fn == 0 else 2  # BINARY for ON_OFF, GRADUAL for positional
            else:
                mode = o["mode"]

            channels = [
                {
                    "dsIndex": i,
                    "channelType": ch["channel_type"],
                    "read_entity": entity_id,
                    "write_action": None,
                    **({"apply_expr": ch["apply_expr"]} if ch.get("apply_expr") else {}),
                    **({"push_expr": ch["push_expr"]} if ch.get("push_expr") else {}),
                }
                for i, ch in enumerate(channels_def)
            ]
            vdsd["output"] = {
                "name": "Output",
                "groups": o["groups"],
                "defaultGroup": o["default_group"],
                "activeGroup": o["default_group"],
                "function": fn,
                "outputUsage": usage,
                "variableRamp": o["variable_ramp"],
                "mode": mode,
                "onThreshold": 50,
                "channels": channels,
                **({"apply_all_expr": o["apply_all_expr"]} if o.get("apply_all_expr") else {}),
                **{
                    k: float(user_input[k])
                    for k in ("openTime", "closeTime", "angleOpenTime", "angleCloseTime", "stopDelayTime")
                    if k in user_input and user_input[k] is not None
                },
            }

        # Resolve entity icon and store in vdSD dict
        icon_name, icon_b64 = await self._resolve_entity_icon(entity_id)
        vdsd["icon_name"] = icon_name
        if icon_b64:
            vdsd["icon_data_b64"] = icon_b64
        _state_for_slug = self.hass.states.get(entity_id)
        vdsd["icon_slug"] = _mdi_icon_name_for(_state_for_slug, entity_id) if _state_for_slug else None

        # Store result and forward to channel mapping or model_features
        self._current_vdsd = vdsd
        self._current_buttons = vdsd["buttons"]
        self._current_binary_inputs = vdsd["binary_inputs"]
        self._current_sensors = vdsd["sensors"]
        self._current_output = vdsd["output"]
        self._current_channels = vdsd["output"]["channels"] if vdsd["output"] else []

        if vdsd["output"] and self._current_channels:
            apply_all = vdsd["output"].get("apply_all_expr")
            all_auto = apply_all is not None or all(ch.get("apply_expr") for ch in self._current_channels)
            if not all_auto:
                return await self.async_step_entity_channel_mapping()
        return await self.async_step_model_features()

    async def async_step_entity_channel_mapping(self, user_input: dict | None = None):
        """Let the user bind HA entities / actions to each output channel."""
        if user_input is not None:
            for ch in self._current_channels:
                read = user_input.get(f"read_{ch['dsIndex']}")
                write = user_input.get(f"write_{ch['dsIndex']}")
                if read is not None:
                    ch["read_entity"] = read
                if write is not None:
                    ch["write_action"] = write
            if self._current_output:
                self._current_output["channels"] = self._current_channels
            return await self.async_step_model_features()

        schema_dict: dict = {}
        for ch in self._current_channels:
            idx = ch["dsIndex"]
            schema_dict[vol.Optional(f"read_{idx}", default=ch.get("read_entity"))] = (
                selector.EntitySelector()
            )
            schema_dict[vol.Optional(f"write_{idx}")] = selector.ActionSelector()

        return self.async_show_form(
            step_id="entity_channel_mapping",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "channels": ", ".join(
                    ch.get("name", f"Channel {ch['dsIndex']}") for ch in self._current_channels
                )
            },
        )

    # ── "From HA device" creation path ────────────────────────────────────────

    async def async_step_device_picker(self, user_input: dict | None = None):
        """Select a HA device; derive and group all its entities into VdsdPlans."""
        if user_input is not None:
            device_id: str = user_input["device_id"]
            dev_reg = dr.async_get(self.hass)
            ent_reg = er.async_get(self.hass)

            device = dev_reg.async_get(device_id)
            self._ha_device_id = device_id
            self._device_name = (
                (device.name_by_user or device.name) if device else device_id
            )
            self._vendor_name = (device.manufacturer or "") if device else ""
            self._display_id = (device.model or "") if device else ""

            entities: list[_EntityInfo] = []
            for entry in ent_reg.entities.get_entries_for_device_id(device_id):
                if entry.disabled_by is not None:
                    continue
                state = self.hass.states.get(entry.entity_id)
                domain = entry.entity_id.split(".")[0]
                device_class: str | None = (
                    state.attributes.get("device_class")
                    if state
                    else (entry.device_class or entry.original_device_class)
                )
                mapping = resolve_entity_mapping(entry.entity_id, state, domain, device_class)
                cat = entry.entity_category
                cat_str = cat.value if cat is not None else None
                entity_info = _EntityInfo(
                    entity_id=entry.entity_id,
                    friendly_name=(state.name or entry.entity_id) if state else entry.entity_id,
                    domain=domain,
                    device_class=device_class,
                    mapping=mapping,
                    needs_choices=needs_user_input(mapping) if mapping else False,
                    entity_category=cat_str,
                )
                entities.append(entity_info)

            self._device_entities = entities
            return await self.async_step_device_entity_select()

        schema = vol.Schema({
            vol.Required("device_id"): selector.DeviceSelector(),
        })
        return self.async_show_form(step_id="device_picker", data_schema=schema)

    async def async_step_device_entity_select(self, user_input: dict | None = None):
        """Let the user select which device entities to expose as vdSDs."""
        if user_input is not None:
            selected_ids: list[str] = user_input.get("entity_ids", [])
            self._selected_entity_ids = selected_ids
            filtered = [e for e in self._device_entities if e.entity_id in selected_ids]
            self._vdsd_plans, self._unsupported_entities = compute_vdsd_plan(
                filtered, self._device_name
            )
            self._pending_choice_entities = []
            for plan_idx, plan in enumerate(self._vdsd_plans):
                for candidate in [
                    plan.output_entity,
                    plan.binary_input_entity,
                    plan.button_entity,
                    *plan.sensor_entities,
                ]:
                    if candidate is not None and candidate.needs_choices:
                        self._pending_choice_entities.append((candidate, plan_idx))
            self._pending_choice_idx = 0
            self._pending_vdsd_idx = 0
            if self._pending_choice_entities:
                return await self.async_step_device_entity_user_input()
            return await self.async_step_device_plan_summary()

        # Build list of supported entity options
        options: list[selector.SelectOptionDict] = []
        for entity_info in self._device_entities:
            if entity_info.mapping is not None:
                options.append(
                    selector.SelectOptionDict(
                        value=entity_info.entity_id,
                        label=f"{entity_info.friendly_name} ({entity_info.domain})",
                    )
                )

        if not options:
            # No supported entities — skip and build empty plan
            self._vdsd_plans, self._unsupported_entities = compute_vdsd_plan(
                [], self._device_name
            )
            self._pending_choice_entities = []
            self._pending_choice_idx = 0
            self._pending_vdsd_idx = 0
            return await self.async_step_device_plan_summary()

        schema = vol.Schema({
            vol.Required("entity_ids", default=[o["value"] for o in options]): selector.SelectSelector(
                selector.SelectSelectorConfig(options=options, multiple=True)
            ),
        })
        return self.async_show_form(
            step_id="device_entity_select",
            data_schema=schema,
            description_placeholders={"device_name": self._device_name},
        )

    async def async_step_device_entity_user_input(self, user_input: dict | None = None):
        """Collect per-entity choices (one entity at a time) for the HA-device path."""
        entity_info, plan_idx = self._pending_choice_entities[self._pending_choice_idx]
        mapping = entity_info.mapping or {}

        if user_input is not None:
            self._vdsd_plans[plan_idx].user_choices[entity_info.entity_id] = dict(user_input)
            self._pending_choice_idx += 1
            if self._pending_choice_idx < len(self._pending_choice_entities):
                return await self.async_step_device_entity_user_input()
            return await self.async_step_device_plan_summary()

        # Build same schema as async_step_entity_user_input
        schema_dict: dict = {}
        bi = mapping.get("binary_input", {})
        sen = mapping.get("sensor", {})
        btn = mapping.get("button", {})
        out = mapping.get("output", {})

        sfc = bi.get("sensor_function_choices")
        if sfc == "any":
            schema_dict[vol.Required("sensor_function", default=str(bi["sensor_function"]))] = (
                selector.SelectSelector(selector.SelectSelectorConfig(options=_BINARY_INPUT_TYPE_OPTIONS))
            )
        elif sfc:
            schema_dict[vol.Required("sensor_function", default=str(bi["sensor_function"]))] = (
                _select([selector.SelectOptionDict(value=str(v), label=lbl) for v, lbl in sfc])
            )

        if btn.get("group_choices"):
            schema_dict[vol.Required("group", default=str(btn["group"]))] = (
                _select([selector.SelectOptionDict(value=str(v), label=lbl) for v, lbl in btn["group_choices"]])
            )
        if bi.get("group_choices"):
            schema_dict[vol.Required("bi_group", default=str(bi["group"]))] = (
                _select([selector.SelectOptionDict(value=str(v), label=lbl) for v, lbl in bi["group_choices"]])
            )
        if bi.get("input_usage_choices"):
            schema_dict[vol.Required("input_usage", default=str(bi["input_usage"]))] = (
                _select([selector.SelectOptionDict(value=str(v), label=lbl) for v, lbl in bi["input_usage_choices"]])
            )
        stc = sen.get("sensor_type_choices")
        if stc == "any":
            schema_dict[vol.Required("sensor_type", default=str(sen["sensor_type"]))] = (
                selector.SelectSelector(selector.SelectSelectorConfig(options=_SENSOR_TYPE_OPTIONS))
            )
        elif stc:
            schema_dict[vol.Required("sensor_type", default=str(sen["sensor_type"]))] = (
                selector.SelectSelector(selector.SelectSelectorConfig(options=[
                    selector.SelectOptionDict(value=str(v), label=lbl)
                    for v, lbl in stc
                ]))
            )
        state = self.hass.states.get(entity_info.entity_id)
        # Prefer live state attributes so repeat-visits pre-fill current values
        attrs = state.attributes if state else {}
        if sen.get("min_max_user"):
            schema_dict[vol.Required("min", default=attrs.get("min", sen.get("min", 0)))] = (
                selector.NumberSelector(selector.NumberSelectorConfig(mode="box"))
            )
            schema_dict[vol.Required("max", default=attrs.get("max", sen.get("max", 100)))] = (
                selector.NumberSelector(selector.NumberSelectorConfig(mode="box"))
            )
            schema_dict[vol.Required("resolution", default=attrs.get("step", sen.get("resolution", 0.4)))] = (
                selector.NumberSelector(selector.NumberSelectorConfig(min=0, step=0.01, mode="box"))
            )
        suc = sen.get("sensor_usage_choices")
        if suc == "any":
            schema_dict[vol.Required("sensor_usage", default=str(sen["sensor_usage"]))] = (
                selector.SelectSelector(selector.SelectSelectorConfig(options=_SENSOR_USAGE_OPTIONS))
            )
        elif suc:
            schema_dict[vol.Required("sensor_usage", default=str(sen["sensor_usage"]))] = (
                _select([selector.SelectOptionDict(value=str(v), label=lbl) for v, lbl in suc])
            )
        if out.get("output_usage_choices"):
            schema_dict[vol.Required("output_usage", default=str(out["output_usage"]))] = (
                _select([selector.SelectOptionDict(value=str(v), label=lbl) for v, lbl in out["output_usage_choices"]])
            )
        if out.get("function_choices"):
            schema_dict[vol.Required("function", default=str(out["function"]))] = (
                _select([selector.SelectOptionDict(value=str(v), label=lbl) for v, lbl in out["function_choices"]])
            )
        if out.get("optional_tilt"):
            schema_dict[vol.Optional("has_tilt", default=False)] = selector.BooleanSelector()

        if out.get("placement_choice"):
            schema_dict[vol.Required("cover_placement", default="indoor")] = (
                selector.SelectSelector(selector.SelectSelectorConfig(options=_COVER_PLACEMENT_OPTIONS))
            )

        def _timing_field(key: str):
            v = out.get(key)
            return vol.Optional(key, default=v) if v is not None else vol.Optional(key)

        if out.get("shadow_position_timing"):
            _ns = selector.NumberSelectorConfig(min=0, step=0.1, mode="box", unit_of_measurement="s")
            schema_dict[_timing_field("openTime")]      = selector.NumberSelector(_ns)
            schema_dict[_timing_field("closeTime")]     = selector.NumberSelector(_ns)
            schema_dict[_timing_field("stopDelayTime")] = selector.NumberSelector(_ns)
        if out.get("shadow_angle_timing"):
            _ns = selector.NumberSelectorConfig(min=0, step=0.1, mode="box", unit_of_measurement="s")
            schema_dict[_timing_field("angleOpenTime")]  = selector.NumberSelector(_ns)
            schema_dict[_timing_field("angleCloseTime")] = selector.NumberSelector(_ns)

        current = self._pending_choice_idx + 1
        total = len(self._pending_choice_entities)
        return self.async_show_form(
            step_id="device_entity_user_input",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "current": str(current),
                "total": str(total),
                "entity_name": entity_info.friendly_name,
                "domain": entity_info.domain,
            },
        )

    async def async_step_device_plan_summary(self, user_input: dict | None = None):
        """Show auto-generated vdSD plan; user proceeds or cancels."""
        if user_input is not None:
            if user_input.get("action") == "cancel":
                return await self.async_step_creation_mode()
            # Resolve all plans now (user_choices are all set)
            entity_states: dict[str, dict] = {}
            for plan in self._vdsd_plans:
                for e in [plan.output_entity, plan.binary_input_entity,
                          plan.button_entity, *plan.sensor_entities]:
                    if e is not None:
                        state = self.hass.states.get(e.entity_id)
                        entity_states[e.entity_id] = dict(state.attributes) if state else {}
            for plan in self._vdsd_plans:
                plan.resolved_vdsd = resolve_vdsd_plan(
                    plan, self._device_name, self._vendor_name,
                    self._display_id, entity_states,
                )
                primary_e = (
                    plan.output_entity
                    or plan.binary_input_entity
                    or plan.button_entity
                    or (plan.sensor_entities[0] if plan.sensor_entities else None)
                )
                if primary_e and plan.resolved_vdsd is not None:
                    icon_name, icon_b64 = await self._resolve_entity_icon(
                        primary_e.entity_id
                    )
                    plan.resolved_vdsd["icon_name"] = icon_name
                    if icon_b64:
                        plan.resolved_vdsd["icon_data_b64"] = icon_b64
                    _state_for_slug = self.hass.states.get(primary_e.entity_id)
                    plan.resolved_vdsd["icon_slug"] = (
                        _mdi_icon_name_for(_state_for_slug, primary_e.entity_id)
                        if _state_for_slug else None
                    )
            self._pending_vdsd_idx = 0
            return await self.async_step_device_model_features()

        # Build summary text for description_placeholders
        lines: list[str] = []
        for i, plan in enumerate(self._vdsd_plans, 1):
            parts: list[str] = []
            if plan.output_entity:
                parts.append(f"output: {plan.output_entity.entity_id}")
            if plan.binary_input_entity:
                parts.append(f"binary input: {plan.binary_input_entity.entity_id}")
            if plan.button_entity:
                parts.append(f"button: {plan.button_entity.entity_id}")
            if plan.sensor_entities:
                parts.append(f"{len(plan.sensor_entities)} sensor(s)")
            lines.append(f"{i}. {plan.name} ({', '.join(parts)})")
        summary = "\n".join(lines) or "(no vdSDs)"

        unsupported_lines: list[str] = [
            f"• {e.entity_id}" for e in self._unsupported_entities
        ]
        unsupported = (
            "\n".join(unsupported_lines)
            if unsupported_lines
            else "(none — all entities mapped)"
        )

        schema = vol.Schema({
            vol.Required("action", default="proceed"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=[
                    selector.SelectOptionDict(value="proceed", label="Proceed"),
                    selector.SelectOptionDict(value="cancel", label="Cancel"),
                ])
            ),
        })
        return self.async_show_form(
            step_id="device_plan_summary",
            data_schema=schema,
            description_placeholders={"summary": summary, "unsupported": unsupported},
        )

    async def async_step_device_model_features(self, user_input: dict | None = None):
        """Per-vdSD model features selection for the HA-device path."""
        plan = self._vdsd_plans[self._pending_vdsd_idx]
        vdsd: dict = plan.resolved_vdsd or {}

        if user_input is not None:
            plan.model_features = user_input.get("features", [])
            if plan.resolved_vdsd is not None:
                plan.resolved_vdsd["model_features"] = plan.model_features
            self._pending_vdsd_idx += 1
            if self._pending_vdsd_idx < len(self._vdsd_plans):
                return await self.async_step_device_model_features()
            self._pending_name_confirm_idx = 0
            return await self.async_step_name_confirm()

        auto_features = derive_model_features_for_config(vdsd)
        options: list[selector.SelectOptionDict] = [
            selector.SelectOptionDict(value=k, label=l)
            for k, l in {**_AUTO_FEATURE_LABELS, **_OPTIONAL_FEATURE_LABELS}.items()
        ]
        schema = vol.Schema({
            vol.Optional("features", default=sorted(auto_features)): selector.SelectSelector(
                selector.SelectSelectorConfig(options=options, multiple=True)
            ),
        })
        current = self._pending_vdsd_idx + 1
        total = len(self._vdsd_plans)
        return self.async_show_form(
            step_id="device_model_features",
            data_schema=schema,
            description_placeholders={
                "current": str(current),
                "total": str(total),
                "vdsd_name": plan.name,
            },
        )

    # ── "From scratch" creation path ──────────────────────────────────────────

    async def async_step_device_info(self, user_input: dict | None = None):
        """Collect basic device identity."""
        if user_input is not None:
            self._creation_mode = "from_scratch"
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
            return_step = self._optional_return_step if self._optional_return_step in _OPTIONAL_RETURN_STEPS else "vdsd_overview"
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
            if self._creation_mode == "from_entity":
                return await self.async_step_name_confirm()
            self._vdsds.append(dict(self._current_vdsd))
            return await self.async_step_device_summary()

        auto_features = derive_model_features_for_config({
            "primaryGroup": self._current_vdsd.get("primaryGroup", 1),
            "buttons": self._current_buttons,
            "binary_inputs": self._current_binary_inputs,
            "sensors": self._current_sensors,
            "output": self._current_output,
            "identify_action": self._current_vdsd.get("identify_action"),
        })
        options: list[selector.SelectOptionDict] = [
            selector.SelectOptionDict(value=k, label=l)
            for k, l in {**_AUTO_FEATURE_LABELS, **_OPTIONAL_FEATURE_LABELS}.items()
        ]
        schema = vol.Schema({
            vol.Optional("features", default=sorted(auto_features)): selector.SelectSelector(
                selector.SelectSelectorConfig(options=options, multiple=True)
            ),
        })
        return self.async_show_form(step_id="model_features", data_schema=schema)

    async def async_step_entity_completion(self, user_input: dict | None = None):
        """Entity-based flow: create the device or add another vdSD component."""
        if user_input is not None:
            action = user_input.get("action", "create")
            if action == "add_vdsd":
                # Reset per-vdSD state; preserve _device_name/_vendor_name/_display_id/_vdsds
                self._current_vdsd = {}
                self._current_buttons = []
                self._current_binary_inputs = []
                self._current_sensors = []
                self._current_output = None
                self._current_channels = []
                self._entity_id = ""
                self._entity_mapping = None
                return await self.async_step_entity_picker()
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
            f"{v.get('name', v.get('displayId', '?'))} (group {v.get('primaryGroup', '?')})"
            for v in self._vdsds
        ]
        schema = vol.Schema({
            vol.Required("action", default="create"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=[
                    selector.SelectOptionDict(value="create", label="Create device"),
                    selector.SelectOptionDict(value="add_vdsd",
                                              label="Add additional device component (vdSD)"),
                ])
            ),
        })
        return self.async_show_form(
            step_id="entity_completion",
            data_schema=schema,
            description_placeholders={
                "device_name": self._device_name,
                "vdsds": ", ".join(vdsd_summary),
            },
        )

    async def async_step_name_confirm(self, user_input: dict | None = None):
        """Let the user confirm or edit device and entity names before saving."""
        if self._creation_mode == "from_ha_device":
            plan = self._vdsd_plans[self._pending_name_confirm_idx]
            vdsd = plan.resolved_vdsd or {}
            if user_input is not None:
                if plan.resolved_vdsd is not None:
                    plan.resolved_vdsd["displayId"] = user_input.get("device_name", vdsd.get("displayId", ""))
                    plan.resolved_vdsd["name"] = user_input.get("entity_name", vdsd.get("name", ""))
                self._pending_name_confirm_idx += 1
                if self._pending_name_confirm_idx < len(self._vdsd_plans):
                    return await self.async_step_name_confirm()
                self._vdsds = [p.resolved_vdsd for p in self._vdsd_plans if p.resolved_vdsd]
                return await self.async_step_device_summary()
            device_name = vdsd.get("displayId", vdsd.get("name", ""))
            entity_name = vdsd.get("name", "")
        else:
            if user_input is not None:
                if "device_name" in user_input:
                    self._current_vdsd["displayId"] = user_input["device_name"]
                if "entity_name" in user_input:
                    self._apply_entity_name(user_input["entity_name"])
                self._vdsds.append(dict(self._current_vdsd))
                return await self.async_step_entity_completion()
            device_name = self._current_vdsd.get("displayId", self._current_vdsd.get("name", ""))
            entity_name = self._derive_entity_name_proposal()

        schema = vol.Schema({
            vol.Required("device_name", default=device_name): selector.TextSelector(),
            vol.Required("entity_name", default=entity_name): selector.TextSelector(),
        })
        return self.async_show_form(step_id="name_confirm", data_schema=schema)

    def _derive_entity_name_proposal(self) -> str:
        """Return a proposed entity name based on what's configured."""
        if self._current_output:
            return self._current_output.get("name", "Output")
        if self._current_binary_inputs:
            return self._current_binary_inputs[0].get("name", "Binary Input")
        if self._current_sensors:
            return self._current_sensors[0].get("name", "Sensor")
        if self._current_buttons:
            return self._current_buttons[0].get("name", "Button")
        return ""

    def _apply_entity_name(self, name: str) -> None:
        """Apply the confirmed entity name to the configured component."""
        if self._current_output:
            self._current_output["name"] = name
        elif self._current_binary_inputs:
            self._current_binary_inputs[0]["name"] = name
        elif self._current_sensors:
            self._current_sensors[0]["name"] = name
        elif self._current_buttons:
            self._current_buttons[0]["name"] = name

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
            vol.Required("buttonType", default="1"): _select(_BUTTON_TYPE_OPTIONS),
            vol.Required("group", default="1"): _select(_BUTTON_GROUP_OPTIONS),
            vol.Required("function", default="0"): _select(_BUTTON_FUNCTION_OPTIONS),
            vol.Required("mode", default="0"): _select(_BUTTON_MODE_OPTIONS),
            vol.Optional("channel", default=0): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=255, mode="box")
            ),
            vol.Optional("supportsLocalKeyMode", default=False): selector.BooleanSelector(),
            vol.Optional("setsLocalPriority", default=False): selector.BooleanSelector(),
            vol.Optional("callsPresent", default=True): selector.BooleanSelector(),
            vol.Required("callbackType", default="clickTypes"): _select([
                selector.SelectOptionDict(value="clickTypes", label="Click types (passthrough: entity state = click type number)"),
                selector.SelectOptionDict(value="actionIds", label="Scene / action IDs (passthrough: entity state = scene number)"),
                selector.SelectOptionDict(value="detect_clicks", label="Auto-detect (binary sensor / event / button entity)"),
            ]),
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
            return await self.async_step_binary_input_binding()
        schema = vol.Schema({
            vol.Required("name"): selector.TextSelector(),
            vol.Required("group", default="8"): _select(_BINARY_INPUT_GROUP_OPTIONS),
            vol.Required("sensorFunction", default="0"): _select(_BINARY_INPUT_TYPE_OPTIONS),
            vol.Required("hardwiredFunction", default="0"): _select(_BINARY_INPUT_TYPE_OPTIONS),
            vol.Optional("updateInterval", default=0): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, mode="box")
            ),
            vol.Required("inputType", default="1"): _select(_INPUT_TYPE_OPTIONS),
            vol.Required("inputUsage", default="0"): _select(_BINARY_INPUT_USAGE_OPTIONS),
            vol.Required("valueType", default="boolean"): _select([
                selector.SelectOptionDict(value="boolean", label="Boolean (true / false)"),
                selector.SelectOptionDict(value="integer", label="Integer (extended value)"),
            ]),
            vol.Optional("callback_entity"): selector.EntitySelector(),
        })
        return self.async_show_form(step_id="binary_input", data_schema=schema)

    async def async_step_binary_input_binding(self, user_input: dict | None = None):
        """Structured binding for binary input callback."""
        if user_input is not None:
            bi = self._current_binary_inputs[-1]
            binding_type = user_input.get("binding_type", "entity_state")
            if binding_type == "entity_state":
                bi["callback_entity"] = user_input.get("source_entity")
            elif binding_type == "entity_attribute":
                bi["callback_entity"] = user_input.get("source_entity")
                if attr := user_input.get("source_attribute"):
                    bi["value_attribute"] = attr
                bi["value_transform"] = user_input.get("transform", "passthrough")
            return await self.async_step_vdsd_overview()

        schema = vol.Schema({
            vol.Required("binding_type", default="entity_state"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=[
                    selector.SelectOptionDict(value="entity_state", label="Use entity on/off state"),
                    selector.SelectOptionDict(value="entity_attribute", label="Use attribute value with transform"),
                ], mode=selector.SelectSelectorMode.LIST)
            ),
            vol.Optional("source_entity"): selector.EntitySelector(),
            vol.Optional("source_attribute", default=""): selector.TextSelector(),
            vol.Optional("transform", default="bool_to_1_0"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=TRANSFORM_OPTIONS)
            ),
        })
        return self.async_show_form(step_id="binary_input_binding", data_schema=schema)

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
            return await self.async_step_sensor_binding()
        schema = vol.Schema({
            vol.Required("name"): selector.TextSelector(),
            vol.Required("group", default="0"): _select(_SENSOR_GROUP_OPTIONS),
            vol.Required("sensorType", default="1"): _select(_SENSOR_TYPE_OPTIONS),
            vol.Required("sensorUsage", default="1"): _select(_SENSOR_USAGE_OPTIONS),
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

    async def async_step_sensor_binding(self, user_input: dict | None = None):
        """Structured binding for sensor input callback."""
        if user_input is not None:
            si = self._current_sensors[-1]
            si["callback_entity"] = user_input.get("source_entity")
            if attr := user_input.get("source_attribute"):
                si["value_attribute"] = attr
            if transform := user_input.get("transform"):
                si["value_transform"] = transform
            return await self.async_step_vdsd_overview()

        schema = vol.Schema({
            vol.Optional("source_entity"): selector.EntitySelector(),
            vol.Optional("source_attribute", default=""): selector.TextSelector(),
            vol.Optional("transform", default="passthrough"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=TRANSFORM_OPTIONS)
            ),
        })
        return self.async_show_form(step_id="sensor_binding", data_schema=schema)

    async def async_step_output(self, user_input: dict | None = None):
        """Collect output configuration."""
        if user_input is not None:
            action = user_input.pop("action", "next") if isinstance(user_input, dict) else "next"
            fn = int(user_input["function"])
            output = {
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
            self._current_output = output
            self._current_channels = []

            if action == "output_optional":
                return await self.async_step_output_optional()

            if fn in _MANUAL_CHANNEL_FUNCTIONS:
                return await self.async_step_channel()
            for i, ct in enumerate(FUNCTION_CHANNELS.get(OutputFunction(fn), [])):
                self._current_channels.append({
                    "dsIndex": i,
                    "channelType": int(ct),
                })
            return await self.async_step_channel_mapping()
        schema = vol.Schema({
            vol.Required("name"): selector.TextSelector(),
            vol.Required("groups", default=["1"]): _select(_COLOR_CLASS_OPTIONS, multiple=True),
            vol.Required("defaultGroup", default="1"): _select(_COLOR_CLASS_OPTIONS),
            vol.Required("function", default="0"): _select(_OUTPUT_FUNCTION_OPTIONS),
            vol.Required("outputUsage", default="0"): _select(_OUTPUT_USAGE_OPTIONS),
            vol.Optional("variableRamp", default=False): selector.BooleanSelector(),
            vol.Required("mode", default="127"): _select(_OUTPUT_MODE_OPTIONS),
            vol.Required("action", default="next"): _select([
                selector.SelectOptionDict(value="next", label="Continue"),
                selector.SelectOptionDict(value="output_optional", label="Optional output settings…"),
            ]),
        })
        return self.async_show_form(step_id="output", data_schema=schema)

    async def async_step_output_optional(self, user_input: dict | None = None):
        """Collect optional output settings."""
        if user_input is not None:
            if self._current_output:
                for k, v in user_input.items():
                    if v is not None and v != "":
                        self._current_output[k] = v
            # Convert dim_time NumberSelector floats to int (dS 8-bit format)
            for _k in ("dimTimeUp", "dimTimeDown", "dimTimeUpAlt1", "dimTimeDownAlt1",
                       "dimTimeUpAlt2", "dimTimeDownAlt2"):
                if _k in self._current_output:
                    self._current_output[_k] = int(self._current_output[_k])
            fn = self._current_output.get("function", 0) if self._current_output else 0
            if fn in _MANUAL_CHANNEL_FUNCTIONS:
                return await self.async_step_channel()
            for i, ct in enumerate(FUNCTION_CHANNELS.get(OutputFunction(fn), [])):
                self._current_channels.append({
                    "dsIndex": i,
                    "channelType": int(ct),
                })
            return await self.async_step_channel_mapping()

        fn = self._current_output.get("function", 0) if self._current_output else 0
        is_positional = fn == OutputFunction.POSITIONAL.value
        is_on_off = fn == OutputFunction.ON_OFF.value
        _ns_pct = selector.NumberSelectorConfig(min=0, max=100, mode="box")
        _ns_s   = selector.NumberSelectorConfig(min=0, step=0.1, mode="box", unit_of_measurement="s")
        schema_dict: dict = {}
        if is_on_off:
            schema_dict[vol.Optional("onThreshold", default=50)] = selector.NumberSelector(_ns_pct)
        schema_dict.update({
            vol.Optional("minBrightness"): selector.NumberSelector(_ns_pct),
            vol.Optional("maxPower"): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, mode="box")
            ),
            vol.Optional("activeCoolingMode", default=False): selector.BooleanSelector(),
        })
        if is_positional:
            schema_dict[vol.Optional("openTime")]      = selector.NumberSelector(_ns_s)
            schema_dict[vol.Optional("closeTime")]     = selector.NumberSelector(_ns_s)
            schema_dict[vol.Optional("stopDelayTime")] = selector.NumberSelector(_ns_s)
            schema_dict[vol.Optional("angleOpenTime")] = selector.NumberSelector(_ns_s)
            schema_dict[vol.Optional("angleCloseTime")]= selector.NumberSelector(_ns_s)
        is_dimmer = fn in (
            OutputFunction.DIMMER.value,
            OutputFunction.DIMMER_COLOR_TEMP.value,
            OutputFunction.FULL_COLOR_DIMMER.value,
        )
        if is_dimmer:
            # dS 8-bit format int (0-255), NOT milliseconds
            _ns_ds8 = selector.NumberSelectorConfig(min=0, max=255, step=1, mode="box")
            schema_dict[vol.Optional("dimTimeUp")]        = selector.NumberSelector(_ns_ds8)
            schema_dict[vol.Optional("dimTimeDown")]      = selector.NumberSelector(_ns_ds8)
            schema_dict[vol.Optional("dimTimeUpAlt1")]    = selector.NumberSelector(_ns_ds8)
            schema_dict[vol.Optional("dimTimeDownAlt1")]  = selector.NumberSelector(_ns_ds8)
            schema_dict[vol.Optional("dimTimeUpAlt2")]    = selector.NumberSelector(_ns_ds8)
            schema_dict[vol.Optional("dimTimeDownAlt2")]  = selector.NumberSelector(_ns_ds8)
        schema_dict[vol.Optional("heatingSystemCapability")] = selector.SelectSelector(
            selector.SelectSelectorConfig(options=[
                selector.SelectOptionDict(value="", label="(not specified)"),
                *[selector.SelectOptionDict(value=str(m.value), label=m.name)
                  for m in HeatingSystemCapability],
            ])
        )
        schema_dict[vol.Optional("heatingSystemType")] = selector.SelectSelector(
            selector.SelectSelectorConfig(options=[
                selector.SelectOptionDict(value="", label="(not specified)"),
                *[selector.SelectOptionDict(value=str(m.value), label=m.name)
                  for m in HeatingSystemType],
            ])
        )
        return self.async_show_form(step_id="output_optional", data_schema=vol.Schema(schema_dict))

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

    async def async_step_channel_push_binding(self, user_input: dict | None = None):
        """Collect the HA→dS push binding for the current output channel (one channel at a time)."""
        if user_input is not None:
            ch = self._current_channels[self._channel_mapping_idx]
            source_attr = user_input.get("source_attribute") or None
            binding = {
                "source_entity": user_input.get("source_entity"),
                "source_attribute": source_attr,
                "transform": user_input.get("transform", "passthrough"),
            }
            if binding["source_entity"]:
                ch["read_entity"] = binding["source_entity"]
            ch["push_expr"] = compile_push_binding(binding)
            return await self.async_step_channel_apply_binding()

        ch = self._current_channels[self._channel_mapping_idx]
        ch_type = ch.get("channelType", 0)
        ch_label = _CHANNEL_TYPE_LABELS.get(ch_type, f"Channel {ch_type}")

        attr_options = [
            {"value": "", "label": "(use main entity state)"},
            {"value": "brightness", "label": "brightness"},
            {"value": "color_temp", "label": "color_temp (mired)"},
            {"value": "color_temp_kelvin", "label": "color_temp_kelvin (K)"},
            {"value": "current_position", "label": "current_position"},
            {"value": "current_tilt_position", "label": "current_tilt_position"},
            {"value": "hs_color", "label": "hs_color (tuple)"},
            {"value": "percentage", "label": "percentage"},
            {"value": "volume_level", "label": "volume_level"},
        ]

        schema = vol.Schema({
            vol.Required("source_entity"): selector.EntitySelector(),
            vol.Optional("source_attribute", default=""): selector.SelectSelector(
                selector.SelectSelectorConfig(options=attr_options, custom_value=True)
            ),
            vol.Required("transform", default="passthrough"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=TRANSFORM_OPTIONS)
            ),
        })
        return self.async_show_form(
            step_id="channel_push_binding",
            data_schema=schema,
            description_placeholders={"channel": ch_label},
        )

    async def async_step_channel_apply_binding(self, user_input: dict | None = None):
        """Collect the dS→HA apply binding for the current output channel."""
        ch = self._current_channels[self._channel_mapping_idx]
        ch_type = ch.get("channelType", 0)
        ch_label = _CHANNEL_TYPE_LABELS.get(ch_type, f"Channel {ch_type}")

        if user_input is not None:
            service_raw = user_input.get("service", "")
            if service_raw:
                binding = {
                    "service": service_raw,
                    "parameter": user_input.get("parameter") or None,
                    "transform": user_input.get("transform", "passthrough"),
                }
                ch["apply_expr"] = compile_apply_binding(binding)
            # Advance to next channel or finish
            self._channel_mapping_idx += 1
            if self._channel_mapping_idx < len(self._current_channels):
                return await self.async_step_channel_push_binding()
            if self._current_output is not None:
                self._current_output["channels"] = self._current_channels
            return await self.async_step_vdsd_overview()

        service_options = [
            {"value": "", "label": "(no dS→HA control for this channel)"},
            {"value": "light.turn_on", "label": "light.turn_on"},
            {"value": "light.turn_off", "label": "light.turn_off"},
            {"value": "switch.turn_on", "label": "switch.turn_on"},
            {"value": "switch.turn_off", "label": "switch.turn_off"},
            {"value": "cover.set_cover_position", "label": "cover.set_cover_position"},
            {"value": "cover.set_cover_tilt_position", "label": "cover.set_cover_tilt_position"},
            {"value": "fan.set_percentage", "label": "fan.set_percentage"},
            {"value": "number.set_value", "label": "number.set_value"},
            {"value": "climate.set_temperature", "label": "climate.set_temperature"},
        ]

        parameter_options = [
            {"value": "", "label": "(no parameter — value not passed)"},
            {"value": "brightness", "label": "brightness"},
            {"value": "color_temp_kelvin", "label": "color_temp_kelvin"},
            {"value": "position", "label": "position"},
            {"value": "tilt_position", "label": "tilt_position"},
            {"value": "percentage", "label": "percentage"},
            {"value": "value", "label": "value"},
            {"value": "temperature", "label": "temperature"},
            {"value": "volume_level", "label": "volume_level"},
        ]

        schema = vol.Schema({
            vol.Optional("service", default=""): selector.SelectSelector(
                selector.SelectSelectorConfig(options=service_options, custom_value=True)
            ),
            vol.Optional("parameter", default=""): selector.SelectSelector(
                selector.SelectSelectorConfig(options=parameter_options, custom_value=True)
            ),
            vol.Required("transform", default="passthrough"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=TRANSFORM_OPTIONS)
            ),
        })
        return self.async_show_form(
            step_id="channel_apply_binding",
            data_schema=schema,
            description_placeholders={"channel": ch_label},
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
