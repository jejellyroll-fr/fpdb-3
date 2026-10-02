"""Send a hand's preflop to PreflopAdvisor for a solver review (#328).

The Replayer and the Hand Viewer offer the same review; this module holds the
dialog so the two cannot drift apart. What the hand is turned into lives in
:mod:`fpdb_3_legacy.hand_review_payload` and has no Qt dependency.

The dialog saves or copies the document, or opens it straight in PreflopAdvisor
(#413): the document is written to a temporary folder and PreflopAdvisor is
started on it with ``--review``.
"""

from __future__ import annotations

import datetime
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

from PySide6.QtCore import QProcess
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
    LaunchError,
    PreflopAdvisorTransport,
    build_hand_review,
    decision_at,
    dumps,
    preflop_advisor_command,
    review_document,
    summary_lines,
)
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("hand_review_dialog")

#: The prefix of the folder documents opened in PreflopAdvisor are written to.
REVIEW_FOLDER_PREFIX = "fpdb-hand-reviews-"


def start_detached(program: str, arguments: list[str]) -> bool:
    """Start *program* on its own, without a shell; whether it started."""
    started = QProcess.startDetached(program, arguments)
    # PySide6 returns (started, pid); older bindings returned the flag alone.
    return bool(started[0] if isinstance(started, tuple) else started)


def add_review_action(
    menu: QMenu,
    hand: Any,
    parent: QWidget | None = None,
    *,
    fpdb_hand_id: int | None = None,
    config: Any = None,
) -> None:
    """Append the solver review entry to *menu*."""
    menu.addAction(_("Solver review (PreflopAdvisor)...")).triggered.connect(
        lambda: HandReviewDialog(hand, parent, fpdb_hand_id=fpdb_hand_id, config=config).exec()
    )


class HandReviewDialog(QDialog):
    """Show what PreflopAdvisor will be sent, and save or copy it."""

    #: This session's folder for documents opened in PreflopAdvisor, made once and reused,
    #: so a hand opened again rewrites its own file instead of adding another.
    _review_folder: ClassVar[Path | None] = None

    def __init__(
        self,
        hand: Any,
        parent: QWidget | None = None,
        *,
        hero: str | None = None,
        fpdb_hand_id: int | None = None,
        applied_preflop: int | None = None,
        config: Any = None,
        start: Callable[[str, list[str]], bool] = start_detached,
    ) -> None:
        super().__init__(parent)
        #: Where PreflopAdvisor's location is remembered (``<general preflop_advisor>``).
        self.config = config
        self.start = start
        self.setWindowTitle(_("Solver review"))
        self.resize(640, 520)
        self.review: HandReview | None = None
        self.error: str | None = None
        self.selected: int | None = None
        try:
            self.review = build_hand_review(hand, hero=hero, fpdb_hand_id=fpdb_hand_id)
        except HandReviewError as exc:
            self.error = str(exc)
        except Exception as exc:  # noqa: BLE001 - shown, never swallowed by the Qt slot that opened the dialog.
            log.exception("Could not describe the hand for a solver review")
            self.error = str(exc) or type(exc).__name__
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
            _("Open it in PreflopAdvisor, or save the file and load it there with Review Hands > Load a hand review.")
            if self.error is None
            else _("This hand cannot be sent to PreflopAdvisor.")
        )
        hint.setWordWrap(True)

        buttons = self._buttons()

        layout = QVBoxLayout(self)
        layout.addLayout(scope_row)
        layout.addWidget(self.preview, 1)
        layout.addWidget(hint)
        layout.addWidget(buttons)
        self.refresh()

    def _buttons(self) -> QDialogButtonBox:
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.open_button = buttons.addButton(_("Open in PreflopAdvisor"), QDialogButtonBox.ButtonRole.ActionRole)
        self.open_button.clicked.connect(self.open_in_preflop_advisor)
        self.save_button = buttons.addButton(_("Save for PreflopAdvisor..."), QDialogButtonBox.ButtonRole.ActionRole)
        self.copy_button = buttons.addButton(_("Copy JSON"), QDialogButtonBox.ButtonRole.ActionRole)
        self.save_button.clicked.connect(self.save)
        self.copy_button.clicked.connect(self.copy)
        buttons.rejected.connect(self.reject)
        for button in (self.open_button, self.save_button, self.copy_button):
            button.setEnabled(self.error is None)
        return buttons

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

    # -- opening in PreflopAdvisor ----------------------------------------------
    def configured_path(self) -> str | None:
        general = getattr(self.config, "general", None) or {}
        return general.get("preflop_advisor") or None

    def review_path(self) -> Path:
        """A new file for this review, which PreflopAdvisor is then started on.

        In a folder ``mkdtemp`` makes once per session -- an unpredictable name, readable and
        writable by this user only -- rather than a fixed name in the shared temporary
        directory, where another user could have made it first and left links in it. Each
        launch gets its own file (``mkstemp``): a PreflopAdvisor still starting on the first
        one must not find it rewritten by a second click on the same hand.
        """
        folder = HandReviewDialog._review_folder
        if folder is None or not folder.is_dir():
            folder = Path(tempfile.mkdtemp(prefix=REVIEW_FOLDER_PREFIX))
            HandReviewDialog._review_folder = folder
        stem = Path(self.default_name()).stem
        handle, name = tempfile.mkstemp(prefix=f"{stem}-", suffix=".json", dir=folder)
        os.close(handle)
        return Path(name)

    def open_in_preflop_advisor(self) -> None:
        """Start PreflopAdvisor on this review, asking where it is when it cannot be found.

        A program the user picks is remembered only once it has started, and a remembered
        one that no longer starts is forgotten: either would otherwise be retried, and asked
        about, on every review that follows. Forgotten, the next review looks on the PATH.
        """
        located: str | None = None
        configured = self.configured_path()
        command = preflop_advisor_command(configured)
        # Whether *command* is the remembered program, rather than one found on the PATH.
        remembered = bool(configured) and command == preflop_advisor_command(configured, which=lambda _name: None)
        if command is None:
            located, command = self.locate_preflop_advisor()
        while command is not None:
            try:
                PreflopAdvisorTransport(command, self.review_path(), self.start).send(self.document())
            except LaunchError as exc:
                log.warning("Could not start PreflopAdvisor: %s", exc)
                if remembered:
                    self.remember_preflop_advisor(None)
                    remembered = False
                answer = QMessageBox.question(
                    self,
                    _("Solver review"),
                    _("PreflopAdvisor could not be started:\n%s\n\nLocate it?") % exc,
                )
                located, command = (
                    self.locate_preflop_advisor() if answer == QMessageBox.StandardButton.Yes else (None, None)
                )
                continue
            except OSError as exc:
                # Another program would not help: the review itself could not be written.
                log.warning("Could not write the hand review for PreflopAdvisor: %s", exc)
                QMessageBox.warning(self, _("Solver review"), _("Could not save the hand review:\n%s") % exc)
                return
            if located:
                self.remember_preflop_advisor(located)
            self.accept()
            return

    def locate_preflop_advisor(self) -> tuple[str | None, list[str] | None]:
        """Ask where PreflopAdvisor is: the path picked and how to start it, or nothing."""
        path, _selected = QFileDialog.getOpenFileName(self, _("Locate PreflopAdvisor"))
        if not path:
            return None, None
        command = preflop_advisor_command(path, which=lambda _name: None)
        if command is None:
            QMessageBox.warning(self, _("Solver review"), _("%s is not a program that can be started.") % path)
            return None, None
        return path, command

    def remember_preflop_advisor(self, path: str | None) -> None:
        """Save where PreflopAdvisor is, or forget it (``None``)."""
        if self.config is None or not hasattr(self.config, "set_preflop_advisor_path"):
            return
        try:
            self.config.set_preflop_advisor_path(path)
        except OSError as exc:
            # Only the configuration could not be written; the review itself is unaffected.
            log.warning("Could not save where PreflopAdvisor is: %s", exc)
