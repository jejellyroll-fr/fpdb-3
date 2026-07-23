"""Conservative diff helpers for HTTP snapshot-based capture."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def diff_snapshot_steps(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    """Return conservative deltas between two normalized snapshot steps.

    These deltas are evidence for future action reconstruction. They are not
    treated as ordered FPDB actions yet.
    """

    if not previous:
        return {"kind": "initial_snapshot", "candidates": []}

    candidates = []
    previous_bets = previous.get("bets", {})
    current_bets = current.get("bets", {})
    previous_stacks = previous.get("stacks", {})
    current_stacks = current.get("stacks", {})
    previous_folded = set(previous.get("folded", []))
    current_folded = set(current.get("folded", []))
    previous_pot = _decimal(previous.get("pot", 0))
    current_pot = _decimal(current.get("pot", 0))

    for player in sorted(set(previous_bets) | set(current_bets)):
        prev_bet = _decimal(previous_bets.get(player, 0))
        curr_bet = _decimal(current_bets.get(player, 0))
        bet_delta = curr_bet - prev_bet
        if bet_delta > 0:
            candidates.append(
                {
                    "type": "committed_delta",
                    "player": player,
                    "amount_delta": str(bet_delta),
                    "from": str(prev_bet),
                    "to": str(curr_bet),
                }
            )

    for player in sorted(set(previous_stacks) | set(current_stacks)):
        prev_stack = _decimal(previous_stacks.get(player, 0))
        curr_stack = _decimal(current_stacks.get(player, 0))
        stack_delta = curr_stack - prev_stack
        if stack_delta:
            candidates.append(
                {
                    "type": "stack_delta",
                    "player": player,
                    "amount_delta": str(stack_delta),
                    "from": str(prev_stack),
                    "to": str(curr_stack),
                }
            )

    previous_board = previous.get("board", [])
    current_board = current.get("board", [])
    if current_board != previous_board:
        candidates.append(
            {
                "type": "board_delta",
                "from": previous_board,
                "to": current_board,
                "added": current_board[len(previous_board) :]
                if current_board[: len(previous_board)] == previous_board
                else [],
            }
        )

    previous_placed = previous.get("placed", {})
    current_placed = current.get("placed", {})
    for player in sorted(set(previous_placed) | set(current_placed)):
        if previous_placed.get(player) != current_placed.get(player):
            candidates.append(
                {
                    "type": "cards_delta",
                    "player": player,
                    "from": previous_placed.get(player),
                    "to": current_placed.get(player),
                }
            )

    if previous.get("ts") != current.get("ts"):
        candidates.append({"type": "turn_delta", "from": previous.get("ts"), "to": current.get("ts")})

    for player in sorted(current_folded - previous_folded):
        candidates.append({"type": "fold_delta", "player": player, "from": False, "to": True})

    pot_delta = current_pot - previous_pot
    if pot_delta:
        candidates.append(
            {
                "type": "pot_delta",
                "amount_delta": str(pot_delta),
                "from": str(previous_pot),
                "to": str(current_pot),
            }
        )

    return {"kind": "snapshot_diff", "candidates": candidates}
