#!/usr/bin/env python
"""Tests for PopupThemes.py

Test suite for the modern popup theme system.
"""

import unittest
import sys
import os

# Add the parent directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PopupThemes import (
    PopupTheme, MaterialDarkTheme, MaterialLightTheme, ClassicTheme,
    get_theme, get_stat_color, AVAILABLE_THEMES
)


class TestPopupTheme(unittest.TestCase):
    """Test the base PopupTheme class."""
    
    def setUp(self):
        """Set up test theme."""
        self.theme = PopupTheme("test_theme")
        self.theme.colors = {
            "window_bg": "#000000",
            "text_primary": "#FFFFFF",
            "stat_high": "#FF0000",
            "stat_low": "#00FF00",
            "stat_neutral": "#808080"
        }
        self.theme.fonts = {
            "header": {"family": "Arial", "size": 12, "weight": "bold"}
        }
        self.theme.spacing = {
            "window_padding": 10,
            "row_height": 20
        }
    
    def test_theme_initialization(self):
        """Test theme initialization."""
        self.assertEqual(self.theme.name, "test_theme")
        self.assertIsInstance(self.theme.colors, dict)
        self.assertIsInstance(self.theme.fonts, dict)
        self.assertIsInstance(self.theme.spacing, dict)
    
    def test_get_color(self):
        """Test color retrieval."""
        self.assertEqual(self.theme.get_color("window_bg"), "#000000")
        self.assertEqual(self.theme.get_color("text_primary"), "#FFFFFF")
        self.assertEqual(self.theme.get_color("nonexistent"), "#FFFFFF")  # Default
    
    def test_get_font(self):
        """Test font retrieval."""
        font = self.theme.get_font("header")
        self.assertEqual(font["family"], "Arial")
        self.assertEqual(font["size"], 12)
        self.assertEqual(font["weight"], "bold")
        
        # Test default
        default_font = self.theme.get_font("nonexistent")
        self.assertEqual(default_font["family"], "Arial")
        self.assertEqual(default_font["size"], 10)
    
    def test_get_spacing(self):
        """Test spacing retrieval."""
        self.assertEqual(self.theme.get_spacing("window_padding"), 10)
        self.assertEqual(self.theme.get_spacing("row_height"), 20)
        self.assertEqual(self.theme.get_spacing("nonexistent"), 5)  # Default


class TestMaterialDarkTheme(unittest.TestCase):
    """Test the Material Dark theme."""
    
    def setUp(self):
        """Set up Material Dark theme."""
        self.theme = MaterialDarkTheme()
    
    def test_theme_name(self):
        """Test theme name."""
        self.assertEqual(self.theme.name, "material_dark")
    
    def test_dark_colors(self):
        """Test dark theme colors."""
        self.assertEqual(self.theme.get_color("window_bg"), "#2E2E2E")
        self.assertEqual(self.theme.get_color("text_primary"), "#FFFFFF")
        self.assertEqual(self.theme.get_color("stat_high"), "#F44336")
        self.assertEqual(self.theme.get_color("stat_low"), "#4CAF50")
    
    def test_fonts(self):
        """Test font configurations."""
        header_font = self.theme.get_font("header")
        self.assertEqual(header_font["family"], "Segoe UI")
        self.assertEqual(header_font["size"], 12)
        self.assertEqual(header_font["weight"], "bold")
        
        stat_font = self.theme.get_font("stat_name")
        self.assertEqual(stat_font["family"], "Segoe UI")
        self.assertEqual(stat_font["size"], 9)
    
    def test_spacing(self):
        """Test spacing configurations."""
        self.assertEqual(self.theme.get_spacing("window_padding"), 8)
        self.assertEqual(self.theme.get_spacing("row_height"), 24)
        self.assertEqual(self.theme.get_spacing("border_radius"), 4)


class TestMaterialLightTheme(unittest.TestCase):
    """Test the Material Light theme."""
    
    def setUp(self):
        """Set up Material Light theme."""
        self.theme = MaterialLightTheme()
    
    def test_theme_name(self):
        """Test theme name."""
        self.assertEqual(self.theme.name, "material_light")
    
    def test_light_colors(self):
        """Test light theme colors."""
        self.assertEqual(self.theme.get_color("window_bg"), "#FAFAFA")
        self.assertEqual(self.theme.get_color("text_primary"), "#212121")
        self.assertEqual(self.theme.get_color("stat_high"), "#D32F2F")
        self.assertEqual(self.theme.get_color("stat_low"), "#388E3C")
    
    def test_contrast_with_dark(self):
        """Test that light theme has different colors from dark."""
        dark_theme = MaterialDarkTheme()
        self.assertNotEqual(
            self.theme.get_color("window_bg"),
            dark_theme.get_color("window_bg")
        )
        self.assertNotEqual(
            self.theme.get_color("text_primary"),
            dark_theme.get_color("text_primary")
        )


class TestClassicTheme(unittest.TestCase):
    """Test the Classic theme."""
    
    def setUp(self):
        """Set up Classic theme."""
        self.theme = ClassicTheme()
    
    def test_theme_name(self):
        """Test theme name."""
        self.assertEqual(self.theme.name, "classic")
    
    def test_classic_colors(self):
        """Test classic theme colors."""
        self.assertEqual(self.theme.get_color("window_bg"), "#EEEEEE")
        self.assertEqual(self.theme.get_color("text_primary"), "#000000")
    
    def test_classic_fonts(self):
        """Test classic fonts (Arial instead of Segoe UI)."""
        header_font = self.theme.get_font("header")
        self.assertEqual(header_font["family"], "Arial")
        self.assertEqual(header_font["size"], 11)
    
    def test_classic_spacing(self):
        """Test classic spacing (smaller values)."""
        self.assertEqual(self.theme.get_spacing("window_padding"), 5)
        self.assertEqual(self.theme.get_spacing("row_height"), 20)


class TestThemeRegistry(unittest.TestCase):
    """Test the theme registry and factory functions."""
    
    def test_available_themes(self):
        """Test that all themes are registered."""
        expected_themes = ["material_dark", "material_light", "classic"]
        self.assertEqual(set(AVAILABLE_THEMES.keys()), set(expected_themes))
    
    def test_get_theme_valid(self):
        """Test getting valid themes."""
        dark_theme = get_theme("material_dark")
        self.assertIsInstance(dark_theme, MaterialDarkTheme)
        
        light_theme = get_theme("material_light")
        self.assertIsInstance(light_theme, MaterialLightTheme)
        
        classic_theme = get_theme("classic")
        self.assertIsInstance(classic_theme, ClassicTheme)
    
    def test_get_theme_invalid(self):
        """Test getting invalid theme returns default."""
        theme = get_theme("nonexistent_theme")
        self.assertIsInstance(theme, MaterialDarkTheme)
    
    def test_get_theme_default(self):
        """Test default theme."""
        theme = get_theme()
        self.assertIsInstance(theme, MaterialDarkTheme)


class TestStatColorFunction(unittest.TestCase):
    """Test the get_stat_color function."""
    
    def setUp(self):
        """Set up theme for testing."""
        self.theme = MaterialDarkTheme()
    
    def test_vpip_colors(self):
        """Test VPIP color classification."""
        # Low VPIP (tight)
        color = get_stat_color(self.theme, "vpip", 15.0)
        self.assertEqual(color, self.theme.get_color("stat_low"))
        
        # Medium VPIP
        color = get_stat_color(self.theme, "vpip", 28.0)
        self.assertEqual(color, self.theme.get_color("stat_medium"))
        
        # High VPIP (loose)
        color = get_stat_color(self.theme, "vpip", 45.0)
        self.assertEqual(color, self.theme.get_color("stat_high"))
    
    def test_pfr_colors(self):
        """Test PFR color classification."""
        # Low PFR (passive)
        color = get_stat_color(self.theme, "pfr", 10.0)
        self.assertEqual(color, self.theme.get_color("stat_low"))
        
        # High PFR (aggressive)
        color = get_stat_color(self.theme, "pfr", 30.0)
        self.assertEqual(color, self.theme.get_color("stat_high"))
    
    def test_three_bet_colors(self):
        """Test 3-bet color classification."""
        # Low 3-bet
        color = get_stat_color(self.theme, "three_B", 2.0)
        self.assertEqual(color, self.theme.get_color("stat_low"))
        
        # High 3-bet
        color = get_stat_color(self.theme, "three_B", 12.0)
        self.assertEqual(color, self.theme.get_color("stat_high"))
    
    def test_unknown_stat(self):
        """Test unknown stat returns neutral color."""
        color = get_stat_color(self.theme, "unknown_stat", 50.0)
        self.assertEqual(color, self.theme.get_color("stat_neutral"))
    
    def test_custom_thresholds(self):
        """Test custom thresholds."""
        custom_thresholds = {
            "custom_stat": {"low": 10, "high": 30}
        }
        
        # Low value
        color = get_stat_color(self.theme, "custom_stat", 5.0, custom_thresholds)
        self.assertEqual(color, self.theme.get_color("stat_low"))
        
        # Medium value
        color = get_stat_color(self.theme, "custom_stat", 20.0, custom_thresholds)
        self.assertEqual(color, self.theme.get_color("stat_medium"))
        
        # High value
        color = get_stat_color(self.theme, "custom_stat", 40.0, custom_thresholds)
        self.assertEqual(color, self.theme.get_color("stat_high"))
    
    def test_edge_values(self):
        """Test edge values at thresholds."""
        # Just below low threshold
        color = get_stat_color(self.theme, "vpip", 19.9)
        self.assertEqual(color, self.theme.get_color("stat_low"))
        
        # Just above high threshold
        color = get_stat_color(self.theme, "vpip", 35.1)
        self.assertEqual(color, self.theme.get_color("stat_high"))
        
        # Exactly at thresholds should be medium
        color = get_stat_color(self.theme, "vpip", 20.0)
        self.assertEqual(color, self.theme.get_color("stat_medium"))
        
        color = get_stat_color(self.theme, "vpip", 35.0)
        self.assertEqual(color, self.theme.get_color("stat_medium"))


class TestThemeConsistency(unittest.TestCase):
    """Test theme consistency and completeness."""
    
    def test_all_themes_have_required_colors(self):
        """Test that all themes have required color keys."""
        required_colors = [
            "window_bg", "header_bg", "section_bg", "text_primary", 
            "stat_high", "stat_medium", "stat_low", "stat_neutral"
        ]
        
        for theme_name in AVAILABLE_THEMES:
            theme = get_theme(theme_name)
            for color_key in required_colors:
                self.assertIn(color_key, theme.colors, 
                    f"Theme {theme_name} missing color {color_key}")
    
    def test_all_themes_have_required_fonts(self):
        """Test that all themes have required font keys."""
        required_fonts = [
            "header", "section_title", "stat_name", "stat_value"
        ]
        
        for theme_name in AVAILABLE_THEMES:
            theme = get_theme(theme_name)
            for font_key in required_fonts:
                self.assertIn(font_key, theme.fonts,
                    f"Theme {theme_name} missing font {font_key}")
    
    def test_all_themes_have_required_spacing(self):
        """Test that all themes have required spacing keys."""
        required_spacing = [
            "window_padding", "section_spacing", "row_height", "icon_size"
        ]
        
        for theme_name in AVAILABLE_THEMES:
            theme = get_theme(theme_name)
            for spacing_key in required_spacing:
                self.assertIn(spacing_key, theme.spacing,
                    f"Theme {theme_name} missing spacing {spacing_key}")
    
    def test_color_values_format(self):
        """Test that color values are valid hex colors."""
        import re
        hex_pattern = re.compile(r'^#[0-9A-Fa-f]{6}$')
        
        for theme_name in AVAILABLE_THEMES:
            theme = get_theme(theme_name)
            for color_key, color_value in theme.colors.items():
                self.assertIsInstance(color_value, str,
                    f"Color {color_key} in {theme_name} is not a string")
                self.assertTrue(hex_pattern.match(color_value),
                    f"Color {color_key} in {theme_name} is not valid hex: {color_value}")
    
    def test_font_values_format(self):
        """Test that font values have required properties."""
        for theme_name in AVAILABLE_THEMES:
            theme = get_theme(theme_name)
            for font_key, font_value in theme.fonts.items():
                self.assertIsInstance(font_value, dict,
                    f"Font {font_key} in {theme_name} is not a dict")
                self.assertIn("family", font_value,
                    f"Font {font_key} in {theme_name} missing family")
                self.assertIn("size", font_value,
                    f"Font {font_key} in {theme_name} missing size")
                self.assertIsInstance(font_value["size"], int,
                    f"Font {font_key} size in {theme_name} is not an integer")
    
    def test_spacing_values_format(self):
        """Test that spacing values are positive integers."""
        for theme_name in AVAILABLE_THEMES:
            theme = get_theme(theme_name)
            for spacing_key, spacing_value in theme.spacing.items():
                self.assertIsInstance(spacing_value, int,
                    f"Spacing {spacing_key} in {theme_name} is not an integer")
                self.assertGreater(spacing_value, 0,
                    f"Spacing {spacing_key} in {theme_name} is not positive")


if __name__ == '__main__':
    unittest.main()