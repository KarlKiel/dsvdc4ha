# vdSD Names from HA Entity Name Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every vdSD name reflect the HA entity's friendly name rather than prepending the HA device name.

**Architecture:** Two independent creation paths set vdSD names today — the device-based path via `_assign_names` in `device_grouper.py` and the entity-based path inline in `config_flow.py`. Both currently produce `"{device_name} — {entity_label}"`. Removing the `"{device_name} — "` prefix from both gives names that match exactly what users see for each entity in the HA UI.

**Tech Stack:** Python, pytest. No new dependencies.

---

## File Structure

- Modify: `custom_components/dsvdc4ha/device_grouper.py` — remove `device_name` prefix from `_assign_names`; the `device_name` parameter becomes unused and is dropped from the function signature; update call site
- Modify: `custom_components/dsvdc4ha/config_flow.py` — change line 1009 to use `friendly_name` alone
- Modify: `tests/test_device_grouper.py` — update two `_assign_names`-output assertions
- Modify: `tests/test_config_flow.py` — update one entity-path name assertion

---

### Task 1: Fix device-based path naming in `device_grouper.py`

**Files:**
- Modify: `custom_components/dsvdc4ha/device_grouper.py:58-72,152`
- Test: `tests/test_device_grouper.py`

**Background for implementer:**

`_assign_names(plans, device_name)` at line 58 is a private helper called once from `compute_vdsd_plan` (line 152). It currently produces:
- unique label → `f"{device_name} — {label}"`
- duplicate label → `f"{device_name} — {label} {n}"`

After this task it should produce:
- unique label → `label`
- duplicate label → `f"{label} {n}"`

The `device_name` parameter is no longer needed inside the function, so remove it. Update the call at line 152 accordingly. `resolve_vdsd_plan` already has its own `device_name` parameter marked `# noqa: ARG001` (it's unused there — the name is embedded in `plan.name`). That signature stays unchanged.

`_primary_entity_label(plan)` returns the entity's friendly name (or a group label fallback like `"Light"`, `"Shadow"`) — this is already the right value for the vdSD name.

Two existing tests in `tests/test_device_grouper.py` assert on the old format with the device prefix:
- `test_plan_naming_unique_groups` at line 182 — asserts `"My Device — Living Room Lamp"` and `"My Device — Bedroom Blind"`
- `test_plan_naming_duplicate_entity_names_get_suffix` at line 193 — asserts `"My Device — Lamp 1"` and `"My Device — Lamp 2"`

These are the tests that must FAIL before the fix and PASS after.

- [ ] **Step 1: Run the two existing tests to confirm they currently pass (they will break in Step 2)**

  ```bash
  cd /home/arne/Development/dsvdc4ha
  source .venv/bin/activate
  pytest tests/test_device_grouper.py::test_plan_naming_unique_groups \
         tests/test_device_grouper.py::test_plan_naming_duplicate_entity_names_get_suffix -v
  ```

  Expected: both PASS (showing the current "wrong" behavior).

- [ ] **Step 2: Update the two tests to assert on the new format (they will now FAIL)**

  In `tests/test_device_grouper.py`, change lines 189-190 and 200-201:

  ```python
  def test_plan_naming_unique_groups():
      entities = [
          _entity("light.lamp", "light", _LIGHT_MAPPING, friendly_name="Living Room Lamp"),
          _entity("cover.blind", "cover", _COVER_MAPPING, friendly_name="Bedroom Blind"),
      ]
      plans, _ = compute_vdsd_plan(entities, "My Device")
      names = {p.name for p in plans}
      assert "Living Room Lamp" in names
      assert "Bedroom Blind" in names


  def test_plan_naming_duplicate_entity_names_get_suffix():
      entities = [
          _entity("light.a", "light", _LIGHT_MAPPING, friendly_name="Lamp"),
          _entity("light.b", "light", _LIGHT_MAPPING, friendly_name="Lamp"),
      ]
      plans, _ = compute_vdsd_plan(entities, "My Device")
      names = [p.name for p in plans]
      assert "Lamp 1" in names
      assert "Lamp 2" in names
  ```

- [ ] **Step 3: Run the two tests to confirm they now FAIL**

  ```bash
  pytest tests/test_device_grouper.py::test_plan_naming_unique_groups \
         tests/test_device_grouper.py::test_plan_naming_duplicate_entity_names_get_suffix -v
  ```

  Expected: both FAIL — `AssertionError: assert "Living Room Lamp" in {"My Device — Living Room Lamp", ...}`

- [ ] **Step 4: Apply the fix to `device_grouper.py`**

  Replace the `_assign_names` function (lines 58–71) and update its call site (line 152):

  ```python
  def _assign_names(plans: list[VdsdPlan]) -> None:
      label_counts: dict[str, int] = {}
      for plan in plans:
          label = _primary_entity_label(plan)
          label_counts[label] = label_counts.get(label, 0) + 1

      label_seen: dict[str, int] = {}
      for plan in plans:
          label = _primary_entity_label(plan)
          if label_counts[label] == 1:
              plan.name = label
          else:
              label_seen[label] = label_seen.get(label, 0) + 1
              plan.name = f"{label} {label_seen[label]}"
  ```

  And at line 152, change the call site:

  ```python
      _assign_names(plans)
      return plans, unsupported
  ```

- [ ] **Step 5: Run the two tests to confirm they now PASS**

  ```bash
  pytest tests/test_device_grouper.py::test_plan_naming_unique_groups \
         tests/test_device_grouper.py::test_plan_naming_duplicate_entity_names_get_suffix -v
  ```

  Expected: both PASS.

- [ ] **Step 6: Run the full test suite**

  ```bash
  pytest tests/ -q
  ```

  Expected: all 177 tests pass, 0 failed.

- [ ] **Step 7: Commit**

  ```bash
  git add custom_components/dsvdc4ha/device_grouper.py tests/test_device_grouper.py
  git commit -m "feat: use entity friendly name alone as vdSD name in device-based creation"
  ```

---

### Task 2: Fix entity-based path naming in `config_flow.py`

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py:1009`
- Test: `tests/test_config_flow.py:771-787`

**Background for implementer:**

`_build_entity_vdsd_and_continue` builds the vdSD dict at lines 1002–1010. The `"name"` field at line 1009 is:

```python
"name": f"{self._device_name} — {friendly_name}",
```

where:
- `self._device_name` = the HA device's name (e.g., `"Kitchen"`)
- `friendly_name` = `(state.name if state else None) or entity_id` at line 999 — the HA entity's friendly name (e.g., `"Kitchen Switch"`)

The fix: use `friendly_name` directly.

There is one existing test that asserts on the old combined format:

`test_entity_flow_vdsd_name_combines_device_and_entity_name` at line 771 in `tests/test_config_flow.py`:
```python
assert flow._current_vdsd["name"] == "Kitchen — Kitchen Switch"
```

This test must FAIL before the fix and PASS after (with the updated assertion). The test description also needs updating to reflect the new behavior.

`self._device_name` is still used elsewhere (config entry title at line 1633, subentry data at line 1659, manual creation path). Only line 1009 changes.

- [ ] **Step 1: Update the test to assert the new format (it will now FAIL)**

  In `tests/test_config_flow.py`, change lines 771–787:

  ```python
  @pytest.mark.asyncio
  async def test_entity_flow_vdsd_name_uses_entity_friendly_name():
      """_build_entity_vdsd_and_continue names the vdSD with the entity's friendly name only."""
      flow = _make_switch_flow()
      flow._device_name = "Kitchen"
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

      assert flow._current_vdsd["name"] == "Kitchen Switch"
  ```

  (Rename the function and change `"Kitchen — Kitchen Switch"` to `"Kitchen Switch"`.)

- [ ] **Step 2: Run the test to confirm it FAILS**

  ```bash
  cd /home/arne/Development/dsvdc4ha
  source .venv/bin/activate
  pytest tests/test_config_flow.py::test_entity_flow_vdsd_name_uses_entity_friendly_name -v
  ```

  Expected: FAIL — `AssertionError: assert "Kitchen — Kitchen Switch" == "Kitchen Switch"`

- [ ] **Step 3: Apply the fix to `config_flow.py`**

  At line 1009, change:

  ```python
              "name": f"{self._device_name} — {friendly_name}",
  ```

  to:

  ```python
              "name": friendly_name,
  ```

- [ ] **Step 4: Run the test to confirm it PASSES**

  ```bash
  pytest tests/test_config_flow.py::test_entity_flow_vdsd_name_uses_entity_friendly_name -v
  ```

  Expected: PASS.

- [ ] **Step 5: Run the full test suite**

  ```bash
  pytest tests/ -q
  ```

  Expected: all 177 tests pass, 0 failed.

- [ ] **Step 6: Commit**

  ```bash
  git add custom_components/dsvdc4ha/config_flow.py tests/test_config_flow.py
  git commit -m "feat: use entity friendly name alone as vdSD name in entity-based creation"
  ```
