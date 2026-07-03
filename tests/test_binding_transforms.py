"""Tests for the binding transform registry."""

def test_transform_registry_has_passthrough():
    from custom_components.dsvdc4ha.binding_transforms import TRANSFORMS
    assert "passthrough" in TRANSFORMS

def test_passthrough_transform():
    from custom_components.dsvdc4ha.binding_transforms import apply_transform
    assert apply_transform("passthrough", 42.0) == 42.0

def test_scale_0_255_to_0_100():
    from custom_components.dsvdc4ha.binding_transforms import apply_transform
    result = apply_transform("scale_0_255_to_0_100", 255.0)
    assert abs(result - 100.0) < 0.1
    result = apply_transform("scale_0_255_to_0_100", 0.0)
    assert result == 0.0

def test_scale_0_100_to_0_255():
    from custom_components.dsvdc4ha.binding_transforms import apply_transform
    result = apply_transform("scale_0_100_to_0_255", 100.0)
    assert abs(result - 255.0) < 0.5

def test_bool_to_0_1():
    from custom_components.dsvdc4ha.binding_transforms import apply_transform
    assert apply_transform("bool_to_1_0", "on") == 1.0
    assert apply_transform("bool_to_1_0", "off") == 0.0

def test_invert_0_100():
    from custom_components.dsvdc4ha.binding_transforms import apply_transform
    assert apply_transform("invert_0_100", 70.0) == 30.0
