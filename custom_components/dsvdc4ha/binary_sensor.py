"""Binary sensor platform for dsvdc4ha — binary input mirrors."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .base_entity import DsvdcBaseEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities: list[DsvdcBaseEntity] = []
    for idx, vdsd_data in enumerate(entry.data.get("vdsds", [])):
        for bi in vdsd_data.get("binary_inputs", []):
            if bi.get("valueType") == "boolean":
                entities.append(BinaryInputEntity(entry.entry_id, idx, vdsd_data, bi))
    async_add_entities(entities)


class BinaryInputEntity(DsvdcBaseEntity, BinarySensorEntity):
    """Binary sensor mirroring a dS binary input value."""

    def __init__(self, entry_id: str, vdsd_index: int, vdsd_data: dict, bi_data: dict) -> None:
        super().__init__(entry_id, vdsd_index, vdsd_data, f"binary_input_{bi_data['dsIndex']}")
        self._bi_data = bi_data
        self._attr_name = bi_data["name"]
        self._attr_is_on: bool | None = None

    @property
    def is_on(self) -> bool | None:
        return self._attr_is_on

    def _handle_value(self, value: bool | None) -> None:
        self._attr_is_on = value
        if self.hass:
            self.async_write_ha_state()
