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
        hub = hass.data.get(DOMAIN, {}).get("hub")
        if hub:
            await hub.api.vanish_device(entry.entry_id)
