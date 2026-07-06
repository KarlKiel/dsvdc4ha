# HA Light DS Channel Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the four broken static light entries in `entity_mapping.py` with a single entry that derives the correct DS output function and channel set from `supported_color_modes` at config time, and emits one atomic `light.turn_on` call when DS applies a scene.

**Architecture:** A new `derive_fn` hook in entity mapping entries lets any entity type inject runtime-derived config (OutputFunction, channels, apply_all_expr) at the point of entity selection. The single light entry uses `_derive_light_output_config` to pick one of four output tiers based on the live HA entity's `supported_color_modes`. A new `apply_all_expr` output field causes `setup_output_listeners` to register one callback that routes all simultaneous DS channel updates through `_light_apply`, which combines them into a single `light.turn_on` call.

**Tech Stack:** Python, Home Assistant config entries / entity registry, pydsvdcapi enums, pytest-asyncio

---

## File Map

| File | Change |
|---|---|
| `custom_components/dsvdc4ha/entity_mapping.py` | Add 5 functions + `resolve_entity_mapping`; replace 4 broken light entries with 1 |
| `custom_components/dsvdc4ha/listeners.py` | Add `_light_apply`, `_eval_apply_all`, `apply_all_expr` path in `setup_output_listeners` |
| `custom_components/dsvdc4ha/config_flow.py` | Import + 2 call-site updates + store `apply_all_expr` in output dict |
| `custom_components/dsvdc4ha/device_grouper.py` | Store `apply_all_expr` in output dict |
| `tests/test_light_mapping.py` | New: `_derive_light_output_config` + `resolve_entity_mapping` tests |
| `tests/test_listeners.py` | Add: `_light_apply` + `apply_all_expr` path tests |
| `tests/test_config_flow.py` | Add: light entity picker tests using `resolve_entity_mapping` |

---

## Task 1: Light capability derivation in `entity_mapping.py`

**Files:**
- Modify: `custom_components/dsvdc4ha/entity_mapping.py:107` (add functions before `ENTITY_MAPPING`)
- Modify: `custom_components/dsvdc4ha/entity_mapping.py:660-734` (replace 4 broken light entries)
- Modify: `custom_components/dsvdc4ha/entity_mapping.py:1299` (add `resolve_entity_mapping` after `get_entity_mapping`)
- Create: `tests/test_light_mapping.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_light_mapping.py`:

```python
"""Tests for light capability derivation and resolve_entity_mapping."""
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from unittest.mock import MagicMock
import pytest

from custom_components.dsvdc4ha.entity_mapping import (
    _derive_light_output_config,
    resolve_entity_mapping,
)
from pydsvdcapi.enums import OutputFunction, OutputMode, OutputChannelType


def _make_state(supported_color_modes, color_mode=None):
    state = MagicMock()
    state.state = "on"
    state.attributes = {
        "supported_color_modes": list(supported_color_modes),
        "color_mode": color_mode,
        "brightness": 128,
        "hs_color": (180.0, 50.0),
        "color_temp": 370,
        "xy_color": (0.3, 0.3),
    }
    return state


def test_derive_light_onoff():
    state = _make_state({"onoff"})
    result = _derive_light_output_config("light.test", state)
    o = result["output"]
    assert o["function"] == OutputFunction.ON_OFF
    assert o["mode"] == OutputMode.BINARY
    assert len(o["channels"]) == 1
    assert o["channels"][0]["channel_type"] == OutputChannelType.BRIGHTNESS
    assert result["model_uid"] == "ha-light-onoff"
    assert "apply_all_expr" in o


def test_derive_light_dimmer():
    state = _make_state({"brightness"})
    result = _derive_light_output_config("light.test", state)
    o = result["output"]
    assert o["function"] == OutputFunction.DIMMER
    assert o["mode"] == OutputMode.GRADUAL
    assert len(o["channels"]) == 1
    assert o["channels"][0]["channel_type"] == OutputChannelType.BRIGHTNESS
    assert result["model_uid"] == "ha-light-dimmer"


def test_derive_light_dimmer_white_mode():
    state = _make_state({"white"})
    result = _derive_light_output_config("light.test", state)
    assert result["output"]["function"] == OutputFunction.DIMMER


def test_derive_light_color_temp():
    state = _make_state({"color_temp"})
    result = _derive_light_output_config("light.test", state)
    o = result["output"]
    assert o["function"] == OutputFunction.DIMMER_COLOR_TEMP
    assert len(o["channels"]) == 2
    ch_types = {ch["channel_type"] for ch in o["channels"]}
    assert OutputChannelType.BRIGHTNESS in ch_types
    assert OutputChannelType.COLOR_TEMPERATURE in ch_types
    assert result["model_uid"] == "ha-light-color-temp"


def test_derive_light_full_color_hs():
    state = _make_state({"hs", "color_temp"})
    result = _derive_light_output_config("light.test", state)
    o = result["output"]
    assert o["function"] == OutputFunction.FULL_COLOR_DIMMER
    assert len(o["channels"]) == 6
    ch_types = {ch["channel_type"] for ch in o["channels"]}
    assert ch_types == {
        OutputChannelType.BRIGHTNESS, OutputChannelType.HUE, OutputChannelType.SATURATION,
        OutputChannelType.COLOR_TEMPERATURE, OutputChannelType.CIE_X, OutputChannelType.CIE_Y,
    }
    assert result["model_uid"] == "ha-light-full-color"


def test_derive_light_full_color_rgbww():
    state = _make_state({"rgbww", "color_temp"})
    result = _derive_light_output_config("light.test", state)
    assert result["output"]["function"] == OutputFunction.FULL_COLOR_DIMMER
    assert len(result["output"]["channels"]) == 6


def test_derive_light_full_color_rgb():
    state = _make_state({"rgb"})
    result = _derive_light_output_config("light.test", state)
    assert result["output"]["function"] == OutputFunction.FULL_COLOR_DIMMER


def test_derive_light_fallback_unavailable():
    """When state is None (entity unavailable), fall back to FULL_COLOR_DIMMER."""
    result = _derive_light_output_config("light.test", None)
    assert result["output"]["function"] == OutputFunction.FULL_COLOR_DIMMER
    assert len(result["output"]["channels"]) == 6


def test_derive_light_fallback_empty_modes():
    """Empty supported_color_modes also falls back to FULL_COLOR_DIMMER."""
    state = _make_state([])
    result = _derive_light_output_config("light.test", state)
    assert result["output"]["function"] == OutputFunction.FULL_COLOR_DIMMER


def test_all_tiers_have_apply_all_expr():
    for modes in [{"onoff"}, {"brightness"}, {"color_temp"}, {"hs"}]:
        state = _make_state(modes)
        result = _derive_light_output_config("light.test", state)
        assert "apply_all_expr" in result["output"], f"Missing apply_all_expr for {modes}"


def test_all_tiers_channels_have_push_expr():
    for modes in [{"onoff"}, {"brightness"}, {"color_temp"}, {"hs"}]:
        state = _make_state(modes)
        result = _derive_light_output_config("light.test", state)
        for ch in result["output"]["channels"]:
            assert "push_expr" in ch, f"Channel missing push_expr for {modes}: {ch}"


def test_all_channels_reference_entity():
    state = _make_state({"hs"})
    result = _derive_light_output_config("light.rgb_lamp", state)
    for ch in result["output"]["channels"]:
        assert ch.get("read_entity") == "light.rgb_lamp"


def test_resolve_entity_mapping_no_derive_fn():
    """Non-light entities without derive_fn are returned unchanged."""
    result = resolve_entity_mapping("switch.test", None, "switch", None)
    assert result is not None
    assert result["domain"] == "switch"
    # No derive_fn → mapping returned as-is
    assert "derive_fn" not in result


def test_resolve_entity_mapping_unsupported_domain():
    result = resolve_entity_mapping("media_player.tv", None, "media_player", None)
    assert result is None


def test_resolve_entity_mapping_light_with_state():
    state = _make_state({"brightness"})
    result = resolve_entity_mapping("light.lamp", state, "light", None)
    assert result is not None
    assert result["output"]["function"] == OutputFunction.DIMMER
    assert "derive_fn" not in result  # derive_fn not serialised — only output


def test_resolve_entity_mapping_light_without_state():
    result = resolve_entity_mapping("light.lamp", None, "light", None)
    assert result is not None
    assert result["output"]["function"] == OutputFunction.FULL_COLOR_DIMMER
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/arne/Development/dsvdc4ha && python -m pytest tests/test_light_mapping.py -v 2>&1 | head -40
```

Expected: ImportError or AttributeError — `_derive_light_output_config` and `resolve_entity_mapping` don't exist yet.

- [ ] **Step 3: Add tier builder functions to `entity_mapping.py`**

Insert the following block immediately before the `ENTITY_MAPPING: list[dict[str, Any]] = [` line (line 107). Add the `from __future__ import annotations` import at the top if not present and add a `Callable` import. The `Any` import is already present.

Actually the file already has `from typing import Any`. Add `Callable` to that import:

In the existing:
```python
from typing import Any
```
Change to:
```python
from typing import Any, Callable
```

Then insert these functions before line 107 (`ENTITY_MAPPING: list[...] = [`):

```python
# ---------------------------------------------------------------------------
# Light capability tier builders
# ---------------------------------------------------------------------------

def _onoff_output(entity_id: str) -> dict:
    return {
        "function": OutputFunction.ON_OFF,
        "default_group": ColorClass.LIGHTS,
        "output_usage": OutputUsage.ROOM,
        "variable_ramp": True,
        "mode": OutputMode.BINARY,
        "groups": [1],
        "apply_all_expr": "_light_apply(channel_updates, attrs)",
        "channels": [
            {
                "channel_type": OutputChannelType.BRIGHTNESS,
                "name": "Brightness",
                "read_entity": entity_id,
                "push_expr": "100.0 if entity.state == 'on' else 0.0",
            }
        ],
    }


def _dimmer_output(entity_id: str) -> dict:
    return {
        "function": OutputFunction.DIMMER,
        "default_group": ColorClass.LIGHTS,
        "output_usage": OutputUsage.ROOM,
        "variable_ramp": True,
        "mode": OutputMode.GRADUAL,
        "groups": [1],
        "apply_all_expr": "_light_apply(channel_updates, attrs)",
        "channels": [
            {
                "channel_type": OutputChannelType.BRIGHTNESS,
                "name": "Brightness",
                "read_entity": entity_id,
                "push_expr": "round(attrs.get('brightness', 0) / 2.55, 1)",
            }
        ],
    }


def _color_temp_dimmer_output(entity_id: str) -> dict:
    return {
        "function": OutputFunction.DIMMER_COLOR_TEMP,
        "default_group": ColorClass.LIGHTS,
        "output_usage": OutputUsage.ROOM,
        "variable_ramp": True,
        "mode": OutputMode.GRADUAL,
        "groups": [1],
        "apply_all_expr": "_light_apply(channel_updates, attrs)",
        "channels": [
            {
                "channel_type": OutputChannelType.BRIGHTNESS,
                "name": "Brightness",
                "read_entity": entity_id,
                "push_expr": "round(attrs.get('brightness', 0) / 2.55, 1)",
            },
            {
                "channel_type": OutputChannelType.COLOR_TEMPERATURE,
                "name": "Color Temperature",
                "read_entity": entity_id,
                "push_expr": "float(attrs.get('color_temp') or 370)",
            },
        ],
    }


def _full_color_dimmer_output(entity_id: str) -> dict:
    return {
        "function": OutputFunction.FULL_COLOR_DIMMER,
        "default_group": ColorClass.LIGHTS,
        "output_usage": OutputUsage.ROOM,
        "variable_ramp": True,
        "mode": OutputMode.GRADUAL,
        "groups": [1],
        "apply_all_expr": "_light_apply(channel_updates, attrs)",
        "channels": [
            {
                "channel_type": OutputChannelType.BRIGHTNESS,
                "name": "Brightness",
                "read_entity": entity_id,
                "push_expr": "round(attrs.get('brightness', 0) / 2.55, 1)",
            },
            {
                "channel_type": OutputChannelType.HUE,
                "name": "Hue",
                "read_entity": entity_id,
                "push_expr": "attrs.get('hs_color', (0, 0))[0] if attrs.get('color_mode') in ('hs', 'rgb', 'rgbw', 'rgbww', 'xy') else 0.0",
            },
            {
                "channel_type": OutputChannelType.SATURATION,
                "name": "Saturation",
                "read_entity": entity_id,
                "push_expr": "attrs.get('hs_color', (0, 100))[1] if attrs.get('color_mode') in ('hs', 'rgb', 'rgbw', 'rgbww', 'xy') else 0.0",
            },
            {
                "channel_type": OutputChannelType.COLOR_TEMPERATURE,
                "name": "Color Temperature",
                "read_entity": entity_id,
                "push_expr": "float(attrs.get('color_temp') or 370)",
            },
            {
                "channel_type": OutputChannelType.CIE_X,
                "name": "CIE X",
                "read_entity": entity_id,
                "push_expr": "round(attrs.get('xy_color', (0.3127, 0.3290))[0] * 10000, 1)",
            },
            {
                "channel_type": OutputChannelType.CIE_Y,
                "name": "CIE Y",
                "read_entity": entity_id,
                "push_expr": "round(attrs.get('xy_color', (0.3127, 0.3290))[1] * 10000, 1)",
            },
        ],
    }


def _derive_light_output_config(entity_id: str, state) -> dict:
    """Return the per-tier output config for a light entity based on supported_color_modes."""
    attrs = state.attributes if state else {}
    supported = set(attrs.get("supported_color_modes") or [])

    if supported & {"hs", "xy", "rgb", "rgbw", "rgbww"}:
        return {
            "model": "HA Light (Full Color)",
            "model_uid": "ha-light-full-color",
            "output": _full_color_dimmer_output(entity_id),
        }
    if "color_temp" in supported:
        return {
            "model": "HA Light (Color Temp)",
            "model_uid": "ha-light-color-temp",
            "output": _color_temp_dimmer_output(entity_id),
        }
    if "brightness" in supported or "white" in supported:
        return {
            "model": "HA Light (Dimmer)",
            "model_uid": "ha-light-dimmer",
            "output": _dimmer_output(entity_id),
        }
    return {
        "model": "HA Light (On/Off)",
        "model_uid": "ha-light-onoff",
        "output": _onoff_output(entity_id),
    }

```

- [ ] **Step 4: Replace the 4 broken light entries with 1 entry using `derive_fn`**

Remove lines 660-734 (the four `domain: "light"` entries — `device_class: None`, `"brightness"`, `"color_temp"`, `"rgb"`). Replace them with:

```python
    # ── Light ─────────────────────────────────────────────────────────────────
    {
        "domain": "light", "device_class": None, "primary_group": ColorGroup.YELLOW,
        "model": "HA Light",
        "model_uid": "ha-light",
        "vendor_name": "Home Assistant",
        "derive_fn": _derive_light_output_config,
    },
```

- [ ] **Step 5: Add `resolve_entity_mapping` after `get_entity_mapping` (line 1299)**

After the `get_entity_mapping` function (which ends at line 1299), add:

```python

def resolve_entity_mapping(
    entity_id: str,
    state,
    domain: str,
    device_class: str | None,
) -> dict[str, Any] | None:
    """Return the fully resolved mapping, calling derive_fn when present.

    derive_fn is called only at config time; the result is merged over the base
    entry. The returned dict contains no callables — safe to serialise.
    """
    mapping = get_entity_mapping(domain, device_class)
    if mapping is None:
        return None
    derive_fn = mapping.get("derive_fn")
    if derive_fn is None:
        return mapping
    derived = derive_fn(entity_id, state)
    return {k: v for k, v in {**mapping, **derived}.items() if k != "derive_fn"}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd /home/arne/Development/dsvdc4ha && python -m pytest tests/test_light_mapping.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Run full test suite**

```bash
cd /home/arne/Development/dsvdc4ha && python -m pytest --tb=short -q
```

Expected: all previously-passing tests still pass (≥274 tests).

- [ ] **Step 8: Commit**

```bash
cd /home/arne/Development/dsvdc4ha && git add custom_components/dsvdc4ha/entity_mapping.py tests/test_light_mapping.py && git commit -m "feat: derive light output config from supported_color_modes via derive_fn hook"
```

---

## Task 2: Atomic DS → HA apply in `listeners.py`

**Files:**
- Modify: `custom_components/dsvdc4ha/listeners.py:17-27` (add `_light_apply` + register in `_SAFE_EVAL_CONTEXT`)
- Modify: `custom_components/dsvdc4ha/listeners.py:38-44` (add `_eval_apply_all` after `_eval_apply`)
- Modify: `custom_components/dsvdc4ha/listeners.py:299-334` (add `apply_all_expr` path)
- Modify: `tests/test_listeners.py` (extend with new tests)

- [ ] **Step 1: Write failing tests**

Append the following to `tests/test_listeners.py`. First check the existing imports at the top of that file — add any missing ones.

```python
# ── _light_apply unit tests ──────────────────────────────────────────────────

from custom_components.dsvdc4ha.listeners import _light_apply


def test_light_apply_brightness_only():
    result = _light_apply({1: 50.0}, {})
    assert result["service"] == "turn_on"
    assert result["service_data"]["brightness"] == round(50.0 * 2.55)
    assert "hs_color" not in result["service_data"]
    assert "color_temp" not in result["service_data"]


def test_light_apply_brightness_zero_turns_off():
    result = _light_apply({1: 0.0}, {})
    assert result["service"] == "turn_off"
    assert result["service_data"] == {}


def test_light_apply_brightness_negative_turns_off():
    result = _light_apply({1: -1.0}, {})
    assert result["service"] == "turn_off"


def test_light_apply_hs_both():
    result = _light_apply({2: 180.0, 3: 75.0}, {})
    assert result["service"] == "turn_on"
    assert result["service_data"]["hs_color"] == (180.0, 75.0)


def test_light_apply_hue_only_uses_current_sat_from_attrs():
    attrs = {"hs_color": (45.0, 90.0)}
    result = _light_apply({2: 200.0}, attrs)
    assert result["service_data"]["hs_color"] == (200.0, 90.0)


def test_light_apply_sat_only_uses_current_hue_from_attrs():
    attrs = {"hs_color": (45.0, 90.0)}
    result = _light_apply({3: 50.0}, attrs)
    assert result["service_data"]["hs_color"] == (45.0, 50.0)


def test_light_apply_ct_only():
    result = _light_apply({4: 370.0}, {})
    assert result["service"] == "turn_on"
    assert result["service_data"]["color_temp"] == 370


def test_light_apply_brightness_and_ct():
    result = _light_apply({1: 80.0, 4: 300.0}, {})
    assert result["service_data"]["brightness"] == round(80.0 * 2.55)
    assert result["service_data"]["color_temp"] == 300


def test_light_apply_brightness_and_hs():
    result = _light_apply({1: 60.0, 2: 120.0, 3: 80.0}, {})
    assert result["service_data"]["brightness"] == round(60.0 * 2.55)
    assert result["service_data"]["hs_color"] == (120.0, 80.0)


def test_light_apply_cie_priority_over_hs():
    """CIE XY wins over HS when both are present."""
    attrs = {"xy_color": (0.3127, 0.3290), "hs_color": (45.0, 90.0)}
    result = _light_apply({2: 180.0, 3: 75.0, 5: 3127.0, 6: 3290.0}, attrs)
    assert "xy_color" in result["service_data"]
    assert "hs_color" not in result["service_data"]
    assert result["service_data"]["xy_color"] == (round(3127.0 / 10000, 4), round(3290.0 / 10000, 4))


def test_light_apply_cie_partial_uses_attrs():
    """CIE X alone → Y from attrs."""
    attrs = {"xy_color": (0.3127, 0.3290)}
    result = _light_apply({5: 2000.0}, attrs)
    assert "xy_color" in result["service_data"]
    assert result["service_data"]["xy_color"][0] == round(2000.0 / 10000, 4)
    assert result["service_data"]["xy_color"][1] == round(0.3290, 4)


def test_light_apply_empty_channel_updates():
    """No channel updates → turn_on with no service_data changes."""
    result = _light_apply({}, {})
    assert result["service"] == "turn_on"
    assert result["service_data"] == {}


# ── apply_all_expr path in setup_output_listeners ───────────────────────────

@pytest.mark.asyncio
async def test_apply_all_expr_callback_fires_once():
    """apply_all_expr registers ONE callback; async_call called exactly once per DS scene."""
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.states = MagicMock()
    hass.states.get.return_value = None

    api = MagicMock()
    mock_device = MagicMock()
    mock_vdsd = MagicMock()
    mock_output = MagicMock()
    mock_output.get_channel.return_value = MagicMock()
    mock_vdsd.output = mock_output
    mock_device.get_vdsd.return_value = mock_vdsd
    api.get_device.return_value = mock_device

    captured = []
    api.set_channel_applied_callback.side_effect = lambda out, cb: captured.append(cb)

    channels_data = [
        {"dsIndex": 0, "channelType": 1, "read_entity": "light.rgb",
         "push_expr": "round(attrs.get('brightness', 0) / 2.55, 1)"},
        {"dsIndex": 1, "channelType": 2, "read_entity": "light.rgb",
         "push_expr": "attrs.get('hs_color', (0, 0))[0]"},
    ]
    output_data = {
        "channels": channels_data,
        "apply_all_expr": "_light_apply(channel_updates, attrs)",
    }

    with patch("custom_components.dsvdc4ha.listeners.async_track_state_change_event",
               return_value=lambda: None):
        setup_output_listeners(hass, api, "entry1", [{"output": output_data}])

    assert len(captured) == 1, "Expected exactly one callback registered"

    await captured[0](mock_output, {1: 80.0, 2: 180.0})

    assert hass.services.async_call.await_count == 1
    call_kwargs = hass.services.async_call.call_args.kwargs
    assert call_kwargs["domain"] == "light"
    assert call_kwargs["service"] == "turn_on"


@pytest.mark.asyncio
async def test_apply_all_expr_does_not_affect_per_channel_path():
    """Outputs without apply_all_expr still use the existing per-channel expr path."""
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    api = MagicMock()
    mock_device = MagicMock()
    mock_vdsd = MagicMock()
    mock_output = MagicMock()
    mock_output.get_channel.return_value = MagicMock()
    mock_vdsd.output = mock_output
    mock_device.get_vdsd.return_value = mock_vdsd
    api.get_device.return_value = mock_device

    captured = []
    api.set_channel_applied_callback.side_effect = lambda out, cb: captured.append(cb)

    channels_data = [
        {"dsIndex": 0, "channelType": 19, "read_entity": "switch.test",
         "apply_expr": "{'domain':'switch','service':'turn_on' if value>=1 else 'turn_off','service_data':{}}",
         "push_expr": "1 if entity.state == 'on' else 0"},
    ]
    output_data = {"channels": channels_data}  # no apply_all_expr

    with patch("custom_components.dsvdc4ha.listeners.async_track_state_change_event",
               return_value=lambda: None):
        setup_output_listeners(hass, api, "entry1", [{"output": output_data}])

    assert len(captured) == 1

    state = MagicMock()
    state.state = "on"
    hass.states.get.return_value = state
    await captured[0](mock_output, {19: 1.0})
    assert hass.services.async_call.await_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/arne/Development/dsvdc4ha && python -m pytest tests/test_listeners.py::test_light_apply_brightness_only tests/test_listeners.py::test_apply_all_expr_callback_fires_once -v 2>&1 | head -30
```

Expected: ImportError — `_light_apply` doesn't exist yet.

- [ ] **Step 3: Add `_light_apply` before `_SAFE_EVAL_CONTEXT` in `listeners.py`**

Insert before line 17 (`_SAFE_EVAL_CONTEXT: dict = {`):

```python
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

    if cie_x is not None or cie_y is not None:
        x = (cie_x if cie_x is not None
             else attrs.get("xy_color", (0.3127, 0.3290))[0] * 10000) / 10000
        y = (cie_y if cie_y is not None
             else attrs.get("xy_color", (0.3127, 0.3290))[1] * 10000) / 10000
        sd["xy_color"] = (round(x, 4), round(y, 4))
    elif hue is not None or sat is not None:
        h = hue if hue is not None else attrs.get("hs_color", (0, 0))[0]
        s = sat if sat is not None else attrs.get("hs_color", (0, 100))[1]
        sd["hs_color"] = (h, s)
    elif ct is not None:
        sd["color_temp"] = round(ct)

    return {"domain": "light", "service": "turn_on", "service_data": sd}

```

Then add `"_light_apply": _light_apply,` to `_SAFE_EVAL_CONTEXT`. The dict currently looks like:

```python
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
}
```

Change to:

```python
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
```

- [ ] **Step 4: Add `_eval_apply_all` after `_eval_apply`**

After the `_eval_apply` function (currently ending around line 44), insert:

```python

def _eval_apply_all(expr: str, channel_updates: dict, state) -> dict:
    """Evaluate an apply_all_expr with channel_updates and current state in context."""
    ctx = {
        **_SAFE_EVAL_CONTEXT,
        "channel_updates": channel_updates,
        "entity": state,
        "attrs": state.attributes if state else {},
    }
    return eval(expr, ctx)  # noqa: S307

```

- [ ] **Step 5: Add `apply_all_expr` path in `setup_output_listeners`**

In `setup_output_listeners`, the write-side section starts at line 299:

```python
        # Write side: one callback per output handles all channels
        expr_bindings: list[tuple[int, str, str | None]] = []
        static_action: dict | None = None
        for ch_data in output_data.get("channels", []):
            ...

        if expr_bindings:
            ...
        elif static_action:
            ...
```

Change the `if expr_bindings:` block (at line 310) to `elif expr_bindings:`, and insert the new `apply_all_expr` block before it:

```python
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
```

- [ ] **Step 6: Run all listener tests**

```bash
cd /home/arne/Development/dsvdc4ha && python -m pytest tests/test_listeners.py -v
```

Expected: all tests PASS (including old and new ones).

- [ ] **Step 7: Run full test suite**

```bash
cd /home/arne/Development/dsvdc4ha && python -m pytest --tb=short -q
```

Expected: all previously-passing tests still pass.

- [ ] **Step 8: Commit**

```bash
cd /home/arne/Development/dsvdc4ha && git add custom_components/dsvdc4ha/listeners.py tests/test_listeners.py && git commit -m "feat: add _light_apply and apply_all_expr path for atomic DS→HA light scenes"
```

---

## Task 3: Config flow and device grouper wiring

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py:60-65` (import `resolve_entity_mapping`, remove `get_entity_mapping`)
- Modify: `custom_components/dsvdc4ha/config_flow.py:841` (call site 1 — entity picker)
- Modify: `custom_components/dsvdc4ha/config_flow.py:1131-1142` (store `apply_all_expr` in output dict)
- Modify: `custom_components/dsvdc4ha/config_flow.py:1224` (call site 2 — device picker)
- Modify: `custom_components/dsvdc4ha/device_grouper.py:295-306` (store `apply_all_expr` in output dict)
- Modify: `tests/test_config_flow.py` (add light-specific tests)

- [ ] **Step 1: Write failing tests**

Append the following to `tests/test_config_flow.py`. Check the existing import block at the top of that file and add missing imports (`from unittest.mock import patch, AsyncMock, MagicMock` etc. are likely already present).

```python
# ── Light entity picker tests (resolve_entity_mapping) ───────────────────────

@pytest.mark.asyncio
async def test_entity_picker_light_full_color_yields_6_channels():
    """Picking a full-color light auto-selects FULL_COLOR_DIMMER with 6 channels."""
    flow = _make_subentry_flow()

    mock_ent_reg = MagicMock()
    mock_ent_entry = MagicMock()
    mock_ent_entry.unique_id = "light_rgb_unique"
    mock_ent_reg.async_get.return_value = mock_ent_entry

    mock_dev_reg = MagicMock()

    state = MagicMock()
    state.name = "RGB Lamp"
    state.attributes = {
        "device_class": None,
        "supported_color_modes": ["hs", "color_temp"],
        "brightness": 128,
        "hs_color": (180.0, 50.0),
        "color_temp": 370,
        "xy_color": (0.3, 0.3),
    }
    flow.hass.states.get.return_value = state

    with (
        patch("custom_components.dsvdc4ha.config_flow.er.async_get",
              return_value=mock_ent_reg),
        patch("custom_components.dsvdc4ha.config_flow.dr.async_get",
              return_value=mock_dev_reg),
        patch("custom_components.dsvdc4ha.config_flow.bundled_icon_b64_for",
              return_value=None),
    ):
        # Simulate submit of entity_id
        flow._entity_id = "light.rgb_lamp"
        flow._entity_mapping = None
        result = await flow.async_step_entity_picker({"entity_id": "light.rgb_lamp"})

    assert result["type"] != "error"
    assert flow._entity_mapping is not None
    from pydsvdcapi.enums import OutputFunction
    assert flow._entity_mapping["output"]["function"] == OutputFunction.FULL_COLOR_DIMMER
    assert len(flow._entity_mapping["output"]["channels"]) == 6


@pytest.mark.asyncio
async def test_entity_picker_light_dimmer_yields_1_channel():
    """Picking a brightness-only light selects DIMMER with 1 channel."""
    flow = _make_subentry_flow()

    mock_ent_reg = MagicMock()
    mock_ent_entry = MagicMock()
    mock_ent_entry.unique_id = "light_dim_unique"
    mock_ent_reg.async_get.return_value = mock_ent_entry
    mock_dev_reg = MagicMock()

    state = MagicMock()
    state.name = "Dim Lamp"
    state.attributes = {
        "device_class": None,
        "supported_color_modes": ["brightness"],
        "brightness": 200,
    }
    flow.hass.states.get.return_value = state

    with (
        patch("custom_components.dsvdc4ha.config_flow.er.async_get",
              return_value=mock_ent_reg),
        patch("custom_components.dsvdc4ha.config_flow.dr.async_get",
              return_value=mock_dev_reg),
        patch("custom_components.dsvdc4ha.config_flow.bundled_icon_b64_for",
              return_value=None),
    ):
        flow._entity_id = "light.dim_lamp"
        flow._entity_mapping = None
        result = await flow.async_step_entity_picker({"entity_id": "light.dim_lamp"})

    from pydsvdcapi.enums import OutputFunction
    assert flow._entity_mapping["output"]["function"] == OutputFunction.DIMMER
    assert len(flow._entity_mapping["output"]["channels"]) == 1


@pytest.mark.asyncio
async def test_entity_picker_light_unavailable_fallback():
    """When state is unavailable (None), light falls back to FULL_COLOR_DIMMER."""
    flow = _make_subentry_flow()

    mock_ent_reg = MagicMock()
    mock_ent_entry = MagicMock()
    mock_ent_entry.unique_id = "light_unavail_unique"
    mock_ent_reg.async_get.return_value = mock_ent_entry
    mock_dev_reg = MagicMock()

    # State returns None (entity unavailable)
    flow.hass.states.get.return_value = None

    with (
        patch("custom_components.dsvdc4ha.config_flow.er.async_get",
              return_value=mock_ent_reg),
        patch("custom_components.dsvdc4ha.config_flow.dr.async_get",
              return_value=mock_dev_reg),
        patch("custom_components.dsvdc4ha.config_flow.bundled_icon_b64_for",
              return_value=None),
    ):
        result = await flow.async_step_entity_picker({"entity_id": "light.unavail"})

    # Entity not found → error; this is the correct flow behaviour
    assert result.get("errors", {}).get("entity_id") == "entity_not_found"


@pytest.mark.asyncio
async def test_entity_picker_light_apply_all_expr_stored():
    """apply_all_expr from the mapping's output is stored in the built vdSD output."""
    from unittest.mock import patch as _patch
    from custom_components.dsvdc4ha.entity_mapping import resolve_entity_mapping

    flow = _make_subentry_flow()

    state = MagicMock()
    state.name = "Full Lamp"
    state.attributes = {
        "device_class": None,
        "supported_color_modes": ["hs"],
        "brightness": 128,
        "hs_color": (0.0, 0.0),
        "color_temp": 370,
        "xy_color": (0.3127, 0.3290),
    }
    flow.hass.states.get.return_value = state

    mock_ent_reg = MagicMock()
    mock_ent_entry = MagicMock()
    mock_ent_entry.unique_id = "light_full_unique"
    mock_ent_entry.device_id = None
    mock_ent_reg.async_get.return_value = mock_ent_entry

    mapping = resolve_entity_mapping("light.full", state, "light", None)
    flow._entity_id = "light.full"
    flow._entity_mapping = mapping
    flow._display_id = "Light"

    with (
        _patch("custom_components.dsvdc4ha.config_flow.er.async_get",
               return_value=mock_ent_reg),
        _patch("custom_components.dsvdc4ha.config_flow.dr.async_get",
               return_value=MagicMock()),
        _patch.object(flow, "_resolve_entity_icon",
                      new=AsyncMock(return_value=("light_full", None))),
        _patch.object(flow, "async_step_model_features",
                      new=AsyncMock(return_value={"type": "form", "step_id": "model_features"})),
    ):
        await flow._build_entity_vdsd_and_continue({})

    output = flow._current_vdsd.get("output") if flow._current_vdsd else None
    assert output is not None
    assert "apply_all_expr" in output, "apply_all_expr must be stored in vdSD output"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/arne/Development/dsvdc4ha && python -m pytest tests/test_config_flow.py::test_entity_picker_light_full_color_yields_6_channels tests/test_config_flow.py::test_entity_picker_light_apply_all_expr_stored -v 2>&1 | head -40
```

Expected: failures — `resolve_entity_mapping` not imported / not called yet.

- [ ] **Step 3: Update `config_flow.py` import block**

Change lines 60-65 from:

```python
from .entity_mapping import (
    CHANNEL_TYPE_LABELS as _CHANNEL_TYPE_LABELS,
    SUPPORTED_DOMAINS,
    get_entity_mapping,
    needs_user_input,
)
```

To:

```python
from .entity_mapping import (
    CHANNEL_TYPE_LABELS as _CHANNEL_TYPE_LABELS,
    SUPPORTED_DOMAINS,
    resolve_entity_mapping,
    needs_user_input,
)
```

(`get_entity_mapping` is no longer called directly from `config_flow.py`.)

- [ ] **Step 4: Update call site 1 — `async_step_entity_picker` (line 841)**

Change:

```python
                mapping = get_entity_mapping(domain, device_class)
```

To:

```python
                mapping = resolve_entity_mapping(entity_id, state, domain, device_class)
```

`entity_id` and `state` are both already in scope at this point (lines 832-840).

- [ ] **Step 5: Update call site 2 — `async_step_device_picker` (line 1224)**

Change:

```python
                mapping = get_entity_mapping(domain, device_class)
```

To:

```python
                mapping = resolve_entity_mapping(entry.entity_id, state, domain, device_class)
```

`entry.entity_id` is the entity ID; `state` is `self.hass.states.get(entry.entity_id)` which is already assigned on line 1217.

- [ ] **Step 6: Store `apply_all_expr` in the output dict — `config_flow.py`**

In `_build_entity_vdsd_and_continue`, the `vdsd["output"]` dict is built at lines ~1131-1142:

```python
            vdsd["output"] = {
                "name": "Output",
                "groups": o["groups"],
                "defaultGroup": o["default_group"],
                "activeGroup": o["default_group"],
                "function": fn,
                "outputUsage": usage,
                "variableRamp": o["variable_ramp"],
                "mode": mode,
                "onThreshold": 50,
                "channels": channels,
            }
```

Change to:

```python
            vdsd["output"] = {
                "name": "Output",
                "groups": o["groups"],
                "defaultGroup": o["default_group"],
                "activeGroup": o["default_group"],
                "function": fn,
                "outputUsage": usage,
                "variableRamp": o["variable_ramp"],
                "mode": mode,
                "onThreshold": 50,
                "channels": channels,
                **({"apply_all_expr": o["apply_all_expr"]} if o.get("apply_all_expr") else {}),
            }
```

- [ ] **Step 6b: Fix `all_auto` routing for outputs using `apply_all_expr`**

In `_build_entity_vdsd_and_continue`, right after setting `self._current_channels` (around line 1158):

```python
        if vdsd["output"] and self._current_channels:
            all_auto = all(ch.get("apply_expr") for ch in self._current_channels)
            if not all_auto:
                return await self.async_step_entity_channel_mapping()
        return await self.async_step_model_features()
```

Change to:

```python
        if vdsd["output"] and self._current_channels:
            apply_all = vdsd["output"].get("apply_all_expr")
            all_auto = apply_all is not None or all(ch.get("apply_expr") for ch in self._current_channels)
            if not all_auto:
                return await self.async_step_entity_channel_mapping()
        return await self.async_step_model_features()
```

Without this fix, light outputs (which have `apply_all_expr` but no per-channel `apply_expr`) would incorrectly route to the channel binding step.

- [ ] **Step 7: Store `apply_all_expr` in the output dict — `device_grouper.py`**

In `resolve_vdsd_plan`, the `vdsd["output"]` dict is built at lines ~295-306:

```python
        vdsd["output"] = {
            "name": "Output",
            "groups": o["groups"],
            "defaultGroup": o["default_group"],
            "activeGroup": o["default_group"],
            "function": fn,
            "outputUsage": usage,
            "variableRamp": o["variable_ramp"],
            "mode": mode,
            "onThreshold": _OUTPUT_ON_THRESHOLD,
            "channels": channels,
        }
```

Change to:

```python
        vdsd["output"] = {
            "name": "Output",
            "groups": o["groups"],
            "defaultGroup": o["default_group"],
            "activeGroup": o["default_group"],
            "function": fn,
            "outputUsage": usage,
            "variableRamp": o["variable_ramp"],
            "mode": mode,
            "onThreshold": _OUTPUT_ON_THRESHOLD,
            "channels": channels,
            **({"apply_all_expr": o["apply_all_expr"]} if o.get("apply_all_expr") else {}),
        }
```

- [ ] **Step 8: Run all config_flow tests**

```bash
cd /home/arne/Development/dsvdc4ha && python -m pytest tests/test_config_flow.py -v --tb=short
```

Expected: all tests PASS (including the new light tests).

Note: `test_entity_picker_light_unavailable_fallback` verifies the `entity_not_found` error path — the config flow checks `state is None` before calling `resolve_entity_mapping`, so unavailable entities are rejected cleanly, not fallen back to FULL_COLOR_DIMMER. This is correct: the fallback is only for the device-picker path where state may not be available.

- [ ] **Step 9: Run full test suite**

```bash
cd /home/arne/Development/dsvdc4ha && python -m pytest --tb=short -q
```

Expected: all tests PASS.

- [ ] **Step 10: Commit**

```bash
cd /home/arne/Development/dsvdc4ha && git add custom_components/dsvdc4ha/config_flow.py custom_components/dsvdc4ha/device_grouper.py tests/test_config_flow.py && git commit -m "feat: wire resolve_entity_mapping into config flow and propagate apply_all_expr"
```
