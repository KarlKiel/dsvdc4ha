"""State listeners: forward HA entity state changes to dS."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN

if TYPE_CHECKING:
    from .api import DsvdcApi

_LOGGER = logging.getLogger(__name__)


def setup_input_listeners(
    hass: HomeAssistant,
    api: "DsvdcApi",
    entry_id: str,
    vdsds_data: list[dict],
) -> list:
    """Register state listeners for all input callback entities. Returns unsubscribe list."""
    unsubs = []
    device = api.get_device(entry_id)
    if not device:
        return unsubs

    for idx, vdsd_data in enumerate(vdsds_data):
        vdsd = device.get_vdsd(idx)
        if not vdsd:
            continue

        # Button listeners
        for btn_data in vdsd_data.get("buttons", []):
            entity_id = btn_data.get("callback_entity")
            if not entity_id:
                continue
            btn = vdsd.get_button_input(btn_data["dsIndex"])
            if not btn:
                continue
            cb_type = btn_data.get("callbackType", "clickTypes")

            @callback
            def _on_button_state(event: Event, _btn=btn, _cb_type=cb_type) -> None:
                new_state = event.data.get("new_state")
                if not new_state or new_state.state in ("unknown", "unavailable"):
                    return
                try:
                    value = int(float(new_state.state))
                except ValueError:
                    return
                if _cb_type == "clickTypes":
                    hass.async_create_task(api.report_button_click(_btn, value))
                else:
                    hass.async_create_task(api.report_button_action(_btn, value))

            unsubs.append(async_track_state_change_event(hass, entity_id, _on_button_state))

        # Sensor listeners
        for si_data in vdsd_data.get("sensors", []):
            entity_id = si_data.get("callback_entity")
            if not entity_id:
                continue
            si = vdsd.get_sensor_input(si_data["dsIndex"])
            if not si:
                continue

            @callback
            def _on_sensor_state(event: Event, _si=si) -> None:
                new_state = event.data.get("new_state")
                if not new_state or new_state.state in ("unknown", "unavailable"):
                    hass.async_create_task(api.report_sensor_value(_si, None))
                    return
                try:
                    value = float(new_state.state)
                    hass.async_create_task(api.report_sensor_value(_si, value))
                except ValueError:
                    pass

            unsubs.append(async_track_state_change_event(hass, entity_id, _on_sensor_state))

        # Binary input listeners
        for bi_data in vdsd_data.get("binary_inputs", []):
            entity_id = bi_data.get("callback_entity")
            if not entity_id:
                continue
            bi = vdsd.get_binary_input(bi_data["dsIndex"])
            if not bi:
                continue
            is_bool = bi_data.get("valueType", "boolean") == "boolean"

            @callback
            def _on_binary_state(event: Event, _bi=bi, _is_bool=is_bool) -> None:
                new_state = event.data.get("new_state")
                if not new_state or new_state.state in ("unknown", "unavailable"):
                    return
                if _is_bool:
                    value = new_state.state in ("on", "true", "1", "True")
                    hass.async_create_task(api.report_binary_value(_bi, value))
                else:
                    try:
                        value_int = int(float(new_state.state))
                        hass.async_create_task(api.report_binary_extended_value(_bi, value_int))
                    except ValueError:
                        pass

            unsubs.append(async_track_state_change_event(hass, entity_id, _on_binary_state))

    return unsubs


def setup_output_listeners(
    hass: HomeAssistant,
    api: "DsvdcApi",
    entry_id: str,
    vdsds_data: list[dict],
) -> list:
    """Register state listeners for output read-bindings and dS->HA callbacks."""
    unsubs = []
    device = api.get_device(entry_id)
    if not device:
        return unsubs

    for idx, vdsd_data in enumerate(vdsds_data):
        output_data = vdsd_data.get("output")
        if not output_data:
            continue
        vdsd = device.get_vdsd(idx)
        if not vdsd:
            continue
        output = vdsd.output
        if not output:
            continue

        for ch_data in output_data.get("channels", []):
            read_entity = ch_data.get("read_entity")
            write_action = ch_data.get("write_action")
            ds_index = ch_data["dsIndex"]
            channel = output.get_channel(ds_index)
            if not channel:
                continue

            if read_entity:
                @callback
                def _on_channel_state(event: Event, _ch=channel) -> None:
                    new_state = event.data.get("new_state")
                    if not new_state or new_state.state in ("unknown", "unavailable"):
                        return
                    try:
                        value = float(new_state.state)
                        hass.async_create_task(api.report_channel_value(_ch, value))
                    except ValueError:
                        pass

                unsubs.append(async_track_state_change_event(hass, read_entity, _on_channel_state))

            if write_action:
                async def _on_channel_applied(
                    _output,
                    channel_updates: dict,
                    _action: dict = write_action,
                ) -> None:
                    """Forward dS->HA output apply to an HA service call."""
                    await hass.services.async_call(
                        **_action,
                        blocking=False,
                    )

                api.set_channel_applied_callback(output, _on_channel_applied)

    return unsubs
