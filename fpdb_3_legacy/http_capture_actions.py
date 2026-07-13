"""Conservative action reconstruction for snapshot-based HTTP captures."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _money(value: Any) -> str:
    normalized = _decimal(value).normalize()
    return format(normalized, "f")


def _players_by_seat(hand_data: dict[str, Any]) -> dict[int, str]:
    players = {}
    for player in hand_data.get("players", []):
        if player.get("seat_idx") is not None and player.get("name"):
            players[int(player["seat_idx"])] = player["name"]
    return players


def infer_snapshot_street(hand_data: dict[str, Any], step: dict[str, Any]) -> str:
    """Infer the FPDB street for a normalized snapshot step when safe."""

    game = hand_data.get("game", {})
    base = game.get("base") or hand_data.get("gametype", {}).get("base")
    if base == "hold":
        board_len = len(step.get("board", []))
        if board_len == 0:
            return "PREFLOP"
        if board_len == 3:
            return "FLOP"
        if board_len == 4:
            return "TURN"
        if board_len >= 5:
            return "RIVER"
    return "UNKNOWN"


def _classify_single_commit(previous_step: dict[str, Any], step: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any] | None:
    previous_bets = previous_step.get("bets", {})
    player = candidate.get("player")
    if not player:
        return None

    prev_bet = _decimal(candidate.get("from", previous_bets.get(player, 0)))
    curr_bet = _decimal(candidate.get("to", 0))
    amount_delta = _decimal(candidate.get("amount_delta", 0))
    previous_max = max((_decimal(amount) for amount in previous_bets.values()), default=Decimal("0"))

    if amount_delta <= 0 or curr_bet <= prev_bet:
        return None

    action = {
        "street": step.get("street", "UNKNOWN"),
        "player": player,
        "amount": _money(amount_delta),
        "source": "snapshot_single_commit_delta",
        "fpdb_action": True,
    }

    if previous_max == 0:
        return {**action, "type": "bets"}
    if prev_bet < previous_max and curr_bet == previous_max:
        return {**action, "type": "calls"}
    if curr_bet > previous_max:
        return {**action, "type": "raises", "to": _money(curr_bet)}
    return None


def _reconstruct_single_commit_action(previous_step: dict[str, Any], step: dict[str, Any]) -> tuple[dict[str, Any] | None, set[int]]:
    candidates = step.get("diff", {}).get("candidates", [])
    committed = [(idx, candidate) for idx, candidate in enumerate(candidates) if candidate.get("type") == "committed_delta"]
    structural = [candidate for candidate in candidates if candidate.get("type") in {"board_delta", "cards_delta"}]
    if len(committed) != 1 or structural:
        return None, set()

    idx, candidate = committed[0]
    action = _classify_single_commit(previous_step, step, candidate)
    if not action:
        return None, set()
    consumed = {idx}
    consumed.update(_matching_stack_delta_indexes(candidates, candidate.get("player"), -_decimal(candidate.get("amount_delta", 0))))
    return action, consumed


def _matching_stack_delta_indexes(candidates: list[dict[str, Any]], player: str | None, amount_delta: Decimal) -> set[int]:
    consumed: set[int] = set()
    if not player:
        return consumed
    for index, candidate in enumerate(candidates):
        if candidate.get("type") != "stack_delta" or candidate.get("player") != player:
            continue
        if _decimal(candidate.get("amount_delta", 0)) == amount_delta:
            consumed.add(index)
    return consumed


def _reconstruct_check_action(
    previous_step: dict[str, Any],
    step: dict[str, Any],
    players_by_seat: dict[int, str],
) -> tuple[dict[str, Any] | None, set[int]]:
    candidates = step.get("diff", {}).get("candidates", [])
    if len(candidates) != 1 or candidates[0].get("type") != "turn_delta":
        return None, set()
    if previous_step.get("street") != step.get("street"):
        return None, set()

    previous_seat = candidates[0].get("from")
    if previous_seat is None or previous_seat == -1:
        return None, set()
    try:
        player = players_by_seat[int(previous_seat)]
    except (KeyError, TypeError, ValueError):
        return None, set()

    previous_bets = previous_step.get("bets", {})
    player_bet = _decimal(previous_bets.get(player, 0))
    previous_max = max((_decimal(amount) for amount in previous_bets.values()), default=Decimal("0"))
    if player_bet != previous_max:
        return None, set()

    return (
        {
            "street": step.get("street", "UNKNOWN"),
            "player": player,
            "type": "checks",
            "source": "snapshot_turn_delta_no_commit",
            "fpdb_action": True,
        },
        {0},
    )


def _reconstruct_fold_action(previous_step: dict[str, Any], step: dict[str, Any]) -> tuple[dict[str, Any] | None, set[int]]:
    candidates = step.get("diff", {}).get("candidates", [])
    fold_candidates = [(idx, candidate) for idx, candidate in enumerate(candidates) if candidate.get("type") == "fold_delta"]
    structural = [candidate for candidate in candidates if candidate.get("type") in {"board_delta", "cards_delta"}]
    committed = [candidate for candidate in candidates if candidate.get("type") == "committed_delta"]
    if len(fold_candidates) != 1 or structural or committed:
        return None, set()
    if previous_step.get("street") != step.get("street"):
        return None, set()

    idx, candidate = fold_candidates[0]
    player = candidate.get("player")
    if not player:
        return None, set()
    return (
        {
            "street": step.get("street", "UNKNOWN"),
            "player": player,
            "type": "folds",
            "source": "snapshot_fold_delta",
            "fpdb_action": True,
        },
        {idx},
    )


def _reconstruct_street_transition_call(previous_step: dict[str, Any], step: dict[str, Any]) -> tuple[dict[str, Any] | None, set[int]]:
    candidates = step.get("diff", {}).get("candidates", [])
    board_candidates = [(idx, candidate) for idx, candidate in enumerate(candidates) if candidate.get("type") == "board_delta"]
    pot_candidates = [(idx, candidate) for idx, candidate in enumerate(candidates) if candidate.get("type") == "pot_delta"]
    stack_candidates = [(idx, candidate) for idx, candidate in enumerate(candidates) if candidate.get("type") == "stack_delta"]
    committed = [candidate for candidate in candidates if candidate.get("type") == "committed_delta"]
    if committed or len(board_candidates) != 1 or len(pot_candidates) != 1 or len(stack_candidates) != 1:
        return None, set()
    if previous_step.get("street") == step.get("street"):
        return None, set()
    if not board_candidates[0][1].get("added"):
        return None, set()
    if _decimal(pot_candidates[0][1].get("amount_delta", 0)) <= 0:
        return None, set()

    stack_idx, stack_candidate = stack_candidates[0]
    amount = -_decimal(stack_candidate.get("amount_delta", 0))
    player = stack_candidate.get("player")
    previous_bets = previous_step.get("bets", {})
    previous_max = max((_decimal(value) for value in previous_bets.values()), default=Decimal("0"))
    previous_player_bet = _decimal(previous_bets.get(player, 0))
    owed = previous_max - previous_player_bet
    if not player or amount <= 0 or owed <= 0 or amount != owed:
        return None, set()

    consumed = {stack_idx, board_candidates[0][0], pot_candidates[0][0]}
    return (
        {
            "street": previous_step.get("street", "UNKNOWN"),
            "player": player,
            "type": "calls",
            "amount": _money(amount),
            "source": "snapshot_street_transition_call",
            "fpdb_action": True,
        },
        consumed,
    )


def _reconstruct_collections(previous_step: dict[str, Any], step: dict[str, Any]) -> tuple[list[dict[str, Any]], set[int]]:
    candidates = step.get("diff", {}).get("candidates", [])
    pot_candidates = [(idx, candidate) for idx, candidate in enumerate(candidates) if candidate.get("type") == "pot_delta"]
    stack_candidates = [(idx, candidate) for idx, candidate in enumerate(candidates) if candidate.get("type") == "stack_delta"]
    if len(pot_candidates) != 1:
        return [], set()

    pot_idx, pot_delta = pot_candidates[0]
    previous_pot = _decimal(pot_delta.get("from", previous_step.get("pot", 0)))
    current_pot = _decimal(pot_delta.get("to", step.get("pot", 0)))
    if previous_pot <= 0 or current_pot != 0:
        return [], set()

    collections = []
    consumed = {pot_idx}
    for idx, candidate in stack_candidates:
        amount = _decimal(candidate.get("amount_delta", 0))
        player = candidate.get("player")
        if amount > 0 and player:
            consumed.add(idx)
            collections.append(
                {
                    "player": player,
                    "pot": _money(amount),
                    "street": previous_step.get("street", step.get("street", "UNKNOWN")),
                    "source": "snapshot_pot_settlement_delta",
                    "step_num": step.get("step_num"),
                }
            )
    if collections:
        consumed.update(
            idx
            for idx, candidate in enumerate(candidates)
            if candidate.get("type") == "turn_delta" and _decimal(candidate.get("to", 0)) > _decimal(candidate.get("from", 0))
        )
    return collections, consumed


def _is_action_evidence(candidate: dict[str, Any], previous_step: dict[str, Any], players_by_seat: dict[int, str]) -> bool:
    candidate_type = candidate.get("type")
    if candidate_type in {"committed_delta", "fold_delta", "unclassified_initial_commit"}:
        return True
    if candidate_type == "stack_delta":
        return _decimal(candidate.get("amount_delta", 0)) < 0
    if candidate_type == "turn_delta":
        previous_seat = candidate.get("from")
        if previous_seat is None or previous_seat == -1:
            return False
        try:
            player = players_by_seat[int(previous_seat)]
        except (KeyError, TypeError, ValueError):
            return False
        previous_bets = previous_step.get("bets", {})
        player_bet = _decimal(previous_bets.get(player, 0))
        previous_max = max((_decimal(amount) for amount in previous_bets.values()), default=Decimal("0"))
        return player_bet < previous_max
    return False


def reconstruct_snapshot_actions(hand_data: dict[str, Any]) -> None:
    """Populate safe actions and evidence from normalized snapshot steps.

    Only non-ambiguous blind postings become FPDB-shaped actions for now.
    Other snapshot deltas are preserved as evidence for future reconstruction.
    """

    actions: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    state_evidence: list[dict[str, Any]] = []
    collections: list[dict[str, Any]] = []
    steps = hand_data.get("steps", [])
    players_by_seat = _players_by_seat(hand_data)

    if steps:
        first_step = steps[0]
        bets = first_step.get("bets", {})
        blind_seats = (
            ("small blind", hand_data.get("sb_idx")),
            ("big blind", hand_data.get("bb_idx")),
        )
        blind_players = set()
        for blind_type, seat_idx in blind_seats:
            if seat_idx is None or seat_idx == -1:
                continue
            player = players_by_seat.get(int(seat_idx))
            amount = _decimal(bets.get(player, 0)) if player else Decimal("0")
            if player and amount > 0:
                actions.append(
                    {
                        "street": "BLINDSANTES",
                        "player": player,
                        "type": blind_type,
                        "amount": _money(amount),
                        "source": "snapshot_blind_index",
                        "fpdb_action": True,
                    }
                )
                blind_players.add(player)

        for player, amount in bets.items():
            amount = _decimal(amount)
            if amount > 0 and player not in blind_players:
                evidence.append(
                    {
                        "type": "unclassified_initial_commit",
                        "street": first_step.get("street", "UNKNOWN"),
                        "player": player,
                        "amount": _money(amount),
                        "step_num": first_step.get("step_num"),
                    }
                )

    for index, step in enumerate(steps[1:], start=1):
        previous_step = steps[index - 1]
        action, consumed_candidate_indexes = _reconstruct_single_commit_action(previous_step, step)
        if not action:
            action, consumed_candidate_indexes = _reconstruct_check_action(previous_step, step, players_by_seat)
        if not action:
            action, consumed_candidate_indexes = _reconstruct_fold_action(previous_step, step)
        if not action:
            action, consumed_candidate_indexes = _reconstruct_street_transition_call(previous_step, step)
        if action:
            actions.append(action)

        step_collections, consumed_collection_indexes = _reconstruct_collections(previous_step, step)
        collections.extend(step_collections)
        consumed_candidate_indexes.update(consumed_collection_indexes)

        for candidate_index, candidate in enumerate(step.get("diff", {}).get("candidates", [])):
            if candidate_index in consumed_candidate_indexes:
                continue
            if candidate.get("type") in {"committed_delta", "stack_delta", "turn_delta", "board_delta", "cards_delta", "fold_delta", "pot_delta"}:
                item = {"step_num": step.get("step_num"), "street": step.get("street", "UNKNOWN"), **candidate}
                if _is_action_evidence(candidate, previous_step, players_by_seat):
                    evidence.append(item)
                else:
                    state_evidence.append(item)

    hand_data["actions"] = actions
    hand_data["action_evidence"] = evidence
    hand_data["state_evidence"] = state_evidence
    if collections:
        hand_data["collections"] = collections
    status = "none"
    if actions and not evidence:
        status = "complete"
    elif actions or evidence:
        status = "partial"
    hand_data.setdefault("metadata", {})["action_reconstruction"] = {
        "status": status,
        "safe_actions": len(actions),
        "evidence_items": len(evidence),
        "state_evidence_items": len(state_evidence),
    }
