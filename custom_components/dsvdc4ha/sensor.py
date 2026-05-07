"""Sensor platform for dsvdc4ha — button, sensor-input, and output-channel mirrors."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .base_entity import DsvdcBaseEntity
from .const import CLICK_TYPE_NAMES, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities: list[DsvdcBaseEntity] = []
    for idx, vdsd_data in enumerate(entry.data.get("vdsds", [])):
        for btn in vdsd_data.get("buttons", []):
            entities.append(ButtonSensorEntity(entry.entry_id, idx, vdsd_data, btn))
        for si in vdsd_data.get("sensors", []):
            entities.append(SensorInputEntity(entry.entry_id, idx, vdsd_data, si))
        if output := vdsd_data.get("output"):
            for ch in output.get("channels", []):
                entities.append(OutputChannelEntity(entry.entry_id, idx, vdsd_data, output, ch))
    async_add_entities(entities)


class ButtonSensorEntity(DsvdcBaseEntity, SensorEntity):
    """Sensor showing the last click type or action ID forwarded to dS."""

    def __init__(self, entry_id: str, vdsd_index: int, vdsd_data: dict, btn_data: dict) -> None:
        super().__init__(entry_id, vdsd_index, vdsd_data, f"button_{btn_data['dsIndex']}")
        self._btn_data = btn_data
        self._attr_name = btn_data["name"]
        self._attr_native_value: str | None = None
        self._source_entity_id: str | None = btn_data.get("callback_entity")
        self._cb_type: str = btn_data.get("callbackType", "clickTypes")

    @property
    def state(self) -> str | None:
        return self._attr_native_value

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if not self._source_entity_id:
            return
        state = self.hass.states.get(self._source_entity_id)
        if state and state.state not in ("unknown", "unavailable"):
            self._update_from_raw(state.state)
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_entity_id, self._handle_source_change
            )
        )

    @callback
    def _handle_source_change(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in ("unknown", "unavailable"):
            return
        self._update_from_raw(new_state.state)
        self.async_write_ha_state()

    def _update_from_raw(self, raw: str) -> None:
        try:
            value = int(float(raw))
        except ValueError:
            return
        if self._cb_type == "clickTypes":
            self._attr_native_value = CLICK_TYPE_NAMES.get(value, str(value))
        else:
            self._attr_native_value = f"scene_{value}"

    def _handle_click(self, click_type: int) -> None:
        self._attr_native_value = CLICK_TYPE_NAMES.get(click_type, str(click_type))
        if self.hass:
            self.async_write_ha_state()

    def _handle_action(self, action_id: int) -> None:
        self._attr_native_value = f"scene_{action_id}"
        if self.hass:
            self.async_write_ha_state()


class SensorInputEntity(DsvdcBaseEntity, SensorEntity):
    """Sensor mirroring a dS sensor input value."""

    def __init__(self, entry_id: str, vdsd_index: int, vdsd_data: dict, si_data: dict) -> None:
        super().__init__(entry_id, vdsd_index, vdsd_data, f"sensor_{si_data['dsIndex']}")
        self._si_data = si_data
        self._attr_name = si_data["name"]
        self._attr_native_value: float | None = None
        self._source_entity_id: str | None = si_data.get("callback_entity")

    @property
    def state(self) -> float | None:
        return self._attr_native_value

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if not self._source_entity_id:
            return
        state = self.hass.states.get(self._source_entity_id)
        if state and state.state not in ("unknown", "unavailable"):
            try:
                self._attr_native_value = float(state.state)
            except ValueError:
                pass
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_entity_id, self._handle_source_change
            )
        )

    @callback
    def _handle_source_change(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in ("unknown", "unavailable"):
            self._attr_native_value = None
        else:
            try:
                self._attr_native_value = float(new_state.state)
            except ValueError:
                return
        self.async_write_ha_state()

    def _handle_value(self, value: float | None) -> None:
        self._attr_native_value = value
        if self.hass:
            self.async_write_ha_state()


class OutputChannelEntity(DsvdcBaseEntity, SensorEntity):
    """Sensor mirroring the current value of an output channel."""

    def __init__(
        self,
        entry_id: str,
        vdsd_index: int,
        vdsd_data: dict,
        output_data: dict,
        ch_data: dict,
    ) -> None:
        super().__init__(entry_id, vdsd_index, vdsd_data, f"channel_{ch_data['dsIndex']}")
        self._ch_data = ch_data
        self._attr_name = ch_data.get("name", f"Channel {ch_data['dsIndex']}")
        self._attr_native_value: float | None = None
        self._source_entity_id: str | None = ch_data.get("read_entity")

    @property
    def state(self) -> float | None:
        return self._attr_native_value

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if not self._source_entity_id:
            return
        state = self.hass.states.get(self._source_entity_id)
        if state and state.state not in ("unknown", "unavailable"):
            try:
                self._attr_native_value = float(state.state)
            except ValueError:
                pass
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_entity_id, self._handle_source_change
            )
        )

    @callback
    def _handle_source_change(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in ("unknown", "unavailable"):
            self._attr_native_value = None
        else:
            try:
                self._attr_native_value = float(new_state.state)
            except ValueError:
                return
        self.async_write_ha_state()

    def _handle_value(self, value: float) -> None:
        self._attr_native_value = value
        if self.hass:
            self.async_write_ha_state()
