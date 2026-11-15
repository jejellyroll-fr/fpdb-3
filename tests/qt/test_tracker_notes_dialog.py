"""Import ▸ PokerTracker 4 Notes (#618): preview, import, and a PT4 that cannot be read.

PT4 is replaced by the dialog's ``read_notes`` seam, fpdb's database by an
in-memory SQLite one holding fpdb's own ``Players`` table.
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QLineEdit

from fpdb_3_legacy.sql_schema_player import player_schema_queries
from fpdb_3_legacy.tracker_notes import TrackerNote
from fpdb_3_legacy.tracker_notes_dialog import GuiTrackerNotes

pytestmark = pytest.mark.qt


class FakeDb:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.sql = SimpleNamespace(query={"placeholder": "?"})
        self.closed = 0

    def close_connection(self) -> None:
        self.closed += 1


@pytest.fixture
def fpdb() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE Sites (id INTEGER PRIMARY KEY, name TEXT, code TEXT)")
    connection.execute("INSERT INTO Sites VALUES (2, 'PokerStars', 'PS')")
    connection.execute(player_schema_queries("sqlite")["createPlayersTable"])
    connection.execute("INSERT INTO Players (name, siteId, comment) VALUES ('alice', 2, 'Old note')")
    connection.commit()
    return connection


def _dialog(qtbot, fpdb, read_notes):
    db = FakeDb(fpdb)
    dialog = GuiTrackerNotes(SimpleNamespace(supported_sites={}), read_notes=read_notes, open_db=lambda: db)
    qtbot.addWidget(dialog)
    return dialog, db


def _comment(fpdb) -> str:
    return fpdb.execute("SELECT comment FROM Players WHERE name = 'alice'").fetchone()[0]


def test_the_password_is_not_shown(qtbot, fpdb) -> None:
    dialog, _db = _dialog(qtbot, fpdb, list)

    assert dialog.password.echoMode() == QLineEdit.EchoMode.Password


def test_preview_writes_nothing_then_import_appends(qtbot, fpdb) -> None:
    notes = [TrackerNote("PokerStars", "alice", "Calls too much", ("Fish",))]
    dialog, db = _dialog(qtbot, fpdb, lambda: notes)

    dialog.preview_button.click()

    assert _comment(fpdb) == "Old note"
    assert dialog.report.toPlainText().startswith("Preview, nothing written: 0 notes to add, 1 to append")

    dialog.import_button.click()

    assert _comment(fpdb) == "Old note\n\n[PokerTracker 4 | Fish]\nCalls too much"
    assert dialog.report.toPlainText().startswith("0 notes added, 1 appended")
    assert db.closed == 2


def test_skip_existing_leaves_the_fpdb_note(qtbot, fpdb) -> None:
    dialog, _db = _dialog(qtbot, fpdb, lambda: [TrackerNote("PokerStars", "alice", "Calls too much")])
    dialog.skip_existing.setChecked(True)

    dialog.import_button.click()

    assert _comment(fpdb) == "Old note"
    assert "skipped: fpdb already has a note" in dialog.report.toPlainText()


def test_a_pt4_that_cannot_be_read_is_reported_and_fpdb_untouched(qtbot, fpdb) -> None:
    def unreachable():
        raise ConnectionError("connection refused")

    dialog, db = _dialog(qtbot, fpdb, unreachable)

    dialog.import_button.click()

    assert "connection refused" in dialog.report.toPlainText()
    assert _comment(fpdb) == "Old note"
    assert db.closed == 0


def test_the_auto_notes_box_reaches_the_pt4_reader(qtbot, fpdb, monkeypatch) -> None:
    from contextlib import nullcontext

    from fpdb_3_legacy import pt4_adapter, tracker_notes

    asked = []
    monkeypatch.setattr(pt4_adapter, "connect_pt4", lambda _config: nullcontext("pt4"))
    monkeypatch.setattr(
        tracker_notes,
        "read_pt4_notes",
        lambda conn, *, auto_notes: asked.append((conn, auto_notes)) or [],
    )
    dialog = GuiTrackerNotes(SimpleNamespace(supported_sites={}), open_db=lambda: FakeDb(fpdb))
    qtbot.addWidget(dialog)

    dialog.preview_button.click()
    dialog.auto_notes.setChecked(True)
    dialog.preview_button.click()

    assert asked == [("pt4", False), ("pt4", True)]
