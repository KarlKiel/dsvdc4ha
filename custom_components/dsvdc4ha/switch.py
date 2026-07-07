"""Switch platform for dsvdc4ha — bool-type writable settings and active state."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .base_entity import DsvdcBaseEntity
from .const import DOMAIN, VDC_HOST_MODEL, VDC_HOST_NAME, VDC_HOST_VENDOR_NAME
from .coordinator import HubCoordinator

_LOGGER = logging.getLogger(__name__)

# (input_type, setting_key) pairs that map to bool-type settings
BOOL_SETTING_KEYS: set[tuple[str, str]] = {
    ("btn", "setsLocalPriority"),
    ("btn", "callsPresent"),
    ("out", "pushChanges"),
    ("vdsd", "progMode"),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: HubCoordinator = hass.data[DOMAIN]["hub"]
    async_add_entities([VdcActiveSwitchEntity(entry, coordinator)])
    hass.data.setdefault(DOMAIN, {})["_add_switch_entities"] = async_add_entities


class VdcActiveSwitchEntity(SwitchEntity):
    """CONFIG switch to manually mark the VDC (all vdSDs) active or inactive.

    Turning off sends DeviceLifecycleState.INACTIVE for every registered vdSD,
    signalling temporary unavailability (e.g. hardware error).
    Turning on sends DeviceLifecycleState.ACTIVE for all vdSDs.
    """

    _attr_entity_registry_visible_default = False
    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_name = "VDC Active"

    def __init__(self, entry: ConfigEntry, coordinator: HubCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_vdc_active"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=VDC_HOST_NAME,
            model=VDC_HOST_MODEL,
            manufacturer=VDC_HOST_VENDOR_NAME,
        )
        self._attr_is_on = True  # assume active at startup

    async def _set(self, active: bool) -> None:
        if self._coordinator.api is None:
            return
        from pydsvdcapi.enums import DeviceLifecycleState
        lc = DeviceLifecycleState.ACTIVE if active else DeviceLifecycleState.INACTIVE
        try:
            await self._coordinator.api.set_all_vdsds_lifecycle(lc)
        except Exception:
            _LOGGER.exception("Failed to set VDC active=%s", active)
            return
        self._attr_is_on = active
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)


class VdsdActiveSwitchEntity(DsvdcBaseEntity, SwitchEntity):
    """CONFIG switch to manually mark an individual vdSD active or inactive."""

    _attr_entity_registry_visible_default = False
    _attr_entity_category = EntityCategory.CONFIG
    _attr_should_poll = False

    def __init__(
        self,
        subentry_id: str,
        vdsd_index: int,
        vdsd_data: dict,
        value: bool,
    ) -> None:
        super().__init__(subentry_id, vdsd_index, vdsd_data, "vdsd_active")
        self._attr_name = "Active"
        self._attr_is_on = bool(value)

    async def _set(self, active: bool) -> None:
        coordinator = self.hass.data[DOMAIN].get("hub")
        if coordinator is None or coordinator.api is None:
            return
        from pydsvdcapi.enums import DeviceLifecycleState
        lc = DeviceLifecycleState.ACTIVE if active else DeviceLifecycleState.INACTIVE
        try:
            await coordinator.api.set_vdsd_lifecycle(self._subentry_id, self._vdsd_index, lc)
        except Exception:
            _LOGGER.exception(
                "Failed to set vdSD %s[%d] active=%s",
                self._subentry_id, self._vdsd_index, active,
            )
            return
        self._attr_is_on = active
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)


class BoolSettingEntity(DsvdcBaseEntity, SwitchEntity):
    """Hidden CONFIG-category switch entity for a boolean writable setting."""

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
        value: bool | int | None,
        input_type: str,
        input_idx: int | None,
        setting_key: str,
    ) -> None:
        super().__init__(subentry_id, vdsd_index, vdsd_data, uid_suffix)
        self._attr_name = display_name
        self._attr_is_on = bool(value) if value is not None else False
        self._input_type = input_type
        self._input_idx = input_idx
        self._setting_key = setting_key

    async def _write_value(self, new_val: bool) -> None:
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
            if self._input_type == "btn":
                inp = vdsd.button_inputs.get(self._input_idx)
                if inp:
                    inp.apply_settings({self._setting_key: new_val})
                    await inp.push_settings()
            elif self._input_type == "out":
                if vdsd.output:
                    vdsd.output.apply_settings({self._setting_key: new_val})
                    await vdsd.output.push_settings()
            elif self._input_type == "vdsd":
                vdsd.prog_mode = new_val
                await vdsd.push_property({"progMode": new_val})
        except Exception:
            _LOGGER.exception(
                "Failed to write bool setting %s on %s[%s]",
                self._setting_key,
                self._input_type,
                self._input_idx,
            )
            return
        self._attr_is_on = new_val
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._write_value(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._write_value(False)
