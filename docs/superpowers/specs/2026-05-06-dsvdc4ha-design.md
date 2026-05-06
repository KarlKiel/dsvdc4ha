# dsvdc4ha — Integration Design Spec

**Date:** 2026-05-06
**Status:** Approved

---

## 1. Overview

`dsvdc4ha` is an asynchronous Home Assistant custom integration that uses the `pydsvdcapi` library to expose existing HA entities as virtual digitalStrom devices (vdSDs) inside a connected digitalStrom system (DSS).

The integration acts as a **translation layer**, not a device driver. Real devices and their entities already exist in HA. This integration maps their values into the dS protocol so they can be monitored and controlled from within the DSS.

### Key goals
- Announce a `vdc-host` and a `vDC` to the DSS via pydsvdcapi and zero-conf
- Allow users to define physical devices, each containing one or more vdSDs
- Map HA entity state changes (inputs) and HA actions (output write-back) to dS callback variables
- Persist all configuration in HA config entries; restore fully on restart
- Clean teardown when config entries are removed

---

## 2. Architecture

```
DSS ◄──── pydsvdcapi ────► api.py ◄──── coordinator.py  (hub lifecycle)
                                  │
                                  ├──── sensor.py         (input + output channel mirrors)
                                  └──── binary_sensor.py  (boolean binary inputs)
```

### Layers

| Layer | File | Responsibility |
|---|---|---|
| Library wrapper | `api.py` | All pydsvdcapi calls. Coordinator and entities never import pydsvdcapi directly. |
| Hub lifecycle | `coordinator.py` | Manages VDC-HOST + VDC connection: setup, announcement, teardown. |
| Config flow | `config_flow.py` | Hub flow (port) and device sub-flow (multi-step). |
| Entity base | `base_entity.py` | Shared HA entity base class for all integration entities. |
| Platforms | `sensor.py`, `binary_sensor.py` | Entity creation and state management per platform. |
| Constants | `const.py` | Domains, entry types, enum mappings, platform list. |

---

## 3. Project File Structure

```
dsvdc4ha/                                  # repository root
├── hacs.json                              # HACS metadata
├── README.md
├── LICENSE
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-05-06-dsvdc4ha-design.md
├── tests/                                 # test suite (repo root, standard HA convention)
│   ├── __init__.py
│   ├── conftest.py                        # shared fixtures (mock hass, mock pydsvdcapi)
│   ├── test_config_flow.py               # hub flow + device flow steps
│   ├── test_coordinator.py               # hub setup, teardown, restart restore
│   └── test_sensor.py                    # entity state updates, callback forwarding
└── custom_components/
    └── dsvdc4ha/
        ├── __init__.py                    # async_setup_entry / async_unload_entry / async_remove_entry
        ├── manifest.json                  # domain, requirements (pydsvdcapi), config_flow, iot_class
        ├── const.py                       # DOMAIN, entry type constants, enum maps
        ├── strings.json                   # UI strings (authoritative, mirrored by translations/)
        ├── config_flow.py                 # hub flow + device sub-flow
        ├── api.py                         # pydsvdcapi wrapper
        ├── coordinator.py                 # HubCoordinator
        ├── base_entity.py                 # DsvdcBaseEntity
        ├── sensor.py                      # sensor platform
        ├── binary_sensor.py               # binary_sensor platform
        ├── translations/
        │   └── en.json                    # English UI strings
        └── vdc.png                        # default vdSD icon (16x16 PNG)
```

---

## 4. Config Entry Model

### 4.1 Hub entry (`entry_type = "hub"`)

One per HA instance. Created by the initial "add integration" flow.

**Stored data:**
```json
{
  "entry_type": "hub",
  "port": 8765
}
```

**On setup:** Instantiates `HubCoordinator` → calls `api.py` to create VDC-HOST and VDC, announce via zero-conf. Validates handshake with DSS. Stores coordinator in `hass.data[DOMAIN]["hub"]`.

**No HA devices or entities are created for the hub entry.**

**On unload:** Tears down coordinator cleanly (does not vanish devices — that is reserved for removal).

**On removal:** Calls pydsvdcapi to de-announce VDC, vanish all child devices, say goodbye, close connection.

### 4.2 Device entries (`entry_type = "device"`)

One per physical device. Created via the "Add" button on the integration page.

**Stored data:**
```json
{
  "entry_type": "device",
  "name": "Livingroom Ceiling Lamp",
  "vendorName": "Occhio",
  "displayId": "Lunanova",
  "vdsds": [
    {
      "displayId": "Lunanova PowerUnit",
      "primaryGroup": 1,
      "model": "Lunanova PowerUnit",
      "vendorName": "Occhio",
      "modelVersion": "v1.0",
      "modelUID": "OcchioLunanovaV1",
      "active": true,
      "identify_action": null,
      "firmwareUpdate_action": null,
      "optional": { ... },
      "buttons": [ ... ],
      "binary_inputs": [ ... ],
      "sensors": [ ... ],
      "outputs": [ ... ]
    }
  ]
}
```

**On setup:** For each vdSD in `entry.data["vdsds"]`:
1. Register an HA device in the device registry (name = vdSD `displayId`, via `DeviceInfo`)
2. Forward platform setup to `sensor.py` and `binary_sensor.py` to create entities
3. Call `api.py` to announce the vdSD to pydsvdcapi

**On removal:** Call pydsvdcapi to vanish/de-announce the device and its vdSDs.

---

## 5. VDC-HOST and VDC Parameters

All parameters are derived automatically except `port`. The integration package version is used for `modelVersion` and `hardwareVersion`.

### VDC-HOST
| Parameter | Value |
|---|---|
| `port` | user-provided |
| `displayId` | `"KarlKiel's Home Assistant vDC Host"` |
| `type` | `"vDChost"` |
| `model` | `"KarlKiel's vDC-host @ Home Assistant"` |
| `modelVersion` | derived from integration version |
| `modelUID` | `"KarlKiel's Home Assistant vDC-host"` |
| `hardwareVersion` | derived from integration version |
| `vendorName` | `"KarlKiel"` |
| `vendorGuid` | `"vendorname:KarlKiel"` |
| `configURL` | derived at runtime from HA base URL |
| `name` | `"KarlKiel's Home Assistant vDC-host"` |
| `active` | `true` |
| `dSUID` | auto-generated by pydsvdcapi |

### VDC
| Parameter | Value |
|---|---|
| `displayId` | `"KarlKiel's Home Assistant DS vDC"` |
| `type` | `"vDC"` |
| `model` | `"KarlKiel's generic vDC @ Home Assistant"` |
| `modelVersion` | derived from integration version |
| `modelUID` | `"KarlKiel's Home Assistant DS vDC"` |
| `vendorName` | `"KarlKiel"` |
| `vendorGuid` | `"vendorname:KarlKiel"` |
| `configURL` | derived at runtime from HA base URL |
| `deviceIcon16` | `vdc.png` |
| `deviceIconName` | `"KarlKielVDC.png"` |
| `name` | `"KarlKiel's Home Assistant DS vDC"` |
| `active` | `true` |
| `zoneID` | `null` |
| `implementationId` | `"x-KarlKiel-HomeAssistant-vDC"` |
| `capabilities.metering` | `false` |
| `capabilities.identification` | `false` |
| `capabilities.dynamicDefinitions` | `true` |
| `dSUID` | auto-generated by pydsvdcapi |

---

## 6. Config Flow Design

### 6.1 Hub flow

Single step. User provides `port`. On submit, the flow calls `api.py` to validate the handshake. On success: creates hub config entry.

### 6.2 Device sub-flow

Multi-step flow accessed via "Add device" on the integration page. Intermediate state is held in flow instance variables. An `_optional_return_step` variable tracks which step triggered an optional settings screen.

**Step sequence:**

```
device_info
  └─► vdsd_creation
        ├─► [optional_settings]  ← navigated to via button, returns here
        └─► vdsd_overview
              ├─► button          (repeating: one step per button element)
              ├─► binary_input
              ├─► sensor
              └─► output
                    ├─► [output_optional]  ← navigated to via button, returns here
                    ├─► channel            (repeating: one step per channel)
                    └─► channel_mapping
                          └─► model_features
                                └─► device_summary  ──► CREATE
```

After `device_summary` the user confirms and the config entry is created.

**"Back" behaviour:** Each step that exposes a "back" button navigates to the previous step. Partially entered data for the current vdSD or component is discarded on cancel; already-confirmed vdSDs on the vdSD overview are preserved.

**Multiple vdSDs:** After each vdSD is saved from `model_features`, the flow returns to `vdsd_overview`. The user can add further vdSDs or proceed to `device_summary`.

### 6.3 Key field derivations

| Field | Derived from |
|---|---|
| vdSD `name` | device `name` |
| vdSD `model` | vdSD `displayId` |
| vdSD `modelUID` | `vendorName` + `modelVersion` |
| vdSD `configURL` | HA base URL at runtime |
| button `buttonID` | 0 (same for all elements of a button group) |
| button `dsIndex` | minimal free index in vdSD for buttons |
| binary input `dsIndex` | minimal free index in vdSD for binary inputs|
| sensor `dsIndex` | minimal free index in vdSD for sensors
| output `activeGroup` | `defaultGroup` |
| modelFeatures | auto-derived from vdSD config, pre-selected; user can adjust |

---

## 7. Entity Model

### Architectural principle

> dsvdc4ha entities are **read-only diagnostic mirrors** of values forwarded to or received from digitalStrom. They are not controllable from HA. The bound HA entities are the authoritative source for automations and direct control.

### 7.1 Input entities (button, binary input, sensor)

| vdSD element | HA platform | State value |
|---|---|---|
| Button | `sensor` | enum-converted clickType (e.g. `"single_click"`) or actionID (e.g. `"Scene11"`) |
| Binary input (boolean) | `binary_sensor` | `True` / `False` |
| Binary input (integer extended value) | `sensor` | numeric string |
| Sensor | `sensor` | numeric value with `unit_of_measurement` and `device_class` derived from `sensorType` |

**Data flow (inputs):** Bound HA entity state changes → integration state listener → value converted → forwarded to dS via `api.py` → integration entity state updated to reflect forwarded value.

**Known limitation:** If the same button is pressed twice consecutively with the same clickType, the sensor state does not change and `state_changed` automations will not fire. Users should trigger automations on the bound HA entity directly.

### 7.2 Output entities (output channels)

Each configured output channel creates one `sensor` entity.

**Data flow (outputs — HA → dS):** Bound read entity state changes → integration detects via state listener → value forwarded to dS via `api.py` → channel sensor entity updated to reflect forwarded value.

**Data flow (outputs — dS → HA):** pydsvdcapi callback received → `api.py` passes command to integration → write-bound HA action called with channel value → real HA entity updated → state listener fires → dS confirmed.

### 7.3 Channel binding (per channel)

Each output channel has two bindings configured in the flow:

| Binding | Type | Purpose |
|---|---|---|
| **Read binding** | HA entity selector | Provides current channel value to dS |
| **Write binding** | HA action selector | Called when dS sends a command for this channel |

Scale conversion and value mapping are handled in the write action (templates or custom scripts).

---

## 8. HACS Compliance

### `hacs.json`
```json
{
  "name": "dsvdc4ha",
  "render_readme": true
}
```

### `manifest.json` (key fields)
```json
{
  "domain": "dsvdc4ha",
  "name": "dSVDC for Home Assistant",
  "version": "0.1.0",
  "requirements": ["pydsvdcapi"],
  "config_flow": true,
  "iot_class": "local_push",
  "codeowners": ["@KarlKiel"]
}
```

Note: `iot_class` is `local_push` because the DSS pushes updates to the vDC via pydsvdcapi callbacks.

### Minimum HA version

No hard minimum set for v1. Will be documented in `manifest.json` under `homeassistant` after implementation once the APIs used are known.

### Default icon

`vdc.png` (16x16 PNG, already in repo) is used as the default `deviceIcon16` for all vdSDs. Custom icon upload via config flow is deferred.

---

## 9. Testing Approach

Tests live in `tests/` at the repo root (standard HA integration test convention). The test suite runs alongside implementation as a parallel track.

| File | Coverage |
|---|---|
| `conftest.py` | Shared fixtures: mock `hass`, mock `pydsvdcapi` API layer, sample config entry data |
| `test_config_flow.py` | Hub flow (port validation, handshake success/failure), device flow (each step, back navigation, optional settings, multiple vdSDs) |
| `test_coordinator.py` | Hub setup, VDC-HOST/VDC announcement, restart restore, teardown, removal |
| `test_sensor.py` | Entity state updates from bound HA entities, value forwarding to dS, output write-back via action |

---

## 10. Deferred Features

The following are explicitly out of scope for v1:

- Custom icon upload for vdSDs (file selector not supported in HA config flow)
- Dynamic capabilities: custom events, actions, properties, states
- Per-output-type HA platforms (`light`, `cover`, `climate`) — all outputs use `sensor`
- HA minimum version constraint in `manifest.json` (added after implementation)

---

## 11. Design Decisions Log

| Decision | Choice | Reason |
|---|---|---|
| Optional settings screens | Regular sequential steps, navigated via button | HA config flow has no modal popup support |
| Button callback entity | `sensor` (enum-converted string state) | Read-only mirror; bound entity used for automations |
| Output entity | `sensor` (read-only channel value mirror) | Consistent with inputs; real control via bound entities |
| Output write direction | Explicit HA action binding per channel | Maximum flexibility; supports templates and custom scripts for value scaling |
| All entity platforms | `sensor` + `binary_sensor` only | Integration is a translation layer; platform-specific entities (`light`, `cover`) imply HA-side control which is not the intent |
| pydsvdcapi isolation | All calls via `api.py` | Testability; single point of change if library API evolves |
| Hub coordinator type | Custom `HubCoordinator`, not `DataUpdateCoordinator` | Integration is push/callback-based, not polling |
| Icon | `vdc.png` default | File upload not supported in HA config flow |
| Tests | Parallel track with implementation | Quality gate; required for eventual HA integration quality tier compliance |
