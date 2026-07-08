"""Number platform for dsvdc4ha — writable input/output settings."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .base_entity import DsvdcBaseEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# (native_min, native_max, native_step) per setting key.
# Enum-type and bool-type settings are handled by select.py / switch.py and
# are intentionally absent from this table.
_SETTING_RANGES: dict[str, tuple[float, float, float]] = {
    "channel": (0, 255, 1),
    "minPushInterval": (0, 3600, 0.1),
    "changesOnlyInterval": (0, 3600, 0.1),
    "onThreshold": (0, 100, 0.1),
    "minBrightness": (0, 100, 0.1),
    "dimTimeUp": (0, 255, 1),
    "dimTimeDown": (0, 255, 1),
    "dimTimeUpAlt1": (0, 255, 1),
    "dimTimeDownAlt1": (0, 255, 1),
    "dimTimeUpAlt2": (0, 255, 1),
    "dimTimeDownAlt2": (0, 255, 1),
    "openTime": (0, 3600, 0.1),
    "closeTime": (0, 3600, 0.1),
    "angleOpenTime": (0, 3600, 0.1),
    "angleCloseTime": (0, 3600, 0.1),
    "stopDelayTime": (0, 3600, 0.1),
    # vdSD-level writable properties
    "zoneID": (0, 65535, 1),
}
_DEFAULT_RANGE: tuple[float, float, float] = (0, 255, 1)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    hass.data.setdefault(DOMAIN, {})["_add_number_entities"] = async_add_entities


class WritableSettingNumberEntity(DsvdcBaseEntity, NumberEntity):
    """Hidden CONFIG-category number entity for a writable input/output setting."""

    _attr_entity_registry_visible_default = False
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_should_poll = False

    def __init__(
        self,
        subentry_id: str,
        vdsd_index: int,
        vdsd_data: dict,
        uid_suffix: str,
        display_name: str,
        value: Any,
        input_type: str,
        input_idx: int | None,
        setting_key: str,
    ) -> None:
        """Create a writable setting number entity.

        input_type: "bi" | "si" | "btn" | "out"
        input_idx:  index in vdsd.binary_inputs / sensor_inputs / button_inputs;
                    None for output.
        setting_key: the pydsvdcapi setting key, e.g. "group", "minPushInterval"
        """
        super().__init__(subentry_id, vdsd_index, vdsd_data, uid_suffix)
        self._attr_name = display_name
        self._attr_native_value = float(value)
        lo, hi, step = _SETTING_RANGES.get(setting_key, _DEFAULT_RANGE)
        self._attr_native_min_value = lo
        self._attr_native_max_value = hi
        self._attr_native_step = step
        self._input_type = input_type
        self._input_idx = input_idx
        self._setting_key = setting_key

    async def async_set_native_value(self, value: float) -> None:
        coordinator = self.hass.data[DOMAIN].get("hub")
        if coordinator is None or coordinator.api is None:
            return
        device = coordinator.api.get_device(self._subentry_id)
        if device is None:
            return
        vdsd = device.get_vdsd(self._vdsd_index)
        if vdsd is None:
            return

        step = self._attr_native_step
        typed: int | float = int(round(value)) if step == 1.0 else float(value)

        try:
            if self._input_type == "bi":
                inp = vdsd.binary_inputs.get(self._input_idx)
                if inp:
                    inp.apply_settings({self._setting_key: typed})
                    await inp.push_settings()
            elif self._input_type == "si":
                inp = vdsd.sensor_inputs.get(self._input_idx)
                if inp:
                    inp.apply_settings({self._setting_key: typed})
                    await inp.push_settings()
            elif self._input_type == "btn":
                inp = vdsd.button_inputs.get(self._input_idx)
                if inp:
                    inp.apply_settings({self._setting_key: typed})
                    await inp.push_settings()
            elif self._input_type == "out":
                if vdsd.output:
                    vdsd.output.apply_settings({self._setting_key: typed})
                    await vdsd.output.push_settings()
            elif self._input_type == "vdsd":
                # Only "zoneID" is routed here; maps to vdsd.zone_id
                if self._setting_key == "zoneID":
                    vdsd.zone_id = int(round(value))
            await coordinator.api.force_reannounce_device(self._subentry_id)
        except Exception:
            _LOGGER.exception(
                "Failed to write setting %s on %s[%s]",
                self._setting_key,
                self._input_type,
                self._input_idx,
            )
            return

        self._attr_native_value = value
        self.async_write_ha_state()
