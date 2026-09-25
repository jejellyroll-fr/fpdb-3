"""Copy or save a hand in a readable, shareable form.

The Hand Viewer and the Replayer both offer the same share actions; this
module holds them so the two screens cannot drift apart. The rendering itself
lives in :mod:`fpdb_3_legacy.hand_share` and has no Qt dependency.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.hand_share import ShareOptions, render_hand, supports_bb_amounts
from fpdb_3_legacy.i18n import N_
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("hand_share_dialog")

_FORMAT_CHOICES = (
    ("text", N_("Plain text")),
    ("markdown", N_("Markdown")),
    ("bbcode", N_("Forum (BBCode)")),
)
_ANONYMIZE_CHOICES = (
    ("all", N_("Hide every name (Hero, Villain 1 ...)")),
    ("opponents", N_("Keep my name, hide opponents")),
    ("none", N_("Keep every name")),
)
_AMOUNT_CHOICES = (
    ("native", N_("Money / chips")),
    ("bb", N_("Big blinds")),
)
_EXTENSIONS = {"text": "txt", "markdown": "md", "bbcode": "txt"}
_METADATA = (
    ("site", N_("Site")),
    ("table", N_("Table name")),
    ("hand_id", N_("Hand number")),
    ("timestamp", N_("Date and time")),
    ("stacks", N_("Stacks")),
    ("results", N_("Showdown and results")),
    ("rake", N_("Rake")),
    ("cashout", N_("EV cashout")),
)


def copy_rendered(hand: Any, parent: QWidget | None = None, **options: Any) -> bool:
    """Render *hand* and put it on the clipboard; report failures to the user."""
    try:
        text = render_hand(hand, **options)
    except Exception as exc:  # noqa: BLE001 - any failure is shown, never swallowed by the Qt slot.
        log.exception("Could not render hand for sharing")
        QMessageBox.warning(parent, _("Share hand"), _("This hand could not be rendered:\n%s") % exc)
        return False
    QApplication.clipboard().setText(text)
    return True


def add_share_actions(menu: QMenu, hand: Any, parent: QWidget | None = None) -> None:
    """Append the quick copy entries and the share dialog to *menu*."""
    menu.addAction(_("Copy as text")).triggered.connect(lambda: copy_rendered(hand, parent, format="text"))
    menu.addAction(_("Copy as Markdown")).triggered.connect(lambda: copy_rendered(hand, parent, format="markdown"))
    bb_action = menu.addAction(_("Copy as Markdown in BB"))
    bb_action.triggered.connect(lambda: copy_rendered(hand, parent, format="markdown", amounts="bb"))
    bb_action.setEnabled(supports_bb_amounts(hand))
    menu.addAction(_("Share...")).triggered.connect(lambda: HandShareDialog(hand, parent).exec())


class HandShareDialog(QDialog):
    """Pick a format, what to hide, and copy or save the result."""

    def __init__(self, hand: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.hand = hand
        self.setWindowTitle(_("Share hand"))
        self.resize(720, 640)

        self.format_combo = self._combo(_FORMAT_CHOICES)
        self.anonymize_combo = self._combo(_ANONYMIZE_CHOICES)
        self.amounts_combo = self._combo(_AMOUNT_CHOICES)
        if not supports_bb_amounts(hand):
            self.amounts_combo.model().item(1).setEnabled(False)
            self.amounts_combo.setToolTip(_("This game has no big blind to count in."))

        form = QFormLayout()
        form.addRow(_("Format"), self.format_combo)
        form.addRow(_("Names"), self.anonymize_combo)
        form.addRow(_("Amounts"), self.amounts_combo)

        defaults = ShareOptions()
        self.checks: dict[str, QCheckBox] = {}
        details = QGroupBox(_("Include"))
        grid = QGridLayout(details)
        for index, (key, label) in enumerate(_METADATA):
            check = QCheckBox(_(label))
            check.setChecked(bool(getattr(defaults, key)))
            check.toggled.connect(self.refresh)
            self.checks[key] = check
            grid.addWidget(check, index // 2, index % 2)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        copy_button = buttons.addButton(_("Copy"), QDialogButtonBox.ButtonRole.ActionRole)
        save_button = buttons.addButton(_("Save..."), QDialogButtonBox.ButtonRole.ActionRole)
        copy_button.clicked.connect(self.copy)
        save_button.clicked.connect(self.save)
        buttons.rejected.connect(self.reject)

        top = QHBoxLayout()
        top.addLayout(form)
        top.addWidget(details)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.preview, 1)
        layout.addWidget(buttons)

        for combo in (self.format_combo, self.anonymize_combo, self.amounts_combo):
            combo.currentIndexChanged.connect(self.refresh)
        self.refresh()

    @staticmethod
    def _combo(choices: tuple[tuple[str, str], ...]) -> QComboBox:
        combo = QComboBox()
        for value, label in choices:
            combo.addItem(_(label), value)
        return combo

    def options(self) -> ShareOptions:
        return ShareOptions(
            format=self.format_combo.currentData(),
            anonymize=self.anonymize_combo.currentData(),
            amounts=self.amounts_combo.currentData(),
            **{key: check.isChecked() for key, check in self.checks.items()},
        )

    def rendered(self) -> str:
        return render_hand(self.hand, self.options())

    def refresh(self) -> None:
        try:
            self.preview.setPlainText(self.rendered())
        except Exception as exc:  # noqa: BLE001 - the preview says what went wrong instead of going blank.
            log.exception("Could not render hand preview")
            self.preview.setPlainText(_("This hand could not be rendered:\n%s") % exc)

    def copy(self) -> None:
        QApplication.clipboard().setText(self.preview.toPlainText())

    def save(self) -> None:
        extension = _EXTENSIONS[self.options().format]
        path, _selected = QFileDialog.getSaveFileName(
            self,
            _("Save hand"),
            f"hand.{extension}",
            f"*.{extension}",
        )
        if not path:
            return
        try:
            Path(path).write_text(self.preview.toPlainText(), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, _("Share hand"), _("Could not save the hand:\n%s") % exc)
