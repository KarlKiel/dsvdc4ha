"""Tests for sensor and binary_sensor entities."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock
from custom_components.dsvdc4ha.sensor import ButtonSensorEntity, SensorInputEntity, OutputChannelEntity
from custom_components.dsvdc4ha.binary_sensor import BinaryInputEntity
from custom_components.dsvdc4ha.const import CLICK_TYPE_NAMES


def _make_vdsd():
    return {
        "displayId": "TestUnit",
        "vendorName": "Acme",
        "model": "U1",
        "modelVersion": "v1",
        "name": "Lamp",
    }


def test_button_sensor_initial_state_is_none():
    btn_data = {"dsIndex": 0, "name": "Btn", "callbackType": "clickTypes", "callback_entity": "sensor.x"}
    entity = ButtonSensorEntity("entry1", 0, _make_vdsd(), btn_data)
    assert entity.state is None


def test_button_sensor_updates_state_from_click_type():
    btn_data = {"dsIndex": 0, "name": "Btn", "callbackType": "clickTypes", "callback_entity": "sensor.x"}
    entity = ButtonSensorEntity("entry1", 0, _make_vdsd(), btn_data)
    entity._handle_click(7)
    assert entity.state == CLICK_TYPE_NAMES[7]


def test_button_sensor_unique_id():
    btn_data = {"dsIndex": 2, "name": "Btn", "callbackType": "clickTypes", "callback_entity": "sensor.x"}
    entity = ButtonSensorEntity("entry1", 0, _make_vdsd(), btn_data)
    assert entity.unique_id == "entry1_0_button_2"


def test_sensor_input_initial_state_is_none():
    si_data = {"dsIndex": 0, "name": "Temp", "sensorType": 1, "callback_entity": "sensor.temp"}
    entity = SensorInputEntity("entry1", 0, _make_vdsd(), si_data)
    assert entity.state is None


def test_sensor_input_updates_state():
    si_data = {"dsIndex": 0, "name": "Temp", "sensorType": 1, "callback_entity": "sensor.temp"}
    entity = SensorInputEntity("entry1", 0, _make_vdsd(), si_data)
    entity._handle_value(22.5)
    assert entity.state == 22.5


def test_output_channel_entity_initial_state():
    ch_data = {"dsIndex": 0, "name": "Brightness", "channelType": 1}
    entity = OutputChannelEntity("entry1", 0, _make_vdsd(), {}, ch_data)
    assert entity.state is None


def test_output_channel_entity_updates():
    ch_data = {"dsIndex": 0, "name": "Brightness", "channelType": 1}
    entity = OutputChannelEntity("entry1", 0, _make_vdsd(), {}, ch_data)
    entity._handle_value(75.0)
    assert entity.state == 75.0


def test_binary_input_initial_state_is_none():
    bi_data = {"dsIndex": 0, "name": "Window", "valueType": "boolean", "callback_entity": "binary_sensor.w"}
    entity = BinaryInputEntity("entry1", 0, _make_vdsd(), bi_data)
    assert entity.is_on is None


def test_binary_input_updates_state():
    bi_data = {"dsIndex": 0, "name": "Window", "valueType": "boolean", "callback_entity": "binary_sensor.w"}
    entity = BinaryInputEntity("entry1", 0, _make_vdsd(), bi_data)
    entity._handle_value(True)
    assert entity.is_on is True


def test_binary_input_unique_id():
    bi_data = {"dsIndex": 1, "name": "Window", "valueType": "boolean", "callback_entity": "binary_sensor.w"}
    entity = BinaryInputEntity("entry1", 0, _make_vdsd(), bi_data)
    assert entity.unique_id == "entry1_0_binary_input_1"
