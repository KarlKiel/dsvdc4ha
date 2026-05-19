"""Tests for _icon_utils shared icon helpers."""
from __future__ import annotations
import base64
from unittest.mock import patch


def test_bundled_icon_b64_returns_none_for_unknown_slug(tmp_path):
    """bundled_icon_b64 returns None when the PNG file does not exist."""
    from custom_components.dsvdc4ha._icon_utils import bundled_icon_b64
    with patch("custom_components.dsvdc4ha._icon_utils.ICONS_DIR", tmp_path):
        assert bundled_icon_b64("nonexistent-icon") is None


def test_bundled_icon_b64_returns_base64_png_for_known_slug(tmp_path):
    """bundled_icon_b64 returns base64-encoded bytes when the file exists."""
    from custom_components.dsvdc4ha._icon_utils import bundled_icon_b64
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    (tmp_path / "lightbulb.png").write_bytes(fake_png)
    with patch("custom_components.dsvdc4ha._icon_utils.ICONS_DIR", tmp_path):
        result = bundled_icon_b64("lightbulb")
    assert result is not None
    assert base64.b64decode(result) == fake_png


def test_bundled_icon_b64_for_returns_icon_for_known_domain(tmp_path):
    """bundled_icon_b64_for resolves domain → slug → PNG."""
    from custom_components.dsvdc4ha._icon_utils import bundled_icon_b64_for
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    (tmp_path / "lightbulb.png").write_bytes(fake_png)  # "light" → "lightbulb"
    with patch("custom_components.dsvdc4ha._icon_utils.ICONS_DIR", tmp_path):
        result = bundled_icon_b64_for("light", None)
    assert result is not None
    assert base64.b64decode(result) == fake_png


def test_bundled_icon_b64_for_returns_none_for_unknown_domain(tmp_path):
    """bundled_icon_b64_for returns None for domains not in MDI_DOMAIN_ICONS."""
    from custom_components.dsvdc4ha._icon_utils import bundled_icon_b64_for
    with patch("custom_components.dsvdc4ha._icon_utils.ICONS_DIR", tmp_path):
        assert bundled_icon_b64_for("weather", None) is None


def test_bundled_icon_b64_for_prefers_device_class_over_domain(tmp_path):
    """bundled_icon_b64_for uses domain.device_class before plain domain."""
    from custom_components.dsvdc4ha._icon_utils import bundled_icon_b64_for
    blind_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 10
    (tmp_path / "blinds.png").write_bytes(blind_png)  # cover.blind → blinds
    with patch("custom_components.dsvdc4ha._icon_utils.ICONS_DIR", tmp_path):
        result = bundled_icon_b64_for("cover", "blind")
    assert result is not None
    assert base64.b64decode(result) == blind_png
