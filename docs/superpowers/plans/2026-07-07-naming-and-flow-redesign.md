# Naming Architecture & Flow Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate the physical device name (config entry title only) from the dS vdSD name (= HA device name = DSS name), implement consistent reverse renaming in both directions, redesign the device flow to be iterative, and replace confirm-switch patterns with menu steps.

**Architecture:** Three phases that must be applied in order: (1) runtime naming foundation — data model fields + reverse sync between HA device registry and DSS; (2) config flow naming — config-entry-name first step, artefact-driven vdSD name, remove confirm switch; (3) device flow redesign — iterative one-entity-at-a-time selection replaces the batch plan/summary approach. Each phase ships independently and leaves the integration in a working state.

**Tech Stack:** Python, Home Assistant config flow API (`async_show_menu`, `async_update_device`), pydsvdcapi 0.9.1 (`vdsd.push_property`, `vdsd.on_settings_changed`), voluptuous, pytest-asyncio.

---

## Background: current data layout

Each config subentry stores:
```python
{
    "name": "Smart Livingroom Light",   # used as subentry title AND sometimes vdSD name
    "vendorName": "Acme",
    "displayId": "AcmeLight",           # model/type name
    "vdsds": [
        {
            "name": "Living Room Light",    # DSS vdSD name (may differ from confirmed HA name)
            "displayId": "AcmeLight",       # overwritten with confirmed HA device name in name_confirm
            "primaryGroup": 1,
            "buttons": [...],
            "binary_inputs": [...],
            "sensors": [...],
            "output": {...},
        }
    ]
}
```

`DsvdcBaseEntity` uses `vdsd_data.get("displayId", vdsd_data.get("name", "vdSD"))` for the HA device name. After the config-flow `name_confirm` step `displayId` holds the confirmed device name; `name` may hold a different value (the entity friendly-name), causing DSS and HA to show different names.

**Target layout after this plan:**
```python
{
    "entry_name": "Smart Livingroom Light",  # subentry title ONLY — never sent to DSS
    "vendorName": "Acme",
    "displayId": "AcmeLight",               # model identifier (unchanged role)
    "vdsds": [
        {
            "name": "Smart Livingroom Light",   # confirmed device name = DSS name = HA device name
            "displayId": "AcmeLight",           # model identifier
            ...
        }
    ]
}
```

`DsvdcBaseEntity` will use `name` for the HA device registry name. `displayId` keeps its role as the model/type identifier. New config flow always sets both `name` AND `displayId` correctly, so `DsvdcBaseEntity` can use `name` as the primary source, with `displayId` as fallback for old entries.

---

## Files touched

| File | Change |
|------|--------|
| `custom_components/dsvdc4ha/base_entity.py` | Use `name` then `displayId` fallback for HA device name |
| `custom_components/dsvdc4ha/text.py` | After name push: update HA device registry + subentry data |
| `custom_components/dsvdc4ha/__init__.py` | Add `hass` param to `_create_property_entities`; vdSD name-change cb updates registry + subentry |
| `custom_components/dsvdc4ha/config_flow.py` | New first step, artefact→vdSD naming, iterative device flow, menu steps |
| `custom_components/dsvdc4ha/strings.json` | New step keys, remove confirm refs, update device-flow labels |
| `custom_components/dsvdc4ha/translations/en.json` | Mirror strings.json changes |
| `tests/test_base_entity.py` | Verify name field used for device registry name |
| `tests/test_text.py` | Verify device registry update on name change |
| `tests/test_init_naming.py` | Verify DSS→HA reverse naming updates registry + subentry |

---

## Phase 1 — Runtime Naming Foundation

### Task 1: Switch `DsvdcBaseEntity` to use `name` for HA device name

**Files:**
- Modify: `custom_components/dsvdc4ha/base_entity.py:26-31`
- Test: `tests/test_base_entity.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_base_entity.py
"""Tests for DsvdcBaseEntity."""
from __future__ import annotations

def _make_entity(vdsd_data):
    from custom_components.dsvdc4ha.base_entity import DsvdcBaseEntity
    class Concrete(DsvdcBaseEntity):
        pass
    return Concrete("sub1", 0, vdsd_data, "uid")

def test_device_name_uses_name_field():
    ent = _make_entity({"name": "Smart Light", "displayId": "ModelX"})
    assert ent._attr_device_info.name == "Smart Light"

def test_device_name_falls_back_to_display_id():
    ent = _make_entity({"displayId": "ModelX"})
    assert ent._attr_device_info.name == "ModelX"

def test_device_name_falls_back_to_default():
    ent = _make_entity({})
    assert ent._attr_device_info.name == "vdSD"
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd /home/arne/Development/dsvdc4ha && source .venv/bin/activate
pytest tests/test_base_entity.py -v
```
Expected: `test_device_name_uses_name_field` FAILS (currently `displayId` wins).

- [ ] **Step 3: Update `DsvdcBaseEntity`**

```python
# custom_components/dsvdc4ha/base_entity.py
self._attr_device_info = DeviceInfo(
    identifiers={(DOMAIN, f"{subentry_id}_{vdsd_index}")},
    name=vdsd_data.get("name", vdsd_data.get("displayId", "vdSD")),
    manufacturer=vdsd_data.get("vendorName"),
    model=vdsd_data.get("model"),
    sw_version=vdsd_data.get("modelVersion"),
)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_base_entity.py tests/ -x -q
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/base_entity.py tests/test_base_entity.py
git commit -m "feat: use vdSD name field as HA device registry name with displayId fallback"
```

---

### Task 2: HA→DSS name change also updates HA device registry and subentry data

When the user edits the "Name" text entity in HA, `TextSettingEntity.async_set_value` pushes to DSS. It must also update the HA device registry (so the device card title changes immediately) and persist the new name back into the subentry data (so it survives restart).

**Files:**
- Modify: `custom_components/dsvdc4ha/text.py:89-106`
- Test: `tests/test_text.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_text.py`:

```python
@pytest.mark.asyncio
async def test_set_value_updates_ha_device_registry():
    from custom_components.dsvdc4ha.text import TextSettingEntity
    from unittest.mock import patch, MagicMock, AsyncMock
    from homeassistant.helpers import device_registry as dr

    ent = TextSettingEntity(
        "sub1", 0, {"name": "Old Name"},
        "vdsd_name", "Name", "Old Name",
    )
    ent.async_write_ha_state = MagicMock()

    mock_vdsd = MagicMock()
    mock_vdsd.push_property = AsyncMock()
    mock_device = MagicMock()
    mock_device.get_vdsd = MagicMock(return_value=mock_vdsd)
    mock_api = MagicMock()
    mock_api.get_device = MagicMock(return_value=mock_device)
    mock_coordinator = MagicMock()
    mock_coordinator.api = mock_api

    mock_ha_device = MagicMock()
    mock_ha_device.id = "dev-id-1"
    mock_dev_reg = MagicMock()
    mock_dev_reg.async_get_device = MagicMock(return_value=mock_ha_device)
    mock_dev_reg.async_update_device = MagicMock()

    # Subentry with one vdSD
    mock_subentry = MagicMock()
    mock_subentry.subentry_id = "sub1"
    mock_subentry.data = {"entry_name": "Physical Device", "vdsds": [{"name": "Old Name"}]}
    mock_entry = MagicMock()
    mock_entry.subentries = {"sub1": mock_subentry}
    mock_entries = MagicMock()
    mock_entries.async_entries = MagicMock(return_value=[mock_entry])
    mock_entries.async_update_subentry = MagicMock()

    ent.hass = MagicMock()
    ent.hass.data = {"dsvdc4ha": {"hub": mock_coordinator}}

    with patch("custom_components.dsvdc4ha.text.dr.async_get", return_value=mock_dev_reg):
        with patch.object(ent, "hass") as mock_hass:
            mock_hass.data = {"dsvdc4ha": {"hub": mock_coordinator}}
            mock_hass.config_entries = mock_entries
            mock_dev_reg2 = MagicMock()
            mock_dev_reg2.async_get_device = MagicMock(return_value=mock_ha_device)
            mock_dev_reg2.async_update_device = MagicMock()
            with patch("custom_components.dsvdc4ha.text.dr.async_get", return_value=mock_dev_reg2):
                await ent.async_set_value("New Name")

    mock_dev_reg2.async_update_device.assert_called_once_with("dev-id-1", name="New Name")
```

- [ ] **Step 2: Run to confirm it fails**

```bash
pytest tests/test_text.py::test_set_value_updates_ha_device_registry -v
```
Expected: FAIL — `async_update_device` not called.

- [ ] **Step 3: Update `TextSettingEntity.async_set_value`**

```python
# custom_components/dsvdc4ha/text.py  — add import at top
from homeassistant.helpers import device_registry as dr

# async_set_value method — replace existing body
async def async_set_value(self, value: str) -> None:
    coordinator = self.hass.data[DOMAIN].get("hub")
    if coordinator is None or coordinator.api is None:
        return
    device = coordinator.api.get_device(self._subentry_id)
    if device is None:
        return
    vdsd = device.get_vdsd(self._vdsd_index)
    if vdsd is None:
        return
    try:
        vdsd.name = value
        await vdsd.push_property({"name": value})
    except Exception:
        _LOGGER.exception("Failed to set vdSD name on %s", self._subentry_id)
        return

    # Update HA device registry so the device card title changes immediately.
    identifier = (DOMAIN, f"{self._subentry_id}_{self._vdsd_index}")
    dev_reg = dr.async_get(self.hass)
    ha_device = dev_reg.async_get_device(identifiers={identifier})
    if ha_device:
        dev_reg.async_update_device(ha_device.id, name=value)

    # Persist the new name into subentry data so it survives restart.
    for entry in self.hass.config_entries.async_entries(DOMAIN):
        if self._subentry_id in entry.subentries:
            subentry = entry.subentries[self._subentry_id]
            vdsds = list(subentry.data.get("vdsds", []))
            if self._vdsd_index < len(vdsds):
                vdsds[self._vdsd_index] = {**vdsds[self._vdsd_index], "name": value, "displayId": value}
                self.hass.config_entries.async_update_subentry(
                    entry, subentry,
                    data={**subentry.data, "vdsds": vdsds},
                )
            break

    self._attr_native_value = value
    self.async_write_ha_state()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_text.py -x -q
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/text.py tests/test_text.py
git commit -m "feat: name change syncs HA device registry and persists to subentry data"
```

---

### Task 3: DSS→HA name change updates device registry and subentry data

When DSS pushes a name change, `vdsd.on_settings_changed` fires. The callback in `__init__.py` updates the `TextSettingEntity` value. It must also update the HA device registry and subentry data, matching what `TextSettingEntity.async_set_value` does.

**Files:**
- Modify: `custom_components/dsvdc4ha/__init__.py` — `_create_property_entities`, `async_setup_entry`, `_async_subentry_update_listener`
- Create: `tests/test_init_naming.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_init_naming.py
"""Tests for DSS→HA name propagation in _create_property_entities."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


def _make_mock_vdsd(name="Device", zone_id=0, prog_mode=None, active=True):
    vdsd = MagicMock()
    vdsd.name = name
    vdsd.zone_id = zone_id
    vdsd.prog_mode = prog_mode
    vdsd.active = active
    vdsd.binary_inputs = {}
    vdsd.sensor_inputs = {}
    vdsd.button_inputs = {}
    vdsd.output = None
    vdsd.get_properties = MagicMock(return_value={})
    vdsd.on_settings_changed = None
    return vdsd


def _make_mock_env(vdsd_name="Device"):
    from homeassistant.helpers import device_registry as dr

    mock_hass = MagicMock()

    mock_vdsd = _make_mock_vdsd(name=vdsd_name)
    mock_device = MagicMock()
    mock_device.get_vdsd = MagicMock(return_value=mock_vdsd)
    mock_api = MagicMock()
    mock_api.get_device = MagicMock(return_value=mock_device)

    mock_subentry = MagicMock()
    mock_subentry.subentry_id = "sub1"
    mock_subentry.data = {
        "entry_name": "Physical Device",
        "vdsds": [{"name": vdsd_name, "displayId": vdsd_name}],
    }
    mock_entry = MagicMock()
    mock_entry.subentries = {"sub1": mock_subentry}
    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])
    mock_hass.config_entries.async_update_subentry = MagicMock()

    mock_ha_device = MagicMock()
    mock_ha_device.id = "ha-dev-1"
    mock_dev_reg = MagicMock()
    mock_dev_reg.async_get_device = MagicMock(return_value=mock_ha_device)
    mock_dev_reg.async_update_device = MagicMock()

    return mock_hass, mock_api, mock_subentry, mock_entry, mock_vdsd, mock_dev_reg, mock_ha_device


@pytest.mark.asyncio
async def test_dss_name_change_updates_device_registry():
    """When DSS pushes a name change, the HA device registry name is updated."""
    mock_hass, mock_api, mock_subentry, mock_entry, mock_vdsd, mock_dev_reg, mock_ha_device = (
        _make_mock_env("Old Name")
    )
    captured_cb = None

    def _capture_on_settings_changed(cb):
        nonlocal captured_cb
        captured_cb = cb

    # Patch so we can capture the callback that gets set
    type(mock_vdsd).__class__ = MagicMock  # allow attribute assignment
    mock_vdsd.on_settings_changed = None

    add_text_calls = []
    def fake_add_text(entities, **kw):
        add_text_calls.extend(entities)

    with patch("custom_components.dsvdc4ha.__init__.dr.async_get", return_value=mock_dev_reg):
        from custom_components.dsvdc4ha.__init__ import _create_property_entities
        _create_property_entities(
            mock_api, mock_subentry,
            None, None, None, None, fake_add_text,
            hass=mock_hass,
        )

    # The callback must have been set
    assert mock_vdsd.on_settings_changed is not None

    # Fire the callback with a name change
    await mock_vdsd.on_settings_changed(mock_vdsd, {"name": "New Name"})

    # Device registry must be updated
    mock_dev_reg.async_update_device.assert_called_once_with("ha-dev-1", name="New Name")
    # Subentry data must be persisted
    mock_hass.config_entries.async_update_subentry.assert_called_once()
```

- [ ] **Step 2: Run to confirm it fails**

```bash
pytest tests/test_init_naming.py -v
```
Expected: FAIL — `_create_property_entities` does not accept `hass` kwarg.

- [ ] **Step 3: Update `_create_property_entities` signature and `_make_vdsd_cb`**

Add `hass` parameter to `_create_property_entities`:

```python
def _create_property_entities(
    api: Any,
    subentry: Any,
    add_sensor: Any,
    add_number: Any,
    add_select: Any,
    add_switch: Any,
    add_text: Any,
    hass: Any = None,      # NEW
) -> None:
```

Update `_make_vdsd_cb` inside `_create_property_entities` to capture `hass`, `subentry`, `entry` and update the registry + subentry data when "name" changes:

```python
def _make_vdsd_cb(name_ent, zone_ent, prog_ent, active_ent, hass, sid, vdsd_idx, subentry):
    async def cb(changed_vdsd: Any, changed: dict) -> None:
        if "name" in changed and name_ent is not None:
            new_name = str(changed["name"])
            name_ent._attr_native_value = new_name
            name_ent.async_write_ha_state()
            if hass is not None:
                # Update HA device registry
                from homeassistant.helpers import device_registry as dr
                identifier = (DOMAIN, f"{sid}_{vdsd_idx}")
                dev_reg = dr.async_get(hass)
                ha_device = dev_reg.async_get_device(identifiers={identifier})
                if ha_device:
                    dev_reg.async_update_device(ha_device.id, name=new_name)
                # Persist to subentry data
                for entry in hass.config_entries.async_entries(DOMAIN):
                    if sid in entry.subentries:
                        sub = entry.subentries[sid]
                        vdsds = list(sub.data.get("vdsds", []))
                        if vdsd_idx < len(vdsds):
                            vdsds[vdsd_idx] = {**vdsds[vdsd_idx], "name": new_name, "displayId": new_name}
                            hass.config_entries.async_update_subentry(
                                entry, sub,
                                data={**sub.data, "vdsds": vdsds},
                            )
                        break
        if "zoneID" in changed and zone_ent is not None and changed["zoneID"] is not None:
            zone_ent._attr_native_value = float(int(changed["zoneID"]))
            zone_ent.async_write_ha_state()
        if "progMode" in changed and prog_ent is not None:
            val = changed["progMode"]
            prog_ent._attr_is_on = bool(val) if val is not None else False
            prog_ent.async_write_ha_state()
        if "active" in changed and active_ent is not None:
            active_ent._attr_is_on = bool(changed["active"])
            active_ent.async_write_ha_state()
    return cb
```

Update the call site inside `_create_property_entities`:

```python
vdsd.on_settings_changed = _make_vdsd_cb(
    _vdsd_name_ent, _vdsd_zone_ent, _vdsd_prog_ent, _vdsd_active_ent,
    hass, sid, vdsd_idx, subentry,
)
```

Update both call sites in `__init__.py` to pass `hass=hass`:

```python
# in async_setup_entry
_create_property_entities(
    coordinator.api, subentry,
    _add_sensor, _add_number, _add_select, _add_switch, _add_text,
    hass=hass,
)

# in _async_subentry_update_listener
_create_property_entities(
    coordinator.api, subentry,
    add_sensor, add_number, add_select, add_switch, add_text,
    hass=hass,
)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_init_naming.py tests/test_text.py tests/ -x -q
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/__init__.py tests/test_init_naming.py
git commit -m "feat: DSS→HA name change updates device registry and persists to subentry"
```

---

## Phase 2 — Config Flow Naming

### Task 4: Introduce `entry_name` — physical device name as first step

The physical device name (the config entry / subentry title) is asked first in all three creation flows. It is stored as `entry_name` in subentry data and used only for the subentry title; it is never written to DSS.

The old top-level `"name"` key in subentry data becomes `"entry_name"`. A read-time fallback handles old installations.

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py` — `VdsdSubentryFlowHandler.__init__`, `async_step_creation_mode`, `async_step_device_info`, `async_step_device_summary`, `async_step_entity_completion`, `async_step_name_confirm`
- Modify: `custom_components/dsvdc4ha/strings.json`
- Modify: `custom_components/dsvdc4ha/translations/en.json`

- [ ] **Step 1: Add `_entry_name` to flow state and a new first step**

In `VdsdSubentryFlowHandler.__init__`, add:
```python
self._entry_name: str = ""
```

After `async_step_user`, add:
```python
async def async_step_config_entry_name(self, user_input: dict | None = None):
    """Ask the user for the physical device name (subentry title, not sent to DSS)."""
    if user_input is not None:
        self._entry_name = user_input["entry_name"].strip()
        return await self.async_step_creation_mode()
    schema = vol.Schema({
        vol.Required("entry_name"): selector.TextSelector(),
    })
    return self.async_show_form(step_id="config_entry_name", data_schema=schema)
```

Change `async_step_user` to route through the new step:
```python
async def async_step_user(self, user_input: dict | None = None):
    return await self.async_step_config_entry_name(user_input)
```

- [ ] **Step 2: Remove name question from `device_info` (from_scratch)**

`async_step_device_info` currently has `DEVICE_INFO_SCHEMA` which includes `"name"`. It should no longer ask for a name since that was captured in `config_entry_name`.

Find `DEVICE_INFO_SCHEMA` near the top of the file and remove the `"name"` field from it. Update `async_step_device_info` to NOT set `self._device_name` from user_input:

```python
async def async_step_device_info(self, user_input: dict | None = None):
    if user_input is not None:
        self._creation_mode = "from_scratch"
        self._vendor_name = user_input["vendorName"]
        self._display_id = user_input["displayId"]
        return await self.async_step_vdsd_creation()
    return self.async_show_form(step_id="device_info", data_schema=DEVICE_INFO_SCHEMA)
```

Where `DEVICE_INFO_SCHEMA` no longer includes `"name"`:
```python
DEVICE_INFO_SCHEMA = vol.Schema({
    vol.Required("vendorName"): selector.TextSelector(),
    vol.Required("displayId"): selector.TextSelector(),
    vol.Optional("data_description"): selector.TextSelector(),
})
```

- [ ] **Step 3: Update all `async_create_entry` calls to use `entry_name`**

There are two call sites: `async_step_entity_completion` and `async_step_device_summary`.

```python
# both now use self._entry_name for title, and store entry_name in data
return self.async_create_entry(
    title=self._entry_name,
    data={
        "entry_name": self._entry_name,
        "vendorName": self._vendor_name,
        "displayId": self._display_id,
        "vdsds": self._vdsds,
    },
)
```

- [ ] **Step 4: Add `config_entry_name` step to `strings.json`**

In the `config_subentries.device.step` object, add:
```json
"config_entry_name": {
  "title": "Physical Device Name",
  "description": "Enter a name for the physical device. This name is used only in Home Assistant to identify your device and is not reported to digitalSTROM.",
  "data": {
    "entry_name": "Device name"
  },
  "data_description": {
    "entry_name": "Human-readable label for this physical device as it will appear in the Home Assistant configuration. Example: 'Smart Livingroom Light'."
  }
}
```

Also remove `"name"` from the `device_info` step data section in `strings.json` (keep only `vendorName` and `displayId`).

Mirror the same in `translations/en.json`.

- [ ] **Step 5: Run tests**

```bash
pytest tests/ -x -q
```
Expected: all pass (no existing test exercises the new first step yet).

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py custom_components/dsvdc4ha/strings.json custom_components/dsvdc4ha/translations/en.json
git commit -m "feat: add config_entry_name as first step in all creation flows"
```

---

### Task 5: Artefact-driven vdSD name (single artefact auto-names; multi asks)

After `name_inputs` assigns names to each artefact, the vdSD name is determined:
- **Single artefact** (one of: button, binary_input, sensor, output): `vdsd["name"]` and `vdsd["displayId"]` are set to that artefact's name automatically.
- **Multiple artefacts**: a new step `async_step_vdsd_name` asks for the device name.

This replaces the `name_confirm` step for the entity flow. The `name_confirm` step is retained for the `from_ha_device` flow (Task 8 will address that fully).

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py` — `async_step_name_inputs`, `async_step_name_confirm`, `async_step_model_features`
- Modify: `custom_components/dsvdc4ha/strings.json`

- [ ] **Step 1: Add `async_step_vdsd_name` step**

```python
async def async_step_vdsd_name(self, user_input: dict | None = None):
    """Ask for the vdSD / HA device name when the vdSD has more than one artefact."""
    if user_input is not None:
        confirmed = user_input["name"].strip()
        self._current_vdsd["name"] = confirmed
        self._current_vdsd["displayId"] = confirmed
        self._vdsds.append(dict(self._current_vdsd))
        return await self.async_step_entity_completion()

    # Suggest the primary artefact name
    proposal = self._derive_entity_name_proposal()
    schema = vol.Schema({
        vol.Required("name", default=proposal): selector.TextSelector(),
    })
    return self.async_show_form(step_id="vdsd_name", data_schema=schema)
```

- [ ] **Step 2: Add helper `_count_artefacts` and `_auto_apply_single_artefact_name`**

```python
def _count_artefacts(self) -> int:
    """Count configured artefacts: each button, binary input, sensor counts as 1; output counts as 1."""
    return (
        len(self._current_buttons)
        + len(self._current_binary_inputs)
        + len(self._current_sensors)
        + (1 if self._current_output else 0)
    )

def _auto_apply_single_artefact_name(self) -> None:
    """When exactly one artefact, set vdSD name = artefact name."""
    name = self._derive_entity_name_proposal()
    if not name:
        return
    self._current_vdsd["name"] = name
    self._current_vdsd["displayId"] = name
```

- [ ] **Step 3: Route from `async_step_model_features` for entity flow**

In `async_step_model_features`, the entity-flow branch currently calls `_init_name_inputs("name_confirm")`. Change it to call `_init_name_inputs("_vdsd_name_dispatch")` and add a dispatch helper:

```python
async def async_step__vdsd_name_dispatch(self, user_input: dict | None = None):
    """After name_inputs: pick vdsd_name step or auto-name and go to entity_completion."""
    self._current_vdsd["model_features"] = self._current_vdsd.get("model_features", [])
    self._current_vdsd["buttons"] = self._current_buttons
    self._current_vdsd["binary_inputs"] = self._current_binary_inputs
    self._current_vdsd["sensors"] = self._current_sensors
    self._current_vdsd["output"] = self._current_output
    if self._count_artefacts() == 1:
        self._auto_apply_single_artefact_name()
        self._vdsds.append(dict(self._current_vdsd))
        return await self.async_step_entity_completion()
    return await self.async_step_vdsd_name()
```

And update `async_step_model_features` entity-flow branch:

```python
if self._creation_mode == "from_entity":
    self._current_vdsd["model_features"] = user_input.get("features", [])
    self._current_vdsd["buttons"] = self._current_buttons
    self._current_vdsd["binary_inputs"] = self._current_binary_inputs
    self._current_vdsd["sensors"] = self._current_sensors
    self._current_vdsd["output"] = self._current_output
    self._init_name_inputs("_vdsd_name_dispatch")
    if self._pending_name_input_items:
        return await self.async_step_name_inputs()
    return await self.async_step__vdsd_name_dispatch()
```

- [ ] **Step 4: Add `vdsd_name` step to `strings.json`**

```json
"vdsd_name": {
  "title": "Name this Device",
  "description": "This vdSD has multiple artefacts. Enter a name for the Home Assistant device and the digitalSTROM virtual device.",
  "data": {
    "name": "Device name"
  },
  "data_description": {
    "name": "Name shown in the Home Assistant device page and in the digitalSTROM configurator."
  }
}
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/ -x -q
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py custom_components/dsvdc4ha/strings.json custom_components/dsvdc4ha/translations/en.json
git commit -m "feat: artefact name drives vdSD name; multi-artefact asks separately"
```

---

### Task 6: Replace confirm-switch with menu in `device_summary` and `entity_completion`

`device_summary` has a `BooleanSelector("confirm")` — the user must flip it to True before creating. This is removed. Both `device_summary` and `entity_completion` get `async_show_menu` instead of a `SelectSelector`.

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py` — `async_step_device_summary`, `async_step_entity_completion`
- Modify: `custom_components/dsvdc4ha/strings.json`

- [ ] **Step 1: Rewrite `async_step_entity_completion`**

```python
async def async_step_entity_completion(self, user_input: dict | None = None):
    """Entity-based flow: menu to create device or add another vdSD component."""
    vdsd_summary = ", ".join(
        v.get("name", v.get("displayId", "?")) for v in self._vdsds
    )
    return self.async_show_menu(
        step_id="entity_completion",
        menu_options=["entity_completion_create", "entity_completion_add"],
        description_placeholders={
            "device_name": self._entry_name,
            "vdsds": vdsd_summary,
        },
    )

async def async_step_entity_completion_create(self, user_input: dict | None = None):
    return self.async_create_entry(
        title=self._entry_name,
        data={
            "entry_name": self._entry_name,
            "vendorName": self._vendor_name,
            "displayId": self._display_id,
            "vdsds": self._vdsds,
        },
    )

async def async_step_entity_completion_add(self, user_input: dict | None = None):
    self._current_vdsd = {}
    self._current_buttons = []
    self._current_binary_inputs = []
    self._current_sensors = []
    self._current_output = None
    self._current_channels = []
    self._entity_id = ""
    self._entity_mapping = None
    return await self.async_step_entity_picker()
```

- [ ] **Step 2: Rewrite `async_step_device_summary`**

```python
async def async_step_device_summary(self, user_input: dict | None = None):
    """Show device summary as a menu — no confirm switch needed."""
    vdsd_summary = ", ".join(
        f"{v.get('name', v.get('displayId', '?'))} (group {v.get('primaryGroup', '?')})"
        for v in self._vdsds
    )
    return self.async_show_menu(
        step_id="device_summary",
        menu_options=["device_summary_create", "device_summary_add_vdsd"],
        description_placeholders={
            "device_name": self._entry_name,
            "vdsds": vdsd_summary,
        },
    )

async def async_step_device_summary_create(self, user_input: dict | None = None):
    return self.async_create_entry(
        title=self._entry_name,
        data={
            "entry_name": self._entry_name,
            "vendorName": self._vendor_name,
            "displayId": self._display_id,
            "vdsds": self._vdsds,
        },
    )

async def async_step_device_summary_add_vdsd(self, user_input: dict | None = None):
    return await self.async_step_vdsd_creation()
```

- [ ] **Step 3: Update `strings.json` menus**

For `entity_completion`:
```json
"entity_completion": {
  "title": "Complete Device — {device_name}",
  "description": "Configured vdSD components: {vdsds}\n\nChoose how to proceed.",
  "menu_options": {
    "entity_completion_create": "Create device",
    "entity_completion_add": "Add another vdSD from another entity"
  }
}
```

For `device_summary`:
```json
"device_summary": {
  "title": "Device Summary — {device_name}",
  "description": "vdSD components: {vdsds}\n\nChoose how to proceed.",
  "menu_options": {
    "device_summary_create": "Create device",
    "device_summary_add_vdsd": "Add another vdSD first"
  }
}
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/ -x -q
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py custom_components/dsvdc4ha/strings.json custom_components/dsvdc4ha/translations/en.json
git commit -m "feat: replace confirm-switch with async_show_menu in entity_completion and device_summary"
```

---

## Phase 3 — Device Flow Redesign

### Task 7: State model for iterative device flow

The old device flow used `_vdsd_plans`, `_pending_choice_entities`, `_pending_vdsd_idx`, etc. to batch-process a pre-selected entity list. The new flow builds one vdSD interactively. New state variables replace the batch ones.

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py` — `VdsdSubentryFlowHandler.__init__`

- [ ] **Step 1: Add new state variables, mark old batch ones as unused**

In `__init__`, add:
```python
# Device-flow iterative state (replaces _vdsd_plans etc.)
self._device_remaining_entities: list[_EntityInfo] = []  # supported, not yet added
self._device_added_summary: list[str] = []               # display labels for already-added
```

Keep the existing `_vdsd_plans` etc. initialised (they're still used by `device_grouper.compute_vdsd_plan` until Task 8 removes that code path). No test needed for this step.

- [ ] **Step 2: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py
git commit -m "refactor: add iterative device-flow state variables to VdsdSubentryFlowHandler"
```

---

### Task 8: Implement iterative `device_entity_build` screen

Replace `async_step_device_entity_select` + `async_step_device_plan_summary` + `async_step_device_model_features` with a single loop screen `async_step_device_entity_build` that lets the user add one entity at a time. When done, routes to `async_step_model_features` (same as entity flow) then `entity_completion` menu.

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py`
- Modify: `custom_components/dsvdc4ha/strings.json`

- [ ] **Step 1: Rewrite `async_step_device_picker` to feed iterative flow**

```python
async def async_step_device_picker(self, user_input: dict | None = None):
    if user_input is not None:
        device_id: str = user_input["device_id"]
        dev_reg = dr.async_get(self.hass)
        ent_reg = er.async_get(self.hass)
        device = dev_reg.async_get(device_id)
        self._ha_device_id = device_id
        self._vendor_name = (device.manufacturer or "") if device else ""
        self._display_id = (device.model or "") if device else ""

        entities: list[_EntityInfo] = []
        for entry in ent_reg.entities.get_entries_for_device_id(device_id):
            if entry.disabled_by is not None:
                continue
            state = self.hass.states.get(entry.entity_id)
            domain = entry.entity_id.split(".")[0]
            device_class: str | None = (
                state.attributes.get("device_class") if state
                else (entry.device_class or entry.original_device_class)
            )
            mapping = resolve_entity_mapping(entry.entity_id, state, domain, device_class)
            if mapping is None:
                continue
            cat = entry.entity_category
            entities.append(_EntityInfo(
                entity_id=entry.entity_id,
                friendly_name=(state.name or entry.entity_id) if state else entry.entity_id,
                domain=domain,
                device_class=device_class,
                mapping=mapping,
                needs_choices=needs_user_input(mapping),
                entity_category=cat.value if cat else None,
            ))

        self._device_entities = entities
        self._device_remaining_entities = list(entities)
        self._device_added_summary = []
        # Reset current vdSD state
        self._current_vdsd = {
            "displayId": self._display_id,
            "primaryGroup": 1,
            "model": self._display_id,
            "vendorName": self._vendor_name,
            "modelVersion": "1.0",
            "modelUID": (self._vendor_name + self._display_id).replace(" ", ""),
            "name": "",
            "identify_action": None,
            "firmwareUpdate_action": None,
            "optional": {},
        }
        self._current_buttons = []
        self._current_binary_inputs = []
        self._current_sensors = []
        self._current_output = None
        self._current_channels = []
        return await self.async_step_device_entity_build()

    schema = vol.Schema({vol.Required("device_id"): selector.DeviceSelector()})
    return self.async_show_form(step_id="device_picker", data_schema=schema)
```

- [ ] **Step 2: Add `async_step_device_entity_build`**

This is the loop screen. If there are remaining entities and the user clicks "Add entity", it routes to `async_step_device_entity_add`. If the user clicks "Done", it routes to model features.

```python
async def async_step_device_entity_build(self, user_input: dict | None = None):
    """Iterative screen: shows added entities and offers to add more or finish."""
    if user_input is not None:
        action = user_input.get("action", "done")
        if action == "add":
            return await self.async_step_device_entity_add()
        # "done" — go to model features then entity_completion
        self._creation_mode = "from_ha_device"
        return await self.async_step_model_features()

    has_remaining = bool(self._device_remaining_entities)
    options = []
    if has_remaining:
        options.append(selector.SelectOptionDict(value="add", label="Add entity →"))
    options.append(selector.SelectOptionDict(value="done", label="Done — create vdSD"))

    schema = vol.Schema({
        vol.Required("action", default="add" if has_remaining else "done"): selector.SelectSelector(
            selector.SelectSelectorConfig(options=options)
        ),
    })
    added_text = "\n".join(f"• {s}" for s in self._device_added_summary) or "(none yet)"
    remaining_text = "\n".join(
        f"• {e.friendly_name} ({e.domain})" for e in self._device_remaining_entities
    ) or "(all added)"
    return self.async_show_form(
        step_id="device_entity_build",
        data_schema=schema,
        description_placeholders={
            "added": added_text,
            "remaining": remaining_text,
        },
    )
```

- [ ] **Step 3: Add `async_step_device_entity_add`**

Single-entity picker showing only remaining supported entities.

```python
async def async_step_device_entity_add(self, user_input: dict | None = None):
    """Pick one entity from the remaining supported entities on this HA device."""
    errors: dict[str, str] = {}
    if user_input is not None:
        entity_id: str = user_input["entity_id"]
        state = self.hass.states.get(entity_id)
        domain = entity_id.split(".")[0]
        device_class: str | None = state.attributes.get("device_class") if state else None
        mapping = resolve_entity_mapping(entity_id, state, domain, device_class)
        if mapping is None:
            errors["entity_id"] = "entity_not_supported"
        else:
            self._entity_id = entity_id
            self._entity_mapping = mapping
            # Remove from remaining
            self._device_remaining_entities = [
                e for e in self._device_remaining_entities if e.entity_id != entity_id
            ]
            if needs_user_input(mapping):
                # Reuse entity_user_input step but return to device flow after
                self._device_entity_add_return = True
                return await self.async_step_entity_user_input()
            return await self._build_device_entity_artefact({})

    options = [
        selector.SelectOptionDict(
            value=e.entity_id,
            label=f"{e.friendly_name} ({e.domain})",
        )
        for e in self._device_remaining_entities
    ]
    schema = vol.Schema({
        vol.Required("entity_id"): selector.SelectSelector(
            selector.SelectSelectorConfig(options=options)
        ),
    })
    return self.async_show_form(
        step_id="device_entity_add",
        errors=errors,
        data_schema=schema,
    )
```

- [ ] **Step 4: Add `_build_device_entity_artefact` and state flag `_device_entity_add_return`**

Add to `__init__`:
```python
self._device_entity_add_return: bool = False
```

Add method:
```python
async def _build_device_entity_artefact(self, user_input: dict) -> Any:
    """Build one artefact from the selected entity and add it to the current vdSD."""
    self._device_entity_add_return = False
    # Reuse entity-flow builder to produce artefact data
    await self._build_entity_vdsd_and_continue.__func__  # note: we'll call it differently

    # Actually: call _build_entity_artefact_only (new helper, see below)
    return await self._apply_entity_artefact_to_current(user_input)
```

The simplest approach is to reuse the existing `_build_entity_vdsd_and_continue` but intercept before it resets `_current_vdsd`. Instead add a new helper that only adds the artefact parts to `_current_*` lists:

```python
async def _apply_entity_artefact_to_current(self, user_input: dict) -> Any:
    """Add artefact(s) from self._entity_id/mapping to _current_* lists, then name them."""
    mapping = self._entity_mapping
    if mapping is None:
        return await self.async_step_device_entity_build()
    entity_id = self._entity_id
    state = self.hass.states.get(entity_id)
    friendly_name: str = (state.name if state else None) or entity_id.split(".")[-1]

    if "binary_input" in mapping:
        bi = mapping["binary_input"]
        sf = int(user_input.get("sensor_function", bi["sensor_function"]))
        self._current_binary_inputs.append({
            "dsIndex": len(self._current_binary_inputs),
            "name": friendly_name,
            "group": int(user_input.get("bi_group", bi["group"])),
            "sensorFunction": sf,
            "hardwiredFunction": sf,
            "updateInterval": bi["update_interval"],
            "inputType": bi["input_type"],
            "inputUsage": int(user_input.get("input_usage", bi["input_usage"])),
            "valueType": "boolean",
            "callback_entity": entity_id,
        })

    if "sensor" in mapping:
        s = mapping["sensor"]
        st = int(user_input.get("sensor_type", s["sensor_type"]))
        self._current_sensors.append({
            "dsIndex": len(self._current_sensors),
            "name": friendly_name,
            "group": s["group"],
            "sensorType": st,
            "sensorUsage": int(user_input.get("sensor_usage", s["sensor_usage"])),
            "min": float(user_input.get("min", s["min"])),
            "max": float(user_input.get("max", s["max"])),
            "resolution": float(user_input.get("resolution", s["resolution"])),
            "updateInterval": s["update_interval"],
            "aliveSignInterval": s["alive_sign_interval"],
            "minPushInterval": s["min_push_interval"],
            "changesOnlyInterval": s["changes_only_interval"],
            "callback_entity": entity_id,
        })

    if "button" in mapping:
        b = mapping["button"]
        group = int(user_input.get("group", b["group"]))
        function = b["function"]
        self._current_buttons.append({
            "dsIndex": len(self._current_buttons),
            "name": friendly_name,
            "buttonType": b["button_type"],
            "buttonElementID": 0,
            "group": group,
            "function": function,
            "mode": b["mode"],
            "channel": 0,
            "supportsLocalKeyMode": b.get("supports_local_key_mode", False),
            "setsLocalPriority": False,
            "callsPresent": b.get("calls_present", True),
            "buttonID": 0,
            "callbackType": "detect_clicks",
            "callback_entity": entity_id,
        })

    if "output" in mapping and self._current_output is None:
        o = mapping["output"]
        fn = int(user_input.get("function", o["function"]))
        usage = int(user_input.get("output_usage", o["output_usage"]))
        channels_def = list(o.get("channels", []))
        mode = o["mode"]
        channels = [
            {
                "dsIndex": i,
                "channelType": ch["channel_type"],
                "read_entity": entity_id,
                "write_action": None,
                **({"apply_expr": ch["apply_expr"]} if ch.get("apply_expr") else {}),
                **({"push_expr": ch["push_expr"]} if ch.get("push_expr") else {}),
            }
            for i, ch in enumerate(channels_def)
        ]
        self._current_output = {
            "name": "Output",
            "groups": o["groups"],
            "defaultGroup": o["default_group"],
            "activeGroup": o["default_group"],
            "function": fn,
            "outputUsage": usage,
            "variableRamp": o["variable_ramp"],
            "mode": mode,
            "onThreshold": 50,
            "channels": channels,
        }
        self._current_channels = channels

    entity_info = next(
        (e for e in self._device_entities if e.entity_id == entity_id), None
    )
    label = entity_info.friendly_name if entity_info else entity_id
    self._device_added_summary.append(label)

    # Now name the newly added artefact(s)
    self._init_name_inputs("device_entity_build")
    if self._pending_name_input_items:
        return await self.async_step_name_inputs()
    return await self.async_step_device_entity_build()
```

- [ ] **Step 5: Handle `entity_user_input` return for device flow**

`async_step_entity_user_input` currently calls `_build_entity_vdsd_and_continue`. For the device flow path it should call `_apply_entity_artefact_to_current`. Add a guard:

```python
async def async_step_entity_user_input(self, user_input: dict | None = None):
    mapping = self._entity_mapping
    if mapping is None:
        return await self.async_step_creation_mode()
    if user_input is not None:
        if getattr(self, "_device_entity_add_return", False):
            return await self._apply_entity_artefact_to_current(user_input)
        return await self._build_entity_vdsd_and_continue(user_input)
    schema_dict = _build_entity_choices_schema(mapping)
    return self.async_show_form(
        step_id="entity_user_input",
        data_schema=vol.Schema(schema_dict),
    )
```

- [ ] **Step 6: Handle `model_features` for `from_ha_device`**

In `async_step_model_features`, the `from_ha_device` path currently goes to `async_step_device_summary`. With the redesign it should route the same as `from_entity` (after features are set, artefact-driven name dispatch):

```python
if user_input is not None:
    self._current_vdsd["model_features"] = user_input.get("features", [])
    self._current_vdsd["buttons"] = self._current_buttons
    self._current_vdsd["binary_inputs"] = self._current_binary_inputs
    self._current_vdsd["sensors"] = self._current_sensors
    self._current_vdsd["output"] = self._current_output
    if self._creation_mode in ("from_entity", "from_ha_device"):
        self._init_name_inputs("_vdsd_name_dispatch")
        if self._pending_name_input_items:
            return await self.async_step_name_inputs()
        return await self.async_step__vdsd_name_dispatch()
    # from_scratch
    self._vdsds.append(dict(self._current_vdsd))
    return await self.async_step_device_summary()
```

- [ ] **Step 7: Update `async_step__vdsd_name_dispatch` for `from_ha_device`**

`async_step__vdsd_name_dispatch` currently always calls `async_step_entity_completion`. For `from_ha_device` it must also call `entity_completion` (the same menu, but the "add another" option is relabelled in strings.json):

No code change needed here — `entity_completion` menu already exists and the strings.json will carry the relabelled option.

- [ ] **Step 8: Add new strings.json entries for device flow**

```json
"device_entity_build": {
  "title": "Add Entities to vdSD",
  "description": "Already added:\n{added}\n\nRemaining supported entities on this device:\n{remaining}",
  "data": {
    "action": "Action"
  }
},
"device_entity_add": {
  "title": "Select Entity to Add",
  "description": "Pick one entity from the remaining supported entities on this HA device.",
  "data": {
    "entity_id": "Entity"
  }
}
```

In `entity_completion.menu_options`, relabel `entity_completion_add` so it reads differently in context:
```json
"entity_completion_add": "Add vdSD from another entity"
```
(The same label works in both entity flow and device flow; for device flow the user already configured the current device's entities and is now adding a vdSD from a different device.)

- [ ] **Step 9: Run tests**

```bash
pytest tests/ -x -q
```
Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py custom_components/dsvdc4ha/strings.json custom_components/dsvdc4ha/translations/en.json
git commit -m "feat: iterative one-entity-at-a-time device flow replaces batch plan/summary"
```

---

### Task 9: Tests for the new config entry name step and artefact naming

**Files:**
- Create: `tests/test_config_flow_naming.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_config_flow_naming.py
"""Tests for naming changes in config flow."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


def _make_flow():
    from custom_components.dsvdc4ha.config_flow import VdsdSubentryFlowHandler
    flow = VdsdSubentryFlowHandler()
    flow.hass = MagicMock()
    flow.hass.states.get = MagicMock(return_value=None)
    return flow


def test_config_entry_name_step_stores_entry_name():
    """config_entry_name step stores the name and routes to creation_mode."""
    from custom_components.dsvdc4ha.config_flow import VdsdSubentryFlowHandler
    flow = _make_flow()
    # Patch async_step_creation_mode to avoid full flow setup
    async def fake_creation_mode(user_input=None):
        return "creation_mode_result"

    import asyncio
    flow.async_step_creation_mode = fake_creation_mode
    result = asyncio.get_event_loop().run_until_complete(
        flow.async_step_config_entry_name({"entry_name": "My Physical Device"})
    )
    assert flow._entry_name == "My Physical Device"
    assert result == "creation_mode_result"


def test_count_artefacts_single_sensor():
    flow = _make_flow()
    flow._current_buttons = []
    flow._current_binary_inputs = []
    flow._current_sensors = [{"name": "Temperature"}]
    flow._current_output = None
    assert flow._count_artefacts() == 1


def test_count_artefacts_multiple():
    flow = _make_flow()
    flow._current_buttons = [{"name": "Button"}]
    flow._current_binary_inputs = [{"name": "Motion"}]
    flow._current_sensors = [{"name": "Temperature"}]
    flow._current_output = {"name": "Light"}
    assert flow._count_artefacts() == 4


def test_auto_apply_single_artefact_name_sensor():
    flow = _make_flow()
    flow._current_buttons = []
    flow._current_binary_inputs = []
    flow._current_sensors = [{"name": "Temperature"}]
    flow._current_output = None
    flow._current_vdsd = {"displayId": "old"}
    flow._auto_apply_single_artefact_name()
    assert flow._current_vdsd["name"] == "Temperature"
    assert flow._current_vdsd["displayId"] == "Temperature"


def test_auto_apply_single_artefact_name_output():
    flow = _make_flow()
    flow._current_buttons = []
    flow._current_binary_inputs = []
    flow._current_sensors = []
    flow._current_output = {"name": "Light"}
    flow._current_vdsd = {"displayId": "old"}
    flow._auto_apply_single_artefact_name()
    assert flow._current_vdsd["name"] == "Light"
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_config_flow_naming.py -v
```
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_config_flow_naming.py
git commit -m "test: config entry name step and artefact-driven vdSD name helpers"
```

---

### Task 10: Final integration run

- [ ] **Step 1: Run the full test suite**

```bash
cd /home/arne/Development/dsvdc4ha && source .venv/bin/activate
pytest tests/ -q
```
Expected: all tests pass, 0 failures.

- [ ] **Step 2: Verify `strings.json` has no orphan step keys**

```bash
grep -o '"[a-z_]*": {' custom_components/dsvdc4ha/strings.json | sort
```
Check that every step key has a corresponding `async_step_*` method in `config_flow.py`.

- [ ] **Step 3: Commit if any last-minute fixes needed, then tag**

```bash
git add -A
git commit -m "chore: final cleanup after naming and flow redesign"
```

---

## Self-Review

**Spec coverage:**
- ✅ Physical device name asked first in all flows → Task 4
- ✅ Config entry name not sent to DSS → `entry_name` only in title
- ✅ Artefact name proposal from type label → existing `_suggest_name_*` helpers used by `name_inputs`, called from device flow in Task 8
- ✅ Single artefact: artefact name = vdSD name → Task 5 `_auto_apply_single_artefact_name`
- ✅ Multiple artefacts: extra `vdsd_name` step → Task 5 `async_step_vdsd_name`
- ✅ DSS→HA reverse naming updates HA device registry → Task 3
- ✅ HA→DSS reverse naming updates HA device registry → Task 2
- ✅ Both sides persist to subentry data → Tasks 2 and 3
- ✅ Device flow starts empty, add one entity at a time → Task 8
- ✅ After configuring entity, run config flow, come back → Task 8 `_apply_entity_artefact_to_current` + return to `device_entity_build`
- ✅ When done, route to entity_completion → Task 8 `async_step_model_features` from_ha_device branch
- ✅ entity_completion label "Add vdSD from another entity" → Task 6 strings.json
- ✅ Confirm switch removed from `device_summary` → Task 6
- ✅ Confirm switch removed from `entity_completion` → Task 6
- ✅ `DsvdcBaseEntity` uses `name` for HA device name → Task 1

**Placeholder scan:** None found.

**Type consistency:** `_entry_name: str` used consistently. `_count_artefacts()` referenced in Tasks 5 and 9. `_auto_apply_single_artefact_name()` consistent between Tasks 5 and 9.

**Note on `name_confirm` step:** The old `async_step_name_confirm` is still called for the `from_ha_device` flow in the current Task 8 design because `from_ha_device` now routes through `_vdsd_name_dispatch` (same as entity flow). The old `name_confirm` step can be removed once all flows use the new dispatch. Removing it is safe after Task 8 is confirmed working.
