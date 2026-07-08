# Architecture

## Overview

**dSVDC for Home Assistant** (`dsvdc4ha`) is a Home Assistant custom integration that exposes HA entities to a digitalSTROM (dS) system as virtual digitalSTROM Devices (vdSDs). It implements the dS Virtual Device Connector (VDC) protocol, allowing a Home Assistant installation to appear as a native dS bus participant: lights, covers, sensors, switches and other entities become fully controllable from the dSS configurator and can participate in dS zones, scenes and rules.

The integration has an `iot_class` of `local_push` — all communication is on the local network and state changes are pushed in real time.

---

## High-Level Data Flow

```
                   ┌──────────────────────────────────────────────┐
                   │          Home Assistant                       │
                   │                                               │
                   │   ┌──────────┐   HA entities   ┌──────────┐ │
  dSS / dSM ◄────►│   │VdcHost   │◄───────────────► │Listeners │ │
  (TCP + mDNS)     │   │  (port)  │                 │          │ │
                   │   └────┬─────┘                 └──────────┘ │
                   │        │ pydsvdcapi                          │
                   │   ┌────▼─────┐                 ┌──────────┐ │
                   │   │  DsvdcApi │◄───────────────► │Config   │ │
                   │   │  (wrapper)│   entry data    │  Flow   │ │
                   │   └────┬─────┘                 └──────────┘ │
                   │        │                                     │
                   │   ┌────▼──────────────────────┐            │
                   │   │  HubCoordinator            │            │
                   │   │  (lifecycle + reconnect)   │            │
                   │   └───────────────────────────┘            │
                   └──────────────────────────────────────────────┘
```

The dSS connects to the VDC host over mDNS-discovered TCP. The `DsvdcApi` wraps `pydsvdcapi`'s `VdcHost`/`Vdc`/`Device`/`Vdsd` object tree, which is the only place pydsvdcapi is imported directly — all other modules go through `DsvdcApi`.

---

## Module Map

| File | Responsibility |
|---|---|
| `__init__.py` | HA entry lifecycle (`async_setup`, `async_setup_entry`, `async_unload_entry`). Wires platforms, registers devices with the API, seeds initial values, sets config URLs, and manages the entity-registry listener. |
| `api.py` | `DsvdcApi` — sole importer of pydsvdcapi. Builds and owns the `VdcHost`/`Vdc` tree, manages device add/remove/announce/vanish, forwards HA state changes to dS, registers dS→HA callbacks. |
| `coordinator.py` | `HubCoordinator` — owns the `DsvdcApi` instance for the hub config entry. Handles start/stop lifecycle and implements auto-reconnect with exponential backoff (5 s → 15 s → 30 s → 60 s → 120 s → 300 s). |
| `config_flow.py` | All UI flows for creating and editing hub and device config entries. Three vdSD creation paths: `from_entity`, `from_ha_device`, `from_scratch`. |
| `device_grouper.py` | Pure grouping logic: given a list of `EntityInfo` objects, computes a list of `VdsdPlan` objects grouping entities into proposed vdSDs. No HA imports. |
| `entity_mapping.py` | Static map from HA domain + device class → dS vdSD parameters (sensor type, binary input type, output function, channel type, etc.). Derived directly from pydsvdcapi enums. |
| `listeners.py` | State listeners: subscribes to HA entity state changes and forwards them to the dS API. Handles buttons, sensor inputs, binary inputs, and output channels. Also contains `seed_initial_values()` and `_eval_push`/`_eval_apply` sandbox eval helpers. |
| `binding_compiler.py` | Translates structured binding configs (`{source_attribute, transform}`, `{service, parameter, transform}`) into the `push_expr`/`apply_expr` expression strings consumed by `listeners.py`. |
| `binding_transforms.py` | Registry of 10 named value transforms (passthrough, scale, invert, bool↔float conversions). Each transform has a `push_expr` and `apply_expr` template using `v` as the value placeholder. |
| `unit_conversion.py` | Look-up table for HA sensor unit → dS expected unit conversion (35 sensor types, 100+ unit strings). |
| `base_entity.py` | `DsvdcBaseEntity` — shared base for all per-vdSD HA entities. Derives unique_id and `DeviceInfo` from `subentry_id + vdsd_index`. |
| `binary_sensor.py` | `BinaryInputEntity` (mirrors a boolean binary input) and `HubConnectivitySensor` (reports dSM session state). |
| `sensor.py` | `ButtonSensorEntity`, `SensorInputEntity`, `OutputChannelEntity`, `PropertySensorEntity` — all hidden by default. |
| `button.py` | `ReannounceButtonEntity` — CONFIG category button per vdSD; pressing it forces re-announcement to dSS. |
| `button_translator.py` | `ButtonEventTranslator` — timing-based state machine to detect multi-click patterns from HA binary sensor / button entities and map them to dS click types. |
| `_icon_utils.py` | MDI icon resolution: maps HA entity domain/device class to a MDI icon name, converts SVG to PNG via cairosvg, and bundles a set of fallback PNG icons. |
| `const.py` | Domain, platform list, VDC host identity strings, click type name map. |

---

## Config Entry Structure

The integration uses a **single config entry** with one hub entry and multiple **subentries** — one per virtual device group (a "subentry" maps to one or more vdSDs on the dS side).

```
ConfigEntry (hub)
│   data: { port: 9090 }
│
├── ConfigSubEntry (device A)
│   data: { vdsds: [ vdsd_0, vdsd_1, ... ] }
│
└── ConfigSubEntry (device B)
    data: { vdsds: [ vdsd_0 ] }
```

Each `vdsd` dict in the subentry data contains the full configuration needed to reconstruct the pydsvdcapi object tree: identity fields, buttons, binary_inputs, sensors, output (with channels), callback entity references, and precompiled `push_expr`/`apply_expr` strings.

---

## HA → dS Direction (Push)

1. A HA entity state changes.
2. `async_track_state_change_event` fires the registered callback in `listeners.py`.
3. For **output channels**: `_eval_push(push_expr, state)` evaluates the expression in a sandboxed context and calls `api.report_channel_value(channel, value)`.
4. For **sensor inputs**: the value is optionally unit-converted via `unit_conversion.convert_sensor_value()` then forwarded via `api.report_sensor_value(si, value)`.
5. For **binary inputs**: the boolean or extended-integer value is forwarded via `api.report_binary_value()` / `api.report_binary_extended_value()`.
6. For **buttons**: click type or action ID forwarded via `api.report_button_click()` / `api.report_button_action()`.

---

## dS → HA Direction (Apply)

When dSS sends a channel-value command (e.g., dim to 70%):

1. pydsvdcapi fires `output.on_channel_applied(output, channel_updates)`.
2. The callback registered by `setup_output_listeners()` in `listeners.py` evaluates `apply_expr` or `apply_all_expr` in a sandboxed context.
3. The result is an HA service call dict (`domain`, `service`, `service_data`, `target`).
4. `hass.services.async_call(**action)` is called.

The `apply_all_expr` path is used for complex multi-channel devices like lights, where all channel updates (brightness, hue, saturation, color temp) must be consolidated into a single `light.turn_on` call rather than separate per-channel calls.

---

## Expression Sandbox

Both `push_expr` and `apply_expr`/`apply_all_expr` are Python expressions evaluated in a restricted context (`__builtins__: {}`). Permitted names:

| Name | Purpose |
|---|---|
| `round`, `float`, `int`, `abs`, `min`, `max` | Standard math |
| `entity` | Current HA state object |
| `attrs` | State attributes dict (None values stripped for push) |
| `value` | Channel value (apply only) |
| `channel_updates` | Dict of channel_type → value (apply_all only) |
| `_norm(v, lo, hi)` | Normalise v from [lo,hi] to [0,100] |
| `_denorm(v, lo, hi)` | Denormalise v from [0,100] to [lo,hi] |
| `_light_apply(cu, attrs)` | Consolidate channel updates into a HA light action |

---

## Binding Compilation

The config flow stores bindings in structured form:

```json
{
  "source_attribute": "brightness",
  "transform": "scale_0_255_to_0_100"
}
```

`binding_compiler.compile_push_binding()` compiles this at save time into:

```python
"round(attrs.get('brightness') / 2.55, 1)"
```

This precompiled string is stored in the subentry data and evaluated at runtime by `listeners.py`. The transform registry (`binding_transforms.TRANSFORMS`) maps each named transform to a `push_expr` and `apply_expr` template with `v` as the value placeholder.

---

## Reconnect & Resilience

`HubCoordinator._reconnect_with_backoff()` is triggered by `on_disconnect` from pydsvdcapi. It:

1. Stops the existing `DsvdcApi`.
2. Waits `_RECONNECT_DELAYS[attempt]` seconds (5, 15, 30, 60, 120, 300 — capped at 300 s).
3. Creates a new `DsvdcApi`, re-registers all subentry devices, re-wires all listeners, re-seeds initial values, and announces all devices.

Connection state is published to subscribers via `HubCoordinator.subscribe_connection_status()`. `HubConnectivitySensor` subscribes to this to keep the HA binary sensor in sync.

---

## vdSD Lifecycle Management

A vdSD's `active` property tells dSS whether the virtual device is operational.

**Automatic deactivation** — `DsvdcApi.report_entity_available()` tracks which HA callback entities are unavailable. When any entity becomes unavailable the vdSD transitions to `INACTIVE`; it returns to `ACTIVE` only when all entities are available again.

**Auto-restore on dSS-initiated deactivation** — dSS occasionally sets `active=False` on its own (e.g., after a reconfiguration round). When this happens pydsvdcapi fires `Vdsd.on_settings_changed` with `{"active": False}`. The integration intercepts this and immediately pushes `active=True` back to dSS — *unless* the vdSD is legitimately inactive because HA entities are unavailable (`DsvdcApi.has_unavailable_entities()` returns `True`). The restore is logged at `INFO` level.

**Manual control** — `VdcActiveSwitchEntity` and `VdsdActiveSwitchEntity` allow the user to manually set lifecycle state. These go through `DsvdcApi.set_vdsd_lifecycle()` which pushes a notification outbound to dSS — this path does **not** trigger `on_settings_changed`, so the auto-restore logic is never activated by a user-initiated change.

---

## Entity Visibility

Mirror entities (`ButtonSensorEntity`, `SensorInputEntity`, `OutputChannelEntity`, `BinaryInputEntity`, `PropertySensorEntity`) are **active but hidden** by default (`_attr_entity_registry_visible_default = False`). They collect data and are included in statistics but do not appear on the default HA dashboard. Users can enable visibility per entity from the entity registry UI.

`HubConnectivitySensor` and `ReannounceButtonEntity` use the HA defaults (visible and enabled).

---

## Property Sensor Entities

On setup, `__init__.py` creates one `PropertySensorEntity` per scalar vdSD property value:

- **vdSD identity** (`Vdsd.get_properties()`) — `EntityCategory.DIAGNOSTIC`
- **Per BinaryInput**: description properties (DIAGNOSTIC), settings (CONFIG), state
- **Per SensorInput**: description, settings, state
- **Per ButtonInput**: description, settings, state
- **Output** (when present): description, settings, state

Writable setting entities (number, select, switch, text — e.g. zoneID, progMode, button mode, sensor interval) apply changes in HA memory and automatically trigger `force_reannounce_device()` on the affected vdSD. This performs a full vanish + re-announce cycle, which forces dSS to re-read the complete device description and apply the new property values immediately. No manual "Re-announce" action is required after changing a writable property.

---

## Device Registry Layout

Each subentry produces one or more HA devices:

- **Hub device** — `(DOMAIN, entry.entry_id)` — groups `HubConnectivitySensor`.
- **Per-vdSD device** — `(DOMAIN, "{subentry_id}_{vdsd_index}")` — groups all mirror entities, property sensors, and the `ReannounceButtonEntity` for that vdSD.

Config URLs for per-vdSD devices are patched after platform setup to point at `/config/devices/device/{ha_device_id}` so the dSS configurator opens the correct HA device page.
