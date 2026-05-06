"""pydsvdcapi wrapper — only file that imports pydsvdcapi directly."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydsvdcapi.dsuid import DsUid, DsUidNamespace
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
