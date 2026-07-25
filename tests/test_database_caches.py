"""Behavioural tests for the statistics cache writers.

``database_caches.py`` produces the aggregates the HUD and the reports read:
HudCache, CardsCache, PositionsCache, Sessions, SessionsCache and
TourneysCache. A mistake here does not raise, it displays a wrong number, so
these tests assert on the values written rather than on the absence of an
exception.

Two layers:

* the buffers built while hands are imported (``doinsert=False``), which is
  where the grouping and summing actually happens;
* the flush to a real SQLite schema (``doinsert=True``), which is where those
  buffers meet the rows already in the database.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

import pytest

import fpdb_3_legacy.Database as Database
import fpdb_3_legacy.SQL as SQL

CACHE_KEYS = Database.CACHE_KEYS
HUDCACHE_EXTRA_KEYS = Database.HUDCACHE_EXTRA_KEYS

RING = {"type": "ring"}
TOUR = {"type": "tour"}

# Indices into the packed CACHE_KEYS line, used to read a value back out.
N = CACHE_KEYS.index("n")
VPI = CACHE_KEYS.index("street0VPI")
PROFIT = CACHE_KEYS.index("totalProfit")
SAW_SD = CACHE_KEYS.index("sawShowdown")


def player_stats(position: Any = 0, tourney_type_id: Any = None, **overrides: Any) -> dict[str, Any]:
    """One player's per-hand statistics, as DerivedStats hands them over."""
    stats: dict[str, Any] = dict.fromkeys(CACHE_KEYS, 0)
    stats.update(dict.fromkeys(HUDCACHE_EXTRA_KEYS, 0))
    stats.update(position=position, tourneyTypeId=tourney_type_id, startCards=0)
    stats.update(overrides)
    return stats


def caches_host(**overrides: Any) -> Any:
    """A Database carrying only what the cache mixin borrows from its host.

    Built without __init__ on purpose: the buffer semantics under test need no
    connection, and the borrowed attributes are exactly those the mixin
    declares.
    """
    db = Database.Database.__new__(Database.Database)
    db.day_start = 0
    db.build_full_hudcache = False
    db.sessionTimeout = 30
    db.import_options = {"hhBulkPath": ""}
    db.ttnew, db.ttold = set(), set()
    db.wmnew, db.wmold = set(), set()
    db.hcbulk, db.dcbulk, db.pcbulk, db.tbulk = {}, {}, {}, {}
    db.s = {"bk": []}
    db.sc, db.tc = {}, {}
    db.hbulk, db.hids = [], []
    for name, value in overrides.items():
        setattr(db, name, value)
    return db


# --------------------------------------------------------------------------
# HudCache
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("position", "bucket"),
    [(0, "D"), (1, "C"), (2, "M"), (4, "M"), (5, "E"), (9, "E"), ("B", "B"), ("S", "S")],
)
def test_hudcache_buckets_each_position_into_its_letter(position, bucket) -> None:
    # The HUD reads these letters back; stat_adapters and the aggregated-stats
    # query both depend on this exact mapping.
    db = caches_host()

    db.storeHudCache(7, RING, {"Hero": 1}, datetime(2026, 7, 20, 14, 30), {"Hero": player_stats(position=position)})

    assert [key[3] for key in db.hcbulk] == [bucket]


def test_hudcache_key_records_gametype_player_seats_and_tourney_type() -> None:
    db = caches_host()
    pids = {"Hero": 11, "Villain": 22}

    db.storeHudCache(
        7,
        TOUR,
        pids,
        datetime(2026, 7, 20, 14, 30),
        {"Hero": player_stats(position=0, tourney_type_id=3), "Villain": player_stats(position=1, tourney_type_id=3)},
    )

    assert set(db.hcbulk) == {(7, 11, 2, "D", 3, "A000000"), (7, 22, 2, "C", 3, "A000000")}


def test_hudcache_sums_repeated_hands_and_counts_them() -> None:
    db = caches_host()
    pids = {"Hero": 11}

    for profit in (250, -100):
        db.storeHudCache(
            7,
            RING,
            pids,
            datetime(2026, 7, 20, 14, 30),
            {"Hero": player_stats(position=0, street0VPI=1, totalProfit=profit)},
        )

    (line,) = db.hcbulk.values()
    assert line[N] == 2
    assert line[VPI] == 2
    assert line[PROFIT] == 150


def test_hudcache_coerces_booleans_so_sums_stay_numeric() -> None:
    # DerivedStats yields booleans for several flags; summing them as bools
    # would make the column unusable.
    db = caches_host()

    for _ in range(2):
        db.storeHudCache(
            7,
            RING,
            {"Hero": 11},
            datetime(2026, 7, 20, 14, 30),
            {"Hero": player_stats(position=0, sawShowdown=True)},
        )

    (line,) = db.hcbulk.values()
    assert line[SAW_SD] == 2
    assert not isinstance(line[SAW_SD], bool)


def test_hudcache_dates_the_style_key_when_the_full_cache_is_built() -> None:
    # The exact day depends on the machine's UTC offset (see
    # test_style_key_day_offset_is_computed_from_a_negative_timedelta), so pin
    # the shape rather than the value.
    db = caches_host(build_full_hudcache=True)

    db.storeHudCache(7, RING, {"Hero": 11}, datetime(2026, 7, 20, 14, 30), {"Hero": player_stats()})

    ((*_, style_key),) = db.hcbulk
    assert re.fullmatch(r"d\d{6}", style_key)


def test_hudcache_groups_a_days_hands_under_one_style_key() -> None:
    db = caches_host(build_full_hudcache=True)
    start = datetime(2026, 7, 20, 14, 30)

    db.storeHudCache(7, RING, {"Hero": 11}, start, {"Hero": player_stats()})
    db.storeHudCache(7, RING, {"Hero": 11}, start + timedelta(minutes=1), {"Hero": player_stats()})
    db.storeHudCache(7, RING, {"Hero": 11}, start + timedelta(days=5), {"Hero": player_stats()})

    style_keys = [key[-1] for key in db.hcbulk]
    assert len(style_keys) == 2
    assert len(set(style_keys)) == 2


def test_hudcache_skips_garbage_tourney_types_during_bulk_import() -> None:
    # A bulk import rebuilds these rows wholesale afterwards; feeding them
    # during the import would double-count.
    db = caches_host(import_options={"hhBulkPath": "/tmp/hands"}, ttnew={3})

    db.storeHudCache(
        7,
        TOUR,
        {"Hero": 11, "Villain": 22},
        datetime(2026, 7, 20, 14, 30),
        {"Hero": player_stats(tourney_type_id=3), "Villain": player_stats(position=1, tourney_type_id=9)},
    )

    assert [key[1] for key in db.hcbulk] == [22]


# --------------------------------------------------------------------------
# Sessions: the grouping of hands into playing sessions
# --------------------------------------------------------------------------


def store_session(db: Any, hid: int, start: datetime, tid: Any = None, hero_id: int = 11) -> None:
    """Feed one hand to the session grouper, as Hand.updateSessionsCache does."""
    db.storeSessions(hid, {"Hero": hero_id}, start, tid, [11], "UTC")


def test_first_hand_opens_a_session_bounded_by_itself() -> None:
    db = caches_host()
    start = datetime(2026, 7, 20, 14, 30)

    store_session(db, 1, start)

    (bucket,) = db.s["bk"]
    assert (bucket["sessionStart"], bucket["sessionEnd"]) == (start, start)
    assert bucket["ids"] == [1]


def test_a_hand_inside_the_timeout_extends_the_session_rather_than_opening_one() -> None:
    db = caches_host()
    start = datetime(2026, 7, 20, 14, 30)

    store_session(db, 1, start)
    store_session(db, 2, start + timedelta(minutes=20))

    (bucket,) = db.s["bk"]
    assert bucket["sessionEnd"] == start + timedelta(minutes=20)
    assert bucket["ids"] == [1, 2]


def test_an_earlier_hand_moves_the_session_start_backwards() -> None:
    # Hands do not arrive in chronological order when several files are imported.
    db = caches_host()
    start = datetime(2026, 7, 20, 14, 30)

    store_session(db, 1, start)
    store_session(db, 2, start - timedelta(minutes=20))

    (bucket,) = db.s["bk"]
    assert bucket["sessionStart"] == start - timedelta(minutes=20)
    assert bucket["sessionEnd"] == start


def test_a_hand_beyond_the_timeout_opens_a_second_session() -> None:
    db = caches_host()
    start = datetime(2026, 7, 20, 14, 30)

    store_session(db, 1, start)
    store_session(db, 2, start + timedelta(hours=3))

    assert len(db.s["bk"]) == 2


def test_a_bridging_hand_merges_two_sessions_into_one() -> None:
    db = caches_host()
    start = datetime(2026, 7, 20, 14, 30)
    store_session(db, 1, start)
    store_session(db, 2, start + timedelta(minutes=50))
    assert len(db.s["bk"]) == 2

    # 14:55 is within the 30-minute timeout of both.
    store_session(db, 3, start + timedelta(minutes=25))

    (bucket,) = db.s["bk"]
    assert (bucket["sessionStart"], bucket["sessionEnd"]) == (start, start + timedelta(minutes=50))
    assert sorted(bucket["ids"]) == [1, 2, 3]


def test_hands_of_one_tournament_share_a_session_across_the_timeout() -> None:
    # A tournament can pause far longer than the timeout and still be one session.
    db = caches_host()
    start = datetime(2026, 7, 20, 14, 30)

    store_session(db, 1, start, tid=42)
    store_session(db, 2, start + timedelta(hours=5), tid=42)

    (bucket,) = db.s["bk"]
    assert bucket["tourneys"] == {42}
    assert bucket["ids"] == [1, 2]


def test_a_hand_the_hero_did_not_play_opens_no_session() -> None:
    db = caches_host()

    db.storeSessions(1, {"Villain": 22}, datetime(2026, 7, 20, 14, 30), None, [11], "UTC")

    assert db.s["bk"] == []


# --------------------------------------------------------------------------
# SessionsCache: per game type and player
# --------------------------------------------------------------------------


def store_sessions_cache(db: Any, hid: int, start: datetime, pdata: dict, gametype_id: int = 5) -> None:
    pids = {name: 11 if name == "Hero" else 22 for name in pdata}
    db.storeSessionsCache(hid, pids, start, gametype_id, RING, pdata, [11])


def test_sessions_cache_sums_a_players_hands_within_one_session() -> None:
    db = caches_host()
    start = datetime(2026, 7, 20, 14, 30)

    store_sessions_cache(db, 1, start, {"Hero": player_stats(street0VPI=1, totalProfit=300)})
    store_sessions_cache(db, 2, start + timedelta(minutes=10), {"Hero": player_stats(street0VPI=1, totalProfit=-100)})

    (sessions,) = db.sc.values()
    (session,) = sessions
    assert session["line"][N] == 2
    assert session["line"][VPI] == 2
    assert session["line"][PROFIT] == 200


def test_sessions_cache_keeps_game_types_apart() -> None:
    # Mixing a 0.01/0.02 session into a 5/10 one would corrupt both.
    db = caches_host()
    start = datetime(2026, 7, 20, 14, 30)

    store_sessions_cache(db, 1, start, {"Hero": player_stats(totalProfit=300)}, gametype_id=5)
    store_sessions_cache(db, 2, start, {"Hero": player_stats(totalProfit=700)}, gametype_id=6)

    assert set(db.sc) == {(5, 11), (6, 11)}
    assert [s[0]["line"][PROFIT] for s in db.sc.values()] == [300, 700]


def test_sessions_cache_records_hand_ids_for_the_hero_only() -> None:
    db = caches_host()
    start = datetime(2026, 7, 20, 14, 30)

    store_sessions_cache(db, 1, start, {"Hero": player_stats(), "Villain": player_stats(position=1)})

    assert db.sc[(5, 11)][0]["ids"] == [1]
    assert db.sc[(5, 22)][0]["ids"] == []


def test_sessions_cache_splits_sessions_beyond_the_timeout() -> None:
    db = caches_host()
    start = datetime(2026, 7, 20, 14, 30)

    store_sessions_cache(db, 1, start, {"Hero": player_stats(totalProfit=300)})
    store_sessions_cache(db, 2, start + timedelta(hours=4), {"Hero": player_stats(totalProfit=700)})

    (sessions,) = db.sc.values()
    assert [s["line"][PROFIT] for s in sessions] == [300, 700]


def test_sessions_cache_merges_two_sessions_bridged_by_a_hand() -> None:
    db = caches_host()
    start = datetime(2026, 7, 20, 14, 30)
    store_sessions_cache(db, 1, start, {"Hero": player_stats(totalProfit=300)})
    store_sessions_cache(db, 2, start + timedelta(minutes=50), {"Hero": player_stats(totalProfit=700)})
    assert len(db.sc[(5, 11)]) == 2

    store_sessions_cache(db, 3, start + timedelta(minutes=25), {"Hero": player_stats(totalProfit=11)})

    (session,) = db.sc[(5, 11)]
    assert session["line"][PROFIT] == 1011
    assert session["line"][N] == 3


# --------------------------------------------------------------------------
# TourneysCache
# --------------------------------------------------------------------------


def test_tourneys_cache_ignores_ring_hands() -> None:
    db = caches_host()

    db.storeTourneysCache(1, {"Hero": 11}, datetime(2026, 7, 20, 14, 30), 42, RING, {"Hero": player_stats()}, [11])

    assert db.tc == {}


def test_tourneys_cache_sums_a_players_hands_and_spans_the_tournament() -> None:
    db = caches_host()
    start = datetime(2026, 7, 20, 14, 30)

    for offset, profit in ((2, 700), (0, 300), (1, -100)):
        db.storeTourneysCache(
            offset + 1,
            {"Hero": 11},
            start + timedelta(hours=offset),
            42,
            TOUR,
            {"Hero": player_stats(totalProfit=profit)},
            [11],
        )

    entry = db.tc[(42, 11)]
    assert entry["line"][N] == 3
    assert entry["line"][PROFIT] == 900
    assert entry["startTime"] == start
    assert entry["endTime"] == start + timedelta(hours=2)


def test_tourneys_cache_anchors_its_hand_id_on_the_earliest_hand() -> None:
    # The flush reads the session of tc["hid"]; it must be a hand of this tourney
    # that actually opened it.
    db = caches_host()
    start = datetime(2026, 7, 20, 14, 30)

    db.storeTourneysCache(9, {"Hero": 11}, start + timedelta(hours=2), 42, TOUR, {"Hero": player_stats()}, [11])
    db.storeTourneysCache(4, {"Hero": 11}, start, 42, TOUR, {"Hero": player_stats()}, [11])

    assert db.tc[(42, 11)]["hid"] == 4


# --------------------------------------------------------------------------
# CardsCache and PositionsCache
# --------------------------------------------------------------------------


def test_cards_cache_keys_each_player_hand_by_its_starting_cards() -> None:
    db = caches_host()

    db.storeCardsCache(
        7,
        {"Hero": 11, "Villain": 22},
        datetime(2026, 7, 20, 14, 30),
        5,
        None,
        {"Hero": player_stats(startCards=169), "Villain": player_stats(position=1, startCards=13)},
        [11],
        "UTC",
        False,
    )

    assert set(db.dcbulk) == {(7, 5, None, 11, 169), (7, 5, None, 22, 13)}


def test_positions_cache_keys_on_seats_max_position_and_position() -> None:
    db = caches_host()

    db.storePositionsCache(
        7,
        {"Hero": 11, "Villain": 22},
        datetime(2026, 7, 20, 14, 30),
        5,
        None,
        {"Hero": player_stats(position=0), "Villain": player_stats(position="B")},
        {"maxPosition": 5},
        [11],
        "UTC",
        False,
    )

    assert set(db.pcbulk) == {(7, 5, None, 11, 2, 5, "0"), (7, 5, None, 22, 2, 5, "B")}


# --------------------------------------------------------------------------
# appendHandsSessionIds
# --------------------------------------------------------------------------


def test_hands_receive_the_session_id_resolved_for_them() -> None:
    db = caches_host()
    db.hids = [101, 102]
    db.hbulk = [[None, None, None, None, None], [None, None, 42, None, None]]
    db.s = {"bk": [], 101: {"id": 7, "wid": 1, "mid": 2}, 102: {"id": 8, "wid": 1, "mid": 2}}

    db.appendHandsSessionIds()

    assert [row[4] for row in db.hbulk] == [7, 8]
    assert db.tbulk == {42: 8}


def test_a_hand_without_a_session_keeps_its_empty_session_id() -> None:
    db = caches_host()
    db.hids = [101]
    db.hbulk = [[None, None, None, None, None]]
    db.s = {"bk": []}

    db.appendHandsSessionIds()

    assert db.hbulk[0][4] is None
    assert db.tbulk == {}


# --------------------------------------------------------------------------
# Flush to a real schema
# --------------------------------------------------------------------------


def rows(db: Any, query: str) -> list[tuple]:
    cursor = db.get_cursor()
    cursor.execute(query)
    return cursor.fetchall()


def test_flushing_sessions_writes_one_row_spanning_the_whole_session(fresh_db) -> None:
    start = datetime(2026, 7, 20, 14, 30)
    fresh_db.storeSessions(1, {"Hero": 11}, start, None, [11], "UTC")
    fresh_db.storeSessions(2, {"Hero": 11}, start + timedelta(minutes=10), None, [11], "UTC", True)

    (row,) = rows(fresh_db, "SELECT sessionStart, sessionEnd FROM Sessions")

    assert str(row[0]).startswith("2026-07-20 14:30")
    assert str(row[1]).startswith("2026-07-20 14:40")


def test_flushing_sessions_links_a_week_and_a_month(fresh_db) -> None:
    fresh_db.storeSessions(1, {"Hero": 11}, datetime(2026, 7, 20, 14, 30), None, [11], "UTC", True)

    (row,) = rows(fresh_db, "SELECT weekId, monthId FROM Sessions")

    assert row[0] is not None
    assert row[1] is not None
    assert rows(fresh_db, "SELECT COUNT(*) FROM Weeks")[0][0] == 1
    assert rows(fresh_db, "SELECT COUNT(*) FROM Months")[0][0] == 1


def test_flushing_sessions_resolves_a_session_id_for_every_hand(fresh_db) -> None:
    # appendHandsSessionIds later reads self.s[hid]; without it, hands are
    # stored with no session and the session reports lose them.
    start = datetime(2026, 7, 20, 14, 30)
    fresh_db.storeSessions(1, {"Hero": 11}, start, None, [11], "UTC")
    fresh_db.storeSessions(2, {"Hero": 11}, start + timedelta(minutes=10), None, [11], "UTC", True)

    assert fresh_db.s[1]["id"] == fresh_db.s[2]["id"]
    assert rows(fresh_db, "SELECT id FROM Sessions")[0][0] == fresh_db.s[1]["id"]


def test_a_second_import_extends_the_existing_session_rather_than_adding_one(fresh_db) -> None:
    start = datetime(2026, 7, 20, 14, 30)
    fresh_db.storeSessions(1, {"Hero": 11}, start, None, [11], "UTC", True)
    fresh_db.resetBulkCache()

    fresh_db.storeSessions(2, {"Hero": 11}, start + timedelta(minutes=20), None, [11], "UTC", True)

    (row,) = rows(fresh_db, "SELECT sessionStart, sessionEnd FROM Sessions")
    assert str(row[1]).startswith("2026-07-20 14:50")


def test_flushing_the_hud_cache_writes_the_aggregated_row(fresh_db) -> None:
    start = datetime(2026, 7, 20, 14, 30)
    for profit in (300, -100):
        fresh_db.storeHudCache(
            5, RING, {"Hero": 11}, start, {"Hero": player_stats(position=0, street0VPI=1, totalProfit=profit)}
        )
    fresh_db.storeHudCache(5, RING, {"Hero": 11}, start, {"Hero": player_stats(position=0)}, True)

    (row,) = rows(fresh_db, "SELECT gametypeId, playerId, seats, position, n, totalProfit FROM HudCache")

    assert row == (5, 11, 1, "D", 3, 200)


def test_flushing_the_hud_cache_twice_updates_the_existing_row(fresh_db) -> None:
    # Re-importing a file must not double a player's profit.
    start = datetime(2026, 7, 20, 14, 30)
    fresh_db.storeHudCache(5, RING, {"Hero": 11}, start, {"Hero": player_stats(position=0, totalProfit=300)}, True)
    fresh_db.resetBulkCache()

    fresh_db.storeHudCache(5, RING, {"Hero": 11}, start, {"Hero": player_stats(position=0, totalProfit=50)}, True)

    (row,) = rows(fresh_db, "SELECT n, totalProfit FROM HudCache")
    assert row == (2, 350)


# --------------------------------------------------------------------------
# The CACHE_KEYS drift
#
# CACHE_KEYS carries 253 statistics. HudCache was widened to hold them all when
# issue #134 was fixed, and test_hudcache_schema_sync.py guards it. The four
# other cache tables were never widened: they hold 116 of those 253 columns,
# and their INSERT statements bind ~120 values while the writers supply ~258.
# Every insert into them therefore raises, so SessionsCache, TourneysCache,
# CardsCache and PositionsCache cannot be populated at all.
#
# The writers are only reached when the `cacheSessions` import option is on,
# and it ships off, which is why this has stayed invisible.
#
# The xfails below are strict: widening the four tables will turn them green
# and CI will then require the markers to go.
# --------------------------------------------------------------------------

CACHE_INSERTS = {
    # query name: values the writer supplies (see database_caches.py)
    "insert_hudcache": 6 + len(CACHE_KEYS) + len(HUDCACHE_EXTRA_KEYS),
    "insert_SC": 5 + len(CACHE_KEYS),
    "insert_TC": 5 + len(CACHE_KEYS),
    "insert_cardscache": 6 + len(CACHE_KEYS),
    "insert_positionscache": 8 + len(CACHE_KEYS),
}


@pytest.mark.parametrize(
    "query_name",
    [
        "insert_hudcache",
        pytest.param("insert_SC", marks=pytest.mark.xfail(strict=True, reason="SessionsCache holds 116/253 CACHE_KEYS")),
        pytest.param("insert_TC", marks=pytest.mark.xfail(strict=True, reason="TourneysCache holds 116/253 CACHE_KEYS")),
        pytest.param(
            "insert_cardscache",
            marks=pytest.mark.xfail(strict=True, reason="CardsCache holds 116/253 CACHE_KEYS"),
        ),
        pytest.param(
            "insert_positionscache",
            marks=pytest.mark.xfail(strict=True, reason="PositionsCache holds 116/253 CACHE_KEYS"),
        ),
    ],
)
def test_every_cache_insert_binds_as_many_values_as_its_writer_supplies(query_name) -> None:
    query = SQL.Sql(db_server="sqlite").query[query_name]

    assert query.count("?") == CACHE_INSERTS[query_name]


@pytest.mark.xfail(strict=True, reason="SessionsCache holds 116 of the 253 CACHE_KEYS columns")
def test_flushing_writes_the_summed_statistics_of_a_cash_session(fresh_db) -> None:
    start = datetime(2026, 7, 20, 14, 30)
    pids = {"Hero": 11}
    for hid, offset, profit in ((1, 0, 300), (2, 10, -100)):
        moment = start + timedelta(minutes=offset)
        last = hid == 2
        fresh_db.storeSessions(hid, pids, moment, None, [11], "UTC", last)
        fresh_db.storeSessionsCache(
            hid, pids, moment, 5, RING, {"Hero": player_stats(street0VPI=1, totalProfit=profit)}, [11], last
        )

    (row,) = rows(fresh_db, "SELECT gametypeId, playerId, n, street0VPI, totalProfit FROM SessionsCache")
    assert row == (5, 11, 2, 2, 200)


@pytest.mark.xfail(strict=True, reason="TourneysCache holds 116 of the 253 CACHE_KEYS columns")
def test_flushing_writes_the_summed_statistics_of_a_tournament(fresh_db) -> None:
    start = datetime(2026, 7, 20, 14, 30)
    pids = {"Hero": 11}
    fresh_db.storeSessions(1, pids, start, 42, [11], "UTC", True)
    fresh_db.storeTourneysCache(1, pids, start, 42, TOUR, {"Hero": player_stats(totalProfit=700)}, [11], True)

    (row,) = rows(fresh_db, "SELECT tourneyId, playerId, n, totalProfit FROM TourneysCache")
    assert row == (42, 11, 1, 700)


@pytest.mark.xfail(strict=True, reason="CardsCache holds 116 of the 253 CACHE_KEYS columns")
def test_flushing_writes_the_statistics_of_a_starting_hand(fresh_db) -> None:
    start = datetime(2026, 7, 20, 14, 30)
    pids = {"Hero": 11}
    fresh_db.storeSessions(1, pids, start, None, [11], "UTC", True)
    fresh_db.storeCardsCache(
        1, pids, start, 5, None, {"Hero": player_stats(startCards=169, totalProfit=300)}, [11], "UTC", True
    )

    (row,) = rows(fresh_db, "SELECT startCards, n, totalProfit FROM CardsCache")
    assert row == (169, 1, 300)


@pytest.mark.xfail(strict=True, reason="PositionsCache holds 116 of the 253 CACHE_KEYS columns")
def test_flushing_writes_the_statistics_of_a_position(fresh_db) -> None:
    start = datetime(2026, 7, 20, 14, 30)
    pids = {"Hero": 11}
    fresh_db.storeSessions(1, pids, start, None, [11], "UTC", True)
    fresh_db.storePositionsCache(
        1, pids, start, 5, None, {"Hero": player_stats(position=0, totalProfit=300)}, {"maxPosition": 5}, [11],
        "UTC", True,
    )

    (row,) = rows(fresh_db, "SELECT position, n, totalProfit FROM PositionsCache")
    assert row == ("0", 1, 300)


def test_style_key_day_offset_is_computed_from_a_negative_timedelta() -> None:
    """Pins a latent defect in storeHudCache's timezone arithmetic.

    ``datetime.utcnow() - datetime.today()`` is negative outside UTC, and
    ``timedelta.seconds`` never is: at UTC+2 the difference is
    ``-1 day, 21:59:59`` whose ``.seconds`` is 79199, so the code derives a
    21-hour offset instead of -2. Even at UTC it derives 23 rather than 0.
    The dated styleKey therefore files hands under the wrong day, and the
    `day_start` preference is added to a bogus base.

    Only reached with ``build_full_hudcache`` on. Recorded rather than fixed:
    changing it moves existing HudCache rows to different styleKey buckets.
    """
    delta = datetime.utcnow() - datetime.today()
    computed = delta.seconds // 3600
    true_hours = delta.total_seconds() / 3600

    # timedelta.seconds is never negative, so the derived offset never is either.
    assert computed >= 0
    if true_hours < 0:
        # East of UTC, and on a UTC runner, the sign is lost: the offset comes
        # back as 24 + true_hours instead of the small negative it should be.
        assert computed > 0
