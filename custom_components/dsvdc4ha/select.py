"""Select platform for dsvdc4ha — enum-type writable settings."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .base_entity import DsvdcBaseEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# (input_type, setting_key) -> [(label, int_value), ...]
SETTING_OPTIONS: dict[tuple[str, str], list[tuple[str, int]]] = {
    ("bi", "group"): [
        ("Light", 1), ("Shadow", 2), ("Heating", 3), ("Audio", 4),
        ("Video", 5), ("Security", 6), ("Access", 7), ("Joker", 8),
        ("Ventilation", 10), ("Recirculation", 12),
    ],
    ("bi", "sensorFunction"): [
        ("Generic", 0), ("Presence", 1), ("Brightness", 2), ("Presence in Darkness", 3),
        ("Twilight", 4), ("Motion", 5), ("Motion in Darkness", 6), ("Smoke", 7),
        ("Wind", 8), ("Rain", 9), ("Sun Radiation", 10), ("Thermostat", 11),
        ("Battery Low", 12), ("Window Open", 13), ("Door Open", 14),
        ("Window Tilted", 15), ("Garage Door Open", 16), ("Sun Protection", 17),
        ("Frost", 18), ("Heating System Enabled", 19), ("Heating Change Over", 20),
        ("Initialization", 21), ("Malfunction", 22), ("Service", 23),
    ],
    ("si", "group"): [
        ("Joker", 0), ("Light", 1), ("Shadow", 2), ("Climate", 3),
        ("Audio", 4), ("Video", 5), ("Security", 6), ("Access", 7),
    ],
    ("btn", "group"): [
        ("Light", 1), ("Shadow", 2), ("Heating", 3), ("Audio", 4),
        ("Video", 5), ("Security", 6), ("Access", 7), ("Joker", 8),
        ("Cooling", 9), ("Ventilation", 10), ("Window", 11),
        ("Recirculation", 12), ("Temperature", 48),
    ],
    ("btn", "function"): [
        ("Device", 0), ("Area 1", 1), ("Area 2", 2), ("Area 3", 3),
        ("Area 4", 4), ("Room", 5), ("Extended 1", 6), ("Extended 2", 7),
        ("Extended 3", 8), ("Extended 4", 9), ("Extended Area 1", 10),
        ("Extended Area 2", 11), ("Extended Area 3", 12), ("Extended Area 4", 13),
        ("Apartment", 14), ("App", 15),
    ],
    ("btn", "mode"): [
        ("Standard", 0), ("Turbo", 1), ("Switched", 2),
        ("Two-Way Down Paired 1", 5), ("Two-Way Down Paired 2", 6),
        ("Two-Way Down Paired 3", 7), ("Two-Way Down Paired 4", 8),
        ("Two-Way Up Paired 1", 9), ("Two-Way Up Paired 2", 10),
        ("Two-Way Up Paired 3", 11), ("Two-Way Up Paired 4", 12),
        ("Two-Way", 13), ("One-Way", 14),
        ("AKM Standard", 16), ("AKM Inverted", 17),
        ("AKM On Rising Edge", 18), ("AKM On Falling Edge", 19),
        ("AKM Off Rising Edge", 20), ("AKM Off Falling Edge", 21),
        ("AKM Rising Edge", 22), ("AKM Falling Edge", 23),
        ("Heating Pushbutton", 65), ("Deactivated", 255),
    ],
    ("out", "activeGroup"): [
        ("None", 0), ("Lights", 1), ("Blinds", 2), ("Heating", 3),
        ("Audio", 4), ("Video", 5), ("Security", 6), ("Access", 7),
        ("Joker", 8), ("Cooling", 9), ("Ventilation", 10), ("Window", 11),
        ("Recirculation", 12), ("Temperature Control", 48),
        ("Apartment Ventilation", 64), ("Awnings", 65),
        ("Apartment Recirculation", 69),
    ],
    ("out", "mode"): [
        ("Disabled", 0), ("Binary", 1), ("Gradual", 2), ("Default", 127),
    ],
    ("out", "heatingSystemCapability"): [
        ("Heating Only", 1), ("Cooling Only", 2), ("Heating and Cooling", 3),
    ],
    ("out", "heatingSystemType"): [
        ("Undefined", 0), ("Floor Heating", 1), ("Radiator", 2),
        ("Wall Heating", 3), ("Convector Passive", 4),
        ("Convector Active", 5), ("Floor Heating Low Energy", 6),
    ],
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    hass.data.setdefault(DOMAIN, {})["_add_select_entities"] = async_add_entities


class SelectableSettingEntity(DsvdcBaseEntity, SelectEntity):
    """Hidden CONFIG-category select entity for an enum-type writable setting."""

    _attr_entity_registry_visible_default = False
    _attr_entity_category = EntityCategory.CONFIG
    _attr_should_poll = False

    def __init__(
        self,
        subentry_id: str,
        vdsd_index: int,
        vdsd_data: dict,
        uid_suffix: str,
        display_name: str,
        value: int,
        input_type: str,
        input_idx: int | None,
        setting_key: str,
        options: list[tuple[str, int]],
    ) -> None:
        super().__init__(subentry_id, vdsd_index, vdsd_data, uid_suffix)
        self._attr_name = display_name
        self._options_map: dict[str, int] = dict(options)
        self._reverse_map: dict[int, str] = {v: k for k, v in options}
        self._attr_options = [label for label, _ in options]
        self._attr_current_option = self._reverse_map.get(int(value))
        self._input_type = input_type
        self._input_idx = input_idx
        self._setting_key = setting_key

    async def async_select_option(self, option: str) -> None:
        raw = self._options_map.get(option)
        if raw is None:
            return
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
            if self._input_type == "bi":
                inp = vdsd.binary_inputs.get(self._input_idx)
                if inp:
                    inp.apply_settings({self._setting_key: raw})
                    await inp.push_settings()
            elif self._input_type == "si":
                inp = vdsd.sensor_inputs.get(self._input_idx)
                if inp:
                    inp.apply_settings({self._setting_key: raw})
                    await inp.push_settings()
            elif self._input_type == "btn":
                inp = vdsd.button_inputs.get(self._input_idx)
                if inp:
                    inp.apply_settings({self._setting_key: raw})
                    await inp.push_settings()
            elif self._input_type == "out":
                if vdsd.output:
                    vdsd.output.apply_settings({self._setting_key: raw})
                    await vdsd.output.push_settings()
        except Exception:
            _LOGGER.exception(
                "Failed to write setting %s on %s[%s]",
                self._setting_key,
                self._input_type,
                self._input_idx,
            )
            return
        self._attr_current_option = option
        self.async_write_ha_state()
