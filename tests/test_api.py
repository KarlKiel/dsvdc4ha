"""Tests for DsvdcApi."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from custom_components.dsvdc4ha.api import DsvdcApi


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
        MockHost.return_value = mock_host_instance

        api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp/test_state")
        await api.start(zeroconf=mock_zeroconf)
        await api.stop()

        mock_host_instance.start.assert_awaited_once_with(announce=False)
        mock_zeroconf.async_register_service.assert_awaited_once()
        mock_zeroconf.async_unregister_service.assert_awaited_once()
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
        await api.announce_device("entry-abc", [])

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
        mock_device.announce = AsyncMock()
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
        await api.announce_device("entry-xyz", [vdsd_data])

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
