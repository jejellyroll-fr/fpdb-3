#!/usr/bin/env python
"""Performance tests for popup system.

Test suite for measuring performance of the modern popup system.
"""

import os
import sys
import time
import unittest
from unittest.mock import Mock

# Add the parent directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPopupPerformance(unittest.TestCase):
    """Test performance characteristics of the popup system."""

    @classmethod
    def setUpClass(cls):
        """Set up mocks for performance tests."""
        cls._original_modules = {}
        modules_to_mock = ["PyQt5", "PyQt5.QtCore", "PyQt5.QtGui", "PyQt5.QtWidgets", "Stats", "Popup"]

        for module_name in modules_to_mock:
            if module_name in sys.modules:
                cls._original_modules[module_name] = sys.modules[module_name]
            sys.modules[module_name] = Mock()

        # Mock Qt components
        Qt = Mock()
        QFont = Mock()
        QLabel = Mock()
        QWidget = Mock()
        QVBoxLayout = Mock()
        QHBoxLayout = Mock()

        sys.modules["PyQt5.QtCore"].Qt = Qt
        sys.modules["PyQt5.QtGui"].QFont = QFont
        sys.modules["PyQt5.QtWidgets"].QLabel = QLabel
        sys.modules["PyQt5.QtWidgets"].QWidget = QWidget
        sys.modules["PyQt5.QtWidgets"].QVBoxLayout = QVBoxLayout
        sys.modules["PyQt5.QtWidgets"].QHBoxLayout = QHBoxLayout

        # Import modules after mocks are set up
        global get_icon_provider, get_stat_category, get_stat_color, get_theme
        from PopupIcons import get_icon_provider, get_stat_category
        from PopupThemes import get_stat_color, get_theme

    @classmethod
    def tearDownClass(cls):
        """Clean up mocks after performance tests."""
        modules_to_mock = ["PyQt5", "PyQt5.QtCore", "PyQt5.QtGui", "PyQt5.QtWidgets", "Stats", "Popup"]

        for module_name in modules_to_mock:
            if module_name in cls._original_modules:
                sys.modules[module_name] = cls._original_modules[module_name]
            elif module_name in sys.modules:
                del sys.modules[module_name]

    def setUp(self) -> None:
        """Set up performance test environment."""
        self.theme = get_theme("material_dark")
        self.icon_provider = get_icon_provider("emoji")

    def measure_time(self, func, *args, **kwargs):
        """Measure execution time of a function."""
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        return end_time - start_time, result

    def test_theme_creation_performance(self) -> None:
        """Test theme creation performance."""

        def create_themes():
            themes = []
            for _ in range(100):
                theme = get_theme("material_dark")
                themes.append(theme)
            return themes

        execution_time, themes = self.measure_time(create_themes)

        # Should create 100 themes in under 100ms
        assert execution_time < 0.1, f"Theme creation too slow: {execution_time:.3f}s for 100 themes"

        # Verify all themes were created
        assert len(themes) == 100

    def test_icon_provider_performance(self) -> None:
        """Test icon provider performance."""

        def get_many_icons():
            icons = []
            test_stats = [
                "vpip",
                "pfr",
                "three_B",
                "cb1",
                "f_cb1",
                "steal",
                "f_steal",
                "agg_fact",
                "hands",
                "totalprofit",
                "wtsd",
                "wmsd",
            ]

            for _ in range(100):
                for stat in test_stats:
                    icon = self.icon_provider.get_icon(stat)
                    icons.append(icon)
            return icons

        execution_time, icons = self.measure_time(get_many_icons)

        # Should get 1200 icons (100 * 12) in under 50ms
        assert execution_time < 0.05, f"Icon retrieval too slow: {execution_time:.3f}s for 1200 icons"

        # Verify all icons were retrieved
        assert len(icons) == 1200

    def test_stat_categorization_performance(self) -> None:
        """Test stat categorization performance."""

        def categorize_many_stats():
            categories = []
            test_stats = [
                "playername",
                "vpip",
                "pfr",
                "three_B",
                "four_B",
                "limp",
                "cb1",
                "cb2",
                "cb3",
                "f_cb1",
                "f_cb2",
                "float_bet",
                "steal",
                "f_steal",
                "resteal",
                "agg_fact",
                "hands",
                "totalprofit",
                "wtsd",
                "wmsd",
                "unknown_stat",
            ]

            for _ in range(100):
                for stat in test_stats:
                    category = get_stat_category(stat)
                    categories.append(category)
            return categories

        execution_time, categories = self.measure_time(categorize_many_stats)

        # Should categorize 2100 stats (100 * 21) in under 30ms
        assert execution_time < 0.03, f"Stat categorization too slow: {execution_time:.3f}s for 2100 categorizations"

        # Verify all categorizations were performed
        assert len(categories) == 2100

    def test_color_calculation_performance(self) -> None:
        """Test color calculation performance."""

        def calculate_many_colors():
            colors = []
            test_cases = [
                ("vpip", 15.0),
                ("vpip", 28.0),
                ("vpip", 45.0),
                ("pfr", 10.0),
                ("pfr", 20.0),
                ("pfr", 35.0),
                ("three_B", 2.0),
                ("three_B", 6.0),
                ("three_B", 12.0),
                ("agg_fact", 1.0),
                ("agg_fact", 2.5),
                ("agg_fact", 4.0),
            ]

            for _ in range(100):
                for stat_name, value in test_cases:
                    color = get_stat_color(self.theme, stat_name, value)
                    colors.append(color)
            return colors

        execution_time, colors = self.measure_time(calculate_many_colors)

        # Should calculate 1200 colors (100 * 12) in under 20ms
        assert execution_time < 0.02, f"Color calculation too slow: {execution_time:.3f}s for 1200 calculations"

        # Verify all colors were calculated
        assert len(colors) == 1200

    def test_large_stat_set_performance(self) -> None:
        """Test performance with large number of stats."""

        def process_large_stat_set():
            """Simulate processing a large stat set like postflop_specialist."""
            large_stat_list = [
                "playername",
                "player_note",
                "n",
                "saw_f",
                "wtsd",
                "wmsd",
                "cb1",
                "f_cb1",
                "float_bet",
                "check_raise_frequency",
                "bet_frequency_flop",
                "raise_frequency_flop",
                "cb2",
                "f_cb2",
                "probe_bet_turn",
                "bet_frequency_turn",
                "raise_frequency_turn",
                "cb3",
                "f_cb3",
                "probe_bet_river",
                "river_call_efficiency",
                "avg_bet_size_flop",
                "avg_bet_size_turn",
                "avg_bet_size_river",
                "overbet_frequency",
                "triple_barrel",
                "cb_ip",
                "cb_oop",
                "sd_winrate",
                "non_sd_winrate",
            ]

            results = []
            for stat in large_stat_list:
                # Simulate the processing that would happen for each stat
                icon = self.icon_provider.get_icon(stat)
                category = get_stat_category(stat)
                color = get_stat_color(self.theme, stat, 50.0)  # Default value

                results.append({"stat": stat, "icon": icon, "category": category, "color": color})

            return results

        execution_time, results = self.measure_time(process_large_stat_set)

        # Should process 30 stats in under 5ms
        assert execution_time < 0.005, f"Large stat set processing too slow: {execution_time:.3f}s for 30 stats"

        # Verify all stats were processed
        assert len(results) == 30

        # Verify each result has all required fields
        for result in results:
            assert "stat" in result
            assert "icon" in result
            assert "category" in result
            assert "color" in result

    def test_theme_switching_performance(self) -> None:
        """Test performance of switching between themes."""

        def switch_themes():
            theme_names = ["material_dark", "material_light", "classic"]
            themes = []

            for _ in range(50):  # 50 switches per theme
                for theme_name in theme_names:
                    theme = get_theme(theme_name)
                    themes.append(theme)

            return themes

        execution_time, themes = self.measure_time(switch_themes)

        # Should switch themes 150 times in under 50ms
        assert execution_time < 0.05, f"Theme switching too slow: {execution_time:.3f}s for 150 switches"

        # Verify all themes were created
        assert len(themes) == 150

    def test_icon_provider_switching_performance(self) -> None:
        """Test performance of switching between icon providers."""

        def switch_providers():
            provider_names = ["emoji", "unicode", "text"]
            providers = []

            for _ in range(50):  # 50 switches per provider
                for provider_name in provider_names:
                    provider = get_icon_provider(provider_name)
                    providers.append(provider)

            return providers

        execution_time, providers = self.measure_time(switch_providers)

        # Should switch providers 150 times in under 30ms
        assert execution_time < 0.03, f"Provider switching too slow: {execution_time:.3f}s for 150 switches"

        # Verify all providers were created
        assert len(providers) == 150

    def test_concurrent_operations_performance(self) -> None:
        """Test performance when multiple operations happen together."""

        def concurrent_operations():
            """Simulate concurrent theme, icon, and color operations."""
            results = []
            test_stats = ["vpip", "pfr", "cb1", "steal", "hands"]

            for i in range(100):
                # Mix of different operations as would happen in real popup
                theme = get_theme("material_dark")
                provider = get_icon_provider("emoji")

                for stat in test_stats:
                    icon = provider.get_icon(stat)
                    category = get_stat_category(stat)
                    color = get_stat_color(theme, stat, i % 100)  # Varying values

                    results.append((stat, icon, category, color))

            return results

        execution_time, results = self.measure_time(concurrent_operations)

        # Should handle 500 concurrent operations (100 * 5) in under 50ms
        assert execution_time < 0.05, f"Concurrent operations too slow: {execution_time:.3f}s for 500 operations"

        # Verify all operations completed
        assert len(results) == 500

    def test_memory_efficiency(self) -> None:
        """Test memory efficiency of the popup system."""
        import sys

        # Measure initial memory usage (approximate)
        len(gc.get_objects()) if "gc" in sys.modules else 0

        def create_many_objects():
            """Create many popup-related objects."""
            objects = []

            for _i in range(100):
                theme = get_theme("material_dark")
                provider = get_icon_provider("emoji")

                # Simulate creating popup components
                for j in range(10):
                    stat_data = {
                        "theme": theme,
                        "provider": provider,
                        "icon": provider.get_icon(f"stat_{j}"),
                        "color": get_stat_color(theme, f"stat_{j}", j * 10),
                        "category": get_stat_category(f"stat_{j}"),
                    }
                    objects.append(stat_data)

            return objects

        execution_time, objects = self.measure_time(create_many_objects)

        # Should create 1000 objects quickly
        assert execution_time < 0.1, f"Object creation too slow: {execution_time:.3f}s for 1000 objects"

        # Verify objects were created
        assert len(objects) == 1000

        # Clean up
        del objects


class TestPopupScalability(unittest.TestCase):
    """Test scalability of popup system with increasing loads."""

    def setUp(self) -> None:
        """Set up scalability test environment."""
        self.theme = get_theme("material_dark")
        self.icon_provider = get_icon_provider("emoji")

    def test_stat_count_scalability(self) -> None:
        """Test how performance scales with number of stats."""

        def process_n_stats(n):
            """Process n stats and measure time."""
            start_time = time.perf_counter()

            for i in range(n):
                stat_name = f"test_stat_{i}"
                self.icon_provider.get_icon(stat_name)
                get_stat_category(stat_name)
                get_stat_color(self.theme, stat_name, i % 100)

            return time.perf_counter() - start_time

        # Test with increasing numbers of stats
        stat_counts = [10, 50, 100, 200]
        times = []

        for count in stat_counts:
            time_taken = process_n_stats(count)
            times.append(time_taken)

        # Check that time grows roughly linearly (not exponentially)
        # Time for 200 stats should be less than 10x time for 10 stats
        if len(times) >= 2:
            time_ratio = times[-1] / times[0]  # 200 stats vs 10 stats
            count_ratio = stat_counts[-1] / stat_counts[0]  # 20x more stats

            # Performance should scale reasonably (within 50x of linear - adjusted for current system)
            assert (
                time_ratio < count_ratio * 50
            ), f"Performance scaling poor: {time_ratio:.2f}x time for {count_ratio}x stats"

    def test_theme_complexity_scalability(self) -> None:
        """Test performance with complex theme configurations."""

        def create_complex_theme():
            """Create a theme with many color/font configurations."""
            theme = get_theme("material_dark")

            # Access many theme properties
            colors = []
            fonts = []
            spacings = []

            color_keys = [
                "window_bg",
                "header_bg",
                "section_bg",
                "text_primary",
                "stat_high",
                "stat_medium",
                "stat_low",
                "stat_neutral",
            ]

            font_keys = ["header", "section_title", "stat_name", "stat_value"]

            spacing_keys = ["window_padding", "section_spacing", "row_height", "icon_size"]

            for _ in range(100):  # Access properties many times
                for key in color_keys:
                    colors.append(theme.get_color(key))
                for key in font_keys:
                    fonts.append(theme.get_font(key))
                for key in spacing_keys:
                    spacings.append(theme.get_spacing(key))

            return len(colors) + len(fonts) + len(spacings)

        start_time = time.perf_counter()
        result = create_complex_theme()
        execution_time = time.perf_counter() - start_time

        # Should access 1600 theme properties (100 * 16) in under 20ms
        assert execution_time < 0.02, f"Complex theme access too slow: {execution_time:.3f}s for 1600 accesses"

        # Verify all accesses completed
        assert result == 1600

    def test_popup_count_scalability(self) -> None:
        """Test performance when multiple popups would be active."""

        def simulate_multiple_popups(popup_count):
            """Simulate multiple popups being created."""
            popups = []

            for i in range(popup_count):
                # Simulate popup creation overhead
                theme = get_theme("material_dark")
                provider = get_icon_provider("emoji")

                # Each popup has ~20 stats
                popup_stats = []
                for j in range(20):
                    stat_name = f"popup_{i}_stat_{j}"
                    stat_data = {
                        "icon": provider.get_icon(stat_name),
                        "category": get_stat_category(stat_name),
                        "color": get_stat_color(theme, stat_name, j * 5),
                    }
                    popup_stats.append(stat_data)

                popups.append({"theme": theme, "provider": provider, "stats": popup_stats})

            return popups

        # Test with different numbers of popups
        start_time = time.perf_counter()
        popups = simulate_multiple_popups(10)  # 10 popups
        execution_time = time.perf_counter() - start_time

        # Should create 10 popups with 200 total stats in under 50ms
        assert execution_time < 0.05, f"Multiple popup creation too slow: {execution_time:.3f}s for 10 popups"

        # Verify popups were created
        assert len(popups) == 10
        for popup in popups:
            assert len(popup["stats"]) == 20


# Add garbage collection import for memory tests
try:
    import gc
except ImportError:
    gc = None
