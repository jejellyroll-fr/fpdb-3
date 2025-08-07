#!/usr/bin/env python
"""Tests for ModernPopup.py.

Integration test suite for the modern popup system.
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch

# Add the parent directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock PyQt5 to avoid GUI dependencies in tests
sys.modules["PyQt5"] = Mock()
sys.modules["PyQt5.QtCore"] = Mock()
sys.modules["PyQt5.QtGui"] = Mock()
sys.modules["PyQt5.QtWidgets"] = Mock()

# Import Qt classes and set up mocks
from unittest.mock import Mock

Qt = Mock()
Qt.AlignCenter = 1
Qt.AlignRight = 2
Qt.ScrollBarAsNeeded = 1
Qt.ScrollBarNever = 2

QFont = Mock()
QLabel = Mock()
QWidget = Mock()
QVBoxLayout = Mock()
QHBoxLayout = Mock()
QGridLayout = Mock()
QScrollArea = Mock()
QPushButton = Mock()
QFrame = Mock()

# Mock the Qt imports
sys.modules["PyQt5.QtCore"].Qt = Qt
sys.modules["PyQt5.QtGui"].QFont = QFont
sys.modules["PyQt5.QtWidgets"].QLabel = QLabel
sys.modules["PyQt5.QtWidgets"].QWidget = QWidget
sys.modules["PyQt5.QtWidgets"].QVBoxLayout = QVBoxLayout
sys.modules["PyQt5.QtWidgets"].QHBoxLayout = QHBoxLayout
sys.modules["PyQt5.QtWidgets"].QGridLayout = QGridLayout
sys.modules["PyQt5.QtWidgets"].QScrollArea = QScrollArea
sys.modules["PyQt5.QtWidgets"].QPushButton = QPushButton
sys.modules["PyQt5.QtWidgets"].QFrame = QFrame

# Mock Stats module
Stats = Mock()
Stats.do_stat = Mock()
Stats.do_tip = Mock()
sys.modules["Stats"] = Stats

# Mock Popup module
Popup = Mock()
Popup.Popup = Mock()
sys.modules["Popup"] = Popup

# Now import our modules
from ModernPopup import (
    MODERN_POPUP_CLASSES,
    ModernSectionWidget,
    ModernStatRow,
    ModernSubmenu,
    ModernSubmenuClassic,
    ModernSubmenuLight,
)
from PopupIcons import EmojiIconProvider, TextIconProvider
from PopupThemes import ClassicTheme, MaterialDarkTheme, MaterialLightTheme


class TestModernStatRow(unittest.TestCase):
    """Test the ModernStatRow widget."""

    def setUp(self) -> None:
        """Set up test environment."""
        self.theme = MaterialDarkTheme()
        self.icon_provider = EmojiIconProvider()
        self.stat_data = ("vpip", "23.4", "23.4%", "VPIP 23.4%", "details", "tooltip")

        with patch("ModernPopup.QHBoxLayout"), patch("ModernPopup.QLabel"), patch("ModernPopup.QWidget.__init__"):
            self.row = ModernStatRow("vpip", self.stat_data, self.theme, self.icon_provider)

    def test_initialization(self) -> None:
        """Test ModernStatRow initialization."""
        assert self.row.stat_name == "vpip"
        assert self.row.stat_data == self.stat_data
        assert self.row.theme == self.theme
        assert self.row.icon_provider == self.icon_provider

    def test_icon_assignment(self) -> None:
        """Test that correct icon is assigned."""
        self.icon_provider.get_icon("vpip")
        # The icon_label should be created and assigned in setup_ui
        assert self.row.icon_label is not None

    def test_stat_data_handling(self) -> None:
        """Test handling of stat data."""
        # Test with valid stat data
        assert self.row.name_label is not None
        assert self.row.value_label is not None

        # Test with None stat data
        with patch("ModernPopup.QHBoxLayout"), patch("ModernPopup.QLabel"), patch("ModernPopup.QWidget.__init__"):
            row_none = ModernStatRow("test", None, self.theme, self.icon_provider)
            assert row_none.name_label is not None
            assert row_none.value_label is not None


class TestModernSectionWidget(unittest.TestCase):
    """Test the ModernSectionWidget."""

    def setUp(self) -> None:
        """Set up test environment."""
        self.theme = MaterialDarkTheme()
        self.icon_provider = EmojiIconProvider()

        with (
            patch("ModernPopup.QVBoxLayout"),
            patch("ModernPopup.QHBoxLayout"),
            patch("ModernPopup.QLabel"),
            patch("ModernPopup.QWidget"),
            patch("ModernPopup.QFrame.__init__"),
        ):
            self.section = ModernSectionWidget("preflop", self.theme, self.icon_provider)

    def test_initialization(self) -> None:
        """Test ModernSectionWidget initialization."""
        assert self.section.section_name == "preflop"
        assert self.section.theme == self.theme
        assert self.section.icon_provider == self.icon_provider
        assert self.section.stat_rows == []

    def test_section_header(self) -> None:
        """Test section header creation."""
        assert self.section.header_icon is not None
        assert self.section.header_label is not None
        assert self.section.header_widget is not None

    def test_add_stat_row(self) -> None:
        """Test adding stat rows to section."""
        stat_data = ("vpip", "23.4", "23.4%", "VPIP 23.4%", "details", "tooltip")

        with patch("ModernPopup.ModernStatRow") as mock_row:
            self.section.add_stat_row("vpip", stat_data)

            # Check that a ModernStatRow was created
            mock_row.assert_called_once_with("vpip", stat_data, self.theme, self.icon_provider)

            # Check that it was added to stat_rows list
            assert len(self.section.stat_rows) == 1


class TestModernSubmenu(unittest.TestCase):
    """Test the ModernSubmenu popup."""

    def setUp(self) -> None:
        """Set up test environment."""
        # Mock the popup configuration
        self.mock_pop = Mock()
        self.mock_pop.pu_stats = [("playername", None), ("vpip", None), ("pfr", None)]
        self.mock_pop.pu_stats_submenu = [("playername", None), ("vpip", None), ("pfr", None)]

        # Mock stat_dict with player data
        self.stat_dict = {1: {"seat": 2, "screen_name": "TestPlayer", "hands": 100}}

        # Mock hand_instance
        self.hand_instance = Mock()

        with (
            patch("ModernPopup.Popup.__init__"),
            patch("ModernPopup.MaterialDarkTheme") as mock_theme,
            patch("ModernPopup.EmojiIconProvider") as mock_icons,
        ):
            # Create ModernSubmenu instance
            self.popup = ModernSubmenu()
            self.popup.pop = self.mock_pop
            self.popup.stat_dict = self.stat_dict
            self.popup.seat = 2
            self.popup.hand_instance = self.hand_instance

            # Set up mocks
            mock_theme.return_value = MaterialDarkTheme()
            mock_icons.return_value = EmojiIconProvider()

    def test_initialization(self) -> None:
        """Test ModernSubmenu initialization."""
        assert self.popup.theme_name == "material_dark"
        assert self.popup.icon_provider_name == "emoji"
        assert self.popup.sections is not None

    def test_theme_selection(self) -> None:
        """Test theme selection via kwargs."""
        with patch("ModernPopup.Popup.__init__"), patch("ModernPopup.ClassicTheme"):
            popup_classic = ModernSubmenu(theme="classic")
            assert popup_classic.theme_name == "classic"

    def test_icon_provider_selection(self) -> None:
        """Test icon provider selection via kwargs."""
        with patch("ModernPopup.Popup.__init__"), patch("ModernPopup.TextIconProvider"):
            popup_text = ModernSubmenu(icon_provider="text")
            assert popup_text.icon_provider_name == "text"

    @patch("ModernPopup.Stats.do_stat")
    def test_create_content(self, mock_do_stat) -> None:
        """Test content creation."""
        # Mock Stats.do_stat to return test data
        mock_do_stat.return_value = ("vpip", "23.4", "23.4%", "VPIP 23.4%", "details", "tooltip")

        with (
            patch.object(self.popup, "setup_window_style"),
            patch.object(self.popup, "create_header"),
            patch.object(self.popup, "create_content") as mock_create_content,
            patch.object(self.popup, "destroy_pop"),
        ):
            self.popup.create()

            # Verify that create_content was called
            mock_create_content.assert_called_once()

    def test_player_id_discovery(self) -> None:
        """Test finding player ID from seat."""
        # The create method should find player_id = 1 for seat = 2
        with (
            patch.object(self.popup, "setup_window_style"),
            patch.object(self.popup, "create_header"),
            patch.object(self.popup, "create_content"),
            patch.object(self.popup, "destroy_pop") as mock_destroy,
        ):
            self.popup.create()

            # Should not call destroy_pop since player was found
            mock_destroy.assert_not_called()

    def test_no_player_found(self) -> None:
        """Test behavior when no player is found for seat."""
        # Modify stat_dict so no player matches the seat
        self.popup.stat_dict = {1: {"seat": 999}}

        with patch.object(self.popup, "destroy_pop") as mock_destroy:
            self.popup.create()

            # Should call destroy_pop since no player found
            mock_destroy.assert_called_once()

    def test_no_stats_to_display(self) -> None:
        """Test behavior when no stats are configured."""
        self.popup.pop.pu_stats = []

        with patch.object(self.popup, "destroy_pop") as mock_destroy:
            self.popup.create()

            # Should call destroy_pop since no stats to show
            mock_destroy.assert_called_once()


class TestModernSubmenuVariants(unittest.TestCase):
    """Test the ModernSubmenu variants."""

    def test_modern_submenu_light(self) -> None:
        """Test ModernSubmenuLight uses light theme."""
        with patch("ModernPopup.Popup.__init__"):
            popup = ModernSubmenuLight()
            assert popup.theme_name == "material_light"

    def test_modern_submenu_classic(self) -> None:
        """Test ModernSubmenuClassic uses classic theme and text icons."""
        with patch("ModernPopup.Popup.__init__"):
            popup = ModernSubmenuClassic()
            assert popup.theme_name == "classic"
            assert popup.icon_provider_name == "text"

    def test_kwargs_override(self) -> None:
        """Test that explicit kwargs override variant defaults."""
        with patch("ModernPopup.Popup.__init__"):
            # Light variant with dark theme override
            popup_light = ModernSubmenuLight(theme="material_dark")
            assert popup_light.theme_name == "material_dark"

            # Classic variant with emoji icons override
            popup_classic = ModernSubmenuClassic(icon_provider="emoji")
            assert popup_classic.icon_provider_name == "emoji"


class TestModernPopupClasses(unittest.TestCase):
    """Test the MODERN_POPUP_CLASSES registry."""

    def test_all_classes_registered(self) -> None:
        """Test that all modern popup classes are registered."""
        expected_classes = ["ModernSubmenu", "ModernSubmenuLight", "ModernSubmenuClassic"]

        assert set(MODERN_POPUP_CLASSES.keys()) == set(expected_classes)

    def test_registered_classes_are_classes(self) -> None:
        """Test that registered items are actually classes."""
        for class_name, class_obj in MODERN_POPUP_CLASSES.items():
            assert callable(class_obj), f"{class_name} should be a callable class"


class TestPopupIntegration(unittest.TestCase):
    """Test integration between popup components."""

    def setUp(self) -> None:
        """Set up integration test environment."""
        self.theme = MaterialDarkTheme()
        self.icon_provider = EmojiIconProvider()

    def test_theme_icon_provider_compatibility(self) -> None:
        """Test that themes and icon providers work together."""
        # Test all theme/provider combinations
        themes = [MaterialDarkTheme(), MaterialLightTheme(), ClassicTheme()]
        providers = [EmojiIconProvider(), TextIconProvider()]

        for theme in themes:
            for provider in providers:
                # Should be able to create a stat row with any combination
                with (
                    patch("ModernPopup.QHBoxLayout"),
                    patch("ModernPopup.QLabel"),
                    patch("ModernPopup.QWidget.__init__"),
                ):
                    stat_data = ("vpip", "23.4", "23.4%", "VPIP", "details", "tooltip")
                    row = ModernStatRow("vpip", stat_data, theme, provider)

                    assert row is not None
                    assert row.theme == theme
                    assert row.icon_provider == provider

    def test_stat_categorization_integration(self) -> None:
        """Test that stat categorization works with section creation."""
        from PopupIcons import get_stat_category

        # Test stats from different categories
        test_stats = [
            ("playername", "player_info"),
            ("vpip", "preflop"),
            ("cb1", "flop"),
            ("steal", "steal"),
            ("agg_fact", "aggression"),
            ("hands", "general"),
        ]

        for stat_name, expected_category in test_stats:
            category = get_stat_category(stat_name)
            assert category == expected_category, f"Stat {stat_name} should be in category {expected_category}"

    def test_color_calculation_integration(self) -> None:
        """Test color calculation with different stat values."""
        from PopupThemes import get_stat_color

        theme = MaterialDarkTheme()

        # Test VPIP color ranges
        test_cases = [
            ("vpip", 15.0, "stat_low"),  # Tight
            ("vpip", 28.0, "stat_medium"),  # Medium
            ("vpip", 45.0, "stat_high"),  # Loose
            ("pfr", 10.0, "stat_low"),  # Passive
            ("pfr", 30.0, "stat_high"),  # Aggressive
        ]

        for stat_name, value, expected_color_key in test_cases:
            color = get_stat_color(theme, stat_name, value)
            expected_color = theme.get_color(expected_color_key)
            assert color == expected_color, f"Stat {stat_name} with value {value} should have {expected_color_key} color"


class TestErrorHandling(unittest.TestCase):
    """Test error handling in popup components."""

    def test_invalid_stat_data(self) -> None:
        """Test handling of invalid stat data."""
        theme = MaterialDarkTheme()
        icon_provider = EmojiIconProvider()

        # Test with various invalid stat data
        invalid_data_sets = [
            None,
            (),
            ("single_element",),
            ("one", "two"),  # Too few elements
        ]

        for invalid_data in invalid_data_sets:
            with patch("ModernPopup.QHBoxLayout"), patch("ModernPopup.QLabel"), patch("ModernPopup.QWidget.__init__"):
                # Should not raise exception
                try:
                    row = ModernStatRow("test_stat", invalid_data, theme, icon_provider)
                    assert row is not None
                except Exception as e:
                    self.fail(f"ModernStatRow should handle invalid data gracefully: {e}")

    def test_missing_stat_dict_player(self) -> None:
        """Test handling when stat_dict doesn't contain expected player."""
        with (
            patch("ModernPopup.Popup.__init__"),
            patch("ModernPopup.MaterialDarkTheme"),
            patch("ModernPopup.EmojiIconProvider"),
        ):
            popup = ModernSubmenu()
            popup.stat_dict = {}  # Empty stat_dict
            popup.seat = 2
            popup.pop = Mock()
            popup.pop.pu_stats = [("vpip", None)]

            with patch.object(popup, "destroy_pop") as mock_destroy:
                popup.create()

                # Should call destroy_pop when no player found
                mock_destroy.assert_called_once()

    def test_stats_do_stat_returns_none(self) -> None:
        """Test handling when Stats.do_stat returns None."""
        with patch("ModernPopup.Stats.do_stat", return_value=None):
            theme = MaterialDarkTheme()
            icon_provider = EmojiIconProvider()

            with patch("ModernPopup.QHBoxLayout"), patch("ModernPopup.QLabel"), patch("ModernPopup.QWidget.__init__"):
                # Should handle None stat data gracefully
                row = ModernStatRow("vpip", None, theme, icon_provider)
                assert row is not None


class TestPerformanceConsiderations(unittest.TestCase):
    """Test performance-related aspects."""

    def test_large_number_of_stats(self) -> None:
        """Test handling of large number of stats."""
        theme = MaterialDarkTheme()
        icon_provider = EmojiIconProvider()

        with (
            patch("ModernPopup.QVBoxLayout"),
            patch("ModernPopup.QHBoxLayout"),
            patch("ModernPopup.QLabel"),
            patch("ModernPopup.QWidget"),
            patch("ModernPopup.QFrame.__init__"),
        ):
            section = ModernSectionWidget("test", theme, icon_provider)

            # Add many stat rows
            stat_data = ("test", "value", "display", "tip", "details", "tooltip")

            for i in range(100):  # 100 stats
                with patch("ModernPopup.ModernStatRow"):
                    section.add_stat_row(f"stat_{i}", stat_data)

            assert len(section.stat_rows) == 100

    def test_theme_caching(self) -> None:
        """Test that themes can be reused efficiently."""
        # Create multiple components with same theme
        theme = MaterialDarkTheme()
        icon_provider = EmojiIconProvider()

        components = []
        for i in range(10):
            with (
                patch("ModernPopup.QVBoxLayout"),
                patch("ModernPopup.QHBoxLayout"),
                patch("ModernPopup.QLabel"),
                patch("ModernPopup.QWidget"),
                patch("ModernPopup.QFrame.__init__"),
            ):
                section = ModernSectionWidget(f"section_{i}", theme, icon_provider)
                components.append(section)

        # All components should reference the same theme object
        for component in components:
            assert component.theme is theme


if __name__ == "__main__":
    # Configure test runner to be less verbose
    unittest.main(verbosity=2)
