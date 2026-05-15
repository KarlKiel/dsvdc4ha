# MDI Icon Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `_resolve_entity_icon` in `config_flow.py` so MDI icon names (e.g. `mdi:lightbulb`) produce an actual 16×16 PNG instead of falling back to the generic vdc.png.

**Architecture:** Add two module-level helpers — `_mdi_icon_name_for(state, entity_id)` extracts the MDI slug from the entity state's `icon` attribute, or falls back to a hardcoded `_MDI_DOMAIN_ICONS` lookup table. `_fetch_mdi_icon_b64(hass, slug)` fetches the SVG from the MDI CDN (jsDelivr), caches it in `_MDI_SVG_CACHE`, renders to 16×16 PNG with `cairosvg`, and returns base64. `_resolve_entity_icon` tries `entity_picture` first (existing), then delegates to these two helpers. Add `cairosvg` to `manifest.json` requirements so HA installs it.

**Tech Stack:** Python, cairosvg (new requirement), Pillow (already available), pytest.

---

## File Structure

- Modify: `custom_components/dsvdc4ha/config_flow.py:747-750` — insert `_MDI_DOMAIN_ICONS`, `_MDI_SVG_CACHE`, `_mdi_icon_name_for()`, `_fetch_mdi_icon_b64()` between the two class definitions
- Modify: `custom_components/dsvdc4ha/config_flow.py:781-829` — replace `_resolve_entity_icon` body
- Modify: `custom_components/dsvdc4ha/manifest.json` — add `cairosvg` to requirements
- Modify: `tests/test_config_flow.py` — add 7 new tests after the existing icon tests (after line 851)

---

### Task 1: Extend `_resolve_entity_icon` to resolve MDI icons

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py`
- Modify: `custom_components/dsvdc4ha/manifest.json`
- Test: `tests/test_config_flow.py`

**Background:**

`_resolve_entity_icon` currently returns `(icon_name, None)` for any entity that does not have an `entity_picture` URL — which covers almost every entity using a MDI icon (the vast majority). The HA entity state's `icon` attribute holds the MDI slug prefixed by `"mdi:"`, e.g. `"mdi:lightbulb"`. Entities without an explicit `icon` attribute can be matched by domain (and optionally device_class) against `_MDI_DOMAIN_ICONS`. Once the slug is known, the SVG is fetched from `https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/{slug}.svg` and converted to PNG with `cairosvg.svg2png(bytestring=..., output_width=16, output_height=16)`.

`async_get_clientsession` is already imported at line 17. `Any` is already imported at line 8. Both are available to module-level functions.

The seven tests to add:

**Pure unit tests for `_mdi_icon_name_for` (no async, no mocking):**
1. `test_mdi_icon_name_for_returns_explicit_mdi_icon` — `{"icon": "mdi:toggle-switch-variant"}` → `"toggle-switch-variant"`
2. `test_mdi_icon_name_for_returns_domain_fallback` — empty attributes, entity_id `light.lamp` → `"lightbulb"`
3. `test_mdi_icon_name_for_returns_device_class_fallback` — `{"device_class": "blind"}`, entity_id `cover.bedroom_blind` → `"blinds"`
4. `test_mdi_icon_name_for_returns_none_for_unknown_domain` — empty attributes, entity_id `weather.home` → `None`

**Integration tests for `_resolve_entity_icon` MDI path:**
5. `test_resolve_entity_icon_uses_mdi_icon_attribute` — explicit `mdi:` icon attribute → PNG returned
6. `test_resolve_entity_icon_uses_domain_fallback_when_no_explicit_icon` — domain `light`, no icon attr → PNG returned
7. `test_resolve_entity_icon_returns_none_when_mdi_cdn_unreachable` — CDN raises exception → `None`

- [ ] **Step 1: Run the full existing test suite to confirm starting baseline**

  ```bash
  cd /home/arne/Development/dsvdc4ha
  source .venv/bin/activate
  pytest tests/ -q 2>&1 | tail -5
  ```

  Expected: `177 passed`.

- [ ] **Step 2: Add the 7 failing tests to `tests/test_config_flow.py`**

  Append after line 851 (after `# PNG magic bytes` assertion), before the `# Entity-completion screen` section comment. Add the following block:

  ```python
  # ---------------------------------------------------------------------------
  # MDI icon resolution tests
  # ---------------------------------------------------------------------------

  def test_mdi_icon_name_for_returns_explicit_mdi_icon():
      """_mdi_icon_name_for returns the slug from an explicit mdi: icon attribute."""
      from custom_components.dsvdc4ha.config_flow import _mdi_icon_name_for
      state = MagicMock()
      state.attributes = {"icon": "mdi:toggle-switch-variant"}
      assert _mdi_icon_name_for(state, "switch.kitchen") == "toggle-switch-variant"


  def test_mdi_icon_name_for_returns_domain_fallback():
      """_mdi_icon_name_for falls back to domain lookup when no icon attribute."""
      from custom_components.dsvdc4ha.config_flow import _mdi_icon_name_for
      state = MagicMock()
      state.attributes = {}
      assert _mdi_icon_name_for(state, "light.lamp") == "lightbulb"


  def test_mdi_icon_name_for_returns_device_class_fallback():
      """_mdi_icon_name_for uses domain.device_class lookup when no icon attribute."""
      from custom_components.dsvdc4ha.config_flow import _mdi_icon_name_for
      state = MagicMock()
      state.attributes = {"device_class": "blind"}
      assert _mdi_icon_name_for(state, "cover.bedroom_blind") == "blinds"


  def test_mdi_icon_name_for_returns_none_for_unknown_domain():
      """_mdi_icon_name_for returns None for unsupported domains."""
      from custom_components.dsvdc4ha.config_flow import _mdi_icon_name_for
      state = MagicMock()
      state.attributes = {}
      assert _mdi_icon_name_for(state, "weather.home") is None


  @pytest.mark.asyncio
  async def test_resolve_entity_icon_uses_mdi_icon_attribute():
      """_resolve_entity_icon returns a PNG when the entity has an explicit mdi: icon."""
      import base64, io
      from PIL import Image
      from custom_components.dsvdc4ha.config_flow import _MDI_SVG_CACHE

      _MDI_SVG_CACHE.clear()

      flow = _make_switch_flow()
      state = MagicMock()
      state.attributes = {"icon": "mdi:lightbulb"}
      flow.hass.states.get.return_value = state

      fake_svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22A10,10 0 0,1 2,12A10,10 0 0,1 12,2Z"/></svg>'
      buf = io.BytesIO()
      Image.new("RGBA", (16, 16), (0, 0, 0, 255)).save(buf, format="PNG")
      fake_png = buf.getvalue()

      mock_response = AsyncMock()
      mock_response.__aenter__ = AsyncMock(return_value=mock_response)
      mock_response.__aexit__ = AsyncMock(return_value=False)
      mock_response.status = 200
      mock_response.read = AsyncMock(return_value=fake_svg)
      mock_session = MagicMock()
      mock_session.get.return_value = mock_response

      async def mock_executor_job(func, data):
          return func(data)

      flow.hass.async_add_executor_job = AsyncMock(side_effect=mock_executor_job)

      with patch("custom_components.dsvdc4ha.config_flow.async_get_clientsession",
                 return_value=mock_session):
          with patch("cairosvg.svg2png", return_value=fake_png):
              icon_name, b64 = await flow._resolve_entity_icon("switch.kitchen")

      assert icon_name == "switch_kitchen"
      assert b64 is not None
      assert base64.b64decode(b64)[:8] == b"\x89PNG\r\n\x1a\n"


  @pytest.mark.asyncio
  async def test_resolve_entity_icon_uses_domain_fallback_when_no_explicit_icon():
      """_resolve_entity_icon returns a PNG via domain fallback when entity has no icon attr."""
      import base64, io
      from PIL import Image
      from custom_components.dsvdc4ha.config_flow import _MDI_SVG_CACHE

      _MDI_SVG_CACHE.clear()

      flow = _make_switch_flow()
      state = MagicMock()
      state.attributes = {}
      flow.hass.states.get.return_value = state

      fake_svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22A10,10 0 0,1 2,12A10,10 0 0,1 12,2Z"/></svg>'
      buf = io.BytesIO()
      Image.new("RGBA", (16, 16), (255, 255, 0, 255)).save(buf, format="PNG")
      fake_png = buf.getvalue()

      mock_response = AsyncMock()
      mock_response.__aenter__ = AsyncMock(return_value=mock_response)
      mock_response.__aexit__ = AsyncMock(return_value=False)
      mock_response.status = 200
      mock_response.read = AsyncMock(return_value=fake_svg)
      mock_session = MagicMock()
      mock_session.get.return_value = mock_response

      async def mock_executor_job(func, data):
          return func(data)

      flow.hass.async_add_executor_job = AsyncMock(side_effect=mock_executor_job)

      with patch("custom_components.dsvdc4ha.config_flow.async_get_clientsession",
                 return_value=mock_session):
          with patch("cairosvg.svg2png", return_value=fake_png):
              icon_name, b64 = await flow._resolve_entity_icon("light.lamp")

      assert icon_name == "light_lamp"
      assert b64 is not None
      assert base64.b64decode(b64)[:8] == b"\x89PNG\r\n\x1a\n"


  @pytest.mark.asyncio
  async def test_resolve_entity_icon_returns_none_when_mdi_cdn_unreachable():
      """_resolve_entity_icon returns None gracefully when the MDI CDN fetch fails."""
      from custom_components.dsvdc4ha.config_flow import _MDI_SVG_CACHE

      _MDI_SVG_CACHE.clear()

      flow = _make_switch_flow()
      state = MagicMock()
      state.attributes = {"icon": "mdi:lightbulb"}
      flow.hass.states.get.return_value = state

      mock_session = MagicMock()
      mock_session.get.side_effect = Exception("Connection refused")

      with patch("custom_components.dsvdc4ha.config_flow.async_get_clientsession",
                 return_value=mock_session):
          icon_name, b64 = await flow._resolve_entity_icon("switch.kitchen")

      assert icon_name == "switch_kitchen"
      assert b64 is None
  ```

- [ ] **Step 3: Run the 7 new tests to confirm they all FAIL**

  ```bash
  cd /home/arne/Development/dsvdc4ha
  source .venv/bin/activate
  pytest tests/test_config_flow.py::test_mdi_icon_name_for_returns_explicit_mdi_icon \
         tests/test_config_flow.py::test_mdi_icon_name_for_returns_domain_fallback \
         tests/test_config_flow.py::test_mdi_icon_name_for_returns_device_class_fallback \
         tests/test_config_flow.py::test_mdi_icon_name_for_returns_none_for_unknown_domain \
         tests/test_config_flow.py::test_resolve_entity_icon_uses_mdi_icon_attribute \
         tests/test_config_flow.py::test_resolve_entity_icon_uses_domain_fallback_when_no_explicit_icon \
         tests/test_config_flow.py::test_resolve_entity_icon_returns_none_when_mdi_cdn_unreachable \
         -v 2>&1 | tail -20
  ```

  Expected: all 7 FAIL with `ImportError: cannot import name '_mdi_icon_name_for'` or `AttributeError`.

- [ ] **Step 4: Add module-level helpers to `config_flow.py`**

  Insert the following block into `custom_components/dsvdc4ha/config_flow.py` **replacing** lines 747–750 (the section comment before `class VdsdSubentryFlowHandler`):

  ```python
  # ---------------------------------------------------------------------------
  # MDI icon resolution helpers
  # ---------------------------------------------------------------------------

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

  _MDI_SVG_CACHE: dict[str, bytes] = {}


  def _mdi_icon_name_for(state: Any, entity_id: str) -> str | None:
      """Return the MDI icon slug for an entity state, or None if not resolvable."""
      icon: str | None = state.attributes.get("icon")
      if icon and icon.startswith("mdi:"):
          return icon[4:]
      domain = entity_id.split(".")[0]
      device_class: str | None = state.attributes.get("device_class")
      if device_class:
          result = _MDI_DOMAIN_ICONS.get(f"{domain}.{device_class}")
          if result:
              return result
      return _MDI_DOMAIN_ICONS.get(domain)


  async def _fetch_mdi_icon_b64(hass: Any, icon_slug: str) -> str | None:
      """Fetch MDI SVG from CDN, render to 16x16 PNG, return base64 string or None."""
      import aiohttp
      import base64

      svg_bytes = _MDI_SVG_CACHE.get(icon_slug)
      if svg_bytes is None:
          try:
              url = f"https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/{icon_slug}.svg"
              session = async_get_clientsession(hass)
              async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                  if resp.status != 200:
                      return None
                  svg_bytes = await resp.read()
              _MDI_SVG_CACHE[icon_slug] = svg_bytes
          except Exception:
              _LOGGER.debug("Failed to fetch MDI icon %s", icon_slug, exc_info=True)
              return None

      try:
          import cairosvg

          def _svg_to_png(svg: bytes) -> bytes:
              return cairosvg.svg2png(bytestring=svg, output_width=16, output_height=16)

          png_bytes = await hass.async_add_executor_job(_svg_to_png, svg_bytes)
          return base64.b64encode(png_bytes).decode()
      except Exception:
          _LOGGER.debug("Failed to render MDI icon %s to PNG", icon_slug, exc_info=True)
          return None


  # ---------------------------------------------------------------------------
  # Device subentry flow — handles both "from entity" and "from scratch" paths
  # ---------------------------------------------------------------------------
  ```

- [ ] **Step 5: Replace `_resolve_entity_icon` in `config_flow.py`**

  Replace the entire method from line 781 to 829 (the current `_resolve_entity_icon`) with:

  ```python
      async def _resolve_entity_icon(self, entity_id: str) -> tuple[str, str | None]:
          """Return (icon_name, base64_16x16_png_or_None) for an entity.

          icon_name is entity_id with dots replaced by underscores.
          Tries entity_picture first, then MDI icon attribute, then domain fallback.
          Returns None for b64 on any failure.
          """
          import base64
          import io

          icon_name = entity_id.replace(".", "_")
          state = self.hass.states.get(entity_id)
          if state is None:
              return icon_name, None

          # Path 1: entity_picture (camera snapshots, custom pictures)
          picture_url: str | None = state.attributes.get("entity_picture")
          if picture_url:
              try:
                  from PIL import Image
                  import aiohttp

                  if not (picture_url.startswith("http") or picture_url.startswith("//")):
                      api_cfg = getattr(self.hass.config, "api", None)
                      base = str(api_cfg.base_url).rstrip("/") if api_cfg else "http://localhost:8123"
                      picture_url = f"{base}{picture_url}"

                  session = async_get_clientsession(self.hass)
                  async with session.get(
                      picture_url, timeout=aiohttp.ClientTimeout(total=5)
                  ) as resp:
                      if resp.status != 200:
                          return icon_name, None
                      raw = await resp.read()

                  def _resize(data: bytes) -> bytes:
                      img = Image.open(io.BytesIO(data)).convert("RGBA").resize(
                          (16, 16), Image.LANCZOS
                      )
                      out = io.BytesIO()
                      img.save(out, format="PNG")
                      return out.getvalue()

                  resized = await self.hass.async_add_executor_job(_resize, raw)
                  return icon_name, base64.b64encode(resized).decode()
              except Exception:
                  _LOGGER.debug("Failed to resolve icon for %s from entity_picture", entity_id, exc_info=True)
                  return icon_name, None

          # Path 2: MDI icon (explicit attribute or domain/device_class fallback)
          mdi_name = _mdi_icon_name_for(state, entity_id)
          if mdi_name is None:
              return icon_name, None

          b64 = await _fetch_mdi_icon_b64(self.hass, mdi_name)
          return icon_name, b64
  ```

- [ ] **Step 6: Add `cairosvg` to `manifest.json` requirements**

  In `custom_components/dsvdc4ha/manifest.json`, change:

  ```json
  "requirements": ["pydsvdcapi==0.8.1"],
  ```

  to:

  ```json
  "requirements": ["pydsvdcapi==0.8.1", "cairosvg"],
  ```

- [ ] **Step 7: Install `cairosvg` in the dev venv**

  ```bash
  cd /home/arne/Development/dsvdc4ha
  source .venv/bin/activate
  pip install cairosvg -q
  ```

  Expected: installs without error (requires libcairo2 system library, which is present on standard Linux).

- [ ] **Step 8: Run the 7 new tests to confirm they all PASS**

  ```bash
  pytest tests/test_config_flow.py::test_mdi_icon_name_for_returns_explicit_mdi_icon \
         tests/test_config_flow.py::test_mdi_icon_name_for_returns_domain_fallback \
         tests/test_config_flow.py::test_mdi_icon_name_for_returns_device_class_fallback \
         tests/test_config_flow.py::test_mdi_icon_name_for_returns_none_for_unknown_domain \
         tests/test_config_flow.py::test_resolve_entity_icon_uses_mdi_icon_attribute \
         tests/test_config_flow.py::test_resolve_entity_icon_uses_domain_fallback_when_no_explicit_icon \
         tests/test_config_flow.py::test_resolve_entity_icon_returns_none_when_mdi_cdn_unreachable \
         -v 2>&1 | tail -20
  ```

  Expected: all 7 PASS.

- [ ] **Step 9: Run the full test suite**

  ```bash
  pytest tests/ -q 2>&1 | tail -10
  ```

  Expected: all 184 tests pass (177 existing + 7 new), 0 failed.

- [ ] **Step 10: Commit**

  ```bash
  git add custom_components/dsvdc4ha/config_flow.py \
          custom_components/dsvdc4ha/manifest.json \
          tests/test_config_flow.py
  git commit -m "feat: resolve MDI icons to 16x16 PNG for vdSD device icons"
  ```
