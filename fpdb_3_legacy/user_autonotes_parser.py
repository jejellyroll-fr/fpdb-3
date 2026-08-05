"""Declarative engine and parser for user-defined custom Auto Note rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fpdb_3_legacy.AutoNotePlo import normalize_cards, rank_counts
from fpdb_3_legacy.AutoNoteRules import PreflopContext
from fpdb_3_legacy.AutoNotes import AutoNoteRule, AutoNoteRuleSet, GeneratedAutoNote
from fpdb_3_legacy.Configuration import CONFIG_PATH
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("user_autonotes_parser")


def get_user_autonotes_path(custom_path: Path | str | None = None) -> Path:
    if custom_path:
        return Path(custom_path)
    if CONFIG_PATH:
        return Path(CONFIG_PATH) / "user_autonotes.json"
    return Path.home() / ".fpdb" / "user_autonotes.json"


class CustomAutoNoteRule(AutoNoteRule):
    """AutoNoteRule subclass supporting dynamic evidence key replacement in note templates."""

    def evaluate(self, hand: Any, player_name: str, context: PreflopContext) -> GeneratedAutoNote | None:
        player_ids = getattr(hand, "playerIds", {}) or {}
        hand_id = getattr(hand, "dbid_hands", None)
        player_id = player_ids.get(player_name)
        if not player_id or hand_id is None or not self.predicate(hand, player_name, context):
            return None

        evidence = self.evidence_builder(hand, player_name, context)

        # Prepare kwargs for template formatting
        fmt_kwargs: dict[str, str] = {"player": player_name}
        for k, v in evidence.items():
            if isinstance(v, list):
                fmt_kwargs[k] = " ".join(str(item) for item in v)
            else:
                fmt_kwargs[k] = str(v)

        # Allow fallback for common alias names
        if "eff_stack_bb" in fmt_kwargs and "eff_stack" not in fmt_kwargs:
            fmt_kwargs["eff_stack"] = fmt_kwargs["eff_stack_bb"]
        if "flop" in fmt_kwargs and "board" not in fmt_kwargs:
            fmt_kwargs["board"] = fmt_kwargs["flop"]

        # Safe template evaluation
        class SafeDict(dict):
            def __missing__(self, key: str) -> str:
                return f"{{{key}}}"

        try:
            note_text = self.note_template.format_map(SafeDict(fmt_kwargs))
        except Exception:
            note_text = self.note_template.format(player=player_name)

        return GeneratedAutoNote(
            player_id=player_id,
            hand_id=hand_id,
            rule_id=self.rule_id,
            rule_version=self.version,
            note_text=note_text,
            evidence=evidence,
        )


from decimal import Decimal


def _extract_big_blind(hand: Any) -> float:
    for attr in ("bigBlind", "bb", "big_blind"):
        val = getattr(hand, attr, None)
        if isinstance(val, (int, float, str, Decimal)):
            try:
                f_val = float(val)
                if f_val > 0:
                    return f_val
            except (TypeError, ValueError):
                pass
    return 1.0


def _extract_player_chips(hand: Any, player_name: str) -> float:
    players = getattr(hand, "players", []) or []
    for p in players:
        if len(p) >= 3 and p[1] == player_name:
            try:
                return float(p[2])
            except (TypeError, ValueError):
                pass
    handsplayers = getattr(hand, "handsplayers", {}) or {}
    stats = handsplayers.get(player_name, {})
    chips = stats.get("chips") or stats.get("start_stack") or 0.0
    try:
        return float(chips)
    except (TypeError, ValueError):
        return 0.0


def _extract_community_cards(hand: Any) -> list[str]:
    board = getattr(hand, "board", None)
    if isinstance(board, dict):
        cards = []
        for street in ("FLOP", "TURN", "RIVER"):
            cards.extend(board.get(street, []))
        return normalize_cards(cards)
    if isinstance(board, list):
        return normalize_cards(board)
    cc = getattr(hand, "communityCards", None) or []
    return normalize_cards(cc)


def _position_name(pos_val: Any) -> str:
    if pos_val == 0 or pos_val == "0":
        return "BTN"
    if pos_val == 1 or pos_val == "S" or pos_val == "SB":
        return "SB"
    if pos_val == 2 or pos_val == "B" or pos_val == "BB":
        return "BB"
    if isinstance(pos_val, str):
        return pos_val.upper()
    if pos_val == 3:
        return "CO"
    if pos_val == 4:
        return "MP"
    if pos_val == 5:
        return "UTG"
    return str(pos_val) if pos_val is not None else ""


def extract_field_value(field: str, hand: Any, player_name: str, context: PreflopContext) -> Any:  # noqa: C901, PLR0912, PLR0915
    """Extract named field value from hand context for declarative evaluation."""
    field = field.lower().strip()

    if field == "game.base":
        gt = getattr(hand, "gametype", {}) or {}
        if isinstance(gt, dict):
            base = gt.get("base", "holdem")
        else:
            base = getattr(gt, "base", "holdem")
        base = str(base).lower()
        if base in ("hold", "holdem"):
            return "holdem"
        return base

    if field == "game.category":
        gt = getattr(hand, "gametype", {}) or {}
        if isinstance(gt, dict):
            return str(gt.get("category", "ring")).lower()
        return str(getattr(gt, "category", "ring")).lower()

    if field == "game.limit":
        gt = getattr(hand, "gametype", {}) or {}
        if isinstance(gt, dict):
            return str(gt.get("limitType", "nl")).lower()
        return str(getattr(gt, "limitType", "nl")).lower()

    if field == "player.position":
        pos_raw = context.positions.get(player_name)
        return _position_name(pos_raw)

    if field == "opponent.position":
        first_raise = context.first_raise
        if first_raise and first_raise.player != player_name:
            has_pos = context.has_position_on(player_name, first_raise.player)
            return "IP" if has_pos else "OOP"
        return "IP"

    if field == "player.eff_stack_bb":
        bb = _extract_big_blind(hand)
        chips = _extract_player_chips(hand, player_name)
        return round(chips / bb, 2) if bb > 0 else 0.0

    if field in ("spr.flop", "spr"):
        bb = _extract_big_blind(hand)
        chips = _extract_player_chips(hand, player_name)
        pot = getattr(hand, "pot", None) or getattr(hand, "totalPot", None) or (bb * 2)
        try:
            pot_val = float(pot)
        except (TypeError, ValueError):
            pot_val = bb * 2
        return round(chips / pot_val, 2) if pot_val > 0 else 99.0

    if field == "action.preflop":
        player_actions = context.player_actions.get(player_name, [])
        if not player_actions:
            return "none"
        first_act = player_actions[0]
        if context.player_made_raise_number(player_name, 1):
            return "open_raise"
        if context.player_made_raise_number(player_name, 2):
            return "3bet_allin" if first_act.is_allin else "3bet"
        if context.player_made_raise_number(player_name, 3):
            return "4bet"
        if context.player_called_first_raise(player_name):
            return "cold_call"
        if context.player_open_raised_then_folded_to_3bet(player_name):
            return "fold_vs_3bet"
        if first_act.is_call and len(context.raises) == 0:
            return "limp"
        return first_act.action.lower()

    if field == "action.flop":
        actions = getattr(hand, "actions", {}).get("FLOP", [])
        for act in actions:
            if len(act) >= 2 and act[0] == player_name:
                act_str = str(act[1]).lower()
                if "bet" in act_str or "raise" in act_str:
                    return "cbet" if context.player_made_raise_number(player_name, 1) else "donk"
                if "check" in act_str:
                    return "check"
                if "call" in act_str:
                    return "check_call"
                if "fold" in act_str:
                    return "fold_vs_cbet"
        return "none"

    if field == "action.turn":
        actions = getattr(hand, "actions", {}).get("TURN", [])
        for act in actions:
            if len(act) >= 2 and act[0] == player_name:
                act_str = str(act[1]).lower()
                if "bet" in act_str or "raise" in act_str:
                    return "second_barrel"
                if "fold" in act_str:
                    return "fold"
        return "none"

    if field == "action.river":
        actions = getattr(hand, "actions", {}).get("RIVER", [])
        for act in actions:
            if len(act) >= 2 and act[0] == player_name:
                act_str = str(act[1]).lower()
                if "bet" in act_str or "raise" in act_str:
                    return "third_barrel"
        return "none"

    if field == "hand.rank":
        hp = getattr(hand, "handsplayers", {}).get(player_name, {})
        rank = hp.get("handText") or hp.get("showCards") or ""
        return str(rank).lower()

    if field == "board.flop_texture":
        board = _extract_community_cards(hand)
        flop = board[:3]
        if not flop:
            return "dry"
        counts = rank_counts(flop)
        if any(c >= 2 for c in counts.values()):
            return "paired"
        suits = [card[-1].lower() for card in flop if len(card) >= 2]
        if len(set(suits)) == 1:
            return "monotone"
        if len(set(suits)) == 2:
            return "twotone"
        return "rainbow"

    return ""


def evaluate_leaf_condition(  # noqa: C901, PLR0912
    rule: dict[str, Any], hand: Any, player_name: str, context: PreflopContext
) -> bool:
    field = rule.get("field", "")
    op = rule.get("operator", "eq").lower()
    target_val = rule.get("value")

    actual_val = extract_field_value(field, hand, player_name, context)

    if op in ("eq", "=="):
        if isinstance(target_val, str) and isinstance(actual_val, str):
            return actual_val.lower() == target_val.lower()
        return actual_val == target_val

    if op in ("neq", "!="):
        if isinstance(target_val, str) and isinstance(actual_val, str):
            return actual_val.lower() != target_val.lower()
        return actual_val != target_val

    if op in ("gt", ">"):
        try:
            if actual_val is None or target_val is None:
                return False
            return float(actual_val) > float(target_val)
        except (TypeError, ValueError):
            return False

    if op in ("gte", ">="):
        try:
            if actual_val is None or target_val is None:
                return False
            return float(actual_val) >= float(target_val)
        except (TypeError, ValueError):
            return False

    if op in ("lt", "<"):
        try:
            if actual_val is None or target_val is None:
                return False
            return float(actual_val) < float(target_val)
        except (TypeError, ValueError):
            return False

    if op in ("lte", "<="):
        try:
            if actual_val is None or target_val is None:
                return False
            return float(actual_val) <= float(target_val)
        except (TypeError, ValueError):
            return False

    if op == "in":
        if isinstance(target_val, (list, tuple, set)):
            target_set = {str(x).lower() for x in target_val}
            return str(actual_val).lower() in target_set
        return str(target_val).lower() in str(actual_val).lower()

    if op in ("not_in", "not in"):
        if isinstance(target_val, (list, tuple, set)):
            target_set = {str(x).lower() for x in target_val}
            return str(actual_val).lower() not in target_set
        return str(target_val).lower() not in str(actual_val).lower()

    if op == "between":
        if isinstance(target_val, (list, tuple)) and len(target_val) >= 2:
            try:
                val = float(actual_val)
                return float(target_val[0]) <= val <= float(target_val[1])
            except (TypeError, ValueError):
                return False
        return False

    if op == "contains":
        return str(target_val).lower() in str(actual_val).lower()

    return False


def evaluate_condition_tree(
    condition_tree: dict[str, Any],
    hand: Any,
    player_name: str,
    context: PreflopContext,
) -> bool:
    """Evaluate a nested logical condition tree (AND, OR, NOT)."""
    if not condition_tree:
        return True

    op = str(condition_tree.get("operator", "")).upper()
    rules = condition_tree.get("rules", [])

    if op == "AND":
        return all(evaluate_condition_tree(r, hand, player_name, context) for r in rules)
    if op == "OR":
        return any(evaluate_condition_tree(r, hand, player_name, context) for r in rules)
    if op == "NOT":
        return not any(evaluate_condition_tree(r, hand, player_name, context) for r in rules)

    # Leaf condition
    return evaluate_leaf_condition(condition_tree, hand, player_name, context)


def build_evidence_dict(  # noqa: C901
    hand: Any,
    player_name: str,
    context: PreflopContext,
    evidence_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build captured evidence payload based on requested schema flags."""
    cfg = evidence_config or {}
    evidence: dict[str, Any] = {}

    bb = _extract_big_blind(hand)
    chips = _extract_player_chips(hand, player_name)
    eff_stack_bb = round(chips / bb, 1) if bb > 0 else 0.0

    if cfg.get("capture_hole", True):
        evidence["hole"] = context.hole_cards.get(player_name, [])

    if cfg.get("capture_board", True):
        cards = _extract_community_cards(hand)
        evidence["flop"] = cards[:3]
        if len(cards) >= 4:
            evidence["turn"] = [cards[3]]
        if len(cards) >= 5:
            evidence["river"] = [cards[4]]

    if cfg.get("capture_eff_stack", True):
        evidence["eff_stack_bb"] = eff_stack_bb
        evidence["eff_stack"] = eff_stack_bb

    if cfg.get("capture_action_sequence", True):
        player_acts = [a.action for a in context.player_actions.get(player_name, [])]
        evidence["action_sequence"] = player_acts

    if cfg.get("capture_pot", True):
        pot = getattr(hand, "pot", None) or getattr(hand, "totalPot", None) or (bb * 2)
        try:
            evidence["pot"] = round(float(pot), 1)
        except (TypeError, ValueError):
            evidence["pot"] = round(bb * 2, 1)

    if cfg.get("capture_spr", True):
        pot_val = evidence.get("pot", bb * 2)
        evidence["spr"] = round(chips / pot_val, 2) if pot_val > 0 else 99.0

    if cfg.get("capture_made_hand", False):
        evidence["made_hand"] = extract_field_value("hand.rank", hand, player_name, context)

    return evidence


def compile_custom_rule(rule_dict: dict[str, Any], rule_set_id: str = "custom_user_rules") -> AutoNoteRule:
    """Compile declarative JSON rule dict into an AutoNoteRule instance."""
    rule_id = str(rule_dict.get("rule_id", "custom_rule"))
    version = int(rule_dict.get("version", 1))
    name = str(rule_dict.get("name", "Custom Rule"))
    note_template = str(rule_dict.get("note_template", "{player}: custom note"))
    condition_tree = rule_dict.get("conditions", {})
    evidence_config = rule_dict.get("evidence", {})

    def predicate(hand: Any, player_name: str, context: PreflopContext) -> bool:
        return evaluate_condition_tree(condition_tree, hand, player_name, context)

    def evidence_builder(hand: Any, player_name: str, context: PreflopContext) -> dict[str, Any]:
        return build_evidence_dict(hand, player_name, context, evidence_config)

    return CustomAutoNoteRule(
        rule_id=rule_id,
        version=version,
        name=name,
        note_template=note_template,
        predicate=predicate,
        evidence_builder=evidence_builder,
    )


def compile_custom_rule_set(rule_set_dict: dict[str, Any]) -> AutoNoteRuleSet:
    """Compile declarative JSON rule set into an AutoNoteRuleSet instance."""
    rule_set_id = str(rule_set_dict.get("rule_set_id", "custom_user_rules"))
    raw_rules = rule_set_dict.get("rules", [])
    compiled_rules = tuple(compile_custom_rule(r, rule_set_id) for r in raw_rules if isinstance(r, dict))

    return AutoNoteRuleSet(
        rule_set_id=rule_set_id,
        rules=compiled_rules,
        supports_hand=lambda _h: True,
        enabled_by_default=False,
    )


def load_user_autonotes_data(filepath: Path | str | None = None) -> dict[str, Any]:
    """Read user_autonotes.json file or return empty standard structure."""
    path = get_user_autonotes_path(filepath)
    if not path.exists():
        return {"version": 1, "custom_rule_sets": []}

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        log.exception("Failed to parse user_autonotes.json at %s", path)

    return {"version": 1, "custom_rule_sets": []}


def save_user_autonotes_data(data: dict[str, Any], filepath: Path | str | None = None) -> None:
    """Save user autonotes data structure to user_autonotes.json."""
    path = get_user_autonotes_path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_custom_rule_sets(filepath: Path | str | None = None) -> tuple[AutoNoteRuleSet, ...]:
    """Load and compile custom AutoNoteRuleSets from user_autonotes.json."""
    data = load_user_autonotes_data(filepath)
    raw_sets = data.get("custom_rule_sets", [])
    rule_sets = []

    for set_dict in raw_sets:
        if isinstance(set_dict, dict):
            rule_sets.append(compile_custom_rule_set(set_dict))

    return tuple(rule_sets)
