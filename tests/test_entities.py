"""Tests that mirror entity classes have correct default visibility.

HA's CachedProperties metaclass moves `_attr_X = value` class assignments
into a private `__attr_X` backing attribute and replaces `_attr_X` with a
property.  Tests therefore check `__attr_entity_registry_visible_default`
(the backing store) rather than `_attr_entity_registry_visible_default`
(which resolves to the property descriptor after metaclass processing).
"""


def test_button_sensor_entity_hidden_by_default():
    from custom_components.dsvdc4ha.sensor import ButtonSensorEntity
    assert getattr(ButtonSensorEntity, "__attr_entity_registry_visible_default") is False


def test_sensor_input_entity_hidden_by_default():
    from custom_components.dsvdc4ha.sensor import SensorInputEntity
    assert getattr(SensorInputEntity, "__attr_entity_registry_visible_default") is False


def test_output_channel_entity_hidden_by_default():
    from custom_components.dsvdc4ha.sensor import OutputChannelEntity
    assert getattr(OutputChannelEntity, "__attr_entity_registry_visible_default") is False


def test_binary_input_entity_hidden_by_default():
    from custom_components.dsvdc4ha.binary_sensor import BinaryInputEntity
    assert getattr(BinaryInputEntity, "__attr_entity_registry_visible_default") is False


def test_output_settings_sensor_entity_hidden_by_default():
    from custom_components.dsvdc4ha.sensor import OutputSettingsSensorEntity
    assert getattr(OutputSettingsSensorEntity, "__attr_entity_registry_visible_default") is False


def test_hub_connectivity_sensor_visible_by_default():
    from custom_components.dsvdc4ha.binary_sensor import HubConnectivitySensor
    # HubConnectivitySensor has no _attr_ override, so no __attr_ backing is set.
    # Default of True should apply at runtime.
    assert getattr(HubConnectivitySensor, "__attr_entity_registry_visible_default", True) is True
