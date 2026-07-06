"""Named value transforms for structured channel bindings."""
from __future__ import annotations
from typing import Any

TRANSFORMS: dict[str, dict[str, str]] = {
    "passthrough": {
        "label": "Pass through (no conversion)",
        "push_expr": "float(v)",
        "apply_expr": "float(v)",
    },
    "scale_0_255_to_0_100": {
        "label": "HA brightness (0-255) → dS (0-100%)",
        "push_expr": "round(v / 2.55, 1)",
        "apply_expr": "round(v * 2.55)",
    },
    "scale_0_100_to_0_255": {
        "label": "dS percentage (0-100%) → HA (0-255)",
        "push_expr": "round(v * 2.55)",
        "apply_expr": "round(v / 2.55, 1)",
    },
    "bool_to_1_0": {
        "label": "HA on/off → dS 1/0",
        "push_expr": "1.0 if str(v).lower() in ('on','true','1') else 0.0",
        "apply_expr": "1.0 if v > 0 else 0.0",
    },
    "bool_to_100_0": {
        "label": "HA on/off → dS 100%/0%",
        "push_expr": "100.0 if str(v).lower() in ('on','true','1') else 0.0",
        "apply_expr": "100.0 if v > 0 else 0.0",
    },
    "invert_0_100": {
        "label": "Invert 0-100% (dS shade position vs. HA open position)",
        "push_expr": "round(100.0 - float(v), 1)",
        "apply_expr": "round(100.0 - float(v), 1)",
    },
    "mired_to_kelvin": {
        "label": "HA color_temp (mired) → dS color temperature (mired — passthrough, dS uses mired)",
        "push_expr": "float(v)",
        "apply_expr": "float(v)",
    },
    "kelvin_to_mired": {
        "label": "HA color_temp_kelvin (K) → dS color temperature (mired)",
        "push_expr": "round(1_000_000 / max(float(v), 1))",
        "apply_expr": "round(1_000_000 / max(float(v), 1))",
    },
    "hs_hue": {
        "label": "HA hs_color[0] → dS hue (0-360°)",
        "push_expr": "(v or (0, 0))[0]",
        "apply_expr": "float(v)",
    },
    "hs_saturation": {
        "label": "HA hs_color[1] → dS saturation (0-100%)",
        "push_expr": "(v or (0, 0))[1]",
        "apply_expr": "float(v)",
    },
}


def apply_transform(name: str, value: Any) -> float:
    """Apply a transform by name. For testing and runtime use.

    Security note (S2): the expr evaluated here always comes from the hardcoded
    TRANSFORMS dict above — never from user input or the network.  Callers are
    required to validate that *name* is a key in TRANSFORMS before calling this
    function (listeners.py checks ``name in TRANSFORMS`` before dispatch).

    Security note (S4): this context is intentionally smaller than the
    _SAFE_EVAL_CONTEXT in listeners.py.  It adds ``str`` (required by
    bool_to_1_0 / bool_to_100_0) but omits ``int``, ``abs``, ``_norm``,
    ``_denorm``, and ``_light_apply`` which are only needed for the richer
    user-authored push/apply expressions evaluated in listeners.py.
    """
    t = TRANSFORMS.get(name)
    if t is None:
        raise ValueError(f"Unknown transform: {name!r}")
    ctx = {"v": value, "__builtins__": {}, "round": round, "float": float, "str": str, "max": max}
    return float(eval(t["push_expr"], ctx))  # noqa: S307


TRANSFORM_OPTIONS: list[dict] = [
    {"value": k, "label": v["label"]} for k, v in TRANSFORMS.items()
]
