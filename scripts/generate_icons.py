#!/usr/bin/env python3
"""One-time script: download MDI SVGs from CDN and render to 16x16 PNGs.

Run from the repo root with:
    source .venv/bin/activate
    python scripts/generate_icons.py
"""
import asyncio
import sys
from pathlib import Path

import aiohttp
import cairosvg

ICONS_DIR = Path(__file__).parent.parent / "custom_components/dsvdc4ha/icons"
CDN_BASE = "https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg"

sys.path.insert(0, str(Path(__file__).parent.parent))
from custom_components.dsvdc4ha._icon_utils import MDI_DOMAIN_ICONS


async def main() -> None:
    ICONS_DIR.mkdir(exist_ok=True)
    slugs = sorted(set(MDI_DOMAIN_ICONS.values()))
    print(f"Generating {len(slugs)} icons → {ICONS_DIR}")
    async with aiohttp.ClientSession() as session:
        for slug in slugs:
            url = f"{CDN_BASE}/{slug}.svg"
            async with session.get(url) as resp:
                if resp.status != 200:
                    print(f"  FAIL {slug}: HTTP {resp.status}")
                    continue
                svg_bytes = await resp.read()
            png_bytes = cairosvg.svg2png(bytestring=svg_bytes, output_width=16, output_height=16)
            out = ICONS_DIR / f"{slug}.png"
            out.write_bytes(png_bytes)
            print(f"  OK   {slug} ({len(png_bytes)} bytes)")
    print("Done.")


asyncio.run(main())
