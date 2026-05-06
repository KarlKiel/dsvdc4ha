"""Tests for HubCoordinator."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


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
