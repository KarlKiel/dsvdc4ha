"""HubCoordinator — manages VdcHost + Vdc lifecycle with auto-reconnect."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.components.zeroconf import async_get_instance
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .api import DsvdcApi
from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

_RECONNECT_DELAYS = [5, 15, 30, 60, 120, 300]  # seconds, capped at last value


class HubCoordinator:
    """Owns the DsvdcApi instance for the hub config entry."""

    def __init__(self, hass: HomeAssistant, port: int) -> None:
        self.hass = hass
        self._port = port
        self.api: DsvdcApi | None = None
        self._connected: bool = False
        self._connection_listeners: list[Callable[[bool], None]] = []
        self._reconnect_attempt: int = 0
        self._reconnect_task: asyncio.Task | None = None
        self._entry: Any = None
        self._on_session_ready_ext: Callable | None = None
        self._zeroconf: Any = None
        self._version: str = "0.0.0"

    @property
    def is_connected(self) -> bool:
        """True when the dSM has an active session with this vDC host."""
        return self._connected

    def subscribe_connection_status(
        self, callback: Callable[[bool], None]
    ) -> Callable[[], None]:
        """Register *callback* to be called whenever connection state changes."""
        self._connection_listeners.append(callback)

        def _unsub() -> None:
            try:
                self._connection_listeners.remove(callback)
            except ValueError:
                pass

        return _unsub

    def _fire_connection_status(self, connected: bool) -> None:
        self._connected = connected
        for cb in list(self._connection_listeners):
            try:
                cb(connected)
            except Exception:
                _LOGGER.exception("Error in connection status callback")

    async def async_start(self, on_session_ready=None) -> None:
        integration = await async_get_integration(self.hass, DOMAIN)
        self._version = str(integration.version) if integration.version else "0.0.0"
        config_url = (
            f"{self.hass.config.internal_url}/config/integrations"
            if self.hass.config.internal_url
            else "http://homeassistant.local/config/integrations"
        )
        state_path = self.hass.config.path("dsvdc4ha", "host_state")
        self.api = DsvdcApi(
            port=self._port,
            version=self._version,
            config_url=config_url,
            state_path=state_path,
        )
        self._zeroconf = await async_get_instance(self.hass)
        self._on_session_ready_ext = on_session_ready

        _outer_cb = on_session_ready

        def _on_session_ready() -> None:
            self._reconnect_attempt = 0
            self._fire_connection_status(True)
            if _outer_cb is not None:
                _outer_cb()

        async def _on_disconnect(host, reason) -> None:
            _LOGGER.warning("dSS disconnected: %s — scheduling reconnect", reason)
            self._fire_connection_status(False)
            if self._reconnect_task is None or self._reconnect_task.done():
                self._reconnect_task = self.hass.async_create_task(
                    self._reconnect_with_backoff()
                )

        await self.api.start(
            zeroconf=self._zeroconf,
            on_session_ready=_on_session_ready,
            on_disconnect=_on_disconnect,
        )
        _LOGGER.info("dsvdc4ha hub started")

    async def _reconnect_with_backoff(self) -> None:
        """Stop and restart the API with exponential backoff."""
        delay = _RECONNECT_DELAYS[
            min(self._reconnect_attempt, len(_RECONNECT_DELAYS) - 1)
        ]
        self._reconnect_attempt += 1
        _LOGGER.info("Reconnect attempt %d in %ds…", self._reconnect_attempt, delay)
        await asyncio.sleep(delay)
        await self._do_reconnect()

    async def _do_reconnect(self) -> None:
        """Restart the vDC host and re-register all known devices."""
        try:
            if self.api:
                await self.api.stop()
                self.api = None
            await self.async_start(on_session_ready=self._on_session_ready_ext)
            if self._entry is not None:
                from .listeners import (
                    setup_input_listeners,
                    setup_output_listeners,
                    seed_initial_values,
                )
                from homeassistant.helpers import device_registry as dr
                dev_reg = dr.async_get(self.hass)
                internal_url = (
                    self.hass.config.internal_url or "http://homeassistant.local:8123"
                ).rstrip("/")
                for subentry in self._entry.subentries.values():
                    vdsds = subentry.data.get("vdsds", [])
                    if self.api:
                        self.api.add_device(subentry.subentry_id, vdsds)
                        url_map: dict[tuple[str, int], str] = {}
                        for vdsd_idx in range(len(vdsds)):
                            identifier = (DOMAIN, f"{subentry.subentry_id}_{vdsd_idx}")
                            ha_device = dev_reg.async_get_device(identifiers={identifier})
                            if ha_device is not None:
                                url_map[(subentry.subentry_id, vdsd_idx)] = (
                                    f"{internal_url}/config/devices/device/{ha_device.id}"
                                )
                        if url_map:
                            self.api.patch_vdsd_config_urls(url_map)
                        setup_input_listeners(self.hass, self.api, subentry.subentry_id, vdsds)
                        setup_output_listeners(self.hass, self.api, subentry.subentry_id, vdsds)
                        await seed_initial_values(self.hass, self.api, subentry.subentry_id, vdsds)
                        await self.api.announce_device(subentry.subentry_id)
                from . import _backfill_missing_icons
                await _backfill_missing_icons(self.hass, self._entry)
            _LOGGER.info("dsvdc4ha hub reconnected successfully")
        except Exception:
            _LOGGER.exception("Reconnect failed — will retry")
            self._reconnect_task = self.hass.async_create_task(
                self._reconnect_with_backoff()
            )

    async def async_stop(self) -> None:
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            self._reconnect_task = None
        if self.api:
            await self.api.stop()
        _LOGGER.info("dsvdc4ha hub stopped")
