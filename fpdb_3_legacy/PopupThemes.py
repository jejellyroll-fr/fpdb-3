"""PopupThemes.py.
from __future__ import annotations
Themes and color schemes for modern popup windows.
"""

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("popup_themes")

FontSpec = dict[str, str | int]
StatThresholds = dict[str, dict[str, float]]


class PopupTheme:
    """Base class for popup themes."""

    #: Colours cycled through to tell consecutive sections apart. A theme that
    #: wants its own set overrides this; renderers must not hard-code one.
    section_accents: tuple[str, ...] = ("#03DAC6", "#BB86FC", "#FFB74D", "#4FC3F7", "#F06292")

    def __init__(self, name: str) -> None:
        self.name = name
        self.colors: dict[str, str] = {}
        self.fonts: dict[str, FontSpec] = {}
        self.spacing: dict[str, int] = {}

    #: Where to look when a theme predates a colour a renderer now asks for.
    #: Without this a new key falls through to white, which on a dark theme is
    #: a bright band the author never chose.
    _COLOR_FALLBACKS = {
        "text_muted": ("text_secondary", "text_primary"),
        "scrollbar_bg": ("header_bg", "window_bg"),
        "stat_neutral": ("text_primary",),
        "row_bg_odd": ("row_bg_even", "window_bg"),
    }

    def get_color(self, element: str) -> str:
        """Get color for a specific element."""
        if element in self.colors:
            return self.colors[element]
        for alias in self._COLOR_FALLBACKS.get(element, ()):
            if alias in self.colors:
                return self.colors[alias]
        return "#FFFFFF"

    def get_section_accent(self, index: int) -> str:
        """Accent colour for the section at ``index``, cycling as needed."""
        accents = self.section_accents or PopupTheme.section_accents
        return accents[index % len(accents)]

    def get_font(self, element: str) -> FontSpec:
        """Get font properties for a specific element."""
        return self.fonts.get(element, {"family": "Arial", "size": 10})

    def get_spacing(self, element: str) -> int:
        """Get spacing for a specific element."""
        return self.spacing.get(element, 5)


class MaterialDarkTheme(PopupTheme):
    """Material Design Dark theme."""

    def __init__(self) -> None:
        super().__init__("material_dark")

        self.colors = {
            # Background colors
            "window_bg": "#2E2E2E",
            "header_bg": "#424242",
            "section_bg": "#383838",
            "row_bg_even": "#2E2E2E",
            "row_bg_odd": "#343434",
            # Text colors
            "text_primary": "#FFFFFF",
            "text_secondary": "#B0B0B0",
            "text_accent": "#03DAC6",
            # Element colors
            "border": "#555555",
            "hover": "#4A4A4A",
            "selected": "#6200EE",
            # Status colors
            "stat_high": "#F44336",  # Red for high values
            "stat_medium": "#FF9800",  # Orange for medium
            "stat_low": "#4CAF50",  # Green for low values
            "stat_neutral": "#9E9E9E",  # Gray for neutral
            # Close button
            "close_bg": "#F44336",
            "close_text": "#FFFFFF",
        }

        self.fonts = {
            "header": {"family": "Segoe UI", "size": 12, "weight": "bold"},
            "section_title": {"family": "Segoe UI", "size": 10, "weight": "bold"},
            "stat_name": {"family": "Segoe UI", "size": 9, "weight": "normal"},
            "stat_value": {"family": "Segoe UI", "size": 9, "weight": "bold"},
            "close_button": {"family": "Segoe UI", "size": 10, "weight": "bold"},
        }

        self.spacing = {
            "window_padding": 8,
            "section_spacing": 6,
            "row_height": 24,
            "icon_size": 16,
            "border_radius": 4,
        }


class MaterialLightTheme(PopupTheme):
    """Material Design Light theme."""

    def __init__(self) -> None:
        super().__init__("material_light")

        self.colors = {
            # Background colors
            "window_bg": "#FAFAFA",
            "header_bg": "#F5F5F5",
            "section_bg": "#FFFFFF",
            "row_bg_even": "#FFFFFF",
            "row_bg_odd": "#F8F8F8",
            # Text colors
            "text_primary": "#212121",
            "text_secondary": "#757575",
            "text_accent": "#6200EE",
            # Element colors
            "border": "#E0E0E0",
            "hover": "#EEEEEE",
            "selected": "#E1F5FE",
            # Status colors
            "stat_high": "#D32F2F",
            "stat_medium": "#F57C00",
            "stat_low": "#388E3C",
            "stat_neutral": "#616161",
            # Close button
            "close_bg": "#D32F2F",
            "close_text": "#FFFFFF",
        }

        self.fonts = {
            "header": {"family": "Segoe UI", "size": 12, "weight": "bold"},
            "section_title": {"family": "Segoe UI", "size": 10, "weight": "bold"},
            "stat_name": {"family": "Segoe UI", "size": 9, "weight": "normal"},
            "stat_value": {"family": "Segoe UI", "size": 9, "weight": "bold"},
            "close_button": {"family": "Segoe UI", "size": 10, "weight": "bold"},
        }

        self.spacing = {
            "window_padding": 8,
            "section_spacing": 6,
            "row_height": 24,
            "icon_size": 16,
            "border_radius": 4,
        }


class ClassicTheme(PopupTheme):
    """Classic FPDB theme for compatibility."""

    def __init__(self) -> None:
        super().__init__("classic")

        self.colors = {
            "window_bg": "#EEEEEE",
            "header_bg": "#DDDDDD",
            "section_bg": "#FFFFFF",
            "row_bg_even": "#FFFFFF",
            "row_bg_odd": "#F0F0F0",
            "text_primary": "#000000",
            "text_secondary": "#666666",
            "text_accent": "#0066CC",
            "border": "#CCCCCC",
            "hover": "#E0E0E0",
            "selected": "#CCE5FF",
            "stat_high": "#CC0000",
            "stat_medium": "#FF6600",
            "stat_low": "#009900",
            "stat_neutral": "#666666",
            "close_bg": "#CC0000",
            "close_text": "#FFFFFF",
        }

        self.fonts = {
            "header": {"family": "Arial", "size": 11, "weight": "bold"},
            "section_title": {"family": "Arial", "size": 10, "weight": "bold"},
            "stat_name": {"family": "Arial", "size": 9, "weight": "normal"},
            "stat_value": {"family": "Arial", "size": 9, "weight": "normal"},
            "close_button": {"family": "Arial", "size": 9, "weight": "bold"},
        }

        self.spacing = {
            "window_padding": 5,
            "section_spacing": 4,
            "row_height": 20,
            "icon_size": 14,
            "border_radius": 2,
        }


class HudDarkTheme(PopupTheme):
    """Near-black, high-contrast theme for popups read over a poker table.

    The Material themes are built for a desktop window; a popup that opens on
    top of a lit table needs a darker surface and brighter values to stay
    legible. Nothing here is tied to a poker variant -- any profile can select
    it with ``pu_theme="hud_dark"``.
    """

    section_accents = ("#00B8F0", "#00E5A8", "#A78BFA", "#F5B942", "#FB7185")

    def __init__(self) -> None:
        super().__init__("hud_dark")
        self.colors = {
            "window_bg": "#020407",
            "header_bg": "#101A2E",
            "section_bg": "#111B30",
            "row_bg_even": "#020407",
            "row_bg_odd": "#070E1A",
            "text_primary": "#D7E0EA",
            "text_secondary": "#9AA9C1",
            "text_muted": "#63758F",
            "text_accent": "#16C5F4",
            "border": "#334155",
            "hover": "#152238",
            "selected": "#1E293B",
            "stat_high": "#FF6B7A",
            "stat_medium": "#F5B942",
            "stat_low": "#00E59B",
            "stat_neutral": "#F8FAFC",
            "scrollbar_bg": "#07101F",
            "close_bg": "#FF6B7A",
            "close_text": "#020407",
        }
        self.fonts = {
            "header": {"family": "Segoe UI", "size": 12, "weight": "bold"},
            "section_title": {"family": "Segoe UI", "size": 11, "weight": "bold"},
            "stat_name": {"family": "Segoe UI", "size": 11, "weight": "normal"},
            "stat_value": {"family": "Segoe UI", "size": 12, "weight": "bold"},
            "stat_sample": {"family": "Segoe UI", "size": 10, "weight": "normal"},
            "close_button": {"family": "Segoe UI", "size": 10, "weight": "bold"},
        }
        self.spacing = {
            "window_padding": 8,
            "section_spacing": 6,
            "row_height": 21,
            "icon_size": 14,
            "border_radius": 0,
        }


# Theme registry
AVAILABLE_THEMES = {
    "material_dark": MaterialDarkTheme,
    "material_light": MaterialLightTheme,
    "classic": ClassicTheme,
    "hud_dark": HudDarkTheme,
}


def get_theme(theme_name: str = "material_dark") -> PopupTheme:
    """Get a theme instance by name."""
    theme_class = AVAILABLE_THEMES.get(theme_name, MaterialDarkTheme)
    return theme_class()


def get_stat_color(theme: PopupTheme, stat_name: str, value: float, thresholds: StatThresholds | None = None) -> str:
    """Get color for a stat based on its value and thresholds."""
    if thresholds is None:
        # Default thresholds for common stats
        thresholds = {
            "vpip": {"low": 20, "high": 35},
            "pfr": {"low": 15, "high": 25},
            "three_B": {"low": 3, "high": 8},
            "agg_fact": {"low": 1.5, "high": 3.0},
            "cb1": {"low": 50, "high": 75},
        }

    stat_thresholds = thresholds.get(stat_name)
    if not stat_thresholds:
        return theme.get_color("stat_neutral")

    if value < stat_thresholds["low"]:
        return theme.get_color("stat_low")
    if value > stat_thresholds["high"]:
        return theme.get_color("stat_high")
    return theme.get_color("stat_medium")
