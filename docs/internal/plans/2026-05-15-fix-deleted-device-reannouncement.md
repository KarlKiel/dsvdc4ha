# Fix Deleted Device Re-Announcement After Connection Loss

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Devices deleted in HA are immediately vanished from the dSS and never re-announced after a connection loss.

**Architecture:** Two gaps are closed. First, `async_unload_entry` (called on every subentry deletion via reload) never calls `vanish_device` for deleted subentries — we fix it to compare the API's known devices against the now-current config entry and vanish the diff before stopping. Second, if the dSS is offline at deletion time the vanish message can't be sent; we add an in-memory `_pending_vanish` dict in `DsvdcApi` and flush it on the next `_on_session_ready`. A pydsvdcapi change (noted below) is required to cover the edge case where HA also restarts before the dSS comes back.

**Tech Stack:** Python, HA config entries API, pydsvdcapi `VdcHost._on_session_ready`, `Device.vanish()`.

---

## pydsvdcapi gap (call-out — implement separately)

`DsvdcApi._pending_vanish` is **in-memory only**. If HA restarts after a device is deleted while the dSS is offline, the pending set is lost and the dSS never receives the vanish message. The correct long-term fix is a pydsvdcapi change:

- When `vdc.remove_device(dsuid)` is called and no active session exists, append the dSUID to a `pendingVanish` list in the YAML state.
- On `_on_session_ready`, send `VDC_SEND_VANISH` for each dSUID in `pendingVanish`, then clear and save.

This plan covers the integration-side fix (handles all cases except "offline deletion + HA restart + later reconnect"). That edge case needs the pydsvdcapi change above.

---

## File Structure

| File | Change |
|------|--------|
| `custom_components/dsvdc4ha/api.py` | Add `registered_entry_ids` property; add `_pending_vanish`; modify `vanish_device`; add `_flush_pending_vanish`; always hook `_on_session_ready` |
| `custom_components/dsvdc4ha/__init__.py` | Add `_vanish_deleted_devices` helper; call it in `async_unload_entry` before stopping |
| `tests/test_api.py` | Tests for pending vanish behaviour |
| `tests/test_init.py` | Tests for `_vanish_deleted_devices` |

---

### Task 1: Add pending-vanish mechanism to `DsvdcApi`

When `vanish_device` is called while the dSS session is down, keep the `Device` object in `_pending_vanish` and flush it on the next session-ready.

**Files:**
- Modify: `custom_components/dsvdc4ha/api.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_api.py  — add after existing tests

def test_vanish_without_session_queues_pending():
    """vanish_device with no session stores the device in _pending_vanish."""
    from custom_components.dsvdc4ha.api import DsvdcApi
    api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")

    mock_device = MagicMock()
    api._devices["sub1"] = mock_device
    api._vdc = MagicMock()
    # _host is None → no session

    import asyncio
    asyncio.get_event_loop().run_until_complete(api.vanish_device("sub1"))

    assert "sub1" not in api._devices
    assert api._pending_vanish.get("sub1") is mock_device
    api._vdc.remove_device.assert_called_once()


@pytest.mark.asyncio
async def test_flush_pending_vanish_sends_and_clears():
    """_flush_pending_vanish calls device.vanish for each pending entry then clears."""
    from custom_components.dsvdc4ha.api import DsvdcApi
    api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")

    mock_device = MagicMock()
    mock_device.vanish = AsyncMock()
    api._pending_vanish["sub1"] = mock_device

    mock_session = MagicMock()
    await api._flush_pending_vanish(mock_session)

    mock_device.vanish.assert_awaited_once_with(mock_session)
    assert "sub1" not in api._pending_vanish


@pytest.mark.asyncio
async def test_flush_pending_vanish_skips_failed_and_continues():
    """_flush_pending_vanish continues if one device.vanish raises."""
    from custom_components.dsvdc4ha.api import DsvdcApi
    api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")

    bad_device = MagicMock()
    bad_device.vanish = AsyncMock(side_effect=Exception("boom"))
    good_device = MagicMock()
    good_device.vanish = AsyncMock()
    api._pending_vanish["bad"] = bad_device
    api._pending_vanish["good"] = good_device

    mock_session = MagicMock()
    await api._flush_pending_vanish(mock_session)  # must not raise

    good_device.vanish.assert_awaited_once_with(mock_session)
    assert not api._pending_vanish  # both cleared
```

- [ ] **Step 2: Run — confirm fail**

```bash
.venv/bin/python -m pytest tests/test_api.py::test_vanish_without_session_queues_pending tests/test_api.py::test_flush_pending_vanish_sends_and_clears tests/test_api.py::test_flush_pending_vanish_skips_failed_and_continues -v
```
Expected: FAIL (AttributeError `_pending_vanish` or `_flush_pending_vanish`)

- [ ] **Step 3: Implement in `api.py`**

In `DsvdcApi.__init__`, add after `self._devices`:
```python
self._pending_vanish: dict[str, Any] = {}  # entry_id → Device awaiting session to vanish
```

Replace `vanish_device` (lines ~463–470):
```python
async def vanish_device(self, entry_id: str) -> None:
    """Vanish and remove a device from dS.

    If no session is active the vanish message cannot be sent now;
    the Device is kept in _pending_vanish and flushed on the next
    session-ready event.
    """
    if device := self._devices.pop(entry_id, None):
        if self._host and self._host.session:
            await device.vanish(self._host.session)
        else:
            self._pending_vanish[entry_id] = device
        if self._vdc:
            dsuid = self._build_device_dsuid(entry_id)
            self._vdc.remove_device(dsuid)
```

Add new method after `vanish_device`:
```python
async def _flush_pending_vanish(self, session: Any) -> None:
    """Send VDC_SEND_VANISH for all devices deleted while session was down."""
    for entry_id in list(self._pending_vanish):
        device = self._pending_vanish.pop(entry_id)
        try:
            await device.vanish(session)
        except Exception:
            _LOGGER.warning("Failed to vanish pending device %s", entry_id, exc_info=True)
```

Also add `registered_entry_ids` property (needed by Task 2):
```python
@property
def registered_entry_ids(self) -> set[str]:
    """Set of entry_ids currently tracked by this API."""
    return set(self._devices.keys())
```

Finally, in `start()`, replace the conditional `_on_session_ready` hook with one that **always** runs and flushes pending vanish first:

Replace the existing block:
```python
if on_session_ready is not None:
    _orig = host._on_session_ready
    _cb = on_session_ready
    async def _hooked(session) -> None:
        await _orig(session)
        _cb()
    host._on_session_ready = _hooked
```

With:
```python
_orig_session_ready = host._on_session_ready
_cb = on_session_ready

async def _hooked(session) -> None:
    await self._flush_pending_vanish(session)
    await _orig_session_ready(session)
    if _cb is not None:
        _cb()

host._on_session_ready = _hooked
```

- [ ] **Step 4: Run — confirm pass**

```bash
.venv/bin/python -m pytest tests/test_api.py::test_vanish_without_session_queues_pending tests/test_api.py::test_flush_pending_vanish_sends_and_clears tests/test_api.py::test_flush_pending_vanish_skips_failed_and_continues -v
```
Expected: PASS

- [ ] **Step 5: Run all tests**

```bash
.venv/bin/python -m pytest tests/ -q
```
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/api.py tests/test_api.py
git commit -m "feat: queue pending vanish for devices deleted while dSS session is down"
```

---

### Task 2: Vanish deleted subentries during `async_unload_entry`

When a subentry is deleted HA triggers a config-entry reload (`_async_update_listener` → `async_reload`). `async_unload_entry` runs with `entry.subentries` already reflecting the post-deletion state while `coordinator.api._devices` still holds all pre-deletion devices. We compute the diff and vanish before stopping.

**Files:**
- Modify: `custom_components/dsvdc4ha/__init__.py`
- Test: `tests/test_init.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_init.py — add after existing tests

@pytest.mark.asyncio
async def test_vanish_deleted_devices_vanishes_diff():
    """_vanish_deleted_devices vanishes entry_ids in api but not in entry.subentries."""
    from custom_components.dsvdc4ha import _vanish_deleted_devices

    api = MagicMock()
    api.registered_entry_ids = {"sub_kept", "sub_deleted"}
    api.vanish_device = AsyncMock()

    coordinator = MagicMock()
    coordinator.api = api

    entry = _make_entry([{"subentry_id": "sub_kept", "data": {}}])

    await _vanish_deleted_devices(coordinator, entry)

    api.vanish_device.assert_awaited_once_with("sub_deleted")


@pytest.mark.asyncio
async def test_vanish_deleted_devices_noop_when_no_deletions():
    """_vanish_deleted_devices does nothing when entry matches api devices."""
    from custom_components.dsvdc4ha import _vanish_deleted_devices

    api = MagicMock()
    api.registered_entry_ids = {"sub1"}
    api.vanish_device = AsyncMock()

    coordinator = MagicMock()
    coordinator.api = api

    entry = _make_entry([{"subentry_id": "sub1", "data": {}}])

    await _vanish_deleted_devices(coordinator, entry)

    api.vanish_device.assert_not_awaited()
```

- [ ] **Step 2: Run — confirm fail**

```bash
.venv/bin/python -m pytest tests/test_init.py::test_vanish_deleted_devices_vanishes_diff tests/test_init.py::test_vanish_deleted_devices_noop_when_no_deletions -v
```
Expected: FAIL (ImportError `_vanish_deleted_devices`)

- [ ] **Step 3: Implement in `__init__.py`**

Add `_vanish_deleted_devices` helper before `async_setup_entry`:
```python
async def _vanish_deleted_devices(coordinator: Any, entry: ConfigEntry) -> None:
    """Vanish devices that were removed from entry.subentries since last setup."""
    current_ids = set(entry.subentries.keys())
    for entry_id in coordinator.api.registered_entry_ids - current_ids:
        await coordinator.api.vanish_device(entry_id)
```

Update `async_unload_entry` to call it before stopping:
```python
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data.get(DOMAIN, {})

    for subentry in entry.subentries.values():
        subentry_data = domain_data.pop(subentry.subentry_id, {})
        for unsub in subentry_data.get("unsubs", []):
            unsub()

    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    coordinator: HubCoordinator | None = domain_data.pop("hub", None)
    if coordinator:
        await _vanish_deleted_devices(coordinator, entry)
        await coordinator.async_stop()

    return True
```

Also update the import line at the top of `__init__.py` — `_vanish_deleted_devices` takes `Any` for coordinator; add `Any` to the `typing` import if not already present:
```python
from typing import Any
```

- [ ] **Step 4: Run — confirm pass**

```bash
.venv/bin/python -m pytest tests/test_init.py::test_vanish_deleted_devices_vanishes_diff tests/test_init.py::test_vanish_deleted_devices_noop_when_no_deletions -v
```
Expected: PASS

- [ ] **Step 5: Run all tests**

```bash
.venv/bin/python -m pytest tests/ -q
```
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/__init__.py tests/test_init.py
git commit -m "feat: vanish deleted subentry devices during config-entry unload"
```

---

## Notes

- The `Any` type annotation for `coordinator` in `_vanish_deleted_devices` avoids a circular import between `__init__.py` and `coordinator.py`. If a `HubCoordinator` import is already present in `__init__.py`, use that instead.
- `_flush_pending_vanish` is called **before** pydsvdcapi's own `_on_session_ready` auto-announce so the dSS processes the vanish before any new announcements arrive on the same connection.
- VDC_SEND_VANISH is fire-and-forget (no response expected). Sending it for a device the dSS no longer knows about is harmless.
- Persistence across HA restarts requires the pydsvdcapi change described at the top of this document. Without it, the edge case "deleted while offline + HA restarted before dSS came back" is not covered.
