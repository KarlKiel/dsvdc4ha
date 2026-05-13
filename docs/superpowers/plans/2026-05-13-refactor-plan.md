# dsvdc4ha Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all critical, high, and medium issues identified in `docs/superpowers/specs/2026-05-13-refactor-findings.md`, restoring correct runtime behaviour and test-suite stability.

**Architecture:** Move the "Create from entity" flow from `DsvdcConfigFlow` to `VdsdSubentryFlowHandler` so the hub flow handles only hub setup and the subentry flow handles all device creation (both paths). Fix constants, invalid mapping data, string/schema mismatches, and deprecated API usage.

**Tech Stack:** Python 3.12, Home Assistant 2025.x, pytest

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `custom_components/dsvdc4ha/const.py` | Modify | Add missing `CONF_ENTRY_TYPE`, `ENTRY_TYPE_HUB` |
| `custom_components/dsvdc4ha/config_flow.py` | Modify | Fix duplicate step_user; move entity flow from DsvdcConfigFlow to VdsdSubentryFlowHandler; fix deprecated API |
| `custom_components/dsvdc4ha/entity_mapping.py` | Modify | Fix invalid `input_usage: 4`; fix `displayId` assignment |
| `custom_components/dsvdc4ha/strings.json` | Modify | Add `config_subentries` section; fix optional_settings fields; add channel action label |
| `custom_components/dsvdc4ha/translations/en.json` | Modify | Remove duplicate `state_files`; move entity steps to subentry section; add channel action label |
| `tests/test_config_flow.py` | Modify | Verify tests pass with corrected routing |

---

## Phase 1 — Constants and Mapping Data

### Task 1: Add missing constants to `const.py` and fix `entity_mapping.py`

**Files:**
- Modify: `custom_components/dsvdc4ha/const.py`
- Modify: `custom_components/dsvdc4ha/entity_mapping.py`

- [ ] **Step 1: Add `CONF_ENTRY_TYPE`, `ENTRY_TYPE_HUB` to `const.py`**

Open [custom_components/dsvdc4ha/const.py](../../custom_components/dsvdc4ha/const.py) and add after `CONF_PORT`:

```python
CONF_ENTRY_TYPE = "entry_type"
ENTRY_TYPE_HUB = "hub"
ENTRY_TYPE_DEVICE = "device"
```

- [ ] **Step 2: Fix invalid `input_usage` values in `entity_mapping.py`**

Open [custom_components/dsvdc4ha/entity_mapping.py](../../custom_components/dsvdc4ha/entity_mapping.py).

Line 198 (`binary_sensor/problem`): change `"input_usage": 4` → `"input_usage": 0`
Line 205 (`binary_sensor/running`): change `"input_usage": 4` → `"input_usage": 0`

```python
# binary_sensor/problem — was: "input_usage": 4
"binary_input": {
    "sensor_function": 22, "group": 8, "input_usage": 0,
    "input_type": 1, "update_interval": 1.0,
},

# binary_sensor/running — was: "input_usage": 4
"binary_input": {
    "sensor_function": 0, "group": 8, "input_usage": 0,
    "input_type": 1, "update_interval": 1.0,
},
```

- [ ] **Step 3: Run tests to verify no regressions**

```bash
cd /home/arne/Development/dsvdc4ha && source .venv/bin/activate && pytest tests/ -v 2>&1 | tail -30
```

Expected: all previously-passing tests still pass (some may still fail due to issues fixed in later tasks — that is expected at this stage).

- [ ] **Step 4: Commit**

```bash
git add custom_components/dsvdc4ha/const.py custom_components/dsvdc4ha/entity_mapping.py
git commit -m "fix: add missing CONF_ENTRY_TYPE/ENTRY_TYPE_HUB constants; fix invalid input_usage values"
```

---

## Phase 2 — Config Flow Architecture

### Task 2: Move entity flow from `DsvdcConfigFlow` to `VdsdSubentryFlowHandler`

This is the core fix. The entity creation steps (`creation_mode`, `entity_picker`, `entity_user_input`, `_build_entity_vdsd_and_continue`, `entity_channel_mapping`) and all associated state variables must move from `DsvdcConfigFlow` to `VdsdSubentryFlowHandler`.

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py`

**Strategy:**
1. Strip `DsvdcConfigFlow` down to hub-only steps
2. Extend `VdsdSubentryFlowHandler` with `creation_mode` as the new entry point and the full entity flow

#### Part A: Clean up `DsvdcConfigFlow`

- [ ] **Step 1: Fix the import block in `config_flow.py`**

At the top of config_flow.py, change:
```python
from .const import (
    CONF_PORT,
    DOMAIN,
)
```
to:
```python
from .const import (
    CONF_ENTRY_TYPE,
    CONF_PORT,
    DOMAIN,
    ENTRY_TYPE_HUB,
)
```

Also remove `SubentryFlowResult` from the homeassistant import (it is unused):
```python
# Before:
from homeassistant.config_entries import ConfigSubentryFlow, SubentryFlowResult
# After:
from homeassistant.config_entries import ConfigSubentryFlow
```

- [ ] **Step 2: Remove entity-flow state variables from `DsvdcConfigFlow.__init__`**

Remove from `DsvdcConfigFlow.__init__` (these belong only on `VdsdSubentryFlowHandler`):
```python
# REMOVE these lines:
self._device_name: str = ""
self._vendor_name: str = ""
self._display_id: str = ""
self._vdsds: list[dict[str, Any]] = []
self._current_vdsd: dict[str, Any] = {}
self._current_buttons: list[dict[str, Any]] = []
self._current_binary_inputs: list[dict[str, Any]] = []
self._current_sensors: list[dict[str, Any]] = []
self._current_output: dict[str, Any] | None = None
self._current_channels: list[dict[str, Any]] = []
self._current_button_element_idx: int = 0
self._current_button_elements_total: int = 1
self._current_button_type: int = 1
self._optional_return_step: str = ""
self._entity_id: str = ""
self._entity_mapping: dict[str, Any] | None = None
```

Keep only hub-flow state:
```python
def __init__(self) -> None:
    self._pending_port: int = 0
    self._temp_coordinator: Any = None
    self._dss_connected: bool | None = None
    self._dss_wait_task: asyncio.Task | None = None
```

- [ ] **Step 3: Replace both `async_step_user` definitions with one correct one**

Remove the current two definitions (lines 658–669) and replace with a single definition:

```python
async def async_step_user(self, user_input: dict | None = None):
    """Route to hub setup; abort if already configured."""
    existing = [
        e for e in self._async_current_entries()
        if e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_HUB
    ]
    if existing:
        return self.async_abort(reason="already_configured")
    return await self.async_step_hub(user_input)
```

- [ ] **Step 4: Fix `async_step_finalize_hub` to store `CONF_ENTRY_TYPE` in entry data**

Change:
```python
return self.async_create_entry(
    title="dSVDC Hub",
    data={CONF_PORT: self._pending_port},
)
```
to:
```python
return self.async_create_entry(
    title="dSVDC Hub",
    data={CONF_ENTRY_TYPE: ENTRY_TYPE_HUB, CONF_PORT: self._pending_port},
)
```

- [ ] **Step 5: Remove entity flow methods from `DsvdcConfigFlow`**

Delete the following methods entirely from `DsvdcConfigFlow` (lines 780–1108):
- `async_step_creation_mode`
- `async_step_entity_picker`
- `async_step_entity_user_input`
- `_build_entity_vdsd_and_continue`
- `async_step_entity_channel_mapping`

The class should end with `async_get_supported_subentry_types` (which stays).

- [ ] **Step 6: Replace deprecated `asyncio.get_event_loop()` calls**

In `async_step_hub`:
```python
# Before:
available = await asyncio.get_event_loop().run_in_executor(
    None, _port_is_available, port
)
# After:
available = await self.hass.async_add_executor_job(_port_is_available, port)
```

In `async_step_state_files`:
```python
# Before:
existing = await asyncio.get_event_loop().run_in_executor(
    None, _existing_state_files, state_path
)
# After:
existing = await self.hass.async_add_executor_job(_existing_state_files, state_path)
```

#### Part B: Extend `VdsdSubentryFlowHandler`

- [ ] **Step 7: Add entity-flow imports to `VdsdSubentryFlowHandler`**

The `VdsdSubentryFlowHandler` needs access to `SUPPORTED_DOMAINS`, `get_entity_mapping`, `needs_user_input`. These are already imported at the top of `config_flow.py` via `from .entity_mapping import ...`, so no change to the import block is needed.

- [ ] **Step 8: Add entity-flow state variables to `VdsdSubentryFlowHandler.__init__`**

```python
def __init__(self) -> None:
    # ... existing variables unchanged ...
    self._device_name: str = ""
    self._vendor_name: str = ""
    self._display_id: str = ""
    self._vdsds: list[dict[str, Any]] = []
    self._current_vdsd: dict[str, Any] = {}
    self._current_buttons: list[dict[str, Any]] = []
    self._current_binary_inputs: list[dict[str, Any]] = []
    self._current_sensors: list[dict[str, Any]] = []
    self._current_output: dict[str, Any] | None = None
    self._current_channels: list[dict[str, Any]] = []
    self._current_button_element_idx: int = 0
    self._current_button_elements_total: int = 1
    self._current_button_type: int = 1
    self._optional_return_step: str = ""
    # Entity-flow state (new)
    self._entity_id: str = ""
    self._entity_mapping: dict[str, Any] | None = None
```

(The non-entity variables are already present; add only `_entity_id` and `_entity_mapping`.)

- [ ] **Step 9: Change `VdsdSubentryFlowHandler.async_step_user` to route through `creation_mode`**

Change:
```python
async def async_step_user(self, user_input: dict | None = None):
    return await self.async_step_device_info(user_input)
```
to:
```python
async def async_step_user(self, user_input: dict | None = None):
    return await self.async_step_creation_mode(user_input)
```

- [ ] **Step 10: Add `async_step_creation_mode` to `VdsdSubentryFlowHandler`**

Insert before `async_step_device_info`:

```python
async def async_step_creation_mode(self, user_input: dict | None = None):
    """Choose between creating a vdSD from an existing HA entity or from scratch."""
    if user_input is not None:
        mode = user_input.get("mode", "from_scratch")
        if mode == "from_entity":
            return await self.async_step_entity_picker()
        return await self.async_step_device_info()
    schema = vol.Schema({
        vol.Required("mode", default="from_entity"): selector.SelectSelector(
            selector.SelectSelectorConfig(options=[
                selector.SelectOptionDict(value="from_entity", label="Create from entity"),
                selector.SelectOptionDict(value="from_scratch", label="Create from scratch"),
            ])
        ),
    })
    return self.async_show_form(step_id="creation_mode", data_schema=schema)
```

- [ ] **Step 11: Add `async_step_entity_picker` to `VdsdSubentryFlowHandler`**

Copy the method verbatim from the removed `DsvdcConfigFlow` version. No changes needed — it references `self._entity_id`, `self._entity_mapping`, `self._device_name`, `self._vendor_name`, `self._display_id` which now all exist on `VdsdSubentryFlowHandler`.

```python
async def async_step_entity_picker(self, user_input: dict | None = None):
    """Select the HA entity to derive a vdSD from."""
    errors: dict[str, str] = {}
    if user_input is not None:
        entity_id: str = user_input["entity_id"]
        state = self.hass.states.get(entity_id)
        if state is None:
            errors["entity_id"] = "entity_not_found"
        else:
            domain = entity_id.split(".")[0]
            device_class: str | None = state.attributes.get("device_class")
            mapping = get_entity_mapping(domain, device_class)
            if mapping is None:
                errors["entity_id"] = "entity_not_supported"
            else:
                self._entity_id = entity_id
                self._entity_mapping = mapping
                friendly_name: str = state.name or entity_id
                manufacturer: str = ""
                model: str = ""
                try:
                    from homeassistant.helpers import entity_registry as er, device_registry as dr
                    ent_reg = er.async_get(self.hass)
                    dev_reg = dr.async_get(self.hass)
                    entry = ent_reg.async_get(entity_id)
                    if entry and entry.device_id:
                        device = dev_reg.async_get(entry.device_id)
                        if device:
                            friendly_name = device.name_by_user or device.name or friendly_name
                            manufacturer = device.manufacturer or ""
                            model = device.model or ""
                except Exception:
                    pass
                self._device_name = friendly_name
                self._vendor_name = manufacturer
                self._display_id = model or domain.title()
                if needs_user_input(mapping):
                    return await self.async_step_entity_user_input()
                return await self._build_entity_vdsd_and_continue({})

    schema = vol.Schema({
        vol.Required("entity_id"): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=SUPPORTED_DOMAINS)
        ),
    })
    return self.async_show_form(
        step_id="entity_picker",
        data_schema=schema,
        errors=errors,
    )
```

- [ ] **Step 12: Add `async_step_entity_user_input` to `VdsdSubentryFlowHandler`**

Copy verbatim from the removed `DsvdcConfigFlow` version. Change the fallback in the guard at the top:

```python
async def async_step_entity_user_input(self, user_input: dict | None = None):
    """Collect the extra choices required by this entity's mapping."""
    mapping = self._entity_mapping
    if mapping is None:
        return await self.async_step_creation_mode()   # was async_step_creation_mode — same name
    # ... rest unchanged ...
```

- [ ] **Step 13: Add `_build_entity_vdsd_and_continue` to `VdsdSubentryFlowHandler` with displayId fix**

Copy verbatim from the removed version, fixing the `displayId` bug (H2):

```python
async def _build_entity_vdsd_and_continue(self, user_input: dict) -> Any:
    mapping = self._entity_mapping
    assert mapping is not None
    entity_id = self._entity_id
    state = self.hass.states.get(entity_id)
    friendly_name: str = (state.name if state else None) or entity_id

    pg = mapping["primary_group"]
    vdsd: dict[str, Any] = {
        "displayId": self._display_id,      # FIX: was friendly_name — displayId is the model name
        "primaryGroup": pg,
        "model": self._display_id,          # FIX: same — model should be the type name
        "vendorName": self._vendor_name,
        "modelVersion": "1.0",
        "modelUID": (self._vendor_name + self._display_id).replace(" ", ""),
        "name": self._device_name,          # friendly name goes in "name"
        "active": True,
        "identify_action": None,
        "firmwareUpdate_action": None,
        "optional": {},
        "buttons": [],
        "binary_inputs": [],
        "sensors": [],
        "output": None,
    }
    # ... remainder of method unchanged ...
```

- [ ] **Step 14: Add `async_step_entity_channel_mapping` to `VdsdSubentryFlowHandler`**

Copy verbatim from the removed version. No changes needed.

- [ ] **Step 15: Run tests**

```bash
cd /home/arne/Development/dsvdc4ha && source .venv/bin/activate && pytest tests/ -v 2>&1 | tail -30
```

Expected: all tests pass.

- [ ] **Step 16: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py
git commit -m "refactor: move entity creation flow from DsvdcConfigFlow to VdsdSubentryFlowHandler"
```

---

## Phase 3 — Fix Device Wizard Navigation

### Task 3: Make `output_optional` reachable and fix its navigation

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py`

- [ ] **Step 1: Add "Output options…" action to `async_step_output` schema**

In `VdsdSubentryFlowHandler.async_step_output`, add `output_optional` as an action before writing channels. The simplest approach is a standalone action option that appears at form-show time (similar to how `vdsd_overview` has an `optional_settings` action):

Change `async_step_output` to accept an `action` field:

```python
async def async_step_output(self, user_input: dict | None = None):
    """Collect output configuration."""
    if user_input is not None:
        action = user_input.pop("action", "next")
        if action == "output_optional":
            # Save partial state so optional can return here
            self._current_output = {
                "name": user_input.get("name", "Output"),
                "groups": [int(g) for g in user_input.get("groups", ["1"])],
                "defaultGroup": int(user_input.get("defaultGroup", 1)),
                "activeGroup": int(user_input.get("defaultGroup", 1)),
                "function": int(user_input.get("function", 0)),
                "outputUsage": int(user_input.get("outputUsage", 0)),
                "variableRamp": bool(user_input.get("variableRamp", False)),
                "mode": int(user_input.get("mode", 127)),
                "onThreshold": 50,
            }
            return await self.async_step_output_optional()
        # ... existing submit logic (unchanged) ...
    schema = vol.Schema({
        # ... existing fields unchanged ...
        vol.Required("action", default="next"): selector.SelectSelector(
            selector.SelectSelectorConfig(options=[
                selector.SelectOptionDict(value="next", label="Continue"),
                selector.SelectOptionDict(value="output_optional", label="Optional output settings…"),
            ])
        ),
    })
    return self.async_show_form(step_id="output", data_schema=schema)
```

- [ ] **Step 2: Fix `async_step_output_optional` return navigation**

The submit handler currently returns to `async_step_output()` (re-shows the output form). After setting optional fields, the user has already configured the output — they should advance. Change to return to `async_step_channel_mapping` (or `async_step_channel` for manual functions):

```python
async def async_step_output_optional(self, user_input: dict | None = None):
    """Collect optional output settings."""
    if user_input is not None:
        if self._current_output:
            for k, v in user_input.items():
                if v is not None and v != "":
                    self._current_output[k] = v
        # Advance: if manual channel function, go to channel; else channel_mapping
        fn = self._current_output.get("function", 0) if self._current_output else 0
        if fn in _MANUAL_CHANNEL_FUNCTIONS:
            return await self.async_step_channel()
        for i, ct in enumerate(FUNCTION_CHANNELS.get(OutputFunction(fn), [])):
            self._current_channels.append({
                "dsIndex": i,
                "channelType": int(ct),
                "name": _CHANNEL_TYPE_LABELS.get(int(ct), f"Channel {i}"),
                "min": 0.0, "max": 100.0, "resolution": 0.4,
            })
        return await self.async_step_channel_mapping()
    # schema unchanged
```

- [ ] **Step 3: Add `action` label to `strings.json` and `en.json` for output step**

See Task 4 for all string changes together.

- [ ] **Step 4: Run tests**

```bash
cd /home/arne/Development/dsvdc4ha && source .venv/bin/activate && pytest tests/ -v 2>&1 | tail -30
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py
git commit -m "fix: make output_optional step reachable and fix its return navigation"
```

---

## Phase 4 — Fix UI Strings

### Task 4: Fix `strings.json` and `en.json` to match code reality

**Files:**
- Modify: `custom_components/dsvdc4ha/strings.json`
- Modify: `custom_components/dsvdc4ha/translations/en.json`

- [ ] **Step 1: Add `config_subentries` section to `strings.json`**

`strings.json` needs a `config_subentries.device` block matching what `en.json` already has. Append after the closing `}` of the `"config"` block:

```json
"config_subentries": {
  "device": {
    "initiate_flow": {
      "user": "Add Device"
    },
    "entry": "{title}",
    "step": {
      "creation_mode": {
        "title": "Create Device",
        "description": "How would you like to create the virtual device (vdSD)?",
        "data": {
          "mode": "Creation method"
        }
      },
      "entity_picker": {
        "title": "Select Entity",
        "description": "Choose the Home Assistant entity you want to expose to digitalStrom. Only entities with a supported type are shown.",
        "data": {
          "entity_id": "Entity"
        }
      },
      "entity_user_input": {
        "title": "Additional Configuration",
        "description": "Some settings for this entity type require your input.",
        "data": {
          "sensor_function": "Binary input function",
          "group": "Button / input group",
          "sensor_type": "Sensor type",
          "min": "Minimum value",
          "max": "Maximum value",
          "resolution": "Resolution (LSB)",
          "output_usage": "Output usage (indoor / outdoor)",
          "function": "Output function",
          "has_tilt": "Device supports tilt / blade angle control"
        }
      },
      "entity_channel_mapping": {
        "title": "Bind Output Channels to HA",
        "description": "Select the entities and actions that provide and control each output channel ({channels}). The entity you selected is pre-filled as the read source."
      },
      "device_info": { ... (copy existing) ... },
      "vdsd_creation": { ... },
      "optional_settings": {
        "title": "Optional vdSD Settings",
        "data": {
          "hardwareVersion": "Hardware version",
          "hardwareGuid": "Hardware GUID",
          "vendorGuid": "Vendor GUID",
          "oemGuid": "OEM GUID"
        }
      },
      "vdsd_overview": { "title": "vdSD Overview" },
      "button": { ... },
      "binary_input": { ... },
      "sensor": { ... },
      "output": {
        "title": "Configure Output",
        "data": {
          "name": "Name for this output",
          "groups": "Groups the output generally supports",
          "defaultGroup": "Default group of the output",
          "function": "Function defining the output behavior",
          "outputUsage": "Usage field of the output",
          "variableRamp": "Output supports variable / configurable ramps",
          "mode": "Operating mode of the output",
          "action": "Continue or configure optional output settings"
        }
      },
      "output_optional": { ... },
      "channel": {
        "title": "Configure Output Channel",
        "data": {
          "channelType": "Type of channel to add to the output",
          "name": "Name of this channel",
          "min": "Minimum value for the channel",
          "max": "Maximum value for the channel",
          "resolution": "Channel resolution — smallest deviation that can be displayed (LSB)",
          "action": "Add another channel or proceed to channel mapping"
        }
      },
      "channel_mapping": { ... },
      "model_features": { ... },
      "device_summary": { "title": "Device Summary" }
    },
    "error": {
      "entity_not_found": "Entity not found.",
      "entity_not_supported": "This entity type / device class combination is not supported."
    }
  }
}
```

> **Note:** Fill in the `...` sections by copying the matching step blocks from the existing `strings.json` content. The key changes are: `optional_settings` now has `hardwareGuid`+`oemGuid` instead of `deviceIcon16`; `output` and `channel` gain `action` labels; the entity flow steps are added.

- [ ] **Step 2: Remove entity flow steps from `strings.json` top-level `config.step`**

The steps `creation_mode`, `entity_picker`, `entity_user_input`, `entity_channel_mapping` should be removed from `config.step` (since the entity flow now lives in the subentry) and only exist in `config_subentries.device.step`.

The `config.step` section should contain only hub flow steps: `hub`, `wait_for_dss`, `state_files`.

- [ ] **Step 3: Fix `optional_settings` data fields in both files**

In `strings.json` and `en.json` `optional_settings.data`:
- Remove `deviceIcon16` (not in schema)
- Add `hardwareGuid: "Hardware GUID"`
- Add `oemGuid: "OEM GUID"`

- [ ] **Step 4: Fix `en.json` — remove duplicate `state_files` from `config.step`**

In `en.json`, the duplicate `state_files` block (lines 113–119, inside `config.step` after `binary_input`) must be deleted. The `binary_input` step should be the last entry before `config.step` closes.

The remaining `config.step` in `en.json` should mirror the updated `strings.json`: only hub flow steps (`hub`, `wait_for_dss`, `state_files`).

- [ ] **Step 5: Sync entity flow steps in `en.json` to subentry section**

Move `creation_mode`, `entity_picker`, `entity_user_input`, `entity_channel_mapping` from `config.step` (where they currently are in `en.json`) to `config_subentries.device.step`.

Update `config_subentries.device.step.creation_mode` to reflect the subentry context:
```json
"creation_mode": {
  "title": "Create Device",
  "description": "How would you like to create the virtual device (vdSD)?",
  "data": { "mode": "Creation method" }
}
```

- [ ] **Step 6: Verify JSON validity**

```bash
python3 -c "
import json
for f in ['custom_components/dsvdc4ha/strings.json', 'custom_components/dsvdc4ha/translations/en.json']:
    with open(f) as fh:
        json.load(fh)
    print(f'{f}: valid')
"
```

Expected: both files print `valid`.

- [ ] **Step 7: Commit**

```bash
git add custom_components/dsvdc4ha/strings.json custom_components/dsvdc4ha/translations/en.json
git commit -m "fix: sync strings.json with en.json; add config_subentries section; fix optional_settings fields"
```

---

## Phase 5 — Update Tests and Documentation

### Task 5: Verify tests and update documentation

**Files:**
- Modify: `tests/test_config_flow.py`
- Modify: `docs/superpowers/specs/2026-05-13-refactor-findings.md` (mark resolved)
- Modify: `docs/superpowers/specs/2026-05-06-dsvdc4ha-design.md`

- [ ] **Step 1: Update test that checks hub routing**

`test_hub_flow_routes_to_device_when_hub_exists` now expects `async_step_user` to abort (since hub already exists = `already_configured`), not show `creation_mode`. Update:

```python
@pytest.mark.asyncio
async def test_hub_flow_aborts_when_hub_already_exists():
    """async_step_user aborts with already_configured when a hub entry exists."""
    flow = DsvdcConfigFlow()
    flow.hass = MagicMock()
    flow.context = {"source": "user"}

    mock_hub_entry = MagicMock()
    mock_hub_entry.data = {CONF_ENTRY_TYPE: ENTRY_TYPE_HUB}
    flow._async_current_entries = MagicMock(return_value=[mock_hub_entry])

    result = await flow.async_step_user(user_input=None)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
```

- [ ] **Step 2: Add a test for `VdsdSubentryFlowHandler.async_step_user` routing to `creation_mode`**

```python
@pytest.mark.asyncio
async def test_subentry_flow_routes_to_creation_mode():
    """VdsdSubentryFlowHandler.async_step_user routes to creation_mode."""
    from custom_components.dsvdc4ha.config_flow import VdsdSubentryFlowHandler
    flow = VdsdSubentryFlowHandler()
    flow.hass = MagicMock()
    flow.context = {}

    result = await flow.async_step_user(user_input=None)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "creation_mode"
```

- [ ] **Step 3: Run full test suite**

```bash
cd /home/arne/Development/dsvdc4ha && source .venv/bin/activate && pytest tests/ -v 2>&1
```

Expected: all tests pass with 0 failures.

- [ ] **Step 4: Update design spec**

In `docs/superpowers/specs/2026-05-06-dsvdc4ha-design.md`:

- Section 6.1 Hub flow: add note that hub flow aborts with `already_configured` if a hub already exists
- Section 6.2 Device sub-flow: update creation_mode description — it is now the entry point for `VdsdSubentryFlowHandler` (the subentry "Add device" flow), not for the hub flow
- Section 13 Design Decisions Log: add entry: "Entity flow in subentry, not hub flow | Moved to VdsdSubentryFlowHandler | DsvdcConfigFlow is a ConfigFlow and cannot create config subentries; only ConfigSubentryFlow can"

- [ ] **Step 5: Final commit**

```bash
git add tests/test_config_flow.py docs/
git commit -m "fix: update tests for corrected routing; update design spec"
```

---

## Self-Review Checklist

**Findings addressed:**
- [x] C1 — Duplicate `async_step_user` → removed, replaced with single correct definition
- [x] C2 — `CONF_ENTRY_TYPE`/`ENTRY_TYPE_HUB` missing → added to `const.py`
- [x] C3 — Entity flow calls missing methods → methods moved to `VdsdSubentryFlowHandler`
- [x] C4 — Entity flow in wrong class → moved to `VdsdSubentryFlowHandler`
- [x] C5 — Hub entry data missing `CONF_ENTRY_TYPE` → `async_step_finalize_hub` now stores it
- [x] H1 — Invalid `input_usage: 4` → changed to 0 (Generic)
- [x] H2 — `displayId` uses `friendly_name` → changed to `self._display_id`
- [x] H3 — `output_optional` unreachable → added action to output step; fixed return navigation
- [x] H4 — `optional_settings` fields mismatch → strings updated to match schema
- [x] M1 — `strings.json` missing `config_subentries` → added
- [x] M2 — Duplicate `state_files` in `en.json` → removed
- [x] M3 — `SubentryFlowResult` unused import → removed
- [x] M4 — Deprecated `asyncio.get_event_loop()` → replaced with `async_add_executor_job`
- [ ] L1 — `cover/damper` missing from design doc table → noted, update in Task 5 Step 4
- [ ] L2 — `channel` step `action` field has no UI string → fixed in Task 4 Step 1
