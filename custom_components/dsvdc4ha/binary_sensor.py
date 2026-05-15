"""Binary sensor platform for dsvdc4ha — binary input mirrors."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .base_entity import DsvdcBaseEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    hass.data.setdefault(DOMAIN, {})["_add_binary_entities"] = async_add_entities
    for subentry in entry.subentries.values():
        _add_entities_for_subentry(subentry, async_add_entities)


def _add_entities_for_subentry(
    subentry: Any,  # ConfigSubEntry is not yet exported by HA's public API
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    entities: list[DsvdcBaseEntity] = []
    for idx, vdsd_data in enumerate(subentry.data.get("vdsds", [])):
        for bi in vdsd_data.get("binary_inputs", []):
            if bi.get("valueType") == "boolean":
                entities.append(
                    BinaryInputEntity(subentry.subentry_id, idx, vdsd_data, bi)
                )
    async_add_entities(entities, config_subentry_id=subentry.subentry_id)


class BinaryInputEntity(DsvdcBaseEntity, BinarySensorEntity):
    """Binary sensor mirroring a dS binary input value."""

    def __init__(self, subentry_id: str, vdsd_index: int, vdsd_data: dict, bi_data: dict) -> None:
        super().__init__(subentry_id, vdsd_index, vdsd_data, f"binary_input_{bi_data['dsIndex']}")
        self._bi_data = bi_data
        self._attr_name = bi_data["name"]
        self._attr_is_on: bool | None = None
        self._source_entity_id: str | None = bi_data.get("callback_entity")

    @property
    def is_on(self) -> bool | None:
        return self._attr_is_on

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if not self._source_entity_id:
            return
        # Seed initial state from the current state of the source entity.
        state = self.hass.states.get(self._source_entity_id)
        if state and state.state not in ("unknown", "unavailable"):
            self._attr_is_on = state.state in ("on", "true", "1", "True")
        # Subscribe to future changes so the entity stays in sync.
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                self._source_entity_id,
                self._handle_source_change,
            )
        )

    @callback
    def _handle_source_change(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        if new_state.state in ("unknown", "unavailable"):
            self._attr_is_on = None
        else:
            self._attr_is_on = new_state.state in ("on", "true", "1", "True")
        self.async_write_ha_state()

    def _handle_value(self, value: bool | None) -> None:
        self._attr_is_on = value
        if self.hass:
            self.async_write_ha_state()
