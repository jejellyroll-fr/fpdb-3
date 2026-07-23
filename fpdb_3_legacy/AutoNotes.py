"""Legacy automatic player note generation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Any

from fpdb_3_legacy.AutoNotePlo import (
    is_aaxx,
    is_non_aaxx,
    is_plo4,
    is_rainbow,
    is_single_paired_non_aaxx,
)
from fpdb_3_legacy.AutoNoteRules import PreflopContext

RULE_SET_HWANG_PLO_PREFLOP = "hwang_plo_preflop"
RULE_SET_HOLDEM_CASH_PREFLOP = "holdem_cash_preflop"
RULE_SET_TOURNAMENT_PUSH_FOLD = "tournament_push_fold"
RULE_SET_PLO_SPR_POSTFLOP = "plo_spr_postflop"
RULE_SET_FLOP_TEXTURE = "flop_texture"
RULE_SET_SHOWDOWN_QUALITY = "showdown_quality"
RULE_SET_HERO_RELATIVE = "hero_relative"
RULE_SET_RANGE_CAPTURE = "range_capture"
RULE_SET_STUD_DRAW_FIRST_STREET = "stud_draw_first_street"


@dataclass(frozen=True)
class GeneratedAutoNote:
    player_id: int
    hand_id: int
    rule_id: str
    rule_version: int
    note_text: str
    evidence: dict[str, Any]

    @property
    def idempotency_key(self) -> tuple[int, int, str, int]:
        return (self.player_id, self.hand_id, self.rule_id, self.rule_version)


@dataclass(frozen=True)
class AutoNoteRule:
    rule_id: str
    version: int
    name: str
    note_template: str
    predicate: Callable[[Any, str, PreflopContext], bool]
    evidence_builder: Callable[[Any, str, PreflopContext], dict[str, Any]]

    def evaluate(self, hand, player_name: str, context: PreflopContext) -> GeneratedAutoNote | None:
        player_ids = getattr(hand, "playerIds", {}) or {}
        hand_id = getattr(hand, "dbid_hands", None)
        player_id = player_ids.get(player_name)
        if not player_id or hand_id is None or not self.predicate(hand, player_name, context):
            return None
        return GeneratedAutoNote(
            player_id=player_id,
            hand_id=hand_id,
            rule_id=self.rule_id,
            rule_version=self.version,
            note_text=self.note_template.format(player=player_name),
            evidence=self.evidence_builder(hand, player_name, context),
        )


@dataclass(frozen=True)
class AutoNoteRuleSet:
    rule_set_id: str
    rules: tuple[AutoNoteRule, ...]
    supports_hand: Callable[[Any], bool]
    enabled_by_default: bool = True


def generate_for_hand(
    hand,
    rules: tuple[AutoNoteRule, ...] | None = None,
    config=None,
    rule_set_ids: set[str] | None = None,
    rule_ids: set[str] | None = None,
) -> list[GeneratedAutoNote]:
    if not autonotes_enabled(config):
        return []

    context = PreflopContext.from_hand(hand)
    selected_rule_sets = _rule_sets_for_hand(
        hand,
        rules,
        config,
        rule_set_ids=rule_set_ids,
        rule_ids=rule_ids,
    )
    notes: dict[tuple[int, int, str, int], GeneratedAutoNote] = {}
    for player in getattr(hand, "players", []) or []:
        if len(player) < 2:
            continue
        player_name = player[1]
        for rule_set in selected_rule_sets:
            for rule in rule_set.rules:
                note = rule.evaluate(hand, player_name, context)
                if note:
                    note = _apply_note_template_override(note, rule, rule_set.rule_set_id, config, player_name)
                    notes[note.idempotency_key] = note
    generated = list(notes.values())
    max_notes_per_player = max_auto_notes_per_player_per_hand(config)
    if max_notes_per_player is not None:
        generated = _limit_notes_per_player(generated, max_notes_per_player)
    max_notes = max_auto_notes_per_hand(config)
    if max_notes is None:
        return generated
    return generated[:max_notes]


def available_rule_sets() -> tuple[AutoNoteRuleSet, ...]:
    return RULE_SET_REGISTRY


def available_rule_set_ids() -> set[str]:
    return {rule_set.rule_set_id for rule_set in available_rule_sets()}


def available_rule_ids() -> set[str]:
    return {rule.rule_id for rule_set in available_rule_sets() for rule in rule_set.rules}


def available_rule_id_to_rule_set_id() -> dict[str, str]:
    return {rule.rule_id: rule_set.rule_set_id for rule_set in available_rule_sets() for rule in rule_set.rules}


def configured_rule_summary(
    config=None,
    rule_set_ids: set[str] | None = None,
    rule_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Return rule-set/rule enablement details for diagnostics and UI."""
    summary = []
    for rule_set in available_rule_sets():
        if rule_set_ids is not None and rule_set.rule_set_id not in rule_set_ids:
            continue
        rule_set_enabled_value = rule_set_enabled(
            config,
            rule_set.rule_set_id,
            default=rule_set.enabled_by_default,
        )
        rules = [rule for rule in rule_set.rules if rule_ids is None or rule.rule_id in rule_ids]
        if not rules:
            continue
        summary.append(
            {
                "ruleSet": rule_set.rule_set_id,
                "enabled": rule_set_enabled_value,
                "enabledByDefault": rule_set.enabled_by_default,
                "rules": [
                    {
                        "id": rule.rule_id,
                        "name": rule.name,
                        "version": rule.version,
                        "noteTemplate": rule.note_template,
                        "configuredNoteTemplate": rule_note_template(
                            config,
                            rule.rule_id,
                            rule_set.rule_set_id,
                            rule.note_template,
                        ),
                        "enabled": rule_set_enabled_value and rule_enabled(config, rule.rule_id, rule_set.rule_set_id),
                    }
                    for rule in rules
                ],
            },
        )
    return summary


def format_rule_summary(summary: list[dict[str, Any]]) -> str:
    """Format configured rule details for command-line display."""
    lines = []
    for rule_set in summary:
        status = "enabled" if rule_set["enabled"] else "disabled"
        default_status = "default on" if rule_set["enabledByDefault"] else "default off"
        lines.append(f"{rule_set['ruleSet']} [{status}, {default_status}]")
        for rule in rule_set["rules"]:
            rule_status = "on" if rule["enabled"] else "off"
            lines.append(f"  - {rule['id']} v{rule['version']} [{rule_status}] {rule['name']}")
    return "\n".join(lines)


def rule_manifest() -> dict[str, Any]:
    """Return a stable legacy autonote rule manifest for parity work."""
    return {
        "engine": "fpdb_3_legacy.autonotes",
        "schemaVersion": 1,
        "ruleSets": [
            {
                "id": rule_set.rule_set_id,
                "enabledByDefault": rule_set.enabled_by_default,
                "rules": [
                    {
                        "id": rule.rule_id,
                        "version": rule.version,
                        "name": rule.name,
                        "noteTemplate": rule.note_template,
                    }
                    for rule in rule_set.rules
                ],
            }
            for rule_set in available_rule_sets()
        ],
    }


def _rule_sets_for_hand(
    hand,
    rules: tuple[AutoNoteRule, ...] | None,
    config,
    rule_set_ids: set[str] | None = None,
    rule_ids: set[str] | None = None,
) -> tuple[AutoNoteRuleSet, ...]:
    if rules is not None:
        enabled_rules = tuple(
            rule
            for rule in rules
            if (rule_ids is None or rule.rule_id in rule_ids) and rule_enabled(config, rule.rule_id)
        )
        return (AutoNoteRuleSet("custom", enabled_rules, lambda _h: True),)

    selected = []
    for rule_set in RULE_SET_REGISTRY:
        if rule_set_ids is not None and rule_set.rule_set_id not in rule_set_ids:
            continue
        if not rule_set.supports_hand(hand) or not rule_set_enabled(
            config,
            rule_set.rule_set_id,
            default=rule_set.enabled_by_default,
        ):
            continue
        enabled_rules = tuple(
            rule
            for rule in rule_set.rules
            if (rule_ids is None or rule.rule_id in rule_ids)
            and rule_enabled(config, rule.rule_id, rule_set.rule_set_id)
        )
        if enabled_rules:
            selected.append(
                AutoNoteRuleSet(rule_set.rule_set_id, enabled_rules, rule_set.supports_hand),
            )
    return tuple(selected)


def autonotes_enabled(config=None) -> bool:
    node = _autonotes_node(config)
    if node is None:
        return True
    return _string_to_bool(node.getAttribute("enabled"), default=True)


def max_auto_notes_per_hand(config=None) -> int | None:
    return _autonote_int_attribute(config, "maxPerHand")


def max_auto_notes_per_player_per_hand(config=None) -> int | None:
    return _autonote_int_attribute(config, "maxPerPlayerPerHand")


def set_autonotes_enabled(config, enabled: bool) -> None:
    """Set the global automatic-note switch in the XML config."""
    node = ensure_autonotes_node(config)
    node.setAttribute("enabled", _bool_to_string(enabled))


def set_rule_set_enabled(config, rule_set_name: str, enabled: bool) -> None:
    """Set one automatic-note rule-set switch in the XML config."""
    rule_set_node = ensure_rule_set_node(config, rule_set_name)
    rule_set_node.setAttribute("enabled", _bool_to_string(enabled))


def set_rule_enabled(
    config,
    rule_id: str,
    enabled: bool,
    rule_set_name: str = RULE_SET_HWANG_PLO_PREFLOP,
) -> None:
    """Set one automatic-note rule switch in the XML config."""
    rule_node = ensure_rule_node(config, rule_set_name, rule_id)
    rule_node.setAttribute("enabled", _bool_to_string(enabled))


def set_rule_note_template(
    config,
    rule_id: str,
    note_template: str,
    rule_set_name: str = RULE_SET_HWANG_PLO_PREFLOP,
) -> None:
    """Set one automatic-note rule text template in the XML config."""
    rule_node = ensure_rule_node(config, rule_set_name, rule_id)
    rule_node.setAttribute("noteTemplate", note_template)


def rule_note_template(
    config,
    rule_id: str,
    rule_set_name: str = RULE_SET_HWANG_PLO_PREFLOP,
    default: str = "",
) -> str:
    """Return a configured note template for one rule, falling back to default."""
    node = _autonotes_node(config)
    if node is None:
        return default
    for rule_set_node in node.getElementsByTagName("ruleset"):
        if rule_set_node.getAttribute("name") != rule_set_name:
            continue
        for rule_node in rule_set_node.getElementsByTagName("rule"):
            if rule_node.getAttribute("id") == rule_id:
                return rule_node.getAttribute("noteTemplate") or default
    return default


def ensure_autonotes_node(config):
    """Return the config autonotes node, creating it when absent."""
    doc = getattr(config, "doc", None)
    if doc is None:
        msg = "config must expose a minidom document as .doc"
        raise ValueError(msg)

    node = _autonotes_node(config)
    if node is not None:
        return node

    root = doc.documentElement
    if root is None:
        root = doc.createElement("FreePokerToolsConfig")
        doc.appendChild(root)
    node = doc.createElement("autonotes")
    root.appendChild(node)
    return node


def ensure_rule_set_node(config, rule_set_name: str):
    """Return a rule-set config node, creating it when absent."""
    node = ensure_autonotes_node(config)
    for rule_set_node in node.getElementsByTagName("ruleset"):
        if rule_set_node.getAttribute("name") == rule_set_name:
            return rule_set_node

    rule_set_node = config.doc.createElement("ruleset")
    rule_set_node.setAttribute("name", rule_set_name)
    node.appendChild(rule_set_node)
    return rule_set_node


def ensure_rule_node(config, rule_set_name: str, rule_id: str):
    """Return a rule config node, creating it under its rule set when absent."""
    rule_set_node = ensure_rule_set_node(config, rule_set_name)
    for rule_node in rule_set_node.getElementsByTagName("rule"):
        if rule_node.getAttribute("id") == rule_id:
            return rule_node

    rule_node = config.doc.createElement("rule")
    rule_node.setAttribute("id", rule_id)
    rule_set_node.appendChild(rule_node)
    return rule_node


def _autonote_int_attribute(config, attribute_name: str) -> int | None:
    node = _autonotes_node(config)
    if node is None:
        return None
    value = node.getAttribute(attribute_name)
    if value == "":
        return None
    try:
        limit = int(value)
    except ValueError:
        return None
    return max(0, limit)


def _limit_notes_per_player(notes: list[GeneratedAutoNote], max_notes_per_player: int) -> list[GeneratedAutoNote]:
    counts: dict[int, int] = {}
    selected = []
    for note in notes:
        count = counts.get(note.player_id, 0)
        if count >= max_notes_per_player:
            continue
        selected.append(note)
        counts[note.player_id] = count + 1
    return selected


def _apply_note_template_override(
    note: GeneratedAutoNote,
    rule: AutoNoteRule,
    rule_set_id: str,
    config,
    player_name: str,
) -> GeneratedAutoNote:
    template = rule_note_template(config, rule.rule_id, rule_set_id, rule.note_template)
    if template == rule.note_template:
        return note
    try:
        return replace(note, note_text=template.format(player=player_name))
    except (IndexError, KeyError, ValueError):
        return note


def rule_set_enabled(config, rule_set_name: str, default: bool = True) -> bool:
    node = _autonotes_node(config)
    if node is None:
        return default
    for rule_set_node in node.getElementsByTagName("ruleset"):
        if rule_set_node.getAttribute("name") == rule_set_name:
            return _string_to_bool(rule_set_node.getAttribute("enabled"), default=True)
    return default


def rule_enabled(config, rule_id: str, rule_set_name: str = RULE_SET_HWANG_PLO_PREFLOP) -> bool:
    node = _autonotes_node(config)
    if node is None:
        return True

    for rule_set_node in node.getElementsByTagName("ruleset"):
        if rule_set_node.getAttribute("name") != rule_set_name:
            continue
        for rule_node in rule_set_node.getElementsByTagName("rule"):
            if rule_node.getAttribute("id") == rule_id:
                return _string_to_bool(rule_node.getAttribute("enabled"), default=True)

    for child in node.childNodes:
        if getattr(child, "tagName", None) == "rule" and child.getAttribute("id") == rule_id:
            return _string_to_bool(child.getAttribute("enabled"), default=True)
    return True


def _autonotes_node(config):
    doc = getattr(config, "doc", None)
    if doc is None:
        return None
    nodes = doc.getElementsByTagName("autonotes")
    return nodes[0] if nodes else None


def _string_to_bool(value: str, default=True) -> bool:
    value = (value or "").lower()
    if value in {"1", "true", "t", "yes", "y"}:
        return True
    if value in {"0", "false", "f", "no", "n"}:
        return False
    return default


def _bool_to_string(enabled: bool) -> str:
    return "True" if enabled else "False"


def format_generated_notes(
    notes: list[dict],
    limit: int | None = None,
    include_summary: bool = True,
    rule_set_ids: set[str] | None = None,
    rule_ids: set[str] | None = None,
) -> str:
    """Format generated notes for read-only UI display."""
    filtered_notes = filter_generated_notes(notes, rule_set_ids=rule_set_ids, rule_ids=rule_ids)
    selected = filtered_notes if limit is None else filtered_notes[: max(0, int(limit))]
    sections = []
    if include_summary and filtered_notes:
        summary_lines = ["Summary"]
        rule_set_summary = summarize_generated_notes_by_rule_set(filtered_notes)
        if rule_set_summary:
            summary_lines.append("Rule sets")
            summary_lines.extend(f"- {item['ruleSet']}: {item['count']}" for item in rule_set_summary)
        summary = summarize_generated_notes(filtered_notes)
        summary_lines.append("Rules")
        summary_lines.extend(f"- {item['ruleId']}: {item['count']}" for item in summary)
        sections.append("\n".join(summary_lines))

    for note in selected:
        rule = note.get("ruleId", "unknown")
        rule_set = _note_rule_set_id(note)
        version = note.get("ruleVersion", 1)
        hand_id = note.get("handId", "")
        created = note.get("createdTs") or ""
        text = note.get("noteText", "")
        header = f"[{rule_set}:{rule} v{version}] hand {hand_id}"
        if created:
            header = f"{header} - {created}"
        evidence = format_note_evidence(note.get("evidence", {}))
        body = f"{text}\nEvidence: {evidence}" if evidence else text
        sections.append(f"{header}\n{body}")
    return "\n\n".join(sections)


def filter_generated_notes(
    notes: list[dict],
    rule_set_ids: set[str] | None = None,
    rule_ids: set[str] | None = None,
) -> list[dict]:
    """Filter generated note rows by rule set and/or rule id, preserving order."""
    if rule_set_ids is None and rule_ids is None:
        return list(notes)

    selected = []
    for note in notes:
        rule_id = note.get("ruleId")
        rule_set_id = _note_rule_set_id(note)
        if rule_set_ids is not None and rule_set_id not in rule_set_ids:
            continue
        if rule_ids is not None and rule_id not in rule_ids:
            continue
        selected.append(note)
    return selected


def format_note_evidence(evidence: dict[str, Any]) -> str:
    """Format a generated note's evidence as compact key=value pairs."""
    if not evidence:
        return ""

    preferred_keys = [
        "hole_cards",
        "position",
        "street",
        "board",
        "texture",
        "spr",
        "action",
        "all_in",
        "hero",
        "villain",
        "hero_action",
        "villain_action",
        "range_hand",
        "range_action",
        "raise_number",
        "door_card",
        "draw_hand",
        "mixed_action",
        "variant",
        "preflop_aggressor",
        "hand_class",
        "final_pot_bb",
        "showdown_winnings",
        "won_at_showdown",
        "preflop_raises",
        "three_bettor",
        "game",
        "base",
        "site_hand_no",
    ]
    ordered_keys = [key for key in preferred_keys if key in evidence]
    ordered_keys.extend(sorted(key for key in evidence if key not in preferred_keys))

    parts = []
    for key in ordered_keys:
        value = evidence.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, list):
            value = " > ".join(str(item) for item in value)
        parts.append(f"{key}={value}")
    return "; ".join(parts)


def summarize_generated_notes(notes: list[dict]) -> list[dict]:
    """Return counts by generated-note rule, sorted by count then rule id."""
    counts: dict[str, int] = {}
    for note in notes:
        rule_id = note.get("ruleId", "unknown")
        counts[rule_id] = counts.get(rule_id, 0) + 1
    return [
        {"ruleId": rule_id, "count": count}
        for rule_id, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def summarize_generated_notes_by_rule_set(notes: list[dict]) -> list[dict]:
    """Return counts by generated-note rule set, sorted by count then rule set id."""
    counts: dict[str, int] = {}
    for note in notes:
        rule_set_id = _note_rule_set_id(note)
        counts[rule_set_id] = counts.get(rule_set_id, 0) + 1
    return [
        {"ruleSet": rule_set_id, "count": count}
        for rule_set_id, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _note_rule_set_id(note: dict) -> str:
    rule_set_id = note.get("ruleSet")
    if isinstance(rule_set_id, str) and rule_set_id:
        return rule_set_id

    rule_id = note.get("ruleId")
    if not isinstance(rule_id, str):
        return "unknown"
    return available_rule_id_to_rule_set_id().get(rule_id, "unknown")


def _cards(context: PreflopContext, player: str) -> list[str]:
    return context.hole_cards.get(player, [])


def _plo_legacy_cards(context: PreflopContext, player: str) -> list[str]:
    return _cards(context, player)[:4]


def _is_holdem_cash(hand) -> bool:
    gametype = getattr(hand, "gametype", {}) or {}
    return (
        str(gametype.get("base", "")).lower() == "hold"
        and str(gametype.get("category", "")).lower() in {"holdem", "holdemhilo"}
        and str(gametype.get("type", "")).lower() not in {"tour", "tournament"}
    )


def _is_holdem_tournament(hand) -> bool:
    gametype = getattr(hand, "gametype", {}) or {}
    return (
        str(gametype.get("base", "")).lower() == "hold"
        and str(gametype.get("category", "")).lower() in {"holdem", "holdemhilo"}
        and (
            str(gametype.get("type", "")).lower() in {"tour", "tournament"}
            or bool(getattr(hand, "tourNo", None))
            or bool(getattr(hand, "isSng", False))
        )
    )


def _is_flop_game(hand) -> bool:
    gametype = getattr(hand, "gametype", {}) or {}
    return str(gametype.get("base", "")).lower() == "hold" and str(
        gametype.get("category", ""),
    ).lower() in {
        "holdem",
        "holdemhilo",
        "omahahi",
        "omahahilo",
        "5_omahahi",
    }


def _is_stud_game(hand) -> bool:
    gametype = getattr(hand, "gametype", {}) or {}
    category = str(gametype.get("category", "")).lower()
    return str(gametype.get("base", "")).lower() == "stud" or category in {
        "5_studhi",
        "27_razz",
        "razz",
        "studhi",
        "studhilo",
    }


def _is_draw_game(hand) -> bool:
    gametype = getattr(hand, "gametype", {}) or {}
    category = str(gametype.get("category", "")).lower()
    return str(gametype.get("base", "")).lower() == "draw" or category in {
        "27_1draw",
        "27_3draw",
        "a5_1draw",
        "a5_3draw",
        "badugi",
        "baduci",
        "badeucey",
        "drawmaha",
        "fivedraw",
    }


def _is_stud_or_draw_game(hand) -> bool:
    return _is_stud_game(hand) or _is_draw_game(hand)


def _to_decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _big_blind(hand) -> Decimal | None:
    gametype = getattr(hand, "gametype", {}) or {}
    for value in (gametype.get("bigBlind"), gametype.get("bb"), getattr(hand, "bb", None)):
        decimal_value = _to_decimal(value)
        if decimal_value and decimal_value > 0:
            return decimal_value
    return None


def _final_pot(hand) -> Decimal | None:
    hand_stats = getattr(hand, "hands", {}) or {}
    for value in (
        hand_stats.get("finalPot"),
        getattr(hand, "finalPot", None),
        getattr(hand, "totalpot", None),
        getattr(hand, "totalPot", None),
    ):
        decimal_value = _to_decimal(value)
        if decimal_value and decimal_value > 0:
            return decimal_value
    return None


def _final_pot_bb(hand) -> Decimal | None:
    pot = _final_pot(hand)
    big_blind = _big_blind(hand)
    if not pot or not big_blind:
        return None
    return pot / big_blind


def _player_start_stack(hand, player: str, context: PreflopContext) -> Decimal | None:
    stats = context.handsplayers.get(player, {})
    for value in (stats.get("startCash"), stats.get("effStack")):
        decimal_value = _to_decimal(value)
        if decimal_value and decimal_value > 0:
            return decimal_value

    for row in getattr(hand, "players", []) or []:
        if len(row) >= 3 and row[1] == player:
            decimal_value = _to_decimal(row[2])
            if decimal_value and decimal_value > 0:
                return decimal_value
    return None


def _player_stack_bb(hand, player: str, context: PreflopContext) -> Decimal | None:
    stack = _player_start_stack(hand, player, context)
    big_blind = _big_blind(hand)
    if not stack or not big_blind:
        return None
    return stack / big_blind


def _base_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    gametype = getattr(hand, "gametype", {}) or {}
    return {
        "site_hand_no": getattr(hand, "handid", None),
        "game": gametype.get("category"),
        "base": gametype.get("base"),
        "hole_cards": " ".join(_cards(context, player)),
        "position": context.positions.get(player),
    }


def _raise_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    evidence = _base_evidence(hand, player, context)
    evidence["preflop_raises"] = [action.player for action in context.raises]
    return evidence


def _fold_to_3bet_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    evidence = _raise_evidence(hand, player, context)
    evidence["three_bettor"] = context.second_raise.player if context.second_raise else None
    return evidence


def _holdem_preflop_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    evidence = _raise_evidence(hand, player, context)
    evidence["first_raiser"] = context.first_raise.player if context.first_raise else None
    evidence["preflop_actions"] = [
        f"{action.player}:{action.action}" for action in context.actions if action.player == player or action.is_raise
    ]
    return evidence


def _tournament_preflop_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    evidence = _holdem_preflop_evidence(hand, player, context)
    stack_bb = _player_stack_bb(hand, player, context)
    evidence["stack_bb"] = float(round(stack_bb, 2)) if stack_bb is not None else None
    evidence["big_blind"] = _big_blind(hand)
    evidence["is_sng"] = bool(getattr(hand, "isSng", False))
    return evidence


PLO_SPR_STREETS = (
    ("FLOP", "cnt_f_spr", "val_f_spr"),
    ("TURN", "cnt_t_spr", "val_t_spr"),
    ("RIVER", "cnt_r_spr", "val_r_spr"),
)
PLO_SPR_AGGRESSIVE_ACTIONS = {"bets", "raises", "completes"}
RANK_VALUES = {
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "T": 10,
    "J": 11,
    "Q": 12,
    "K": 13,
    "A": 14,
}


def _street_actions(hand, street: str) -> list[tuple]:
    return list((getattr(hand, "actions", {}) or {}).get(street, []))


def _board_cards(hand, street: str = "FLOP") -> list[str]:
    board = getattr(hand, "board", {}) or {}
    return [str(card) for card in board.get(street, []) if str(card) and str(card) != "0x"][:3]


def _flop_texture(hand) -> dict[str, Any] | None:
    cards = _board_cards(hand)
    if len(cards) < 3:
        return None

    ranks = [card[0].upper() for card in cards if len(card) >= 2]
    suits = [card[-1].lower() for card in cards if len(card) >= 2]
    if len(ranks) < 3 or len(suits) < 3:
        return None

    rank_counts = {rank: ranks.count(rank) for rank in set(ranks)}
    suit_counts = {suit: suits.count(suit) for suit in set(suits)}
    values = sorted({RANK_VALUES.get(rank, 0) for rank in ranks if RANK_VALUES.get(rank, 0)})
    wheel_values = sorted({1 if value == 14 else value for value in values})
    connected = bool(
        len(values) >= 3 and (max(values) - min(values) <= 4 or max(wheel_values) - min(wheel_values) <= 4),
    )
    paired = max(rank_counts.values()) >= 2
    monotone = max(suit_counts.values()) == 3
    two_tone = max(suit_counts.values()) == 2
    wet = bool(monotone or two_tone or connected)

    labels = []
    if paired:
        labels.append("paired")
    if monotone:
        labels.append("monotone")
    elif two_tone:
        labels.append("two-tone")
    if connected:
        labels.append("connected")
    if not labels:
        labels.append("dry")

    return {
        "board": " ".join(cards),
        "paired": paired,
        "monotone": monotone,
        "two_tone": two_tone,
        "connected": connected,
        "wet": wet,
        "label": ", ".join(labels),
    }


def _raw_action_is_allin(raw: tuple) -> bool:
    return bool(raw and isinstance(raw[-1], bool) and raw[-1])


def _spr_for_street(context: PreflopContext, player: str, cnt_key: str, val_key: str) -> Decimal | None:
    stats = context.handsplayers.get(player, {})
    if not stats.get(cnt_key):
        return None
    spr = _to_decimal(stats.get(val_key))
    if spr is None:
        return None
    return spr / Decimal("100")


def _first_postflop_spr_match(
    hand,
    player: str,
    context: PreflopContext,
    action_predicate: Callable[[tuple], bool],
) -> dict[str, Any] | None:
    for street, cnt_key, val_key in PLO_SPR_STREETS:
        spr = _spr_for_street(context, player, cnt_key, val_key)
        if spr is None or spr > Decimal("1"):
            continue
        for raw in _street_actions(hand, street):
            if len(raw) < 2 or raw[0] != player or not action_predicate(raw):
                continue
            return {
                "street": street,
                "spr": spr,
                "action": raw[1],
                "all_in": _raw_action_is_allin(raw),
            }
    return None


def _low_spr_fold_match(hand, player: str, context: PreflopContext) -> dict[str, Any] | None:
    return _first_postflop_spr_match(
        hand,
        player,
        context,
        lambda raw: raw[1] == "folds",
    )


def _low_spr_aggressive_allin_match(hand, player: str, context: PreflopContext) -> dict[str, Any] | None:
    return _first_postflop_spr_match(
        hand,
        player,
        context,
        lambda raw: raw[1] in PLO_SPR_AGGRESSIVE_ACTIONS and _raw_action_is_allin(raw),
    )


def _low_spr_call_allin_match(hand, player: str, context: PreflopContext) -> dict[str, Any] | None:
    return _first_postflop_spr_match(
        hand,
        player,
        context,
        lambda raw: raw[1] == "calls" and _raw_action_is_allin(raw),
    )


def _folds_low_spr_postflop(hand, player: str, context: PreflopContext) -> bool:
    return _low_spr_fold_match(hand, player, context) is not None


def _aggressive_allin_low_spr_postflop(hand, player: str, context: PreflopContext) -> bool:
    return _low_spr_aggressive_allin_match(hand, player, context) is not None


def _calls_allin_low_spr_postflop(hand, player: str, context: PreflopContext) -> bool:
    return _low_spr_call_allin_match(hand, player, context) is not None


def _postflop_spr_evidence(
    hand,
    player: str,
    context: PreflopContext,
    matcher: Callable[[Any, str, PreflopContext], dict[str, Any] | None],
) -> dict[str, Any]:
    evidence = _base_evidence(hand, player, context)
    match = matcher(hand, player, context)
    if match:
        evidence["street"] = match["street"]
        evidence["spr"] = float(round(match["spr"], 2))
        evidence["action"] = match["action"]
        evidence["all_in"] = match["all_in"]
    return evidence


def _low_spr_fold_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    return _postflop_spr_evidence(hand, player, context, _low_spr_fold_match)


def _low_spr_aggressive_allin_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    return _postflop_spr_evidence(hand, player, context, _low_spr_aggressive_allin_match)


def _low_spr_call_allin_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    return _postflop_spr_evidence(hand, player, context, _low_spr_call_allin_match)


def _preflop_aggressor(context: PreflopContext) -> str | None:
    return context.raises[-1].player if context.raises else None


def _first_flop_bet(actions: list[tuple]) -> tuple | None:
    return next((raw for raw in actions if len(raw) >= 2 and raw[1] == "bets"), None)


def _flop_texture_action_match(
    hand,
    player: str,
    context: PreflopContext,
    matcher: Callable[[list[tuple], str | None, dict[str, Any]], dict[str, Any] | None],
) -> dict[str, Any] | None:
    texture = _flop_texture(hand)
    if not texture:
        return None
    return matcher(_street_actions(hand, "FLOP"), _preflop_aggressor(context), texture)


def _donks_wet_flop_match(hand, player: str, context: PreflopContext) -> dict[str, Any] | None:
    def matcher(actions: list[tuple], aggressor: str | None, texture: dict[str, Any]) -> dict[str, Any] | None:
        first_bet = _first_flop_bet(actions)
        if not aggressor or not first_bet or first_bet[0] != player or player == aggressor or not texture["wet"]:
            return None
        return {"action": "bets", "preflop_aggressor": aggressor, **texture}

    return _flop_texture_action_match(hand, player, context, matcher)


def _raises_cbet_wet_flop_match(hand, player: str, context: PreflopContext) -> dict[str, Any] | None:
    def matcher(actions: list[tuple], aggressor: str | None, texture: dict[str, Any]) -> dict[str, Any] | None:
        first_bet = _first_flop_bet(actions)
        if not aggressor or not first_bet or first_bet[0] != aggressor or not texture["wet"]:
            return None
        return next(
            (
                {"action": "raises", "preflop_aggressor": aggressor, **texture}
                for raw in actions
                if len(raw) >= 2 and raw[0] == player and raw[1] == "raises"
            ),
            None,
        )

    return _flop_texture_action_match(hand, player, context, matcher)


def _calls_cbet_paired_flop_match(hand, player: str, context: PreflopContext) -> dict[str, Any] | None:
    def matcher(actions: list[tuple], aggressor: str | None, texture: dict[str, Any]) -> dict[str, Any] | None:
        first_bet = _first_flop_bet(actions)
        if not aggressor or not first_bet or first_bet[0] != aggressor or not texture["paired"]:
            return None
        return next(
            (
                {"action": "calls", "preflop_aggressor": aggressor, **texture}
                for raw in actions
                if len(raw) >= 2 and raw[0] == player and raw[1] == "calls"
            ),
            None,
        )

    return _flop_texture_action_match(hand, player, context, matcher)


def _donks_wet_flop(hand, player: str, context: PreflopContext) -> bool:
    return _donks_wet_flop_match(hand, player, context) is not None


def _raises_cbet_wet_flop(hand, player: str, context: PreflopContext) -> bool:
    return _raises_cbet_wet_flop_match(hand, player, context) is not None


def _calls_cbet_paired_flop(hand, player: str, context: PreflopContext) -> bool:
    return _calls_cbet_paired_flop_match(hand, player, context) is not None


def _flop_texture_evidence(
    hand,
    player: str,
    context: PreflopContext,
    matcher: Callable[[Any, str, PreflopContext], dict[str, Any] | None],
) -> dict[str, Any]:
    evidence = _base_evidence(hand, player, context)
    match = matcher(hand, player, context)
    if match:
        evidence["street"] = "FLOP"
        evidence["board"] = match["board"]
        evidence["texture"] = match["label"]
        evidence["action"] = match["action"]
        evidence["preflop_aggressor"] = match["preflop_aggressor"]
    return evidence


def _donks_wet_flop_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    return _flop_texture_evidence(hand, player, context, _donks_wet_flop_match)


def _raises_cbet_wet_flop_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    return _flop_texture_evidence(hand, player, context, _raises_cbet_wet_flop_match)


def _calls_cbet_paired_flop_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    return _flop_texture_evidence(hand, player, context, _calls_cbet_paired_flop_match)


WEAK_SHOWDOWN_MARKERS = ("high card", "one pair", "a pair")
NON_NUT_FLUSH_EXCLUSIONS = ("ace high", "king high")
MEDIUM_POT_BB = Decimal("20")


def _showdown_stats(context: PreflopContext, player: str) -> dict[str, Any]:
    return context.handsplayers.get(player, {})


def _hand_string(context: PreflopContext, player: str) -> str:
    return str(_showdown_stats(context, player).get("handString") or "").strip()


def _saw_showdown(context: PreflopContext, player: str) -> bool:
    return bool(_showdown_stats(context, player).get("sawShowdown"))


def _won_at_showdown(context: PreflopContext, player: str) -> bool | None:
    stats = _showdown_stats(context, player)
    if "wonAtSD" in stats:
        return bool(stats.get("wonAtSD"))
    winnings = _to_decimal(stats.get("showdownWinnings"))
    if winnings is None:
        return None
    return winnings > 0


def _lost_showdown(context: PreflopContext, player: str) -> bool:
    won = _won_at_showdown(context, player)
    if won is not None:
        return not won
    winnings = _to_decimal(_showdown_stats(context, player).get("showdownWinnings"))
    return bool(winnings is not None and winnings < 0)


def _weak_showdown_hand(context: PreflopContext, player: str) -> bool:
    hand_string = _hand_string(context, player).lower()
    return any(marker in hand_string for marker in WEAK_SHOWDOWN_MARKERS)


def _non_nut_flush_showdown_hand(context: PreflopContext, player: str) -> bool:
    hand_string = _hand_string(context, player).lower()
    return (
        "flush" in hand_string
        and "straight flush" not in hand_string
        and not any(marker in hand_string for marker in NON_NUT_FLUSH_EXCLUSIONS)
    )


def _medium_or_larger_pot(hand) -> bool:
    pot_bb = _final_pot_bb(hand)
    return bool(pot_bb is not None and pot_bb >= MEDIUM_POT_BB)


def _river_call_match(hand, player: str) -> dict[str, Any] | None:
    return next(
        (
            {"street": "RIVER", "action": "calls"}
            for raw in _street_actions(hand, "RIVER")
            if len(raw) >= 2 and raw[0] == player and raw[1] == "calls"
        ),
        None,
    )


def _weak_lost_showdown_match(hand, player: str, context: PreflopContext) -> dict[str, Any] | None:
    if (
        not _saw_showdown(context, player)
        or not _lost_showdown(context, player)
        or not _weak_showdown_hand(context, player)
        or not _medium_or_larger_pot(hand)
    ):
        return None
    return {"street": "SHOWDOWN", "action": "showed"}


def _river_call_weak_lost_showdown_match(hand, player: str, context: PreflopContext) -> dict[str, Any] | None:
    river_call = _river_call_match(hand, player)
    if not river_call or not _weak_lost_showdown_match(hand, player, context):
        return None
    return river_call


def _non_nut_flush_showdown_match(hand, player: str, context: PreflopContext) -> dict[str, Any] | None:
    if (
        not _saw_showdown(context, player)
        or not _non_nut_flush_showdown_hand(context, player)
        or not _medium_or_larger_pot(hand)
    ):
        return None
    return {"street": "SHOWDOWN", "action": "showed"}


def _weak_lost_showdown(hand, player: str, context: PreflopContext) -> bool:
    return _weak_lost_showdown_match(hand, player, context) is not None


def _river_call_weak_lost_showdown(hand, player: str, context: PreflopContext) -> bool:
    return _river_call_weak_lost_showdown_match(hand, player, context) is not None


def _non_nut_flush_showdown(hand, player: str, context: PreflopContext) -> bool:
    return _non_nut_flush_showdown_match(hand, player, context) is not None


def _showdown_quality_evidence(
    hand,
    player: str,
    context: PreflopContext,
    matcher: Callable[[Any, str, PreflopContext], dict[str, Any] | None],
) -> dict[str, Any]:
    evidence = _base_evidence(hand, player, context)
    stats = _showdown_stats(context, player)
    match = matcher(hand, player, context)
    if match:
        evidence["street"] = match["street"]
        evidence["action"] = match["action"]
    evidence["hand_class"] = _hand_string(context, player)
    pot_bb = _final_pot_bb(hand)
    evidence["final_pot_bb"] = float(round(pot_bb, 2)) if pot_bb is not None else None
    evidence["showdown_winnings"] = stats.get("showdownWinnings")
    evidence["won_at_showdown"] = _won_at_showdown(context, player)
    return evidence


def _weak_lost_showdown_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    return _showdown_quality_evidence(hand, player, context, _weak_lost_showdown_match)


def _river_call_weak_lost_showdown_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    return _showdown_quality_evidence(hand, player, context, _river_call_weak_lost_showdown_match)


def _non_nut_flush_showdown_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    return _showdown_quality_evidence(hand, player, context, _non_nut_flush_showdown_match)


def _hero_name(hand) -> str | None:
    hero = getattr(hand, "hero", None)
    if hero:
        return str(hero)
    return None


def _hero_relative_action_match(
    hand,
    player: str,
    context: PreflopContext,
    matcher: Callable[[str, str, PreflopContext], dict[str, Any] | None],
) -> dict[str, Any] | None:
    hero = _hero_name(hand)
    if not hero or player == hero:
        return None
    return matcher(hero, player, context)


def _villain_three_bets_hero_match(hand, player: str, context: PreflopContext) -> dict[str, Any] | None:
    def matcher(hero: str, villain: str, ctx: PreflopContext) -> dict[str, Any] | None:
        if (
            ctx.first_raise
            and ctx.second_raise
            and ctx.first_raise.player == hero
            and ctx.second_raise.player == villain
        ):
            return {
                "hero": hero,
                "villain": villain,
                "hero_action": "raises",
                "villain_action": "3bets",
            }
        return None

    return _hero_relative_action_match(hand, player, context, matcher)


def _villain_four_bets_hero_match(hand, player: str, context: PreflopContext) -> dict[str, Any] | None:
    def matcher(hero: str, villain: str, ctx: PreflopContext) -> dict[str, Any] | None:
        if (
            ctx.second_raise
            and ctx.third_raise
            and ctx.second_raise.player == hero
            and ctx.third_raise.player == villain
        ):
            return {
                "hero": hero,
                "villain": villain,
                "hero_action": "3bets",
                "villain_action": "4bets",
            }
        return None

    return _hero_relative_action_match(hand, player, context, matcher)


def _villain_folds_to_hero_three_bet_match(hand, player: str, context: PreflopContext) -> dict[str, Any] | None:
    def matcher(hero: str, villain: str, ctx: PreflopContext) -> dict[str, Any] | None:
        if not ctx.first_raise or not ctx.second_raise:
            return None
        if ctx.first_raise.player != villain or ctx.second_raise.player != hero:
            return None
        if any(
            action.index > ctx.second_raise.index and action.is_fold for action in ctx.player_actions.get(villain, [])
        ):
            return {
                "hero": hero,
                "villain": villain,
                "hero_action": "3bets",
                "villain_action": "folds",
            }
        return None

    return _hero_relative_action_match(hand, player, context, matcher)


def _villain_folds_to_hero_four_bet_match(hand, player: str, context: PreflopContext) -> dict[str, Any] | None:
    def matcher(hero: str, villain: str, ctx: PreflopContext) -> dict[str, Any] | None:
        if not ctx.second_raise or not ctx.third_raise:
            return None
        if ctx.second_raise.player != villain or ctx.third_raise.player != hero:
            return None
        if any(
            action.index > ctx.third_raise.index and action.is_fold for action in ctx.player_actions.get(villain, [])
        ):
            return {
                "hero": hero,
                "villain": villain,
                "hero_action": "4bets",
                "villain_action": "folds",
            }
        return None

    return _hero_relative_action_match(hand, player, context, matcher)


def _villain_three_bets_hero(hand, player: str, context: PreflopContext) -> bool:
    return _villain_three_bets_hero_match(hand, player, context) is not None


def _villain_four_bets_hero(hand, player: str, context: PreflopContext) -> bool:
    return _villain_four_bets_hero_match(hand, player, context) is not None


def _villain_folds_to_hero_three_bet(hand, player: str, context: PreflopContext) -> bool:
    return _villain_folds_to_hero_three_bet_match(hand, player, context) is not None


def _villain_folds_to_hero_four_bet(hand, player: str, context: PreflopContext) -> bool:
    return _villain_folds_to_hero_four_bet_match(hand, player, context) is not None


def _hero_relative_evidence(
    hand,
    player: str,
    context: PreflopContext,
    matcher: Callable[[Any, str, PreflopContext], dict[str, Any] | None],
) -> dict[str, Any]:
    evidence = _raise_evidence(hand, player, context)
    match = matcher(hand, player, context)
    if match:
        evidence["street"] = "PREFLOP"
        evidence["hero"] = match["hero"]
        evidence["villain"] = match["villain"]
        evidence["hero_action"] = match["hero_action"]
        evidence["villain_action"] = match["villain_action"]
    return evidence


def _villain_three_bets_hero_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    return _hero_relative_evidence(hand, player, context, _villain_three_bets_hero_match)


def _villain_four_bets_hero_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    return _hero_relative_evidence(hand, player, context, _villain_four_bets_hero_match)


def _villain_folds_to_hero_three_bet_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    return _hero_relative_evidence(hand, player, context, _villain_folds_to_hero_three_bet_match)


def _villain_folds_to_hero_four_bet_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    return _hero_relative_evidence(hand, player, context, _villain_folds_to_hero_four_bet_match)


def _visible_range_cards(context: PreflopContext, player: str) -> list[str]:
    return [card for card in _cards(context, player) if card and card != "0x"]


def _range_hand_notation(hand, player: str, context: PreflopContext) -> str | None:
    cards = _visible_range_cards(context, player)
    category = str((getattr(hand, "gametype", {}) or {}).get("category", "")).lower()
    if category in {"holdem", "holdemhilo"} and len(cards) >= 2:
        first, second = cards[0], cards[1]
        if len(first) < 2 or len(second) < 2:
            return None
        rank1, suit1 = first[0].upper(), first[-1].lower()
        rank2, suit2 = second[0].upper(), second[-1].lower()
        rank_values = sorted((RANK_VALUES.get(rank1, 0), RANK_VALUES.get(rank2, 0)), reverse=True)
        value_to_rank = {value: rank for rank, value in RANK_VALUES.items()}
        ranks = "".join(value_to_rank.get(value, "") for value in rank_values)
        if not ranks:
            return None
        if rank1 == rank2:
            return ranks
        return f"{ranks}{'s' if suit1 == suit2 else 'o'}"
    if len(cards) >= 4 and ("omaha" in category or category in {"5_omahahi"}):
        return " ".join(cards)
    return " ".join(cards) if cards else None


def _range_action_match(
    hand,
    player: str,
    context: PreflopContext,
    action_predicate: Callable[[PreflopContext, str], tuple[str, int | None] | None],
) -> dict[str, Any] | None:
    range_hand = _range_hand_notation(hand, player, context)
    if not range_hand:
        return None
    action = action_predicate(context, player)
    if not action:
        return None
    range_action, raise_number = action
    return {
        "street": "PREFLOP",
        "range_hand": range_hand,
        "range_action": range_action,
        "raise_number": raise_number,
    }


def _rfi_range_match(hand, player: str, context: PreflopContext) -> dict[str, Any] | None:
    return _range_action_match(
        hand,
        player,
        context,
        lambda ctx, name: ("rfi", 1) if ctx.first_raise and ctx.first_raise.player == name else None,
    )


def _three_bet_range_match(hand, player: str, context: PreflopContext) -> dict[str, Any] | None:
    return _range_action_match(
        hand,
        player,
        context,
        lambda ctx, name: ("3bet", 2) if ctx.second_raise and ctx.second_raise.player == name else None,
    )


def _four_bet_range_match(hand, player: str, context: PreflopContext) -> dict[str, Any] | None:
    return _range_action_match(
        hand,
        player,
        context,
        lambda ctx, name: ("4bet", 3) if ctx.third_raise and ctx.third_raise.player == name else None,
    )


def _call_vs_raise_range_match(hand, player: str, context: PreflopContext) -> dict[str, Any] | None:
    def predicate(ctx: PreflopContext, name: str) -> tuple[str, int | None] | None:
        first_raise = ctx.first_raise
        if not first_raise:
            return None
        if any(action.index > first_raise.index and action.is_call for action in ctx.player_actions.get(name, [])):
            return ("call_vs_raise", None)
        return None

    return _range_action_match(hand, player, context, predicate)


def _rfi_range(hand, player: str, context: PreflopContext) -> bool:
    return _rfi_range_match(hand, player, context) is not None


def _three_bet_range(hand, player: str, context: PreflopContext) -> bool:
    return _three_bet_range_match(hand, player, context) is not None


def _four_bet_range(hand, player: str, context: PreflopContext) -> bool:
    return _four_bet_range_match(hand, player, context) is not None


def _call_vs_raise_range(hand, player: str, context: PreflopContext) -> bool:
    return _call_vs_raise_range_match(hand, player, context) is not None


def _range_capture_evidence(
    hand,
    player: str,
    context: PreflopContext,
    matcher: Callable[[Any, str, PreflopContext], dict[str, Any] | None],
) -> dict[str, Any]:
    evidence = _raise_evidence(hand, player, context)
    match = matcher(hand, player, context)
    if match:
        evidence.update(match)
    return evidence


def _rfi_range_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    return _range_capture_evidence(hand, player, context, _rfi_range_match)


def _three_bet_range_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    return _range_capture_evidence(hand, player, context, _three_bet_range_match)


def _four_bet_range_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    return _range_capture_evidence(hand, player, context, _four_bet_range_match)


def _call_vs_raise_range_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    return _range_capture_evidence(hand, player, context, _call_vs_raise_range_match)


def _visible_player_cards(hand, player: str, limit: int | None = None) -> list[str]:
    try:
        cards = [card for card in hand.join_holecards(player, asList=True) if card and card != "0x"]
    except (AttributeError, KeyError, TypeError, ValueError):
        cards = []
    return cards[:limit] if limit is not None else cards


def _mixed_game_variant(hand) -> str:
    return str((getattr(hand, "gametype", {}) or {}).get("category", "")).lower()


def _stud_door_card(hand, player: str) -> str | None:
    cards = _visible_player_cards(hand, player)
    return cards[-1] if cards else None


def _draw_hand(hand, player: str) -> str | None:
    cards = _visible_player_cards(hand, player, limit=5)
    return " ".join(cards) if cards else None


def _first_street_open_action(context: PreflopContext):
    return context.first_raise


def _stud_complete_match(hand, player: str, context: PreflopContext) -> dict[str, Any] | None:
    first_raise = _first_street_open_action(context)
    door_card = _stud_door_card(hand, player)
    if not _is_stud_game(hand) or not first_raise or first_raise.player != player or not door_card:
        return None
    return {
        "street": "FIRST",
        "mixed_action": "complete",
        "door_card": door_card,
        "variant": _mixed_game_variant(hand),
    }


def _stud_call_complete_match(hand, player: str, context: PreflopContext) -> dict[str, Any] | None:
    first_raise = _first_street_open_action(context)
    door_card = _stud_door_card(hand, player)
    if not _is_stud_game(hand) or not first_raise or not door_card:
        return None
    if any(action.index > first_raise.index and action.is_call for action in context.player_actions.get(player, [])):
        return {
            "street": "FIRST",
            "mixed_action": "call_complete",
            "door_card": door_card,
            "variant": _mixed_game_variant(hand),
        }
    return None


def _draw_open_raise_match(hand, player: str, context: PreflopContext) -> dict[str, Any] | None:
    first_raise = _first_street_open_action(context)
    draw_hand = _draw_hand(hand, player)
    if not _is_draw_game(hand) or not first_raise or first_raise.player != player or not draw_hand:
        return None
    return {
        "street": "FIRST",
        "mixed_action": "open_raise",
        "draw_hand": draw_hand,
        "variant": _mixed_game_variant(hand),
    }


def _draw_call_raise_match(hand, player: str, context: PreflopContext) -> dict[str, Any] | None:
    first_raise = _first_street_open_action(context)
    draw_hand = _draw_hand(hand, player)
    if not _is_draw_game(hand) or not first_raise or not draw_hand:
        return None
    if any(action.index > first_raise.index and action.is_call for action in context.player_actions.get(player, [])):
        return {
            "street": "FIRST",
            "mixed_action": "call_raise",
            "draw_hand": draw_hand,
            "variant": _mixed_game_variant(hand),
        }
    return None


def _stud_completes_first_street(hand, player: str, context: PreflopContext) -> bool:
    return _stud_complete_match(hand, player, context) is not None


def _stud_calls_complete_first_street(hand, player: str, context: PreflopContext) -> bool:
    return _stud_call_complete_match(hand, player, context) is not None


def _draw_open_raises_first_street(hand, player: str, context: PreflopContext) -> bool:
    return _draw_open_raise_match(hand, player, context) is not None


def _draw_calls_raise_first_street(hand, player: str, context: PreflopContext) -> bool:
    return _draw_call_raise_match(hand, player, context) is not None


def _stud_draw_evidence(
    hand,
    player: str,
    context: PreflopContext,
    matcher: Callable[[Any, str, PreflopContext], dict[str, Any] | None],
) -> dict[str, Any]:
    evidence = _base_evidence(hand, player, context)
    match = matcher(hand, player, context)
    if match:
        evidence.update(match)
    return evidence


def _stud_complete_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    return _stud_draw_evidence(hand, player, context, _stud_complete_match)


def _stud_call_complete_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    return _stud_draw_evidence(hand, player, context, _stud_call_complete_match)


def _draw_open_raise_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    return _stud_draw_evidence(hand, player, context, _draw_open_raise_match)


def _draw_call_raise_evidence(hand, player: str, context: PreflopContext) -> dict[str, Any]:
    return _stud_draw_evidence(hand, player, context, _draw_call_raise_match)


def _player_limped_before_raise(player: str, context: PreflopContext):
    for action in context.player_actions.get(player, []):
        if action.is_raise:
            return None
        if action.is_call and not any(prior.is_raise for prior in context.actions[: action.index]):
            return action
    return None


def _open_limps_preflop(hand, player: str, context: PreflopContext) -> bool:
    player_actions = context.player_actions.get(player, [])
    if not player_actions:
        return False
    first_action = player_actions[0]
    return bool(first_action.is_call and not any(action.is_raise for action in context.actions[: first_action.index]))


def _limp_calls_preflop_raise(hand, player: str, context: PreflopContext) -> bool:
    limp_action = _player_limped_before_raise(player, context)
    first_raise = context.first_raise
    return bool(
        limp_action
        and first_raise
        and first_raise.index > limp_action.index
        and any(
            action.is_call and action.index > first_raise.index for action in context.player_actions.get(player, [])
        )
    )


def _three_bets_blind_vs_late_steal(hand, player: str, context: PreflopContext) -> bool:
    return bool(
        context.player_made_raise_number(player, 2)
        and context.first_raise_is_late_steal()
        and context.positions.get(player) in {"S", "B"}
    )


def _open_shoves_short_stack(hand, player: str, context: PreflopContext) -> bool:
    stack_bb = _player_stack_bb(hand, player, context)
    return bool(
        stack_bb is not None
        and stack_bb <= Decimal("15")
        and context.player_made_raise_number(player, 1)
        and context.first_raise
        and context.first_raise.is_allin
    )


def _three_bet_shoves_short_stack_vs_steal(hand, player: str, context: PreflopContext) -> bool:
    stack_bb = _player_stack_bb(hand, player, context)
    return bool(
        stack_bb is not None
        and stack_bb <= Decimal("20")
        and context.player_made_raise_number(player, 2)
        and context.second_raise
        and context.second_raise.is_allin
        and context.first_raise_is_late_steal()
    )


def _short_stack_open_raises_then_folds_to_3bet(hand, player: str, context: PreflopContext) -> bool:
    stack_bb = _player_stack_bb(hand, player, context)
    return bool(
        stack_bb is not None and stack_bb <= Decimal("15") and context.player_open_raised_then_folded_to_3bet(player)
    )


def _three_bets_single_paired_non_aaxx(hand, player: str, context: PreflopContext) -> bool:
    return context.player_made_raise_number(player, 2) and is_single_paired_non_aaxx(_plo_legacy_cards(context, player))


def _vpip_rainbow_non_aaxx(hand, player: str, context: PreflopContext) -> bool:
    cards = _plo_legacy_cards(context, player)
    return context.player_vpip(player) and is_rainbow(cards) and is_non_aaxx(cards)


def _three_bets_oop_vs_late_steal(hand, player: str, context: PreflopContext) -> bool:
    first_raise = context.first_raise
    return bool(
        context.player_made_raise_number(player, 2)
        and first_raise
        and context.first_raise_is_late_steal()
        and not context.has_position_on(player, first_raise.player)
    )


def _four_bets_non_aaxx(hand, player: str, context: PreflopContext) -> bool:
    return context.player_made_raise_number(player, 3) and is_non_aaxx(_plo_legacy_cards(context, player))


def _flats_aaxx_preflop(hand, player: str, context: PreflopContext) -> bool:
    return context.player_called_first_raise(player) and is_aaxx(_plo_legacy_cards(context, player))


def _raises_then_folds_to_3bet_ip(hand, player: str, context: PreflopContext) -> bool:
    second_raise = context.second_raise
    return bool(
        second_raise
        and context.player_open_raised_then_folded_to_3bet(player)
        and context.has_position_on(player, second_raise.player)
    )


def _raises_then_folds_to_3bet_oop(hand, player: str, context: PreflopContext) -> bool:
    second_raise = context.second_raise
    return bool(
        second_raise
        and context.player_open_raised_then_folded_to_3bet(player)
        and not context.has_position_on(player, second_raise.player)
    )


HWANG_PLO_PREFLOP_RULES: tuple[AutoNoteRule, ...] = (
    AutoNoteRule(
        "hwang_plo_081",
        1,
        "3Bets with single-paired non-AAxx hand",
        "{player}: 3-bet preflop with single-paired non-AAxx PLO hand",
        _three_bets_single_paired_non_aaxx,
        _raise_evidence,
    ),
    AutoNoteRule(
        "hwang_plo_082",
        1,
        "VPIP with rainbow non-AAxx hand",
        "{player}: VPIP preflop with rainbow non-AAxx PLO hand",
        _vpip_rainbow_non_aaxx,
        _base_evidence,
    ),
    AutoNoteRule(
        "hwang_plo_083",
        1,
        "3Bets OOP vs late position steal",
        "{player}: 3-bet OOP versus late-position steal",
        _three_bets_oop_vs_late_steal,
        _raise_evidence,
    ),
    AutoNoteRule(
        "hwang_plo_084",
        1,
        "4Bets with non-AAxx hand",
        "{player}: 4-bet preflop with non-AAxx PLO hand",
        _four_bets_non_aaxx,
        _raise_evidence,
    ),
    AutoNoteRule(
        "hwang_plo_085",
        1,
        "Flats AAxx preflop",
        "{player}: flat-called a preflop raise with AAxx",
        _flats_aaxx_preflop,
        _raise_evidence,
    ),
    AutoNoteRule(
        "hwang_plo_086",
        1,
        "Raises then folds to 3bet in position",
        "{player}: open-raised then folded to a 3-bet in position",
        _raises_then_folds_to_3bet_ip,
        _fold_to_3bet_evidence,
    ),
    AutoNoteRule(
        "hwang_plo_087",
        1,
        "Raises then folds to 3bet OOP",
        "{player}: open-raised then folded to a 3-bet out of position",
        _raises_then_folds_to_3bet_oop,
        _fold_to_3bet_evidence,
    ),
)

HOLDEM_CASH_PREFLOP_RULES: tuple[AutoNoteRule, ...] = (
    AutoNoteRule(
        "holdem_cash_001",
        1,
        "Open limps preflop",
        "{player}: open-limped preflop in Hold'em cash",
        _open_limps_preflop,
        _holdem_preflop_evidence,
    ),
    AutoNoteRule(
        "holdem_cash_002",
        1,
        "Limp-calls preflop raise",
        "{player}: limp-called a preflop raise in Hold'em cash",
        _limp_calls_preflop_raise,
        _holdem_preflop_evidence,
    ),
    AutoNoteRule(
        "holdem_cash_003",
        1,
        "3Bets blind versus late-position steal",
        "{player}: 3-bet from the blinds versus a late-position steal in Hold'em cash",
        _three_bets_blind_vs_late_steal,
        _holdem_preflop_evidence,
    ),
)

TOURNAMENT_PUSH_FOLD_RULES: tuple[AutoNoteRule, ...] = (
    AutoNoteRule(
        "tourney_pf_001",
        1,
        "Open shoves short stack",
        "{player}: open-shoved preflop with a short tournament stack",
        _open_shoves_short_stack,
        _tournament_preflop_evidence,
    ),
    AutoNoteRule(
        "tourney_pf_002",
        1,
        "3Bet shoves short stack vs steal",
        "{player}: 3-bet shoved short stack versus a late-position steal",
        _three_bet_shoves_short_stack_vs_steal,
        _tournament_preflop_evidence,
    ),
    AutoNoteRule(
        "tourney_pf_003",
        1,
        "Short stack raise-folds to 3bet",
        "{player}: open-raised then folded to a 3-bet with a short tournament stack",
        _short_stack_open_raises_then_folds_to_3bet,
        _tournament_preflop_evidence,
    ),
)

PLO_SPR_POSTFLOP_RULES: tuple[AutoNoteRule, ...] = (
    AutoNoteRule(
        "plo_spr_001",
        1,
        "Folds postflop with SPR <= 1",
        "{player}: folded postflop with SPR <= 1",
        _folds_low_spr_postflop,
        _low_spr_fold_evidence,
    ),
    AutoNoteRule(
        "plo_spr_002",
        1,
        "Bets or raises all-in postflop with SPR <= 1",
        "{player}: bet or raised all-in postflop with SPR <= 1",
        _aggressive_allin_low_spr_postflop,
        _low_spr_aggressive_allin_evidence,
    ),
    AutoNoteRule(
        "plo_spr_003",
        1,
        "Calls all-in postflop with SPR <= 1",
        "{player}: called all-in postflop with SPR <= 1",
        _calls_allin_low_spr_postflop,
        _low_spr_call_allin_evidence,
    ),
)

FLOP_TEXTURE_RULES: tuple[AutoNoteRule, ...] = (
    AutoNoteRule(
        "flop_texture_001",
        1,
        "Donks wet flop into preflop aggressor",
        "{player}: donk-bet a wet flop into the preflop aggressor",
        _donks_wet_flop,
        _donks_wet_flop_evidence,
    ),
    AutoNoteRule(
        "flop_texture_002",
        1,
        "Raises flop c-bet on wet flop",
        "{player}: raised a flop continuation bet on a wet board",
        _raises_cbet_wet_flop,
        _raises_cbet_wet_flop_evidence,
    ),
    AutoNoteRule(
        "flop_texture_003",
        1,
        "Calls flop c-bet on paired flop",
        "{player}: called a flop continuation bet on a paired board",
        _calls_cbet_paired_flop,
        _calls_cbet_paired_flop_evidence,
    ),
)

SHOWDOWN_QUALITY_RULES: tuple[AutoNoteRule, ...] = (
    AutoNoteRule(
        "showdown_quality_001",
        1,
        "Loses medium pot at showdown with one pair or worse",
        "{player}: lost a medium-or-larger pot at showdown with one pair or worse",
        _weak_lost_showdown,
        _weak_lost_showdown_evidence,
    ),
    AutoNoteRule(
        "showdown_quality_002",
        1,
        "River call then loses showdown with one pair or worse",
        "{player}: called river and lost showdown with one pair or worse",
        _river_call_weak_lost_showdown,
        _river_call_weak_lost_showdown_evidence,
    ),
    AutoNoteRule(
        "showdown_quality_003",
        1,
        "Shows non-nut flush in medium pot",
        "{player}: went to showdown in a medium-or-larger pot with a non-nut flush",
        _non_nut_flush_showdown,
        _non_nut_flush_showdown_evidence,
    ),
)

HERO_RELATIVE_RULES: tuple[AutoNoteRule, ...] = (
    AutoNoteRule(
        "hero_relative_001",
        1,
        "Villain 3-bets hero",
        "{player}: 3-bet hero preflop",
        _villain_three_bets_hero,
        _villain_three_bets_hero_evidence,
    ),
    AutoNoteRule(
        "hero_relative_002",
        1,
        "Villain 4-bets hero",
        "{player}: 4-bet hero preflop",
        _villain_four_bets_hero,
        _villain_four_bets_hero_evidence,
    ),
    AutoNoteRule(
        "hero_relative_003",
        1,
        "Villain folds to hero 3-bet",
        "{player}: folded to hero's preflop 3-bet",
        _villain_folds_to_hero_three_bet,
        _villain_folds_to_hero_three_bet_evidence,
    ),
    AutoNoteRule(
        "hero_relative_004",
        1,
        "Villain folds to hero 4-bet",
        "{player}: folded to hero's preflop 4-bet",
        _villain_folds_to_hero_four_bet,
        _villain_folds_to_hero_four_bet_evidence,
    ),
)

RANGE_CAPTURE_RULES: tuple[AutoNoteRule, ...] = (
    AutoNoteRule(
        "range_capture_001",
        1,
        "Captures visible RFI hand",
        "{player}: showed/captured a raised-first-in preflop hand",
        _rfi_range,
        _rfi_range_evidence,
    ),
    AutoNoteRule(
        "range_capture_002",
        1,
        "Captures visible 3-bet hand",
        "{player}: showed/captured a preflop 3-bet hand",
        _three_bet_range,
        _three_bet_range_evidence,
    ),
    AutoNoteRule(
        "range_capture_003",
        1,
        "Captures visible 4-bet hand",
        "{player}: showed/captured a preflop 4-bet hand",
        _four_bet_range,
        _four_bet_range_evidence,
    ),
    AutoNoteRule(
        "range_capture_004",
        1,
        "Captures visible call-vs-raise hand",
        "{player}: showed/captured a preflop call versus raise hand",
        _call_vs_raise_range,
        _call_vs_raise_range_evidence,
    ),
)

STUD_DRAW_FIRST_STREET_RULES: tuple[AutoNoteRule, ...] = (
    AutoNoteRule(
        "stud_draw_001",
        1,
        "Stud/Razz completes first street",
        "{player}: completed first street in Stud/Razz",
        _stud_completes_first_street,
        _stud_complete_evidence,
    ),
    AutoNoteRule(
        "stud_draw_002",
        1,
        "Stud/Razz calls a complete",
        "{player}: called a first-street complete in Stud/Razz",
        _stud_calls_complete_first_street,
        _stud_call_complete_evidence,
    ),
    AutoNoteRule(
        "stud_draw_003",
        1,
        "Draw open-raises first street",
        "{player}: open-raised first street in Draw",
        _draw_open_raises_first_street,
        _draw_open_raise_evidence,
    ),
    AutoNoteRule(
        "stud_draw_004",
        1,
        "Draw calls first-street raise",
        "{player}: called a first-street raise in Draw",
        _draw_calls_raise_first_street,
        _draw_call_raise_evidence,
    ),
)

RULE_SET_REGISTRY: tuple[AutoNoteRuleSet, ...] = (
    AutoNoteRuleSet(
        rule_set_id=RULE_SET_HWANG_PLO_PREFLOP,
        rules=HWANG_PLO_PREFLOP_RULES,
        supports_hand=is_plo4,
    ),
    AutoNoteRuleSet(
        rule_set_id=RULE_SET_HOLDEM_CASH_PREFLOP,
        rules=HOLDEM_CASH_PREFLOP_RULES,
        supports_hand=_is_holdem_cash,
        enabled_by_default=False,
    ),
    AutoNoteRuleSet(
        rule_set_id=RULE_SET_TOURNAMENT_PUSH_FOLD,
        rules=TOURNAMENT_PUSH_FOLD_RULES,
        supports_hand=_is_holdem_tournament,
        enabled_by_default=False,
    ),
    AutoNoteRuleSet(
        rule_set_id=RULE_SET_PLO_SPR_POSTFLOP,
        rules=PLO_SPR_POSTFLOP_RULES,
        supports_hand=is_plo4,
        enabled_by_default=False,
    ),
    AutoNoteRuleSet(
        rule_set_id=RULE_SET_FLOP_TEXTURE,
        rules=FLOP_TEXTURE_RULES,
        supports_hand=_is_flop_game,
        enabled_by_default=False,
    ),
    AutoNoteRuleSet(
        rule_set_id=RULE_SET_SHOWDOWN_QUALITY,
        rules=SHOWDOWN_QUALITY_RULES,
        supports_hand=_is_flop_game,
        enabled_by_default=False,
    ),
    AutoNoteRuleSet(
        rule_set_id=RULE_SET_HERO_RELATIVE,
        rules=HERO_RELATIVE_RULES,
        supports_hand=_is_flop_game,
        enabled_by_default=False,
    ),
    AutoNoteRuleSet(
        rule_set_id=RULE_SET_RANGE_CAPTURE,
        rules=RANGE_CAPTURE_RULES,
        supports_hand=_is_flop_game,
        enabled_by_default=False,
    ),
    AutoNoteRuleSet(
        rule_set_id=RULE_SET_STUD_DRAW_FIRST_STREET,
        rules=STUD_DRAW_FIRST_STREET_RULES,
        supports_hand=_is_stud_or_draw_game,
        enabled_by_default=False,
    ),
)
