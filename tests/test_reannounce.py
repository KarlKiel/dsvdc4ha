"""Tests for re-announce button."""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_force_reannounce_clears_announced_flag():
    """force_reannounce_device removes entry from _ever_announced and calls announce."""
    from custom_components.dsvdc4ha.api import DsvdcApi
    api = DsvdcApi(port=9090, version="1.0", config_url="http://ha", state_path="/tmp/s")
    api._ever_announced = {"subentry-1"}
    api._devices = {}
    api._host = MagicMock()
    api._host.session = None
    await api.force_reannounce_device("subentry-1")
    assert "subentry-1" not in api._ever_announced
