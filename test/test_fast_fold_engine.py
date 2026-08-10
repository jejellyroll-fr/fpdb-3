"""Unit tests for FastFoldEngine and real-time Fast-Fold HUD updates."""

from __future__ import annotations

from unittest.mock import MagicMock

from fpdb_3_legacy.fast_fold_engine import FastFoldEngine, build_seat_map, is_fast_fold_table


def test_build_seat_map_anchors_hero_and_keeps_clockwise_order() -> None:
    # Ring is clockwise from the small blind; hero acted third.
    ring = ["SB_guy", "BB_guy", "Hero", "UTG1", "CO", "BTN"]

    seats = build_seat_map(ring, "Hero", max_seats=6, hero_seat=1)

    assert seats[1] == "Hero"
    # Everyone else follows clockwise from the hero, wrapping the blinds around.
    assert seats == {1: "Hero", 2: "UTG1", 3: "CO", 4: "BTN", 5: "SB_guy", 6: "BB_guy"}


def test_build_seat_map_respects_pinned_hero_seat() -> None:
    """The hero must land on the seat adj_seats already rotated to the bottom."""
    ring = ["SB_guy", "BB_guy", "Hero"]

    seats = build_seat_map(ring, "Hero", max_seats=6, hero_seat=4)

    assert seats[4] == "Hero"
    assert seats == {4: "Hero", 2: "SB_guy", 3: "BB_guy"}


def test_build_seat_map_is_stable_when_the_button_moves() -> None:
    """Same players, next hand, blinds moved: seat numbers must not change."""
    hand1 = build_seat_map(["A", "B", "Hero", "C"], "Hero", max_seats=4, hero_seat=1)
    hand2 = build_seat_map(["B", "Hero", "C", "A"], "Hero", max_seats=4, hero_seat=1)

    assert hand1 == hand2


def test_build_seat_map_without_hero_returns_empty() -> None:
    assert build_seat_map(["A", "B"], None, max_seats=6) == {}
    assert build_seat_map(["A", "B"], "Hero", max_seats=6) == {}
    assert build_seat_map([], "Hero", max_seats=6) == {}


def test_is_fast_fold_table_detection() -> None:
    assert is_fast_fold_table("Winamax Go Fast Pool 1") is True
    assert is_fast_fold_table("Winamax HOLD-UP 0.05/0.10") is True
    assert is_fast_fold_table("PokerStars Zoom - Table 1") is True
    assert is_fast_fold_table("Rush Poker - NL50") is True
    assert is_fast_fold_table("Winamax Casablanca 02") is False
    assert is_fast_fold_table("Winamax Poker - Expresso 5€ - 12345") is False
    assert is_fast_fold_table(None, game_type="fast_fold") is True


def _db_with_players(**stats_by_id):
    """A db whose aggregate answers with raw HUD counter rows, as the real one does."""
    ids = {"PlayerA": 101, "PlayerB": 102}
    mock_db = MagicMock()
    mock_db.get_player_id_by_name.side_effect = ids.get
    mock_db.get_stats_for_players.return_value = {int(k): v for k, v in stats_by_id.items()}
    return mock_db


def test_fast_fold_engine_stat_fetching() -> None:
    mock_db = _db_with_players(
        **{
            "101": {"player_id": 101, "screen_name": "PlayerA", "n": 150, "vpip": 37, "pfr": 27},
            "102": {"player_id": 102, "screen_name": "PlayerB", "n": 50, "vpip": 20, "pfr": 5},
        }
    )

    engine = FastFoldEngine(db_connection=mock_db)
    stat_dict = engine.get_player_stats_for_seat_map({1: "PlayerA", 2: "PlayerB"}, gametype_id=7)

    mock_db.get_stats_for_players.assert_called_once()
    assert sorted(mock_db.get_stats_for_players.call_args[0][0]) == [101, 102]
    assert mock_db.get_stats_for_players.call_args[0][1] == 7
    # Raw counters are passed through untouched: the stat functions do the maths.
    assert stat_dict[101]["screen_name"] == "PlayerA"
    assert stat_dict[101]["vpip"] == 37
    assert stat_dict[101]["seat"] == 1
    assert stat_dict[102]["seat"] == 2


def test_seat_map_keeps_players_the_aggregate_returned_nothing_for() -> None:
    """A brand-new opponent must still get a named seat, not a hole in the table."""
    mock_db = _db_with_players(**{"101": {"player_id": 101, "screen_name": "PlayerA", "n": 150}})

    engine = FastFoldEngine(db_connection=mock_db)
    stat_dict = engine.get_player_stats_for_seat_map({1: "PlayerA", 2: "PlayerB"}, gametype_id=7)

    seats = {row["seat"]: row["screen_name"] for row in stat_dict.values()}
    assert seats == {1: "PlayerA", 2: "PlayerB"}
    assert stat_dict[102]["n"] == 0


def test_seat_map_without_a_gametype_still_names_the_seats() -> None:
    """Before any hand is imported there is no gametypeId to compare stakes with."""
    mock_db = _db_with_players()

    engine = FastFoldEngine(db_connection=mock_db)
    stat_dict = engine.get_player_stats_for_seat_map({1: "PlayerA"}, gametype_id=None)

    mock_db.get_stats_for_players.assert_not_called()
    assert stat_dict[101]["screen_name"] == "PlayerA"
    assert stat_dict[101]["seat"] == 1


def test_fast_fold_engine_hud_update() -> None:
    mock_hud = MagicMock()
    mock_db = MagicMock()
    mock_db.get_player_id_by_name.return_value = 55
    mock_db.get_stats_for_players.return_value = {
        55: {"player_id": 55, "screen_name": "HeroOpponent", "n": 80, "vpip": 22, "pfr": 16},
    }

    mock_aux = MagicMock()
    mock_hud.aux_windows = [mock_aux]
    mock_hud.is_loading = False

    engine = FastFoldEngine(db_connection=mock_db)
    success = engine.update_hud_seats(mock_hud, {1: "HeroOpponent"}, game_type="ring", gametype_id=7)

    assert success is True
    assert 55 in mock_hud.stat_dict
    assert mock_hud.stat_dict[55]["screen_name"] == "HeroOpponent"
    assert mock_hud.seat_players[1]["screen_name"] == "HeroOpponent"
    # Redraw straight from stat_dict: the live hand is not in the database yet,
    # so update_data would query for a hand that does not exist.
    mock_aux.refresh_stats.assert_called_once_with(None)
    mock_aux.update_data.assert_not_called()


def test_partial_hand_seat_map_extraction() -> None:
    from fpdb_3_legacy.WinamaxToFpdb import Winamax

    mock_config = MagicMock()
    parser = Winamax(mock_config)
    hand_text = (
        'Winamax Poker - Go Fast "Marbella" - HandId: #9434802-28434-1490719852 - Holdem no limit (2€/4€)\n'
        "Table: 'Marbella' 6-max (real money) Seat #1 is the button\n"
        "Seat 1: Player15 (86.50€)\n"
        "Seat 2: player2 (102€)\n"
        "Seat 3: Player13.. (99.50€)\n"
        "Seat 4: Player14 (36€)\n"
        "Seat 5: Hero (101.50€)\n"
        "Seat 6: Player16 (80.50€)\n"
        "*** ANTE/BLINDS ***\n"
        "Player15 posts small blind 1€\n"
        "player2 posts big blind 2€\n"
        "Dealt to Hero [9h 7h 8d 7d]\n"
        "*** PRE-FLOP ***\n"
    )

    mock_hand = MagicMock()
    mock_hand.handText = hand_text

    try:
        parser.readPlayerStacks(mock_hand)
    except Exception:
        pass

    assert hasattr(mock_hand, "seat_map")
    assert mock_hand.seat_map == {
        1: "Player15",
        2: "player2",
        3: "Player13..",
        4: "Player14",
        5: "Hero",
        6: "Player16",
    }


def test_pin_hero_seat_locks_to_the_layout_anchor_seat() -> None:
    """FastFold HUDs always anchor the hero at the bottom-centre (seat 3 by default)."""
    config = MagicMock()
    config.is_hero_name.side_effect = lambda _site, name: name == "Hero"
    hud = MagicMock()
    hud.stat_dict = {7: {"screen_name": "Hero", "seat": 4}, 8: {"screen_name": "Villain", "seat": 2}}
    del hud.fast_fold_hero_seat

    assert FastFoldEngine(config=config).pin_hero_seat(hud) == 3


def test_pin_hero_seat_falls_back_to_the_layout_anchor_before_any_hand() -> None:
    """A loading HUD has no stats yet, so adj_seats left the layout unrotated."""
    config = MagicMock()
    config.is_hero_name.return_value = False
    aux = MagicMock()
    aux._anchor_slot.return_value = 5
    hud = MagicMock()
    hud.stat_dict = {}
    hud.aux_windows = [aux]
    del hud.fast_fold_hero_seat

    assert FastFoldEngine(config=config).pin_hero_seat(hud) == 5


def test_pin_hero_seat_is_remembered_once_decided() -> None:
    hud = MagicMock()
    hud.fast_fold_hero_seat = 3

    assert FastFoldEngine(config=MagicMock()).pin_hero_seat(hud) == 3


def test_clear_seats_blanks_the_overlay_and_redraws() -> None:
    aux = MagicMock()
    hud = MagicMock()
    hud.aux_windows = [aux]

    FastFoldEngine.clear_seats(hud)

    assert hud.stat_dict == {}
    assert hud.seat_players == {}
    assert hud.fast_fold_seats == {}
    aux.refresh_stats.assert_called_once_with(None)


def test_apply_seats_ignores_an_empty_read() -> None:
    hud = MagicMock()
    hud.aux_windows = []

    assert FastFoldEngine.apply_seats(hud, {1: "A"}, {}) is False


def test_a_placeholder_hud_keeps_the_seats_without_being_redrawn() -> None:
    """It has no seat windows yet, so asking it to redraw raises."""
    mock_db = _db_with_players(**{"101": {"player_id": 101, "screen_name": "PlayerA", "n": 5}})
    aux = MagicMock()
    hud = MagicMock()
    hud.aux_windows = [aux]
    hud.is_loading = True

    engine = FastFoldEngine(db_connection=mock_db)
    assert engine.update_hud_seats(hud, {1: "PlayerA"}, gametype_id=7) is True

    assert hud.seat_players[1]["screen_name"] == "PlayerA"
    aux.refresh_stats.assert_not_called()
    # Still the placeholder: only a real hand can give it its seat windows.
    assert hud.is_loading is True


def test_every_seat_points_at_a_row_the_stats_actually_hold() -> None:
    """A seat whose player id is missing from stat_dict shows a nameless NA column.

    playername returns "" on KeyError and every other stat reads NA, so this
    invariant is what keeps an unknown opponent's name on screen.
    """
    mock_db = _db_with_players(**{"101": {"player_id": 101, "screen_name": "PlayerA", "n": 150}})
    aux = MagicMock()
    hud = MagicMock()
    hud.aux_windows = [aux]
    hud.is_loading = False

    engine = FastFoldEngine(db_connection=mock_db)
    # PlayerB is unknown to the database and gets a placeholder row.
    assert engine.update_hud_seats(hud, {1: "PlayerA", 2: "PlayerB"}, gametype_id=7) is True

    for seat, entry in hud.seat_players.items():
        assert entry["player_id"] in hud.stat_dict, seat
        assert hud.stat_dict[entry["player_id"]]["screen_name"] == entry["screen_name"]
