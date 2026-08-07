"""Unit tests for FastFoldEngine and real-time Fast-Fold HUD updates."""

from __future__ import annotations

from unittest.mock import MagicMock

from fpdb_3_legacy.fast_fold_engine import FastFoldEngine, is_fast_fold_table


def test_is_fast_fold_table_detection() -> None:
    assert is_fast_fold_table("Winamax Go Fast Pool 1") is True
    assert is_fast_fold_table("Winamax HOLD-UP 0.05/0.10") is True
    assert is_fast_fold_table("PokerStars Zoom - Table 1") is True
    assert is_fast_fold_table("Rush Poker - NL50") is True
    assert is_fast_fold_table("Winamax Casablanca 02") is False
    assert is_fast_fold_table("Winamax Poker - Expresso 5€ - 12345") is False
    assert is_fast_fold_table(None, game_type="fast_fold") is True


def test_fast_fold_engine_stat_fetching() -> None:
    mock_db = MagicMock()
    mock_db.get_player_id_by_name.side_effect = lambda name: 101 if name == "PlayerA" else 102
    mock_db.get_player_stats_by_name.side_effect = lambda name, game_type="ring": (
        {"n": 150, "vpip": 24.5, "pfr": 18.0, "three_B": 8.5}
        if name == "PlayerA"
        else {"n": 50, "vpip": 40.0, "pfr": 10.0, "three_B": 2.0}
    )

    engine = FastFoldEngine(db_connection=mock_db)
    seat_map = {1: "PlayerA", 2: "PlayerB"}

    stat_dict = engine.get_player_stats_for_seat_map(seat_map, game_type="ring")

    assert 101 in stat_dict
    assert 102 in stat_dict
    assert stat_dict[101]["screen_name"] == "PlayerA"
    assert stat_dict[101]["vpip"] == 24.5
    assert stat_dict[101]["pfr"] == 18.0
    assert stat_dict[102]["screen_name"] == "PlayerB"
    assert stat_dict[102]["vpip"] == 40.0


def test_fast_fold_engine_hud_update() -> None:
    mock_hud = MagicMock()
    mock_db = MagicMock()
    mock_db.get_player_id_by_name.return_value = 55
    mock_db.get_player_stats_by_name.return_value = {"n": 80, "vpip": 22.0, "pfr": 16.0}

    engine = FastFoldEngine(db_connection=mock_db)
    success = engine.update_hud_seats(mock_hud, {1: "HeroOpponent"}, game_type="ring")

    assert success is True
    assert hasattr(mock_hud, "stat_dict")
    assert 55 in mock_hud.stat_dict
    assert mock_hud.stat_dict[55]["screen_name"] == "HeroOpponent"
    mock_hud.update_hud.assert_called_once()


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
