#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ConfigReloadWidget.py

Widget to display configuration reload status in the status bar.
"""

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPixmap
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QWidget

from ConfigurationManager import ConfigurationManager
from loggingFpdb import get_logger

log = get_logger("configwidget")


class ConfigReloadWidget(QWidget):
    """Widget displaying configuration reload status"""

    # Signals
    reload_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.config_manager = ConfigurationManager()

    def setup_ui(self):
        """Configure widget interface"""
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 0, 5, 0)
        self.setLayout(layout)

        # Status icon
        self.status_icon = QLabel()
        self.status_icon.setFixedSize(16, 16)
        self.update_status_icon("idle")
        layout.addWidget(self.status_icon)

        # Status label
        self.status_label = QLabel("Configuration up to date")
        layout.addWidget(self.status_label)

        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumHeight(15)
        self.progress_bar.setMaximumWidth(100)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # Reload button
        self.reload_button = QPushButton("↻")
        self.reload_button.setToolTip("Reload configuration")
        self.reload_button.setMaximumSize(20, 20)
        self.reload_button.clicked.connect(self.on_reload_clicked)
        layout.addWidget(self.reload_button)

        layout.addStretch()

    def update_status_icon(self, status):
        """Update icon according to status"""
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Colors by status
        colors = {
            "idle": QColor(0, 200, 0),  # Green
            "loading": QColor(255, 165, 0),  # Orange
            "error": QColor(255, 0, 0),  # Red
            "warning": QColor(255, 255, 0),  # Yellow
        }

        color = colors.get(status, colors["idle"])
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, 12, 12)
        painter.end()

        self.status_icon.setPixmap(pixmap)

    def on_reload_clicked(self):
        """Called when reload button is clicked"""
        self.reload_requested.emit()
        self.start_reload()

    def start_reload(self):
        """Start reload animation"""
        self.update_status_icon("loading")
        self.status_label.setText("Reloading...")
        self.progress_bar.show()
        self.progress_bar.setRange(0, 0)  # Indeterminate mode
        self.reload_button.setEnabled(False)

    def reload_complete(self, success, message, restart_required=False):
        """Called when reload is complete"""
        self.progress_bar.hide()
        self.reload_button.setEnabled(True)

        if success:
            if restart_required:
                self.update_status_icon("warning")
                self.status_label.setText("Restart required")
                self.status_label.setToolTip(message)
            else:
                self.update_status_icon("idle")
                self.status_label.setText("Configuration up to date")
                self.status_label.setToolTip(message)

                # Success animation
                self.flash_success()
        else:
            self.update_status_icon("error")
            self.status_label.setText("Reload error")
            self.status_label.setToolTip(message)

    def flash_success(self):
        """Flash animation to indicate success"""
        self.status_label.setStyleSheet("QLabel { background-color: #90EE90; }")
        QTimer.singleShot(500, lambda: self.status_label.setStyleSheet(""))

    def set_config_modified(self, modified=True):
        """Indicates if configuration has been modified"""
        if modified:
            self.status_label.setText("Configuration modified*")
            self.status_label.setToolTip(
                "Unsaved changes are present"
            )
        else:
            self.status_label.setText("Configuration up to date")
            self.status_label.setToolTip("")


class ConfigStatusBar(QWidget):
    """Extended status bar with configuration reload support"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()

    def setup_ui(self):
        """Configure status bar interface"""
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        # Main message
        self.message_label = QLabel()
        layout.addWidget(self.message_label)

        layout.addStretch()

        # Reload widget
        self.reload_widget = ConfigReloadWidget()
        self.reload_widget.reload_requested.connect(self.on_reload_requested)
        layout.addWidget(self.reload_widget)

    def showMessage(self, message, timeout=0):
        """Display a message in the status bar"""
        self.message_label.setText(message)
        if timeout > 0:
            QTimer.singleShot(timeout, lambda: self.message_label.setText(""))

    def on_reload_requested(self):
        """Called when reload is requested"""
        self.reload_widget.start_reload()

        # Delegate to main window
        if hasattr(self.main_window, "reload_config"):
            # Simulate asynchronous call
            QTimer.singleShot(100, self._do_reload)

    def _do_reload(self):
        """Perform reload"""
        try:
            # Call main window's reload_config
            self.main_window.reload_config()
            # Note: Result will be handled by callbacks
        except Exception as e:
            log.error(f"Error during reload: {e}")
            self.reload_widget.reload_complete(False, str(e))

    def notify_reload_complete(self, success, message, restart_required=False):
        """Notify reload completion"""
        self.reload_widget.reload_complete(success, message, restart_required)

    def set_config_modified(self, modified=True):
        """Indicates if configuration has been modified"""
        self.reload_widget.set_config_modified(modified)
