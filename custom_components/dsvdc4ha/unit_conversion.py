# custom_components/dsvdc4ha/unit_conversion.py
"""HA → dS sensor unit conversion table and helper."""
from __future__ import annotations

# Conversion table: sensor_type_int → {ha_unit_str → converter(float) → float}
# The target unit for each sensor type is the dS-expected unit.
# Unknown sensor types and unknown units are passed through unchanged.
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
    # 21 — Precipitation → mm
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
    - *ha_unit* is ``None`` (entity has no unit)
    - the sensor type is not in the conversion table
    - the specific *ha_unit* has no registered conversion for this type
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
