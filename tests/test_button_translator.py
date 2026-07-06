"""Tests for ButtonEventTranslator — all three source-entity modes."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from custom_components.dsvdc4ha.button_translator import (
    ButtonEventTranslator,
    CT_TIP_1X,
    CT_TIP_2X,
    CT_TIP_3X,
    CT_TIP_4X,
    CT_HOLD_START,
    CT_HOLD_REPEAT,
    CT_HOLD_END,
    CT_CLICK_1X,
    CT_CLICK_2X,
    CT_CLICK_3X,
    DEFAULT_EVENT_TYPE_MAP,
    _CLICK_GAP_MAX,
    _TIP_GAP_MAX,
    _HOLD_MIN,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(state: str, entity_id: str = "binary_sensor.btn"):
    s = MagicMock()
    s.state = state
    s.entity_id = entity_id
    return s


def _make_state_event(new_state_value: str, entity_id: str = "binary_sensor.btn"):
    evt = MagicMock()
    evt.data = {"new_state": _make_state(new_state_value, entity_id)}
    return evt


def _make_hass(initial_state=None):
    hass = MagicMock()
    hass.states.get.return_value = initial_state
    tasks = []

    def _create_task(coro):
        task = asyncio.ensure_future(coro)
        tasks.append(task)
        return task

    hass.async_create_task.side_effect = _create_task
    hass._tasks = tasks
    return hass


# ---------------------------------------------------------------------------
# Event-entity source
# ---------------------------------------------------------------------------

class TestEventEntity:
    """ButtonEventTranslator with an event.* source entity."""

    def setup_method(self):
        self.clicks: list[int] = []

        async def _on_click(ct: int) -> None:
            self.clicks.append(ct)

        self.hass = _make_hass()
        self.unsub = MagicMock()

    @pytest.mark.asyncio
    async def test_single_press_maps_to_tip1(self):
        with patch(
            "custom_components.dsvdc4ha.button_translator.async_track_state_change_event",
            return_value=self.unsub,
        ) as mock_track:
            async def _on_click(ct):
                self.clicks.append(ct)

            tr = ButtonEventTranslator(self.hass, "event.btn", _on_click)
            cleanup = tr.setup()

            # capture the callback
            cb = mock_track.call_args[0][2]
            cb(_make_state_event("single_press", "event.btn"))
            await asyncio.sleep(0)

            assert self.clicks == [CT_TIP_1X]
            cleanup()

    @pytest.mark.asyncio
    async def test_double_press_maps_to_tip2(self):
        with patch(
            "custom_components.dsvdc4ha.button_translator.async_track_state_change_event",
            return_value=self.unsub,
        ) as mock_track:
            async def _on_click(ct):
                self.clicks.append(ct)

            tr = ButtonEventTranslator(self.hass, "event.btn", _on_click)
            cleanup = tr.setup()
            cb = mock_track.call_args[0][2]

            cb(_make_state_event("double_press", "event.btn"))
            await asyncio.sleep(0)

            assert self.clicks == [CT_TIP_2X]
            cleanup()

    @pytest.mark.asyncio
    async def test_hold_start_then_release(self):
        with patch(
            "custom_components.dsvdc4ha.button_translator.async_track_state_change_event",
            return_value=self.unsub,
        ) as mock_track:
            async def _on_click(ct):
                self.clicks.append(ct)

            tr = ButtonEventTranslator(self.hass, "event.btn", _on_click)
            cleanup = tr.setup()
            cb = mock_track.call_args[0][2]

            cb(_make_state_event("long_press", "event.btn"))
            await asyncio.sleep(0)
            cb(_make_state_event("long_release", "event.btn"))
            await asyncio.sleep(0)

            assert CT_HOLD_START in self.clicks
            assert CT_HOLD_END in self.clicks
            cleanup()

    @pytest.mark.asyncio
    async def test_hold_repeat_without_prior_start_synthesises_hold_start(self):
        with patch(
            "custom_components.dsvdc4ha.button_translator.async_track_state_change_event",
            return_value=self.unsub,
        ) as mock_track:
            async def _on_click(ct):
                self.clicks.append(ct)

            tr = ButtonEventTranslator(self.hass, "event.btn", _on_click)
            cleanup = tr.setup()
            cb = mock_track.call_args[0][2]

            cb(_make_state_event("repeat", "event.btn"))
            await asyncio.sleep(0)

            assert self.clicks[0] == CT_HOLD_START
            assert CT_HOLD_REPEAT in self.clicks
            cleanup()

    @pytest.mark.asyncio
    async def test_unmapped_event_type_ignored(self):
        with patch(
            "custom_components.dsvdc4ha.button_translator.async_track_state_change_event",
            return_value=self.unsub,
        ) as mock_track:
            async def _on_click(ct):
                self.clicks.append(ct)

            tr = ButtonEventTranslator(self.hass, "event.btn", _on_click)
            cleanup = tr.setup()
            cb = mock_track.call_args[0][2]

            cb(_make_state_event("unknown_action", "event.btn"))
            await asyncio.sleep(0)

            assert self.clicks == []
            cleanup()

    @pytest.mark.asyncio
    async def test_custom_event_type_map_overrides_default(self):
        with patch(
            "custom_components.dsvdc4ha.button_translator.async_track_state_change_event",
            return_value=self.unsub,
        ) as mock_track:
            async def _on_click(ct):
                self.clicks.append(ct)

            tr = ButtonEventTranslator(
                self.hass, "event.btn", _on_click,
                event_type_map={"my_action": CT_TIP_4X},
            )
            cleanup = tr.setup()
            cb = mock_track.call_args[0][2]

            cb(_make_state_event("my_action", "event.btn"))
            await asyncio.sleep(0)

            assert CT_TIP_4X in self.clicks
            cleanup()

    @pytest.mark.asyncio
    async def test_unknown_or_unavailable_state_ignored(self):
        with patch(
            "custom_components.dsvdc4ha.button_translator.async_track_state_change_event",
            return_value=self.unsub,
        ) as mock_track:
            async def _on_click(ct):
                self.clicks.append(ct)

            tr = ButtonEventTranslator(self.hass, "event.btn", _on_click)
            cleanup = tr.setup()
            cb = mock_track.call_args[0][2]

            for bad in ("unknown", "unavailable"):
                cb(_make_state_event(bad, "event.btn"))
            await asyncio.sleep(0)

            assert self.clicks == []
            cleanup()

    @pytest.mark.asyncio
    async def test_none_new_state_ignored(self):
        with patch(
            "custom_components.dsvdc4ha.button_translator.async_track_state_change_event",
            return_value=self.unsub,
        ) as mock_track:
            async def _on_click(ct):
                self.clicks.append(ct)

            tr = ButtonEventTranslator(self.hass, "event.btn", _on_click)
            cleanup = tr.setup()
            cb = mock_track.call_args[0][2]

            evt = MagicMock()
            evt.data = {"new_state": None}
            cb(evt)
            await asyncio.sleep(0)

            assert self.clicks == []
            cleanup()


# ---------------------------------------------------------------------------
# Binary-sensor source — timing state machine
# ---------------------------------------------------------------------------

class TestBinarySensorSource:
    """ButtonEventTranslator with a binary_sensor.* source entity."""

    def _setup(self, initial_state: str | None = None):
        self.clicks: list[int] = []

        async def _on_click(ct: int) -> None:
            self.clicks.append(ct)

        initial = _make_state(initial_state, "binary_sensor.btn") if initial_state else None
        self.hass = _make_hass(initial)
        self.unsub = MagicMock()
        self._on_click = _on_click

    @pytest.mark.asyncio
    async def test_short_press_emits_click(self):
        self._setup()
        with patch(
            "custom_components.dsvdc4ha.button_translator.async_track_state_change_event",
            return_value=self.unsub,
        ) as mock_track, patch("custom_components.dsvdc4ha.button_translator.time") as mock_time:
            mock_time.monotonic.side_effect = [0.0, 0.05]  # press at 0, release at 50ms

            tr = ButtonEventTranslator(self.hass, "binary_sensor.btn", self._on_click)
            cleanup = tr.setup()
            cb = mock_track.call_args[0][2]

            cb(_make_state_event("on"))
            cb(_make_state_event("off"))
            await asyncio.sleep(_CLICK_GAP_MAX + 0.05)

            assert CT_CLICK_1X in self.clicks
            cleanup()

    @pytest.mark.asyncio
    async def test_medium_press_emits_tip(self):
        self._setup()
        with patch(
            "custom_components.dsvdc4ha.button_translator.async_track_state_change_event",
            return_value=self.unsub,
        ) as mock_track, patch("custom_components.dsvdc4ha.button_translator.time") as mock_time:
            mock_time.monotonic.side_effect = [0.0, 0.200]  # 200ms — tip range

            tr = ButtonEventTranslator(self.hass, "binary_sensor.btn", self._on_click)
            cleanup = tr.setup()
            cb = mock_track.call_args[0][2]

            cb(_make_state_event("on"))
            cb(_make_state_event("off"))
            await asyncio.sleep(_TIP_GAP_MAX + 0.05)

            assert CT_TIP_1X in self.clicks
            cleanup()

    @pytest.mark.asyncio
    async def test_long_press_emits_hold_start_and_hold_end(self):
        self._setup()
        with patch(
            "custom_components.dsvdc4ha.button_translator.async_track_state_change_event",
            return_value=self.unsub,
        ) as mock_track:
            tr = ButtonEventTranslator(self.hass, "binary_sensor.btn", self._on_click)
            cleanup = tr.setup()
            cb = mock_track.call_args[0][2]

            cb(_make_state_event("on"))
            await asyncio.sleep(_HOLD_MIN + 0.05)  # wait for HOLD_START to fire
            cb(_make_state_event("off"))
            await asyncio.sleep(0.05)

            assert self.clicks[0] == CT_HOLD_START
            assert CT_HOLD_END in self.clicks
            cleanup()

    @pytest.mark.asyncio
    async def test_hold_repeat_fires_while_held(self):
        self._setup()
        with patch(
            "custom_components.dsvdc4ha.button_translator.async_track_state_change_event",
            return_value=self.unsub,
        ) as mock_track:
            tr = ButtonEventTranslator(self.hass, "binary_sensor.btn", self._on_click)
            cleanup = tr.setup()
            cb = mock_track.call_args[0][2]

            cb(_make_state_event("on"))
            # Wait past HOLD_START + one HOLD_REPEAT
            await asyncio.sleep(_HOLD_MIN + 1.1)
            cb(_make_state_event("off"))
            await asyncio.sleep(0.05)

            assert CT_HOLD_REPEAT in self.clicks
            cleanup()

    @pytest.mark.asyncio
    async def test_initial_state_on_seeds_press(self):
        self._setup(initial_state="on")
        with patch(
            "custom_components.dsvdc4ha.button_translator.async_track_state_change_event",
            return_value=self.unsub,
        ):
            tr = ButtonEventTranslator(self.hass, "binary_sensor.btn", self._on_click)
            cleanup = tr.setup()

            # press_start was set — simulate release immediately
            await asyncio.sleep(0)
            # _hold_task should be pending (was scheduled on setup)
            assert tr._hold_task is not None
            cleanup()

    @pytest.mark.asyncio
    async def test_double_short_press_emits_click_2x(self):
        self._setup()
        with patch(
            "custom_components.dsvdc4ha.button_translator.async_track_state_change_event",
            return_value=self.unsub,
        ) as mock_track, patch("custom_components.dsvdc4ha.button_translator.time") as mock_time:
            # Two 50ms presses separated by < 140ms gap
            mock_time.monotonic.side_effect = [0.0, 0.05, 0.10, 0.15]

            tr = ButtonEventTranslator(self.hass, "binary_sensor.btn", self._on_click)
            cleanup = tr.setup()
            cb = mock_track.call_args[0][2]

            cb(_make_state_event("on"))
            cb(_make_state_event("off"))
            cb(_make_state_event("on"))
            cb(_make_state_event("off"))
            await asyncio.sleep(_CLICK_GAP_MAX + 0.05)

            assert CT_CLICK_2X in self.clicks
            cleanup()


# ---------------------------------------------------------------------------
# Button / generic entity source
# ---------------------------------------------------------------------------

class TestButtonEntitySource:
    """ButtonEventTranslator with a button.* source entity."""

    def _setup(self):
        self.clicks: list[int] = []

        async def _on_click(ct: int) -> None:
            self.clicks.append(ct)

        self.hass = _make_hass()
        self.unsub = MagicMock()
        self._on_click = _on_click

    def _iso_state(self, press_ago_secs: float, entity_id: str = "button.btn"):
        now = datetime.now(timezone.utc)
        press_time = now.timestamp() - press_ago_secs
        press_dt = datetime.fromtimestamp(press_time, tz=timezone.utc)
        st = MagicMock()
        st.state = press_dt.isoformat()
        st.last_changed = now
        st.entity_id = entity_id
        return st

    @pytest.mark.asyncio
    async def test_short_timestamp_press_emits_tip(self):
        self._setup()
        with patch(
            "custom_components.dsvdc4ha.button_translator.async_track_state_change_event",
            return_value=self.unsub,
        ) as mock_track:
            tr = ButtonEventTranslator(self.hass, "button.btn", self._on_click)
            cleanup = tr.setup()
            cb = mock_track.call_args[0][2]

            state = self._iso_state(press_ago_secs=0.1)  # 100ms press
            evt = MagicMock()
            evt.data = {"new_state": state}
            cb(evt)
            await asyncio.sleep(_TIP_GAP_MAX + 0.05)

            assert CT_TIP_1X in self.clicks
            cleanup()

    @pytest.mark.asyncio
    async def test_long_timestamp_press_emits_hold(self):
        self._setup()
        with patch(
            "custom_components.dsvdc4ha.button_translator.async_track_state_change_event",
            return_value=self.unsub,
        ) as mock_track:
            tr = ButtonEventTranslator(self.hass, "button.btn", self._on_click)
            cleanup = tr.setup()
            cb = mock_track.call_args[0][2]

            state = self._iso_state(press_ago_secs=0.6)  # 600ms press
            evt = MagicMock()
            evt.data = {"new_state": state}
            cb(evt)
            await asyncio.sleep(0.05)

            assert CT_HOLD_START in self.clicks
            assert CT_HOLD_END in self.clicks
            cleanup()

    @pytest.mark.asyncio
    async def test_event_type_string_state_dispatches_correctly(self):
        self._setup()
        with patch(
            "custom_components.dsvdc4ha.button_translator.async_track_state_change_event",
            return_value=self.unsub,
        ) as mock_track:
            tr = ButtonEventTranslator(self.hass, "button.btn", self._on_click)
            cleanup = tr.setup()
            cb = mock_track.call_args[0][2]

            st = MagicMock()
            st.state = "single"
            evt = MagicMock()
            evt.data = {"new_state": st}
            cb(evt)
            await asyncio.sleep(0)

            assert CT_TIP_1X in self.clicks
            cleanup()

    @pytest.mark.asyncio
    async def test_none_or_unknown_state_ignored(self):
        self._setup()
        with patch(
            "custom_components.dsvdc4ha.button_translator.async_track_state_change_event",
            return_value=self.unsub,
        ) as mock_track:
            tr = ButtonEventTranslator(self.hass, "button.btn", self._on_click)
            cleanup = tr.setup()
            cb = mock_track.call_args[0][2]

            for bad_state in ("unknown", "unavailable", "None", "none"):
                st = MagicMock()
                st.state = bad_state
                evt = MagicMock()
                evt.data = {"new_state": st}
                cb(evt)
            await asyncio.sleep(0)

            assert self.clicks == []
            cleanup()


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

class TestCleanup:
    """setup() returns a callable that cancels pending tasks on invocation."""

    @pytest.mark.asyncio
    async def test_cleanup_cancels_gap_task(self):
        clicks: list[int] = []

        async def _on_click(ct):
            clicks.append(ct)

        hass = _make_hass()
        unsub = MagicMock()

        with patch(
            "custom_components.dsvdc4ha.button_translator.async_track_state_change_event",
            return_value=unsub,
        ) as mock_track, patch("custom_components.dsvdc4ha.button_translator.time") as mock_time:
            mock_time.monotonic.side_effect = [0.0, 0.05]

            tr = ButtonEventTranslator(hass, "binary_sensor.btn", _on_click)
            cleanup = tr.setup()
            cb = mock_track.call_args[0][2]

            cb(_make_state_event("on"))
            cb(_make_state_event("off"))
            # gap task is now pending
            assert tr._gap_task is not None
            assert not tr._gap_task.done()

            cleanup()
            # unsub was called
            unsub.assert_called_once()
            # gap task was cancelled
            assert tr._gap_task is None or tr._gap_task.cancelled()

    @pytest.mark.asyncio
    async def test_cleanup_cancels_hold_task(self):
        clicks: list[int] = []

        async def _on_click(ct):
            clicks.append(ct)

        hass = _make_hass()
        unsub = MagicMock()

        with patch(
            "custom_components.dsvdc4ha.button_translator.async_track_state_change_event",
            return_value=unsub,
        ) as mock_track:
            tr = ButtonEventTranslator(hass, "binary_sensor.btn", _on_click)
            cleanup = tr.setup()
            cb = mock_track.call_args[0][2]

            cb(_make_state_event("on"))
            assert tr._hold_task is not None

            cleanup()
            unsub.assert_called_once()
            assert tr._hold_task is None


# ---------------------------------------------------------------------------
# Accumulation logic
# ---------------------------------------------------------------------------

class TestAccumulation:
    """_accumulate handles tip/click counting and mixed-kind reset."""

    @pytest.mark.asyncio
    async def test_tip_up_to_4x(self):
        clicks: list[int] = []

        async def _on_click(ct):
            clicks.append(ct)

        hass = _make_hass()
        unsub = MagicMock()

        with patch(
            "custom_components.dsvdc4ha.button_translator.async_track_state_change_event",
            return_value=unsub,
        ) as mock_track, patch("custom_components.dsvdc4ha.button_translator.time") as mock_time:
            # 4 medium presses (tip range)
            times = []
            for i in range(4):
                times.extend([i * 0.5, i * 0.5 + 0.2])
            mock_time.monotonic.side_effect = times

            tr = ButtonEventTranslator(hass, "binary_sensor.btn", _on_click)
            cleanup = tr.setup()
            cb = mock_track.call_args[0][2]

            for _ in range(4):
                cb(_make_state_event("on"))
                cb(_make_state_event("off"))

            await asyncio.sleep(_TIP_GAP_MAX + 0.05)

            assert CT_TIP_4X in clicks
            cleanup()

    @pytest.mark.asyncio
    async def test_click_up_to_3x(self):
        clicks: list[int] = []

        async def _on_click(ct):
            clicks.append(ct)

        hass = _make_hass()
        unsub = MagicMock()

        with patch(
            "custom_components.dsvdc4ha.button_translator.async_track_state_change_event",
            return_value=unsub,
        ) as mock_track, patch("custom_components.dsvdc4ha.button_translator.time") as mock_time:
            # 3 short presses (click range, < 140ms each)
            times = []
            for i in range(3):
                times.extend([i * 0.2, i * 0.2 + 0.05])
            mock_time.monotonic.side_effect = times

            tr = ButtonEventTranslator(hass, "binary_sensor.btn", _on_click)
            cleanup = tr.setup()
            cb = mock_track.call_args[0][2]

            for _ in range(3):
                cb(_make_state_event("on"))
                cb(_make_state_event("off"))

            await asyncio.sleep(_CLICK_GAP_MAX + 0.05)

            assert CT_CLICK_3X in clicks
            cleanup()


# ---------------------------------------------------------------------------
# DEFAULT_EVENT_TYPE_MAP coverage
# ---------------------------------------------------------------------------

def test_default_event_type_map_has_expected_keys():
    assert "press" in DEFAULT_EVENT_TYPE_MAP
    assert "single" in DEFAULT_EVENT_TYPE_MAP
    assert "long_press" in DEFAULT_EVENT_TYPE_MAP
    assert "long_release" in DEFAULT_EVENT_TYPE_MAP
    assert "repeat" in DEFAULT_EVENT_TYPE_MAP
    assert "double_press" in DEFAULT_EVENT_TYPE_MAP


def test_default_event_type_map_values():
    assert DEFAULT_EVENT_TYPE_MAP["press"] == CT_TIP_1X
    assert DEFAULT_EVENT_TYPE_MAP["double_press"] == CT_TIP_2X
    assert DEFAULT_EVENT_TYPE_MAP["triple_press"] == CT_TIP_3X
    assert DEFAULT_EVENT_TYPE_MAP["quadruple_press"] == CT_TIP_4X
    assert DEFAULT_EVENT_TYPE_MAP["long_press"] == CT_HOLD_START
    assert DEFAULT_EVENT_TYPE_MAP["repeat"] == CT_HOLD_REPEAT
    assert DEFAULT_EVENT_TYPE_MAP["long_release"] == CT_HOLD_END
