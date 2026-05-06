"""Config flow for dsvdc4ha."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector as selector_module

from pydsvdcapi.enums import ColorGroup

from .const import (
    CONF_ENTRY_TYPE,
    CONF_PORT,
    DOMAIN,
    ENTRY_TYPE_DEVICE,
    ENTRY_TYPE_HUB,
)

_LOGGER = logging.getLogger(__name__)

_COLOR_GROUP_OPTIONS = [
    selector_module.SelectOptionDict(value=str(g.value), label=g.name.replace("_", " ").title())
    for g in ColorGroup
]

HUB_SCHEMA = vol.Schema({
    vol.Required(CONF_PORT, default=8444): vol.All(vol.Coerce(int), vol.Range(min=1024, max=65535)),
})

DEVICE_INFO_SCHEMA = vol.Schema({
    vol.Required("name"): selector_module.TextSelector(),
    vol.Required("vendorName"): selector_module.TextSelector(),
    vol.Required("displayId"): selector_module.TextSelector(),
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
        """Collect basic device identity."""
        if user_input is not None:
            self._device_name = user_input["name"]
            self._vendor_name = user_input["vendorName"]
            self._display_id = user_input["displayId"]
            return await self.async_step_vdsd_creation()
        return self.async_show_form(step_id="device_info", data_schema=DEVICE_INFO_SCHEMA)

    async def async_step_vdsd_creation(self, user_input: dict | None = None):
        """Collect vDSD-specific settings."""
        if user_input is not None:
            display_id = user_input["displayId"]
            primary_group = int(user_input["primaryGroup"])
            model_version = user_input["modelVersion"]
            self._current_vdsd = {
                "displayId": display_id,
                "primaryGroup": primary_group,
                "model": display_id,
                "vendorName": self._vendor_name,
                "modelVersion": model_version,
                "modelUID": f"{self._vendor_name}{model_version}".replace(" ", ""),
                "name": self._device_name,
                "active": True,
                "identify_action": user_input.get("identify_action"),
                "firmwareUpdate_action": user_input.get("firmwareUpdate_action"),
                "optional": {},
            }
            self._current_buttons = []
            self._current_binary_inputs = []
            self._current_sensors = []
            self._current_output = None
            self._current_channels = []
            return await self.async_step_vdsd_overview()
        schema = vol.Schema({
            vol.Required("displayId"): selector_module.TextSelector(),
            vol.Required("primaryGroup", default="1"): selector_module.SelectSelector(
                selector_module.SelectSelectorConfig(options=_COLOR_GROUP_OPTIONS)
            ),
            vol.Required("modelVersion"): selector_module.TextSelector(),
            vol.Optional("identify_action"): selector_module.ActionSelector(),
            vol.Optional("firmwareUpdate_action"): selector_module.ActionSelector(),
        })
        return self.async_show_form(step_id="vdsd_creation", data_schema=schema)

    async def async_step_vdsd_overview(self, user_input: dict | None = None):
        """Show overview of the current vdSD with action buttons."""
        if user_input is not None:
            action = user_input.get("action", "next")
            if action == "optional_settings":
                self._optional_return_step = "vdsd_overview"
                return await self.async_step_optional_settings()
            if action == "add_button":
                self._current_button_element_idx = 0
                return await self.async_step_button()
            if action == "add_binary_input":
                return await self.async_step_binary_input()
            if action == "add_sensor":
                return await self.async_step_sensor()
            if action == "add_output":
                return await self.async_step_output()
            if action == "next":
                return await self.async_step_model_features()

        buttons_summary = [b["name"] for b in self._current_buttons]
        bi_summary = [b["name"] for b in self._current_binary_inputs]
        si_summary = [s["name"] for s in self._current_sensors]
        has_output = self._current_output is not None

        action_options = [
            selector_module.SelectOptionDict(value="optional_settings", label="Optional Settings"),
            selector_module.SelectOptionDict(value="add_button", label="Add Button"),
            selector_module.SelectOptionDict(value="add_binary_input", label="Add Binary Input"),
            selector_module.SelectOptionDict(value="add_sensor", label="Add Sensor"),
        ]
        if not has_output:
            action_options.append(
                selector_module.SelectOptionDict(value="add_output", label="Add Output")
            )
        action_options.append(selector_module.SelectOptionDict(value="next", label="Next →"))

        schema = vol.Schema({
            vol.Required("action", default="next"): selector_module.SelectSelector(
                selector_module.SelectSelectorConfig(options=action_options)
            ),
        })
        description_placeholders = {
            "vdsd_name": self._current_vdsd.get("displayId", ""),
            "buttons": ", ".join(buttons_summary) or "none",
            "binary_inputs": ", ".join(bi_summary) or "none",
            "sensors": ", ".join(si_summary) or "none",
            "output": self._current_output.get("name", "") if has_output else "none",
        }
        return self.async_show_form(
            step_id="vdsd_overview",
            data_schema=schema,
            description_placeholders=description_placeholders,
        )

    async def async_step_optional_settings(self, user_input: dict | None = None):
        """Collect optional device metadata."""
        if user_input is not None:
            self._current_vdsd["optional"].update(
                {k: v for k, v in user_input.items() if v}
            )
            return_step = self._optional_return_step or "vdsd_overview"
            self._optional_return_step = ""
            return await getattr(self, f"async_step_{return_step}")()
        schema = vol.Schema({
            vol.Optional("hardwareVersion"): selector_module.TextSelector(),
            vol.Optional("hardwareGuid"): selector_module.TextSelector(),
            vol.Optional("vendorGuid"): selector_module.TextSelector(),
            vol.Optional("oemGuid"): selector_module.TextSelector(),
        })
        return self.async_show_form(step_id="optional_settings", data_schema=schema)

    async def async_step_model_features(self, user_input: dict | None = None):
        """Placeholder — implemented in Task 14."""
        return self.async_show_form(step_id="model_features", data_schema=vol.Schema({}))

    async def async_step_button(self, user_input: dict | None = None):
        """Placeholder — implemented in Task 11."""
        return self.async_show_form(step_id="button", data_schema=vol.Schema({}))

    async def async_step_binary_input(self, user_input: dict | None = None):
        """Placeholder — implemented in Task 12."""
        return self.async_show_form(step_id="binary_input", data_schema=vol.Schema({}))

    async def async_step_sensor(self, user_input: dict | None = None):
        """Placeholder — implemented in Task 12."""
        return self.async_show_form(step_id="sensor", data_schema=vol.Schema({}))

    async def async_step_output(self, user_input: dict | None = None):
        """Placeholder — implemented in Task 13."""
        return self.async_show_form(step_id="output", data_schema=vol.Schema({}))
