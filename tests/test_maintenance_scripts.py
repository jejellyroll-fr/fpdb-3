"""Tests for the maintenance scripts that write to, or delete from, the database.

These scripts run outside the application, against a player's real database, and
were entirely uncovered. ``fix_draw_starting_hands`` deletes hands outright, so
the tests below check what it selects and what it removes, not merely that it
runs.

Every test works on the throwaway SQLite schema of the ``fresh_db`` fixture; a
real ``HUD_config.xml`` is never written to.
"""

from __future__ import annotations

import importlib
from datetime import datetime
from typing import Any

import pytest

from fpdb_3_legacy import backfill_boards, backfill_showdown, fix_draw_starting_hands

HERO_SEAT = 1
VILLAIN_SEAT = 2


def insert_row(db: Any, table: str, **values: Any) -> int:
    """Insert one row and return its rowid."""
    columns = ", ".join(values)
    placeholders = ", ".join(["?"] * len(values))
    cursor = db.get_cursor()
    cursor.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(values.values()))
    return cursor.lastrowid


def add_gametype(db: Any, category: str = "fivedraw", base: str = "draw") -> int:
    return insert_row(
        db,
        "Gametypes",
        siteId=1,
        currency="USD",
        type="ring",
        base=base,
        category=category,
        limitType="fl",
        hiLo="h",
        mix="none",
        smallBet=50,
        bigBet=100,
        maxSeats=6,
        ante=0,
        buyinType="regular",
        fast=0,
        newToGame=0,
        homeGame=0,
        split=0,
    )


def add_hand(db: Any, gametype_id: int, site_hand_no: str = "1001", file_id: int | None = None) -> int:
    return insert_row(
        db,
        "Hands",
        tableName="Table",
        siteHandNo=site_hand_no,
        gametypeId=gametype_id,
        fileId=file_id if file_id is not None else 1,
        startTime=datetime(2026, 7, 20, 14, 30),
        importTime=datetime(2026, 7, 20, 15, 0),
        seats=2,
        heroSeat=HERO_SEAT,
        maxPosition=1,
        playersVpi=1,
        playersAtStreet1=0,
        playersAtStreet2=0,
        playersAtStreet3=0,
        playersAtStreet4=0,
        playersAtShowdown=0,
        street0Raises=0,
        street1Raises=0,
        street2Raises=0,
        street3Raises=0,
        street4Raises=0,
    )


def player_id_for(db: Any, name: str) -> int:
    """Return the id of ``name``, creating the player on first use.

    Players are unique per (name, siteId), and the same player sits in several
    hands across these tests.
    """
    cursor = db.get_cursor()
    cursor.execute("SELECT id FROM Players WHERE name = ? AND siteId = 1", (name,))
    found = cursor.fetchone()
    if found:
        return found[0]
    return insert_row(db, "Players", name=name, siteId=1, hero=name == "Player1")


def add_player_in_hand(db: Any, hand_id: int, seat: int, cards: list[int], *, saw_showdown: bool = False) -> int:
    """Seat a player with the given DEAL cards (card1..card5, 0 meaning absent)."""
    padded = [*cards, 0, 0, 0, 0, 0][:5]
    player_id = player_id_for(db, f"Player{seat}")
    insert_row(
        db,
        "HandsPlayers",
        handId=hand_id,
        playerId=player_id,
        startCash=10000,
        effStack=10000,
        seatNo=seat,
        sitout=0,
        card1=padded[0],
        card2=padded[1],
        card3=padded[2],
        card4=padded[3],
        card5=padded[4],
        common=0,
        committed=0,
        winnings=0,
        rake=0,
        rakeDealt=0,
        rakeContributed=0,
        rakeWeighted=0,
        totalProfit=0,
        sawShowdown=saw_showdown,
    )
    return player_id


def rows(db: Any, query: str) -> list[tuple]:
    cursor = db.get_cursor()
    cursor.execute(query)
    return cursor.fetchall()


# --------------------------------------------------------------------------
# fix_draw_starting_hands: what it selects
# --------------------------------------------------------------------------


def test_only_draw_games_are_scanned() -> None:
    categories = fix_draw_starting_hands.draw_categories()

    assert "fivedraw" in categories
    assert "badugi" in categories
    assert "holdem" not in categories
    assert "27_3draw" in categories


@pytest.mark.parametrize(("category", "size"), [("badugi", 4), ("fivedraw", 5), ("27_3draw", 5)])
def test_the_deal_hand_size_follows_the_game(category, size) -> None:
    # The corruption signature is "fewer cards than the game deals", so a wrong
    # size here would silently under- or over-report affected hands.
    assert fix_draw_starting_hands.deal_handsize(category) == size


def test_a_hero_holding_fewer_cards_than_dealt_is_reported(fresh_db) -> None:
    gametype = add_gametype(fresh_db)
    hand = add_hand(fresh_db, gametype)
    add_player_in_hand(fresh_db, hand, HERO_SEAT, [2, 3, 4])  # 3 of 5

    (affected,) = fix_draw_starting_hands.find_affected(fresh_db, include_all=False, only_hand_id=None)

    assert affected["hand_id"] == hand
    assert affected["deal_present"] == 3
    assert affected["deal_size"] == 5
    assert "3/5" in affected["reason"]


def test_a_complete_hero_holding_is_left_alone(fresh_db) -> None:
    gametype = add_gametype(fresh_db)
    hand = add_hand(fresh_db, gametype)
    add_player_in_hand(fresh_db, hand, HERO_SEAT, [2, 3, 4, 5, 6])

    assert fix_draw_starting_hands.find_affected(fresh_db, include_all=False, only_hand_id=None) == []


def test_a_badugi_hero_with_four_cards_is_complete(fresh_db) -> None:
    # Badugi deals four; judging it against five would flag every clean hand.
    gametype = add_gametype(fresh_db, category="badugi")
    hand = add_hand(fresh_db, gametype)
    add_player_in_hand(fresh_db, hand, HERO_SEAT, [2, 3, 4, 5])

    assert fix_draw_starting_hands.find_affected(fresh_db, include_all=False, only_hand_id=None) == []


def test_a_holdem_hand_is_never_scanned(fresh_db) -> None:
    gametype = add_gametype(fresh_db, category="holdem", base="hold")
    hand = add_hand(fresh_db, gametype)
    add_player_in_hand(fresh_db, hand, HERO_SEAT, [2])

    assert fix_draw_starting_hands.find_affected(fresh_db, include_all=False, only_hand_id=None) == []


def test_the_superset_mode_reports_every_showdown_draw_hand(fresh_db) -> None:
    gametype = add_gametype(fresh_db)
    complete = add_hand(fresh_db, gametype, site_hand_no="1")
    add_player_in_hand(fresh_db, complete, HERO_SEAT, [2, 3, 4, 5, 6], saw_showdown=True)
    no_showdown = add_hand(fresh_db, gametype, site_hand_no="2")
    add_player_in_hand(fresh_db, no_showdown, HERO_SEAT, [2, 3, 4, 5, 6], saw_showdown=False)

    affected = fix_draw_starting_hands.find_affected(fresh_db, include_all=True, only_hand_id=None)

    assert [a["hand_id"] for a in affected] == [complete]
    assert affected[0]["reason"].endswith("(superset)")


def test_a_single_hand_can_be_inspected_in_isolation(fresh_db) -> None:
    gametype = add_gametype(fresh_db)
    first = add_hand(fresh_db, gametype, site_hand_no="1")
    add_player_in_hand(fresh_db, first, HERO_SEAT, [2, 3])
    second = add_hand(fresh_db, gametype, site_hand_no="2")
    add_player_in_hand(fresh_db, second, HERO_SEAT, [2, 3])

    affected = fix_draw_starting_hands.find_affected(fresh_db, include_all=False, only_hand_id=second)

    assert [a["hand_id"] for a in affected] == [second]


def test_only_the_hero_seat_decides(fresh_db) -> None:
    # A villain never shows their full starting hand, so judging on their cards
    # would flag every hand in the database.
    gametype = add_gametype(fresh_db)
    hand = add_hand(fresh_db, gametype)
    add_player_in_hand(fresh_db, hand, HERO_SEAT, [2, 3, 4, 5, 6])
    add_player_in_hand(fresh_db, hand, VILLAIN_SEAT, [])

    assert fix_draw_starting_hands.find_affected(fresh_db, include_all=False, only_hand_id=None) == []


# --------------------------------------------------------------------------
# fix_draw_starting_hands: what it deletes
# --------------------------------------------------------------------------


def test_deleting_removes_the_hand_and_its_children(fresh_db) -> None:
    gametype = add_gametype(fresh_db)
    hand = add_hand(fresh_db, gametype)
    player = add_player_in_hand(fresh_db, hand, HERO_SEAT, [2, 3])
    insert_row(fresh_db, "Boards", handId=hand, boardId=1, boardcard1=2)
    insert_row(fresh_db, "HandsShowdown", handId=hand, playerId=player, combo="a pair", cards="Kh Kd")

    fix_draw_starting_hands.delete_hands(fresh_db, [hand])

    assert rows(fresh_db, "SELECT id FROM Hands") == []
    assert rows(fresh_db, "SELECT handId FROM HandsPlayers") == []
    assert rows(fresh_db, "SELECT handId FROM Boards") == []
    assert rows(fresh_db, "SELECT handId FROM HandsShowdown") == []


def test_deleting_spares_the_hands_that_were_not_listed(fresh_db) -> None:
    gametype = add_gametype(fresh_db)
    doomed = add_hand(fresh_db, gametype, site_hand_no="1")
    add_player_in_hand(fresh_db, doomed, HERO_SEAT, [2, 3])
    kept = add_hand(fresh_db, gametype, site_hand_no="2")
    add_player_in_hand(fresh_db, kept, HERO_SEAT, [2, 3, 4, 5, 6])

    fix_draw_starting_hands.delete_hands(fresh_db, [doomed])

    assert [row[0] for row in rows(fresh_db, "SELECT id FROM Hands")] == [kept]
    assert [row[0] for row in rows(fresh_db, "SELECT handId FROM HandsPlayers")] == [kept]


def test_deleting_nothing_touches_nothing(fresh_db) -> None:
    gametype = add_gametype(fresh_db)
    hand = add_hand(fresh_db, gametype)
    add_player_in_hand(fresh_db, hand, HERO_SEAT, [2, 3])

    fix_draw_starting_hands.delete_hands(fresh_db, [])

    assert [row[0] for row in rows(fresh_db, "SELECT id FROM Hands")] == [hand]


def test_the_reported_hands_are_exactly_the_ones_deleted(fresh_db) -> None:
    # The script feeds find_affected straight into delete_hands, so the two must
    # agree or it removes hands it never reported.
    gametype = add_gametype(fresh_db)
    broken = add_hand(fresh_db, gametype, site_hand_no="1")
    add_player_in_hand(fresh_db, broken, HERO_SEAT, [2, 3])
    intact = add_hand(fresh_db, gametype, site_hand_no="2")
    add_player_in_hand(fresh_db, intact, HERO_SEAT, [2, 3, 4, 5, 6])

    affected = fix_draw_starting_hands.find_affected(fresh_db, include_all=False, only_hand_id=None)
    fix_draw_starting_hands.delete_hands(fresh_db, [a["hand_id"] for a in affected])

    assert [row[0] for row in rows(fresh_db, "SELECT id FROM Hands")] == [intact]


# --------------------------------------------------------------------------
# backfill_boards
# --------------------------------------------------------------------------


class FakeHand:
    """The handful of attributes backfill_boards reads off a parsed hand."""

    def __init__(self, run_it_times: Any, board: dict[str, list[str]] | None = None) -> None:
        self.runItTimes = run_it_times
        self.board = board or {}


def test_a_hand_played_once_produces_no_board_row() -> None:
    assert backfill_boards.boards_from_hand(FakeHand(1)) == []


@pytest.mark.parametrize("run_it_times", [None, "", "not-a-number"])
def test_an_unusable_run_count_produces_no_board_row(run_it_times) -> None:
    assert backfill_boards.boards_from_hand(FakeHand(run_it_times)) == []


def test_each_run_becomes_its_own_numbered_board() -> None:
    hand = FakeHand(
        2,
        {
            "FLOP1": ["2h", "3h", "4h"], "TURN1": ["5h"], "RIVER1": ["6h"],
            "FLOP2": ["2s", "3s", "4s"], "TURN2": ["5s"], "RIVER2": ["6s"],
        },
    )

    boards = backfill_boards.boards_from_hand(hand)

    assert [board[0] for board in boards] == [1, 2]
    assert all(len(board) == 6 for board in boards)
    assert boards[0][1:] != boards[1][1:]


def test_a_short_run_is_padded_to_five_cards() -> None:
    # A hand run twice but folded on the turn still owes five board columns.
    boards = backfill_boards.boards_from_hand(FakeHand(2, {"FLOP1": ["2h", "3h", "4h"], "FLOP2": ["2s", "3s", "4s"]}))

    assert all(len(board) == 6 for board in boards)


def test_a_hand_is_found_by_its_site_number_and_room(fresh_db) -> None:
    gametype = add_gametype(fresh_db)
    hand = add_hand(fresh_db, gametype, site_hand_no="990099")

    assert backfill_boards._lookup_hand_ids(fresh_db, "990099", 1) == [hand]
    assert backfill_boards._lookup_hand_ids(fresh_db, 990099, 1) == [hand]


def test_a_hand_of_another_room_is_not_matched(fresh_db) -> None:
    gametype = add_gametype(fresh_db)
    add_hand(fresh_db, gametype, site_hand_no="990099")

    assert backfill_boards._lookup_hand_ids(fresh_db, "990099", 2) == []


# --------------------------------------------------------------------------
# backfill_showdown
# --------------------------------------------------------------------------


class FakeShowdownHand:
    def __init__(self, showdown_strings=None, winning_hand=None) -> None:
        self.showdownStrings = showdown_strings or {}
        self.winningHand = winning_hand or {}


def test_showdown_rows_pair_each_player_with_their_combination() -> None:
    hand = FakeShowdownHand({"Hero": "a pair of kings"}, {"Hero": ["Kh", "Kd"]})

    (row,) = backfill_showdown._rows_for_hand(hand, {"Hero": 11}, 7)

    assert row == (7, 11, "a pair of kings", "Kh Kd")


def test_a_player_absent_from_the_hand_is_skipped() -> None:
    hand = FakeShowdownHand({"Ghost": "a pair"}, {})

    assert backfill_showdown._rows_for_hand(hand, {"Hero": 11}, 7) == []


def test_a_player_with_neither_combination_nor_cards_is_skipped() -> None:
    hand = FakeShowdownHand({"Hero": None}, {"Hero": []})

    assert backfill_showdown._rows_for_hand(hand, {"Hero": 11}, 7) == []


def test_showdown_players_are_resolved_from_the_database(fresh_db) -> None:
    gametype = add_gametype(fresh_db)
    hand = add_hand(fresh_db, gametype)
    hero = add_player_in_hand(fresh_db, hand, HERO_SEAT, [2, 3, 4, 5, 6])

    assert backfill_showdown._player_ids_for_hand(fresh_db, hand) == {"Player1": hero}


def test_ensuring_the_showdown_table_is_safe_when_it_already_exists(fresh_db) -> None:
    # The script runs against databases created before HandsShowdown existed.
    backfill_showdown._ensure_table(fresh_db)
    backfill_showdown._ensure_table(fresh_db)

    assert rows(fresh_db, "SELECT COUNT(*) FROM HandsShowdown")[0][0] == 0


# --------------------------------------------------------------------------
# The scripts are reachable at all
# --------------------------------------------------------------------------

MAINTENANCE_SCRIPTS = [
    "backfill_autonotes",
    "backfill_boards",
    "backfill_showdown",
    "fix_draw_starting_hands",
    "migration_helper",
    "sync_databases",
]

# sync_databases imports fpdb.infrastructure.adapters.legacy_schema_adapter and
# fpdb.infrastructure.database.models, neither of which has ever existed in this
# repository -- the module arrived dead with the initial legacy import and
# raises ModuleNotFoundError. mypy does not catch it because missing imports are
# ignored. Listed rather than skipped so the day it is repaired or removed, this
# test says so.
UNIMPORTABLE = {"sync_databases"}


@pytest.mark.parametrize("name", [s for s in MAINTENANCE_SCRIPTS if s not in UNIMPORTABLE])
def test_every_maintenance_script_can_be_imported(name) -> None:
    assert importlib.import_module(f"fpdb_3_legacy.{name}") is not None


@pytest.mark.parametrize("name", sorted(UNIMPORTABLE))
def test_the_broken_script_is_still_broken(name) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(f"fpdb_3_legacy.{name}")
