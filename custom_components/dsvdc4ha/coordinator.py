"""HubCoordinator — manages VdcHost + Vdc lifecycle."""
from __future__ import annotations

import logging

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

    async def async_start(self) -> None:
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
        await self.api.start(zeroconf=zeroconf)
        _LOGGER.info("dsvdc4ha hub started")

    async def async_stop(self) -> None:
        if self.api:
            await self.api.stop()
        _LOGGER.info("dsvdc4ha hub stopped")
