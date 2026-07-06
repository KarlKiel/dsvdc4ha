# Fix Entity Binding Bugs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix five bugs that together make DSS→HA control, HA→DSS push (for non-ON/OFF lights), and channel sensor entities completely non-functional.

**Architecture:** Three files need changes — `listeners.py` (entity_id injection + None guards in `_light_apply`), `entity_mapping.py` (FULL_COLOR channel order + push_expr robustness), and `sensor.py` (use push_expr instead of float-coercion). Each task is independent and produces passing tests on its own.

**Tech Stack:** Python 3.13, Home Assistant custom component, pydsvdcapi, pytest-asyncio.

---

## Root Causes (read before implementing)

**Bug 1 — DSS→HA broken for ALL output entity types:**
`hass.services.async_call(**action)` is fired with no `entity_id` in `service_data` and no `target`. HA entity services silently no-op when no target entity is given. The entity to control (`re_id` / `read_entity`) is known at listener-setup time but never injected.

**Bug 2 — `_light_apply` None-attr crash:**
`attrs.get("xy_color", default)` returns `None` when the key exists with value `None` (many HA light integrations set `xy_color: null`). Subscripting `None[0]` raises `TypeError` which is caught and logged — the service call is silently dropped.

**Bug 3 — FULL_COLOR_DIMMER channel order wrong:**
`_full_color_dimmer_output` lists channels: BRIGHTNESS(0), HUE(1), SAT(2), CT(3), CIE_X(4), CIE_Y(5). pydsvdcapi's `FUNCTION_CHANNELS` canonical order is: BRIGHTNESS(0), **CT(1)**, **HUE(2)**, **SAT(3)**, CIE_X(4), CIE_Y(5). DSS uses ds_index positions to route scene commands, so with the wrong order CT and color control are crossed.

**Bug 4 — BRIGHTNESS push_expr sends wrong value when light is off:**
`"round(attrs.get('brightness', 0) / 2.55, 1)"` pushes the last known brightness (e.g. 78%) when the light turns off. In dS, BRIGHTNESS=0 means off. Additionally, `attrs.get('brightness', 0)` returns `None` (not 0) when the key exists with `None` value → `None / 2.55` → `TypeError`.

**Bug 5 — `OutputChannelEntity` always shows "unknown":**
`float(state.state)` raises `ValueError` for "on"/"off"/"open"/"closed" — the sensor never gets a value. `push_expr` exists for exactly this conversion but is never used by the sensor.

---

## File Map

| File | Change |
|---|---|
| `custom_components/dsvdc4ha/listeners.py` | Bug 1: inject `entity_id` after eval; Bug 2: `or`-guard None attrs in `_light_apply` |
| `custom_components/dsvdc4ha/entity_mapping.py` | Bug 3: reorder FULL_COLOR channels; Bug 4: fix push_exprs |
| `custom_components/dsvdc4ha/sensor.py` | Bug 5: use `push_expr` in `OutputChannelEntity` |
| `tests/test_listeners.py` | Update existing + add new tests |
| `tests/test_light_mapping.py` | Add order + push_expr robustness tests |
| `tests/test_sensor.py` | Add push_expr usage tests |

---

## Task 1: Fix DSS→HA entity_id injection + `_light_apply` None guards

**Files:**
- Modify: `custom_components/dsvdc4ha/listeners.py`
- Test: `tests/test_listeners.py`

### Step 1.1: Write failing tests

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_listeners.py` after the existing `test_apply_expr_calls_ha_service`:

```python
@pytest.mark.asyncio
async def test_apply_expr_injects_entity_id():
    """apply_expr callback injects read_entity as entity_id into service_data."""
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
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

    channels_data = [{"dsIndex": 0, "channelType": 8,
                      "read_entity": "cover.blind",
                      "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(100-value)}}"}]
    with patch("custom_components.dsvdc4ha.listeners.async_track_state_change_event",
               return_value=lambda: None):
        setup_output_listeners(hass, api, "entry1", [{"output": {"channels": channels_data}}])

    await captured[0](mock_output, {8: 25.0})

    sd = hass.services.async_call.call_args.kwargs["service_data"]
    assert sd["entity_id"] == "cover.blind"
    assert sd["position"] == 75


@pytest.mark.asyncio
async def test_apply_all_expr_injects_entity_id():
    """apply_all_expr callback injects read_entity as entity_id into service_data."""
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
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

    channels_data = [{"dsIndex": 0, "channelType": 1, "read_entity": "light.bedroom",
                      "push_expr": "100.0 if entity.state == 'on' else 0.0"}]
    output_data = {"channels": channels_data,
                   "apply_all_expr": "_light_apply(channel_updates, attrs)"}
    with patch("custom_components.dsvdc4ha.listeners.async_track_state_change_event",
               return_value=lambda: None):
        setup_output_listeners(hass, api, "entry1", [{"output": output_data}])

    await captured[0](mock_output, {1: 80.0})

    sd = hass.services.async_call.call_args.kwargs["service_data"]
    assert sd.get("entity_id") == "light.bedroom"


def test_light_apply_none_xy_color_in_attrs():
    """_light_apply does not crash when xy_color attr is None."""
    result = _light_apply({5: 3127.0}, {"xy_color": None})
    assert result["service"] == "turn_on"
    assert "xy_color" in result["service_data"]


def test_light_apply_none_hs_color_in_attrs():
    """_light_apply does not crash when hs_color attr is None."""
    result = _light_apply({2: 180.0}, {"hs_color": None})
    assert result["service"] == "turn_on"
    assert result["service_data"]["hs_color"][0] == 180.0
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/test_listeners.py::test_apply_expr_injects_entity_id tests/test_listeners.py::test_apply_all_expr_injects_entity_id tests/test_listeners.py::test_light_apply_none_xy_color_in_attrs tests/test_listeners.py::test_light_apply_none_hs_color_in_attrs -v
```

Expected: FAIL — `entity_id` not in service_data; `TypeError` for None subscript.

- [ ] **Step 3: Fix `_light_apply` None guards (lines 17–47 of `listeners.py`)**

Replace the full `_light_apply` function:

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
        sd["color_temp"] = round(ct)

    return {"domain": "light", "service": "turn_on", "service_data": sd}
```

- [ ] **Step 4: Inject `entity_id` in the `apply_all_expr` callback (listeners.py ~line 363–374)**

In `setup_output_listeners`, locate the `_on_channel_applied_all` async function and update it:

```python
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
```

- [ ] **Step 5: Inject `entity_id` in the `apply_expr` per-channel callback (listeners.py ~line 376–391)**

Update `_on_channel_applied_expr`:

```python
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
```

- [ ] **Step 6: Update existing tests that assert service_data without entity_id**

In `tests/test_listeners.py`, update `test_apply_expr_calls_ha_service` (line ~282):
```python
    hass.services.async_call.assert_awaited_once_with(
        domain="cover",
        service="set_cover_position",
        service_data={"position": 75, "entity_id": "cover.blind"},
        blocking=False,
    )
```

Update `test_apply_expr_multi_channel_single_callback` (lines ~327–334): add `"entity_id": "light.rgb"` to both `service_data` assertions:
```python
    assert call0.kwargs["service_data"] == {"brightness": 255, "entity_id": "light.rgb"}
    # ...
    assert call1.kwargs["service_data"] == {"hs_color": (180.0, 50), "entity_id": "light.rgb"}
```

Update `test_apply_all_expr_callback_fires_once` (line ~456–459) to also assert `entity_id`:
```python
    call_kwargs = hass.services.async_call.call_args.kwargs
    assert call_kwargs["domain"] == "light"
    assert call_kwargs["service"] == "turn_on"
    assert call_kwargs["service_data"].get("entity_id") == "light.rgb"
```

Note: that test uses `channels_data` with `"read_entity": "light.rgb"` — the injection uses that as entity_id.

- [ ] **Step 7: Run all listener tests**

```bash
source .venv/bin/activate && pytest tests/test_listeners.py -v
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add custom_components/dsvdc4ha/listeners.py tests/test_listeners.py
git commit -m "fix: inject entity_id into service calls and guard None attrs in _light_apply"
```

---

## Task 2: Fix FULL_COLOR channel order + push_expr robustness

**Files:**
- Modify: `custom_components/dsvdc4ha/entity_mapping.py`
- Test: `tests/test_light_mapping.py`

### Context

pydsvdcapi's `FUNCTION_CHANNELS[FULL_COLOR_DIMMER]` order (from source):
```
ds_index 0: BRIGHTNESS
ds_index 1: COLOR_TEMPERATURE   ← must be here for DSS configurator
ds_index 2: HUE
ds_index 3: SATURATION
ds_index 4: CIE_X
ds_index 5: CIE_Y
```

Current `_full_color_dimmer_output` has HUE at index 1 and COLOR_TEMPERATURE at index 3, which is wrong.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_light_mapping.py`:

```python
def test_full_color_channel_order_matches_pydsvdcapi():
    """FULL_COLOR_DIMMER channels must be in pydsvdcapi canonical order: BRIGHTNESS, CT, HUE, SAT, CIE_X, CIE_Y."""
    result = _derive_light_output_config("light.test", _make_state({"hs"}))
    channels = result["output"]["channels"]
    assert len(channels) == 6
    assert channels[0]["channel_type"] == OutputChannelType.BRIGHTNESS
    assert channels[1]["channel_type"] == OutputChannelType.COLOR_TEMPERATURE
    assert channels[2]["channel_type"] == OutputChannelType.HUE
    assert channels[3]["channel_type"] == OutputChannelType.SATURATION
    assert channels[4]["channel_type"] == OutputChannelType.CIE_X
    assert channels[5]["channel_type"] == OutputChannelType.CIE_Y


def test_brightness_push_expr_returns_zero_when_off():
    """BRIGHTNESS push_expr for DIMMER returns 0.0 when entity state is 'off'."""
    from custom_components.dsvdc4ha.listeners import _eval_push
    result = _derive_light_output_config("light.test", _make_state({"brightness"}))
    expr = result["output"]["channels"][0]["push_expr"]
    state_off = MagicMock()
    state_off.state = "off"
    state_off.attributes = {"brightness": 200}
    assert _eval_push(expr, state_off) == 0.0


def test_brightness_push_expr_handles_none_brightness():
    """BRIGHTNESS push_expr treats None brightness as 0 (no crash, no TypeError)."""
    from custom_components.dsvdc4ha.listeners import _eval_push
    result = _derive_light_output_config("light.test", _make_state({"brightness"}))
    expr = result["output"]["channels"][0]["push_expr"]
    state_none = MagicMock()
    state_none.state = "on"
    state_none.attributes = {"brightness": None}
    assert _eval_push(expr, state_none) == 0.0


def test_hs_push_expr_handles_none_hs_color():
    """HUE/SAT push_expr treats None hs_color as (0, 0)/(0, 100) without crashing."""
    from custom_components.dsvdc4ha.listeners import _eval_push
    result = _derive_light_output_config("light.test", _make_state({"hs"}))
    channels = result["output"]["channels"]
    hue_ch = next(ch for ch in channels if ch["channel_type"] == OutputChannelType.HUE)
    sat_ch = next(ch for ch in channels if ch["channel_type"] == OutputChannelType.SATURATION)
    state_none = MagicMock()
    state_none.state = "on"
    state_none.attributes = {"hs_color": None, "color_mode": "hs"}
    assert _eval_push(hue_ch["push_expr"], state_none) == 0.0
    assert _eval_push(sat_ch["push_expr"], state_none) == 0.0


def test_xy_push_expr_handles_none_xy_color():
    """CIE_X/CIE_Y push_expr treats None xy_color as (0.3127, 0.3290) without crashing."""
    from custom_components.dsvdc4ha.listeners import _eval_push
    result = _derive_light_output_config("light.test", _make_state({"hs"}))
    channels = result["output"]["channels"]
    cie_x = next(ch for ch in channels if ch["channel_type"] == OutputChannelType.CIE_X)
    state_none = MagicMock()
    state_none.state = "on"
    state_none.attributes = {"xy_color": None}
    val = _eval_push(cie_x["push_expr"], state_none)
    assert val == round(0.3127 * 10000, 1)
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/test_light_mapping.py::test_full_color_channel_order_matches_pydsvdcapi tests/test_light_mapping.py::test_brightness_push_expr_returns_zero_when_off tests/test_light_mapping.py::test_brightness_push_expr_handles_none_brightness tests/test_light_mapping.py::test_hs_push_expr_handles_none_hs_color tests/test_light_mapping.py::test_xy_push_expr_handles_none_xy_color -v
```

Expected: FAIL on channel order and push_expr tests.

- [ ] **Step 3: Fix `_full_color_dimmer_output` channel order and push_exprs in `entity_mapping.py`**

Replace the full `_full_color_dimmer_output` function:

```python
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
                "push_expr": "0.0 if entity.state == 'off' else round((attrs.get('brightness') or 0) / 2.55, 1)",
            },
            {
                "channel_type": OutputChannelType.COLOR_TEMPERATURE,
                "name": "Color Temperature",
                "read_entity": entity_id,
                "push_expr": "float(attrs.get('color_temp') or 370)",
            },
            {
                "channel_type": OutputChannelType.HUE,
                "name": "Hue",
                "read_entity": entity_id,
                "push_expr": "(attrs.get('hs_color') or (0, 0))[0] if attrs.get('color_mode') in ('hs', 'rgb', 'rgbw', 'rgbww', 'xy') else 0.0",
            },
            {
                "channel_type": OutputChannelType.SATURATION,
                "name": "Saturation",
                "read_entity": entity_id,
                "push_expr": "(attrs.get('hs_color') or (0, 100))[1] if attrs.get('color_mode') in ('hs', 'rgb', 'rgbw', 'rgbww', 'xy') else 0.0",
            },
            {
                "channel_type": OutputChannelType.CIE_X,
                "name": "CIE X",
                "read_entity": entity_id,
                "push_expr": "round((attrs.get('xy_color') or (0.3127, 0.3290))[0] * 10000, 1)",
            },
            {
                "channel_type": OutputChannelType.CIE_Y,
                "name": "CIE Y",
                "read_entity": entity_id,
                "push_expr": "round((attrs.get('xy_color') or (0.3127, 0.3290))[1] * 10000, 1)",
            },
        ],
    }
```

- [ ] **Step 4: Fix BRIGHTNESS push_expr in `_dimmer_output` and `_color_temp_dimmer_output`**

In `_dimmer_output`, change the BRIGHTNESS channel's `push_expr`:
```python
"push_expr": "0.0 if entity.state == 'off' else round((attrs.get('brightness') or 0) / 2.55, 1)",
```

In `_color_temp_dimmer_output`, change the BRIGHTNESS channel's `push_expr` to the same:
```python
"push_expr": "0.0 if entity.state == 'off' else round((attrs.get('brightness') or 0) / 2.55, 1)",
```

- [ ] **Step 5: Run all light_mapping tests**

```bash
source .venv/bin/activate && pytest tests/test_light_mapping.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/entity_mapping.py tests/test_light_mapping.py
git commit -m "fix: correct FULL_COLOR_DIMMER channel order and harden push_expr for None attrs"
```

---

## Task 3: Fix `OutputChannelEntity` to use push_expr

**Files:**
- Modify: `custom_components/dsvdc4ha/sensor.py`
- Test: `tests/test_sensor.py`

### Context

`OutputChannelEntity` currently tries `float(state.state)` to get the channel value. For any entity whose state is not a plain number ("on"/"off"/"open"/"closed"), this always raises `ValueError` and the sensor stays at `None` forever.

The fix: store `push_expr` from channel data and use `_eval_push` from `listeners.py` when it's available. Fall back to `float(state.state)` for numeric-state entities (e.g., number, input_number).

- [ ] **Step 1: Write failing tests**

Add to `tests/test_sensor.py` after `test_output_channel_entity_updates`:

```python
from unittest.mock import MagicMock


def test_output_channel_entity_uses_push_expr_to_compute_value():
    """OutputChannelEntity with push_expr evaluates it instead of float(state.state)."""
    ch_data = {
        "dsIndex": 0, "name": "Brightness", "channelType": 1,
        "read_entity": "light.lamp",
        "push_expr": "100.0 if entity.state == 'on' else 0.0",
    }
    entity = OutputChannelEntity("entry1", 0, _make_vdsd(), {}, ch_data)
    state = MagicMock()
    state.state = "on"
    state.attributes = {}
    val = entity._compute_value(state)
    assert val == 100.0


def test_output_channel_entity_push_expr_off_state():
    """OutputChannelEntity push_expr correctly returns 0 for 'off' state."""
    ch_data = {
        "dsIndex": 0, "name": "Brightness", "channelType": 1,
        "read_entity": "light.lamp",
        "push_expr": "100.0 if entity.state == 'on' else 0.0",
    }
    entity = OutputChannelEntity("entry1", 0, _make_vdsd(), {}, ch_data)
    state = MagicMock()
    state.state = "off"
    state.attributes = {}
    assert entity._compute_value(state) == 0.0


def test_output_channel_entity_falls_back_to_float_without_push_expr():
    """OutputChannelEntity without push_expr uses float(state.state) for numeric states."""
    ch_data = {"dsIndex": 0, "name": "Position", "channelType": 8}
    entity = OutputChannelEntity("entry1", 0, _make_vdsd(), {}, ch_data)
    state = MagicMock()
    state.state = "75.5"
    state.attributes = {}
    assert entity._compute_value(state) == 75.5


def test_output_channel_entity_push_expr_failure_returns_none():
    """OutputChannelEntity returns None when push_expr evaluation raises."""
    ch_data = {
        "dsIndex": 0, "name": "Brightness", "channelType": 1,
        "push_expr": "1 / 0",  # always raises
    }
    entity = OutputChannelEntity("entry1", 0, _make_vdsd(), {}, ch_data)
    state = MagicMock()
    state.state = "on"
    state.attributes = {}
    assert entity._compute_value(state) is None
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/test_sensor.py::test_output_channel_entity_uses_push_expr_to_compute_value tests/test_sensor.py::test_output_channel_entity_push_expr_off_state tests/test_sensor.py::test_output_channel_entity_falls_back_to_float_without_push_expr tests/test_sensor.py::test_output_channel_entity_push_expr_failure_returns_none -v
```

Expected: FAIL — `AttributeError: 'OutputChannelEntity' object has no attribute '_compute_value'`

- [ ] **Step 3: Update `OutputChannelEntity` in `sensor.py`**

Replace the `OutputChannelEntity` class (currently lines 150–202) with:

```python
class OutputChannelEntity(DsvdcBaseEntity, SensorEntity):
    """Sensor mirroring the current value of an output channel."""

    def __init__(
        self,
        subentry_id: str,
        vdsd_index: int,
        vdsd_data: dict,
        output_data: dict,
        ch_data: dict,
    ) -> None:
        super().__init__(subentry_id, vdsd_index, vdsd_data, f"channel_{ch_data['dsIndex']}")
        self._ch_data = ch_data
        self._attr_name = ch_data.get("name", f"Channel {ch_data['dsIndex']}")
        self._attr_native_value: float | None = None
        self._source_entity_id: str | None = ch_data.get("read_entity")
        self._push_expr: str | None = ch_data.get("push_expr")

    @property
    def state(self) -> float | None:
        return self._attr_native_value

    def _compute_value(self, state) -> float | None:
        if self._push_expr:
            try:
                from .listeners import _eval_push
                return _eval_push(self._push_expr, state)
            except Exception:
                return None
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if not self._source_entity_id:
            return
        state = self.hass.states.get(self._source_entity_id)
        if state and state.state not in ("unknown", "unavailable"):
            self._attr_native_value = self._compute_value(state)
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._source_entity_id, self._handle_source_change
            )
        )

    @callback
    def _handle_source_change(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in ("unknown", "unavailable"):
            self._attr_native_value = None
        else:
            self._attr_native_value = self._compute_value(new_state)
        self.async_write_ha_state()

    def _handle_value(self, value: float) -> None:
        self._attr_native_value = value
        if self.hass:
            self.async_write_ha_state()
```

- [ ] **Step 4: Run all sensor tests**

```bash
source .venv/bin/activate && pytest tests/test_sensor.py -v
```

Expected: all pass.

- [ ] **Step 5: Run full test suite**

```bash
source .venv/bin/activate && pytest --timeout=60 -q
```

Expected: all pass (285+ tests, 0 failures).

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/sensor.py tests/test_sensor.py
git commit -m "fix: use push_expr in OutputChannelEntity to show correct channel value"
```

---

## Self-Review

**Spec coverage:**
- Bug 1 (DSS→HA entity_id): covered by Task 1 steps 3–5 ✓
- Bug 2 (_light_apply None attrs): covered by Task 1 step 3 ✓
- Bug 3 (FULL_COLOR channel order): covered by Task 2 step 3 ✓
- Bug 4 (brightness push_expr): covered by Task 2 steps 3–4 ✓
- Bug 5 (OutputChannelEntity "unknown"): covered by Task 3 ✓
- Other entity types (cover/fan/switch/valve): covered by the same entity_id injection in Task 1 ✓

**Placeholder scan:** None found — all steps contain exact code.

**Type consistency:** `_compute_value` returns `float | None` consistently; `_eval_push` returns `float` (may raise, caught to None). Consistent throughout.
