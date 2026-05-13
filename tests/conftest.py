"""Shared test fixtures for dsvdc4ha."""
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture
def mock_api():
    """Return a mock DsvdcApi instance."""
    api = MagicMock()
    api.start = AsyncMock()
    api.stop = AsyncMock()
    api.add_device = MagicMock()
    api.announce_device = AsyncMock()
    api.vanish_device = AsyncMock()
    api.report_button_click = AsyncMock()
    api.report_sensor_value = AsyncMock()
    api.report_binary_value = AsyncMock()
    api.report_binary_extended_value = AsyncMock()
    api.report_channel_value = AsyncMock()
    return api


@pytest.fixture
def hub_config_entry_data():
    return {"port": 9090}


@pytest.fixture
def subentry_data():
    return {
        "name": "Test Lamp",
        "vendorName": "Acme",
        "displayId": "LampV1",
        "vdsds": [
            {
                "displayId": "LampUnit",
                "primaryGroup": 1,
                "model": "LampUnit",
                "vendorName": "Acme",
                "modelVersion": "v1",
                "modelUID": "AcmeLampV1",
                "active": True,
                "identify_action": None,
                "firmwareUpdate_action": None,
                "optional": {},
                "buttons": [],
                "binary_inputs": [],
                "sensors": [],
                "output": None,
            }
        ],
    }
