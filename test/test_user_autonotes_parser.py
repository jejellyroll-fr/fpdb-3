"""Unit tests for user_autonotes_parser declarative engine."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from fpdb_3_legacy.AutoNoteRules import LegacyAction, PreflopContext
from fpdb_3_legacy.user_autonotes_parser import (
    build_evidence_dict,
    compile_custom_rule,
    compile_custom_rule_set,
    evaluate_condition_tree,
    load_custom_rule_sets,
    load_user_autonotes_data,
    save_user_autonotes_data,
)


def _make_mock_hand(
    player_name="Hero",
    hole_cards=None,
    board_cards=None,
    bb=2.0,
    chips=30.0,
    actions_list=None,
):
    hand = MagicMock()
    hand.dbid_hands = 101
    hand.playerIds = {"Hero": 1, "Villain": 2}
    hand.players = [["1", "Hero"], ["2", "Villain"]]
    hand.bigBlind = bb
    hand.handsplayers = {
        "Hero": {"chips": chips, "position": 0, "handText": "Pair of Aces"},
        "Villain": {"chips": 100.0, "position": "S", "handText": "High Card"},
    }
    hand.join_holecards.side_effect = lambda p, asList=True: (hole_cards or ["Ah", "Kh"]) if p == "Hero" else ["Ts", "9s"]
    hand.communityCards = board_cards or ["Td", "7c", "2s"]
    hand.pot = 10.0
    hand.gametype = {"base": "holdem", "category": "ring", "limitType": "nl"}
    hand.actionStreets = [0, "PREFLOP", "FLOP"]
    hand.actions = {
        "PREFLOP": actions_list or [
            ("Villain", "small blind", 1.0),
            ("Hero", "big blind", 2.0),
            ("Villain", "raises", 6.0),
            ("Hero", "raises", 30.0, True),  # allin
        ]
    }
    return hand


def test_evaluate_condition_tree_and_leaf():
    hand = _make_mock_hand()
    context = PreflopContext.from_hand(hand)

    condition_tree = {
        "operator": "AND",
        "rules": [
            {"field": "game.base", "operator": "eq", "value": "holdem"},
            {"field": "player.position", "operator": "eq", "value": "BTN"},
            {"field": "player.eff_stack_bb", "operator": "lte", "value": 20.0},
        ],
    }

    assert evaluate_condition_tree(condition_tree, hand, "Hero", context) is True


def test_evaluate_condition_tree_or_not():
    hand = _make_mock_hand()
    context = PreflopContext.from_hand(hand)

    tree_or = {
        "operator": "OR",
        "rules": [
            {"field": "game.base", "operator": "eq", "value": "omaha"},
            {"field": "player.position", "operator": "eq", "value": "BTN"},
        ],
    }
    assert evaluate_condition_tree(tree_or, hand, "Hero", context) is True

    tree_not = {
        "operator": "NOT",
        "rules": [
            {"field": "game.base", "operator": "eq", "value": "omaha"},
        ],
    }
    assert evaluate_condition_tree(tree_not, hand, "Hero", context) is True


def test_build_evidence_dict():
    hand = _make_mock_hand()
    context = PreflopContext.from_hand(hand)

    evidence = build_evidence_dict(hand, "Hero", context)
    assert evidence["hole"] == ["Ah", "Kh"]
    assert evidence["flop"] == ["Td", "7c", "2s"]
    assert evidence["eff_stack_bb"] == 15.0


def test_compile_custom_rule_and_evaluate():
    rule_dict = {
        "rule_id": "custom_holdem_3bet_push",
        "version": 1,
        "name": "3-Bet Push Shortstack (<15bb)",
        "note_template": "{player} 3-Bet Shove Preflop {eff_stack_bb}BB with {hole}",
        "enabled": True,
        "conditions": {
            "operator": "AND",
            "rules": [
                {"field": "game.base", "operator": "eq", "value": "holdem"},
                {"field": "player.eff_stack_bb", "operator": "lte", "value": 15.0},
            ],
        },
        "evidence": {
            "capture_hole": True,
            "capture_board": True,
            "capture_eff_stack": True,
        },
    }

    rule = compile_custom_rule(rule_dict)
    hand = _make_mock_hand()
    context = PreflopContext.from_hand(hand)

    note = rule.evaluate(hand, "Hero", context)
    assert note is not None
    assert note.rule_id == "custom_holdem_3bet_push"
    assert "Hero 3-Bet Shove Preflop 15.0BB with Ah Kh" in note.note_text


def test_save_and_load_user_autonotes(tmp_path: Path):
    file_path = tmp_path / "user_autonotes.json"
    data = {
        "version": 1,
        "custom_rule_sets": [
            {
                "rule_set_id": "custom_user_rules",
                "name": "User Custom Rules",
                "enabled": True,
                "rules": [
                    {
                        "rule_id": "test_rule_1",
                        "name": "Test Rule 1",
                        "note_template": "{player} tested",
                        "enabled": True,
                        "conditions": {"field": "game.base", "operator": "eq", "value": "holdem"},
                    }
                ],
            }
        ],
    }

    save_user_autonotes_data(data, file_path)
    loaded_data = load_user_autonotes_data(file_path)
    assert loaded_data == data

    rule_sets = load_custom_rule_sets(file_path)
    assert len(rule_sets) == 1
    assert rule_sets[0].rule_set_id == "custom_user_rules"
    assert len(rule_sets[0].rules) == 1
    assert rule_sets[0].rules[0].rule_id == "test_rule_1"
