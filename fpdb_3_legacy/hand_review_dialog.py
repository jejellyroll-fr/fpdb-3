"""Send a hand's preflop to PreflopAdvisor for a solver review (#328).

The Replayer and the Hand Viewer offer the same review; this module holds the
dialog so the two cannot drift apart. What the hand is turned into lives in
:mod:`fpdb_3_legacy.hand_review_payload` and has no Qt dependency.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.hand_review_payload import (
    HandReview,
    HandReviewError,
    JsonFileTransport,
    build_hand_review,
    decision_at,
    dumps,
    review_document,
    summary_lines,
)
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("hand_review_dialog")


def add_review_action(
    menu: QMenu, hand: Any, parent: QWidget | None = None, *, fpdb_hand_id: int | None = None
) -> None:
    """Append the solver review entry to *menu*."""
    menu.addAction(_("Solver review (PreflopAdvisor)...")).triggered.connect(
        lambda: HandReviewDialog(hand, parent, fpdb_hand_id=fpdb_hand_id).exec()
    )


class HandReviewDialog(QDialog):
    """Show what PreflopAdvisor will be sent, and save or copy it."""

    def __init__(
        self,
        hand: Any,
        parent: QWidget | None = None,
        *,
        hero: str | None = None,
        fpdb_hand_id: int | None = None,
        applied_preflop: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Solver review"))
        self.resize(640, 520)
        self.review: HandReview | None = None
        self.error: str | None = None
        self.selected: int | None = None
        try:
            self.review = build_hand_review(hand, hero=hero, fpdb_hand_id=fpdb_hand_id)
        except HandReviewError as exc:
            self.error = str(exc)
        if self.review is not None and applied_preflop is not None:
            self.selected = decision_at(self.review, applied_preflop)

        self.decision_button = QRadioButton(_("This decision"))
        self.hand_button = QRadioButton(_("Every hero decision of the hand"))
        scope = QButtonGroup(self)
        scope.addButton(self.decision_button)
        scope.addButton(self.hand_button)
        self.decision_button.setEnabled(self.selected is not None)
        (self.decision_button if self.selected is not None else self.hand_button).setChecked(True)
        self.decision_button.toggled.connect(self.refresh)
        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel(_("Review:")))
        scope_row.addWidget(self.decision_button)
        scope_row.addWidget(self.hand_button)
        scope_row.addStretch(1)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        hint = QLabel(
            _("Save the file, then open it in PreflopAdvisor with Hand review > Load a hand review.")
            if self.error is None
            else _("This hand cannot be sent to PreflopAdvisor.")
        )
        hint.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.save_button = buttons.addButton(_("Save for PreflopAdvisor..."), QDialogButtonBox.ButtonRole.ActionRole)
        self.copy_button = buttons.addButton(_("Copy JSON"), QDialogButtonBox.ButtonRole.ActionRole)
        self.save_button.clicked.connect(self.save)
        self.copy_button.clicked.connect(self.copy)
        buttons.rejected.connect(self.reject)
        for button in (self.save_button, self.copy_button):
            button.setEnabled(self.error is None)

        layout = QVBoxLayout(self)
        layout.addLayout(scope_row)
        layout.addWidget(self.preview, 1)
        layout.addWidget(hint)
        layout.addWidget(buttons)
        self.refresh()

    def current_review(self) -> HandReview | None:
        if self.review is None:
            return None
        selected = self.selected if self.decision_button.isChecked() else None
        return self.review.with_selected_decision(selected)

    def document(self) -> dict[str, Any]:
        review = self.current_review()
        if review is None:
            raise HandReviewError("unavailable", self.error or "")
        generated = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        return review_document([review], generated_at=generated)

    def refresh(self) -> None:
        review = self.current_review()
        if review is None:
            self.preview.setPlainText(self.error or "")
            return
        self.preview.setPlainText("\n".join(summary_lines(review)))

    def copy(self) -> None:
        QApplication.clipboard().setText(dumps(self.document()))

    def default_name(self) -> str:
        review = self.review
        ident = (review.fpdb_hand_id or review.site_hand_no) if review is not None else "hand"
        return f"fpdb-hand-review-{ident}.json"

    def save(self) -> None:
        path, _selected = QFileDialog.getSaveFileName(
            self, _("Save hand review"), self.default_name(), _("Hand review (*.json)")
        )
        if not path:
            return
        try:
            JsonFileTransport(Path(path)).send(self.document())
        except OSError as exc:
            QMessageBox.warning(self, _("Solver review"), _("Could not save the hand review:\n%s") % exc)
