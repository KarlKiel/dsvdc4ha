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
