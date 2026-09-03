"""Analyze HA entity history to derive sensor update-interval estimates."""
from __future__ import annotations

import statistics
from datetime import timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_HISTORY_HOURS = 24
_MIN_GAPS = 3          # need at least 3 gap samples for a meaningful median
_ALIVE_FACTOR = 5.0    # aliveSignInterval = ALIVE_FACTOR × updateInterval


async def analyze_sensor_intervals(
    hass: HomeAssistant,
    entity_id: str,
) -> dict[str, float] | None:
    """Return derived sensor interval settings from 24 h of recorder history.

    Computes the median gap between state-changes (excluding unavailable /
    unknown states) and derives the four interval parameters:
        update_interval      – median gap (seconds)
        alive_sign_interval  – 5 × update_interval
        min_push_interval    – equal to update_interval
        changes_only_interval– equal to update_interval

    Returns None when the entity has fewer than 3 valid state-change gaps in
    the last 24 hours (new entity, very sparse updates, or recorder not loaded).
    """
    try:
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder import history as rec_history
        from homeassistant.util import dt as dt_util
    except ImportError:
        return None

    now = dt_util.utcnow()
    start = now - timedelta(hours=_HISTORY_HOURS)

    try:
        instance = get_instance(hass)
        states_map: dict = await instance.async_add_executor_job(
            rec_history.state_changes_during_period,
            hass,
            start,
            now,
            entity_id,
            True,   # no_attributes – we only need timestamps and state string
        )
    except Exception:
        return None

    raw_states = states_map.get(entity_id, [])

    # Keep only states with a parseable numeric value (or any valid state for
    # non-numeric entities).  The key requirement is: not unavailable / unknown.
    valid = [
        s for s in raw_states
        if s.state not in ("unavailable", "unknown")
        and s.last_changed is not None
    ]

    if len(valid) < _MIN_GAPS + 1:
        return None

    valid.sort(key=lambda s: s.last_changed)

    gaps = [
        (valid[i + 1].last_changed - valid[i].last_changed).total_seconds()
        for i in range(len(valid) - 1)
    ]
    gaps = [g for g in gaps if g > 0]

    if len(gaps) < _MIN_GAPS:
        return None

    update_interval = statistics.median(gaps)
    alive_sign_interval = update_interval * _ALIVE_FACTOR

    return {
        "update_interval": round(update_interval, 2),
        "alive_sign_interval": round(alive_sign_interval, 2),
        "min_push_interval": round(update_interval, 2),
        "changes_only_interval": round(update_interval, 2),
    }
