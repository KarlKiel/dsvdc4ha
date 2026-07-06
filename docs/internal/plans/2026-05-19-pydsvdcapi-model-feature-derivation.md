# pydsvdcapi Model-Feature Derivation — Remove Local Mirror

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete `_compute_auto_features()` from the config flow and replace it with a call to the real `pydsvdcapi.Vdsd.derive_model_features()`, so feature derivation logic lives in exactly one place.

**Architecture:** Four instance-method helpers (`_add_button`, `_add_binary_input`, `_add_sensor`, `_add_output`) in `DsvdcApi` use zero instance state; they become module-level functions. A new module-level function `derive_model_features_for_config(vdsd_data)` uses a minimal stand-in for `Device` (the only constructor dependency that is not meaningful for derivation), builds a real `Vdsd`, adds components via those helpers, calls `derive_model_features()`, and returns the feature set. The config flow imports and calls this function instead of `_compute_auto_features()`. The old mirror function is deleted.

**Tech Stack:** pydsvdcapi (`Vdsd`, `DsUid`, `BinaryInput`, `ButtonInput`, `SensorInput`, `Output`, `ColorGroup`), Python, pytest.

---

## File Map

| File | Change |
|------|--------|
| `custom_components/dsvdc4ha/api.py` | Tasks 1 + 2: promote helpers to module-level, add `_PreviewDevice` + `derive_model_features_for_config` |
| `custom_components/dsvdc4ha/config_flow.py` | Task 3: import new function, replace both call sites, delete `_compute_auto_features` |
| `tests/test_api.py` | Task 2: 3 new unit tests |
| `tests/test_entity_mapping_bindings.py` | Task 3: delete `test_compute_auto_features_uses_enum_for_joker` (tests a function that no longer exists) |

---

## Task 1: Promote builder helpers to module-level functions

`_add_button`, `_add_binary_input`, `_add_sensor`, `_add_output` are instance methods of `DsvdcApi` that reference only their arguments — `self` is never used. Making them module-level allows both `DsvdcApi._build_vdsd()` and the upcoming preview function to call them without importing the class.

**Files:**
- Modify: `custom_components/dsvdc4ha/api.py` — remove `self` from four helpers, call them directly in `_build_vdsd`

- [ ] **Step 1: Verify that `self` is truly unused in each helper**

```bash
cd /home/arne/Development/dsvdc4ha
grep -A 20 "def _add_button\|def _add_binary_input\|def _add_sensor\|def _add_output" custom_components/dsvdc4ha/api.py | grep "self\."
```

Expected: no output (nothing accesses `self.` inside those four methods).

- [ ] **Step 2: Convert the four helpers**

In `custom_components/dsvdc4ha/api.py`, replace the four instance methods with module-level functions. Move them to just *before* the `DsvdcApi` class definition (they are currently inside the class). Change `def _add_*(self, vdsd, data)` → `def _add_*(vdsd, data)`.

The four functions after the change:

```python
def _add_button(vdsd: Vdsd, data: dict[str, Any]) -> None:
    btn = ButtonInput(
        vdsd=vdsd,
        ds_index=data["dsIndex"],
        name=data["name"],
        button_type=ButtonType(data["buttonType"]),
        button_element_id=ButtonElementID(data["buttonElementID"]),
        group=data["group"],
        function=data["function"],
        mode=ButtonMode(data["mode"]),
        channel=data.get("channel", 0),
        supports_local_key_mode=data.get("supportsLocalKeyMode", False),
        sets_local_priority=data.get("setsLocalPriority", False),
        calls_present=data.get("callsPresent", True),
        button_id=data.get("buttonID", 0),
    )
    vdsd.add_button_input(btn)


def _add_binary_input(vdsd: Vdsd, data: dict[str, Any]) -> None:
    bi = BinaryInput(
        vdsd=vdsd,
        ds_index=data["dsIndex"],
        name=data["name"],
        sensor_function=BinaryInputType(data["sensorFunction"]),
        hardwired_function=BinaryInputType(data.get("hardwiredFunction", 0)),
        group=data.get("group", 0),
        update_interval=float(data.get("updateInterval", 0)),
        input_type=data.get("inputType", 1),
        input_usage=BinaryInputUsage(data.get("inputUsage", 0)),
    )
    vdsd.add_binary_input(bi)


def _add_sensor(vdsd: Vdsd, data: dict[str, Any]) -> None:
    si = SensorInput(
        vdsd=vdsd,
        ds_index=data["dsIndex"],
        name=data["name"],
        sensor_type=SensorType(data["sensorType"]),
        sensor_usage=SensorUsage(data.get("sensorUsage", 0) or 1),
        group=data.get("group", 0),
        min_value=float(data["min"]),
        max_value=float(data["max"]),
        resolution=float(data["resolution"]),
        update_interval=float(data.get("updateInterval", 0)),
        alive_sign_interval=float(data.get("aliveSignInterval", 0)),
        min_push_interval=float(data.get("minPushInterval", 2.0)),
        changes_only_interval=float(data.get("changesOnlyInterval", 0)),
    )
    vdsd.add_sensor_input(si)


def _add_output(vdsd: Vdsd, data: dict[str, Any]) -> None:
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

- [ ] **Step 3: Update `_build_vdsd` to call the module-level functions**

Inside `DsvdcApi._build_vdsd()`, change the four `self._add_*` calls to direct calls:

```python
        for btn_data in data.get("buttons", []):
            _add_button(vdsd, btn_data)
        for bi_data in data.get("binary_inputs", []):
            _add_binary_input(vdsd, bi_data)
        for si_data in data.get("sensors", []):
            _add_sensor(vdsd, si_data)
        if output_data := data.get("output"):
            _add_output(vdsd, output_data)
```

- [ ] **Step 4: Run all tests — must be identical to baseline**

```bash
source .venv/bin/activate && pytest tests/ -q
```

Expected: `259 passed, 1 warning`

- [ ] **Step 5: Commit**

```bash
git add custom_components/dsvdc4ha/api.py
git commit -m "refactor: promote _add_button/binary_input/sensor/output to module-level functions"
```

---

## Task 2: Add `derive_model_features_for_config()` + tests

Add a module-level function that builds a minimal `Vdsd` using a lightweight stand-in for `Device` (the only constructor dependency that is irrelevant to feature derivation), populates it with components from a raw config dict, calls pydsvdcapi's `derive_model_features()`, and returns the resulting feature set. No feature rules live in our code.

**Files:**
- Modify: `custom_components/dsvdc4ha/api.py` — add `_PreviewDevice` class and `derive_model_features_for_config()`
- Modify: `tests/test_api.py` — 3 new tests

### Why `_PreviewDevice`?

`Vdsd.__init__` requires `device: Device`. It only uses it for `device.dsuid.derive_subdevice(subdevice_index)`. A stand-in with a valid `DsUid` attribute satisfies this without instantiating a full `Device → Vdc → VdcHost` chain.

- [ ] **Step 1: Write three failing tests**

Add to `tests/test_api.py`:

```python
def test_derive_model_features_for_config_binary_input():
    """Binary input → akmsensor only; akminput and akmdelay must NOT appear."""
    from custom_components.dsvdc4ha.api import derive_model_features_for_config
    data = {
        "primaryGroup": 1,
        "buttons": [],
        "binary_inputs": [
            {"dsIndex": 0, "name": "bi", "sensorFunction": 0,
             "group": 1, "inputUsage": 0},
        ],
        "sensors": [],
        "output": None,
    }
    features = derive_model_features_for_config(data)
    assert "akmsensor" in features
    assert "akminput" not in features
    assert "akmdelay" not in features


def test_derive_model_features_for_config_no_components():
    """vdSD with no components → no akmsensor, no pushbutton."""
    from custom_components.dsvdc4ha.api import derive_model_features_for_config
    data = {
        "primaryGroup": 1,
        "buttons": [],
        "binary_inputs": [],
        "sensors": [],
        "output": None,
    }
    features = derive_model_features_for_config(data)
    assert "akmsensor" not in features
    assert "pushbutton" not in features


def test_derive_model_features_for_config_button():
    """Button present → pushbutton in feature set."""
    from custom_components.dsvdc4ha.api import derive_model_features_for_config
    from pydsvdcapi.enums import ButtonGroup
    data = {
        "primaryGroup": 1,
        "buttons": [
            {
                "dsIndex": 0, "name": "btn",
                "buttonType": 1,            # ButtonType.SINGLE_PRESS
                "buttonElementID": 1,
                "group": ButtonGroup.YELLOW.value,
                "function": 0,
                "mode": 0,
            }
        ],
        "binary_inputs": [],
        "sensors": [],
        "output": None,
    }
    features = derive_model_features_for_config(data)
    assert "pushbutton" in features
```

- [ ] **Step 2: Run the three tests — must all FAIL**

```bash
source .venv/bin/activate
pytest tests/test_api.py::test_derive_model_features_for_config_binary_input \
       tests/test_api.py::test_derive_model_features_for_config_no_components \
       tests/test_api.py::test_derive_model_features_for_config_button -v
```

Expected: `ImportError` or `AttributeError` — `derive_model_features_for_config` does not exist yet.

- [ ] **Step 3: Add `_PreviewDevice` and `derive_model_features_for_config` to `api.py`**

Insert the following immediately **before** the `DsvdcApi` class definition (i.e. after the four module-level helpers from Task 1):

```python
class _PreviewDevice:
    """Minimal Device stand-in used only by derive_model_features_for_config.

    Vdsd.__init__ reads device.dsuid once to derive the vdSD dSUID.  No other
    Device attributes are accessed during feature derivation, so a class with
    a single valid DsUid attribute is sufficient.
    """
    dsuid: DsUid = DsUid.random()


def derive_model_features_for_config(vdsd_data: dict[str, Any]) -> set[str]:
    """Return the model features pydsvdcapi would auto-derive for a vdSD config.

    Builds a temporary Vdsd from the raw config dict, populates it with
    components, delegates to pydsvdcapi's derive_model_features(), and returns
    the resulting set.  No feature rules live in this codebase.

    *vdsd_data* keys used:
      primaryGroup (int), buttons (list), binary_inputs (list),
      sensors (list), output (dict | None).
    """
    vdsd = Vdsd(
        device=_PreviewDevice(),
        primary_group=ColorGroup(vdsd_data.get("primaryGroup", 1)),
        name="preview",
        model="preview",
    )
    for btn_data in vdsd_data.get("buttons", []):
        _add_button(vdsd, btn_data)
    for bi_data in vdsd_data.get("binary_inputs", []):
        _add_binary_input(vdsd, bi_data)
    for si_data in vdsd_data.get("sensors", []):
        _add_sensor(vdsd, si_data)
    if output_data := vdsd_data.get("output"):
        _add_output(vdsd, output_data)
    vdsd.derive_model_features()
    return set(vdsd.model_features)
```

- [ ] **Step 4: Run the three new tests — must all PASS**

```bash
source .venv/bin/activate
pytest tests/test_api.py::test_derive_model_features_for_config_binary_input \
       tests/test_api.py::test_derive_model_features_for_config_no_components \
       tests/test_api.py::test_derive_model_features_for_config_button -v
```

Expected: `3 passed`

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -q
```

Expected: `262 passed, 1 warning`

- [ ] **Step 6: Commit**

```bash
git add custom_components/dsvdc4ha/api.py tests/test_api.py
git commit -m "feat: add derive_model_features_for_config() delegating to pydsvdcapi"
```

---

## Task 3: Wire config flow to use pydsvdcapi derivation, delete the mirror

Replace both `_compute_auto_features(...)` call sites in `config_flow.py` with `derive_model_features_for_config(...)`, delete `_compute_auto_features`, and remove the now-dead test that validated the deleted function.

**Files:**
- Modify: `custom_components/dsvdc4ha/config_flow.py`
- Modify: `tests/test_entity_mapping_bindings.py`

- [ ] **Step 1: Import `derive_model_features_for_config` in `config_flow.py`**

In `custom_components/dsvdc4ha/config_flow.py`, the existing import block from `.api` (around line 26) already imports enums and helpers. Add `derive_model_features_for_config` to it:

```python
from .api import (
    BinaryInputGroup,
    BinaryInputType,
    BinaryInputUsage,
    ButtonFunction,
    ButtonGroup,
    ButtonMode,
    ButtonType,
    ColorClass,
    ColorGroup,
    derive_model_features_for_config,
    FUNCTION_CHANNELS,
    OutputChannelType,
    OutputFunction,
    OutputMode,
    OutputUsage,
    SensorGroup,
    SensorType,
    SensorUsage,
)
```

- [ ] **Step 2: Replace call site 1 — `async_step_device_model_features`**

Find the block in `async_step_device_model_features` (around line 1590):

```python
        auto_features = _compute_auto_features(
            primary_group=int(vdsd.get("primaryGroup", 1)),
            buttons=vdsd.get("buttons", []),
            binary_inputs=vdsd.get("binary_inputs", []),
            sensors=vdsd.get("sensors", []),
            output=vdsd.get("output"),
            has_identify=bool(vdsd.get("identify_action")),
        )
```

Replace with:

```python
        auto_features = derive_model_features_for_config(vdsd)
```

`vdsd` is already the resolved vdSD dict with keys `primaryGroup`, `buttons`, `binary_inputs`, `sensors`, `output` — passing it directly works.

- [ ] **Step 3: Replace call site 2 — `async_step_model_features`**

Find the block in `async_step_model_features` (around line 1756):

```python
        auto_features = _compute_auto_features(
            primary_group=int(self._current_vdsd.get("primaryGroup", 1)),
            buttons=self._current_buttons,
            binary_inputs=self._current_binary_inputs,
            sensors=self._current_sensors,
            output=self._current_output,
            has_identify=bool(self._current_vdsd.get("identify_action")),
        )
```

Replace with:

```python
        auto_features = derive_model_features_for_config({
            "primaryGroup": self._current_vdsd.get("primaryGroup", 1),
            "buttons": self._current_buttons,
            "binary_inputs": self._current_binary_inputs,
            "sensors": self._current_sensors,
            "output": self._current_output,
        })
```

- [ ] **Step 4: Delete `_compute_auto_features` and its module-level constants**

Delete the entire `_compute_auto_features` function from `config_flow.py` (~80 lines, starting from `def _compute_auto_features(`).

Also delete the two module-level constants that existed solely to support `_compute_auto_features`:

```python
_TRANST_CHANNEL_TYPES: frozenset[int] = frozenset(set(range(1, 13)) | set(range(14, 19)) | set(range(22, 25)))
_VENTILATION_CHANNEL_TYPES: frozenset[int] = frozenset({12, 13, 14, 15, 20, 21})
```

These are already defined in pydsvdcapi's `Vdsd` class (`_TRANST_CHANNEL_TYPES`, `_VENTILATION_CHANNEL_TYPES`); having copies here was the duplication.

- [ ] **Step 5: Delete the dead test in `test_entity_mapping_bindings.py`**

Remove the entire `test_compute_auto_features_uses_enum_for_joker` test function (it validates the now-deleted `_compute_auto_features`):

```python
def test_compute_auto_features_uses_enum_for_joker():
    """_compute_auto_features must use ButtonGroup.JOKER, not a hardcoded 8."""
    import ast, pathlib
    src = (pathlib.Path(__file__).parent.parent / "custom_components/dsvdc4ha/config_flow.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for comp in node.comparators:
                if isinstance(comp, ast.Constant) and comp.value == 8:
                    if isinstance(node.left, ast.Name) and node.left.id == "grp":
                        raise AssertionError(
                            f"Line {node.lineno}: hardcoded 8 in grp comparison — use ButtonGroup.JOKER"
                        )
```

- [ ] **Step 6: Run full test suite**

```bash
source .venv/bin/activate && pytest tests/ -q
```

Expected: `261 passed, 1 warning`

(262 from after Task 2, minus the 1 deleted test = 261)

- [ ] **Step 7: Confirm `_compute_auto_features` is gone**

```bash
grep -n "_compute_auto_features\|_TRANST_CHANNEL_TYPES\|_VENTILATION_CHANNEL_TYPES" \
    custom_components/dsvdc4ha/config_flow.py
```

Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add custom_components/dsvdc4ha/config_flow.py tests/test_entity_mapping_bindings.py
git commit -m "feat: replace _compute_auto_features with pydsvdcapi derive_model_features_for_config"
```

---

## Expected Outcome

After all three tasks:

- `_compute_auto_features()` is deleted. Feature derivation logic lives exclusively in pydsvdcapi.
- `derive_model_features_for_config()` builds a real `Vdsd`, calls `derive_model_features()`, and returns the result. Any future change to pydsvdcapi's derivation rules is automatically reflected in the config flow UI without touching this integration.
- The four builder helpers are module-level; `_build_vdsd` and `derive_model_features_for_config` both use them.
- 261 tests pass.
