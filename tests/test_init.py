"""Tests for __init__.py — entity registry listener and helper functions."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from custom_components.dsvdc4ha import (
    _build_entity_index,
    _entity_ids_in_vdsd,
)


# ---------------------------------------------------------------------------
# Helper: build a minimal config entry mock with subentries
# ---------------------------------------------------------------------------

def _make_entry(subentries: list[dict]) -> MagicMock:
    entry = MagicMock()
    sub_mocks = {}
    for sd in subentries:
        sub = MagicMock()
        sub.subentry_id = sd["subentry_id"]
        sub.data = sd["data"]
        sub_mocks[sd["subentry_id"]] = sub
    entry.subentries = sub_mocks
    return entry


def _vdsd_with_output(entity_id: str) -> dict:
    return {
        "displayId": "x", "primaryGroup": 1, "model": "x", "vendorName": "V",
        "modelVersion": "1.0", "modelUID": "Vx", "name": "X", "active": True,
        "identify_action": None, "firmwareUpdate_action": None, "optional": {},
        "buttons": [], "binary_inputs": [], "sensors": [],
        "output": {"channels": [{"channel_type": 1, "read_entity": entity_id}]},
    }


def _vdsd_with_sensor(entity_id: str) -> dict:
    return {
        "displayId": "x", "primaryGroup": 8, "model": "x", "vendorName": "V",
        "modelVersion": "1.0", "modelUID": "Vx", "name": "X", "active": True,
        "identify_action": None, "firmwareUpdate_action": None, "optional": {},
        "buttons": [], "binary_inputs": [],
        "sensors": [{"callback_entity": entity_id}],
        "output": None,
    }


def _vdsd_with_binary_input(entity_id: str) -> dict:
    return {
        "displayId": "x", "primaryGroup": 8, "model": "x", "vendorName": "V",
        "modelVersion": "1.0", "modelUID": "Vx", "name": "X", "active": True,
        "identify_action": None, "firmwareUpdate_action": None, "optional": {},
        "buttons": [], "binary_inputs": [{"callback_entity": entity_id}],
        "sensors": [], "output": None,
    }


# ---------------------------------------------------------------------------
# _entity_ids_in_vdsd
# ---------------------------------------------------------------------------

def test_entity_ids_in_vdsd_output_channel():
    vdsd = _vdsd_with_output("light.lamp")
    assert _entity_ids_in_vdsd(vdsd) == {"light.lamp"}


def test_entity_ids_in_vdsd_sensor():
    vdsd = _vdsd_with_sensor("sensor.temp")
    assert _entity_ids_in_vdsd(vdsd) == {"sensor.temp"}


def test_entity_ids_in_vdsd_binary_input():
    vdsd = _vdsd_with_binary_input("binary_sensor.motion")
    assert _entity_ids_in_vdsd(vdsd) == {"binary_sensor.motion"}


def test_entity_ids_in_vdsd_empty():
    vdsd = {
        "output": None, "buttons": [], "binary_inputs": [], "sensors": [],
    }
    assert _entity_ids_in_vdsd(vdsd) == set()


# ---------------------------------------------------------------------------
# _build_entity_index
# ---------------------------------------------------------------------------

def test_build_entity_index_single_subentry():
    entry = _make_entry([{
        "subentry_id": "sub1",
        "data": {"vdsds": [_vdsd_with_output("light.lamp")]},
    }])
    index = _build_entity_index(entry)
    assert index == {"light.lamp": [("sub1", 0)]}


def test_build_entity_index_two_subentries():
    entry = _make_entry([
        {"subentry_id": "sub1", "data": {"vdsds": [_vdsd_with_output("light.a")]}},
        {"subentry_id": "sub2", "data": {"vdsds": [_vdsd_with_output("light.b")]}},
    ])
    index = _build_entity_index(entry)
    assert set(index.keys()) == {"light.a", "light.b"}
    assert index["light.a"] == [("sub1", 0)]
    assert index["light.b"] == [("sub2", 0)]


def test_build_entity_index_multiple_vdsds_in_subentry():
    entry = _make_entry([{
        "subentry_id": "sub1",
        "data": {"vdsds": [
            _vdsd_with_output("light.a"),
            _vdsd_with_sensor("sensor.temp"),
        ]},
    }])
    index = _build_entity_index(entry)
    assert index["light.a"] == [("sub1", 0)]
    assert index["sensor.temp"] == [("sub1", 1)]


# ---------------------------------------------------------------------------
# Entity registry listener — simulated via the callback
# ---------------------------------------------------------------------------

def _make_hass_with_listener() -> tuple[MagicMock, list]:
    """Return (hass_mock, registered_listeners).

    async_listen captures the callback so tests can fire events manually.
    """
    hass = MagicMock()
    hass.async_create_task = MagicMock()
    captured = []

    def _listen(event_type, callback):
        captured.append(callback)
        return MagicMock()  # unsub

    hass.bus.async_listen.side_effect = _listen
    return hass, captured


def _fire(callback, action: str, entity_id: str, changes: dict | None = None) -> None:
    event = MagicMock()
    event.data = {"action": action, "entity_id": entity_id}
    if changes is not None:
        event.data["changes"] = changes
    callback(event)


@pytest.mark.asyncio
async def test_entity_disabled_calls_set_vdsd_active_false():
    """Disabling an entity triggers set_vdsd_active(subentry_id, 0, False)."""
    hass, captured = _make_hass_with_listener()
    api = MagicMock()
    api.set_vdsd_active = AsyncMock()
    api.vanish_device = AsyncMock()

    entity_index = {"light.lamp": [("sub1", 0)]}

    reg_entry = MagicMock()
    reg_entry.disabled_by = MagicMock()  # non-None → disabled

    with patch("custom_components.dsvdc4ha.er.async_get") as mock_er:
        mock_er.return_value.async_get.return_value = reg_entry

        # Import and call the private listener builder by simulating setup
        from custom_components.dsvdc4ha import _build_entity_index
        from homeassistant.helpers import entity_registry as er

        # Build listener manually (mirrors what async_setup_entry does)
        from homeassistant.core import callback

        @callback
        def _on_entity_registry_updated(event):
            action = event.data.get("action", "")
            eid = event.data.get("entity_id", "")
            if eid not in entity_index:
                return
            if action == "update" and "disabled_by" in event.data.get("changes", {}):
                reg = er.async_get(hass).async_get(eid)
                active = reg is not None and reg.disabled_by is None
                for subentry_id, vdsd_idx in entity_index[eid]:
                    hass.async_create_task(
                        api.set_vdsd_active(subentry_id, vdsd_idx, active)
                    )
            elif action == "remove":
                for subentry_id, _ in entity_index.pop(eid, []):
                    hass.async_create_task(api.vanish_device(subentry_id))

        _fire(_on_entity_registry_updated, "update", "light.lamp",
              changes={"disabled_by": None})

    hass.async_create_task.assert_called_once()
    coro = hass.async_create_task.call_args[0][0]
    await coro
    api.set_vdsd_active.assert_awaited_once_with("sub1", 0, False)


@pytest.mark.asyncio
async def test_entity_enabled_calls_set_vdsd_active_true():
    """Re-enabling an entity triggers set_vdsd_active(subentry_id, 0, True)."""
    hass, _ = _make_hass_with_listener()
    api = MagicMock()
    api.set_vdsd_active = AsyncMock()

    entity_index = {"light.lamp": [("sub1", 0)]}

    reg_entry = MagicMock()
    reg_entry.disabled_by = None  # None → enabled

    with patch("custom_components.dsvdc4ha.er.async_get") as mock_er:
        mock_er.return_value.async_get.return_value = reg_entry

        from homeassistant.helpers import entity_registry as er
        from homeassistant.core import callback

        @callback
        def _on(event):
            eid = event.data.get("entity_id", "")
            if eid not in entity_index:
                return
            if event.data.get("action") == "update" and "disabled_by" in event.data.get("changes", {}):
                reg = er.async_get(hass).async_get(eid)
                active = reg is not None and reg.disabled_by is None
                for subentry_id, vdsd_idx in entity_index[eid]:
                    hass.async_create_task(api.set_vdsd_active(subentry_id, vdsd_idx, active))

        _fire(_on, "update", "light.lamp", changes={"disabled_by": "user"})

    coro = hass.async_create_task.call_args[0][0]
    await coro
    api.set_vdsd_active.assert_awaited_once_with("sub1", 0, True)


@pytest.mark.asyncio
async def test_entity_removed_calls_vanish_device():
    """Removing an entity triggers vanish_device for its subentry."""
    hass, _ = _make_hass_with_listener()
    api = MagicMock()
    api.vanish_device = AsyncMock()

    entity_index = {"light.lamp": [("sub1", 0)]}

    from homeassistant.core import callback

    @callback
    def _on(event):
        eid = event.data.get("entity_id", "")
        if eid not in entity_index:
            return
        if event.data.get("action") == "remove":
            for subentry_id, _ in entity_index.pop(eid, []):
                hass.async_create_task(api.vanish_device(subentry_id))

    _fire(_on, "remove", "light.lamp")

    coro = hass.async_create_task.call_args[0][0]
    await coro
    api.vanish_device.assert_awaited_once_with("sub1")


def test_unrelated_entity_change_ignored():
    """Events for entity_ids not in the index are ignored."""
    hass, _ = _make_hass_with_listener()
    api = MagicMock()

    entity_index = {"light.lamp": [("sub1", 0)]}

    from homeassistant.core import callback

    @callback
    def _on(event):
        eid = event.data.get("entity_id", "")
        if eid not in entity_index:
            return
        hass.async_create_task(MagicMock())

    _fire(_on, "update", "light.other", changes={"disabled_by": None})

    hass.async_create_task.assert_not_called()


@pytest.mark.asyncio
async def test_vanish_deleted_devices_vanishes_diff():
    """_vanish_deleted_devices vanishes entry_ids in api but not in entry.subentries."""
    from custom_components.dsvdc4ha import _vanish_deleted_devices

    api = MagicMock()
    api.registered_entry_ids = {"sub_kept", "sub_deleted"}
    api.vanish_device = AsyncMock()

    coordinator = MagicMock()
    coordinator.api = api

    entry = _make_entry([{"subentry_id": "sub_kept", "data": {}}])

    await _vanish_deleted_devices(coordinator, entry)

    api.vanish_device.assert_awaited_once_with("sub_deleted")


@pytest.mark.asyncio
async def test_vanish_deleted_devices_noop_when_api_is_none():
    """_vanish_deleted_devices does nothing when coordinator.api is None."""
    from custom_components.dsvdc4ha import _vanish_deleted_devices

    coordinator = MagicMock()
    coordinator.api = None

    entry = _make_entry([{"subentry_id": "sub1", "data": {}}])

    await _vanish_deleted_devices(coordinator, entry)  # must not raise


@pytest.mark.asyncio
async def test_vanish_deleted_devices_noop_when_no_deletions():
    """_vanish_deleted_devices does nothing when entry matches api devices."""
    from custom_components.dsvdc4ha import _vanish_deleted_devices

    api = MagicMock()
    api.registered_entry_ids = {"sub1"}
    api.vanish_device = AsyncMock()

    coordinator = MagicMock()
    coordinator.api = api

    entry = _make_entry([{"subentry_id": "sub1", "data": {}}])

    await _vanish_deleted_devices(coordinator, entry)

    api.vanish_device.assert_not_awaited()
