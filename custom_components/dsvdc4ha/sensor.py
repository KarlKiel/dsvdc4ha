"""Sensor platform for dsvdc4ha — button, sensor-input, and output-channel mirrors."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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
    """Sensor mirroring the last click type or action ID forwarded to dS."""

    def __init__(self, entry_id: str, vdsd_index: int, vdsd_data: dict, btn_data: dict) -> None:
        super().__init__(entry_id, vdsd_index, vdsd_data, f"button_{btn_data['dsIndex']}")
        self._btn_data = btn_data
        self._attr_name = btn_data["name"]
        self._attr_native_value: str | None = None

    @property
    def state(self) -> str | None:
        return self._attr_native_value

    def _handle_click(self, click_type: int) -> None:
        self._attr_native_value = CLICK_TYPE_NAMES.get(click_type, str(click_type))
        if self.hass:
            self.async_write_ha_state()

    def _handle_action(self, action_id: int) -> None:
        self._attr_native_value = f"scene_{action_id}"
        if self.hass:
            self.async_write_ha_state()


class SensorInputEntity(DsvdcBaseEntity, SensorEntity):
    """Sensor mirroring a dS sensor input value forwarded to dS."""

    def __init__(self, entry_id: str, vdsd_index: int, vdsd_data: dict, si_data: dict) -> None:
        super().__init__(entry_id, vdsd_index, vdsd_data, f"sensor_{si_data['dsIndex']}")
        self._si_data = si_data
        self._attr_name = si_data["name"]
        self._attr_native_value: float | None = None

    @property
    def state(self) -> float | None:
        return self._attr_native_value

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

    @property
    def state(self) -> float | None:
        return self._attr_native_value

    def _handle_value(self, value: float) -> None:
        self._attr_native_value = value
        if self.hass:
            self.async_write_ha_state()
