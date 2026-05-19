# HA Light → DS Channel Mapping Design

**Date:** 2026-05-19
**Branch:** Completely-re-implement-Light-entity-implementation

---

## Goal

Replace the broken static `device_class`-based light entries in `entity_mapping.py` with a runtime capability derivation system that:

1. Reads `supported_color_modes` from the live HA light entity at config time
2. Selects the correct DS `OutputFunction` and channel set automatically
3. Pushes the correct per-channel DS values when HA state changes (HA → DS)
4. Emits one atomic `light.turn_on` call when DS applies a scene (DS → HA)
5. Exposes one `sensor` entity per DS output channel (already supported by `OutputChannelEntity`)

The design also introduces a general `derive_fn` hook in `entity_mapping.py` that any future entity type with runtime-dependent config can use.

---

## Root cause of the current brokenness

HA's `light` domain has no `device_class` attribute. The config flow calls `get_entity_mapping(domain, device_class)` where `device_class` is always `None` for lights, so every light matches only the `("light", None)` entry (ON/OFF). The `("light", "brightness")`, `("light", "color_temp")`, and `("light", "rgb")` entries are unreachable dead code.

---

## Architecture

### File structure

| File | Change |
|---|---|
| `entity_mapping.py` | Remove 4 broken light entries; add single light entry with `derive_fn`; add `_derive_light_output_config()` + 4 tier builders; add `resolve_entity_mapping()` |
| `config_flow.py` | Replace all `get_entity_mapping()` call sites with `resolve_entity_mapping()` |
| `listeners.py` | Add `_light_apply()` to `_SAFE_EVAL_CONTEXT`; add `apply_all_expr` path in `setup_output_listeners` |
| `sensor.py` | No changes — `OutputChannelEntity` already creates one sensor per channel |
| `tests/test_entity_mapping.py` | New: tests for `_derive_light_output_config` and `resolve_entity_mapping` |
| `tests/test_listeners.py` | New or extended: tests for `apply_all_expr` path and `_light_apply` |
| `tests/test_config_flow.py` | Update: config flow tests for light entity selection |

---

## Component 1: `derive_fn` hook in `entity_mapping.py`

### The hook

Entity mapping entries may carry an optional `derive_fn` field:

```python
"derive_fn": Callable[[str, Any], dict]
# (entity_id: str, state: State | None) -> partial mapping dict
```

When present, `resolve_entity_mapping()` merges the returned dict over the base entry. The `derive_fn` is called only at config time; the result is serialised into the config entry as plain dicts — no callable is stored.

### New wrapper (replaces all `get_entity_mapping()` call sites)

```python
def resolve_entity_mapping(
    entity_id: str,
    state,               # HA State object or None
    domain: str,
    device_class: str | None,
) -> dict | None:
    """Return the fully resolved mapping, calling derive_fn when present."""
    mapping = get_entity_mapping(domain, device_class)
    if mapping is None:
        return None
    if derive_fn := mapping.get("derive_fn"):
        return {**mapping, **derive_fn(entity_id, state)}
    return mapping
```

Backward compatible: entities without `derive_fn` are unchanged.

### Updated light entry (replaces the 4 broken entries)

```python
{
    "domain": "light", "device_class": None,
    "primary_group": ColorGroup.YELLOW,
    "model": "HA Light",       # overridden per-tier by derive_fn
    "model_uid": "ha-light",   # overridden per-tier by derive_fn
    "vendor_name": "Home Assistant",
    "derive_fn": _derive_light_output_config,
}
```

---

## Component 2: Light capability derivation (`entity_mapping.py`)

### Capability tier map

| `supported_color_modes` contains | DS `OutputFunction` | DS channels |
|---|---|---|
| only `onoff`, or unavailable/empty | `ON_OFF` | BRIGHTNESS (binary 0/100) |
| `brightness` or `white` | `DIMMER` | BRIGHTNESS (0–100 %) |
| `color_temp` (no color mode) | `DIMMER_COLOR_TEMP` | BRIGHTNESS + COLOR_TEMP |
| any of `hs`, `xy`, `rgb`, `rgbw`, `rgbww` | `FULL_COLOR_DIMMER` | BRIGHTNESS + HUE + SATURATION + COLOR_TEMP + CIE_X + CIE_Y |

RGBWW lights map to FULL_COLOR_DIMMER: the DS COLOR_TEMP channel controls the warm/cool white balance (HA translates `color_temp` → warm/cool white ratio internally). No DS channel is wasted.

Fallback when `supported_color_modes` is absent (entity unavailable at setup): FULL_COLOR_DIMMER — safest assumption, exposes maximum channels.

### `_derive_light_output_config`

```python
def _derive_light_output_config(entity_id: str, state) -> dict:
    attrs = state.attributes if state else {}
    supported = set(attrs.get("supported_color_modes") or [])

    if supported & {"hs", "xy", "rgb", "rgbw", "rgbww"}:
        return {"model": "HA Light (Full Color)", "model_uid": "ha-light-full-color",
                "output": _full_color_dimmer_output(entity_id)}
    if "color_temp" in supported:
        return {"model": "HA Light (Color Temp)", "model_uid": "ha-light-color-temp",
                "output": _color_temp_dimmer_output(entity_id)}
    if "brightness" in supported or "white" in supported:
        return {"model": "HA Light (Dimmer)", "model_uid": "ha-light-dimmer",
                "output": _dimmer_output(entity_id)}
    return {"model": "HA Light (On/Off)", "model_uid": "ha-light-onoff",
            "output": _onoff_output(entity_id)}
```

### Output config builders

All four builders return an `output` dict in the same format as existing entity_mapping entries. The `apply_all_expr` field (new) is set on the output dict; per-channel `apply_expr` is omitted for light tiers.

**Common fields across all tiers:**
```python
"default_group": ColorClass.LIGHTS
"output_usage": OutputUsage.ROOM
"variable_ramp": True
"groups": [1]
"apply_all_expr": "_light_apply(channel_updates, attrs)"
```

**Channels per tier:**

*ON_OFF* — `mode: OutputMode.BINARY`, function: `ON_OFF`
```python
{"channel_type": OutputChannelType.BRIGHTNESS, "name": "Brightness",
 "read_entity": entity_id,
 "push_expr": "100.0 if entity.state == 'on' else 0.0"}
```

*DIMMER* — `mode: OutputMode.GRADUAL`, function: `DIMMER`
```python
{"channel_type": OutputChannelType.BRIGHTNESS, "name": "Brightness",
 "read_entity": entity_id,
 "push_expr": "round(attrs.get('brightness', 0) / 2.55, 1)"}
```

*DIMMER_COLOR_TEMP* — `mode: OutputMode.GRADUAL`, function: `DIMMER_COLOR_TEMP`
```python
{"channel_type": OutputChannelType.BRIGHTNESS,        "name": "Brightness",
 "read_entity": entity_id,
 "push_expr": "round(attrs.get('brightness', 0) / 2.55, 1)"},
{"channel_type": OutputChannelType.COLOR_TEMPERATURE, "name": "Color Temperature",
 "read_entity": entity_id,
 "push_expr": "float(attrs.get('color_temp') or 370)"},
```

*FULL_COLOR_DIMMER* — `mode: OutputMode.GRADUAL`, function: `FULL_COLOR_DIMMER`
```python
{"channel_type": OutputChannelType.BRIGHTNESS,        "name": "Brightness",
 "read_entity": entity_id,
 "push_expr": "round(attrs.get('brightness', 0) / 2.55, 1)"},
{"channel_type": OutputChannelType.HUE,               "name": "Hue",
 "read_entity": entity_id,
 "push_expr": "attrs.get('hs_color',(0,0))[0] if attrs.get('color_mode') in ('hs','rgb','rgbw','rgbww','xy') else 0.0"},
{"channel_type": OutputChannelType.SATURATION,        "name": "Saturation",
 "read_entity": entity_id,
 "push_expr": "attrs.get('hs_color',(0,100))[1] if attrs.get('color_mode') in ('hs','rgb','rgbw','rgbww','xy') else 0.0"},
{"channel_type": OutputChannelType.COLOR_TEMPERATURE, "name": "Color Temperature",
 "read_entity": entity_id,
 "push_expr": "float(attrs.get('color_temp') or 370)"},
{"channel_type": OutputChannelType.CIE_X,             "name": "CIE X",
 "read_entity": entity_id,
 "push_expr": "round(attrs.get('xy_color',(0.3127,0.3290))[0]*10000, 1)"},
{"channel_type": OutputChannelType.CIE_Y,             "name": "CIE Y",
 "read_entity": entity_id,
 "push_expr": "round(attrs.get('xy_color',(0.3127,0.3290))[1]*10000, 1)"},
```

**Push expression design rationale:**
- HUE and SATURATION: zero out when `color_mode` is not a color mode. Prevents stale hs values appearing in DS when the light switches to color_temp mode.
- COLOR_TEMP: always push; `370` mired (≈2700 K warm white) as fallback when unavailable.
- CIE X/Y: D65 white point `(0.3127, 0.3290)` as fallback.
- All channels share the same `read_entity` — a single HA state change triggers all channel sensors to update.

---

## Component 3: Atomic DS → HA apply (`listeners.py`)

### `_light_apply` helper

Added as a module-level pure function and registered in `_SAFE_EVAL_CONTEXT`:

```python
def _light_apply(channel_updates: dict, attrs: dict) -> dict:
    """Translate simultaneous DS channel_updates to one light.turn_on/off call."""
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
    # DS scenes use one color space at a time; if multiple arrive, CIE XY is
    # most precise, HS takes priority over CT for colored scenes.
    if cie_x is not None or cie_y is not None:
        x = ((cie_x if cie_x is not None
              else attrs.get("xy_color", (0.3127, 0.3290))[0] * 10000)) / 10000
        y = ((cie_y if cie_y is not None
              else attrs.get("xy_color", (0.3127, 0.3290))[1] * 10000)) / 10000
        sd["xy_color"] = (round(x, 4), round(y, 4))
    elif hue is not None or sat is not None:
        h = hue if hue is not None else attrs.get("hs_color", (0, 0))[0]
        s = sat if sat is not None else attrs.get("hs_color", (0, 100))[1]
        sd["hs_color"] = (h, s)
    elif ct is not None:
        sd["color_temp"] = round(ct)

    return {"domain": "light", "service": "turn_on", "service_data": sd}

```

`_light_apply` is defined **before** the `_SAFE_EVAL_CONTEXT` dict literal in `listeners.py`, and included directly inside it: `"_light_apply": _light_apply`. Do not append it after the fact — define the function first, then reference it in the dict.

### `apply_all_expr` path in `setup_output_listeners`

```python
# New eval function
def _eval_apply_all(expr: str, channel_updates: dict, state) -> dict:
    ctx = {**_SAFE_EVAL_CONTEXT,
           "channel_updates": channel_updates,
           "entity": state,
           "attrs": state.attributes if state else {}}
    return eval(expr, ctx)  # noqa: S307
```

In `setup_output_listeners`, before the existing `expr_bindings` block:

```python
apply_all_expr: str | None = output_data.get("apply_all_expr")
if apply_all_expr:
    # find the read_entity for current state lookup (all light channels share one)
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
            await hass.services.async_call(**action, blocking=False)
        except Exception:
            _LOGGER.warning("apply_all_expr eval failed: %s", _expr, exc_info=True)
    api.set_channel_applied_callback(output, _on_channel_applied_all)
    # skip existing per-channel expr_bindings block for this output
elif expr_bindings:
    # existing per-channel path — unchanged
    ...
```

The existing per-channel path is fully preserved for all other entities.

---

## Component 4: Config flow changes

### Call site updates

Two call sites in `config_flow.py` currently call `get_entity_mapping(domain, device_class)`:

1. `async_step_entity_picker` (~line 841) — single entity flow
2. `async_step_device_picker` (~line 1224) — device-level bulk flow

Both are updated to:
```python
mapping = resolve_entity_mapping(entity_id, state, domain, device_class)
```

`state` is already available at both call sites (`hass.states.get(entity_id)` is called immediately before in both).

`resolve_entity_mapping` must be imported from `entity_mapping.py` alongside `get_entity_mapping`.

### `needs_user_input` compatibility

`needs_user_input(mapping)` checks for `_choices` fields in the output config. Light output configs generated by `derive_fn` contain no choices fields, so `needs_user_input` correctly returns `False` — no extra user input step is shown for lights. This is the desired behaviour: capability is auto-detected, not manually selected.

### Entity / device picker icon derivation

`_resolve_entity_icon` and `_mdi_icon_name_for` use `state.attributes.get("device_class")` for icon lookup. For lights this returns `None`, which already maps to `"lightbulb"` via `MDI_DOMAIN_ICONS["light"]`. No change needed.

---

## Error handling

| Situation | Behaviour |
|---|---|
| Entity unavailable at config time (`state is None`) | `derive_fn` receives `None`; falls back to FULL_COLOR_DIMMER |
| `supported_color_modes` is absent or empty | Falls back to FULL_COLOR_DIMMER |
| `apply_all_expr` eval raises | Warning logged; HA service not called |
| `push_expr` eval raises | Existing warning path (unchanged) |

---

## Testing strategy

### `tests/test_entity_mapping.py` (new file)

- `test_derive_light_onoff` — `supported_color_modes={"onoff"}` → ON_OFF, 1 channel
- `test_derive_light_dimmer` — `supported_color_modes={"brightness"}` → DIMMER, 1 channel
- `test_derive_light_color_temp` — `supported_color_modes={"color_temp"}` → DIMMER_COLOR_TEMP, 2 channels
- `test_derive_light_full_color_hs` — `supported_color_modes={"hs","color_temp"}` → FULL_COLOR_DIMMER, 6 channels
- `test_derive_light_full_color_rgbww` — `supported_color_modes={"rgbww","color_temp"}` → FULL_COLOR_DIMMER, 6 channels
- `test_derive_light_fallback_unavailable` — `state=None` → FULL_COLOR_DIMMER
- `test_resolve_entity_mapping_no_derive_fn` — non-light entity unchanged
- `test_resolve_entity_mapping_with_derive_fn` — merge applied correctly

### `tests/test_listeners.py` (new or extended)

- `test_light_apply_brightness_only` — only channel 1 → `turn_on(brightness=128)`
- `test_light_apply_brightness_zero` — channel 1 = 0 → `turn_off`
- `test_light_apply_hs_both` — channels 2+3 → single `turn_on(hs_color=(h,s))`
- `test_light_apply_hs_hue_only` — channel 2 only → uses current sat from attrs
- `test_light_apply_ct` — channel 4 only → `turn_on(color_temp=370)`
- `test_light_apply_brightness_and_ct` — channels 1+4 → `turn_on(brightness=X, color_temp=Y)`
- `test_light_apply_brightness_and_hs` — channels 1+2+3 → `turn_on(brightness=X, hs_color=(h,s))`
- `test_light_apply_cie_priority_over_hs` — channels 2+3+5+6 → xy_color wins
- `test_apply_all_expr_callback_fires_once` — verify `async_call` called exactly once per DS action
- `test_apply_all_expr_does_not_affect_per_channel_path` — outputs without `apply_all_expr` still use existing path

### `tests/test_config_flow.py` (updates)

- `test_entity_picker_light_full_color` — mock light with `supported_color_modes={"hs","color_temp"}`, verify 6 channels in vdsd_data
- `test_entity_picker_light_dimmer` — mock light with `{"brightness"}`, verify 1 channel, DIMMER function
- `test_entity_picker_light_unavailable_fallback` — state=None, verify FULL_COLOR_DIMMER fallback
