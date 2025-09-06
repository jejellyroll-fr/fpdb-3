#!/usr/bin/env python

"""ModernSitePreferences.py.

Modern and responsive interface for site settings in fpdb.
"""

import os
from functools import partial

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QPainter
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

import DetectInstalledSites
from loggingFpdb import get_logger

log = get_logger("modern_site_preferences")


class ModernSiteCard(QFrame):
    """Modern widget to display a site's settings."""

    def __init__(self, site_name, site_config, site_id=None, parent=None) -> None:
        super().__init__(parent)
        self.site_name = site_name
        self.site_config = site_config
        self.site_id = site_id
        self.parent_dialog = parent

        self.setFrameStyle(QFrame.NoFrame)
        # Minimal style, will be applied later if needed
        self._style_applied = False

        self.setup_ui()

    def apply_styles(self) -> None:
        """Apply styles (called only when visible)."""
        if not self._style_applied:
            self.setStyleSheet(
                """
                ModernSiteCard {
                    border: 1px solid rgba(128, 128, 128, 0.3);
                    border-radius: 8px;
                    background-color: rgba(255, 255, 255, 0.05);
                    padding: 15px;
                    margin: 5px;
                }
                ModernSiteCard:hover {
                    border: 1px solid rgba(128, 128, 128, 0.5);
                    background-color: rgba(255, 255, 255, 0.08);
                }
            """,
            )
            self._style_applied = True

    def showEvent(self, event) -> None:
        """Called when the widget becomes visible."""
        super().showEvent(event)
        self.apply_styles()

    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Header with site name and toggle
        header_layout = QHBoxLayout()

        # Icon and site name
        site_label = QLabel(f"<b>{self.site_name}</b>")
        site_label.setProperty("class", "h3")
        header_layout.addWidget(site_label)

        # Site ID badge
        if self.site_id:
            id_badge = QLabel(f"ID: {self.site_id}")
            id_badge.setProperty("class", "badge")
            header_layout.addWidget(id_badge)

        header_layout.addStretch()

        # Toggle switch to enable/disable
        self.enable_toggle = ModernToggleSwitch()
        self.enable_toggle.setChecked(getattr(self.site_config, "enabled", False))
        self.enable_toggle.toggled.connect(self.on_toggle_changed)
        header_layout.addWidget(self.enable_toggle)

        layout.addLayout(header_layout)

        # Main content (hidden if disabled)
        self.content_widget = QWidget()
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # Screen name
        name_layout = QHBoxLayout()
        name_icon = QLabel("👤")
        name_icon.setProperty("emoji", "true")
        name_layout.addWidget(name_icon)

        name_label = QLabel("Screen Name:")
        name_label.setMinimumWidth(120)
        name_layout.addWidget(name_label)

        self.screen_name_input = QLineEdit()
        self.screen_name_input.setText(getattr(self.site_config, "screen_name", ""))
        self.screen_name_input.setPlaceholderText("Enter your username")
        # Let qt_material handle the style
        self.screen_name_input.setProperty("class", "outlined")
        name_layout.addWidget(self.screen_name_input)

        content_layout.addLayout(name_layout)

        # Hand History Path
        hh_layout = QHBoxLayout()
        hh_icon = QLabel("📁")
        hh_icon.setProperty("emoji", "true")
        hh_layout.addWidget(hh_icon)

        hh_label = QLabel("Hand History:")
        hh_label.setMinimumWidth(120)
        hh_layout.addWidget(hh_label)

        self.hh_path_input = QLineEdit()
        self.hh_path_input.setText(getattr(self.site_config, "HH_path", ""))
        self.hh_path_input.setPlaceholderText("Path to hand history files")
        # Let qt_material handle the style
        self.hh_path_input.setProperty("class", "outlined")
        hh_layout.addWidget(self.hh_path_input)

        self.hh_browse_btn = QPushButton("Browse")
        # Style that adapts automatically to the theme
        self.hh_browse_btn.setStyleSheet("")  # Let qt_material handle the style
        self.hh_browse_btn.clicked.connect(partial(self.browse_clicked, self.hh_path_input))
        hh_layout.addWidget(self.hh_browse_btn)

        content_layout.addLayout(hh_layout)

        # Tournament Summary Path
        ts_layout = QHBoxLayout()
        ts_icon = QLabel("🏆")
        ts_icon.setProperty("emoji", "true")
        ts_layout.addWidget(ts_icon)

        ts_label = QLabel("Tournament:")
        ts_label.setMinimumWidth(120)
        ts_layout.addWidget(ts_label)

        self.ts_path_input = QLineEdit()
        self.ts_path_input.setText(getattr(self.site_config, "TS_path", ""))
        self.ts_path_input.setPlaceholderText("Path to tournament summaries")
        # Let qt_material handle the style
        self.ts_path_input.setProperty("class", "outlined")
        ts_layout.addWidget(self.ts_path_input)

        self.ts_browse_btn = QPushButton("Browse")
        # Style that adapts automatically to the theme
        self.ts_browse_btn.setStyleSheet("")  # Let qt_material manage the style
        self.ts_browse_btn.clicked.connect(partial(self.browse_clicked, self.ts_path_input))
        ts_layout.addWidget(self.ts_browse_btn)

        content_layout.addLayout(ts_layout)

        # Detect button (if supported)
        if self.is_site_detectable():
            detect_layout = QHBoxLayout()
            detect_layout.addStretch()

            self.detect_btn = QPushButton("🔍 Auto-Detect Paths")
            # Use the primary style from qt_material
            self.detect_btn.setProperty("class", "primary")
            self.detect_btn.setStyleSheet("")  # Let qt_material manage the style
            self.detect_btn.clicked.connect(self.detect_clicked)
            detect_layout.addWidget(self.detect_btn)

            detect_layout.addStretch()
            content_layout.addLayout(detect_layout)

        layout.addWidget(self.content_widget)

        # Update content visibility
        self.update_content_visibility()

    def on_toggle_changed(self, checked) -> None:
        """Handle toggle state change."""
        self.update_content_visibility()
        # Auto-enable if typing in the screen name field
        if checked and self.screen_name_input.text() == "YOUR SCREEN NAME HERE":
            self.screen_name_input.clear()
            self.screen_name_input.setFocus()

        # Update the set of enabled sites in the parent dialog
        if hasattr(self.parent_dialog, "enabled_sites"):
            if checked:
                self.parent_dialog.enabled_sites.add(self.site_name)
            else:
                self.parent_dialog.enabled_sites.discard(self.site_name)
                # If the site is disabled and visible, hide it and update
                if self.site_name in self.parent_dialog.visible_cards:
                    self.parent_dialog.filter_sites()

    def update_content_visibility(self) -> None:
        """Show/hide content based on toggle state."""
        self.content_widget.setVisible(self.enable_toggle.isChecked())

    def browse_clicked(self, path_input) -> None:
        """Open folder selection dialog."""
        current_path = path_input.text()
        new_path = QFileDialog.getExistingDirectory(
            self,
            f"Select {self.site_name} folder",
            current_path if current_path else os.path.expanduser("~"),
        )
        if new_path:
            path_input.setText(new_path)
            # Auto-enable the site if a path is selected
            if not self.enable_toggle.isChecked():
                self.enable_toggle.setChecked(True)

    def is_site_detectable(self):
        """Check if the site is detectable."""
        detector = DetectInstalledSites.DetectInstalledSites()
        network_name = self.get_network_for_skin(self.site_name)
        return network_name in detector.supportedSites

    def get_network_for_skin(self, site_name):
        """Map a skin to its parent network for detection."""
        # Use the existing logic from fpdb.pyw
        if site_name.startswith("PokerStars"):
            return "PokerStars"
        if site_name == "PMU Poker":
            # PMU Poker standard (iPoker)
            return "iPoker"  # PMU Poker is on iPoker network
        if site_name == "PMU Poker (PartyPoker)":
            # PMU Poker on PartyPoker network (old version)
            return "PartyGaming"  # PMU Poker PartyPoker version uses PartyGaming detector
        if site_name in ["FDJ Poker", "Poker770", "NetBet Poker", "En ligne"]:
            return "iPoker"
        if site_name in ["Americas Cardroom", "ACR Poker", "WinningPoker"]:
            return "ACR"
        if site_name in ["PartyPoker", "Party Poker", "Bwin Poker"]:
            return "PartyGaming"
        return site_name

    def detect_clicked(self) -> None:
        """Automatically detect paths."""
        detector = DetectInstalledSites.DetectInstalledSites()
        detection_site = self.get_network_for_skin(self.site_name)

        if detection_site == "PokerStars":
            all_variants = detector.get_all_pokerstars_variants()
            if all_variants:
                matching_variant = None
                for variant in all_variants:
                    variant_name = variant.get("variant", "PokerStars")
                    if variant_name.replace(".", "") == self.site_name.replace(".", ""):
                        matching_variant = variant
                        break

                if matching_variant:
                    self.apply_detection_results(matching_variant)
                    self.show_detection_success()
                    return
                if all_variants:
                    # Use the first found
                    self.apply_detection_results(all_variants[0])
                    self.show_detection_info(all_variants)
                    return

        elif detection_site == "iPoker":
            # Special handling for iPoker skins
            all_ipoker_skins = detector.get_all_ipoker_skins()
            if all_ipoker_skins:
                # Look for the specific skin we want
                matching_skin = None
                for skin_data in all_ipoker_skins:
                    skin_name = skin_data.get("skin", "")
                    if skin_name == self.site_name:
                        matching_skin = skin_data
                        break

                if matching_skin:
                    self.apply_detection_results(matching_skin)
                    self.show_detection_success()
                    return
                if all_ipoker_skins:
                    # No exact match, use the first detected iPoker skin
                    self.apply_detection_results(all_ipoker_skins[0])
                    self.show_detection_info_ipoker(all_ipoker_skins)
                    return

        elif detection_site == "PartyGaming":
            # Special handling for PartyGaming skins (including PMU Poker PartyPoker)
            all_party_skins = detector.get_all_partypoker_skins()
            if all_party_skins:
                # Look for the specific skin we want
                matching_skin = None
                for skin_data in all_party_skins:
                    skin_name = skin_data.get("skin", "")
                    if skin_name == self.site_name or (
                        self.site_name == "PMU Poker (PartyPoker)" and skin_name == "PMU Poker (PartyPoker)"
                    ):
                        matching_skin = skin_data
                        break

                if matching_skin:
                    self.apply_detection_results(matching_skin)
                    self.show_detection_success()
                    return
                if all_party_skins:
                    # No exact match, use the first detected PartyGaming skin
                    self.apply_detection_results(all_party_skins[0])
                    self.show_detection_info_party(all_party_skins)
                    return

        # General case
        if detection_site in detector.sitestatusdict and detector.sitestatusdict[detection_site]["detected"]:
            self.apply_detection_results(detector.sitestatusdict[detection_site])
            self.show_detection_success()
        else:
            self.show_detection_failure()

    def apply_detection_results(self, detection_data) -> None:
        """Apply detection results."""
        self.screen_name_input.setText(detection_data["heroname"])
        self.hh_path_input.setText(detection_data["hhpath"])

        # For tournament path: use tspath if provided, otherwise use hhpath
        # Many sites (like PokerStars, Winamax) use the same folder for both
        tspath = detection_data.get("tspath", "")
        if tspath:
            self.ts_path_input.setText(tspath)
        else:
            # If no separate tournament path, use the same as hand history path
            self.ts_path_input.setText(detection_data["hhpath"])

        # Auto-enable the site
        if not self.enable_toggle.isChecked():
            self.enable_toggle.setChecked(True)

    def show_detection_success(self) -> None:
        """Show a success message."""
        QToolTip.showText(
            self.detect_btn.mapToGlobal(self.detect_btn.rect().center()),
            "✅ Paths detected successfully!",
            self.detect_btn,
            self.detect_btn.rect(),
            2000,
        )

    def show_detection_info(self, variants) -> None:
        """Show information about detected variants."""
        variants_names = [v.get("variant", "PokerStars") for v in variants]
        QMessageBox.information(
            self,
            "PokerStars Detection",
            f"Detected variants: {', '.join(variants_names)}\nApplied configuration from the first variant found.",
        )

    def show_detection_failure(self) -> None:
        """Show a failure message."""
        QToolTip.showText(
            self.detect_btn.mapToGlobal(self.detect_btn.rect().center()),
            "❌ No installation detected",
            self.detect_btn,
            self.detect_btn.rect(),
            2000,
        )

    def show_detection_success_with_network(self, network) -> None:
        """Show a success message with network info."""
        QToolTip.showText(
            self.detect_btn.mapToGlobal(self.detect_btn.rect().center()),
            f"✅ Paths detected successfully!\nNetwork: {network}",
            self.detect_btn,
            self.detect_btn.rect(),
            3000,
        )

    def show_wrong_network_detected(self, found_network, expected_network) -> None:
        """Show a message when wrong network version is detected."""
        QMessageBox.warning(
            self,
            "Wrong Network Version",
            f"PMU Poker was detected on the {found_network} network,\n"
            f"but this configuration is for the {expected_network} network.\n\n"
            f"Please use the correct PMU Poker configuration for your installation.",
        )

    def show_detection_info_ipoker(self, skins) -> None:
        """Show information about detected iPoker skins."""
        skin_names = [s.get("skin", "Unknown") for s in skins]
        QMessageBox.information(
            self,
            "iPoker Detection",
            f"Detected iPoker skins: {', '.join(skin_names)}\n" f"Applied configuration from the first skin found.",
        )

    def show_detection_info_party(self, skins) -> None:
        """Show information about detected PartyGaming skins."""
        skin_names = [s.get("skin", "Unknown") for s in skins]
        QMessageBox.information(
            self,
            "PartyGaming Detection",
            f"Detected PartyGaming skins: {', '.join(skin_names)}\n"
            f"Applied configuration from the first skin found.",
        )

    def get_values(self):
        """Get current values."""
        return {
            "enabled": self.enable_toggle.isChecked(),
            "screen_name": self.screen_name_input.text(),
            "hh_path": self.hh_path_input.text(),
            "ts_path": self.ts_path_input.text(),
        }


class ModernToggleSwitch(QCheckBox):
    """Modern toggle switch, iOS/Android style."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(50, 25)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Colors based on the theme palette
        palette = self.palette()
        if self.isChecked():
            bg_color = palette.highlight().color()
            handle_color = palette.highlightedText().color()
        else:
            bg_color = palette.mid().color()
            handle_color = palette.base().color()

        # Draw the background
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), self.height() / 2, self.height() / 2)

        # Handle position
        handle_x = self.width() - self.height() + 2 if self.isChecked() else 2

        # Draw the handle
        painter.setBrush(QBrush(handle_color))
        painter.drawEllipse(handle_x, 2, self.height() - 4, self.height() - 4)


class ModernSitePreferencesDialog(QDialog):
    """Modern dialog for site preferences."""

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.site_cards = {}
        self.site_data = {}  # Store data without creating widgets
        self.visible_cards = set()  # Keep track of visible cards
        self.enabled_sites = set()  # Initialize the set of enabled sites

        self.setWindowTitle("Site Preferences")
        self.setMinimumSize(900, 600)
        self.resize(1000, 700)

        # Minimal style - let qt_material handle most styles
        self.setStyleSheet(
            """
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                border: none;
                width: 12px;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                background: rgba(128, 128, 128, 0.3);
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(128, 128, 128, 0.5);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
        """,
        )

        self.setup_ui()
        self.load_sites()

    def setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header_layout = QVBoxLayout()

        title = QLabel("Site Preferences")
        title.setProperty("class", "h1")
        header_layout.addWidget(title)

        subtitle = QLabel("Configure your poker sites and usernames")
        subtitle.setProperty("class", "subtitle")
        header_layout.addWidget(subtitle)

        main_layout.addLayout(header_layout)

        # Search bar and filters
        filter_layout = QHBoxLayout()

        # Search
        search_icon = QLabel("🔍")
        search_icon.setProperty("emoji", "true")
        filter_layout.addWidget(search_icon)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search sites...")
        # Use qt_material style for search
        self.search_input.setProperty("class", "search")
        self.search_input.textChanged.connect(self.filter_sites)
        filter_layout.addWidget(self.search_input)

        filter_layout.addSpacing(20)

        # Note: Search only works on enabled sites
        search_note = QLabel("(search in enabled sites only)")
        search_note.setProperty("class", "caption")
        filter_layout.addWidget(search_note)

        filter_layout.addStretch()

        main_layout.addLayout(filter_layout)

        # Scrollable area for sites
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.sites_container = QWidget()
        self.sites_layout = QVBoxLayout(self.sites_container)
        self.sites_layout.setSpacing(10)

        scroll_area.setWidget(self.sites_container)
        main_layout.addWidget(scroll_area)

        # Action buttons
        button_layout = QHBoxLayout()

        # Auto-detect button
        detect_all_btn = QPushButton("🔍 Auto-Detect All Visible Sites")
        detect_all_btn.clicked.connect(self.detect_all_sites)
        detect_all_btn.setProperty("class", "primary")
        button_layout.addWidget(detect_all_btn)

        button_layout.addStretch()

        # Save/Cancel buttons
        save_btn = QPushButton("Save Changes")
        save_btn.clicked.connect(self.accept)
        save_btn.setProperty("class", "primary")

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(save_btn)

        main_layout.addLayout(button_layout)

    def load_sites(self) -> None:
        """Load site data (without creating widgets)."""
        # Clear existing sites
        for card in self.site_cards.values():
            card.deleteLater()
        self.site_cards.clear()
        self.site_data.clear()
        self.visible_cards.clear()

        # Load only sites that exist in the configuration
        # and pre-calculate which sites are enabled for optimization
        self.enabled_sites = set()

        # Use supported_sites directly because site_ids may be empty
        # if the database is not connected
        for site_name, site_config in self.config.supported_sites.items():
            self.site_data[site_name] = {
                "config": site_config,
                "id": (self.config.site_ids.get(site_name) if self.config.site_ids else None),
            }
            if getattr(site_config, "enabled", False):
                self.enabled_sites.add(site_name)

        # Add a spacer at the end
        self.sites_layout.addStretch()

        # Apply the initial filter (will only create cards for enabled sites)
        self.filter_sites()

    def filter_sites(self) -> None:
        """Filter sites - search only among enabled sites."""
        search_text = self.search_input.text().lower()

        # Determine which sites should be visible
        # Use the pre-calculated set of enabled sites for optimization
        if search_text:
            sites_to_show = {site for site in self.enabled_sites if search_text in site.lower()}
        else:
            sites_to_show = self.enabled_sites.copy()

        # Hide cards that should no longer be visible
        for site_name in list(self.visible_cards):
            if site_name not in sites_to_show:
                if site_name in self.site_cards:
                    self.site_cards[site_name].hide()
                self.visible_cards.remove(site_name)

        # Create and show new cards as needed
        for site_name in sorted(sites_to_show):
            if site_name not in self.visible_cards:
                if site_name not in self.site_cards:
                    # Create the card only if it doesn't exist
                    data = self.site_data[site_name]
                    card = ModernSiteCard(site_name, data["config"], data["id"], self)
                    # Insert at the correct position (alphabetical order)
                    index = sorted(self.visible_cards | {site_name}).index(site_name)
                    self.sites_layout.insertWidget(index, card)
                    self.site_cards[site_name] = card
                else:
                    # Show the existing card again
                    self.site_cards[site_name].show()
                self.visible_cards.add(site_name)

    def detect_all_sites(self) -> None:
        """Detect all possible sites."""
        detected_count = 0
        for site_name in self.visible_cards:
            if site_name in self.site_cards:
                card = self.site_cards[site_name]
                if card.is_site_detectable():
                    card.detect_clicked()
                    detected_count += 1

        if detected_count > 0:
            QMessageBox.information(
                self,
                "Detection Complete",
                f"Attempted detection for {detected_count} sites.\n" "Check individual sites for results.",
            )
        else:
            QMessageBox.information(
                self,
                "No Detectable Sites",
                "No detectable sites found in the current view.",
            )

    def is_site_configured(self, card):
        """Check if a site is configured."""
        try:
            values = card.get_values()
            return (
                values["screen_name"]
                and values["screen_name"] != "YOUR SCREEN NAME HERE"
                and values["hh_path"]
                and len(values["hh_path"].strip()) > 0
            )
        except Exception:
            return False

    def get_changes(self):
        """Get all changes made."""
        changes = {}
        for site_name, card in self.site_cards.items():
            changes[site_name] = card.get_values()
        return changes
