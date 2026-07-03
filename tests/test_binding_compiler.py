"""Tests for the binding compiler."""

def test_compile_push_binding_from_state():
    """Push binding with source_attribute=None uses entity.state directly."""
    from custom_components.dsvdc4ha.binding_compiler import compile_push_binding
    push_expr = compile_push_binding({
        "source_attribute": None,
        "transform": "bool_to_1_0",
    })
    assert "entity.state" in push_expr

def test_compile_push_binding_from_attribute():
    """Push binding with source_attribute uses attrs.get(attr)."""
    from custom_components.dsvdc4ha.binding_compiler import compile_push_binding
    push_expr = compile_push_binding({
        "source_attribute": "brightness",
        "transform": "scale_0_255_to_0_100",
    })
    assert "attrs.get('brightness')" in push_expr or "attrs['brightness']" in push_expr

def test_compile_apply_binding_turn_on():
    """Apply binding produces a valid HA service call expression."""
    from custom_components.dsvdc4ha.binding_compiler import compile_apply_binding
    apply_expr = compile_apply_binding({
        "service": "light.turn_on",
        "parameter": "brightness",
        "transform": "scale_0_100_to_0_255",
    })
    assert "light" in apply_expr
    assert "brightness" in apply_expr

def test_compile_apply_binding_with_no_parameter():
    """Apply binding with no parameter produces a plain on/off service call."""
    from custom_components.dsvdc4ha.binding_compiler import compile_apply_binding
    apply_expr = compile_apply_binding({
        "service": "switch.turn_on",
        "parameter": None,
        "transform": "bool_to_1_0",
    })
    assert "switch" in apply_expr

def test_compile_push_binding_from_attribute_brightness():
    """Compiled push expression correctly evaluates with mock attrs."""
    from custom_components.dsvdc4ha.binding_compiler import compile_push_binding
    expr = compile_push_binding({
        "source_attribute": "brightness",
        "transform": "scale_0_255_to_0_100",
    })
    ctx = {"attrs": {"brightness": 128}, "entity": None, "round": round, "float": float, "__builtins__": {}}
    result = eval(expr, ctx)  # noqa: S307
    assert abs(result - 50.0) < 1.0
