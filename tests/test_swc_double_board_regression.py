"""Non-regression tests: a SwC PLO double-board bomb pot captured via the tap
must show both boards in the hand viewer and the replayer.

The chain, end to end:

1. The SwC client's *text* hand history writes only one board of a
   double-board bomb pot while its payouts reflect both (see
   regression-test-files/cash/SealsWithClubs/Flop/PLO-8max-mBTC-0.04-0.08-double-board-bomb-pot-20261108.txt:
   one ``Board [...]`` line, yet 0.70 + 0.70 collected). The text import
   therefore stores a single board and ``runItTwice = 0``.
2. The native tap sees both boards. ``extract_native_boards`` decodes them from
   the game-state snapshots, and ``merge_native_boards`` keeps the most complete
   version of each board across snapshots -- a single "best snapshot" choice
   loses both boards whenever no one snapshot carried both complete.
3. ``import_http_capture_hand`` repairs the already text-imported hand:
   ``runItTwice = 1`` plus one ``Boards`` row per board
   (``_enrich_existing_native_boards``).
4. The viewer/replayer read the hand back through ``hand_factory``:
   ``Hand.select`` loads the ``Boards`` rows into ``FLOP1/FLOP2/...`` because
   ``runItTwice`` is set; the viewer's double-board flag is
   ``bombPot > 0 AND COUNT(Boards) >= 2`` and the replayer groups
   ``FLOP1/FLOP2`` into one parallel reveal.

Any break in that chain -- boards dropped at extraction, the repair vetoed by
one incomplete board, ``runItTwice`` not persisted, the read path ignoring the
``Boards`` rows -- makes the second board disappear from both views, which is
the reported regression.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fpdb_3_legacy import Card
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.DerivedStats import DerivedStats
from fpdb_3_legacy.Hand import hand_factory
from fpdb_3_legacy.http_capture_db_import import import_http_capture_hand
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.swc_native_capture import (
    NativeProtocolMessage,
    extract_game_state,
    extract_native_boards,
    extract_table_info,
    merge_native_boards,
    normalize_native_hands,
)

REPO = Path(__file__).resolve().parent.parent
BOMB_POT_HH = (
    REPO
    / "regression-test-files/cash/SealsWithClubs/Flop/PLO-8max-mBTC-0.04-0.08-double-board-bomb-pot-20261108.txt"
)

# The hand the client wrote (board one) and the second board only the tap saw.
HAND_ID = 305151201
TABLE_ID = 299672838
BOARD_ONE = ["8d", "9d", "Kd", "9h", "Ah"]
BOARD_TWO = ["2c", "7h", "Js", "4s", "10c"]


def _snapshot(table_id: int, hand_id: int, round_number: int, *boards: list[int]) -> NativeProtocolMessage:
    """One synthetic game-state snapshot carrying count-prefixed boards."""
    player = (
        (7).to_bytes(4, "little")
        + (4).to_bytes(2, "little")
        + b"Hero"
        + b"\0\0prefix\xf0\xbf\0\x16\x80"
        + (b"\0" * 6)
        + (580).to_bytes(3, "little")
        + b"suffix"
    )
    board_bytes = b"".join(bytes([len(b), *b]) for b in boards)
    payload = (
        b"\x16\0"
        + player
        + b"\xf0\xbf\0"
        + board_bytes
        + b"\0" * 10
        + hand_id.to_bytes(4, "little")
        + table_id.to_bytes(4, "little")
        + (b"\0" * 5)
        + bytes([round_number])
    )
    return NativeProtocolMessage(datetime.now(UTC), payload, peer_port=20013)


def _table_message(table_id: int) -> NativeProtocolMessage:
    table_name = b"No-Rake Micro Stakes PLO Double Board Bomb Pots #1"
    payload = (
        b"\x22\0"
        + (b"\0" * 4)
        + table_id.to_bytes(4, "little")
        + b"\x01"
        + (b"\0" * 4)
        + b"H"
        + len(table_name).to_bytes(2, "little")
        + table_name
        + b"PR"
    )
    return NativeProtocolMessage(datetime.now(UTC), payload, peer_port=20013)


def _card_ids(cards: list[str]) -> list[int]:
    """Wire card ids, the inverse of swc_http_adapter.card_id_to_str."""
    from fpdb_3_legacy.swc_http_adapter import RANKS, SUITS

    return [RANKS.index(c[:-1]) * 4 + SUITS.index(c[-1]) for c in cards]


# ---------------------------------------------------------------------------
# Board extraction / merging
# ---------------------------------------------------------------------------


def test_extract_native_boards_reads_omaha_double_board_at_every_round():
    """PLO (family omaha) snapshots carry two count-prefixed boards, like Hold'em."""
    b1, b2 = _card_ids(BOARD_ONE), _card_ids(BOARD_TWO)
    table = extract_table_info(_table_message(TABLE_ID))
    assert table is not None and table.family == "omaha"

    for round_number, n in ((2, 3), (3, 4), (4, 5), (5, 5)):
        message = _snapshot(TABLE_ID, HAND_ID, round_number, b1[:n], b2[:n])
        snapshot = extract_game_state(message, {TABLE_ID})
        assert snapshot is not None
        boards = extract_native_boards(snapshot, "omaha")
        assert boards == (tuple(BOARD_ONE[:n]), tuple(BOARD_TWO[:n]))


def test_merge_native_boards_keeps_the_most_complete_board_per_index():
    """No single snapshot needs to carry both boards complete.

    Before the merge, the envelope's boards came from one ``max`` snapshot, so
    a final snapshot with only board one complete made ``_native_board_rows``
    veto the whole repair (any board short of five cards discards all rows).
    """
    board1_full, board1_short = tuple(BOARD_ONE), tuple(BOARD_ONE[:3])
    board2_full, board2_short = tuple(BOARD_TWO), tuple(BOARD_TWO[:4])

    merged = merge_native_boards(
        [
            (board1_full,),  # late snapshot: only board one seen, complete
            (board1_short, board2_full),  # earlier snapshot: both seen, board one short
            (board1_short, board2_short),
        ]
    )
    assert merged == (board1_full, board2_full)

    # A single-board hand is unchanged.
    assert merge_native_boards([(board1_full,)]) == (board1_full,)
    assert merge_native_boards([(), (board1_short,)]) == (board1_short,)
    assert merge_native_boards([]) == ()


def test_normalize_native_hands_omaha_double_board_envelope_has_both_boards():
    b1, b2 = _card_ids(BOARD_ONE), _card_ids(BOARD_TWO)
    messages = [_table_message(TABLE_ID)]
    # The last snapshot carries board one complete but only a short board two:
    # the merged envelope must still hold two complete boards.
    messages += [
        _snapshot(TABLE_ID, HAND_ID, 2, b1[:3], b2[:3]),
        _snapshot(TABLE_ID, HAND_ID, 3, b1[:4], b2[:4]),
        _snapshot(TABLE_ID, HAND_ID, 4, b1[:5], b2[:5]),
        _snapshot(TABLE_ID, HAND_ID, 5, b1[:5], b2[:4]),
    ]
    hands = normalize_native_hands(messages, raw_ref="test.raw")
    assert len(hands) == 1
    hand = hands[0]
    assert hand["game"]["category"] == "omahahi"
    assert hand["run_it_times"] == 2
    assert hand["double_board"] is True
    assert hand["boards"] == [
        {"FLOP": BOARD_ONE[:3], "TURN": [BOARD_ONE[3]], "RIVER": [BOARD_ONE[4]]},
        {"FLOP": BOARD_TWO[:3], "TURN": [BOARD_TWO[3]], "RIVER": [BOARD_TWO[4]]},
    ]
    assert hand["community"]["FLOP2"] == BOARD_TWO[:3]


# ---------------------------------------------------------------------------
# End to end: text import -> tap repair -> viewer/replayer read-back
# ---------------------------------------------------------------------------


@pytest.fixture
def config(tmp_path: Path) -> Config:
    shutil.copyfile(REPO / "HUD_config.xml", tmp_path / "HUD_config.xml")
    config = Config(file=str(tmp_path / "HUD_config.xml"))
    params = config.get_db_parameters()
    params.update(
        {
            "db-server": "sqlite",
            "db-backend": 4,
            "db-databaseName": str(tmp_path / "double_board.sqlite3"),
            "db-path": "",
        }
    )
    config.get_db_parameters = lambda: params
    schema = Database(config)
    schema.recreate_tables()
    schema.close_connection()
    return config


def _import_text_history(config: Config) -> int:
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.setCallHud(False)
    importer.set_progress_callbacks(lambda _total: None, lambda _path, _count: None, lambda: None)
    importer.addImportFile(str(BOMB_POT_HH), "auto")
    importer.runImport()
    importer.close()
    db = Database(config)
    cursor = db.get_cursor()
    cursor.execute(
        "SELECT h.id FROM Hands h JOIN Gametypes g ON h.gametypeId = g.id WHERE h.siteHandNo = ? AND g.siteId = 23",
        (HAND_ID,),
    )
    row = cursor.fetchone()
    assert row is not None
    return row[0]


def _tap_envelope() -> dict:
    """The normalized native capture of the same hand: both boards, ante pot."""
    return {
        "site": "SealsWithClubs",
        "hand_id": HAND_ID,
        "table_id": TABLE_ID,
        "table_name": "No-Rake Micro Stakes PLO Double Board Bomb Pots #1",
        "game": {"base": "hold", "category": "omahahi", "fpdb_supported": False},
        "gametype": {
            "type": "ring",
            "base": "hold",
            "category": "omahahi",
            "limitType": "pl",
            "currency": "mBTC",
            "sb": 0.02,
            "bb": 0.04,
            "ante": 0,
            "maxSeats": 8,
        },
        "metadata": {
            "adapter": "swc_native",
            "importability": {
                "complete_action_players": True,
                "settlement_conservation_complete": True,
                "has_small_blind": False,  # bomb pot: antes, no blinds
                "has_big_blind": False,
                "has_collection": True,
            },
        },
        "players": [
            {"name": "Player0", "seat_idx": 3, "player_id": 1},
            {"name": "Player1", "seat_idx": 4, "player_id": 2},
            {"name": "Player2", "seat_idx": 5, "player_id": 3},
            {"name": "Hero", "seat_idx": 6, "player_id": 4},
        ],
        "board": BOARD_ONE,
        "boards": [
            {"FLOP": BOARD_ONE[:3], "TURN": [BOARD_ONE[3]], "RIVER": [BOARD_ONE[4]]},
            {"FLOP": BOARD_TWO[:3], "TURN": [BOARD_TWO[3]], "RIVER": [BOARD_TWO[4]]},
        ],
        "run_it_times": 2,
        "double_board": True,
        "bomb_pot": 48,
        "community": {
            "FLOP": BOARD_ONE[:3],
            "TURN": [BOARD_ONE[3]],
            "RIVER": [BOARD_ONE[4]],
            "FLOP2": BOARD_TWO[:3],
            "TURN2": [BOARD_TWO[3]],
            "RIVER2": [BOARD_TWO[4]],
        },
        "actions": [],
        "collections": [],
    }


def _query(db_path: Path, sql: str, params: tuple = ()):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, params)]
    finally:
        con.close()


def test_text_import_alone_leaves_the_bomb_pot_single_board(config: Config, tmp_path: Path) -> None:
    """Documents what the text history alone gives: bomb pot flagged, one board."""
    hand_row_id = _import_text_history(config)
    rows = _query(
        tmp_path / "double_board.sqlite3",
        "SELECT bombPot, runItTwice, boardcard1, boardcard2, boardcard3, boardcard4, boardcard5"
        " FROM Hands WHERE id = ?",
        (hand_row_id,),
    )
    assert rows[0]["bombPot"] == 48  # 4 x 0.12 ante, in cents
    assert rows[0]["runItTwice"] == 0
    assert rows[0]["boardcard1"] != 0
    boards = _query(tmp_path / "double_board.sqlite3", "SELECT * FROM Boards WHERE handId = ?", (hand_row_id,))
    assert boards == []


def test_tap_repair_restores_the_second_board_for_viewer_and_replayer(
    config: Config, tmp_path: Path
) -> None:
    hand_row_id = _import_text_history(config)
    db_path = tmp_path / "double_board.sqlite3"

    db = Database(config)
    result = import_http_capture_hand(db, _tap_envelope())
    assert result.status == "updated"
    assert result.row_id == hand_row_id

    # runItTwice set and one Boards row per board, with the exact cards.
    hand = _query(db_path, "SELECT bombPot, runItTwice FROM Hands WHERE id = ?", (hand_row_id,))[0]
    assert hand["runItTwice"] == 1
    assert hand["bombPot"] == 48  # not clobbered by the repair
    board_rows = _query(
        db_path,
        "SELECT boardId, boardcard1, boardcard2, boardcard3, boardcard4, boardcard5 FROM Boards"
        " WHERE handId = ? ORDER BY boardId",
        (hand_row_id,),
    )
    # The repair converts native "10x" tokens to the legacy "Tx" form before
    # encoding (see _legacy_native_card_tokens), so encode the legacy form.
    expected = [[Card.encodeCard(c.replace("10", "T")) for c in board] for board in (BOARD_ONE, BOARD_TWO)]
    assert [[r["boardId"], r["boardcard1"], r["boardcard2"], r["boardcard3"], r["boardcard4"], r["boardcard5"]] for r in board_rows] == [
        [1, *expected[0]],
        [2, *expected[1]],
    ]

    # The viewer's double-board flag: bomb pot with at least two stored boards.
    flag = _query(
        db_path,
        "SELECT (h.bombPot > 0 AND (SELECT COUNT(*) FROM Boards b WHERE b.handId = h.id) >= 2) AS d"
        " FROM Hands h WHERE h.id = ?",
        (hand_row_id,),
    )[0]["d"]
    assert flag == 1

    # Read back exactly the way GuiHandViewer/GuiReplayer load a hand.
    loaded = hand_factory(hand_row_id, config, db)
    assert loaded.runItTimes == 2
    assert loaded.bombPot == 48
    # Cards read back from the DB are in Hand.py's legacy form ("Tc", not "10c").
    board_two_legacy = [c.replace("10", "T") for c in BOARD_TWO]
    assert loaded.board["FLOP2"] == board_two_legacy[:3]
    assert loaded.board["TURN2"] == [board_two_legacy[3]]
    assert loaded.board["RIVER2"] == [board_two_legacy[4]]
    assert DerivedStats().getBoardsList(loaded) == [BOARD_ONE, board_two_legacy]

    # The replayer groups the two boards of a bomb pot into parallel reveals.
    from fpdb_3_legacy.GuiReplayer import replay_street_groups

    groups = replay_street_groups(loaded)
    assert ("FLOP1", "FLOP2") in groups
    assert ("TURN1", "TURN2") in groups
    assert ("RIVER1", "RIVER2") in groups
    db.close_connection()


def test_tap_repair_is_skipped_when_a_board_is_incomplete(config: Config, tmp_path: Path) -> None:
    """A second board with fewer than five cards must not be stored half-way."""
    hand_row_id = _import_text_history(config)
    envelope = _tap_envelope()
    envelope["boards"][1] = {"FLOP": BOARD_TWO[:3], "TURN": [BOARD_TWO[3]]}  # no river
    db = Database(config)
    result = import_http_capture_hand(db, envelope)
    assert result.status == "skipped"  # bomb pot is not tap-importable, nothing to repair
    rows = _query(
        tmp_path / "double_board.sqlite3",
        "SELECT runItTwice FROM Hands WHERE id = ?",
        (hand_row_id,),
    )
    assert rows[0]["runItTwice"] == 0
    boards = _query(
        tmp_path / "double_board.sqlite3", "SELECT * FROM Boards WHERE handId = ?", (hand_row_id,)
    )
    assert boards == []
    db.close_connection()


# ---------------------------------------------------------------------------
# HUD table detection: a site without a title regex must not crash find_tables
# ---------------------------------------------------------------------------


def test_macos_find_tables_tolerates_a_none_search_string(monkeypatch) -> None:
    """getTableTitleRe returns None when no table name/regex exists; the old
    code passed None to re.compile, whose TypeError escaped find_tables and
    killed table-window construction (seen in HUD-crash.txt)."""
    from fpdb.infrastructure.platform.macos import MacOSTableDetector

    detector = MacOSTableDetector()
    monkeypatch.setattr(detector, "_CGWindowListCopyWindowInfo", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(detector, "_find_tables_without_titles", lambda *a, **k: None)
    assert detector.find_tables(None) == []  # type: ignore[arg-type]
    assert detector.find_tables("") == []
