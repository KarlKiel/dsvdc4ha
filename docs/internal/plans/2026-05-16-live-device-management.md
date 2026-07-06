# Live Device Management Without VdcHost Restart

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the full config-entry reload triggered on every subentry add/remove with a live delta handler that adds/removes devices on the already-running VdcHost, eliminating the TCP disconnect/reconnect that causes VDC + all devices to be re-announced on every single change.

**Architecture:** The current `_async_update_listener` calls `async_reload` which tears down VdcHost (TCP disconnect + mDNS withdrawal) and rebuilds it. On reconnect, pydsvdcapi's `_on_session_ready` correctly re-announces the VDC and *all* registered devices — correct behaviour for a fresh session, but wasteful when the session should have stayed alive. The fix: compute added/removed subentries from a snapshot stored in `hass.data[DOMAIN]`, vanish/add only the delta, and dynamically manage HA platform entities without a reload. The `async_add_entities` callback from each platform's `async_setup_entry` is captured in `hass.data[DOMAIN]` and reused by the listener.

**Tech Stack:** Python, Home Assistant config entries / entity registry / device registry, pydsvdcapi `Device.announce()` / `Device.vanish()`

---

## Root Cause (for context)

- Subentry added/removed → `_async_update_listener` → `async_reload`
- `async_unload_entry` calls `coordinator.async_stop()` → `host.stop()` → TCP drops + mDNS withdrawn
- `async_setup_entry` creates a brand-new `VdcHost`, opens a new TCP session
- `_on_session_ready` fires → `VDC_SEND_ANNOUNCE_VDC` + `VDC_SEND_ANNOUNCE_DEVICE` for **every** device

pydsvdcapi's behaviour is correct — it has to announce everything on a new session. The problem is we create a new session on every single subentry change.

---

## File Structure

| File | Change |
|------|--------|
| `custom_components/dsvdc4ha/sensor.py` | Extract `_add_entities_for_subentry` helper; store callback in `hass.data[DOMAIN]` |
| `custom_components/dsvdc4ha/binary_sensor.py` | Same pattern |
| `custom_components/dsvdc4ha/__init__.py` | Add `dr` import; store `entity_index` + `_known_subentry_ids`; replace reload listener with delta listener; remove old `_async_update_listener` |
| `tests/test_init.py` | Tests for delta listener: remove, add, no-op, no-coordinator |

---

### Task 1: Expose `_add_entities_for_subentry` helper and store the `async_add_entities` callback

When a subentry is added dynamically (no reload), the listener needs to call the platform's `async_add_entities`. The only way to reach it from outside the platform is to capture it during `async_setup_entry`.

**Files:**
- Modify: `custom_components/dsvdc4ha/sensor.py`
- Modify: `custom_components/dsvdc4ha/binary_sensor.py`

No new tests — this is a pure refactor. Confirm by running all existing tests.

- [ ] **Step 1: Refactor `sensor.py`**

Replace the body of `async_setup_entry` and add the helper. Add `from typing import Any` to imports.

```python
from typing import Any

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    hass.data.setdefault(DOMAIN, {})["_add_sensor_entities"] = async_add_entities
    for subentry in entry.subentries.values():
        _add_entities_for_subentry(subentry, async_add_entities)


def _add_entities_for_subentry(
    subentry: Any, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    entities: list[DsvdcBaseEntity] = []
    for idx, vdsd_data in enumerate(subentry.data.get("vdsds", [])):
        for btn in vdsd_data.get("buttons", []):
            entities.append(ButtonSensorEntity(subentry.subentry_id, idx, vdsd_data, btn))
        for si in vdsd_data.get("sensors", []):
            entities.append(SensorInputEntity(subentry.subentry_id, idx, vdsd_data, si))
        if output := vdsd_data.get("output"):
            for ch in output.get("channels", []):
                entities.append(
                    OutputChannelEntity(subentry.subentry_id, idx, vdsd_data, output, ch)
                )
    async_add_entities(entities, config_subentry_id=subentry.subentry_id)
```

- [ ] **Step 2: Refactor `binary_sensor.py`**

```python
from typing import Any

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    hass.data.setdefault(DOMAIN, {})["_add_binary_entities"] = async_add_entities
    for subentry in entry.subentries.values():
        _add_entities_for_subentry(subentry, async_add_entities)


def _add_entities_for_subentry(
    subentry: Any, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    entities: list[DsvdcBaseEntity] = []
    for idx, vdsd_data in enumerate(subentry.data.get("vdsds", [])):
        for bi in vdsd_data.get("binary_inputs", []):
            if bi.get("valueType") == "boolean":
                entities.append(
                    BinaryInputEntity(subentry.subentry_id, idx, vdsd_data, bi)
                )
    async_add_entities(entities, config_subentry_id=subentry.subentry_id)
```

- [ ] **Step 3: Run all tests — confirm no regressions**

```bash
.venv/bin/python -m pytest tests/ -q
```
Expected: all pass, same count as before.

- [ ] **Step 4: Commit**

```bash
git add custom_components/dsvdc4ha/sensor.py custom_components/dsvdc4ha/binary_sensor.py
git commit -m "refactor: extract _add_entities_for_subentry helpers and store async_add_entities callback"
```

---

### Task 2: Implement live delta listener in `__init__.py`

**Files:**
- Modify: `custom_components/dsvdc4ha/__init__.py`
- Modify: `tests/test_init.py`

- [ ] **Step 1: Write failing tests**

Add at the bottom of `tests/test_init.py`. The tests need one additional import at the top: add `from unittest.mock import patch` to the existing import line (it is already there).

```python
# tests/test_init.py — add after existing tests

@pytest.mark.asyncio
async def test_subentry_listener_removes_device_on_deletion():
    """Delta listener vanishes a removed subentry's device and clears HA registry entries."""
    from custom_components.dsvdc4ha import _async_subentry_update_listener

    api = MagicMock()
    api.vanish_device = AsyncMock()
    coordinator = MagicMock()
    coordinator.api = api

    hass = MagicMock()
    hass.data = {
        "dsvdc4ha": {
            "hub": coordinator,
            "_known_subentry_ids": {"sub_a", "sub_b"},
            "sub_b": {"unsubs": []},
        }
    }
    entry = _make_entry([{"subentry_id": "sub_a", "data": {}}])
    entry.entry_id = "entry1"

    with (
        patch("custom_components.dsvdc4ha.er.async_get") as mock_er,
        patch("custom_components.dsvdc4ha.dr.async_get") as mock_dr,
    ):
        await _async_subentry_update_listener(hass, entry)

    api.vanish_device.assert_awaited_once_with("sub_b")
    mock_er.return_value.async_clear_config_subentry.assert_called_once_with("entry1", "sub_b")
    mock_dr.return_value.async_clear_config_subentry.assert_called_once_with("entry1", "sub_b")
    assert hass.data["dsvdc4ha"]["_known_subentry_ids"] == {"sub_a"}


@pytest.mark.asyncio
async def test_subentry_listener_adds_new_device():
    """Delta listener adds + announces a newly added subentry's device."""
    from custom_components.dsvdc4ha import _async_subentry_update_listener

    api = MagicMock()
    api.add_device = MagicMock()
    api.announce_device = AsyncMock()
    coordinator = MagicMock()
    coordinator.api = api

    add_sensor = MagicMock()
    add_binary = MagicMock()
    hass = MagicMock()
    hass.data = {
        "dsvdc4ha": {
            "hub": coordinator,
            "_known_subentry_ids": {"sub_a"},
            "_add_sensor_entities": add_sensor,
            "_add_binary_entities": add_binary,
        }
    }
    entry = _make_entry([
        {"subentry_id": "sub_a", "data": {}},
        {"subentry_id": "sub_b", "data": {"vdsds": []}},
    ])
    entry.entry_id = "entry1"

    with (
        patch("custom_components.dsvdc4ha.er.async_get"),
        patch("custom_components.dsvdc4ha.dr.async_get"),
        patch("custom_components.dsvdc4ha.listeners.setup_input_listeners", return_value=[]),
        patch("custom_components.dsvdc4ha.listeners.setup_output_listeners", return_value=[]),
        patch(
            "custom_components.dsvdc4ha.listeners.seed_initial_values",
            new_callable=AsyncMock,
        ),
        patch("custom_components.dsvdc4ha.sensor._add_entities_for_subentry"),
        patch("custom_components.dsvdc4ha.binary_sensor._add_entities_for_subentry"),
    ):
        await _async_subentry_update_listener(hass, entry)

    api.add_device.assert_called_once_with("sub_b", [])
    api.announce_device.assert_awaited_once_with("sub_b")
    assert hass.data["dsvdc4ha"]["_known_subentry_ids"] == {"sub_a", "sub_b"}


@pytest.mark.asyncio
async def test_subentry_listener_noop_when_no_changes():
    """Delta listener does nothing when subentries match the known ID set."""
    from custom_components.dsvdc4ha import _async_subentry_update_listener

    api = MagicMock()
    api.vanish_device = AsyncMock()
    api.announce_device = AsyncMock()
    coordinator = MagicMock()
    coordinator.api = api

    hass = MagicMock()
    hass.data = {
        "dsvdc4ha": {
            "hub": coordinator,
            "_known_subentry_ids": {"sub_a"},
        }
    }
    entry = _make_entry([{"subentry_id": "sub_a", "data": {}}])
    entry.entry_id = "entry1"

    with (
        patch("custom_components.dsvdc4ha.er.async_get"),
        patch("custom_components.dsvdc4ha.dr.async_get"),
    ):
        await _async_subentry_update_listener(hass, entry)

    api.vanish_device.assert_not_awaited()
    api.announce_device.assert_not_awaited()


@pytest.mark.asyncio
async def test_subentry_listener_noop_when_coordinator_is_none():
    """Delta listener does nothing if coordinator has not been started yet."""
    from custom_components.dsvdc4ha import _async_subentry_update_listener

    hass = MagicMock()
    hass.data = {"dsvdc4ha": {}}
    entry = _make_entry([])
    entry.entry_id = "entry1"

    # Must not raise — no patches needed, coordinator is absent
    await _async_subentry_update_listener(hass, entry)
```

- [ ] **Step 2: Run — confirm fail**

```bash
.venv/bin/python -m pytest \
  tests/test_init.py::test_subentry_listener_removes_device_on_deletion \
  tests/test_init.py::test_subentry_listener_adds_new_device \
  tests/test_init.py::test_subentry_listener_noop_when_no_changes \
  tests/test_init.py::test_subentry_listener_noop_when_coordinator_is_none \
  -v
```
Expected: FAIL — `ImportError: cannot import name '_async_subentry_update_listener'`

- [ ] **Step 3: Implement in `__init__.py`**

**3a. Add `dr` import** (alongside the existing `er` import):
```python
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
```

**3b. Store `entity_index` and `_known_subentry_ids` in `async_setup_entry`.**

After the subentry loop (the one that calls `add_device` / `announce_device`), replace:
```python
    # React to entity enable/disable and deletion in the HA entity registry.
    entity_index = _build_entity_index(entry)
```
with:
```python
    # React to entity enable/disable and deletion in the HA entity registry.
    # Store in domain_data so the subentry delta listener can update it in-place.
    entity_index = _build_entity_index(entry)
    hass.data[DOMAIN]["_entity_index"] = entity_index
    hass.data[DOMAIN]["_known_subentry_ids"] = set(entry.subentries.keys())
```
(The closure `_on_entity_registry_updated` already captures `entity_index` by reference; storing it in `domain_data` gives the listener access to the same dict object so in-place updates are reflected in both.)

**3c. Change the listener registration** — replace the old listener with the new one:
```python
    # Replace:
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    # With:
    entry.async_on_unload(entry.add_update_listener(_async_subentry_update_listener))
```

**3d. Delete `_async_update_listener`** — remove this function entirely:
```python
async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
```

**3e. Add `_async_subentry_update_listener`** — place it where `_async_update_listener` was:
```python
async def _async_subentry_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle subentry add/remove without restarting VdcHost.

    Computes the diff between the previous known subentry IDs and the
    current entry.subentries, then:
    - Removed subentries: vanishes the dS device + clears HA entity/device
      registry entries + unsubscribes state listeners.
    - Added subentries: registers + announces the dS device + adds HA
      platform entities via the stored async_add_entities callbacks.
    """
    domain_data = hass.data.get(DOMAIN, {})
    coordinator: HubCoordinator | None = domain_data.get("hub")
    if coordinator is None or coordinator.api is None:
        return

    known_ids: set[str] = domain_data.get("_known_subentry_ids", set())
    current_ids = set(entry.subentries.keys())
    removed = known_ids - current_ids
    added = current_ids - known_ids

    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    for subentry_id in removed:
        await coordinator.api.vanish_device(subentry_id)
        ent_reg.async_clear_config_subentry(entry.entry_id, subentry_id)
        dev_reg.async_clear_config_subentry(entry.entry_id, subentry_id)
        subentry_data = domain_data.pop(subentry_id, {})
        for unsub in subentry_data.get("unsubs", []):
            unsub()

    if added:
        from .listeners import setup_input_listeners, setup_output_listeners, seed_initial_values
        from . import sensor as _sensor_mod
        from . import binary_sensor as _binary_sensor_mod

        add_sensor = domain_data.get("_add_sensor_entities")
        add_binary = domain_data.get("_add_binary_entities")

        for subentry_id in added:
            subentry = entry.subentries[subentry_id]
            vdsds = subentry.data.get("vdsds", [])
            coordinator.api.add_device(subentry_id, vdsds)
            unsubs = setup_input_listeners(hass, coordinator.api, subentry_id, vdsds)
            unsubs += setup_output_listeners(hass, coordinator.api, subentry_id, vdsds)
            domain_data[subentry_id] = {"unsubs": unsubs}
            await seed_initial_values(hass, coordinator.api, subentry_id, vdsds)
            await coordinator.api.announce_device(subentry_id)
            if add_sensor:
                _sensor_mod._add_entities_for_subentry(subentry, add_sensor)
            if add_binary:
                _binary_sensor_mod._add_entities_for_subentry(subentry, add_binary)

    if removed or added:
        entity_index: dict = domain_data.get("_entity_index", {})
        entity_index.clear()
        entity_index.update(_build_entity_index(entry))
        domain_data["_known_subentry_ids"] = current_ids
```

- [ ] **Step 4: Run — confirm tests pass**

```bash
.venv/bin/python -m pytest \
  tests/test_init.py::test_subentry_listener_removes_device_on_deletion \
  tests/test_init.py::test_subentry_listener_adds_new_device \
  tests/test_init.py::test_subentry_listener_noop_when_no_changes \
  tests/test_init.py::test_subentry_listener_noop_when_coordinator_is_none \
  -v
```
Expected: 4 PASS

- [ ] **Step 5: Run all tests**

```bash
.venv/bin/python -m pytest tests/ -q
```
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/__init__.py tests/test_init.py
git commit -m "feat: replace full reload on subentry change with live delta device management"
```

---

## Notes

- **`_add_entities_for_subentry` patch paths**: The listener uses `from . import sensor as _sensor_mod` so that `_sensor_mod._add_entities_for_subentry` is a live attribute lookup on the module object. This makes `patch("custom_components.dsvdc4ha.sensor._add_entities_for_subentry")` work correctly in tests.

- **`setup_input_listeners` / `seed_initial_values` patch paths**: The lazy `from .listeners import …` inside the function picks up whatever `sys.modules["custom_components.dsvdc4ha.listeners"]` holds at call time, so `patch("custom_components.dsvdc4ha.listeners.setup_input_listeners", …)` works.

- **`entity_index` shared reference**: `async_setup_entry` stores the dict in `hass.data[DOMAIN]["_entity_index"]` AND the `_on_entity_registry_updated` closure captures it by reference. Both reference the same dict object. Calling `entity_index.clear(); entity_index.update(…)` in the listener updates both simultaneously.

- **Offline deletion edge case**: If a subentry is deleted while the dSS is offline, `vanish_device` stores the device in `_pending_vanish` (if that mechanism exists) or simply can't send the vanish message. This plan does not add the pending-vanish mechanism — that is a separate improvement.

- **pydsvdcapi team**: No changes required. pydsvdcapi's `_on_session_ready` announcement behaviour is correct. The problem was entirely in how often we created new sessions.
