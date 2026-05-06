"""Config flow for dsvdc4ha."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries

from .const import (
    CONF_ENTRY_TYPE,
    CONF_PORT,
    DOMAIN,
    ENTRY_TYPE_DEVICE,
    ENTRY_TYPE_HUB,
)

_LOGGER = logging.getLogger(__name__)

HUB_SCHEMA = vol.Schema({
    vol.Required(CONF_PORT, default=8444): vol.All(vol.Coerce(int), vol.Range(min=1024, max=65535)),
})


class DsvdcConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for dsvdc4ha."""

    VERSION = 1

    def __init__(self) -> None:
        self._device_name: str = ""
        self._vendor_name: str = ""
        self._display_id: str = ""
        self._vdsds: list[dict[str, Any]] = []
        self._current_vdsd: dict[str, Any] = {}
        self._current_buttons: list[dict[str, Any]] = []
        self._current_binary_inputs: list[dict[str, Any]] = []
        self._current_sensors: list[dict[str, Any]] = []
        self._current_output: dict[str, Any] | None = None
        self._current_channels: list[dict[str, Any]] = []
        self._current_button_element_idx: int = 0
        self._current_button_elements_total: int = 1
        self._current_button_type: int = 1
        self._optional_return_step: str = ""

    async def async_step_user(self, user_input: dict | None = None):
        """Route to hub flow or device flow based on existing entries."""
        hub_entries = [
            e for e in self._async_current_entries()
            if e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_HUB
        ]
        if hub_entries:
            return await self.async_step_device_info()
        return await self.async_step_hub()

    async def async_step_hub(self, user_input: dict | None = None):
        """Handle the hub setup step — collect the port number."""
        errors: dict[str, str] = {}
        if user_input is not None:
            return self.async_create_entry(
                title="dSVDC Hub",
                data={CONF_ENTRY_TYPE: ENTRY_TYPE_HUB, CONF_PORT: int(user_input[CONF_PORT])},
            )
        return self.async_show_form(step_id="hub", data_schema=HUB_SCHEMA, errors=errors)

    async def async_step_device_info(self, user_input: dict | None = None):
        """Placeholder — implemented in Task 9."""
        return self.async_show_form(
            step_id="device_info",
            data_schema=vol.Schema({}),
        )
