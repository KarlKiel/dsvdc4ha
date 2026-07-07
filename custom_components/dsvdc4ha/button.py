"""Button platform for dsvdc4ha — re-announce buttons."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
    hass.data.setdefault(DOMAIN, {})["_add_button_entities"] = async_add_entities
    async_add_entities([ReannounceAllButtonEntity(entry, coordinator)])
    for subentry in entry.subentries.values():
        _add_entities_for_subentry(subentry, async_add_entities, coordinator)


def _add_entities_for_subentry(
    subentry: Any,
    async_add_entities: AddConfigEntryEntitiesCallback,
    coordinator: HubCoordinator,
) -> None:
    entities: list[DsvdcBaseEntity] = []
    for idx, vdsd_data in enumerate(subentry.data.get("vdsds", [])):
        entities.append(
            ReannounceButtonEntity(subentry.subentry_id, idx, vdsd_data, coordinator)
        )
    async_add_entities(entities, config_subentry_id=subentry.subentry_id)


class ReannounceAllButtonEntity(ButtonEntity):
    """Button that forces a full re-announce of VDC and all registered vdSD devices."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_name = "Re-announce all to dSS"

    def __init__(self, entry: ConfigEntry, coordinator: HubCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_reannounce_all"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=VDC_HOST_NAME,
            model=VDC_HOST_MODEL,
            manufacturer=VDC_HOST_VENDOR_NAME,
        )

    async def async_press(self) -> None:
        if self._coordinator.api is None:
            _LOGGER.warning("Re-announce all pressed but API is not running")
            return
        try:
            await self._coordinator.api.force_reannounce_all()
        except Exception:
            _LOGGER.exception("Failed to re-announce all devices")
        else:
            _LOGGER.info("Re-announced VDC and all vdSD devices")


class ReannounceButtonEntity(DsvdcBaseEntity, ButtonEntity):
    """Button that forces re-announcement of this vdSD to dSS."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True

    def __init__(
        self,
        subentry_id: str,
        vdsd_index: int,
        vdsd_data: dict,
        coordinator: HubCoordinator,
    ) -> None:
        super().__init__(subentry_id, vdsd_index, vdsd_data, "reannounce")
        self._coordinator = coordinator
        self._attr_name = "Re-announce to dSS"

    async def async_press(self) -> None:
        if self._coordinator.api is None:
            _LOGGER.warning("Re-announce pressed but API is not running")
            return
        await self._coordinator.api.force_reannounce_device(self._subentry_id)
        _LOGGER.info(
            "Re-announced vdSD %d of subentry %s",
            self._vdsd_index,
            self._subentry_id,
        )
