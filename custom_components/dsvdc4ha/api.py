"""pydsvdcapi wrapper — only file that imports pydsvdcapi directly."""
from __future__ import annotations

import asyncio
import base64
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
    ButtonElementID,
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
from pydsvdcapi.output import FUNCTION_CHANNELS, Output
from pydsvdcapi.output_channel import CHANNEL_SPECS, OutputChannel, get_channel_spec
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


def _add_button(vdsd: Vdsd, data: dict[str, Any]) -> None:
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


def _add_binary_input(vdsd: Vdsd, data: dict[str, Any]) -> None:
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


def _add_sensor(vdsd: Vdsd, data: dict[str, Any]) -> None:
    si = SensorInput(
        vdsd=vdsd,
        ds_index=data["dsIndex"],
        name=data["name"],
        sensor_type=SensorType(data["sensorType"]),
        sensor_usage=SensorUsage(data.get("sensorUsage", 0) or 1),
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


def _add_output(vdsd: Vdsd, data: dict[str, Any]) -> None:
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
        open_time=data.get("openTime"),
        close_time=data.get("closeTime"),
        angle_open_time=data.get("angleOpenTime"),
        angle_close_time=data.get("angleCloseTime"),
        stop_delay_time=data.get("stopDelayTime"),
    )
    for ch_data in data.get("channels", []):
        ds_index = ch_data["dsIndex"]
        channel_type = OutputChannelType(ch_data["channelType"])
        in_spec = channel_type in CHANNEL_SPECS
        output.remove_channel(ds_index)
        # For standard spec channels honour spec min/max/resolution (pydsvdcapi 0.8.8+
        # already has the correct values, e.g. 16-bit resolution for shade channels).
        # Only apply stored values for channel types not in CHANNEL_SPECS.
        output.add_channel(
            channel_type,
            ds_index=ds_index,
            min_value=None if in_spec else ch_data.get("min"),
            max_value=None if in_spec else ch_data.get("max"),
            resolution=None if in_spec else ch_data.get("resolution"),
        )
    vdsd.set_output(output)


class _PreviewDevice:
    """Minimal Device stand-in for derive_model_features_for_config."""

    def __init__(self) -> None:
        self.dsuid: DsUid = DsUid.random()

    def _schedule_auto_save(self) -> None:
        pass


def derive_model_features_for_config(vdsd_data: dict[str, Any]) -> set[str]:
    """Return model features pydsvdcapi would auto-derive for a vdSD config dict."""
    vdsd = Vdsd(
        device=_PreviewDevice(),
        primary_group=ColorGroup(vdsd_data.get("primaryGroup", 1)),
        name="preview",
        model="preview",
    )
    for btn_data in vdsd_data.get("buttons", []):
        _add_button(vdsd, btn_data)
    for bi_data in vdsd_data.get("binary_inputs", []):
        _add_binary_input(vdsd, bi_data)
    for si_data in vdsd_data.get("sensors", []):
        _add_sensor(vdsd, si_data)
    if output_data := vdsd_data.get("output"):
        _add_output(vdsd, output_data)
    if vdsd_data.get("identify_action"):
        vdsd.on_identify = lambda _: None
    vdsd.derive_model_features()
    return set(vdsd.model_features)


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
        self._pending_vanish: dict[str, Device] = {}  # entry_id → Device awaiting session to vanish
        self._ever_announced: set[str] = set()

    async def start(
        self,
        zeroconf: AsyncZeroconf | None = None,
        on_session_ready: Any = None,
    ) -> None:
        """Create VdcHost + Vdc and start serving.

        Pass the HA shared zeroconf instance so the integration does not create
        a second Zeroconf instance on the network.  When None the host creates
        its own (acceptable in tests where VdcHost is mocked).

        on_session_ready is an optional zero-argument callable invoked once the
        hello handshake with the DSS completes and all VDCs have been announced.
        It is installed before host.start() to avoid any race with an early DSS
        connection.
        """
        if self._host is not None:
            raise RuntimeError("DsvdcApi.start() called while already running")
        if self._icon_path.exists():
            self._icon_bytes = await asyncio.to_thread(self._icon_path.read_bytes)
        host, vdc = await asyncio.to_thread(self._build_host_and_vdc)
        self._host = host
        self._vdc = vdc
        _cb = on_session_ready

        async def _hooked(session) -> None:
            if self._vdc is None:
                return
            await self._flush_pending_vanish(session)
            # Always announce the VDC container so DSS knows it is connected.
            await self._vdc.announce(session)
            # Announce unknown devices concurrently — DSS may not confirm any single
            # announce until all pending announces are in flight; sequential would deadlock.
            async def _announce_device(entry_id: str, device) -> None:
                try:
                    count = await device.announce(session)
                    if count > 0:
                        self._ever_announced.add(entry_id)
                except Exception:
                    _LOGGER.warning("Failed to announce device %s on session ready", entry_id, exc_info=True)

            unknown = [(eid, dev) for eid, dev in self._devices.items()
                       if eid not in self._ever_announced]
            if unknown:
                await asyncio.gather(*(_announce_device(eid, dev) for eid, dev in unknown))
            if _cb is not None:
                _cb()

        host._on_session_ready = _hooked
        if zeroconf is not None:
            await host.start(announce=False)
            await self._register_zeroconf(host, zeroconf)
        else:
            await host.start(announce=True)
        _LOGGER.debug("VdcHost started on port %d", host._port)

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
                continue
            except OSError:
                continue
            # VdcHost overrides its port with the saved value when the requested
            # port equals DEFAULT_VDC_PORT (8444).  Keep the saved port in sync
            # so the host always binds on the user's chosen port after reinstall.
            vdc_host_state = parsed.get("vdcHost")
            if isinstance(vdc_host_state, dict) and vdc_host_state.get("port") != self._port:
                vdc_host_state["port"] = self._port
                try:
                    path.write_text(yaml.safe_dump(parsed))
                    _LOGGER.debug("Corrected port in state file %s to %d", path, self._port)
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
        # Derive a stable, per-machine Vdc dSUID from the host MAC so that
        # two different HA installations never advertise the same Vdc dSUID.
        vdc_dsuid = DsUid.from_name_in_space(
            f"{VDC_IMPLEMENTATION_ID}:{host.mac}", DsUidNamespace.VDC
        )
        vdc = Vdc(
            host=host,
            dsuid=vdc_dsuid,
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
        """Register DNS-SD with the shared Zeroconf instance and inject it into host.

        Injects host._zeroconf and host._service_info so pydsvdcapi's
        unannounce() (called by stop()) references the shared instance — but
        we clear those references in _deregister_zeroconf before calling
        host.stop() so that unannounce() becomes a no-op and never closes the
        shared instance.
        """
        hostname = socket.gethostname()
        service_name = f"{host.name} on {hostname}"

        # A fresh AsyncZeroconf() auto-discovers local IPs and populates the
        # A record automatically.  HA's shared instance does not — supply the
        # address explicitly so the DSS can reach us.  Route toward the mDNS
        # multicast address to discover which interface would be used; no data
        # is actually sent.
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as _s:
                _s.connect(("224.0.0.251", 5353))
                _local_ip = _s.getsockname()[0]
            addresses = [socket.inet_aton(_local_ip)]
            _LOGGER.debug("Using local IP %s for mDNS A record", _local_ip)
        except OSError:
            addresses = None
            _LOGGER.warning("Could not determine local IP for mDNS A record; DSS may not find the vDC host")

        service_info = ServiceInfo(
            type_=_VDC_SERVICE_TYPE,
            name=f"{service_name}.{_VDC_SERVICE_TYPE}",
            port=host._port,
            properties={"dSUID": str(host._dsuid)},
            server=f"{hostname}.local.",
            addresses=addresses,
        )
        host._service_info = service_info
        host._zeroconf = zeroconf

        # Pre-unregister any stale local entry with this name.  Swallow errors:
        # if it was never registered here (or was already cleaned up) that is fine.
        try:
            await zeroconf.async_unregister_service(service_info)
            _LOGGER.debug("Removed stale Zeroconf service '%s'", service_name)
        except Exception:
            pass

        # allow_name_change=True: if the name is still claimed on the network
        # (e.g. by a cached mDNS record from a previous run, an Avahi daemon,
        # or the still-running previous coordinator), Zeroconf will append a
        # counter suffix to make the name unique.  The DSS discovers vDC hosts
        # by service type (_ds-vdc._tcp), not by the exact name, so the name
        # does not matter for functionality.  Zeroconf updates service_info.name
        # in-place if changed, so _deregister_zeroconf will still use the right name.
        await zeroconf.async_register_service(service_info, allow_name_change=True)
        _LOGGER.debug(
            "Registered Zeroconf service '%s' on port %d", service_name, host._port
        )

    async def stop(self) -> None:
        """Stop serving and send mDNS goodbye so DSS removes devices from its lookup."""
        if self._host:
            await self._deregister_zeroconf(self._host)
            await asyncio.to_thread(self._host.flush)
            await self._host.stop()
            self._host = None
            self._vdc = None
            _LOGGER.debug("VdcHost stopped")

    async def _deregister_zeroconf(self, host: VdcHost) -> None:
        """Unregister DNS-SD from the shared Zeroconf instance and detach.

        Clears host._zeroconf so that pydsvdcapi's unannounce() (called inside
        host.stop()) sees no zeroconf and becomes a no-op — preventing it from
        calling async_close() on HA's shared instance.
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

    def add_device(self, entry_id: str, vdsds_data: list[dict[str, Any]]) -> None:
        """Build and register a Device + its Vdsds without announcing.

        The device is added to the VDC so that pydsvdcapi's _on_session_ready
        auto-announcement picks it up when the DSS connects or reconnects.
        Call announce_device(entry_id) after seeding initial values to trigger
        an immediate announcement when a session is already active.
        """
        assert self._vdc is not None and self._host is not None
        dsuid = self._build_device_dsuid(entry_id)
        device = Device(vdc=self._vdc, dsuid=dsuid)
        for idx, vdsd_data in enumerate(vdsds_data):
            vdsd = self._build_vdsd(device, idx, vdsd_data)
            device.add_vdsd(vdsd)
        self._vdc.add_device(device)
        self._devices[entry_id] = device

    async def announce_device(self, entry_id: str) -> None:
        """Announce a device to DSS if not already known and a session is active."""
        if entry_id in self._ever_announced:
            return  # DSS already has this device; skip to avoid unnecessary disruption
        assert self._host is not None
        if device := self._devices.get(entry_id):
            if self._host.session is not None:
                count = await device.announce(self._host.session)
                if count > 0:
                    self._ever_announced.add(entry_id)

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
            device_icon_16=(
                base64.b64decode(data["icon_data_b64"])
                if data.get("icon_data_b64")
                else self._icon_bytes
            ),
            device_icon_name=data.get("icon_name") or VDC_DEVICE_ICON_NAME,
        )
        for btn_data in data.get("buttons", []):
            _add_button(vdsd, btn_data)
        for bi_data in data.get("binary_inputs", []):
            _add_binary_input(vdsd, bi_data)
        for si_data in data.get("sensors", []):
            _add_sensor(vdsd, si_data)
        if output_data := data.get("output"):
            _add_output(vdsd, output_data)
        vdsd.derive_model_features()
        if user_features := data.get("model_features"):
            user_set = set(user_features)
            auto_set = set(vdsd.model_features)
            for f in auto_set - user_set:
                vdsd.remove_model_feature(f)
            for f in user_set - auto_set:
                try:
                    vdsd.add_model_feature(f)
                except ValueError:
                    _LOGGER.warning(
                        "Ignoring unsupported model feature %r stored in config "
                        "(update device in config flow to remove it)", f,
                    )
        return vdsd

    async def vanish_device(self, entry_id: str) -> None:
        """Vanish and remove a device from dS.

        If no session is active the vanish message cannot be sent now;
        the Device is kept in _pending_vanish and flushed on the next
        session-ready event.
        """
        self._ever_announced.discard(entry_id)
        if device := self._devices.pop(entry_id, None):
            if self._host and self._host.session:
                await device.vanish(self._host.session)
            else:
                self._pending_vanish[entry_id] = device
            if self._vdc:
                dsuid = self._build_device_dsuid(entry_id)
                self._vdc.remove_device(dsuid)

    async def _flush_pending_vanish(self, session: Any) -> None:
        """Send VDC_SEND_VANISH for all devices deleted while session was down."""
        for entry_id in list(self._pending_vanish):
            device = self._pending_vanish.pop(entry_id)
            try:
                await device.vanish(session)
            except Exception:
                _LOGGER.warning("Failed to vanish pending device %s", entry_id, exc_info=True)

    def get_device(self, entry_id: str) -> Device | None:
        return self._devices.get(entry_id)

    @property
    def registered_entry_ids(self) -> set[str]:
        """Set of entry_ids currently tracked by this API."""
        return set(self._devices.keys())

    async def set_vdsd_active(self, entry_id: str, vdsd_idx: int, active: bool) -> None:
        """Set the active flag on a single vdSD and push to DSS if connected.

        If the device is currently announced and a session is live, performs a
        vanish → modify → re-announce cycle so the DSS learns the new state
        immediately.  Otherwise the flag is applied locally and will be
        reflected in the next announcement (e.g. on DSS reconnect).
        """
        device = self._devices.get(entry_id)
        if device is None:
            return

        def _apply(dev: Device, _idx: int = vdsd_idx, _val: bool = active) -> None:
            v = dev.get_vdsd(_idx)
            if v is not None:
                v.active = _val

        if device.is_announced and self._host and self._host.session:
            await device.update(self._host.session, _apply)
        else:
            _apply(device)

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
