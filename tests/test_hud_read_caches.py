"""Tests for the two HUD read caches, and for the round-trip count they buy.

The HUD asked the database for a hand's gametype, and for the 24-hour boundary
hand id, once per open table per hand dealt. Measured at twelve tables that was
24 of the 41 statements a dealt hand cost -- pure latency over a VPN for two
answers that cannot have moved in between. Caching them takes the cost of a
secondary table refresh from three statements to one.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy import database_hud_stats

# -- gametype per hand ----------------------------------------------------


def test_a_hands_gametype_is_read_once(fresh_db) -> None:
    """A hand's game is settled when the hand is written."""
    fresh_db.connection = MagicMock()
    cursor = fresh_db.connection.cursor.return_value
    cursor.fetchone.return_value = ("PokerStars", "holdem", "hold", "ring", "nl", "h", 1, 2, 1, 2, "USD", 7, 0)

    first = fresh_db.get_gameinfo_from_hid(42)
    second = fresh_db.get_gameinfo_from_hid(42)

    assert first == second
    assert first["gametypeId"] == 7
    assert cursor.execute.call_count == 1


def test_a_different_hand_is_read_again(fresh_db) -> None:
    fresh_db.connection = MagicMock()
    cursor = fresh_db.connection.cursor.return_value
    cursor.fetchone.return_value = ("PokerStars", "holdem", "hold", "ring", "nl", "h", 1, 2, 1, 2, "USD", 7, 0)

    fresh_db.get_gameinfo_from_hid(42)
    fresh_db.get_gameinfo_from_hid(43)

    assert cursor.execute.call_count == 2


def test_a_hand_that_is_not_there_yet_is_not_cached(fresh_db) -> None:
    """Caching the miss would keep denying the hand after the import lands."""
    fresh_db.connection = MagicMock()
    cursor = fresh_db.connection.cursor.return_value
    cursor.fetchone.return_value = None

    assert fresh_db.get_gameinfo_from_hid(99) is None

    cursor.fetchone.return_value = ("PokerStars", "holdem", "hold", "ring", "nl", "h", 1, 2, 1, 2, "USD", 7, 0)
    assert fresh_db.get_gameinfo_from_hid(99)["gametypeId"] == 7
    assert cursor.execute.call_count == 2


def test_wiping_the_database_drops_the_cache(fresh_db) -> None:
    """recreate_tables restarts hand ids from 1; a kept entry would be another hand's."""
    fresh_db.connection = MagicMock()
    cursor = fresh_db.connection.cursor.return_value
    cursor.fetchone.return_value = ("PokerStars", "holdem", "hold", "ring", "nl", "h", 1, 2, 1, 2, "USD", 7, 0)
    fresh_db.get_gameinfo_from_hid(1)

    fresh_db.resetCache()
    fresh_db.get_gameinfo_from_hid(1)

    assert cursor.execute.call_count == 2


# -- the 24-hour boundary -------------------------------------------------


@pytest.fixture
def clock(monkeypatch):
    """A time source the boundary cache can be walked forward against."""
    now = [1000.0]
    monkeypatch.setattr(database_hud_stats, "time", lambda: now[0])
    return now


def test_the_boundary_is_read_once_per_ttl(fresh_db, clock) -> None:
    fresh_db.connection = MagicMock()
    cursor = fresh_db.connection.cursor.return_value
    cursor.fetchone.return_value = (5150,)

    for _ in range(12):  # one per open table, as the HUD would
        fresh_db.init_hud_stat_vars(30, 30)

    assert cursor.execute.call_count == 1
    assert fresh_db.hand_1day_ago == 5150


def test_the_boundary_is_re_read_once_the_ttl_expires(fresh_db, clock) -> None:
    """It is a sliding window; it has to move eventually."""
    fresh_db.connection = MagicMock()
    cursor = fresh_db.connection.cursor.return_value
    cursor.fetchone.return_value = (5150,)
    fresh_db.init_hud_stat_vars(30, 30)

    clock[0] += database_hud_stats.HAND_1DAY_AGO_TTL + 1
    cursor.fetchone.return_value = (5320,)
    fresh_db.init_hud_stat_vars(30, 30)

    assert cursor.execute.call_count == 2
    assert fresh_db.hand_1day_ago == 5320


def test_the_dates_are_still_recomputed_every_time(fresh_db, clock) -> None:
    """Only the query is cached; the day windows are free and must stay fresh."""
    fresh_db.connection = MagicMock()
    fresh_db.connection.cursor.return_value.fetchone.return_value = (5150,)

    fresh_db.init_hud_stat_vars(30, 30)
    thirty_days = fresh_db.date_ndays_ago
    fresh_db.init_hud_stat_vars(1, 1)

    assert fresh_db.date_ndays_ago != thirty_days


def test_wiping_the_database_drops_the_boundary(fresh_db, clock) -> None:
    fresh_db.connection = MagicMock()
    cursor = fresh_db.connection.cursor.return_value
    cursor.fetchone.return_value = (5150,)
    fresh_db.init_hud_stat_vars(30, 30)

    fresh_db.resetCache()
    fresh_db.init_hud_stat_vars(30, 30)

    assert cursor.execute.call_count == 2


# -- what it is worth, counted --------------------------------------------


def test_the_cacheable_part_of_a_table_refresh_costs_nothing(fresh_db, clock) -> None:
    """The regression guard for the win.

    A secondary refresh -- what every open table other than the one that just
    dealt pays, once per hand -- used to issue three statements: the boundary,
    the gametype, and the statistics aggregate. Only the aggregate does work
    that has to reach the server; the other two must now cost nothing, because
    whatever they cost is multiplied by the number of open tables on the thread
    that repaints the HUD.
    """
    fresh_db.connection = MagicMock()
    cursor = fresh_db.connection.cursor.return_value
    cursor.fetchone.side_effect = [
        (5150,),  # the boundary
        ("PokerStars", "holdem", "hold", "ring", "nl", "h", 1, 2, 1, 2, "USD", 7, 0),  # the gametype
    ]

    # The hand that dealt warms both, exactly as HUD_main's update path does.
    fresh_db.init_hud_stat_vars(30, 30)
    fresh_db.get_gameinfo_from_hid(42)
    warmed = cursor.execute.call_count
    assert warmed == 2, "the warm-up itself must still read both"

    # Then eleven other open tables refresh against the same hand.
    for _ in range(11):
        fresh_db.init_hud_stat_vars(30, 30)
        fresh_db.get_gameinfo_from_hid(42)

    assert cursor.execute.call_count == warmed, "eleven tables must add no statements at all"
