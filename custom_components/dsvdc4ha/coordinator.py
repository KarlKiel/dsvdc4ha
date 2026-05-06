"""HubCoordinator — manages VdcHost + Vdc lifecycle."""
from __future__ import annotations

import logging
from importlib.metadata import version as pkg_version, PackageNotFoundError

from homeassistant.core import HomeAssistant

from .api import DsvdcApi

_LOGGER = logging.getLogger(__name__)


def _get_integration_version() -> str:
    try:
        return pkg_version("dsvdc4ha")
    except PackageNotFoundError:
        return "0.0.0"


class HubCoordinator:
    """Owns the DsvdcApi instance for the hub config entry."""

    def __init__(self, hass: HomeAssistant, port: int) -> None:
        self.hass = hass
        config_url = (
            f"{hass.config.internal_url}/config/integrations"
            if hass.config.internal_url
            else "http://homeassistant.local/config/integrations"
        )
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
