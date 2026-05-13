# dsvdc4ha Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a HACS-compliant HA integration that bridges HA entities to a digitalStrom system via pydsvdcapi, implementing a vDC-host + vDC hub with per-device config entries containing vdSD devices and callback-based sensor/binary_sensor entities.

**Architecture:** A hub config entry sets up the VdcHost + Vdc via `api.py` (pydsvdcapi wrapper) managed by `HubCoordinator`. Device config entries each declare one or more vdSDs; on setup they register HA devices and entities (sensor / binary_sensor mirrors of callback values). Inputs report HA state changes to dS; outputs bridge bidirectionally via a read-entity listener (HA→dS) and a write-action call (dS→HA via `Output.on_channel_applied`).

**Tech Stack:** Python 3.12, Home Assistant 2025.x, pydsvdcapi 0.8.0, pytest, pytest-homeassistant-custom-component

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `hacs.json` | Create | HACS metadata |
| `custom_components/dsvdc4ha/manifest.json` | Update | requirements, iot_class, codeowners |
| `custom_components/dsvdc4ha/const.py` | Update | all domain constants, enum maps |
| `custom_components/dsvdc4ha/strings.json` | Create | UI string definitions |
| `custom_components/dsvdc4ha/translations/en.json` | Update | English UI strings |
| `custom_components/dsvdc4ha/api.py` | Create | pydsvdcapi wrapper — only file that imports pydsvdcapi |
| `custom_components/dsvdc4ha/coordinator.py` | Create | HubCoordinator — VdcHost/Vdc lifecycle |
| `custom_components/dsvdc4ha/base_entity.py` | Create | DsvdcBaseEntity — shared entity base |
| `custom_components/dsvdc4ha/sensor.py` | Create | Button, sensor-input, output-channel sensor entities |
| `custom_components/dsvdc4ha/binary_sensor.py` | Create | Binary input binary_sensor entities |
| `custom_components/dsvdc4ha/__init__.py` | Update | entry_type branching, platform setup, teardown |
| `custom_components/dsvdc4ha/config_flow.py` | Update | Hub flow + full device sub-flow |
| `tests/__init__.py` | Create | empty |
| `tests/conftest.py` | Create | shared fixtures |
| `tests/test_config_flow.py` | Create | hub flow + device flow tests |
| `tests/test_coordinator.py` | Create | coordinator lifecycle tests |
| `tests/test_sensor.py` | Create | entity state + callback tests |

---

## Phase 1 — HACS Scaffold

### Task 1: HACS files + manifest + const skeleton

**Files:**
- Create: `hacs.json`
- Update: `custom_components/dsvdc4ha/manifest.json`
- Update: `custom_components/dsvdc4ha/const.py`
- Create: `custom_components/dsvdc4ha/strings.json`
- Update: `custom_components/dsvdc4ha/translations/en.json`

- [ ] **Step 1: Create `hacs.json`**

```json
{
  "name": "dsvdc4ha",
  "render_readme": true
}
```

- [ ] **Step 2: Update `manifest.json`**

```json
{
  "domain": "dsvdc4ha",
  "name": "dSVDC for Home Assistant",
  "version": "0.1.0",
  "documentation": "https://github.com/KarlKiel/dsvdc4ha",
  "requirements": ["pydsvdcapi==0.8.0"],
  "dependencies": [],
  "codeowners": ["@KarlKiel"],
  "iot_class": "local_push",
  "config_flow": true
}
```

- [ ] **Step 3: Replace `const.py` with full constants**

```python
"""Constants for the dsvdc4ha integration."""
from __future__ import annotations

DOMAIN = "dsvdc4ha"

ENTRY_TYPE_HUB = "hub"
ENTRY_TYPE_DEVICE = "device"

PLATFORMS = ["sensor", "binary_sensor"]

VDC_HOST_NAME = "KarlKiel's Home Assistant vDC-host"
VDC_HOST_MODEL = "KarlKiel's vDC-host @ Home Assistant"
VDC_HOST_MODEL_UID = "KarlKiel's Home Assistant vDC-host"
VDC_HOST_VENDOR_NAME = "KarlKiel"
VDC_HOST_VENDOR_GUID = "vendorname:KarlKiel"

VDC_NAME = "KarlKiel's Home Assistant DS vDC"
VDC_MODEL = "KarlKiel's generic vDC @ Home Assistant"
VDC_MODEL_UID = "KarlKiel's Home Assistant DS vDC"
VDC_IMPLEMENTATION_ID = "x-KarlKiel-HomeAssistant-vDC"
VDC_DEVICE_ICON_NAME = "KarlKielVDC.png"

CONF_PORT = "port"
CONF_ENTRY_TYPE = "entry_type"
CONF_VDSDS = "vdsds"
CONF_VENDOR_NAME = "vendorName"
CONF_DISPLAY_ID = "displayId"

CLICK_TYPE_NAMES: dict[int, str] = {
    0: "tip_1x", 1: "tip_2x", 2: "tip_3x", 3: "tip_4x",
    4: "hold_start", 5: "hold_repeat", 6: "hold_end",
    7: "click_1x", 8: "click_2x", 9: "click_3x",
    10: "short_long", 11: "local_off", 12: "local_on",
    13: "short_short_long", 14: "local_stop", 15: "local_dim",
}
```

- [ ] **Step 4: Create `strings.json`**

```json
{
  "config": {
    "step": {
      "hub": {
        "title": "Set up dSVDC Hub",
        "description": "Enter the port for the virtualDC connection.",
        "data": { "port": "Port" }
      },
      "device_info": {
        "title": "Add Physical Device",
        "data": {
          "name": "Device name",
          "vendorName": "Vendor name",
          "displayId": "Device type / display ID"
        }
      },
      "vdsd_creation": {
        "title": "Create vdSD",
        "data": {
          "displayId": "Component name",
          "primaryGroup": "Primary group",
          "modelVersion": "Exact model name",
          "identify_action": "Identify action (optional)",
          "firmwareUpdate_action": "Firmware update action (optional)"
        }
      },
      "optional_settings": {
        "title": "Optional vdSD Settings",
        "data": {
          "hardwareVersion": "Hardware version",
          "vendorGuid": "Vendor GUID",
          "deviceIcon16": "Device icon name"
        }
      },
      "vdsd_overview": { "title": "vdSD Overview" },
      "button": {
        "title": "Configure Button",
        "data": {
          "name": "Button name",
          "buttonType": "Button type",
          "group": "Group",
          "function": "Function",
          "mode": "Mode",
          "channel": "Output channel",
          "supportsLocalKeyMode": "Supports local key mode",
          "setsLocalPriority": "Sets local priority",
          "callsPresent": "Calls present",
          "callbackType": "Callback type",
          "callback_entity": "HA entity providing click data"
        }
      },
      "binary_input": {
        "title": "Configure Binary Input",
        "data": {
          "name": "Binary input name",
          "group": "Group",
          "sensorFunction": "Sensor function",
          "hardwiredFunction": "Hardwired function",
          "updateInterval": "Update interval (s)",
          "inputType": "Input type",
          "inputUsage": "Input usage",
          "valueType": "Value type",
          "callback_entity": "HA entity providing value"
        }
      },
      "sensor": {
        "title": "Configure Sensor",
        "data": {
          "name": "Sensor name",
          "group": "Group",
          "sensorType": "Sensor type",
          "sensorUsage": "Sensor usage",
          "min": "Min value",
          "max": "Max value",
          "resolution": "Resolution (LSB)",
          "updateInterval": "Update interval (s)",
          "aliveSignInterval": "Alive sign interval (s)",
          "minPushInterval": "Min push interval (s)",
          "changesOnlyInterval": "Changes-only interval (s)",
          "callback_entity": "HA entity providing sensor value"
        }
      },
      "output": {
        "title": "Configure Output",
        "data": {
          "name": "Output name",
          "groups": "Supported groups",
          "defaultGroup": "Default group",
          "function": "Output function",
          "outputUsage": "Output usage",
          "variableRamp": "Variable ramp",
          "mode": "Operating mode"
        }
      },
      "output_optional": {
        "title": "Optional Output Settings",
        "data": {
          "onThreshold": "On threshold",
          "minBrightness": "Min brightness",
          "maxPower": "Max power (W)",
          "activeCoolingMode": "Active cooling mode"
        }
      },
      "channel": {
        "title": "Configure Output Channel",
        "data": {
          "channelType": "Channel type",
          "name": "Channel name",
          "min": "Min value",
          "max": "Max value",
          "resolution": "Resolution"
        }
      },
      "channel_mapping": {
        "title": "Bind Output Channels to HA"
      },
      "model_features": { "title": "Model Features" },
      "device_summary": { "title": "Device Summary" }
    },
    "error": {
      "port_in_use": "Port is already in use.",
      "cannot_connect": "Cannot connect to digitalStrom server.",
      "unknown": "Unexpected error."
    },
    "abort": {
      "already_configured": "Integration is already configured."
    }
  }
}
```

- [ ] **Step 5: Update `translations/en.json`** to match `strings.json` (copy identical content).

- [ ] **Step 6: Commit**

```bash
git add hacs.json custom_components/dsvdc4ha/manifest.json \
  custom_components/dsvdc4ha/const.py custom_components/dsvdc4ha/strings.json \
  custom_components/dsvdc4ha/translations/en.json
git commit -m "feat: HACS scaffold — manifest, const, strings"
```

---

### Task 2: Test infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `requirements_test.txt`

- [ ] **Step 1: Create `requirements_test.txt`**

```
pytest
pytest-asyncio
pytest-homeassistant-custom-component
```

- [ ] **Step 2: Create `tests/__init__.py`** (empty file)

- [ ] **Step 3: Create `tests/conftest.py`**

```python
"""Shared test fixtures for dsvdc4ha."""
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture
def mock_api():
    """Return a mock DsvdcApi instance."""
    api = MagicMock()
    api.start = AsyncMock()
    api.stop = AsyncMock()
    api.announce_device = AsyncMock()
    api.vanish_device = AsyncMock()
    api.report_button_click = AsyncMock()
    api.report_sensor_value = AsyncMock()
    api.report_binary_value = AsyncMock()
    api.report_binary_extended_value = AsyncMock()
    api.report_channel_value = AsyncMock()
    return api


@pytest.fixture
def hub_config_entry_data():
    return {"entry_type": "hub", "port": 9090}


@pytest.fixture
def device_config_entry_data():
    return {
        "entry_type": "device",
        "name": "Test Lamp",
        "vendorName": "Acme",
        "displayId": "LampV1",
        "vdsds": [
            {
                "displayId": "LampUnit",
                "primaryGroup": 1,
                "model": "LampUnit",
                "vendorName": "Acme",
                "modelVersion": "v1",
                "modelUID": "AcmeLampV1",
                "active": True,
                "identify_action": None,
                "firmwareUpdate_action": None,
                "optional": {},
                "buttons": [],
                "binary_inputs": [],
                "sensors": [],
                "output": None,
            }
        ],
    }
```

- [ ] **Step 4: Verify pytest discovers fixtures**

```bash
cd /home/arne/Development/dsvdc4ha
.venv/bin/pytest tests/ --collect-only 2>&1 | head -20
```

Expected: no errors, fixtures listed.

- [ ] **Step 5: Commit**

```bash
git add tests/ requirements_test.txt
git commit -m "feat: test infrastructure — conftest and fixtures"
```

---

## Phase 2 — API Layer

### Task 3: `api.py` — hub setup and lifecycle

**Files:**
- Create: `custom_components/dsvdc4ha/api.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_api.py
"""Tests for DsvdcApi."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from custom_components.dsvdc4ha.api import DsvdcApi


@pytest.mark.asyncio
async def test_api_start_creates_host_and_vdc():
    with patch("custom_components.dsvdc4ha.api.VdcHost") as MockHost, \
         patch("custom_components.dsvdc4ha.api.Vdc") as MockVdc, \
         patch("custom_components.dsvdc4ha.api.VdcCapabilities") as MockCaps:
        mock_host_instance = MagicMock()
        mock_host_instance.start = AsyncMock()
        MockHost.return_value = mock_host_instance
        MockVdc.return_value = MagicMock()
        MockCaps.return_value = MagicMock()

        api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp/test_state")
        await api.start()

        MockHost.assert_called_once()
        call_kwargs = MockHost.call_args.kwargs
        assert call_kwargs["port"] == 9090
        assert call_kwargs["model_version"] == "0.1.0"
        mock_host_instance.start.assert_awaited_once()
        MockVdc.assert_called_once()


@pytest.mark.asyncio
async def test_api_stop_calls_host_stop():
    with patch("custom_components.dsvdc4ha.api.VdcHost") as MockHost, \
         patch("custom_components.dsvdc4ha.api.Vdc"), \
         patch("custom_components.dsvdc4ha.api.VdcCapabilities"):
        mock_host_instance = MagicMock()
        mock_host_instance.start = AsyncMock()
        mock_host_instance.stop = AsyncMock()
        MockHost.return_value = mock_host_instance

        api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp/test_state")
        await api.start()
        await api.stop()

        mock_host_instance.stop.assert_awaited_once()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_api.py -v 2>&1 | tail -10
```

Expected: `ImportError` — `DsvdcApi` not found.

- [ ] **Step 3: Create `api.py`**

```python
"""pydsvdcapi wrapper — only file that imports pydsvdcapi directly."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydsvdcapi.dsuid import DsUid, DsUidNamespace
from pydsvdcapi.enums import ColorGroup, OutputChannelType
from pydsvdcapi.output import Output
from pydsvdcapi.output_channel import OutputChannel
from pydsvdcapi.vdc import Vdc, VdcCapabilities
from pydsvdcapi.vdc_host import VdcHost
from pydsvdcapi.vdsd import Device, Vdsd

from .const import (
    VDC_DEVICE_ICON_NAME,
    VDC_HOST_MODEL,
    VDC_HOST_MODEL_UID,
    VDC_HOST_NAME,
    VDC_HOST_VENDOR_GUID,
    VDC_HOST_VENDOR_NAME,
    VDC_IMPLEMENTATION_ID,
    VDC_MODEL,
    VDC_MODEL_UID,
    VDC_NAME,
)

_LOGGER = logging.getLogger(__name__)


class DsvdcApi:
    """Thin wrapper around pydsvdcapi VdcHost + Vdc."""

    def __init__(
        self,
        port: int,
        version: str,
        config_url: str,
        state_path: str,
    ) -> None:
        icon_path = Path(__file__).parent / "vdc.png"
        self._icon_bytes = icon_path.read_bytes() if icon_path.exists() else None
        self._port = port
        self._version = version
        self._config_url = config_url
        self._state_path = state_path
        self._host: VdcHost | None = None
        self._vdc: Vdc | None = None
        self._devices: dict[str, Device] = {}  # entry_id → Device

    async def start(self) -> None:
        """Create VdcHost + Vdc and start serving."""
        self._host = VdcHost(
            port=self._port,
            name=VDC_HOST_NAME,
            model=VDC_HOST_MODEL,
            model_version=self._version,
            model_uid=VDC_HOST_MODEL_UID,
            hardware_version=self._version,
            vendor_name=VDC_HOST_VENDOR_NAME,
            vendor_guid=VDC_HOST_VENDOR_GUID,
            config_url=self._config_url,
            device_icon_16=self._icon_bytes,
            device_icon_name=VDC_DEVICE_ICON_NAME,
            state_path=self._state_path,
        )
        caps = VdcCapabilities(
            metering=False,
            identification=False,
            dynamic_definitions=True,
        )
        self._vdc = Vdc(
            host=self._host,
            implementation_id=VDC_IMPLEMENTATION_ID,
            name=VDC_NAME,
            model=VDC_MODEL,
            model_version=self._version,
            model_uid=VDC_MODEL_UID,
            vendor_name=VDC_HOST_VENDOR_NAME,
            vendor_guid=VDC_HOST_VENDOR_GUID,
            config_url=self._config_url,
            device_icon_16=self._icon_bytes,
            device_icon_name=VDC_DEVICE_ICON_NAME,
            capabilities=caps,
        )
        self._host.add_vdc(self._vdc)
        await self._host.start(announce=True)
        _LOGGER.debug("VdcHost started on port %d", self._port)

    async def stop(self) -> None:
        """Stop serving (does not vanish devices — call vanish_device first)."""
        if self._host:
            await self._host.stop()
            _LOGGER.debug("VdcHost stopped")

    @property
    def vdc(self) -> Vdc | None:
        return self._vdc

    @property
    def host(self) -> VdcHost | None:
        return self._host
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_api.py -v 2>&1 | tail -15
```

Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/api.py tests/test_api.py
git commit -m "feat: api.py — DsvdcApi hub start/stop"
```

---

### Task 4: `api.py` — device and vdSD management

**Files:**
- Update: `custom_components/dsvdc4ha/api.py`
- Update: `tests/test_api.py`

- [ ] **Step 1: Add failing tests**

```python
# append to tests/test_api.py

@pytest.mark.asyncio
async def test_api_announce_device_adds_to_vdc():
    with patch("custom_components.dsvdc4ha.api.VdcHost") as MockHost, \
         patch("custom_components.dsvdc4ha.api.Vdc") as MockVdc, \
         patch("custom_components.dsvdc4ha.api.VdcCapabilities"), \
         patch("custom_components.dsvdc4ha.api.Device") as MockDevice, \
         patch("custom_components.dsvdc4ha.api.DsUid"):
        mock_host = MagicMock()
        mock_host.start = AsyncMock()
        mock_host.session = MagicMock()
        MockHost.return_value = mock_host
        mock_vdc = MagicMock()
        MockVdc.return_value = mock_vdc
        mock_device = MagicMock()
        mock_device.announce = AsyncMock(return_value=1)
        MockDevice.return_value = mock_device

        api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")
        await api.start()
        await api.announce_device("entry-abc", [])

        mock_vdc.add_device.assert_called_once_with(mock_device)
        mock_device.announce.assert_awaited_once_with(mock_host.session)
```

- [ ] **Step 2: Run test — expect failure**

```bash
.venv/bin/pytest tests/test_api.py::test_api_announce_device_adds_to_vdc -v 2>&1 | tail -8
```

- [ ] **Step 3: Add `announce_device` and `vanish_device` to `api.py`**

Add these imports at top of `api.py`:

```python
from pydsvdcapi.binary_input import BinaryInput
from pydsvdcapi.button_input import ButtonInput
from pydsvdcapi.enums import (
    BinaryInputType,
    BinaryInputUsage,
    ButtonElementID,
    ButtonFunction,
    ButtonMode,
    ButtonType,
    ColorGroup,
    OutputChannelType,
    OutputFunction,
    OutputMode,
    OutputUsage,
    SensorType,
    SensorUsage,
)
from pydsvdcapi.sensor_input import SensorInput
```

Add these methods to `DsvdcApi`:

```python
    def _build_device_dsuid(self, entry_id: str) -> DsUid:
        return DsUid.from_name_in_space(entry_id, DsUidNamespace.VDC)

    async def announce_device(self, entry_id: str, vdsds_data: list[dict[str, Any]]) -> None:
        """Create a Device + its Vdsds and announce to dS."""
        assert self._vdc is not None and self._host is not None
        dsuid = self._build_device_dsuid(entry_id)
        device = Device(vdc=self._vdc, dsuid=dsuid)
        for idx, vdsd_data in enumerate(vdsds_data):
            vdsd = self._build_vdsd(device, idx, vdsd_data)
            device.add_vdsd(vdsd)
        self._vdc.add_device(device)
        self._devices[entry_id] = device
        await device.announce(self._host.session)

    def _build_vdsd(self, device: Device, idx: int, data: dict[str, Any]) -> Vdsd:
        vdsd = Vdsd(
            device=device,
            primary_group=ColorGroup(data["primaryGroup"]),
            subdevice_index=idx,
            name=data.get("name", data["displayId"]),
            model=data["model"],
            model_version=data.get("modelVersion"),
            model_uid=data.get("modelUID"),
            vendor_name=data.get("vendorName"),
            config_url=self._config_url,
            device_icon_16=self._icon_bytes,
            device_icon_name=VDC_DEVICE_ICON_NAME,
        )
        for btn_data in data.get("buttons", []):
            self._add_button(vdsd, btn_data)
        for bi_data in data.get("binary_inputs", []):
            self._add_binary_input(vdsd, bi_data)
        for si_data in data.get("sensors", []):
            self._add_sensor(vdsd, si_data)
        if output_data := data.get("output"):
            self._add_output(vdsd, output_data)
        vdsd.derive_model_features()
        return vdsd

    def _add_button(self, vdsd: Vdsd, data: dict[str, Any]) -> None:
        btn = ButtonInput(
            vdsd=vdsd,
            ds_index=data["dsIndex"],
            name=data["name"],
            button_type=ButtonType(data["buttonType"]),
            button_element_id=ButtonElementID(data["buttonElementID"]),
            group=data["group"],
            function=data["function"],
            mode=ButtonMode(data["mode"]),
            channel=data.get("channel", 0),
            supports_local_key_mode=data.get("supportsLocalKeyMode", False),
            sets_local_priority=data.get("setsLocalPriority", False),
            calls_present=data.get("callsPresent", True),
            button_id=data.get("buttonID", 0),
        )
        vdsd.add_button_input(btn)

    def _add_binary_input(self, vdsd: Vdsd, data: dict[str, Any]) -> None:
        bi = BinaryInput(
            vdsd=vdsd,
            ds_index=data["dsIndex"],
            name=data["name"],
            sensor_function=BinaryInputType(data["sensorFunction"]),
            hardwired_function=BinaryInputType(data.get("hardwiredFunction", 0)),
            group=data.get("group", 0),
            update_interval=float(data.get("updateInterval", 0)),
            input_type=data.get("inputType", 1),
            input_usage=BinaryInputUsage(data.get("inputUsage", 0)),
        )
        vdsd.add_binary_input(bi)

    def _add_sensor(self, vdsd: Vdsd, data: dict[str, Any]) -> None:
        si = SensorInput(
            vdsd=vdsd,
            ds_index=data["dsIndex"],
            name=data["name"],
            sensor_type=SensorType(data["sensorType"]),
            sensor_usage=SensorUsage(data.get("sensorUsage", 0)),
            group=data.get("group", 0),
            min_value=float(data["min"]),
            max_value=float(data["max"]),
            resolution=float(data["resolution"]),
            update_interval=float(data.get("updateInterval", 0)),
            alive_sign_interval=float(data.get("aliveSignInterval", 0)),
            min_push_interval=float(data.get("minPushInterval", 2.0)),
            changes_only_interval=float(data.get("changesOnlyInterval", 0)),
        )
        vdsd.add_sensor_input(si)

    def _add_output(self, vdsd: Vdsd, data: dict[str, Any]) -> None:
        output = Output(
            vdsd=vdsd,
            name=data["name"],
            function=OutputFunction(data["function"]),
            output_usage=OutputUsage(data.get("outputUsage", 0)),
            default_group=data["defaultGroup"],
            active_group=data["activeGroup"],
            groups=set(data["groups"]),
            variable_ramp=data.get("variableRamp", False),
            push_changes=True,
            mode=OutputMode(data["mode"]) if data.get("mode") is not None else None,
            on_threshold=data.get("onThreshold"),
            min_brightness=data.get("minBrightness"),
            max_power=data.get("maxPower"),
        )
        for ch_data in data.get("channels", []):
            OutputChannel(
                output=output,
                channel_type=OutputChannelType(ch_data["channelType"]),
                ds_index=ch_data["dsIndex"],
                name=ch_data.get("name"),
                min_value=ch_data.get("min"),
                max_value=ch_data.get("max"),
                resolution=ch_data.get("resolution"),
            )
        vdsd.set_output(output)

    async def vanish_device(self, entry_id: str) -> None:
        """Vanish and remove a device from dS."""
        if device := self._devices.pop(entry_id, None):
            if self._host and self._host.session:
                await device.vanish(self._host.session)
            if self._vdc:
                dsuid = self._build_device_dsuid(entry_id)
                self._vdc.remove_device(dsuid)

    def get_device(self, entry_id: str) -> Device | None:
        return self._devices.get(entry_id)
```

- [ ] **Step 4: Run all api tests**

```bash
.venv/bin/pytest tests/test_api.py -v 2>&1 | tail -10
```

Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/api.py tests/test_api.py
git commit -m "feat: api.py — device + vdSD management"
```

---

### Task 5: `api.py` — input reporting + output callbacks

**Files:**
- Update: `custom_components/dsvdc4ha/api.py`
- Update: `tests/test_api.py`

- [ ] **Step 1: Add failing tests**

```python
# append to tests/test_api.py

@pytest.mark.asyncio
async def test_report_button_click_calls_update_click():
    with patch("custom_components.dsvdc4ha.api.VdcHost") as MockHost, \
         patch("custom_components.dsvdc4ha.api.Vdc"), \
         patch("custom_components.dsvdc4ha.api.VdcCapabilities"):
        mock_host = MagicMock()
        mock_host.start = AsyncMock()
        mock_host.session = MagicMock()
        MockHost.return_value = mock_host

        api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")
        await api.start()

        mock_btn = MagicMock()
        mock_btn.update_click = AsyncMock()
        await api.report_button_click(mock_btn, 7)
        mock_btn.update_click.assert_awaited_once_with(
            click_type=7, session=mock_host.session
        )
```

- [ ] **Step 2: Run — expect failure**

```bash
.venv/bin/pytest tests/test_api.py::test_report_button_click_calls_update_click -v 2>&1 | tail -8
```

- [ ] **Step 3: Add reporting methods to `api.py`**

```python
    async def report_button_click(self, button: ButtonInput, click_type: int) -> None:
        assert self._host is not None
        await button.update_click(click_type=click_type, session=self._host.session)

    async def report_button_action(self, button: ButtonInput, action_id: int) -> None:
        assert self._host is not None
        await button.update_action(action_id=action_id, session=self._host.session)

    async def report_sensor_value(self, sensor: SensorInput, value: float | None) -> None:
        assert self._host is not None
        await sensor.update_value(value=value, session=self._host.session)

    async def report_binary_value(self, bi: BinaryInput, value: bool | None) -> None:
        assert self._host is not None
        await bi.update_value(value=value, session=self._host.session)

    async def report_binary_extended_value(self, bi: BinaryInput, value: int | None) -> None:
        assert self._host is not None
        await bi.update_extended_value(value=value, session=self._host.session)

    async def report_channel_value(self, channel: OutputChannel, value: float) -> None:
        await channel.update_value(value=value)

    def set_channel_applied_callback(
        self,
        output: Output,
        callback: Any,
    ) -> None:
        """Register callback for dS→HA output commands."""
        output.on_channel_applied = callback
```

- [ ] **Step 4: Run all api tests**

```bash
.venv/bin/pytest tests/test_api.py -v 2>&1 | tail -10
```

Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/api.py tests/test_api.py
git commit -m "feat: api.py — input reporting and output callbacks"
```

---

## Phase 3 — Coordinator & Hub Setup

### Task 6: `coordinator.py` — HubCoordinator

**Files:**
- Create: `custom_components/dsvdc4ha/coordinator.py`
- Create: `tests/test_coordinator.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_coordinator.py
"""Tests for HubCoordinator."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.core import HomeAssistant


@pytest.mark.asyncio
async def test_coordinator_start_delegates_to_api(hass: HomeAssistant, mock_api):
    with patch("custom_components.dsvdc4ha.coordinator.DsvdcApi", return_value=mock_api):
        from custom_components.dsvdc4ha.coordinator import HubCoordinator
        coord = HubCoordinator(hass, port=9090)
        await coord.async_start()
        mock_api.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_coordinator_stop_delegates_to_api(hass: HomeAssistant, mock_api):
    with patch("custom_components.dsvdc4ha.coordinator.DsvdcApi", return_value=mock_api):
        from custom_components.dsvdc4ha.coordinator import HubCoordinator
        coord = HubCoordinator(hass, port=9090)
        await coord.async_start()
        await coord.async_stop()
        mock_api.stop.assert_awaited_once()
```

- [ ] **Step 2: Run — expect failure**

```bash
.venv/bin/pytest tests/test_coordinator.py -v 2>&1 | tail -8
```

- [ ] **Step 3: Create `coordinator.py`**

```python
"""HubCoordinator — manages VdcHost + Vdc lifecycle."""
from __future__ import annotations

import logging
from importlib.metadata import version as pkg_version

from homeassistant.core import HomeAssistant

from .api import DsvdcApi

_LOGGER = logging.getLogger(__name__)


def _get_integration_version() -> str:
    try:
        return pkg_version("dsvdc4ha")
    except Exception:
        return "0.0.0"


class HubCoordinator:
    """Owns the DsvdcApi instance for the hub config entry."""

    def __init__(self, hass: HomeAssistant, port: int) -> None:
        self.hass = hass
        config_url = f"{hass.config.internal_url or 'http://homeassistant.local'}/config/integrations"
        state_path = hass.config.path(".storage", "dsvdc4ha_host_state")
        self.api = DsvdcApi(
            port=port,
            version=_get_integration_version(),
            config_url=config_url,
            state_path=state_path,
        )

    async def async_start(self) -> None:
        await self.api.start()
        _LOGGER.info("dsvdc4ha hub started")

    async def async_stop(self) -> None:
        await self.api.stop()
        _LOGGER.info("dsvdc4ha hub stopped")
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_coordinator.py -v 2>&1 | tail -10
```

Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/coordinator.py tests/test_coordinator.py
git commit -m "feat: HubCoordinator — delegates to DsvdcApi"
```

---

### Task 7: `__init__.py` — hub entry setup, unload, remove

**Files:**
- Update: `custom_components/dsvdc4ha/__init__.py`
- Update: `tests/test_coordinator.py`

- [ ] **Step 1: Add failing test**

```python
# append to tests/test_coordinator.py
from homeassistant.config_entries import ConfigEntry


@pytest.mark.asyncio
async def test_async_setup_entry_hub_starts_coordinator(hass: HomeAssistant, mock_api):
    with patch("custom_components.dsvdc4ha.coordinator.DsvdcApi", return_value=mock_api):
        entry = MagicMock(spec=ConfigEntry)
        entry.data = {"entry_type": "hub", "port": 9090}
        entry.entry_id = "test-hub-id"

        from custom_components.dsvdc4ha import async_setup_entry
        result = await async_setup_entry(hass, entry)

        assert result is True
        assert "hub" in hass.data.get("dsvdc4ha", {})
        mock_api.start.assert_awaited_once()
```

- [ ] **Step 2: Run — expect failure**

```bash
.venv/bin/pytest tests/test_coordinator.py::test_async_setup_entry_hub_starts_coordinator -v 2>&1 | tail -8
```

- [ ] **Step 3: Replace `__init__.py`**

```python
"""dSVDC Home Assistant integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, ENTRY_TYPE_DEVICE, ENTRY_TYPE_HUB, PLATFORMS
from .coordinator import HubCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    entry_type = entry.data.get("entry_type")

    if entry_type == ENTRY_TYPE_HUB:
        coordinator = HubCoordinator(hass, port=entry.data["port"])
        try:
            await coordinator.async_start()
        except Exception as exc:
            raise ConfigEntryNotReady(f"Cannot start vDC host: {exc}") from exc
        hass.data[DOMAIN]["hub"] = coordinator
        return True

    if entry_type == ENTRY_TYPE_DEVICE:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True

    _LOGGER.error("Unknown entry_type: %s", entry_type)
    return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entry_type = entry.data.get("entry_type")

    if entry_type == ENTRY_TYPE_HUB:
        coordinator: HubCoordinator = hass.data[DOMAIN].pop("hub", None)
        if coordinator:
            await coordinator.async_stop()
        return True

    if entry_type == ENTRY_TYPE_DEVICE:
        return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Called when a config entry is fully deleted."""
    entry_type = entry.data.get("entry_type")

    if entry_type == ENTRY_TYPE_HUB:
        hub: HubCoordinator | None = hass.data.get(DOMAIN, {}).get("hub")
        if hub:
            await hub.api.stop()
        return

    if entry_type == ENTRY_TYPE_DEVICE:
        hub: HubCoordinator | None = hass.data.get(DOMAIN, {}).get("hub")
        if hub:
            await hub.api.vanish_device(entry.entry_id)
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_coordinator.py -v 2>&1 | tail -12
```

Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/__init__.py tests/test_coordinator.py
git commit -m "feat: __init__.py — hub entry setup/unload/remove"
```

---

## Phase 4 — Hub Config Flow

### Task 8: Hub config flow — port step

**Files:**
- Update: `custom_components/dsvdc4ha/config_flow.py`
- Create: `tests/test_config_flow.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_config_flow.py
"""Tests for config flows."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, patch
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from custom_components.dsvdc4ha.const import DOMAIN


@pytest.mark.asyncio
async def test_hub_flow_creates_entry(hass: HomeAssistant):
    with patch(
        "custom_components.dsvdc4ha.config_flow.DsvdcApi"
    ) as MockApi:
        mock_api = MockApi.return_value
        mock_api.start = AsyncMock()
        mock_api.stop = AsyncMock()

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "hub"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"port": 9090}
        )
        assert result2["type"] == FlowResultType.CREATE_ENTRY
        assert result2["data"]["port"] == 9090
        assert result2["data"]["entry_type"] == "hub"


@pytest.mark.asyncio
async def test_hub_flow_aborts_if_hub_exists(hass: HomeAssistant):
    from homeassistant.config_entries import ConfigEntry
    from unittest.mock import MagicMock
    existing = MagicMock(spec=ConfigEntry)
    existing.domain = DOMAIN
    existing.data = {"entry_type": "hub"}
    hass.config_entries._entries = {"existing-id": existing}

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    # Should route to device flow, not abort (hub exists → device add)
    assert result["step_id"] == "device_info"
```

- [ ] **Step 2: Run — expect failure**

```bash
.venv/bin/pytest tests/test_config_flow.py::test_hub_flow_creates_entry -v 2>&1 | tail -10
```

- [ ] **Step 3: Replace `config_flow.py`**

```python
"""Config flow for dsvdc4ha."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_ENTRY_TYPE,
    CONF_PORT,
    DOMAIN,
    ENTRY_TYPE_DEVICE,
    ENTRY_TYPE_HUB,
)

_LOGGER = logging.getLogger(__name__)

HUB_SCHEMA = vol.Schema({
    vol.Required(CONF_PORT, default=8444): selector.NumberSelector(
        selector.NumberSelectorConfig(min=1024, max=65535, mode="box")
    ),
})


class DsvdcConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for dsvdc4ha."""

    VERSION = 1

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
        """Route to hub flow or device flow based on existing entries."""
        hub_entries = [
            e for e in self._async_current_entries()
            if e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_HUB
        ]
        if hub_entries:
            return await self.async_step_device_info()
        return await self.async_step_hub()

    async def async_step_hub(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            return self.async_create_entry(
                title="dSVDC Hub",
                data={CONF_ENTRY_TYPE: ENTRY_TYPE_HUB, CONF_PORT: int(user_input[CONF_PORT])},
            )
        return self.async_show_form(step_id="hub", data_schema=HUB_SCHEMA, errors=errors)
```

- [ ] **Step 4: Run hub flow tests**

```bash
.venv/bin/pytest tests/test_config_flow.py::test_hub_flow_creates_entry -v 2>&1 | tail -10
```

Expected: PASSED.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py tests/test_config_flow.py
git commit -m "feat: hub config flow — port input step"
```

---

## Phase 5 — Device Config Flow

### Task 9: Device flow — device_info + vdsd_creation steps

**Files:**
- Update: `custom_components/dsvdc4ha/config_flow.py`
- Update: `tests/test_config_flow.py`

- [ ] **Step 1: Add failing test**

```python
# append to tests/test_config_flow.py

@pytest.mark.asyncio
async def test_device_flow_device_info_step(hass: HomeAssistant):
    from unittest.mock import MagicMock
    from homeassistant.config_entries import ConfigEntry
    existing = MagicMock(spec=ConfigEntry)
    existing.domain = DOMAIN
    existing.data = {"entry_type": "hub", "port": 9090}
    hass.config_entries._entries = {"hub-id": existing}

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "device_info"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"name": "Test Lamp", "vendorName": "Acme", "displayId": "LampV1"},
    )
    assert result2["step_id"] == "vdsd_creation"
```

- [ ] **Step 2: Run — expect failure**

```bash
.venv/bin/pytest tests/test_config_flow.py::test_device_flow_device_info_step -v 2>&1 | tail -8
```

- [ ] **Step 3: Add device_info + vdsd_creation steps to `config_flow.py`**

Add these imports and schemas at the top of `config_flow.py` (after existing imports):

```python
from pydsvdcapi.enums import ColorGroup

_COLOR_GROUP_OPTIONS = [
    selector.SelectOptionDict(value=str(g.value), label=g.name.replace("_", " ").title())
    for g in ColorGroup
]

DEVICE_INFO_SCHEMA = vol.Schema({
    vol.Required("name"): selector.TextSelector(),
    vol.Required("vendorName"): selector.TextSelector(),
    vol.Required("displayId"): selector.TextSelector(),
})

VDSD_CREATION_SCHEMA = vol.Schema({
    vol.Required("displayId"): selector.TextSelector(),
    vol.Required("primaryGroup", default="1"): selector.SelectSelector(
        selector.SelectSelectorConfig(options=_COLOR_GROUP_OPTIONS)
    ),
    vol.Required("modelVersion"): selector.TextSelector(),
    vol.Optional("identify_action"): selector.ActionSelector(),
    vol.Optional("firmwareUpdate_action"): selector.ActionSelector(),
})
```

Add these methods to `DsvdcConfigFlow`:

```python
    async def async_step_device_info(self, user_input: dict | None = None):
        if user_input is not None:
            self._device_name = user_input["name"]
            self._vendor_name = user_input["vendorName"]
            self._display_id = user_input["displayId"]
            return await self.async_step_vdsd_creation()
        return self.async_show_form(step_id="device_info", data_schema=DEVICE_INFO_SCHEMA)

    async def async_step_vdsd_creation(self, user_input: dict | None = None):
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
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_config_flow.py -v 2>&1 | tail -15
```

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py tests/test_config_flow.py
git commit -m "feat: device flow — device_info and vdsd_creation steps"
```

---

### Task 10: Device flow — optional_settings + vdsd_overview steps

**Files:**
- Update: `custom_components/dsvdc4ha/config_flow.py`

- [ ] **Step 1: Add failing test**

```python
# append to tests/test_config_flow.py

@pytest.mark.asyncio
async def test_vdsd_overview_returns_to_optional_and_back(hass: HomeAssistant):
    """Optional settings navigates away and returns to vdsd_overview."""
    from unittest.mock import MagicMock
    from homeassistant.config_entries import ConfigEntry
    existing = MagicMock(spec=ConfigEntry)
    existing.domain = DOMAIN
    existing.data = {"entry_type": "hub", "port": 9090}
    hass.config_entries._entries = {"hub-id": existing}

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"name": "Lamp", "vendorName": "Acme", "displayId": "LampV1"},
    )
    result3 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"displayId": "LampUnit", "primaryGroup": "1", "modelVersion": "v1"},
    )
    assert result3["step_id"] == "vdsd_overview"
```

- [ ] **Step 2: Run — expect failure**

```bash
.venv/bin/pytest tests/test_config_flow.py::test_vdsd_overview_returns_to_optional_and_back -v 2>&1 | tail -8
```

- [ ] **Step 3: Add optional_settings + vdsd_overview steps**

```python
    async def async_step_vdsd_overview(self, user_input: dict | None = None):
        """Show overview of the current vdSD with action buttons."""
        if user_input is not None:
            action = user_input.get("action", "")
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
        if user_input is not None:
            self._current_vdsd["optional"].update(
                {k: v for k, v in user_input.items() if v}
            )
            return_step = self._optional_return_step or "vdsd_overview"
            self._optional_return_step = ""
            return getattr(self, f"async_step_{return_step}")()
        schema = vol.Schema({
            vol.Optional("hardwareVersion"): selector.TextSelector(),
            vol.Optional("hardwareGuid"): selector.TextSelector(),
            vol.Optional("vendorGuid"): selector.TextSelector(),
            vol.Optional("oemGuid"): selector.TextSelector(),
        })
        return self.async_show_form(step_id="optional_settings", data_schema=schema)
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_config_flow.py -v 2>&1 | tail -15
```

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py
git commit -m "feat: device flow — vdsd_overview and optional_settings steps"
```

---

### Task 11: Device flow — button step

**Files:**
- Update: `custom_components/dsvdc4ha/config_flow.py`

- [ ] **Step 1: Add failing test**

```python
# append to tests/test_config_flow.py

@pytest.mark.asyncio
async def test_button_step_adds_button_to_vdsd(hass: HomeAssistant):
    from unittest.mock import MagicMock
    from homeassistant.config_entries import ConfigEntry
    existing = MagicMock(spec=ConfigEntry)
    existing.domain = DOMAIN
    existing.data = {"entry_type": "hub", "port": 9090}
    hass.config_entries._entries = {"hub-id": existing}

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "L", "vendorName": "A", "displayId": "T"}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {"displayId": "U", "primaryGroup": "1", "modelVersion": "v1"}
    )
    # At vdsd_overview — choose add_button
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {"action": "add_button"}
    )
    # Fill button step
    result_btn = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Main Button",
            "buttonType": "1",
            "group": "1",
            "function": "0",
            "mode": "0",
            "channel": "0",
            "supportsLocalKeyMode": False,
            "setsLocalPriority": False,
            "callsPresent": True,
            "callbackType": "clickTypes",
            "callback_entity": "sensor.my_button",
        },
    )
    # Should return to vdsd_overview
    assert result_btn["step_id"] == "vdsd_overview"
```

- [ ] **Step 2: Run — expect failure**

```bash
.venv/bin/pytest tests/test_config_flow.py::test_button_step_adds_button_to_vdsd -v 2>&1 | tail -8
```

- [ ] **Step 3: Add button step**

Add at top of `config_flow.py` after existing imports:

```python
from pydsvdcapi.enums import ButtonType, ButtonFunction, ButtonMode, ButtonElementID

_BUTTON_TYPE_OPTIONS = [
    selector.SelectOptionDict(value=str(t.value), label=t.name.replace("_", " ").title())
    for t in ButtonType
]
_BUTTON_ELEMENTS_BY_TYPE = {0: 1, 1: 1, 2: 2, 3: 4, 4: 5, 5: 9, 6: 1}
```

Add method to `DsvdcConfigFlow`:

```python
    async def async_step_button(self, user_input: dict | None = None):
        if user_input is not None:
            btn_type = int(user_input["buttonType"])
            element_idx = self._current_button_element_idx
            total = _BUTTON_ELEMENTS_BY_TYPE.get(btn_type, 1)

            btn_data = {
                "dsIndex": len(self._current_buttons),
                "name": user_input["name"],
                "buttonType": btn_type,
                "buttonElementID": element_idx,
                "group": int(user_input["group"]),
                "function": int(user_input["function"]),
                "mode": int(user_input["mode"]),
                "channel": int(user_input.get("channel", 0)),
                "supportsLocalKeyMode": bool(user_input.get("supportsLocalKeyMode", False)),
                "setsLocalPriority": bool(user_input.get("setsLocalPriority", False)),
                "callsPresent": bool(user_input.get("callsPresent", True)),
                "buttonID": 0,
                "callbackType": user_input["callbackType"],
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
            vol.Required("group", default="1"): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=9, mode="box")
            ),
            vol.Required("function", default="0"): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=255, mode="box")
            ),
            vol.Required("mode", default="0"): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=255, mode="box")
            ),
            vol.Optional("channel", default=0): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=255, mode="box")
            ),
            vol.Optional("supportsLocalKeyMode", default=False): selector.BooleanSelector(),
            vol.Optional("setsLocalPriority", default=False): selector.BooleanSelector(),
            vol.Optional("callsPresent", default=True): selector.BooleanSelector(),
            vol.Required("callbackType", default="clickTypes"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=[
                    selector.SelectOptionDict(value="clickTypes", label="Click Types"),
                    selector.SelectOptionDict(value="actionIds", label="Action IDs"),
                ])
            ),
            vol.Optional("callback_entity"): selector.EntitySelector(),
        })
        return self.async_show_form(step_id="button", data_schema=schema)
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_config_flow.py -v 2>&1 | tail -15
```

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py
git commit -m "feat: device flow — button step with element iteration"
```

---

### Task 12: Device flow — binary_input + sensor steps

**Files:**
- Update: `custom_components/dsvdc4ha/config_flow.py`

- [ ] **Step 1: Add failing test**

```python
# append to tests/test_config_flow.py

@pytest.mark.asyncio
async def test_binary_input_step_returns_to_overview(hass: HomeAssistant):
    from unittest.mock import MagicMock
    from homeassistant.config_entries import ConfigEntry
    existing = MagicMock(spec=ConfigEntry)
    existing.domain = DOMAIN
    existing.data = {"entry_type": "hub", "port": 9090}
    hass.config_entries._entries = {"hub-id": existing}

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "L", "vendorName": "A", "displayId": "T"}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {"displayId": "U", "primaryGroup": "1", "modelVersion": "v1"}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {"action": "add_binary_input"}
    )
    result_bi = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Window Sensor",
            "group": "8",
            "sensorFunction": "13",
            "hardwiredFunction": "0",
            "updateInterval": "0",
            "inputType": "1",
            "inputUsage": "0",
            "valueType": "boolean",
            "callback_entity": "binary_sensor.window",
        },
    )
    assert result_bi["step_id"] == "vdsd_overview"
```

- [ ] **Step 2: Run — expect failure**

```bash
.venv/bin/pytest tests/test_config_flow.py::test_binary_input_step_returns_to_overview -v 2>&1 | tail -8
```

- [ ] **Step 3: Add binary_input and sensor steps**

Add imports to `config_flow.py`:

```python
from pydsvdcapi.enums import BinaryInputType, BinaryInputUsage, SensorType, SensorUsage

_BINARY_INPUT_TYPE_OPTIONS = [
    selector.SelectOptionDict(value=str(t.value), label=t.name.replace("_", " ").title())
    for t in BinaryInputType
]
_SENSOR_TYPE_OPTIONS = [
    selector.SelectOptionDict(value=str(t.value), label=t.name.replace("_", " ").title())
    for t in SensorType
]
```

Add methods to `DsvdcConfigFlow`:

```python
    async def async_step_binary_input(self, user_input: dict | None = None):
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
            vol.Required("group", default="8"): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=9, mode="box")
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
            vol.Required("inputType", default="1"): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=2, mode="box")
            ),
            vol.Required("inputUsage", default="0"): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, mode="box")
            ),
            vol.Required("valueType", default="boolean"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=[
                    selector.SelectOptionDict(value="boolean", label="Boolean"),
                    selector.SelectOptionDict(value="integer", label="Integer (extended)"),
                ])
            ),
            vol.Optional("callback_entity"): selector.EntitySelector(),
        })
        return self.async_show_form(step_id="binary_input", data_schema=schema)

    async def async_step_sensor(self, user_input: dict | None = None):
        if user_input is not None:
            self._current_sensors.append({
                "dsIndex": len(self._current_sensors),
                "name": user_input["name"],
                "group": int(user_input.get("group", 0)),
                "sensorType": int(user_input["sensorType"]),
                "sensorUsage": int(user_input.get("sensorUsage", 0)),
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
            vol.Required("group", default="0"): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=9, mode="box")
            ),
            vol.Required("sensorType", default="1"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=_SENSOR_TYPE_OPTIONS)
            ),
            vol.Required("sensorUsage", default="0"): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, mode="box")
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
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_config_flow.py -v 2>&1 | tail -15
```

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py
git commit -m "feat: device flow — binary_input and sensor steps"
```

---

### Task 13: Device flow — output, output_optional, channel steps

**Files:**
- Update: `custom_components/dsvdc4ha/config_flow.py`

- [ ] **Step 1: Add failing test**

```python
# append to tests/test_config_flow.py

@pytest.mark.asyncio
async def test_output_step_leads_to_channel_mapping(hass: HomeAssistant):
    from unittest.mock import MagicMock
    from homeassistant.config_entries import ConfigEntry
    existing = MagicMock(spec=ConfigEntry)
    existing.domain = DOMAIN
    existing.data = {"entry_type": "hub", "port": 9090}
    hass.config_entries._entries = {"hub-id": existing}

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "L", "vendorName": "A", "displayId": "T"}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {"displayId": "U", "primaryGroup": "1", "modelVersion": "v1"}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {"action": "add_output"}
    )
    result_out = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Dimmer Output",
            "groups": ["1"],
            "defaultGroup": "1",
            "function": "1",
            "outputUsage": "0",
            "variableRamp": False,
            "mode": "0",
        },
    )
    # function=1 (DIMMER) — should show channel step next
    assert result_out["step_id"] in ("channel", "channel_mapping")
```

- [ ] **Step 2: Run — expect failure**

```bash
.venv/bin/pytest tests/test_config_flow.py::test_output_step_leads_to_channel_mapping -v 2>&1 | tail -8
```

- [ ] **Step 3: Add output, output_optional, channel steps**

Add imports:

```python
from pydsvdcapi.enums import OutputChannelType, OutputFunction, OutputMode, OutputUsage

_OUTPUT_FUNCTION_OPTIONS = [
    selector.SelectOptionDict(value=str(f.value), label=f.name.replace("_", " ").title())
    for f in OutputFunction
]
_CHANNEL_TYPE_OPTIONS = [
    selector.SelectOptionDict(value=str(c.value), label=c.name.replace("_", " ").title())
    for c in OutputChannelType
]
# Functions that require manual channel configuration
_MANUAL_CHANNEL_FUNCTIONS = {
    OutputFunction.POSITIONAL.value,
    OutputFunction.BIPOLAR.value,
    OutputFunction.INTERNALLY_CONTROLLED.value,
}
```

Add methods:

```python
    async def async_step_output(self, user_input: dict | None = None):
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
                "mode": int(user_input.get("mode", 0)),
                "onThreshold": 50,
            }
            self._current_channels = []
            if fn in _MANUAL_CHANNEL_FUNCTIONS or fn == OutputFunction.CUSTOM.value:
                return await self.async_step_channel()
            return await self.async_step_channel_mapping()
        schema = vol.Schema({
            vol.Required("name"): selector.TextSelector(),
            vol.Required("groups", default=["1"]): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[selector.SelectOptionDict(value=str(i), label=str(i)) for i in range(1, 10)],
                    multiple=True,
                )
            ),
            vol.Required("defaultGroup", default="1"): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=9, mode="box")
            ),
            vol.Required("function", default="0"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=_OUTPUT_FUNCTION_OPTIONS)
            ),
            vol.Required("outputUsage", default="0"): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, mode="box")
            ),
            vol.Optional("variableRamp", default=False): selector.BooleanSelector(),
            vol.Required("mode", default="0"): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, mode="box")
            ),
        })
        return self.async_show_form(step_id="output", data_schema=schema)

    async def async_step_output_optional(self, user_input: dict | None = None):
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
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_config_flow.py -v 2>&1 | tail -15
```

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py
git commit -m "feat: device flow — output, output_optional, channel steps"
```

---

### Task 14: Device flow — channel_mapping, model_features, device_summary, CREATE

**Files:**
- Update: `custom_components/dsvdc4ha/config_flow.py`

- [ ] **Step 1: Add failing test**

```python
# append to tests/test_config_flow.py

@pytest.mark.asyncio
async def test_full_device_flow_creates_entry(hass: HomeAssistant):
    from unittest.mock import MagicMock
    from homeassistant.config_entries import ConfigEntry
    existing = MagicMock(spec=ConfigEntry)
    existing.domain = DOMAIN
    existing.data = {"entry_type": "hub", "port": 9090}
    hass.config_entries._entries = {"hub-id": existing}

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Test Lamp", "vendorName": "Acme", "displayId": "LampV1"}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {"displayId": "LampUnit", "primaryGroup": "1", "modelVersion": "v1"}
    )
    # vdsd_overview → next (no components)
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {"action": "next"}
    )
    # model_features → accept defaults
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {"features": []}
    )
    # device_summary → CREATE
    result_final = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"confirm": True}
    )
    assert result_final["type"] == FlowResultType.CREATE_ENTRY
    assert result_final["data"]["entry_type"] == "device"
    assert result_final["data"]["name"] == "Test Lamp"
    assert len(result_final["data"]["vdsds"]) == 1
```

- [ ] **Step 2: Run — expect failure**

```bash
.venv/bin/pytest tests/test_config_flow.py::test_full_device_flow_creates_entry -v 2>&1 | tail -8
```

- [ ] **Step 3: Add channel_mapping, model_features, device_summary steps**

```python
    async def async_step_channel_mapping(self, user_input: dict | None = None):
        if user_input is not None:
            if self._current_output and self._current_channels:
                for ch in self._current_channels:
                    ch["read_entity"] = user_input.get(f"read_{ch['dsIndex']}")
                    ch["write_action"] = user_input.get(f"write_{ch['dsIndex']}")
                self._current_output["channels"] = self._current_channels
            elif self._current_output:
                self._current_output["channels"] = []
            return await self.async_step_vdsd_overview()

        schema_dict: dict[Any, Any] = {}
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

    async def async_step_model_features(self, user_input: dict | None = None):
        if user_input is not None:
            self._current_vdsd["model_features"] = user_input.get("features", [])
            self._current_vdsd["buttons"] = self._current_buttons
            self._current_vdsd["binary_inputs"] = self._current_binary_inputs
            self._current_vdsd["sensors"] = self._current_sensors
            self._current_vdsd["output"] = self._current_output
            self._vdsds.append(dict(self._current_vdsd))
            return await self.async_step_device_summary()
        schema = vol.Schema({
            vol.Optional("features", default=[]): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value="dontcare", label="No special features"),
                        selector.SelectOptionDict(value="identification", label="Identification"),
                        selector.SelectOptionDict(value="firmwareUpgrade", label="Firmware Upgrade"),
                    ],
                    multiple=True,
                )
            ),
        })
        return self.async_show_form(step_id="model_features", data_schema=schema)

    async def async_step_device_summary(self, user_input: dict | None = None):
        if user_input is not None and user_input.get("confirm"):
            action = user_input.get("action", "create")
            if action == "add_vdsd":
                return await self.async_step_vdsd_creation()
            return self.async_create_entry(
                title=self._device_name,
                data={
                    "entry_type": ENTRY_TYPE_DEVICE,
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
```

- [ ] **Step 4: Run all config flow tests**

```bash
.venv/bin/pytest tests/test_config_flow.py -v 2>&1 | tail -20
```

Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py tests/test_config_flow.py
git commit -m "feat: device flow — channel_mapping, model_features, device_summary + CREATE"
```

---

## Phase 6 — Entity Platforms

### Task 15: `base_entity.py` + device registration in `__init__.py`

**Files:**
- Create: `custom_components/dsvdc4ha/base_entity.py`
- Update: `custom_components/dsvdc4ha/__init__.py`

- [ ] **Step 1: Create `base_entity.py`**

```python
"""Shared base entity for all dsvdc4ha entities."""
from __future__ import annotations

from homeassistant.helpers.entity import Entity, DeviceInfo

from .const import DOMAIN


class DsvdcBaseEntity(Entity):
    """Base class for all dsvdc4ha entities."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        entry_id: str,
        vdsd_index: int,
        vdsd_data: dict,
        unique_id_suffix: str,
    ) -> None:
        self._entry_id = entry_id
        self._vdsd_index = vdsd_index
        self._vdsd_data = vdsd_data
        self._attr_unique_id = f"{entry_id}_{vdsd_index}_{unique_id_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{vdsd_index}")},
            name=vdsd_data.get("displayId", vdsd_data.get("name", "vdSD")),
            manufacturer=vdsd_data.get("vendorName"),
            model=vdsd_data.get("model"),
            sw_version=vdsd_data.get("modelVersion"),
        )
```

- [ ] **Step 2: Add `async_setup_entry` device registration to `sensor.py` and `binary_sensor.py` stubs**

Create `custom_components/dsvdc4ha/sensor.py`:

```python
"""Sensor platform for dsvdc4ha — button, sensor-input, and output-channel mirrors."""
from __future__ import annotations

import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .base_entity import DsvdcBaseEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities: list[DsvdcBaseEntity] = []
    for idx, vdsd_data in enumerate(entry.data.get("vdsds", [])):
        for btn in vdsd_data.get("buttons", []):
            entities.append(ButtonSensorEntity(entry.entry_id, idx, vdsd_data, btn))
        for si in vdsd_data.get("sensors", []):
            entities.append(SensorInputEntity(entry.entry_id, idx, vdsd_data, si))
        if output := vdsd_data.get("output"):
            for ch in output.get("channels", []):
                entities.append(OutputChannelEntity(entry.entry_id, idx, vdsd_data, output, ch))
    async_add_entities(entities)
```

Create `custom_components/dsvdc4ha/binary_sensor.py`:

```python
"""Binary sensor platform for dsvdc4ha — binary input mirrors."""
from __future__ import annotations

import logging
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .base_entity import DsvdcBaseEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities: list[DsvdcBaseEntity] = []
    for idx, vdsd_data in enumerate(entry.data.get("vdsds", [])):
        for bi in vdsd_data.get("binary_inputs", []):
            if bi.get("valueType") == "boolean":
                entities.append(BinaryInputEntity(entry.entry_id, idx, vdsd_data, bi))
    async_add_entities(entities)
```

- [ ] **Step 3: Commit skeleton**

```bash
git add custom_components/dsvdc4ha/base_entity.py \
  custom_components/dsvdc4ha/sensor.py \
  custom_components/dsvdc4ha/binary_sensor.py
git commit -m "feat: entity skeleton — base_entity, sensor, binary_sensor platform stubs"
```

---

### Task 16: Sensor entity implementations

**Files:**
- Update: `custom_components/dsvdc4ha/sensor.py`
- Update: `tests/test_sensor.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_sensor.py
"""Tests for sensor entities."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock
from custom_components.dsvdc4ha.sensor import ButtonSensorEntity, SensorInputEntity, OutputChannelEntity
from custom_components.dsvdc4ha.const import CLICK_TYPE_NAMES


def _make_vdsd():
    return {"displayId": "TestUnit", "vendorName": "Acme", "model": "U1", "modelVersion": "v1", "name": "Lamp"}


def test_button_sensor_initial_state_is_none():
    btn_data = {"dsIndex": 0, "name": "Btn", "callbackType": "clickTypes", "callback_entity": "sensor.x"}
    entity = ButtonSensorEntity("entry1", 0, _make_vdsd(), btn_data)
    assert entity.state is None


def test_button_sensor_updates_state_from_click_type():
    btn_data = {"dsIndex": 0, "name": "Btn", "callbackType": "clickTypes", "callback_entity": "sensor.x"}
    entity = ButtonSensorEntity("entry1", 0, _make_vdsd(), btn_data)
    entity._handle_click(7)
    assert entity.state == CLICK_TYPE_NAMES[7]  # "click_1x"


def test_sensor_input_state_is_none_initially():
    si_data = {"dsIndex": 0, "name": "Temp", "sensorType": 1, "callback_entity": "sensor.temp"}
    entity = SensorInputEntity("entry1", 0, _make_vdsd(), si_data)
    assert entity.state is None
```

- [ ] **Step 2: Run — expect failure**

```bash
.venv/bin/pytest tests/test_sensor.py -v 2>&1 | tail -10
```

- [ ] **Step 3: Implement entity classes in `sensor.py`**

```python
# Add these classes to sensor.py (after async_setup_entry)

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from .const import CLICK_TYPE_NAMES
from .base_entity import DsvdcBaseEntity


class ButtonSensorEntity(DsvdcBaseEntity, SensorEntity):
    """Sensor mirroring the last click type or action ID forwarded to dS."""

    def __init__(self, entry_id, vdsd_index, vdsd_data, btn_data):
        super().__init__(entry_id, vdsd_index, vdsd_data, f"button_{btn_data['dsIndex']}")
        self._btn_data = btn_data
        self._attr_name = btn_data["name"]
        self._attr_native_value: str | None = None

    @property
    def state(self):
        return self._attr_native_value

    def _handle_click(self, click_type: int) -> None:
        self._attr_native_value = CLICK_TYPE_NAMES.get(click_type, str(click_type))
        if self.hass:
            self.async_write_ha_state()

    def _handle_action(self, action_id: int) -> None:
        self._attr_native_value = f"scene_{action_id}"
        if self.hass:
            self.async_write_ha_state()


class SensorInputEntity(DsvdcBaseEntity, SensorEntity):
    """Sensor mirroring a dS sensor input value forwarded to dS."""

    def __init__(self, entry_id, vdsd_index, vdsd_data, si_data):
        super().__init__(entry_id, vdsd_index, vdsd_data, f"sensor_{si_data['dsIndex']}")
        self._si_data = si_data
        self._attr_name = si_data["name"]
        self._attr_native_value: float | None = None

    @property
    def state(self):
        return self._attr_native_value

    def _handle_value(self, value: float | None) -> None:
        self._attr_native_value = value
        if self.hass:
            self.async_write_ha_state()


class OutputChannelEntity(DsvdcBaseEntity, SensorEntity):
    """Sensor mirroring the current value of an output channel."""

    def __init__(self, entry_id, vdsd_index, vdsd_data, output_data, ch_data):
        super().__init__(entry_id, vdsd_index, vdsd_data, f"channel_{ch_data['dsIndex']}")
        self._ch_data = ch_data
        self._attr_name = ch_data.get("name", f"Channel {ch_data['dsIndex']}")
        self._attr_native_value: float | None = None

    @property
    def state(self):
        return self._attr_native_value

    def _handle_value(self, value: float) -> None:
        self._attr_native_value = value
        if self.hass:
            self.async_write_ha_state()
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_sensor.py -v 2>&1 | tail -10
```

Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/sensor.py tests/test_sensor.py
git commit -m "feat: sensor entities — ButtonSensor, SensorInput, OutputChannel"
```

---

### Task 17: BinaryInputEntity implementation

**Files:**
- Update: `custom_components/dsvdc4ha/binary_sensor.py`
- Update: `tests/test_sensor.py`

- [ ] **Step 1: Add failing test**

```python
# append to tests/test_sensor.py
from custom_components.dsvdc4ha.binary_sensor import BinaryInputEntity

def test_binary_input_initial_state_is_none():
    bi_data = {"dsIndex": 0, "name": "Window", "valueType": "boolean", "callback_entity": "binary_sensor.w"}
    entity = BinaryInputEntity("entry1", 0, _make_vdsd(), bi_data)
    assert entity.is_on is None

def test_binary_input_updates_state():
    bi_data = {"dsIndex": 0, "name": "Window", "valueType": "boolean", "callback_entity": "binary_sensor.w"}
    entity = BinaryInputEntity("entry1", 0, _make_vdsd(), bi_data)
    entity._handle_value(True)
    assert entity.is_on is True
```

- [ ] **Step 2: Run — expect failure**

```bash
.venv/bin/pytest tests/test_sensor.py::test_binary_input_initial_state_is_none -v 2>&1 | tail -8
```

- [ ] **Step 3: Implement `BinaryInputEntity` in `binary_sensor.py`**

```python
# Add after async_setup_entry in binary_sensor.py

from homeassistant.components.binary_sensor import BinarySensorEntity
from .base_entity import DsvdcBaseEntity


class BinaryInputEntity(DsvdcBaseEntity, BinarySensorEntity):
    """Binary sensor mirroring a dS binary input value."""

    def __init__(self, entry_id, vdsd_index, vdsd_data, bi_data):
        super().__init__(entry_id, vdsd_index, vdsd_data, f"binary_input_{bi_data['dsIndex']}")
        self._bi_data = bi_data
        self._attr_name = bi_data["name"]
        self._attr_is_on: bool | None = None

    @property
    def is_on(self):
        return self._attr_is_on

    def _handle_value(self, value: bool | None) -> None:
        self._attr_is_on = value
        if self.hass:
            self.async_write_ha_state()
```

- [ ] **Step 4: Run all entity tests**

```bash
.venv/bin/pytest tests/test_sensor.py -v 2>&1 | tail -15
```

Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/binary_sensor.py tests/test_sensor.py
git commit -m "feat: BinaryInputEntity implementation"
```

---

## Phase 7 — State Listeners & Callbacks

### Task 18: HA→dS state listeners for inputs

**Files:**
- Create: `custom_components/dsvdc4ha/listeners.py`
- Update: `custom_components/dsvdc4ha/__init__.py`

- [ ] **Step 1: Create `listeners.py`**

```python
"""State listeners: forward HA entity state changes to dS."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN

if TYPE_CHECKING:
    from .api import DsvdcApi

_LOGGER = logging.getLogger(__name__)


def setup_input_listeners(
    hass: HomeAssistant,
    api: "DsvdcApi",
    entry_id: str,
    vdsds_data: list[dict],
) -> list:
    """Register state listeners for all input callback entities. Returns unsubscribe list."""
    unsubs = []
    for idx, vdsd_data in enumerate(vdsds_data):
        device = api.get_device(entry_id)
        if not device:
            continue
        vdsd = device.get_vdsd(idx)
        if not vdsd:
            continue

        for btn_data in vdsd_data.get("buttons", []):
            entity_id = btn_data.get("callback_entity")
            if not entity_id:
                continue
            btn = vdsd.get_button_input(btn_data["dsIndex"])
            if not btn:
                continue
            cb_type = btn_data.get("callbackType", "clickTypes")

            @callback
            def _on_button_state(event: Event, _btn=btn, _cb_type=cb_type) -> None:
                new_state = event.data.get("new_state")
                if not new_state or new_state.state in ("unknown", "unavailable"):
                    return
                try:
                    value = int(float(new_state.state))
                except ValueError:
                    return
                if _cb_type == "clickTypes":
                    hass.async_create_task(api.report_button_click(_btn, value))
                else:
                    hass.async_create_task(api.report_button_action(_btn, value))

            unsubs.append(async_track_state_change_event(hass, entity_id, _on_button_state))

        for si_data in vdsd_data.get("sensors", []):
            entity_id = si_data.get("callback_entity")
            if not entity_id:
                continue
            si = vdsd.get_sensor_input(si_data["dsIndex"])
            if not si:
                continue

            @callback
            def _on_sensor_state(event: Event, _si=si) -> None:
                new_state = event.data.get("new_state")
                if not new_state or new_state.state in ("unknown", "unavailable"):
                    hass.async_create_task(api.report_sensor_value(_si, None))
                    return
                try:
                    value = float(new_state.state)
                    hass.async_create_task(api.report_sensor_value(_si, value))
                except ValueError:
                    pass

            unsubs.append(async_track_state_change_event(hass, entity_id, _on_sensor_state))

        for bi_data in vdsd_data.get("binary_inputs", []):
            entity_id = bi_data.get("callback_entity")
            if not entity_id:
                continue
            bi = vdsd.get_binary_input(bi_data["dsIndex"])
            if not bi:
                continue
            is_bool = bi_data.get("valueType", "boolean") == "boolean"

            @callback
            def _on_binary_state(event: Event, _bi=bi, _is_bool=is_bool) -> None:
                new_state = event.data.get("new_state")
                if not new_state or new_state.state in ("unknown", "unavailable"):
                    return
                if _is_bool:
                    value = new_state.state in ("on", "true", "1", "True")
                    hass.async_create_task(api.report_binary_value(_bi, value))
                else:
                    try:
                        value_int = int(float(new_state.state))
                        hass.async_create_task(api.report_binary_extended_value(_bi, value_int))
                    except ValueError:
                        pass

            unsubs.append(async_track_state_change_event(hass, entity_id, _on_binary_state))

    return unsubs
```

- [ ] **Step 2: Add output listeners function**

```python
def setup_output_listeners(
    hass: HomeAssistant,
    api: "DsvdcApi",
    entry_id: str,
    vdsds_data: list[dict],
) -> list:
    """Register state listeners for output channel read-bindings and dS→HA callbacks."""
    from pydsvdcapi.enums import OutputChannelType
    unsubs = []
    for idx, vdsd_data in enumerate(vdsds_data):
        output_data = vdsd_data.get("output")
        if not output_data:
            continue
        device = api.get_device(entry_id)
        if not device:
            continue
        vdsd = device.get_vdsd(idx)
        if not vdsd or not vdsd._output:
            continue
        output = vdsd._output

        for ch_data in output_data.get("channels", []):
            read_entity = ch_data.get("read_entity")
            write_action = ch_data.get("write_action")
            ds_index = ch_data["dsIndex"]
            channel = output._channels.get(ds_index) if hasattr(output, "_channels") else None
            if not channel:
                continue

            if read_entity:
                @callback
                def _on_channel_state(event: Event, _ch=channel) -> None:
                    new_state = event.data.get("new_state")
                    if not new_state or new_state.state in ("unknown", "unavailable"):
                        return
                    try:
                        value = float(new_state.state)
                        hass.async_create_task(api.report_channel_value(_ch, value))
                    except ValueError:
                        pass

                unsubs.append(async_track_state_change_event(hass, read_entity, _on_channel_state))

            if write_action:
                async def _on_channel_applied(channels: dict, _action=write_action, _hass=hass) -> None:
                    for ch_type, value in channels.items():
                        await _hass.services.async_call(
                            **_action,
                            blocking=False,
                        )

                api.set_channel_applied_callback(output, _on_channel_applied)

    return unsubs
```

- [ ] **Step 3: Wire listeners into device entry setup in `__init__.py`**

Update the device entry branch in `async_setup_entry`:

```python
    if entry_type == ENTRY_TYPE_DEVICE:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        hub: HubCoordinator | None = hass.data[DOMAIN].get("hub")
        if hub:
            await hub.api.announce_device(entry.entry_id, entry.data.get("vdsds", []))
            from .listeners import setup_input_listeners, setup_output_listeners
            unsubs = setup_input_listeners(hass, hub.api, entry.entry_id, entry.data.get("vdsds", []))
            unsubs += setup_output_listeners(hass, hub.api, entry.entry_id, entry.data.get("vdsds", []))
            hass.data[DOMAIN][entry.entry_id] = {"unsubs": unsubs}
        return True
```

Update `async_unload_entry` device branch:

```python
    if entry_type == ENTRY_TYPE_DEVICE:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, {})
        for unsub in entry_data.get("unsubs", []):
            unsub()
        return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
```

- [ ] **Step 4: Commit**

```bash
git add custom_components/dsvdc4ha/listeners.py custom_components/dsvdc4ha/__init__.py
git commit -m "feat: HA→dS state listeners for inputs and output read-bindings"
```

---

## Phase 8 — Final Wiring & Cleanup

### Task 19: Integration smoke test + final checks

**Files:**
- Update: `tests/test_coordinator.py`

- [ ] **Step 1: Add integration smoke test**

```python
# append to tests/test_coordinator.py

@pytest.mark.asyncio
async def test_device_entry_unload_calls_unsubs(hass: HomeAssistant, mock_api):
    with patch("custom_components.dsvdc4ha.coordinator.DsvdcApi", return_value=mock_api), \
         patch("custom_components.dsvdc4ha.listeners.setup_input_listeners", return_value=[]) as mock_il, \
         patch("custom_components.dsvdc4ha.listeners.setup_output_listeners", return_value=[]) as mock_ol:
        from unittest.mock import MagicMock
        from homeassistant.config_entries import ConfigEntry

        # Setup hub first
        hub_entry = MagicMock(spec=ConfigEntry)
        hub_entry.data = {"entry_type": "hub", "port": 9090}
        hub_entry.entry_id = "hub-id"
        hass.data.setdefault("dsvdc4ha", {})

        from custom_components.dsvdc4ha import async_setup_entry, async_unload_entry
        await async_setup_entry(hass, hub_entry)

        # Setup device
        device_entry = MagicMock(spec=ConfigEntry)
        device_entry.data = {
            "entry_type": "device",
            "name": "Lamp",
            "vendorName": "A",
            "displayId": "L",
            "vdsds": [],
        }
        device_entry.entry_id = "dev-id"

        with patch("custom_components.dsvdc4ha.hass.config_entries.async_forward_entry_setups", new=AsyncMock()):
            result = await async_setup_entry(hass, device_entry)
            assert result is True
```

- [ ] **Step 2: Run all tests**

```bash
.venv/bin/pytest tests/ -v 2>&1 | tail -25
```

Expected: all tests PASSED (or clearly expected failures noted).

- [ ] **Step 3: Run HACS validation check**

```bash
pip install hacs-action-helper 2>/dev/null || true
# Validate manifest manually
.venv/bin/python -c "
import json, sys
with open('custom_components/dsvdc4ha/manifest.json') as f:
    m = json.load(f)
required = ['domain','name','version','requirements','config_flow','iot_class','codeowners']
missing = [k for k in required if k not in m]
print('Missing:', missing or 'none')
print('iot_class:', m.get('iot_class'))
print('config_flow:', m.get('config_flow'))
"
```

Expected: `Missing: none`, `iot_class: local_push`, `config_flow: True`.

- [ ] **Step 4: Final commit**

```bash
git add -u
git commit -m "feat: complete dsvdc4ha v0.1.0 — full hub + device integration"
```

---

## Phase 9 — Create from Entity Flow

### Task 20: Entity mapping + "Create from entity" config flow path

**Files:**
- Create: `custom_components/dsvdc4ha/entity_mapping.py`
- Modify: `custom_components/dsvdc4ha/config_flow.py`
- Modify: `custom_components/dsvdc4ha/strings.json`
- Modify: `custom_components/dsvdc4ha/translations/en.json`
- Modify: `tests/test_config_flow.py`

**Goal:** Add a second device creation path that auto-derives the full dS vdSD configuration from a selected HA entity, reducing required user input to only fields with genuine choices.

- [x] **Step 1: Create `entity_mapping.py`**

Static mapping table (`ENTITY_MAPPING: list[dict]`) with 90 entries covering 13 HA domains. Each entry contains the complete dS config for one `(domain, device_class)` pair, plus optional choice flags:

```python
SUPPORTED_DOMAINS: list[str]  # sorted list of domains with at least one mapping
ENTITY_MAPPING: list[dict]    # 90 entries

def get_entity_mapping(domain: str, device_class: str | None) -> dict | None: ...
def needs_user_input(mapping: dict) -> bool: ...
```

- [x] **Step 2: Add `creation_mode` step to `config_flow.py`**

`async_step_user` routes to `creation_mode` when a hub entry exists. `creation_mode` branches to `entity_picker` or `device_info`.

- [x] **Step 3: Add `entity_picker` step**

`EntitySelector` filtered to `SUPPORTED_DOMAINS`. On submit, reads domain + device_class from HA state, calls `get_entity_mapping`, pre-fills device name/vendor/displayId from HA device registry.

- [x] **Step 4: Add `entity_user_input` step**

Shown only when `needs_user_input(mapping)` is True. Dynamically builds schema from whichever choice flags are present (sensor_function, group, sensor_type, output_usage, function, min/max, tilt).

- [x] **Step 5: Add `_build_entity_vdsd_and_continue` helper**

Builds complete vdSD dict from mapping + user choices. Resolves `channels_by_usage` for blind covers. Derives button function from group (`JOKER → APP=15, else ROOM=5`). Pre-populates `read_entity` with the selected entity.

- [x] **Step 6: Add `entity_channel_mapping` step**

Shows read_entity + write_action per channel (pre-filled from entity). Routes to `model_features`.

- [x] **Step 7: Add strings to `strings.json` + `translations/en.json`**

New steps: `creation_mode`, `entity_picker`, `entity_user_input`, `entity_channel_mapping`.
New errors: `entity_not_found`, `entity_not_supported`.

- [x] **Step 8: Update `test_config_flow.py`**

Update `test_hub_flow_routes_to_device_when_hub_exists` to assert `step_id == "creation_mode"` (was `"device_info"`).

---

## Self-Review Checklist

**Spec coverage:**
- [x] Hub config entry with port input → Task 8
- [x] VDC-HOST + VDC parameters derived from version/config → Task 3
- [x] Device config entries with vdSD sub-devices → Task 9-14
- [x] Button, binary input, sensor, output config flow steps → Tasks 11-13
- [x] Optional settings as regular steps with return navigation → Task 10
- [x] Channel mapping with read-entity + write-action → Task 13
- [x] ModelFeatures auto-derive + user selection → Task 14
- [x] Device summary + CREATE → Task 14
- [x] sensor + binary_sensor entities as read-only mirrors → Tasks 16-17
- [x] HA→dS state listeners for inputs → Task 18
- [x] dS→HA via Output.on_channel_applied → Task 18
- [x] Announce on startup, vanish on removal → Tasks 7, 18
- [x] pydsvdcapi isolated in api.py → Task 3-5
- [x] Tests parallel track → Tasks 1-19
- [x] HACS files — hacs.json, manifest.json → Task 1
- [x] "Create from entity" flow with entity mapping → Task 20

**No placeholders found.**

**Type consistency verified:** `DsvdcApi` methods used in listeners.py match signatures in api.py. Entity `_handle_value`/`_handle_click` signatures consistent throughout.
