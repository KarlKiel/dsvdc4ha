"""Text platform for dsvdc4ha — writable vdSD name and VDC name."""
from __future__ import annotations

import logging

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .base_entity import DsvdcBaseEntity
from .const import DOMAIN, VDC_HOST_MODEL, VDC_HOST_NAME, VDC_HOST_VENDOR_NAME
from .coordinator import HubCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: HubCoordinator = hass.data[DOMAIN]["hub"]
    async_add_entities([VdcNameTextEntity(entry, coordinator)])
    hass.data.setdefault(DOMAIN, {})["_add_text_entities"] = async_add_entities


class VdcNameTextEntity(TextEntity):
    """CONFIG text entity to set the VDC's name on the VDC host device."""

    _attr_entity_registry_visible_default = False
    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_name = "VDC Name"
    _attr_native_min = 1
    _attr_native_max = 128

    def __init__(self, entry: ConfigEntry, coordinator: HubCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_vdc_name"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=VDC_HOST_NAME,
            model=VDC_HOST_MODEL,
            manufacturer=VDC_HOST_VENDOR_NAME,
        )
        vdc = coordinator.api.vdc if coordinator.api else None
        self._attr_native_value = vdc.name if vdc else ""

    async def async_set_value(self, value: str) -> None:
        if self._coordinator.api is None or self._coordinator.api.vdc is None:
            return
        vdc = self._coordinator.api.vdc
        vdc.name = value
        if self._coordinator.api.host and self._coordinator.api.host.session:
            try:
                await vdc.announce(self._coordinator.api.host.session)
            except Exception:
                _LOGGER.exception("Failed to re-announce VDC after name change")
        self._attr_native_value = value
        self.async_write_ha_state()


class TextSettingEntity(DsvdcBaseEntity, TextEntity):
    """Hidden CONFIG-category text entity for a writable vdSD name."""

    _attr_entity_registry_visible_default = False
    _attr_entity_category = EntityCategory.CONFIG
    _attr_should_poll = False
    _attr_native_min = 1
    _attr_native_max = 128

    def __init__(
        self,
        subentry_id: str,
        vdsd_index: int,
        vdsd_data: dict,
        uid_suffix: str,
        display_name: str,
        value: str,
    ) -> None:
        super().__init__(subentry_id, vdsd_index, vdsd_data, uid_suffix)
        self._attr_name = display_name
        self._attr_native_value = value

    async def async_set_value(self, value: str) -> None:
        coordinator = self.hass.data[DOMAIN].get("hub")
        if coordinator is None or coordinator.api is None:
            return
        device = coordinator.api.get_device(self._subentry_id)
        if device is None:
            return
        vdsd = device.get_vdsd(self._vdsd_index)
        if vdsd is None:
            return
        try:
            vdsd.name = value
            await coordinator.api.push_vdsd_changes(self._subentry_id)
        except Exception:
            _LOGGER.exception("Failed to set vdSD name on %s", self._subentry_id)
            return

        try:
            # Update HA device registry so the device card title changes immediately.
            identifier = (DOMAIN, f"{self._subentry_id}_{self._vdsd_index}")
            dev_reg = dr.async_get(self.hass)
            ha_device = dev_reg.async_get_device(identifiers={identifier})
            if ha_device:
                dev_reg.async_update_device(ha_device.id, name=value)

            # Persist the new name into subentry data so it survives restart.
            for entry in self.hass.config_entries.async_entries(DOMAIN):
                if self._subentry_id in entry.subentries:
                    subentry = entry.subentries[self._subentry_id]
                    vdsds = list(subentry.data.get("vdsds", []))
                    if self._vdsd_index < len(vdsds):
                        vdsds[self._vdsd_index] = {
                            **vdsds[self._vdsd_index],
                            "name": value,
                            "displayId": value,
                        }
                        self.hass.config_entries.async_update_subentry(
                            entry, subentry,
                            data={**subentry.data, "vdsds": vdsds},
                        )
                    break
        except Exception:
            _LOGGER.exception("Failed to sync name to HA registry/subentry for %s", self._subentry_id)

        self._attr_native_value = value
        self.async_write_ha_state()
