"""Shared base entity for all dsvdc4ha entities."""
from __future__ import annotations

from homeassistant.helpers.entity import Entity, DeviceInfo

from .const import DOMAIN


class DsvdcBaseEntity(Entity):
    """Base class for all dsvdc4ha entities."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        subentry_id: str,
        vdsd_index: int,
        vdsd_data: dict,
        unique_id_suffix: str,
    ) -> None:
        self._subentry_id = subentry_id
        self._vdsd_index = vdsd_index
        self._vdsd_data = vdsd_data
        self._attr_unique_id = f"{subentry_id}_{vdsd_index}_{unique_id_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{subentry_id}_{vdsd_index}")},
            name=vdsd_data.get("name", vdsd_data.get("displayId", "vdSD")),
            manufacturer=vdsd_data.get("vendorName"),
            model=vdsd_data.get("model"),
            sw_version=vdsd_data.get("modelVersion"),
        )
