"""dSVDC Home Assistant integration."""
from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from ._icon_utils import MDI_DOMAIN_ICONS, bundled_icon_b64
from .const import DOMAIN, PLATFORMS
from .coordinator import HubCoordinator

_LOGGER = logging.getLogger(__name__)

_MANIFEST = json.loads((pathlib.Path(__file__).parent / "manifest.json").read_text())
_PYDSVDCAPI_REQ: str = next(
    r for r in _MANIFEST["requirements"] if r.startswith("pydsvdcapi")
)


def _pydsvdcapi_needs_update(requirement: str) -> bool:
    """Return True when the installed pydsvdcapi version doesn't match *requirement*."""
    import importlib.metadata

    if "==" not in requirement:
        return False
    pkg_name, required_version = requirement.split("==", 1)
    try:
        installed = importlib.metadata.version(pkg_name)
        return installed != required_version
    except importlib.metadata.PackageNotFoundError:
        return True


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Ensure the pinned pydsvdcapi version is installed before any entry setup."""
    from homeassistant.util.package import install_package

    if await hass.async_add_executor_job(_pydsvdcapi_needs_update, _PYDSVDCAPI_REQ):
        _LOGGER.info("Installing/updating required package: %s", _PYDSVDCAPI_REQ)
        success = await hass.async_add_executor_job(install_package, _PYDSVDCAPI_REQ)
        if not success:
            _LOGGER.error(
                "Failed to install %s — the integration may not work correctly",
                _PYDSVDCAPI_REQ,
            )
    return True


def _entity_ids_in_vdsd(vdsd_data: dict[str, Any]) -> set[str]:
    """Return all HA entity_ids referenced by a single vdSD config dict."""
    ids: set[str] = set()
    if output := vdsd_data.get("output"):
        for ch in output.get("channels", []):
            if eid := ch.get("read_entity"):
                ids.add(eid)
    for key in ("binary_inputs", "sensors", "buttons"):
        for comp in vdsd_data.get(key, []):
            if eid := comp.get("callback_entity"):
                ids.add(eid)
    return ids


def _build_entity_index(entry: ConfigEntry) -> dict[str, list[tuple[str, int]]]:
    """Map entity_id → [(subentry_id, vdsd_idx), …] for all subentries."""
    index: dict[str, list[tuple[str, int]]] = {}
    for subentry in entry.subentries.values():
        for vdsd_idx, vdsd_data in enumerate(subentry.data.get("vdsds", [])):
            for eid in _entity_ids_in_vdsd(vdsd_data):
                index.setdefault(eid, []).append((subentry.subentry_id, vdsd_idx))
    return index


async def _backfill_missing_icons(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Backfill/upgrade icon_data_b64 for vdSDs missing an icon_slug (old-format entries).

    New-format entries store icon_slug alongside icon_data_b64 so this backfill
    skips them.  Old-format entries (no icon_slug key) are upgraded to the best
    device-class-specific bundled icon available, which covers all supported
    device classes now that the bundled PNG set is complete.
    """
    for subentry in entry.subentries.values():
        vdsds = list(subentry.data.get("vdsds", []))
        updated = False
        for i, vdsd in enumerate(vdsds):
            if "icon_slug" in vdsd:
                continue  # Already processed by new-format config flow
            for eid in _entity_ids_in_vdsd(vdsd):
                state = hass.states.get(eid)
                if state is None:
                    continue
                domain = eid.split(".")[0]
                device_class = state.attributes.get("device_class")
                slug = MDI_DOMAIN_ICONS.get(f"{domain}.{device_class}") if device_class else None
                slug = slug or MDI_DOMAIN_ICONS.get(domain)
                b64 = bundled_icon_b64(slug) if slug else None
                if b64:
                    vdsds[i] = {**vdsd, "icon_data_b64": b64, "icon_slug": slug}
                else:
                    vdsds[i] = {**vdsd, "icon_slug": slug}
                updated = True
                break
        if updated:
            hass.config_entries.async_update_subentry(
                entry, subentry, data={**subentry.data, "vdsds": vdsds}
            )


async def _vanish_deleted_devices(coordinator: HubCoordinator, entry: ConfigEntry) -> None:
    """Vanish devices that were removed from entry.subentries since last setup."""
    if coordinator.api is None:
        return
    current_ids = set(entry.subentries.keys())
    for entry_id in coordinator.api.registered_entry_ids - current_ids:
        try:
            await coordinator.api.vanish_device(entry_id)
        except Exception:
            _LOGGER.warning("Failed to vanish deleted device %s", entry_id, exc_info=True)


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
    await _backfill_missing_icons(hass, entry)
    from homeassistant.helpers import device_registry as dr
    from .listeners import setup_input_listeners, setup_output_listeners, seed_initial_values
    dev_reg = dr.async_get(hass)
    internal_url = (hass.config.internal_url or "http://homeassistant.local:8123").rstrip("/")
    for subentry in entry.subentries.values():
        vdsds = subentry.data.get("vdsds", [])
        coordinator.api.add_device(subentry.subentry_id, vdsds)
        # Patch per-vdSD config URLs to point to their individual HA device pages.
        url_map: dict[tuple[str, int], str] = {}
        for vdsd_idx in range(len(vdsds)):
            identifier = (DOMAIN, f"{subentry.subentry_id}_{vdsd_idx}")
            ha_device = dev_reg.async_get_device(identifiers={identifier})
            if ha_device is not None:
                url_map[(subentry.subentry_id, vdsd_idx)] = (
                    f"{internal_url}/config/devices/device/{ha_device.id}"
                )
        if url_map:
            coordinator.api.patch_vdsd_config_urls(url_map)
        unsubs = setup_input_listeners(hass, coordinator.api, subentry.subentry_id, vdsds)
        unsubs += setup_output_listeners(hass, coordinator.api, subentry.subentry_id, vdsds)
        hass.data[DOMAIN][subentry.subentry_id] = {"unsubs": unsubs}
        await seed_initial_values(hass, coordinator.api, subentry.subentry_id, vdsds)
        await coordinator.api.announce_device(subentry.subentry_id)

    # React to entity enable/disable and deletion in the HA entity registry.
    # Store in domain_data so the subentry delta listener can update it in-place.
    entity_index = _build_entity_index(entry)
    hass.data[DOMAIN]["_entity_index"] = entity_index
    hass.data[DOMAIN]["_known_subentry_ids"] = set(entry.subentries.keys())

    @callback
    def _on_entity_registry_updated(event: Event) -> None:
        action: str = event.data.get("action", "")
        entity_id: str = event.data.get("entity_id", "")
        if entity_id not in entity_index:
            return

        if action == "update" and "disabled_by" in event.data.get("changes", {}):
            reg_entry = er.async_get(hass).async_get(entity_id)
            active = reg_entry is not None and reg_entry.disabled_by is None
            for subentry_id, vdsd_idx in entity_index[entity_id]:
                hass.async_create_task(
                    coordinator.api.set_vdsd_active(subentry_id, vdsd_idx, active)
                )
        elif action == "remove":
            for subentry_id, _ in entity_index.pop(entity_id, []):
                hass.async_create_task(coordinator.api.vanish_device(subentry_id))

    entry.async_on_unload(
        hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, _on_entity_registry_updated)
    )

    entry.async_on_unload(entry.add_update_listener(_async_subentry_update_listener))

    return True


async def _async_subentry_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    domain_data = hass.data.get(DOMAIN, {})
    coordinator: HubCoordinator | None = domain_data.get("hub")
    if coordinator is None or coordinator.api is None:
        return

    known_ids: set[str] = domain_data.get("_known_subentry_ids", set())
    current_ids = set(entry.subentries.keys())
    removed = known_ids - current_ids
    added = current_ids - known_ids

    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    for subentry_id in removed:
        await coordinator.api.vanish_device(subentry_id)
        ent_reg.async_clear_config_subentry(entry.entry_id, subentry_id)
        dev_reg.async_clear_config_subentry(entry.entry_id, subentry_id)
        subentry_data = domain_data.pop(subentry_id, {})
        for unsub in subentry_data.get("unsubs", []):
            unsub()

    if added:
        from .listeners import setup_input_listeners, setup_output_listeners, seed_initial_values
        from . import sensor as _sensor_mod
        from . import binary_sensor as _binary_sensor_mod
        from . import button as _button_mod

        add_sensor = domain_data.get("_add_sensor_entities")
        add_binary = domain_data.get("_add_binary_entities")
        add_button = domain_data.get("_add_button_entities")

        for subentry_id in added:
            subentry = entry.subentries[subentry_id]
            vdsds = subentry.data.get("vdsds", [])
            coordinator.api.add_device(subentry_id, vdsds)
            unsubs = setup_input_listeners(hass, coordinator.api, subentry_id, vdsds)
            unsubs += setup_output_listeners(hass, coordinator.api, subentry_id, vdsds)
            domain_data[subentry_id] = {"unsubs": unsubs}
            await seed_initial_values(hass, coordinator.api, subentry_id, vdsds)
            await coordinator.api.announce_device(subentry_id)
            if add_sensor:
                _sensor_mod._add_entities_for_subentry(subentry, add_sensor)
            if add_binary:
                _binary_sensor_mod._add_entities_for_subentry(subentry, add_binary)
            if add_button:
                _button_mod._add_entities_for_subentry(subentry, add_button, coordinator)

    if removed or added:
        entity_index: dict = domain_data.get("_entity_index", {})
        entity_index.clear()
        entity_index.update(_build_entity_index(entry))
        domain_data["_known_subentry_ids"] = current_ids


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data.get(DOMAIN, {})

    for subentry in entry.subentries.values():
        subentry_data = domain_data.pop(subentry.subentry_id, {})
        for unsub in subentry_data.get("unsubs", []):
            unsub()

    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    coordinator: HubCoordinator | None = domain_data.pop("hub", None)
    if coordinator:
        await _vanish_deleted_devices(coordinator, entry)
        await coordinator.async_stop()

    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Called when the hub config entry is fully deleted."""
    hub: HubCoordinator | None = hass.data.get(DOMAIN, {}).pop("hub", None)
    if hub:
        for subentry in entry.subentries.values():
            await hub.api.vanish_device(subentry.subentry_id)
        await hub.api.stop()
