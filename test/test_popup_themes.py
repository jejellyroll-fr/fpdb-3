#!/usr/bin/env python
"""Tests for PopupThemes.py.

Test suite for the modern popup theme system.
"""

import os
import sys
import unittest

# Add the parent directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PopupThemes import (
    AVAILABLE_THEMES,
    ClassicTheme,
    MaterialDarkTheme,
    MaterialLightTheme,
    PopupTheme,
    get_stat_color,
    get_theme,
)


class TestPopupTheme(unittest.TestCase):
    """Test the base PopupTheme class."""

    def setUp(self) -> None:
        """Set up test theme."""
        self.theme = PopupTheme("test_theme")
        self.theme.colors = {
            "window_bg": "#000000",
            "text_primary": "#FFFFFF",
            "stat_high": "#FF0000",
            "stat_low": "#00FF00",
            "stat_neutral": "#808080",
        }
        self.theme.fonts = {"header": {"family": "Arial", "size": 12, "weight": "bold"}}
        self.theme.spacing = {"window_padding": 10, "row_height": 20}

    def test_theme_initialization(self) -> None:
        """Test theme initialization."""
        assert self.theme.name == "test_theme"
        assert isinstance(self.theme.colors, dict)
        assert isinstance(self.theme.fonts, dict)
        assert isinstance(self.theme.spacing, dict)

    def test_get_color(self) -> None:
        """Test color retrieval."""
        assert self.theme.get_color("window_bg") == "#000000"
        assert self.theme.get_color("text_primary") == "#FFFFFF"
        assert self.theme.get_color("nonexistent") == "#FFFFFF"  # Default

    def test_get_font(self) -> None:
        """Test font retrieval."""
        font = self.theme.get_font("header")
        assert font["family"] == "Arial"
        assert font["size"] == 12
        assert font["weight"] == "bold"

        # Test default
        default_font = self.theme.get_font("nonexistent")
        assert default_font["family"] == "Arial"
        assert default_font["size"] == 10

    def test_get_spacing(self) -> None:
        """Test spacing retrieval."""
        assert self.theme.get_spacing("window_padding") == 10
        assert self.theme.get_spacing("row_height") == 20
        assert self.theme.get_spacing("nonexistent") == 5  # Default


class TestMaterialDarkTheme(unittest.TestCase):
    """Test the Material Dark theme."""

    def setUp(self) -> None:
        """Set up Material Dark theme."""
        self.theme = MaterialDarkTheme()

    def test_theme_name(self) -> None:
        """Test theme name."""
        assert self.theme.name == "material_dark"

    def test_dark_colors(self) -> None:
        """Test dark theme colors."""
        assert self.theme.get_color("window_bg") == "#2E2E2E"
        assert self.theme.get_color("text_primary") == "#FFFFFF"
        assert self.theme.get_color("stat_high") == "#F44336"
        assert self.theme.get_color("stat_low") == "#4CAF50"

    def test_fonts(self) -> None:
        """Test font configurations."""
        header_font = self.theme.get_font("header")
        assert header_font["family"] == "Segoe UI"
        assert header_font["size"] == 12
        assert header_font["weight"] == "bold"

        stat_font = self.theme.get_font("stat_name")
        assert stat_font["family"] == "Segoe UI"
        assert stat_font["size"] == 9

    def test_spacing(self) -> None:
        """Test spacing configurations."""
        assert self.theme.get_spacing("window_padding") == 8
        assert self.theme.get_spacing("row_height") == 24
        assert self.theme.get_spacing("border_radius") == 4


class TestMaterialLightTheme(unittest.TestCase):
    """Test the Material Light theme."""

    def setUp(self) -> None:
        """Set up Material Light theme."""
        self.theme = MaterialLightTheme()

    def test_theme_name(self) -> None:
        """Test theme name."""
        assert self.theme.name == "material_light"

    def test_light_colors(self) -> None:
        """Test light theme colors."""
        assert self.theme.get_color("window_bg") == "#FAFAFA"
        assert self.theme.get_color("text_primary") == "#212121"
        assert self.theme.get_color("stat_high") == "#D32F2F"
        assert self.theme.get_color("stat_low") == "#388E3C"

    def test_contrast_with_dark(self) -> None:
        """Test that light theme has different colors from dark."""
        dark_theme = MaterialDarkTheme()
        assert self.theme.get_color("window_bg") != dark_theme.get_color("window_bg")
        assert self.theme.get_color("text_primary") != dark_theme.get_color("text_primary")


class TestClassicTheme(unittest.TestCase):
    """Test the Classic theme."""

    def setUp(self) -> None:
        """Set up Classic theme."""
        self.theme = ClassicTheme()

    def test_theme_name(self) -> None:
        """Test theme name."""
        assert self.theme.name == "classic"

    def test_classic_colors(self) -> None:
        """Test classic theme colors."""
        assert self.theme.get_color("window_bg") == "#EEEEEE"
        assert self.theme.get_color("text_primary") == "#000000"

    def test_classic_fonts(self) -> None:
        """Test classic fonts (Arial instead of Segoe UI)."""
        header_font = self.theme.get_font("header")
        assert header_font["family"] == "Arial"
        assert header_font["size"] == 11

    def test_classic_spacing(self) -> None:
        """Test classic spacing (smaller values)."""
        assert self.theme.get_spacing("window_padding") == 5
        assert self.theme.get_spacing("row_height") == 20


class TestThemeRegistry(unittest.TestCase):
    """Test the theme registry and factory functions."""

    def test_available_themes(self) -> None:
        """Test that all themes are registered."""
        expected_themes = ["material_dark", "material_light", "classic"]
        assert set(AVAILABLE_THEMES.keys()) == set(expected_themes)

    def test_get_theme_valid(self) -> None:
        """Test getting valid themes."""
        dark_theme = get_theme("material_dark")
        assert isinstance(dark_theme, MaterialDarkTheme)

        light_theme = get_theme("material_light")
        assert isinstance(light_theme, MaterialLightTheme)

        classic_theme = get_theme("classic")
        assert isinstance(classic_theme, ClassicTheme)

    def test_get_theme_invalid(self) -> None:
        """Test getting invalid theme returns default."""
        theme = get_theme("nonexistent_theme")
        assert isinstance(theme, MaterialDarkTheme)

    def test_get_theme_default(self) -> None:
        """Test default theme."""
        theme = get_theme()
        assert isinstance(theme, MaterialDarkTheme)


class TestStatColorFunction(unittest.TestCase):
    """Test the get_stat_color function."""

    def setUp(self) -> None:
        """Set up theme for testing."""
        self.theme = MaterialDarkTheme()

    def test_vpip_colors(self) -> None:
        """Test VPIP color classification."""
        # Low VPIP (tight)
        color = get_stat_color(self.theme, "vpip", 15.0)
        assert color == self.theme.get_color("stat_low")

        # Medium VPIP
        color = get_stat_color(self.theme, "vpip", 28.0)
        assert color == self.theme.get_color("stat_medium")

        # High VPIP (loose)
        color = get_stat_color(self.theme, "vpip", 45.0)
        assert color == self.theme.get_color("stat_high")

    def test_pfr_colors(self) -> None:
        """Test PFR color classification."""
        # Low PFR (passive)
        color = get_stat_color(self.theme, "pfr", 10.0)
        assert color == self.theme.get_color("stat_low")

        # High PFR (aggressive)
        color = get_stat_color(self.theme, "pfr", 30.0)
        assert color == self.theme.get_color("stat_high")

    def test_three_bet_colors(self) -> None:
        """Test 3-bet color classification."""
        # Low 3-bet
        color = get_stat_color(self.theme, "three_B", 2.0)
        assert color == self.theme.get_color("stat_low")

        # High 3-bet
        color = get_stat_color(self.theme, "three_B", 12.0)
        assert color == self.theme.get_color("stat_high")

    def test_unknown_stat(self) -> None:
        """Test unknown stat returns neutral color."""
        color = get_stat_color(self.theme, "unknown_stat", 50.0)
        assert color == self.theme.get_color("stat_neutral")

    def test_custom_thresholds(self) -> None:
        """Test custom thresholds."""
        custom_thresholds = {"custom_stat": {"low": 10, "high": 30}}

        # Low value
        color = get_stat_color(self.theme, "custom_stat", 5.0, custom_thresholds)
        assert color == self.theme.get_color("stat_low")

        # Medium value
        color = get_stat_color(self.theme, "custom_stat", 20.0, custom_thresholds)
        assert color == self.theme.get_color("stat_medium")

        # High value
        color = get_stat_color(self.theme, "custom_stat", 40.0, custom_thresholds)
        assert color == self.theme.get_color("stat_high")

    def test_edge_values(self) -> None:
        """Test edge values at thresholds."""
        # Just below low threshold
        color = get_stat_color(self.theme, "vpip", 19.9)
        assert color == self.theme.get_color("stat_low")

        # Just above high threshold
        color = get_stat_color(self.theme, "vpip", 35.1)
        assert color == self.theme.get_color("stat_high")

        # Exactly at thresholds should be medium
        color = get_stat_color(self.theme, "vpip", 20.0)
        assert color == self.theme.get_color("stat_medium")

        color = get_stat_color(self.theme, "vpip", 35.0)
        assert color == self.theme.get_color("stat_medium")


class TestThemeConsistency(unittest.TestCase):
    """Test theme consistency and completeness."""

    def test_all_themes_have_required_colors(self) -> None:
        """Test that all themes have required color keys."""
        required_colors = [
            "window_bg",
            "header_bg",
            "section_bg",
            "text_primary",
            "stat_high",
            "stat_medium",
            "stat_low",
            "stat_neutral",
        ]

        for theme_name in AVAILABLE_THEMES:
            theme = get_theme(theme_name)
            for color_key in required_colors:
                assert color_key in theme.colors, f"Theme {theme_name} missing color {color_key}"

    def test_all_themes_have_required_fonts(self) -> None:
        """Test that all themes have required font keys."""
        required_fonts = ["header", "section_title", "stat_name", "stat_value"]

        for theme_name in AVAILABLE_THEMES:
            theme = get_theme(theme_name)
            for font_key in required_fonts:
                assert font_key in theme.fonts, f"Theme {theme_name} missing font {font_key}"

    def test_all_themes_have_required_spacing(self) -> None:
        """Test that all themes have required spacing keys."""
        required_spacing = ["window_padding", "section_spacing", "row_height", "icon_size"]

        for theme_name in AVAILABLE_THEMES:
            theme = get_theme(theme_name)
            for spacing_key in required_spacing:
                assert spacing_key in theme.spacing, f"Theme {theme_name} missing spacing {spacing_key}"

    def test_color_values_format(self) -> None:
        """Test that color values are valid hex colors."""
        import re

        hex_pattern = re.compile(r"^#[0-9A-Fa-f]{6}$")

        for theme_name in AVAILABLE_THEMES:
            theme = get_theme(theme_name)
            for color_key, color_value in theme.colors.items():
                assert isinstance(color_value, str), f"Color {color_key} in {theme_name} is not a string"
                assert hex_pattern.match(color_value), f"Color {color_key} in {theme_name} is not valid hex: {color_value}"

    def test_font_values_format(self) -> None:
        """Test that font values have required properties."""
        for theme_name in AVAILABLE_THEMES:
            theme = get_theme(theme_name)
            for font_key, font_value in theme.fonts.items():
                assert isinstance(font_value, dict), f"Font {font_key} in {theme_name} is not a dict"
                assert "family" in font_value, f"Font {font_key} in {theme_name} missing family"
                assert "size" in font_value, f"Font {font_key} in {theme_name} missing size"
                assert isinstance(font_value["size"], int), f"Font {font_key} size in {theme_name} is not an integer"

    def test_spacing_values_format(self) -> None:
        """Test that spacing values are positive integers."""
        for theme_name in AVAILABLE_THEMES:
            theme = get_theme(theme_name)
            for spacing_key, spacing_value in theme.spacing.items():
                assert isinstance(spacing_value, int), f"Spacing {spacing_key} in {theme_name} is not an integer"
                assert spacing_value > 0, f"Spacing {spacing_key} in {theme_name} is not positive"


if __name__ == "__main__":
    unittest.main()
