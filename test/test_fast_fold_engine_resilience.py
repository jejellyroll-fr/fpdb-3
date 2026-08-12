"""What the Fast-Fold engine does when something under it fails.

Every one of these paths runs on a live table: a database that has gone away
mid-session, an aux window destroyed while the seats were being read, a HUD
whose layout cannot say where the hero sits. None of them may take the HUD
down -- an overlay that disappears mid-hand is worse than one showing stale
numbers, because the player cannot tell it happened.

They were also the only uncovered part of the engine, and the engine is shared
by every platform: the same ``apply_seats`` and ``clear_seats`` will serve a
Windows and a Linux seat reader.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy.fast_fold_engine import FastFoldEngine, is_fast_fold_table

# ---------------------------------------------------------------------------
# Recognising a Fast-Fold table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("game_type", ["fast", "FAST", "zoom", "Zoom Poker"])
def test_the_game_type_alone_can_settle_it(game_type) -> None:
    assert is_fast_fold_table("", game_type=game_type) is True


@pytest.mark.parametrize("title", ["", None])
def test_a_table_with_no_name_and_no_game_type_is_not_fast_fold(title) -> None:
    """Guessing would put a Fast-Fold HUD on an ordinary cash table."""
    assert is_fast_fold_table(title, game_type="ring") is False


# ---------------------------------------------------------------------------
# Resolving player ids
# ---------------------------------------------------------------------------


def test_a_connection_that_cannot_look_players_up_yields_nothing() -> None:
    """The GUI thread's replay facade has no player lookup."""
    assert FastFoldEngine._resolve_player_ids(object(), ["jejellyroll"]) == {}


def test_no_connection_at_all_yields_nothing() -> None:
    assert FastFoldEngine._resolve_player_ids(None, ["jejellyroll"]) == {}


def test_a_lookup_that_fails_drops_only_that_player() -> None:
    """One unreadable name must not cost the table its other five."""
    conn = MagicMock()
    conn.get_player_id_by_name.side_effect = [RuntimeError("connection reset"), 7]

    ids = FastFoldEngine._resolve_player_ids(conn, ["broken", "villain"])

    assert ids == {"villain": 7}


def test_a_player_the_database_does_not_know_is_dropped() -> None:
    """A new opponent still gets a seat, just with no numbers in it."""
    conn = MagicMock()
    conn.get_player_id_by_name.return_value = None

    assert FastFoldEngine._resolve_player_ids(conn, ["newcomer"]) == {}


# ---------------------------------------------------------------------------
# Reading the statistics
# ---------------------------------------------------------------------------


def test_an_empty_seat_map_reads_nothing() -> None:
    conn = MagicMock()

    assert FastFoldEngine(db_connection=conn).get_player_stats_for_seat_map({}) == {}
    conn.get_stats_for_players.assert_not_called()


def test_a_seat_map_of_empty_names_reads_nothing() -> None:
    """A half-drawn window can name nobody."""
    assert FastFoldEngine(db_connection=MagicMock()).get_player_stats_for_seat_map({1: "", 2: None}) == {}


def test_a_failing_statistics_query_still_seats_everyone() -> None:
    """Named-but-empty blocks beat no blocks: the player sees who is there."""
    conn = MagicMock()
    conn.get_player_id_by_name.side_effect = [1, 2]
    conn.get_stats_for_players.side_effect = RuntimeError("server closed the connection")
    engine = FastFoldEngine(db_connection=conn)

    stat_dict = engine.get_player_stats_for_seat_map({4: "jejellyroll", 5: "villain"}, gametype_id=9)

    assert sorted(row["screen_name"] for row in stat_dict.values()) == ["jejellyroll", "villain"]
    assert all(row["n"] == 0 for row in stat_dict.values())


# ---------------------------------------------------------------------------
# Pinning the hero's seat
# ---------------------------------------------------------------------------


def test_an_aux_window_that_cannot_say_where_the_hero_sits_is_skipped() -> None:
    """A layout read mid-rebuild raises; the default anchor still applies."""
    aux = MagicMock()
    aux._anchor_slot.side_effect = RuntimeError("layout is being rebuilt")
    hud = MagicMock(aux_windows=[aux])
    del hud.fast_fold_hero_seat

    assert FastFoldEngine(config=MagicMock()).pin_hero_seat(hud) == 3


def test_a_hud_with_no_aux_windows_falls_back_to_the_default_anchor() -> None:
    hud = MagicMock(aux_windows=[])
    del hud.fast_fold_hero_seat

    assert FastFoldEngine(config=MagicMock()).pin_hero_seat(hud) == 3


# ---------------------------------------------------------------------------
# Applying and clearing
# ---------------------------------------------------------------------------


def test_nothing_to_update_is_not_an_update() -> None:
    engine = FastFoldEngine(db_connection=MagicMock())

    assert engine.update_hud_seats(None, {1: "villain"}) is False
    assert engine.update_hud_seats(MagicMock(), {}) is False


def test_clearing_a_hud_that_is_gone_is_harmless() -> None:
    """A table can close between the decision to clear and the clearing."""
    FastFoldEngine.clear_seats(None)


def test_one_failing_aux_window_does_not_stop_the_others_clearing() -> None:
    """Blocks left behind by a partial clear describe players who have left."""
    broken, working = MagicMock(), MagicMock()
    broken.refresh_stats.side_effect = RuntimeError("window already destroyed")
    hud = MagicMock(aux_windows=[broken, working])

    FastFoldEngine.clear_seats(hud)

    working.refresh_stats.assert_called_once_with(None)
    assert hud.stat_dict == {}
    assert hud.seat_players == {}


def test_one_failing_aux_window_does_not_stop_the_others_updating() -> None:
    broken, working = MagicMock(), MagicMock()
    broken.refresh_stats.side_effect = RuntimeError("window already destroyed")
    hud = MagicMock(aux_windows=[broken, working], is_loading=False)

    applied = FastFoldEngine.apply_seats(hud, {4: "jejellyroll"}, {1: {"screen_name": "jejellyroll", "seat": 4}})

    assert applied is True
    working.refresh_stats.assert_called_once()


def test_a_loading_placeholder_keeps_the_seats_without_redrawing() -> None:
    """It has no seat windows yet; the real HUD that replaces it will draw them."""
    hud = MagicMock(aux_windows=[MagicMock()], is_loading=True)

    applied = FastFoldEngine.apply_seats(hud, {4: "jejellyroll"}, {1: {"screen_name": "jejellyroll", "seat": 4}})

    assert applied is True
    assert hud.fast_fold_seats == {4: "jejellyroll"}
    hud.aux_windows[0].refresh_stats.assert_not_called()


def test_pinning_a_seat_without_a_hud_still_answers() -> None:
    """Callers ask before the HUD exists; the anchor is a property of the layout."""
    assert FastFoldEngine(config=MagicMock()).pin_hero_seat(None) == 3


def test_an_aux_window_with_no_anchor_to_read_is_skipped() -> None:
    """Mucked and its like carry no seat layout at all."""
    plain = MagicMock()
    plain._anchor_slot = "not callable"
    knows = MagicMock()
    knows._anchor_slot = lambda: 5
    hud = MagicMock(aux_windows=[plain, knows])
    del hud.fast_fold_hero_seat

    assert FastFoldEngine(config=MagicMock()).pin_hero_seat(hud) == 5


def test_a_player_the_query_gave_no_seat_is_not_seated() -> None:
    """A row without a seat cannot be drawn anywhere, and 0 is a real seat."""
    hud = MagicMock(aux_windows=[], is_loading=False)

    FastFoldEngine.apply_seats(
        hud,
        {4: "jejellyroll"},
        {1: {"screen_name": "jejellyroll", "seat": 4}, 2: {"screen_name": "ghost", "seat": None}},
    )

    assert sorted(hud.fast_fold_seat_players) == [4]
