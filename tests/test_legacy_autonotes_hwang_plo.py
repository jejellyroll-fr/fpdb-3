from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from xml.dom import minidom

from fpdb_3_legacy.AutoNotePlo import (
    is_aaxx,
    is_rainbow,
    is_single_paired,
    is_single_paired_non_aaxx,
)
from fpdb_3_legacy.AutoNoteRules import PreflopContext
from fpdb_3_legacy.AutoNotes import (
    AutoNoteRule,
    GeneratedAutoNote,
    autonotes_enabled,
    available_rule_id_to_rule_set_id,
    available_rule_ids,
    available_rule_set_ids,
    available_rule_sets,
    configured_rule_summary,
    filter_generated_notes,
    format_generated_notes,
    format_note_evidence,
    format_rule_summary,
    generate_for_hand,
    max_auto_notes_per_hand,
    max_auto_notes_per_player_per_hand,
    rule_enabled,
    rule_manifest,
    rule_note_template,
    rule_set_enabled,
    set_autonotes_enabled,
    set_rule_enabled,
    set_rule_note_template,
    set_rule_set_enabled,
    summarize_generated_notes,
    summarize_generated_notes_by_rule_set,
)
from fpdb_3_legacy.backfill_autonotes import (
    _add_rule_counts,
    _lookup_hand_ids,
    _prepare_hand_for_autonotes,
    _preview_row,
    backfill_database_preview,
    format_rule_counts,
    format_rule_summary_json,
    format_stats_json,
    load_hand_from_database,
    parse_id_filter,
    parse_rule_set_filter,
    unknown_filter_ids,
)
from fpdb_3_legacy.backfill_autonotes import (
    main as backfill_main,
)
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.SQL import Sql


@dataclass
class LegacyHandStub:
    players: list[tuple[int, str]]
    cards: dict[str, list[str]]
    actions: dict[str, list[tuple]]
    positions: dict[str, object]
    handid: str = "site-hand-1"
    dbid_hands: int = 100
    actionStreets: list[str] = field(default_factory=lambda: ["BLINDSANTES", "PREFLOP", "FLOP"])
    gametype: dict[str, object] = field(
        default_factory=lambda: {
            "base": "hold",
            "category": "omahahi",
            "limitType": "pl",
        }
    )

    def __post_init__(self):
        self.playerIds = {player[1]: index + 1 for index, player in enumerate(self.players)}
        self.handsplayers = {player[1]: {"position": self.positions[player[1]]} for player in self.players}

    def join_holecards(self, player_name, asList=False):
        cards = self.cards[player_name]
        return cards if asList else " ".join(cards)

    def assembleHand(self):
        self.handsplayers = {player[1]: {"position": self.positions[player[1]]} for player in self.players}


def hand(players, cards, actions, positions, gametype=None):
    return LegacyHandStub(
        players=[(index + 1, name) for index, name in enumerate(players)],
        cards=cards,
        actions={"PREFLOP": actions},
        positions=positions,
        gametype=gametype
        or {
            "base": "hold",
            "category": "omahahi",
            "limitType": "pl",
        },
    )


def holdem_hand(players, cards, actions, positions):
    return hand(
        players,
        cards,
        actions,
        positions,
        gametype={
            "base": "hold",
            "category": "holdem",
            "limitType": "nl",
            "type": "ring",
        },
    )


def tournament_hand(players, cards, actions, positions, stacks, big_blind=100):
    legacy_hand = hand(
        players,
        cards,
        actions,
        positions,
        gametype={
            "base": "hold",
            "category": "holdem",
            "limitType": "nl",
            "type": "tour",
            "bigBlind": big_blind,
        },
    )
    legacy_hand.isSng = True
    legacy_hand.tourNo = "T100"
    for player, stack in stacks.items():
        legacy_hand.handsplayers[player]["startCash"] = stack
    return legacy_hand


def plo_postflop_hand(players, cards, postflop_actions, positions, spr_stats):
    legacy_hand = hand(players, cards, [], positions)
    legacy_hand.actionStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
    for street, actions in postflop_actions.items():
        legacy_hand.actions[street] = actions
    for player, stats in spr_stats.items():
        legacy_hand.handsplayers[player].update(stats)
    return legacy_hand


def flop_texture_hand(players, cards, preflop_actions, flop_actions, positions, board):
    legacy_hand = holdem_hand(players, cards, preflop_actions, positions)
    legacy_hand.actions["FLOP"] = flop_actions
    legacy_hand.board = {"FLOP": board}
    return legacy_hand


def showdown_quality_hand(players, cards, positions, player_stats, final_pot=2500, river_actions=None):
    legacy_hand = holdem_hand(players, cards, [], positions)
    legacy_hand.gametype["bigBlind"] = 100
    legacy_hand.actionStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
    legacy_hand.actions["RIVER"] = river_actions or []
    legacy_hand.hands = {"finalPot": final_pot}
    for player, stats in player_stats.items():
        legacy_hand.handsplayers[player].update(stats)
    return legacy_hand


def hero_relative_hand(players, cards, actions, positions, hero="Hero"):
    legacy_hand = holdem_hand(players, cards, actions, positions)
    legacy_hand.hero = hero
    return legacy_hand


def stud_hand(players, cards, actions, positions, category="razz"):
    return hand(
        players,
        cards,
        actions,
        positions,
        gametype={
            "base": "stud",
            "category": category,
            "limitType": "fl",
        },
    )


def draw_hand(players, cards, actions, positions, category="27_3draw"):
    return hand(
        players,
        cards,
        actions,
        positions,
        gametype={
            "base": "draw",
            "category": category,
            "limitType": "fl",
        },
    )


def note_ids(legacy_hand) -> set[str]:
    return {note.rule_id for note in generate_for_hand(legacy_hand)}


def config_from_xml(xml: str):
    return type("ConfigStub", (), {"doc": minidom.parseString(xml)})()


def test_plo_classifier_identifies_hwang_classes():
    assert is_aaxx(["As", "Ah", "Kd", "7c"])
    assert not is_aaxx(["As", "Kh", "Kd", "7c"])

    assert is_single_paired(["Ks", "Kh", "Qd", "7c"])
    assert is_single_paired_non_aaxx(["Ks", "Kh", "Qd", "7c"])
    assert not is_single_paired(["Ks", "Kh", "Qd", "Qc"])
    assert not is_single_paired(["Ks", "Kh", "Kd", "7c"])

    assert is_rainbow(["As", "Kh", "Qd", "7c"])
    assert not is_rainbow(["As", "Kh", "Qd", "7d"])


def test_081_generates_single_paired_non_aaxx_3bet_note():
    legacy_hand = hand(
        ["BTN", "SB", "BB"],
        {"BTN": ["As", "Kh", "Qd", "7c"], "SB": ["Ks", "Kh", "Qd", "7c"], "BB": ["As", "Ah", "Qd", "7c"]},
        [("BB", "big blind", 1), ("BTN", "raises", 3), ("SB", "raises", 10)],
        {"BTN": 0, "SB": "S", "BB": "B"},
    )

    assert "hwang_plo_081" in note_ids(legacy_hand)


def test_082_generates_rainbow_non_aaxx_vpip_note():
    legacy_hand = hand(
        ["BTN", "BB"],
        {"BTN": ["As", "Kh", "Qd", "7c"], "BB": ["As", "Ah", "Qd", "7c"]},
        [("BTN", "calls", 1)],
        {"BTN": 0, "BB": "B"},
    )

    assert "hwang_plo_082" in note_ids(legacy_hand)


def test_083_generates_3bet_oop_vs_late_steal_note():
    legacy_hand = hand(
        ["BTN", "SB", "BB"],
        {"BTN": ["As", "Kh", "Qd", "7c"], "SB": ["Ks", "Kh", "Qd", "7c"], "BB": ["As", "Ah", "Qd", "7c"]},
        [("BTN", "raises", 3), ("BB", "raises", 10)],
        {"BTN": 0, "SB": "S", "BB": "B"},
    )

    assert "hwang_plo_083" in note_ids(legacy_hand)


def test_084_generates_non_aaxx_4bet_note():
    legacy_hand = hand(
        ["BTN", "SB", "BB"],
        {"BTN": ["As", "Ah", "Qd", "7c"], "SB": ["Ks", "Kh", "Qd", "7c"], "BB": ["As", "Kh", "Qd", "7c"]},
        [("BTN", "raises", 3), ("SB", "raises", 10), ("BB", "raises", 25)],
        {"BTN": 0, "SB": "S", "BB": "B"},
    )

    assert "hwang_plo_084" in note_ids(legacy_hand)


def test_hwang_plo4_rules_do_not_run_on_5_card_plo():
    legacy_hand = hand(
        ["BTN", "SB", "BB"],
        {
            "BTN": ["As", "Ah", "Qd", "7c", "2s"],
            "SB": ["Ks", "5h", "Ts", "Ac", "9d"],
            "BB": ["As", "Kh", "Qd", "7c", "3s"],
        },
        [("BTN", "raises", 3), ("BB", "raises", 10), ("SB", "raises", 25)],
        {"BTN": 0, "SB": 2, "BB": "B"},
        gametype={
            "base": "hold",
            "category": "5_omahahi",
            "limitType": "pl",
        },
    )

    context = PreflopContext.from_hand(legacy_hand)

    assert context.hole_cards["SB"] == ["Ks", "5h", "Ts", "Ac", "9d"]
    assert generate_for_hand(legacy_hand, rule_set_ids={"hwang_plo_preflop"}) == []


def test_085_generates_aaxx_flat_note():
    legacy_hand = hand(
        ["BTN", "BB"],
        {"BTN": ["Ks", "Kh", "Qd", "7c"], "BB": ["As", "Ah", "Qd", "7c"]},
        [("BTN", "raises", 3), ("BB", "calls", 3)],
        {"BTN": 0, "BB": "B"},
    )

    assert "hwang_plo_085" in note_ids(legacy_hand)


def test_086_and_087_split_raise_fold_to_3bet_by_position():
    ip_hand = hand(
        ["BTN", "BB"],
        {"BTN": ["As", "Kh", "Qd", "7c"], "BB": ["Ks", "Kh", "Qd", "7c"]},
        [("BTN", "raises", 3), ("BB", "raises", 10), ("BTN", "folds")],
        {"BTN": 0, "BB": "B"},
    )
    ip_notes = note_ids(ip_hand)
    assert "hwang_plo_086" in ip_notes
    assert "hwang_plo_087" not in ip_notes

    oop_hand = hand(
        ["SB", "BTN", "BB"],
        {"SB": ["As", "Kh", "Qd", "7c"], "BTN": ["Ks", "Kh", "Qd", "7c"], "BB": ["As", "Ah", "Qd", "7c"]},
        [("SB", "raises", 3), ("BTN", "raises", 10), ("SB", "folds")],
        {"SB": "S", "BTN": 0, "BB": "B"},
    )
    oop_notes = note_ids(oop_hand)
    assert "hwang_plo_087" in oop_notes
    assert "hwang_plo_086" not in oop_notes


def test_autonotes_config_can_disable_all_rules():
    legacy_hand = hand(
        ["BTN", "SB"],
        {"BTN": ["As", "Kh", "Qd", "7c"], "SB": ["Ks", "Kh", "Qd", "7c"]},
        [("BTN", "raises", 3), ("SB", "raises", 10)],
        {"BTN": 0, "SB": "S"},
    )
    config = config_from_xml('<FreePokerToolsConfig><autonotes enabled="False"/></FreePokerToolsConfig>')

    assert not autonotes_enabled(config)
    assert generate_for_hand(legacy_hand, config=config) == []


def test_autonotes_config_can_disable_hwang_ruleset():
    legacy_hand = hand(
        ["BTN", "SB"],
        {"BTN": ["As", "Kh", "Qd", "7c"], "SB": ["Ks", "Kh", "Qd", "7c"]},
        [("BTN", "raises", 3), ("SB", "raises", 10)],
        {"BTN": 0, "SB": "S"},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="hwang_plo_preflop" enabled="False"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    assert not rule_set_enabled(config, "hwang_plo_preflop")
    assert generate_for_hand(legacy_hand, config=config) == []


def test_autonotes_config_can_disable_single_rule():
    legacy_hand = hand(
        ["BTN", "SB"],
        {"BTN": ["As", "Kh", "Qd", "7c"], "SB": ["Ks", "Kh", "Qd", "7c"]},
        [("BTN", "raises", 3), ("SB", "raises", 10)],
        {"BTN": 0, "SB": "S"},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="hwang_plo_preflop" enabled="True">'
        '<rule id="hwang_plo_081" enabled="False"/>'
        "</ruleset></autonotes></FreePokerToolsConfig>",
    )

    generated = {note.rule_id for note in generate_for_hand(legacy_hand, config=config)}
    assert not rule_enabled(config, "hwang_plo_081")
    assert "hwang_plo_081" not in generated
    assert "hwang_plo_082" in generated


def test_autonotes_config_setters_create_missing_xml_nodes():
    config = config_from_xml("<FreePokerToolsConfig/>")

    set_autonotes_enabled(config, False)
    set_rule_set_enabled(config, "holdem_cash_preflop", True)
    set_rule_enabled(config, "holdem_cash_001", False, rule_set_name="holdem_cash_preflop")

    autonotes = config.doc.getElementsByTagName("autonotes")
    rulesets = config.doc.getElementsByTagName("ruleset")
    rules = config.doc.getElementsByTagName("rule")

    assert len(autonotes) == 1
    assert autonotes[0].getAttribute("enabled") == "False"
    assert len(rulesets) == 1
    assert rulesets[0].getAttribute("name") == "holdem_cash_preflop"
    assert rulesets[0].getAttribute("enabled") == "True"
    assert len(rules) == 1
    assert rules[0].getAttribute("id") == "holdem_cash_001"
    assert rules[0].getAttribute("enabled") == "False"
    assert not autonotes_enabled(config)
    assert rule_set_enabled(config, "holdem_cash_preflop", default=False)
    assert not rule_enabled(config, "holdem_cash_001", "holdem_cash_preflop")


def test_autonotes_config_setters_update_existing_nodes_without_duplicates():
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="False">'
        '<ruleset name="hwang_plo_preflop" enabled="False">'
        '<rule id="hwang_plo_081" enabled="False"/>'
        "</ruleset></autonotes></FreePokerToolsConfig>",
    )

    set_autonotes_enabled(config, True)
    set_rule_set_enabled(config, "hwang_plo_preflop", True)
    set_rule_enabled(config, "hwang_plo_081", True, rule_set_name="hwang_plo_preflop")

    assert len(config.doc.getElementsByTagName("autonotes")) == 1
    assert len(config.doc.getElementsByTagName("ruleset")) == 1
    assert len(config.doc.getElementsByTagName("rule")) == 1
    assert autonotes_enabled(config)
    assert rule_set_enabled(config, "hwang_plo_preflop")
    assert rule_enabled(config, "hwang_plo_081", "hwang_plo_preflop")


def test_configured_rule_summary_reflects_ui_setter_changes():
    config = config_from_xml("<FreePokerToolsConfig/>")

    set_rule_set_enabled(config, "range_capture", True)
    set_rule_enabled(config, "range_capture_001", False, rule_set_name="range_capture")

    summary = configured_rule_summary(config, rule_set_ids={"range_capture"})

    assert summary[0]["enabled"]
    assert {rule["id"]: rule["enabled"] for rule in summary[0]["rules"]}["range_capture_001"] is False


def test_autonotes_config_can_override_rule_note_template():
    legacy_hand = hand(
        ["BTN", "SB"],
        {"BTN": ["As", "Kh", "Qd", "7c"], "SB": ["Ks", "Kh", "Qd", "7c"]},
        [("BTN", "raises", 3), ("SB", "raises", 10)],
        {"BTN": 0, "SB": "S"},
    )
    config = config_from_xml("<FreePokerToolsConfig/>")

    set_rule_note_template(
        config,
        "hwang_plo_081",
        "{player}: custom template",
        rule_set_name="hwang_plo_preflop",
    )

    notes = generate_for_hand(legacy_hand, config=config, rule_ids={"hwang_plo_081"})

    assert rule_note_template(config, "hwang_plo_081", "hwang_plo_preflop") == "{player}: custom template"
    assert notes[0].note_text == "SB: custom template"


def test_generate_for_hand_can_filter_rule_sets():
    legacy_hand = hand(
        ["BTN", "SB"],
        {"BTN": ["As", "Kh", "Qd", "7c"], "SB": ["Ks", "Kh", "Qd", "7c"]},
        [("BTN", "raises", 3), ("SB", "raises", 10)],
        {"BTN": 0, "SB": "S"},
    )

    assert generate_for_hand(legacy_hand, rule_set_ids={"holdem_cash_preflop"}) == []
    generated = {note.rule_id for note in generate_for_hand(legacy_hand, rule_set_ids={"hwang_plo_preflop"})}
    assert generated >= {"hwang_plo_081", "hwang_plo_082"}


def test_generate_for_hand_can_filter_rule_ids():
    legacy_hand = hand(
        ["BTN", "SB"],
        {"BTN": ["As", "Kh", "Qd", "7c"], "SB": ["Ks", "Kh", "Qd", "7c"]},
        [("BTN", "raises", 3), ("SB", "raises", 10)],
        {"BTN": 0, "SB": "S"},
    )

    generated = {note.rule_id for note in generate_for_hand(legacy_hand, rule_ids={"hwang_plo_081"})}

    assert generated == {"hwang_plo_081"}
    assert generate_for_hand(legacy_hand, rule_ids={"holdem_cash_001"}) == []


def test_generate_for_hand_filter_can_select_opt_in_rule_set():
    legacy_hand = holdem_hand(
        ["CO", "BTN", "SB", "BB"],
        {"CO": ["As", "Kh"], "BTN": ["Qd", "Jc"], "SB": ["9s", "9d"], "BB": ["2c", "2d"]},
        [("CO", "calls", 1), ("BTN", "raises", 5), ("CO", "calls", 5)],
        {"CO": 1, "BTN": 0, "SB": "S", "BB": "B"},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="holdem_cash_preflop" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    assert generate_for_hand(legacy_hand, config=config, rule_set_ids={"hwang_plo_preflop"}) == []
    generated = {
        note.rule_id
        for note in generate_for_hand(legacy_hand, config=config, rule_set_ids={"holdem_cash_preflop"})
    }
    assert generated == {"holdem_cash_001", "holdem_cash_002"}


def test_autonotes_config_can_limit_notes_per_hand():
    legacy_hand = hand(
        ["BTN", "SB"],
        {"BTN": ["As", "Kh", "Qd", "7c"], "SB": ["Ks", "Kh", "Qd", "7c"]},
        [("BTN", "raises", 3), ("SB", "raises", 10)],
        {"BTN": 0, "SB": "S"},
    )
    config = config_from_xml('<FreePokerToolsConfig><autonotes enabled="True" maxPerHand="1"/></FreePokerToolsConfig>')

    notes = generate_for_hand(legacy_hand, config=config)

    assert max_auto_notes_per_hand(config) == 1
    assert len(notes) == 1
    assert notes[0].rule_id == "hwang_plo_082"


def test_autonotes_config_zero_max_per_hand_suppresses_notes():
    legacy_hand = hand(
        ["BTN", "SB"],
        {"BTN": ["As", "Kh", "Qd", "7c"], "SB": ["Ks", "Kh", "Qd", "7c"]},
        [("BTN", "raises", 3), ("SB", "raises", 10)],
        {"BTN": 0, "SB": "S"},
    )
    config = config_from_xml('<FreePokerToolsConfig><autonotes enabled="True" maxPerHand="0"/></FreePokerToolsConfig>')

    assert max_auto_notes_per_hand(config) == 0
    assert generate_for_hand(legacy_hand, config=config) == []


def test_autonotes_config_invalid_max_per_hand_is_ignored():
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True" maxPerHand="many"/></FreePokerToolsConfig>',
    )

    assert max_auto_notes_per_hand(config) is None


def test_autonotes_config_can_limit_notes_per_player_per_hand():
    legacy_hand = hand(
        ["BTN", "SB"],
        {"BTN": ["As", "Kh", "Qd", "7c"], "SB": ["Ks", "Kh", "Qd", "7c"]},
        [("BTN", "raises", 3), ("SB", "raises", 10)],
        {"BTN": 0, "SB": "S"},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True" maxPerPlayerPerHand="1"/></FreePokerToolsConfig>',
    )

    notes = generate_for_hand(legacy_hand, config=config)

    assert max_auto_notes_per_player_per_hand(config) == 1
    assert [note.rule_id for note in notes] == ["hwang_plo_082", "hwang_plo_081"]
    assert [note.player_id for note in notes] == [1, 2]


def test_autonotes_config_zero_max_per_player_per_hand_suppresses_notes():
    legacy_hand = hand(
        ["BTN", "SB"],
        {"BTN": ["As", "Kh", "Qd", "7c"], "SB": ["Ks", "Kh", "Qd", "7c"]},
        [("BTN", "raises", 3), ("SB", "raises", 10)],
        {"BTN": 0, "SB": "S"},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True" maxPerPlayerPerHand="0"/></FreePokerToolsConfig>',
    )

    assert max_auto_notes_per_player_per_hand(config) == 0
    assert generate_for_hand(legacy_hand, config=config) == []


def test_available_rule_sets_exposes_hwang_registry():
    rule_sets = {rule_set.rule_set_id: rule_set for rule_set in available_rule_sets()}

    assert "hwang_plo_preflop" in rule_sets
    assert {rule.rule_id for rule in rule_sets["hwang_plo_preflop"].rules} >= {"hwang_plo_081", "hwang_plo_087"}
    assert "holdem_cash_preflop" in rule_sets
    assert not rule_sets["holdem_cash_preflop"].enabled_by_default
    assert "plo_spr_postflop" in rule_sets
    assert not rule_sets["plo_spr_postflop"].enabled_by_default
    assert "flop_texture" in rule_sets
    assert not rule_sets["flop_texture"].enabled_by_default
    assert "showdown_quality" in rule_sets
    assert not rule_sets["showdown_quality"].enabled_by_default
    assert "hero_relative" in rule_sets
    assert not rule_sets["hero_relative"].enabled_by_default
    assert "range_capture" in rule_sets
    assert not rule_sets["range_capture"].enabled_by_default
    assert "stud_draw_first_street" in rule_sets
    assert not rule_sets["stud_draw_first_street"].enabled_by_default
    assert available_rule_set_ids() >= {
        "hwang_plo_preflop",
        "holdem_cash_preflop",
        "plo_spr_postflop",
        "flop_texture",
        "showdown_quality",
        "hero_relative",
        "range_capture",
        "stud_draw_first_street",
    }
    assert available_rule_ids() >= {
        "hwang_plo_081",
        "hwang_plo_087",
        "holdem_cash_001",
        "plo_spr_001",
        "flop_texture_001",
        "showdown_quality_001",
        "hero_relative_001",
        "range_capture_001",
        "stud_draw_001",
    }
    assert available_rule_id_to_rule_set_id()["hwang_plo_081"] == "hwang_plo_preflop"
    assert available_rule_id_to_rule_set_id()["holdem_cash_001"] == "holdem_cash_preflop"
    assert available_rule_id_to_rule_set_id()["tourney_pf_001"] == "tournament_push_fold"
    assert available_rule_id_to_rule_set_id()["plo_spr_001"] == "plo_spr_postflop"
    assert available_rule_id_to_rule_set_id()["flop_texture_001"] == "flop_texture"
    assert available_rule_id_to_rule_set_id()["showdown_quality_001"] == "showdown_quality"
    assert available_rule_id_to_rule_set_id()["hero_relative_001"] == "hero_relative"
    assert available_rule_id_to_rule_set_id()["range_capture_001"] == "range_capture"
    assert available_rule_id_to_rule_set_id()["stud_draw_001"] == "stud_draw_first_street"


def test_configured_rule_summary_reflects_defaults_and_rule_config():
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="hwang_plo_preflop" enabled="True">'
        '<rule id="hwang_plo_081" enabled="False"/>'
        "</ruleset></autonotes></FreePokerToolsConfig>",
    )

    summary = {rule_set["ruleSet"]: rule_set for rule_set in configured_rule_summary(config)}
    hwang_rules = {rule["id"]: rule for rule in summary["hwang_plo_preflop"]["rules"]}

    assert summary["hwang_plo_preflop"]["enabled"]
    assert summary["hwang_plo_preflop"]["enabledByDefault"]
    assert not hwang_rules["hwang_plo_081"]["enabled"]
    assert hwang_rules["hwang_plo_082"]["enabled"]
    assert not summary["holdem_cash_preflop"]["enabled"]
    assert not summary["holdem_cash_preflop"]["rules"][0]["enabled"]


def test_configured_rule_summary_can_be_filtered():
    summary = configured_rule_summary(rule_set_ids={"hwang_plo_preflop"}, rule_ids={"hwang_plo_081"})

    assert [rule_set["ruleSet"] for rule_set in summary] == ["hwang_plo_preflop"]
    assert [rule["id"] for rule in summary[0]["rules"]] == ["hwang_plo_081"]
    assert configured_rule_summary(rule_set_ids={"holdem_cash_preflop"}, rule_ids={"hwang_plo_081"}) == []


def test_format_rule_summary_for_cli():
    text = format_rule_summary(
        [
            {
                "ruleSet": "demo",
                "enabled": True,
                "enabledByDefault": False,
                "rules": [
                    {"id": "demo_001", "name": "Demo rule", "version": 2, "enabled": True},
                    {"id": "demo_002", "name": "Disabled rule", "version": 1, "enabled": False},
                ],
            },
        ],
    )

    assert text == (
        "demo [enabled, default off]\n"
        "  - demo_001 v2 [on] Demo rule\n"
        "  - demo_002 v1 [off] Disabled rule"
    )


def test_format_rule_summary_json_for_automation():
    text = format_rule_summary_json(
        [
            {
                "ruleSet": "demo",
                "enabled": True,
                "enabledByDefault": False,
                "rules": [{"id": "demo_001", "name": "Demo rule", "version": 2, "enabled": True}],
            },
        ],
    )

    assert json.loads(text) == {
        "rule_sets": [
            {
                "ruleSet": "demo",
                "enabled": True,
                "enabledByDefault": False,
                "rules": [{"id": "demo_001", "name": "Demo rule", "version": 2, "enabled": True}],
            },
        ],
    }


def test_holdem_cash_rules_are_disabled_by_default():
    legacy_hand = holdem_hand(
        ["CO", "BTN", "SB", "BB"],
        {"CO": ["As", "Kh"], "BTN": ["Qd", "Jc"], "SB": ["9s", "9d"], "BB": ["2c", "2d"]},
        [("CO", "calls", 1)],
        {"CO": 1, "BTN": 0, "SB": "S", "BB": "B"},
    )

    assert note_ids(legacy_hand) == set()


def test_holdem_cash_rules_generate_when_ruleset_is_enabled():
    legacy_hand = holdem_hand(
        ["CO", "BTN", "SB", "BB"],
        {"CO": ["As", "Kh"], "BTN": ["Qd", "Jc"], "SB": ["9s", "9d"], "BB": ["2c", "2d"]},
        [("CO", "calls", 1), ("BTN", "raises", 5), ("CO", "calls", 5)],
        {"CO": 1, "BTN": 0, "SB": "S", "BB": "B"},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="holdem_cash_preflop" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    generated = {note.rule_id for note in generate_for_hand(legacy_hand, config=config)}

    assert generated == {"holdem_cash_001", "holdem_cash_002"}


def test_holdem_cash_rules_honor_single_rule_disable():
    legacy_hand = holdem_hand(
        ["CO", "BTN", "SB", "BB"],
        {"CO": ["As", "Kh"], "BTN": ["Qd", "Jc"], "SB": ["9s", "9d"], "BB": ["2c", "2d"]},
        [("CO", "calls", 1), ("BTN", "raises", 5), ("CO", "calls", 5)],
        {"CO": 1, "BTN": 0, "SB": "S", "BB": "B"},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="holdem_cash_preflop" enabled="True">'
        '<rule id="holdem_cash_001" enabled="False"/>'
        "</ruleset></autonotes></FreePokerToolsConfig>",
    )

    generated = {note.rule_id for note in generate_for_hand(legacy_hand, config=config)}

    assert generated == {"holdem_cash_002"}


def test_holdem_cash_3bet_blind_vs_late_steal_rule():
    legacy_hand = holdem_hand(
        ["BTN", "SB", "BB"],
        {"BTN": ["As", "Kh"], "SB": ["Qd", "Jc"], "BB": ["9s", "9d"]},
        [("BTN", "raises", 3), ("BB", "raises", 10)],
        {"BTN": 0, "SB": "S", "BB": "B"},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="holdem_cash_preflop" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    generated = {note.rule_id for note in generate_for_hand(legacy_hand, config=config)}

    assert generated == {"holdem_cash_003"}


def test_tournament_push_fold_rules_are_disabled_by_default():
    legacy_hand = tournament_hand(
        ["BTN", "SB", "BB"],
        {"BTN": ["As", "Kh"], "SB": ["Qd", "Jc"], "BB": ["9s", "9d"]},
        [("BTN", "raises", 1200, 1200, 0, True)],
        {"BTN": 0, "SB": "S", "BB": "B"},
        {"BTN": 1200, "SB": 3000, "BB": 3000},
    )

    assert note_ids(legacy_hand) == set()


def test_tournament_push_fold_generates_open_shove_note_when_enabled():
    legacy_hand = tournament_hand(
        ["BTN", "SB", "BB"],
        {"BTN": ["As", "Kh"], "SB": ["Qd", "Jc"], "BB": ["9s", "9d"]},
        [("BTN", "raises", 1200, 1200, 0, True)],
        {"BTN": 0, "SB": "S", "BB": "B"},
        {"BTN": 1200, "SB": 3000, "BB": 3000},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="tournament_push_fold" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    notes = generate_for_hand(legacy_hand, config=config)

    assert [note.rule_id for note in notes] == ["tourney_pf_001"]
    assert notes[0].evidence["stack_bb"] == 12.0


def test_tournament_push_fold_generates_3bet_shove_vs_steal_note():
    legacy_hand = tournament_hand(
        ["BTN", "SB", "BB"],
        {"BTN": ["As", "Kh"], "SB": ["Qd", "Jc"], "BB": ["9s", "9d"]},
        [("BTN", "raises", 250, 250, 0, False), ("BB", "raises", 1800, 2000, 250, True)],
        {"BTN": 0, "SB": "S", "BB": "B"},
        {"BTN": 4000, "SB": 3000, "BB": 1800},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="tournament_push_fold" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    generated = {note.rule_id for note in generate_for_hand(legacy_hand, config=config)}

    assert generated == {"tourney_pf_002"}


def test_tournament_push_fold_generates_short_stack_raise_fold_note():
    legacy_hand = tournament_hand(
        ["CO", "BTN", "SB", "BB"],
        {"CO": ["As", "Kh"], "BTN": ["Qd", "Jc"], "SB": ["9s", "9d"], "BB": ["2c", "2d"]},
        [("CO", "raises", 250, 250, 0, False), ("BTN", "raises", 750, 1000, 250, False), ("CO", "folds")],
        {"CO": 1, "BTN": 0, "SB": "S", "BB": "B"},
        {"CO": 1400, "BTN": 5000, "SB": 3000, "BB": 3000},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="tournament_push_fold" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    generated = {note.rule_id for note in generate_for_hand(legacy_hand, config=config)}

    assert generated == {"tourney_pf_003"}


def test_plo_spr_postflop_rules_are_disabled_by_default():
    legacy_hand = plo_postflop_hand(
        ["BTN", "BB"],
        {"BTN": ["As", "Kh", "Qd", "7c"], "BB": ["Ks", "Kh", "Qd", "7c"]},
        {"FLOP": [("BTN", "folds")]},
        {"BTN": 0, "BB": "B"},
        {"BTN": {"cnt_f_spr": 1, "val_f_spr": 80}},
    )

    assert note_ids(legacy_hand) == set()


def test_plo_spr_postflop_generates_fold_note_when_enabled():
    legacy_hand = plo_postflop_hand(
        ["BTN", "BB"],
        {"BTN": ["As", "Kh", "Qd", "7c"], "BB": ["Ks", "Kh", "Qd", "7c"]},
        {"FLOP": [("BTN", "folds")]},
        {"BTN": 0, "BB": "B"},
        {"BTN": {"cnt_f_spr": 1, "val_f_spr": 80}},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="plo_spr_postflop" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    notes = generate_for_hand(legacy_hand, config=config)

    assert [note.rule_id for note in notes] == ["plo_spr_001"]
    assert notes[0].evidence["street"] == "FLOP"
    assert notes[0].evidence["spr"] == 0.8
    assert notes[0].evidence["action"] == "folds"


def test_plo_spr_postflop_generates_aggressive_allin_note():
    legacy_hand = plo_postflop_hand(
        ["BTN", "BB"],
        {"BTN": ["As", "Kh", "Qd", "7c"], "BB": ["Ks", "Kh", "Qd", "7c"]},
        {"TURN": [("BTN", "raises", 800, 1200, 400, True)]},
        {"BTN": 0, "BB": "B"},
        {"BTN": {"cnt_t_spr": 1, "val_t_spr": 100}},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="plo_spr_postflop" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    notes = generate_for_hand(legacy_hand, config=config)

    assert [note.rule_id for note in notes] == ["plo_spr_002"]
    assert notes[0].evidence["street"] == "TURN"
    assert notes[0].evidence["all_in"]


def test_plo_spr_postflop_generates_call_allin_note():
    legacy_hand = plo_postflop_hand(
        ["BTN", "BB"],
        {"BTN": ["As", "Kh", "Qd", "7c"], "BB": ["Ks", "Kh", "Qd", "7c"]},
        {"RIVER": [("BTN", "calls", 800, True)]},
        {"BTN": 0, "BB": "B"},
        {"BTN": {"cnt_r_spr": 1, "val_r_spr": 25}},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="plo_spr_postflop" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    notes = generate_for_hand(legacy_hand, config=config)

    assert [note.rule_id for note in notes] == ["plo_spr_003"]
    assert notes[0].evidence["street"] == "RIVER"
    assert notes[0].evidence["spr"] == 0.25
    assert notes[0].evidence["all_in"]


def test_plo_spr_postflop_ignores_high_spr_actions():
    legacy_hand = plo_postflop_hand(
        ["BTN", "BB"],
        {"BTN": ["As", "Kh", "Qd", "7c"], "BB": ["Ks", "Kh", "Qd", "7c"]},
        {"FLOP": [("BTN", "bets", 800, True)]},
        {"BTN": 0, "BB": "B"},
        {"BTN": {"cnt_f_spr": 1, "val_f_spr": 150}},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="plo_spr_postflop" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    assert generate_for_hand(legacy_hand, config=config) == []


def test_flop_texture_rules_are_disabled_by_default():
    legacy_hand = flop_texture_hand(
        ["BTN", "BB"],
        {"BTN": ["As", "Kh"], "BB": ["Qd", "Jc"]},
        [("BTN", "raises", 3)],
        [("BB", "bets", 5)],
        {"BTN": 0, "BB": "B"},
        ["As", "9s", "2d"],
    )

    assert note_ids(legacy_hand) == set()


def test_flop_texture_generates_wet_donk_note_when_enabled():
    legacy_hand = flop_texture_hand(
        ["BTN", "BB"],
        {"BTN": ["As", "Kh"], "BB": ["Qd", "Jc"]},
        [("BTN", "raises", 3)],
        [("BB", "bets", 5)],
        {"BTN": 0, "BB": "B"},
        ["As", "9s", "2d"],
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="flop_texture" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    notes = generate_for_hand(legacy_hand, config=config)

    assert [note.rule_id for note in notes] == ["flop_texture_001"]
    assert notes[0].evidence["board"] == "As 9s 2d"
    assert notes[0].evidence["texture"] == "two-tone"
    assert notes[0].evidence["preflop_aggressor"] == "BTN"


def test_flop_texture_generates_raise_cbet_note_on_wet_board():
    legacy_hand = flop_texture_hand(
        ["CO", "BTN"],
        {"CO": ["As", "Kh"], "BTN": ["Qd", "Jc"]},
        [("CO", "raises", 3)],
        [("CO", "bets", 5), ("BTN", "raises", 16)],
        {"CO": 1, "BTN": 0},
        ["9s", "8s", "7d"],
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="flop_texture" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    notes = generate_for_hand(legacy_hand, config=config)

    assert [note.rule_id for note in notes] == ["flop_texture_002"]
    assert notes[0].evidence["texture"] == "two-tone, connected"
    assert notes[0].evidence["action"] == "raises"


def test_flop_texture_generates_call_cbet_note_on_paired_board():
    legacy_hand = flop_texture_hand(
        ["CO", "BTN"],
        {"CO": ["As", "Kh"], "BTN": ["Qd", "Jc"]},
        [("CO", "raises", 3)],
        [("CO", "bets", 5), ("BTN", "calls", 5)],
        {"CO": 1, "BTN": 0},
        ["Kc", "Kd", "2s"],
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="flop_texture" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    notes = generate_for_hand(legacy_hand, config=config)

    assert [note.rule_id for note in notes] == ["flop_texture_003"]
    assert notes[0].evidence["texture"] == "paired"
    assert notes[0].evidence["action"] == "calls"


def test_flop_texture_ignores_dry_board_donk():
    legacy_hand = flop_texture_hand(
        ["BTN", "BB"],
        {"BTN": ["As", "Kh"], "BB": ["Qd", "Jc"]},
        [("BTN", "raises", 3)],
        [("BB", "bets", 5)],
        {"BTN": 0, "BB": "B"},
        ["Kc", "7d", "2s"],
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="flop_texture" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    assert generate_for_hand(legacy_hand, config=config) == []


def test_showdown_quality_rules_are_disabled_by_default():
    legacy_hand = showdown_quality_hand(
        ["BTN", "BB"],
        {"BTN": ["As", "Kh"], "BB": ["Qd", "Jc"]},
        {"BTN": 0, "BB": "B"},
        {"BB": {"sawShowdown": True, "wonAtSD": False, "showdownWinnings": -2500, "handString": "one pair, Queens"}},
    )

    assert note_ids(legacy_hand) == set()


def test_showdown_quality_generates_weak_lost_showdown_note_when_enabled():
    legacy_hand = showdown_quality_hand(
        ["BTN", "BB"],
        {"BTN": ["As", "Kh"], "BB": ["Qd", "Jc"]},
        {"BTN": 0, "BB": "B"},
        {"BB": {"sawShowdown": True, "wonAtSD": False, "showdownWinnings": -2500, "handString": "one pair, Queens"}},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="showdown_quality" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    notes = generate_for_hand(legacy_hand, config=config)

    assert [note.rule_id for note in notes] == ["showdown_quality_001"]
    assert notes[0].evidence["hand_class"] == "one pair, Queens"
    assert notes[0].evidence["final_pot_bb"] == 25.0
    assert notes[0].evidence["won_at_showdown"] is False


def test_showdown_quality_generates_river_call_weak_lost_note():
    legacy_hand = showdown_quality_hand(
        ["BTN", "BB"],
        {"BTN": ["As", "Kh"], "BB": ["Qd", "Jc"]},
        {"BTN": 0, "BB": "B"},
        {"BB": {"sawShowdown": True, "wonAtSD": False, "showdownWinnings": -3000, "handString": "high card Queen"}},
        final_pot=3000,
        river_actions=[("BTN", "bets", 1000), ("BB", "calls", 1000)],
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="showdown_quality" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    notes = generate_for_hand(legacy_hand, config=config)

    assert [note.rule_id for note in notes] == ["showdown_quality_001", "showdown_quality_002"]
    assert notes[1].evidence["street"] == "RIVER"
    assert notes[1].evidence["action"] == "calls"


def test_showdown_quality_generates_non_nut_flush_note():
    legacy_hand = showdown_quality_hand(
        ["BTN", "BB"],
        {"BTN": ["As", "Kh"], "BB": ["Qd", "Jd"]},
        {"BTN": 0, "BB": "B"},
        {"BB": {"sawShowdown": True, "wonAtSD": True, "showdownWinnings": 3000, "handString": "a flush, Queen high"}},
        final_pot=3000,
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="showdown_quality" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    notes = generate_for_hand(legacy_hand, config=config)

    assert [note.rule_id for note in notes] == ["showdown_quality_003"]
    assert notes[0].evidence["hand_class"] == "a flush, Queen high"


def test_showdown_quality_ignores_small_pots_and_nut_flush_strings():
    weak_small_pot = showdown_quality_hand(
        ["BTN", "BB"],
        {"BTN": ["As", "Kh"], "BB": ["Qd", "Jc"]},
        {"BTN": 0, "BB": "B"},
        {"BB": {"sawShowdown": True, "wonAtSD": False, "showdownWinnings": -1500, "handString": "one pair, Queens"}},
        final_pot=1500,
    )
    ace_high_flush = showdown_quality_hand(
        ["BTN", "BB"],
        {"BTN": ["As", "Kh"], "BB": ["Qd", "Jd"]},
        {"BTN": 0, "BB": "B"},
        {"BB": {"sawShowdown": True, "wonAtSD": True, "showdownWinnings": 3000, "handString": "a flush, Ace high"}},
        final_pot=3000,
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="showdown_quality" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    assert generate_for_hand(weak_small_pot, config=config) == []
    assert generate_for_hand(ace_high_flush, config=config) == []


def test_hero_relative_rules_are_disabled_by_default():
    legacy_hand = hero_relative_hand(
        ["Hero", "Villain"],
        {"Hero": ["As", "Kh"], "Villain": ["Qd", "Jc"]},
        [("Hero", "raises", 3), ("Villain", "raises", 10)],
        {"Hero": 0, "Villain": "B"},
    )

    assert note_ids(legacy_hand) == set()


def test_hero_relative_generates_villain_3bets_hero_note():
    legacy_hand = hero_relative_hand(
        ["Hero", "Villain"],
        {"Hero": ["As", "Kh"], "Villain": ["Qd", "Jc"]},
        [("Hero", "raises", 3), ("Villain", "raises", 10)],
        {"Hero": 0, "Villain": "B"},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="hero_relative" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    notes = generate_for_hand(legacy_hand, config=config)

    assert [note.rule_id for note in notes] == ["hero_relative_001"]
    assert notes[0].player_id == 2
    assert notes[0].evidence["hero"] == "Hero"
    assert notes[0].evidence["villain"] == "Villain"
    assert notes[0].evidence["villain_action"] == "3bets"


def test_hero_relative_generates_villain_4bets_hero_note():
    legacy_hand = hero_relative_hand(
        ["CO", "Hero", "Villain"],
        {"CO": ["2s", "2d"], "Hero": ["As", "Kh"], "Villain": ["Qd", "Jc"]},
        [("CO", "raises", 3), ("Hero", "raises", 10), ("Villain", "raises", 24)],
        {"CO": 1, "Hero": 0, "Villain": "B"},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="hero_relative" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    notes = generate_for_hand(legacy_hand, config=config)

    assert [note.rule_id for note in notes] == ["hero_relative_002"]
    assert notes[0].player_id == 3
    assert notes[0].evidence["hero_action"] == "3bets"
    assert notes[0].evidence["villain_action"] == "4bets"


def test_hero_relative_generates_villain_folds_to_hero_3bet_note():
    legacy_hand = hero_relative_hand(
        ["Hero", "Villain"],
        {"Hero": ["As", "Kh"], "Villain": ["Qd", "Jc"]},
        [("Villain", "raises", 3), ("Hero", "raises", 10), ("Villain", "folds")],
        {"Hero": 0, "Villain": 1},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="hero_relative" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    notes = generate_for_hand(legacy_hand, config=config)

    assert [note.rule_id for note in notes] == ["hero_relative_003"]
    assert notes[0].player_id == 2
    assert notes[0].evidence["hero_action"] == "3bets"
    assert notes[0].evidence["villain_action"] == "folds"


def test_hero_relative_generates_villain_folds_to_hero_4bet_note():
    legacy_hand = hero_relative_hand(
        ["Hero", "Villain"],
        {"Hero": ["As", "Kh"], "Villain": ["Qd", "Jc"]},
        [("Hero", "raises", 3), ("Villain", "raises", 10), ("Hero", "raises", 25), ("Villain", "folds")],
        {"Hero": 0, "Villain": "B"},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="hero_relative" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    notes = generate_for_hand(legacy_hand, config=config)

    assert [note.rule_id for note in notes] == ["hero_relative_001", "hero_relative_004"]
    assert notes[1].player_id == 2
    assert notes[1].evidence["hero_action"] == "4bets"
    assert notes[1].evidence["villain_action"] == "folds"


def test_range_capture_rules_are_disabled_by_default():
    legacy_hand = holdem_hand(
        ["BTN", "BB"],
        {"BTN": ["As", "Ks"], "BB": ["Qd", "Jc"]},
        [("BTN", "raises", 3)],
        {"BTN": 0, "BB": "B"},
    )

    assert note_ids(legacy_hand) == set()


def test_range_capture_generates_rfi_note_when_enabled():
    legacy_hand = holdem_hand(
        ["BTN", "BB"],
        {"BTN": ["As", "Ks"], "BB": ["Qd", "Jc"]},
        [("BTN", "raises", 3)],
        {"BTN": 0, "BB": "B"},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="range_capture" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    notes = generate_for_hand(legacy_hand, config=config)

    assert [note.rule_id for note in notes] == ["range_capture_001"]
    assert notes[0].evidence["range_hand"] == "AKs"
    assert notes[0].evidence["range_action"] == "rfi"
    assert notes[0].evidence["raise_number"] == 1


def test_range_capture_generates_3bet_and_call_vs_raise_notes():
    legacy_hand = holdem_hand(
        ["CO", "BTN", "BB"],
        {"CO": ["As", "Kh"], "BTN": ["Qd", "Qh"], "BB": ["Jd", "Tc"]},
        [("CO", "raises", 3), ("BTN", "raises", 10), ("BB", "calls", 10)],
        {"CO": 1, "BTN": 0, "BB": "B"},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="range_capture" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    notes = generate_for_hand(legacy_hand, config=config)

    assert [note.rule_id for note in notes] == ["range_capture_001", "range_capture_002", "range_capture_004"]
    assert notes[0].evidence["range_hand"] == "AKo"
    assert notes[1].evidence["range_hand"] == "QQ"
    assert notes[1].evidence["range_action"] == "3bet"
    assert notes[2].evidence["range_hand"] == "JTo"
    assert notes[2].evidence["range_action"] == "call_vs_raise"


def test_range_capture_generates_4bet_note():
    legacy_hand = holdem_hand(
        ["CO", "BTN", "BB"],
        {"CO": ["As", "Kh"], "BTN": ["Qd", "Qh"], "BB": ["Jd", "Jc"]},
        [("CO", "raises", 3), ("BTN", "raises", 10), ("BB", "raises", 25)],
        {"CO": 1, "BTN": 0, "BB": "B"},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="range_capture" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    notes = generate_for_hand(legacy_hand, config=config)

    assert [note.rule_id for note in notes] == ["range_capture_001", "range_capture_002", "range_capture_003"]
    assert notes[2].evidence["range_hand"] == "JJ"
    assert notes[2].evidence["range_action"] == "4bet"
    assert notes[2].evidence["raise_number"] == 3


def test_range_capture_keeps_plo_cards_for_visible_range():
    legacy_hand = hand(
        ["BTN", "BB"],
        {"BTN": ["As", "Kh", "Qd", "Jc"], "BB": ["Ks", "Kd", "7c", "2d"]},
        [("BTN", "raises", 3)],
        {"BTN": 0, "BB": "B"},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="hwang_plo_preflop" enabled="False"/>'
        '<ruleset name="range_capture" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    notes = generate_for_hand(legacy_hand, config=config)

    assert [note.rule_id for note in notes] == ["range_capture_001"]
    assert notes[0].evidence["range_hand"] == "As Kh Qd Jc"


def test_stud_draw_first_street_rules_are_disabled_by_default():
    legacy_hand = stud_hand(
        ["Seat1", "Seat2"],
        {"Seat1": ["2c", "7d", "Kc"], "Seat2": ["3c", "4d", "8s"]},
        [("Seat1", "bringin", 1), ("Seat2", "completes", 2)],
        {"Seat1": 1, "Seat2": 0},
    )

    assert note_ids(legacy_hand) == set()


def test_stud_draw_first_street_generates_stud_complete_and_call_notes():
    legacy_hand = stud_hand(
        ["Seat1", "Seat2", "Seat3"],
        {
            "Seat1": ["2c", "7d", "Kc"],
            "Seat2": ["3c", "4d", "8s"],
            "Seat3": ["5h", "6h", "9d"],
        },
        [("Seat1", "bringin", 1), ("Seat2", "completes", 2), ("Seat3", "calls", 2)],
        {"Seat1": 2, "Seat2": 1, "Seat3": 0},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="stud_draw_first_street" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    notes = generate_for_hand(legacy_hand, config=config)

    assert [note.rule_id for note in notes] == ["stud_draw_001", "stud_draw_002"]
    assert notes[0].evidence["door_card"] == "8s"
    assert notes[0].evidence["mixed_action"] == "complete"
    assert notes[0].evidence["variant"] == "razz"
    assert notes[1].evidence["door_card"] == "9d"
    assert notes[1].evidence["mixed_action"] == "call_complete"


def test_stud_draw_first_street_generates_draw_open_and_call_notes():
    legacy_hand = draw_hand(
        ["BTN", "BB"],
        {
            "BTN": ["2c", "3d", "4h", "7s", "8c"],
            "BB": ["2d", "5d", "6h", "9s", "Tc"],
        },
        [("BTN", "raises", 2), ("BB", "calls", 2)],
        {"BTN": 0, "BB": "B"},
    )
    config = config_from_xml(
        '<FreePokerToolsConfig><autonotes enabled="True">'
        '<ruleset name="stud_draw_first_street" enabled="True"/>'
        "</autonotes></FreePokerToolsConfig>",
    )

    notes = generate_for_hand(legacy_hand, config=config)

    assert [note.rule_id for note in notes] == ["stud_draw_003", "stud_draw_004"]
    assert notes[0].evidence["draw_hand"] == "2c 3d 4h 7s 8c"
    assert notes[0].evidence["mixed_action"] == "open_raise"
    assert notes[1].evidence["draw_hand"] == "2d 5d 6h 9s Tc"
    assert notes[1].evidence["mixed_action"] == "call_raise"


def test_generate_for_hand_still_accepts_custom_rules():
    legacy_hand = hand(
        ["BTN", "SB"],
        {"BTN": ["As", "Kh", "Qd", "7c"], "SB": ["Ks", "Kh", "Qd", "7c"]},
        [("BTN", "raises", 3)],
        {"BTN": 0, "SB": "S"},
    )
    custom_rule = AutoNoteRule(
        rule_id="custom_rule",
        version=1,
        name="Custom rule",
        note_template="{player}: custom",
        predicate=lambda _hand, player, _context: player == "BTN",
        evidence_builder=lambda _hand, _player, _context: {"source": "test"},
    )

    notes = generate_for_hand(legacy_hand, rules=(custom_rule,))

    assert [note.rule_id for note in notes] == ["custom_rule"]
    assert notes[0].evidence == {"source": "test"}

    assert generate_for_hand(legacy_hand, rules=(custom_rule,), rule_ids={"other_rule"}) == []


def sqlite_autonote_db():
    conn = sqlite3.connect(":memory:")
    sql = Sql(db_server="sqlite")
    conn.execute(
        "CREATE TABLE Players (id INTEGER PRIMARY KEY, name TEXT, siteId INTEGER, comment TEXT)",
    )
    conn.execute(
        "CREATE TABLE Gametypes (id INTEGER PRIMARY KEY, siteId INTEGER, type TEXT, base TEXT, "
        "category TEXT, limitType TEXT, smallBlind INTEGER, bigBlind INTEGER)",
    )
    conn.execute(
        "CREATE TABLE Hands (id INTEGER PRIMARY KEY, siteHandNo INTEGER, tourneyId INTEGER, gametypeId INTEGER, "
        "startTime timestamp, seats INTEGER, heroSeat INTEGER, boardcard1 INTEGER, boardcard2 INTEGER, "
        "boardcard3 INTEGER, boardcard4 INTEGER, boardcard5 INTEGER, street0Pot INTEGER, street1Pot INTEGER, "
        "street2Pot INTEGER, street3Pot INTEGER, street4Pot INTEGER, finalPot INTEGER)",
    )
    conn.execute(
        "CREATE TABLE HandsPlayers (handId INTEGER, playerId INTEGER, startCash INTEGER, effStack INTEGER, "
        "position TEXT, seatNo INTEGER, card1 INTEGER, card2 INTEGER, card3 INTEGER, card4 INTEGER, "
        "card5 INTEGER, card6 INTEGER, card7 INTEGER, card8 INTEGER, card9 INTEGER, card10 INTEGER, "
        "card11 INTEGER, card12 INTEGER, card13 INTEGER, card14 INTEGER, card15 INTEGER, card16 INTEGER, "
        "card17 INTEGER, card18 INTEGER, card19 INTEGER, card20 INTEGER, totalProfit INTEGER, winnings INTEGER, "
        "comment TEXT, wonAtSD INTEGER, sawShowdown INTEGER, cnt_f_spr INTEGER, val_f_spr INTEGER, "
        "cnt_t_spr INTEGER, val_t_spr INTEGER, cnt_r_spr INTEGER, val_r_spr INTEGER)",
    )
    conn.execute("CREATE TABLE Actions (id INTEGER PRIMARY KEY, name TEXT, code TEXT)")
    conn.execute(
        "CREATE TABLE HandsActions (handId INTEGER, playerId INTEGER, street INTEGER, actionNo INTEGER, "
        "streetActionNo INTEGER, actionId INTEGER, amount INTEGER, raiseTo INTEGER, amountCalled INTEGER, "
        "numDiscarded INTEGER, cardsDiscarded TEXT, allIn INTEGER)",
    )
    conn.execute(sql.query["createPlayerAutoNotesTable"])
    conn.execute("INSERT INTO Players (id, name, siteId, comment) VALUES (1, 'Villain', 2, '')")
    conn.execute(
        "INSERT INTO Gametypes (id, siteId, type, base, category, limitType, smallBlind, bigBlind) "
        "VALUES (10, 2, 'ring', 'hold', 'omahahi', 'pl', 50, 100)",
    )
    conn.execute(
        "INSERT INTO Hands (id, siteHandNo, tourneyId, gametypeId, startTime, seats, heroSeat, "
        "boardcard1, boardcard2, boardcard3, boardcard4, boardcard5, street0Pot, street1Pot, "
        "street2Pot, street3Pot, street4Pot, finalPot) "
        "VALUES (100, 12345, NULL, 10, '2026-06-30 12:00:00', 3, 0, "
        "0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3000)",
    )
    conn.executemany(
        "INSERT INTO Actions (id, name, code) VALUES (?, ?, ?)",
        [
            (4, "big blind", "BB"),
            (6, "calls", "C"),
            (7, "raises", "R"),
            (10, "folds", "F"),
            (11, "checks", "K"),
        ],
    )
    conn.commit()

    db = Database.__new__(Database)
    db.sql = sql
    db.conn = conn
    db.panbulk = []
    db.get_cursor = conn.cursor
    db.commit = conn.commit
    db.rollback = conn.rollback
    return db


def test_sqlite_drop_tables_ignores_internal_sequence_table():
    conn = sqlite3.connect(":memory:")
    sql = Sql(db_server="sqlite")
    conn.execute("CREATE TABLE Example (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
    conn.execute("INSERT INTO Example (name) VALUES ('row')")
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='sqlite_sequence'").fetchone()

    db = Database.__new__(Database)
    db.sql = sql
    db.backend = Database.SQLITE
    db.connection = conn
    db.get_cursor = conn.cursor
    db.commit = conn.commit
    db.rollback = conn.rollback

    db.drop_tables()

    assert conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Example'").fetchone() is None


def encode_cards(*cards):
    from fpdb_3_legacy.Card import encodeCard

    return [encodeCard(card) for card in cards] + [0] * (20 - len(cards))


def insert_hands_player(conn, hand_id, player_id, seat_no, position, cards):
    values = [
        hand_id,
        player_id,
        10000,
        10000,
        position,
        seat_no,
        *encode_cards(*cards),
        0,
        0,
        "",
        0,
        0,
        None,
        None,
        None,
        None,
        None,
        None,
    ]
    placeholders = ", ".join("?" for _value in values)
    conn.execute(
        "INSERT INTO HandsPlayers (handId, playerId, startCash, effStack, position, seatNo, "
        "card1, card2, card3, card4, card5, card6, card7, card8, card9, card10, card11, card12, "
        "card13, card14, card15, card16, card17, card18, card19, card20, totalProfit, winnings, "
        "comment, wonAtSD, sawShowdown, cnt_f_spr, val_f_spr, cnt_t_spr, val_t_spr, cnt_r_spr, val_r_spr) "
        f"VALUES ({placeholders})",
        values,
    )


def test_database_stores_and_reads_autonotes_idempotently():
    db = sqlite_autonote_db()
    note = GeneratedAutoNote(
        player_id=1,
        hand_id=100,
        rule_id="hwang_plo_081",
        rule_version=1,
        note_text="first",
        evidence={"hole_cards": "Ks Kh Qd 7c"},
    )
    updated = GeneratedAutoNote(
        player_id=1,
        hand_id=100,
        rule_id="hwang_plo_081",
        rule_version=1,
        note_text="updated",
        evidence={"hole_cards": "Ks Kh Qd 7c", "action": "3bet"},
    )

    db.storePlayerAutoNotes([note], doinsert=True)
    db.storePlayerAutoNotes([updated], doinsert=True)

    assert db.getPlayerAutoNoteCount(1) == 1
    assert db.playerHasNotes(1)
    notes = db.getPlayerAutoNotes(1)
    assert len(notes) == 1
    assert notes[0]["ruleSet"] == "hwang_plo_preflop"
    assert notes[0]["noteText"] == "updated"
    assert notes[0]["evidence"]["action"] == "3bet"
    assert notes[0]["evidenceText"] == "hole_cards=Ks Kh Qd 7c; action=3bet"
    assert db.getPlayerAutoNotes(1, rule_set_ids={"holdem_cash_preflop"}) == []
    assert db.getPlayerAutoNotes(1, rule_ids={"hwang_plo_081"})[0]["ruleSet"] == "hwang_plo_preflop"


def test_database_summarizes_autonotes_for_workbench():
    db = sqlite_autonote_db()
    db.storePlayerAutoNotes(
        [
            GeneratedAutoNote(1, 100, "hwang_plo_081", 1, "single pair 3bet", {"hole_cards": "Ks Kh Qd 7c"}),
            GeneratedAutoNote(1, 100, "hwang_plo_082", 1, "rainbow VPIP", {"hole_cards": "As Kh Qd 7c"}),
        ],
        doinsert=True,
    )

    players = db.searchPlayersWithAutoNotes("vill")
    recent = db.getRecentPlayerAutoNotes(limit=10)
    player_summary = db.getAutoNotePlayerSummary(limit=10)
    rule_summary = db.getAutoNoteRuleSummary(limit=10)
    filtered_recent = db.getRecentPlayerAutoNotes(
        limit=10,
        player_filter="vill",
        date_from="2026-06-30",
        date_to="2026-06-30",
        site_id=2,
        limit_type="pl",
    )

    assert players == [{"playerId": 1, "playerName": "Villain", "siteId": 2}]
    assert [note["ruleId"] for note in recent] == ["hwang_plo_082", "hwang_plo_081"]
    assert [note["ruleId"] for note in filtered_recent] == ["hwang_plo_082", "hwang_plo_081"]
    assert db.getRecentPlayerAutoNotes(limit=10, site_id=99) == []
    assert recent[0]["playerName"] == "Villain"
    assert recent[0]["siteHandNo"] == 12345
    assert recent[0]["handStartTime"] == "2026-06-30 12:00:00"
    assert player_summary[0]["playerId"] == 1
    assert player_summary[0]["playerName"] == "Villain"
    assert player_summary[0]["noteCount"] == 2
    assert player_summary[0]["lastNoteTs"]
    assert {row["ruleId"]: row["noteCount"] for row in rule_summary} == {
        "hwang_plo_081": 1,
        "hwang_plo_082": 1,
    }
    assert all(row["ruleSet"] == "hwang_plo_preflop" for row in rule_summary)


def test_backfill_database_preview_generates_notes_from_imported_hands():
    db = sqlite_autonote_db()
    conn = db.conn
    conn.execute("INSERT INTO Players (id, name, siteId, comment) VALUES (2, 'BTN', 2, '')")
    conn.execute("INSERT INTO Players (id, name, siteId, comment) VALUES (3, 'BB', 2, '')")
    insert_hands_player(conn, 100, 2, 1, 0, ["As", "Kh", "Qd", "7c"])
    insert_hands_player(conn, 100, 1, 2, "S", ["Ks", "Kh", "Qd", "7c"])
    insert_hands_player(conn, 100, 3, 3, "B", ["As", "Ah", "Qd", "7c"])
    conn.executemany(
        "INSERT INTO HandsActions (handId, playerId, street, actionNo, streetActionNo, actionId, amount, "
        "raiseTo, amountCalled, numDiscarded, cardsDiscarded, allIn) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (100, 3, 0, 1, 1, 4, 100, 0, 0, 0, None, 0),
            (100, 2, 0, 2, 2, 7, 300, 300, 100, 0, None, 0),
            (100, 1, 0, 3, 3, 7, 1000, 1000, 300, 0, None, 0),
        ],
    )
    conn.commit()

    hand_from_db = load_hand_from_database(db, 100)
    assert hand_from_db is not None
    assert hand_from_db.join_holecards("Villain", asList=True)[:4] == ["Ks", "Kh", "Qd", "7c"]
    assert hand_from_db.actions["PREFLOP"][1][:2] == ("BTN", "raises")

    stats = backfill_database_preview(
        db=db,
        rule_set_ids={"hwang_plo_preflop"},
        limit=10,
        date_from="2026-06-30",
        date_to="2026-06-30",
    )

    assert stats["source"] == "database"
    assert stats["hands"] == 1
    assert stats["matched_hands"] == 1
    assert stats["notes"] >= 1
    assert any(row["playerName"] == "Villain" and row["ruleId"] == "hwang_plo_081" for row in stats["preview"])


def test_file_backfill_lookup_falls_back_to_site_hand_number_when_site_id_differs():
    db = sqlite_autonote_db()
    stats = {}

    assert _lookup_hand_ids(db, 12345, 99, stats=stats) == [100]
    assert stats["matched_by_site_hand_only"] == 1


def test_format_generated_notes_for_ui():
    notes = [
        {
            "handId": 100,
            "ruleId": "hwang_plo_081",
            "ruleVersion": 1,
            "noteText": "3-bet single paired non-AAxx",
            "createdTs": "2026-06-30 12:00:00",
            "evidence": {
                "hole_cards": "Ks Kh Qd 7c",
                "position": "S",
                "preflop_raises": ["BTN", "SB"],
            },
        },
        {
            "handId": 101,
            "ruleId": "hwang_plo_081",
            "ruleVersion": 1,
            "noteText": "another 3-bet single paired non-AAxx",
            "createdTs": "2026-06-30 12:05:00",
        },
        {
            "handId": 102,
            "ruleId": "hwang_plo_082",
            "ruleVersion": 1,
            "noteText": "rainbow VPIP",
            "createdTs": "2026-06-30 12:10:00",
        },
    ]
    text = format_generated_notes(
        notes,
    )

    assert "Summary" in text
    assert "Rule sets" in text
    assert "- hwang_plo_preflop: 3" in text
    assert "Rules" in text
    assert "- hwang_plo_081: 2" in text
    assert "- hwang_plo_082: 1" in text
    assert "hwang_plo_preflop:hwang_plo_081 v1" in text
    assert "hand 100" in text
    assert "3-bet single paired non-AAxx" in text
    assert "Evidence: hole_cards=Ks Kh Qd 7c; position=S; preflop_raises=BTN > SB" in text

    filtered = format_generated_notes(notes, rule_ids={"hwang_plo_082"})
    assert "- hwang_plo_082: 1" in filtered
    assert "- hwang_plo_081: 2" not in filtered
    assert "rainbow VPIP" in filtered
    assert "3-bet single paired non-AAxx" not in filtered


def test_filter_generated_notes_preserves_order_and_supports_rule_set_fallback():
    notes = [
        {"ruleId": "hwang_plo_081", "noteText": "first"},
        {"ruleSet": "manual_override", "ruleId": "hwang_plo_082", "noteText": "second"},
        {"ruleId": "holdem_cash_001", "noteText": "third"},
    ]

    assert [note["noteText"] for note in filter_generated_notes(notes)] == ["first", "second", "third"]
    assert [
        note["noteText"] for note in filter_generated_notes(notes, rule_set_ids={"hwang_plo_preflop"})
    ] == ["first"]
    assert [note["noteText"] for note in filter_generated_notes(notes, rule_ids={"holdem_cash_001"})] == ["third"]


def test_format_note_evidence_prioritizes_known_fields():
    text = format_note_evidence(
        {
            "extra": "value",
            "position": 0,
            "preflop_raises": ["CO", "BB"],
            "hole_cards": "As Kh Qd 7c",
        },
    )

    assert text == "hole_cards=As Kh Qd 7c; position=0; preflop_raises=CO > BB; extra=value"


def test_summarize_generated_notes_sorts_by_count_then_rule_id():
    summary = summarize_generated_notes(
        [
            {"ruleId": "hwang_plo_082"},
            {"ruleId": "hwang_plo_081"},
            {"ruleId": "hwang_plo_081"},
        ],
    )

    assert summary == [
        {"ruleId": "hwang_plo_081", "count": 2},
        {"ruleId": "hwang_plo_082", "count": 1},
    ]


def test_summarize_generated_notes_by_rule_set_sorts_by_count_then_rule_set_id():
    summary = summarize_generated_notes_by_rule_set(
        [
            {"ruleId": "hwang_plo_082"},
            {"ruleSet": "manual_override", "ruleId": "hwang_plo_082"},
            {"ruleId": "holdem_cash_001"},
            {"ruleId": "hwang_plo_081"},
            {"ruleId": "unknown_rule"},
        ],
    )

    assert summary == [
        {"ruleSet": "hwang_plo_preflop", "count": 2},
        {"ruleSet": "holdem_cash_preflop", "count": 1},
        {"ruleSet": "manual_override", "count": 1},
        {"ruleSet": "unknown", "count": 1},
    ]


def test_backfill_rule_count_summary_is_stable():
    stats = {}
    _add_rule_counts(
        stats,
        [
            GeneratedAutoNote(1, 100, "hwang_plo_082", 1, "rainbow VPIP", {}),
            GeneratedAutoNote(2, 100, "hwang_plo_081", 1, "3-bet single pair", {}),
            GeneratedAutoNote(3, 101, "hwang_plo_081", 1, "3-bet single pair", {}),
        ],
    )

    assert stats["rules"] == {"hwang_plo_081": 2, "hwang_plo_082": 1}
    assert stats["rule_sets"] == {"hwang_plo_preflop": 3}
    assert format_rule_counts(stats["rules"]) == "hwang_plo_081=2, hwang_plo_082=1"
    assert format_rule_counts(stats["rule_sets"]) == "hwang_plo_preflop=3"
    assert format_rule_counts({}) == ""


def test_backfill_preview_row_is_gui_friendly():
    legacy_hand = hand(
        ["BTN", "SB"],
        {"BTN": ["As", "Kh", "Qd", "7c"], "SB": ["Ks", "Kh", "Qd", "7c"]},
        [("BTN", "raises", 3), ("SB", "raises", 10)],
        {"BTN": 0, "SB": "S"},
    )
    note = GeneratedAutoNote(
        11,
        555,
        "hwang_plo_081",
        1,
        "3-bet single pair",
        {"hole_cards": "Ks Kh Qd 7c", "preflop_raises": ["BTN", "SB"]},
    )

    row = _preview_row(note, {11: "SB"}, legacy_hand)

    assert row == {
        "playerId": 11,
        "playerName": "SB",
        "handId": 555,
        "siteHandNo": "site-hand-1",
        "siteId": "",
        "ruleSet": "hwang_plo_preflop",
        "ruleId": "hwang_plo_081",
        "ruleVersion": 1,
        "noteText": "3-bet single pair",
        "evidence": {"hole_cards": "Ks Kh Qd 7c", "preflop_raises": ["BTN", "SB"]},
        "evidenceText": "hole_cards=Ks Kh Qd 7c; preflop_raises=BTN > SB",
    }


def test_backfill_stats_json_is_stable_for_automation():
    text = format_stats_json(
        {
            "files": 2,
            "files_skipped": 1,
            "hands": 10,
            "matched_hands": 3,
            "notes": 4,
            "rule_sets": {"hwang_plo_preflop": 4},
            "rules": {"hwang_plo_082": 1, "hwang_plo_081": 3},
        },
        commit=True,
        rule_set_ids={"hwang_plo_preflop"},
        rule_ids={"hwang_plo_081"},
    )

    payload = json.loads(text)

    assert payload == {
        "disabled_hands": 0,
        "files": 2,
        "files_skipped": 1,
        "games": {},
        "hands_without_actions": 0,
        "hands": 10,
        "import_duplicates": 0,
        "import_errors": 0,
        "import_files": 0,
        "import_partial": 0,
        "import_skipped": 0,
        "import_stored": 0,
        "matched_hands": 3,
        "matched_by_site_hand_only": 0,
        "mode": "write",
        "no_note_hands": 0,
        "notes": 4,
        "raw_unmatched_hands": 0,
        "raw_unmatched_notes": 0,
        "raw_unmatched_rule_sets": {},
        "raw_unmatched_rules": {},
        "rule_sets": {"hwang_plo_preflop": 4},
        "rule_sets_filter": ["hwang_plo_preflop"],
        "rules": {"hwang_plo_081": 3, "hwang_plo_082": 1},
        "rules_filter": ["hwang_plo_081"],
        "source": "files",
        "unmatched_hands": 0,
        "unmatched_samples": [],
        "unsupported_hands": 0,
    }
    assert text.index("hwang_plo_081") < text.index("hwang_plo_082")


def test_rule_manifest_exposes_legacy_parity_surface():
    manifest = rule_manifest()

    assert manifest["engine"] == "fpdb_3_legacy.autonotes"
    assert manifest["schemaVersion"] == 1
    rule_sets = {rule_set["id"]: rule_set for rule_set in manifest["ruleSets"]}
    assert "hwang_plo_preflop" in rule_sets
    assert any(rule["id"] == "hwang_plo_081" for rule in rule_sets["hwang_plo_preflop"]["rules"])
    assert any(rule_set["id"] == "stud_draw_first_street" for rule_set in manifest["ruleSets"])



def test_backfill_cli_can_print_parity_manifest(capsys):
    assert backfill_main(["--manifest"]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload["engine"] == "fpdb_3_legacy.autonotes"
    assert payload["ruleSets"]


def test_backfill_parse_rule_set_filter():
    assert parse_id_filter(None) is None
    assert parse_id_filter([]) is None
    assert parse_id_filter(["hwang_plo_preflop, holdem_cash_preflop", ""]) == {
        "hwang_plo_preflop",
        "holdem_cash_preflop",
    }
    assert parse_rule_set_filter(["hwang_plo_preflop"]) == {"hwang_plo_preflop"}


def test_backfill_filter_validation_reports_unknown_ids():
    assert unknown_filter_ids(None, {"known"}) == []
    assert unknown_filter_ids({"known"}, {"known"}) == []
    assert unknown_filter_ids({"zeta", "alpha", "known"}, {"known"}) == ["alpha", "zeta"]


def test_backfill_prepare_hand_sets_ids_and_generates_notes():
    legacy_hand = hand(
        ["BTN", "SB", "BB"],
        {"BTN": ["As", "Kh", "Qd", "7c"], "SB": ["Ks", "Kh", "Qd", "7c"], "BB": ["As", "Ah", "Qd", "7c"]},
        [("BTN", "raises", 3), ("SB", "raises", 10)],
        {"BTN": 0, "SB": "S", "BB": "B"},
    )
    legacy_hand.handsplayers = {}

    notes = _prepare_hand_for_autonotes(legacy_hand, 555, {"BTN": 10, "SB": 11, "BB": 12})

    assert {note.rule_id for note in notes} >= {"hwang_plo_081"}
    assert all(note.hand_id == 555 for note in notes)
    assert any(note.player_id == 11 for note in notes)
