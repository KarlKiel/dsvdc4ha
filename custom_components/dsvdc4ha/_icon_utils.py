"""Shared icon helpers: MDI slug mapping, bundled PNG directory, lookup functions."""
from __future__ import annotations

import base64
from pathlib import Path

ICONS_DIR: Path = Path(__file__).parent / "icons"

MDI_DOMAIN_ICONS: dict[str, str] = {
    "light": "lightbulb",
    "switch": "toggle-switch-variant",
    "cover": "window-shutter",
    "cover.awning": "awning",
    "cover.blind": "blinds",
    "cover.curtain": "curtains",
    "cover.door": "door",
    "cover.garage": "garage",
    "cover.gate": "gate",
    "cover.shutter": "window-shutter",
    "binary_sensor": "radiobox-blank",
    "sensor": "eye",
    "event": "calendar-star",
    "number": "ray-vertex",
    "lock": "lock",
}


def bundled_icon_b64(mdi_slug: str) -> str | None:
    """Return base64-encoded 16x16 PNG for a known MDI slug, or None if not bundled."""
    f = ICONS_DIR / f"{mdi_slug}.png"
    try:
        return base64.b64encode(f.read_bytes()).decode() if f.exists() else None
    except OSError:
        return None


def bundled_icon_b64_for(domain: str, device_class: str | None) -> str | None:
    """Return base64-encoded 16x16 PNG for a domain/device_class, or None."""
    slug = MDI_DOMAIN_ICONS.get(f"{domain}.{device_class}") if device_class else None
    slug = slug or MDI_DOMAIN_ICONS.get(domain)
    return bundled_icon_b64(slug) if slug else None
