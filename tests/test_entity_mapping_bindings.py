"""Validate that all output channel defs have apply_expr/push_expr."""
from __future__ import annotations
import pytest
from custom_components.dsvdc4ha.entity_mapping import ENTITY_MAPPING


def _collect_channel_defs() -> list[tuple[str, str | None, int, dict]]:
    """Return (domain, device_class, ch_index, ch_dict) for every output channel def."""
    result = []
    for entry in ENTITY_MAPPING:
        o = entry.get("output")
        if not o:
            continue
        domain = entry["domain"]
        dc = entry["device_class"]
        for i, ch in enumerate(o.get("channels", [])):
            result.append((domain, dc, i, ch))
        for usage_channels in o.get("channels_by_usage", {}).values():
            for i, ch in enumerate(usage_channels):
                result.append((domain, dc, i, ch))
    return result


@pytest.mark.parametrize("domain,dc,ch_idx,ch", _collect_channel_defs())
def test_channel_has_apply_expr(domain, dc, ch_idx, ch):
    assert "apply_expr" in ch, (
        f"{domain}/{dc} ch{ch_idx} (channel_type={ch['channel_type']}) missing apply_expr"
    )
    assert isinstance(ch["apply_expr"], str) and ch["apply_expr"]


@pytest.mark.parametrize("domain,dc,ch_idx,ch", _collect_channel_defs())
def test_channel_has_push_expr(domain, dc, ch_idx, ch):
    assert "push_expr" in ch, (
        f"{domain}/{dc} ch{ch_idx} (channel_type={ch['channel_type']}) missing push_expr"
    )
    assert isinstance(ch["push_expr"], str) and ch["push_expr"]
