# DSS Connection Status Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show DSS connection state and IP in HA — a hub device with a `binary_sensor` (connectivity) and a diagnostic `sensor` (DSS IP address), kept live by 30-second polling.

**Architecture:** `DsvdcApi` gets three read-only properties sourced from `VdcHost.session`. `HubCoordinator` polls every 30 s via `async_track_time_interval`, fires registered callbacks on state change. `binary_sensor.py` and `sensor.py` each add one hub-level entity that subscribes to those callbacks. `__init__.py` registers the hub HA device and subscribes to update the config entry title when the DSS IP changes.

**Tech Stack:** Home Assistant config-entries / device-registry / entity platform APIs, `homeassistant.helpers.event.async_track_time_interval`, `pydsvdcapi 0.8.8` (`VdcHost.session`, `VdcSession.is_active`, `VdcSession.connection.peername`, `VdcSession.vdsm_dsuid`)

---

## File Map

| File | Change |
|------|--------|
| `custom_components/dsvdc4ha/api.py` | Add `is_connected`, `dss_peer`, `dss_dsuid` properties |
| `custom_components/dsvdc4ha/coordinator.py` | Add state-change callback registry + 30 s polling |
| `custom_components/dsvdc4ha/__init__.py` | Register hub device; subscribe to update entry title |
| `custom_components/dsvdc4ha/binary_sensor.py` | Add `DssConnectivityEntity` (hub-level) |
| `custom_components/dsvdc4ha/sensor.py` | Add `DssAddressSensor` (hub-level diagnostic) |
| `custom_components/dsvdc4ha/strings.json` | Add `entity` section for translation keys |
| `custom_components/dsvdc4ha/translations/en.json` | Same |
| `tests/test_api.py` | Tests for the three new properties |
| `tests/test_coordinator.py` | Tests for polling + callback mechanism |
| `tests/test_sensor.py` | Tests for `DssAddressSensor` |

---

## Task 1: Add connection state properties to `DsvdcApi`

**Files:**
- Modify: `custom_components/dsvdc4ha/api.py`
- Test: `tests/test_api.py`

`DsvdcApi` already holds `self._host: VdcHost | None` (set in `start()`). `host.session` is `VdcSession | None`. `VdcSession.connection.peername` returns `"IP:port"`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_api.py`:

```python
def _make_api():
    return DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp/s")


def test_is_connected_false_when_no_host():
    api = _make_api()
    assert api.is_connected is False


def test_is_connected_false_when_session_none():
    api = _make_api()
    api._host = MagicMock()
    api._host.session = None
    assert api.is_connected is False


def test_is_connected_false_when_session_inactive():
    api = _make_api()
    session = MagicMock()
    session.is_active = False
    api._host = MagicMock()
    api._host.session = session
    assert api.is_connected is False


def test_is_connected_true_when_session_active():
    api = _make_api()
    session = MagicMock()
    session.is_active = True
    api._host = MagicMock()
    api._host.session = session
    assert api.is_connected is True


def test_dss_peer_none_when_disconnected():
    api = _make_api()
    assert api.dss_peer is None


def test_dss_peer_returns_peername():
    api = _make_api()
    session = MagicMock()
    session.is_active = True
    session.connection.peername = "192.168.1.100:8444"
    api._host = MagicMock()
    api._host.session = session
    assert api.dss_peer == "192.168.1.100:8444"


def test_dss_dsuid_none_when_disconnected():
    api = _make_api()
    assert api.dss_dsuid is None


def test_dss_dsuid_returns_vdsm_dsuid():
    api = _make_api()
    session = MagicMock()
    session.is_active = True
    session.vdsm_dsuid = "0000000000000000000000000000000001"
    api._host = MagicMock()
    api._host.session = session
    assert api.dss_dsuid == "0000000000000000000000000000000001"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_api.py -k "is_connected or dss_peer or dss_dsuid" -v
```

Expected: `AttributeError: 'DsvdcApi' object has no attribute 'is_connected'`

- [ ] **Step 3: Add the three properties to `DsvdcApi`**

Find the `DsvdcApi` class definition in `api.py` (the class body ends around line 450+). Add these three properties right after the `__init__` method or after the existing `registered_entry_ids` property:

```python
@property
def is_connected(self) -> bool:
    """True when a DSS session is currently active."""
    session = getattr(self._host, "session", None) if self._host else None
    return session is not None and bool(session.is_active)

@property
def dss_peer(self) -> str | None:
    """Return 'IP:port' of the connected DSS, or None."""
    session = getattr(self._host, "session", None) if self._host else None
    if session is None or not session.is_active:
        return None
    try:
        return session.connection.peername
    except Exception:
        return None

@property
def dss_dsuid(self) -> str | None:
    """Return the dSUID of the connected DSS, or None."""
    session = getattr(self._host, "session", None) if self._host else None
    if session is None or not session.is_active:
        return None
    return getattr(session, "vdsm_dsuid", None)
```

Note: `self._host` is set to `None` initially (before `start()`) — verify the attribute name by reading `DsvdcApi.__init__` before editing. The attribute is assigned as `self._host` in `_build_host_and_vdc`.

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_api.py -k "is_connected or dss_peer or dss_dsuid" -v
```

Expected: 8 tests PASS

- [ ] **Step 5: Run full test suite to check for regressions**

```
pytest tests/ -x -q
```

Expected: all existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/api.py tests/test_api.py
git commit -m "feat: add is_connected/dss_peer/dss_dsuid properties to DsvdcApi"
```

---

## Task 2: Add state polling and callback mechanism to `HubCoordinator`

**Files:**
- Modify: `custom_components/dsvdc4ha/coordinator.py`
- Test: `tests/test_coordinator.py`

The coordinator needs to poll every 30 s and fire sync callbacks when `is_connected` or `dss_peer` changes. Hub entities and `__init__.py` will subscribe.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_coordinator.py` (after the existing tests):

```python
from unittest.mock import call
from datetime import timedelta


@pytest.mark.asyncio
async def test_coordinator_register_callback_and_unregister(mock_hass):
    from custom_components.dsvdc4ha.coordinator import HubCoordinator
    coord = HubCoordinator(mock_hass, port=9090)
    called = []
    unsub = coord.register_state_callback(lambda: called.append(1))
    assert len(coord._state_callbacks) == 1
    unsub()
    assert len(coord._state_callbacks) == 0


@pytest.mark.asyncio
async def test_check_and_notify_fires_on_connect(mock_hass):
    from custom_components.dsvdc4ha.coordinator import HubCoordinator
    coord = HubCoordinator(mock_hass, port=9090)
    coord.api = MagicMock()
    coord.api.is_connected = True
    coord.api.dss_peer = "192.168.1.1:8444"
    coord._last_connected = False
    coord._last_peer = None

    fired = []
    coord.register_state_callback(lambda: fired.append(1))
    await coord._check_and_notify()
    assert len(fired) == 1
    assert coord._last_connected is True
    assert coord._last_peer == "192.168.1.1:8444"


@pytest.mark.asyncio
async def test_check_and_notify_no_fire_when_unchanged(mock_hass):
    from custom_components.dsvdc4ha.coordinator import HubCoordinator
    coord = HubCoordinator(mock_hass, port=9090)
    coord.api = MagicMock()
    coord.api.is_connected = True
    coord.api.dss_peer = "192.168.1.1:8444"
    coord._last_connected = True
    coord._last_peer = "192.168.1.1:8444"

    fired = []
    coord.register_state_callback(lambda: fired.append(1))
    await coord._check_and_notify()
    assert len(fired) == 0


@pytest.mark.asyncio
async def test_async_stop_cancels_poll(mock_hass, mock_api):
    mock_zeroconf = MagicMock()
    mock_integration = MagicMock()
    mock_integration.version = "1.2.3"
    mock_unsub = MagicMock()
    with (
        patch("custom_components.dsvdc4ha.coordinator.DsvdcApi", return_value=mock_api),
        patch(
            "custom_components.dsvdc4ha.coordinator.async_get_instance",
            new=AsyncMock(return_value=mock_zeroconf),
        ),
        patch(
            "custom_components.dsvdc4ha.coordinator.async_get_integration",
            new=AsyncMock(return_value=mock_integration),
        ),
        patch(
            "custom_components.dsvdc4ha.coordinator.async_track_time_interval",
            return_value=mock_unsub,
        ),
    ):
        from custom_components.dsvdc4ha.coordinator import HubCoordinator
        coord = HubCoordinator(mock_hass, port=9090)
        await coord.async_start()
        await coord.async_stop()
        mock_unsub.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_coordinator.py -k "callback or notify or poll" -v
```

Expected: `AttributeError` on `_state_callbacks` / `register_state_callback` / `_check_and_notify`

- [ ] **Step 3: Rewrite `coordinator.py`**

Replace the entire content of `custom_components/dsvdc4ha/coordinator.py`:

```python
"""HubCoordinator — manages VdcHost + Vdc lifecycle."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from homeassistant.components.zeroconf import async_get_instance
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.loader import async_get_integration

from .api import DsvdcApi
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_POLL_INTERVAL = timedelta(seconds=30)


class HubCoordinator:
    """Owns the DsvdcApi instance for the hub config entry."""

    def __init__(self, hass: HomeAssistant, port: int) -> None:
        self.hass = hass
        self._port = port
        self.api: DsvdcApi | None = None
        self._state_callbacks: list[Callable[[], None]] = []
        self._last_connected: bool = False
        self._last_peer: str | None = None
        self._poll_unsub: Callable[[], None] | None = None

    def register_state_callback(self, cb: Callable[[], None]) -> Callable[[], None]:
        """Register a callback fired whenever connection state changes.

        Returns an unsubscribe callable.
        """
        self._state_callbacks.append(cb)

        def _unsub() -> None:
            try:
                self._state_callbacks.remove(cb)
            except ValueError:
                pass

        return _unsub

    async def _check_and_notify(self, now: Any = None) -> None:
        """Compare current DSS state to cache; fire callbacks on change."""
        if self.api is None:
            return
        connected = self.api.is_connected
        peer = self.api.dss_peer
        if connected != self._last_connected or peer != self._last_peer:
            self._last_connected = connected
            self._last_peer = peer
            for cb in list(self._state_callbacks):
                cb()

    async def async_start(self, on_session_ready=None) -> None:
        integration = await async_get_integration(self.hass, DOMAIN)
        version = str(integration.version) if integration.version else "0.0.0"
        config_url = (
            f"{self.hass.config.internal_url}/config/integrations"
            if self.hass.config.internal_url
            else "http://homeassistant.local/config/integrations"
        )
        state_path = self.hass.config.path("dsvdc4ha", "host_state")
        self.api = DsvdcApi(
            port=self._port,
            version=version,
            config_url=config_url,
            state_path=state_path,
        )
        zeroconf = await async_get_instance(self.hass)
        await self.api.start(zeroconf=zeroconf, on_session_ready=on_session_ready)
        self._poll_unsub = async_track_time_interval(
            self.hass, self._check_and_notify, _POLL_INTERVAL
        )
        _LOGGER.info("dsvdc4ha hub started")

    async def async_stop(self) -> None:
        if self._poll_unsub:
            self._poll_unsub()
            self._poll_unsub = None
        if self.api:
            await self.api.stop()
        _LOGGER.info("dsvdc4ha hub stopped")
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_coordinator.py -v
```

Expected: all coordinator tests PASS

- [ ] **Step 5: Run full suite**

```
pytest tests/ -x -q
```

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/coordinator.py tests/test_coordinator.py
git commit -m "feat: add DSS state polling and callback mechanism to HubCoordinator"
```

---

## Task 3: Register hub device and update entry title in `__init__.py`

**Files:**
- Modify: `custom_components/dsvdc4ha/__init__.py`
- Test: `tests/test_init.py`

The hub device must exist in the HA device registry before platform setups run (so hub entities have a parent). The config entry title should show the DSS IP when connected.

- [ ] **Step 1: Write the failing test**

Read `tests/test_init.py` first to understand its structure. Then add:

```python
@pytest.mark.asyncio
async def test_hub_device_registered_on_setup(mock_hass):
    """async_setup_entry must create a hub device in the device registry."""
    from custom_components.dsvdc4ha import async_setup_entry
    from custom_components.dsvdc4ha.const import DOMAIN

    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {"port": 9090}
    entry.subentries = {}

    mock_coordinator = AsyncMock()
    mock_coordinator.api = MagicMock()
    mock_coordinator.api.is_connected = False
    mock_coordinator.api.dss_peer = None
    mock_coordinator.register_state_callback.return_value = lambda: None

    dev_reg = MagicMock()
    dev_reg.async_get_or_create.return_value = MagicMock()

    with (
        patch("custom_components.dsvdc4ha.HubCoordinator", return_value=mock_coordinator),
        patch("custom_components.dsvdc4ha.dr.async_get", return_value=dev_reg),
        patch("custom_components.dsvdc4ha.er.async_get", return_value=MagicMock()),
        patch("homeassistant.config_entries.ConfigEntries.async_forward_entry_setups", new=AsyncMock()),
        patch("custom_components.dsvdc4ha._backfill_missing_icons", new=AsyncMock()),
    ):
        mock_hass.data = {}
        mock_hass.config_entries = MagicMock()
        mock_hass.config_entries.async_forward_entry_setups = AsyncMock()
        await async_setup_entry(mock_hass, entry)
        dev_reg.async_get_or_create.assert_called_once()
        call_kwargs = dev_reg.async_get_or_create.call_args.kwargs
        assert (DOMAIN, "test_entry_id") in call_kwargs["identifiers"]
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_init.py::test_hub_device_registered_on_setup -v
```

Expected: FAIL (no `async_get_or_create` call yet)

- [ ] **Step 3: Add hub device registration and title update to `async_setup_entry`**

In `custom_components/dsvdc4ha/__init__.py`, modify `async_setup_entry`:

After `hass.data[DOMAIN]["hub"] = coordinator` and before the `async_forward_entry_setups` call, insert:

```python
    # Register hub device so hub-level entities have a parent in the device registry.
    from .const import VDC_HOST_MODEL, VDC_HOST_VENDOR_NAME
    dev_reg = dr.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name="dSVDC Hub",
        manufacturer=VDC_HOST_VENDOR_NAME,
        model=VDC_HOST_MODEL,
    )

    @callback
    def _on_dss_state_changed() -> None:
        if coordinator.api is None:
            return
        peer = coordinator.api.dss_peer
        if peer:
            ip = peer.split(":")[0]
            new_title = f"dSVDC Hub ({ip})"
        else:
            new_title = "dSVDC Hub"
        hass.config_entries.async_update_entry(entry, title=new_title)

    entry.async_on_unload(coordinator.register_state_callback(_on_dss_state_changed))
    # Set initial title immediately (coordinator may already be connected).
    _on_dss_state_changed()
    # Also fire a state check immediately to warm the coordinator's cache.
    hass.async_create_task(coordinator._check_and_notify())
```

Also ensure `from homeassistant.core import Event, HomeAssistant, callback` — `callback` is already imported.

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_init.py::test_hub_device_registered_on_setup -v
```

Expected: PASS

- [ ] **Step 5: Run full suite**

```
pytest tests/ -x -q
```

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/__init__.py tests/test_init.py
git commit -m "feat: register hub device and update entry title with DSS IP"
```

---

## Task 4: Add `DssConnectivityEntity` to `binary_sensor.py`

**Files:**
- Modify: `custom_components/dsvdc4ha/binary_sensor.py`
- No new test file needed — add to `tests/test_sensor.py` pattern or inline

The hub binary sensor shows `True` when the DSS session is active. It subscribes to coordinator state callbacks and calls `async_write_ha_state()` on change. It does NOT have a `config_subentry_id`.

- [ ] **Step 1: Write the failing test**

Create or append to a new test block — add to `tests/test_sensor.py` (it already imports similar patterns):

Actually, add to `tests/test_coordinator.py` at the bottom since it already has the coordinator fixture context, or create a minimal test in `tests/test_init.py`. The simplest approach is to test the entity directly in isolation. Add to a new block at end of `tests/test_sensor.py`:

```python
def test_dss_connectivity_entity_is_on_when_connected():
    from custom_components.dsvdc4ha.binary_sensor import DssConnectivityEntity
    from unittest.mock import MagicMock

    entry = MagicMock()
    entry.entry_id = "eid"

    coordinator = MagicMock()
    coordinator.api = MagicMock()
    coordinator.api.is_connected = True

    entity = DssConnectivityEntity(entry, coordinator)
    assert entity.is_on is True


def test_dss_connectivity_entity_is_off_when_disconnected():
    from custom_components.dsvdc4ha.binary_sensor import DssConnectivityEntity
    from unittest.mock import MagicMock

    entry = MagicMock()
    entry.entry_id = "eid"

    coordinator = MagicMock()
    coordinator.api = MagicMock()
    coordinator.api.is_connected = False

    entity = DssConnectivityEntity(entry, coordinator)
    assert entity.is_on is False


def test_dss_connectivity_entity_is_off_when_no_api():
    from custom_components.dsvdc4ha.binary_sensor import DssConnectivityEntity
    from unittest.mock import MagicMock

    entry = MagicMock()
    entry.entry_id = "eid"

    coordinator = MagicMock()
    coordinator.api = None

    entity = DssConnectivityEntity(entry, coordinator)
    assert entity.is_on is False
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_sensor.py -k "dss_connectivity" -v
```

Expected: `ImportError` — `DssConnectivityEntity` does not exist yet

- [ ] **Step 3: Add `DssConnectivityEntity` to `binary_sensor.py`**

At the top of `binary_sensor.py`, add to imports:

```python
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
```

(Replace the existing `from homeassistant.components.binary_sensor import BinarySensorEntity` line with the expanded import above — add `BinarySensorDeviceClass`; add `EntityCategory` to the `homeassistant.helpers.entity` import.)

Also add the coordinator import:
```python
from .coordinator import HubCoordinator
```

Then add the new class at the bottom of `binary_sensor.py`:

```python
class DssConnectivityEntity(BinarySensorEntity):
    """Hub-level binary sensor showing DSS connection status."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "dss_connectivity"

    def __init__(self, entry: ConfigEntry, coordinator: HubCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_dss_connectivity"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
        )

    @property
    def is_on(self) -> bool:
        return self._coordinator.api is not None and self._coordinator.api.is_connected

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.register_state_callback(
                lambda: self.async_write_ha_state()
            )
        )
```

Finally, modify `async_setup_entry` in `binary_sensor.py` to also create the hub entity:

```python
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    hass.data.setdefault(DOMAIN, {})["_add_binary_entities"] = async_add_entities
    coordinator = hass.data[DOMAIN]["hub"]
    async_add_entities([DssConnectivityEntity(entry, coordinator)])
    for subentry in entry.subentries.values():
        _add_entities_for_subentry(subentry, async_add_entities)
```

Note: `async_add_entities([DssConnectivityEntity(...)])` is called without `config_subentry_id` so the entity belongs to the main entry (and its device is the hub device).

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_sensor.py -k "dss_connectivity" -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Run full suite**

```
pytest tests/ -x -q
```

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/binary_sensor.py tests/test_sensor.py
git commit -m "feat: add DssConnectivityEntity hub binary sensor"
```

---

## Task 5: Add `DssAddressSensor` to `sensor.py`

**Files:**
- Modify: `custom_components/dsvdc4ha/sensor.py`
- Test: add to `tests/test_sensor.py`

Shows the DSS IP address as a diagnostic sensor. Native value is just the IP (not port). Extra state attributes include the dSUID for advanced users.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_sensor.py`:

```python
def test_dss_address_sensor_returns_ip():
    from custom_components.dsvdc4ha.sensor import DssAddressSensor
    from unittest.mock import MagicMock

    entry = MagicMock()
    entry.entry_id = "eid"

    coordinator = MagicMock()
    coordinator.api = MagicMock()
    coordinator.api.dss_peer = "192.168.1.55:8444"
    coordinator.api.dss_dsuid = "abc123"

    entity = DssAddressSensor(entry, coordinator)
    assert entity.native_value == "192.168.1.55"


def test_dss_address_sensor_returns_none_when_disconnected():
    from custom_components.dsvdc4ha.sensor import DssAddressSensor
    from unittest.mock import MagicMock

    entry = MagicMock()
    entry.entry_id = "eid"

    coordinator = MagicMock()
    coordinator.api = MagicMock()
    coordinator.api.dss_peer = None
    coordinator.api.dss_dsuid = None

    entity = DssAddressSensor(entry, coordinator)
    assert entity.native_value is None


def test_dss_address_sensor_extra_attrs_include_dsuid():
    from custom_components.dsvdc4ha.sensor import DssAddressSensor
    from unittest.mock import MagicMock

    entry = MagicMock()
    entry.entry_id = "eid"

    coordinator = MagicMock()
    coordinator.api = MagicMock()
    coordinator.api.dss_peer = "10.0.0.1:8444"
    coordinator.api.dss_dsuid = "dsuid_value"

    entity = DssAddressSensor(entry, coordinator)
    attrs = entity.extra_state_attributes
    assert attrs["dsuid"] == "dsuid_value"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_sensor.py -k "dss_address" -v
```

Expected: `ImportError` — `DssAddressSensor` does not exist yet

- [ ] **Step 3: Add `DssAddressSensor` to `sensor.py`**

Add to the import block at the top:

```python
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
```

(Add `EntityCategory` if not already imported; `DeviceInfo` may already be there.)

Also add the coordinator import:
```python
from .coordinator import HubCoordinator
```

Add the new class at the bottom of `sensor.py`:

```python
class DssAddressSensor(SensorEntity):
    """Hub-level diagnostic sensor showing the connected DSS IP address."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "dss_address"

    def __init__(self, entry: ConfigEntry, coordinator: HubCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_dss_address"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
        )

    @property
    def native_value(self) -> str | None:
        if self._coordinator.api is None:
            return None
        peer = self._coordinator.api.dss_peer
        if not peer:
            return None
        return peer.split(":")[0]

    @property
    def extra_state_attributes(self) -> dict:
        if self._coordinator.api is None:
            return {}
        dsuid = self._coordinator.api.dss_dsuid
        return {"dsuid": dsuid} if dsuid else {}

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.register_state_callback(
                lambda: self.async_write_ha_state()
            )
        )
```

Also add the `ConfigEntry` import to `sensor.py`:
```python
from homeassistant.config_entries import ConfigEntry
```

Modify `async_setup_entry` in `sensor.py` to also create hub entities:

```python
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    hass.data.setdefault(DOMAIN, {})["_add_sensor_entities"] = async_add_entities
    coordinator = hass.data[DOMAIN]["hub"]
    async_add_entities([DssAddressSensor(entry, coordinator)])
    for subentry in entry.subentries.values():
        _add_entities_for_subentry(subentry, async_add_entities)
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_sensor.py -k "dss_address" -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Run full suite**

```
pytest tests/ -x -q
```

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/sensor.py tests/test_sensor.py
git commit -m "feat: add DssAddressSensor hub diagnostic sensor"
```

---

## Task 6: Add entity translation keys to strings.json and en.json

**Files:**
- Modify: `custom_components/dsvdc4ha/strings.json`
- Modify: `custom_components/dsvdc4ha/translations/en.json`

HA resolves `_attr_translation_key` by looking up `entity.<platform>.<translation_key>.name` in the translation file. The platform is the entity's domain (`binary_sensor` / `sensor`).

- [ ] **Step 1: Verify no existing `entity` section**

```
grep -n '"entity"' custom_components/dsvdc4ha/strings.json
```

Expected: no output

- [ ] **Step 2: Add `entity` section to both files**

In `custom_components/dsvdc4ha/strings.json`, add before the closing `}` of the top-level object (after the `"config_subentries"` block):

```json
  ,
  "entity": {
    "binary_sensor": {
      "dss_connectivity": {
        "name": "DSS Connection"
      }
    },
    "sensor": {
      "dss_address": {
        "name": "DSS Address"
      }
    }
  }
```

Apply the exact same addition to `custom_components/dsvdc4ha/translations/en.json`.

- [ ] **Step 3: Verify JSON validity**

```bash
python -c "import json; json.load(open('custom_components/dsvdc4ha/strings.json'))" && echo OK
python -c "import json; json.load(open('custom_components/dsvdc4ha/translations/en.json'))" && echo OK
```

Expected: `OK` for both

- [ ] **Step 4: Run full suite**

```
pytest tests/ -x -q
```

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/strings.json custom_components/dsvdc4ha/translations/en.json
git commit -m "feat: add entity translation keys for hub DSS status entities"
```

---

## Self-Review

**Spec coverage:**
- [x] DSS IP shown in config entry title → Task 3 (`_on_dss_state_changed` → `async_update_entry`)
- [x] Connection tracking via polling → Task 2 (30 s `async_track_time_interval`)
- [x] HA best practice: `binary_sensor` with `device_class=connectivity` → Task 4
- [x] DSS IP in diagnostic sensor → Task 5
- [x] Hub device in device registry (parent for both hub entities) → Task 3
- [x] All entities subscribe to state changes via callback → Tasks 4, 5

**Placeholder scan:** None — all steps contain exact code.

**Type consistency:**
- `DssConnectivityEntity(entry: ConfigEntry, coordinator: HubCoordinator)` — same signature in Tasks 3, 4
- `DssAddressSensor(entry: ConfigEntry, coordinator: HubCoordinator)` — same signature in Tasks 3, 5
- `coordinator.register_state_callback(cb) → Callable[[], None]` — defined in Task 2, used in Tasks 3, 4, 5
- `coordinator.api.is_connected: bool` — defined in Task 1, used in Tasks 4
- `coordinator.api.dss_peer: str | None` — defined in Task 1, used in Tasks 3, 5
- `coordinator.api.dss_dsuid: str | None` — defined in Task 1, used in Task 5
