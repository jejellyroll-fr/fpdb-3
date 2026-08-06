"""Compare a captured SwC hand against the text history the client wrote for it.

SwC writes text hand histories for some game families and not others -- Stud,
draw games, Drawmaha, mixed games and OFC arrive only over the wire. Where both
exist, the two paths describe the same hand and must agree; a disagreement means
the capture decoder drifted from the room's own record.

This module is the comparison itself, kept away from any test fixture so it can
be pointed at real archives from the CLI as well as run in CI.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

# Money is compared at the precision the room reports, not exactly: the text
# history rounds to the table currency while the capture carries integer units.
MONEY_TOLERANCE = Decimal("0.01")


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError):
        return None


def _seats(hand: Any) -> dict[str, int]:
    """Map player name -> seat number, from either a Hand or a captured dict."""
    players = getattr(hand, "players", None)
    if players is None and isinstance(hand, dict):
        players = hand.get("players", [])
    seats: dict[str, int] = {}
    for player in players or []:
        if isinstance(player, dict):
            name, seat = player.get("name"), player.get("seat", player.get("seat_idx"))
        else:
            seat, name = player[0], player[1]
        if name is not None and seat is not None:
            seats[str(name)] = int(seat)
    return seats


def _board(hand: Any) -> list[str]:
    board = getattr(hand, "board", None)
    if board is None and isinstance(hand, dict):
        board = hand.get("board")
    if isinstance(board, dict):
        cards: list[str] = []
        for street in ("FLOP", "TURN", "RIVER"):
            cards.extend(board.get(street) or [])
        return [str(card) for card in cards]
    return [str(card) for card in board or []]


def _collected(hand: Any) -> dict[str, Decimal]:
    collectees = getattr(hand, "collectees", None)
    if collectees is None and isinstance(hand, dict):
        collectees = hand.get("collectees", {})
    result: dict[str, Decimal] = {}
    for name, amount in (collectees or {}).items():
        parsed = _decimal(amount)
        if parsed is not None:
            result[str(name)] = parsed
    return result


def _attr(hand: Any, name: str, *aliases: str) -> Any:
    for candidate in (name, *aliases):
        value = getattr(hand, candidate, None)
        if value is None and isinstance(hand, dict):
            value = hand.get(candidate)
        if value is not None:
            return value
    return None


def compare_hands(text_hand: Any, captured_hand: Any) -> list[str]:
    """Return the discrepancies between the two views of one hand.

    An empty list means the capture agrees with the room's own text history on
    everything that changes the meaning of an imported hand: which hand it is,
    who sat where, what came down, and who got paid.
    """
    problems: list[str] = []

    text_id = _attr(text_hand, "handid", "hand_id")
    captured_id = _attr(captured_hand, "handid", "hand_id")
    if str(text_id) != str(captured_id):
        problems.append(f"hand id: text {text_id!r} != capture {captured_id!r}")

    text_seats, captured_seats = _seats(text_hand), _seats(captured_hand)
    if set(text_seats) != set(captured_seats):
        only_text = sorted(set(text_seats) - set(captured_seats))
        only_capture = sorted(set(captured_seats) - set(text_seats))
        problems.append(f"players: only in text {only_text}, only in capture {only_capture}")
    else:
        for name, seat in sorted(text_seats.items()):
            if captured_seats[name] != seat:
                problems.append(f"seat of {name}: text {seat} != capture {captured_seats[name]}")

    text_board, captured_board = _board(text_hand), _board(captured_hand)
    if text_board != captured_board:
        problems.append(f"board: text {text_board} != capture {captured_board}")

    text_pot, captured_pot = _decimal(_attr(text_hand, "totalpot")), _decimal(_attr(captured_hand, "totalpot"))
    if text_pot is not None and captured_pot is not None and abs(text_pot - captured_pot) > MONEY_TOLERANCE:
        problems.append(f"total pot: text {text_pot} != capture {captured_pot}")

    text_won, captured_won = _collected(text_hand), _collected(captured_hand)
    for name in sorted(set(text_won) | set(captured_won)):
        text_amount, captured_amount = text_won.get(name), captured_won.get(name)
        if text_amount is None or captured_amount is None:
            problems.append(f"winnings of {name}: text {text_amount}, capture {captured_amount}")
        elif abs(text_amount - captured_amount) > MONEY_TOLERANCE:
            problems.append(f"winnings of {name}: text {text_amount} != capture {captured_amount}")

    return problems
