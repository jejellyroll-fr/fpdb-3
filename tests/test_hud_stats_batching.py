"""Equivalence tests for the batched HUD statistics query.

Every open table refreshes its statistics on every hand dealt at any table, so
the aggregate runs once per table per hand -- one round trip each, and over a
VPN that is the largest cost the HUD imposes. get_stats_from_hands answers for
several tables in one round trip.

These are the tests that make that change trustworthy: the batched answer is
compared against the per-hand answer, over real imported hands, stat by stat.
A HUD is something a player bets money on, so "faster" is only worth having if
it is first identical.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HANDS_DIR = REPO / "regression-test-files" / "cash" / "Stars" / "Flop"
SITE = "PokerStars.COM"

HUD_PARAMS = {
    "stat_range": "A",
    "agg_bb_mult": 1000,
    "seats_style": "A",
    "seats_cust_nums_low": 1,
    "seats_cust_nums_high": 10,
    "h_stat_range": "A",
    "h_agg_bb_mult": 1000,
    "h_seats_style": "A",
    "h_seats_cust_nums_low": 1,
    "h_seats_cust_nums_high": 10,
}


@pytest.fixture(scope="module")
def imported_db():
    """A database with the regression corpus imported, built once."""
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.Database import Database
    from fpdb_3_legacy.Importer import Importer

    if not HANDS_DIR.is_dir():
        pytest.skip(f"no hand histories at {HANDS_DIR}")

    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = Config(file=str(REPO / "HUD_config.xml"))
        params = cfg.get_db_parameters()
        params.update(
            {
                "db-host": "localhost",
                "db-server": "sqlite",
                "db-backend": 4,
                "db-databaseName": str(Path(tmpdir) / "batching.sqlite3"),
                "db-path": "",
            },
        )
        cfg.get_db_parameters = lambda: params

        db = Database(cfg)
        db.recreate_tables()
        importer = Importer(None, {"threads": 1}, cfg, sql=db.sql)
        # Importer creates its own connection before the fixture replaces it.
        # POSIX lets TemporaryDirectory unlink that still-open SQLite file, but
        # Windows keeps it locked, so close the superseded connection first.
        importer.database.disconnect()
        importer.database = db
        importer.setCallHud(False)
        importer.setMode("bulk")
        importer.addBulkImportImportFileOrDir(str(HANDS_DIR), site=SITE)
        importer.runImport()
        db.connection.commit()

        # Keep importer referenced while the tests run: its __del__ would
        # otherwise disconnect the shared database early.
        yield db, importer
        importer.database = None
        db.disconnect()


def some_hands(db, count):
    c = db.get_cursor()
    c.execute(f"SELECT id FROM Hands ORDER BY id DESC LIMIT {int(count)}")
    return [row[0] for row in c.fetchall()]


def test_the_corpus_actually_imported(imported_db) -> None:
    """Otherwise every equivalence below would pass on two empty dicts."""
    db, _ = imported_db
    hands = some_hands(db, 12)

    assert len(hands) == 12
    stats = db.get_stats_from_hand(hands[0], "ring", HUD_PARAMS, -1, 6)
    assert stats, "the corpus must yield real statistics to compare"


def test_batched_stats_equal_per_hand_stats(imported_db) -> None:
    """The whole point: same numbers, fewer round trips."""
    db, _ = imported_db
    hands = some_hands(db, 12)

    one_at_a_time = {hand: db.get_stats_from_hand(hand, "ring", HUD_PARAMS, -1, 6) for hand in hands}
    batched = db.get_stats_from_hands(hands, "ring", HUD_PARAMS, -1, 6)

    assert set(batched) == set(one_at_a_time)
    for hand in hands:
        assert batched[hand] == one_at_a_time[hand], f"hand {hand} differs between the two paths"


def test_batched_stats_preserve_string_hand_ids_from_zmq(imported_db) -> None:
    """SQL returns integer ids, but HUD_main indexes results with ZMQ strings."""
    db, _ = imported_db
    hands = [str(hand) for hand in some_hands(db, 12)]

    batched = db.get_stats_from_hands(hands, "ring", HUD_PARAMS, -1, 6)

    assert set(batched) == set(hands)
    for hand in hands:
        expected = db.get_stats_from_hand(hand, "ring", HUD_PARAMS, -1, 6)
        assert expected
        assert batched[hand] == expected


def test_the_seat_of_each_player_survives_batching(imported_db) -> None:
    """Seat is the one column that is per-hand rather than per-player.

    It comes from a max() over the join, so it is exactly what a missing hand
    id in the GROUP BY would corrupt -- silently, and only when a player sits
    at more than one of the batched tables.
    """
    db, _ = imported_db
    hands = some_hands(db, 12)

    batched = db.get_stats_from_hands(hands, "ring", HUD_PARAMS, -1, 6)

    for hand in hands:
        per_hand = db.get_stats_from_hand(hand, "ring", HUD_PARAMS, -1, 6)
        for player_id, stats in per_hand.items():
            assert batched[hand][player_id]["seat"] == stats["seat"]


def test_a_player_at_several_batched_tables_keeps_each_seat(imported_db) -> None:
    """The corruption this guards against needs a shared player to appear."""
    db, _ = imported_db
    hands = some_hands(db, 12)
    batched = db.get_stats_from_hands(hands, "ring", HUD_PARAMS, -1, 6)

    seen: dict[int, list] = {}
    for hand, stats in batched.items():
        for player_id in stats:
            seen.setdefault(player_id, []).append(hand)
    shared = {p: hs for p, hs in seen.items() if len(hs) > 1}
    if not shared:
        pytest.skip("no player appears in more than one hand of this corpus")

    for player_id, hand_ids in shared.items():
        for hand in hand_ids:
            expected = db.get_stats_from_hand(hand, "ring", HUD_PARAMS, -1, 6)
            assert batched[hand][player_id] == expected[player_id]


def test_hands_of_different_gametypes_are_split_and_still_correct(imported_db) -> None:
    """gametypeId is a query parameter, so mixed stakes cannot share one query."""
    db, _ = imported_db
    c = db.get_cursor()
    c.execute("SELECT id, gametypeId FROM Hands ORDER BY id DESC LIMIT 40")
    rows = c.fetchall()
    by_type: dict = {}
    for hand_id, gametype_id in rows:
        by_type.setdefault(gametype_id, []).append(hand_id)
    if len(by_type) < 2:
        pytest.skip("corpus does not contain two gametypes")

    hands = [group[0] for group in by_type.values()][:4]
    batched = db.get_stats_from_hands(hands, "ring", HUD_PARAMS, -1, 6)

    for hand in hands:
        assert batched[hand] == db.get_stats_from_hand(hand, "ring", HUD_PARAMS, -1, 6)


def test_one_hand_batched_matches_that_hand_alone(imported_db) -> None:
    db, _ = imported_db
    hand = some_hands(db, 1)[0]

    batched = db.get_stats_from_hands([hand], "ring", HUD_PARAMS, -1, 6)

    assert batched[hand] == db.get_stats_from_hand(hand, "ring", HUD_PARAMS, -1, 6)


def test_no_hands_asks_nothing(imported_db) -> None:
    db, _ = imported_db
    assert db.get_stats_from_hands([]) == {}


def test_a_repeated_hand_is_asked_for_once(imported_db) -> None:
    db, _ = imported_db
    hand = some_hands(db, 1)[0]

    batched = db.get_stats_from_hands([hand, hand, hand], "ring", HUD_PARAMS, -1, 6)

    assert list(batched) == [hand]


def test_an_unknown_hand_is_skipped_not_fatal(imported_db) -> None:
    """A hand the HUD has but the database has not committed yet."""
    db, _ = imported_db
    known = some_hands(db, 1)[0]

    batched = db.get_stats_from_hands([known, 99999999], "ring", HUD_PARAMS, -1, 6)

    assert known in batched
    assert 99999999 not in batched


def test_the_session_range_falls_back_to_asking_per_hand(imported_db) -> None:
    """Session stats read a different query per hand; there is nothing to batch."""
    db, _ = imported_db
    hands = some_hands(db, 4)
    session_params = dict(HUD_PARAMS, stat_range="S", h_stat_range="S")

    batched = db.get_stats_from_hands(hands, "ring", session_params, -1, 6)

    for hand in hands:
        assert batched[hand] == db.get_stats_from_hand(hand, "ring", session_params, -1, 6)


def test_a_query_that_can_no_longer_be_rewritten_falls_back(imported_db) -> None:
    """The rewrite must fail loudly into the slow path, never into wrong numbers."""
    db, _ = imported_db

    assert db._batched_aggregated_sql("SELECT 1 FROM Hands", 3) is None
