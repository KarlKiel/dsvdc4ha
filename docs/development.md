# Development Guide

## Repository Layout

```
dsvdc4ha/
├── custom_components/dsvdc4ha/   # Integration source
├── tests/                        # pytest test suite
├── tools/                        # Audit and Excel generator scripts
├── scripts/                      # Icon generation script
├── docs/                         # This documentation
├── documents/                    # ha_vdsd_mapping.xlsx (entity mapping spec)
├── requirements_test.txt         # Test dependencies
└── venv/                         # Local Python virtual environment
```

---

## Environment Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements_test.txt
```

---

## Running Tests

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

All 399 tests should pass. The test suite uses `pytest-homeassistant-custom-component` which provides HA fixtures and stubs.

Two `RuntimeWarning: coroutine … was never awaited` warnings are expected from the test harness garbage collector — they are not errors in integration code.

---

## Test File Map

| Test file | What it covers |
|---|---|
| `test_api.py` | DsvdcApi device add/announce/vanish lifecycle |
| `test_binding_compiler.py` | push_expr and apply_expr compilation from structured bindings |
| `test_binding_transforms.py` | Each named transform's push evaluation |
| `test_config_flow.py` | Hub flow and device sub-entry flow steps |
| `test_coordinator.py` | HubCoordinator start/stop delegates to API |
| `test_device_grouper.py` | Entity→VdsdPlan grouping logic |
| `test_entities.py` | Entity class-level visibility defaults |
| `test_entity_mapping.py` | entity_mapping.py values match Excel spec rows |
| `test_entity_mapping_bindings.py` | push_expr/apply_expr in mapping compile correctly |
| `test_icon_utils.py` | MDI icon resolution and fallback |
| `test_init.py` | _build_entity_index and entity-registry listener |
| `test_light_mapping.py` | Light channel derivation from color modes |
| `test_listeners.py` | push_expr eval, apply_expr eval, seed_initial_values, sensor unit conversion, _light_apply |
| `test_mapping_excel.py` | Excel schema columns match code |
| `test_properties.py` | PropertySensorEntity uid suffixes and entity categories |
| `test_reannounce.py` | ReannounceButtonEntity fires force_reannounce_device |
| `test_sensor.py` | ButtonSensorEntity, SensorInputEntity, OutputChannelEntity state management |
| `test_unit_conversion.py` | convert_sensor_value for all sensor types and unit strings |

---

## Adding a New HA Entity Type

1. Add a row to `documents/ha_vdsd_mapping.xlsx` (confirm with the project owner before modifying).
2. Add the corresponding entry to `entity_mapping.py`. Follow the existing pattern for the entity's domain.
3. If the entity needs unit conversion, add it to `unit_conversion.py`.
4. Run `python tools/audit_mapping.py` to check alignment.
5. Run `python tools/generate_mapping_excel.py` to regenerate the Excel from updated code if needed.
6. Add/update tests in `test_entity_mapping.py` and `test_unit_conversion.py`.

---

## Adding a New Transform

1. Add an entry to `TRANSFORMS` in `binding_transforms.py`:
   ```python
   "my_transform": {
       "label": "Human readable label",
       "push_expr": "some_expr_using_v",
       "apply_expr": "some_expr_using_v",
   }
   ```
2. Add a test in `test_binding_transforms.py`.
3. The transform will automatically appear in the config flow UI.

---

## Working with Git Worktrees

Feature branches are developed in `.worktrees/` (git-ignored). The standard workflow:

```bash
# Create isolated workspace
git worktree add .worktrees/my-feature -b feat/my-feature

# Work in the worktree
cd .worktrees/my-feature
# ... make changes, run tests, commit ...

# Merge back from repo root
cd /path/to/dsvdc4ha
git merge feat/my-feature --no-ff
git worktree remove .worktrees/my-feature
git worktree prune
git branch -d feat/my-feature
```

---

## pydsvdcapi Integration Points

`api.py` is the **only file** that imports pydsvdcapi directly. All other modules interact with dS through `DsvdcApi` methods. This isolates pydsvdcapi version changes to a single file.

Key pydsvdcapi objects used:

| Object | Purpose |
|---|---|
| `VdcHost` | TCP server + mDNS advertisement |
| `Vdc` | Virtual Device Connector container |
| `Device` | Group of vdSDs with a shared dSUID |
| `Vdsd` | Single virtual dS Device |
| `ButtonInput` | dS button with click/action reporting |
| `BinaryInput` | dS binary contact with boolean/extended value |
| `SensorInput` | dS sensor with float value push |
| `Output` / `OutputChannel` | dS output channel (dimmable, shade, switch, etc.) |

pydsvdcapi version is pinned in `manifest.json` → `requirements`. Version checks and auto-installation happen in `async_setup()`.

---

## Expression Security

`eval()` is used in three places (`listeners.py`) and one place (`binding_transforms.py`) to evaluate push/apply expressions at runtime. All calls use a restricted context:

```python
_SAFE_EVAL_CONTEXT = {
    "__builtins__": {},
    "round": round, "float": float, "int": int,
    "abs": abs, "min": min, "max": max,
    "_norm": ..., "_denorm": ..., "_light_apply": ...,
}
```

Setting `__builtins__` to `{}` prevents access to `__import__`, `open`, `exec`, and other dangerous builtins. Expressions are compiled by the config flow from user-entered structured bindings (not from raw user text in the expression field), which limits attack surface. The `# noqa: S307` comment suppresses the security linter warning at each call site.

---

## Icon Pipeline

Icons for vdSDs are resolved in `_icon_utils.py`:

1. Check for a MDI icon matching the HA entity's domain + device class.
2. If found, attempt to render the MDI SVG to a 16×16 PNG via `cairosvg`.
3. If cairosvg fails or no MDI match, fall back to a bundled PNG from `icons/`.
4. The resulting PNG bytes are stored in vdSD config data as base64 (`icon_data_b64`) and passed to pydsvdcapi as `device_icon_16`.

Bundled icons are generated by `scripts/generate_icons.py` from MDI SVG sources.

---

## State File Migration

pydsvdcapi persists device state to a YAML file (`dsvdc4ha/host_state` under the HA config directory). On startup, `DsvdcApi._purge_corrupted_state_files()`:

1. Migrates any legacy file from `.storage/dsvdc4ha_host_state` to the new path.
2. Removes any file that fails `yaml.safe_load` (e.g., old Python-object tags from AwesomeVersion serialisation).
3. Patches the saved port to match the current config, avoiding pydsvdcapi's DEFAULT_VDC_PORT override.
