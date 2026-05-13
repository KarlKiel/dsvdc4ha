# dsvdc4ha — Refactor Findings

**Date:** 2026-05-13
**Scope:** Full codebase audit — correctness, consistency, completeness, logic, form
**Status:** All issues resolved ✅

---

## Summary

| Severity | Count | Status |
|---|---|---|
| Critical | 5 | ✅ All resolved |
| High | 4 | ✅ All resolved |
| Medium | 4 | ✅ All resolved |
| Low | 2 | ✅ All resolved |

---

## Critical Issues

### C1 — Duplicate `async_step_user` ✅ Fixed

**Resolution:** `DsvdcConfigFlow` now has a single `async_step_user` that aborts with `already_configured` when a hub entry exists, and routes to `async_step_hub` otherwise. Device creation is handled entirely by `VdsdSubentryFlowHandler`, making the routing simple and unambiguous.

### C2 — `CONF_ENTRY_TYPE` and `ENTRY_TYPE_HUB` missing from `const.py` ✅ Fixed

**Resolution:** Both constants added to [const.py](../../custom_components/dsvdc4ha/const.py). Tests updated to import them.

### C3 — Entity flow called methods from wrong class ✅ Fixed

**Resolution:** The entity creation flow (`creation_mode`, `entity_picker`, `entity_user_input`, `entity_channel_mapping`, `_build_entity_vdsd_and_continue`) was moved to `VdsdSubentryFlowHandler`, which has full access to all device-wizard steps.

### C4 — Entity flow in wrong class ✅ Fixed

**Resolution:** Entity flow now lives entirely in `VdsdSubentryFlowHandler`. `DsvdcConfigFlow` is hub-only. The architecture is:
```
"Add integration" → DsvdcConfigFlow → hub setup only
"Add device"      → VdsdSubentryFlowHandler → creation_mode → entity or scratch path
```

### C5 — Hub entry missing `CONF_ENTRY_TYPE` key ✅ Fixed

**Resolution:** `async_step_finalize_hub` now stores `{CONF_ENTRY_TYPE: ENTRY_TYPE_HUB, CONF_PORT: port}`. The `already_configured` check uses `e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_HUB` and now works correctly.

---

## High Issues

### H1 — `input_usage: 4` invalid for `BinaryInputUsage` ✅ Fixed

**Resolution:** Both `binary_sensor/problem` and `binary_sensor/running` entries in [entity_mapping.py](../../custom_components/dsvdc4ha/entity_mapping.py) changed to `input_usage: 0` (Generic).

### H2 — `_build_entity_vdsd_and_continue` used wrong field for `displayId` ✅ Fixed

**Resolution:** `displayId` and `model` now correctly use `self._display_id` (the device/model type name set from entity discovery). `self._device_name` (the friendly name) goes in the `name` field.

### H3 — `async_step_output_optional` was unreachable ✅ Fixed

**Resolution:** The `output` step schema now includes an `action` selector with `"next"` and `"output_optional"` options. `async_step_output_optional` on submit advances to `async_step_channel` or `async_step_channel_mapping` rather than looping back to `output`.

### H4 — `optional_settings` schema fields diverged from UI strings ✅ Fixed

**Resolution:** `strings.json` and `en.json` now define `hardwareVersion`, `hardwareGuid`, `vendorGuid`, `oemGuid` — matching the schema exactly. `deviceIcon16` removed.

---

## Medium Issues

### M1 — `strings.json` missing `config_subentries` section ✅ Fixed

**Resolution:** `strings.json` now contains the full `config_subentries.device` block with all device-wizard step strings, including the new entity flow steps.

### M2 — `en.json` duplicate `state_files` block ✅ Fixed

**Resolution:** Duplicate `state_files` block (lines 113–119 in old file) removed from `en.json`.

### M3 — `SubentryFlowResult` imported but unused ✅ Fixed

**Resolution:** Unused import removed from `config_flow.py`.

### M4 — Deprecated `asyncio.get_event_loop()` ✅ Fixed

**Resolution:** Both call sites updated to `await self.hass.async_add_executor_job(fn, *args)`.

---

## Low Issues

### L1 — `cover/damper` missing from design doc's supported entity types table ✅ Fixed

**Resolution:** Added to Section 10.3 of the design spec.

### L2 — `channel` step `action` field had no UI string ✅ Fixed

**Resolution:** `action` field label added to `channel` step in `strings.json` and `en.json`. Same fix applied to the `output` step.

---

## Root Cause Summary

The critical issues shared a common origin: the "Create from entity" feature was added to `DsvdcConfigFlow` (hub flow) during development, but the codebase had already been migrated to a subentry-based architecture where device creation lives in `VdsdSubentryFlowHandler`. The entity flow was never moved from the hub class to the subentry class. The duplicate `async_step_user` was a residue of an incomplete merge. All issues have been resolved and the test suite passes (40/40).
