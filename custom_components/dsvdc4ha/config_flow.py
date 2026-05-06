"""Config flow for dSVDC integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN


STEP_USER_DATA_SCHEMA = vol.Schema({})


class DsvdcConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for dSVDC."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLLING

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(title="dSVDC", data=user_input)

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA)
