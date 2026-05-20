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

def _light_apply(channel_updates: dict, attrs: dict) -> dict:
    """Translate simultaneous DS channel_updates into one light.turn_on/off call."""
    brightness = channel_updates.get(1)   # BRIGHTNESS  0–100 %
    hue        = channel_updates.get(2)   # HUE         0–360 °
    sat        = channel_updates.get(3)   # SATURATION  0–100 %
    ct         = channel_updates.get(4)   # COLOR_TEMP  100–1000 mired
    cie_x      = channel_updates.get(5)   # CIE_X       0–10000
    cie_y      = channel_updates.get(6)   # CIE_Y       0–10000

    if brightness is not None and brightness <= 0:
        return {"domain": "light", "service": "turn_off", "service_data": {}}

    sd: dict = {}
    if brightness is not None:
        sd["brightness"] = round(brightness * 2.55)

    # Color priority: CIE XY > HS > CT
    if cie_x is not None or cie_y is not None:
        _xy = (attrs.get("xy_color") or (0.3127, 0.3290))
        x = (cie_x if cie_x is not None else _xy[0] * 10000) / 10000
        y = (cie_y if cie_y is not None else _xy[1] * 10000) / 10000
        sd["xy_color"] = (round(x, 4), round(y, 4))
    elif hue is not None or sat is not None:
        _hs = (attrs.get("hs_color") or (0, 0))
        h = hue if hue is not None else _hs[0]
        s = sat if sat is not None else (attrs.get("hs_color") or (0, 100))[1]
        sd["hs_color"] = (h, s)
    elif ct is not None:
        sd["color_temp_kelvin"] = round(1_000_000 / max(ct, 1))

    return {"domain": "light", "service": "turn_on", "service_data": sd}


_SAFE_EVAL_CONTEXT: dict = {
    "__builtins__": {},
    "round": round,
    "float": float,
    "int": int,
    "abs": abs,
    "min": min,
    "max": max,
    "_norm": lambda v, lo, hi: 0.0 if hi == lo else round((v - lo) / (hi - lo) * 100, 1),
    "_denorm": lambda v, lo, hi: lo + v / 100 * (hi - lo),
    "_light_apply": _light_apply,
}


def _eval_push(expr: str, state) -> float:
    """Evaluate a push_expr with entity/attrs in context. Returns float."""
    ctx = dict(_SAFE_EVAL_CONTEXT)
    ctx["entity"] = state
    ctx["attrs"] = state.attributes if state else {}
    return float(eval(expr, ctx))  # noqa: S307


def _eval_apply(expr: str, value: float, state) -> dict:
    """Evaluate an apply_expr with value/entity/attrs in context. Returns HA action dict."""
    ctx = dict(_SAFE_EVAL_CONTEXT)
    ctx["value"] = value
    ctx["entity"] = state
    ctx["attrs"] = state.attributes if state else {}
    return eval(expr, ctx)  # noqa: S307


def _eval_apply_all(expr: str, channel_updates: dict, state) -> dict:
    """Evaluate an apply_all_expr with channel_updates and current state in context."""
    ctx = {
        **_SAFE_EVAL_CONTEXT,
        "channel_updates": channel_updates,
        "entity": state,
        "attrs": state.attributes if state else {},
    }
    return eval(expr, ctx)  # noqa: S307


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

            if cb_type == "detect_clicks":
                # Auto-detect click type from entity behavior using the timing
                # state machine in ButtonEventTranslator.
                from .button_translator import ButtonEventTranslator

                async def _click_cb(ct: int, _btn=btn) -> None:
                    await api.report_button_click(_btn, ct)

                translator = ButtonEventTranslator(hass, entity_id, _click_cb)
                unsubs.append(translator.setup())
                continue

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


async def seed_initial_values(
    hass: HomeAssistant,
    api: "DsvdcApi",
    entry_id: str,
    vdsds_data: list[dict],
) -> None:
    """Seed initial values into pydsvdcapi components before device announcement.

    pydsvdcapi's _wait_for_initial_values() blocks announce() until every
    SensorInput and OutputChannel has reported at least one value.  We push
    the current HA state (or a safe default) with session=None so the flag is
    set before announce() is awaited, avoiding the 61-second timeout.
    """
    device = api.get_device(entry_id)
    if not device:
        return
    for idx, vdsd_data in enumerate(vdsds_data):
        vdsd = device.get_vdsd(idx)
        if not vdsd:
            continue
        for si_data in vdsd_data.get("sensors", []):
            si = vdsd.get_sensor_input(si_data["dsIndex"])
            if not si:
                continue
            value: float | None = None
            if entity_id := si_data.get("callback_entity"):
                state = hass.states.get(entity_id)
                if state and state.state not in ("unknown", "unavailable"):
                    try:
                        value = float(state.state)
                    except ValueError:
                        pass
            if value is None:
                value = si.min_value
            await si.update_value(value=value, session=None)
        for bi_data in vdsd_data.get("binary_inputs", []):
            bi = vdsd.get_binary_input(bi_data["dsIndex"])
            if not bi:
                continue
            entity_id = bi_data.get("callback_entity")
            if not entity_id:
                continue
            state = hass.states.get(entity_id)
            if not state or state.state in ("unknown", "unavailable"):
                continue
            is_bool = bi_data.get("valueType", "boolean") == "boolean"
            if is_bool:
                await bi.update_value(state.state in ("on", "true", "1", "True"), session=None)
            else:
                try:
                    await bi.update_extended_value(int(float(state.state)), session=None)
                except ValueError:
                    pass

        output_data = vdsd_data.get("output")
        if not output_data or not vdsd.output:
            continue
        for ch_data in output_data.get("channels", []):
            ch = vdsd.output.get_channel(ch_data["dsIndex"])
            if not ch:
                continue
            ch_value: float = 0.0
            if entity_id := ch_data.get("read_entity"):
                state = hass.states.get(entity_id)
                if state and state.state not in ("unknown", "unavailable"):
                    push_expr = ch_data.get("push_expr")
                    if push_expr:
                        try:
                            ch_value = _eval_push(push_expr, state)
                        except Exception:
                            _LOGGER.warning("push_expr eval failed during seed: %s", push_expr, exc_info=True)
                    else:
                        try:
                            ch_value = float(state.state)
                        except ValueError:
                            pass
            await ch.update_value(ch_value)


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
            ds_index = ch_data["dsIndex"]
            channel = output.get_channel(ds_index)
            if not channel:
                continue

            if read_entity:
                push_expr = ch_data.get("push_expr")
                if push_expr:
                    @callback
                    def _on_channel_state_expr(
                        event: Event,
                        _ch=channel,
                        _expr=push_expr,
                    ) -> None:
                        new_state = event.data.get("new_state")
                        if not new_state or new_state.state in ("unknown", "unavailable"):
                            return
                        try:
                            val = _eval_push(_expr, new_state)
                            hass.async_create_task(api.report_channel_value(_ch, val))
                        except Exception:
                            _LOGGER.warning("push_expr eval failed: %s", _expr, exc_info=True)
                    unsubs.append(
                        async_track_state_change_event(hass, read_entity, _on_channel_state_expr)
                    )
                else:
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
                    unsubs.append(
                        async_track_state_change_event(hass, read_entity, _on_channel_state)
                    )

        # Write side: one callback per output handles all channels
        apply_all_expr: str | None = output_data.get("apply_all_expr")
        expr_bindings: list[tuple[int, str, str | None]] = []
        static_action: dict | None = None
        for ch_data in output_data.get("channels", []):
            ch_type = ch_data["channelType"]
            apply_expr = ch_data.get("apply_expr")
            if apply_expr:
                expr_bindings.append((ch_type, apply_expr, ch_data.get("read_entity")))
            elif ch_data.get("write_action"):
                static_action = ch_data["write_action"]

        if apply_all_expr:
            re_id: str | None = next(
                (ch.get("read_entity") for ch in output_data.get("channels", [])
                 if ch.get("read_entity")),
                None,
            )
            async def _on_channel_applied_all(
                _out,
                channel_updates: dict,
                _expr: str = apply_all_expr,
                _re_id: str | None = re_id,
            ) -> None:
                state = hass.states.get(_re_id) if _re_id else None
                try:
                    action = _eval_apply_all(_expr, channel_updates, state)
                    if _re_id and "service_data" in action and "entity_id" not in action["service_data"]:
                        action["service_data"]["entity_id"] = _re_id
                    await hass.services.async_call(**action, blocking=False)
                except Exception:
                    _LOGGER.warning("apply_all_expr eval failed: %s", _expr, exc_info=True)
            api.set_channel_applied_callback(output, _on_channel_applied_all)
        elif expr_bindings:
            async def _on_channel_applied_expr(
                _out,
                channel_updates: dict,
                _bindings: list = expr_bindings,
            ) -> None:
                for ch_type, expr, re_id in _bindings:
                    if ch_type not in channel_updates:
                        continue
                    ch_value = channel_updates[ch_type]
                    state = hass.states.get(re_id) if re_id else None
                    try:
                        action = _eval_apply(expr, ch_value, state)
                        if re_id and "service_data" in action and "entity_id" not in action["service_data"]:
                            action["service_data"]["entity_id"] = re_id
                        await hass.services.async_call(**action, blocking=False)
                    except Exception:
                        _LOGGER.warning("apply_expr eval failed: %s", expr, exc_info=True)
            api.set_channel_applied_callback(output, _on_channel_applied_expr)
        elif static_action:
            async def _on_channel_applied_static(
                _out,
                channel_updates: dict,
                _action: dict = static_action,
            ) -> None:
                await hass.services.async_call(**_action, blocking=False)
            api.set_channel_applied_callback(output, _on_channel_applied_static)

    return unsubs
