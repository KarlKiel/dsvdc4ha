# vdSD Icon Fix — Bundled PNG Fallback + Startup Migration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix vdSD icons — they show the generic `vdc.png` because `cairosvg` silently fails on systems without `libcairo`, so `icon_data_b64` is never stored in config entries.

**Architecture:** Add a shared `_icon_utils.py` module holding the MDI slug mapping, the icons directory path, and two lookup helpers. Bundle pre-rendered 16×16 PNGs for all known domain/device_class slugs. Update `_resolve_entity_icon()` to use bundled PNGs as fallback when cairosvg/CDN fail. Add a startup migration (`_backfill_missing_icons`) that retroactively fills `icon_data_b64` in existing sub-entries that have none.

**Tech Stack:** pydsvdcapi, cairosvg (dev-time only), aiohttp (icon generation script), Python pathlib, pytest, Home Assistant ConfigEntry/subentry API.

---

## File Map

| File | Change |
|------|--------|
| `custom_components/dsvdc4ha/_icon_utils.py` | **Create**: `MDI_DOMAIN_ICONS`, `ICONS_DIR`, `bundled_icon_b64()`, `bundled_icon_b64_for()` |
| `custom_components/dsvdc4ha/icons/` | **Create**: 12 pre-rendered 16×16 PNG files (one per unique MDI slug) |
| `scripts/generate_icons.py` | **Create**: one-time script to download+render PNGs |
| `custom_components/dsvdc4ha/config_flow.py` | **Modify**: import from `_icon_utils`, remove local `_MDI_DOMAIN_ICONS`, add bundled fallback in `_resolve_entity_icon()` |
| `custom_components/dsvdc4ha/__init__.py` | **Modify**: import `bundled_icon_b64_for`, add `_backfill_missing_icons`, call it in `async_setup_entry` |
| `tests/test_icon_utils.py` | **Create**: 5 unit tests for `_icon_utils` |
| `tests/test_config_flow.py` | **Modify**: 2 new tests for bundled fallback |
| `tests/test_init.py` | **Modify**: 2 new tests for `_backfill_missing_icons` |

---

## Task 1: Add `_icon_utils.py` and bundle pre-rendered PNG icons

**Files:**
- Create: `custom_components/dsvdc4ha/_icon_utils.py`
- Create: `custom_components/dsvdc4ha/icons/*.png` (12 files, via script)
- Create: `scripts/generate_icons.py`
- Create: `tests/test_icon_utils.py`

- [ ] **Step 1: Write 5 failing tests**

Create `tests/test_icon_utils.py`:

```python
"""Tests for _icon_utils shared icon helpers."""
from __future__ import annotations
import base64
from unittest.mock import patch


def test_bundled_icon_b64_returns_none_for_unknown_slug(tmp_path):
    """bundled_icon_b64 returns None when the PNG file does not exist."""
    from custom_components.dsvdc4ha._icon_utils import bundled_icon_b64
    with patch("custom_components.dsvdc4ha._icon_utils.ICONS_DIR", tmp_path):
        assert bundled_icon_b64("nonexistent-icon") is None


def test_bundled_icon_b64_returns_base64_png_for_known_slug(tmp_path):
    """bundled_icon_b64 returns base64-encoded bytes when the file exists."""
    from custom_components.dsvdc4ha._icon_utils import bundled_icon_b64
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    (tmp_path / "lightbulb.png").write_bytes(fake_png)
    with patch("custom_components.dsvdc4ha._icon_utils.ICONS_DIR", tmp_path):
        result = bundled_icon_b64("lightbulb")
    assert result is not None
    assert base64.b64decode(result) == fake_png


def test_bundled_icon_b64_for_returns_icon_for_known_domain(tmp_path):
    """bundled_icon_b64_for resolves domain → slug → PNG."""
    from custom_components.dsvdc4ha._icon_utils import bundled_icon_b64_for
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    (tmp_path / "lightbulb.png").write_bytes(fake_png)  # "light" → "lightbulb"
    with patch("custom_components.dsvdc4ha._icon_utils.ICONS_DIR", tmp_path):
        result = bundled_icon_b64_for("light", None)
    assert result is not None
    assert base64.b64decode(result) == fake_png


def test_bundled_icon_b64_for_returns_none_for_unknown_domain(tmp_path):
    """bundled_icon_b64_for returns None for domains not in MDI_DOMAIN_ICONS."""
    from custom_components.dsvdc4ha._icon_utils import bundled_icon_b64_for
    with patch("custom_components.dsvdc4ha._icon_utils.ICONS_DIR", tmp_path):
        assert bundled_icon_b64_for("weather", None) is None


def test_bundled_icon_b64_for_prefers_device_class_over_domain(tmp_path):
    """bundled_icon_b64_for uses domain.device_class before plain domain."""
    from custom_components.dsvdc4ha._icon_utils import bundled_icon_b64_for
    blind_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 10
    (tmp_path / "blinds.png").write_bytes(blind_png)  # cover.blind → blinds
    with patch("custom_components.dsvdc4ha._icon_utils.ICONS_DIR", tmp_path):
        result = bundled_icon_b64_for("cover", "blind")
    assert result is not None
    assert base64.b64decode(result) == blind_png
```

- [ ] **Step 2: Run tests — must all FAIL**

```bash
cd /home/arne/Development/dsvdc4ha
source .venv/bin/activate
pytest tests/test_icon_utils.py -v
```

Expected: `ImportError` — `_icon_utils` does not exist yet.

- [ ] **Step 3: Create `custom_components/dsvdc4ha/_icon_utils.py`**

```python
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
    """Return base64-encoded 16×16 PNG for a known MDI slug, or None if not bundled."""
    f = ICONS_DIR / f"{mdi_slug}.png"
    try:
        return base64.b64encode(f.read_bytes()).decode() if f.exists() else None
    except OSError:
        return None


def bundled_icon_b64_for(domain: str, device_class: str | None) -> str | None:
    """Return base64-encoded 16×16 PNG for a domain/device_class, or None."""
    slug = MDI_DOMAIN_ICONS.get(f"{domain}.{device_class}") if device_class else None
    slug = slug or MDI_DOMAIN_ICONS.get(domain)
    return bundled_icon_b64(slug) if slug else None
```

- [ ] **Step 4: Run the 5 tests — must all PASS**

```bash
pytest tests/test_icon_utils.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Create the icon generation script**

Create `scripts/generate_icons.py`:

```python
#!/usr/bin/env python3
"""One-time script: download MDI SVGs from CDN and render to 16×16 PNGs.

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
```

- [ ] **Step 6: Run the generation script**

```bash
source .venv/bin/activate
python scripts/generate_icons.py
```

Expected output (12 unique slugs):
```
Generating 12 icons → .../custom_components/dsvdc4ha/icons
  OK   awning (...)
  OK   blinds (...)
  OK   calendar-star (...)
  OK   curtains (...)
  OK   door (...)
  OK   eye (...)
  OK   garage (...)
  OK   gate (...)
  OK   lightbulb (...)
  OK   lock (...)
  OK   radiobox-blank (...)
  OK   ray-vertex (...)
  OK   toggle-switch-variant (...)
  OK   window-shutter (...)
Done.
```

Verify 12 files exist:
```bash
ls custom_components/dsvdc4ha/icons/
```

- [ ] **Step 7: Run full suite — baseline must hold**

```bash
pytest tests/ -q
```

Expected: `268 passed, 1 warning` (263 + 5 new)

- [ ] **Step 8: Commit**

```bash
git add custom_components/dsvdc4ha/_icon_utils.py \
        custom_components/dsvdc4ha/icons/ \
        scripts/generate_icons.py \
        tests/test_icon_utils.py
git commit -m "feat: add _icon_utils with MDI slug mapping and bundled PNG lookup"
```

---

## Task 2: Update `config_flow.py` — import from `_icon_utils`, add bundled fallback

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py`
- Modify: `tests/test_config_flow.py`

- [ ] **Step 1: Write 2 failing tests**

Append to `tests/test_config_flow.py`:

```python
@pytest.mark.asyncio
async def test_resolve_entity_icon_falls_back_to_bundled_when_cairosvg_unavailable(tmp_path):
    """When _cairosvg is None (libcairo missing), bundled PNG is used as fallback."""
    import base64
    # switch domain → toggle-switch-variant slug
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    (tmp_path / "toggle-switch-variant.png").write_bytes(fake_png)

    flow = _make_switch_flow()
    state = MagicMock()
    state.attributes = {}  # no explicit mdi: icon → switch domain fallback
    flow.hass.states.get.return_value = state

    with patch("custom_components.dsvdc4ha.config_flow._cairosvg", None):
        with patch("custom_components.dsvdc4ha._icon_utils.ICONS_DIR", tmp_path):
            icon_name, b64 = await flow._resolve_entity_icon("switch.kitchen")

    assert icon_name == "switch_kitchen"
    assert b64 is not None
    assert base64.b64decode(b64) == fake_png


@pytest.mark.asyncio
async def test_resolve_entity_icon_returns_none_when_cairosvg_and_bundled_both_unavailable(tmp_path):
    """Returns (name, None) when cairosvg unavailable and no bundled icon file exists."""
    flow = _make_switch_flow()
    state = MagicMock()
    state.attributes = {}
    flow.hass.states.get.return_value = state

    # tmp_path is empty — no bundled PNG
    with patch("custom_components.dsvdc4ha.config_flow._cairosvg", None):
        with patch("custom_components.dsvdc4ha._icon_utils.ICONS_DIR", tmp_path):
            icon_name, b64 = await flow._resolve_entity_icon("switch.kitchen")

    assert icon_name == "switch_kitchen"
    assert b64 is None
```

- [ ] **Step 2: Run the 2 tests — must FAIL**

```bash
pytest tests/test_config_flow.py::test_resolve_entity_icon_falls_back_to_bundled_when_cairosvg_unavailable \
       tests/test_config_flow.py::test_resolve_entity_icon_returns_none_when_cairosvg_and_bundled_both_unavailable -v
```

Expected: FAIL — the fallback doesn't exist yet.

- [ ] **Step 3: Update `config_flow.py`**

**3a — Import from `_icon_utils` and remove the local `_MDI_DOMAIN_ICONS` dict.**

Find (around line 652–671):
```python
# MDI icon resolution helpers
...
_MDI_DOMAIN_ICONS: dict[str, str] = {
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
```

Replace with:
```python
# MDI icon resolution helpers
from ._icon_utils import MDI_DOMAIN_ICONS, bundled_icon_b64
```

(Keep `_MDI_SVG_CACHE: dict[str, bytes] = {}` and `_mdi_icon_name_for` unchanged — they're right after.)

**3b — Update `_mdi_icon_name_for` to use the imported name.**

`_mdi_icon_name_for` references `_MDI_DOMAIN_ICONS` internally. Rename those two references to `MDI_DOMAIN_ICONS`:

Find (around line 684–687):
```python
        result = _MDI_DOMAIN_ICONS.get(f"{domain}.{device_class}")
        if result:
            return result
    return _MDI_DOMAIN_ICONS.get(domain)
```

Replace with:
```python
        result = MDI_DOMAIN_ICONS.get(f"{domain}.{device_class}")
        if result:
            return result
    return MDI_DOMAIN_ICONS.get(domain)
```

**3c — Add bundled fallback in `_resolve_entity_icon()`.**

Find (around line 806–812):
```python
        # Path 2: MDI icon (explicit attribute or domain/device_class fallback)
        mdi_name = _mdi_icon_name_for(state, entity_id)
        if mdi_name is None:
            return icon_name, None

        b64 = await _fetch_mdi_icon_b64(self.hass, mdi_name)
        return icon_name, b64
```

Replace with:
```python
        # Path 2: MDI icon — CDN+cairosvg first, bundled PNG fallback
        mdi_name = _mdi_icon_name_for(state, entity_id)
        if mdi_name is None:
            return icon_name, None

        b64 = await _fetch_mdi_icon_b64(self.hass, mdi_name)
        if b64 is None:
            b64 = bundled_icon_b64(mdi_name)
        return icon_name, b64
```

- [ ] **Step 4: Run the 2 new tests — must PASS**

```bash
pytest tests/test_config_flow.py::test_resolve_entity_icon_falls_back_to_bundled_when_cairosvg_unavailable \
       tests/test_config_flow.py::test_resolve_entity_icon_returns_none_when_cairosvg_and_bundled_both_unavailable -v
```

Expected: `2 passed`

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -q
```

Expected: `270 passed, 1 warning` (268 + 2 new)

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py tests/test_config_flow.py
git commit -m "feat: fall back to bundled PNG icon when cairosvg/CDN unavailable"
```

---

## Task 3: Startup icon migration — backfill existing configs

**Files:**
- Modify: `custom_components/dsvdc4ha/__init__.py`
- Modify: `tests/test_init.py`

- [ ] **Step 1: Write 2 failing tests**

Append to `tests/test_init.py`:

```python
@pytest.mark.asyncio
async def test_backfill_missing_icons_fills_icon_for_vdsd_without_data(tmp_path):
    """_backfill_missing_icons sets icon_data_b64 for a vdSD that has none."""
    from custom_components.dsvdc4ha.__init__ import _backfill_missing_icons
    import base64

    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    (tmp_path / "toggle-switch-variant.png").write_bytes(fake_png)

    hass = MagicMock()
    state = MagicMock()
    state.attributes = {}  # no device_class → switch → toggle-switch-variant
    hass.states.get.return_value = state

    vdsd = {
        "name": "Test Switch",
        "buttons": [{"callback_entity": "switch.kitchen"}],
        "binary_inputs": [], "sensors": [], "output": None,
        "icon_name": "switch_kitchen",
    }
    subentry = MagicMock()
    subentry.subentry_id = "sub1"
    subentry.data = {"vdsds": [vdsd]}
    entry = MagicMock()
    entry.subentries = {"sub1": subentry}

    with patch("custom_components.dsvdc4ha._icon_utils.ICONS_DIR", tmp_path):
        await _backfill_missing_icons(hass, entry)

    hass.config_entries.async_update_subentry.assert_called_once()
    call_args = hass.config_entries.async_update_subentry.call_args
    updated_vdsds = call_args.kwargs["data"]["vdsds"]
    assert base64.b64decode(updated_vdsds[0]["icon_data_b64"]) == fake_png


@pytest.mark.asyncio
async def test_backfill_missing_icons_skips_vdsd_with_existing_icon(tmp_path):
    """_backfill_missing_icons does not overwrite an already-present icon_data_b64."""
    from custom_components.dsvdc4ha.__init__ import _backfill_missing_icons

    hass = MagicMock()
    vdsd = {
        "name": "Test",
        "buttons": [{"callback_entity": "switch.kitchen"}],
        "binary_inputs": [], "sensors": [], "output": None,
        "icon_name": "switch_kitchen",
        "icon_data_b64": "EXISTINGDATA",
    }
    subentry = MagicMock()
    subentry.subentry_id = "sub1"
    subentry.data = {"vdsds": [vdsd]}
    entry = MagicMock()
    entry.subentries = {"sub1": subentry}

    with patch("custom_components.dsvdc4ha._icon_utils.ICONS_DIR", tmp_path):
        await _backfill_missing_icons(hass, entry)

    hass.config_entries.async_update_subentry.assert_not_called()
```

- [ ] **Step 2: Run the 2 tests — must FAIL**

```bash
pytest tests/test_init.py::test_backfill_missing_icons_fills_icon_for_vdsd_without_data \
       tests/test_init.py::test_backfill_missing_icons_skips_vdsd_with_existing_icon -v
```

Expected: `ImportError` — `_backfill_missing_icons` does not exist yet.

- [ ] **Step 3: Add `_backfill_missing_icons` to `__init__.py`**

Add at module level (after `_vanish_deleted_devices`, before `async_setup_entry`), and add the import at the top of the file in the local imports block:

**Import** (add to the existing `from .const import ...` line):
```python
from ._icon_utils import bundled_icon_b64_for
```

**New function** (insert before `async_setup_entry`):
```python
async def _backfill_missing_icons(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Backfill icon_data_b64 for vdSDs that have no icon stored.

    Runs once at startup to silently fix existing configs created when
    cairosvg was unavailable (libcairo not installed on the system).
    """
    for subentry in entry.subentries.values():
        vdsds = list(subentry.data.get("vdsds", []))
        updated = False
        for vdsd in vdsds:
            if vdsd.get("icon_data_b64"):
                continue
            for eid in _entity_ids_in_vdsd(vdsd):
                state = hass.states.get(eid)
                if state is None:
                    continue
                domain = eid.split(".")[0]
                device_class = state.attributes.get("device_class")
                b64 = bundled_icon_b64_for(domain, device_class)
                if b64:
                    vdsd["icon_data_b64"] = b64
                    updated = True
                    break
        if updated:
            hass.config_entries.async_update_subentry(
                entry, subentry, data={**subentry.data, "vdsds": vdsds}
            )
```

**Call it** in `async_setup_entry`, before the `for subentry in entry.subentries.values():` loop (around line 100):

Find:
```python
    # Register, seed initial values, then announce each device subentry.
    # Order matters: add_device first (builds the object graph), then wire up
    # HA→dS listeners, then seed current HA state so pydsvdcapi's
    # _wait_for_initial_values() is satisfied before announce() is awaited.
    from .listeners import setup_input_listeners, setup_output_listeners, seed_initial_values
    for subentry in entry.subentries.values():
```

Replace with:
```python
    # Backfill icon_data_b64 for existing devices that were configured when
    # cairosvg was unavailable (silent no-op if all icons are already set).
    await _backfill_missing_icons(hass, entry)

    # Register, seed initial values, then announce each device subentry.
    # Order matters: add_device first (builds the object graph), then wire up
    # HA→dS listeners, then seed current HA state so pydsvdcapi's
    # _wait_for_initial_values() is satisfied before announce() is awaited.
    from .listeners import setup_input_listeners, setup_output_listeners, seed_initial_values
    for subentry in entry.subentries.values():
```

- [ ] **Step 4: Run the 2 new tests — must PASS**

```bash
pytest tests/test_init.py::test_backfill_missing_icons_fills_icon_for_vdsd_without_data \
       tests/test_init.py::test_backfill_missing_icons_skips_vdsd_with_existing_icon -v
```

Expected: `2 passed`

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -q
```

Expected: `272 passed, 1 warning` (270 + 2 new)

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/__init__.py tests/test_init.py
git commit -m "feat: backfill missing vdSD icons at startup for existing configs"
```

---

## Expected Outcome

After all three tasks:

- 12 bundled 16×16 PNG files in `custom_components/dsvdc4ha/icons/`
- `_resolve_entity_icon()` tries CDN+cairosvg first (best quality, works when libcairo installed), then falls back to bundled PNG (always works), then returns `None` (generic vdc.png)
- `_backfill_missing_icons()` runs once at every HA startup and silently fills `icon_data_b64` for any vdSD that lacks it — no user action required for existing configs
- 272 tests pass
