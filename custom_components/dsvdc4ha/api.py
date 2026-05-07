"""pydsvdcapi wrapper — only file that imports pydsvdcapi directly."""
from __future__ import annotations

import asyncio
import logging
import socket
from pathlib import Path
from typing import Any

from zeroconf import ServiceInfo
from zeroconf.asyncio import AsyncZeroconf

_VDC_SERVICE_TYPE = "_ds-vdc._tcp.local."

from pydsvdcapi.binary_input import BinaryInput
from pydsvdcapi.button_input import ButtonInput
from pydsvdcapi.dsuid import DsUid, DsUidNamespace
from pydsvdcapi.enums import (
    BinaryInputGroup,
    BinaryInputType,
    BinaryInputUsage,
    ButtonFunction,
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
        self._icon_path = Path(__file__).parent / "vdc.png"
        self._icon_bytes: bytes | None = None  # loaded in start() off the event loop
        self._port = port
        self._version = version
        self._config_url = config_url
        self._state_path = state_path
        self._host: VdcHost | None = None
        self._vdc: Vdc | None = None
        self._devices: dict[str, Device] = {}  # entry_id → Device

    async def start(self, zeroconf: AsyncZeroconf | None = None) -> None:
        """Create VdcHost + Vdc and start serving.

        Pass the HA shared zeroconf instance (from async_get_instance) so the
        integration does not create a second Zeroconf instance on the network.
        When zeroconf is None the host falls back to its own instance (tests).
        """
        if self._host is not None:
            raise RuntimeError("DsvdcApi.start() called while already running")
        # Load icon bytes and construct VdcHost+Vdc in a thread — both involve
        # synchronous file I/O (read_bytes, persistence.py open) that must not
        # run on the HA event loop.
        if self._icon_path.exists():
            self._icon_bytes = await asyncio.to_thread(self._icon_path.read_bytes)
        host, vdc = await asyncio.to_thread(self._build_host_and_vdc)
        if zeroconf is not None:
            await host.start(announce=False)
            # Assign _host immediately after host.start() so that stop() can
            # always reach host.stop() even if _register_zeroconf() raises.
            self._host = host
            self._vdc = vdc
            await self._register_zeroconf(host, zeroconf)
        else:
            await host.start(announce=True)
            self._host = host
            self._vdc = vdc
        _LOGGER.debug("VdcHost started on port %d", self._port)

    def _purge_corrupted_state_files(self) -> None:
        """Ensure state directory exists and remove any state files that fail YAML validation.

        pydsvdcapi uses yaml.safe_load to read state files.  Any file that
        safe_load rejects (e.g. Python-object tags from old AwesomeVersion
        serialisation, truncated writes, other YAML corruption) is deleted so
        VdcHost starts clean rather than logging repeated load errors.

        Also migrates any legacy file from .storage/dsvdc4ha_host_state to the
        new per-integration directory so existing device state is preserved.
        """
        import yaml  # noqa: PLC0415 — lazy; yaml is always available in HA

        state_path = Path(self._state_path)
        state_path.parent.mkdir(parents=True, exist_ok=True)

        # Migrate legacy file from .storage if present and parseable.
        legacy = state_path.parent.parent / ".storage" / "dsvdc4ha_host_state"
        for src, dst in (
            (legacy, state_path),
            (Path(str(legacy) + ".bak"), Path(str(state_path) + ".bak")),
        ):
            if src.exists() and not dst.exists():
                try:
                    content = src.read_text(errors="replace")
                    yaml.safe_load(content)  # raises yaml.YAMLError if unparseable
                    src.rename(dst)
                    _LOGGER.info("Migrated state file %s → %s", src, dst)
                except yaml.YAMLError:
                    try:
                        src.unlink()
                        _LOGGER.info("Removed unparseable legacy state file %s", src)
                    except OSError:
                        pass
                except OSError:
                    pass

        for path in (state_path, Path(str(state_path) + ".bak")):
            if not path.exists():
                continue
            try:
                content = path.read_text(errors="replace")
                parsed = yaml.safe_load(content)
                if not isinstance(parsed, dict) or not parsed:
                    raise yaml.YAMLError("empty or non-dict state file")
            except yaml.YAMLError:
                try:
                    path.unlink()
                    _LOGGER.info("Removed unusable state file %s", path)
                except OSError:
                    _LOGGER.warning("Could not remove unusable state file %s", path)
            except OSError:
                pass

    def _build_host_and_vdc(self) -> tuple[VdcHost, Vdc]:
        """Construct VdcHost and Vdc synchronously — called via asyncio.to_thread."""
        self._purge_corrupted_state_files()
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
        return host, vdc

    async def _register_zeroconf(self, host: VdcHost, zeroconf: AsyncZeroconf) -> None:
        """Register the vDC-host DNS-SD service using the HA shared Zeroconf instance.

        Replicates VdcHost.announce() but injects the provided zeroconf so that
        host._zeroconf and host._service_info are set — required for pydsvdcapi's
        stop()/deannounce() to clean up correctly.
        """
        hostname = socket.gethostname()
        service_name = f"{host.name} on {hostname}"
        service_info = ServiceInfo(
            type_=_VDC_SERVICE_TYPE,
            name=f"{service_name}.{_VDC_SERVICE_TYPE}",
            port=host._port,
            properties={"dSUID": str(host._dsuid)},
            server=f"{hostname}.local.",
        )
        host._service_info = service_info
        host._zeroconf = zeroconf
        try:
            await zeroconf.async_register_service(service_info)
        except Exception as exc:
            # A previous failed or aborted setup may have left a stale registration
            # with the same name.  Update it in place rather than fighting to remove
            # it first — async_update_service replaces the existing entry.
            if type(exc).__name__ == "NonUniqueNameException":
                _LOGGER.debug(
                    "Zeroconf service '%s' already registered; updating", service_name
                )
                await zeroconf.async_update_service(service_info)
            else:
                raise
        _LOGGER.debug("Registered Zeroconf service '%s'", service_name)

    async def stop(self) -> None:
        """Stop serving (does not vanish devices — call vanish_device first)."""
        if self._host:
            await self._deregister_zeroconf(self._host)
            await self._host.stop()
            self._host = None
            self._vdc = None
            _LOGGER.debug("VdcHost stopped")

    async def _deregister_zeroconf(self, host: VdcHost) -> None:
        """Unregister the DNS-SD service from the shared Zeroconf instance.

        VdcHost.unannounce() calls async_close() on whatever zeroconf it holds,
        which would shut down HA's shared instance and leave the TCP server open
        (port blocked) if the close raises.  We unregister the service ourselves
        and clear the reference so unannounce() becomes a no-op.
        """
        if host._zeroconf is None:
            return
        if host._service_info is not None:
            try:
                await host._zeroconf.async_unregister_service(host._service_info)
            except Exception:
                _LOGGER.debug("Zeroconf unregister raised (ignored)", exc_info=True)
        host._zeroconf = None
        host._service_info = None

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
        # Apply the user's explicit feature selection saved during config flow.
        # derive_model_features() above seeds the set; we then add optional
        # features the user enabled and remove auto-derived ones they deselected.
        if user_features := data.get("model_features"):
            user_set = set(user_features)
            auto_set = set(vdsd.model_features)
            for f in auto_set - user_set:
                vdsd.remove_model_feature(f)
            for f in user_set - auto_set:
                vdsd.add_model_feature(f)
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
        assert self._host is not None
        await channel.update_value(value)

    def set_channel_applied_callback(
        self,
        output: Output,
        callback: Any,
    ) -> None:
        """Register callback for dS→HA output commands."""
        output.on_channel_applied = callback
