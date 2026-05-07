"""dSVDC Home Assistant integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, PLATFORMS
from .coordinator import HubCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    # Pick up the already-running coordinator started during config flow (if present).
    pending = hass.data[DOMAIN].pop("_pending_coordinator", None)
    if pending is not None:
        coordinator = pending
    else:
        coordinator = HubCoordinator(hass, port=entry.data["port"])
        try:
            await coordinator.async_start()
        except Exception as exc:
            raise ConfigEntryNotReady(f"Cannot start vDC host: {exc}") from exc
    hass.data[DOMAIN]["hub"] = coordinator

    # Set up sensor / binary_sensor platforms — they iterate entry.subentries
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register, seed initial values, then announce each device subentry.
    # Order matters: add_device first (builds the object graph), then wire up
    # HA→dS listeners, then seed current HA state so pydsvdcapi's
    # _wait_for_initial_values() is satisfied before announce() is awaited.
    from .listeners import setup_input_listeners, setup_output_listeners, seed_initial_values
    for subentry in entry.subentries.values():
        vdsds = subentry.data.get("vdsds", [])
        coordinator.api.add_device(subentry.subentry_id, vdsds)
        unsubs = setup_input_listeners(hass, coordinator.api, subentry.subentry_id, vdsds)
        unsubs += setup_output_listeners(hass, coordinator.api, subentry.subentry_id, vdsds)
        hass.data[DOMAIN][subentry.subentry_id] = {"unsubs": unsubs}
        await seed_initial_values(hass, coordinator.api, subentry.subentry_id, vdsds)
        await coordinator.api.announce_device(subentry.subentry_id)

    # Reload when subentries change (device added / removed)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data.get(DOMAIN, {})

    for subentry in entry.subentries.values():
        subentry_data = domain_data.pop(subentry.subentry_id, {})
        for unsub in subentry_data.get("unsubs", []):
            unsub()

    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    coordinator: HubCoordinator | None = domain_data.pop("hub", None)
    if coordinator:
        await coordinator.async_stop()

    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Called when the hub config entry is fully deleted."""
    hub: HubCoordinator | None = hass.data.get(DOMAIN, {}).pop("hub", None)
    if hub:
        for subentry in entry.subentries.values():
            await hub.api.vanish_device(subentry.subentry_id)
        await hub.api.stop()
