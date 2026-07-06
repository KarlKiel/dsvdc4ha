"""Shared icon helpers: MDI slug mapping, bundled PNG directory, lookup functions."""
from __future__ import annotations

import base64
from collections import OrderedDict
from pathlib import Path

_MDI_SVG_CACHE_MAXSIZE = 256
_mdi_svg_cache: OrderedDict[str, bytes] = OrderedDict()

ICONS_DIR: Path = Path(__file__).parent / "icons"

# Pre-load all bundled PNGs at import time so runtime lookups are I/O-free.
_ICON_CACHE: dict[str, str] = {
    f.stem: base64.b64encode(f.read_bytes()).decode()
    for f in ICONS_DIR.glob("*.png")
    if f.is_file()
}

MDI_DOMAIN_ICONS: dict[str, str] = {
    # Domains (fallback when no device_class match)
    "light": "lightbulb",
    "switch": "toggle-switch-variant",
    "cover": "window-shutter",
    "binary_sensor": "radiobox-blank",
    "sensor": "eye",
    "event": "calendar-star",
    "number": "ray-vertex",
    "lock": "lock",
    "fan": "fan",
    # cover device classes
    "cover.awning": "awning",
    "cover.blind": "blinds",
    "cover.curtain": "curtains",
    "cover.damper": "valve-open",
    "cover.door": "door",
    "cover.garage": "garage",
    "cover.gate": "gate",
    "cover.shade": "roller-shade",
    "cover.shutter": "window-shutter",
    "cover.window": "window-open",
    # binary_sensor device classes
    "binary_sensor.battery": "battery",
    "binary_sensor.battery_charging": "battery-charging",
    "binary_sensor.carbon_monoxide": "molecule-co",
    "binary_sensor.cold": "snowflake",
    "binary_sensor.connectivity": "check-network",
    "binary_sensor.door": "door-open",
    "binary_sensor.garage_door": "garage-open",
    "binary_sensor.gas": "smoke-detector-alert",
    "binary_sensor.heat": "fire",
    "binary_sensor.light": "brightness-5",
    "binary_sensor.lock": "lock-open",
    "binary_sensor.moisture": "water",
    "binary_sensor.motion": "motion-sensor",
    "binary_sensor.moving": "run",
    "binary_sensor.occupancy": "home",
    "binary_sensor.opening": "square-rounded",
    "binary_sensor.plug": "power-plug",
    "binary_sensor.power": "power",
    "binary_sensor.presence": "home",
    "binary_sensor.problem": "alert-circle",
    "binary_sensor.running": "run",
    "binary_sensor.safety": "shield-check",
    "binary_sensor.smoke": "smoke-detector",
    "binary_sensor.sound": "ear-hearing",
    "binary_sensor.tamper": "alert-decagram",
    "binary_sensor.update": "package-up",
    "binary_sensor.vibration": "vibrate",
    "binary_sensor.window": "window-open",
    # sensor device classes
    "sensor.apparent_power": "flash",
    "sensor.aqi": "air-filter",
    "sensor.atmospheric_pressure": "gauge",
    "sensor.battery": "battery",
    "sensor.carbon_dioxide": "molecule-co2",
    "sensor.carbon_monoxide": "molecule-co",
    "sensor.current": "current-ac",
    "sensor.distance": "arrow-left-right",
    "sensor.duration": "clock",
    "sensor.energy": "lightning-bolt",
    "sensor.frequency": "sine-wave",
    "sensor.gas": "meter-gas",
    "sensor.humidity": "water-percent",
    "sensor.illuminance": "brightness-5",
    "sensor.moisture": "water-percent",
    "sensor.pm1": "air-filter",
    "sensor.pm10": "air-filter",
    "sensor.pm25": "air-filter",
    "sensor.power": "flash",
    "sensor.power_factor": "angle-acute",
    "sensor.precipitation": "weather-rainy",
    "sensor.sound_pressure": "ear-hearing",
    "sensor.speed": "speedometer",
    "sensor.temperature": "thermometer",
    "sensor.voltage": "sine-wave",
    "sensor.water": "water",
    "sensor.weight": "weight",
    "sensor.wind_speed": "weather-windy",
    # event device classes
    "event.button": "button-pointer",
    "event.doorbell": "doorbell",
    "event.motion": "motion-sensor",
}


def get_mdi_svg_cache(slug: str) -> bytes | None:
    """Return cached SVG bytes for *slug*, promoting it to most-recently-used."""
    if slug in _mdi_svg_cache:
        _mdi_svg_cache.move_to_end(slug)
        return _mdi_svg_cache[slug]
    return None


def put_mdi_svg_cache(slug: str, data: bytes) -> None:
    """Store SVG bytes, evicting the oldest entry when the cache is full."""
    _mdi_svg_cache[slug] = data
    _mdi_svg_cache.move_to_end(slug)
    while len(_mdi_svg_cache) > _MDI_SVG_CACHE_MAXSIZE:
        _mdi_svg_cache.popitem(last=False)


def bundled_icon_b64(mdi_slug: str) -> str | None:
    """Return base64-encoded 16x16 PNG for a known MDI slug, or None if not bundled."""
    return _ICON_CACHE.get(mdi_slug)


def bundled_icon_b64_for(domain: str, device_class: str | None) -> str | None:
    """Return base64-encoded 16x16 PNG for a domain/device_class, or None."""
    slug = MDI_DOMAIN_ICONS.get(f"{domain}.{device_class}") if device_class else None
    slug = slug or MDI_DOMAIN_ICONS.get(domain)
    return bundled_icon_b64(slug) if slug else None
