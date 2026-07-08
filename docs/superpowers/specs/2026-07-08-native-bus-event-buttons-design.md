# Native Bus Event Button Support — Design Spec

## Goal

Extend dsvdc4ha to support physical buttons from integrations that fire raw events on the HA event bus rather than exposing HA entities. Covers six integrations: KNX, ZHA, deCONZ, Lutron Caseta, dingz, and Homematic. The existing `from_entity` creation path is extended to also handle these virtual button types without introducing a new top-level creation mode.

## Architecture

Two orthogonal additions:

1. **Virtual entity types** in `entity_mapping.py` — six new entries with `domain: "bus_event"`. These carry the same `button` config dict as existing button entries, plus a `bus_event` block describing the HA event type, discriminator fields, and default click mapping.

2. **Bus event listener** in `listeners.py` — `setup_bus_event_listeners()` registers `hass.bus.async_listen()` for buttons with `callbackType: "bus_event"`, translating raw event payloads to dS click types via either a static map (direct-mode) or a timing state machine (timed-mode).

The `ButtonEventTranslator` in `button_translator.py` gains a standalone `BusEventTimingEngine` class extracted from its existing binary-sensor timing logic. Bus-event buttons in timed mode feed press/release signals into this engine rather than calling it via HA state listeners.

---

## Tech Stack

- Python 3.13, Home Assistant custom component
- pydsvdcapi `ButtonInput`, `report_button_click`
- `hass.bus.async_listen` (new — not currently used anywhere in the integration)
- dS timing constants from ds-basics.pdf §10.1.1 Table 8 (already live in `button_translator.py`)

---

## File Structure

| File | Change |
|---|---|
| `entity_mapping.py` | Add 6 bus-event entries |
| `config_flow.py` | Extend entity-type picker; add discriminator, count, topology steps |
| `listeners.py` | Add `setup_bus_event_listeners()` |
| `button_translator.py` | Extract `BusEventTimingEngine` from binary-sensor path |
| `strings.json` | Labels and hint text for new config flow steps |
| `tests/test_button_translator.py` | Timing engine unit tests |
| `tests/test_listeners.py` | Bus event listener tests |
| `tests/test_entity_mapping_bindings.py` | Validate new entries |
| `tests/test_config_flow.py` | New config flow steps |

---

## Section 1 — entity_mapping.py additions

### Bus-event entry schema

Each entry adds a `bus_event` block alongside the existing `button` block:

```python
{
    "domain": "bus_event",
    "integration": "<name>",          # e.g. "knx"
    "model": "KNX Button",
    "model_uid": "ha-bus-event-knx",
    "vendor_name": "KNX",
    "primary_group": ColorGroup.BLACK,
    "prefer_event_entity": False,     # True → show guidance banner in config flow
    "bus_event": {
        "event_type": "knx_event",
        "discriminator_fields": [
            {"key": "destination", "label": "KNX Group Address", "example": "1/2/3"},
        ],
        "click_field": "value",        # field in event.data that holds the raw click value
        "bus_event_mode": "timed",     # "direct" or "timed"
        "default_click_map": {1: "press", 0: "release"},
    },
    "button": {
        "button_type": ButtonType.SINGLE_PUSHBUTTON,
        "group": ButtonGroup.JOKER,
        "group_choices": _BTN_GROUP_CHOICES,
        "function": ButtonFunctionJoker.APP,
        "mode": ButtonMode.STANDARD,
        "supports_local_key_mode": False,
        "calls_present": False,
    },
}
```

### Six entries

#### KNX
```python
"integration": "knx",
"prefer_event_entity": False,
"bus_event": {
    "event_type": "knx_event",
    "discriminator_fields": [
        {"key": "destination", "label": "KNX Group Address", "example": "1/2/3"},
    ],
    "click_field": "value",
    "bus_event_mode": "timed",
    "default_click_map": {1: "press", 0: "release"},
}
```

#### ZHA
```python
"integration": "zha",
"prefer_event_entity": True,
"bus_event": {
    "event_type": "zha_event",
    "discriminator_fields": [
        {"key": "device_ieee", "label": "Device IEEE Address", "example": "00:17:88:01:04:xx:xx:xx"},
        {"key": "endpoint_id", "label": "Endpoint ID (leave blank for any)", "example": "1", "optional": True},
    ],
    "click_field": "command",
    "bus_event_mode": "direct",
    "default_click_map": {
        "toggle": 0, "press": 0, "short_release": 0, "single": 0,
        "double": 1, "double_press": 1,
        "triple_press": 2,
        "quadruple_press": 3,
        "long_press": 4, "move": 4, "move_with_on_off": 4, "hold": 4,
        "hold_repeat": 5, "repeat": 5,
        "long_release": 6, "stop": 6, "stop_with_on_off": 6,
        "single_click": 7,
        "double_click": 8,
        "triple_click": 9,
    },
}
```

#### deCONZ
```python
"integration": "deconz",
"prefer_event_entity": True,
"bus_event": {
    "event_type": "deconz_event",
    "discriminator_fields": [
        {"key": "unique_id", "label": "Sensor unique_id", "example": "00:0d:6f:00:0f:xx:xx:xx-01-1000"},
    ],
    "click_field": "event",
    "bus_event_mode": "direct",
    # Keys are full event codes (button_number * 1000 + event_suffix).
    # default_click_map covers button 1 (1xxx); per-button maps are
    # generated at creation time for each button index.
    "default_click_map": {
        # button 1 — template; creator substitutes Nxxx for button N
        1002: 0,   # short release → TIP_1X
        1004: 1,   # double press  → TIP_2X
        1001: 4,   # hold          → HOLD_START
        1003: 6,   # long release  → HOLD_END
    },
    "event_code_button_stride": 1000,  # button_number * stride + suffix
}
```

#### Lutron Caseta
```python
"integration": "lutron_caseta",
"prefer_event_entity": True,
"bus_event": {
    "event_type": "lutron_caseta_button_event",
    "discriminator_fields": [
        {"key": "serial", "label": "Device Serial Number", "example": "12345678"},
        {"key": "button_number", "label": "Button Number (0-based)", "example": "0"},
    ],
    "click_field": "action",
    "bus_event_mode": "timed",
    "default_click_map": {"press": "press", "release": "release"},
}
```

#### dingz
```python
"integration": "dingz",
"prefer_event_entity": False,
"bus_event": {
    "event_type": "dingz_event",
    "discriminator_fields": [
        {"key": "unique_id", "label": "dingz Host / unique_id", "example": "aabbccddeeff"},
        {"key": "index", "label": "Button Index (1–4)", "example": "1"},
    ],
    "click_field": "action",
    "bus_event_mode": "direct",
    "default_click_map": {
        "single": 0,   # TIP_1X
        "double": 1,   # TIP_2X
        "triple": 2,   # TIP_3X
        "long":   4,   # HOLD_START (no release event — known limitation)
    },
}
```

#### Homematic
```python
"integration": "homematic",
"prefer_event_entity": False,
"bus_event": {
    "event_type": "homematic_keypress",
    "discriminator_fields": [
        {"key": "name", "label": "Device + Channel", "example": "KEQ1234567:1"},
    ],
    "click_field": "param",
    "bus_event_mode": "direct",
    "default_click_map": {
        "PRESS_SHORT":        7,   # CLICK_1X
        "PRESS_LONG":         4,   # HOLD_START
        "PRESS_CONT":         5,   # HOLD_REPEAT
        "PRESS_LONG_RELEASE": 6,   # HOLD_END
    },
}
```

---

## Section 2 — Config flow changes

### Renamed step

The `from_entity` mode is renamed to `"from_entity_or_bus_event"` internally. Its display label becomes **"From Entity / Bus Event"**. All existing behaviour for real entity selections is unchanged.

### Entity-type picker extension

The step that currently lists HA domain/device-class pairs is extended. After the real entity types, a separator followed by six bus-event entries appears:

```
─── Native Bus Event Buttons ───────────────────
  KNX Button (native bus event)
  ZHA Button (native bus event — event entity preferred)
  deCONZ Button (native bus event — event entity preferred)
  Lutron Caseta Button (native bus event — event entity preferred)
  dingz Button (native bus event)
  Homematic Button (native bus event)
```

The three `prefer_event_entity` entries show the parenthetical nudge in their label.

### New step: discriminator form (`async_step_bus_event_discriminator`)

Shown instead of the HA entity picker when a bus-event type is selected.

For `prefer_event_entity` integrations an info box appears:

> *"[Integration] now exposes HA event entities for physical buttons. Using an event entity (via the entity picker above) is simpler and more reliable. Use this native bus event path only if your firmware predates event entity support."*

Below the info box: integration-specific labelled fields as defined by `discriminator_fields` in the entity mapping entry. Optional fields show "(leave blank for any)" in their label.

All field values are stored as strings and converted to the correct type (int/str) at listener setup time.

### New step: button count (`async_step_bus_event_count`)

Single number selector (range 1–8):

> *"How many physical buttons does this device have?"*

If the answer is 1, the topology step is skipped and the wizard proceeds directly to button-group/function config.

### New step: button topology (`async_step_bus_event_topology`) — skipped when count = 1

Two-option select:

> *"Are these buttons independent, or part of a logical button group?"*
>
> - **Independent** — each button acts on its own and will become a separate dS device
> - **Part of a logical button group** *(e.g. UP/DOWN, UP/DOWN/CENTER, UP/DOWN/LEFT/RIGHT/CENTER)* — the buttons act together and will form a single dS device

### Branch A — Independent buttons

For each button index 0…N−1, a sub-form asks for its **per-button discriminator value**: the single field within `discriminator_fields` that varies per button (e.g. `button_number` for Lutron, `index` for dingz, `destination` group address for KNX).

Each button produces a **separate vdSD** with one `ButtonInput`. The N vdSDs each go through the existing button-group/function/model-features/naming steps.

### Branch B — Button group

One vdSD is produced with N `ButtonInput` entries. An assignment step asks which physical button index maps to which dS function role (UP, DOWN, CENTER, etc.), with available roles derived from the button count. Function values are pre-populated from dS button-group conventions and can be adjusted.

### Downstream steps (shared)

After either branch: existing `async_step_model_features` → naming → save. No changes to these steps.

---

## Section 3 — Storage format

Buttons created via the bus-event path add three keys to the standard button dict stored in `vdsds[n]["buttons"][m]`:

```python
{
    # --- all existing fields unchanged ---
    "dsIndex": 0,
    "name": "KNX Button 1/2/3",
    "buttonType": 1,
    "group": 8,
    "function": 5,
    "mode": 1,
    "channel": 0,
    "supportsLocalKeyMode": False,
    "setsLocalPriority": False,
    "callsPresent": False,
    "buttonID": 0,
    # --- new ---
    "callbackType": "bus_event",
    "callback_entity": None,              # unused; kept for schema consistency
    "bus_event_type": "knx_event",
    "bus_event_filter": {"destination": "1/2/3"},   # all must match event.data
    "bus_event_click_field": "value",
    "bus_event_mode": "timed",            # "direct" or "timed"
    "bus_event_click_map": {1: "press", 0: "release"},  # raw value → ct int or sentinel
}
```

`bus_event_filter` is a flat dict. The listener ANDs all entries — the event is dropped unless every key/value pair matches `event.data`.

For deCONZ multi-button devices, the per-button `bus_event_filter` includes `unique_id` and the `bus_event_click_map` contains the full event codes for that specific button, generated at creation time using: `code = button_index * event_code_button_stride + suffix`, where the suffixes are 2 (short release→TIP_1X), 4 (double→TIP_2X), 1 (hold→HOLD_START), 3 (long release→HOLD_END). Example for button 2 (index 2, stride 1000): `{2002: 0, 2004: 1, 2001: 4, 2003: 6}`.

---

## Section 4 — `button_translator.py` — BusEventTimingEngine

### Extraction

The timing state machine in `ButtonEventTranslator._setup_binary_sensor()` / `_bs_on()` / `_bs_off()` / `_hold_sequence()` / `_accumulate()` is extracted into a new class `BusEventTimingEngine` in the same file.

```python
class BusEventTimingEngine:
    """Signal-driven dS timing state machine (Table 8, ds-basics.pdf §10.1.1).

    The caller feeds press/release signals; the engine fires the
    appropriate dS click-type via *on_click*.

    signal_press()   — button went active (H starts)
    signal_release() — button went inactive (H ends); optional.
                       If never called, each press is treated as an
                       instantaneous tip and tips accumulate within
                       the 800 ms inter-tip window.
    """

    def __init__(self, hass: HomeAssistant, on_click: Callable[[int], Awaitable[None]]) -> None:
        ...

    def signal_press(self) -> None:
        """Feed a press (H-start) signal into the state machine."""
        ...

    def signal_release(self) -> None:
        """Feed a release (H-end) signal into the state machine."""
        ...
```

Constants remain module-level in `button_translator.py` (unchanged):

```python
_CLICK_MAX = 0.140      # H < 140 ms → click
_TIP_MIN   = 0.140      # H ≥ 140 ms → tip  
_HOLD_MIN  = 0.500      # H ≥ 500 ms → hold
_TIP_GAP_MAX   = 0.800  # L window for tip accumulation
_CLICK_GAP_MAX = 0.140  # L window for click accumulation
_HOLD_REPEAT_INTERVAL = 1.0
```

`ButtonEventTranslator._setup_binary_sensor()` is refactored to delegate to `BusEventTimingEngine` instead of duplicating the logic.

### Press-only behaviour

If `signal_release()` is never called (press-only integration), each `signal_press()` is treated as an instantaneous **tip**. Since H duration cannot be measured, each press is assumed to be in the tip range (140–500 ms). This is the natural mapping for zone/area buttons.

Implementation: `signal_press()` without a subsequent `signal_release()` within a short window (50 ms guard) calls `_accumulate("tip")` directly. Consecutive tip signals within the 800 ms gap accumulate into TIP_2X, TIP_3X, TIP_4X.

---

## Section 5 — `listeners.py` — setup_bus_event_listeners()

```python
def setup_bus_event_listeners(
    hass: HomeAssistant,
    api: DsvdcApi,
    entry_id: str,
    vdsds_data: list[dict],
    unsubs: list[Callable],
) -> None:
```

Called from the same site as `setup_output_listeners`, `setup_button_listeners`, etc.

For each vdSD, for each button where `callbackType == "bus_event"`:

1. Retrieve `bus_event_type`, `bus_event_filter`, `bus_event_click_field`, `bus_event_mode`, `bus_event_click_map` from the stored button dict.
2. Get the pydsvdcapi `ButtonInput` via `device.get_vdsd(idx).get_button_input(dsIndex)`.
3. **Direct mode**: Register `hass.bus.async_listen(bus_event_type, handler)` where the handler:
   - Checks all filter key/value pairs against `event.data` — drops if any mismatch (type-coerced: stored strings compared to int event values after conversion)
   - Reads `click_value = event.data.get(click_field)`
   - Looks up `ct = bus_event_click_map.get(click_value)` — logs debug and drops if not found
   - Calls `hass.async_create_task(api.report_button_click(btn, ct))`
4. **Timed mode**: Same filter logic, then:
   - Creates a `BusEventTimingEngine(hass, _click_cb)` per button
   - Handler calls `engine.signal_press()` when raw value maps to `"press"` in click_map
   - Handler calls `engine.signal_release()` when raw value maps to `"release"` in click_map
5. Returned unsub callable appended to `unsubs`. For timed mode, unsub also cancels any pending timing tasks in the engine.

---

## Section 6 — Event entity guidance

For `prefer_event_entity: True` entries (ZHA, deCONZ, Lutron Caseta), the config flow discriminator step shows:

```
ℹ️  [Integration name] now supports HA event entities for physical buttons.
   Using an event entity via "From Entity / Bus Event" (select the matching
   event.* entity) is simpler and more reliable. Use this native bus event
   path only if your device firmware predates event entity support.
```

No behaviour is gated — the user proceeds normally after reading.

---

## Section 7 — Testing

### `test_button_translator.py` — BusEventTimingEngine

- `test_timing_engine_single_tip`: press + release at 200 ms → TIP_1X (0)
- `test_timing_engine_double_tip`: two press+release within 800 ms gap → TIP_2X (1)
- `test_timing_engine_triple_tip`: three presses → TIP_3X (2)
- `test_timing_engine_quadruple_tip`: four presses → TIP_4X (3)
- `test_timing_engine_single_click`: press + release at 80 ms → CLICK_1X (7)
- `test_timing_engine_double_click`: two clicks within 140 ms gap → CLICK_2X (8)
- `test_timing_engine_hold`: press held ≥ 500 ms → HOLD_START (4), then HOLD_REPEAT (5), then release → HOLD_END (6)
- `test_timing_engine_press_only`: signal_press only, no release → accumulates as tip
- `test_timing_engine_press_only_double`: two press-only signals within 800 ms → TIP_2X

### `test_listeners.py` — setup_bus_event_listeners

- `test_bus_event_direct_match`: event with matching filter → correct click type reported
- `test_bus_event_direct_filter_mismatch`: event with non-matching filter field → dropped
- `test_bus_event_direct_unknown_value`: click_value not in click_map → dropped, debug logged
- `test_bus_event_timed_press_release`: event for press then release → timing engine receives signals
- `test_bus_event_unsub_cancels_tasks`: calling unsub cancels pending timing tasks

### `test_entity_mapping_bindings.py`

- `test_bus_event_entries_have_required_keys`: all six entries have `domain`, `integration`, `bus_event`, `button` keys
- `test_bus_event_click_maps_have_valid_ct_values`: all direct-mode click_map values are valid dS click-type ints (0–9) or sentinels `"press"`/`"release"`

### `test_config_flow.py`

- `test_bus_event_discriminator_step_knx`: selecting KNX bus-event type shows group-address field
- `test_bus_event_discriminator_step_zha_shows_guidance`: ZHA shows prefer-entity-entity banner
- `test_bus_event_count_step`: count=1 skips topology step
- `test_bus_event_independent_topology`: count=3 + independent → 3 separate vdSDs created
- `test_bus_event_group_topology`: count=2 + group → 1 vdSD with 2 ButtonInputs

---

## Known Limitations

- **dingz HOLD_END not sent**: the dingz integration fires no release event for long presses. dS receives HOLD_START without a matching HOLD_END.
- **KNX single-group-address**: if only one group address is configured (press only, no release group), the listener runs in press-only tip mode. Users wanting HOLD semantics must configure a separate KNX group address for release and add it as a second bus-event button mapped to a release-only filter.
- **ZHA command vocabulary varies by device**: the `default_click_map` covers common Zigbee command names but cannot cover every device-specific ZHA command. Unknown commands are dropped with a debug log.
