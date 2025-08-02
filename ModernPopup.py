"""ModernPopup.py.

Modern popup windows with improved UI/UX for the HUD.
"""

from collections import defaultdict

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import Stats
from loggingFpdb import get_logger
from Popup import Popup
from PopupIcons import IconProvider, get_icon_provider, get_stat_category
from PopupThemes import PopupTheme, get_stat_color, get_theme

log = get_logger("modern_popup")


class ModernStatRow(QWidget):
    """A modern stat row with icon, name, value and visual indicators."""

    def __init__(self, stat_name: str, stat_data: tuple, theme: PopupTheme, icon_provider: IconProvider):
        super().__init__()
        self.stat_name = stat_name
        self.stat_data = stat_data
        self.theme = theme
        self.icon_provider = icon_provider

        self.setup_ui()
        self.setup_style()

    def setup_ui(self):
        """Setup the UI elements."""
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # Icon
        self.icon_label = QLabel(self.icon_provider.get_icon(self.stat_name))
        self.icon_label.setFixedSize(20, 20)
        self.icon_label.setAlignment(Qt.AlignCenter)

        # Stat name - extract clean name without "n=value" format
        if self.stat_data:
            # Get clean stat name by removing the "=value" part
            full_name = self.stat_data[3]
            if "=" in full_name:
                clean_name = full_name.split("=")[0]
            else:
                clean_name = full_name
        else:
            clean_name = self.stat_name

        self.name_label = QLabel(clean_name)
        self.name_label.setMinimumWidth(120)

        # Stat value
        value_text = self.stat_data[1] if self.stat_data else "N/A"
        self.value_label = QLabel(str(value_text))
        self.value_label.setMinimumWidth(60)
        self.value_label.setAlignment(Qt.AlignRight)

        # Visual indicator (progress bar style)
        self.indicator = QProgressBar()
        self.indicator.setMinimumWidth(80)
        self.indicator.setMaximumWidth(80)
        self.indicator.setMinimumHeight(12)
        self.indicator.setMaximumHeight(12)
        self.indicator.setTextVisible(False)  # Hide percentage text
        self._update_progress_bar()

        layout.addWidget(self.icon_label)
        layout.addWidget(self.name_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.indicator)
        layout.addStretch()

        self.setLayout(layout)

    def setup_style(self):
        """Apply theme styling."""
        # Extract numeric value for color determination
        try:
            if self.stat_data and len(self.stat_data) > 1:
                value_str = str(self.stat_data[1]).replace("%", "")
                numeric_value = float(value_str)
                color = get_stat_color(self.theme, self.stat_name, numeric_value)
            else:
                color = self.theme.get_color("text_secondary")
        except (ValueError, TypeError):
            color = self.theme.get_color("text_secondary")

        # Apply styles
        font_props = self.theme.get_font("stat_name")
        font = QFont(font_props["family"], font_props["size"])
        if font_props.get("weight") == "bold":
            font.setBold(True)

        self.name_label.setFont(font)
        self.name_label.setStyleSheet(f"color: {self.theme.get_color('text_primary')};")

        value_font = self.theme.get_font("stat_value")
        value_font_obj = QFont(value_font["family"], value_font["size"])
        if value_font.get("weight") == "bold":
            value_font_obj.setBold(True)

        self.value_label.setFont(value_font_obj)
        self.value_label.setStyleSheet(f"color: {color}; font-weight: bold;")

        self.icon_label.setStyleSheet(f"color: {color}; font-size: 14px;")

        # Style the progress bar with a clean rectangular design
        progress_bar_style = f"""
            QProgressBar {{
                border: 1px solid {self.theme.get_color('border')};
                border-radius: 3px;
                background-color: {self.theme.get_color('section_bg')};
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 2px;
                margin: 1px;
            }}
        """
        self.indicator.setStyleSheet(progress_bar_style)

        # Row hover effect
        self.setStyleSheet(f"""
            ModernStatRow:hover {{
                background-color: {self.theme.get_color('hover')};
                border-radius: {self.theme.get_spacing('border_radius')}px;
            }}
        """)

    def _update_progress_bar(self):
        """Update the progress bar based on stat value."""
        if not self.stat_data or len(self.stat_data) < 2:
            self.indicator.setValue(0)
            return

        try:
            # Get the numeric value from stat_data[0] or parse from stat_data[1]
            if isinstance(self.stat_data[0], (int, float)):
                value = float(self.stat_data[0])
            else:
                # Try to parse percentage from display value
                value_str = str(self.stat_data[1]).replace("%", "").replace("-", "0")
                value = float(value_str) if value_str.replace(".", "").isdigit() else 0.0

            # Clamp value between 0 and 100 for percentage display
            if value > 1.0:  # Likely already a percentage
                percentage = min(max(value, 0), 100)
            else:  # Convert from fraction to percentage
                percentage = min(max(value * 100, 0), 100)

            # Set progress bar value (0-100)
            self.indicator.setRange(0, 100)
            self.indicator.setValue(int(percentage))

        except (ValueError, TypeError, IndexError):
            # Fallback for non-numeric stats
            self.indicator.setValue(0)


class ModernSectionWidget(QFrame):
    """A collapsible section for grouping related stats."""

    def __init__(self, section_name: str, theme: PopupTheme, icon_provider: IconProvider):
        super().__init__()
        self.section_name = section_name
        self.theme = theme
        self.icon_provider = icon_provider
        self.stat_rows = []

        self.setup_ui()
        self.setup_style()

    def setup_ui(self):
        """Setup the section UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Section header
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(8, 6, 8, 6)

        section_icon = self.icon_provider.get_section_icon(self.section_name)
        self.header_icon = QLabel(section_icon)
        self.header_icon.setFixedSize(18, 18)

        self.header_label = QLabel(self.section_name.replace("_", " ").title())
        header_font = self.theme.get_font("section_title")
        font = QFont(header_font["family"], header_font["size"])
        if header_font.get("weight") == "bold":
            font.setBold(True)
        self.header_label.setFont(font)

        header_layout.addWidget(self.header_icon)
        header_layout.addWidget(self.header_label)
        header_layout.addStretch()

        self.header_widget = QWidget()
        self.header_widget.setLayout(header_layout)

        # Content area
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(1)
        self.content_widget.setLayout(self.content_layout)

        layout.addWidget(self.header_widget)
        layout.addWidget(self.content_widget)

        self.setLayout(layout)

    def setup_style(self):
        """Apply section styling."""
        self.setFrameStyle(QFrame.Box)
        self.setStyleSheet(f"""
            ModernSectionWidget {{
                background-color: {self.theme.get_color('section_bg')};
                border: 1px solid {self.theme.get_color('border')};
                border-radius: {self.theme.get_spacing('border_radius')}px;
                margin: 2px;
            }}
        """)

        self.header_widget.setStyleSheet(f"""
            QWidget {{
                background-color: {self.theme.get_color('header_bg')};
                border-radius: {self.theme.get_spacing('border_radius')}px;
            }}
        """)

        self.header_label.setStyleSheet(f"color: {self.theme.get_color('text_primary')};")
        self.header_icon.setStyleSheet(f"color: {self.theme.get_color('text_accent')};")

    def add_stat_row(self, stat_name: str, stat_data: tuple):
        """Add a stat row to this section."""
        row = ModernStatRow(stat_name, stat_data, self.theme, self.icon_provider)
        self.stat_rows.append(row)
        self.content_layout.addWidget(row)


class ModernSubmenu(Popup):
    """Modern popup window with sectioned layout and improved styling."""

    def __init__(self, *args, **kwargs):
        # Extract theme from kwargs if provided
        self.theme_name = kwargs.pop("theme", "material_dark")
        self.icon_provider_name = kwargs.pop("icon_provider", "emoji")

        # Initialize theme and icon provider BEFORE calling super()
        # because super().__init__() calls create() which needs these attributes
        self.theme = get_theme(self.theme_name)
        self.icon_provider = get_icon_provider(self.icon_provider_name)
        self.sections = {}

        # Variables for making popup draggable
        self.drag_start_position = None
        self.is_dragging = False

        super().__init__(*args, **kwargs)

    def create(self) -> None:
        """Create the modern popup window."""
        super().create()

        # Find player
        player_id = None
        for pid in list(self.stat_dict.keys()):
            if self.seat == self.stat_dict[pid]["seat"]:
                player_id = pid
                break

        if player_id is None:
            self.destroy_pop()
            return

        if len(self.pop.pu_stats) < 1:
            self.destroy_pop()
            return

        self.setup_window_style()
        self.create_header(player_id)
        self.create_content(player_id)

    def setup_window_style(self):
        """Setup the overall window styling."""
        self.setStyleSheet(f"""
            ModernSubmenu {{
                background-color: {self.theme.get_color('window_bg')};
                border: 2px solid {self.theme.get_color('border')};
                border-radius: {self.theme.get_spacing('border_radius') * 2}px;
            }}
        """)

        # Main layout
        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(
            self.theme.get_spacing("window_padding"),
            self.theme.get_spacing("window_padding"),
            self.theme.get_spacing("window_padding"),
            self.theme.get_spacing("window_padding"),
        )
        self.main_layout.setSpacing(self.theme.get_spacing("section_spacing"))
        self.setLayout(self.main_layout)

    def create_header(self, player_id: int):
        """Create the popup header with player info and close button."""
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(8, 6, 8, 6)

        # Player info
        player_name = self.stat_dict[player_id].get("screen_name", "Unknown")
        self.player_label = QLabel(f"👤 {player_name}")

        header_font = self.theme.get_font("header")
        font = QFont(header_font["family"], header_font["size"])
        if header_font.get("weight") == "bold":
            font.setBold(True)
        self.player_label.setFont(font)
        self.player_label.setStyleSheet(f"color: {self.theme.get_color('text_primary')};")

        # Close button
        self.close_button = QPushButton("✕")
        self.close_button.setFixedSize(24, 24)
        self.close_button.clicked.connect(self.destroy_pop)
        self.close_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.theme.get_color('close_bg')};
                color: {self.theme.get_color('close_text')};
                border: none;
                border-radius: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #D32F2F;
            }}
        """)

        header_layout.addWidget(self.player_label)
        header_layout.addStretch()
        header_layout.addWidget(self.close_button)

        self.header_widget = QWidget()
        self.header_widget.setLayout(header_layout)
        self.header_widget.setStyleSheet(f"""
            QWidget {{
                background-color: {self.theme.get_color('header_bg')};
                border-radius: {self.theme.get_spacing('border_radius')}px;
                margin-bottom: 4px;
            }}
        """)

        self.main_layout.addWidget(self.header_widget)

    def create_content(self, player_id: int):
        """Create the main content with sectioned stats."""
        # Scroll area for content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QFrame.NoFrame)

        # Content widget
        content_widget = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(self.theme.get_spacing("section_spacing"))

        # Group stats by category
        categorized_stats = defaultdict(list)

        for stat, submenu_to_run in self.pop.pu_stats_submenu:
            # Get stat data
            stat_data = Stats.do_stat(
                self.stat_dict,
                player=int(player_id),
                stat=stat,
                hand_instance=self.hand_instance,
            )

            # Categorize the stat
            category = get_stat_category(stat)
            categorized_stats[category].append((stat, stat_data, submenu_to_run))

        # Create sections
        section_order = ["player_info", "preflop", "flop", "turn", "river", "steal", "aggression", "general"]

        for section_name in section_order:
            if section_name in categorized_stats:
                section = ModernSectionWidget(section_name, self.theme, self.icon_provider)

                for stat, stat_data, submenu in categorized_stats[section_name]:
                    section.add_stat_row(stat, stat_data)

                content_layout.addWidget(section)
                self.sections[section_name] = section

        # Add any remaining categories not in the predefined order
        for section_name, stats in categorized_stats.items():
            if section_name not in self.sections:
                section = ModernSectionWidget(section_name, self.theme, self.icon_provider)

                for stat, stat_data, submenu in stats:
                    section.add_stat_row(stat, stat_data)

                content_layout.addWidget(section)
                self.sections[section_name] = section

        content_layout.addStretch()
        content_widget.setLayout(content_layout)

        scroll_area.setWidget(content_widget)
        self.main_layout.addWidget(scroll_area)

        # Set minimum size
        self.setMinimumSize(320, 400)
        self.setMaximumSize(500, 600)

    def mousePressEvent(self, event):
        """Handle mouse press for dragging."""
        if event.button() == Qt.LeftButton:
            # Check if click is on header area for dragging
            click_pos = event.pos()
            if hasattr(self, "header_widget") and self.header_widget:
                header_geometry = self.header_widget.geometry()
                if header_geometry.contains(click_pos):
                    self.drag_start_position = event.globalPos()
                    self.is_dragging = False
                    # Don't call parent for header clicks to prevent popup closing
                    return
        # Call parent to handle other events (right-click popup destruction, etc.)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging."""
        if (event.buttons() == Qt.LeftButton and
            self.drag_start_position is not None):

            # Calculate drag distance
            diff = event.globalPos() - self.drag_start_position

            # Only start dragging after minimum distance to avoid accidental drags
            if not self.is_dragging and diff.manhattanLength() > 10:
                self.is_dragging = True

            if self.is_dragging:
                # Move the window
                self.move(self.pos() + diff)
                self.drag_start_position = event.globalPos()
                # Don't call parent when dragging to prevent other mouse handling
                return

        # Call parent for other mouse move events
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release to stop dragging."""
        if event.button() == Qt.LeftButton and self.drag_start_position is not None:
            # If we were dragging, just reset drag state and don't call parent
            if self.is_dragging:
                self.drag_start_position = None
                self.is_dragging = False
                return
            # Quick click on header without dragging - reset drag state
            self.drag_start_position = None
            self.is_dragging = False

        # Call parent to handle other mouse events (including popup closing)
        super().mouseReleaseEvent(event)


class ModernSubmenuLight(ModernSubmenu):
    """Light theme variant of ModernSubmenu."""

    def __init__(self, *args, **kwargs):
        kwargs["theme"] = "material_light"
        super().__init__(*args, **kwargs)


class ModernSubmenuClassic(ModernSubmenu):
    """Classic theme variant of ModernSubmenu for compatibility."""

    def __init__(self, *args, **kwargs):
        kwargs["theme"] = "classic"
        kwargs["icon_provider"] = "text"
        super().__init__(*args, **kwargs)


# Register the new popup classes
# These can be used in HUD_config.xml as pu_class values
MODERN_POPUP_CLASSES = {
    "ModernSubmenu": ModernSubmenu,
    "ModernSubmenuLight": ModernSubmenuLight,
    "ModernSubmenuClassic": ModernSubmenuClassic,
}
