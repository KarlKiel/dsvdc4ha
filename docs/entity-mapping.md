# Entity Mapping Reference

`entity_mapping.py` contains the static map from HA entity domain + device class to dS vdSD configuration. This is the single source of truth for which HA entity types are supported and how they translate to dS parameters.

The file is validated against `documents/ha_vdsd_mapping.xlsx` by the test `test_entity_mapping.py` to ensure code and spec stay in sync.

---

## Supported HA Entity Types

### Output-capable entities (can control dS outputs)

| HA Domain | Device Class / Condition | dS Function | Notes |
|---|---|---|---|
| `light` | — | Dimmer (BRIGHTNESS channel) or RGB/CT depending on `supported_color_modes` | Auto-derives channels from HA color modes |
| `cover` | `blind`, `curtain`, `window_covering`, `roller_shutter` | Shadow positional | Indoor or outdoor placement choice; optional tilt channel |
| `cover` | `garage_door`, `gate` | Shadow positional (generic) | |
| `switch` | — | ON/OFF (POWER_STATE channel) | |
| `input_boolean` | — | ON/OFF (POWER_STATE channel) | |
| `climate` | — | Heating (HEATING_POWER or similar) | |

### Binary input entities

| HA Domain | Device Class | dS Sensor Function |
|---|---|---|
| `binary_sensor` | `motion` | MOVEMENT / PIR |
| `binary_sensor` | `door` | DOOR_OPEN |
| `binary_sensor` | `window` | WINDOW_OPEN |
| `binary_sensor` | `garage_door` | GARAGE_DOOR_OPEN |
| `binary_sensor` | `smoke` | SMOKE |
| `binary_sensor` | `moisture` | WATER_LEAKAGE |
| `binary_sensor` | `vibration` | VIBRATION |
| `binary_sensor` | `occupancy` | PRESENCE |
| `binary_sensor` | any other | Joker (configurable) |

For `WINDOW_OPEN`, `DOOR_OPEN`, and `GARAGE_DOOR_OPEN` the polarity is inverted: HA `on` (contact open) maps to dS `inactive` (False), because dS "active" means contact closed.

### Sensor input entities

| HA Domain | Device Class | dS Sensor Type | dS Unit |
|---|---|---|---|
| `sensor` | `temperature` | TEMPERATURE (1) | °C |
| `sensor` | `humidity` | HUMIDITY (2) | % |
| `sensor` | `illuminance` | BRIGHTNESS (3) | lx |
| `sensor` | `voltage` | POWER_SUPPLY_VOLTAGE (4) | V |
| `sensor` | `carbon_monoxide` | CO_CONCENTRATION (5) | ppm |
| `sensor` | `pm10` | PARTICULATE_MATTER_10 (8) | µg/m³ |
| `sensor` | `pm25` | PARTICULATE_MATTER_2P5 (9) | µg/m³ |
| `sensor` | `wind_speed` | WIND_SPEED (13) | m/s |
| `sensor` | `power` | ACTIVE_POWER (14) | W |
| `sensor` | `current` | ELECTRIC_CURRENT (15) | A |
| `sensor` | `energy` | ENERGY_METER (16) | kWh |
| `sensor` | `apparent_power` | APPARENT_POWER (17) | VA |
| `sensor` | `pressure` | AIR_PRESSURE (18) | hPa |
| `sensor` | `sound_pressure` | SOUND_PRESSURE (20) | dB |
| `sensor` | `precipitation` | PRECIPITATION (21) | mm |
| `sensor` | `carbon_dioxide` | CO2_CONCENTRATION (22) | ppm |
| `sensor` | `wind_gust_speed` | WIND_GUST (23) | m/s |
| `sensor` | `weight` | WEIGHT (30) | g |
| `sensor` | `frequency` | GENERAL_PURPOSE (34) | Hz |
| `number` | — | GENERAL_PURPOSE (34) | |
| `input_number` | — | GENERAL_PURPOSE (34) | |

### Button / event entities

| HA Domain | Notes |
|---|---|
| `button` | Mapped as dS button input; `detect_clicks` mode auto-detects click type |
| `event` | Event type mapped to dS click types |

---

## Unit Conversion

When HA reports a sensor in a unit different from the dS expected unit, `unit_conversion.convert_sensor_value()` handles the conversion automatically. For example:

- HA temperature in `°F` → converted to `°C` before sending to dS
- HA power in `kW` → multiplied by 1000 to get `W`
- HA pressure in `PSI` → converted to `hPa`

The conversion table covers 35 sensor types and over 100 source unit strings. Values with unknown units or unknown sensor types are passed through unchanged.

---

## Channel Type Labels

Each output channel type has a human-readable label used in the config flow UI:

| Channel | Type ID | Label |
|---|---|---|
| BRIGHTNESS | 1 | Brightness |
| HUE | 2 | Hue |
| SATURATION | 3 | Saturation |
| COLOR_TEMP | 4 | Color Temperature |
| SHADE_POSITION_OUTSIDE | 7 | Shade Position (Outside) |
| SHADE_POSITION_INDOOR | 8 | Shade Position (Indoor) |
| SHADE_OPENING_ANGLE_OUTSIDE | 9 | Shade Angle (Outside) |
| SHADE_OPENING_ANGLE_INDOOR | 10 | Shade Angle (Indoor) |
| AIR_FLOW_INTENSITY | 12 | Air Flow Intensity |
| HEATING_POWER | 16 | Heating Power |
| POWER_STATE | 19 | Power State |
| AUDIO_VOLUME | 18 | Audio Volume |
| WATER_TEMPERATURE | 22 | Water Temperature |

---

## Excel Spec Alignment

The mapping is kept in sync with `documents/ha_vdsd_mapping.xlsx` which is the authoritative specification. The test `test_mapping_excel.py` validates that:

- All columns present in the Excel sheet exist in the code.
- All values in `entity_mapping.py` match the corresponding rows in the Excel file.

The audit tool (`tools/audit_mapping.py`) can be run to identify discrepancies between the code and the Excel spec. The Excel file can be regenerated from the current code state using `tools/generate_mapping_excel.py`.

> **Important:** The Excel file must not be modified without explicit confirmation, as it is the source-of-truth specification document.
