"""Import ▸ PokerTracker 4 Notes: bring PT4 player notes into fpdb (#618).

The dialog asks for PT4's database connection, previews what would change, then
imports. ``tracker_notes`` does the work; this only renders it.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from fpdb_3_legacy import tracker_notes
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("tracker_notes")

__all__ = ["GuiTrackerNotes"]


class GuiTrackerNotes(QDialog):
    """``config`` and ``sql`` are the main window's; ``read_notes`` and ``open_db`` are seams for tests."""

    def __init__(
        self,
        config: Any,
        sql: Any = None,
        parent: Any = None,
        read_notes: Any = None,
        open_db: Any = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.sql = sql
        self._read_notes = read_notes or self._read_pt4
        self._open_db = open_db or self._open_fpdb
        self.setWindowTitle(_("Import PokerTracker 4 notes"))

        from fpdb_3_legacy.pt4_adapter import Pt4Config

        defaults = Pt4Config.from_env()
        layout = QVBoxLayout(self)
        intro = QLabel(
            _(
                "fpdb reads the notes and player tags from PokerTracker 4's database, read-only. "
                "An fpdb note is never overwritten: the PT4 note is added after it. "
                "Notes on players fpdb has no hands of are listed, not imported: import the hands first.",
            ),
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.host = QLineEdit(defaults.host)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(defaults.port)
        self.user = QLineEdit(defaults.user)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.database = QLineEdit(defaults.database)
        form.addRow(_("Host"), self.host)
        form.addRow(_("Port"), self.port)
        form.addRow(_("User"), self.user)
        form.addRow(_("Password"), self.password)
        form.addRow(_("Database"), self.database)
        layout.addLayout(form)

        self.skip_existing = QCheckBox(_("Leave players who already have an fpdb note alone"))
        layout.addWidget(self.skip_existing)

        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        layout.addWidget(self.report)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.preview_button = QPushButton(_("Preview"))
        self.import_button = QPushButton(_("Import"))
        buttons.addButton(self.preview_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(self.import_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        self.preview_button.clicked.connect(lambda: self.run(dry_run=True))
        self.import_button.clicked.connect(lambda: self.run(dry_run=False))
        layout.addWidget(buttons)
        self.resize(640, 520)

    def _read_pt4(self) -> list[tracker_notes.TrackerNote]:
        from fpdb_3_legacy.pt4_adapter import Pt4Config, connect_pt4

        pt4 = Pt4Config(
            self.host.text().strip(),
            self.port.value(),
            self.user.text().strip(),
            self.password.text(),
            self.database.text().strip(),
        )
        with connect_pt4(pt4) as conn:
            return tracker_notes.read_pt4_notes(conn)

    def _open_fpdb(self) -> Any:
        from fpdb_3_legacy import Database

        return Database.Database(self.config, sql=self.sql)

    def run(self, *, dry_run: bool) -> tracker_notes.NotesReport | None:
        """Read PT4's notes and preview or import them; the report is shown either way."""
        try:
            notes = self._read_notes()
        except Exception as exc:  # noqa: BLE001 - any driver error is the user's to read, not a crash
            log.warning("Reading PT4 notes failed", exc_info=True)
            self.report.setPlainText(_("Could not read PokerTracker 4's database:\n%s") % exc)
            return None
        db = self._open_db()
        try:
            report = tracker_notes.apply_notes(
                db.connection,
                notes,
                placeholder=db.sql.query["placeholder"],
                on_existing="skip" if self.skip_existing.isChecked() else "append",
                network_rooms=tracker_notes.ipoker_rooms_of(self.config),
                dry_run=dry_run,
            )
        except Exception as exc:  # noqa: BLE001 - shown, and nothing half-written is committed
            log.warning("Importing PT4 notes failed", exc_info=True)
            db.connection.rollback()
            self.report.setPlainText(_("The import stopped on an error:\n%s") % exc)
            return None
        finally:
            db.close_connection()
        self.report.setPlainText(tracker_notes.format_report(report))
        return report
