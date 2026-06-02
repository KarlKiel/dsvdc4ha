"""Tests for DsvdcApi."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from custom_components.dsvdc4ha.api import DsvdcApi, _add_output


@pytest.mark.asyncio
async def test_api_start_creates_host_and_vdc():
    with patch("custom_components.dsvdc4ha.api.VdcHost") as MockHost, \
         patch("custom_components.dsvdc4ha.api.Vdc") as MockVdc, \
         patch("custom_components.dsvdc4ha.api.VdcCapabilities") as MockCaps:
        mock_host_instance = MagicMock()
        mock_host_instance.start = AsyncMock()
        MockHost.return_value = mock_host_instance
        MockVdc.return_value = MagicMock()
        MockCaps.return_value = MagicMock()

        api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp/test_state")
        await api.start()

        MockHost.assert_called_once()
        call_kwargs = MockHost.call_args.kwargs
        assert call_kwargs["port"] == 9090
        assert call_kwargs["model_version"] == "0.1.0"
        mock_host_instance.start.assert_awaited_once()
        MockVdc.assert_called_once()
        mock_vdc_instance = MockVdc.return_value
        mock_host_instance.add_vdc.assert_called_once_with(mock_vdc_instance)
        mock_host_instance.start.assert_awaited_once_with(announce=True)


def test_vdc_dsuid_incorporates_host_mac():
    """Vdc must receive a dsuid derived from the host MAC, not a static hash."""
    from pydsvdcapi.dsuid import DsUid, DsUidNamespace
    from custom_components.dsvdc4ha.const import VDC_IMPLEMENTATION_ID

    mac_a = "AA:BB:CC:DD:EE:FF"
    mac_b = "11:22:33:44:55:66"

    dsuid_a = DsUid.from_name_in_space(f"{VDC_IMPLEMENTATION_ID}:{mac_a}", DsUidNamespace.VDC)
    dsuid_b = DsUid.from_name_in_space(f"{VDC_IMPLEMENTATION_ID}:{mac_b}", DsUidNamespace.VDC)
    dsuid_static = DsUid.from_name_in_space(VDC_IMPLEMENTATION_ID, DsUidNamespace.VDC)

    assert dsuid_a != dsuid_b, "Different MACs must produce different Vdc dSUIDs"
    assert dsuid_a != dsuid_static, "MAC-based dSUID must differ from the static fallback"


@pytest.mark.asyncio
async def test_api_vdc_receives_mac_based_dsuid():
    """Vdc constructor must be called with a dsuid= derived from the host MAC."""
    with patch("custom_components.dsvdc4ha.api.VdcHost") as MockHost, \
         patch("custom_components.dsvdc4ha.api.Vdc") as MockVdc, \
         patch("custom_components.dsvdc4ha.api.VdcCapabilities"):
        mock_host = MagicMock()
        mock_host.start = AsyncMock()
        mock_host.mac = "AA:BB:CC:DD:EE:01"
        MockHost.return_value = mock_host

        api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp/test_state")
        await api.start()

        vdc_kwargs = MockVdc.call_args.kwargs
        assert "dsuid" in vdc_kwargs, "Vdc must be called with explicit dsuid="
        from pydsvdcapi.dsuid import DsUid, DsUidNamespace
        from custom_components.dsvdc4ha.const import VDC_IMPLEMENTATION_ID
        expected = DsUid.from_name_in_space(
            f"{VDC_IMPLEMENTATION_ID}:AA:BB:CC:DD:EE:01", DsUidNamespace.VDC
        )
        assert vdc_kwargs["dsuid"] == expected


@pytest.mark.asyncio
async def test_api_stop_calls_host_stop():
    with patch("custom_components.dsvdc4ha.api.VdcHost") as MockHost, \
         patch("custom_components.dsvdc4ha.api.Vdc"), \
         patch("custom_components.dsvdc4ha.api.VdcCapabilities"):
        mock_host_instance = MagicMock()
        mock_host_instance.start = AsyncMock()
        mock_host_instance.stop = AsyncMock()
        mock_host_instance._zeroconf = None  # no shared zeroconf injected
        MockHost.return_value = mock_host_instance

        api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp/test_state")
        await api.start()
        await api.stop()

        mock_host_instance.stop.assert_awaited_once()



@pytest.mark.asyncio
async def test_api_stop_deregisters_shared_zeroconf():
    """stop() unregisters the DNS-SD service but does NOT close HA's shared zeroconf."""
    mock_sock = MagicMock()
    mock_sock.__enter__ = MagicMock(return_value=mock_sock)
    mock_sock.__exit__ = MagicMock(return_value=False)
    mock_sock.getsockname.return_value = ("192.168.1.100", 0)

    with patch("custom_components.dsvdc4ha.api.VdcHost") as MockHost, \
         patch("custom_components.dsvdc4ha.api.Vdc"), \
         patch("custom_components.dsvdc4ha.api.VdcCapabilities"), \
         patch("custom_components.dsvdc4ha.api.socket.gethostname", return_value="testhostname"), \
         patch("custom_components.dsvdc4ha.api.socket.socket", return_value=mock_sock), \
         patch("custom_components.dsvdc4ha.api.socket.inet_aton", return_value=b"\xc0\xa8\x01\x64"):
        mock_zeroconf = MagicMock()
        mock_zeroconf.async_register_service = AsyncMock()
        mock_zeroconf.async_unregister_service = AsyncMock()

        mock_host_instance = MagicMock()
        mock_host_instance.name = "TestVdcHost"
        mock_host_instance.start = AsyncMock()
        mock_host_instance.stop = AsyncMock()
        mock_host_instance._port = 9090
        mock_host_instance._dsuid = "AABBCCDDEEFF0011223344556677889900"
        mock_host_instance._zeroconf = None
        mock_host_instance._service_info = None
        mock_host_instance._on_session_ready = AsyncMock()
        MockHost.return_value = mock_host_instance

        api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp/test_state")
        await api.start(zeroconf=mock_zeroconf)
        await api.stop()

        mock_host_instance.start.assert_awaited_once_with(announce=False)
        mock_zeroconf.async_register_service.assert_awaited_once()
        # async_unregister_service is called twice: once as pre-unregister during
        # _register_zeroconf and once in _deregister_zeroconf during stop()
        assert mock_zeroconf.async_unregister_service.await_count == 2
        mock_zeroconf.async_close.assert_not_called()
        mock_host_instance.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_api_announce_device_adds_to_vdc():
    with patch("custom_components.dsvdc4ha.api.VdcHost") as MockHost, \
         patch("custom_components.dsvdc4ha.api.Vdc") as MockVdc, \
         patch("custom_components.dsvdc4ha.api.VdcCapabilities"), \
         patch("custom_components.dsvdc4ha.api.Device") as MockDevice, \
         patch("custom_components.dsvdc4ha.api.DsUid"):
        mock_host = MagicMock()
        mock_host.start = AsyncMock()
        mock_host.session = MagicMock()
        MockHost.return_value = mock_host
        mock_vdc = MagicMock()
        MockVdc.return_value = mock_vdc
        mock_device = MagicMock()
        mock_device.announce = AsyncMock(return_value=1)
        MockDevice.return_value = mock_device

        api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")
        await api.start()
        api.add_device("entry-abc", [])
        await api.announce_device("entry-abc")

        mock_vdc.add_device.assert_called_once_with(mock_device)
        mock_device.announce.assert_awaited_once()


@pytest.mark.asyncio
async def test_api_announce_device_builds_vdsd():
    with patch("custom_components.dsvdc4ha.api.VdcHost") as MockHost, \
         patch("custom_components.dsvdc4ha.api.Vdc") as MockVdc, \
         patch("custom_components.dsvdc4ha.api.VdcCapabilities"), \
         patch("custom_components.dsvdc4ha.api.Device") as MockDevice, \
         patch("custom_components.dsvdc4ha.api.Vdsd") as MockVdsd, \
         patch("custom_components.dsvdc4ha.api.DsUid"):
        mock_host = MagicMock()
        mock_host.start = AsyncMock()
        mock_host.session = MagicMock()
        MockHost.return_value = mock_host
        MockVdc.return_value = MagicMock()
        mock_device = MagicMock()
        mock_device.announce = AsyncMock(return_value=1)
        MockDevice.return_value = mock_device
        mock_vdsd = MagicMock()
        MockVdsd.return_value = mock_vdsd

        vdsd_data = {
            "displayId": "TestUnit",
            "primaryGroup": 1,
            "model": "TestUnit",
            "vendorName": "Acme",
            "modelVersion": "v1",
            "modelUID": "AcmeTestV1",
            "active": True,
            "buttons": [],
            "binary_inputs": [],
            "sensors": [],
            "output": None,
        }

        api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")
        await api.start()
        api.add_device("entry-xyz", [vdsd_data])
        await api.announce_device("entry-xyz")

        MockVdsd.assert_called_once()
        call_kwargs = MockVdsd.call_args.kwargs
        assert call_kwargs["primary_group"].value == 1  # ColorGroup(1)
        mock_vdsd.derive_model_features.assert_called_once()
        mock_device.add_vdsd.assert_called_once_with(mock_vdsd)


@pytest.mark.asyncio
async def test_report_button_click_calls_update_click():
    with patch("custom_components.dsvdc4ha.api.VdcHost") as MockHost, \
         patch("custom_components.dsvdc4ha.api.Vdc"), \
         patch("custom_components.dsvdc4ha.api.VdcCapabilities"):
        mock_host = MagicMock()
        mock_host.start = AsyncMock()
        mock_host.session = MagicMock()
        MockHost.return_value = mock_host

        api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")
        await api.start()

        mock_btn = MagicMock()
        mock_btn.update_click = AsyncMock()
        await api.report_button_click(mock_btn, 7)
        mock_btn.update_click.assert_awaited_once_with(click_type=7, session=mock_host.session)


@pytest.mark.asyncio
async def test_report_sensor_value_calls_update_value():
    with patch("custom_components.dsvdc4ha.api.VdcHost") as MockHost, \
         patch("custom_components.dsvdc4ha.api.Vdc"), \
         patch("custom_components.dsvdc4ha.api.VdcCapabilities"):
        mock_host = MagicMock()
        mock_host.start = AsyncMock()
        mock_host.session = MagicMock()
        MockHost.return_value = mock_host

        api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")
        await api.start()

        mock_sensor = MagicMock()
        mock_sensor.update_value = AsyncMock()
        await api.report_sensor_value(mock_sensor, 42.5)
        mock_sensor.update_value.assert_awaited_once_with(value=42.5, session=mock_host.session)


def test_set_channel_applied_callback_sets_property():
    api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")

    mock_output = MagicMock()
    my_callback = MagicMock()
    api.set_channel_applied_callback(mock_output, my_callback)
    assert mock_output.on_channel_applied == my_callback


@pytest.mark.asyncio
async def test_report_channel_value_calls_update_value():
    with patch("custom_components.dsvdc4ha.api.VdcHost") as MockHost, \
         patch("custom_components.dsvdc4ha.api.Vdc"), \
         patch("custom_components.dsvdc4ha.api.VdcCapabilities"):
        mock_host = MagicMock()
        mock_host.start = AsyncMock()
        mock_host.session = MagicMock()
        MockHost.return_value = mock_host

        api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")
        await api.start()

        mock_channel = MagicMock()
        mock_channel.update_value = AsyncMock()
        await api.report_channel_value(mock_channel, 75.0)
        mock_channel.update_value.assert_awaited_once_with(75.0)


def test_build_vdsd_uses_per_vdsd_icon_when_present():
    """_build_vdsd uses icon_data_b64 and icon_name from vdSD data instead of global fallback."""
    import base64, io
    from PIL import Image
    from unittest.mock import MagicMock, patch
    buf = io.BytesIO()
    Image.new("RGBA", (16, 16), (0, 128, 0, 255)).save(buf, format="PNG")
    entity_icon = buf.getvalue()
    icon_b64 = base64.b64encode(entity_icon).decode()

    from custom_components.dsvdc4ha.api import DsvdcApi
    from pydsvdcapi.vdsd import Device

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


def test_positional_output_registers_both_channels():
    """Bug: POSITIONAL (function=2) outputs had 0 channels because OutputChannel
    objects were created but discarded — they don't self-register."""
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
    _add_output(mock_vdsd, output_data)
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
    _add_output(mock_vdsd, output_data)
    actual_output = mock_vdsd.set_output.call_args[0][0]

    ch = actual_output.get_channel(0)
    assert ch is not None
    assert int(ch.channel_type) == 19, (
        f"expected POWER_STATE (19), got {int(ch.channel_type)} — "
        "auto-created BRIGHTNESS channel was not replaced"
    )


@pytest.mark.asyncio
async def test_vanish_without_session_queues_pending():
    """vanish_device with no session stores the device in _pending_vanish."""
    api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")

    mock_device = MagicMock()
    api._devices["sub1"] = mock_device
    api._vdc = MagicMock()
    # _host is None → no session

    await api.vanish_device("sub1")

    assert "sub1" not in api._devices
    assert api._pending_vanish.get("sub1") is mock_device
    api._vdc.remove_device.assert_called_once()


@pytest.mark.asyncio
async def test_flush_pending_vanish_sends_and_clears():
    """_flush_pending_vanish calls device.vanish for each pending entry then clears."""
    api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")

    mock_device = MagicMock()
    mock_device.vanish = AsyncMock()
    api._pending_vanish["sub1"] = mock_device

    mock_session = MagicMock()
    await api._flush_pending_vanish(mock_session)

    mock_device.vanish.assert_awaited_once_with(mock_session)
    assert "sub1" not in api._pending_vanish


@pytest.mark.asyncio
async def test_flush_pending_vanish_skips_failed_and_continues():
    """_flush_pending_vanish continues if one device.vanish raises."""
    api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")

    bad_device = MagicMock()
    bad_device.vanish = AsyncMock(side_effect=Exception("boom"))
    good_device = MagicMock()
    good_device.vanish = AsyncMock()
    api._pending_vanish["bad"] = bad_device
    api._pending_vanish["good"] = good_device

    mock_session = MagicMock()
    await api._flush_pending_vanish(mock_session)  # must not raise

    good_device.vanish.assert_awaited_once_with(mock_session)
    assert not api._pending_vanish  # both cleared


@pytest.mark.asyncio
async def test_session_ready_hook_skips_known_devices():
    """_on_session_ready only announces devices NOT in _ever_announced."""
    with patch("custom_components.dsvdc4ha.api.VdcHost") as MockHost, \
         patch("custom_components.dsvdc4ha.api.Vdc"), \
         patch("custom_components.dsvdc4ha.api.VdcCapabilities"):
        mock_host_instance = MagicMock()
        mock_host_instance.start = AsyncMock()
        mock_host_instance._on_session_ready = AsyncMock()
        mock_host_instance.session = None
        MockHost.return_value = mock_host_instance

        api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")
        await api.start()

        # Simulate two registered devices; "known" was announced before
        mock_device_known = MagicMock()
        mock_device_known.announce = AsyncMock(return_value=1)
        mock_device_new = MagicMock()
        mock_device_new.announce = AsyncMock(return_value=1)
        api._devices["known"] = mock_device_known
        api._devices["new"] = mock_device_new
        api._ever_announced.add("known")

        mock_vdc = MagicMock()
        mock_vdc.announce = AsyncMock(return_value=True)
        api._vdc = mock_vdc

        mock_session = MagicMock()
        # Trigger the installed hook
        await mock_host_instance._on_session_ready(mock_session)

        mock_vdc.announce.assert_awaited_once_with(mock_session)
        mock_device_known.announce.assert_not_awaited()
        mock_device_new.announce.assert_awaited_once_with(mock_session)
        assert "new" in api._ever_announced


@pytest.mark.asyncio
async def test_session_ready_hook_adds_to_ever_announced():
    """Newly announced devices are added to _ever_announced."""
    with patch("custom_components.dsvdc4ha.api.VdcHost") as MockHost, \
         patch("custom_components.dsvdc4ha.api.Vdc"), \
         patch("custom_components.dsvdc4ha.api.VdcCapabilities"):
        mock_host_instance = MagicMock()
        mock_host_instance.start = AsyncMock()
        mock_host_instance._on_session_ready = AsyncMock()
        mock_host_instance.session = None
        MockHost.return_value = mock_host_instance

        api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")
        await api.start()

        mock_device = MagicMock()
        mock_device.announce = AsyncMock(return_value=2)  # 2 vdSDs announced
        api._devices["sub1"] = mock_device

        mock_vdc = MagicMock()
        mock_vdc.announce = AsyncMock(return_value=True)
        api._vdc = mock_vdc

        await mock_host_instance._on_session_ready(MagicMock())

        assert "sub1" in api._ever_announced


@pytest.mark.asyncio
async def test_announce_device_skips_if_already_known():
    """announce_device() is a no-op for entry_ids in _ever_announced."""
    api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")

    mock_host = MagicMock()
    mock_host.session = MagicMock()  # session active
    api._host = mock_host

    mock_device = MagicMock()
    mock_device.announce = AsyncMock(return_value=1)
    api._devices["sub1"] = mock_device
    api._ever_announced.add("sub1")  # already known

    await api.announce_device("sub1")

    mock_device.announce.assert_not_awaited()


@pytest.mark.asyncio
async def test_vanish_device_removes_from_ever_announced():
    """vanish_device() removes the entry_id from _ever_announced."""
    api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp")
    api._vdc = MagicMock()
    # No session — device queued for pending vanish, but _ever_announced cleared immediately
    mock_device = MagicMock()
    api._devices["sub1"] = mock_device
    api._ever_announced.add("sub1")

    await api.vanish_device("sub1")

    assert "sub1" not in api._ever_announced


