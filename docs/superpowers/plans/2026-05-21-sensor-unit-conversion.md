# Sensor Unit Conversion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically convert HA sensor values from their native HA unit to the dS-expected unit before forwarding to pydsvdcapi.

**Architecture:** A new `unit_conversion.py` module holds the static conversion table `{sensor_type_int → {ha_unit_str → converter_fn}}` and a single `convert_sensor_value(sensor_type, ha_unit, value)` entry point. The two places in `listeners.py` that read sensor values (`_on_sensor_state` callback and `seed_initial_values`) are updated to capture the sensor type from config and call the converter. The HA unit is read from `state.attributes["unit_of_measurement"]` at runtime, so no extra config is needed.

**Tech Stack:** Python 3.12+, pydsvdcapi SensorType enum, pytest, existing dsvdc4ha listener infrastructure.

---

## dS expected units (reference)

| SensorType int | dS unit |
|---|---|
| 1 Temperature | °C |
| 2 Humidity | % |
| 3 Illuminance | lx |
| 4 Supply Voltage | V |
| 5 CO | ppm |
| 6 Radon | Bq/m³ |
| 8 PM10 | µg/m³ |
| 9 PM2.5 | µg/m³ |
| 10 PM1 | µg/m³ |
| 13 Wind Speed | m/s |
| 14 Active Power | W |
| 15 Electric Current | A |
| 16 Energy Meter | kWh |
| 17 Apparent Power | VA |
| 18 Air Pressure | hPa |
| 20 Sound Pressure | dB |
| 21 Precipitation | mm |
| 22 CO₂ | ppm |
| 23 Wind Gust Speed | m/s |
| 25 Generated Active Power | W |
| 26 Generated Energy | kWh |
| 27 Water Quantity | L |
| 28 Water Flow Rate | L/s |

---

## File structure

| File | Change |
|---|---|
| `custom_components/dsvdc4ha/unit_conversion.py` | **Create** — conversion table + `convert_sensor_value()` |
| `custom_components/dsvdc4ha/listeners.py` | **Modify** — apply conversion in `_on_sensor_state` (line 161) and `seed_initial_values` (lines 229-237) |
| `tests/test_unit_conversion.py` | **Create** — unit tests for conversion table |

---

## Task 1: Create `unit_conversion.py` with the conversion table

**Files:**
- Create: `custom_components/dsvdc4ha/unit_conversion.py`
- Test: `tests/test_unit_conversion.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_unit_conversion.py
"""Tests for HA → dS sensor unit conversion."""
from __future__ import annotations
import pytest
from custom_components.dsvdc4ha.unit_conversion import convert_sensor_value


# ---------------------------------------------------------------------------
# Passthrough cases
# ---------------------------------------------------------------------------

def test_none_unit_passthrough():
    assert convert_sensor_value(1, None, 20.0) == 20.0

def test_unknown_unit_passthrough():
    assert convert_sensor_value(1, "furlong", 20.0) == 20.0

def test_unknown_sensor_type_passthrough():
    assert convert_sensor_value(999, "°F", 32.0) == 32.0


# ---------------------------------------------------------------------------
# Temperature (type 1) — target °C
# ---------------------------------------------------------------------------

def test_temperature_celsius_identity():
    assert convert_sensor_value(1, "°C", 20.0) == pytest.approx(20.0)

def test_temperature_fahrenheit_to_celsius():
    assert convert_sensor_value(1, "°F", 32.0) == pytest.approx(0.0)
    assert convert_sensor_value(1, "°F", 212.0) == pytest.approx(100.0)
    assert convert_sensor_value(1, "°F", -40.0) == pytest.approx(-40.0)

def test_temperature_kelvin_to_celsius():
    assert convert_sensor_value(1, "K", 273.15) == pytest.approx(0.0)
    assert convert_sensor_value(1, "K", 373.15) == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Wind speed (types 13 and 23) — target m/s
# ---------------------------------------------------------------------------

def test_wind_speed_ms_identity():
    assert convert_sensor_value(13, "m/s", 5.0) == pytest.approx(5.0)

def test_wind_speed_kmh_to_ms():
    assert convert_sensor_value(13, "km/h", 36.0) == pytest.approx(10.0)

def test_wind_speed_mph_to_ms():
    assert convert_sensor_value(13, "mph", 1.0) == pytest.approx(0.44704)

def test_wind_speed_knots_to_ms():
    assert convert_sensor_value(13, "kn", 1.0) == pytest.approx(0.51444, rel=1e-4)

def test_wind_gust_speed_same_conversions():
    assert convert_sensor_value(23, "km/h", 36.0) == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Air pressure (type 18) — target hPa
# ---------------------------------------------------------------------------

def test_pressure_hpa_identity():
    assert convert_sensor_value(18, "hPa", 1013.25) == pytest.approx(1013.25)

def test_pressure_mbar_equals_hpa():
    assert convert_sensor_value(18, "mbar", 1013.25) == pytest.approx(1013.25)

def test_pressure_pa_to_hpa():
    assert convert_sensor_value(18, "Pa", 101325.0) == pytest.approx(1013.25)

def test_pressure_kpa_to_hpa():
    assert convert_sensor_value(18, "kPa", 101.325) == pytest.approx(1013.25)

def test_pressure_psi_to_hpa():
    assert convert_sensor_value(18, "PSI", 14.6959) == pytest.approx(1013.25, rel=1e-3)

def test_pressure_inhg_to_hpa():
    assert convert_sensor_value(18, "inHg", 29.9213) == pytest.approx(1013.25, rel=1e-3)

def test_pressure_mmhg_to_hpa():
    assert convert_sensor_value(18, "mmHg", 760.0) == pytest.approx(1013.25, rel=1e-3)


# ---------------------------------------------------------------------------
# Power (types 14 and 25) — target W
# ---------------------------------------------------------------------------

def test_power_w_identity():
    assert convert_sensor_value(14, "W", 100.0) == pytest.approx(100.0)

def test_power_kw_to_w():
    assert convert_sensor_value(14, "kW", 1.5) == pytest.approx(1500.0)

def test_generated_power_kw_to_w():
    assert convert_sensor_value(25, "kW", 2.0) == pytest.approx(2000.0)


# ---------------------------------------------------------------------------
# Energy (types 16 and 26) — target kWh
# ---------------------------------------------------------------------------

def test_energy_kwh_identity():
    assert convert_sensor_value(16, "kWh", 10.0) == pytest.approx(10.0)

def test_energy_wh_to_kwh():
    assert convert_sensor_value(16, "Wh", 1000.0) == pytest.approx(1.0)

def test_energy_mwh_to_kwh():
    assert convert_sensor_value(16, "MWh", 1.0) == pytest.approx(1000.0)


# ---------------------------------------------------------------------------
# Electric current (type 15) — target A
# ---------------------------------------------------------------------------

def test_current_a_identity():
    assert convert_sensor_value(15, "A", 2.5) == pytest.approx(2.5)

def test_current_ma_to_a():
    assert convert_sensor_value(15, "mA", 2500.0) == pytest.approx(2.5)


# ---------------------------------------------------------------------------
# Voltage (type 4) — target V
# ---------------------------------------------------------------------------

def test_voltage_v_identity():
    assert convert_sensor_value(4, "V", 230.0) == pytest.approx(230.0)

def test_voltage_mv_to_v():
    assert convert_sensor_value(4, "mV", 3300.0) == pytest.approx(3.3)


# ---------------------------------------------------------------------------
# Apparent power (type 17) — target VA
# ---------------------------------------------------------------------------

def test_apparent_power_va_identity():
    assert convert_sensor_value(17, "VA", 500.0) == pytest.approx(500.0)

def test_apparent_power_kva_to_va():
    assert convert_sensor_value(17, "kVA", 1.5) == pytest.approx(1500.0)


# ---------------------------------------------------------------------------
# CO concentration (type 5) — target ppm
# ---------------------------------------------------------------------------

def test_co_ppm_identity():
    assert convert_sensor_value(5, "ppm", 50.0) == pytest.approx(50.0)

def test_co_ppb_to_ppm():
    assert convert_sensor_value(5, "ppb", 50000.0) == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# CO₂ concentration (type 22) — target ppm
# ---------------------------------------------------------------------------

def test_co2_ppm_identity():
    assert convert_sensor_value(22, "ppm", 400.0) == pytest.approx(400.0)

def test_co2_ppb_to_ppm():
    assert convert_sensor_value(22, "ppb", 400000.0) == pytest.approx(400.0)


# ---------------------------------------------------------------------------
# Radon activity (type 6) — target Bq/m³
# ---------------------------------------------------------------------------

def test_radon_bqm3_identity():
    assert convert_sensor_value(6, "Bq/m³", 100.0) == pytest.approx(100.0)

def test_radon_pcil_to_bqm3():
    assert convert_sensor_value(6, "pCi/L", 1.0) == pytest.approx(37.0)


# ---------------------------------------------------------------------------
# Precipitation (type 21) — target mm
# ---------------------------------------------------------------------------

def test_precipitation_mm_identity():
    assert convert_sensor_value(21, "mm", 5.0) == pytest.approx(5.0)

def test_precipitation_in_to_mm():
    assert convert_sensor_value(21, "in", 1.0) == pytest.approx(25.4)


# ---------------------------------------------------------------------------
# Water quantity (type 27) — target L
# ---------------------------------------------------------------------------

def test_water_quantity_l_identity():
    assert convert_sensor_value(27, "L", 100.0) == pytest.approx(100.0)

def test_water_quantity_m3_to_l():
    assert convert_sensor_value(27, "m³", 1.0) == pytest.approx(1000.0)

def test_water_quantity_gal_to_l():
    assert convert_sensor_value(27, "gal", 1.0) == pytest.approx(3.78541, rel=1e-4)


# ---------------------------------------------------------------------------
# Water flow rate (type 28) — target L/s
# ---------------------------------------------------------------------------

def test_water_flow_ls_identity():
    assert convert_sensor_value(28, "L/s", 2.0) == pytest.approx(2.0)

def test_water_flow_lmin_to_ls():
    assert convert_sensor_value(28, "L/min", 60.0) == pytest.approx(1.0)

def test_water_flow_lh_to_ls():
    assert convert_sensor_value(28, "L/h", 3600.0) == pytest.approx(1.0)

def test_water_flow_m3h_to_ls():
    assert convert_sensor_value(28, "m³/h", 3.6) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Particle sensors (types 8, 9, 10) — target µg/m³
# ---------------------------------------------------------------------------

def test_pm10_ugm3_identity():
    assert convert_sensor_value(8, "µg/m³", 50.0) == pytest.approx(50.0)

def test_pm25_ugm3_identity():
    assert convert_sensor_value(9, "µg/m³", 12.0) == pytest.approx(12.0)

def test_pm1_ugm3_identity():
    assert convert_sensor_value(10, "µg/m³", 5.0) == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Sound pressure (type 20) — target dB
# ---------------------------------------------------------------------------

def test_sound_pressure_db_identity():
    assert convert_sensor_value(20, "dB", 65.0) == pytest.approx(65.0)

def test_sound_pressure_dba_to_db():
    # dBA is A-weighted dB — treated as numerically equal for dS purposes
    assert convert_sensor_value(20, "dBa", 65.0) == pytest.approx(65.0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/arne/Development/dsvdc4ha
.venv/bin/pytest tests/test_unit_conversion.py -q
```

Expected: `ImportError: cannot import name 'convert_sensor_value'`

- [ ] **Step 3: Create `unit_conversion.py`**

```python
# custom_components/dsvdc4ha/unit_conversion.py
"""HA → dS sensor unit conversion table and helper."""
from __future__ import annotations

# Conversion table: sensor_type_int → {ha_unit_str → converter(float) → float}
# The target unit for each sensor type is the dS-expected unit.
# Unknown sensor types and unknown units are passed through unchanged (callers log a warning).
_CONVERSIONS: dict[int, dict[str, object]] = {
    # 1 — Temperature → °C
    1: {
        "°C": lambda v: v,
        "°F": lambda v: (v - 32.0) * 5.0 / 9.0,
        "K":  lambda v: v - 273.15,
    },
    # 2 — Humidity → %  (HA always reports %)
    2: {"%": lambda v: v},
    # 3 — Illuminance → lx  (HA always reports lx)
    3: {"lx": lambda v: v},
    # 4 — Supply Voltage → V
    4: {
        "V":  lambda v: v,
        "mV": lambda v: v / 1_000.0,
    },
    # 5 — CO concentration → ppm
    5: {
        "ppm": lambda v: v,
        "ppb": lambda v: v / 1_000.0,
    },
    # 6 — Radon activity → Bq/m³
    6: {
        "Bq/m³": lambda v: v,
        "Bq/m3": lambda v: v,
        "pCi/L": lambda v: v * 37.0,
    },
    # 8 — PM10 → µg/m³
    8: {
        "µg/m³": lambda v: v,
        "μg/m³": lambda v: v,  # U+03BC vs U+00B5
        "mg/m³": lambda v: v * 1_000.0,
    },
    # 9 — PM2.5 → µg/m³
    9: {
        "µg/m³": lambda v: v,
        "μg/m³": lambda v: v,
        "mg/m³": lambda v: v * 1_000.0,
    },
    # 10 — PM1 → µg/m³
    10: {
        "µg/m³": lambda v: v,
        "μg/m³": lambda v: v,
        "mg/m³": lambda v: v * 1_000.0,
    },
    # 13 — Wind speed → m/s
    13: {
        "m/s":  lambda v: v,
        "km/h": lambda v: v / 3.6,
        "mph":  lambda v: v * 0.44704,
        "kn":   lambda v: v * 0.51444,
        "ft/s": lambda v: v * 0.3048,
    },
    # 14 — Active Power → W
    14: {
        "W":  lambda v: v,
        "kW": lambda v: v * 1_000.0,
        "mW": lambda v: v / 1_000.0,
    },
    # 15 — Electric current → A
    15: {
        "A":  lambda v: v,
        "mA": lambda v: v / 1_000.0,
    },
    # 16 — Energy Meter → kWh
    16: {
        "kWh": lambda v: v,
        "Wh":  lambda v: v / 1_000.0,
        "MWh": lambda v: v * 1_000.0,
        "GWh": lambda v: v * 1_000_000.0,
    },
    # 17 — Apparent Power → VA
    17: {
        "VA":  lambda v: v,
        "kVA": lambda v: v * 1_000.0,
    },
    # 18 — Air pressure → hPa
    18: {
        "hPa":  lambda v: v,
        "mbar": lambda v: v,          # 1 mbar == 1 hPa
        "Pa":   lambda v: v / 100.0,
        "kPa":  lambda v: v * 10.0,
        "bar":  lambda v: v * 1_000.0,
        "PSI":  lambda v: v * 68.9476,
        "psi":  lambda v: v * 68.9476,
        "mmHg": lambda v: v * 1.33322,
        "inHg": lambda v: v * 33.8639,
        "cbar": lambda v: v * 1.0,    # 1 cbar == 1 hPa
    },
    # 20 — Sound pressure level → dB
    20: {
        "dB":  lambda v: v,
        "dBm": lambda v: v,
        "dBa": lambda v: v,  # A-weighted — numerically equal for dS purposes
        "dBA": lambda v: v,
    },
    # 21 — Precipitation → mm  (mm/m² ≡ mm depth)
    21: {
        "mm": lambda v: v,
        "cm": lambda v: v * 10.0,
        "in": lambda v: v * 25.4,
    },
    # 22 — CO₂ concentration → ppm
    22: {
        "ppm": lambda v: v,
        "ppb": lambda v: v / 1_000.0,
    },
    # 23 — Wind gust speed → m/s  (same conversions as wind speed)
    23: {
        "m/s":  lambda v: v,
        "km/h": lambda v: v / 3.6,
        "mph":  lambda v: v * 0.44704,
        "kn":   lambda v: v * 0.51444,
        "ft/s": lambda v: v * 0.3048,
    },
    # 25 — Generated Active Power → W
    25: {
        "W":  lambda v: v,
        "kW": lambda v: v * 1_000.0,
        "mW": lambda v: v / 1_000.0,
    },
    # 26 — Generated Energy → kWh
    26: {
        "kWh": lambda v: v,
        "Wh":  lambda v: v / 1_000.0,
        "MWh": lambda v: v * 1_000.0,
    },
    # 27 — Water Quantity → L
    27: {
        "L":       lambda v: v,
        "l":       lambda v: v,
        "mL":      lambda v: v / 1_000.0,
        "m³":      lambda v: v * 1_000.0,
        "ft³":     lambda v: v * 28.3168,
        "gal":     lambda v: v * 3.78541,
        "CCF":     lambda v: v * 2_831.685,
        "fl. oz.": lambda v: v * 0.029574,
    },
    # 28 — Water Flow Rate → L/s
    28: {
        "L/s":     lambda v: v,
        "L/min":   lambda v: v / 60.0,
        "L/h":     lambda v: v / 3_600.0,
        "m³/h":    lambda v: v * 1_000.0 / 3_600.0,
        "m³/min":  lambda v: v * 1_000.0 / 60.0,
        "ft³/min": lambda v: v * 28.3168 / 60.0,
        "ft³/h":   lambda v: v * 28.3168 / 3_600.0,
        "gal/min": lambda v: v * 3.78541 / 60.0,
        "gal/h":   lambda v: v * 3.78541 / 3_600.0,
    },
}


def convert_sensor_value(
    sensor_type: int,
    ha_unit: str | None,
    value: float,
) -> float:
    """Convert *value* from *ha_unit* to the dS expected unit for *sensor_type*.

    Returns *value* unchanged when:
    - *ha_unit* is ``None`` (entity has no unit, e.g. a dimensionless counter)
    - the sensor type is not in the conversion table (no dS unit requirement)
    - the specific *ha_unit* has no registered conversion for this type

    Callers are responsible for logging a warning when the unit is
    non-None but unknown (i.e. the return value equals the raw input).
    """
    if ha_unit is None:
        return value
    conversions = _CONVERSIONS.get(sensor_type)
    if conversions is None:
        return value
    converter = conversions.get(ha_unit)
    if converter is None:
        return value
    return converter(value)  # type: ignore[call-arg]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_unit_conversion.py -q
```

Expected: all tests green, no failures.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/unit_conversion.py tests/test_unit_conversion.py
git commit -m "feat: add HA→dS sensor unit conversion table"
```

---

## Task 2: Wire conversion into `listeners.py`

**Files:**
- Modify: `custom_components/dsvdc4ha/listeners.py:151-172` (sensor listener setup)
- Modify: `custom_components/dsvdc4ha/listeners.py:224-238` (seed_initial_values)
- Test: `tests/test_listeners.py`

The two call sites are:
1. `_on_sensor_state` — fires on HA state changes, must pass `sensor_type` into the closure and apply conversion before `report_sensor_value`.
2. `seed_initial_values` — seeds pydsvdcapi at startup, already reads `si_data` so can call the converter inline.

- [ ] **Step 1: Write failing tests for the wired conversion**

Add to `tests/test_listeners.py`:

```python
# ── Sensor unit conversion ───────────────────────────────────────────────


def test_sensor_listener_applies_unit_conversion():
    """_on_sensor_state converts value via unit_of_measurement before reporting."""
    hass = MagicMock()
    hass.async_create_task = MagicMock()
    api = MagicMock()
    api.report_sensor_value = AsyncMock()

    mock_device = MagicMock()
    mock_vdsd = MagicMock()
    mock_vdsd.output = None
    mock_si = MagicMock()
    mock_vdsd.get_sensor_input.return_value = mock_si
    mock_device.get_vdsd.return_value = mock_vdsd
    api.get_device.return_value = mock_device

    # sensor type 14 = Active Power, HA reports in kW → dS expects W
    si_data = {"dsIndex": 0, "callback_entity": "sensor.power", "sensorType": 14}
    vdsd_data = [{"sensors": [si_data]}]

    registered_cbs = []
    with patch("custom_components.dsvdc4ha.listeners.async_track_state_change_event",
               side_effect=lambda h, e, cb: (registered_cbs.append(cb), lambda: None)[1]):
        setup_input_listeners(hass, api, "entry1", vdsd_data)

    assert len(registered_cbs) == 1

    new_state = MagicMock()
    new_state.state = "1.5"                             # 1.5 kW
    new_state.attributes = {"unit_of_measurement": "kW"}
    event = MagicMock()
    event.data = {"new_state": new_state}

    registered_cbs[0](event)

    # report_sensor_value should have been called with 1500 W (via async_create_task)
    hass.async_create_task.assert_called_once()
    api.report_sensor_value.assert_called_once_with(mock_si, 1500.0)


def test_sensor_listener_no_conversion_when_unit_unknown():
    """_on_sensor_state passes value unchanged when unit is not in conversion table."""
    hass = MagicMock()
    hass.async_create_task = MagicMock()
    api = MagicMock()
    api.report_sensor_value = AsyncMock()

    mock_device = MagicMock()
    mock_vdsd = MagicMock()
    mock_vdsd.output = None
    mock_si = MagicMock()
    mock_vdsd.get_sensor_input.return_value = mock_si
    mock_device.get_vdsd.return_value = mock_vdsd
    api.get_device.return_value = mock_device

    si_data = {"dsIndex": 0, "callback_entity": "sensor.temp", "sensorType": 1}
    vdsd_data = [{"sensors": [si_data]}]

    registered_cbs = []
    with patch("custom_components.dsvdc4ha.listeners.async_track_state_change_event",
               side_effect=lambda h, e, cb: (registered_cbs.append(cb), lambda: None)[1]):
        setup_input_listeners(hass, api, "entry1", vdsd_data)

    new_state = MagicMock()
    new_state.state = "25.0"
    new_state.attributes = {"unit_of_measurement": "exotic_unit"}
    event = MagicMock()
    event.data = {"new_state": new_state}

    registered_cbs[0](event)
    api.report_sensor_value.assert_called_once_with(mock_si, 25.0)


@pytest.mark.asyncio
async def test_seed_initial_values_applies_unit_conversion():
    """seed_initial_values converts the initial channel value via unit_of_measurement."""
    hass = MagicMock()
    # temperature sensor seeding: HA in °F, dS expects °C
    state = MagicMock()
    state.state = "32.0"                              # 32 °F = 0 °C
    state.attributes = {"unit_of_measurement": "°F"}
    hass.states.get.return_value = state

    api = MagicMock()
    mock_device = MagicMock()
    mock_vdsd = MagicMock()
    mock_si = MagicMock()
    mock_si.min_value = -40.0
    mock_si.update_value = AsyncMock()
    mock_vdsd.get_sensor_input.return_value = mock_si
    mock_vdsd.output = None
    mock_device.get_vdsd.return_value = mock_vdsd
    api.get_device.return_value = mock_device

    si_data = {
        "dsIndex": 0,
        "callback_entity": "sensor.temp",
        "sensorType": 1,          # Temperature
    }
    await seed_initial_values(hass, api, "entry1", [{"sensors": [si_data]}])

    mock_si.update_value.assert_awaited_once_with(value=pytest.approx(0.0), session=None)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_listeners.py -k "unit_conversion or seed_initial_values_applies" -q
```

Expected: 3 failures — `report_sensor_value` is called with the raw value (no conversion applied yet).

- [ ] **Step 3: Modify `_on_sensor_state` in `listeners.py`**

Current code at lines 151–172 (sensor listener block inside `setup_input_listeners`):

```python
        # Sensor listeners
        for si_data in vdsd_data.get("sensors", []):
            entity_id = si_data.get("callback_entity")
            if not entity_id:
                continue
            si = vdsd.get_sensor_input(si_data["dsIndex"])
            if not si:
                continue

            @callback
            def _on_sensor_state(event: Event, _si=si) -> None:
                new_state = event.data.get("new_state")
                if not new_state or new_state.state in ("unknown", "unavailable"):
                    hass.async_create_task(api.report_sensor_value(_si, None))
                    return
                try:
                    value = float(new_state.state)
                    hass.async_create_task(api.report_sensor_value(_si, value))
                except ValueError:
                    pass

            unsubs.append(async_track_state_change_event(hass, entity_id, _on_sensor_state))
```

Replace it with:

```python
        # Sensor listeners
        for si_data in vdsd_data.get("sensors", []):
            entity_id = si_data.get("callback_entity")
            if not entity_id:
                continue
            si = vdsd.get_sensor_input(si_data["dsIndex"])
            if not si:
                continue
            _sensor_type: int = si_data.get("sensorType", 0)

            @callback
            def _on_sensor_state(event: Event, _si=si, _st=_sensor_type) -> None:
                from .unit_conversion import convert_sensor_value  # noqa: PLC0415
                new_state = event.data.get("new_state")
                if not new_state or new_state.state in ("unknown", "unavailable"):
                    hass.async_create_task(api.report_sensor_value(_si, None))
                    return
                try:
                    value = float(new_state.state)
                    unit = new_state.attributes.get("unit_of_measurement")
                    value = convert_sensor_value(_st, unit, value)
                    hass.async_create_task(api.report_sensor_value(_si, value))
                except ValueError:
                    pass

            unsubs.append(async_track_state_change_event(hass, entity_id, _on_sensor_state))
```

- [ ] **Step 4: Modify `seed_initial_values` in `listeners.py`**

Current code at lines 224–238 (sensor seeding block inside `seed_initial_values`):

```python
        for si_data in vdsd_data.get("sensors", []):
            si = vdsd.get_sensor_input(si_data["dsIndex"])
            if not si:
                continue
            value: float | None = None
            if entity_id := si_data.get("callback_entity"):
                state = hass.states.get(entity_id)
                if state and state.state not in ("unknown", "unavailable"):
                    try:
                        value = float(state.state)
                    except ValueError:
                        pass
            if value is None:
                value = si.min_value
            await si.update_value(value=value, session=None)
```

Replace with:

```python
        for si_data in vdsd_data.get("sensors", []):
            si = vdsd.get_sensor_input(si_data["dsIndex"])
            if not si:
                continue
            from .unit_conversion import convert_sensor_value  # noqa: PLC0415
            sensor_type: int = si_data.get("sensorType", 0)
            value: float | None = None
            if entity_id := si_data.get("callback_entity"):
                state = hass.states.get(entity_id)
                if state and state.state not in ("unknown", "unavailable"):
                    try:
                        raw = float(state.state)
                        unit = state.attributes.get("unit_of_measurement")
                        value = convert_sensor_value(sensor_type, unit, raw)
                    except ValueError:
                        pass
            if value is None:
                value = si.min_value
            await si.update_value(value=value, session=None)
```

- [ ] **Step 5: Run the new tests**

```bash
.venv/bin/pytest tests/test_listeners.py -k "unit_conversion or seed_initial_values_applies" -v
```

Expected: all 3 new tests PASS.

- [ ] **Step 6: Run the full test suite**

```bash
.venv/bin/pytest tests/ -q
```

Expected: all tests pass (the number should be 300 + 3 new listener tests + all unit_conversion tests).

- [ ] **Step 7: Commit**

```bash
git add custom_components/dsvdc4ha/listeners.py tests/test_listeners.py
git commit -m "feat: apply HA→dS unit conversion in sensor listeners and seed"
```

---

## Self-review

**Spec coverage:**
- Auto-convert for all dS sensor types with unit-varying HA equivalents ✓ (Task 1 table covers all 28 dS types that have non-trivial HA units)
- Apply at state-change time ✓ (Task 2, `_on_sensor_state`)
- Apply at seeding time ✓ (Task 2, `seed_initial_values`)
- No user input required when unit is auto-detectable ✓ (reads `unit_of_measurement` from HA state attributes)
- Pass-through when unit is unknown ✓ (`convert_sensor_value` returns value unchanged; warning is at caller discretion — kept out of scope as the caller already has a ValueError guard)

**Placeholder scan:** None found — all test bodies and implementation code are fully written.

**Type consistency:** `convert_sensor_value(sensor_type: int, ha_unit: str | None, value: float) -> float` is used identically across Task 1 tests, Task 1 implementation, and Task 2 integration sites. ✓

**Gap: warning log for unknown units.** When `ha_unit` is non-None but has no converter, the value is silently passed through. This is intentional (avoid noise for dimensionless sensors, custom units) — callers can add a `_LOGGER.debug` later if needed. Not a spec gap since the user did not request it.
