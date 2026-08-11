"""styles.py

Fournit les feuilles de style (QSS) dynamiques et les palettes de couleurs
synchronized with FPDB's ThemeManager.
"""

from __future__ import annotations

from fpdb_3_legacy.ThemeManager import ThemeManager


def get_theme_palette() -> dict[str, str]:
    """Retrieve the normalized color palette for the active theme."""
    return ThemeManager().get_legacy_palette()


def get_modern_qss() -> str:
    """Generate the global QSS stylesheet for modern components."""
    c = get_theme_palette()

    # Text colors
    text_color = c.get("text", "#edf2f7")
    muted_color = c.get("muted_text", "#a0aec0")

    # Border & backgrounds
    border_color = c.get("border", "#4a5568")
    bg_window = c.get("window", "#2d3748")
    bg_card = c.get("sidebar", "#1a202c")
    bg_base = c.get("base", "#1a202c")

    # Accents
    accent = c.get("accent", "#319795")
    accent_hover = c.get("accent_hover", "#4fd1c5")

    # Up/Down (Profit/Loss colors)
    color_up = c.get("graph_up", "#48bb78")
    color_down = c.get("graph_down", "#f56565")

    # Dynamically detect dark/light mode
    dark = True
    try:
        h = bg_window.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        yiq = ((r * 299) + (g * 587) + (b * 114)) / 1000
        dark = yiq < 128
    except (AttributeError, ValueError):
        dark = True

    # Translucent variables for automatic background adaptation
    border_rgba = "rgba(255, 255, 255, 0.08)" if dark else "rgba(0, 0, 0, 0.08)"
    grid_rgba = "rgba(255, 255, 255, 0.06)" if dark else "rgba(0, 0, 0, 0.06)"
    alt_bg_rgba = "rgba(255, 255, 255, 0.02)" if dark else "rgba(0, 0, 0, 0.02)"
    card_border_rgba = "rgba(255, 255, 255, 0.12)" if dark else "rgba(0, 0, 0, 0.12)"

    return f"""
    /* General tab style - modern flat/web */
    QTabWidget::panel {{
        border: 1px solid {border_rgba};
        background-color: {bg_window};
        border-radius: 8px;
    }}
    QTabBar::tab {{
        background-color: transparent;
        color: {muted_color};
        border: none;
        padding: 10px 20px;
        margin-right: 4px;
        font-weight: bold;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}
    QTabBar::tab:selected {{
        color: {accent};
        border-bottom: 2px solid {accent};
    }}
    QTabBar::tab:hover:!selected {{
        color: {text_color};
        border-bottom: 2px solid {border_rgba};
    }}

    /* Cartes KPI du Tableau de bord */
    QFrame#kpiCard {{
        background-color: {bg_card};
        border: 1px solid {card_border_rgba};
        border-radius: 8px;
    }}
    QLabel#kpiTitle {{
        color: {muted_color};
        font-size: 11px;
        font-weight: bold;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}
    QLabel#kpiValue {{
        color: {text_color};
        font-size: 22px;
        font-weight: bold;
    }}
    QLabel#kpiValueGreen {{
        color: {color_up};
        font-size: 22px;
        font-weight: bold;
    }}
    QLabel#kpiValueRed {{
        color: {color_down};
        font-size: 22px;
        font-weight: bold;
    }}

    /* Modernized statistics tables (without vertical grid lines) */
    QTableView {{
        background-color: {bg_base};
        gridline-color: transparent; /* Hide the default system grid */
        selection-background-color: {accent};
        selection-color: #ffffff;
        border: 1px solid {border_rgba};
        border-radius: 8px;
        font-size: 12px;
        alternate-background-color: {alt_bg_rgba};
    }}
    QTableView::item {{
        padding: 8px 12px;
        border: none;
        border-bottom: 1px solid {grid_rgba}; /* Ligne horizontale uniquement */
    }}
    QTableView::item:selected {{
        background-color: {accent};
        color: #ffffff;
    }}
    QHeaderView::section {{
        background-color: {bg_card};
        color: {muted_color};
        padding: 10px 12px;
        border: none;
        border-bottom: 2px solid {accent}; /* Header underline */
        font-weight: bold;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}
    QHeaderView::section:hover {{
        background-color: {accent};
        color: #ffffff;
    }}

    /* Scrollbars */
    QScrollBar:vertical {{
        background-color: {bg_base};
        width: 8px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background-color: {border_color};
        min-height: 20px;
        border-radius: 4px;
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

    QScrollBar:horizontal {{
        background-color: {bg_base};
        height: 8px;
        margin: 0px;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {border_color};
        min-width: 20px;
        border-radius: 4px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {accent};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        border: none;
        background: none;
        width: 0px;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: none;
    }}

    /* QGroupBox, QComboBox, QSpinBox */
    QGroupBox {{
        border: 1px solid {border_rgba};
        border-radius: 8px;
        margin-top: 6px;
        padding-top: 10px;
        background-color: {bg_card};
    }}
    QComboBox, QSpinBox {{
        background-color: {bg_base};
        border: 1px solid {border_rgba};
        border-radius: 5px;
        padding: 4px 8px;
        color: {text_color};
        min-height: 24px;
    }}
    QComboBox:hover, QSpinBox:hover {{
        border-color: {accent};
    }}

    /* Splitters */
    QSplitter::handle {{
        background-color: {border_rgba};
    }}
    QSplitter::handle:horizontal {{
        width: 1px;
    }}
    QSplitter::handle:vertical {{
        height: 1px;
    }}

    /* Buttons and interactive elements */
    QPushButton {{
        background-color: {bg_card};
        border: 1px solid {border_rgba};
        border-radius: 5px;
        color: {text_color};
        padding: 6px 12px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background-color: {accent};
        border-color: {accent_hover};
        color: #ffffff;
    }}
    QPushButton:pressed {{
        background-color: {accent_hover};
    }}

    /* Grille de Starting Hands */
    QFrame#handCell {{
        border: 1px solid {grid_rgba};
        border-radius: 2px;
    }}
    QLabel#handCellText {{
        font-size: 10px;
        font-weight: bold;
        color: {text_color};
    }}
    """
