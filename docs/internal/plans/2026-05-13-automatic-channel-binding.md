# Automatic Output Channel Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically derive `apply_expr`/`push_expr` channel bindings from entity type data instead of asking the user, skipping the channel mapping UI step entirely when all channels can be auto-derived.

**Architecture:** Add `apply_expr` (Python expression → HA service call dict) and `push_expr` (Python expression → float dS value) to each channel definition in `entity_mapping.py`. Update `listeners.py` to `eval()` these expressions at runtime. Update `config_flow._build_entity_vdsd_and_continue` and `device_grouper.resolve_vdsd_plan` to copy the expressions into the channel data dict. Skip `async_step_entity_channel_mapping` automatically when all channels have `apply_expr`.

**Tech Stack:** Python 3.13, Home Assistant custom component, pydsvdcapi. Tests: pytest + pytest-homeassistant-custom-component, all in `.venv`. Run tests with: `pytest tests/ -v`

---

## Files Changed

| File | Type | Description |
|---|---|---|
| `custom_components/dsvdc4ha/entity_mapping.py` | Modified | Add `apply_expr`/`push_expr` to every output channel dict |
| `custom_components/dsvdc4ha/listeners.py` | Modified | Eval push_expr for read side; eval apply_expr for write side; fix multi-channel callback bug |
| `custom_components/dsvdc4ha/config_flow.py` | Modified | Copy exprs from channel defs; skip channel mapping step when all channels are auto-bound |
| `custom_components/dsvdc4ha/device_grouper.py` | Modified | Copy exprs from channel defs in `resolve_vdsd_plan` |
| `tests/test_listeners.py` | New | Unit tests for expression-based push and apply |
| `tests/test_device_grouper.py` | Modified | Tests for expr passthrough in `resolve_vdsd_plan` |
| `tests/test_config_flow.py` | Modified | Tests for skipping/showing channel mapping step |

---

## Expression Format

- **`apply_expr`**: Python expression string. Available names: `value` (float, 0–100, the dS channel value), `entity` (HA State object), `attrs` (shorthand for `entity.attributes`). Returns a dict: `{"domain": ..., "service": ..., "service_data": {...}}` suitable for `hass.services.async_call(**result)`.
- **`push_expr`**: Python expression string. Available names: `entity` (HA State object), `attrs` (shorthand for `entity.attributes`). Returns a float (the dS sensor/channel value to push).

Both expressions are evaluated with a safe context (`__builtins__` restricted, only `round`, `float`, `int`, `abs`, `min`, `max`, `_norm`, `_denorm` available).

`_norm(v, lo, hi)` → normalises `v` from `[lo, hi]` to `[0, 100]`.  
`_denorm(v, lo, hi)` → de-normalises `v` from `[0, 100]` to `[lo, hi]`.

---

## Task 1: Add `apply_expr`/`push_expr` to entity_mapping.py channel defs

**Files:**
- Modify: `custom_components/dsvdc4ha/entity_mapping.py` (throughout; every `"channels"` and `"channels_by_usage"` entry for output entities)

This task is **data-only** — no behavior changes. The test validates the data.

- [ ] **Step 1: Write the failing test**

Create `tests/test_entity_mapping_bindings.py`:

```python
"""Validate that all output channel defs have apply_expr/push_expr, or are known exceptions."""
from __future__ import annotations
import pytest
from custom_components.dsvdc4ha.entity_mapping import ENTITY_MAPPING

# Channel defs known to NOT have auto-binding (⚠ not natively supported in HA)
_KNOWN_UNBOUND = {
    # light/rgb channels 4,5 have cie xy bindings so all 6 are bound
}

def _collect_channel_defs() -> list[tuple[str, str | None, int, dict]]:
    """Return (domain, device_class, ch_index, ch_dict) for every output channel def."""
    result = []
    for entry in ENTITY_MAPPING:
        o = entry.get("output")
        if not o:
            continue
        domain = entry["domain"]
        dc = entry["device_class"]
        # main channels list
        for i, ch in enumerate(o.get("channels", [])):
            result.append((domain, dc, i, ch))
        # channels_by_usage
        for usage_channels in o.get("channels_by_usage", {}).values():
            for i, ch in enumerate(usage_channels):
                result.append((domain, dc, i, ch))
    return result


@pytest.mark.parametrize("domain,dc,ch_idx,ch", _collect_channel_defs())
def test_channel_has_apply_expr(domain, dc, ch_idx, ch):
    key = (domain, dc, ch_idx)
    if key in _KNOWN_UNBOUND:
        assert "apply_expr" not in ch, f"{domain}/{dc} ch{ch_idx} should not have apply_expr"
        return
    assert "apply_expr" in ch, (
        f"{domain}/{dc} ch{ch_idx} (channel_type={ch['channel_type']}) missing apply_expr"
    )
    assert isinstance(ch["apply_expr"], str) and ch["apply_expr"]


@pytest.mark.parametrize("domain,dc,ch_idx,ch", _collect_channel_defs())
def test_channel_has_push_expr(domain, dc, ch_idx, ch):
    key = (domain, dc, ch_idx)
    if key in _KNOWN_UNBOUND:
        return
    assert "push_expr" in ch, (
        f"{domain}/{dc} ch{ch_idx} (channel_type={ch['channel_type']}) missing push_expr"
    )
    assert isinstance(ch["push_expr"], str) and ch["push_expr"]
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_entity_mapping_bindings.py -v
```
Expected: many `FAILED` — channels missing `apply_expr`/`push_expr`.

- [ ] **Step 3: Update `entity_mapping.py` — add binding data to every output channel def**

The changes are purely additive: each `{"channel_type": N}` dict gains `"apply_expr"` and `"push_expr"` keys. Replace each section as shown below.

**Cover — awning** (around line 272–279): Replace the `"channels"` value with:
```python
"channels": [{"channel_type": 7,
    "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(100-value)}}",
    "push_expr": "round(100-attrs.get('current_position',0),1)"}],
```

**Cover — blind** (around line 281–293): Replace `"channels"` AND `"channels_by_usage"`:
```python
"channels": [
    {"channel_type": 8,
     "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(100-value)}}",
     "push_expr": "round(100-attrs.get('current_position',0),1)"},
    {"channel_type": 10,
     "apply_expr": "{'domain':'cover','service':'set_cover_tilt_position','service_data':{'tilt_position':round(value)}}",
     "push_expr": "attrs.get('current_tilt_position',0)"},
],
"channels_by_usage": {
    1: [
        {"channel_type": 8,
         "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(100-value)}}",
         "push_expr": "round(100-attrs.get('current_position',0),1)"},
        {"channel_type": 10,
         "apply_expr": "{'domain':'cover','service':'set_cover_tilt_position','service_data':{'tilt_position':round(value)}}",
         "push_expr": "attrs.get('current_tilt_position',0)"},
    ],
    2: [
        {"channel_type": 7,
         "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(100-value)}}",
         "push_expr": "round(100-attrs.get('current_position',0),1)"},
        {"channel_type": 9,
         "apply_expr": "{'domain':'cover','service':'set_cover_tilt_position','service_data':{'tilt_position':round(value)}}",
         "push_expr": "attrs.get('current_tilt_position',0)"},
    ],
},
```

**Cover — curtain** (around line 296–302):
```python
"channels": [{"channel_type": 8,
    "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(value)}}",
    "push_expr": "attrs.get('current_position',0)"}],
```

**Cover — damper** (around line 304–309):
```python
"channels": [{"channel_type": 14,
    "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(value)}}",
    "push_expr": "attrs.get('current_position',0)"}],
```

**Cover — door** (around line 311–318):
```python
"channels": [{"channel_type": 19,
    "apply_expr": "{'domain':'cover','service':'open_cover' if value>=1 else 'close_cover','service_data':{}}",
    "push_expr": "1 if entity.state in ('open','opening') else 0"}],
```

**Cover — garage** (around line 319–325): same as door:
```python
"channels": [{"channel_type": 19,
    "apply_expr": "{'domain':'cover','service':'open_cover' if value>=1 else 'close_cover','service_data':{}}",
    "push_expr": "1 if entity.state in ('open','opening') else 0"}],
```

**Cover — gate** (around line 327–336): positional (default function=2):
```python
"channels": [{"channel_type": 7,
    "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(100-value)}}",
    "push_expr": "round(100-attrs.get('current_position',0),1)"}],
```

**Cover — shade** (around line 338–343):
```python
"channels": [{"channel_type": 8,
    "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(value)}}",
    "push_expr": "attrs.get('current_position',0)"}],
```

**Cover — shutter** (around line 345–352):
```python
"channels": [
    {"channel_type": 7,
     "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(100-value)}}",
     "push_expr": "round(100-attrs.get('current_position',0),1)"},
    {"channel_type": 9,
     "apply_expr": "{'domain':'cover','service':'set_cover_tilt_position','service_data':{'tilt_position':round(value)}}",
     "push_expr": "attrs.get('current_tilt_position',0)"},
],
```

**Cover — window** (around line 354–363):
```python
"channels": [{"channel_type": 8,
    "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(value)}}",
    "push_expr": "attrs.get('current_position',0)"}],
```
(The optional tilt channel `{"channel_type": 10}` is handled in Tasks 4 & 5.)

**Fan** (around line 397–403):
```python
"channels": [
    {"channel_type": 12,
     "apply_expr": "{'domain':'fan','service':'set_percentage','service_data':{'percentage':round(value)}}",
     "push_expr": "attrs.get('percentage',0) or 0"},
    {"channel_type": 13,
     "apply_expr": "{'domain':'fan','service':'set_direction','service_data':{'direction':'forward' if value<=1 else 'reverse'}}",
     "push_expr": "0 if attrs.get('direction','forward')=='forward' else 2"},
],
```

**Light — None** (around line 406–412):
```python
"channels": [{"channel_type": 1,
    "apply_expr": "{'domain':'light','service':'turn_on' if value>50 else 'turn_off','service_data':{}}",
    "push_expr": "100.0 if entity.state=='on' else 0.0"}],
```

**Light — brightness** (around line 414–419):
```python
"channels": [{"channel_type": 1,
    "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'brightness':round(value*2.55)}}",
    "push_expr": "round(attrs.get('brightness',0)/2.55,1)"}],
```

**Light — color_temp** (around line 421–428):
```python
"channels": [
    {"channel_type": 1,
     "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'brightness':round(value*2.55)}}",
     "push_expr": "round(attrs.get('brightness',0)/2.55,1)"},
    {"channel_type": 4,
     "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'color_temp':round(value)}}",
     "push_expr": "attrs.get('color_temp',370)"},
],
```

**Light — rgb** (around line 430–438): replace the 6-entry channels list:
```python
"channels": [
    {"channel_type": 1,
     "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'brightness':round(value*2.55)}}",
     "push_expr": "round(attrs.get('brightness',0)/2.55,1)"},
    {"channel_type": 2,
     "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'hs_color':(value,attrs.get('hs_color',(0,100))[1])}}",
     "push_expr": "attrs.get('hs_color',(0,0))[0]"},
    {"channel_type": 3,
     "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'hs_color':(attrs.get('hs_color',(0,100))[0],value)}}",
     "push_expr": "attrs.get('hs_color',(0,100))[1]"},
    {"channel_type": 4,
     "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'color_temp':round(value)}}",
     "push_expr": "attrs.get('color_temp',370)"},
    {"channel_type": 5,
     "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'xy_color':(round(value/10000,4),attrs.get('xy_color',(0.3127,0.3290))[1])}}",
     "push_expr": "round(attrs.get('xy_color',(0.3127,0.3290))[0]*10000,1)"},
    {"channel_type": 6,
     "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'xy_color':(attrs.get('xy_color',(0.3127,0.3290))[0],round(value/10000,4))}}",
     "push_expr": "round(attrs.get('xy_color',(0.3127,0.3290))[1]*10000,1)"},
],
```

**Lock** (around line 442–447):
```python
"channels": [{"channel_type": 19,
    "apply_expr": "{'domain':'lock','service':'lock' if value==0 else 'unlock','service_data':{}}",
    "push_expr": "0 if entity.state=='locked' else 1"}],
```

**Number** (around line 455–460):
```python
"channels": [{"channel_type": 24,
    "apply_expr": "{'domain':'number','service':'set_value','service_data':{'value':round(_denorm(value,float(attrs.get('min',0)),float(attrs.get('max',100))),2)}}",
    "push_expr": "_norm(float(entity.state),float(attrs.get('min',0)),float(attrs.get('max',100)))"}],
```

**Siren** (around line 732–739):
```python
"channels": [
    {"channel_type": 19,
     "apply_expr": "{'domain':'siren','service':'turn_on' if value>=1 else 'turn_off','service_data':{}}",
     "push_expr": "1 if entity.state=='on' else 0"},
    {"channel_type": 18,
     "apply_expr": "{'domain':'siren','service':'turn_on','service_data':{'volume_level':round(value/100,2)}}",
     "push_expr": "round(attrs.get('volume_level',1)*100,1)"},
],
```

**Switch — None, outlet, switch** (around lines 741–763): all three entries:
```python
"channels": [{"channel_type": 19,
    "apply_expr": "{'domain':'switch','service':'turn_on' if value>=1 else 'turn_off','service_data':{}}",
    "push_expr": "1 if entity.state=='on' else 0"}],
```

**Valve — None and gas** (around lines 767–780):
```python
"channels": [{"channel_type": 19,
    "apply_expr": "{'domain':'valve','service':'open_valve' if value>=1 else 'close_valve','service_data':{}}",
    "push_expr": "1 if entity.state=='open' else 0"}],
```

**Valve — water and water_heater** (around lines 782–797):
```python
"channels": [{"channel_type": 23,
    "apply_expr": "{'domain':'valve','service':'set_valve_position','service_data':{'position':round(value)}}",
    "push_expr": "attrs.get('current_position',0)"}],
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_entity_mapping_bindings.py -v
```
Expected: all PASS.

- [ ] **Step 5: Run full test suite to check no regressions**

```
pytest tests/ -v
```
Expected: all 67 original tests + new binding tests PASS.

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/entity_mapping.py tests/test_entity_mapping_bindings.py
git commit -m "feat: add apply_expr/push_expr auto-binding data to all output channel defs"
```

---

## Task 2: Update listeners.py — push side (HA state → dS)

**Files:**
- Modify: `custom_components/dsvdc4ha/listeners.py`
- Create: `tests/test_listeners.py`

Add `_SAFE_EVAL_CONTEXT` and `_eval_push` helper. Update `seed_initial_values` and the read-side of `setup_output_listeners` to use `push_expr` when available, falling back to `float(state.state)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_listeners.py`:

```python
"""Tests for listeners — push_expr and apply_expr evaluation."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from custom_components.dsvdc4ha.listeners import (
    seed_initial_values,
    setup_output_listeners,
)


def _make_output_setup(channels_data: list[dict]):
    """Return (hass, api, mock_output, mock_channel) ready for setup_output_listeners."""
    hass = MagicMock()
    hass.async_create_task = MagicMock()
    api = MagicMock()
    api.report_channel_value = AsyncMock()

    mock_device = MagicMock()
    mock_vdsd = MagicMock()
    mock_output = MagicMock()
    mock_channels = {}
    for ch in channels_data:
        mc = MagicMock()
        mock_channels[ch["dsIndex"]] = mc
    mock_output.get_channel = lambda idx: mock_channels.get(idx)
    mock_vdsd.output = mock_output
    mock_device.get_vdsd.return_value = mock_vdsd
    api.get_device.return_value = mock_device
    return hass, api, mock_output, mock_channels


@pytest.mark.asyncio
async def test_seed_initial_values_uses_push_expr():
    """seed_initial_values should eval push_expr for initial channel value."""
    hass = MagicMock()
    state = MagicMock()
    state.state = "open"
    state.attributes = {"current_position": 30}
    hass.states.get.return_value = state

    api = MagicMock()
    mock_device = MagicMock()
    mock_vdsd = MagicMock()
    mock_output = MagicMock()
    mock_ch = MagicMock()
    mock_ch.update_value = AsyncMock()
    mock_output.get_channel.return_value = mock_ch
    mock_vdsd.output = mock_output
    mock_device.get_vdsd.return_value = mock_vdsd
    api.get_device.return_value = mock_device

    await seed_initial_values(hass, api, "entry1", [{
        "output": {"channels": [{
            "dsIndex": 0,
            "channelType": 8,
            "read_entity": "cover.bedroom",
            "push_expr": "round(100-attrs.get('current_position',0),1)",
        }]},
    }])

    mock_ch.update_value.assert_awaited_once_with(70.0)


@pytest.mark.asyncio
async def test_seed_initial_values_fallback_float_state():
    """Without push_expr, seed uses float(state.state)."""
    hass = MagicMock()
    state = MagicMock()
    state.state = "42.5"
    state.attributes = {}
    hass.states.get.return_value = state

    api = MagicMock()
    mock_device = MagicMock()
    mock_vdsd = MagicMock()
    mock_output = MagicMock()
    mock_ch = MagicMock()
    mock_ch.update_value = AsyncMock()
    mock_output.get_channel.return_value = mock_ch
    mock_vdsd.output = mock_output
    mock_device.get_vdsd.return_value = mock_vdsd
    api.get_device.return_value = mock_device

    await seed_initial_values(hass, api, "entry1", [{
        "output": {"channels": [{
            "dsIndex": 0,
            "channelType": 19,
            "read_entity": "sensor.power",
        }]},
    }])

    mock_ch.update_value.assert_awaited_once_with(42.5)


def test_push_expr_state_change_fires_report():
    """State change with push_expr should call report_channel_value with eval'd value."""
    channels_data = [{"dsIndex": 0, "channelType": 8,
                      "read_entity": "cover.blind",
                      "push_expr": "round(100-attrs.get('current_position',0),1)"}]
    hass, api, mock_output, mock_channels = _make_output_setup(channels_data)

    registered_cbs = []
    def _track(h, entity_id, cb):
        registered_cbs.append(cb)
        return lambda: None

    with patch("custom_components.dsvdc4ha.listeners.async_track_state_change_event",
               side_effect=_track):
        setup_output_listeners(hass, api, "entry1", [{
            "output": {"channels": channels_data},
        }])

    assert len(registered_cbs) == 1

    new_state = MagicMock()
    new_state.state = "open"
    new_state.attributes = {"current_position": 70}
    event = MagicMock()
    event.data = {"new_state": new_state}

    registered_cbs[0](event)

    hass.async_create_task.assert_called_once()
    api.report_channel_value.assert_called_once_with(mock_channels[0], 30.0)


def test_push_expr_fallback_to_float_state():
    """Without push_expr, state.state is cast to float."""
    channels_data = [{"dsIndex": 0, "channelType": 19,
                      "read_entity": "switch.light",
                      "push_expr": None}]
    # Remove push_expr key entirely to test fallback
    channels_data[0].pop("push_expr")
    hass, api, mock_output, mock_channels = _make_output_setup(channels_data)

    registered_cbs = []
    with patch("custom_components.dsvdc4ha.listeners.async_track_state_change_event",
               side_effect=lambda h, e, cb: (registered_cbs.append(cb), lambda: None)[1]):
        setup_output_listeners(hass, api, "entry1", [{"output": {"channels": channels_data}}])

    new_state = MagicMock()
    new_state.state = "75.0"
    new_state.attributes = {}
    event = MagicMock()
    event.data = {"new_state": new_state}
    registered_cbs[0](event)

    api.report_channel_value.assert_called_once_with(mock_channels[0], 75.0)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_listeners.py -v
```
Expected: FAIL — functions don't evaluate push_expr yet.

- [ ] **Step 3: Add `_SAFE_EVAL_CONTEXT` and `_eval_push` to listeners.py**

In `listeners.py`, add after the imports block (before `_LOGGER`):

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


def _eval_push(expr: str, state) -> float:
    """Evaluate a push_expr with entity/attrs in context. Returns float."""
    ctx = dict(_SAFE_EVAL_CONTEXT)
    ctx["entity"] = state
    ctx["attrs"] = state.attributes if state else {}
    return float(eval(expr, ctx))  # noqa: S307
```

- [ ] **Step 4: Update `seed_initial_values` to use push_expr**

Replace the channel-value block inside `seed_initial_values` (lines ~164–176 in current file):

```python
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
                            _LOGGER.debug("push_expr eval failed during seed: %s", push_expr)
                    else:
                        try:
                            ch_value = float(state.state)
                        except ValueError:
                            pass
            await ch.update_value(ch_value)
```

- [ ] **Step 5: Update the read-side of `setup_output_listeners` to use push_expr**

The current read-side callback (inside `setup_output_listeners`, lines ~210–222) uses `float(new_state.state)`. Replace the `if read_entity:` block with:

```python
            if read_entity:
                push_expr = ch_data.get("push_expr")
                if push_expr:
                    @callback
                    def _on_channel_state_expr(
                        event: Event,
                        _ch=channel,
                        _expr=push_expr,
                        _entity_id=read_entity,
                    ) -> None:
                        new_state = event.data.get("new_state")
                        if not new_state or new_state.state in ("unknown", "unavailable"):
                            return
                        try:
                            val = _eval_push(_expr, new_state)
                            hass.async_create_task(api.report_channel_value(_ch, val))
                        except Exception:
                            _LOGGER.debug("push_expr eval failed: %s", _expr)

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
```

- [ ] **Step 6: Run tests to verify they pass**

```
pytest tests/test_listeners.py -v
```
Expected: all 4 new tests PASS.

- [ ] **Step 7: Run full suite**

```
pytest tests/ -v
```
Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add custom_components/dsvdc4ha/listeners.py tests/test_listeners.py
git commit -m "feat: eval push_expr for HA→dS channel value derivation in listeners"
```

---

## Task 3: Update listeners.py — apply side (dS → HA) and fix multi-channel callback

**Files:**
- Modify: `custom_components/dsvdc4ha/listeners.py`
- Modify: `tests/test_listeners.py`

Add `_eval_apply` helper. Restructure `setup_output_listeners` to set **one** callback per output (not per channel) that dispatches based on `channelType`, fixing a pre-existing bug where multiple channels on one output would each overwrite the callback leaving only the last one active.

- [ ] **Step 1: Write the failing tests** (add to `tests/test_listeners.py`)

```python
@pytest.mark.asyncio
async def test_apply_expr_calls_ha_service():
    """apply_expr is eval'd with channel value and correct HA service is called."""
    channels_data = [{"dsIndex": 0, "channelType": 8,
                      "read_entity": "cover.blind",
                      "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(100-value)}}"}]
    hass, api, mock_output, mock_channels = _make_output_setup(channels_data)
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    captured_callback = []
    api.set_channel_applied_callback.side_effect = lambda out, cb: captured_callback.append(cb)

    with patch("custom_components.dsvdc4ha.listeners.async_track_state_change_event",
               return_value=lambda: None):
        setup_output_listeners(hass, api, "entry1", [{"output": {"channels": channels_data}}])

    assert len(captured_callback) == 1
    await captured_callback[0](mock_output, {8: 25.0})  # channelType 8, value=25 → position=75

    hass.services.async_call.assert_awaited_once_with(
        domain="cover",
        service="set_cover_position",
        service_data={"position": 75},
        blocking=False,
    )


@pytest.mark.asyncio
async def test_apply_expr_multi_channel_single_callback():
    """Two channels with apply_expr → ONE callback registered, both channels handled."""
    channels_data = [
        {"dsIndex": 0, "channelType": 1,
         "read_entity": "light.rgb",
         "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'brightness':round(value*2.55)}}"},
        {"dsIndex": 1, "channelType": 2,
         "read_entity": "light.rgb",
         "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'hs_color':(value,50)}}"},
    ]
    hass, api, mock_output, mock_channels = _make_output_setup(channels_data)
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    captured_callbacks = []
    api.set_channel_applied_callback.side_effect = lambda out, cb: captured_callbacks.append(cb)

    with patch("custom_components.dsvdc4ha.listeners.async_track_state_change_event",
               return_value=lambda: None):
        setup_output_listeners(hass, api, "entry1", [{"output": {"channels": channels_data}}])

    assert len(captured_callbacks) == 1  # ONE callback for the whole output

    # Fire update for channel type 1 (brightness), value=100
    await captured_callbacks[0](mock_output, {1: 100.0})
    assert hass.services.async_call.await_count == 1
    assert hass.services.async_call.call_args_list[0].kwargs["service_data"] == {"brightness": 255}

    # Fire update for channel type 2 (hue), value=180
    await captured_callbacks[0](mock_output, {2: 180.0})
    assert hass.services.async_call.await_count == 2
    assert hass.services.async_call.call_args_list[1].kwargs["service_data"] == {"hs_color": (180.0, 50)}
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_listeners.py::test_apply_expr_calls_ha_service tests/test_listeners.py::test_apply_expr_multi_channel_single_callback -v
```
Expected: FAIL.

- [ ] **Step 3: Add `_eval_apply` and restructure the write side in `setup_output_listeners`**

In `listeners.py`, add `_eval_apply` helper after `_eval_push`:

```python
def _eval_apply(expr: str, value: float, state) -> dict:
    """Evaluate an apply_expr with value/entity/attrs in context. Returns HA action dict."""
    ctx = dict(_SAFE_EVAL_CONTEXT)
    ctx["value"] = value
    ctx["entity"] = state
    ctx["attrs"] = state.attributes if state else {}
    return eval(expr, ctx)  # noqa: S307
```

Then replace the entire write-side block in `setup_output_listeners`. Remove the old per-channel `if write_action:` block and replace the full channel loop with this restructured version:

```python
        # Collect per-channel bindings keyed by channelType integer
        expr_bindings: list[tuple[int, str, str | None]] = []  # (ch_type, apply_expr, read_entity)
        static_action: dict | None = None

        for ch_data in output_data.get("channels", []):
            read_entity_ch = ch_data.get("read_entity")
            apply_expr = ch_data.get("apply_expr")
            ch_type = ch_data["channelType"]

            if apply_expr:
                expr_bindings.append((ch_type, apply_expr, read_entity_ch))
            elif ch_data.get("write_action"):
                # Legacy: static action dict from manual channel mapping
                static_action = ch_data["write_action"]

        if expr_bindings:
            async def _on_channel_applied_expr(
                _out,
                channel_updates: dict,
                _bindings: list = expr_bindings,
                _read_entity: str | None = (expr_bindings[0][2] if expr_bindings else None),
            ) -> None:
                state = hass.states.get(_read_entity) if _read_entity else None
                for ch_type, expr, _re in _bindings:
                    if ch_type not in channel_updates:
                        continue
                    ch_value = channel_updates[ch_type]
                    try:
                        action = _eval_apply(expr, ch_value, state)
                        await hass.services.async_call(**action, blocking=False)
                    except Exception:
                        _LOGGER.debug("apply_expr eval failed: %s", expr)

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

Note: the read side (push) loop from Task 2 is still unchanged above the write side. The complete new structure for the channel iteration in `setup_output_listeners` is:

```python
        for ch_data in output_data.get("channels", []):
            read_entity = ch_data.get("read_entity")
            ds_index = ch_data["dsIndex"]
            channel = output.get_channel(ds_index)
            if not channel:
                continue

            # Read side: HA → dS
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
                            _LOGGER.debug("push_expr eval failed: %s", _expr)
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

        # Write side: dS → HA (one callback per output, handles all channels)
        expr_bindings: list[tuple[int, str, str | None]] = []
        static_action: dict | None = None
        for ch_data in output_data.get("channels", []):
            ch_type = ch_data["channelType"]
            apply_expr = ch_data.get("apply_expr")
            if apply_expr:
                expr_bindings.append((ch_type, apply_expr, ch_data.get("read_entity")))
            elif ch_data.get("write_action"):
                static_action = ch_data["write_action"]

        if expr_bindings:
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
                        _LOGGER.debug("apply_expr eval failed: %s", expr)
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

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_listeners.py -v
```
Expected: all 6 tests PASS.

- [ ] **Step 5: Run full suite**

```
pytest tests/ -v
```
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/listeners.py tests/test_listeners.py
git commit -m "feat: eval apply_expr for dS→HA channel apply; fix multi-channel callback overwrite"
```

---

## Task 4: Update config_flow.py — copy binding data; skip channel mapping when auto-bound

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py`
- Modify: `tests/test_config_flow.py`

In `_build_entity_vdsd_and_continue`: copy `apply_expr`/`push_expr` from each channel def into the channel data dict. Skip `async_step_entity_channel_mapping` when every channel has `apply_expr`. Also update the optional-tilt channel append to include binding expressions.

- [ ] **Step 1: Write the failing tests** (add to `tests/test_config_flow.py`)

```python
@pytest.mark.asyncio
async def test_channel_mapping_skipped_when_all_channels_auto_bound():
    """When all output channels have apply_expr, entity_channel_mapping step is skipped."""
    flow = VdsdSubentryFlowHandler()
    flow.hass = MagicMock()
    flow.hass.states.get.return_value = None
    flow.context = {}

    # Patch to avoid actually running model_features
    with patch.object(flow, "async_step_model_features", new=AsyncMock(
        return_value={"type": "form", "step_id": "model_features"}
    )):
        result = await flow.async_step_entity_user_input(user_input={
            "entity_id": "switch.lights",
        })

    assert result["step_id"] == "model_features"


@pytest.mark.asyncio
async def test_channel_mapping_shown_when_channel_lacks_apply_expr():
    """When any output channel lacks apply_expr, entity_channel_mapping step is shown."""
    flow = VdsdSubentryFlowHandler()
    flow.hass = MagicMock()
    flow.hass.states.get.return_value = None
    flow.context = {}

    # Manually set up a channel without apply_expr (simulates a manually configured vdSD)
    flow._current_channels = [{"dsIndex": 0, "channelType": 19, "read_entity": "switch.x",
                                "write_action": None}]  # no apply_expr
    flow._current_output = {"channels": flow._current_channels}

    result = await flow.async_step_entity_channel_mapping(user_input=None)
    assert result["step_id"] == "entity_channel_mapping"


@pytest.mark.asyncio
async def test_channels_contain_apply_expr_and_push_expr():
    """Channels built from a switch entity have apply_expr and push_expr copied in."""
    from custom_components.dsvdc4ha.entity_mapping import ENTITY_MAPPING

    flow = VdsdSubentryFlowHandler()
    flow.hass = MagicMock()
    flow.hass.states.get.return_value = None
    flow.context = {}
    flow._current_entity_id = "switch.kitchen"

    with patch.object(flow, "async_step_model_features", new=AsyncMock(
        return_value={"type": "form", "step_id": "model_features"}
    )):
        result = await flow.async_step_entity_user_input(user_input={"entity_id": "switch.kitchen"})

    # Check channels have binding data
    assert flow._current_channels
    for ch in flow._current_channels:
        assert "apply_expr" in ch, f"Channel {ch} missing apply_expr"
        assert "push_expr" in ch, f"Channel {ch} missing push_expr"
```

Note: these tests depend on the existing flow setup. The exact test structure follows the pattern in the existing `test_config_flow.py`. You may need to set `flow._current_entity_id`, `flow._current_mapping`, etc. — look at existing tests like `test_entity_user_input_*` for the pattern used. Adjust the test setup to match.

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_config_flow.py -k "channel_mapping_skipped or channel_mapping_shown or channels_contain_apply" -v
```
Expected: FAIL.

- [ ] **Step 3: Update channel building in `_build_entity_vdsd_and_continue` to copy exprs**

In `config_flow.py`, find the channel list comprehension (around lines 1049–1061):

```python
            channels = [
                {
                    "dsIndex": i,
                    "channelType": ch["channel_type"],
                    "name": _CHANNEL_TYPE_LABELS.get(ch["channel_type"], f"Channel {i}"),
                    "min": 0.0,
                    "max": 100.0,
                    "resolution": 0.4,
                    "read_entity": entity_id,  # pre-populate with selected entity
                    "write_action": None,
                }
                for i, ch in enumerate(channels_def)
            ]
```

Replace with:

```python
            channels = [
                {
                    "dsIndex": i,
                    "channelType": ch["channel_type"],
                    "name": _CHANNEL_TYPE_LABELS.get(ch["channel_type"], f"Channel {i}"),
                    "min": 0.0,
                    "max": 100.0,
                    "resolution": 0.4,
                    "read_entity": entity_id,
                    "write_action": None,
                    **({"apply_expr": ch["apply_expr"]} if ch.get("apply_expr") else {}),
                    **({"push_expr": ch["push_expr"]} if ch.get("push_expr") else {}),
                }
                for i, ch in enumerate(channels_def)
            ]
```

- [ ] **Step 4: Update the optional-tilt append to include binding expressions**

Find (in `config_flow.py`, around line 1041):

```python
            if o.get("optional_tilt") and user_input.get("has_tilt"):
                channels_def = channels_def + [{"channel_type": 10}]  # SHADE_OPENING_ANGLE_INDOOR
```

Replace with:

```python
            if o.get("optional_tilt") and user_input.get("has_tilt"):
                channels_def = channels_def + [{
                    "channel_type": 10,
                    "apply_expr": "{'domain':'cover','service':'set_cover_tilt_position','service_data':{'tilt_position':round(value)}}",
                    "push_expr": "attrs.get('current_tilt_position',0)",
                }]
```

- [ ] **Step 5: Update the routing logic after channel building**

Find (around lines 1083–1085):

```python
        if vdsd["output"] and self._current_channels:
            return await self.async_step_entity_channel_mapping()
        return await self.async_step_model_features()
```

Replace with:

```python
        if vdsd["output"] and self._current_channels:
            all_auto = all(ch.get("apply_expr") for ch in self._current_channels)
            if not all_auto:
                return await self.async_step_entity_channel_mapping()
        return await self.async_step_model_features()
```

- [ ] **Step 6: Run tests to verify they pass**

```
pytest tests/test_config_flow.py -k "channel_mapping_skipped or channel_mapping_shown or channels_contain_apply" -v
```
Expected: PASS.

- [ ] **Step 7: Run full suite**

```
pytest tests/ -v
```
Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py tests/test_config_flow.py
git commit -m "feat: copy auto-binding exprs into channel data; skip channel mapping step when all auto-bound"
```

---

## Task 5: Update device_grouper.py — copy binding data in `resolve_vdsd_plan`

**Files:**
- Modify: `custom_components/dsvdc4ha/device_grouper.py`
- Modify: `tests/test_device_grouper.py`

In `resolve_vdsd_plan`, copy `apply_expr`/`push_expr` from channel defs into the channel data dict when building vdSD output channels. Also update the optional-tilt append.

- [ ] **Step 1: Write the failing tests** (add to `tests/test_device_grouper.py`)

```python
def test_resolve_vdsd_plan_copies_apply_expr_and_push_expr():
    """resolve_vdsd_plan copies apply_expr/push_expr from channel defs into channel data."""
    mapping = {
        "primary_group": 1,
        "output": {
            "function": 1, "output_usage": 1, "groups": [1], "default_group": 1,
            "variable_ramp": True, "mode": 2,
            "channels": [{
                "channel_type": 1,
                "apply_expr": "{'domain':'light','service':'turn_on','service_data':{'brightness':round(value*2.55)}}",
                "push_expr": "round(attrs.get('brightness',0)/2.55,1)",
            }],
        },
    }
    e = _entity("light.lamp", "light", mapping)
    plan = VdsdPlan(primary_group=1, name="Test — Light", output_entity=e)

    vdsd = resolve_vdsd_plan(plan, "Test", "Vendor", "Model", {})

    channels = vdsd["output"]["channels"]
    assert len(channels) == 1
    assert channels[0]["apply_expr"] == "{'domain':'light','service':'turn_on','service_data':{'brightness':round(value*2.55)}}"
    assert channels[0]["push_expr"] == "round(attrs.get('brightness',0)/2.55,1)"


def test_resolve_vdsd_plan_optional_tilt_has_binding():
    """Optional tilt channel added via has_tilt includes apply_expr/push_expr."""
    mapping = {
        "primary_group": 3,
        "output": {
            "function": 2, "output_usage": 1, "groups": [3], "default_group": 3,
            "variable_ramp": True, "mode": 2, "optional_tilt": True,
            "channels": [{
                "channel_type": 8,
                "apply_expr": "{'domain':'cover','service':'set_cover_position','service_data':{'position':round(value)}}",
                "push_expr": "attrs.get('current_position',0)",
            }],
        },
    }
    e = _entity("cover.window", "cover", mapping)
    plan = VdsdPlan(
        primary_group=3, name="Test — Climate",
        output_entity=e,
        user_choices={"cover.window": {"has_tilt": True}},
    )

    vdsd = resolve_vdsd_plan(plan, "Test", "Vendor", "Model", {})

    channels = vdsd["output"]["channels"]
    assert len(channels) == 2  # main + tilt
    tilt_ch = channels[1]
    assert tilt_ch["channelType"] == 10
    assert "apply_expr" in tilt_ch
    assert "push_expr" in tilt_ch


def test_resolve_vdsd_plan_channel_without_binding_stays_clean():
    """Channels without apply_expr/push_expr don't get those keys added."""
    mapping = {
        "primary_group": 1,
        "output": {
            "function": 1, "output_usage": 1, "groups": [1], "default_group": 1,
            "variable_ramp": True, "mode": 2,
            "channels": [{"channel_type": 1}],  # no binding
        },
    }
    e = _entity("light.lamp", "light", mapping)
    plan = VdsdPlan(primary_group=1, name="Test", output_entity=e)

    vdsd = resolve_vdsd_plan(plan, "Test", "Vendor", "Model", {})

    channels = vdsd["output"]["channels"]
    assert "apply_expr" not in channels[0]
    assert "push_expr" not in channels[0]
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_device_grouper.py::test_resolve_vdsd_plan_copies_apply_expr_and_push_expr tests/test_device_grouper.py::test_resolve_vdsd_plan_optional_tilt_has_binding tests/test_device_grouper.py::test_resolve_vdsd_plan_channel_without_binding_stays_clean -v
```
Expected: FAIL (first two tests missing exprs, third passes or fails depending on current code).

- [ ] **Step 3: Update channel building in `resolve_vdsd_plan`**

In `device_grouper.py`, find the channel list comprehension (lines 266–278):

```python
        channels = [
            {
                "dsIndex": i,
                "channelType": ch["channel_type"],
                "name": CHANNEL_TYPE_LABELS.get(ch["channel_type"], f"Channel {i}"),
                "min": 0.0,
                "max": 100.0,
                "resolution": 0.4,
                "read_entity": e.entity_id,
                "write_action": None,
            }
            for i, ch in enumerate(channels_def)
        ]
```

Replace with:

```python
        channels = [
            {
                "dsIndex": i,
                "channelType": ch["channel_type"],
                "name": CHANNEL_TYPE_LABELS.get(ch["channel_type"], f"Channel {i}"),
                "min": 0.0,
                "max": 100.0,
                "resolution": 0.4,
                "read_entity": e.entity_id,
                "write_action": None,
                **({"apply_expr": ch["apply_expr"]} if ch.get("apply_expr") else {}),
                **({"push_expr": ch["push_expr"]} if ch.get("push_expr") else {}),
            }
            for i, ch in enumerate(channels_def)
        ]
```

- [ ] **Step 4: Update the optional-tilt append in `resolve_vdsd_plan`**

Find (line 264 in `device_grouper.py`):

```python
        if o.get("optional_tilt") and choices.get("has_tilt"):
            channels_def = channels_def + [{"channel_type": 10}]
```

Replace with:

```python
        if o.get("optional_tilt") and choices.get("has_tilt"):
            channels_def = channels_def + [{
                "channel_type": 10,
                "apply_expr": "{'domain':'cover','service':'set_cover_tilt_position','service_data':{'tilt_position':round(value)}}",
                "push_expr": "attrs.get('current_tilt_position',0)",
            }]
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_device_grouper.py -v
```
Expected: all tests PASS (19 existing + 3 new = 22).

- [ ] **Step 6: Run full suite**

```
pytest tests/ -v
```
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add custom_components/dsvdc4ha/device_grouper.py tests/test_device_grouper.py
git commit -m "feat: copy auto-binding exprs into channel data in resolve_vdsd_plan"
```

---

## Self-Review Notes

**Spec coverage check:**
- ✅ Auto-derive bindings from entity type → entity_mapping.py data + listeners.py eval
- ✅ Only ask user when not auto-derivable → config_flow skips step when all channels have `apply_expr`
- ✅ Both entity-based single-vdSD flow AND multi-vdSD HA device flow covered (config_flow + device_grouper)
- ✅ Initial value seeding uses push_expr (seed_initial_values)
- ✅ Multi-channel callback bug fixed (one callback per output, not per channel)

**Known limitations in scope:**
- Cover gate with `function_choices`: auto-binding uses the default positional function (2). If user picks function=0 (on/off), the binding is incorrect. The user can override via reconfigure.
- Light channels 4 (CIE_X) and 5 (CIE_Y) require dividing/multiplying by 10000 since HA uses 0–1 range and dS uses 0–10000 range — this is encoded in the apply_expr/push_expr directly.

**Type consistency check:** All uses of `apply_expr`/`push_expr` as string keys are consistent across entity_mapping.py, listeners.py, config_flow.py, device_grouper.py, and all test files.
