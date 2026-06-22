"""Tests for device property exposure."""
from homeassistant.helpers.entity import EntityCategory


def test_output_description_sensor_entity_has_correct_attributes():
    from custom_components.dsvdc4ha.sensor import OutputDescriptionSensorEntity
    ent = OutputDescriptionSensorEntity("sub1", 0, {"name": "MyDevice"}, "function", 0)
    assert ent._attr_name == "Description: function"
    assert getattr(ent, "__attr_entity_registry_visible_default", None) is False
    assert ent._attr_entity_category == EntityCategory.DIAGNOSTIC


def test_output_state_sensor_entity_has_correct_attributes():
    from custom_components.dsvdc4ha.sensor import OutputStateSensorEntity
    ent = OutputStateSensorEntity("sub1", 0, {"name": "MyDevice"}, "localPriority", False)
    assert ent._attr_name == "State: localPriority"
    assert getattr(ent, "__attr_entity_registry_visible_default", None) is False


def test_output_description_sensor_entity_state():
    from custom_components.dsvdc4ha.sensor import OutputDescriptionSensorEntity
    ent = OutputDescriptionSensorEntity("sub1", 0, {"name": "MyDevice"}, "outputUsage", 3)
    assert ent.state == 3


def test_output_state_sensor_entity_handle_update():
    from custom_components.dsvdc4ha.sensor import OutputStateSensorEntity
    ent = OutputStateSensorEntity("sub1", 0, {"name": "MyDevice"}, "error", 0)
    ent.hass = None
    ent._handle_state_update(5)
    assert ent._attr_native_value == 5
