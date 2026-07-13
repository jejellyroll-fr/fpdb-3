#!/usr/bin/env python
from __future__ import annotations

"""ModernSeatPreferences.py.

Modern interface for dynamic management of favorite seats by site.
"""

import json
import os
from math import cos, sin
from typing import Any

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("modern_seat_preferences")

SEAT_CONFIG_ERRORS = (AttributeError, KeyError, TypeError, ValueError)
SEAT_IO_ERRORS = (OSError, TypeError, ValueError, json.JSONDecodeError)


class SeatSelector(QWidget):
    """Widget to select a favorite seat with visualization."""

    seatChanged = Signal(int)

    def __init__(self, max_seats, current_seat=0, parent=None) -> None:
        super().__init__(parent)
        self.max_seats = max_seats
        self.current_seat = current_seat
        self.seat_buttons: list[QPushButton] = []
        self.setFixedSize(120, 80)  # Fixed size for uniformity

    def paintEvent(self, event) -> None:
        """Draw the poker table."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Dimensions
        width = self.width()
        height = self.height()
        margin = 10

        # Calculate table dimensions for good proportions
        # Typical poker table ratio: width = 1.5 * height
        table_width = width - 2 * margin
        table_height = min(height - 2 * margin, table_width / 1.5)

        # Center the table vertically
        table_x = margin
        table_y = (height - table_height) / 2

        # Draw the table (oval)
        table_rect = QRect(int(table_x), int(table_y), int(table_width), int(table_height))
        painter.setBrush(QBrush(QColor(0, 100, 0)))  # Vert poker
        painter.setPen(QPen(QColor(139, 69, 19), 2))  # Bordure marron
        painter.drawEllipse(table_rect)

        # Calculate seat positions
        center_x = width / 2
        center_y = height / 2
        radius_x = table_width / 2 - 10
        radius_y = table_height / 2 - 10

        # Draw the seats
        for i in range(1, self.max_seats + 1):
            angle = 2 * 3.14159 * (i - 1) / self.max_seats - 3.14159 / 2
            x = center_x + radius_x * cos(angle)
            y = center_y + radius_y * sin(angle)

            # Seat color
            if i == self.current_seat:
                painter.setBrush(QBrush(QColor(255, 215, 0)))  # Gold for selected seat
                painter.setPen(QPen(QColor(255, 165, 0), 2))
            else:
                painter.setBrush(QBrush(QColor(200, 200, 200)))
                painter.setPen(QPen(QColor(100, 100, 100), 1))

            # Draw the seat circle
            seat_size = 20
            painter.drawEllipse(int(x - seat_size / 2), int(y - seat_size / 2), seat_size, seat_size)

            # Seat number
            painter.setPen(QPen(QColor(Qt.GlobalColor.black)))
            painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            painter.drawText(
                int(x - seat_size / 2),
                int(y - seat_size / 2),
                seat_size,
                seat_size,
                Qt.AlignmentFlag.AlignCenter,
                str(i),
            )

    def mousePressEvent(self, event) -> None:
        """Handle click on a seat."""
        # Calculate which seat was clicked
        width = self.width()
        height = self.height()
        margin = 10

        # Same calculations as in paintEvent
        table_width = width - 2 * margin
        table_height = min(height - 2 * margin, table_width / 1.5)

        center_x = width / 2
        center_y = height / 2
        radius_x = table_width / 2 - 10
        radius_y = table_height / 2 - 10

        # Qt6: event.x()/y() are deprecated; use the QPointF-based position().
        click_pos = event.position().toPoint()
        click_x = click_pos.x()
        click_y = click_pos.y()

        # Check each seat
        for i in range(1, self.max_seats + 1):
            angle = 2 * 3.14159 * (i - 1) / self.max_seats - 3.14159 / 2
            x = center_x + radius_x * cos(angle)
            y = center_y + radius_y * sin(angle)

            # Distance from click to seat center
            distance = ((click_x - x) ** 2 + (click_y - y) ** 2) ** 0.5

            if distance <= 10:  # Seat radius (seat_size / 2)
                self.current_seat = i
                self.seatChanged.emit(i)
                self.update()
                break

    def setSeat(self, seat) -> None:
        """Set the selected seat."""
        if 0 <= seat <= self.max_seats:
            self.current_seat = seat
            self.update()


class ModernSeatCard(QFrame):
    """Card to configure favorite seats for a site."""

    def __init__(self, site_name, site_config, parent=None) -> None:
        super().__init__(parent)
        self.site_name = site_name
        self.site_config = site_config
        self.parent_dialog = parent
        self.seat_inputs: dict[int, QLineEdit] = {}
        self.seat_selectors: dict[int, SeatSelector] = {}

        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet(
            """
            ModernSeatCard {
                border: 1px solid rgba(128, 128, 128, 0.3);
                border-radius: 8px;
                background-color: rgba(255, 255, 255, 0.05);
                padding: 10px;
                margin: 3px;
            }
            ModernSeatCard:hover {
                border: 1px solid rgba(128, 128, 128, 0.5);
                background-color: rgba(255, 255, 255, 0.08);
            }
        """,
        )

        # Set a maximum height to avoid stretching
        self.setMaximumHeight(700)

        self.setup_ui()

    def get_seat_mapping(self, max_seats):
        """Get mapping from visual seat index (1 to max_seats clockwise from top)
        to layout seat index.
        """
        import math
        # Default mapping is identity
        default_mapping = {i: i for i in range(1, max_seats + 1)}

        try:
            config = self.parent_dialog.config
            # Resolve layout set for this site
            layout_set_name = None
            if hasattr(self.site_config, "layout_set"):
                if isinstance(self.site_config.layout_set, dict):
                    layout_set_name = self.site_config.layout_set.get("all") or next(iter(self.site_config.layout_set.values()), None)

            if not layout_set_name:
                return default_mapping

            if not hasattr(config, "layout_sets") or layout_set_name not in config.layout_sets:
                return default_mapping

            layout_set = config.layout_sets[layout_set_name]
            if max_seats not in layout_set.layout:
                return default_mapping

            layout = layout_set.layout[max_seats]
            if not hasattr(layout, "location") or not layout.location:
                return default_mapping

            cx = layout.width / 2.0
            cy = layout.height / 2.0

            seats_with_angles = []
            for i in range(1, max_seats + 1):
                if i < len(layout.location) and layout.location[i] is not None:
                    x, y = layout.location[i]
                    angle = math.atan2(y - cy, x - cx)
                    shifted = angle + math.pi / 2.0
                    while shifted < 0:
                        shifted += 2 * math.pi
                    while shifted >= 2 * math.pi:
                        shifted -= 2 * math.pi
                    seats_with_angles.append((i, shifted))

            if len(seats_with_angles) != max_seats:
                return default_mapping

            # Sort seats clockwise starting from top-center
            seats_with_angles.sort(key=lambda item: item[1])

            mapping = {}
            for visual_idx, (layout_idx, _) in enumerate(seats_with_angles, 1):
                mapping[visual_idx] = layout_idx
            return mapping
        except Exception:  # intentional broad catch
            log.exception(f"Error computing seat mapping for site {self.site_name} max {max_seats}:")
            return default_mapping

    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Header
        header_layout = QHBoxLayout()

        site_label = QLabel(f"<b>{self.site_name}</b>")
        site_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        header_layout.addWidget(site_label)

        # Indicator if the site is enabled
        if hasattr(self.site_config, "enabled") and self.site_config.enabled:
            status_label = QLabel("✓ Enabled")
            status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        else:
            status_label = QLabel("✗ Disabled")
            status_label.setStyleSheet("color: #F44336;")
        header_layout.addWidget(status_label)

        header_layout.addStretch()

        # Button to reset
        reset_btn = QPushButton("Reset to Default")
        reset_btn.clicked.connect(self.reset_to_default)
        header_layout.addWidget(reset_btn)

        layout.addLayout(header_layout)

        # Grid for seat configurations
        seats_group = QGroupBox("Favorite Seats by Table Size")
        seats_layout = QGridLayout()
        seats_layout.setSpacing(25)  # Increase spacing to avoid overlap
        seats_layout.setContentsMargins(20, 30, 20, 25)
        seats_layout.setVerticalSpacing(50)  # Large vertical spacing
        seats_layout.setHorizontalSpacing(30)  # Horizontal spacing between columns

        # Headers
        players_header = QLabel("<b>Players</b>")
        players_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        seats_layout.addWidget(players_header, 0, 0)

        seat_header = QLabel("<b>Seat</b>")
        seat_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        seats_layout.addWidget(seat_header, 0, 1)

        visual_header = QLabel("<b>Visual Selection</b>")
        visual_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        seats_layout.addWidget(visual_header, 0, 2)

        # Configurations for each number of players (2-10)
        # Organize in two columns to save vertical space
        col = 0
        row = 1
        for max_seats in range(2, 11):
            if max_seats == 7:  # Switch to second column after 6 players
                col = 4  # Increase spacing between columns
                row = 1
                # Add a vertical separator
                separator = QFrame()
                separator.setFrameShape(QFrame.Shape.VLine)
                separator.setFrameShadow(QFrame.Shadow.Sunken)
                seats_layout.addWidget(separator, 0, 3, 8, 1)  # Increase separator height
                # Add headers for the second column
                players_header2 = QLabel("<b>Players</b>")
                players_header2.setAlignment(Qt.AlignmentFlag.AlignCenter)
                seats_layout.addWidget(players_header2, 0, 4)

                seat_header2 = QLabel("<b>Seat</b>")
                seat_header2.setAlignment(Qt.AlignmentFlag.AlignCenter)
                seats_layout.addWidget(seat_header2, 0, 5)

                visual_header2 = QLabel("<b>Visual Selection</b>")
                visual_header2.setAlignment(Qt.AlignmentFlag.AlignCenter)
                seats_layout.addWidget(visual_header2, 0, 6)

            # Create a container to vertically align all elements
            # Label for number of players
            players_label = QLabel(f"{max_seats}P")
            players_label.setMinimumWidth(60)
            players_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            players_label.setMinimumHeight(80)  # Same height as table
            players_label.setMaximumHeight(80)
            seats_layout.addWidget(
                players_label, row, col, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter,
            )

            # Input for favorite seat
            seat_input = QLineEdit()
            seat_input.setMaximumWidth(50)
            seat_input.setMinimumHeight(30)
            seat_input.setMaximumHeight(30)
            seat_input.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Handle different data structures for fav_seat
            current_fav: Any = 0
            try:
                if hasattr(self.site_config, "fav_seat"):
                    if isinstance(self.site_config.fav_seat, dict):
                        # If it's a dictionary
                        current_fav = self.site_config.fav_seat.get(
                            str(max_seats),
                            self.site_config.fav_seat.get(max_seats, 0),
                        )
                    elif isinstance(self.site_config.fav_seat, list) and len(self.site_config.fav_seat) > max_seats:
                        # If it's a list
                        current_fav = self.site_config.fav_seat[max_seats]
                    else:
                        current_fav = 0
            except SEAT_CONFIG_ERRORS:
                current_fav = 0

            # Map the loaded layout preferred seat index to the UI's visual seat index
            mapping = self.get_seat_mapping(max_seats)
            reverse_mapping = {v: k for k, v in mapping.items()}
            visual_fav = reverse_mapping.get(int(current_fav), 0) if current_fav != 0 else 0

            seat_input.setText(str(visual_fav))
            seat_input.setPlaceholderText("0")
            seat_input.textChanged.connect(lambda text, ms=max_seats: self.on_seat_changed(ms, text))
            self.seat_inputs[max_seats] = seat_input

            # Create a widget container to vertically center the input
            input_container = QWidget()
            input_container.setMinimumHeight(80)
            input_container.setMaximumHeight(80)
            input_layout = QVBoxLayout(input_container)
            input_layout.setContentsMargins(0, 0, 0, 0)
            input_layout.addWidget(seat_input, 0, Qt.AlignmentFlag.AlignCenter)
            seats_layout.addWidget(input_container, row, col + 1, Qt.AlignmentFlag.AlignCenter)

            # Visual selector
            seat_selector = SeatSelector(max_seats, int(visual_fav))
            seat_selector.seatChanged.connect(lambda seat, ms=max_seats: self.on_visual_seat_changed(ms, seat))
            self.seat_selectors[max_seats] = seat_selector
            seats_layout.addWidget(
                seat_selector, row, col + 2, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter,
            )

            # Add vertical spacing between rows
            seats_layout.setRowMinimumHeight(row, 130)  # Increase minimum row height

            row += 1

        seats_group.setLayout(seats_layout)
        layout.addWidget(seats_group)

        # Info note
        info_label = QLabel("💡 Set to 0 to disable favorite seat for a table size")
        info_label.setStyleSheet("color: palette(disabled-text); font-style: italic; padding: 5px;")
        layout.addWidget(info_label)

    def on_seat_changed(self, max_seats, text) -> None:
        """Handle text change in the input."""
        try:
            seat = int(text) if text else 0
            if 0 <= seat <= max_seats:
                self.seat_selectors[max_seats].setSeat(seat)
                # Auto-save if enabled
                if hasattr(self.parent_dialog, "auto_save_check") and self.parent_dialog.auto_save_check.isChecked():
                    self.parent_dialog.auto_save_single_site(self.site_name)
        except ValueError:
            pass

    def on_visual_seat_changed(self, max_seats, seat) -> None:
        """Handle change via the visual selector."""
        self.seat_inputs[max_seats].setText(str(seat))
        # Auto-save will be triggered by on_seat_changed

    def reset_to_default(self) -> None:
        """Reset all seats to 0."""
        reply = QMessageBox.question(
            self,
            "Reset Seats",
            f"Reset all favorite seats for {self.site_name} to default (0)?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            for max_seats in range(2, 11):
                self.seat_inputs[max_seats].setText("0")
                self.seat_selectors[max_seats].setSeat(0)

    def get_values(self):
        """Get the values of favorite seats."""
        values = {}
        for max_seats in range(2, 11):
            try:
                visual_seat = int(self.seat_inputs[max_seats].text() or "0")
                if visual_seat == 0:
                    values[max_seats] = 0
                else:
                    mapping = self.get_seat_mapping(max_seats)
                    layout_seat = mapping.get(visual_seat, 0)
                    values[max_seats] = layout_seat if 0 <= layout_seat <= max_seats else 0
            except (ValueError, KeyError):
                values[max_seats] = 0
        return values


class ModernSeatPreferencesDialog(QDialog):
    """Modern dialog for managing favorite seats."""

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.site_cards: dict[str, ModernSeatCard] = {}
        self.changes_made = False

        self.setWindowTitle("Seat Preferences")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        self.setup_ui()
        self.load_sites()

    def setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header_layout = QVBoxLayout()

        title = QLabel("Seat Preferences")
        title.setStyleSheet("font-size: 24px; font-weight: bold; padding: 10px 0;")
        header_layout.addWidget(title)

        subtitle = QLabel("Configure your favorite seats for each table size")
        subtitle.setStyleSheet("font-size: 14px; padding-bottom: 10px; opacity: 0.7;")
        header_layout.addWidget(subtitle)

        main_layout.addLayout(header_layout)

        # Filter bar
        filter_layout = QHBoxLayout()

        # Status filter
        filter_label = QLabel("Show:")
        filter_layout.addWidget(filter_label)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All Enabled Sites", "Sites with Custom Seats"])
        self.filter_combo.currentTextChanged.connect(self.apply_filter)
        self.filter_combo.setMinimumWidth(200)
        filter_layout.addWidget(self.filter_combo)

        # Search
        filter_layout.addSpacing(20)
        search_label = QLabel("🔍")
        filter_layout.addWidget(search_label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search sites...")
        self.search_input.setStyleSheet(
            """
            QLineEdit {
                padding: 8px 15px;
                border: 1px solid rgba(128, 128, 128, 0.3);
                border-radius: 20px;
                font-size: 14px;
            }
        """,
        )
        self.search_input.textChanged.connect(self.apply_filter)
        filter_layout.addWidget(self.search_input)

        filter_layout.addStretch()

        # Button for auto-save
        self.auto_save_check = QCheckBox("Auto-save changes")
        self.auto_save_check.setChecked(True)
        filter_layout.addWidget(self.auto_save_check)

        main_layout.addLayout(filter_layout)

        # Scrollable area for sites
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.sites_container = QWidget()
        self.sites_layout = QVBoxLayout(self.sites_container)
        self.sites_layout.setSpacing(10)

        scroll_area.setWidget(self.sites_container)
        main_layout.addWidget(scroll_area)

        # Action buttons
        button_layout = QHBoxLayout()

        # Import/Export buttons
        import_btn = QPushButton("Import Settings")
        import_btn.clicked.connect(self.import_settings)
        button_layout.addWidget(import_btn)

        export_btn = QPushButton("Export Settings")
        export_btn.clicked.connect(self.export_settings)
        button_layout.addWidget(export_btn)

        button_layout.addSpacing(20)

        # Statistics
        self.stats_label = QLabel()
        self.update_stats()
        button_layout.addWidget(self.stats_label)

        button_layout.addStretch()

        # Save/Cancel buttons
        save_btn = QPushButton("Save Changes")
        save_btn.clicked.connect(self.save_changes)
        save_btn.setProperty("class", "primary")

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(save_btn)

        main_layout.addLayout(button_layout)

        # Status bar
        self.status_bar = QStatusBar()
        main_layout.addWidget(self.status_bar)

    def load_sites(self) -> None:
        """Load all sites."""
        # Clear existing sites
        for card in self.site_cards.values():
            card.deleteLater()
        self.site_cards.clear()

        # Load only enabled sites by default
        for site_name, site_config in sorted(self.config.supported_sites.items()):
            # Only load enabled sites
            if hasattr(site_config, "enabled") and site_config.enabled:
                card = ModernSeatCard(site_name, site_config, self)
                self.sites_layout.addWidget(card)
                self.site_cards[site_name] = card

        # Add a spacer
        self.sites_layout.addStretch()

        # Update statistics
        self.update_stats()

    def apply_filter(self) -> None:
        """Apply search and status filters."""
        search_text = self.search_input.text().lower()
        filter_mode = self.filter_combo.currentText()

        visible_count = 0

        for site_name, card in self.site_cards.items():
            # Search filter
            if search_text and search_text not in site_name.lower():
                card.hide()
                continue

            # Status filter
            show = True
            if filter_mode == "Sites with Custom Seats":
                # Check if at least one favorite seat is set
                show = False
                try:
                    if hasattr(card.site_config, "fav_seat"):
                        if isinstance(card.site_config.fav_seat, dict):
                            show = any(
                                card.site_config.fav_seat.get(str(i), card.site_config.fav_seat.get(i, 0)) != 0
                                for i in range(2, 11)
                            )
                        elif isinstance(card.site_config.fav_seat, list):
                            show = any(
                                i < len(card.site_config.fav_seat) and card.site_config.fav_seat[i] != 0
                                for i in range(2, 11)
                            )
                except SEAT_CONFIG_ERRORS:
                    show = True  # Show by default if error
            # By default "All Enabled Sites" shows all loaded sites (already filtered as enabled)

            if show:
                card.show()
                visible_count += 1
            else:
                card.hide()

        # Update stats
        self.update_stats()

    def update_stats(self) -> None:
        """Update displayed statistics."""
        # All displayed sites are already enabled
        enabled_sites = len(self.site_cards)
        configured_sites = 0
        for card in self.site_cards.values():
            try:
                has_config = False
                if hasattr(card.site_config, "fav_seat"):
                    if isinstance(card.site_config.fav_seat, dict):
                        has_config = any(
                            card.site_config.fav_seat.get(str(i), card.site_config.fav_seat.get(i, 0)) != 0
                            for i in range(2, 11)
                        )
                    elif isinstance(card.site_config.fav_seat, list):
                        has_config = any(
                            i < len(card.site_config.fav_seat) and card.site_config.fav_seat[i] != 0
                            for i in range(2, 11)
                        )
                if has_config:
                    configured_sites += 1
            except SEAT_CONFIG_ERRORS:
                pass

        self.stats_label.setText(f"Enabled sites: {enabled_sites} | Sites with custom seats: {configured_sites}")

    def auto_save_single_site(self, site_name) -> None:
        """Auto-save changes for a single site."""
        try:
            if site_name in self.site_cards:
                card = self.site_cards[site_name]
                seat_values = card.get_values()

                # Check if changes were made
                changes_made = False
                for max_seats in range(2, 11):
                    try:
                        current_val: Any = 0
                        if hasattr(card.site_config, "fav_seat"):
                            if isinstance(card.site_config.fav_seat, dict):
                                current_val = card.site_config.fav_seat.get(
                                    str(max_seats),
                                    card.site_config.fav_seat.get(max_seats, 0),
                                )
                            elif (
                                isinstance(card.site_config.fav_seat, list)
                                and len(card.site_config.fav_seat) > max_seats
                            ):
                                current_val = card.site_config.fav_seat[max_seats]

                        if int(current_val) != seat_values.get(max_seats, 0):
                            changes_made = True
                            break
                    except SEAT_CONFIG_ERRORS:
                        continue

                if not changes_made:
                    return

                # Get the current enabled state of the site
                enabled = str(card.site_config.enabled) if hasattr(card.site_config, "enabled") else "True"

                # Update configuration for this site only
                self.config.edit_fav_seat(
                    site_name,
                    enabled,  # Add enabled parameter
                    seat2_dict=str(seat_values.get(2, 0)),
                    seat3_dict=str(seat_values.get(3, 0)),
                    seat4_dict=str(seat_values.get(4, 0)),
                    seat5_dict=str(seat_values.get(5, 0)),
                    seat6_dict=str(seat_values.get(6, 0)),
                    seat7_dict=str(seat_values.get(7, 0)),
                    seat8_dict=str(seat_values.get(8, 0)),
                    seat9_dict=str(seat_values.get(9, 0)),
                    seat10_dict=str(seat_values.get(10, 0)),
                )

                # Save immediately
                self.config.save()

                # Reload configuration dynamically
                self.reload_parent_config()

                # Update statistics
                self.update_stats()

                # Show a subtle visual indicator
                self.status_bar.showMessage(f"✔️ Auto-saved seats for {site_name}", 2000)

        except Exception:  # intentional broad catch: auto-save must not interrupt live UI editing.
            # On error, do not interrupt the user
            pass

    def save_changes(self) -> None:
        """Save changes."""
        try:
            # Collect all changes
            changes_made = False
            for site_name, card in self.site_cards.items():
                seat_values = card.get_values()

                # Check if changes were made
                for max_seats in range(2, 11):
                    try:
                        current_val: Any = 0
                        if hasattr(card.site_config, "fav_seat"):
                            if isinstance(card.site_config.fav_seat, dict):
                                current_val = card.site_config.fav_seat.get(
                                    str(max_seats),
                                    card.site_config.fav_seat.get(max_seats, 0),
                                )
                            elif (
                                isinstance(card.site_config.fav_seat, list)
                                and len(card.site_config.fav_seat) > max_seats
                            ):
                                current_val = card.site_config.fav_seat[max_seats]

                        if int(current_val) != seat_values.get(max_seats, 0):
                            changes_made = True
                            break
                    except SEAT_CONFIG_ERRORS:
                        continue

                # Get the current enabled state of the site
                enabled = str(card.site_config.enabled) if hasattr(card.site_config, "enabled") else "True"

                # Update configuration
                self.config.edit_fav_seat(
                    site_name,
                    enabled,  # Add enabled parameter
                    seat2_dict=str(seat_values.get(2, 0)),
                    seat3_dict=str(seat_values.get(3, 0)),
                    seat4_dict=str(seat_values.get(4, 0)),
                    seat5_dict=str(seat_values.get(5, 0)),
                    seat6_dict=str(seat_values.get(6, 0)),
                    seat7_dict=str(seat_values.get(7, 0)),
                    seat8_dict=str(seat_values.get(8, 0)),
                    seat9_dict=str(seat_values.get(9, 0)),
                    seat10_dict=str(seat_values.get(10, 0)),
                )

            # Detect changes before saving
            try:
                from fpdb_3_legacy.ConfigurationManager import ConfigurationManager

                config_manager = ConfigurationManager()
                if config_manager.initialized:
                    # Register favorite seat changes
                    if changes_made and hasattr(config_manager, "_pending_changes"):
                        if isinstance(config_manager._pending_changes, dict):
                            if "seat_preferences" not in config_manager._pending_changes:
                                config_manager._pending_changes["seat_preferences"] = {}
                            config_manager._pending_changes["seat_preferences"]["changed"] = True
                            config_manager._pending_changes["seat_preferences"]["sites"] = list(self.site_cards.keys())
            except ImportError:
                pass  # ConfigurationManager not available

            # Save to file
            self.config.save()

            # Reload configuration dynamically
            self.reload_parent_config()

            if not self.auto_save_check.isChecked():
                QMessageBox.information(self, "Success", "Seat preferences saved successfully!")

            self.accept()

        except (AttributeError, OSError, TypeError, ValueError) as e:
            QMessageBox.critical(self, "Error", f"Failed to save seat preferences:\n{e!s}")

    def reload_parent_config(self) -> None:
        """Reload configuration in the parent application."""
        try:
            # Try to reload via the parent (fpdb)
            if hasattr(self.parent(), "reload_config"):
                self.parent().reload_config()
                return

            # If no direct parent, try via ConfigurationManager
            try:
                from fpdb_3_legacy.ConfigurationManager import ConfigurationManager

                config_manager = ConfigurationManager()
                if config_manager.initialized and hasattr(config_manager, "reload_config"):
                    config_manager.reload_config()

                    # Notify observers of changes
                    if hasattr(config_manager, "notify_observers"):
                        config_manager.notify_observers("seat_preferences_changed")
            except ImportError:
                pass

        except Exception:  # intentional broad catch: parent/config reload callbacks are optional runtime hooks.
            pass

    def closeEvent(self, event) -> None:
        """Handle window close event."""
        # Check for unsaved changes
        has_changes = False
        for card in self.site_cards.values():
            seat_values = card.get_values()
            for max_seats in range(2, 11):
                try:
                    current_val: Any = 0
                    if hasattr(card.site_config, "fav_seat"):
                        if isinstance(card.site_config.fav_seat, dict):
                            current_val = card.site_config.fav_seat.get(
                                str(max_seats),
                                card.site_config.fav_seat.get(max_seats, 0),
                            )
                        elif isinstance(card.site_config.fav_seat, list) and len(card.site_config.fav_seat) > max_seats:
                            current_val = card.site_config.fav_seat[max_seats]

                    if int(current_val) != seat_values.get(max_seats, 0):
                        has_changes = True
                        break
                except SEAT_CONFIG_ERRORS:
                    continue
            if has_changes:
                break

        if has_changes:
            if self.auto_save_check.isChecked():
                # Auto-save if the option is enabled
                self.save_changes()
            else:
                # Ask for confirmation if changes were made
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "Do you want to save your changes before closing?",
                    QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                )

                if reply == QMessageBox.Save:
                    self.save_changes()
                elif reply == QMessageBox.Cancel:
                    event.ignore()
                    return

        event.accept()

    def export_settings(self) -> None:
        """Export seat settings to a JSON file."""
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Seat Settings",
            os.path.expanduser("~/fpdb_seat_settings.json"),
            "JSON Files (*.json)",
        )

        if filename:
            try:
                # Collect all configurations
                export_data = {}
                for site_name, card in self.site_cards.items():
                    seat_values = card.get_values()
                    # Only export sites with configured seats
                    if any(seat_values.get(i, 0) != 0 for i in range(2, 11)):
                        export_data[site_name] = seat_values

                # Save to file
                with open(filename, "w") as f:
                    json.dump(export_data, f, indent=2)

                QMessageBox.information(self, "Export Successful", f"Seat settings exported to:\n{filename}")

            except SEAT_IO_ERRORS as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export settings:\n{e!s}")

    def import_settings(self) -> None:
        """Import seat settings from a JSON file."""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Import Seat Settings",
            os.path.expanduser("~"),
            "JSON Files (*.json)",
        )

        if filename:
            try:
                # Load the file
                with open(filename) as f:
                    import_data = json.load(f)

                # Apply configurations
                imported_count = 0
                for site_name, seat_values in import_data.items():
                    if site_name in self.site_cards:
                        card = self.site_cards[site_name]
                        # Update values
                        for max_seats in range(2, 11):
                            if str(max_seats) in seat_values:
                                value = str(seat_values[str(max_seats)])
                            elif max_seats in seat_values:
                                value = str(seat_values[max_seats])
                            else:
                                continue

                            if max_seats in card.seat_inputs:
                                card.seat_inputs[max_seats].setText(value)

                        imported_count += 1

                # Update statistics
                self.update_stats()

                QMessageBox.information(
                    self,
                    "Import Successful",
                    f"Imported seat settings for {imported_count} sites from:\n{filename}",
                )

                # If auto-save is enabled, save immediately
                if self.auto_save_check.isChecked():
                    self.save_changes()

            except SEAT_IO_ERRORS as e:
                QMessageBox.critical(self, "Import Error", f"Failed to import settings:\n{e!s}")


# Utility function to integrate with fpdb.pyw
def show_modern_seat_preferences(config, parent=None):
    """Show the modern seat preferences dialog."""
    dialog = ModernSeatPreferencesDialog(config, parent)
    result = dialog.exec()

    # If changes were saved, notify the parent
    if result == QDialog.DialogCode.Accepted and parent:
        try:
            # Try to notify the parent of changes
            if hasattr(parent, "on_seat_preferences_changed"):
                parent.on_seat_preferences_changed()
            elif hasattr(parent, "refresh_tables"):
                parent.refresh_tables()
        except Exception:  # intentional broad catch: parent notification callbacks are optional runtime hooks.
            pass

    return result
