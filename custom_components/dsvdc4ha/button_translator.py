"""Translate HA entity press activity into dS pushbutton click types.

Three source-entity modes, auto-selected by entity domain:

binary_sensor  Full timing state machine (H/L measurement).  Most accurate.
               Measures actual press duration and inter-press gaps to
               distinguish Single/Multi Click vs Single/Multi Tip vs Hold.

event          Maps HA event_type strings directly to click types.  Works
               with ZHA, Z2M, ZWave-JS, Hue, and any platform that exposes
               an event entity with event_type in its state.

button / other Timestamp-diff heuristic: state holds the press-start time,
               last_changed reflects when HA received (≈ released) the event.
               If the gap ≥ 500 ms → HOLD_START + HOLD_END.
               Otherwise → accumulate Tip presses.

Timing constants are taken directly from dS spec Table 8 (ds-basics.pdf §10.1.1).
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Awaitable, Callable

from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.helpers.event import async_track_state_change_event

_LOGGER = logging.getLogger(__name__)

# ── Timing thresholds (seconds) — dS spec Table 8 ───────────────────────────
_CLICK_MAX = 0.140      # H < 140 ms → click
_TIP_MIN = 0.140        # H ≥ 140 ms → tip boundary
_HOLD_MIN = 0.500       # H ≥ 500 ms → hold starts; fires HOLD_START while still held
_TIP_GAP_MAX = 0.800    # gap between tips must be < 800 ms
_CLICK_GAP_MAX = 0.140  # gap between clicks must be < 140 ms
_HOLD_REPEAT_INTERVAL = 1.0  # HOLD_REPEAT fires every ~1 s during hold

# ── dS click-type values — dS spec Tables 9–19 ──────────────────────────────
CT_TIP_1X    = 0
CT_TIP_2X    = 1
CT_TIP_3X    = 2
CT_TIP_4X    = 3
CT_HOLD_START  = 4
CT_HOLD_REPEAT = 5
CT_HOLD_END    = 6
CT_CLICK_1X  = 7
CT_CLICK_2X  = 8
CT_CLICK_3X  = 9

_TIP_FOR_COUNT   = (CT_TIP_1X,   CT_TIP_2X,   CT_TIP_3X,   CT_TIP_4X)   # index = count-1
_CLICK_FOR_COUNT = (CT_CLICK_1X, CT_CLICK_2X, CT_CLICK_3X)               # index = count-1


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
        # Pending press-only tip count: incremented by the guard when a press
        # arrives with no release within PRESS_ONLY_GUARD ms.  The commit task
        # flushes accumulated pending tips into _accumulate after TIP_GAP_MAX.
        self._pending_tips: int = 0
        self._commit_task: asyncio.Task | None = None

    def signal_press(self) -> None:
        """Feed a press (H-start) signal into the state machine."""
        self._press_start = time.monotonic()
        self._cancel_gap_task()
        self._cancel_commit_task()
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

        # If the press-only guard had flagged this press as a pending tip,
        # cancel that — we now have a real release and can classify by duration.
        if self._pending_tips > 0:
            self._pending_tips -= 1
            self._cancel_commit_task()
            # Re-start commit task only if there are still remaining pending tips.
            if self._pending_tips > 0:
                self._commit_task = self._hass.async_create_task(
                    self._commit_pending_tips()
                )

        if h >= _HOLD_MIN:
            # Hold_task was cancelled by the press-only guard, but the press was
            # actually long enough to be a hold.  Synthesise the hold events based
            # on actual duration (HOLD_START + N×HOLD_REPEAT + HOLD_END).
            self._hass.async_create_task(self._synthesise_hold(h))
        elif h < _CLICK_MAX:
            self._accumulate("click")
        else:
            # _CLICK_MAX ≤ h < _HOLD_MIN → tip
            self._accumulate("tip")

    def cancel(self) -> None:
        """Cancel all pending tasks — call when unregistering the listener."""
        self._cancel_gap_task()
        self._cancel_commit_task()
        self._pending_tips = 0
        for task_attr in ("_hold_task", "_press_only_task"):
            task = getattr(self, task_attr)
            if task and not task.done():
                task.cancel()
            setattr(self, task_attr, None)

    async def _press_only_guard_timer(self) -> None:
        await asyncio.sleep(self._PRESS_ONLY_GUARD)
        self._press_only_task = None
        # Cancel the hold sequence — if a genuine hold occurs, signal_release()
        # will detect h ≥ HOLD_MIN and synthesise the hold events itself.
        if self._hold_task and not self._hold_task.done():
            self._hold_task.cancel()
        self._hold_task = None
        self._pending_tips += 1
        self._cancel_commit_task()
        self._commit_task = self._hass.async_create_task(self._commit_pending_tips())

    async def _synthesise_hold(self, duration: float) -> None:
        """Emit HOLD_START + N×HOLD_REPEAT + HOLD_END for a press-only-guard hold."""
        repeat_count = max(0, int((duration - _HOLD_MIN) / _HOLD_REPEAT_INTERVAL))
        await self._on_click(CT_HOLD_START)
        for _ in range(repeat_count):
            await self._on_click(CT_HOLD_REPEAT)
        await self._on_click(CT_HOLD_END)

    async def _commit_pending_tips(self) -> None:
        """Wait TIP_GAP_MAX, then flush all pending press-only tips."""
        await asyncio.sleep(_TIP_GAP_MAX)
        count = self._pending_tips
        self._pending_tips = 0
        self._commit_task = None
        if count > 0:
            # Emit directly — don't go through _accumulate to avoid interacting
            # with existing click/tip accumulation state.
            ct = _TIP_FOR_COUNT[min(count, 4) - 1]
            _LOGGER.debug(
                "BusEventTimingEngine: press-only × %d → click_type %d", count, ct
            )
            self._hass.async_create_task(self._on_click(ct))

    def _cancel_commit_task(self) -> None:
        if self._commit_task and not self._commit_task.done():
            self._commit_task.cancel()
        self._commit_task = None

    async def _hold_sequence(self) -> None:
        await asyncio.sleep(_HOLD_MIN)
        if self._press_only_task and not self._press_only_task.done():
            self._press_only_task.cancel()
        self._press_only_task = None
        # If the press-only guard queued a pending tip, cancel it — this is a hold.
        self._cancel_commit_task()
        self._pending_tips = 0
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


# ── Default event_type → click_type mapping for HA event entities ────────────
# Covers ZHA, Z2M, Hue, and other common naming conventions.
DEFAULT_EVENT_TYPE_MAP: dict[str, int] = {
    # ── single press ──
    "press":           CT_TIP_1X,
    "single":          CT_TIP_1X,
    "single_press":    CT_TIP_1X,
    "short_press":     CT_TIP_1X,
    "1_times":         CT_TIP_1X,
    # ── multi-press ──
    "double_press":    CT_TIP_2X,
    "2_times":         CT_TIP_2X,
    "triple_press":    CT_TIP_3X,
    "3_times":         CT_TIP_3X,
    "quadruple_press": CT_TIP_4X,
    "4_times":         CT_TIP_4X,
    # ── hold start / repeat / end ──
    "long_press":      CT_HOLD_START,
    "hold":            CT_HOLD_START,
    "held":            CT_HOLD_START,
    "initial_press":   CT_HOLD_START,
    "hold_start":      CT_HOLD_START,
    "repeat":          CT_HOLD_REPEAT,
    "hold_repeat":     CT_HOLD_REPEAT,
    "long_release":    CT_HOLD_END,
    "release":         CT_HOLD_END,
    "hold_end":        CT_HOLD_END,
    "end":             CT_HOLD_END,
}


class ButtonEventTranslator:
    """Watches an HA entity and emits dS click types via *on_click*.

    Usage::

        async def _report(ct: int) -> None:
            await api.report_button_click(button_input, ct)

        translator = ButtonEventTranslator(hass, "binary_sensor.hall_btn", _report)
        unsub = translator.setup()          # register listeners
        # …later…
        unsub()                             # unregister + cancel pending tasks
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entity_id: str,
        on_click: Callable[[int], Awaitable[None]],
        event_type_map: dict[str, int] | None = None,
    ) -> None:
        self._hass = hass
        self._entity_id = entity_id
        self._on_click = on_click
        self._event_type_map: dict[str, int] = {
            **DEFAULT_EVENT_TYPE_MAP,
            **(event_type_map or {}),
        }
        self._source_domain = entity_id.split(".")[0]

        # ── Shared press-accumulation state ─────────────────────────────────
        self._press_count: int = 0
        self._press_kind: str | None = None   # "tip" or "click"
        self._gap_task: asyncio.Task | None = None

        # ── Binary-sensor / hold state ───────────────────────────────────────
        self._press_start: float | None = None   # monotonic time of press start
        self._hold_task: asyncio.Task | None = None
        self._in_hold: bool = False              # True while HOLD_START fired but HOLD_END not yet

    # ── Public API ───────────────────────────────────────────────────────────

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

    # ── Binary-sensor source ─────────────────────────────────────────────────

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

    # ── Event-entity source ──────────────────────────────────────────────────

    def _setup_event_entity(self) -> Callable[[], None]:
        @callback
        def _on_state(event: Event) -> None:
            new = event.data.get("new_state")
            if new is None or new.state in ("unknown", "unavailable"):
                return
            # HA event entities store the event_type as their state value.
            event_type = new.state.lower()
            ct = self._event_type_map.get(event_type)
            if ct is None:
                _LOGGER.debug(
                    "%s: unmapped event_type %r — add it to event_type_map",
                    self._entity_id, event_type,
                )
                return
            self._handle_event_click(ct)

        return async_track_state_change_event(self._hass, self._entity_id, _on_state)

    def _handle_event_click(self, ct: int) -> None:
        """Handle a click-type derived from an event_type mapping."""
        if ct == CT_HOLD_START:
            if self._in_hold:
                # Device is sending repeated hold events → map to HOLD_REPEAT.
                ct = CT_HOLD_REPEAT
            else:
                self._in_hold = True
                # Schedule automatic HOLD_END after one interval if the device
                # doesn't send an explicit long_release / hold_end event.
                self._hold_task = self._hass.async_create_task(self._auto_hold_end())

        elif ct == CT_HOLD_REPEAT:
            if not self._in_hold:
                # Got repeat without prior start — synthesise HOLD_START first.
                self._in_hold = True
                self._hass.async_create_task(self._on_click(CT_HOLD_START))

        elif ct == CT_HOLD_END:
            self._in_hold = False
            # If we had an auto-end pending, cancel it — explicit end takes over.
            if self._hold_task and not self._hold_task.done():
                self._hold_task.cancel()
            self._hold_task = None

        self._hass.async_create_task(self._on_click(ct))

    async def _auto_hold_end(self) -> None:
        """Fire HOLD_END after one hold-repeat interval if no explicit release arrives."""
        await asyncio.sleep(_HOLD_REPEAT_INTERVAL)
        self._hold_task = None
        self._in_hold = False
        await self._on_click(CT_HOLD_END)

    # ── Button / generic entity source ───────────────────────────────────────

    def _setup_button_entity(self) -> Callable[[], None]:
        @callback
        def _on_state(event: Event) -> None:
            new = event.data.get("new_state")
            if new is None or new.state in ("unknown", "unavailable", "None", "none"):
                return

            # Attempt 1: state is an ISO timestamp (button / input_button).
            # Compare to last_changed (≈ when HA received the release event from
            # the device) to estimate hold duration.
            try:
                press_time = datetime.fromisoformat(new.state)
                event_time = new.last_changed
                if event_time.tzinfo is None:
                    event_time = event_time.replace(tzinfo=timezone.utc)
                if press_time.tzinfo is None:
                    press_time = press_time.replace(tzinfo=timezone.utc)
                duration = (event_time - press_time).total_seconds()
                if duration >= _HOLD_MIN:
                    self._cancel_gap_task()
                    self._press_count = 0
                    self._press_kind = None
                    self._hass.async_create_task(self._btn_hold())
                else:
                    # Treat as a tip (deliberate short press).
                    self._accumulate("tip")
                return
            except (ValueError, TypeError):
                pass

            # Attempt 2: state is an event-type string (sensor.last_action, etc.).
            ct = self._event_type_map.get(new.state.lower())
            if ct is not None:
                self._handle_event_click(ct)

        return async_track_state_change_event(self._hass, self._entity_id, _on_state)

    async def _btn_hold(self) -> None:
        """Simulate hold sequence for button entities.

        For button entities we have no ongoing press signal — we know the press
        happened and infer it was long.  Report HOLD_START + HOLD_END as a pair.
        """
        await self._on_click(CT_HOLD_START)
        await self._on_click(CT_HOLD_END)

    # ── Shared press accumulation ─────────────────────────────────────────────

    def _accumulate(self, kind: str) -> None:
        """Add one press of *kind* ("tip" or "click") to the current sequence.

        Starts (or restarts) the inter-press gap timer.  When the timer fires
        (no further press arrived within the gap window), the accumulated count
        is emitted as the corresponding click type.
        """
        if self._press_kind and self._press_kind != kind:
            # Mixed tip/click sequence — emit what we had and start fresh.
            self._emit_accumulated()

        self._press_kind = kind
        self._press_count = min(self._press_count + 1, 4)  # dS supports up to 4x tip / 3x click

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

        _LOGGER.debug("%s: %s × %d → click_type %d", self._entity_id, kind, count, ct)
        self._hass.async_create_task(self._on_click(ct))

    def _cancel_gap_task(self) -> None:
        if self._gap_task and not self._gap_task.done():
            self._gap_task.cancel()
        self._gap_task = None
