"""Graph, stats and filter colours follow the theme and read on it (#712).

The graph, stats and hands surfaces were a fixed ``#222b32``. That only matched
``dark_teal``: grey on every other dark theme, and dark under a light theme
whose text and grid are dark too. The filter sidebar hardcoded its greys the
same way, and wrote headings in the raw accent, yellow on near-white under
``light_amber``.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from fpdb_3_legacy.ThemeManager import ThemeManager

# WCAG AA for normal-size text: the filter headings are 11px bold.
MIN_TEXT_RATIO = 4.5

BUNDLED_THEMES_DIR = Path(__file__).resolve().parent.parent / "fpdb_3_legacy" / "themes"


def _stock_themes() -> list[str]:
    """qt_material's own themes, found without importing it (it wants PySide6 first)."""
    spec = importlib.util.find_spec("qt_material")
    if spec is None or spec.origin is None:
        return []
    return sorted(path.name for path in (Path(spec.origin).parent / "themes").glob("*.xml"))


def _all_themes() -> list[str]:
    bundled = sorted(str(path) for path in BUNDLED_THEMES_DIR.glob("*.xml"))
    return _stock_themes() + bundled


# ---------------------------------------------------------------------------
# contrast helpers
# ---------------------------------------------------------------------------
def test_contrast_ratio_spans_one_to_twenty_one():
    assert ThemeManager.contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)
    assert ThemeManager.contrast_ratio("#ffffff", "#000000") == pytest.approx(21.0)
    assert ThemeManager.contrast_ratio("#777777", "#777777") == pytest.approx(1.0)


def test_a_readable_accent_is_kept_as_is():
    assert ThemeManager._readable_accent("#34d399", "#0f172a") == "#34d399"


def test_a_yellow_accent_is_darkened_on_a_light_background():
    shade = ThemeManager._readable_accent("#fff64f", "#f4f4f4")

    assert ThemeManager.contrast_ratio(shade, "#f4f4f4") >= MIN_TEXT_RATIO
    red, green, blue = ThemeManager._rgb(shade)
    assert red > blue and green > blue, f"{shade} is no longer a yellow"


def test_a_dark_accent_is_lightened_on_a_dark_background():
    shade = ThemeManager._readable_accent("#1a237e", "#202020")

    assert ThemeManager.contrast_ratio(shade, "#202020") >= MIN_TEXT_RATIO
    assert ThemeManager._relative_luminance(shade) > ThemeManager._relative_luminance("#1a237e")


# ---------------------------------------------------------------------------
# every theme, applied for real
# ---------------------------------------------------------------------------
@pytest.mark.qt
@pytest.mark.parametrize("theme", _all_themes(), ids=lambda theme: Path(theme).stem)
def test_surfaces_follow_the_theme_and_read(theme):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    import qt_material

    qt_material.apply_stylesheet(app, theme=theme)
    manager = ThemeManager()
    palette = manager.get_legacy_palette()
    graph = manager.get_theme_colors()

    for surface in ("surface", "surface_panel", "sidebar", "sidebar_panel"):
        assert manager._is_dark(palette[surface]) == manager._is_dark(palette["window"]), (
            f"{surface} {palette[surface]} is not on the same side as the window {palette['window']}"
        )
    assert manager.contrast_ratio(graph["foreground"], graph["background"]) >= MIN_TEXT_RATIO
    assert manager.contrast_ratio(palette["text"], palette["surface_panel"]) >= MIN_TEXT_RATIO
    assert manager.contrast_ratio(palette["accent_text"], palette["window"]) >= MIN_TEXT_RATIO

    filters = manager.build_filter_stylesheet()
    heading = manager._stylesheet_property(filters, "QLabel#filterTitle", "color")
    assert heading is not None
    assert manager.contrast_ratio(heading, palette["sidebar"]) >= MIN_TEXT_RATIO
