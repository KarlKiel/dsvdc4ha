"""Tests for HubCoordinator."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.config_entries import ConfigEntry


@pytest.fixture
def mock_hass():
    """Return a minimal mock HomeAssistant object."""
    hass = MagicMock()
    hass.config.internal_url = "http://homeassistant.local:8123"
    hass.config.path.return_value = "/tmp/.storage/dsvdc4ha_host_state"
    return hass


@pytest.mark.asyncio
async def test_coordinator_start_delegates_to_api(mock_hass, mock_api):
    mock_zeroconf = MagicMock()
    mock_integration = MagicMock()
    mock_integration.version = "1.2.3"
    with (
        patch("custom_components.dsvdc4ha.coordinator.DsvdcApi", return_value=mock_api),
        patch(
            "custom_components.dsvdc4ha.coordinator.async_get_instance",
            new=AsyncMock(return_value=mock_zeroconf),
        ),
        patch(
            "custom_components.dsvdc4ha.coordinator.async_get_integration",
            new=AsyncMock(return_value=mock_integration),
        ),
    ):
        from custom_components.dsvdc4ha.coordinator import HubCoordinator
        coord = HubCoordinator(mock_hass, port=9090)
        await coord.async_start()
        mock_api.start.assert_awaited_once()
        call_kwargs = mock_api.start.call_args.kwargs
        assert call_kwargs["zeroconf"] is mock_zeroconf
        assert callable(call_kwargs["on_session_ready"])
        assert callable(call_kwargs["on_disconnect"])


@pytest.mark.asyncio
async def test_coordinator_stop_delegates_to_api(mock_hass, mock_api):
    mock_zeroconf = MagicMock()
    mock_integration = MagicMock()
    mock_integration.version = "1.2.3"
    with (
        patch("custom_components.dsvdc4ha.coordinator.DsvdcApi", return_value=mock_api),
        patch(
            "custom_components.dsvdc4ha.coordinator.async_get_instance",
            new=AsyncMock(return_value=mock_zeroconf),
        ),
        patch(
            "custom_components.dsvdc4ha.coordinator.async_get_integration",
            new=AsyncMock(return_value=mock_integration),
        ),
    ):
        from custom_components.dsvdc4ha.coordinator import HubCoordinator
        coord = HubCoordinator(mock_hass, port=9090)
        await coord.async_start()
        await coord.async_stop()
        mock_api.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_setup_entry_hub_starts_coordinator(mock_api):
    mock_hass = MagicMock()
    mock_hass.data = {}
    mock_hass.config.internal_url = "http://ha.local"
    mock_hass.config.path = MagicMock(return_value="/tmp/dsvdc4ha_state")
    mock_hass.config_entries = MagicMock()
    mock_zeroconf = MagicMock()
    mock_integration = MagicMock()
    mock_integration.version = "1.2.3"

    with (
        patch("custom_components.dsvdc4ha.coordinator.DsvdcApi", return_value=mock_api),
        patch(
            "custom_components.dsvdc4ha.coordinator.async_get_instance",
            new=AsyncMock(return_value=mock_zeroconf),
        ),
        patch(
            "custom_components.dsvdc4ha.coordinator.async_get_integration",
            new=AsyncMock(return_value=mock_integration),
        ),
    ):
        entry = MagicMock(spec=ConfigEntry)
        entry.data = {"port": 9090}
        entry.entry_id = "test-hub-id"
        entry.subentries = {}
        mock_hass.config_entries.async_forward_entry_setups = AsyncMock()

        from custom_components.dsvdc4ha import async_setup_entry
        result = await async_setup_entry(mock_hass, entry)

        assert result is True
        assert "hub" in mock_hass.data.get("dsvdc4ha", {})
        mock_api.start.assert_awaited_once()
        call_kwargs = mock_api.start.call_args.kwargs
        assert call_kwargs["zeroconf"] is mock_zeroconf
        assert callable(call_kwargs["on_session_ready"])
        assert callable(call_kwargs["on_disconnect"])
