"""HubCoordinator — manages VdcHost + Vdc lifecycle."""
from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.components.zeroconf import async_get_instance
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .api import DsvdcApi
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class HubCoordinator:
    """Owns the DsvdcApi instance for the hub config entry."""

    def __init__(self, hass: HomeAssistant, port: int) -> None:
        self.hass = hass
        self._port = port
        self.api: DsvdcApi | None = None
        self._connected: bool = False
        self._connection_listeners: list[Callable[[bool], None]] = []

    @property
    def is_connected(self) -> bool:
        """True when the dSM has an active session with this vDC host."""
        return self._connected

    def subscribe_connection_status(
        self, callback: Callable[[bool], None]
    ) -> Callable[[], None]:
        """Register *callback* to be called whenever connection state changes.

        Returns an unsubscribe callable.
        """
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
        version = str(integration.version) if integration.version else "0.0.0"
        config_url = (
            f"{self.hass.config.internal_url}/config/integrations"
            if self.hass.config.internal_url
            else "http://homeassistant.local/config/integrations"
        )
        state_path = self.hass.config.path("dsvdc4ha", "host_state")
        self.api = DsvdcApi(
            port=self._port,
            version=version,
            config_url=config_url,
            state_path=state_path,
        )
        zeroconf = await async_get_instance(self.hass)

        _outer_cb = on_session_ready

        def _on_session_ready() -> None:
            self._fire_connection_status(True)
            if _outer_cb is not None:
                _outer_cb()

        async def _on_disconnect(host, reason) -> None:
            self._fire_connection_status(False)

        await self.api.start(
            zeroconf=zeroconf,
            on_session_ready=_on_session_ready,
            on_disconnect=_on_disconnect,
        )
        _LOGGER.info("dsvdc4ha hub started")

    async def async_stop(self) -> None:
        if self.api:
            await self.api.stop()
        _LOGGER.info("dsvdc4ha hub stopped")
