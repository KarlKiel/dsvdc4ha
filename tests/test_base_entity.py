"""Tests for DsvdcBaseEntity."""
from __future__ import annotations


def _make_entity(vdsd_data):
    from custom_components.dsvdc4ha.base_entity import DsvdcBaseEntity

    class Concrete(DsvdcBaseEntity):
        pass

    return Concrete("sub1", 0, vdsd_data, "uid")


def test_device_name_uses_name_field():
    ent = _make_entity({"name": "Smart Light", "displayId": "ModelX"})
    assert ent._attr_device_info["name"] == "Smart Light"


def test_device_name_falls_back_to_display_id():
    ent = _make_entity({"displayId": "ModelX"})
    assert ent._attr_device_info["name"] == "ModelX"


def test_device_name_falls_back_to_default():
    ent = _make_entity({})
    assert ent._attr_device_info["name"] == "vdSD"
