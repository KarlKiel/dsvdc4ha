"""Tests for device property exposure."""
from homeassistant.helpers.entity import EntityCategory


def test_property_sensor_entity_hidden_by_default():
    from custom_components.dsvdc4ha.sensor import PropertySensorEntity
    assert getattr(PropertySensorEntity, "__attr_entity_registry_visible_default") is False


def test_property_sensor_entity_description_category():
    from custom_components.dsvdc4ha.sensor import PropertySensorEntity
    ent = PropertySensorEntity(
        "sub1", 0, {"name": "MyDevice"},
        "out_desc_function", "Output Desc: function", 0, EntityCategory.DIAGNOSTIC,
    )
    assert ent._attr_name == "Output Desc: function"
    assert ent._attr_entity_category == EntityCategory.DIAGNOSTIC
    assert ent.state == 0


def test_property_sensor_entity_config_category():
    from custom_components.dsvdc4ha.sensor import PropertySensorEntity
    ent = PropertySensorEntity(
        "sub1", 0, {"name": "MyDevice"},
        "out_setting_mode", "Output Setting: mode", 1, EntityCategory.CONFIG,
    )
    assert ent._attr_entity_category == EntityCategory.CONFIG


def test_property_sensor_entity_no_category():
    from custom_components.dsvdc4ha.sensor import PropertySensorEntity
    ent = PropertySensorEntity(
        "sub1", 0, {"name": "MyDevice"},
        "out_state_error", "Output State: error", 0,
    )
    assert ent._attr_entity_category is None


def test_property_sensor_entity_bi_naming():
    from custom_components.dsvdc4ha.sensor import PropertySensorEntity
    ent = PropertySensorEntity(
        "sub1", 0, {"name": "MyDevice"},
        "bi_0_desc_inputType", "BI 0 Desc: inputType", 3, EntityCategory.DIAGNOSTIC,
    )
    assert ent._attr_name == "BI 0 Desc: inputType"
    assert ent.state == 3


def test_property_sensor_entity_vdsd_naming():
    from custom_components.dsvdc4ha.sensor import PropertySensorEntity
    ent = PropertySensorEntity(
        "sub1", 0, {"name": "MyDevice"},
        "vdsd_primaryGroup", "vdSD: primaryGroup", 1, EntityCategory.DIAGNOSTIC,
    )
    assert ent._attr_name == "vdSD: primaryGroup"
    assert ent.state == 1
