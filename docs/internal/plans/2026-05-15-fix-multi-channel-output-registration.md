# Fix Multi-Channel Output Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix a bug where output channels are created but never stored in pydsvdcapi, causing all `POSITIONAL` (covers/shades), `BIPOLAR`, and `CUSTOM` function outputs to have zero channels and silently failing dS↔HA bidirectional control.

**Architecture:** In `api.py`'s `_add_output`, the channel loop calls `OutputChannel(output=output, ...)` but discards the return value — `OutputChannel.__init__` does NOT self-register. For `ON_OFF`/`DIMMER`/`DIMMER_COLOR_TEMP`/`FULL_COLOR_DIMMER` functions, `Output.__init__` auto-creates channels via `FUNCTION_CHANNELS` so those accidentally work; for `POSITIONAL` (function=2), `BIPOLAR` (5), `CUSTOM` (127) there are no auto-created channels, resulting in 0 channels registered. Additionally, `ON_OFF` outputs where entity_mapping uses a non-`BRIGHTNESS` channel type (e.g. `cover/door`, `cover/garage` use `POWER_STATE`=19) register the wrong type, silently breaking the dS→HA apply direction. The fix: call `output.remove_channel(ds_index)` (clears any auto-created channel at that slot) then `output.add_channel(channel_type, ds_index=...)` which properly stores the channel and updates scene table entries.

**Tech Stack:** Python, pydsvdcapi 0.8.1 (`Output.add_channel`, `Output.remove_channel`, `Output.get_channel`), pytest

---

## File Structure

- Modify: `custom_components/dsvdc4ha/api.py` — fix `_add_output` channel registration loop; remove unused `FUNCTION_CHANNELS` import
- Modify: `tests/test_api.py` — add two tests that call `DsvdcApi._add_output` directly to verify channel registration

---

### Task 1: Write failing tests for channel registration

**Files:**
- Modify: `tests/test_api.py`

**Background for implementer:**

`DsvdcApi._add_output(vdsd, data)` is a private sync method. You can call it directly on an unstarted `DsvdcApi` instance — `__init__` only sets instance variables, no network setup needed. Pass a `MagicMock()` for `vdsd`; the `Output` constructor only stores a reference to it. After `_add_output` returns, the `Output` object is accessible via `mock_vdsd.set_output.call_args[0][0]` (the positional arg passed to `vdsd.set_output(output)`).

`output.get_channel(ds_index)` returns `OutputChannel | None`. `OutputChannel.channel_type` is `OutputChannelType | int` — use `int(ch.channel_type)` for comparison.

Before the fix:
- POSITIONAL (function=2): `FUNCTION_CHANNELS` has no entry → `_auto_create_channels` creates nothing → `_add_output` loop creates `OutputChannel` objects but discards them → `get_channel(0)` returns `None` → assertion fails.
- ON_OFF (function=0): `_auto_create_channels` creates `BRIGHTNESS` (type=1) at index 0 → `_add_output` loop creates a `POWER_STATE` channel but discards it → `get_channel(0).channel_type` is still `BRIGHTNESS`=1 → assertion fails.

- [ ] **Step 1: Add the two failing tests to `tests/test_api.py`**

  No new imports are needed — `DsvdcApi`, `MagicMock`, and `pytest` are already imported. The test passes integer function values directly in the dict; `_add_output` handles the enum conversion internally.

  Add these two tests at the bottom of the file:
  ```python
  def test_positional_output_registers_both_channels():
      """Bug: POSITIONAL (function=2) outputs had 0 channels because OutputChannel
      objects were created but discarded — they don't self-register."""
      api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")
      mock_vdsd = MagicMock()
      output_data = {
          "name": "test-blind",
          "function": 2,      # POSITIONAL — not in FUNCTION_CHANNELS
          "defaultGroup": 2,
          "activeGroup": 2,
          "groups": [2],
          "channels": [
              {"dsIndex": 0, "channelType": 8},   # SHADE_POSITION_INDOOR
              {"dsIndex": 1, "channelType": 10},  # SHADE_ANGLE_INDOOR
          ],
      }
      api._add_output(mock_vdsd, output_data)
      actual_output = mock_vdsd.set_output.call_args[0][0]

      ch0 = actual_output.get_channel(0)
      ch1 = actual_output.get_channel(1)
      assert ch0 is not None, "channel at dsIndex 0 must be registered"
      assert ch1 is not None, "channel at dsIndex 1 must be registered"
      assert int(ch0.channel_type) == 8
      assert int(ch1.channel_type) == 10


  def test_on_off_output_channel_type_replaced_correctly():
      """Bug: ON_OFF (function=0) auto-creates BRIGHTNESS (type=1) at dsIndex 0.
      When entity_mapping specifies POWER_STATE (type=19), apply_pending_channels
      builds {BRIGHTNESS: v} not {POWER_STATE: v} — dS→HA direction silently broken."""
      api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")
      mock_vdsd = MagicMock()
      output_data = {
          "name": "test-door",
          "function": 0,      # ON_OFF — auto-creates BRIGHTNESS at dsIndex 0
          "defaultGroup": 7,
          "activeGroup": 7,
          "groups": [7],
          "channels": [
              {"dsIndex": 0, "channelType": 19},  # POWER_STATE — not BRIGHTNESS
          ],
      }
      api._add_output(mock_vdsd, output_data)
      actual_output = mock_vdsd.set_output.call_args[0][0]

      ch = actual_output.get_channel(0)
      assert ch is not None
      assert int(ch.channel_type) == 19, (
          f"expected POWER_STATE (19), got {int(ch.channel_type)} — "
          "auto-created BRIGHTNESS channel was not replaced"
      )
  ```

- [ ] **Step 2: Run the tests and confirm they fail**

  ```bash
  cd /home/arne/Development/dsvdc4ha
  source .venv/bin/activate
  pytest tests/test_api.py::test_positional_output_registers_both_channels \
         tests/test_api.py::test_on_off_output_channel_type_replaced_correctly -v
  ```

  Expected: both FAIL — `AssertionError: channel at dsIndex 0 must be registered` and `AssertionError: expected POWER_STATE (19), got 1`.

- [ ] **Step 3: Commit the failing tests**

  ```bash
  git add tests/test_api.py
  git commit -m "test: add failing tests for multi-channel and wrong-type output registration"
  ```

---

### Task 2: Fix `_add_output` channel registration

**Files:**
- Modify: `custom_components/dsvdc4ha/api.py:38,450-459`

**Background for implementer:**

`output.add_channel(channel_type, *, ds_index, name, min_value, max_value, resolution)` stores the channel in `output._channels[ds_index]` and calls `_ensure_scene_channel_entries()`. It raises `ValueError` if `ds_index` is already in use, so call `output.remove_channel(ds_index)` first to clear any auto-created channel (remove_channel is a no-op if the slot is empty). `FUNCTION_CHANNELS` is imported on line 38 but unused anywhere — remove it to avoid lint warnings.

- [ ] **Step 1: Apply the fix**

  **Change 1** — line 38, remove `FUNCTION_CHANNELS` from the import:

  Old:
  ```python
  from pydsvdcapi.output import FUNCTION_CHANNELS, Output
  ```
  New:
  ```python
  from pydsvdcapi.output import Output
  ```

  **Change 2** — lines 450–459, replace the channel loop so the full `_add_output` method reads:

  ```python
  def _add_output(self, vdsd: Vdsd, data: dict[str, Any]) -> None:
      output = Output(
          vdsd=vdsd,
          name=data["name"],
          function=OutputFunction(data["function"]),
          output_usage=OutputUsage(data.get("outputUsage", 0)),
          default_group=data["defaultGroup"],
          active_group=data["activeGroup"],
          groups=set(data["groups"]),
          variable_ramp=data.get("variableRamp", False),
          push_changes=True,
          mode=OutputMode(data["mode"]) if data.get("mode") is not None else None,
          on_threshold=data.get("onThreshold"),
          min_brightness=data.get("minBrightness"),
          max_power=data.get("maxPower"),
      )
      for ch_data in data.get("channels", []):
          ds_index = ch_data["dsIndex"]
          output.remove_channel(ds_index)
          output.add_channel(
              OutputChannelType(ch_data["channelType"]),
              ds_index=ds_index,
              name=ch_data.get("name"),
              min_value=ch_data.get("min"),
              max_value=ch_data.get("max"),
              resolution=ch_data.get("resolution"),
          )
      vdsd.set_output(output)
  ```

  The `OutputChannel` import on line 39 stays — it is still used for the `report_channel_value` type annotation.

- [ ] **Step 2: Run only the two new tests to verify they now pass**

  ```bash
  cd /home/arne/Development/dsvdc4ha
  source .venv/bin/activate
  pytest tests/test_api.py::test_positional_output_registers_both_channels \
         tests/test_api.py::test_on_off_output_channel_type_replaced_correctly -v
  ```

  Expected: both PASS.

- [ ] **Step 3: Run the full test suite**

  ```bash
  pytest tests/ -q
  ```

  Expected: 216 passed, 0 failed (214 existing + 2 new).

- [ ] **Step 4: Commit**

  ```bash
  git add custom_components/dsvdc4ha/api.py
  git commit -m "fix: register output channels via add_channel to fix zero-channel POSITIONAL/BIPOLAR/CUSTOM outputs"
  ```
