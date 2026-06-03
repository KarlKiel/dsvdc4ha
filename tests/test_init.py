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
async def test_subentry_listener_removes_device_on_deletion():
    """Delta listener vanishes a removed subentry's device and clears HA registry entries."""
    from custom_components.dsvdc4ha import _async_subentry_update_listener

    api = MagicMock()
    api.vanish_device = AsyncMock()
    coordinator = MagicMock()
    coordinator.api = api

    hass = MagicMock()
    hass.data = {
        "dsvdc4ha": {
            "hub": coordinator,
            "_known_subentry_ids": {"sub_a", "sub_b"},
            "sub_b": {"unsubs": []},
        }
    }
    entry = _make_entry([{"subentry_id": "sub_a", "data": {}}])
    entry.entry_id = "entry1"

    with (
        patch("custom_components.dsvdc4ha.er.async_get") as mock_er,
        patch("custom_components.dsvdc4ha.dr.async_get") as mock_dr,
    ):
        await _async_subentry_update_listener(hass, entry)

    api.vanish_device.assert_awaited_once_with("sub_b")
    mock_er.return_value.async_clear_config_subentry.assert_called_once_with("entry1", "sub_b")
    mock_dr.return_value.async_clear_config_subentry.assert_called_once_with("entry1", "sub_b")
    assert hass.data["dsvdc4ha"]["_known_subentry_ids"] == {"sub_a"}


@pytest.mark.asyncio
async def test_subentry_listener_adds_new_device():
    """Delta listener adds + announces a newly added subentry's device."""
    from custom_components.dsvdc4ha import _async_subentry_update_listener

    api = MagicMock()
    api.add_device = MagicMock()
    api.announce_device = AsyncMock()
    coordinator = MagicMock()
    coordinator.api = api

    add_sensor = MagicMock()
    add_binary = MagicMock()
    hass = MagicMock()
    hass.data = {
        "dsvdc4ha": {
            "hub": coordinator,
            "_known_subentry_ids": {"sub_a"},
            "_add_sensor_entities": add_sensor,
            "_add_binary_entities": add_binary,
        }
    }
    entry = _make_entry([
        {"subentry_id": "sub_a", "data": {}},
        {"subentry_id": "sub_b", "data": {"vdsds": []}},
    ])
    entry.entry_id = "entry1"

    with (
        patch("custom_components.dsvdc4ha.er.async_get"),
        patch("custom_components.dsvdc4ha.dr.async_get"),
        patch("custom_components.dsvdc4ha.listeners.setup_input_listeners", return_value=[]),
        patch("custom_components.dsvdc4ha.listeners.setup_output_listeners", return_value=[]),
        patch(
            "custom_components.dsvdc4ha.listeners.seed_initial_values",
            new_callable=AsyncMock,
        ),
        patch("custom_components.dsvdc4ha.sensor._add_entities_for_subentry"),
        patch("custom_components.dsvdc4ha.binary_sensor._add_entities_for_subentry"),
    ):
        await _async_subentry_update_listener(hass, entry)

    api.add_device.assert_called_once_with("sub_b", [])
    api.announce_device.assert_awaited_once_with("sub_b")
    assert hass.data["dsvdc4ha"]["_known_subentry_ids"] == {"sub_a", "sub_b"}


@pytest.mark.asyncio
async def test_subentry_listener_noop_when_no_changes():
    """Delta listener does nothing when subentries match the known ID set."""
    from custom_components.dsvdc4ha import _async_subentry_update_listener

    api = MagicMock()
    api.vanish_device = AsyncMock()
    api.announce_device = AsyncMock()
    coordinator = MagicMock()
    coordinator.api = api

    hass = MagicMock()
    hass.data = {
        "dsvdc4ha": {
            "hub": coordinator,
            "_known_subentry_ids": {"sub_a"},
        }
    }
    entry = _make_entry([{"subentry_id": "sub_a", "data": {}}])
    entry.entry_id = "entry1"

    with (
        patch("custom_components.dsvdc4ha.er.async_get"),
        patch("custom_components.dsvdc4ha.dr.async_get"),
    ):
        await _async_subentry_update_listener(hass, entry)

    api.vanish_device.assert_not_awaited()
    api.announce_device.assert_not_awaited()


@pytest.mark.asyncio
async def test_subentry_listener_noop_when_coordinator_is_none():
    """Delta listener does nothing if coordinator has not been started yet."""
    from custom_components.dsvdc4ha import _async_subentry_update_listener

    hass = MagicMock()
    hass.data = {"dsvdc4ha": {}}
    entry = _make_entry([])
    entry.entry_id = "entry1"

    # Must not raise — no patches needed, coordinator is absent
    await _async_subentry_update_listener(hass, entry)


@pytest.mark.asyncio
async def test_backfill_missing_icons_fills_from_entity_state():
    """backfill fills icon_data_b64 and icon_slug for old-format entries (no icon_slug key)."""
    from custom_components.dsvdc4ha import _backfill_missing_icons

    vdsd = _vdsd_with_binary_input("binary_sensor.mylight")
    vdsd.pop("icon_data_b64", None)
    vdsd.pop("icon_slug", None)  # old-format entry

    subentry = MagicMock()
    subentry.subentry_id = "sub1"
    subentry.data = {"vdsds": [vdsd]}

    entry = MagicMock()
    entry.subentries = {"sub1": subentry}

    state = MagicMock()
    state.attributes = {"device_class": "motion"}

    hass = MagicMock()
    hass.states.get.return_value = state
    hass.config_entries.async_update_subentry = MagicMock()

    with patch("custom_components.dsvdc4ha.MDI_DOMAIN_ICONS", {"binary_sensor.motion": "motion-sensor", "binary_sensor": "radiobox-blank"}):
        with patch("custom_components.dsvdc4ha.bundled_icon_b64", return_value="FAKEBASE64"):
            await _backfill_missing_icons(hass, entry)

    hass.config_entries.async_update_subentry.assert_called_once()
    call_kwargs = hass.config_entries.async_update_subentry.call_args
    updated_vdsd = call_kwargs.kwargs["data"]["vdsds"][0]
    assert updated_vdsd["icon_data_b64"] == "FAKEBASE64"
    assert updated_vdsd["icon_slug"] == "motion-sensor"


@pytest.mark.asyncio
async def test_backfill_missing_icons_skips_if_icon_slug_present():
    """backfill does NOT call async_update_subentry when icon_slug key is present (new format)."""
    from custom_components.dsvdc4ha import _backfill_missing_icons

    vdsd = _vdsd_with_binary_input("binary_sensor.mylight")
    vdsd["icon_data_b64"] = "EXISTING"
    vdsd["icon_slug"] = "radiobox-blank"  # new-format entry

    subentry = MagicMock()
    subentry.subentry_id = "sub1"
    subentry.data = {"vdsds": [vdsd]}

    entry = MagicMock()
    entry.subentries = {"sub1": subentry}

    hass = MagicMock()
    hass.config_entries.async_update_subentry = MagicMock()

    await _backfill_missing_icons(hass, entry)

    hass.config_entries.async_update_subentry.assert_not_called()


@pytest.mark.asyncio
async def test_backfill_stores_icon_slug_even_when_no_bundled_icon():
    """backfill stores icon_slug without icon_data_b64 when no bundled PNG is available."""
    from custom_components.dsvdc4ha import _backfill_missing_icons

    vdsd = _vdsd_with_binary_input("binary_sensor.mylight")
    vdsd.pop("icon_data_b64", None)
    vdsd.pop("icon_slug", None)

    subentry = MagicMock()
    subentry.subentry_id = "sub1"
    subentry.data = {"vdsds": [vdsd]}

    entry = MagicMock()
    entry.subentries = {"sub1": subentry}

    state = MagicMock()
    state.attributes = {"device_class": None}

    hass = MagicMock()
    hass.states.get.return_value = state
    hass.config_entries.async_update_subentry = MagicMock()

    with patch("custom_components.dsvdc4ha.MDI_DOMAIN_ICONS", {"binary_sensor": "radiobox-blank"}):
        with patch("custom_components.dsvdc4ha.bundled_icon_b64", return_value=None):
            await _backfill_missing_icons(hass, entry)

    hass.config_entries.async_update_subentry.assert_called_once()
    call_kwargs = hass.config_entries.async_update_subentry.call_args
    updated_vdsd = call_kwargs.kwargs["data"]["vdsds"][0]
    assert updated_vdsd["icon_slug"] == "radiobox-blank"
    assert "icon_data_b64" not in updated_vdsd or updated_vdsd.get("icon_data_b64") is None


@pytest.mark.asyncio
async def test_backfill_missing_icons_skips_if_no_entity_state():
    """backfill does NOT call async_update_subentry when hass.states.get returns None."""
    from custom_components.dsvdc4ha import _backfill_missing_icons

    vdsd = _vdsd_with_binary_input("binary_sensor.mylight")
    vdsd.pop("icon_data_b64", None)
    vdsd.pop("icon_slug", None)

    subentry = MagicMock()
    subentry.subentry_id = "sub1"
    subentry.data = {"vdsds": [vdsd]}

    entry = MagicMock()
    entry.subentries = {"sub1": subentry}

    hass = MagicMock()
    hass.states.get.return_value = None
    hass.config_entries.async_update_subentry = MagicMock()

    await _backfill_missing_icons(hass, entry)

    hass.config_entries.async_update_subentry.assert_not_called()


@pytest.mark.asyncio
async def test_async_remove_entry_stops_api():
    """async_remove_entry vanishes all subentries and stops the API."""
    from custom_components.dsvdc4ha import async_remove_entry

    mock_api = MagicMock()
    mock_api.vanish_device = AsyncMock()
    mock_api.stop = AsyncMock()

    mock_coordinator = MagicMock()
    mock_coordinator.api = mock_api

    mock_entry = MagicMock()
    mock_entry.subentries = {"sub1": MagicMock(), "sub2": MagicMock()}

    hass = MagicMock()
    hass.data = {"dsvdc4ha": {"hub": mock_coordinator}}

    await async_remove_entry(hass, mock_entry)

    # vanish called for every subentry
    assert mock_api.vanish_device.await_count == 2
    mock_api.stop.assert_awaited_once_with()
