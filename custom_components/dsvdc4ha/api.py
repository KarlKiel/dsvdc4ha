"""pydsvdcapi wrapper — only file that imports pydsvdcapi directly."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydsvdcapi.binary_input import BinaryInput
from pydsvdcapi.button_input import ButtonInput
from pydsvdcapi.dsuid import DsUid, DsUidNamespace
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
from pydsvdcapi.output import Output
from pydsvdcapi.output_channel import OutputChannel
from pydsvdcapi.sensor_input import SensorInput
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
        if self._host is not None:
            raise RuntimeError("DsvdcApi.start() called while already running")
        host = VdcHost(
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
        vdc = Vdc(
            host=host,
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
        host.add_vdc(vdc)
        await host.start(announce=True)
        self._host = host
        self._vdc = vdc
        _LOGGER.debug("VdcHost started on port %d", self._port)

    async def stop(self) -> None:
        """Stop serving (does not vanish devices — call vanish_device first)."""
        if self._host:
            await self._host.stop()
            self._host = None
            self._vdc = None
            _LOGGER.debug("VdcHost stopped")

    @property
    def vdc(self) -> Vdc | None:
        return self._vdc

    @property
    def host(self) -> VdcHost | None:
        return self._host

    def _build_device_dsuid(self, entry_id: str) -> DsUid:
        return DsUid.from_name_in_space(entry_id, DsUidNamespace.VDC)

    async def announce_device(self, entry_id: str, vdsds_data: list[dict[str, Any]]) -> None:
        """Create a Device + its Vdsds and announce to dS."""
        assert self._vdc is not None and self._host is not None
        assert self._host.session is not None, "VdcHost has no active session"
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
