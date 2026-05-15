# Persist dSS-Assigned Settings Across HA Restarts

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Binary input `group`, `sensorFunction`, and other dSS-writable settings survive HA restarts instead of being reset to entity_mapping defaults on every startup.

**Architecture:** pydsvdcapi lets the dSS write settings like `binaryInputSettings/group` via `setProperty`. Our integration currently replaces the whole device from config-entry data on every restart, discarding those writes. The fix: intercept `apply_settings` via a subclass or callback, and write any dSS-changed settings back into the HA config-entry data so they're used on the next startup.

**Tech Stack:** Python, HA config entries API (`hass.config_entries.async_update_entry`), pydsvdcapi `BinaryInput`, `SensorInput`.

---

## Root Cause

After a device is announced, the dSS sends `setProperty binaryInputSettings group=<its stored value>` to configure it from the dSS's own database. On first setup for a newly-learned device the dSS default may be 0 (reserved/unassigned). pydsvdcapi calls `bi.apply_settings({"group": 0})`, overwriting our group=8.

On the next HA restart we recreate the device from `subentry.data["vdsds"]` — which still has group=8 — so the dSS resets it to 0 again. Loop.

The binary-input *state* (value/age) is volatile and NOT persisted; only *settings* (group, sensorFunction) are affected.

---

## File Structure

| File | Change |
|------|--------|
| `custom_components/dsvdc4ha/api.py` | `_add_binary_input`: wrap `apply_settings` to fire a save callback |
| `custom_components/dsvdc4ha/__init__.py` | Wire up the save callback during `add_device`; provide update helper |
| `tests/test_api.py` | Test that `apply_settings` fires the callback with the right data |
| `tests/test_init.py` | Integration test: settings written by dSS are stored in config entry |

---

### Task 1: Monkey-patch `apply_settings` on BinaryInput to fire a callback

When the dSS changes a binary input's settings we need to know immediately.

**Files:**
- Modify: `custom_components/dsvdc4ha/api.py` — `_add_binary_input` method (lines ~402-414)

- [ ] **Step 1: Write a failing test**

```python
# tests/test_api.py
def test_add_binary_input_fires_settings_callback_on_apply():
    """_add_binary_input should wrap apply_settings so that when the dSS writes
    new settings, a provided callback is called with (entry_id, vdsd_idx, bi_dsindex, settings)."""
    api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")
    mock_vdsd = MagicMock()
    mock_vdsd.get_binary_input = MagicMock()

    captured = []
    def _on_settings(entry_id, vdsd_idx, ds_index, settings):
        captured.append((entry_id, vdsd_idx, ds_index, settings))

    bi_data = {
        "dsIndex": 0, "name": "Motion", "group": 8, "sensorFunction": 1,
        "hardwiredFunction": 1, "updateInterval": 1.0, "inputType": 1, "inputUsage": 0,
    }
    # _add_binary_input needs to accept an optional on_settings_changed kwarg
    api._add_binary_input(mock_vdsd, bi_data, on_settings_changed=_on_settings,
                          entry_id="sub1", vdsd_idx=0)

    created_bi = mock_vdsd.add_binary_input.call_args[0][0]
    created_bi.apply_settings({"group": 0, "sensorFunction": 2})

    assert len(captured) == 1
    entry_id, vdsd_idx, ds_index, settings = captured[0]
    assert entry_id == "sub1"
    assert vdsd_idx == 0
    assert ds_index == 0
    assert settings == {"group": 0, "sensorFunction": 2}
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
.venv/bin/python -m pytest tests/test_api.py::test_add_binary_input_fires_settings_callback_on_apply -v
```
Expected: FAIL (TypeError or AttributeError)

- [ ] **Step 3: Implement the wrapper in `_add_binary_input`**

```python
def _add_binary_input(
    self,
    vdsd: Vdsd,
    data: dict[str, Any],
    *,
    on_settings_changed: Any | None = None,
    entry_id: str = "",
    vdsd_idx: int = 0,
) -> None:
    bi = BinaryInput(
        vdsd=vdsd,
        ds_index=data["dsIndex"],
        name=data["name"],
        sensor_function=BinaryInputType(data["sensorFunction"]),
        hardwired_function=BinaryInputType(data.get("hardwiredFunction", 0)),
        group=data.get("group", 0),
        update_interval=float(data.get("updateInterval", 0)),
        input_type=data.get("inputType", 1),
        input_usage=BinaryInputUsage(data.get("inputUsage", 0)),
    )
    if on_settings_changed is not None:
        _orig_apply = bi.apply_settings
        _ds_index = data["dsIndex"]

        def _patched_apply(incoming: dict) -> None:
            _orig_apply(incoming)
            on_settings_changed(entry_id, vdsd_idx, _ds_index, dict(incoming))

        bi.apply_settings = _patched_apply
    vdsd.add_binary_input(bi)
```

- [ ] **Step 4: Run test — confirm it passes**

```bash
.venv/bin/python -m pytest tests/test_api.py::test_add_binary_input_fires_settings_callback_on_apply -v
```
Expected: PASS

- [ ] **Step 5: Run all tests to check nothing broke**

```bash
.venv/bin/python -m pytest tests/ -q
```
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/api.py tests/test_api.py
git commit -m "feat: wrap BinaryInput.apply_settings to fire callback on dSS-side settings write"
```

---

### Task 2: Update `_build_vdsd` to pass the callback into `_add_binary_input`

`_build_vdsd` currently calls `_add_binary_input(vdsd, bi_data)` — we need it to pass `entry_id`, `vdsd_idx`, and `on_settings_changed`.

**Files:**
- Modify: `custom_components/dsvdc4ha/api.py` — `_build_vdsd` (lines ~345-382) and `add_device`

- [ ] **Step 1: Write failing test**

```python
def test_build_vdsd_passes_entry_id_and_vdsd_idx_to_add_binary_input():
    """_build_vdsd should forward entry_id and vdsd_idx to _add_binary_input."""
    api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")
    captured = []
    original = api._add_binary_input

    def _spy(vdsd, data, **kwargs):
        captured.append(kwargs)
        return original(vdsd, data, **kwargs)

    api._add_binary_input = _spy

    mock_device = MagicMock()
    bi_data = {
        "dsIndex": 0, "name": "M", "group": 8, "sensorFunction": 0,
        "hardwiredFunction": 0, "updateInterval": 1.0, "inputType": 1, "inputUsage": 0,
        "callback_entity": "binary_sensor.m",
    }
    vdsd_data = {
        "displayId": "T", "primaryGroup": 8, "model": "T", "vendorName": "V",
        "modelVersion": "1.0", "modelUID": "VT", "name": "Test",
        "active": True, "identify_action": None, "firmwareUpdate_action": None,
        "optional": {}, "buttons": [], "binary_inputs": [bi_data], "sensors": [], "output": None,
    }
    api._build_vdsd(mock_device, 2, vdsd_data, entry_id="sub_abc", on_settings_changed=lambda *a: None)

    assert len(captured) == 1
    assert captured[0]["entry_id"] == "sub_abc"
    assert captured[0]["vdsd_idx"] == 2
    assert "on_settings_changed" in captured[0]
```

- [ ] **Step 2: Run — confirm fail**

```bash
.venv/bin/python -m pytest tests/test_api.py::test_build_vdsd_passes_entry_id_and_vdsd_idx_to_add_binary_input -v
```

- [ ] **Step 3: Update `_build_vdsd` signature and `_add_binary_input` calls**

```python
def _build_vdsd(
    self,
    device: Device,
    idx: int,
    data: dict[str, Any],
    *,
    entry_id: str = "",
    on_settings_changed: Any | None = None,
) -> Vdsd:
    vdsd = Vdsd(...)  # unchanged
    for btn_data in data.get("buttons", []):
        self._add_button(vdsd, btn_data)
    for bi_data in data.get("binary_inputs", []):
        self._add_binary_input(
            vdsd, bi_data,
            on_settings_changed=on_settings_changed,
            entry_id=entry_id,
            vdsd_idx=idx,
        )
    for si_data in data.get("sensors", []):
        self._add_sensor(vdsd, si_data)
    ...
```

Also update `add_device` to accept and pass `on_settings_changed`:

```python
def add_device(
    self,
    entry_id: str,
    vdsds_data: list[dict[str, Any]],
    *,
    on_settings_changed: Any | None = None,
) -> None:
    ...
    for idx, vdsd_data in enumerate(vdsds_data):
        vdsd = self._build_vdsd(device, idx, vdsd_data,
                                entry_id=entry_id,
                                on_settings_changed=on_settings_changed)
        device.add_vdsd(vdsd)
    ...
```

- [ ] **Step 4: Run — confirm pass**

```bash
.venv/bin/python -m pytest tests/test_api.py -v -q
```

- [ ] **Step 5: Run all tests**

```bash
.venv/bin/python -m pytest tests/ -q
```

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/api.py tests/test_api.py
git commit -m "feat: thread entry_id and settings callback through _build_vdsd/_add_binary_input"
```

---

### Task 3: Wire up the settings persistence callback in `__init__.py`

When the dSS changes binary input settings, update the HA config-entry data so the new values survive the next restart.

**Files:**
- Modify: `custom_components/dsvdc4ha/__init__.py` — `async_setup_entry`

- [ ] **Step 1: Write failing test**

```python
# tests/test_init.py  (create if it doesn't exist; a simple pytest file, no HA fixtures needed)
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


def test_on_settings_changed_updates_subentry_data():
    """The on_settings_changed callback should update subentry.data['vdsds'] in-place
    and schedule a config-entry update."""
    from custom_components.dsvdc4ha.__init__ import _make_on_settings_changed

    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_update_subentry = AsyncMock()
    hass.loop = MagicMock()

    entry = MagicMock()
    subentry = MagicMock()
    subentry.subentry_id = "sub1"
    subentry.data = {
        "vdsds": [{
            "binary_inputs": [
                {"dsIndex": 0, "group": 8, "sensorFunction": 1},
            ],
        }],
    }
    entry.subentries = {"sub1": subentry}

    cb = _make_on_settings_changed(hass, entry, "sub1")
    cb("sub1", 0, 0, {"group": 2, "sensorFunction": 3})

    updated_bi = subentry.data["vdsds"][0]["binary_inputs"][0]
    assert updated_bi["group"] == 2
    assert updated_bi["sensorFunction"] == 3
```

- [ ] **Step 2: Run — confirm fail**

```bash
.venv/bin/python -m pytest tests/test_init.py::test_on_settings_changed_updates_subentry_data -v
```

- [ ] **Step 3: Implement `_make_on_settings_changed` in `__init__.py`**

Add at module level (before `async_setup_entry`):

```python
def _make_on_settings_changed(
    hass: HomeAssistant,
    entry: ConfigEntry,
    subentry_id: str,
) -> Any:
    """Return a callback that persists dSS-written binary-input settings.

    When the dSS sends setProperty to change a binary input's group or
    sensorFunction, this callback updates the config-entry data so the
    new value survives the next HA restart.
    """
    def _on_settings(entry_id: str, vdsd_idx: int, ds_index: int, settings: dict) -> None:
        subentry = entry.subentries.get(entry_id)
        if subentry is None:
            return
        vdsds = subentry.data.get("vdsds", [])
        if vdsd_idx >= len(vdsds):
            return
        vdsd_data = vdsds[vdsd_idx]
        for bi in vdsd_data.get("binary_inputs", []):
            if bi.get("dsIndex") == ds_index:
                bi.update(settings)
                break
        # Persist asynchronously — fire-and-forget from sync context.
        hass.async_create_task(
            hass.config_entries.async_update_subentry(entry, subentry, data=subentry.data)
        )

    return _on_settings
```

And in `async_setup_entry`, update the `add_device` call:

```python
for subentry in entry.subentries.values():
    vdsds = subentry.data.get("vdsds", [])
    on_settings = _make_on_settings_changed(hass, entry, subentry.subentry_id)
    coordinator.api.add_device(subentry.subentry_id, vdsds,
                               on_settings_changed=on_settings)
    ...
```

- [ ] **Step 4: Run — confirm pass**

```bash
.venv/bin/python -m pytest tests/test_init.py -v -q
```

- [ ] **Step 5: Run all tests**

```bash
.venv/bin/python -m pytest tests/ -q
```

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/__init__.py tests/test_init.py
git commit -m "feat: persist dSS-written binary-input settings (group, sensorFunction) to config entry"
```

---

## Notes

- `async_update_subentry` is the HA 2025.x API for updating a subentry's data dict. Check that it exists on the HA version used; fall back to `async_update_entry` with a patched subentries dict if not.
- The callback modifies `subentry.data` in-place. If HA enforces immutability (frozen dataclass), clone the dict first.
- This plan covers only binary inputs. Sensor `group` and `sensorType` could be handled similarly in a follow-up.
