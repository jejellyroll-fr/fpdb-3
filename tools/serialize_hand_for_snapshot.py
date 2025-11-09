#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Canonical serialization for snapshot-based regression tests.

This module turns parsed ``Hand`` instances into deterministic dictionaries
that mirror the ``Hands``, ``HandsPlayers`` and ``HandsActions`` tables. The
output is purely declarative: it does not mutate or "fix" the parsed data, and
all monetary values are represented in integer cents.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP
import json
import pickle
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Heuristics to detect keys representing monetary amounts. The objective is to
# guarantee they end up serialized as integer cents while keeping non-monetary
# fields intact.
_MONETARY_HINTS = (
    "amount",
    "bet",
    "bounty",
    "buy",
    "cash",
    "chip",
    "collect",
    "cost",
    "fee",
    "pot",
    "profit",
    "rake",
    "stack",
    "wager",
    "win",
)

_HAND_REQUIRED_TYPES = {
    "startTime": str,
    "importTime": str,
    "heroSeat": int,
    "seats": int,
    "tableName": str,
    "siteHandNo": int,
}

_PLAYER_REQUIRED_TYPES = {
    "playerName": str,
    "seatNo": int,
    "startCash": int,
    "winnings": int,
    "rake": int,
}

_ACTION_REQUIRED_TYPES = {
    "actionNo": int,
    "streetActionNo": int,
    "street": int,
    "actionId": int,
    "player": str,
}

_PLAYER_BASE_COLUMNS = {
    "seatNo",
    "startCash",
    "winnings",
    "rake",
    "totalProfit",
    "allInEV",
    "effStack",
    "position",
    "startCards",
    "handString",
    "startBounty",
    "endBounty",
    "cashout",
    "cashoutFee",
    "isCashOut",
    "tourneysPlayersId",
    "common",
    "committed",
    "sawShowdown",
    "showed",
    "wentAllIn",
}
_PLAYER_CARD_COLUMNS = {f"card{i}" for i in range(1, 21)}
_PLAYER_ALLOWED_KEYS = _PLAYER_BASE_COLUMNS | _PLAYER_CARD_COLUMNS

_HANDS_MIN_COLUMNS = {
    "siteHandNo",
    "tableName",
    "siteId",
    "siteName",
    "startTime",
    "importTime",
    "seats",
    "heroSeat",
}

_HANDS_PLAYERS_MIN_COLUMNS = {
    "playerName",
    "seatNo",
    "startCash",
    "winnings",
    "rake",
}

_HANDS_ACTIONS_MIN_COLUMNS = {
    "actionNo",
    "streetActionNo",
    "street",
    "actionId",
    "player",
}


def _looks_like_money(key_path: Tuple[str, ...]) -> bool:
    """Return True when the key path suggests the value is monetary."""
    if not key_path:
        return False
    key = key_path[-1].lower()
    return any(hint in key for hint in _MONETARY_HINTS)


def _to_cents(value: Any) -> int:
    """Convert Decimal/float monetary values to integer cents."""
    if value is None:
        return 0
    dec_value = Decimal(str(value))
    cents = (dec_value * 100).to_integral_value(rounding=ROUND_HALF_UP)
    return int(cents)


def _normalize_scalar(value: Any, key_path: Tuple[str, ...]) -> Any:
    """Normalize a scalar value into snapshot-friendly representation."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (datetime, date, time)):
        # Serialize temporal values as ISO 8601 strings. Keep naive times for
        # backwards compatibility.
        if isinstance(value, time) and value.tzinfo is None:
            return value.isoformat(timespec="seconds")
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, Decimal):
        if value.is_nan():
            return None
        if _looks_like_money(key_path):
            return int(value.to_integral_value(rounding=ROUND_HALF_UP))
        integral = value.to_integral_value(rounding=ROUND_HALF_UP)
        if value == integral:
            return int(integral)
        return float(value)
    if isinstance(value, float):
        if _looks_like_money(key_path) or value.is_integer():
            return int(round(value))
        return value
    return value


def _normalize_value(value: Any, key_path: Tuple[str, ...] = ()) -> Any:
    """Recursively normalize nested structures for JSON serialization."""
    if isinstance(value, Mapping):
        normalized: Dict[str, Any] = {}
        for key in sorted(value):
            normalized[key] = _normalize_value(value[key], key_path + (str(key),))
        return normalized
    if isinstance(value, (list, tuple, set)):
        return [_normalize_value(item, key_path) for item in value]
    return _normalize_scalar(value, key_path)


def _extract_hand_details(hand: Any) -> Dict[str, Any]:
    """Collect the canonical ``Hands`` row for the provided hand."""
    stats = getattr(hand, "stats", None)
    hand_stats = {}
    if stats and hasattr(stats, "getHands"):
        hand_stats = stats.getHands() or {}

    details: Dict[str, Any] = dict(hand_stats)
    details.setdefault("siteHandNo", getattr(hand, "handid", None))
    details.setdefault("tableName", getattr(hand, "tablename", None))
    details.setdefault("siteId", getattr(hand, "siteId", None))
    details.setdefault("siteName", getattr(hand, "sitename", None))

    gametype = getattr(hand, "gametype", None) or {}
    if gametype:
        gametype_details = {
            "base": gametype.get("base"),
            "category": gametype.get("category"),
            "currency": gametype.get("currency"),
            "limitType": gametype.get("limitType"),
            "mixed": gametype.get("mixgame"),
            "sb": gametype.get("sb"),
            "bb": gametype.get("bb"),
        }
        details.setdefault("gametype", gametype_details)

    if details.get("startTime") is None and hasattr(hand, "startTime"):
        details["startTime"] = getattr(hand, "startTime")
    if details.get("importTime") is None and hasattr(hand, "importTime"):
        details["importTime"] = getattr(hand, "importTime")
    if details.get("importTime") is None:
        details["importTime"] = details.get("startTime")

    site_hand_no = details.get("siteHandNo")
    if isinstance(site_hand_no, str) and site_hand_no.isdigit():
        try:
            details["siteHandNo"] = int(site_hand_no)
        except ValueError:
            pass

    pot = getattr(hand, "pot", None)
    if pot is not None:
        street_mapping = [
            ("PREFLOP", "street0Pot"),
            ("FLOP", "street1Pot"),
            ("TURN", "street2Pot"),
            ("RIVER", "street3Pot"),
        ]

        for street_name, key in street_mapping:
            total = pot.getTotalAtStreet(street_name)
            if total:
                details[key] = _to_cents(total)
            elif key in details:
                details[key] = None

        final_total = getattr(hand, "totalpot", None)
        if final_total in (None, 0) and getattr(pot, "total", None) not in (None, 0):
            final_total = pot.total
        if final_total is not None:
            cents = _to_cents(final_total)
            details["finalPot"] = cents
            details["street4Pot"] = cents
            details["totalPot"] = cents

        rake = getattr(hand, "rake", None)
        if rake is not None:
            details["rake"] = _to_cents(rake)

    return _normalize_value(details)


def _extract_players(hand: Any) -> List[Dict[str, Any]]:
    """Collect the canonical ``HandsPlayers`` rows."""
    stats = getattr(hand, "stats", None)
    players_stats = {}
    if stats and hasattr(stats, "getHandsPlayers"):
        players_stats = stats.getHandsPlayers() or {}

    players: List[Dict[str, Any]] = []
    for player_name, raw_stats in players_stats.items():
        record = {"playerName": player_name}
        if raw_stats:
            filtered = {k: raw_stats[k] for k in _PLAYER_ALLOWED_KEYS if k in raw_stats}
            record.update(filtered)
        players.append(_normalize_value(record))

    players.sort(
        key=lambda player: (
            player.get("seatNo") if player.get("seatNo") is not None else -1,
            player.get("playerName"),
        )
    )
    return players


def _extract_actions(hand: Any) -> List[Dict[str, Any]]:
    """Collect the canonical ``HandsActions`` rows."""
    stats = getattr(hand, "stats", None)
    actions_map = {}
    if stats and hasattr(stats, "getHandsActions"):
        actions_map = stats.getHandsActions() or {}
    elif hasattr(hand, "handsactions") and hand.handsactions:
        actions_map = hand.handsactions

    items = list(actions_map.values())
    items.sort(key=lambda action: action.get("actionNo", 0))
    normalized_actions = [_normalize_value(dict(action)) for action in items]

    if hand and hasattr(hand, "shown") and hand.shown:
        max_action_no = max((action.get("actionNo", 0) for action in normalized_actions), default=0)
        street_counts: Dict[int, int] = {}
        for action in normalized_actions:
            street = action.get("street", 0)
            street_counts[street] = max(street_counts.get(street, 0), action.get("streetActionNo", 0))

        showdown_street = 4
        for idx, player in enumerate(sorted(hand.shown)):
            cards = []
            try:
                hole_info = hand.holecards.get("PREFLOP", {}).get(player)
                if hole_info and len(hole_info) > 1 and isinstance(hole_info[1], (list, tuple)):
                    cards = [card for card in hole_info[1] if card and card != "0x"]
            except AttributeError:
                cards = []

            street_counts[showdown_street] = street_counts.get(showdown_street, 0) + 1
            max_action_no += 1

            show_action = {
                "actionId": 18,
                "actionNo": max_action_no,
                "allIn": False,
                "amount": 0,
                "amountCalled": 0,
                "cards": cards,
                "cardsDiscarded": None,
                "numDiscarded": 0,
                "player": player,
                "raiseTo": 0,
                "street": showdown_street,
                "streetActionNo": street_counts[showdown_street],
            }
            normalized_actions.append(_normalize_value(show_action))

    normalized_actions.sort(key=lambda action: action.get("actionNo", 0))
    return normalized_actions


def serialize_hand_for_snapshot(hand: Any) -> Dict[str, Any]:
    """Serialize a ``Hand`` instance to the canonical snapshot structure."""
    if hand is None:
        raise ValueError("serialize_hand_for_snapshot requires a hand instance")

    serialized = {
        "hand_details": _extract_hand_details(hand),
        "players": _extract_players(hand),
        "actions": _extract_actions(hand),
    }

    return serialized


def serialize_hands_batch(hands: List[Any]) -> List[Dict[str, Any]]:
    """Serialize a batch of hands to deterministic canonical records."""
    serialized_hands: List[Dict[str, Any]] = []
    for hand in hands:
        try:
            serialized_hands.append(serialize_hand_for_snapshot(hand))
        except Exception as exc:  # pragma: no cover - defensive guard
            serialized_hands.append(
                {
                    "error": str(exc),
                    "hand_id": getattr(hand, "handid", "Unknown"),
                    "site": getattr(hand, "sitename", "Unknown"),
                }
            )

    def sort_key(item: Dict[str, Any]) -> Any:
        details = item.get("hand_details")
        if isinstance(details, Mapping):
            return details.get("siteHandNo") or details.get("startTime") or ""
        return item.get("hand_id") or ""

    serialized_hands.sort(key=sort_key)
    return serialized_hands


def serialize_raw_hand_object(hand: Any) -> Dict[str, Any]:
    """Backward-compatible helper for legacy tooling."""
    return serialize_hand_for_snapshot(hand)


def serialize_hand_to_stars_format(hand: Any) -> str:
    """Return a PokerStars-formatted string when available."""
    if hasattr(hand, "handText") and hand.handText:
        return str(hand.handText)
    raise ValueError("Hand object does not expose raw hand text for Stars format export")


def print_hand_to_stdout(hand: Any) -> None:
    """Print a textual representation of the hand to stdout."""
    try:
        print(serialize_hand_to_stars_format(hand))
    except ValueError:
        print(json.dumps(serialize_hand_for_snapshot(hand), indent=2, sort_keys=True))


def save_raw_hand_objects(hands: List[Any], output_path: str, fmt: str = "json") -> None:
    """Persist hand objects for legacy workflows."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        data = [serialize_hand_for_snapshot(hand) for hand in hands]
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    elif fmt == "pickle":
        data = [serialize_hand_for_snapshot(hand) for hand in hands]
        path.write_bytes(pickle.dumps(data))
    elif fmt == "stars":
        rendered_hands = []
        for hand in hands:
            try:
                rendered_hands.append(serialize_hand_to_stars_format(hand))
            except ValueError:
                rendered_hands.append(
                    json.dumps(serialize_hand_for_snapshot(hand), indent=2, sort_keys=True)
                )
        path.write_text("\n\n".join(rendered_hands), encoding="utf-8")
    else:
        raise ValueError(f"Unsupported raw format: {fmt}")


def compare_raw_hand_objects(before_path: str, after_path: str) -> int:
    """Compare two raw hand object exports."""
    before = Path(before_path)
    after = Path(after_path)
    if not before.exists() or not after.exists():
        raise FileNotFoundError("Both raw hand object files must exist for comparison")

    before_data = before.read_bytes()
    after_data = after.read_bytes()

    if before_data == after_data:
        print("No differences found between raw hand object exports")
        return 0

    print("Raw hand object exports differ")
    return 1


def verify_hand_invariants(serialized_hand: Dict[str, Any]) -> List[str]:
    """Verify structural expectations for the canonical snapshot."""
    violations: List[str] = []

    hand_details = serialized_hand.get("hand_details")
    if not isinstance(hand_details, Mapping):
        violations.append("hand_details section missing or invalid")
        return violations

    players = serialized_hand.get("players", [])
    seat_numbers = [player.get("seatNo") for player in players if player.get("seatNo") is not None]
    if len(seat_numbers) != len(set(seat_numbers)):
        violations.append("Players do not have unique seat numbers")

    for field, expected_type in _HAND_REQUIRED_TYPES.items():
        value = hand_details.get(field)
        if value in (None, ""):
            violations.append(f"Missing hand_details.{field}")
            continue
        if expected_type is int and not isinstance(value, int):
            violations.append(f"hand_details.{field} should be an integer")
        if expected_type is str and not isinstance(value, str):
            violations.append(f"hand_details.{field} should be a string")

    for player in players:
        for key, value in player.items():
            if value is None:
                continue
            if key in _PLAYER_REQUIRED_TYPES:
                continue
            if _looks_like_money((key,)) and not isinstance(value, int):
                violations.append(f"Player field {key} should be an integer (cents)")

    hand_money_fields = [
        "totalPot",
        "finalPot",
        "street0Pot",
        "street1Pot",
        "street2Pot",
        "street3Pot",
        "street4Pot",
        "rake",
    ]
    for field in hand_money_fields:
        value = hand_details.get(field)
        if value in (None, 0):
            continue
        if not isinstance(value, int):
            violations.append(f"hand_details.{field} should be an integer (cents)")

    actions = serialized_hand.get("actions", [])
    for action in actions:
        for field in ("amount", "amountCalled", "raiseTo"):
            value = action.get(field)
            if value not in (None, 0) and not isinstance(value, int):
                violations.append(f"Action field {field} should be an integer (cents)")

    monetary_fields = [
        ("finalPot", hand_details.get("finalPot")),
        ("rake_total", sum(player.get("rake", 0) or 0 for player in players)),
        ("winnings_total", sum(player.get("winnings", 0) or 0 for player in players)),
    ]
    for name, value in monetary_fields:
        if isinstance(value, float):
            violations.append(f"Monetary field {name} should be an integer")

    # Game-specific invariants
    game_type = hand_details.get("gameType", "").lower()
    base = hand_details.get("base", "").lower()

    # Hold'em/Omaha: Board card validation
    if base in ("hold", "holdem"):
        board_cards = [
            hand_details.get("boardcard1"),
            hand_details.get("boardcard2"),
            hand_details.get("boardcard3"),
            hand_details.get("boardcard4"),
            hand_details.get("boardcard5"),
        ]
        # Count non-None board cards
        board_count = sum(1 for card in board_cards if card is not None and card != 0)

        # Valid board counts: 0 (no flop), 3 (flop), 4 (turn), 5 (river)
        if board_count not in (0, 3, 4, 5):
            violations.append(f"Invalid board card count: {board_count} (expected 0, 3, 4, or 5)")

        # If there's a turn, there must be a flop
        if board_cards[3] and not all(board_cards[0:3]):
            violations.append("Turn card present without complete flop")

        # If there's a river, there must be a turn
        if board_cards[4] and not board_cards[3]:
            violations.append("River card present without turn card")

    # Omaha: Hole cards validation
    if "omaha" in game_type.lower():
        for player in players:
            hole_cards = [
                player.get("card1"),
                player.get("card2"),
                player.get("card3"),
                player.get("card4"),
            ]
            # Count non-None hole cards
            hole_count = sum(1 for card in hole_cards if card is not None and card != 0)

            # Omaha players should have 4 hole cards (or 0 if not shown)
            if hole_count > 0 and hole_count != 4:
                player_name = player.get("playerName", "Unknown")
                violations.append(f"Omaha player {player_name} has {hole_count} hole cards (expected 4)")

    # Action amount validation
    for action in actions:
        action_type = action.get("actionType", "").lower()
        amount = action.get("amount", 0)
        amount_called = action.get("amountCalled", 0)

        # Fold/check should have amount=0
        if action_type in ("fold", "check"):
            if amount and amount != 0:
                violations.append(f"{action_type} action should have amount=0, got {amount}")

        # Call should have amount > 0
        if action_type == "call" and amount <= 0 and amount_called <= 0:
            violations.append(f"Call action should have amount > 0 or amountCalled > 0")

        # Raise should have amount > 0
        if action_type in ("raise", "bet"):
            if amount <= 0 and action.get("raiseTo", 0) <= 0:
                violations.append(f"{action_type} action should have amount > 0 or raiseTo > 0")

    # Rake validation
    total_rake = sum(player.get("rake", 0) or 0 for player in players)
    if total_rake < 0:
        violations.append(f"Total rake cannot be negative: {total_rake}")

    # Winner validation
    total_winnings = sum(player.get("winnings", 0) or 0 for player in players)
    final_pot = hand_details.get("finalPot", 0)
    if final_pot > 0 and total_winnings == 0:
        violations.append(f"Final pot is {final_pot} but no player has winnings")

    violations.extend(validate_snapshot_for_db(serialized_hand))

    return violations


def validate_snapshot_for_db(serialized_hand: Dict[str, Any]) -> List[str]:
    """Check snapshot data against essential database constraints."""
    violations: List[str] = []

    hand_details = serialized_hand.get("hand_details")
    if not isinstance(hand_details, Mapping):
        return ["hand_details section missing or invalid"]

    for field, expected_type in _HAND_REQUIRED_TYPES.items():
        value = hand_details.get(field)
        if value in (None, ""):
            violations.append(f"Missing hand_details.{field}")
            continue
        if expected_type is int and not isinstance(value, int):
            violations.append(f"hand_details.{field} should be an integer")
        if expected_type is str and not isinstance(value, str):
            violations.append(f"hand_details.{field} should be a string")

    players = serialized_hand.get("players", [])
    if not players:
        violations.append("No players present for HandsPlayers insert")
    for player in players:
        for field, expected_type in _PLAYER_REQUIRED_TYPES.items():
            value = player.get(field)
            if value in (None, ""):
                violations.append(f"Missing players[].{field}")
                continue
            if expected_type is int and not isinstance(value, int):
                violations.append(f"players[].{field} should be an integer")
            if expected_type is str and not isinstance(value, str):
                violations.append(f"players[].{field} should be a string")

    actions = serialized_hand.get("actions", [])
    if not actions:
        violations.append("No actions present for HandsActions insert")
    for action in actions:
        for field, expected_type in _ACTION_REQUIRED_TYPES.items():
            value = action.get(field)
            if value in (None, ""):
                violations.append(f"Missing actions[].{field}")
                continue
            if expected_type is int and not isinstance(value, int):
                violations.append(f"actions[].{field} should be an integer")
            if expected_type is str and not isinstance(value, str):
                violations.append(f"actions[].{field} should be a string")

    return violations


def build_db_payload(serialized_hand: Dict[str, Any]) -> Dict[str, Any]:
    """Create a structure that mirrors DB insert payloads for validation."""
    violations = validate_snapshot_for_db(serialized_hand)
    if violations:
        raise ValueError("Snapshot violates database constraints: " + "; ".join(violations))

    hand_details = dict(serialized_hand.get("hand_details", {}))
    hand_details.pop("gametype", None)

    hands_row = {k: v for k, v in hand_details.items() if not isinstance(v, (dict, list))}
    players_rows = [dict(player) for player in serialized_hand.get("players", [])]
    actions_rows = [dict(action) for action in serialized_hand.get("actions", [])]

    return {
        "Hands": hands_row,
        "HandsPlayers": players_rows,
        "HandsActions": actions_rows,
    }


def simulate_db_insert(serialized_hand: Dict[str, Any]) -> List[str]:
    """Simulate database insertions to surface schema issues before real writes."""
    payload = build_db_payload(serialized_hand)
    issues: List[str] = []

    hands_row = payload["Hands"]
    for column in _HANDS_MIN_COLUMNS:
        if column not in hands_row:
            issues.append(f"Hands.{column} is required for insert simulation")

    players_rows = payload["HandsPlayers"]
    for idx, player_row in enumerate(players_rows):
        for column in _HANDS_PLAYERS_MIN_COLUMNS:
            if column not in player_row:
                issues.append(f"HandsPlayers.{column} missing for player index {idx}")

    actions_rows = payload["HandsActions"]
    for idx, action_row in enumerate(actions_rows):
        for column in _HANDS_ACTIONS_MIN_COLUMNS:
            if column not in action_row:
                issues.append(f"HandsActions.{column} missing for action index {idx}")

    return issues
