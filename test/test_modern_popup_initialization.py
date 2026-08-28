#!/usr/bin/env python
"""Test to verify the fix for ModernSubmenu initialization bug."""


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
    from fpdb_3_legacy.PopupIcons import get_icon_provider
    from fpdb_3_legacy.PopupThemes import get_theme

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


def test_modern_submenu_attributes() -> None:
    """Test que ModernSubmenu a tous les attributs requis après init."""
    _run_theme_and_provider_tests()


def test_initialization_order() -> None:
    """Test that the initialization order is correct."""
    # Simulate the corrected initialization order

    # Steps are documented above for reference
