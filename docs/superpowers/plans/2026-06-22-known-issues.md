# Known Issues Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 12 tracked known issues: UI/logo, hub naming, entity visibility, per-vdSD config URL, vdSD name limits, plug output bugs, re-announce action, auto-reconnect, binary sensor flow UI, device properties exposure, naming confirmation screens, and entity selection in the "from device" flow.

**Architecture:** Issues are implemented as independent tasks in dependency order (simple fixes first, then behaviour bugs, then new features). Each task is self-contained and leaves tests green.

**Tech Stack:** Python, Home Assistant custom_components patterns, pydsvdcapi 0.8.9, HA entity registry / device registry helpers.

**Excluded from this plan:** Manual callback bindings redesign → covered by `2026-06-22-callback-bindings.md`.

---

## File Structure

Files that will be touched per task:

| Task | Files |
|------|-------|
| 1. Logo | `custom_components/dsvdc4ha/brand/icon.png`, `brand/icon@2x.png` |
| 2. Hub naming | `custom_components/dsvdc4ha/const.py` |
| 3. Entity visibility | `custom_components/dsvdc4ha/sensor.py`, `binary_sensor.py` |
| 4. Config URL | `custom_components/dsvdc4ha/__init__.py`, `api.py`, `tests/test_api.py` |
| 5. vdSD name truncation | `custom_components/dsvdc4ha/config_flow.py`, investigate pydsvdcapi |
| 6. Plug output bugs | `custom_components/dsvdc4ha/entity_mapping.py`, `config_flow.py`, `listeners.py`, `tests/test_listeners.py` |
| 7. Re-announce | `custom_components/dsvdc4ha/button.py` (new), `__init__.py`, `const.py`, `coordinator.py`, `tests/test_reannounce.py` |
| 8. Auto-reconnect | `custom_components/dsvdc4ha/coordinator.py`, `tests/test_coordinator.py` |
| 9. Binary sensor UI | `custom_components/dsvdc4ha/config_flow.py`, `entity_mapping.py`, `translations/en.json` |
| 10. Device properties | `custom_components/dsvdc4ha/sensor.py`, `binary_sensor.py`, `__init__.py`, `tests/test_properties.py` |
| 11. Naming screens | `custom_components/dsvdc4ha/config_flow.py`, `translations/en.json` |
| 12. Entity selection | `custom_components/dsvdc4ha/config_flow.py`, `translations/en.json` |

---

## Task 1: Integration Logo

Add the standard HA integration logo files so the logo appears in the integration overview and entity detail views.

**Files:**
- Create: `custom_components/dsvdc4ha/brand/icon.png` (256×256 px)
- Create: `custom_components/dsvdc4ha/brand/icon@2x.png` (512×512 px)

Note: The `brand/` directory already exists with `logo.png` / `logo@2x.png`. HA's frontend looks for `icon.png` / `icon@2x.png` at the same path to show the integration icon in larger UI contexts.

- [ ] **Step 1: Create icon files**

  Copy or resize `custom_components/dsvdc4ha/brand/logo.png` and `logo@2x.png` to `icon.png` / `icon@2x.png`. If you have ImageMagick available:
  
  ```bash
  cd custom_components/dsvdc4ha/brand
  convert logo.png -resize 256x256 icon.png
  convert logo@2x.png -resize 512x512 icon@2x.png
  ```
  
  If ImageMagick is unavailable, copy the files directly (the logo sizes may differ from spec, but HA will still use them):
  
  ```bash
  cp custom_components/dsvdc4ha/brand/logo.png custom_components/dsvdc4ha/brand/icon.png
  cp custom_components/dsvdc4ha/brand/logo@2x.png custom_components/dsvdc4ha/brand/icon@2x.png
  ```

- [ ] **Step 2: Verify files exist**

  ```bash
  ls -la custom_components/dsvdc4ha/brand/icon*.png
  ```
  
  Expected: two files, both non-zero size.

- [ ] **Step 3: Commit**

  ```bash
  git add custom_components/dsvdc4ha/brand/icon.png custom_components/dsvdc4ha/brand/icon@2x.png
  git commit -m "feat: add integration icon.png / icon@2x.png for HA logo display"
  ```

---

## Task 2: Hub Device & Constants Naming

Rename the hub device from "KarlKiel's Home Assistant vDC-host" to "vdc @ Home Assistant" and clean up related model/vendor strings.

**Files:**
- Modify: `custom_components/dsvdc4ha/const.py`

Note: `VDC_HOST_NAME` drives the HA device registry name for the hub device (identified by `(DOMAIN, entry.entry_id)`). Changing it causes HA to update the device name on next reload — safe because device identity uses the identifiers tuple, not the name.

- [ ] **Step 1: Write the failing test**

  In `tests/test_coordinator.py`, add:
  
  ```python
  def test_hub_device_name_constant():
      from custom_components.dsvdc4ha.const import VDC_HOST_NAME
      assert VDC_HOST_NAME == "vdc @ Home Assistant"
  ```

- [ ] **Step 2: Run test to verify it fails**

  ```bash
  pytest tests/test_coordinator.py::test_hub_device_name_constant -v
  ```
  
  Expected: FAIL — current value is "KarlKiel's Home Assistant vDC-host".

- [ ] **Step 3: Update constants**

  Edit `custom_components/dsvdc4ha/const.py`:
  
  ```python
  VDC_HOST_NAME = "vdc @ Home Assistant"
  VDC_HOST_MODEL = "vDC-host @ Home Assistant"
  VDC_HOST_MODEL_UID = "ha-vdc-host"
  VDC_HOST_VENDOR_NAME = "Home Assistant"
  VDC_HOST_VENDOR_GUID = "vendorname:HomeAssistant"
  
  VDC_NAME = "vDC for Home Assistant"
  VDC_MODEL = "vDC @ Home Assistant"
  VDC_MODEL_UID = "ha-vdc"
  VDC_IMPLEMENTATION_ID = "x-HA-vDC"
  ```

- [ ] **Step 4: Run test to verify it passes**

  ```bash
  pytest tests/test_coordinator.py::test_hub_device_name_constant -v
  ```

- [ ] **Step 5: Run full test suite**

  ```bash
  pytest tests/ -v
  ```

- [ ] **Step 6: Commit**

  ```bash
  git add custom_components/dsvdc4ha/const.py tests/test_coordinator.py
  git commit -m "feat: rename hub device and vendor strings to generic HA identity"
  ```

---

## Task 3: Mirror Entity Visibility Default

All generated mirror entities (button sensors, sensor inputs, output channel sensors, binary input sensors) should be disabled by default in HA so users do not accidentally use them in automations. They can be re-enabled manually.

The hub connectivity sensor (`HubConnectivitySensor`) is kept enabled — it provides genuine integration monitoring information.

**Files:**
- Modify: `custom_components/dsvdc4ha/sensor.py`
- Modify: `custom_components/dsvdc4ha/binary_sensor.py`

Note: `_attr_entity_registry_enabled_default = False` disables the entity in HA's entity registry by default. The entity still gets created and added to the registry; users can enable it manually. The pydsvdcapi integration layer (listeners.py) doesn't depend on these mirror entities — it tracks source entities directly — so disabling them does not break HA→dS or dS→HA communication.

- [ ] **Step 1: Write failing tests**

  In `tests/test_entities.py` (create if not exists):
  
  ```python
  """Tests that mirror entity classes have correct default visibility."""
  
  def test_button_sensor_entity_disabled_by_default():
      from custom_components.dsvdc4ha.sensor import ButtonSensorEntity
      assert ButtonSensorEntity._attr_entity_registry_enabled_default is False
  
  def test_sensor_input_entity_disabled_by_default():
      from custom_components.dsvdc4ha.sensor import SensorInputEntity
      assert SensorInputEntity._attr_entity_registry_enabled_default is False
  
  def test_output_channel_entity_disabled_by_default():
      from custom_components.dsvdc4ha.sensor import OutputChannelEntity
      assert OutputChannelEntity._attr_entity_registry_enabled_default is False
  
  def test_binary_input_entity_disabled_by_default():
      from custom_components.dsvdc4ha.binary_sensor import BinaryInputEntity
      assert BinaryInputEntity._attr_entity_registry_enabled_default is False
  
  def test_hub_connectivity_sensor_enabled_by_default():
      from custom_components.dsvdc4ha.binary_sensor import HubConnectivitySensor
      assert getattr(HubConnectivitySensor, "_attr_entity_registry_enabled_default", True) is True
  ```

- [ ] **Step 2: Run tests to verify they fail**

  ```bash
  pytest tests/test_entities.py -v
  ```

- [ ] **Step 3: Add attribute to sensor entity classes**

  In `custom_components/dsvdc4ha/sensor.py`, add `_attr_entity_registry_enabled_default = False` to each class:
  
  ```python
  class ButtonSensorEntity(DsvdcBaseEntity, SensorEntity):
      _attr_entity_registry_enabled_default = False
      ...
  
  class SensorInputEntity(DsvdcBaseEntity, SensorEntity):
      _attr_entity_registry_enabled_default = False
      ...
  
  class OutputChannelEntity(DsvdcBaseEntity, SensorEntity):
      _attr_entity_registry_enabled_default = False
      ...
  ```

- [ ] **Step 4: Add attribute to binary sensor entity class**

  In `custom_components/dsvdc4ha/binary_sensor.py`, add to `BinaryInputEntity` only (NOT `HubConnectivitySensor`):
  
  ```python
  class BinaryInputEntity(DsvdcBaseEntity, BinarySensorEntity):
      _attr_entity_registry_enabled_default = False
      ...
  ```

- [ ] **Step 5: Run tests to verify they pass**

  ```bash
  pytest tests/test_entities.py tests/ -v
  ```

- [ ] **Step 6: Commit**

  ```bash
  git add custom_components/dsvdc4ha/sensor.py custom_components/dsvdc4ha/binary_sensor.py tests/test_entities.py
  git commit -m "feat: disable mirror entities by default in HA entity registry"
  ```

---

## Task 4: Per-vdSD Config URL Using HA Device Registry ID

Currently all vdSDs share a single `config_url` pointing to the integration page. Each vdSD should link directly to its HA device page: `{internal_url}/config/devices/device/{ha_device_id}`.

**Files:**
- Modify: `custom_components/dsvdc4ha/__init__.py`
- Modify: `custom_components/dsvdc4ha/api.py`

Architecture: After platforms are set up (which registers devices in HA's device registry), iterate all vdSDs, look up their HA device ID via `dr.async_get_device(identifiers={(DOMAIN, f"{subentry_id}_{vdsd_idx}")})`, and patch `vdsd.config_url` on the pydsvdcapi `Vdsd` object. The `config_url` attribute on `Vdsd` is writable and gets included in the next announcement.

- [ ] **Step 1: Write the failing test**

  In `tests/test_api.py`, add:
  
  ```python
  def test_build_vdsd_uses_default_config_url():
      """Verify _build_vdsd stores the hub config_url initially (per-vdSD is patched later)."""
      from custom_components.dsvdc4ha.api import DsvdcApi
      api = DsvdcApi(port=9090, version="1.0", config_url="http://ha.local/config/integrations", state_path="/tmp/state")
      # config_url is stored on the api instance for initial use
      assert api._config_url == "http://ha.local/config/integrations"
  ```

- [ ] **Step 2: Run test to verify it passes (baseline)**

  ```bash
  pytest tests/test_api.py::test_build_vdsd_uses_default_config_url -v
  ```

- [ ] **Step 3: Add `patch_vdsd_config_urls` method to DsvdcApi**

  In `custom_components/dsvdc4ha/api.py`, add a new method after `announce_device`:
  
  ```python
  def patch_vdsd_config_urls(self, url_map: dict[tuple[str, int], str]) -> None:
      """Patch config_url on individual vdSDs after HA device registration.
  
      url_map: {(entry_id, vdsd_idx): config_url_str}
      Silently skips missing entry_ids or vdsd indices.
      """
      for (entry_id, vdsd_idx), url in url_map.items():
          device = self._devices.get(entry_id)
          if device is None:
              continue
          vdsd = device.get_vdsd(vdsd_idx)
          if vdsd is not None:
              vdsd.config_url = url
  ```

- [ ] **Step 4: Write test for patch_vdsd_config_urls**

  In `tests/test_api.py`, add:
  
  ```python
  def test_patch_vdsd_config_urls(mock_api):
      """patch_vdsd_config_urls silently skips unknown entries."""
      from custom_components.dsvdc4ha.api import DsvdcApi
      api = DsvdcApi(port=9090, version="1.0", config_url="http://ha.local/config", state_path="/tmp/s")
      # No devices registered — should not raise
      api.patch_vdsd_config_urls({("nonexistent", 0): "http://ha.local/device/abc"})
  ```

- [ ] **Step 5: Call patch_vdsd_config_urls in async_setup_entry**

  In `custom_components/dsvdc4ha/__init__.py`, add after `async_forward_entry_setups`:
  
  ```python
  # Patch per-vdSD config URLs to point to their HA device pages.
  from homeassistant.helpers import device_registry as dr
  dev_reg = dr.async_get(hass)
  internal_url = hass.config.internal_url or "http://homeassistant.local"
  url_map: dict[tuple[str, int], str] = {}
  for subentry in entry.subentries.values():
      for vdsd_idx in range(len(subentry.data.get("vdsds", []))):
          identifier = (DOMAIN, f"{subentry.subentry_id}_{vdsd_idx}")
          ha_device = dev_reg.async_get_device(identifiers={identifier})
          if ha_device is not None:
              url_map[(subentry.subentry_id, vdsd_idx)] = (
                  f"{internal_url}/config/devices/device/{ha_device.id}"
              )
  if url_map and coordinator.api:
      coordinator.api.patch_vdsd_config_urls(url_map)
  ```

  Insert this block at line ~149, after `await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)` but before `await _backfill_missing_icons(...)`.

- [ ] **Step 6: Run full test suite**

  ```bash
  pytest tests/ -v
  ```

- [ ] **Step 7: Commit**

  ```bash
  git add custom_components/dsvdc4ha/__init__.py custom_components/dsvdc4ha/api.py tests/test_api.py
  git commit -m "feat: set per-vdSD config URL to HA device page after platform setup"
  ```

---

## Task 5: vdSD Name Length Investigation and Fix

vdSD device names appear truncated in the dSS UI. Since the dSS configurator allows extending names manually, the truncation is on our side. Investigate and remove the limit.

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py` (if TextSelector has maxlength)
- Modify: `custom_components/dsvdc4ha/api.py` (if _build_vdsd truncates)

- [ ] **Step 1: Find where truncation happens**

  ```bash
  # Search for maxlength, truncate, [:N] slicing, or len checks on name fields
  grep -n "maxlength\|truncat\|\[:.*\]\|len(.*name\|name.*len" \
    custom_components/dsvdc4ha/config_flow.py \
    custom_components/dsvdc4ha/api.py \
    custom_components/dsvdc4ha/const.py
  
  # Also check pydsvdcapi vdsd.py for any name limit enforcement
  grep -n "maxlength\|truncat\|\[:.*\]\|len(.*name\|MAX_NAME" \
    .venv/lib/python*/site-packages/pydsvdcapi/vdsd.py
  ```

- [ ] **Step 2: Check config flow TextSelector for name fields**

  In `config_flow.py`, search for all `TextSelector` usages near name fields:
  
  ```bash
  grep -n "TextSelector\|name.*text\|text.*name" custom_components/dsvdc4ha/config_flow.py | head -20
  ```
  
  If any `TextSelectorConfig` has a `maxlength` set, remove it or raise it to 255.

- [ ] **Step 3: Check pydsvdcapi protocol limits**

  Look at pydsvdcapi's `vdsd.py` to see if it truncates `self.name` before encoding:
  
  ```bash
  grep -n "name\[:.*\]\|str.*name\|name.*str" .venv/lib/python*/site-packages/pydsvdcapi/vdsd.py | grep "\[:" | head -10
  ```

  If pydsvdcapi truncates names in the protocol encoding, this is an upstream issue. Document it and open a ticket; for now, do nothing (we can't fix pydsvdcapi in this plan).

- [ ] **Step 4: If limit found in our code, write failing test and fix**

  Example — if `config_flow.py` has `TextSelectorConfig(type=TextSelectorType.TEXT, maxlength=20)` on a name field:
  
  ```python
  # In tests/test_config_flow.py
  def test_name_field_has_no_artificial_maxlength():
      """TextSelector for vdSD name fields must not limit to <100 chars."""
      import custom_components.dsvdc4ha.config_flow as cf
      import inspect, ast
      src = inspect.getsource(cf)
      # If a TextSelectorConfig with maxlength <= 100 is used near 'name', fail
      # (This is a documentation test — adjust to match actual code pattern found.)
      assert "maxlength=20" not in src, "Remove artificial name length limit from config flow"
  ```

- [ ] **Step 5: Apply fix if needed**

  If truncation found in config_flow.py, remove the `maxlength` parameter from `TextSelectorConfig` on name-related fields.

- [ ] **Step 6: Commit (only if changes were made)**

  ```bash
  git add custom_components/dsvdc4ha/config_flow.py
  git commit -m "fix: remove artificial vdSD name length limit in config flow"
  ```

---

## Task 6: Plug Output Bugs

Three bugs with plug/switch (ON_OFF + POWER_STATE channel) outputs:

1. `onThreshold` "no output" error — fires when dSM sends `setOutputChannelValue` to a vdSD whose `vdsd.output` is None in pydsvdcapi. Root cause: the output is not being attached in `_build_vdsd`.
2. HA→dS scaling wrong — `push_expr` returns 1 for "on" but POWER_STATE channel max=3 (enum: 0=off, 1=on, 2=standby, 3=extendedStandby). Value 1 is correct, but we need to verify dSM displays it as "on" vs. percentage.
3. dS→HA not working — `on_channel_applied` callback not firing.

**Files:**
- Modify: `custom_components/dsvdc4ha/entity_mapping.py`
- Modify: `custom_components/dsvdc4ha/config_flow.py`
- Modify: `custom_components/dsvdc4ha/listeners.py`

- [ ] **Step 1: Diagnose — check config storage for switch entity from entity flow**

  In a Python REPL or test, trace what `output_data` looks like when stored for a switch entity:
  
  ```python
  # What gets stored in subentry.data for a switch entity:
  # From entity_mapping.py ENTITY_MAPPING, switch entry:
  # output = {
  #   "function": OutputFunction.ON_OFF,       ← IntEnum
  #   "mode": OutputMode.BINARY,               ← IntEnum
  #   ...
  #   "channels": [{"channel_type": OutputChannelType.POWER_STATE, ...}]
  # }
  # When serialized to HA config (JSON), IntEnum → int. Good.
  # But what key is used in _build_vdsd: data.get("output") ?
  ```
  
  Check: in `config_flow.py`, what key is used to store output data for entity-flow-created vdSDs. Look for where `vdsd_data["output"]` or similar is built.

  ```bash
  grep -n '"output"\|vdsd_data\[.output.\]\|_current_output\|subentry.*output\|output.*subentry' \
    custom_components/dsvdc4ha/config_flow.py | head -20
  ```

- [ ] **Step 2: Verify _add_output is called for switch vdSDs**

  Add a temporary debug log to `api.py` `_build_vdsd`:
  
  ```python
  def _build_vdsd(self, device: Device, idx: int, data: dict[str, Any]) -> Vdsd:
      ...
      if output_data := data.get("output"):
          _LOGGER.debug("_build_vdsd: adding output for idx=%d fn=%s", idx, output_data.get("function"))
          _add_output(vdsd, output_data)
      else:
          _LOGGER.warning("_build_vdsd: NO OUTPUT data for idx=%d data_keys=%s", idx, list(data.keys()))
  ```
  
  After testing, remove the debug logs.

- [ ] **Step 3: Fix POWER_STATE push_expr and apply_expr**

  The POWER_STATE channel spec: `min=0, max=3, resolution=1, enum: {0:off, 1:on, 2:standby, 3:extendedStandby}`.
  
  Current push_expr: `"1 if entity.state=='on' else 0"` → value 1 for "on". This is correct for the enum.
  Current apply_expr: `"... if value>=1 else ..."` → triggers on value≥1. This is correct if dSM sends enum value (1=on).
  
  BUT: dSM may send a percentage value (0-100) rather than the raw enum. In BINARY mode, dSM typically sends 100% for "on" and 0% for "off". pydsvdcapi receives this and calls `channel.set_value_from_vdsm(100)` → clamps to max=3 → stores 3.
  
  Fix `apply_expr` to handle both cases:
  
  In `entity_mapping.py`, update ALL switch/outlet/valve/siren POWER_STATE apply_expr from `value>=1` to `value>0`:
  
  ```python
  # switch (device_class=None):
  "apply_expr": "{'domain':'switch','service':'turn_on' if value>0 else 'turn_off','service_data':{}}",
  
  # switch (device_class='outlet'):
  "apply_expr": "{'domain':'switch','service':'turn_on' if value>0 else 'turn_off','service_data':{}}",
  
  # switch (device_class='switch'):
  "apply_expr": "{'domain':'switch','service':'turn_on' if value>0 else 'turn_off','service_data':{}}",
  
  # valve (ON_OFF):
  "apply_expr": "{'domain':'valve','service':'open_valve' if value>0 else 'close_valve','service_data':{}}",
  
  # cover/door, cover/garage, cover/gate (ON_OFF):
  "apply_expr": "{'domain':'cover','service':'open_cover' if value>0 else 'close_cover','service_data':{}}",
  
  # siren POWER_STATE:
  "apply_expr": "{'domain':'siren','service':'turn_on' if value>0 else 'turn_off','service_data':{}}",
  ```
  
  Also fix push_expr to return 1 (enum "on") not 0/1 raw boolean:
  The current `"1 if entity.state=='on' else 0"` already returns the correct POWER_STATE enum value. Keep as-is.

- [ ] **Step 4: Fix config flow to only show onThreshold for ON_OFF function**

  In `custom_components/dsvdc4ha/config_flow.py`, in `async_step_output_optional`, the current code shows `onThreshold` for all function types. Fix:
  
  ```python
  async def async_step_output_optional(self, user_input: dict | None = None):
      ...
      fn = self._current_output.get("function", 0) if self._current_output else 0
      is_on_off = fn == OutputFunction.ON_OFF.value
      is_positional = fn == OutputFunction.POSITIONAL.value
      is_dimmer = fn in (
          OutputFunction.DIMMER.value,
          OutputFunction.DIMMER_COLOR_TEMP.value,
          OutputFunction.FULL_COLOR_DIMMER.value,
      )
      _ns_pct = selector.NumberSelectorConfig(min=0, max=100, mode="box")
      schema_dict: dict = {}
      # onThreshold: only for ON_OFF
      if is_on_off:
          schema_dict[vol.Optional("onThreshold", default=50)] = selector.NumberSelector(_ns_pct)
      schema_dict[vol.Optional("minBrightness")] = selector.NumberSelector(_ns_pct)
      ...
  ```

- [ ] **Step 5: Write tests for apply_expr threshold fix**

  In `tests/test_listeners.py` (create if not exists):
  
  ```python
  """Tests for listeners.py output callback."""
  import pytest
  from unittest.mock import AsyncMock, MagicMock, patch
  
  @pytest.mark.asyncio
  async def test_power_state_apply_expr_on_when_value_greater_than_zero():
      """apply_expr for POWER_STATE triggers turn_on for any value > 0."""
      from custom_components.dsvdc4ha.listeners import _eval_apply
      state = MagicMock()
      state.attributes = {}
      # dSM sends 100% (binary on), pydsvdcapi clamps to max=3
      expr = "{'domain':'switch','service':'turn_on' if value>0 else 'turn_off','service_data':{}}"
      result = _eval_apply(expr, 3.0, state)
      assert result["service"] == "turn_on"
  
  @pytest.mark.asyncio
  async def test_power_state_apply_expr_off_when_value_zero():
      """apply_expr for POWER_STATE triggers turn_off for value 0."""
      from custom_components.dsvdc4ha.listeners import _eval_apply
      state = MagicMock()
      state.attributes = {}
      expr = "{'domain':'switch','service':'turn_on' if value>0 else 'turn_off','service_data':{}}"
      result = _eval_apply(expr, 0.0, state)
      assert result["service"] == "turn_off"
  ```

- [ ] **Step 6: Run tests**

  ```bash
  pytest tests/test_listeners.py -v
  pytest tests/ -v
  ```

- [ ] **Step 7: Commit**

  ```bash
  git add custom_components/dsvdc4ha/entity_mapping.py \
          custom_components/dsvdc4ha/config_flow.py \
          tests/test_listeners.py
  git commit -m "fix: correct POWER_STATE apply_expr threshold and restrict onThreshold to ON_OFF outputs"
  ```

---

## Task 7: Re-announce Device Action

Add a way for users to manually trigger re-announcement of a vdSD device to dSS. Implement as a button entity with `EntityCategory.CONFIG` on each vdSD device, backed by a HA action (service call).

**Files:**
- Create: `custom_components/dsvdc4ha/button.py`
- Modify: `custom_components/dsvdc4ha/const.py`
- Modify: `custom_components/dsvdc4ha/__init__.py`
- Modify: `custom_components/dsvdc4ha/api.py`

Architecture: A new `ReannounceButtonEntity` is added per vdSD. When pressed, it calls `coordinator.api.force_reannounce_device(subentry_id)` which discards the device from `_ever_announced` and calls `announce_device()` again.

- [ ] **Step 1: Add PLATFORMS to const.py**

  In `custom_components/dsvdc4ha/const.py`, add "button" to platforms:
  
  ```python
  PLATFORMS = ["sensor", "binary_sensor", "button"]
  ```

- [ ] **Step 2: Add force_reannounce_device to DsvdcApi**

  In `custom_components/dsvdc4ha/api.py`, add:
  
  ```python
  async def force_reannounce_device(self, entry_id: str) -> None:
      """Force re-announcement of a device to dSS, ignoring _ever_announced cache."""
      self._ever_announced.discard(entry_id)
      await self.announce_device(entry_id)
  ```

- [ ] **Step 3: Create button.py**

  Create `custom_components/dsvdc4ha/button.py`:
  
  ```python
  """Button platform for dsvdc4ha — re-announce device button."""
  from __future__ import annotations
  
  import logging
  from typing import Any
  
  from homeassistant.components.button import ButtonEntity
  from homeassistant.config_entries import ConfigEntry
  from homeassistant.core import HomeAssistant
  from homeassistant.helpers.entity import EntityCategory
  from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
  
  from .base_entity import DsvdcBaseEntity
  from .const import DOMAIN
  from .coordinator import HubCoordinator
  
  _LOGGER = logging.getLogger(__name__)
  
  
  async def async_setup_entry(
      hass: HomeAssistant,
      entry: ConfigEntry,
      async_add_entities: AddConfigEntryEntitiesCallback,
  ) -> None:
      coordinator: HubCoordinator = hass.data[DOMAIN]["hub"]
      hass.data.setdefault(DOMAIN, {})["_add_button_entities"] = async_add_entities
      for subentry in entry.subentries.values():
          _add_entities_for_subentry(subentry, async_add_entities, coordinator)
  
  
  def _add_entities_for_subentry(
      subentry: Any,
      async_add_entities: AddConfigEntryEntitiesCallback,
      coordinator: HubCoordinator,
  ) -> None:
      entities: list[DsvdcBaseEntity] = []
      for idx, vdsd_data in enumerate(subentry.data.get("vdsds", [])):
          entities.append(
              ReannounceButtonEntity(subentry.subentry_id, idx, vdsd_data, coordinator)
          )
      async_add_entities(entities, config_subentry_id=subentry.subentry_id)
  
  
  class ReannounceButtonEntity(DsvdcBaseEntity, ButtonEntity):
      """Button that forces re-announcement of this vdSD to dSS."""
  
      _attr_entity_category = EntityCategory.CONFIG
      _attr_has_entity_name = True
  
      def __init__(
          self,
          subentry_id: str,
          vdsd_index: int,
          vdsd_data: dict,
          coordinator: HubCoordinator,
      ) -> None:
          super().__init__(subentry_id, vdsd_index, vdsd_data, "reannounce")
          self._coordinator = coordinator
          self._attr_name = "Re-announce to dSS"
  
      async def async_press(self) -> None:
          if self._coordinator.api is None:
              _LOGGER.warning("Re-announce pressed but API is not running")
              return
          await self._coordinator.api.force_reannounce_device(self._subentry_id)
          _LOGGER.info(
              "Re-announced vdSD %d of subentry %s",
              self._vdsd_index,
              self._subentry_id,
          )
  ```

- [ ] **Step 4: Update __init__.py to add button entities for new subentries**

  In `custom_components/dsvdc4ha/__init__.py`, in `_async_subentry_update_listener`, add button entity support:
  
  ```python
  from . import button as _button_mod
  add_button = domain_data.get("_add_button_entities")
  
  for subentry_id in added:
      ...
      if add_button:
          _button_mod._add_entities_for_subentry(subentry, add_button, coordinator)
  ```

- [ ] **Step 5: Write test for re-announce**

  Create `tests/test_reannounce.py`:
  
  ```python
  """Tests for re-announce button."""
  import pytest
  from unittest.mock import AsyncMock, MagicMock, patch
  
  @pytest.mark.asyncio
  async def test_force_reannounce_clears_announced_flag(mock_api):
      """force_reannounce_device removes entry from _ever_announced and calls announce."""
      from custom_components.dsvdc4ha.api import DsvdcApi
      api = DsvdcApi(port=9090, version="1.0", config_url="http://ha", state_path="/tmp/s")
      api._ever_announced = {"subentry-1"}
      api._devices = {}  # no device → announce_device is a no-op
      api._host = MagicMock()
      api._host.session = None
      await api.force_reannounce_device("subentry-1")
      assert "subentry-1" not in api._ever_announced
  ```

- [ ] **Step 6: Run tests**

  ```bash
  pytest tests/test_reannounce.py tests/ -v
  ```

- [ ] **Step 7: Commit**

  ```bash
  git add custom_components/dsvdc4ha/button.py \
          custom_components/dsvdc4ha/const.py \
          custom_components/dsvdc4ha/__init__.py \
          custom_components/dsvdc4ha/api.py \
          tests/test_reannounce.py
  git commit -m "feat: add re-announce button entity per vdSD with EntityCategory.CONFIG"
  ```

---

## Task 8: Auto-Reconnect Watchdog

When the dSS connection is lost, the integration should automatically attempt to restart the vDC host rather than requiring a manual HA integration reload.

**Files:**
- Modify: `custom_components/dsvdc4ha/coordinator.py`
- Modify: `custom_components/dsvdc4ha/__init__.py`
- Modify: `tests/test_coordinator.py`

Architecture: On disconnect, `HubCoordinator` schedules an async task that stops the API, restarts it, and re-registers all known devices. The coordinator stores a reference to the HA entry and a list of `(subentry_id, vdsds_data)` pairs so it can restore state after restart. Exponential backoff prevents flooding dSS.

- [ ] **Step 1: Write failing test**

  In `tests/test_coordinator.py`, add:
  
  ```python
  @pytest.mark.asyncio
  async def test_coordinator_schedules_reconnect_on_disconnect(mock_hass, mock_api):
      """On disconnect, coordinator marks itself disconnected and schedules reconnect."""
      import asyncio
      from unittest.mock import AsyncMock, MagicMock, patch
  
      mock_zeroconf = MagicMock()
      mock_integration = MagicMock()
      mock_integration.version = "1.2.3"
  
      with (
          patch("custom_components.dsvdc4ha.coordinator.DsvdcApi", return_value=mock_api),
          patch("custom_components.dsvdc4ha.coordinator.async_get_instance", new=AsyncMock(return_value=mock_zeroconf)),
          patch("custom_components.dsvdc4ha.coordinator.async_get_integration", new=AsyncMock(return_value=mock_integration)),
      ):
          from custom_components.dsvdc4ha.coordinator import HubCoordinator
          coord = HubCoordinator(mock_hass, port=9090)
          reconnect_calls: list[str] = []
  
          async def _fake_reconnect():
              reconnect_calls.append("reconnect")
  
          coord._do_reconnect = _fake_reconnect
          await coord.async_start()
  
          # Simulate disconnect
          disconnect_cb = mock_api.start.call_args.kwargs["on_disconnect"]
          await disconnect_cb(None, "test-reason")
  
          # Connected flag must be cleared
          assert coord.is_connected is False
          # A reconnect task must have been scheduled (check hass.async_create_task was called)
          assert mock_hass.async_create_task.called
  ```

- [ ] **Step 2: Update HubCoordinator with reconnect logic**

  Replace `coordinator.py` with:
  
  ```python
  """HubCoordinator — manages VdcHost + Vdc lifecycle with auto-reconnect."""
  from __future__ import annotations
  
  import asyncio
  import logging
  from collections.abc import Callable
  from typing import TYPE_CHECKING, Any
  
  from homeassistant.components.zeroconf import async_get_instance
  from homeassistant.core import HomeAssistant
  from homeassistant.loader import async_get_integration
  
  from .api import DsvdcApi
  from .const import DOMAIN
  
  if TYPE_CHECKING:
      from homeassistant.config_entries import ConfigEntry
  
  _LOGGER = logging.getLogger(__name__)
  
  _RECONNECT_DELAYS = [5, 15, 30, 60, 120, 300]  # seconds, capped at last value
  
  
  class HubCoordinator:
      """Owns the DsvdcApi instance for the hub config entry."""
  
      def __init__(self, hass: HomeAssistant, port: int) -> None:
          self.hass = hass
          self._port = port
          self.api: DsvdcApi | None = None
          self._connected: bool = False
          self._connection_listeners: list[Callable[[bool], None]] = []
          self._reconnect_attempt: int = 0
          self._reconnect_task: asyncio.Task | None = None
          # Set by async_start_with_entry for reconnect support
          self._entry: Any = None
          self._on_session_ready_ext: Callable | None = None
          self._zeroconf: Any = None
          self._version: str = "0.0.0"
  
      @property
      def is_connected(self) -> bool:
          return self._connected
  
      def subscribe_connection_status(self, callback: Callable[[bool], None]) -> Callable[[], None]:
          self._connection_listeners.append(callback)
          def _unsub() -> None:
              try:
                  self._connection_listeners.remove(callback)
              except ValueError:
                  pass
          return _unsub
  
      def _fire_connection_status(self, connected: bool) -> None:
          self._connected = connected
          for cb in list(self._connection_listeners):
              try:
                  cb(connected)
              except Exception:
                  _LOGGER.exception("Error in connection status callback")
  
      async def async_start(self, on_session_ready=None) -> None:
          integration = await async_get_integration(self.hass, DOMAIN)
          self._version = str(integration.version) if integration.version else "0.0.0"
          config_url = (
              f"{self.hass.config.internal_url}/config/integrations"
              if self.hass.config.internal_url
              else "http://homeassistant.local/config/integrations"
          )
          state_path = self.hass.config.path("dsvdc4ha", "host_state")
          self.api = DsvdcApi(
              port=self._port,
              version=self._version,
              config_url=config_url,
              state_path=state_path,
          )
          self._zeroconf = await async_get_instance(self.hass)
          self._on_session_ready_ext = on_session_ready
  
          _outer_cb = on_session_ready
  
          def _on_session_ready() -> None:
              self._reconnect_attempt = 0
              self._fire_connection_status(True)
              if _outer_cb is not None:
                  _outer_cb()
  
          async def _on_disconnect(host, reason) -> None:
              _LOGGER.warning("dSS disconnected: %s — scheduling reconnect", reason)
              self._fire_connection_status(False)
              if self._reconnect_task is None or self._reconnect_task.done():
                  self._reconnect_task = self.hass.async_create_task(
                      self._reconnect_with_backoff()
                  )
  
          await self.api.start(
              zeroconf=self._zeroconf,
              on_session_ready=_on_session_ready,
              on_disconnect=_on_disconnect,
          )
          _LOGGER.info("dsvdc4ha hub started")
  
      async def _reconnect_with_backoff(self) -> None:
          """Stop and restart the API with exponential backoff."""
          delay = _RECONNECT_DELAYS[
              min(self._reconnect_attempt, len(_RECONNECT_DELAYS) - 1)
          ]
          self._reconnect_attempt += 1
          _LOGGER.info(
              "Reconnect attempt %d in %ds…", self._reconnect_attempt, delay
          )
          await asyncio.sleep(delay)
          await self._do_reconnect()
  
      async def _do_reconnect(self) -> None:
          """Restart the vDC host and re-register all known devices."""
          try:
              if self.api:
                  await self.api.stop()
                  self.api = None
              await self.async_start(on_session_ready=self._on_session_ready_ext)
              # Re-register devices from the config entry if available.
              if self._entry is not None:
                  from .listeners import (
                      setup_input_listeners,
                      setup_output_listeners,
                      seed_initial_values,
                  )
                  for subentry in self._entry.subentries.values():
                      vdsds = subentry.data.get("vdsds", [])
                      if self.api:
                          self.api.add_device(subentry.subentry_id, vdsds)
                          setup_input_listeners(self.hass, self.api, subentry.subentry_id, vdsds)
                          setup_output_listeners(self.hass, self.api, subentry.subentry_id, vdsds)
                          await seed_initial_values(self.hass, self.api, subentry.subentry_id, vdsds)
                          await self.api.announce_device(subentry.subentry_id)
              _LOGGER.info("dsvdc4ha hub reconnected successfully")
          except Exception:
              _LOGGER.exception("Reconnect failed — will retry")
              self._reconnect_task = self.hass.async_create_task(
                  self._reconnect_with_backoff()
              )
  
      async def async_stop(self) -> None:
          if self._reconnect_task and not self._reconnect_task.done():
              self._reconnect_task.cancel()
              self._reconnect_task = None
          if self.api:
              await self.api.stop()
          _LOGGER.info("dsvdc4ha hub stopped")
  ```

- [ ] **Step 3: Store entry reference in coordinator from __init__.py**

  In `custom_components/dsvdc4ha/__init__.py`, after creating the coordinator and before `async_start()`, add:
  
  ```python
  coordinator._entry = entry
  ```
  
  Insert at approximately line 135, inside `async_setup_entry`, after the coordinator is assigned to `coordinator`.

- [ ] **Step 4: Run tests**

  ```bash
  pytest tests/test_coordinator.py -v
  pytest tests/ -v
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add custom_components/dsvdc4ha/coordinator.py \
          custom_components/dsvdc4ha/__init__.py \
          tests/test_coordinator.py
  git commit -m "feat: add auto-reconnect watchdog with exponential backoff to coordinator"
  ```

---

## Task 9: Binary Sensor Config Flow UI Fixes

Three issues:
1. `bi_group` field name shows as label instead of a human-readable string → fix translation.
2. Binary sensor pre-selection defaults: the default group "Light" should be "Joker" for generic flows.
3. All small enum selectors (≤5 options) should use `SelectSelectorMode.LIST` (button group); larger enums use default (DROPDOWN).

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py`
- Modify: `custom_components/dsvdc4ha/entity_mapping.py`
- Modify: `custom_components/dsvdc4ha/translations/en.json`

- [ ] **Step 1: Fix bi_group translation**

  In `custom_components/dsvdc4ha/translations/en.json`, in every step that shows `bi_group`, add:
  
  ```json
  "bi_group": "dS Binary Input Group"
  ```
  
  Find affected steps:
  ```bash
  grep -n "bi_group" custom_components/dsvdc4ha/config_flow.py | grep "schema_dict"
  ```
  
  Steps that use `bi_group` schema key: `device_entity_user_input` and `entity_user_input`. In `translations/en.json`, under each of those steps' `"data"` objects, add the `bi_group` key.

- [ ] **Step 2: Fix SelectSelectorMode for small enums**

  Identify selectors in `config_flow.py` with ≤5 options and add `mode=SelectSelectorMode.LIST`.
  
  Key enums to check (count options; use LIST if ≤5):
  
  - `group` choices for buttons (`_BTN_GROUP_CHOICES`: 2 options) → LIST
  - `bi_group` choices from `_BI_GROUP_ALL` (8 options) → DROPDOWN (keep)
  - `bi_group` choices from `_BI_GROUP_MOISTURE` (3 options) → LIST
  - `sensor_function` choices that have ≤5 entries → LIST
  - `input_usage` choices (`_BI_USAGE_ALL`: 4 options) → LIST
  - `sensor_usage` choices (`_SU_ROOM_OUTDOOR`: 2 options) → LIST
  - `output_usage` choices (typically 2-3) → LIST
  - `function_choices` (e.g., POSITIONAL vs ON_OFF: 2 options) → LIST
  - `callbackType` (3 options) → LIST
  
  In `config_flow.py`, for each `SelectSelector` call, inspect the options list length and add:
  
  ```python
  # Example — for a 2-option selector:
  selector.SelectSelectorConfig(
      options=[...],
      mode=selector.SelectSelectorMode.LIST,  # ≤5 options → button group
  )
  
  # Example — for the 8-option BI_GROUP_ALL:
  selector.SelectSelectorConfig(
      options=[...],
      # no mode → defaults to DROPDOWN
  )
  ```
  
  Helper function to reduce repetition (add near top of `config_flow.py`):
  
  ```python
  def _select(options: list, *, multiple: bool = False) -> selector.SelectSelector:
      """Return a SelectSelector using LIST mode for ≤5 options, DROPDOWN for more."""
      mode = (
          selector.SelectSelectorMode.LIST
          if len(options) <= 5
          else selector.SelectSelectorMode.DROPDOWN
      )
      cfg = selector.SelectSelectorConfig(options=options, mode=mode, multiple=multiple)
      return selector.SelectSelector(cfg)
  ```
  
  Then replace inline `selector.SelectSelector(selector.SelectSelectorConfig(options=[...]))` with `_select([...])`.

- [ ] **Step 3: Fix binary sensor default group in entity_mapping**

  For the `binary_sensor` with `device_class: None` (generic):
  
  In `entity_mapping.py`, the generic binary_sensor already defaults to `BinaryInputGroup.JOKER`. Check that `group_choices` is NOT set (so the user is not shown a selector defaulting to Light).
  
  If `group_choices` appears on the generic entry, remove it:
  
  ```python
  {
      "domain": "binary_sensor", "device_class": None, "primary_group": ColorGroup.BLACK,
      ...
      "binary_input": {
          "sensor_function": BinaryInputType.GENERIC,
          "sensor_function_choices": "any",
          "group": BinaryInputGroup.JOKER,  # no group_choices → not shown to user
          "input_usage": BinaryInputUsage.UNDEFINED,
          "input_usage_choices": _BI_USAGE_ALL,
          ...
      },
  },
  ```

- [ ] **Step 4: Run tests**

  ```bash
  pytest tests/ -v
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add custom_components/dsvdc4ha/config_flow.py \
          custom_components/dsvdc4ha/entity_mapping.py \
          custom_components/dsvdc4ha/translations/en.json
  git commit -m "fix: bi_group label, LIST/DROPDOWN enum display mode, binary sensor default to Joker"
  ```

---

## Task 10: Device Output Properties Exposure

Expose pydsvdcapi's `Output` property groups as HA entities on each vdSD that has an output:
- `get_description_properties()` → read-only sensor entities with `EntityCategory.DIAGNOSTIC`
- `get_settings_properties()` → writable entities with `EntityCategory.CONFIG` (number/select/switch per property)
- `get_state_properties()` → read-only sensor entities (no EntityCategory — already shown for output channels; add missing: localPriority, transitionTime, error)

All generated property entities should be disabled by default (`entity_registry_enabled_default = False`).

**Files:**
- Modify: `custom_components/dsvdc4ha/sensor.py`
- Modify: `custom_components/dsvdc4ha/__init__.py`
- Modify: `custom_components/dsvdc4ha/api.py`
- Create: `custom_components/dsvdc4ha/number.py`
- Create: `custom_components/dsvdc4ha/select.py`
- Create: `custom_components/dsvdc4ha/switch_platform.py` (to avoid conflict with homeassistant.components.switch import)
- Modify: `custom_components/dsvdc4ha/const.py`

Note on scope: This is a substantial feature. The plan covers the minimal viable implementation: expose properties as read-only sensors first (description + state). Writable settings entities are a follow-up.

### Sub-task 10a: Description and State Properties as Diagnostic Sensors

- [ ] **Step 1: Add OutputDescriptionSensorEntity to sensor.py**

  In `custom_components/dsvdc4ha/sensor.py`, add:
  
  ```python
  from homeassistant.helpers.entity import EntityCategory
  
  class OutputDescriptionSensorEntity(DsvdcBaseEntity, SensorEntity):
      """Read-only diagnostic sensor for an outputDescription property."""
  
      _attr_entity_registry_enabled_default = False
      _attr_entity_category = EntityCategory.DIAGNOSTIC
      _attr_should_poll = False
  
      def __init__(
          self,
          subentry_id: str,
          vdsd_index: int,
          vdsd_data: dict,
          prop_key: str,
          prop_value: Any,
      ) -> None:
          super().__init__(subentry_id, vdsd_index, vdsd_data, f"desc_{prop_key}")
          self._prop_key = prop_key
          self._attr_name = f"Description: {prop_key}"
          self._attr_native_value = prop_value
  
      @property
      def state(self) -> Any:
          return self._attr_native_value
  
  
  class OutputStateSensorEntity(DsvdcBaseEntity, SensorEntity):
      """Sensor for an outputState property (localPriority, transitionTime, error)."""
  
      _attr_entity_registry_enabled_default = False
      _attr_should_poll = False
  
      def __init__(
          self,
          subentry_id: str,
          vdsd_index: int,
          vdsd_data: dict,
          prop_key: str,
          prop_value: Any,
      ) -> None:
          super().__init__(subentry_id, vdsd_index, vdsd_data, f"state_{prop_key}")
          self._prop_key = prop_key
          self._attr_name = f"State: {prop_key}"
          self._attr_native_value = prop_value
  
      @property
      def state(self) -> Any:
          return self._attr_native_value
  
      def _handle_state_update(self, new_value: Any) -> None:
          self._attr_native_value = new_value
          if self.hass:
              self.async_write_ha_state()
  ```

- [ ] **Step 2: Extend _add_entities_for_subentry in sensor.py**

  In `sensor.py`'s `_add_entities_for_subentry`, after the existing loop, add property entities when the pydsvdcapi Output object is accessible:
  
  ```python
  def _add_entities_for_subentry(subentry, async_add_entities):
      entities = []
      ...
      # Existing loop for buttons, sensors, output channels
      # (keep as is)
      ...
      # Property entities require coordinator access; stored separately
      async_add_entities(entities, config_subentry_id=subentry.subentry_id)
  ```
  
  Property entities are added from `__init__.py` where the coordinator is accessible.

- [ ] **Step 3: Add property entity creation in __init__.py**

  In `async_setup_entry` in `__init__.py`, after seeding initial values, add:
  
  ```python
  # Expose Output description and state properties as diagnostic sensor entities.
  _add_sensor = hass.data[DOMAIN].get("_add_sensor_entities")
  if _add_sensor and coordinator.api:
      for subentry in entry.subentries.values():
          for vdsd_idx, vdsd_data in enumerate(subentry.data.get("vdsds", [])):
              if not vdsd_data.get("output"):
                  continue
              device = coordinator.api.get_device(subentry.subentry_id)
              if not device:
                  continue
              vdsd = device.get_vdsd(vdsd_idx)
              if not vdsd or not vdsd.output:
                  continue
              from .sensor import OutputDescriptionSensorEntity, OutputStateSensorEntity
              prop_entities = []
              for key, val in vdsd.output.get_description_properties().items():
                  prop_entities.append(
                      OutputDescriptionSensorEntity(
                          subentry.subentry_id, vdsd_idx, vdsd_data, key, val
                      )
                  )
              for key, val in vdsd.output.get_state_properties().items():
                  prop_entities.append(
                      OutputStateSensorEntity(
                          subentry.subentry_id, vdsd_idx, vdsd_data, key, val
                      )
                  )
              if prop_entities:
                  _add_sensor(prop_entities, config_subentry_id=subentry.subentry_id)
  ```

- [ ] **Step 4: Write tests**

  In `tests/test_properties.py`:
  
  ```python
  """Tests for device property exposure."""
  
  def test_output_description_sensor_entity_has_correct_attributes():
      from custom_components.dsvdc4ha.sensor import OutputDescriptionSensorEntity
      ent = OutputDescriptionSensorEntity("sub1", 0, {"name": "MyDevice"}, "function", 0)
      assert ent._attr_name == "Description: function"
      assert ent._attr_entity_registry_enabled_default is False
      from homeassistant.helpers.entity import EntityCategory
      assert ent._attr_entity_category == EntityCategory.DIAGNOSTIC
  
  def test_output_state_sensor_entity_has_correct_attributes():
      from custom_components.dsvdc4ha.sensor import OutputStateSensorEntity
      ent = OutputStateSensorEntity("sub1", 0, {"name": "MyDevice"}, "localPriority", False)
      assert ent._attr_name == "State: localPriority"
      assert ent._attr_entity_registry_enabled_default is False
  ```

- [ ] **Step 5: Run tests**

  ```bash
  pytest tests/test_properties.py tests/ -v
  ```

- [ ] **Step 6: Commit**

  ```bash
  git add custom_components/dsvdc4ha/sensor.py \
          custom_components/dsvdc4ha/__init__.py \
          tests/test_properties.py
  git commit -m "feat: expose Output description and state properties as diagnostic sensor entities"
  ```

---

## Task 11: Naming Confirmation Screens in Config Flows

Users should be able to confirm/edit the proposed names for HA devices and vdSD entities at the end of each creation flow. Add a name confirmation step before finalizing the subentry.

Scope:
- **Entity flow**: propose device name = HA device name, entity name = HA entity name
- **Device flow**: propose device name = HA device name, entity name = HA entity name
- **From-scratch flow**: derive from already-stated names (no extra screen needed — names are explicitly entered already)

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py`
- Modify: `custom_components/dsvdc4ha/translations/en.json`

- [ ] **Step 1: Add name confirmation step**

  In `config_flow.py`, add a new step `async_step_name_confirm` that shows pre-filled text fields:
  
  ```python
  async def async_step_name_confirm(self, user_input: dict | None = None):
      """Let the user confirm or edit device and entity names before saving."""
      if user_input is not None:
          # Apply user-edited names to current vdsd data
          if "device_name" in user_input:
              self._current_vdsd["displayId"] = user_input["device_name"]
          if "entity_name" in user_input:
              # Update the name field in the relevant vdSD component
              # (output name, or binary_input/sensor/button name based on what's configured)
              self._apply_entity_name(user_input["entity_name"])
          return await self._finalize_vdsd()
  
      # Propose names
      device_name = self._current_vdsd.get("displayId", self._current_vdsd.get("name", ""))
      entity_name = self._derive_entity_name_proposal()
  
      schema = vol.Schema({
          vol.Required("device_name", default=device_name): selector.TextSelector(),
          vol.Required("entity_name", default=entity_name): selector.TextSelector(),
      })
      return self.async_show_form(step_id="name_confirm", data_schema=schema)
  
  def _derive_entity_name_proposal(self) -> str:
      """Return a proposed entity name based on what's configured."""
      if self._current_output:
          return self._current_output.get("name", "Output")
      if self._current_binary_inputs:
          return self._current_binary_inputs[0].get("name", "Binary Input")
      if self._current_sensors:
          return self._current_sensors[0].get("name", "Sensor")
      if self._current_buttons:
          return self._current_buttons[0].get("name", "Button")
      return ""
  
  def _apply_entity_name(self, name: str) -> None:
      """Apply the confirmed entity name to the configured component."""
      if self._current_output:
          self._current_output["name"] = name
      elif self._current_binary_inputs:
          self._current_binary_inputs[0]["name"] = name
      elif self._current_sensors:
          self._current_sensors[0]["name"] = name
      elif self._current_buttons:
          self._current_buttons[0]["name"] = name
  ```

- [ ] **Step 2: Route entity flow and device flow through name_confirm**

  Find the step that currently calls `_finalize_vdsd()` (or equivalent) in the entity and device flows. Before finalizing, redirect to `name_confirm`:
  
  ```python
  # At the point where the flow would normally finalize (e.g., after model features step):
  return await self.async_step_name_confirm()
  ```

  Search for:
  ```bash
  grep -n "_finalize_vdsd\|async_step_finalize\|vdsd_overview.*next\|action.*next" \
    custom_components/dsvdc4ha/config_flow.py | head -20
  ```

- [ ] **Step 3: Add translations for name_confirm step**

  In `translations/en.json`, add:
  
  ```json
  "name_confirm": {
    "title": "Confirm Names",
    "description": "Review and confirm the proposed names for the HA device and entity.",
    "data": {
      "device_name": "Device name (shown in HA)",
      "entity_name": "Entity name (shown in HA)"
    }
  }
  ```

- [ ] **Step 4: Run tests**

  ```bash
  pytest tests/ -v
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add custom_components/dsvdc4ha/config_flow.py \
          custom_components/dsvdc4ha/translations/en.json
  git commit -m "feat: add name confirmation step to entity and device config flows"
  ```

---

## Task 12: Entity Selection in "From Device" Flow

When adding a device via the "from device" flow, the user should be able to select which of the device's entities to expose as vdSDs (currently all supported ones are used).

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py`
- Modify: `custom_components/dsvdc4ha/translations/en.json`

- [ ] **Step 1: Find where device entities are collected**

  ```bash
  grep -n "from_device\|device_id\|supported.*entit\|entit.*supported\|device_entity" \
    custom_components/dsvdc4ha/config_flow.py | head -20
  ```

- [ ] **Step 2: Add entity multi-select step**

  After selecting the HA device but before generating the vdSD plan, insert a step that lets the user choose which entities to include:
  
  ```python
  async def async_step_device_entity_select(self, user_input: dict | None = None):
      """Let the user select which device entities to expose as vdSDs."""
      if user_input is not None:
          selected_ids: list[str] = user_input.get("entity_ids", [])
          self._selected_entity_ids = selected_ids
          return await self._async_step_build_device_plan()
  
      # Build list of supported entity options
      from homeassistant.helpers import entity_registry as er
      from .entity_mapping import get_entity_mapping, SUPPORTED_DOMAINS
  
      ent_reg = er.async_get(self.hass)
      device_id = self._device_id  # stored from previous step
      options: list[selector.SelectOptionDict] = []
  
      for entry in ent_reg.entities.get_entries_for_device_id(device_id, include_disabled_entities=False):
          state = self.hass.states.get(entry.entity_id)
          domain = entry.domain
          device_class = state.attributes.get("device_class") if state else entry.device_class
          if get_entity_mapping(domain, device_class) is not None:
              friendly = state.attributes.get("friendly_name", entry.entity_id) if state else entry.entity_id
              options.append(
                  selector.SelectOptionDict(
                      value=entry.entity_id,
                      label=f"{friendly} ({domain})",
                  )
              )
  
      if not options:
          # No supported entities — skip the select step
          self._selected_entity_ids = None  # None = include all
          return await self._async_step_build_device_plan()
  
      schema = vol.Schema({
          vol.Required("entity_ids", default=[o["value"] for o in options]): selector.SelectSelector(
              selector.SelectSelectorConfig(options=options, multiple=True)
          ),
      })
      return self.async_show_form(step_id="device_entity_select", data_schema=schema)
  ```

- [ ] **Step 3: Filter entities in device plan builder**

  In `_async_step_build_device_plan` (or wherever the vdSD list is built from device entities), respect `self._selected_entity_ids`:
  
  ```python
  def _should_include_entity(self, entity_id: str) -> bool:
      if self._selected_entity_ids is None:
          return True  # None = include all (no filter step was shown)
      return entity_id in self._selected_entity_ids
  ```

- [ ] **Step 4: Route from device step through entity_select**

  Find the step in the device flow that transitions from device selection to plan building, and insert the `device_entity_select` step:
  
  ```bash
  grep -n "async_step_device\|_build_device_plan\|device_plan" custom_components/dsvdc4ha/config_flow.py | head -20
  ```

- [ ] **Step 5: Add translation**

  In `translations/en.json`:
  
  ```json
  "device_entity_select": {
    "title": "Select Entities to Expose",
    "description": "Choose which entities from '{device_name}' to expose as vdSDs in digitalSTROM. All supported entities are pre-selected.",
    "data": {
      "entity_ids": "Entities to expose"
    }
  }
  ```

- [ ] **Step 6: Run tests**

  ```bash
  pytest tests/ -v
  ```

- [ ] **Step 7: Commit**

  ```bash
  git add custom_components/dsvdc4ha/config_flow.py \
          custom_components/dsvdc4ha/translations/en.json
  git commit -m "feat: add entity multi-select step to 'from device' config flow"
  ```
