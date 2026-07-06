# QA Findings — dsvdc4ha

**Examination date:** 2026-07-06
**Branch:** main
**Test suite:** 416 tests at examination → 443 tests after CQ1-CQ13 fixes, 0 failures

---

## Summary

| Area | Findings | Critical | Important | Minor |
|------|----------|----------|-----------|-------|
| Code Quality | 13 | 2 | 5 | 6 |
| Security | 4 | 0 | 3 | 1 |
| Performance | 4 | 0 | 2 | 2 |
| Consistency | 6 | 0 | 3 | 3 |
| Documentation | 6 | 0 | 1 | 5 |
| **Total** | **33** | **2** | **14** | **17** |

---

## Code Quality

### CQ1 — `assert` used as runtime guard (Critical) — ✅ Fixed

**Files:** `api.py` — 6 `report_*` methods, `add_device()`

**Problem:** Precondition checks like `assert self._host is not None` are disabled under `python -O` (optimized mode). If HA ever runs with optimization flags, these silently become no-ops and subsequent code operates on `None`, causing `AttributeError` deep in pydsvdcapi instead of a meaningful failure at the boundary.

**Affected methods:** `report_button_click`, `report_channel_value`, `report_sensor_value`, `report_binary_input`, `force_reannounce_device`, `add_device`

**Fix:** Replace with early returns or raise `RuntimeError`:
```python
if self._host is None:
    _LOGGER.warning("report_* called but host is not connected")
    return
```

---

### CQ2 — Private attribute access on pydsvdcapi internals (Critical) — ✅ Fixed

**File:** `api.py`

**Problem:** Five internal attributes of pydsvdcapi's `VdcHost` are accessed directly: `host._port`, `host._dsuid`, `host._zeroconf`, `host._service_info`, `host._on_session_ready`. These are implementation details with no stability guarantee. A pydsvdcapi minor version bump that renames or restructures these will break the integration silently at runtime.

**Fix:** Request public accessors in pydsvdcapi, or at minimum add a version guard comment so future upgrades surface the breakage early.

---

### CQ3 — `config_flow.py` at 2341 lines with DRY violations (Important) — ✅ Fixed

**File:** `config_flow.py`

**Problem:** The file is 2341 lines — effectively too large to hold in context. Two pairs of methods share near-identical schema-building blocks:
- `async_step_entity_user_input` and `async_step_device_entity_user_input` both build 100+ line schema dicts with identical field definitions for `sensor_function`, `sensor_type`, `output_usage`, `function`, `has_tilt`, etc.
- `async_step_channel_push_binding` / `async_step_channel_apply_binding` repeat the same attribute and service option lists inline.

**Fix:** Extract a `_build_entity_options_schema(entity_info)` helper and shared option-list constants to reduce the file to a manageable size. This is a refactoring task, not an urgent fix.

---

### CQ4 — Deferred imports repeated across 4+ config_flow step methods (Important) — ✅ Fixed

**File:** `config_flow.py`

**Problem:** `from .binding_transforms import TRANSFORM_OPTIONS` appears inside the body of at least four `async_step_*` methods. This was presumably done to avoid a circular import, but it means the same deferred import executes every time a config flow step is visited. If the circular import has since been resolved (or can be), these should be moved to the module level. If not, the reason should be documented.

**Fix:** Verify if circular import is still necessary. If yes, add a comment explaining it. If no, move to module level.

---

### CQ5 — `ENTRY_TYPE_DEVICE` constant defined but never used (Important) — ✅ Fixed

**File:** `const.py:23`

**Problem:** `ENTRY_TYPE_DEVICE = "device"` is defined but never referenced in production code. It appears only in historical plan documents. Devices are now managed as subentries, making this constant dead code.

**Fix:** Remove the constant and confirm nothing in the test suite depends on it directly.

---

### CQ6 — `"active": True` field stored in vdSD config but not consumed (Important) — ✅ Fixed

**Files:** `device_grouper.py:180`, `entity_mapping.py` (multiple mapping dicts)

**Problem:** Every vdSD config dict written to HA config entries includes `"active": True`. Since pydsvdcapi 0.9.0 removed the settable `active` property, this field is stored but never acted on by either pydsvdcapi or the integration. It wastes config storage and could mislead future developers into thinking the field has meaning.

**Fix:** Remove `"active": True` from `resolve_vdsd_plan()` in `device_grouper.py` and from all mapping dicts in `entity_mapping.py`.

---

### CQ7 — `_VDC_SERVICE_TYPE` constant placement breaks import ordering (Minor) — ✅ Fixed

**File:** `api.py:14`

**Problem:** `_VDC_SERVICE_TYPE = "_dsreg._tcp.local."` is defined at line 14, between the logging setup and the pydsvdcapi imports. This breaks the conventional import-then-constants ordering and makes the file harder to scan.

**Fix:** Move to after all imports.

---

### CQ8 — `import time` inside hot-path callback methods (Minor) — ✅ Fixed

**File:** `button_translator.py:168, 179`

**Problem:** `import time` appears inside `_bs_on()` and `_bs_off()`, both called on every binary sensor state change. Python caches module imports after the first load, so there is no I/O cost after startup, but the dict lookup still executes on every call and the intent is confusing to readers.

**Fix:** Move `import time` to the top of `button_translator.py`.

---

### CQ9 — `from .unit_conversion import DS_TARGET_UNIT` inside `__init__` (Minor) — ✅ Fixed

**File:** `sensor.py:139`

**Problem:** Module import inside `SensorInputEntity.__init__`. This runs once per entity creation, not on the hot path, but is still non-idiomatic.

**Fix:** Move to top-level import. If the concern was circular imports, add a comment.

---

### CQ10 — `from .listeners import _eval_push` inside hot-path method (Minor) — ✅ Fixed

**File:** `sensor.py:212` — `OutputChannelEntity._compute_value()`

**Problem:** Deferred import of a private function (`_eval_push`) inside a method called on every state change. Accessing a private function from a sibling module is also an encapsulation concern — `_eval_push` should either be promoted to a public helper or moved to a shared `eval_helpers.py`.

**Fix:** Move import to module level and consider making `_eval_push` a named public function.

---

### CQ11 — `device_name` parameter unused in `resolve_vdsd_plan` (Minor) — ✅ Fixed

**File:** `device_grouper.py:162`

**Problem:** The `device_name` parameter is accepted for API symmetry but suppressed with `# noqa: ARG001`. The name is already embedded in `plan.name` by `compute_vdsd_plan`, so the parameter is structurally unnecessary. Keeping it with a noqa suppression adds noise.

**Fix:** Either remove the parameter and update call sites in `config_flow.py`, or document clearly why it must remain part of the signature.

---

### CQ12 — Dynamic step dispatch via string formatting (Minor) — ✅ Fixed

**File:** `config_flow.py:1675`

**Problem:** `getattr(self, f"async_step_{return_step}")()` dispatches to a config flow step by constructing the method name from an internal state variable. If `return_step` is ever influenced by user input or stored config data, this opens an unintended method dispatch surface. Currently it appears safe, but the pattern is fragile.

**Fix:** Use an explicit dispatch dict `{"step_name": self.async_step_foo, ...}` instead of `getattr`.

---

### CQ13 — No dedicated tests for `button_translator.py` (Minor) — ✅ Fixed

**File:** `button_translator.py` (373 lines of timing state machine logic)

**Problem:** This is the most complex non-trivial module in the codebase — a timing state machine implementing dS click type discrimination from HA entity events — with no dedicated test file. The `test_listeners.py` file covers some button paths indirectly, but none of the edge cases in `ButtonEventTranslator` (hold sequence cancellation, mixed tip/click detection, auto hold-end, event entity mapping) are directly exercised.

**Fix:** Create `tests/test_button_translator.py` covering at minimum: single tip, double tip, hold start/repeat/end, click discrimination, event entity mapping, and cleanup/unsub.

---

## Security

### S1 — `eval()` used for push/apply expressions (Important)

**File:** `listeners.py:83, 92, 103`

**Problem:** Output channel state changes are processed by `eval(push_expr, _SAFE_EVAL_CONTEXT)` where `_SAFE_EVAL_CONTEXT = {"__builtins__": {}, "round": round, "float": float, ...}`. The expressions are user-configured at setup time, not received from the network, so the attack surface is limited to the local HA instance. However, sandbox escapes via `__class__.__mro__` and similar chains are possible if `__builtins__: {}` is the only guard — Python builtins restrictions can be bypassed through object introspection in some Python versions.

**Note:** This is the only practical architecture given the use case (user-defined expressions for channel value mapping), but the risk should be acknowledged.

**Recommendation:** Document the security model explicitly. Consider `ast.literal_eval` or a restricted DSL for simple passthrough cases, reserving `eval` for complex expressions only.

---

### S2 — `eval()` in `binding_transforms.apply_transform()` (Important)

**File:** `binding_transforms.py`

**Problem:** `apply_transform()` also uses `eval()` with a minimal sandbox. The transforms are loaded from the hardcoded `TRANSFORMS` dict, so at present no user-supplied string reaches `eval()` directly. However, if a transform entry were ever user-editable (e.g., via a future config option), this would become a direct injection vector.

**Recommendation:** Audit every path that calls `apply_transform()` to confirm the transform name always comes from the hardcoded `TRANSFORMS` dict and never from user input.

---

### S3 — `_MDI_SVG_CACHE` unbounded growth (Important)

**File:** `config_flow.py`

**Problem:** MDI SVG icons are fetched from an external URL and cached in `_MDI_SVG_CACHE` (a module-level dict) with no size limit. In a long-running HA instance that processes many config flows across many entity types, this cache grows indefinitely. In theory, a compromised MDI CDN could serve arbitrarily large payloads that fill memory.

**Fix:** Cap the cache with `maxlen` (use `collections.OrderedDict` with eviction) or set a maximum SVG byte size guard before caching.

---

### S4 — `eval()` sandbox inconsistency between modules (Minor)

**Files:** `listeners.py`, `binding_transforms.py`

**Problem:** `_SAFE_EVAL_CONTEXT` in `listeners.py` allows `round, float, int, abs, min, max, _norm, _denorm, _light_apply`. `apply_transform()` in `binding_transforms.py` uses a separate context that includes `str` but lacks `_norm`/`_denorm`. The two sandboxes serve related purposes but are independently maintained, risking drift.

**Fix:** Consolidate into a single `_eval_context()` factory in a shared module, or at minimum document the intentional differences.

---

## Performance

### P1 — `_unavailable_entities` dict never cleaned up in `vanish_device()` (Important)

**File:** `api.py`

**Problem:** When a device is vanished (removed from pydsvdcapi), `_unavailable_entities` entries for that device are not removed. In a system where devices are frequently added and removed (e.g., users reconfiguring mappings), these stale entries accumulate indefinitely.

**Fix:** In `vanish_device()`, after removing the device from `_devices`, purge all keys `(entry_id, idx)` from `_unavailable_entities` that belong to the vanished subentry.

---

### P2 — `from .unit_conversion import convert_sensor_value` per event (Important)

**File:** `listeners.py:193`

**Problem:** The import is executed inside `_on_sensor_state` which fires on every sensor state change. Python caches the module after first load, so no disk I/O occurs, but `sys.modules` dict lookup and local name binding happen on every callback invocation. This is annotated with `# noqa: PLC0415` but no explanation of why it cannot be top-level.

**Fix:** Move to module level. If there is a circular import concern, document it.

---

### P3 — PNG icon cache loaded at import time (Minor)

**File:** `_icon_utils.py:10-14`

**Problem:** All bundled PNG files are read from disk and base64-encoded into `_ICON_CACHE` at module import time. This is intentionally I/O-free at runtime, which is correct. However, it adds to HA startup latency proportional to the number of bundled icons. Currently bounded by the number of files in `icons/`, so this is low risk but worth monitoring as the icon set grows.

**Recommendation:** If icon count grows beyond ~200 files, switch to lazy loading.

---

### P4 — Two separate icon caching systems (Minor)

**Files:** `_icon_utils.py`, `config_flow.py`

**Problem:** Bundled PNG icons use `_ICON_CACHE` (bounded, load-time). Fetched MDI SVGs use `_MDI_SVG_CACHE` (unbounded, runtime). These serve related purposes but are maintained separately, making cache size management inconsistent.

**Recommendation:** Consolidate icon caching into `_icon_utils.py` so eviction policy can be applied uniformly.

---

## Consistency

### C1 — `_do_reconnect()` skips icon backfill (Important)

**File:** `coordinator.py`

**Problem:** `async_setup_entry()` in `__init__.py` calls both `_backfill_missing_icons()` and `patch_vdsd_config_urls()` after setting up listeners. `_do_reconnect()` in `coordinator.py` calls `setup_input_listeners` and `setup_output_listeners` but does **not** call either post-setup function. After a reconnect, any vdSDs that had not yet received icons before the disconnect will remain without icons for the rest of the session.

**Fix:** Either call `_backfill_missing_icons()` and `patch_vdsd_config_urls()` from `_do_reconnect()`, or extract a shared `_post_connect_setup()` coroutine used by both paths.

---

### C2 — `mired_to_kelvin` transform has misleading label (Important)

**File:** `binding_transforms.py`

**Problem:** The `mired_to_kelvin` transform entry carries the label `"HA color_temp (mired) → dS color temperature (mired)"`. The source and target are labeled identically (both "mired"), which contradicts the transform name. Either the label is wrong or the transform is a no-op passthrough masquerading as a conversion.

**Fix:** Verify the actual behavior and correct the label to accurately describe the input/output units.

---

### C3 — `callbackType: "detect_clicks"` stored in config but not in button callback handling (Important)

**File:** `device_grouper.py:231`

**Problem:** Auto-detected button entities created by the device-picker flow use `"callbackType": "detect_clicks"` (from device_grouper), but the entity-picker manual flow stores `"callbackType": user_input.get("callbackType", "clickTypes")` (from config_flow.py). The listeners code must correctly distinguish these modes. If `"detect_clicks"` is not handled identically in both paths, one flow will silently fail to wire button listeners.

**Fix:** Audit `listeners.py` button setup to confirm `"detect_clicks"` from both code paths is handled identically.

---

### C4 — Sensor `_convert()` re-imports on every call (Minor)

**File:** `sensor.py:147-152`

**Problem:** `SensorInputEntity._convert()` contains `from .unit_conversion import convert_sensor_value` on every call. Combined with CQ9 and CQ10, there are three separate per-call deferred imports for related concerns in `sensor.py`. Pattern is inconsistent with the rest of the codebase.

**Fix:** Consolidate with CQ9 fix — move all unit_conversion imports to module level.

---

### C5 — `"callsPresent": True` default differs between manual and auto-detect flows (Minor)

**Files:** `config_flow.py:1837`, `device_grouper.py:229`

**Problem:** Manual button creation in `async_step_button` defaults `callsPresent` to `True`. Device-picker flow in `device_grouper.py` also uses `callsPresent: False`. The dS spec treats `callsPresent = True` as "pressing this button sets the room to occupied", which is a significant behavioral default — most generic buttons should probably default to `False`.

**Fix:** Align both flows to the same default and document the reasoning.

---

### C6 — `ENTRY_TYPE_HUB` used without corresponding `ENTRY_TYPE_DEVICE` (Minor)

**File:** `const.py`

**Problem:** `ENTRY_TYPE_HUB = "hub"` is actively used; `ENTRY_TYPE_DEVICE = "device"` is dead code (finding CQ5). Having one live and one dead constant of the same pattern is confusing.

**Fix:** Remove `ENTRY_TYPE_DEVICE` along with CQ5 fix.

---

## Documentation

### D1 — No CHANGELOG.md (Important)

**Problem:** The project has no changelog. For a HACS integration, users upgrading between versions have no way to understand what changed or whether breaking changes are involved. The version is currently `0.2.0` in `manifest.json`.

**Fix:** Create `CHANGELOG.md` at the project root following Keep a Changelog format. At minimum document breaking changes from 0.1.x → 0.2.0.

---

### D2 — No dedicated tests for `button_translator.py` (see CQ13) (Minor)

Referenced in Code Quality as CQ13. The documentation angle: no developer documentation describes the timing state machine design or references the dS spec tables the constants are derived from (though the code does reference "dS spec Table 8" in comments, which is good).

---

### D3 — `docs/superpowers/plans/` contains 15+ outdated historical plans (Minor)

**Path:** `docs/superpowers/plans/`

**Problem:** This directory contains internal implementation planning artifacts from the project's development. They are outdated by definition (completed plans) and are unlikely to be useful to contributors or users. They add noise to the repository and appear in GitHub's file tree.

**Fix:** Either move to a separate `docs/internal/` path not shown prominently, or delete the older plans and retain only active ones.

---

### D4 — `unit_conversion.py` line-1 file-path comment (Minor)

**File:** `unit_conversion.py:1`

**Problem:** `# custom_components/dsvdc4ha/unit_conversion.py` — the file declares its own path as a comment. This is redundant metadata (git already knows the path) and will become stale if the file is moved.

**Fix:** Remove.

---

### D5 — `hacs.json` missing recommended fields (Minor)

**File:** `hacs.json`

**Problem:** The current `hacs.json` only has `name` and `render_readme`. HACS recommends also specifying `filename` (for custom component discovery), `homeassistant` (minimum HA version), and `country` (for regional integrations). Without `filename`, HACS falls back to domain-name discovery which may behave unexpectedly on some HACS versions.

**Fix:**
```json
{
  "name": "dsvdc4ha",
  "render_readme": true,
  "filename": "custom_components/dsvdc4ha",
  "homeassistant": "2024.1.0"
}
```

---

### D6 — `documents/` and `docs/` serve overlapping purposes (Minor)

**Problem:** `documents/` contains reference PDFs, Word docs, and the Excel mapping file. `docs/` contains markdown documentation. A new contributor may not know which folder to look in or add to.

**Fix:** Add a brief `README.md` at the project root (or in `docs/`) clarifying the distinction: `docs/` for markdown documentation, `documents/` for reference materials.

---

## Positive Findings

The following areas were examined and found to be well-implemented:

- **Entity visibility:** All mirror entities correctly use `_attr_entity_registry_visible_default = False`, never `enabled_default = False`. Mirrors stay active while hidden by default — correct per design intent.
- **Test coverage:** 416 tests across 20 test files covering all major modules. Good use of `pytest-asyncio` and HA test helpers.
- **`_SAFE_EVAL_CONTEXT` in listeners.py:** `__builtins__: {}` is the correct starting point for sandboxed eval. The explicit allowlist is minimal and intentional.
- **`ButtonEventTranslator`:** Timing constants are clearly cross-referenced to dS spec Table 8. The hold/tip/click discrimination logic is well-structured.
- **`DsvdcBaseEntity`:** Clean base class; `_attr_has_entity_name = True` and `_attr_should_poll = False` correctly set as class attributes.
- **`_unavailable_entities` design:** Using a `set[str]` per `(entry_id, vdsd_idx)` correctly handles multiple entities mapping to the same vdSD — lifecycle goes INACTIVE on first unavailable, ACTIVE only when all recover.
- **`device_grouper.py`:** Pure Python with no HA dependency; correctly separated from config flow logic and independently testable.
- **`binding_compiler.py`:** Small, focused, well-tested.
- **Import guards in `__init__.py`:** `DeviceLifecycleState` is imported inside the callback function body to defer pydsvdcapi import until after async setup ensures the package is installed.
