"""The HUD process's own windows: the main window and the macOS permissions dialog."""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class HudMainWindow(QWidget):
    """Top-level HUD window with a typed close callback."""

    def __init__(self, on_close: Callable[[QCloseEvent], None]) -> None:
        """Initialize the window and retain its close callback."""
        super().__init__(
            None,
            Qt.WindowType.Dialog | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowCloseButtonHint,
        )
        self._on_close = on_close

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Forward the native close event to the HUD owner."""
        self._on_close(event)



class MacOSPermissionsDialog(QDialog):
    """Explicit, non-modal onboarding for the HUD's macOS permissions.

    Constructing or refreshing this dialog only runs side-effect-free
    preflights. Native prompts and System Settings are reached exclusively from
    the corresponding user-operated buttons.
    """

    status_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the permission status and action rows."""
        super().__init__(parent)
        self.setWindowTitle("FPDB macOS Permissions")
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "FPDB checks these permissions without requesting them. "
            "Use the buttons below only when you want macOS to prompt or open System Settings.",
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        screen_note = QLabel(
            "macOS groups this under Screen & System Audio Recording. "
            "FPDB reads window metadata only and does not request microphone access.",
        )
        screen_note.setWordWrap(True)
        layout.addWidget(screen_note)

        grid = QGridLayout()
        grid.addWidget(QLabel("Permission"), 0, 0)
        grid.addWidget(QLabel("Status"), 0, 1)
        grid.addWidget(QLabel("Actions"), 0, 2, 1, 2)

        self.screen_status_label = QLabel()
        self.screen_request_button = QPushButton("Request Screen Recording")
        self.screen_settings_button = QPushButton("Open Screen Recording Settings")
        grid.addWidget(QLabel("Screen Recording"), 1, 0)
        grid.addWidget(self.screen_status_label, 1, 1)
        grid.addWidget(self.screen_request_button, 1, 2)
        grid.addWidget(self.screen_settings_button, 1, 3)

        self.accessibility_status_label = QLabel()
        self.accessibility_request_button = QPushButton("Request Accessibility")
        self.accessibility_settings_button = QPushButton("Open Accessibility Settings")
        grid.addWidget(QLabel("Accessibility"), 2, 0)
        grid.addWidget(self.accessibility_status_label, 2, 1)
        grid.addWidget(self.accessibility_request_button, 2, 2)
        grid.addWidget(self.accessibility_settings_button, 2, 3)

        self.app_data_status_label = QLabel()
        self.app_data_info_label = QLabel(
            "Informational only: macOS prompts on the first protected Winamax file access, "
            "using the bundle's NSAppDataUsageDescription.",
        )
        self.app_data_info_label.setWordWrap(True)
        grid.addWidget(QLabel("App Data"), 3, 0)
        grid.addWidget(self.app_data_status_label, 3, 1)
        grid.addWidget(self.app_data_info_label, 3, 2, 1, 2)
        grid.setColumnStretch(2, 1)
        layout.addLayout(grid)

        restart_note = QLabel(
            "After changing Screen Recording, quit and reopen FPDB yourself if table titles remain unavailable. "
            "FPDB never restarts automatically.",
        )
        restart_note.setWordWrap(True)
        layout.addWidget(restart_note)

        button_row = QHBoxLayout()
        self.recheck_button = QPushButton("Recheck")
        self.close_button = QPushButton("Close")
        button_row.addWidget(self.recheck_button)
        button_row.addStretch(1)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)

        self.screen_request_button.clicked.connect(self._request_screen_recording)
        self.screen_settings_button.clicked.connect(self._open_screen_recording_settings)
        self.accessibility_request_button.clicked.connect(self._request_accessibility)
        self.accessibility_settings_button.clicked.connect(self._open_accessibility_settings)
        self.recheck_button.clicked.connect(self.refresh_status)
        self.close_button.clicked.connect(self.hide)

    @staticmethod
    def _binary_status(granted: bool) -> str:
        return "Granted" if granted else "Missing"

    def set_status(self, status: Any) -> None:
        """Render an already-computed permission snapshot without side effects."""
        self.screen_status_label.setText(self._binary_status(status.screen_recording))
        self.accessibility_status_label.setText(self._binary_status(status.accessibility))
        if status.app_data is None:
            self.app_data_status_label.setText("Not preflightable")
        else:
            self.app_data_status_label.setText(self._binary_status(status.app_data))
        self.screen_request_button.setEnabled(not status.screen_recording)
        self.accessibility_request_button.setEnabled(not status.accessibility)

    def refresh_status(self) -> Any:
        """Run diagnostic-only preflights and update the three status rows."""
        from fpdb.infrastructure.platform import permissions

        status = permissions.get_status()
        self.set_status(status)
        self.status_changed.emit(status)
        return status

    def _request_screen_recording(self) -> None:
        """Request Screen Recording after an explicit button click."""
        from fpdb.infrastructure.platform import permissions

        permissions.request_screen_recording_permission()
        self.refresh_status()

    def _request_accessibility(self) -> None:
        """Request Accessibility after an explicit button click."""
        from fpdb.infrastructure.platform import permissions

        permissions.request_accessibility_permission(prompt=True)
        self.refresh_status()

    @staticmethod
    def _open_screen_recording_settings() -> None:
        from fpdb.infrastructure.platform import permissions

        permissions.open_screen_recording_settings()

    @staticmethod
    def _open_accessibility_settings() -> None:
        from fpdb.infrastructure.platform import permissions

        permissions.open_accessibility_settings()

