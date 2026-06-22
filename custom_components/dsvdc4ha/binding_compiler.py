"""Compile structured binding configs to push_expr / apply_expr strings."""
from __future__ import annotations

import re

from .binding_transforms import TRANSFORMS


def compile_push_binding(binding: dict) -> str:
    """Return a push_expr string for the given structured push binding.

    binding keys:
      source_attribute: str | None  — None = use entity.state; otherwise attrs key
      transform: str                — key in TRANSFORMS registry
    """
    t = TRANSFORMS.get(binding.get("transform", "passthrough"), TRANSFORMS["passthrough"])
    push_template = t["push_expr"]

    attr = binding.get("source_attribute")
    if attr is None:
        source = "entity.state"
    else:
        source = f"attrs.get('{attr}')"

    # Replace standalone `v` in the push template with the actual source expression.
    expr = re.sub(r'\bv\b', source, push_template)
    return expr


def compile_apply_binding(binding: dict) -> str:
    """Return an apply_expr string for the given structured apply binding.

    binding keys:
      service: str        — HA service in 'domain.service' format
      parameter: str|None — service_data key to set; None = no data beyond entity_id
      transform: str      — key in TRANSFORMS registry (applied to the dS channel value)
    """
    t = TRANSFORMS.get(binding.get("transform", "passthrough"), TRANSFORMS["passthrough"])
    apply_template = t["apply_expr"]

    service = binding["service"]
    parts = service.split(".", 1)
    domain = parts[0]
    service_name = parts[1] if len(parts) > 1 else service
    parameter = binding.get("parameter")

    # Build the transformed-value expression (applied to `value` from listeners.py)
    transformed = re.sub(r'\bv\b', "value", apply_template)

    if parameter:
        service_data = f"{{'{parameter}': {transformed}}}"
    else:
        service_data = "{}"

    return f"{{'domain':'{domain}','service':'{service_name}','service_data':{service_data}}}"


def compile_channel_binding(push_binding: dict, apply_binding: dict | None) -> dict:
    """Return a channel config dict with push_expr and optionally apply_expr."""
    result: dict = {}
    result["push_expr"] = compile_push_binding(push_binding)
    if push_binding.get("source_entity"):
        result["read_entity"] = push_binding["source_entity"]
    if apply_binding:
        result["apply_expr"] = compile_apply_binding(apply_binding)
    return result
