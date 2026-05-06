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


@pytest.mark.asyncio
async def test_api_stop_calls_host_stop():
    with patch("custom_components.dsvdc4ha.api.VdcHost") as MockHost, \
         patch("custom_components.dsvdc4ha.api.Vdc"), \
         patch("custom_components.dsvdc4ha.api.VdcCapabilities"):
        mock_host_instance = MagicMock()
        mock_host_instance.start = AsyncMock()
        mock_host_instance.stop = AsyncMock()
        MockHost.return_value = mock_host_instance

        api = DsvdcApi(port=9090, version="0.1.0", config_url="http://ha.local", state_path="/tmp/test_state")
        await api.start()
        await api.stop()

        mock_host_instance.stop.assert_awaited_once()
