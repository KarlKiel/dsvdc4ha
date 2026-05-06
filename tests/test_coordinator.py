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
    with patch("custom_components.dsvdc4ha.coordinator.DsvdcApi", return_value=mock_api):
        from custom_components.dsvdc4ha.coordinator import HubCoordinator
        coord = HubCoordinator(mock_hass, port=9090)
        await coord.async_start()
        mock_api.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_coordinator_stop_delegates_to_api(mock_hass, mock_api):
    with patch("custom_components.dsvdc4ha.coordinator.DsvdcApi", return_value=mock_api):
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

    with patch("custom_components.dsvdc4ha.coordinator.DsvdcApi", return_value=mock_api):
        entry = MagicMock(spec=ConfigEntry)
        entry.data = {"entry_type": "hub", "port": 9090}
        entry.entry_id = "test-hub-id"

        from custom_components.dsvdc4ha import async_setup_entry
        result = await async_setup_entry(mock_hass, entry)

        assert result is True
        assert "hub" in mock_hass.data.get("dsvdc4ha", {})
        mock_api.start.assert_awaited_once()
