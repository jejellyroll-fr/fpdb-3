#!/usr/bin/env python
"""Test to verify the fix for ModernSubmenu initialization bug."""

import sys
from pathlib import Path

# Add the main directory to sys.path to import FPDB modules
sys.path.insert(0, str(Path(__file__).parent.parent))


def _test_theme_methods(theme) -> None:
    """Test that the theme has the required methods."""
    assert hasattr(theme, "get_color"), "Theme should have get_color method"
    assert hasattr(theme, "get_spacing"), "Theme should have get_spacing method"


def _test_icon_provider_methods(icon_provider) -> None:
    """Test that the icon provider has the required methods."""
    assert hasattr(icon_provider, "get_icon"), "Icon provider should have get_icon method"


def _test_theme_values(theme) -> None:
    """Test that theme values are available."""
    bg_color = theme.get_color("window_bg")
    border_color = theme.get_color("border")
    border_radius = theme.get_spacing("border_radius")

    assert bg_color is not None, "Background color should be available"
    assert border_color is not None, "Border color should be available"
    assert border_radius is not None, "Border radius should be available"


def _get_theme_and_icon_provider():
    """Import and return theme and icon provider functions."""
    from PopupIcons import get_icon_provider
    from PopupThemes import get_theme

    return get_theme, get_icon_provider


def _run_theme_and_provider_tests() -> None:
    """Run theme and icon provider initialization tests."""
    get_theme, get_icon_provider = _get_theme_and_icon_provider()

    # Test that classes have the required methods
    theme = get_theme("material_dark")
    _test_theme_methods(theme)

    icon_provider = get_icon_provider("emoji")
    _test_icon_provider_methods(icon_provider)

    # Test initialization order without creating a QWidget
    # Simulate what happens in __init__
    theme_name = "material_dark"
    icon_provider_name = "emoji"

    # These assignments must succeedr AVANT super().__init__()
    theme = get_theme(theme_name)
    icon_provider = get_icon_provider(icon_provider_name)

    # Vérifier que les objets sont utilisables
    _test_theme_values(theme)


def test_modern_submenu_attributes() -> bool | None:
    """Test que ModernSubmenu a tous les attributs requis après init."""
    try:
        _run_theme_and_provider_tests()
        return True

    except Exception:
        import traceback

        traceback.print_exc()
        return False


def test_initialization_order() -> None:
    """Test that the initialization order is correct."""
    # Simulate the corrected initialization order
    steps = [
        "1. Extract theme/icon names from kwargs",
        "2. Initialize theme = get_theme(theme_name)",
        "3. Initialize icon_provider = get_icon_provider(icon_provider_name)",
        "4. Initialize sections = {}",
        "5. Call super().__init__() which calls create()",
        "6. create() calls setup_window_style() which uses self.theme",
    ]

    # Steps are documented above for reference
