# Configuration Reference

The integration uses HA's subentry config flow. There are two flow types:

- **Hub flow** (`DsvdcConfigFlow`) — one-time setup of the VDC host (port, DSS wait).
- **Device flow** (`VdsdSubentryFlowHandler`) — creates or edits a virtual device group (one subentry = one or more vdSDs).

---

## Hub Flow

Triggered from **Settings → Integrations → Add Integration → dSVDC for Home Assistant**.

### Steps

| Step | What it does |
|---|---|
| `user` | Checks for existing hub entry; aborts with `already_configured` if one exists. |
| `hub` | User enters the TCP port for the VDC host (default 8444). Validates port availability. |
| `wait_for_dss` | Shows progress while the integration waits for the dSS to connect and complete the hello handshake. Resolves once `on_session_ready` fires or the user aborts. |

The entry is created with `data = { port: <int> }`.

---

## Device Flow (Subentry)

Triggered from the integration's device list via **Add device** or from an existing device's **Configure** option.

Three creation paths are available. The flow automatically selects the right path based on the user's initial choice.

---

### Path 1: From HA Entity (`from_entity`)

Maps a single HA entity directly to a vdSD. Best for simple single-entity mappings.

```
source_select → device_model_features → name_confirm → entity_completion
```

| Step | What it does |
|---|---|
| `source_select` | User picks a source HA entity. |
| `device_model_features` | Shows auto-derived model features; user can add/remove. |
| `name_confirm` | Pre-filled device name and entity name (derived from the HA entity); user can edit before saving. |
| `entity_completion` | Creates the subentry. |

---

### Path 2: From HA Device (`from_ha_device`)

Inspects all entities on a HA device and auto-groups them into vdSD proposals. Best for multi-entity devices (e.g., a light with brightness + color temp + on/off).

```
ha_device_select → device_entity_select
  → [per-entity user_choices steps if needed]
  → device_model_features (per vdSD plan)
  → name_confirm (per vdSD plan)
  → device_summary
```

| Step | What it does |
|---|---|
| `ha_device_select` | User selects an HA device. |
| `device_entity_select` | Multi-select of supported entities on that device. |
| *user_choices steps* | For entities where mapping parameters are ambiguous (e.g., sensor type or binary input function), the user is prompted. |
| `device_model_features` | Per vdSD plan: shows model features, user can adjust. |
| `name_confirm` | Per vdSD plan: pre-filled names, user confirms. Repeated once per planned vdSD. |
| `device_summary` | Summary of all planned vdSDs; user confirms or goes back. |

---

### Path 3: From Scratch (`from_scratch`)

Fully manual construction of a vdSD. The user specifies every field. Best for custom or unusual device configurations.

```
device_info → vdsd_creation → vdsd_overview
  → [button] → [binary_input → binary_input_binding]
  → [sensor → sensor_binding]
  → [output → output_optional? → channel → [channel_mapping | push_binding → apply_binding]]
  → device_plan_summary → name_confirm → entity_completion
```

| Step | What it does |
|---|---|
| `device_info` | Device display name and vendor. |
| `vdsd_creation` | vdSD name and primary group (color group). |
| `vdsd_overview` | Summary of added inputs/outputs; user adds more or proceeds. |
| `button` | Button input configuration (type, group, function, mode, callback type + entity). |
| `binary_input` | Binary input configuration (sensor function, group, input type/usage, value type, callback entity). |
| `binary_input_binding` | Structured binding: source entity, optional attribute, transform. |
| `sensor` | Sensor input configuration (sensor type, group, usage, min/max/resolution, timing parameters, callback entity). |
| `sensor_binding` | Structured binding: source entity, optional attribute, transform. |
| `output` | Output configuration (name, color groups, function, usage, variable ramp, mode). |
| `output_optional` | Optional output parameters: dim timing, heating system, cover timing. |
| `channel` | Manual channel type selection (for manual function outputs). |
| `channel_mapping` | Auto-mapped channels review. |
| `push_binding` | Per-channel HA→dS binding: source entity, source attribute, transform. Produces `push_expr`. |
| `apply_binding` | Per-channel dS→HA binding: HA service (domain.service), parameter, transform. Produces `apply_expr`. |
| `device_plan_summary` | Full review of the configured vdSD before saving. |
| `name_confirm` | Final name confirmation. |
| `entity_completion` | Creates the subentry. |

---

## Model Features

Model features tell the dSS configurator which UI controls to show for a device. They are selected during the `model_features` / `device_model_features` step.

**Auto features** are automatically pre-selected based on the device configuration (primary group, output function, button type, etc.) via `derive_model_features_for_config()` in `api.py`. Users can add or remove them.

**Optional features** are not pre-selected and are marked "(not tested)" — they exist because pydsvdcapi supports them but their dSS-side behaviour has not been verified in this integration.

### Label source of truth

All model feature labels are defined in [`strings.json`](../custom_components/dsvdc4ha/strings.json) under the top-level `"model_features"` key (sections `"auto"` and `"optional"`). `config_flow.py` loads them from there at import time — do **not** define them in Python.

Labels describe what each feature **does in the dSS configurator** (which panel or control it adds), not what the feature key means technically.

### Adding a translation

To translate model feature labels into another language, add the `"model_features"` section with the same key structure to `translations/<lang>.json`. The Python side always uses English from `strings.json`; HA's frontend will pick up translated labels from the translation file for users with that language set.

---

## Selector Helper

All enum selectors use a `_select(options, *, multiple=False)` helper that automatically picks:

- **LIST mode** for ≤ 5 options (radio-button style)
- **DROPDOWN** for more than 5 options

This ensures small enums are displayed as aligned lists rather than compact dropdowns.

---

## Binding System

When a user configures a binding in the config flow (push or apply), the structured binding dict is compiled at save time into an expression string:

**Push binding** (HA entity state → dS channel value):
```json
{ "source_attribute": "brightness", "transform": "scale_0_255_to_0_100" }
```
Compiled to: `"round(attrs.get('brightness') / 2.55, 1)"`

**Apply binding** (dS channel value → HA service call):
```json
{ "service": "light.turn_on", "parameter": "brightness", "transform": "scale_0_100_to_0_255" }
```
Compiled to: `"{'domain':'light','service':'turn_on','service_data':{'brightness':round(value * 2.55)}}"`

The compiler is in `binding_compiler.py`; the transform registry is in `binding_transforms.py`.

---

## Available Transforms

| Name | Label |
|---|---|
| `passthrough` | Pass through (no conversion) |
| `scale_0_255_to_0_100` | HA brightness (0–255) → dS (0–100%) |
| `scale_0_100_to_0_255` | dS percentage (0–100%) → HA (0–255) |
| `bool_to_1_0` | HA on/off → dS 1/0 |
| `bool_to_100_0` | HA on/off → dS 100%/0% |
| `invert_0_100` | Invert 0–100% (shade position vs. open position) |
| `mired_to_kelvin` | HA color_temp (mired) → dS mired (pass-through) |
| `kelvin_to_mired` | HA color_temp_kelvin (K) → dS mired |
| `hs_hue` | HA hs_color[0] → dS hue (0–360°) |
| `hs_saturation` | HA hs_color[1] → dS saturation (0–100%) |
