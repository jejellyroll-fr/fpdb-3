"""Persistence of the situation model (#294) and its lifecycle (#305).

The situations have been derived at import since #294; this module gives
them their table. ``HandsSituations`` holds one row per decision, keyed
``(handId, actionNo)`` exactly like ``HandsActions``: the situation is the
name of that decision, so the two tables read side by side. The column
vocabulary is the situation dataclass's own, in camelCase like the event
columns; ``HANDS_SITUATION_COLUMNS`` is the single ordered list and the DDL,
the store query and the bulk writer are all checked against it.

Tuple- and tuple-of-tuple-valued fields are stored as JSON text: they are
history, not dimensions anyone aggregates by, and a TEXT column keeps the
table flat. Booleans go through the same int coercion the importer uses,
so SQLite (which hands booleans back as 0/1) and PostgreSQL agree on reads.

``situationVersion`` stamps every row with
``analytics_lifecycle.EXTRACTOR_VERSIONS["situations"]`` -- per-row version,
so a stale database knows precisely which rows a rule change invalidates.
"""

from __future__ import annotations

import json
from typing import Any, Final

from .player_situations import PlayerSituation

# The stored columns of HandsSituations, in store order. handId and playerId
# are supplied by the caller (they key the join); everything else comes from
# the situation record. Field names differ from columns only where a Python
# keyword or a shadow forced it: primary -> primaryLabel, group -> groupName.
SITUATION_FIELD_TO_COLUMN: Final[dict[str, str]] = {
    "action_no": "actionNo",
    "street": "street",
    "street_name": "streetName",
    "position": "position",
    "relative_position": "relativePosition",
    "in_position": "inPosition",
    "effective_stack": "effectiveStack",
    "effective_stack_bb": "effectiveStackBB",
    "stack_bucket": "stackBucket",
    "spr_before": "sprBefore",
    "is_hero": "isHero",
    "pot_type": "potType",
    "multiway": "multiway",
    "players_in_hand": "playersInHand",
    "preflop_aggressor": "preflopAggressor",
    "is_preflop_aggressor": "isPreflopAggressor",
    "street_aggressor": "streetAggressor",
    "is_aggressor": "isAggressor",
    "previous_aggressor": "previousAggressor",
    "is_previous_aggressor": "isPreviousAggressor",
    "previous_aggressor_led": "previousAggressorLed",
    "previous_aggressor_checked": "previousAggressorChecked",
    "previous_aggressor_position": "previousAggressorPosition",
    "in_position_vs_previous_aggressor": "inPositionVsPreviousAggressor",
    "aggressor_checked_this_street": "aggressorCheckedThisStreet",
    "previous_raiser": "previousRaiser",
    "is_previous_raiser": "isPreviousRaiser",
    "to_call": "toCall",
    "pot_before": "potBefore",
    "pot_after": "potAfter",
    "pot_odds_bp": "potOddsBp",
    "facing_action": "facingAction",
    "facing_player": "facingPlayer",
    "facing_position": "facingPosition",
    "in_position_vs_facing": "inPositionVsFacing",
    "facing_amount": "facingAmount",
    "facing_sizing_bp": "facingSizingBp",
    "facing_all_in": "facingAllIn",
    "bet_level_faced": "betLevelFaced",
    "raises_before": "raisesBefore",
    "calls_before": "callsBefore",
    "callers_between_raises": "callersBetweenRaises",
    "callers_since_raise": "callersSinceRaise",
    "street_actions": "streetActions",
    "previous_street_actions": "previousStreetActions",
    "board": "board",
    "response": "response",
    "is_all_in": "isAllIn",
    "role": "role",
    "labels": "labels",
    "primary": "primaryLabel",
    "group": "groupName",
    "enum_key": "enumKey",
    "enum_response": "enumResponse",
    "enum_answers": "enumAnswers",
}

# Columns after handId/playerId, in store order (the order the DDL, the
# store query and every writer follow) -- excluding the situationVersion
# stamp, which every writer appends last.
HANDS_SITUATION_COLUMNS: Final[tuple[str, ...]] = tuple(column for column in SITUATION_FIELD_TO_COLUMN.values())

# Fields stored as JSON text instead of scalars.
_JSON_FIELDS: Final[frozenset[str]] = frozenset(
    {"street_actions", "previous_street_actions", "board", "labels", "enum_answers"},
)


def situation_row(
    situation: PlayerSituation,
    situation_version: int,
) -> tuple[list[str], list[Any]]:
    """One situation as (column names, values), ready for a bulk append.

    The tuple/tuple-of-tuple fields are JSON text; booleans stay booleans
    (the adapters coerce per backend on read); None passes through for the
    nullable positions and names.
    """
    record = situation.as_dict()
    columns: list[str] = []
    values: list[Any] = []
    for field_name, column in SITUATION_FIELD_TO_COLUMN.items():
        columns.append(column)
        if field_name in _JSON_FIELDS:
            values.append(json.dumps(record.get(field_name) or [], default=str))
        else:
            values.append(record.get(field_name))
    columns.append("situationVersion")
    values.append(int(situation_version))
    return columns, values


def coerce_situation_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize one read-back row: booleans from 0/1, JSON lists decoded.

    A row may come from SQLite (booleans as ints) or PostgreSQL (bools);
    both normalize to the same shapes here, so the callers above the table
    do not branch per backend.
    """
    out = dict(row)
    for column in (
        "inPosition",
        "isHero",
        "multiway",
        "isPreflopAggressor",
        "isAggressor",
        "isPreviousAggressor",
        "previousAggressorLed",
        "previousAggressorChecked",
        "aggressorCheckedThisStreet",
        "isPreviousRaiser",
        "facingAllIn",
        "isAllIn",
    ):
        if column in out:
            out[column] = bool(out[column])
    for column in ("streetActions", "previousStreetActions", "board", "labels", "enumAnswers"):
        value = out.get(column)
        if isinstance(value, str):
            try:
                out[column] = json.loads(value)
            except ValueError:
                out[column] = []
    return out


def bulk_rows(
    hand_id: int,
    player_ids: dict[str, int],
    situations: list[PlayerSituation],
    situation_version: int,
) -> list[list[Any]]:
    """Rows for store_hands_situations, in column order, one per situation.

    A player the id map does not know (a malformed hand) drops the row --
    the situation names a decision by a player who must exist in Players.
    """
    rows: list[list[Any]] = []
    for situation in situations:
        player_id = player_ids.get(situation.player)
        if player_id is None:
            continue
        _columns, values = situation_row(situation, situation_version)
        rows.append([hand_id, player_id, *values])
    return rows
