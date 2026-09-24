"""Composable, hand-level predicates for the Hand Viewer (#396).

The viewer applies these predicates to hand ids before it reconstructs a Hand.
Action predicates use the canonical HandsActions/HandsSituations rows; the
starting-hand expression is shared with Research's 13x13 range model.

The targeted B608 suppressions below cover only SQL templates assembled from
fixed aliases, allowlisted columns/operators, and validated driver markers;
filter values are always passed separately as DB parameters.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import Card
from .holdem_classes import class_ids, holdem_class_expression

PREFLOP_FILTERS: dict[str, tuple[str | tuple[str, ...], str | None]] = {
    "rfi": ("open_raise", None),
    "limp": (("open_limp", "over_limp"), None),
    "call_open": ("facing_open", "call"),
    "three_bet": ("three_bet", None),
    "four_bet": ("four_bet", None),
    "squeeze": ("squeeze", None),
    "faced_open": ("facing_open", None),
    "faced_three_bet": ("facing_3bet", None),
}

POSTFLOP_FILTERS: dict[str, tuple[str, str | None]] = {
    "cbet": ("cbet", None),
    "faced_cbet": ("facing_cbet", None),
    "check_raise": ("check_raise", None),
}

_ACTION_FILTERS = frozenset({"bet", "call", "raise", "check", "fold"})
_ANALYTICS_SUBSYSTEM_ORDER = ("action_events", "situations")

POSTFLOP_ACTION_TYPES = {
    "bet": "bets",
    "call": "calls",
    "raise": "raises",
    "check": "checks",
    "fold": "folds",
}

SIZING_BUCKETS: dict[str, tuple[int | None, int | None]] = {
    "under_25": (None, 2500),
    "25_50": (2500, 5000),
    "50_75": (5000, 7500),
    "75_100": (7500, 10000),
    "100_150": (10000, 15000),
    "over_150": (15000, None),
}


def required_analytics_subsystems(filters: Mapping[str, Any]) -> tuple[str, ...]:
    """Return derived-data layers required by the selected filters, in stable order."""
    required: set[str] = set()
    preflop = filters.get("preflop")
    postflop = filters.get("postflop")
    if preflop in PREFLOP_FILTERS:
        required.add("action_events")
        required.add("situations")
    if postflop in _ACTION_FILTERS:
        required.add("action_events")
    elif postflop in POSTFLOP_FILTERS:
        required.update(("action_events", "situations"))
    if filters.get("sizing_bucket") in SIZING_BUCKETS or any(
        filters.get(key) not in (None, "") for key in ("stack_min_bb", "stack_max_bb")
    ):
        required.add("action_events")
    return tuple(name for name in _ANALYTICS_SUBSYSTEM_ORDER if name in required)


def _action_exists(
    hand_alias: str,
    label: str | tuple[str, ...],
    response: str | None,
    street_condition: str,
    placeholder: str,
) -> tuple[str, list[Any]]:
    """Match a semantic action label on any decision in a hand."""
    labels = (label,) if isinstance(label, str) else label
    label_conditions = [
        f"SF.primaryLabel IN ({', '.join(placeholder for _ in labels)})",
        "(" + " OR ".join("SF.labels LIKE " + placeholder for _ in labels) + ")",
    ]
    conditions = [
        "AF.handId = " + hand_alias + ".id",
        "AF.playerId = hp.playerId",
        "AF.playerId = SF.playerId",
        "AF.actionNo = SF.actionNo",
        street_condition,
        "(" + " OR ".join(label_conditions) + ")",
    ]
    params: list[Any] = [*labels, *(f'%"{value}"%' for value in labels)]
    if response:
        conditions.append(f"SF.response = {placeholder}")
        params.append(response)
    return (
        "EXISTS (SELECT 1 FROM HandsActions AF JOIN HandsSituations SF "  # nosec B608
        "ON SF.handId = AF.handId AND SF.playerId = AF.playerId AND SF.actionNo = AF.actionNo "
        "WHERE " + " AND ".join(conditions) + ")",
        params,
    )


def _starting_hand_clause(filters: Mapping[str, Any], placeholder: str) -> tuple[list[str], list[Any]]:
    selected = tuple(filters.get("starting_hands") or ())
    if not selected:
        return [], []
    ids = class_ids(selected)
    marks = ", ".join(placeholder for _ in ids)
    class_expression = holdem_class_expression("HPF.")
    clause = (
        "EXISTS (SELECT 1 FROM HandsPlayers HPF WHERE HPF.handId = h.id "  # nosec B608
        "AND HPF.playerId = hp.playerId AND gt.category IN ('holdem', '6_holdem', 'aof_holdem', 'fusion') "
        f"AND ({class_expression}) IN ({marks}))"
    )
    return [clause], ids


def _exact_cards_clause(filters: Mapping[str, Any], placeholder: str) -> tuple[list[str], list[Any]]:
    exact_cards = tuple(card for card in (filters.get("exact_card_1"), filters.get("exact_card_2")) if card)
    if not exact_cards:
        return [], []
    encoded = tuple(Card.encodeCard(card) if isinstance(card, str) else int(card) for card in exact_cards)
    if len(encoded) == 2 and encoded[0] == encoded[1]:
        return ["1=0"], []
    if len(encoded) == 1:
        cards = ", ".join(f"HPX.card{index}" for index in range(1, 21))
        return [
            "EXISTS (SELECT 1 FROM HandsPlayers HPX WHERE HPX.handId = h.id AND HPX.playerId = hp.playerId "  # nosec B608
            f"AND {placeholder} IN ({cards}))"
        ], [encoded[0]]
    cards = ", ".join(f"HPX.card{index}" for index in range(1, 21))
    clause = (
        "EXISTS (SELECT 1 FROM HandsPlayers HPX WHERE HPX.handId = h.id AND HPX.playerId = hp.playerId AND "  # nosec B608
        f"{placeholder} IN ({cards}) AND {placeholder} IN ({cards}))"
    )
    return [clause], [encoded[0], encoded[1]]


def _preflop_clause(filters: Mapping[str, Any], placeholder: str) -> tuple[list[str], list[Any]]:
    preflop = filters.get("preflop")
    if preflop == "vpip":
        return [
            "EXISTS (SELECT 1 FROM HandsPlayers HPV WHERE HPV.handId = h.id AND HPV.playerId = hp.playerId "
            "AND HPV.street0VPIChance IS TRUE AND HPV.street0VPI IS TRUE)"
        ], []
    if preflop == "not_vpip":
        return [
            "EXISTS (SELECT 1 FROM HandsPlayers HPV WHERE HPV.handId = h.id AND HPV.playerId = hp.playerId "
            "AND HPV.street0VPIChance IS TRUE AND HPV.street0VPI IS FALSE)"
        ], []
    if preflop == "all_in":
        return [
            "EXISTS (SELECT 1 FROM HandsActions AAI WHERE AAI.handId = h.id "
            "AND AAI.playerId = hp.playerId AND AAI.street = 0 AND AAI.allIn IS TRUE)"
        ], []
    if preflop in PREFLOP_FILTERS:
        label, response = PREFLOP_FILTERS[preflop]
        clause, params = _action_exists("h", label, response, "AF.street = 0", placeholder)
        return [clause], params
    return [], []


def _postflop_clause(filters: Mapping[str, Any], placeholder: str) -> tuple[list[str], list[Any]]:
    postflop = filters.get("postflop")
    if postflop in {"saw_flop", "saw_turn", "saw_river"}:
        street = {"saw_flop": 1, "saw_turn": 2, "saw_river": 3}[postflop]
        return [
            f"EXISTS (SELECT 1 FROM HandsPlayers HPF WHERE HPF.handId = h.id "  # nosec B608
            f"AND HPF.playerId = hp.playerId AND HPF.street{street}Seen IS TRUE)"
        ], []
    if postflop == "showdown":
        return [
            "EXISTS (SELECT 1 FROM HandsPlayers HPF WHERE HPF.handId = h.id "
            "AND HPF.playerId = hp.playerId AND HPF.sawShowdown IS TRUE)"
        ], []
    if postflop in _ACTION_FILTERS:
        return [
            "EXISTS (SELECT 1 FROM HandsActions AF WHERE AF.handId = h.id AND AF.playerId = hp.playerId "  # nosec B608
            f"AND AF.street BETWEEN 1 AND 3 AND AF.actionType = {placeholder})"
        ], [POSTFLOP_ACTION_TYPES[postflop]]
    if postflop in POSTFLOP_FILTERS:
        label, response = POSTFLOP_FILTERS[postflop]
        clause, params = _action_exists("h", label, response, "AF.street BETWEEN 1 AND 3", placeholder)
        return [clause], params
    return [], []


def _pot_net_clauses(filters: Mapping[str, Any], placeholder: str) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for key, comparator in (("pot_min_bb", ">="), ("pot_max_bb", "<=")):
        value = filters.get(key)
        if value not in (None, ""):
            clauses.append(
                f"(CASE WHEN gt.bigBlind > 0 THEN h.finalPot * 1.0 / gt.bigBlind END) {comparator} {placeholder}"
            )
            params.append(float(value))

    for key, comparator in (("net_min_bb", ">="), ("net_max_bb", "<=")):
        value = filters.get(key)
        if value not in (None, ""):
            clauses.append(f"(gt.bigBlind > 0 AND hp.totalProfit * 1.0 / gt.bigBlind {comparator} {placeholder})")
            params.append(float(value))

    return clauses, params


def _player_count_clauses(filters: Mapping[str, Any], placeholder: str) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for key, comparator in (("players_min", ">="), ("players_max", "<=")):
        value = filters.get(key)
        if value not in (None, ""):
            clauses.append(
                f"(SELECT COUNT(*) FROM HandsPlayers HPP WHERE HPP.handId = h.id) {comparator} {placeholder}"  # nosec B608
            )
            params.append(int(value))

    return clauses, params


def _stack_clauses(filters: Mapping[str, Any], placeholder: str) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    stack_low = filters.get("stack_min_bb")
    stack_high = filters.get("stack_max_bb")
    if stack_low not in (None, "") or stack_high not in (None, ""):
        conditions = ["ASB.handId = h.id", "ASB.playerId = hp.playerId", "ASB.effectiveStackBB > 0"]
        if stack_low not in (None, ""):
            conditions.append(f"ASB.effectiveStackBB >= {placeholder}")
            params.append(float(stack_low) * 100)
        if stack_high not in (None, ""):
            conditions.append(f"ASB.effectiveStackBB <= {placeholder}")
            params.append(float(stack_high) * 100)
        clauses.append("EXISTS (SELECT 1 FROM HandsActions ASB WHERE " + " AND ".join(conditions) + ")")  # nosec B608

    return clauses, params


def _sizing_clause(filters: Mapping[str, Any], placeholder: str) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    sizing_bucket = filters.get("sizing_bucket")
    if sizing_bucket in SIZING_BUCKETS:
        lower, upper = SIZING_BUCKETS[sizing_bucket]
        conditions = ["ASZ.handId = h.id", "ASZ.playerId = hp.playerId", "ASZ.sizingBp > 0"]
        if lower is not None:
            conditions.append(f"ASZ.sizingBp >= {placeholder}")
            params.append(lower)
        if upper is not None:
            conditions.append(f"ASZ.sizingBp < {placeholder}")
            params.append(upper)
        clauses.append("EXISTS (SELECT 1 FROM HandsActions ASZ WHERE " + " AND ".join(conditions) + ")")  # nosec B608

    return clauses, params


def _numeric_clauses(filters: Mapping[str, Any], placeholder: str) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for builder in (_pot_net_clauses, _player_count_clauses, _stack_clauses, _sizing_clause):
        built, values = builder(filters, placeholder)
        clauses.extend(built)
        params.extend(values)
    return clauses, params


def build_filter_clauses(
    filters: Mapping[str, Any],
    placeholder: str = "%s",
) -> tuple[list[str], tuple[Any, ...]]:
    """Build parameterized SQL for the Hand Viewer's outer h/gt/hp query.

    Categories are separate correlated predicates, so an RFI and faced c-bet
    can refer to different actions by the selected player in the same hand.
    """
    if placeholder not in {"?", "%s"}:
        raise ValueError("Unsupported SQL parameter placeholder")
    clauses: list[str] = []
    params: list[Any] = []
    for builder in (_starting_hand_clause, _exact_cards_clause, _preflop_clause, _postflop_clause, _numeric_clauses):
        built, values = builder(filters, placeholder)
        clauses.extend(built)
        params.extend(values)
    return clauses, tuple(params)


__all__ = [
    "PREFLOP_FILTERS",
    "POSTFLOP_FILTERS",
    "SIZING_BUCKETS",
    "build_filter_clauses",
    "required_analytics_subsystems",
]
