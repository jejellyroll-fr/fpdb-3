"""Unit tests for backfill_autonotes database loading and case-insensitive column handling."""

from __future__ import annotations

from fpdb_3_legacy.backfill_autonotes import DatabaseAutoNoteHand, _action_tuple, _dict_get


def test_dict_get_case_insensitive():
    row = {"playerId": 1234, "NAME": "HeroPlayer"}
    assert _dict_get(row, "playerId") == 1234
    assert _dict_get(row, "playerid") == 1234
    assert _dict_get(row, "PLAYERID") == 1234
    assert _dict_get(row, "name") == "HeroPlayer"
    assert _dict_get(row, "missing", "default") == "default"


def test_action_tuple_case_insensitive():
    action_row = {
        "playername": "MrSquiggle",
        "actionname": "folds",
        "allin": 0,
    }
    t = _action_tuple(action_row)
    assert t == ("MrSquiggle", "folds", False)


def test_database_autonote_hand_creation_with_actions():
    hand_row = {
        "id": 1001,
        "sitehandno": "998877",
        "siteid": 140,
        "tourneyid": None,
        "base": "holdem",
        "category": "holdem",
        "limittype": "nl",
        "type": "ring",
        "bigblind": 100,
        "smallblind": 50,
        "finalpot": 500,
    }
    player_rows = [
        {
            "playerid": 5579,
            "name": "MrSquiggle",
            "seatno": 1,
            "position": "BT",
            "startcash": 10000,
            "effstack": 10000,
            "card1": 1,
            "card2": 14,
        }
    ]
    action_rows = [
        {
            "street": 0,  # PREFLOP (0 in STREET_BY_ID)
            "playername": "MrSquiggle",
            "actionname": "folds",
            "allin": 0,
        }
    ]

    hand = DatabaseAutoNoteHand(hand_row, player_rows, action_rows)
    assert hand.dbid_hands == 1001
    assert hand.playerIds["MrSquiggle"] == 5579
    assert len(hand.actions["PREFLOP"]) == 1
    assert hand.actions["PREFLOP"][0] == ("MrSquiggle", "folds", False)
