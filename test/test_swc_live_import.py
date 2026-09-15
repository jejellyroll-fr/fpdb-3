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

import logging
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy.GuiAutoImport import AutoImportThread, GuiAutoImport
from fpdb_3_legacy.http_capture_db_import import _enrich_existing_native_boards, import_http_capture_hand


class _Gui(SimpleNamespace):
    """Stands in for the widget: the callback only needs an importer and addText.

    Calling the method unbound on this keeps a half-constructed QWidget out of
    the tests — the callback touches no Qt state, so building one would only
    add a dependency on the display.
    """

    def addText(self, text: str, _tag: str | None = None) -> None:
        self.messages.append(text)

    def _notify_hud_of_hand(self, row_id) -> None:
        # Records what a running HUD would have been told, without a ZMQ socket.
        self.hud_notifications.append(row_id)

    def on_hand(self, hand_data: dict) -> None:
        GuiAutoImport._on_swc_native_hand_imported(self, hand_data)


class _Tailer:
    """Stands in for SwCNativeTailingThread, recording what the callback told it."""

    def __init__(self) -> None:
        self.completed: list[dict] = []
        self.retried: list[dict] = []
        self.retried_transient: list[bool] = []
        self.capture_only: list[dict] = []

    def mark_hand_complete(self, hand_data: dict) -> None:
        self.completed.append(hand_data)

    def retry_hand(self, hand_data: dict, *, transient: bool = False) -> None:
        self.retried.append(hand_data)
        # A refusal from outside the hand (busy connection, database away) is
        # retried past the budget; the importer's own verdict is not.
        self.retried_transient.append(transient)

    def note_capture_only(self, hand_data: dict) -> bool:
        self.capture_only.append(hand_data)
        return len(self.capture_only) == 1


def _result(status: str, message: str = "") -> SimpleNamespace:
    return SimpleNamespace(site_hand_no="", kind="native", row_id=None, replay_ref=None, status=status, message=message)


@pytest.fixture
def gui():
    return _Gui(messages=[], hud_notifications=[])


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

    gui.on_hand(_hand())

    assert seen["db"] is sentinel
    assert seen["hand"] == _hand()


def test_a_successful_import_is_reported_to_the_user(gui, monkeypatch) -> None:
    gui.importer = SimpleNamespace(database=object())
    monkeypatch.setattr(
        "fpdb_3_legacy.http_capture_db_import.import_http_capture_hand",
        lambda *_a, **_k: None,
    )

    gui.on_hand(_hand())

    assert any("299449673" in message for message in gui.messages)


def test_no_database_is_reported_rather_than_swallowed(gui, caplog) -> None:
    gui.importer = SimpleNamespace()

    gui.on_hand(_hand())

    assert gui.messages == []
    assert any("no database connection" in record.message for record in caplog.records)


def test_a_failing_import_does_not_claim_success(gui, monkeypatch) -> None:
    gui.importer = SimpleNamespace(database=object())

    def explode(*_args, **_kwargs):
        message = "database is away"
        raise RuntimeError(message)

    monkeypatch.setattr("fpdb_3_legacy.http_capture_db_import.import_http_capture_hand", explode)

    gui.on_hand(_hand())

    assert gui.messages == []


def test_a_hand_the_importer_could_not_use_yet_stays_retryable(gui, monkeypatch) -> None:
    """A hand the importer refused is offered again without waiting for new capture.

    Two things complete a hand besides its own later records: the tailer polls
    every 2.5s so a hand is normally decoded mid-play, and a finished hand can
    be waiting for its text history to be imported -- after which it produces no
    more records at all, so a content change would never come.
    """
    gui.importer = SimpleNamespace(database=object())
    gui.swc_tailing_thread = _Tailer()
    monkeypatch.setattr(
        "fpdb_3_legacy.http_capture_db_import.import_http_capture_hand",
        lambda *_a, **_k: _result("skipped", "native hand is incomplete or its settlement is not proven"),
    )

    gui.on_hand(_hand())

    assert gui.swc_tailing_thread.completed == []
    assert gui.swc_tailing_thread.retried == [_hand()]
    assert gui.messages == []


def test_a_failing_import_leaves_the_hand_retryable(gui, monkeypatch) -> None:
    gui.importer = SimpleNamespace(database=object())
    gui.swc_tailing_thread = _Tailer()

    def explode(*_args, **_kwargs):
        message = "database is away"
        raise RuntimeError(message)

    monkeypatch.setattr("fpdb_3_legacy.http_capture_db_import.import_http_capture_hand", explode)

    gui.on_hand(_hand())

    assert gui.swc_tailing_thread.completed == []
    assert gui.swc_tailing_thread.retried == [_hand()]


@pytest.mark.parametrize("status", ["imported", "duplicate", "updated"])
def test_a_terminal_import_result_retires_the_hand(gui, monkeypatch, status) -> None:
    gui.importer = SimpleNamespace(database=object())
    gui.swc_tailing_thread = _Tailer()
    monkeypatch.setattr(
        "fpdb_3_legacy.http_capture_db_import.import_http_capture_hand",
        lambda *_a, **_k: _result(status),
    )

    gui.on_hand(_hand())

    assert gui.swc_tailing_thread.completed == [_hand()]


def test_a_hand_skipped_again_is_reported_once(gui, monkeypatch, caplog) -> None:
    """A growing hand is re-offered every poll; the log must not repeat itself."""
    gui.importer = SimpleNamespace(database=object())
    gui.swc_tailing_thread = _Tailer()
    monkeypatch.setattr(
        "fpdb_3_legacy.http_capture_db_import.import_http_capture_hand",
        lambda *_a, **_k: _result("skipped", "settlement is not proven"),
    )
    caplog.set_level(logging.DEBUG, logger="gui_auto_import")

    gui.on_hand(_hand())
    gui.on_hand(_hand())

    capture_only = [record for record in caplog.records if "capture-only" in record.getMessage()]
    assert [record.levelname for record in capture_only] == ["INFO", "DEBUG"]


def test_the_callback_survives_a_widget_with_no_tailing_thread(gui, monkeypatch) -> None:
    """Auto Import can be driven without the live tailer running."""
    gui.importer = SimpleNamespace(database=object())
    monkeypatch.setattr(
        "fpdb_3_legacy.http_capture_db_import.import_http_capture_hand",
        lambda *_a, **_k: _result("skipped", "settlement is not proven"),
    )

    gui.on_hand(_hand())

    assert gui.messages == []


def _is_held(lock: threading.Lock) -> bool:
    """Whether `lock` is already taken, without keeping it when it was not."""
    if lock.acquire(blocking=False):
        lock.release()
        return False
    return True


def test_a_hand_waits_while_an_import_cycle_owns_the_database(gui, monkeypatch) -> None:
    """The cycle drives the same connection and the same bulk buffers, on another thread.

    No DBAPI driver used here lets two threads share one connection (see
    Database._create_new_worker_connection), and importing through it mid-cycle
    would reset the cycle's buffers and commit inside its transaction. The lock
    is tried rather than waited on: this is the GUI thread, and a cycle can run
    for minutes.
    """
    gui.importer = SimpleNamespace(database=object())
    gui.swc_tailing_thread = _Tailer()
    gui.db_write_lock = threading.Lock()
    gui.db_write_lock.acquire()
    monkeypatch.setattr(
        "fpdb_3_legacy.http_capture_db_import.import_http_capture_hand",
        lambda *_a, **_k: pytest.fail("imported while an import cycle owned the connection"),
    )

    gui.on_hand(_hand())

    assert gui.swc_tailing_thread.retried == [_hand()]
    assert gui.swc_tailing_thread.completed == []
    assert gui.messages == []
    gui.db_write_lock.release()


@pytest.mark.parametrize("status", ["imported", "skipped"])
def test_the_callback_releases_the_write_lock(gui, monkeypatch, status) -> None:
    """A lock left held would stop every later import cycle."""
    gui.importer = SimpleNamespace(database=object())
    gui.db_write_lock = threading.Lock()
    monkeypatch.setattr(
        "fpdb_3_legacy.http_capture_db_import.import_http_capture_hand",
        lambda *_a, **_k: _result(status),
    )

    gui.on_hand(_hand())

    assert _is_held(gui.db_write_lock) is False


def test_the_callback_releases_the_write_lock_after_a_failure(gui, monkeypatch) -> None:
    gui.importer = SimpleNamespace(database=object())
    gui.db_write_lock = threading.Lock()

    def explode(*_args, **_kwargs):
        message = "database is away"
        raise RuntimeError(message)

    monkeypatch.setattr("fpdb_3_legacy.http_capture_db_import.import_http_capture_hand", explode)

    gui.on_hand(_hand())

    assert _is_held(gui.db_write_lock) is False


def test_an_import_cycle_holds_the_write_lock_while_it_runs() -> None:
    """The other half of the contract: the worker owns the connection for its whole cycle."""
    lock = threading.Lock()
    held: list[bool] = []

    class _Importer:
        database = SimpleNamespace(ensure_connection=lambda: True)

        @staticmethod
        def autoSummaryGrab() -> None:
            held.append(_is_held(lock))

        @staticmethod
        def runUpdated() -> None:
            held.append(_is_held(lock))

    AutoImportThread(_Importer(), db_write_lock=lock).run()  # the worker body, without a Qt event loop

    assert held == [True, True]
    assert _is_held(lock) is False


def _native_public_hand() -> dict:
    return {
        "site": "SealsWithClubs",
        "hand_id": 301461728,
        "game": {"base": "hold", "category": "holdem", "fpdb_supported": False},
        "gametype": {"base": "hold", "category": "holdem", "maxSeats": 2},
        "metadata": {
            "adapter": "swc_native",
            "state_model": "snapshot",
            "action_reconstruction": {"status": "complete"},
            "importability": {
                "complete_action_players": True,
                "settlement_conservation_complete": True,
                "has_small_blind": True,
                "has_big_blind": True,
                "has_collection": True,
            },
        },
        "players": [{"name": "Hero", "seat_idx": 1, "starting_stack": None}],
        "board": ["10h", "Jd", "2d", "Ks", "10d"],
        "boards": [
            {"FLOP": ["10h", "Jd", "2d"], "TURN": ["Ks"], "RIVER": ["10d"]},
            {"FLOP": ["10h", "Jd", "2d"], "TURN": ["4c"], "RIVER": ["8c"]},
        ],
        "bomb_pot": True,
        "actions": [
            {"type": "small blind", "player": "Hero", "street": "BLINDSANTES", "amount": 2},
            {"type": "big blind", "player": "Villain", "street": "PREFLOP", "amount": 4},
        ],
        "collections": [{"player": "Hero", "amount_native": 6}],
    }


def test_native_public_hand_is_sent_through_fpdb_importer(monkeypatch) -> None:
    seen = {}
    built = SimpleNamespace()

    def build(hand_data, *, config):
        seen["hand_data"] = hand_data
        seen["config"] = config
        return built

    def store(hand, db, **kwargs):
        seen["store"] = (hand, db, kwargs)
        hand.dbid_hands = 42

    monkeypatch.setattr("fpdb_3_legacy.http_capture_db_import.build_fpdb_hand", build)
    monkeypatch.setattr("fpdb_3_legacy.http_capture_db_import.import_fpdb_hand", store)

    result = import_http_capture_hand(object(), _native_public_hand())

    assert result.status == "imported"
    assert result.row_id == 42
    assert result.replay_ref == "native:301461728"
    assert seen["hand_data"]["game"]["fpdb_supported"] is True
    assert seen["hand_data"]["players"][0]["starting_stack"] == 0
    assert seen["hand_data"]["board"] == ["Th", "Jd", "2d", "Ks", "Td"]
    assert seen["hand_data"]["boards"][1]["RIVER"] == ["8c"]
    assert seen["config"].get_site_id("SealsWithClubs") == 23


def test_native_boards_repair_an_existing_hand_without_overwriting_bomb_pot_amount() -> None:
    class Cursor:
        def __init__(self) -> None:
            self.calls = []

        def execute(self, query, params) -> None:
            self.calls.append((query, params))

        def fetchall(self):
            return [(42,)]

    cursor = Cursor()
    db = SimpleNamespace(
        sql=SimpleNamespace(
            query={
                "placeholder": "?",
                "store_boards": "insert into Boards values (%s, %s, %s, %s, %s, %s, %s)",
            }
        ),
        get_cursor=lambda: cursor,
        commit=lambda: setattr(db, "committed", True),
    )

    repaired_id = _enrich_existing_native_boards(db, _native_public_hand())

    assert repaired_id == 42
    assert db.committed is True
    update_query, update_params = next(
        (query, params) for query, params in cursor.calls if query.startswith("UPDATE Hands")
    )
    assert "runItTwice" in update_query
    assert "bombPot" not in update_query
    assert update_params == (True, 42)
    board_insert = cursor.calls[-2:]
    assert board_insert[0][1][0] == 42
    assert board_insert[0][1][1:3] == [1, 9]
    assert board_insert[1][1][1:3] == [2, 9]


def test_incomplete_native_hand_stays_capture_only(monkeypatch) -> None:
    monkeypatch.setattr(
        "fpdb_3_legacy.http_capture_db_import.build_fpdb_hand",
        lambda **_kwargs: pytest.fail("incomplete native hand must not be built"),
    )
    hand = _native_public_hand()
    hand["metadata"]["importability"]["settlement_conservation_complete"] = False

    result = import_http_capture_hand(object(), hand)

    assert result.status == "skipped"
    assert "settlement is not proven" in result.message


def test_an_external_refusal_is_marked_transient(gui, monkeypatch) -> None:
    """A busy connection and a database that is away both clear on their own."""
    tailer = _Tailer()
    gui.swc_tailing_thread = tailer
    gui.importer = SimpleNamespace(database=object())
    gui.db_write_lock = None
    monkeypatch.setattr(
        "fpdb_3_legacy.http_capture_db_import.import_http_capture_hand",
        MagicMock(side_effect=OSError("database away")),
    )

    gui.on_hand(_hand())

    assert tailer.retried_transient == [True]


def test_the_importers_own_verdict_is_not_transient(gui, monkeypatch) -> None:
    """A skipped hand cannot become importable while its snapshot is unchanged."""
    tailer = _Tailer()
    gui.swc_tailing_thread = tailer
    gui.importer = SimpleNamespace(database=object())
    gui.db_write_lock = None
    monkeypatch.setattr(
        "fpdb_3_legacy.http_capture_db_import.import_http_capture_hand",
        MagicMock(return_value=_result("skipped", "not importable yet")),
    )

    gui.on_hand(_hand())

    assert tailer.retried_transient == [False]
