# dSVDC for Home Assistant

<p align="center">
  <img src="custom_components/dsvdc4ha/brand/logo.png" alt="dSVDC for Home Assistant" width="256">
</p>

A Home Assistant custom integration that exposes existing HA entities as virtual digitalSTROM Devices (vdSDs) inside a connected digitalSTROM system (dSS/dSM).

The integration implements the dS Virtual Device Connector (VDC) protocol, allowing Home Assistant to appear as a native dS bus participant — lights, covers, sensors, switches, and other entities become fully controllable from the dSS configurator and can participate in dS zones, scenes, and rules.

`iot_class`: **local_push** — no cloud services required.

---

## Features

- Announces a VDC host and vDC to the dSS via mDNS (zero-conf)
- Three device creation paths: from a single HA entity, from a HA device, or fully from scratch
- Supports lights (brightness, RGB, color temperature), covers/blinds, switches, sensors, binary sensors, buttons, climate, and more
- Bi-directional: HA state changes push values to dS; dS scene/value commands call back into HA services
- Configurable value transforms and structured bindings compiled to sandboxed expressions at save time
- Auto-reconnect with exponential backoff (5 s → 15 s → 30 s → 60 s → 120 s → 300 s)
- Persists all configuration in HA config subentries; restores fully on restart
- MDI icon resolution with cairosvg rendering; bundled PNG fallbacks

---

## Installation

### Via HACS (recommended)

1. Open HACS in Home Assistant.
2. Go to **Integrations**.
3. Click the menu → **Custom repositories**.
4. Add `https://github.com/KarlKiel/dsvdc4ha` with category **Integration**.
5. Search for **dSVDC for Home Assistant** and install.
6. Restart Home Assistant.

### Manual

Copy the `custom_components/dsvdc4ha/` directory into your HA `custom_components/` folder and restart Home Assistant.

---

## Setup

### 1 — Hub

Go to **Settings → Integrations → Add Integration** and search for **dSVDC for Home Assistant**. Enter the TCP port the VDC host should listen on (default `8444`). The integration waits for the dSS to connect and complete the hello handshake. Open the dSS configurator and trigger a device scan if the dSS does not connect automatically.

Once connected, the hub entry is created and the **dSS Connection** binary sensor becomes available.

### 2 — Virtual Devices

After the hub is configured, use **Add device** on the integration page. Three creation paths are available:

#### From HA Entity

Maps a single HA entity to one vdSD. The integration looks up the entity's domain and device class in the built-in mapping table and automatically derives the correct dS output type, sensor function, group, and output channels. You are only prompted where a genuine choice exists (e.g. indoor vs. outdoor for blinds).

#### From HA Device

Auto-groups all supported entities on a HA device into one or more vdSD proposals. Select the entities to include, confirm or adjust the derived model features, confirm names, and the integration creates and announces all devices in one step.

#### From Scratch

Fully manual wizard. Specify device info, one or more vdSDs, buttons, binary inputs, sensor inputs, outputs, and per-channel push/apply bindings step by step. Best for custom or composite devices not covered by the entity mapping.

---

## Supported Entity Types

### Outputs (dS → HA and HA → dS)

| HA Domain | Condition | dS Function |
|---|---|---|
| `light` | — | Dimmer, RGB, or CT depending on color modes |
| `cover` | `blind`, `curtain`, `window_covering`, `roller_shutter` | Shadow positional (indoor or outdoor) |
| `cover` | `garage_door`, `gate` | Shadow positional (generic) |
| `switch` | — | ON/OFF |
| `input_boolean` | — | ON/OFF |
| `climate` | — | Heating power |

### Sensor Inputs (HA → dS)

Temperature, humidity, illuminance, voltage, CO, PM10, PM25, wind speed, power, current, energy, apparent power, pressure, sound pressure, precipitation, CO₂, wind gust, weight, frequency, and general purpose (`number`, `input_number`).

### Binary Inputs (HA → dS)

Motion, door, window, garage door, smoke, moisture, vibration, occupancy, and joker (any other binary sensor).

### Buttons / Events (HA → dS)

`button` domain and `event` entities mapped to dS click types.

---

## Bindings and Transforms

Each output channel has a **push binding** (HA → dS) and an **apply binding** (dS → HA). Bindings are configured in the UI as structured dicts and compiled at save time into sandboxed Python expressions.

Available transforms:

| Name | Description |
|---|---|
| `passthrough` | No conversion |
| `scale_0_255_to_0_100` | HA brightness (0–255) → dS (0–100%) |
| `scale_0_100_to_0_255` | dS percentage (0–100%) → HA (0–255) |
| `bool_to_1_0` | HA on/off → dS 1/0 |
| `bool_to_100_0` | HA on/off → dS 100%/0% |
| `invert_0_100` | Invert 0–100% (shade open vs. closed) |
| `mired_to_kelvin` | HA color_temp (mired) → dS mired (pass-through) |
| `kelvin_to_mired` | HA color_temp_kelvin (K) → dS mired |
| `hs_hue` | HA hs_color[0] → dS hue (0–360°) |
| `hs_saturation` | HA hs_color[1] → dS saturation (0–100%) |

---

## Requirements

- Home Assistant (any recent release with subentry config flow support)
- `pydsvdcapi == 0.8.9` (installed automatically)
- `cairosvg == 2.9.0` (installed automatically)
- A digitalSTROM system (dSS / dSM) on the same local network

---

## Documentation

Full reference documentation is in the [`docs/`](docs/) folder:

- [Architecture](docs/architecture.md) — module map, data flow, expression sandbox, reconnect logic
- [Config Flow](docs/config-flow.md) — all flow paths and steps, binding system, transforms
- [Entity Mapping](docs/entity-mapping.md) — supported entity types, unit conversion, channel labels
- [Installation and Setup](docs/installation-and-setup.md) — detailed setup, device creation, diagnostics
- [Development](docs/development.md) — test suite, adding entity types and transforms, pydsvdcapi integration points

The [`documents/`](documents/) folder contains reference materials: dS protocol PDFs, the entity-mapping spreadsheet (`ha_vdsd_mapping.xlsx`), and other non-markdown source documents. It is not user documentation.
