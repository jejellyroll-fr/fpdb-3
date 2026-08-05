"""A hand captured live has to reach the database.

The callback read the importer's connection from `self.importer.db`, an
attribute that does not exist — Importer holds it as `database`. Every live
hand therefore raised AttributeError straight into the surrounding
`except Exception`, which logged and moved on, so nothing captured live was
ever imported and nothing said so.

mypy caught it as a type error; these tests pin the behaviour, so the path
cannot go quiet again.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fpdb_3_legacy.GuiAutoImport import GuiAutoImport


@pytest.fixture
def gui(monkeypatch):
    """A GuiAutoImport with just enough wired up to run the callback."""
    widget = GuiAutoImport.__new__(GuiAutoImport)
    widget.messages = []
    widget.addText = lambda text, _tag=None: widget.messages.append(text)
    return widget


def _hand() -> dict:
    return {"hand_id": 299449673, "game": {"category": "holdem"}}


def test_the_hand_is_handed_to_the_importers_database(gui, monkeypatch) -> None:
    sentinel = object()
    gui.importer = SimpleNamespace(database=sentinel)
    seen = {}

    monkeypatch.setattr(
        "fpdb_3_legacy.http_capture_db_import.import_http_capture_hand",
        lambda db, hand_data, **_: seen.update(db=db, hand=hand_data),
    )

    gui._on_swc_native_hand_imported(_hand())

    assert seen["db"] is sentinel
    assert seen["hand"] == _hand()


def test_a_successful_import_is_reported_to_the_user(gui, monkeypatch) -> None:
    gui.importer = SimpleNamespace(database=object())
    monkeypatch.setattr(
        "fpdb_3_legacy.http_capture_db_import.import_http_capture_hand",
        lambda *_a, **_k: None,
    )

    gui._on_swc_native_hand_imported(_hand())

    assert any("299449673" in message for message in gui.messages)


def test_no_database_is_reported_rather_than_swallowed(gui, caplog) -> None:
    gui.importer = SimpleNamespace()

    gui._on_swc_native_hand_imported(_hand())

    assert gui.messages == []
    assert any("no database connection" in record.message for record in caplog.records)


def test_a_failing_import_does_not_claim_success(gui, monkeypatch) -> None:
    gui.importer = SimpleNamespace(database=object())

    def explode(*_args, **_kwargs):
        message = "database is away"
        raise RuntimeError(message)

    monkeypatch.setattr("fpdb_3_legacy.http_capture_db_import.import_http_capture_hand", explode)

    gui._on_swc_native_hand_imported(_hand())

    assert gui.messages == []
