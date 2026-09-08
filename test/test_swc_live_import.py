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
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.GuiAutoImport import GuiAutoImport
from fpdb_3_legacy.http_capture_db_import import _enrich_existing_native_boards, import_http_capture_hand


class _Gui(SimpleNamespace):
    """Stands in for the widget: the callback only needs an importer and addText.

    Calling the method unbound on this keeps a half-constructed QWidget out of
    the tests — the callback touches no Qt state, so building one would only
    add a dependency on the display.
    """

    def addText(self, text: str, _tag: str | None = None) -> None:
        self.messages.append(text)

    def on_hand(self, hand_data: dict) -> None:
        GuiAutoImport._on_swc_native_hand_imported(self, hand_data)


class _Tailer:
    """Stands in for SwCNativeTailingThread, recording what the callback told it."""

    def __init__(self) -> None:
        self.completed: list[dict] = []
        self.capture_only: list[dict] = []

    def mark_hand_complete(self, hand_data: dict) -> None:
        self.completed.append(hand_data)

    def note_capture_only(self, hand_data: dict) -> bool:
        self.capture_only.append(hand_data)
        return len(self.capture_only) == 1


def _result(status: str, message: str = "") -> SimpleNamespace:
    return SimpleNamespace(site_hand_no="", kind="native", row_id=None, replay_ref=None, status=status, message=message)


@pytest.fixture
def gui():
    return _Gui(messages=[])


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
    """The tailer polls every 2.5s, so a hand is normally decoded mid-play.

    Retiring its key on that first, incomplete snapshot discarded the hand for
    good: the records completing its actions and settlement arrived later and
    were suppressed.
    """
    gui.importer = SimpleNamespace(database=object())
    gui.swc_tailing_thread = _Tailer()
    monkeypatch.setattr(
        "fpdb_3_legacy.http_capture_db_import.import_http_capture_hand",
        lambda *_a, **_k: _result("skipped", "native hand is incomplete or its settlement is not proven"),
    )

    gui.on_hand(_hand())

    assert gui.swc_tailing_thread.completed == []
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
