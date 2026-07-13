#!/usr/bin/env python
"""ThemeManager.py

Centralized theme manager for fpdb.
Unifies the three theme systems: qt_material, PopupThemes and settings.json.
"""

from __future__ import annotations

import re
import threading
import xml.etree.ElementTree as ET
from pathlib import Path

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("theme_manager")
FPDB_THEME_START = "/* FPDB_LEGACY_THEME_START */"
FPDB_THEME_END = "/* FPDB_LEGACY_THEME_END */"

# Custom themes directory
CUSTOM_THEMES_DIR = Path.home() / ".fpdb" / "themes"


class ThemeManager:
    """Centralized theme manager for fpdb.

    Manages synchronization between:
    - qt_material themes (main application theme)
    - PopupThemes (HUD popup windows)
    - XML Configuration (persistence)
    """

    _instance = None
    _lock = threading.RLock()

    # Available qt_material themes (dynamically detected)
    AVAILABLE_QT_THEMES = None  # Will be populated on first access

    # Mapping qt_material to popup themes
    QT_TO_POPUP_MAPPING = {
        "dark_purple.xml": "material_dark",
        "dark_amber.xml": "material_dark",
        "dark_blue.xml": "material_dark",
        "dark_cyan.xml": "material_dark",
        "dark_lightgreen.xml": "material_dark",
        "dark_pink.xml": "material_dark",
        "dark_red.xml": "material_dark",
        "dark_teal.xml": "material_dark",
        "dark_yellow.xml": "material_dark",
        "light_amber.xml": "material_light",
        "light_blue.xml": "material_light",
        "light_cyan.xml": "material_light",
        "light_lightgreen.xml": "material_light",
        "light_pink.xml": "material_light",
        "light_purple.xml": "material_light",
        "light_red.xml": "material_light",
        "light_teal.xml": "material_light",
        "light_yellow.xml": "material_light",
    }

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self):
        if not hasattr(self, "initialized"):
            self.initialized = False
            self._qt_material_theme = "dark_purple.xml"
            self._popup_theme = "material_dark"
            self._config = None
            self._main_window = None
            # Initialize available themes list on first instance
            if ThemeManager.AVAILABLE_QT_THEMES is None:
                ThemeManager.AVAILABLE_QT_THEMES = self._detect_available_themes()

    @staticmethod
    def _color_to_hex(color, fallback: str) -> str:
        """Return a valid #RRGGBB color from a QColor-like object."""
        try:
            if color and color.isValid():
                return color.name()
        except AttributeError:
            pass
        return fallback

    @staticmethod
    def _tone(color, factor: int) -> str:
        """Lighten or darken a hex color while keeping a valid Qt stylesheet value."""
        try:
            from PySide6.QtGui import QColor

            qcolor = QColor(color)
            if not qcolor.isValid():
                return color
            return qcolor.lighter(factor).name() if factor >= 100 else qcolor.darker(200 - factor).name()
        except (ImportError, TypeError, ValueError):
            return color

    @staticmethod
    def _is_dark(color: str) -> bool:
        try:
            from PySide6.QtGui import QColor

            return QColor(color).lightness() < 128
        except (ImportError, TypeError, ValueError):
            return True

    @classmethod
    def _readable_text_for(cls, background: str) -> str:
        """Choose readable text for a generated background color."""
        return "#f8fafc" if cls._is_dark(background) else "#101820"

    @staticmethod
    def _stylesheet_property(stylesheet: str, selector: str, prop: str) -> str | None:
        """Extract the first hex color property from a Qt stylesheet rule."""
        match = re.search(rf"{re.escape(selector)}\s*\{{(?P<body>.*?)\}}", stylesheet, flags=re.DOTALL)
        if not match:
            return None
        prop_match = re.search(rf"{re.escape(prop)}\s*:\s*(#[0-9a-fA-F]{{6}})", match.group("body"))
        return prop_match.group(1) if prop_match else None

    def _material_stylesheet_colors(self) -> dict[str, str]:
        """Read colors from qt_material's generated stylesheet when available."""
        try:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            stylesheet = app.styleSheet() if app else ""
            if not isinstance(stylesheet, str):
                stylesheet = ""
        except (ImportError, RuntimeError):
            stylesheet = ""

        if "QtMaterial" not in stylesheet:
            return {}

        text = self._stylesheet_property(stylesheet, "*", "color")
        window = self._stylesheet_property(stylesheet, "QWidget", "background-color")
        accent = re.search(r"selection-background-color\s*:\s*(#[0-9a-fA-F]{6})", stylesheet)
        button = self._stylesheet_property(
            stylesheet,
            "QDateEdit,\nQDateTimeEdit,\nQSpinBox,\nQDoubleSpinBox,\nQTextEdit,\nQLineEdit,\nQPushButton",
            "background-color",
        )

        colors = {}
        if text:
            colors["text"] = text
            colors["window_text"] = text
        if window:
            colors["window"] = window
            colors["base"] = self._tone(window, 78 if self._is_dark(window) else 110)
            colors["button"] = button or window
        if accent:
            colors["accent"] = accent.group(1)
            colors["selection"] = accent.group(1)
        return colors

    def get_legacy_palette(self) -> dict[str, str]:
        """Return normalized colors derived from the active QApplication palette."""
        try:
            from PySide6.QtGui import QPalette
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            palette = app.palette() if app else None
            if not palette:
                raise RuntimeError("No QApplication palette available")

            window = self._color_to_hex(palette.color(QPalette.ColorRole.Window), "#30363c")
            base = self._color_to_hex(palette.color(QPalette.ColorRole.Base), "#1b2026")
            text = self._color_to_hex(palette.color(QPalette.ColorRole.Text), "#edf2f7")
            window_text = self._color_to_hex(palette.color(QPalette.ColorRole.WindowText), text)
            button = self._color_to_hex(palette.color(QPalette.ColorRole.Button), "#242b32")
            highlight = self._color_to_hex(palette.color(QPalette.ColorRole.Highlight), "#b64fd8")
            highlighted_text = self._color_to_hex(
                palette.color(QPalette.ColorRole.HighlightedText),
                "#ffffff",
            )
        except (ImportError, RuntimeError, AttributeError):
            window = "#30363c"
            base = "#1b2026"
            text = "#edf2f7"
            window_text = text
            button = "#242b32"
            highlight = "#b64fd8"
            highlighted_text = "#ffffff"

        material_colors = self._material_stylesheet_colors()
        window = material_colors.get("window", window)
        base = material_colors.get("base", base)
        text = material_colors.get("text", text)
        window_text = material_colors.get("window_text", window_text)
        button = material_colors.get("button", button)
        highlight = material_colors.get("accent", highlight)

        dark = self._is_dark(window)
        sidebar = self._tone(window, 84 if dark else 106)
        sidebar_panel = self._tone(window, 96 if dark else 102)
        table_header = self._tone(highlight, 58 if dark else 180)
        table_header_hover = self._tone(highlight, 72 if dark else 165)
        return {
            "window": window,
            "base": base,
            "app_header": self._tone(window, 88 if dark else 108),
            "sidebar": sidebar,
            "sidebar_panel": sidebar_panel,
            "surface": "#222b32",
            "surface_panel": "#222b32",
            "panel": self._tone(window, 112 if dark else 96),
            "panel_alt": self._tone(window, 126 if dark else 92),
            "button": button,
            "button_hover": self._tone(button, 132 if dark else 92),
            "text": text,
            "muted_text": self._tone(text, 74 if dark else 130),
            "window_text": window_text,
            "accent": highlight,
            "accent_soft": self._tone(highlight, 64 if dark else 170),
            "accent_hover": self._tone(highlight, 122 if dark else 88),
            "highlighted_text": highlighted_text,
            "table_header": table_header,
            "table_header_hover": table_header_hover,
            "table_header_text": self._readable_text_for(table_header),
            "border": self._tone(window, 150 if dark else 82),
            "grid": self._tone(window, 136 if dark else 88),
            "input": self._tone(base, 106 if dark else 102),
            "input_hover": self._tone(base, 125 if dark else 96),
            "selection": highlight,
            "selection_soft": self._tone(highlight, 78 if dark else 188),
            "tooltip": self._tone(window, 145 if dark else 92),
            "tooltip_border": self._tone(highlight, 118 if dark else 88),
            "graph_showdown": "#14a8ff" if dark else "#006db4",
            "graph_nonshowdown": "#ff4771" if dark else "#c91f4a",
            "graph_ev": "#f59e3d" if dark else "#a15c00",
            "graph_hands": "#22c55e" if dark else "#15803d",
            "graph_up": "#22c55e" if dark else "#14843b",
            "graph_down": "#ef4444" if dark else "#b91c1c",
            "graph_purple": "#a78bfa" if dark else "#7c3aed",
        }

    def get_theme_colors(self) -> dict[str, str]:
        """Return colors used by matplotlib-based legacy viewers."""
        colors = self.get_legacy_palette()
        return {
            "background": colors["surface_panel"],
            "foreground": colors["window_text"],
            "grid": colors["grid"],
            "line_up": colors["graph_up"],
            "line_down": colors["graph_down"],
            "line_showdown": colors["graph_showdown"],
            "line_nonshowdown": colors["graph_nonshowdown"],
            "line_ev": colors["graph_ev"],
            "line_hands": colors["graph_hands"],
        }

    def build_legacy_app_stylesheet(self) -> str:
        """Build fpdb-specific Qt polish on top of qt_material."""
        c = self.get_legacy_palette()
        surface_alt = self._tone(c["surface_panel"], 112 if self._is_dark(c["surface_panel"]) else 90)
        return f"""
            {FPDB_THEME_START}
            QMainWindow, QDialog {{
                background-color: {c["window"]};
                color: {c["window_text"]};
            }}
            QStatusBar {{
                background-color: {c["app_header"]};
                color: {c["window_text"]};
                border-top: 1px solid {c["border"]};
                font-weight: 600;
            }}
            QWidget#customTitleBar {{
                background-color: {c["app_header"]};
                border-bottom: 1px solid {c["border"]};
            }}
            QLabel#customTitleBarLabel {{
                color: {c["muted_text"]};
                font-weight: 700;
            }}
            QPushButton#titleBarButton {{
                background-color: transparent;
                color: {c["accent"]};
                border: 1px solid {c["accent"]};
                border-radius: 4px;
                padding: 0;
                font-weight: 700;
                min-width: 20px;
                min-height: 20px;
            }}
            QPushButton#titleBarButton:hover {{
                background-color: {c["accent"]};
                color: {c["highlighted_text"]};
            }}
            QTabWidget::pane {{
                border: 1px solid {c["border"]};
                border-radius: 6px;
                background-color: {c["window"]};
                top: -1px;
            }}
            QTabBar::tab {{
                background: transparent;
                color: {c["muted_text"]};
                border: 0;
                border-bottom: 2px solid transparent;
                padding: 9px 18px;
                margin: 0 3px;
                font-weight: 700;
                text-transform: uppercase;
            }}
            QTabBar::tab:selected {{
                color: {c["accent"]};
                border-bottom-color: {c["accent"]};
            }}
            QTabBar::tab:hover {{
                color: {c["window_text"]};
                background-color: {c["panel"]};
            }}
            QFrame, QScrollArea, QAbstractScrollArea {{
                border-color: {c["border"]};
            }}
            QScrollArea#filterSidebar {{
                background-color: {c["sidebar"]};
                border: 0;
                border-right: 1px solid {c["border"]};
            }}
            QScrollArea#filterSidebar > QWidget > QWidget {{
                background-color: {c["sidebar"]};
            }}
            QFrame#graphSurface, QFrame#statsSurface, QFrame#handsSurface {{
                background-color: {c["surface"]};
                border: 1px solid {c["border"]};
                border-radius: 6px;
            }}
            QFrame#graphCanvasPanel {{
                background-color: {c["surface_panel"]};
                border: 0;
                border-radius: 4px;
            }}
            QSplitter::handle {{
                background-color: {c["border"]};
                margin: 0;
            }}
            QSplitter::handle:hover {{
                background-color: {c["accent"]};
            }}
            QTableView, QTableWidget, QTreeView, QTreeWidget {{
                background-color: {c["base"]};
                alternate-background-color: {c["panel"]};
                color: {c["text"]};
                gridline-color: {c["grid"]};
                border: 1px solid {c["border"]};
                border-radius: 6px;
                selection-background-color: {c["selection"]};
                selection-color: {c["highlighted_text"]};
            }}
            QFrame#graphSurface QTableView, QFrame#statsSurface QTableView, QFrame#handsSurface QTableView {{
                background-color: {c["surface_panel"]};
                alternate-background-color: {surface_alt};
            }}
            QTableView::item, QTableWidget::item, QTreeView::item, QTreeWidget::item {{
                padding: 6px 8px;
            }}
            QTableView::item:hover, QTableWidget::item:hover, QTreeView::item:hover, QTreeWidget::item:hover {{
                background-color: {c["panel_alt"]};
            }}
            QHeaderView::section {{
                background-color: {c["table_header"]};
                color: {c["table_header_text"]};
                border: 0;
                border-right: 1px solid {c["border"]};
                border-bottom: 2px solid {c["accent"]};
                padding: 8px 10px;
                font-weight: 700;
                text-transform: uppercase;
            }}
            QHeaderView::section:hover {{
                background-color: {c["table_header_hover"]};
                color: {c["table_header_text"]};
            }}
            QGroupBox {{
                border: 1px solid {c["border"]};
                border-radius: 7px;
                margin-top: 13px;
                padding: 12px;
                background-color: {c["panel"]};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: {c["accent"]};
                font-weight: 700;
            }}
            QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QDateEdit, QSpinBox {{
                background-color: {c["input"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                border-radius: 5px;
                padding: 5px 8px;
                selection-background-color: {c["selection"]};
                selection-color: {c["highlighted_text"]};
            }}
            QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QComboBox:hover, QDateEdit:hover, QSpinBox:hover {{
                background-color: {c["input_hover"]};
                border-color: {c["accent"]};
            }}
            QToolTip {{
                background-color: {c["tooltip"]};
                color: {c["window_text"]};
                border: 1px solid {c["tooltip_border"]};
                border-radius: 4px;
                padding: 7px;
            }}
            QMenuBar, QMenu {{
                background-color: {c["panel"]};
                color: {c["window_text"]};
                border-color: {c["border"]};
            }}
            QMenuBar::item:selected, QMenu::item:selected {{
                background-color: {c["selection"]};
                color: {c["highlighted_text"]};
            }}
            QScrollBar:vertical, QScrollBar:horizontal {{
                background: {c["panel"]};
                border: 0;
                margin: 0;
            }}
            QScrollBar:vertical {{
                width: 12px;
            }}
            QScrollBar:horizontal {{
                height: 12px;
            }}
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
                background: {c["border"]};
                border-radius: 6px;
                min-height: 28px;
                min-width: 28px;
            }}
            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
                background: {c["accent"]};
            }}
            QScrollBar::add-line, QScrollBar::sub-line,
            QScrollBar::add-page, QScrollBar::sub-page {{
                background: transparent;
                border: 0;
            }}
            {FPDB_THEME_END}
        """

    def build_filter_stylesheet(self) -> str:
        """Build theme-aware styling for the legacy filter sidebar."""
        c = self.get_legacy_palette()
        dark = self._is_dark(c["window"])
        sidebar = "#20262b" if dark else c["sidebar"]
        card = "#222b32" if dark else c["sidebar_panel"]
        card_hover = "#2f3740" if dark else c["panel_alt"]
        input_bg = "#20262b" if dark else c["input"]
        text = "#eef3f7" if dark else c["text"]
        muted = "#aeb8c2" if dark else c["muted_text"]
        accent = c["accent"]
        accent_hover = c["accent_hover"]
        accent_panel = c["accent_soft"]

        # Transparent border styles that scale naturally with dark/light themes
        border_rgba = "rgba(255, 255, 255, 0.08)" if dark else "rgba(0, 0, 0, 0.08)"

        return f"""
            QWidget {{
                background-color: {sidebar};
                color: {text};
                font-size: 13px;
            }}

            /* Cadres et Groupes */
            QGroupBox {{
                border: 1px solid {border_rgba};
                border-radius: 8px;
                padding: 16px 12px 12px 12px;
                background-color: {card};
                margin-top: 10px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 2px 8px;
                color: {accent_hover};
                font-weight: bold;
                font-size: 11px;
                text-transform: uppercase;
                background-color: {sidebar};
                border-radius: 4px;
                border: 1px solid {border_rgba};
                margin-left: 8px;
            }}
            QGroupBox:hover {{
                border-color: {accent_hover}2b;
                background-color: {card_hover};
            }}

            /* Titres de section épurés (plus de boîte verte opaque avec bordure) */
            QLabel#filterTitle {{
                background-color: transparent;
                color: {accent};
                border: none;
                border-radius: 0;
                padding: 0;
                font-weight: 800;
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 1.5px;
                margin-left: 4px;
                margin-top: 14px;
                margin-bottom: 2px;
            }}

            /* Boutons d'action principaux (au bas de la sidebar) */
            #filterSidebar QPushButton {{
                background-color: {accent};
                color: #ffffff;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 1px;
                min-height: 32px;
            }}
            #filterSidebar QPushButton:hover {{
                background-color: {accent_hover};
                color: #ffffff;
            }}
            #filterSidebar QPushButton:pressed {{
                background-color: {accent_panel};
            }}

            /* Boutons secondaires / options (à l'intérieur des cadres) */
            #filterSidebar QGroupBox QPushButton {{
                background-color: {input_bg};
                color: {text};
                border: 1px solid {border_rgba};
                border-radius: 4px;
                padding: 3px 6px;
                font-weight: 600;
                font-size: 11px;
                text-transform: none;
                letter-spacing: 0px;
                min-height: 22px;
            }}
            #filterSidebar QGroupBox QPushButton:hover {{
                background-color: {card_hover};
                border-color: {accent};
                color: {accent};
            }}
            #filterSidebar QGroupBox QPushButton:pressed {{
                background-color: {accent_panel};
                color: #ffffff;
            }}

            /* Cases à cocher et boutons radio modernisés */
            QCheckBox, QRadioButton {{
                spacing: 8px;
                padding: 4px 6px;
                color: {text};
                font-size: 12px;
                border-radius: 4px;
                background: transparent;
                font-weight: 600;
            }}
            QCheckBox:hover, QRadioButton:hover {{
                background-color: {card_hover};
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 2px solid {border_rgba};
                border-radius: 4px;
                background-color: {input_bg};
            }}
            QCheckBox::indicator:hover {{
                border-color: {accent};
            }}
            QCheckBox::indicator:checked {{
                background-color: {accent};
                border-color: {accent};
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'><polyline points='20 6 9 17 4 12'/></svg>");
            }}
            QRadioButton::indicator {{
                width: 16px;
                height: 16px;
                border: 2px solid {border_rgba};
                border-radius: 9px;
                background-color: {input_bg};
            }}
            QRadioButton::indicator:hover {{
                border-color: {accent};
            }}
            QRadioButton::indicator:checked {{
                background-color: {accent};
                border-color: {accent};
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><circle cx='12' cy='12' r='6' fill='white'/></svg>");
            }}

            /* Champs de saisie */
            QComboBox, QDateEdit, QSpinBox, QLineEdit {{
                background-color: {input_bg};
                border: 1px solid {border_rgba};
                border-radius: 5px;
                padding: 4px 8px;
                color: {text};
                font-size: 12px;
                font-weight: 600;
                min-width: 90px;
                min-height: 26px;
            }}
            QComboBox:hover, QDateEdit:hover, QSpinBox:hover, QLineEdit:hover {{
                border-color: {accent};
            }}
            QComboBox QAbstractItemView {{
                background-color: {input_bg};
                border: 1px solid {border_rgba};
                selection-background-color: {accent};
                selection-color: {text};
                color: {text};
            }}
            QComboBox:disabled, QDateEdit:disabled, QSpinBox:disabled, QLineEdit:disabled,
            QCheckBox:disabled, QRadioButton:disabled {{
                color: {muted};
                border-color: {border_rgba};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}

            /* Boutons de sélection numérique (Spin/Date buttons) */
            QDateEdit::up-button, QDateEdit::down-button,
            QSpinBox::up-button, QSpinBox::down-button {{
                subcontrol-origin: border;
                width: 16px;
                border-left: 1px solid {border_rgba};
                background-color: {card};
            }}
            QDateEdit::up-button, QSpinBox::up-button {{
                subcontrol-position: top right;
                border-top-right-radius: 4px;
            }}
            QDateEdit::down-button, QSpinBox::down-button {{
                subcontrol-position: bottom right;
                border-bottom-right-radius: 4px;
            }}
            QDateEdit::up-button:hover, QDateEdit::down-button:hover,
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background-color: {card_hover};
            }}

            /* Scrollbars */
            QScrollBar:vertical {{
                background-color: {sidebar};
                width: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {border_rgba};
                min-height: 20px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {accent};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """

    def apply_legacy_polish(self) -> bool:
        """Apply fpdb-specific styling that qt_material does not cover reliably."""
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtWidgets import QAbstractItemView, QApplication, QScrollArea

            app = QApplication.instance()
            if not app:
                log.warning("No QApplication instance found for legacy theme polish")
                return False

            base_stylesheet = self._strip_legacy_polish(app.styleSheet() or "")
            app.setStyleSheet(base_stylesheet + "\n" + self.build_legacy_app_stylesheet())
            app.setProperty("fpdb_qt_material_theme", self._qt_material_theme)

            colors = self.get_legacy_palette()
            theme_colors = self.get_theme_colors()
            filter_stylesheet = self.build_filter_stylesheet()

            widgets = []
            try:
                widgets = list(app.allWidgets())
            except Exception:  # intentional broad catch: allWidgets might be a Mock in tests
                pass

            for widget in widgets:
                if isinstance(widget, QScrollArea) and widget.widget().__class__.__name__ == "Filters":
                    widget.setObjectName("filterSidebar")
                if widget.__class__.__name__ == "Filters":
                    widget.setStyleSheet(filter_stylesheet)
                    widget.update()
                if isinstance(widget, QAbstractItemView):
                    widget.setAlternatingRowColors(True)
                    widget.setStyleSheet("")
                    if hasattr(widget, "setShowGrid"):
                        widget.setShowGrid(True)
                    header = getattr(widget, "horizontalHeader", lambda: None)()
                    if header:
                        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if hasattr(widget, "colors") and isinstance(getattr(widget, "colors"), dict):
                    widget.colors.update(theme_colors)
                if hasattr(widget, "graphFrame") and hasattr(widget.graphFrame, "setStyleSheet"):
                    widget.graphFrame.setObjectName("graphSurface")
                    widget.graphFrame.setStyleSheet(f"background-color: {theme_colors['background']}")
                if hasattr(widget, "graphBox") and hasattr(widget.graphBox, "setStyleSheet"):
                    widget.graphBox.setObjectName("graphCanvasPanel")
                    widget.graphBox.setStyleSheet(f"background-color: {colors['surface_panel']}")
                if hasattr(widget, "stats_frame") and hasattr(widget.stats_frame, "setObjectName"):
                    widget.stats_frame.setObjectName("statsSurface")
                if hasattr(widget, "handsFrame") and hasattr(widget.handsFrame, "setObjectName"):
                    widget.handsFrame.setObjectName("handsSurface")
                if hasattr(widget, "statsInfoFrame") and hasattr(widget.statsInfoFrame, "setObjectName"):
                    widget.statsInfoFrame.setObjectName("statsSurface")
                refresh_theme = getattr(widget, "refresh_theme", None)
                if callable(refresh_theme):
                    refresh_theme(colors, theme_colors)
                self._refresh_matplotlib_canvas(widget, colors, theme_colors)

            for widget in widgets:
                try:
                    widget.style().unpolish(widget)
                    widget.style().polish(widget)
                    widget.update()
                except Exception:  # intentional broad catch: style method might be mocked in tests
                    pass
            app.processEvents()
            return True
        except (ImportError, RuntimeError, AttributeError) as e:
            log.warning(f"Error applying legacy theme polish: {e}")
            return False

    @staticmethod
    def _strip_legacy_polish(stylesheet: str) -> str:
        """Remove the previous fpdb polish block before appending a fresh one."""
        if not isinstance(stylesheet, str):
            return ""
        pattern = rf"{re.escape(FPDB_THEME_START)}.*?{re.escape(FPDB_THEME_END)}"
        return re.sub(pattern, "", stylesheet, flags=re.DOTALL)

    def _refresh_matplotlib_canvas(self, widget, colors: dict[str, str], theme_colors: dict[str, str]) -> None:
        """Repaint existing matplotlib canvases after a live theme change."""
        fig = getattr(widget, "fig", None)
        canvas = getattr(widget, "canvas", None)
        if fig is None or canvas is None:
            return

        try:
            fig.patch.set_facecolor(theme_colors["background"])
            for axis in getattr(fig, "axes", []):
                axis.set_facecolor(colors["surface_panel"])
                axis.tick_params(axis="x", colors=theme_colors["foreground"])
                axis.tick_params(axis="y", colors=theme_colors["foreground"])
                axis.xaxis.label.set_color(theme_colors["foreground"])
                axis.yaxis.label.set_color(theme_colors["foreground"])
                axis.title.set_color(theme_colors["foreground"])
                for spine in axis.spines.values():
                    spine.set_color(colors["muted_text"])
                axis.grid(color=theme_colors["grid"], linestyle=":", linewidth=0.6, alpha=0.75)
            canvas.draw_idle()
        except (AttributeError, RuntimeError, ValueError) as e:
            log.debug(f"Unable to refresh matplotlib canvas theme: {e}")

    def initialize(self, config=None, main_window=None):
        """Initialize the ThemeManager.

        Args:
            config: Configuration instance
            main_window: Main window instance
        """
        with self._lock:
            if self.initialized:
                log.warning("ThemeManager already initialized")
                return

            self._config = config
            self._main_window = main_window

            # Load saved themes
            self._load_saved_themes()

            self.initialized = True
            log.info("ThemeManager initialized")

    def _load_saved_themes(self):
        """Load saved themes from configuration."""
        if not self._config:
            return

        try:
            # Load from XML configuration
            general = getattr(self._config, "general", {})

            saved_qt_theme = general.get("qt_material_theme", "dark_purple.xml")
            saved_popup_theme = general.get("popup_theme", "material_dark")

            # Validate themes
            if saved_qt_theme in self.AVAILABLE_QT_THEMES:
                self._qt_material_theme = saved_qt_theme
            else:
                log.warning(f"Invalid qt_material theme: {saved_qt_theme}, using default")

            if saved_popup_theme in ["material_dark", "material_light", "classic"]:
                self._popup_theme = saved_popup_theme
            else:
                log.warning(f"Invalid popup theme: {saved_popup_theme}, using default")

            log.info(f"Loaded themes: qt={self._qt_material_theme}, popup={self._popup_theme}")

        except (AttributeError, TypeError, ValueError) as e:
            log.exception(f"Error loading saved themes: {e}")

    def _detect_available_themes(self) -> list[str]:
        """Detect all available qt_material themes dynamically.

        Returns:
            list[str]: List of available theme names (including custom themes)
        """
        try:
            # Get built-in qt_material themes
            builtin_themes = self._get_builtin_qt_themes()

            # Get custom themes
            custom_themes = self._get_custom_themes()

            # Combine and sort
            all_themes = builtin_themes + custom_themes
            return sorted(all_themes)

        except (ImportError, OSError, AttributeError, TypeError) as e:
            log.exception(f"Error in theme detection: {e}")
            return self._get_fallback_themes()

    def _get_builtin_qt_themes(self) -> list[str]:
        """Get built-in qt_material themes.

        Returns:
            list[str]: List of built-in theme names
        """
        try:
            from PySide6.QtWidgets import QApplication

            # Ensure QApplication exists (required for qt_material)
            if QApplication.instance() is None:
                QApplication([])

            import qt_material

            available_themes = qt_material.list_themes()
            log.info(f"Detected {len(available_themes)} built-in qt_material themes")
            return available_themes

        except ImportError:
            log.warning("qt_material not available, using fallback theme list")
            return self._get_fallback_themes()
        except (ImportError, RuntimeError, OSError, AttributeError) as e:
            log.warning(f"Error detecting qt_material themes: {e}, using fallback")
            return self._get_fallback_themes()

    def _get_custom_themes(self) -> list[str]:
        """Get custom themes from user directory.

        Returns:
            list[str]: List of custom theme names
        """
        custom_themes = []

        try:
            if not CUSTOM_THEMES_DIR.exists():
                # Create custom themes directory if it doesn't exist
                CUSTOM_THEMES_DIR.mkdir(parents=True, exist_ok=True)
                log.info(f"Created custom themes directory: {CUSTOM_THEMES_DIR}")
                return custom_themes

            # Scan for .xml files in custom themes directory
            for theme_file in CUSTOM_THEMES_DIR.glob("*.xml"):
                if self._validate_custom_theme(theme_file):
                    custom_themes.append(theme_file.name)
                    log.debug(f"Found valid custom theme: {theme_file.name}")
                else:
                    log.warning(f"Invalid custom theme file: {theme_file.name}")

            if custom_themes:
                log.info(f"Detected {len(custom_themes)} custom themes")

        except OSError as e:
            log.exception(f"Error scanning custom themes: {e}")

        return custom_themes

    def _validate_custom_theme(self, theme_file: Path) -> bool:
        """Validate a custom theme file.

        Args:
            theme_file: Path to theme file

        Returns:
            bool: True if valid
        """
        try:
            # Basic validation - check if it's a valid XML file
            if not theme_file.is_file():
                log.info(f"Theme file does not exist: {theme_file}")
                return False

            if theme_file.suffix.lower() != ".xml":
                log.info(f"Theme file is not .xml: {theme_file}")
                return False

            with open(theme_file, encoding="utf-8") as f:
                content = f.read()

            # Check if file has content
            if not content.strip():
                log.info(f"Theme file is empty: {theme_file}")
                return False

            # Attempt to parse XML
            root = ET.fromstring(content)
            log.info(f"Successfully parsed XML for {theme_file}, root element: {root.tag}")

            # Check if it's a qt_material format theme (resources element) or our old format (theme element)
            if root.tag not in ["resources", "theme"]:
                log.info(f"Invalid root element {root.tag}, expected 'resources' or 'theme'")
                return False

            # Additional validation could be added here
            # (e.g., check for required color elements in qt_material format)

            return True

        except (OSError, UnicodeDecodeError, ET.ParseError) as e:
            log.info(f"Custom theme validation failed for {theme_file}: {e}")
            log.info(
                f"Theme file content preview: {content[:200] if 'content' in locals() else 'Could not read content'}"
            )
            return False

    def _get_fallback_themes(self) -> list[str]:
        """Return fallback theme list if qt_material detection fails.

        Returns:
            list[str]: Fallback theme list
        """
        return [
            "dark_purple.xml",
            "dark_amber.xml",
            "dark_blue.xml",
            "dark_cyan.xml",
            "dark_lightgreen.xml",
            "dark_pink.xml",
            "dark_red.xml",
            "dark_teal.xml",
            "dark_yellow.xml",
            "light_amber.xml",
            "light_blue.xml",
            "light_cyan.xml",
            "light_lightgreen.xml",
            "light_pink.xml",
            "light_purple.xml",
            "light_red.xml",
            "light_teal.xml",
            "light_yellow.xml",
        ]

    def get_qt_material_theme(self) -> str:
        """Return the current qt_material theme."""
        return self._qt_material_theme

    def get_popup_theme(self) -> str:
        """Return the current popup theme."""
        return self._popup_theme

    def set_qt_material_theme(self, theme_name: str, save: bool = True, apply_to_ui: bool = True) -> bool:
        """Set the qt_material theme.

        Args:
            theme_name: qt_material theme name
            save: If True, save to configuration
            apply_to_ui: If True, apply theme to UI (avoid for UI-initiated changes)

        Returns:
            bool: True if successful
        """
        if theme_name not in self.AVAILABLE_QT_THEMES:
            log.error(f"Unknown qt_material theme: {theme_name}")
            return False

        try:
            old_theme = self._qt_material_theme
            self._qt_material_theme = theme_name

            # Auto-sync popup theme based on mapping
            auto_popup_theme = self.QT_TO_POPUP_MAPPING.get(theme_name, "material_dark")
            self._popup_theme = auto_popup_theme

            # Apply theme to application (only if not called from UI)
            if apply_to_ui:
                if self._main_window and hasattr(self._main_window, "change_theme"):
                    try:
                        self._main_window.change_theme(theme_name)
                        log.info(f"Called main_window.change_theme({theme_name})")
                    except (RuntimeError, AttributeError, TypeError) as e:
                        log.warning(f"Error calling main_window.change_theme: {e}")
                        self._apply_theme_to_application(theme_name)
                else:
                    self._apply_theme_to_application(theme_name)

            # Save if requested
            if save:
                self._save_themes()

            log.info(f"Theme changed: {old_theme} -> {theme_name} (popup: {auto_popup_theme})")
            return True

        except Exception as e:  # intentional broad catch: theme callbacks and persistence are runtime-dependent.
            log.exception(f"Error setting qt_material theme: {e}")
            return False

    def set_popup_theme(self, theme_name: str, save: bool = True) -> bool:
        """Set the popup theme only.

        Args:
            theme_name: Popup theme name
            save: If True, save to configuration

        Returns:
            bool: True if successful
        """
        if theme_name not in ["material_dark", "material_light", "classic"]:
            log.error(f"Unknown popup theme: {theme_name}")
            return False

        try:
            old_theme = self._popup_theme
            self._popup_theme = theme_name

            # Save if requested
            if save:
                self._save_themes()

            log.info(f"Popup theme changed: {old_theme} -> {theme_name}")
            return True

        except (AttributeError, TypeError, OSError) as e:
            log.exception(f"Error setting popup theme: {e}")
            return False

    def set_global_theme(self, qt_theme: str, popup_theme: str | None = None, apply_to_ui: bool = True) -> bool:
        """Set a global theme (qt_material + popup).

        Args:
            qt_theme: qt_material theme
            popup_theme: Popup theme (optional, auto-determined if None)
            apply_to_ui: If True, apply theme to UI

        Returns:
            bool: True if successful
        """
        if popup_theme is None:
            popup_theme = self.QT_TO_POPUP_MAPPING.get(qt_theme, "material_dark")

        # Apply both themes without saving individually
        qt_success = self.set_qt_material_theme(qt_theme, save=False, apply_to_ui=apply_to_ui)
        popup_success = self.set_popup_theme(popup_theme, save=False)

        if qt_success and popup_success:
            # Save only once
            self._save_themes()
            return True

        return False

    def _save_themes(self):
        """Save themes to configuration."""
        if not self._config:
            log.warning("No config available for saving themes")
            return

        try:
            # Save to general configuration dictionary
            if not hasattr(self._config, "general"):
                self._config.general = {}

            self._config.general["qt_material_theme"] = self._qt_material_theme
            self._config.general["popup_theme"] = self._popup_theme

            # Update XML DOM structure for persistence
            if hasattr(self._config, "doc") and self._config.doc:
                self._update_xml_theme_attributes()

            # Save configuration file
            if hasattr(self._config, "save"):
                self._config.save()
                log.info("Themes saved to configuration")
            else:
                log.warning("Config.save() method not available")

        except (AttributeError, TypeError, OSError) as e:
            log.exception(f"Error saving themes: {e}")

    def _update_xml_theme_attributes(self):
        """Update XML DOM with theme attributes."""
        try:
            # Find the general element in the XML DOM
            general_nodes = self._config.doc.getElementsByTagName("general")

            if general_nodes:
                general_node = general_nodes[0]
                # Set theme attributes in XML DOM
                general_node.setAttribute("qt_material_theme", self._qt_material_theme)
                general_node.setAttribute("popup_theme", self._popup_theme)
                log.debug(
                    f"Updated XML general node with themes: qt={self._qt_material_theme}, popup={self._popup_theme}"
                )
            else:
                log.warning("No general element found in XML DOM")

        except (AttributeError, IndexError, TypeError) as e:
            log.exception(f"Error updating XML theme attributes: {e}")

    def get_available_qt_themes(self) -> list[str]:
        """Return the list of available qt_material themes."""
        return self.AVAILABLE_QT_THEMES.copy()

    def get_available_popup_themes(self) -> list[str]:
        """Return the list of available popup themes."""
        return ["material_dark", "material_light", "classic"]

    def reset_to_defaults(self) -> bool:
        """Reset to default themes.

        Returns:
            bool: True if successful
        """
        return self.set_global_theme("dark_purple.xml", "material_dark")

    def install_custom_theme(self, theme_file_path: str, theme_name: str | None = None) -> bool:
        """Install a custom theme from file.

        Args:
            theme_file_path: Path to the theme file to install
            theme_name: Optional custom name (defaults to filename)

        Returns:
            bool: True if successfully installed
        """
        try:
            source_path = Path(theme_file_path)

            if not source_path.exists():
                log.error(f"Theme file not found: {theme_file_path}")
                return False

            # Validate the theme file
            if not self._validate_custom_theme(source_path):
                log.error(f"Invalid theme file: {theme_file_path}")
                return False

            # Determine destination filename
            if theme_name:
                if not theme_name.endswith(".xml"):
                    theme_name += ".xml"
                dest_filename = theme_name
            else:
                dest_filename = source_path.name

            # Ensure custom themes directory exists
            CUSTOM_THEMES_DIR.mkdir(parents=True, exist_ok=True)

            # Copy theme file to custom themes directory
            dest_path = CUSTOM_THEMES_DIR / dest_filename

            import shutil

            shutil.copy2(source_path, dest_path)

            # Refresh available themes list
            ThemeManager.AVAILABLE_QT_THEMES = self._detect_available_themes()

            log.info(f"Custom theme installed: {dest_filename}")
            return True

        except (OSError, UnicodeDecodeError, ET.ParseError, ImportError) as e:
            log.exception(f"Error installing custom theme: {e}")
            return False

    def remove_custom_theme(self, theme_name: str) -> bool:
        """Remove a custom theme.

        Args:
            theme_name: Name of the custom theme to remove

        Returns:
            bool: True if successfully removed
        """
        try:
            theme_path = CUSTOM_THEMES_DIR / theme_name

            if not theme_path.exists():
                log.error(f"Custom theme not found: {theme_name}")
                return False

            # Don't allow removing if it's the current theme
            if self._qt_material_theme == theme_name:
                log.error(f"Cannot remove currently active theme: {theme_name}")
                return False

            # Remove the file
            theme_path.unlink()

            # Refresh available themes list
            ThemeManager.AVAILABLE_QT_THEMES = self._detect_available_themes()

            log.info(f"Custom theme removed: {theme_name}")
            return True

        except OSError as e:
            log.exception(f"Error removing custom theme: {e}")
            return False

    def list_custom_themes(self) -> list[str]:
        """List all installed custom themes.

        Returns:
            list[str]: List of custom theme names
        """
        return self._get_custom_themes()

    def is_custom_theme(self, theme_name: str) -> bool:
        """Check if a theme is a custom theme.

        Args:
            theme_name: Theme name to check

        Returns:
            bool: True if it's a custom theme
        """
        return theme_name in self._get_custom_themes()

    def get_custom_themes_directory(self) -> Path:
        """Get the custom themes directory path.

        Returns:
            Path: Path to custom themes directory
        """
        return CUSTOM_THEMES_DIR

    def _apply_theme_to_application(self, theme_name: str) -> bool:
        """Apply theme to the application, handling both built-in and custom themes.

        Args:
            theme_name: Theme name to apply

        Returns:
            bool: True if successfully applied
        """
        try:
            from PySide6.QtWidgets import QApplication

            if self.is_custom_theme(theme_name):
                # For custom themes, copy to qt_material directory temporarily and use qt_material
                theme_path = CUSTOM_THEMES_DIR / theme_name

                app = QApplication.instance()
                if not app:
                    log.warning("No QApplication instance found")
                    return False

                try:
                    import shutil

                    import qt_material

                    # Get qt_material themes directory
                    qt_material_themes_dir = Path(qt_material.__file__).parent / "themes"

                    # Create a temporary copy in qt_material themes directory
                    temp_theme_path = qt_material_themes_dir / theme_name

                    # Copy our custom theme to qt_material directory
                    shutil.copy2(theme_path, temp_theme_path)

                    try:
                        # Now apply using qt_material
                        qt_material.apply_stylesheet(app, theme=theme_name)
                        self.apply_legacy_polish()
                        log.info(f"Applied custom theme via qt_material: {theme_name}")
                    finally:
                        # Clean up - remove the temporary file
                        if temp_theme_path.exists():
                            temp_theme_path.unlink()

                except (ImportError, OSError, RuntimeError, AttributeError) as e:
                    log.error(f"Error applying custom theme {theme_name}: {e}")
                    return False
            else:
                # For built-in themes, use qt_material directly
                app = QApplication.instance()
                if not app:
                    log.warning("No QApplication instance found")
                    return False

                try:
                    import qt_material

                    qt_material.apply_stylesheet(app, theme=theme_name)
                    self.apply_legacy_polish()
                    log.info(f"Applied built-in theme: {theme_name}")
                except (ImportError, RuntimeError, AttributeError) as e:
                    log.error(f"Error applying built-in theme {theme_name}: {e}")
                    return False

            return True

        except (ImportError, OSError, RuntimeError, AttributeError) as e:
            log.exception(f"Error applying theme to application: {e}")
            return False
