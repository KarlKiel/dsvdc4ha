# Soft Shutdown / No Re-announce on Reconnect — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop DSS from removing all devices from its lookup on HA shutdown, and stop unnecessarily re-announcing all devices every time the DSS reconnects.

**Architecture:** Two coordinated changes. (1) `api.stop()` gets a `deregister_mdns` flag (default `False`) — on normal restarts we only null the zeroconf reference (prevents pydsvdcapi from closing HA's shared Zeroconf) without sending the mDNS goodbye packet, so DSS keeps devices in its lookup table. (2) `DsvdcApi` tracks which entry_ids have been successfully announced (`_ever_announced`); the `_on_session_ready` hook only announces devices NOT in that set, skipping re-announcement for devices DSS already knows. `async_remove_entry` (true deletion) passes `deregister_mdns=True` for full cleanup.

**Tech Stack:** pydsvdcapi (`VdcHost`, `Vdc`, `Device`), Python asyncio, zeroconf, pytest + unittest.mock.

**Root Cause (for context):** `_deregister_zeroconf()` in `api.stop()` sends a TTL=0 mDNS goodbye packet before closing TCP. DSS interprets this as "VDC gone permanently" and removes all 20 devices from its lookup. 40 seconds later (HA restart time), VDC reconnects and re-announces everything from scratch. DSS has to re-process all devices, causing delay and brief sensor errors. If we skip the mDNS goodbye, DSS sees only the TCP drop, treats VDC as temporarily offline, keeps its lookup, and devices are immediately operational when TCP reconnects.

---

## File Map

| File | Change |
|------|--------|
| `custom_components/dsvdc4ha/api.py` | Tasks 1 + 2: split `_deregister_zeroconf`, add `deregister_mdns` param to `stop()`, add `_ever_announced`, rewrite `_on_session_ready` hook, update `announce_device()` and `vanish_device()` |
| `custom_components/dsvdc4ha/__init__.py` | Task 3: `async_remove_entry()` passes `deregister_mdns=True` |
| `tests/test_api.py` | All tasks: update existing stop test, add 6 new tests |

---

## Task 1: Soft stop — don't send mDNS goodbye on normal shutdown

`_deregister_zeroconf()` currently does two things: (a) unregisters the mDNS service (sends goodbye), and (b) nulls `host._zeroconf` so pydsvdcapi's `unannounce()` inside `host.stop()` becomes a no-op instead of closing HA's shared Zeroconf. For a soft stop we only need (b). A new `_detach_zeroconf()` does only (b); `_deregister_zeroconf()` keeps doing both. `api.stop()` uses the new `deregister_mdns: bool = False` parameter to pick which one to call.

**Files:**
- Modify: `custom_components/dsvdc4ha/api.py:285-312` (the `stop()` and `_deregister_zeroconf()` methods)
- Modify: `tests/test_api.py` (update one existing test, add one new test)

- [ ] **Step 1: Write two failing tests — soft stop does NOT unregister, hard stop DOES**

Add these tests to `tests/test_api.py`. Put them right after the existing `test_api_stop_deregisters_shared_zeroconf` test (which will be updated in Step 3).

```python
@pytest.mark.asyncio
async def test_api_soft_stop_does_not_unregister_zeroconf():
    """api.stop() (default) nulls zeroconf reference but does NOT unregister the service."""
    mock_sock = MagicMock()
    mock_sock.__enter__ = MagicMock(return_value=mock_sock)
    mock_sock.__exit__ = MagicMock(return_value=False)
    mock_sock.getsockname.return_value = ("192.168.1.100", 0)

    with patch("custom_components.dsvdc4ha.api.VdcHost") as MockHost, \
         patch("custom_components.dsvdc4ha.api.Vdc"), \
         patch("custom_components.dsvdc4ha.api.VdcCapabilities"), \
         patch("custom_components.dsvdc4ha.api.socket.gethostname", return_value="testhostname"), \
         patch("custom_components.dsvdc4ha.api.socket.socket", return_value=mock_sock), \
         patch("custom_components.dsvdc4ha.api.socket.inet_aton", return_value=b"\xc0\xa8\x01\x64"):
        mock_zeroconf = MagicMock()
        mock_zeroconf.async_register_service = AsyncMock()
        mock_zeroconf.async_unregister_service = AsyncMock()

        mock_host_instance = MagicMock()
        mock_host_instance.name = "TestVdcHost"
        mock_host_instance.start = AsyncMock()
        mock_host_instance.stop = AsyncMock()
        mock_host_instance.flush = MagicMock()
        mock_host_instance._port = 9090
        mock_host_instance._dsuid = "AABBCCDDEEFF0011223344556677889900"
        mock_host_instance._zeroconf = None
        mock_host_instance._service_info = None
        mock_host_instance._on_session_ready = AsyncMock()
        MockHost.return_value = mock_host_instance

        api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp/test_state")
        await api.start(zeroconf=mock_zeroconf)

        # After _register_zeroconf the pre-unregister call is already done; reset the counter.
        mock_zeroconf.async_unregister_service.reset_mock()

        await api.stop()  # soft stop — default deregister_mdns=False

        mock_zeroconf.async_unregister_service.assert_not_awaited()
        # host._zeroconf must be None so pydsvdcapi's unannounce() is a no-op
        assert mock_host_instance._zeroconf is None
        mock_host_instance.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_api_hard_stop_unregisters_zeroconf():
    """api.stop(deregister_mdns=True) unregisters the mDNS service before closing TCP."""
    mock_sock = MagicMock()
    mock_sock.__enter__ = MagicMock(return_value=mock_sock)
    mock_sock.__exit__ = MagicMock(return_value=False)
    mock_sock.getsockname.return_value = ("192.168.1.100", 0)

    with patch("custom_components.dsvdc4ha.api.VdcHost") as MockHost, \
         patch("custom_components.dsvdc4ha.api.Vdc"), \
         patch("custom_components.dsvdc4ha.api.VdcCapabilities"), \
         patch("custom_components.dsvdc4ha.api.socket.gethostname", return_value="testhostname"), \
         patch("custom_components.dsvdc4ha.api.socket.socket", return_value=mock_sock), \
         patch("custom_components.dsvdc4ha.api.socket.inet_aton", return_value=b"\xc0\xa8\x01\x64"):
        mock_zeroconf = MagicMock()
        mock_zeroconf.async_register_service = AsyncMock()
        mock_zeroconf.async_unregister_service = AsyncMock()

        mock_host_instance = MagicMock()
        mock_host_instance.name = "TestVdcHost"
        mock_host_instance.start = AsyncMock()
        mock_host_instance.stop = AsyncMock()
        mock_host_instance.flush = MagicMock()
        mock_host_instance._port = 9090
        mock_host_instance._dsuid = "AABBCCDDEEFF0011223344556677889900"
        mock_host_instance._zeroconf = None
        mock_host_instance._service_info = None
        mock_host_instance._on_session_ready = AsyncMock()
        MockHost.return_value = mock_host_instance

        api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp/test_state")
        await api.start(zeroconf=mock_zeroconf)

        mock_zeroconf.async_unregister_service.reset_mock()

        await api.stop(deregister_mdns=True)  # hard stop

        mock_zeroconf.async_unregister_service.assert_awaited_once()
        mock_host_instance.stop.assert_awaited_once()
```

- [ ] **Step 2: Run the two new tests to confirm they fail**

```bash
cd /home/arne/Development/dsvdc4ha && source .venv/bin/activate
pytest tests/test_api.py::test_api_soft_stop_does_not_unregister_zeroconf tests/test_api.py::test_api_hard_stop_unregisters_zeroconf -v
```

Expected: both FAIL (TypeError: `stop()` takes no `deregister_mdns` param, or wrong assertion).

- [ ] **Step 3: Implement `_detach_zeroconf()` and add `deregister_mdns` to `stop()`**

In `custom_components/dsvdc4ha/api.py`, replace the `stop()` and `_deregister_zeroconf()` methods (currently lines 285–312) with:

```python
async def stop(self, *, deregister_mdns: bool = False) -> None:
    """Stop serving.

    When *deregister_mdns* is False (default, for restarts) the mDNS
    service is left registered so DSS keeps devices in its lookup table.
    Pass True only when devices are being permanently deleted.
    """
    if self._host:
        if deregister_mdns:
            await self._deregister_zeroconf(self._host)
        else:
            await self._detach_zeroconf(self._host)
        await asyncio.to_thread(self._host.flush)
        await self._host.stop()
        self._host = None
        self._vdc = None
        _LOGGER.debug("VdcHost stopped")

async def _detach_zeroconf(self, host: VdcHost) -> None:
    """Null out the zeroconf reference without unregistering the mDNS service.

    This prevents pydsvdcapi's unannounce() (called inside host.stop()) from
    calling async_close() on HA's shared Zeroconf, while keeping the mDNS
    advertisement alive so DSS does not remove devices from its lookup.
    """
    host._zeroconf = None
    host._service_info = None

async def _deregister_zeroconf(self, host: VdcHost) -> None:
    """Unregister DNS-SD from the shared Zeroconf instance and detach.

    Clears host._zeroconf so that pydsvdcapi's unannounce() (called inside
    host.stop()) sees no zeroconf and becomes a no-op — preventing it from
    calling async_close() on HA's shared instance.
    """
    if host._zeroconf is None:
        return
    if host._service_info is not None:
        try:
            await host._zeroconf.async_unregister_service(host._service_info)
        except Exception:
            _LOGGER.debug("Zeroconf unregister raised (ignored)", exc_info=True)
    host._zeroconf = None
    host._service_info = None
```

- [ ] **Step 4: Update the existing `test_api_stop_deregisters_shared_zeroconf` test**

This test asserts that `api.stop()` calls `async_unregister_service`. With the new default (soft stop), that is no longer true. Update it to use `deregister_mdns=True`:

Find the line `await api.stop()` in `test_api_stop_deregisters_shared_zeroconf` and change it to:
```python
await api.stop(deregister_mdns=True)
```

Also add `mock_host_instance._on_session_ready = AsyncMock()` to the mock setup in that test (pydsvdcapi needs this attribute to be hookable in `api.start()`).

- [ ] **Step 5: Run all api tests to verify they pass**

```bash
source .venv/bin/activate && pytest tests/test_api.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/api.py tests/test_api.py
git commit -m "feat: soft stop — skip mDNS goodbye on normal shutdown so DSS keeps device lookup"
```

---

## Task 2: Skip re-announcing devices DSS already knows

Track which entry_ids have been successfully announced in `_ever_announced: set[str]`. Replace the session-ready hook's call to pydsvdcapi's `_orig_session_ready` (which announces everything) with a selective version that: always announces the VDC container, and only announces devices not already in `_ever_announced`. `vanish_device()` removes from `_ever_announced` (device truly gone). `announce_device()` skips devices already in `_ever_announced` (DSS already knows them).

**Files:**
- Modify: `custom_components/dsvdc4ha/api.py` — `__init__`, `start()` hook, `announce_device()`, `vanish_device()`
- Modify: `tests/test_api.py` — 4 new tests

- [ ] **Step 1: Write four failing tests**

Add these tests to `tests/test_api.py`:

```python
@pytest.mark.asyncio
async def test_session_ready_hook_skips_known_devices():
    """_on_session_ready only announces devices NOT in _ever_announced."""
    with patch("custom_components.dsvdc4ha.api.VdcHost") as MockHost, \
         patch("custom_components.dsvdc4ha.api.Vdc"), \
         patch("custom_components.dsvdc4ha.api.VdcCapabilities"):
        mock_host_instance = MagicMock()
        mock_host_instance.start = AsyncMock()
        mock_host_instance._on_session_ready = AsyncMock()
        mock_host_instance.session = None
        MockHost.return_value = mock_host_instance

        api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")
        await api.start()

        # Simulate two registered devices; "known" was announced before
        mock_device_known = MagicMock()
        mock_device_known.announce = AsyncMock(return_value=1)
        mock_device_new = MagicMock()
        mock_device_new.announce = AsyncMock(return_value=1)
        api._devices["known"] = mock_device_known
        api._devices["new"] = mock_device_new
        api._ever_announced.add("known")

        mock_vdc = MagicMock()
        mock_vdc.announce = AsyncMock(return_value=True)
        api._vdc = mock_vdc

        mock_session = MagicMock()
        # Trigger the installed hook
        await mock_host_instance._on_session_ready(mock_session)

        mock_vdc.announce.assert_awaited_once_with(mock_session)
        mock_device_known.announce.assert_not_awaited()
        mock_device_new.announce.assert_awaited_once_with(mock_session)
        assert "new" in api._ever_announced


@pytest.mark.asyncio
async def test_session_ready_hook_adds_to_ever_announced():
    """Newly announced devices are added to _ever_announced."""
    with patch("custom_components.dsvdc4ha.api.VdcHost") as MockHost, \
         patch("custom_components.dsvdc4ha.api.Vdc"), \
         patch("custom_components.dsvdc4ha.api.VdcCapabilities"):
        mock_host_instance = MagicMock()
        mock_host_instance.start = AsyncMock()
        mock_host_instance._on_session_ready = AsyncMock()
        mock_host_instance.session = None
        MockHost.return_value = mock_host_instance

        api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")
        await api.start()

        mock_device = MagicMock()
        mock_device.announce = AsyncMock(return_value=2)  # 2 vdSDs announced
        api._devices["sub1"] = mock_device

        mock_vdc = MagicMock()
        mock_vdc.announce = AsyncMock(return_value=True)
        api._vdc = mock_vdc

        await mock_host_instance._on_session_ready(MagicMock())

        assert "sub1" in api._ever_announced


@pytest.mark.asyncio
async def test_announce_device_skips_if_already_known():
    """announce_device() is a no-op for entry_ids in _ever_announced."""
    api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")

    mock_host = MagicMock()
    mock_host.session = MagicMock()  # session active
    api._host = mock_host

    mock_device = MagicMock()
    mock_device.announce = AsyncMock(return_value=1)
    api._devices["sub1"] = mock_device
    api._ever_announced.add("sub1")  # already known

    await api.announce_device("sub1")

    mock_device.announce.assert_not_awaited()


@pytest.mark.asyncio
async def test_vanish_device_removes_from_ever_announced():
    """vanish_device() removes the entry_id from _ever_announced."""
    api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")
    api._vdc = MagicMock()
    # No session — device queued for pending vanish, but _ever_announced cleared immediately
    mock_device = MagicMock()
    api._devices["sub1"] = mock_device
    api._ever_announced.add("sub1")

    await api.vanish_device("sub1")

    assert "sub1" not in api._ever_announced
```

- [ ] **Step 2: Run the four new tests to confirm they fail**

```bash
source .venv/bin/activate && pytest \
  tests/test_api.py::test_session_ready_hook_skips_known_devices \
  tests/test_api.py::test_session_ready_hook_adds_to_ever_announced \
  tests/test_api.py::test_announce_device_skips_if_already_known \
  tests/test_api.py::test_vanish_device_removes_from_ever_announced \
  -v
```

Expected: all FAIL (`AttributeError: 'DsvdcApi' object has no attribute '_ever_announced'` or assertion errors).

- [ ] **Step 3: Add `_ever_announced` to `DsvdcApi.__init__()`**

In `custom_components/dsvdc4ha/api.py`, inside `DsvdcApi.__init__()`, add one line after `self._pending_vanish`:

```python
self._ever_announced: set[str] = set()  # entry_ids DSS knows about; skip re-announce on reconnect
```

- [ ] **Step 4: Rewrite the `_on_session_ready` hook in `start()`**

In `api.start()`, the hook currently looks like this:

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

Replace it with:

```python
_cb = on_session_ready

async def _hooked(session) -> None:
    await self._flush_pending_vanish(session)
    # Always announce the VDC container so DSS knows it is connected.
    await self._vdc.announce(session)
    # Only announce devices DSS does not already have in its lookup.
    for entry_id, device in list(self._devices.items()):
        if entry_id not in self._ever_announced:
            try:
                count = await device.announce(session)
                if count > 0:
                    self._ever_announced.add(entry_id)
            except Exception:
                _LOGGER.warning("Failed to announce device %s on session ready", entry_id, exc_info=True)
    if _cb is not None:
        _cb()

host._on_session_ready = _hooked
```

Note: we no longer need `_orig_session_ready` — pydsvdcapi's original handler announced everything; we replace it with selective logic.

- [ ] **Step 5: Update `announce_device()` to skip known devices**

Replace the existing `announce_device()` method (currently around line 342):

```python
async def announce_device(self, entry_id: str) -> None:
    """Announce a device to DSS if not already known and a session is active."""
    if entry_id in self._ever_announced:
        return  # DSS already has this device; skip to avoid unnecessary disruption
    assert self._host is not None
    if device := self._devices.get(entry_id):
        if self._host.session is not None:
            count = await device.announce(self._host.session)
            if count > 0:
                self._ever_announced.add(entry_id)
```

- [ ] **Step 6: Update `vanish_device()` to clear from `_ever_announced`**

In the existing `vanish_device()` method, add `self._ever_announced.discard(entry_id)` as the first line inside the method body:

```python
async def vanish_device(self, entry_id: str) -> None:
    """Vanish and remove a device from dS."""
    self._ever_announced.discard(entry_id)
    if device := self._devices.pop(entry_id, None):
        if self._host and self._host.session:
            await device.vanish(self._host.session)
        else:
            self._pending_vanish[entry_id] = device
        if self._vdc:
            dsuid = self._build_device_dsuid(entry_id)
            self._vdc.remove_device(dsuid)
```

- [ ] **Step 7: Run all api tests**

```bash
source .venv/bin/activate && pytest tests/test_api.py -v
```

Expected: all tests PASS.

- [ ] **Step 8: Verify test for `_on_session_ready` hook uses the new hook**

The test `test_session_ready_hook_skips_known_devices` calls `mock_host_instance._on_session_ready(mock_session)`. After `api.start()`, `host._on_session_ready` is replaced with `_hooked`. But in the test, `MockHost.return_value = mock_host_instance`, and `mock_host_instance._on_session_ready` is the MagicMock we set as `AsyncMock()`.

When `api.start()` runs, it does:
```python
_orig_session_ready = host._on_session_ready  # captures the AsyncMock
host._on_session_ready = _hooked              # replaces with _hooked
```

So after `api.start()`, `mock_host_instance._on_session_ready` IS `_hooked` — the test calling it correctly triggers our hook. ✓

- [ ] **Step 9: Commit**

```bash
git add custom_components/dsvdc4ha/api.py tests/test_api.py
git commit -m "feat: skip re-announcing known devices on DSS reconnect using _ever_announced"
```

---

## Task 3: Wire `async_remove_entry()` to use hard stop

When the user deletes the integration entry entirely, we want full cleanup: vanish all devices AND deregister mDNS so DSS removes everything cleanly. `async_remove_entry()` is the only caller that needs `deregister_mdns=True`; `coordinator.async_stop()` keeps the default (soft).

**Files:**
- Modify: `custom_components/dsvdc4ha/__init__.py:213-219` (`async_remove_entry`)
- Modify: `tests/test_init.py` — 1 new test (or update existing if one covers remove_entry)

- [ ] **Step 1: Check what test_init.py already covers for `async_remove_entry`**

```bash
source .venv/bin/activate && grep -n "remove_entry\|async_remove" tests/test_init.py
```

Note whether a test for `async_remove_entry` exists. If it does, read it to understand the mock structure before writing the new test.

- [ ] **Step 2: Write a failing test that hard stop is used in `async_remove_entry`**

Add to `tests/test_init.py`:

```python
@pytest.mark.asyncio
async def test_async_remove_entry_uses_hard_stop(hass):
    """async_remove_entry passes deregister_mdns=True to api.stop()."""
    from custom_components.dsvdc4ha import async_remove_entry
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_api = MagicMock()
    mock_api.vanish_device = AsyncMock()
    mock_api.stop = AsyncMock()

    mock_coordinator = MagicMock()
    mock_coordinator.api = mock_api

    mock_entry = MagicMock()
    mock_entry.subentries = {"sub1": MagicMock(), "sub2": MagicMock()}

    hass.data.setdefault("dsvdc4ha", {})["hub"] = mock_coordinator

    await async_remove_entry(hass, mock_entry)

    # vanish called for every subentry
    assert mock_api.vanish_device.await_count == 2
    # stop called with deregister_mdns=True
    mock_api.stop.assert_awaited_once_with(deregister_mdns=True)
```

- [ ] **Step 3: Run the test to confirm it fails**

```bash
source .venv/bin/activate && pytest tests/test_init.py::test_async_remove_entry_uses_hard_stop -v
```

Expected: FAIL (stop called without keyword argument, or `deregister_mdns` not accepted).

- [ ] **Step 4: Update `async_remove_entry()` in `__init__.py`**

Change the last line of `async_remove_entry()` from:

```python
await hub.api.stop()
```

to:

```python
await hub.api.stop(deregister_mdns=True)
```

The full function should now read:

```python
async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Called when the hub config entry is fully deleted."""
    hub: HubCoordinator | None = hass.data.get(DOMAIN, {}).pop("hub", None)
    if hub:
        for subentry in entry.subentries.values():
            await hub.api.vanish_device(subentry.subentry_id)
        await hub.api.stop(deregister_mdns=True)
```

- [ ] **Step 5: Run all tests**

```bash
source .venv/bin/activate && pytest tests/ -q
```

Expected: all tests PASS (252+ passing).

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/__init__.py tests/test_init.py
git commit -m "feat: use hard stop in async_remove_entry to send mDNS goodbye on true deletion"
```

---

## Expected Outcome

After all three tasks, HA shutdown/restart behavior changes from:

**Before:**
1. HA stops → mDNS goodbye sent → DSS removes all 20 devices from lookup
2. HA restarts (~40 s) → VDC announces VDC + all 20 devices
3. DSS re-processes 20 devices → 2 s delay → devices operational

**After:**
1. HA stops → TCP closes (no mDNS goodbye) → DSS marks VDC offline, **keeps all devices in lookup**
2. HA restarts (~40 s) → VDC announces VDC only
3. DSS already has all devices → **immediately operational** after TCP reconnect

For integration reloads within the same HA process (even faster restart):
- mDNS stays registered (no process exit, no Zeroconf goodbye)
- DSS stays connected or reconnects in seconds
- No device re-announcement at all (`_ever_announced` populated from previous session)

True device deletion (`async_remove_entry`): unchanged behavior — vanish + mDNS goodbye + TCP close.
