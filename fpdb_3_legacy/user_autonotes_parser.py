"""Declarative engine and parser for user-defined custom Auto Note rules."""

from __future__ import annotations

import json
import os
import re
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fpdb_3_legacy.AutoNotePlo import normalize_cards, rank_counts
from fpdb_3_legacy.AutoNoteRules import PreflopContext
from fpdb_3_legacy.AutoNotes import AutoNoteRule, AutoNoteRuleSet, GeneratedAutoNote
from fpdb_3_legacy.Configuration import CONFIG_PATH
from fpdb_3_legacy.loggingFpdb import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping

log = get_logger("user_autonotes_parser")

# How deep a hand-edited condition tree may nest before we stop descending.
# json.load itself caps nesting well below Python's recursion limit, but a rule
# file is user-editable and a runaway tree should degrade, not crash the import.
MAX_CONDITION_DEPTH = 32

# Only bare {tag} placeholders are substituted. Attribute access, indexing and
# format specs are left exactly as written instead of being evaluated, so a rule
# file that travels between users cannot reach into objects through a template
# such as "{player.__class__.__mro__}".
_TEMPLATE_TAG = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def render_note_template(template: str, values: Mapping[str, str]) -> str:
    """Substitute {tag} placeholders, leaving unknown ones visible as written."""
    return _TEMPLATE_TAG.sub(lambda m: values.get(m.group(1), m.group(0)), template)


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

        note_text = render_note_template(self.note_template, fmt_kwargs)

        return GeneratedAutoNote(
            player_id=player_id,
            hand_id=hand_id,
            rule_id=self.rule_id,
            rule_version=self.version,
            note_text=note_text,
            evidence=evidence,
        )


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
    depth: int = 0,
) -> bool:
    """Evaluate a nested logical condition tree.

    ``AND`` and ``OR`` behave as expected. ``NOT`` negates the disjunction of its
    operands -- ``NOT [a, b]`` is ``not (a or b)`` -- so with the single operand
    the editor produces it is a plain negation, and with several it reads as
    "none of these".

    An empty tree matches every hand; a tree nested past ``MAX_CONDITION_DEPTH``
    stops matching rather than exhausting the stack, since the file is
    hand-editable.
    """
    if not condition_tree:
        return True

    if depth > MAX_CONDITION_DEPTH:
        log.warning("Condition tree nested deeper than %d levels; refusing to descend", MAX_CONDITION_DEPTH)
        return False

    op = str(condition_tree.get("operator", "")).upper()
    rules = condition_tree.get("rules", [])

    if op == "AND":
        return all(evaluate_condition_tree(r, hand, player_name, context, depth + 1) for r in rules)
    if op == "OR":
        return any(evaluate_condition_tree(r, hand, player_name, context, depth + 1) for r in rules)
    if op == "NOT":
        return not any(evaluate_condition_tree(r, hand, player_name, context, depth + 1) for r in rules)

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


def compile_custom_rule(rule_dict: dict[str, Any]) -> AutoNoteRule:
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


def _supports_hand_for(games: tuple[str, ...]):
    """Build the game filter for a rule set from its declared ``games`` list.

    An empty list keeps the previous behaviour -- every hand matches -- because
    existing rule files carry no such key. Declaring games instead restricts the
    set, so a Hold'em rule stops firing on Stud or Omaha hands.
    """
    if not games:
        return lambda _h: True

    def supports_hand(hand: Any) -> bool:
        gametype = getattr(hand, "gametype", {}) or {}
        base = gametype.get("base") if isinstance(gametype, dict) else getattr(gametype, "base", None)
        base = str(base or "").lower()
        if base in ("hold", "holdem"):
            base = "holdem"
        return base in games

    return supports_hand


def compile_custom_rule_set(rule_set_dict: dict[str, Any]) -> AutoNoteRuleSet:
    """Compile declarative JSON rule set into an AutoNoteRuleSet instance.

    Rules whose ``rule_id`` repeats one already seen in the same set are dropped:
    generated notes are keyed by rule id, so duplicates would make a note
    impossible to attribute back to the rule that produced it.
    """
    rule_set_id = str(rule_set_dict.get("rule_set_id", "custom_user_rules"))
    raw_rules = rule_set_dict.get("rules", [])
    games = tuple(str(g).lower() for g in rule_set_dict.get("games", []) or ())

    compiled_rules = []
    seen_rule_ids: set[str] = set()
    for raw in raw_rules:
        if not isinstance(raw, dict):
            continue
        rule_id = str(raw.get("rule_id", "custom_rule"))
        if rule_id in seen_rule_ids:
            log.warning(
                "Rule set %r declares rule_id %r more than once; keeping the first and skipping the rest",
                rule_set_id,
                rule_id,
            )
            continue
        seen_rule_ids.add(rule_id)
        compiled_rules.append(compile_custom_rule(raw))

    return AutoNoteRuleSet(
        rule_set_id=rule_set_id,
        rules=tuple(compiled_rules),
        supports_hand=_supports_hand_for(games),
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
    """Save user autonotes data, replacing the file only once it is fully written.

    Writing in place would leave the user's whole rule collection truncated if
    the process died mid-write. Serialise to a sibling temporary file, flush it
    to disk, then rename over the target -- the rename is atomic, so a reader
    sees either the old file or the new one, never a partial one.
    """
    path = get_user_autonotes_path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    handle = tempfile.NamedTemporaryFile(  # noqa: SIM115 - closed explicitly below, before the rename
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    tmp_path = Path(handle.name)
    try:
        with handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    _RULE_SET_CACHE.pop(str(path), None)


# Compiled rule sets keyed by path, kept with the (mtime_ns, size) the file had
# when they were built. available_rule_sets() runs once per imported hand, so
# recompiling from disk every time put a stat, a parse and a full compile in the
# import hot path.
_RULE_SET_CACHE: dict[str, tuple[tuple[int, int] | None, tuple[AutoNoteRuleSet, ...]]] = {}


def _file_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def compile_custom_rule_sets(data: dict[str, Any]) -> tuple[AutoNoteRuleSet, ...]:
    """Compile every custom rule set in a loaded document, skipping duplicates.

    Two sets sharing a ``rule_set_id`` -- with each other or with a built-in set
    -- would make the enable/disable toggles ambiguous, since configuration keys
    on that id. The first one wins and the rest are reported.
    """
    from fpdb_3_legacy.AutoNotes import RULE_SET_REGISTRY

    builtin_ids = {rule_set.rule_set_id for rule_set in RULE_SET_REGISTRY}
    rule_sets: list[AutoNoteRuleSet] = []
    seen_ids: set[str] = set()

    for set_dict in data.get("custom_rule_sets", []):
        if not isinstance(set_dict, dict):
            continue
        rule_set_id = str(set_dict.get("rule_set_id", "custom_user_rules"))
        if rule_set_id in builtin_ids:
            log.warning("Custom rule set %r shadows a built-in rule set id; skipping it", rule_set_id)
            continue
        if rule_set_id in seen_ids:
            log.warning("Custom rule set id %r appears more than once; keeping the first", rule_set_id)
            continue
        seen_ids.add(rule_set_id)
        rule_sets.append(compile_custom_rule_set(set_dict))

    return tuple(rule_sets)


def load_custom_rule_sets(filepath: Path | str | None = None) -> tuple[AutoNoteRuleSet, ...]:
    """Load and compile custom AutoNoteRuleSets, reusing the last compile.

    The cache is keyed by path and invalidated when the file's mtime or size
    changes, so edits made by the editor -- or by hand, outside fpdb -- are still
    picked up on the next call.
    """
    path = get_user_autonotes_path(filepath)
    signature = _file_signature(path)

    cached = _RULE_SET_CACHE.get(str(path))
    if cached is not None and cached[0] == signature:
        return cached[1]

    rule_sets = compile_custom_rule_sets(load_user_autonotes_data(path))
    _RULE_SET_CACHE[str(path)] = (signature, rule_sets)
    return rule_sets


def invalidate_custom_rule_cache() -> None:
    """Drop every compiled rule set, forcing the next load to read from disk."""
    _RULE_SET_CACHE.clear()
