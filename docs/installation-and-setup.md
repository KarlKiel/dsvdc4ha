# Installation and Setup

## Requirements

- Home Assistant (any recent release with subentry config flow support)
- `pydsvdcapi == 0.8.9` (installed automatically)
- `cairosvg == 2.9.0` (installed automatically, used for MDI icon rendering)
- A digitalSTROM system (dSS / dSM) on the same local network

The integration is classified as `local_push` — no cloud services are required.

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

1. Copy the `custom_components/dsvdc4ha/` directory into your HA `custom_components/` folder.
2. Restart Home Assistant.

---

## Initial Setup

1. Go to **Settings → Integrations → Add Integration**.
2. Search for **dSVDC for Home Assistant**.
3. Enter the **TCP port** the VDC host should listen on (default `8444`). The port must be available on the HA host.
4. The integration waits for the dSS to connect and complete the handshake. Open the dSS configurator and trigger a device scan if the dSS does not connect automatically.
5. Once the handshake completes, the hub entry is created and the **dSS Connection** binary sensor becomes available.

---

## Adding Virtual Devices

After the hub is configured, add virtual devices from the integration page:

1. Go to **Settings → Integrations → dSVDC for Home Assistant**.
2. Click **Add device**.
3. Choose one of three creation paths:

### From HA Entity

Maps a single HA entity to one vdSD. Best for simple devices.

1. Select the source entity.
2. Review auto-derived model features; adjust if needed.
3. Confirm the device and entity name.
4. The device is created and announced to the dSS.

### From HA Device

Auto-groups all supported entities on a HA device into one or more vdSDs.

1. Select the HA device.
2. Choose which entities to include (multi-select).
3. For entities with ambiguous parameters (e.g., sensor type), choose from the presented options.
4. Review model features for each proposed vdSD.
5. Confirm names for each vdSD.
6. Review the full summary, then confirm to create and announce.

### From Scratch

Fully manual configuration. Useful for custom or composite devices.

1. Enter device display name and vendor.
2. Enter vdSD name and select primary group (color group).
3. Add inputs and/or outputs:
   - **Button**: select type, group, function, mode, and optionally a callback entity.
   - **Binary input**: select sensor function, group, input type/usage, value type, and callback entity. Then configure the binding (source entity, attribute, transform).
   - **Sensor input**: select sensor type, group, usage, range, timing, and callback entity. Then configure the binding.
   - **Output**: select function, groups, usage, mode. Optionally configure timing parameters. Then map channels (HA→dS push binding and dS→HA apply binding per channel).
4. Confirm names and save.

---

## Editing Existing Devices

Open the device in HA (**Settings → Devices**) and use the **Configure** button to reopen the config flow for that subentry. All fields are pre-populated.

---

## Re-announcing a Device

If a vdSD becomes inconsistent in the dSS database, press the **Re-announce to dSS** button (EntityCategory.CONFIG, hidden by default) on the vdSD device. This discards the device from the announced-set and forces a fresh announcement.

To make the button visible: go to the device page, find the entity in the entity list, click the entity, and toggle **Visible** in the entity registry.

---

## Connection Status

The **dSS Connection** binary sensor (`EntityCategory` = default, always visible) reports whether the dSM currently has an active session with the VDC host. On disconnect, the integration automatically attempts to reconnect with exponential backoff (5 s → 15 s → 30 s → 60 s → 120 s → 300 s).

---

## Diagnostics and Property Sensors

For every vdSD, the integration creates a set of hidden diagnostic and config sensors exposing the raw pydsvdcapi property values:

- **Diagnostic sensors** (EntityCategory.DIAGNOSTIC): vdSD identity properties, input/output description properties.
- **Config sensors** (EntityCategory.CONFIG): input/output settings properties (read-only currently; write-back pending a pydsvdcapi API addition).
- **State sensors**: current input/output state values.

These are hidden by default and can be made visible from the entity registry.
