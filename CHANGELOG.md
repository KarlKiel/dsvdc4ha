# Changelog

All notable changes to dSVDC for Home Assistant are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Changed
- `callsPresent` defaults to `true` in both manual and auto-detect button creation flows, consistent with the dS spec intent for most generic buttons.

### Fixed
- `vanish_device()` now cleans up stale `_unavailable_entities` entries for the removed subentry, preventing unbounded accumulation when devices are frequently reconfigured.
- Reconnect path (`_do_reconnect`) now calls `_backfill_missing_icons()` and `patch_vdsd_config_urls()` after re-establishing listeners, matching the initial setup path. Previously, devices missing icons at disconnect time would remain without icons for the rest of the session.
- `mired_to_kelvin` transform label corrected to clarify it is a pass-through (dS uses mired natively).

### Security
- `eval()` sandbox design and accepted risk are documented in a comment block above `_SAFE_EVAL_CONTEXT` in `listeners.py`.
- `apply_transform()` in `binding_transforms.py` now verifies the transform name is a known key in `TRANSFORMS` before evaluation, even though the name always originates from a `SelectSelector` restricted to those keys.
- MDI SVG icon fetches are now capped at 32 768 bytes. Responses larger than this are dropped with a warning. Real `@mdi/svg` icons are under 8 KB; the limit gives a 4× safety margin while blocking oversized payloads from a compromised CDN.

### Refactored
- All deferred imports moved to module level across `config_flow.py`, `sensor.py`, `listeners.py`, and `button_translator.py`.
- `assert` precondition guards replaced with explicit `if`-guards and early returns throughout `api.py`.
- `resolve_vdsd_plan()` `device_name` parameter removed (value already embedded in the plan).
- Duplicate 100-line entity-choices schema block extracted into a shared `_build_entity_choices_schema()` helper in `config_flow.py`.
- Dynamic `getattr` step dispatch replaced with an explicit allowlist frozenset.
- Dead code removed: `ENTRY_TYPE_DEVICE` constant, `"active": True` fields in all vdSD config dicts.
- MDI SVG cache moved from `config_flow.py` to `_icon_utils.py` as a 256-entry LRU `OrderedDict`.
- File-path comment removed from `unit_conversion.py` (redundant; git tracks the path).
- `_eval_push` renamed to `eval_push` (public helper, referenced from `sensor.py`).

### Tests
- Added `tests/test_button_translator.py` with 24 tests covering all three ButtonEventTranslator source modes (binary sensor, button entity, event entity), hold/tip/click discrimination, auto hold-end, and cleanup.

---

## [0.2.0] — 2026-05

### Added
- **Three device creation paths:**
  - *From HA Entity* — maps a single entity to a vdSD using the built-in entity-mapping table; prompts only where a genuine choice exists.
  - *From HA Device* — auto-groups all supported entities on a HA device into vdSD proposals; multi-entity select, model feature confirmation, name confirmation.
  - *From Scratch* — fully manual wizard covering device info, vdSDs, buttons, binary inputs, sensor inputs, outputs, and per-channel bindings.
- **Structured binding UI** — push (HA → dS) and apply (dS → HA) bindings are configured as structured dicts in the UI, compiled at save time into sandboxed Python expressions. Named transform registry with 10 built-in transforms.
- **Binary input and sensor callback bindings** — map dS binary-input and sensor callbacks to HA service calls via a structured UI step.
- **Auto-reconnect watchdog** — exponential backoff (5 s → 15 s → 30 s → 60 s → 120 s → 300 s) with full listener re-registration on reconnect.
- **dSS connection monitoring** — binary sensor entity tracking the dSS connection state; becomes unavailable when the dSS disconnects.
- **MDI icon resolution** — fetches MDI SVG icons, renders to PNG with cairosvg, and caches; falls back to bundled 16×16 PNG icons for 61 common MDI slugs.
- **Property sensors** — hidden diagnostic sensor entities exposing Output settings properties (description, state, etc.) for each vdSD output.
- **Mirror entity support** — output mirror entities use `entity_registry_visible_default = False` (hidden but active); never disabled.
- **Per-vdSD config URLs** — each virtual device's `configURL` points to the corresponding HA device page.
- **Re-announce button** — `EntityCategory.CONFIG` button entity per vdSD to force re-announcement to the dSS.
- **Entity registry listener** — reacts to entity disable, enable, and deletion events without requiring a restart.
- **Sensor unit conversion** — automatic HA → dS unit conversion for all sensor types (temperature, pressure, energy, etc.) using a conversion table covering 50+ unit pairs.
- **Name confirmation step** — both the entity and device creation flows show a final name-confirmation screen before committing.
- **pydsvdcapi 0.9.0** — device lifecycle state management (`DeviceLifecycleState`) with automatic INACTIVE/ACTIVE transitions when entities become unavailable.
- Multi-vdSD support per physical device (from-device flow).
- Integration icon (`icon.png` / `icon@2x.png`) for display in the HA integrations list.

### Changed
- Buttons default to the Joker group (black, group 8) and skip the group-choice screen; the group can be reconfigured in the dSS Configurator.
- vdSD names always combine the HA device name and entity friendly name for clarity in the dSS Configurator.
- Mirror entities use `entity_registry_visible_default = False` instead of `enabled_default = False` — entities remain active (polled/pushed) but are hidden from the default HA entity list.

### Fixed
- Numerous config flow edge cases discovered during end-to-end testing (see git history for details).
- Correct `cbar → hPa` conversion factor (1 cbar = 10 hPa).
- `POWER_STATE` apply_expr threshold and `onThreshold` restriction to ON_OFF outputs.
- Port released on stop by preventing `VdcHost` from closing the shared Zeroconf instance.

---

## [0.1.0] — 2026-05 (initial implementation)

Initial scaffold:
- HACS custom integration structure (`manifest.json`, `const.py`, `strings.json`).
- Hub config flow (port selection) and hub setup/unload/remove lifecycle.
- `DsvdcApi` wrapping pydsvdcapi: device management, input reporting, output callbacks.
- `HubCoordinator` delegating to `DsvdcApi`.
- Basic entity platform (`SensorInputEntity`, `BinarySensorInputEntity`).
- mDNS announcement of VDC host and vDC to the dSS.
