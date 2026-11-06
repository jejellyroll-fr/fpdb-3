"""Comprehensive unit and non-regression tests for Custom Auto Notes engine and UI integration."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from fpdb_3_legacy.AutoNoteRules import PreflopContext
from fpdb_3_legacy.AutoNotes import (
    available_rule_ids,
    available_rule_set_ids,
)
from fpdb_3_legacy.user_autonotes_parser import (
    build_evidence_dict,
    compile_custom_rule,
    evaluate_leaf_condition,
    extract_field_value,
    load_custom_rule_sets,
    load_user_autonotes_data,
    save_user_autonotes_data,
)


def _build_test_hand(
    player_name: str = "Hero",
    hole_cards: list[str] | None = None,
    board_cards: list[str] | None = None,
    game_base: str = "holdem",
    game_cat: str = "ring",
    game_limit: str = "nl",
    bb: float = 2.0,
    chips: float = 30.0,
    position: int | str = 0,
    actions_list: list[tuple[Any, ...]] | None = None,
    flop_actions: list[tuple[Any, ...]] | None = None,
):
    hand = MagicMock()
    hand.dbid_hands = 202
    hand.handid = "202"
    hand.bigBlind = bb
    hand.bb = bb
    hand.playerIds = {"Hero": 1, "Villain": 2, "Villain2": 3}
    hand.players = [[1, "Hero", str(chips)], [2, "Villain", "100.0"], [3, "Villain2", "100.0"]]
    hand.handsplayers = {
        "Hero": {"chips": chips, "position": position, "handText": "Pair of Aces"},
        "Villain": {"chips": 100.0, "position": "S", "handText": "High Card"},
        "Villain2": {"chips": 100.0, "position": "B", "handText": "Two Pair"},
    }
    hand.join_holecards.side_effect = (
        lambda p, asList=True: (hole_cards or ["Ah", "Kh"]) if p == "Hero" else ["Ts", "9s"]
    )
    hand.board = {"FLOP": board_cards[:3] if board_cards else ["Td", "7c", "2s"]}
    if board_cards and len(board_cards) >= 4:
        hand.board["TURN"] = [board_cards[3]]
    if board_cards and len(board_cards) >= 5:
        hand.board["RIVER"] = [board_cards[4]]

    hand.communityCards = board_cards or ["Td", "7c", "2s"]
    hand.pot = 10.0
    hand.gametype = {"base": game_base, "category": game_cat, "limitType": game_limit}
    hand.actionStreets = [0, "PREFLOP", "FLOP"]

    default_preflop = [
        ("Villain", "small blind", 1.0),
        ("Villain2", "big blind", 2.0),
        ("Hero", "raises", 6.0),
        ("Villain", "folds"),
        ("Villain2", "calls", 4.0),
    ]
    hand.actions = {
        "PREFLOP": actions_list if actions_list is not None else default_preflop,
        "FLOP": flop_actions or [("Villain2", "checks"), ("Hero", "bets", 8.0), ("Villain2", "folds")],
    }
    return hand


# ============================================================================
# 1. UNIT TESTS: Field Extractor & Leaf Condition Operators
# ============================================================================


def test_extract_field_value_game_context():
    hand = _build_test_hand(game_base="holdem", game_cat="ring", game_limit="nl")
    context = PreflopContext.from_hand(hand)

    assert extract_field_value("game.base", hand, "Hero", context) == "holdem"
    assert extract_field_value("game.category", hand, "Hero", context) == "ring"
    assert extract_field_value("game.limit", hand, "Hero", context) == "nl"


def test_extract_field_value_stack_and_positions():
    hand = _build_test_hand(position=0, chips=30.0, bb=2.0)
    context = PreflopContext.from_hand(hand)

    assert extract_field_value("player.position", hand, "Hero", context) == "BTN"
    assert extract_field_value("player.eff_stack_bb", hand, "Hero", context) == 15.0
    assert extract_field_value("spr.flop", hand, "Hero", context) == 3.0


def test_extract_field_value_actions_and_textures():
    hand = _build_test_hand(board_cards=["Ac", "Kc", "Qc"])
    context = PreflopContext.from_hand(hand)

    assert extract_field_value("action.preflop", hand, "Hero", context) == "open_raise"
    assert extract_field_value("action.flop", hand, "Hero", context) == "cbet"
    assert extract_field_value("board.flop_texture", hand, "Hero", context) == "monotone"


def test_evaluate_leaf_condition_operators():
    hand = _build_test_hand(chips=20.0, bb=2.0)  # 10.0 BB
    context = PreflopContext.from_hand(hand)

    # eq & neq
    assert evaluate_leaf_condition({"field": "game.base", "operator": "eq", "value": "holdem"}, hand, "Hero", context) is True
    assert evaluate_leaf_condition({"field": "game.base", "operator": "neq", "value": "omaha"}, hand, "Hero", context) is True

    # lte, gte, lt, gt
    assert evaluate_leaf_condition({"field": "player.eff_stack_bb", "operator": "lte", "value": 15.0}, hand, "Hero", context) is True
    assert evaluate_leaf_condition({"field": "player.eff_stack_bb", "operator": "gte", "value": 10.0}, hand, "Hero", context) is True
    assert evaluate_leaf_condition({"field": "player.eff_stack_bb", "operator": "lt", "value": 5.0}, hand, "Hero", context) is False
    assert evaluate_leaf_condition({"field": "player.eff_stack_bb", "operator": "gt", "value": 20.0}, hand, "Hero", context) is False

    # in & not_in
    assert evaluate_leaf_condition({"field": "player.position", "operator": "in", "value": ["BTN", "CO"]}, hand, "Hero", context) is True
    assert evaluate_leaf_condition({"field": "player.position", "operator": "not_in", "value": ["SB", "BB"]}, hand, "Hero", context) is True

    # between
    assert evaluate_leaf_condition({"field": "player.eff_stack_bb", "operator": "between", "value": [5.0, 15.0]}, hand, "Hero", context) is True
    assert evaluate_leaf_condition({"field": "player.eff_stack_bb", "operator": "between", "value": [20.0, 30.0]}, hand, "Hero", context) is False


# ============================================================================
# 2. UNIT TESTS: Template Safe Interpolation & Evidence Schema
# ============================================================================


def test_custom_rule_safe_dict_missing_keys():
    rule_dict = {
        "rule_id": "rule_missing_keys",
        "name": "Template Test",
        "note_template": "{player} open raised with {hole} (Unknown tag: {unknown_tag})",
        "enabled": True,
        "conditions": {"field": "game.base", "operator": "eq", "value": "holdem"},
        "evidence": {"capture_hole": True},
    }
    rule = compile_custom_rule(rule_dict)
    hand = _build_test_hand()
    context = PreflopContext.from_hand(hand)

    note = rule.evaluate(hand, "Hero", context)
    assert note is not None
    assert "{unknown_tag}" in note.note_text  # Gracefully preserved placeholder
    assert "Hero open raised with Ah Kh" in note.note_text


def test_evidence_builder_selective_flags():
    hand = _build_test_hand()
    context = PreflopContext.from_hand(hand)

    # Full evidence
    ev_full = build_evidence_dict(
        hand,
        "Hero",
        context,
        {
            "capture_hole": True,
            "capture_board": True,
            "capture_eff_stack": True,
            "capture_pot": True,
            "capture_spr": True,
            "capture_made_hand": True,
        },
    )
    assert "hole" in ev_full
    assert "flop" in ev_full
    assert "eff_stack_bb" in ev_full
    assert "pot" in ev_full
    assert "spr" in ev_full
    assert "made_hand" in ev_full

    # Minimal evidence
    ev_min = build_evidence_dict(hand, "Hero", context, {"capture_hole": False, "capture_board": False})
    assert "hole" not in ev_min
    assert "flop" not in ev_min


# ============================================================================
# 3. NON-REGRESSION TESTS: Custom Rules Engine Integration & Stability
# ============================================================================


def test_non_regression_corrupted_json_file_handled_gracefully(tmp_path: Path):
    corrupt_file = tmp_path / "user_autonotes.json"
    corrupt_file.write_text("{ malformed json ...")

    # Should not raise exception, but return empty data
    data = load_user_autonotes_data(corrupt_file)
    assert data == {"version": 1, "custom_rule_sets": []}

    rule_sets = load_custom_rule_sets(corrupt_file)
    assert rule_sets == ()


def test_non_regression_available_rule_sets_combines_builtins_and_customs(tmp_path: Path):
    custom_file = tmp_path / "user_autonotes.json"
    custom_data = {
        "version": 1,
        "custom_rule_sets": [
            {
                "rule_set_id": "custom_user_rules_test",
                "name": "Test Custom Rules",
                "enabled": True,
                "rules": [
                    {
                        "rule_id": "custom_rule_nr1",
                        "name": "Custom Non-Reg Rule",
                        "note_template": "{player} non reg",
                        "enabled": True,
                        "conditions": {"field": "game.base", "operator": "eq", "value": "holdem"},
                    }
                ],
            }
        ],
    }
    save_user_autonotes_data(custom_data, custom_file)

    rule_sets = load_custom_rule_sets(custom_file)
    assert len(rule_sets) == 1
    assert rule_sets[0].rule_set_id == "custom_user_rules_test"
    assert rule_sets[0].enabled_by_default is False


def test_non_regression_builtin_rulesets_unaffected():
    # Verify built-in registries are intact
    set_ids = available_rule_set_ids()
    assert "hwang_plo_preflop" in set_ids
    assert "holdem_cash_preflop" in set_ids
    assert "range_capture" in set_ids

    rule_ids = available_rule_ids()
    assert "hwang_plo_081" in rule_ids
    assert "holdem_cash_001" in rule_ids
    assert "range_capture_001" in rule_ids
