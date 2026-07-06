# dSVDC for Home Assistant

<p align="center">
  <img src="custom_components/dsvdc4ha/brand/logo.png" alt="dSVDC for Home Assistant" width="256">
</p>

A Home Assistant custom integration that exposes existing HA entities as virtual digitalSTROM Devices (vdSDs) inside a connected digitalSTROM system (dSS/dSM).

The integration implements the dS Virtual Device Connector (VDC) protocol. Home Assistant appears as a native dS bus participant — lights, covers, sensors, switches, and other entities become fully controllable from the dSS configurator and can participate in dS zones, scenes, and rules.

`iot_class`: **local_push** — no cloud services required.

---

## Features

- Announces a VDC host and vDC to the dSS via mDNS (zero-conf)
- Three device creation paths: from a single HA entity, from a HA device, or fully from scratch
- Supports lights (brightness, RGB, color temperature), covers/blinds, switches, sensors, binary sensors, buttons, and more
- Bi-directional: HA state changes push values to dS; dS scene/value commands call back into HA services
- Configurable value transforms and structured bindings compiled to sandboxed expressions at save time
- Auto-reconnect with exponential backoff (5 s → 15 s → 30 s → 60 s → 120 s → 300 s)
- Persists all configuration in HA config subentries; restores fully on restart
- MDI icon resolution with cairosvg rendering; bundled PNG fallbacks

---

## Requirements

- Home Assistant 2024.11 or newer (subentry config flow support required)
- `pydsvdcapi == 0.9.0` (installed automatically)
- `cairosvg == 2.9.0` (installed automatically)
- A digitalSTROM system (dSS / dSM) on the same local network

---

## Installation

### Via HACS (recommended)

1. Open HACS → **Integrations** → menu → **Custom repositories**.
2. Add `https://github.com/KarlKiel/dsvdc4ha` with category **Integration**.
3. Search for **dSVDC for Home Assistant** and install.
4. Restart Home Assistant.

### Manual

Copy the `custom_components/dsvdc4ha/` directory into your HA `custom_components/` folder and restart Home Assistant.

---

## Documentation

Full reference documentation is in the [`docs/`](docs/) folder:

| Document | What it covers |
|---|---|
| [Architecture](docs/architecture.md) | Module map, data flow, expression sandbox, reconnect logic |
| [Configuration](docs/configuration.md) | All config flow paths and steps, binding system, transforms |
| [Entities](docs/entities.md) | Supported entity types, unit conversion, channel labels |
| [Installation](docs/installation.md) | Detailed setup, device creation, diagnostics |
| [Development](docs/development.md) | Test suite, adding entity types and transforms, pydsvdcapi integration |

The [`documents/`](documents/) folder is gitignored and exists only locally. It contains reference materials: the entity-mapping spreadsheet, dS protocol PDFs, and QA findings.
