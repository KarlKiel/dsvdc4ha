# Native Bus Event Button Support — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend dsvdc4ha to support physical buttons from KNX, ZHA, deCONZ, Lutron Caseta, dingz, and Homematic by listening to raw HA bus events instead of HA entity state changes.

**Architecture:** Two additions: (1) `BusEventTimingEngine` standalone class extracted from `ButtonEventTranslator`'s binary-sensor timing logic, used by both the refactored translator and new bus-event listeners; (2) `setup_bus_event_listeners()` in `listeners.py` that registers `hass.bus.async_listen()` for buttons with `callbackType == "bus_event"`. Config flow gains a type-picker step followed by integration-specific discriminator, count, topology, and assignment steps.

**Tech Stack:** Python 3.13, Home Assistant custom component, pydsvdcapi ButtonInput, `hass.bus.async_listen` (new), dS timing constants from ds-basics.pdf §10.1.1 Table 8.

**Spec:** `docs/superpowers/specs/2026-07-08-native-bus-event-buttons-design.md`

---

## File Structure

| File | Change |
|---|---|
| `custom_components/dsvdc4ha/button_translator.py` | Add `BusEventTimingEngine` class; refactor `_setup_binary_sensor` to delegate to it |
| `custom_components/dsvdc4ha/entity_mapping.py` | Add `BUS_EVENT_MAPPING`, `_BUS_EVENT_INDEX`, `get_bus_event_mapping()` |
| `custom_components/dsvdc4ha/listeners.py` | Add `setup_bus_event_listeners()` |
| `custom_components/dsvdc4ha/__init__.py` | Import + call `setup_bus_event_listeners()` at two existing call sites |
| `custom_components/dsvdc4ha/config_flow.py` | Route `from_entity` to new `entity_type_picker`; add 6 bus-event flow steps; add state vars; add vdSD builder helpers |
| `custom_components/dsvdc4ha/strings.json` | Labels for 7 new config flow steps |
| `tests/test_button_translator.py` | `BusEventTimingEngine` unit tests |
| `tests/test_entity_mapping_bindings.py` | Bus-event entry validation tests |
| `tests/test_listeners.py` | `setup_bus_event_listeners()` tests |
| `tests/test_config_flow.py` | New step flow tests |

---

## Task 1: BusEventTimingEngine

**Files:**
- Modify: `custom_components/dsvdc4ha/button_translator.py`
- Test: `tests/test_button_translator.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_button_translator.py` after the existing imports and helpers:

```python
from custom_components.dsvdc4ha.button_translator import (
    BusEventTimingEngine,   # will not exist yet — import triggers FAIL
    CT_TIP_1X, CT_TIP_2X, CT_TIP_3X, CT_TIP_4X,
    CT_HOLD_START, CT_HOLD_REPEAT, CT_HOLD_END,
    CT_CLICK_1X, CT_CLICK_2X,
    _TIP_GAP_MAX, _CLICK_GAP_MAX, _HOLD_MIN,
)


# ── BusEventTimingEngine helpers ─────────────────────────────────────────────

def _make_engine(hass=None) -> tuple["BusEventTimingEngine", list[int], object]:
    """Return (engine, clicks_received, hass) tuple."""
    if hass is None:
        hass = _make_hass()
    clicks: list[int] = []

    async def _on_click(ct: int) -> None:
        clicks.append(ct)

    return BusEventTimingEngine(hass, _on_click), clicks, hass


# ── Timing engine tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_timing_engine_single_tip():
    """press + release at 200 ms → TIP_1X (0)."""
    engine, clicks, hass = _make_engine()
    engine.signal_press()
    await asyncio.sleep(0.200)
    engine.signal_release()
    await asyncio.sleep(_TIP_GAP_MAX + 0.1)
    assert clicks == [CT_TIP_1X]


@pytest.mark.asyncio
async def test_timing_engine_double_tip():
    """Two press+release within 800 ms gap → TIP_2X (1)."""
    engine, clicks, hass = _make_engine()
    engine.signal_press()
    await asyncio.sleep(0.200)
    engine.signal_release()
    await asyncio.sleep(0.200)
    engine.signal_press()
    await asyncio.sleep(0.200)
    engine.signal_release()
    await asyncio.sleep(_TIP_GAP_MAX + 0.1)
    assert clicks == [CT_TIP_2X]


@pytest.mark.asyncio
async def test_timing_engine_triple_tip():
    """Three press+release → TIP_3X (2)."""
    engine, clicks, hass = _make_engine()
    for _ in range(3):
        engine.signal_press()
        await asyncio.sleep(0.200)
        engine.signal_release()
        await asyncio.sleep(0.100)
    await asyncio.sleep(_TIP_GAP_MAX + 0.1)
    assert clicks == [CT_TIP_3X]


@pytest.mark.asyncio
async def test_timing_engine_quadruple_tip():
    """Four press+release → TIP_4X (3)."""
    engine, clicks, hass = _make_engine()
    for _ in range(4):
        engine.signal_press()
        await asyncio.sleep(0.150)
        engine.signal_release()
        await asyncio.sleep(0.100)
    await asyncio.sleep(_TIP_GAP_MAX + 0.1)
    assert clicks == [CT_TIP_4X]


@pytest.mark.asyncio
async def test_timing_engine_single_click():
    """Press + release at 80 ms → CLICK_1X (7)."""
    engine, clicks, hass = _make_engine()
    engine.signal_press()
    await asyncio.sleep(0.080)
    engine.signal_release()
    await asyncio.sleep(_CLICK_GAP_MAX + 0.1)
    assert clicks == [CT_CLICK_1X]


@pytest.mark.asyncio
async def test_timing_engine_double_click():
    """Two quick clicks → CLICK_2X (8)."""
    engine, clicks, hass = _make_engine()
    engine.signal_press()
    await asyncio.sleep(0.080)
    engine.signal_release()
    await asyncio.sleep(0.100)
    engine.signal_press()
    await asyncio.sleep(0.080)
    engine.signal_release()
    await asyncio.sleep(_CLICK_GAP_MAX + 0.1)
    assert clicks == [CT_CLICK_2X]


@pytest.mark.asyncio
async def test_timing_engine_hold():
    """Hold ≥ 500 ms → HOLD_START, then HOLD_REPEAT, then release → HOLD_END."""
    engine, clicks, hass = _make_engine()
    engine.signal_press()
    await asyncio.sleep(_HOLD_MIN + 0.1)      # HOLD_START fires
    await asyncio.sleep(1.1)                   # HOLD_REPEAT fires
    engine.signal_release()                    # HOLD_END
    await asyncio.sleep(0.1)
    assert CT_HOLD_START in clicks
    assert CT_HOLD_REPEAT in clicks
    assert CT_HOLD_END in clicks
    assert clicks.index(CT_HOLD_START) < clicks.index(CT_HOLD_REPEAT)
    assert clicks.index(CT_HOLD_REPEAT) < clicks.index(CT_HOLD_END)


@pytest.mark.asyncio
async def test_timing_engine_press_only_single():
    """signal_press only (no release within 50 ms) → treated as tip."""
    engine, clicks, hass = _make_engine()
    engine.signal_press()
    # no signal_release()
    await asyncio.sleep(_TIP_GAP_MAX + 0.2)
    assert clicks == [CT_TIP_1X]


@pytest.mark.asyncio
async def test_timing_engine_press_only_double():
    """Two press-only signals within 800 ms → TIP_2X."""
    engine, clicks, hass = _make_engine()
    engine.signal_press()
    await asyncio.sleep(0.300)   # first tip fires at ~50 ms guard
    engine.signal_press()
    await asyncio.sleep(_TIP_GAP_MAX + 0.1)
    assert clicks == [CT_TIP_2X]


@pytest.mark.asyncio
async def test_timing_engine_cancel_clears_tasks():
    """cancel() does not raise and pending tasks are cancelled."""
    engine, clicks, hass = _make_engine()
    engine.signal_press()
    engine.cancel()
    await asyncio.sleep(_HOLD_MIN + 0.1)
    # No clicks should have fired after cancel
    assert clicks == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/arne/Development/dsvdc4ha
python3 -m pytest tests/test_button_translator.py -k "timing_engine" -v 2>&1 | head -40
```

Expected: `ImportError: cannot import name 'BusEventTimingEngine'`

- [ ] **Step 3: Add BusEventTimingEngine class to button_translator.py**

Insert the following class between the module-level constants and `class ButtonEventTranslator`. Place it at line ~55 (after `_CLICK_FOR_COUNT`):

```python
class BusEventTimingEngine:
    """Signal-driven dS timing state machine (Table 8, ds-basics.pdf §10.1.1).

    Feed press/release signals; the engine fires the appropriate dS click-type
    via *on_click*.  If signal_release() is never called (press-only source),
    each signal_press() is treated as an instantaneous tip after a 50 ms guard.
    """

    _PRESS_ONLY_GUARD = 0.050  # seconds — assume press-only if no release within this

    def __init__(
        self,
        hass: HomeAssistant,
        on_click: Callable[[int], Awaitable[None]],
    ) -> None:
        self._hass = hass
        self._on_click = on_click
        self._press_start: float | None = None
        self._hold_task: asyncio.Task | None = None
        self._press_only_task: asyncio.Task | None = None
        self._in_hold: bool = False
        self._press_count: int = 0
        self._press_kind: str | None = None
        self._gap_task: asyncio.Task | None = None

    def signal_press(self) -> None:
        """Feed a press (H-start) signal into the state machine."""
        self._press_start = time.monotonic()
        self._cancel_gap_task()
        self._hold_task = self._hass.async_create_task(self._hold_sequence())
        self._press_only_task = self._hass.async_create_task(
            self._press_only_guard_timer()
        )

    def signal_release(self) -> None:
        """Feed a release (H-end) signal into the state machine."""
        if self._press_only_task and not self._press_only_task.done():
            self._press_only_task.cancel()
        self._press_only_task = None

        if self._hold_task and not self._hold_task.done():
            self._hold_task.cancel()
            self._hold_task = None

        if self._in_hold:
            self._in_hold = False
            self._hold_task = None
            self._hass.async_create_task(self._on_click(CT_HOLD_END))
            return

        if self._press_start is None:
            return

        h = time.monotonic() - self._press_start
        self._press_start = None

        if h < _CLICK_MAX:
            self._accumulate("click")
        elif h < _HOLD_MIN:
            self._accumulate("tip")

    def cancel(self) -> None:
        """Cancel all pending tasks — call when unregistering the listener."""
        self._cancel_gap_task()
        for task_attr in ("_hold_task", "_press_only_task"):
            task = getattr(self, task_attr)
            if task and not task.done():
                task.cancel()
            setattr(self, task_attr, None)

    async def _press_only_guard_timer(self) -> None:
        await asyncio.sleep(self._PRESS_ONLY_GUARD)
        self._press_only_task = None
        self._press_start = None
        self._accumulate("tip")

    async def _hold_sequence(self) -> None:
        await asyncio.sleep(_HOLD_MIN)
        if self._press_only_task and not self._press_only_task.done():
            self._press_only_task.cancel()
        self._press_only_task = None
        self._cancel_gap_task()
        self._press_count = 0
        self._press_kind = None
        self._in_hold = True
        await self._on_click(CT_HOLD_START)
        while True:
            await asyncio.sleep(_HOLD_REPEAT_INTERVAL)
            await self._on_click(CT_HOLD_REPEAT)

    def _accumulate(self, kind: str) -> None:
        if self._press_kind and self._press_kind != kind:
            self._emit_accumulated()
        self._press_kind = kind
        self._press_count = min(self._press_count + 1, 4)
        gap = _CLICK_GAP_MAX if kind == "click" else _TIP_GAP_MAX
        self._cancel_gap_task()
        self._gap_task = self._hass.async_create_task(self._gap_timeout(gap))

    async def _gap_timeout(self, gap: float) -> None:
        await asyncio.sleep(gap)
        self._emit_accumulated()

    def _emit_accumulated(self) -> None:
        count = self._press_count
        kind = self._press_kind
        self._press_count = 0
        self._press_kind = None
        if kind == "tip" and 1 <= count <= 4:
            ct = _TIP_FOR_COUNT[count - 1]
        elif kind == "click" and 1 <= count <= 3:
            ct = _CLICK_FOR_COUNT[count - 1]
        else:
            return
        _LOGGER.debug("BusEventTimingEngine: %s × %d → click_type %d", kind, count, ct)
        self._hass.async_create_task(self._on_click(ct))

    def _cancel_gap_task(self) -> None:
        if self._gap_task and not self._gap_task.done():
            self._gap_task.cancel()
        self._gap_task = None
```

- [ ] **Step 4: Refactor ButtonEventTranslator._setup_binary_sensor() to use BusEventTimingEngine**

Replace the existing `_setup_binary_sensor`, `_bs_on`, `_bs_off`, and `_hold_sequence` methods in `ButtonEventTranslator`. Also update `setup()` so the binary-sensor path returns the engine's cleanup:

Replace `setup()`:
```python
def setup(self) -> Callable[[], None]:
    """Register HA listeners and return a combined unsub/cleanup callable."""
    if self._source_domain == "binary_sensor":
        return self._setup_binary_sensor()   # returns full cleanup

    if self._source_domain == "event":
        unsub = self._setup_event_entity()
    else:
        unsub = self._setup_button_entity()

    def _cleanup() -> None:
        unsub()
        self._cancel_gap_task()
        if self._hold_task and not self._hold_task.done():
            self._hold_task.cancel()
        self._hold_task = None

    return _cleanup
```

Replace `_setup_binary_sensor` (delete `_bs_on`, `_bs_off`, `_hold_sequence` from `ButtonEventTranslator`):
```python
def _setup_binary_sensor(self) -> Callable[[], None]:
    engine = BusEventTimingEngine(self._hass, self._on_click)

    current = self._hass.states.get(self._entity_id)
    if current and current.state == "on":
        engine.signal_press()

    @callback
    def _on_state(event: Event) -> None:
        new = event.data.get("new_state")
        if new is None:
            return
        if new.state == "on":
            engine.signal_press()
        elif new.state == "off":
            engine.signal_release()

    state_unsub = async_track_state_change_event(self._hass, self._entity_id, _on_state)

    def _cleanup() -> None:
        state_unsub()
        engine.cancel()

    return _cleanup
```

- [ ] **Step 5: Run all button_translator tests to verify they pass**

```bash
python3 -m pytest tests/test_button_translator.py -v 2>&1 | tail -30
```

Expected: all tests pass (existing + new).

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/button_translator.py tests/test_button_translator.py
git commit -m "feat: extract BusEventTimingEngine from ButtonEventTranslator binary-sensor path"
```

---

## Task 2: entity_mapping.py — BUS_EVENT_MAPPING

**Files:**
- Modify: `custom_components/dsvdc4ha/entity_mapping.py`
- Test: `tests/test_entity_mapping_bindings.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_entity_mapping_bindings.py`:

```python
from custom_components.dsvdc4ha.entity_mapping import (
    BUS_EVENT_MAPPING,      # will not exist yet
    get_bus_event_mapping,  # will not exist yet
)


def test_bus_event_entries_have_required_keys():
    """All 6 entries have domain, integration, bus_event, button keys."""
    required = {"domain", "integration", "bus_event", "button",
                "model", "model_uid", "vendor_name", "primary_group"}
    for entry in BUS_EVENT_MAPPING:
        missing = required - set(entry.keys())
        assert not missing, f"Entry {entry.get('integration')} missing: {missing}"
    assert len(BUS_EVENT_MAPPING) == 6
    integrations = {e["integration"] for e in BUS_EVENT_MAPPING}
    assert integrations == {"knx", "zha", "deconz", "lutron_caseta", "dingz", "homematic"}


def test_bus_event_click_maps_have_valid_values():
    """All direct-mode click_map values are valid dS ct ints (0–9) or 'press'/'release'."""
    valid_sentinels = {"press", "release"}
    valid_cts = set(range(10))
    for entry in BUS_EVENT_MAPPING:
        if entry["bus_event"]["bus_event_mode"] == "direct":
            for raw, ct in entry["bus_event"]["default_click_map"].items():
                assert ct in valid_cts or ct in valid_sentinels, (
                    f"{entry['integration']}: invalid ct value {ct!r} for key {raw!r}"
                )


def test_get_bus_event_mapping_returns_entry():
    """get_bus_event_mapping() returns the entry for a known integration."""
    entry = get_bus_event_mapping("knx")
    assert entry is not None
    assert entry["integration"] == "knx"
    assert entry["bus_event"]["event_type"] == "knx_event"


def test_get_bus_event_mapping_returns_none_for_unknown():
    """get_bus_event_mapping() returns None for unknown integration."""
    assert get_bus_event_mapping("nonexistent") is None


def test_bus_event_prefer_event_entity_flags():
    """ZHA, deCONZ, and Lutron have prefer_event_entity=True; others False."""
    prefer_true = {"zha", "deconz", "lutron_caseta"}
    for entry in BUS_EVENT_MAPPING:
        if entry["integration"] in prefer_true:
            assert entry.get("prefer_event_entity") is True, entry["integration"]
        else:
            assert not entry.get("prefer_event_entity"), entry["integration"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_entity_mapping_bindings.py -k "bus_event" -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'BUS_EVENT_MAPPING'`

- [ ] **Step 3: Add BUS_EVENT_MAPPING, _BUS_EVENT_INDEX, and get_bus_event_mapping() to entity_mapping.py**

Insert before the existing `_MAPPING_INDEX` definition (around line 1327):

```python
# ---------------------------------------------------------------------------
# Bus-event button mapping entries (domain = "bus_event")
# ---------------------------------------------------------------------------

BUS_EVENT_MAPPING: list[dict[str, Any]] = [
    {
        "domain": "bus_event",
        "integration": "knx",
        "model": "KNX Button",
        "model_uid": "ha-bus-event-knx",
        "vendor_name": "KNX",
        "primary_group": ColorGroup.BLACK,
        "prefer_event_entity": False,
        "bus_event": {
            "event_type": "knx_event",
            "discriminator_fields": [
                {"key": "destination", "label": "KNX Group Address", "example": "1/2/3"},
            ],
            "click_field": "value",
            "bus_event_mode": "timed",
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
    },
    {
        "domain": "bus_event",
        "integration": "zha",
        "model": "ZHA Button",
        "model_uid": "ha-bus-event-zha",
        "vendor_name": "ZHA",
        "primary_group": ColorGroup.BLACK,
        "prefer_event_entity": True,
        "bus_event": {
            "event_type": "zha_event",
            "discriminator_fields": [
                {"key": "device_ieee", "label": "Device IEEE Address",
                 "example": "00:17:88:01:04:xx:xx:xx"},
                {"key": "endpoint_id", "label": "Endpoint ID",
                 "example": "1", "optional": True},
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
    },
    {
        "domain": "bus_event",
        "integration": "deconz",
        "model": "deCONZ Button",
        "model_uid": "ha-bus-event-deconz",
        "vendor_name": "deCONZ",
        "primary_group": ColorGroup.BLACK,
        "prefer_event_entity": True,
        "bus_event": {
            "event_type": "deconz_event",
            "discriminator_fields": [
                {"key": "unique_id", "label": "Sensor unique_id",
                 "example": "00:0d:6f:00:0f:xx:xx:xx-01-1000"},
            ],
            "click_field": "event",
            "bus_event_mode": "direct",
            "default_click_map": {
                1002: 0,   # short release → TIP_1X
                1004: 1,   # double press  → TIP_2X
                1001: 4,   # hold          → HOLD_START
                1003: 6,   # long release  → HOLD_END
            },
            "event_code_button_stride": 1000,
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
    },
    {
        "domain": "bus_event",
        "integration": "lutron_caseta",
        "model": "Lutron Caseta Button",
        "model_uid": "ha-bus-event-lutron-caseta",
        "vendor_name": "Lutron",
        "primary_group": ColorGroup.BLACK,
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
    },
    {
        "domain": "bus_event",
        "integration": "dingz",
        "model": "dingz Button",
        "model_uid": "ha-bus-event-dingz",
        "vendor_name": "dingz",
        "primary_group": ColorGroup.BLACK,
        "prefer_event_entity": False,
        "bus_event": {
            "event_type": "dingz_event",
            "discriminator_fields": [
                {"key": "unique_id", "label": "dingz Host / unique_id",
                 "example": "aabbccddeeff"},
                {"key": "index", "label": "Button Index (1–4)", "example": "1"},
            ],
            "click_field": "action",
            "bus_event_mode": "direct",
            "default_click_map": {
                "single": 0,
                "double": 1,
                "triple": 2,
                "long":   4,
            },
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
    },
    {
        "domain": "bus_event",
        "integration": "homematic",
        "model": "Homematic Button",
        "model_uid": "ha-bus-event-homematic",
        "vendor_name": "Homematic",
        "primary_group": ColorGroup.BLACK,
        "prefer_event_entity": False,
        "bus_event": {
            "event_type": "homematic_keypress",
            "discriminator_fields": [
                {"key": "name", "label": "Device + Channel",
                 "example": "KEQ1234567:1"},
            ],
            "click_field": "param",
            "bus_event_mode": "direct",
            "default_click_map": {
                "PRESS_SHORT":        7,
                "PRESS_LONG":         4,
                "PRESS_CONT":         5,
                "PRESS_LONG_RELEASE": 6,
            },
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
    },
]

_BUS_EVENT_INDEX: dict[str, dict[str, Any]] = {
    e["integration"]: e for e in BUS_EVENT_MAPPING
}


def get_bus_event_mapping(integration: str) -> dict[str, Any] | None:
    """Return bus-event mapping entry for an integration name, or None if unknown."""
    return _BUS_EVENT_INDEX.get(integration)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_entity_mapping_bindings.py -v 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/entity_mapping.py tests/test_entity_mapping_bindings.py
git commit -m "feat: add BUS_EVENT_MAPPING entries for 6 bus-event button integrations"
```

---

## Task 3: setup_bus_event_listeners() + __init__.py call sites

**Files:**
- Modify: `custom_components/dsvdc4ha/listeners.py`
- Modify: `custom_components/dsvdc4ha/__init__.py`
- Test: `tests/test_listeners.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_listeners.py`:

```python
from custom_components.dsvdc4ha.listeners import setup_bus_event_listeners  # will FAIL


def _make_bus_event_hass():
    """Mock hass with capturable bus.async_listen and async_create_task."""
    hass = MagicMock()
    captured_handlers: dict[str, list] = {}

    def _async_listen(event_type, handler):
        captured_handlers.setdefault(event_type, []).append(handler)
        return lambda: None  # unsub

    hass.bus.async_listen.side_effect = _async_listen
    hass._captured_handlers = captured_handlers

    tasks = []

    def _create_task(coro):
        task = asyncio.ensure_future(coro)
        tasks.append(task)
        return task

    hass.async_create_task.side_effect = _create_task
    return hass


def _make_bus_api(btn=None):
    api = MagicMock()
    api.report_button_click = AsyncMock()
    device = MagicMock()
    vdsd = MagicMock()
    if btn is None:
        btn = MagicMock()
    vdsd.get_button_input.return_value = btn
    device.get_vdsd.return_value = vdsd
    api.get_device.return_value = device
    return api, btn


def _make_event(data: dict):
    ev = MagicMock()
    ev.data = data
    return ev


@pytest.mark.asyncio
async def test_bus_event_direct_match():
    """Direct-mode event with matching filter → correct click type reported."""
    hass = _make_bus_event_hass()
    api, btn = _make_bus_api()

    vdsds_data = [{
        "buttons": [{
            "dsIndex": 0,
            "callbackType": "bus_event",
            "callback_entity": None,
            "bus_event_type": "dingz_event",
            "bus_event_filter": {"unique_id": "aabbcc"},
            "bus_event_click_field": "action",
            "bus_event_mode": "direct",
            "bus_event_click_map": {"single": 0, "double": 1},
        }],
    }]

    unsubs = setup_bus_event_listeners(hass, api, "entry1", vdsds_data)
    assert len(unsubs) == 1

    handler = hass._captured_handlers["dingz_event"][0]
    handler(_make_event({"unique_id": "aabbcc", "action": "single"}))
    await asyncio.sleep(0.01)

    api.report_button_click.assert_awaited_once_with(btn, 0)


@pytest.mark.asyncio
async def test_bus_event_direct_filter_mismatch():
    """Event with non-matching filter field → dropped, no click reported."""
    hass = _make_bus_event_hass()
    api, btn = _make_bus_api()

    vdsds_data = [{
        "buttons": [{
            "dsIndex": 0,
            "callbackType": "bus_event",
            "callback_entity": None,
            "bus_event_type": "dingz_event",
            "bus_event_filter": {"unique_id": "aabbcc"},
            "bus_event_click_field": "action",
            "bus_event_mode": "direct",
            "bus_event_click_map": {"single": 0},
        }],
    }]

    setup_bus_event_listeners(hass, api, "entry1", vdsds_data)
    handler = hass._captured_handlers["dingz_event"][0]
    handler(_make_event({"unique_id": "DIFFERENT", "action": "single"}))
    await asyncio.sleep(0.01)
    api.report_button_click.assert_not_awaited()


@pytest.mark.asyncio
async def test_bus_event_direct_unknown_value():
    """click_value not in click_map → dropped (no error raised)."""
    hass = _make_bus_event_hass()
    api, btn = _make_bus_api()

    vdsds_data = [{
        "buttons": [{
            "dsIndex": 0,
            "callbackType": "bus_event",
            "callback_entity": None,
            "bus_event_type": "dingz_event",
            "bus_event_filter": {},
            "bus_event_click_field": "action",
            "bus_event_mode": "direct",
            "bus_event_click_map": {"single": 0},
        }],
    }]

    setup_bus_event_listeners(hass, api, "entry1", vdsds_data)
    handler = hass._captured_handlers["dingz_event"][0]
    handler(_make_event({"action": "unknown_action"}))
    await asyncio.sleep(0.01)
    api.report_button_click.assert_not_awaited()


@pytest.mark.asyncio
async def test_bus_event_timed_press_release():
    """Timed-mode: press event + release event → engine receives both signals."""
    from unittest.mock import patch
    hass = _make_bus_event_hass()
    api, btn = _make_bus_api()

    vdsds_data = [{
        "buttons": [{
            "dsIndex": 0,
            "callbackType": "bus_event",
            "callback_entity": None,
            "bus_event_type": "knx_event",
            "bus_event_filter": {"destination": "1/2/3"},
            "bus_event_click_field": "value",
            "bus_event_mode": "timed",
            "bus_event_click_map": {1: "press", 0: "release"},
        }],
    }]

    press_calls = []
    release_calls = []

    with patch(
        "custom_components.dsvdc4ha.listeners.BusEventTimingEngine"
    ) as MockEngine:
        mock_engine = MagicMock()
        mock_engine.signal_press.side_effect = lambda: press_calls.append(1)
        mock_engine.signal_release.side_effect = lambda: release_calls.append(1)
        MockEngine.return_value = mock_engine

        setup_bus_event_listeners(hass, api, "entry1", vdsds_data)
        handler = hass._captured_handlers["knx_event"][0]

        handler(_make_event({"destination": "1/2/3", "value": 1}))
        handler(_make_event({"destination": "1/2/3", "value": 0}))

    assert press_calls == [1]
    assert release_calls == [1]


@pytest.mark.asyncio
async def test_bus_event_unsub_cancels_engine():
    """Calling unsub for a timed bus event listener also calls engine.cancel()."""
    from unittest.mock import patch
    hass = _make_bus_event_hass()
    api, btn = _make_bus_api()

    vdsds_data = [{
        "buttons": [{
            "dsIndex": 0,
            "callbackType": "bus_event",
            "callback_entity": None,
            "bus_event_type": "knx_event",
            "bus_event_filter": {},
            "bus_event_click_field": "value",
            "bus_event_mode": "timed",
            "bus_event_click_map": {1: "press", 0: "release"},
        }],
    }]

    with patch(
        "custom_components.dsvdc4ha.listeners.BusEventTimingEngine"
    ) as MockEngine:
        mock_engine = MagicMock()
        MockEngine.return_value = mock_engine

        unsubs = setup_bus_event_listeners(hass, api, "entry1", vdsds_data)
        assert len(unsubs) == 1
        unsubs[0]()   # call the unsub

    mock_engine.cancel.assert_called_once()


def test_bus_event_non_bus_event_buttons_skipped():
    """Buttons with callbackType != 'bus_event' are not registered."""
    hass = _make_bus_event_hass()
    api, btn = _make_bus_api()

    vdsds_data = [{
        "buttons": [{
            "dsIndex": 0,
            "callbackType": "clickTypes",
            "callback_entity": "button.hall",
        }],
    }]

    unsubs = setup_bus_event_listeners(hass, api, "entry1", vdsds_data)
    assert unsubs == []
    hass.bus.async_listen.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_listeners.py -k "bus_event" -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'setup_bus_event_listeners'`

- [ ] **Step 3: Add setup_bus_event_listeners() to listeners.py**

Append after `setup_output_listeners()` at the end of `listeners.py`:

```python
def setup_bus_event_listeners(
    hass: HomeAssistant,
    api: "DsvdcApi",
    entry_id: str,
    vdsds_data: list[dict],
) -> list:
    """Register hass.bus listeners for buttons with callbackType == 'bus_event'."""
    from .button_translator import BusEventTimingEngine

    unsubs = []
    device = api.get_device(entry_id)
    if not device:
        return unsubs

    for idx, vdsd_data in enumerate(vdsds_data):
        vdsd = device.get_vdsd(idx)
        if not vdsd:
            continue

        for btn_data in vdsd_data.get("buttons", []):
            if btn_data.get("callbackType") != "bus_event":
                continue

            btn = vdsd.get_button_input(btn_data["dsIndex"])
            if not btn:
                continue

            event_type: str = btn_data["bus_event_type"]
            event_filter: dict = btn_data.get("bus_event_filter", {})
            click_field: str = btn_data["bus_event_click_field"]
            mode: str = btn_data.get("bus_event_mode", "direct")
            click_map: dict = btn_data.get("bus_event_click_map", {})

            def _matches_filter(data: dict, _flt: dict = event_filter) -> bool:
                for k, v in _flt.items():
                    ev = data.get(k)
                    if ev is None or (str(ev) != str(v)):
                        return False
                return True

            def _resolve_sentinel(raw, _map: dict = click_map):
                sentinel = _map.get(raw)
                if sentinel is None:
                    try:
                        sentinel = _map.get(int(raw))
                    except (TypeError, ValueError):
                        pass
                return sentinel

            if mode == "timed":
                async def _click_cb(ct: int, _btn=btn) -> None:
                    await api.report_button_click(_btn, ct)

                engine = BusEventTimingEngine(hass, _click_cb)

                @callback
                def _timed_handler(
                    event,
                    _flt=event_filter,
                    _field=click_field,
                    _map=click_map,
                    _engine=engine,
                ) -> None:
                    data = event.data
                    for k, v in _flt.items():
                        if str(data.get(k)) != str(v):
                            return
                    raw = data.get(_field)
                    sentinel = _map.get(raw)
                    if sentinel is None:
                        try:
                            sentinel = _map.get(int(raw))
                        except (TypeError, ValueError):
                            pass
                    if sentinel is None:
                        _LOGGER.debug(
                            "bus_event: unmapped value %r in click_map for %s",
                            raw, event_type,
                        )
                        return
                    if sentinel == "press":
                        _engine.signal_press()
                    elif sentinel == "release":
                        _engine.signal_release()

                bus_unsub = hass.bus.async_listen(event_type, _timed_handler)

                def _timed_unsub(_unsub=bus_unsub, _engine=engine) -> None:
                    _unsub()
                    _engine.cancel()

                unsubs.append(_timed_unsub)

            else:
                @callback
                def _direct_handler(
                    event,
                    _btn=btn,
                    _flt=event_filter,
                    _field=click_field,
                    _map=click_map,
                ) -> None:
                    data = event.data
                    for k, v in _flt.items():
                        if str(data.get(k)) != str(v):
                            return
                    raw = data.get(_field)
                    ct = _map.get(raw)
                    if ct is None:
                        try:
                            ct = _map.get(int(raw))
                        except (TypeError, ValueError):
                            pass
                    if ct is None:
                        _LOGGER.debug(
                            "bus_event: unmapped value %r in click_map for %s",
                            raw, event_type,
                        )
                        return
                    hass.async_create_task(api.report_button_click(_btn, ct))

                unsubs.append(hass.bus.async_listen(event_type, _direct_handler))

    return unsubs
```

- [ ] **Step 4: Update __init__.py — add import and two call sites**

In `__init__.py`, find the two lines:
```python
from .listeners import setup_input_listeners, setup_output_listeners, seed_initial_values
```
(appears at lines 653 and 755 — update both occurrences):
```python
from .listeners import setup_input_listeners, setup_output_listeners, seed_initial_values, setup_bus_event_listeners
```

Find the two lines (around lines 675-676 and 777-778):
```python
unsubs = setup_input_listeners(hass, coordinator.api, subentry.subentry_id, vdsds)
unsubs += setup_output_listeners(hass, coordinator.api, subentry.subentry_id, vdsds)
```
After each, add:
```python
unsubs += setup_bus_event_listeners(hass, coordinator.api, subentry.subentry_id, vdsds)
```

- [ ] **Step 5: Run all listener tests**

```bash
python3 -m pytest tests/test_listeners.py -v 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/listeners.py custom_components/dsvdc4ha/__init__.py tests/test_listeners.py
git commit -m "feat: add setup_bus_event_listeners() for native bus-event button support"
```

---

## Task 4: Config flow steps + strings.json

**Files:**
- Modify: `custom_components/dsvdc4ha/strings.json`
- Modify: `custom_components/dsvdc4ha/config_flow.py`
- Test: `tests/test_config_flow.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_config_flow.py`:

```python
# ── Bus-event config flow tests ───────────────────────────────────────────────

def _make_bus_subentry_flow(hass_mock=None):
    """Return a DeviceSubentryFlowHandler with minimal mocked hass."""
    from custom_components.dsvdc4ha.config_flow import DeviceSubentryFlowHandler
    flow = DeviceSubentryFlowHandler.__new__(DeviceSubentryFlowHandler)
    if hass_mock is None:
        hass_mock = MagicMock()
        hass_mock.config.language = "en"
    flow.hass = hass_mock
    # Run __init__ to set up state variables
    flow.__init__()
    return flow


@pytest.mark.asyncio
async def test_entity_type_picker_shows_ha_and_bus_options():
    """entity_type_picker step shows HA entity option and 6 bus-event integrations."""
    flow = _make_bus_subentry_flow()
    result = await flow.async_step_entity_type_picker()
    # Step should render a form with 'type' field
    assert result["type"] == "form"
    assert result["step_id"] == "entity_type_picker"
    schema_keys = [str(k) for k in result["data_schema"].schema.keys()]
    assert "type" in schema_keys


@pytest.mark.asyncio
async def test_entity_type_picker_ha_entity_routes_to_entity_picker():
    """Selecting 'ha_entity' routes to entity_picker step."""
    flow = _make_bus_subentry_flow()
    with patch.object(flow, "async_step_entity_picker", new=AsyncMock(return_value={"type": "form", "step_id": "entity_picker"})) as mock:
        result = await flow.async_step_entity_type_picker({"type": "ha_entity"})
    mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_entity_type_picker_knx_routes_to_discriminator():
    """Selecting 'bus_event_knx' routes to bus_event_discriminator."""
    flow = _make_bus_subentry_flow()
    with patch.object(flow, "async_step_bus_event_discriminator", new=AsyncMock(return_value={"type": "form", "step_id": "bus_event_discriminator"})) as mock:
        result = await flow.async_step_entity_type_picker({"type": "bus_event_knx"})
    mock.assert_awaited_once()
    assert flow._bus_event_integration == "knx"


@pytest.mark.asyncio
async def test_bus_event_discriminator_knx_shows_group_address_field():
    """KNX discriminator step renders a form with 'destination' field."""
    flow = _make_bus_subentry_flow()
    flow._bus_event_integration = "knx"
    result = await flow.async_step_bus_event_discriminator()
    assert result["type"] == "form"
    assert result["step_id"] == "bus_event_discriminator"
    keys = [str(k) for k in result["data_schema"].schema.keys()]
    assert "destination" in keys


@pytest.mark.asyncio
async def test_bus_event_discriminator_zha_prefer_event_entity_placeholder():
    """ZHA discriminator step includes prefer_event_entity in placeholders."""
    flow = _make_bus_subentry_flow()
    flow._bus_event_integration = "zha"
    result = await flow.async_step_bus_event_discriminator()
    assert result["type"] == "form"
    # prefer_event_entity integrations pass description_placeholders
    assert "description_placeholders" in result
    placeholders = result["description_placeholders"]
    assert "integration" in placeholders


@pytest.mark.asyncio
async def test_bus_event_count_1_skips_topology():
    """When count=1, topology step is skipped and we proceed to independent flow."""
    flow = _make_bus_subentry_flow()
    flow._bus_event_integration = "knx"
    flow._bus_event_shared_filter = {"destination": "1/2/3"}
    with patch.object(flow, "async_step_bus_event_independent_discrim", new=AsyncMock(return_value={"type": "form"})) as mock:
        await flow.async_step_bus_event_count({"count": 1})
    mock.assert_awaited_once()
    assert flow._bus_event_button_count == 1
    assert flow._bus_event_topology == "independent"


@pytest.mark.asyncio
async def test_bus_event_count_2_shows_topology():
    """When count=2, topology step is shown."""
    flow = _make_bus_subentry_flow()
    flow._bus_event_integration = "knx"
    flow._bus_event_shared_filter = {"destination": "1/2/3"}
    with patch.object(flow, "async_step_bus_event_topology", new=AsyncMock(return_value={"type": "form"})) as mock:
        await flow.async_step_bus_event_count({"count": 2})
    mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_bus_event_topology_independent_routes_to_discrim():
    """Independent topology routes to bus_event_independent_discrim."""
    flow = _make_bus_subentry_flow()
    flow._bus_event_integration = "dingz"
    flow._bus_event_shared_filter = {"unique_id": "aabb", "index": "1"}
    flow._bus_event_button_count = 3
    with patch.object(flow, "async_step_bus_event_independent_discrim", new=AsyncMock(return_value={"type": "form"})) as mock:
        await flow.async_step_bus_event_topology({"topology": "independent"})
    mock.assert_awaited_once()
    assert flow._bus_event_topology == "independent"


@pytest.mark.asyncio
async def test_bus_event_independent_discrim_collects_n_buttons():
    """Independent path: after N discriminator forms, N vdSDs are appended."""
    flow = _make_bus_subentry_flow()
    flow._bus_event_integration = "knx"
    flow._bus_event_shared_filter = {}
    flow._bus_event_button_count = 2
    flow._bus_event_topology = "independent"
    flow._bus_event_per_button_overrides = [{}, {}]
    flow._bus_event_current_button_idx = 0
    flow._bus_event_pending_vdsds = []
    flow._vdsds = []
    flow._device_name = "Test"
    flow._vendor_name = "KNX"
    flow._display_id = "KNX Button"

    # First button
    result1 = await flow.async_step_bus_event_independent_discrim(
        {"destination": "1/2/3"}
    )
    # Should advance to second button
    assert flow._bus_event_current_button_idx == 1

    # Second button
    with patch.object(
        flow, "async_step_bus_event_name_next",
        new=AsyncMock(return_value={"type": "form", "step_id": "bus_event_name_next"})
    ) as mock_name:
        result2 = await flow.async_step_bus_event_independent_discrim(
            {"destination": "4/5/6"}
        )
    # After 2 buttons, should proceed to naming
    mock_name.assert_awaited_once()
    # Two pending vdSDs should be prepared
    assert len(flow._bus_event_pending_vdsds) == 2


@pytest.mark.asyncio
async def test_bus_event_group_topology_creates_single_vdsd():
    """Group topology: one vdSD with N buttons is set as current."""
    flow = _make_bus_subentry_flow()
    flow._bus_event_integration = "lutron_caseta"
    flow._bus_event_shared_filter = {"serial": "12345678"}
    flow._bus_event_button_count = 2
    flow._bus_event_topology = "group"
    flow._vdsds = []
    flow._device_name = "Pico"
    flow._vendor_name = "Lutron"
    flow._display_id = "Pico Remote"

    with patch.object(
        flow, "async_step_model_features",
        new=AsyncMock(return_value={"type": "form", "step_id": "model_features"})
    ) as mock_mf:
        await flow.async_step_bus_event_group_assign({
            "btn_0_button_number": "0",
            "btn_1_button_number": "1",
        })

    mock_mf.assert_awaited_once()
    assert len(flow._current_buttons) == 2
    assert all(b["callbackType"] == "bus_event" for b in flow._current_buttons)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_config_flow.py -k "bus_event or entity_type_picker" -v 2>&1 | head -30
```

Expected: multiple `AttributeError` / `ImportError` failures (missing steps, missing state vars).

- [ ] **Step 3: Add strings.json entries for the new steps**

In `strings.json`, under `config_subentries.device.step`, add these entries (after `entity_user_input`):

```json
"entity_type_picker": {
  "title": "Select Type",
  "description": "Choose a Home Assistant entity to expose, or configure a native bus-event button from a supported integration.",
  "data": {
    "type": "Type"
  }
},
"bus_event_discriminator": {
  "title": "Bus Event — {integration}",
  "description": "Enter the identifying fields for this device. These values are matched against every incoming event to route clicks to the correct dS button.\n{prefer_guidance}",
  "data": {
    "destination": "KNX Group Address",
    "device_ieee": "Device IEEE Address",
    "endpoint_id": "Endpoint ID (optional)",
    "unique_id": "Device unique_id",
    "serial": "Device Serial Number",
    "button_number": "Button Number (0-based)",
    "index": "Button Index (1–4)",
    "name": "Device + Channel"
  }
},
"bus_event_count": {
  "title": "Number of Buttons",
  "description": "How many physical buttons does this device have?",
  "data": {
    "count": "Button count"
  }
},
"bus_event_topology": {
  "title": "Button Topology",
  "description": "Are these buttons independent, or part of a logical button group (e.g. UP/DOWN, UP/DOWN/CENTER)?",
  "data": {
    "topology": "Topology"
  }
},
"bus_event_independent_discrim": {
  "title": "Button {current} of {total} — Discriminator",
  "description": "Enter the identifying field(s) for button {current}.",
  "data": {
    "destination": "KNX Group Address",
    "device_ieee": "Device IEEE Address",
    "endpoint_id": "Endpoint ID (optional)",
    "unique_id": "Device unique_id",
    "serial": "Device Serial Number",
    "button_number": "Button Number (0-based)",
    "index": "Button Index (1–4)",
    "name": "Device + Channel"
  }
},
"bus_event_group_assign": {
  "title": "Button Group Assignment",
  "description": "Assign each physical button to a dS function role.",
  "data": {}
},
"bus_event_name_next": {
  "title": "Name Button {current} of {total}",
  "description": "Enter a name for this button's virtual dS device.",
  "data": {
    "name": "Device name"
  }
}
```

Also in `strings.json` under `labels`, update the `creation_mode.from_entity` label:
```json
"from_entity": "Create device from HA entity or bus event (recommended)"
```

And add a `bus_event_topology` labels section:
```json
"bus_event_topology": {
  "independent": "Independent — each button becomes a separate dS device",
  "group": "Part of a logical button group — all buttons form one dS device"
}
```

- [ ] **Step 4: Add bus-event state variables to the subentry flow __init__**

In `config_flow.py`, find the `DeviceSubentryFlowHandler.__init__` method (around line 870). After the existing state variable declarations, add:

```python
# Bus-event flow state
self._bus_event_integration: str | None = None
self._bus_event_shared_filter: dict[str, str] = {}
self._bus_event_button_count: int = 1
self._bus_event_topology: str = "independent"
self._bus_event_per_button_overrides: list[dict[str, str]] = []
self._bus_event_current_button_idx: int = 0
self._bus_event_pending_vdsds: list[dict] = []
```

- [ ] **Step 5: Update async_step_creation_mode routing and rename from_entity label handling**

In `async_step_creation_mode` (line ~986), change:
```python
if mode == "from_entity":
    return await self.async_step_entity_picker()
```
to:
```python
if mode == "from_entity":
    return await self.async_step_entity_type_picker()
```

- [ ] **Step 6: Add async_step_entity_type_picker**

Insert after `async_step_creation_mode`:

```python
async def async_step_entity_type_picker(self, user_input: dict | None = None):
    """Choose between a real HA entity or a native bus-event integration."""
    from .entity_mapping import BUS_EVENT_MAPPING

    if user_input is not None:
        type_key = user_input["type"]
        if type_key == "ha_entity":
            return await self.async_step_entity_picker()
        self._bus_event_integration = type_key.removeprefix("bus_event_")
        return await self.async_step_bus_event_discriminator()

    options = [{"value": "ha_entity", "label": "Home Assistant Entity"}]
    for entry in BUS_EVENT_MAPPING:
        label = entry["model"]
        if entry.get("prefer_event_entity"):
            label += " (event entity preferred)"
        options.append({
            "value": f"bus_event_{entry['integration']}",
            "label": label,
        })

    schema = vol.Schema({
        vol.Required("type", default="ha_entity"): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=options, mode=selector.SelectSelectorMode.LIST
            )
        ),
    })
    return self.async_show_form(step_id="entity_type_picker", data_schema=schema)
```

- [ ] **Step 7: Add async_step_bus_event_discriminator**

```python
async def async_step_bus_event_discriminator(self, user_input: dict | None = None):
    """Collect integration-specific discriminator fields (shared across all buttons)."""
    from .entity_mapping import get_bus_event_mapping

    mapping = get_bus_event_mapping(self._bus_event_integration or "")
    if mapping is None:
        return await self.async_step_creation_mode()

    bus_event = mapping["bus_event"]
    fields = bus_event["discriminator_fields"]

    if user_input is not None:
        self._bus_event_shared_filter = {
            field["key"]: v
            for field in fields
            if (v := user_input.get(field["key"], ""))
            and (not field.get("optional") or v)
        }
        return await self.async_step_bus_event_count()

    schema_dict: dict = {}
    for field in fields:
        key = field["key"]
        if field.get("optional"):
            schema_dict[vol.Optional(key, default="")] = selector.TextSelector()
        else:
            schema_dict[vol.Required(key)] = selector.TextSelector()

    prefer = mapping.get("prefer_event_entity", False)
    prefer_guidance = (
        f"ℹ️  {mapping['model']} now supports HA event entities for physical buttons. "
        "Using an event entity (via the 'Home Assistant Entity' option) is simpler and "
        "more reliable. Use this native bus event path only if your firmware predates "
        "event entity support."
    ) if prefer else ""

    return self.async_show_form(
        step_id="bus_event_discriminator",
        data_schema=vol.Schema(schema_dict),
        description_placeholders={
            "integration": mapping["model"],
            "prefer_guidance": prefer_guidance,
        },
    )
```

- [ ] **Step 8: Add async_step_bus_event_count**

```python
async def async_step_bus_event_count(self, user_input: dict | None = None):
    """Ask how many physical buttons the device has."""
    if user_input is not None:
        self._bus_event_button_count = int(user_input["count"])
        if self._bus_event_button_count == 1:
            self._bus_event_topology = "independent"
            return await self._start_bus_event_independent()
        return await self.async_step_bus_event_topology()

    schema = vol.Schema({
        vol.Required("count", default=1): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1, max=8,
                mode=selector.NumberSelectorMode.BOX,
                step=1,
            )
        ),
    })
    return self.async_show_form(step_id="bus_event_count", data_schema=schema)
```

- [ ] **Step 9: Add async_step_bus_event_topology**

```python
async def async_step_bus_event_topology(self, user_input: dict | None = None):
    """Ask whether buttons are independent or part of a logical group."""
    if user_input is not None:
        self._bus_event_topology = user_input["topology"]
        if self._bus_event_topology == "independent":
            return await self._start_bus_event_independent()
        return await self.async_step_bus_event_group_assign()

    schema = vol.Schema({
        vol.Required("topology", default="independent"): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=_build_section_opts(self.hass, "bus_event_topology"),
                mode=selector.SelectSelectorMode.LIST,
            )
        ),
    })
    return self.async_show_form(step_id="bus_event_topology", data_schema=schema)
```

- [ ] **Step 10: Add _start_bus_event_independent helper + async_step_bus_event_independent_discrim + async_step_bus_event_name_next**

```python
async def _start_bus_event_independent(self):
    """Initialize state for the independent button path and start discriminator loop."""
    self._bus_event_per_button_overrides = [
        {} for _ in range(self._bus_event_button_count)
    ]
    self._bus_event_current_button_idx = 0
    self._bus_event_pending_vdsds = []
    return await self.async_step_bus_event_independent_discrim()


async def async_step_bus_event_independent_discrim(
    self, user_input: dict | None = None
):
    """Per-button discriminator form — shown once for each independent button."""
    from .entity_mapping import get_bus_event_mapping

    mapping = get_bus_event_mapping(self._bus_event_integration or "")
    if mapping is None:
        return await self.async_step_creation_mode()

    bus_event = mapping["bus_event"]
    fields = bus_event["discriminator_fields"]
    btn_idx = self._bus_event_current_button_idx

    if user_input is not None:
        per_btn: dict[str, str] = {}
        for field in fields:
            v = user_input.get(field["key"], "")
            if v or not field.get("optional"):
                per_btn[field["key"]] = v
        self._bus_event_per_button_overrides[btn_idx] = per_btn
        self._bus_event_current_button_idx += 1

        if self._bus_event_current_button_idx >= self._bus_event_button_count:
            return await self._finalize_bus_event_independent(mapping)

        return await self.async_step_bus_event_independent_discrim()

    # Pre-fill from shared filter
    schema_dict: dict = {}
    for field in fields:
        key = field["key"]
        default = self._bus_event_shared_filter.get(key, "")
        if field.get("optional"):
            schema_dict[vol.Optional(key, default=default)] = selector.TextSelector()
        else:
            schema_dict[vol.Required(key, default=default)] = selector.TextSelector()

    return self.async_show_form(
        step_id="bus_event_independent_discrim",
        data_schema=vol.Schema(schema_dict),
        description_placeholders={
            "current": str(btn_idx + 1),
            "total": str(self._bus_event_button_count),
        },
    )


async def _finalize_bus_event_independent(self, mapping: dict):
    """Build N vdSDs (one per button), store as pending, start naming loop."""
    self._bus_event_pending_vdsds = []
    for i, per_btn_filter in enumerate(self._bus_event_per_button_overrides):
        btn_dict = self._build_bus_event_button_dict(mapping, per_btn_filter, btn_idx=i)
        vdsd = self._build_bus_event_vdsd(
            mapping,
            buttons=[btn_dict],
            name=mapping["model"],
        )
        self._bus_event_pending_vdsds.append(vdsd)
    self._bus_event_current_button_idx = 0
    return await self.async_step_bus_event_name_next()


async def async_step_bus_event_name_next(self, user_input: dict | None = None):
    """Name the next pending independent bus-event vdSD and save it."""
    pending = self._bus_event_pending_vdsds
    idx = self._bus_event_current_button_idx

    if user_input is not None:
        pending[idx]["name"] = user_input["name"].strip()
        self._vdsds.append(dict(pending[idx]))
        self._bus_event_current_button_idx += 1
        if self._bus_event_current_button_idx < len(pending):
            return await self.async_step_bus_event_name_next()
        return await self.async_step_entity_completion()

    schema = vol.Schema({
        vol.Required("name", default=pending[idx].get("name", "Button")): selector.TextSelector(),
    })
    return self.async_show_form(
        step_id="bus_event_name_next",
        data_schema=schema,
        description_placeholders={
            "current": str(idx + 1),
            "total": str(len(pending)),
        },
    )
```

- [ ] **Step 11: Add async_step_bus_event_group_assign**

```python
async def async_step_bus_event_group_assign(self, user_input: dict | None = None):
    """Assign per-button discriminator fields for group topology, create 1 vdSD."""
    from .entity_mapping import get_bus_event_mapping

    mapping = get_bus_event_mapping(self._bus_event_integration or "")
    if mapping is None:
        return await self.async_step_creation_mode()

    bus_event = mapping["bus_event"]
    fields = bus_event["discriminator_fields"]
    n = self._bus_event_button_count

    if user_input is not None:
        buttons = []
        for i in range(n):
            per_btn: dict[str, str] = {}
            for field in fields:
                key = field["key"]
                form_key = f"btn_{i}_{key}"
                v = user_input.get(form_key, self._bus_event_shared_filter.get(key, ""))
                if v or not field.get("optional"):
                    per_btn[key] = v
            btn_dict = self._build_bus_event_button_dict(
                mapping, per_btn, btn_idx=i
            )
            btn_dict["dsIndex"] = i
            buttons.append(btn_dict)

        vdsd = self._build_bus_event_vdsd(mapping, buttons=buttons, name=mapping["model"])

        # Hand off to model_features via the from_entity path
        self._creation_mode = "from_entity"
        self._current_vdsd = vdsd
        self._current_buttons = buttons
        self._current_binary_inputs = []
        self._current_sensors = []
        self._current_output = None
        self._current_channels = []
        if not self._device_name:
            self._device_name = vdsd["name"]
        if not self._vendor_name:
            self._vendor_name = mapping["vendor_name"]
        if not self._display_id:
            self._display_id = mapping["model"]
        return await self.async_step_model_features()

    # Build schema: for each button × each discriminator field
    schema_dict: dict = {}
    for i in range(n):
        for field in fields:
            key = field["key"]
            form_key = f"btn_{i}_{key}"
            default = self._bus_event_shared_filter.get(key, "")
            if field.get("optional"):
                schema_dict[vol.Optional(form_key, default=default)] = selector.TextSelector(
                    selector.TextSelectorConfig(
                        placeholder=f"Button {i+1}: {field.get('label', key)} (optional)"
                    )
                )
            else:
                schema_dict[vol.Required(form_key, default=default)] = selector.TextSelector(
                    selector.TextSelectorConfig(
                        placeholder=f"Button {i+1}: {field.get('label', key)}"
                    )
                )

    return self.async_show_form(
        step_id="bus_event_group_assign",
        data_schema=vol.Schema(schema_dict),
    )
```

- [ ] **Step 12: Add _build_bus_event_button_dict and _build_bus_event_vdsd helpers**

Add as methods of `DeviceSubentryFlowHandler` (e.g. near the other helpers around line 1970):

```python
def _build_bus_event_button_dict(
    self,
    mapping: dict,
    filter_dict: dict[str, str],
    btn_idx: int = 0,
) -> dict:
    """Build a button storage dict for a bus-event button."""
    bus_event = mapping["bus_event"]
    btn_cfg = mapping["button"]

    # Build click map — handle deCONZ stride-based multi-button codes
    default_map = dict(bus_event["default_click_map"])
    stride = bus_event.get("event_code_button_stride")
    if stride and btn_idx > 0:
        suffixes = {2: 0, 4: 1, 1: 4, 3: 6}  # suffix → dS CT
        default_map = {
            (btn_idx + 1) * stride + suffix: ct
            for suffix, ct in suffixes.items()
        }

    def _int_val(v):
        return v.value if hasattr(v, "value") else int(v)

    return {
        "dsIndex": 0,
        "name": mapping["model"],
        "buttonType": _int_val(btn_cfg["button_type"]),
        "buttonElementID": 0,
        "group": _int_val(btn_cfg["group"]),
        "function": _int_val(btn_cfg["function"]),
        "mode": _int_val(btn_cfg["mode"]),
        "channel": 0,
        "supportsLocalKeyMode": btn_cfg.get("supports_local_key_mode", False),
        "setsLocalPriority": False,
        "callsPresent": btn_cfg.get("calls_present", False),
        "buttonID": 0,
        "callbackType": "bus_event",
        "callback_entity": None,
        "bus_event_type": bus_event["event_type"],
        "bus_event_filter": dict(filter_dict),
        "bus_event_click_field": bus_event["click_field"],
        "bus_event_mode": bus_event["bus_event_mode"],
        "bus_event_click_map": default_map,
    }


def _build_bus_event_vdsd(
    self,
    mapping: dict,
    buttons: list[dict],
    name: str,
) -> dict:
    """Build a complete vdSD data dict for a bus-event device."""
    import uuid as _uuid_mod

    def _int_val(v):
        return v.value if hasattr(v, "value") else int(v)

    pg = mapping["primary_group"]
    uid_seed = f"bus_event_{mapping['integration']}_{name}"
    hardware_guid = "uuid:" + str(
        _uuid_mod.uuid5(_uuid_mod.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"), uid_seed)
    )

    from .api import derive_model_features_for_config

    vdsd: dict = {
        "displayId": mapping["model"],
        "primaryGroup": _int_val(pg),
        "model": mapping["model"],
        "vendorName": mapping["vendor_name"],
        "modelVersion": "1.0",
        "modelUID": mapping["model_uid"],
        "name": name,
        "hardwareGuid": hardware_guid,
        "identify_action": None,
        "firmwareUpdate_action": None,
        "optional": {},
        "buttons": buttons,
        "binary_inputs": [],
        "sensors": [],
        "output": None,
    }
    auto_features = derive_model_features_for_config(vdsd)
    vdsd["model_features"] = sorted(auto_features)
    return vdsd
```

- [ ] **Step 13: Run all config flow tests**

```bash
python3 -m pytest tests/test_config_flow.py -k "bus_event or entity_type_picker" -v 2>&1 | tail -30
```

Expected: all new tests pass; no existing tests broken.

Run the full test suite:
```bash
python3 -m pytest tests/ -v 2>&1 | tail -30
```

Expected: all tests pass.

- [ ] **Step 14: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py custom_components/dsvdc4ha/strings.json tests/test_config_flow.py
git commit -m "feat: add native bus-event button config flow steps (entity_type_picker, discriminator, count, topology, independent/group paths)"
```

---

## Self-Review

Spec requirements vs plan coverage:

| Spec requirement | Covered by |
|---|---|
| `BusEventTimingEngine` with `signal_press()`/`signal_release()` | Task 1 |
| Press-only mode (50 ms guard) | Task 1 (`_press_only_guard_timer`) |
| `ButtonEventTranslator` delegates binary-sensor path to engine | Task 1 (step 4) |
| 6 bus-event entries in `entity_mapping.py` | Task 2 |
| `BUS_EVENT_MAPPING`, `get_bus_event_mapping()` | Task 2 |
| `setup_bus_event_listeners()` — direct mode filter + click_map lookup | Task 3 |
| `setup_bus_event_listeners()` — timed mode with `BusEventTimingEngine` | Task 3 |
| Unsub cancels engine for timed mode | Task 3 |
| Call site in `__init__.py` (2 places) | Task 3 |
| `from_entity` creation mode routes to type picker | Task 4 (step 5) |
| `entity_type_picker` step with HA + 6 bus-event options | Task 4 (step 6) |
| `prefer_event_entity` guidance in discriminator | Task 4 (step 7) |
| Discriminator step per integration | Task 4 (step 7) |
| Count step, skips topology when count=1 | Task 4 (step 8) |
| Topology step with 2 options | Task 4 (step 9) |
| Independent path: N discriminators → N vdSDs | Task 4 (step 10) |
| Group path: 1 vdSD with N buttons, model_features | Task 4 (step 11) |
| Storage format with `bus_event_*` fields | Task 4 (steps 12) |
| deCONZ multi-button click_map stride generation | Task 4 (`_build_bus_event_button_dict`) |
| `strings.json` labels for all 7 new steps | Task 4 (step 3) |
| All spec test cases | Tasks 1, 2, 3, 4 |

**No placeholder text** — every step has complete code. All type names, method signatures, and field names are consistent across tasks (`_bus_event_integration`, `bus_event_filter`, `signal_press`/`signal_release`, `BusEventTimingEngine.cancel()`).
