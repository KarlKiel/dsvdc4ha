# Entity Flow UX Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the entity-based device creation flow with better labels, a multi-entity completion screen, entity-name-based vdSD naming, and automatic entity icon derivation.

**Architecture:** Four independent tasks touching `config_flow.py`, `device_grouper.py`, `api.py`, and the two translation files. Tasks are ordered by dependency: labels first (independent), then the multi-entity screen (needs `_creation_mode` field), then naming (touches grouper + flow), then icons (touches flow + api). Tests are added or updated per-task.

**Tech Stack:** Python, Home Assistant config_flow API, pydsvdcapi, PIL/Pillow for image resizing, HA `aiohttp_client` for HTTP fetching.

---

## File Structure

| File | Changes |
|------|---------|
| `custom_components/dsvdc4ha/config_flow.py` | Labels, `_creation_mode` field, entity_completion step, naming, icon helper |
| `custom_components/dsvdc4ha/device_grouper.py` | `_assign_names` uses entity friendly name instead of group label |
| `custom_components/dsvdc4ha/api.py` | `_build_vdsd` reads per-vdSD icon from data |
| `custom_components/dsvdc4ha/strings.json` | Add `entity_completion` step entry |
| `custom_components/dsvdc4ha/translations/en.json` | Add `entity_completion` step entry |
| `tests/test_config_flow.py` | New + updated tests for all flow changes |
| `tests/test_device_grouper.py` | Update naming tests to use entity friendly names |

---

### Task 1: Rename and reorder creation mode options

The current labels and order are wrong. Rename all three options and swap the order of the 2nd and 3rd entries.

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py:793-803`
- Test: `tests/test_config_flow.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config_flow.py` (after the existing `test_creation_mode_*` tests):

```python
@pytest.mark.asyncio
async def test_creation_mode_option_labels_and_order():
    """creation_mode form has correct labels in the correct order."""
    flow = _make_subentry_flow()
    result = await flow.async_step_creation_mode(user_input=None)
    assert result["type"] == FlowResultType.FORM
    options = result["data_schema"].schema["mode"].config["options"]
    assert options[0]["value"] == "from_entity"
    assert "recommended" in options[0]["label"].lower()
    assert options[1]["value"] == "from_ha_device"
    assert options[2]["value"] == "from_scratch"
    assert "BETA" in options[2]["label"]
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /home/arne/Development/dsvdc4ha && .venv/bin/pytest tests/test_config_flow.py::test_creation_mode_option_labels_and_order -v
```

Expected: FAIL — labels don't match yet.

- [ ] **Step 3: Update `async_step_creation_mode` in `config_flow.py`**

Find lines 793–803 in `config_flow.py` (the `schema = vol.Schema({...})` inside `async_step_creation_mode`). Replace the `SelectSelector` options block:

```python
        schema = vol.Schema({
            vol.Required("mode", default="from_entity"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=[
                    selector.SelectOptionDict(value="from_entity",
                                              label="Create device based on HA entities (recommended)"),
                    selector.SelectOptionDict(value="from_ha_device",
                                              label="Create device based on HA device"),
                    selector.SelectOptionDict(value="from_scratch",
                                              label="Create device from scratch (BETA)"),
                ])
            ),
        })
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/arne/Development/dsvdc4ha && .venv/bin/pytest tests/test_config_flow.py -k "creation_mode" -v
```

Expected: All `creation_mode` tests pass (routing tests still pass since mode values haven't changed, label test now passes).

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py tests/test_config_flow.py
git commit -m "feat: rename and reorder creation mode options"
```

---

### Task 2: Entity-completion screen and multi-entity entity flow

Add a `_creation_mode` field so the flow knows which path is active. Add a new `entity_completion` screen that replaces `device_summary` for the `from_entity` path. When "Add additional..." is selected, loop back to `entity_picker` preserving the already-built vdSDs and device info.

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py` (lines 752–778, 784–803, 807–845, 1506–1515, end of file)
- Modify: `custom_components/dsvdc4ha/strings.json`
- Modify: `custom_components/dsvdc4ha/translations/en.json`
- Test: `tests/test_config_flow.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_config_flow.py`:

```python
@pytest.mark.asyncio
async def test_model_features_from_entity_routes_to_entity_completion():
    """model_features submit routes to entity_completion when mode is from_entity."""
    flow = _make_subentry_flow()
    flow._creation_mode = "from_entity"
    flow._current_vdsd = {
        "displayId": "switch", "primaryGroup": 8, "model": "switch",
        "vendorName": "V", "modelVersion": "1.0", "modelUID": "V_switch",
        "name": "Kitchen — Switch", "active": True,
        "identify_action": None, "firmwareUpdate_action": None, "optional": {},
    }
    flow._current_buttons = []
    flow._current_binary_inputs = []
    flow._current_sensors = []
    flow._current_output = None

    result = await flow.async_step_model_features({"features": []})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "entity_completion"


@pytest.mark.asyncio
async def test_entity_completion_create_makes_entry():
    """entity_completion: 'create' action creates the subentry directly."""
    flow = _make_subentry_flow()
    flow._device_name = "Kitchen Switch"
    flow._vendor_name = "Acme"
    flow._display_id = "switch"
    flow._vdsds = [{"displayId": "switch", "primaryGroup": 8, "name": "Kitchen Switch — switch",
                    "model": "switch", "vendorName": "Acme", "modelVersion": "1.0",
                    "modelUID": "Acmeswitch", "active": True, "identify_action": None,
                    "firmwareUpdate_action": None, "optional": {}, "buttons": [],
                    "binary_inputs": [], "sensors": [], "output": None}]

    result = await flow.async_step_entity_completion({"action": "create"})
    assert result["type"] == "create_entry"
    assert result["title"] == "Kitchen Switch"
    assert len(result["data"]["vdsds"]) == 1


@pytest.mark.asyncio
async def test_entity_completion_add_vdsd_returns_to_entity_picker():
    """entity_completion: 'add_vdsd' resets per-vdSD state and goes to entity_picker."""
    flow = _make_subentry_flow()
    flow._device_name = "Kitchen Switch"
    flow._vendor_name = "Acme"
    flow._display_id = "switch"
    flow._vdsds = [{"name": "Kitchen Switch — switch"}]

    result = await flow.async_step_entity_completion({"action": "add_vdsd"})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "entity_picker"
    # Device info preserved
    assert flow._device_name == "Kitchen Switch"
    # Per-vdSD state reset
    assert flow._current_vdsd == {}
    assert flow._current_buttons == []


@pytest.mark.asyncio
async def test_entity_picker_preserves_device_info_on_second_pick():
    """entity_picker does not overwrite _device_name/_vendor_name when _vdsds is already populated."""
    flow = _make_subentry_flow()
    flow._device_name = "First Device"
    flow._vendor_name = "Acme"
    flow._display_id = "model"
    flow._vdsds = [{"name": "First Device — entity"}]  # already have one vdSD

    # Simulate: new entity on a different HA device (would overwrite if not guarded)
    state = MagicMock()
    state.name = "Other Device"
    state.attributes = {}
    flow.hass.states.get.return_value = state

    from custom_components.dsvdc4ha.entity_mapping import get_entity_mapping
    mapping = get_entity_mapping("switch", None)
    with patch("custom_components.dsvdc4ha.config_flow.get_entity_mapping", return_value=mapping), \
         patch("custom_components.dsvdc4ha.config_flow.needs_user_input", return_value=False), \
         patch.object(flow, "_build_entity_vdsd_and_continue",
                      new=AsyncMock(return_value={"type": "form", "step_id": "entity_user_input"})):
        await flow.async_step_entity_picker({"entity_id": "switch.second"})

    # Should NOT have overwritten with "Other Device"
    assert flow._device_name == "First Device"
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/arne/Development/dsvdc4ha && .venv/bin/pytest tests/test_config_flow.py -k "entity_completion or entity_picker_preserves or model_features_from_entity" -v
```

Expected: AttributeError (`_creation_mode` doesn't exist) or FAIL.

- [ ] **Step 3: Add `_creation_mode` to `__init__` and set it in `async_step_creation_mode`**

In `config_flow.py` at line 777 (end of `__init__`), add one line before the closing of `__init__`:

```python
        self._creation_mode: str = "from_entity"
```

In `async_step_creation_mode` (line 787), before the `if mode == "from_entity":` block, add:

```python
            self._creation_mode = mode
```

So the full submit block becomes:

```python
        if user_input is not None:
            mode = user_input.get("mode", "from_scratch")
            self._creation_mode = mode
            if mode == "from_entity":
                return await self.async_step_entity_picker()
            if mode == "from_ha_device":
                return await self.async_step_device_picker()
            return await self.async_step_device_info()
```

- [ ] **Step 4: Guard device info update in `async_step_entity_picker`**

In `async_step_entity_picker` (line 840–842), the block that sets `_device_name`, `_vendor_name`, `_display_id`:

```python
                    # Only set device identity on the first entity pick
                    if not self._vdsds:
                        self._device_name = friendly_name
                        self._vendor_name = manufacturer
                        self._display_id = model or domain.title()
```

Replace the current three lines (840–842):
```python
                    self._device_name = friendly_name
                    self._vendor_name = manufacturer
                    self._display_id = model or domain.title()
```
With:
```python
                    if not self._vdsds:
                        self._device_name = friendly_name
                        self._vendor_name = manufacturer
                        self._display_id = model or domain.title()
```

- [ ] **Step 5: Update `async_step_model_features` to route based on `_creation_mode`**

In `async_step_model_features` (line 1514–1515), replace:

```python
            self._vdsds.append(dict(self._current_vdsd))
            return await self.async_step_device_summary()
```

With:

```python
            self._vdsds.append(dict(self._current_vdsd))
            if self._creation_mode == "from_entity":
                return await self.async_step_entity_completion()
            return await self.async_step_device_summary()
```

- [ ] **Step 6: Add `async_step_entity_completion` to `config_flow.py`**

Add this method after `async_step_model_features` (after line 1537):

```python
    async def async_step_entity_completion(self, user_input: dict | None = None):
        """Entity-based flow: create the device or add another vdSD component."""
        if user_input is not None:
            action = user_input.get("action", "create")
            if action == "add_vdsd":
                # Reset per-vdSD state; preserve _device_name/_vendor_name/_display_id/_vdsds
                self._current_vdsd = {}
                self._current_buttons = []
                self._current_binary_inputs = []
                self._current_sensors = []
                self._current_output = None
                self._current_channels = []
                self._entity_id = ""
                self._entity_mapping = None
                return await self.async_step_entity_picker()
            return self.async_create_entry(
                title=self._device_name,
                data={
                    "name": self._device_name,
                    "vendorName": self._vendor_name,
                    "displayId": self._display_id,
                    "vdsds": self._vdsds,
                },
            )

        vdsd_summary = [
            f"{v.get('name', v.get('displayId', '?'))} (group {v['primaryGroup']})"
            for v in self._vdsds
        ]
        schema = vol.Schema({
            vol.Required("action", default="create"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=[
                    selector.SelectOptionDict(value="create", label="Create device"),
                    selector.SelectOptionDict(value="add_vdsd",
                                              label="Add additional device component (vdSD)"),
                ])
            ),
        })
        return self.async_show_form(
            step_id="entity_completion",
            data_schema=schema,
            description_placeholders={
                "device_name": self._device_name,
                "vdsds": ", ".join(vdsd_summary),
            },
        )
```

- [ ] **Step 7: Add `entity_completion` step to `strings.json`**

In `custom_components/dsvdc4ha/strings.json`, inside `config_subentries.device.step`, add after the `model_features` entry:

```json
        "entity_completion": {
          "title": "Complete Device — {device_name}",
          "description": "Configured vdSD components: {vdsds}\n\nChoose whether to create the device now or add another vdSD component first.",
          "data": {
            "action": "Action"
          }
        },
```

- [ ] **Step 8: Add same entry to `translations/en.json`**

In `custom_components/dsvdc4ha/translations/en.json`, inside `config_subentries.device.step`, add the identical block:

```json
        "entity_completion": {
          "title": "Complete Device — {device_name}",
          "description": "Configured vdSD components: {vdsds}\n\nChoose whether to create the device now or add another vdSD component first.",
          "data": {
            "action": "Action"
          }
        },
```

- [ ] **Step 9: Run tests to verify they pass**

```bash
cd /home/arne/Development/dsvdc4ha && .venv/bin/pytest tests/test_config_flow.py -k "entity_completion or entity_picker_preserves or model_features_from_entity" -v
```

Expected: All 4 new tests pass.

- [ ] **Step 10: Run full test suite**

```bash
cd /home/arne/Development/dsvdc4ha && .venv/bin/pytest tests/ -v
```

Expected: All existing tests still pass (device_summary tests for from_scratch path still work since `_creation_mode` defaults to `"from_entity"` but those tests bypass `model_features` and call `async_step_device_summary` directly).

Wait — the test `test_full_device_subentry_flow_creates_entry` calls `async_step_model_features` with the from_scratch path. This test does NOT set `_creation_mode`, so it will default to `"from_entity"` and route to `entity_completion` instead of `device_summary`. Need to fix that test.

Find `test_full_device_subentry_flow_creates_entry` and add `flow._creation_mode = "from_scratch"` before calling `async_step_model_features`:

```python
async def test_full_device_subentry_flow_creates_entry():
    flow = _make_subentry_flow()

    await flow.async_step_device_info(
        {"name": "Test Lamp", "vendorName": "Acme", "displayId": "LampV1"}
    )
    await flow.async_step_vdsd_creation(
        {"displayId": "LampUnit", "primaryGroup": "1", "modelVersion": "v1"}
    )
    await flow.async_step_vdsd_overview({"action": "next"})
    flow._creation_mode = "from_scratch"  # ← add this line
    await flow.async_step_model_features({"features": []})
    result = await flow.async_step_device_summary({"action": "create", "confirm": True})
    ...
```

Also, update `async_step_device_info` to set `_creation_mode = "from_scratch"` internally (best approach, keeps tests clean). In `async_step_device_info` (line 1390–1396):

```python
    async def async_step_device_info(self, user_input: dict | None = None):
        """Collect basic device identity."""
        if user_input is not None:
            self._creation_mode = "from_scratch"
            self._device_name = user_input["name"]
            self._vendor_name = user_input["vendorName"]
            self._display_id = user_input["displayId"]
            return await self.async_step_vdsd_creation()
        return self.async_show_form(step_id="device_info", data_schema=DEVICE_INFO_SCHEMA)
```

(Set `_creation_mode = "from_scratch"` here so it's always set correctly for the from_scratch path regardless of how tests enter the flow.)

- [ ] **Step 11: Run full test suite again**

```bash
cd /home/arne/Development/dsvdc4ha && .venv/bin/pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 12: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py \
        custom_components/dsvdc4ha/strings.json \
        custom_components/dsvdc4ha/translations/en.json \
        tests/test_config_flow.py
git commit -m "feat: add entity-completion screen with multi-vdSD support for entity flow"
```

---

### Task 3: vdSD name = `<devicename> — <entityname>`

For the entity-based flow: the vdSD name in `_build_entity_vdsd_and_continue` should be `"{device_name} — {entity_friendly_name}"`.

For the HA-device flow: `_assign_names` in `device_grouper.py` should use the primary entity's `friendly_name` instead of the group label.

From-scratch flow: unchanged — user provides names manually.

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py:953`
- Modify: `custom_components/dsvdc4ha/device_grouper.py:48-61`
- Test: `tests/test_device_grouper.py` (update two naming tests)
- Test: `tests/test_config_flow.py` (add naming test for entity flow)

- [ ] **Step 1: Write failing tests**

In `tests/test_device_grouper.py`, find and replace the two naming tests:

```python
def test_plan_naming_unique_groups():
    entities = [
        _entity("light.lamp", "light", _LIGHT_MAPPING, friendly_name="Living Room Lamp"),
        _entity("cover.blind", "cover", _COVER_MAPPING, friendly_name="Bedroom Blind"),
    ]
    plans, _ = compute_vdsd_plan(entities, "My Device")
    names = {p.name for p in plans}
    assert "My Device — Living Room Lamp" in names
    assert "My Device — Bedroom Blind" in names


def test_plan_naming_duplicate_entity_names_get_suffix():
    entities = [
        _entity("light.a", "light", _LIGHT_MAPPING, friendly_name="Lamp"),
        _entity("light.b", "light", _LIGHT_MAPPING, friendly_name="Lamp"),
    ]
    plans, _ = compute_vdsd_plan(entities, "My Device")
    names = [p.name for p in plans]
    assert "My Device — Lamp 1" in names
    assert "My Device — Lamp 2" in names
```

Add to `tests/test_config_flow.py`:

```python
@pytest.mark.asyncio
async def test_entity_flow_vdsd_name_combines_device_and_entity_name():
    """_build_entity_vdsd_and_continue names the vdSD as '<device> — <entity>'."""
    flow = _make_switch_flow()
    flow._device_name = "Kitchen"
    # Give the entity state a known name
    state = MagicMock()
    state.name = "Kitchen Switch"
    state.state = "off"
    state.attributes = {}
    flow.hass.states.get.return_value = state

    with patch.object(flow, "async_step_model_features",
                      new=AsyncMock(return_value={"type": "form", "step_id": "model_features"})):
        with patch.object(flow, "async_step_entity_channel_mapping",
                          new=AsyncMock(return_value={"type": "form", "step_id": "entity_channel_mapping"})):
            await flow._build_entity_vdsd_and_continue({})

    assert flow._current_vdsd["name"] == "Kitchen — Kitchen Switch"
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/arne/Development/dsvdc4ha && .venv/bin/pytest tests/test_device_grouper.py::test_plan_naming_unique_groups tests/test_device_grouper.py::test_plan_naming_duplicate_entity_names_get_suffix tests/test_config_flow.py::test_entity_flow_vdsd_name_combines_device_and_entity_name -v
```

Expected: FAIL (old assertions fail, new test gets old name).

- [ ] **Step 3: Update `_assign_names` in `device_grouper.py`**

Replace lines 48–61 (the entire `_assign_names` function and the preceding `_GROUP_LABELS` dict stays):

```python
def _primary_entity_label(plan: VdsdPlan) -> str:
    """Return the friendly name of the plan's primary entity, or a group label fallback."""
    for entity in [plan.output_entity, plan.binary_input_entity, plan.button_entity]:
        if entity is not None:
            return entity.friendly_name
    if plan.sensor_entities:
        return plan.sensor_entities[0].friendly_name
    return _GROUP_LABELS.get(plan.primary_group, f"Group {plan.primary_group}")


def _assign_names(plans: list[VdsdPlan], device_name: str) -> None:
    label_counts: dict[str, int] = {}
    for plan in plans:
        label = _primary_entity_label(plan)
        label_counts[label] = label_counts.get(label, 0) + 1

    label_seen: dict[str, int] = {}
    for plan in plans:
        label = _primary_entity_label(plan)
        if label_counts[label] == 1:
            plan.name = f"{device_name} — {label}"
        else:
            label_seen[label] = label_seen.get(label, 0) + 1
            plan.name = f"{device_name} — {label} {label_seen[label]}"
```

- [ ] **Step 4: Update `_build_entity_vdsd_and_continue` in `config_flow.py`**

Find line 953 in `config_flow.py` (inside `_build_entity_vdsd_and_continue`):

```python
            "name": self._device_name,          # human-readable name goes here
```

Change to:

```python
            "name": f"{self._device_name} — {friendly_name}",
```

- [ ] **Step 5: Run all naming tests**

```bash
cd /home/arne/Development/dsvdc4ha && .venv/bin/pytest tests/test_device_grouper.py tests/test_config_flow.py::test_entity_flow_vdsd_name_combines_device_and_entity_name -v
```

Expected: All naming tests pass, no regressions in other grouper tests.

- [ ] **Step 6: Run full test suite**

```bash
cd /home/arne/Development/dsvdc4ha && .venv/bin/pytest tests/ -v
```

Expected: All tests pass. Note: `test_plan_naming_duplicate_groups_get_suffix` will be replaced by `test_plan_naming_duplicate_entity_names_get_suffix` — the old test name is gone. Make sure you've deleted it from the file.

- [ ] **Step 7: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py \
        custom_components/dsvdc4ha/device_grouper.py \
        tests/test_device_grouper.py \
        tests/test_config_flow.py
git commit -m "feat: vdSD name always combines device name and entity friendly name"
```

---

### Task 4: Derive entity icon from HA for vdSD device icon

Per the mapping spec: `deviceIcon16` = fetch `entity.entity_picture` URL → resize to 16×16 PNG; `deviceIconName` = `entity_id` with `.` replaced by `_`.

Implementation:
1. Add `_resolve_entity_icon(entity_id) → (icon_name: str, b64_png: str | None)` to `VdsdSubentryFlowHandler`
2. Call it in `_build_entity_vdsd_and_continue` and in `async_step_device_plan_summary`
3. Store results as `icon_name` and `icon_data_b64` in the vdSD dict (JSON-safe)
4. In `api.py`'s `_build_vdsd`, decode and use these fields if present

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py` (new helper + two call sites)
- Modify: `custom_components/dsvdc4ha/api.py:344-357` (`_build_vdsd`)
- Test: `tests/test_config_flow.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_config_flow.py`:

```python
@pytest.mark.asyncio
async def test_entity_flow_sets_icon_name_in_vdsd():
    """_build_entity_vdsd_and_continue stores icon_name in the vdSD dict."""
    flow = _make_switch_flow()
    state = MagicMock()
    state.name = "Kitchen Switch"
    state.state = "off"
    state.attributes = {}
    flow.hass.states.get.return_value = state

    with patch.object(flow, "async_step_model_features",
                      new=AsyncMock(return_value={"type": "form", "step_id": "model_features"})):
        with patch.object(flow, "async_step_entity_channel_mapping",
                          new=AsyncMock(return_value={"type": "form", "step_id": "entity_channel_mapping"})):
            await flow._build_entity_vdsd_and_continue({})

    assert flow._current_vdsd.get("icon_name") == "switch_kitchen"


@pytest.mark.asyncio
async def test_entity_flow_fetches_icon_when_entity_picture_available():
    """_resolve_entity_icon stores base64 PNG when entity_picture is present."""
    flow = _make_switch_flow()

    import base64, io
    from PIL import Image
    # Tiny 1x1 red PNG
    buf = io.BytesIO()
    Image.new("RGBA", (1, 1), (255, 0, 0, 255)).save(buf, format="PNG")
    fake_png = buf.getvalue()

    state = MagicMock()
    state.name = "Kitchen Switch"
    state.state = "off"
    state.attributes = {"entity_picture": "/api/entity_pic/switch.kitchen"}
    flow.hass.states.get.return_value = state
    flow.hass.config.api = MagicMock()
    flow.hass.config.api.base_url = "http://localhost:8123"

    mock_response = AsyncMock()
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    mock_response.status = 200
    mock_response.read = AsyncMock(return_value=fake_png)
    mock_session = MagicMock()
    mock_session.get.return_value = mock_response

    with patch("custom_components.dsvdc4ha.config_flow.async_get_clientsession",
               return_value=mock_session):
        icon_name, b64 = await flow._resolve_entity_icon("switch.kitchen")

    assert icon_name == "switch_kitchen"
    assert b64 is not None
    decoded = base64.b64decode(b64)
    assert decoded[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes
```

Add to `tests/test_api.py`:

```python
def test_build_vdsd_uses_per_vdsd_icon_when_present():
    """_build_vdsd uses icon_data_b64 and icon_name from vdSD data instead of global fallback."""
    import base64, io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGBA", (16, 16), (0, 128, 0, 255)).save(buf, format="PNG")
    entity_icon = buf.getvalue()
    icon_b64 = base64.b64encode(entity_icon).decode()

    from custom_components.dsvdc4ha.api import DsvdcApi
    from unittest.mock import MagicMock, patch
    from pydsvdcapi.vdsd import Device, Vdsd
    from pydsvdcapi.dsuid import DsUid, DsUidNamespace

    api = DsvdcApi.__new__(DsvdcApi)
    api._icon_bytes = b"fallback"  # global fallback should NOT be used
    api._config_url = "http://test"

    device = MagicMock(spec=Device)
    vdsd_data = {
        "displayId": "switch", "primaryGroup": 8, "model": "switch",
        "vendorName": "Acme", "modelVersion": "1.0", "modelUID": "Acmeswitch",
        "name": "Kitchen — switch", "active": True, "identify_action": None,
        "firmwareUpdate_action": None, "optional": {}, "buttons": [],
        "binary_inputs": [], "sensors": [], "output": None,
        "icon_name": "switch_kitchen",
        "icon_data_b64": icon_b64,
    }

    with patch("custom_components.dsvdc4ha.api.Vdsd") as MockVdsd:
        mock_vdsd = MagicMock()
        MockVdsd.return_value = mock_vdsd
        mock_vdsd.model_features = []
        api._build_vdsd(device, 0, vdsd_data)
        call_kwargs = MockVdsd.call_args.kwargs
        assert call_kwargs["device_icon_16"] == entity_icon
        assert call_kwargs["device_icon_name"] == "switch_kitchen"
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/arne/Development/dsvdc4ha && .venv/bin/pytest tests/test_config_flow.py::test_entity_flow_sets_icon_name_in_vdsd tests/test_config_flow.py::test_entity_flow_fetches_icon_when_entity_picture_available tests/test_api.py::test_build_vdsd_uses_per_vdsd_icon_when_present -v
```

Expected: AttributeError or FAIL — method doesn't exist yet.

- [ ] **Step 3: Add imports to `config_flow.py`**

At the top of `config_flow.py`, after the existing imports, add:

```python
import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
```

- [ ] **Step 4: Add `_resolve_entity_icon` to `VdsdSubentryFlowHandler`**

Add this method to `VdsdSubentryFlowHandler`, just before `async_step_user` (around line 779):

```python
    async def _resolve_entity_icon(self, entity_id: str) -> tuple[str, str | None]:
        """Return (icon_name, base64_16x16_png_or_None) for an entity.

        icon_name is the entity_id with dots replaced by underscores.
        If the entity has an entity_picture attribute, fetches and resizes to 16×16 PNG.
        Returns None for the b64 component on any failure.
        """
        import asyncio
        import base64
        import io

        icon_name = entity_id.replace(".", "_")
        state = self.hass.states.get(entity_id)
        if state is None:
            return icon_name, None

        picture_url: str | None = state.attributes.get("entity_picture")
        if not picture_url:
            return icon_name, None

        try:
            from PIL import Image

            if not picture_url.startswith("http"):
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

            resized = await asyncio.get_event_loop().run_in_executor(None, _resize, raw)
            return icon_name, base64.b64encode(resized).decode()
        except Exception:
            _LOGGER.debug("Failed to resolve icon for %s", entity_id, exc_info=True)
            return icon_name, None
```

- [ ] **Step 5: Call `_resolve_entity_icon` in `_build_entity_vdsd_and_continue`**

At the end of `_build_entity_vdsd_and_continue`, before the channel routing block (around line 1081, after `self._current_channels = ...`), add:

```python
        # Resolve icon for this entity
        icon_name, icon_b64 = await self._resolve_entity_icon(entity_id)
        vdsd["icon_name"] = icon_name
        if icon_b64:
            vdsd["icon_data_b64"] = icon_b64
        self._current_vdsd = vdsd
```

(Replace the existing `self._current_vdsd = vdsd` line with the block above to ensure `vdsd` is updated before assignment.)

The exact replacement: find the block starting at line 1081:
```python
        self._current_vdsd = vdsd
        self._current_buttons = vdsd["buttons"]
```

Replace with:
```python
        icon_name, icon_b64 = await self._resolve_entity_icon(entity_id)
        vdsd["icon_name"] = icon_name
        if icon_b64:
            vdsd["icon_data_b64"] = icon_b64
        self._current_vdsd = vdsd
        self._current_buttons = vdsd["buttons"]
```

- [ ] **Step 6: Call `_resolve_entity_icon` in `async_step_device_plan_summary` for HA-device flow**

In `async_step_device_plan_summary` (around line 1296–1302), after the plan resolution loop, add icon resolution:

```python
            for plan in self._vdsd_plans:
                plan.resolved_vdsd = resolve_vdsd_plan(
                    plan, self._device_name, self._vendor_name,
                    self._display_id, entity_states,
                )
                # Add icon for primary entity
                primary_e = (
                    plan.output_entity
                    or plan.binary_input_entity
                    or plan.button_entity
                    or (plan.sensor_entities[0] if plan.sensor_entities else None)
                )
                if primary_e and plan.resolved_vdsd is not None:
                    icon_name, icon_b64 = await self._resolve_entity_icon(
                        primary_e.entity_id
                    )
                    plan.resolved_vdsd["icon_name"] = icon_name
                    if icon_b64:
                        plan.resolved_vdsd["icon_data_b64"] = icon_b64
```

- [ ] **Step 7: Update `_build_vdsd` in `api.py` to use per-vdSD icon**

Add `import base64` at the top of `api.py` (after the existing stdlib imports, e.g., after `from pathlib import Path`).

In `_build_vdsd` (line 344), replace:

```python
        vdsd = Vdsd(
            ...
            device_icon_16=self._icon_bytes,
            device_icon_name=VDC_DEVICE_ICON_NAME,
        )
```

With:

```python
        icon_bytes = (
            base64.b64decode(data["icon_data_b64"])
            if data.get("icon_data_b64")
            else self._icon_bytes
        )
        icon_name = data.get("icon_name") or VDC_DEVICE_ICON_NAME
        vdsd = Vdsd(
            device=device,
            primary_group=ColorGroup(data["primaryGroup"]),
            subdevice_index=idx,
            name=data.get("name", data["displayId"]),
            model=data["model"],
            model_version=data.get("modelVersion"),
            model_uid=data.get("modelUID"),
            vendor_name=data.get("vendorName"),
            config_url=self._config_url,
            device_icon_16=icon_bytes,
            device_icon_name=icon_name,
        )
```

- [ ] **Step 8: Run icon tests**

```bash
cd /home/arne/Development/dsvdc4ha && .venv/bin/pytest tests/test_config_flow.py::test_entity_flow_sets_icon_name_in_vdsd tests/test_config_flow.py::test_entity_flow_fetches_icon_when_entity_picture_available tests/test_api.py::test_build_vdsd_uses_per_vdsd_icon_when_present -v
```

Expected: All 3 pass.

- [ ] **Step 9: Run full test suite**

```bash
cd /home/arne/Development/dsvdc4ha && .venv/bin/pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 10: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py \
        custom_components/dsvdc4ha/api.py \
        tests/test_config_flow.py \
        tests/test_api.py
git commit -m "feat: derive vdSD icon from HA entity picture"
```
