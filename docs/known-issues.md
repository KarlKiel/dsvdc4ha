# Known Issues

Collected during testing. Not yet triaged or prioritized.

---

## UI / Visualization

### Integration logo not displayed in HA
**Status:** Resolved (PR #43)

`icon.png` / `icon@2x.png` added to `custom_components/dsvdc4ha/`. The integration logo now appears in the HA integration overview and entity detail views.

---

## Integration / Hub

### No automatic restart after connection loss
**Status:** Resolved (PR #43)

Auto-reconnect watchdog added to `HubCoordinator` with exponential backoff (5 s → 15 s → 30 s → 60 s → 120 s → 300 s). On disconnect, reconnect is attempted automatically; on success, all subentry devices are re-registered.

### No way to manually re-announce a device
**Status:** Resolved (PR #43)

A `ReannounceButtonEntity` (EntityCategory.CONFIG) is created per vdSD. Pressing it calls `force_reannounce_device()` which discards the device from the announced-set and re-announces it to dSS.

---

### vdSD config URL not pointing to device page
**Status:** Resolved (PR #43)

`configURL` is now set to `/config/devices/device/<unique_id>` for each vdSD device after platform setup, so the dSS configurator opens the correct HA device page.

---

## digitalSTROM / dS Side

### vdSD names too short in dS
**Status:** Investigated — not our code

The truncation is not happening in this integration or in pydsvdcapi. The name is sent in full; the dSS UI applies its own display limit. No fix needed on our side.

---

## Architecture

### Structure of config entries needs review
**Status:** Resolved (PR #43)

`HubConnectivitySensor` is associated with a `DeviceInfo` entry named `"vdc @ Home Assistant"` (identifier `(DOMAIN, entry.entry_id)`), creating the integration-level hub device. All hub-relevant entities (connectivity sensor) are grouped under this device. Per-vdSD entities are grouped under their own per-vdSD devices derived from `DsvdcBaseEntity`.

### Naming of devices and entities
**Status:** Resolved (PR #43)

A `name_confirm` step has been added to both the `from_entity` and `from_ha_device` config flows. It shows pre-filled text fields for device name and entity name, derived from the HA source device/entity. The `from_scratch` flow uses the names the user entered explicitly (device name from `device_info` step, vdSD name from `vdsd_creation` step) as HA names directly — no extra confirmation screen.

---

## Device-Specific Bugs

### Plug output configuration broken
**Status:** Resolved (PR #43)

- `onThreshold` is now only included for ON/OFF function outputs (function 0); the "no output" error is gone.
- `POWER_STATE` apply expression threshold corrected to `value > 0` (was incorrectly scaling 0/1 to 0/50%).
- dS → HA push for switch outputs now works via the corrected apply expression.

---

## Device Properties / Settings Exposure

### Device property groups not exposed as HA entities
**Status:** Resolved (PR #43)

`PropertySensorEntity` (hidden by default, `visible_default=False`) is created for every vdSD:

- **vdSD identity** (`Vdsd.get_properties()`) — EntityCategory.DIAGNOSTIC
- **Per binary input**: description (DIAGNOSTIC), settings (CONFIG), state
- **Per sensor input**: description (DIAGNOSTIC), settings (CONFIG), state
- **Per button input**: description (DIAGNOSTIC), settings (CONFIG), state
- **Output** (when present): description (DIAGNOSTIC), settings (CONFIG), state

Bidirectional write-back for settings properties is not yet implemented — entities are read-only for now.

---

## HA Entity Visibility

### Integration-generated entities should be hidden by default
**Status:** Resolved (PR #43)

All mirror entities (`ButtonSensorEntity`, `SensorInputEntity`, `OutputChannelEntity`, `BinaryInputEntity`, `PropertySensorEntity`) now set `_attr_entity_registry_visible_default = False`. Entities remain active and collect data but are not shown in the default HA dashboard view.

---


## Config Flow

### Binary sensor pre-selection defaults and field label
**Status:** Resolved (PR #43)

- The `bi_group` field label has been corrected.
- The binary sensor group pre-selection now defaults to `8` (Joker / undefined) in the from-scratch flow.
- All enum selectors consistently use `_select()` helper: LIST mode for ≤ 5 options, DROPDOWN for more — applied across all flow steps including the binary input step.

### No entity selection in "from device" flow
**Status:** Resolved (PR #43)

A `device_entity_select` step has been added to the `from_ha_device` flow. After selecting the HA device, the user sees a multi-select of all supported entities on that device and can choose which subset to expose as vdSDs.

### Manual callback bindings in custom device flow insufficient
**Status:** Resolved (PR #44)

A structured binding model has been implemented:

- **Transform registry** (`binding_transforms.py`): 10 named transforms (invert, scale_to_percent, clamp_0_100, etc.) using `v` as the value placeholder.
- **Binding compiler** (`binding_compiler.py`): Compiles `{source_attribute, transform}` → `push_expr` (HA→dS) and `{service, parameter, transform}` → `apply_expr` (dS→HA) at config-save time.
- **Push binding UI**: Source entity attribute + transform selection for output channel mappings.
- **Apply binding UI**: Domain/service/parameter + transform for dS→HA service calls on channel changes.
- **Binary input & sensor binding UI**: Source entity + optional attribute + transform for input callbacks.

### Manual settings layout — small enums not aligned
**Status:** Resolved (PR #43)

A `_select()` helper function now auto-selects `SelectSelectorMode.LIST` for enums with ≤ 5 options and `DROPDOWN` for larger enums, applied consistently across all config flow steps.
