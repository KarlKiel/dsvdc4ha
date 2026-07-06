# dSVDC for Home Assistant — Documentation

**dSVDC for Home Assistant** (`dsvdc4ha`) is a Home Assistant custom integration that exposes HA entities to a digitalSTROM (dS) system as virtual digitalSTROM Devices (vdSDs). It implements the dS Virtual Device Connector (VDC) protocol over a local TCP connection discovered by mDNS.

`iot_class`: **local_push** — no cloud services required.

---

## Contents

| Document | What it covers |
|---|---|
| [Architecture](architecture.md) | Module map, data flow, config entry structure, expression sandbox, reconnect logic |
| [Configuration](configuration.md) | All config flow paths and steps, binding system, available transforms |
| [Entities](entities.md) | Supported HA entity types, unit conversion, channel type reference |
| [Installation](installation.md) | Setup guide, adding virtual devices, diagnostics |
| [Development](development.md) | Test suite, adding entity types and transforms, icon pipeline, pydsvdcapi integration |

---

## Quick Start

1. Install via HACS (add `https://github.com/KarlKiel/dsvdc4ha` as a custom repository).
2. Restart Home Assistant.
3. Go to **Settings → Integrations → Add Integration → dSVDC for Home Assistant**.
4. Enter the TCP port for the VDC host (default `8444`).
5. Open the dSS configurator and trigger a device scan.
6. Once connected, use **Add device** to expose HA entities as vdSDs.

See [Installation](installation.md) for the full setup guide.

---

## Key Concepts

- **VDC host** — a TCP server inside HA that the dSS connects to via mDNS. One hub entry per HA installation.
- **Subentry** — each virtual device group maps to a HA config subentry. One subentry can contain one or more vdSDs.
- **vdSD** — a single virtual digitalSTROM Device. Has one or more of: buttons, binary inputs, sensor inputs, and one output.
- **Binding** — the mapping between an HA entity attribute and a dS channel value, compiled at save time into a sandboxed Python expression.
- **Push** — HA state change → dS channel update.
- **Apply** — dS scene/command → HA service call.
