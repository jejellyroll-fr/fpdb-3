"""Tools ▸ Live capture: turn on, after reading what it does, a capture that reaches into a client (#451).

Each capture path of :mod:`fpdb_3_legacy.live_capture_consent` gets a box to
tick. Ticking one shows what it does, the account risk and that the room's
terms prevail, and turns it on only on an explicit yes. Unticking turns it off.
The capture windows ask through :func:`confirm` too, at the point of use.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import live_capture_consent
from fpdb_3_legacy.disabled_sites import is_site_disabled
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.live_capture_consent import Mechanism

#: The room each mechanism feeds: a room whose support is switched off has no
#: capture to turn on.
_ROOMS = {
    live_capture_consent.SWC_NATIVE.key: "SealsWithClubs",
    live_capture_consent.COINPOKER_PACKETS.key: "CoinPoker",
}


def confirm(mechanism: Mechanism, parent: QWidget | None = None, path: Path | None = None) -> bool:
    """Ask before turning ``mechanism`` on; record and return a yes."""
    if live_capture_consent.is_accepted(mechanism, path):
        return True
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(_("Turn on live capture?"))
    box.setText(_(mechanism.title))
    box.setInformativeText(live_capture_consent.statement(mechanism))
    turn_on = box.addButton(_("I understand, turn it on"), QMessageBox.ButtonRole.AcceptRole)
    box.addButton(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(QMessageBox.StandardButton.Cancel)
    box.exec()
    if box.clickedButton() is not turn_on:
        return False
    live_capture_consent.accept(mechanism, path)
    return True


def available_mechanisms() -> list[Mechanism]:
    """The mechanisms whose room fpdb supports, in an install that carries the captures."""
    if not live_capture_consent.capture_installed():
        return []
    return [
        mechanism
        for mechanism in live_capture_consent.MECHANISMS.values()
        if not is_site_disabled(_ROOMS.get(mechanism.key, ""))
    ]


class LiveCaptureDialog(QDialog):
    """One box per capture path: ticked when the user turned it on."""

    def __init__(self, config: Any = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = live_capture_consent.consent_path(getattr(config, "file", None))
        self.setWindowTitle(_("Live capture"))
        layout = QVBoxLayout(self)
        intro = QLabel(
            _(
                "fpdb imports the hand histories your rooms write. For a room that writes none, these "
                "captures read the hands from the client itself. Each is off until you turn it on."
            )
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.boxes: dict[str, QCheckBox] = {}
        if not live_capture_consent.capture_installed():
            missing = QLabel(str(live_capture_consent.CaptureNotInstalled()))
            missing.setWordWrap(True)
            layout.addWidget(missing)
        for mechanism in available_mechanisms():
            box = QCheckBox(_(mechanism.title))
            box.setChecked(live_capture_consent.is_accepted(mechanism, self.path))
            box.toggled.connect(lambda on, m=mechanism: self._toggled(m, on))
            explanation = QLabel(_(mechanism.what_happens))
            explanation.setWordWrap(True)
            explanation.setIndent(24)
            layout.addWidget(box)
            layout.addWidget(explanation)
            self.boxes[mechanism.key] = box

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _toggled(self, mechanism: Mechanism, on: bool) -> None:
        if not on:
            live_capture_consent.withdraw(mechanism, self.path)
            return
        if not confirm(mechanism, self, self.path):
            box = self.boxes[mechanism.key]
            box.blockSignals(True)
            box.setChecked(False)
            box.blockSignals(False)


def open_live_capture(config: Any, parent: Any = None) -> None:
    """Show the live capture window modally."""
    LiveCaptureDialog(config, parent).exec()
