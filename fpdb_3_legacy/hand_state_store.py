"""Persistence of the postflop hand state (#302).

The classifier in :mod:`fpdb_3_legacy.hand_state` says what a known hand *is*
on a street. This module gives that answer a table: ``HandStates`` holds one
row per *classified* decision, keyed ``(handId, actionNo)`` exactly like
``HandsActions`` and ``HandsSituations``, so the three read side by side and a
drill-down can move between them without a second key.

Two things the table deliberately does not contain:

* **A row for every decision.** Only a postflop decision whose actor's two cards
  are known is classified -- a hand state needs a board to be a state at all,
  and unknown cards are never classified (the acceptance criterion of #302).
  Preflop decisions and players who never showed have no row, and "no row" is
  how a query says so: it is one fact, not a bucket called "unknown". The
  composition report counts them separately for that reason.
* **The cards.** The board is already stored on the situation row it joins to
  and the hole cards on ``HandsPlayers``; copying them here would create a
  second version of the same fact that could disagree.

``enumerate_hand_states`` is the single derivation, and it takes anything with
``player`` / ``street_name`` / ``board`` / ``game``: the importer passes the
situations it just built, the in-place rebuild (#305) passes the stored rows
read back from the database, and both run the same rules over the same inputs.
Every row is stamped with ``analytics_lifecycle.EXTRACTOR_VERSIONS["hand_strength"]``
so a rule change is visible per row.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from .hand_state import (
    BLOCKER_BITS,
    BOARD_CARDS_BY_STREET,
    DRAW_BITS,
    EvaluatorUnavailable,
    HandState,
    HandStateError,
    blockers_mask,
    classify_known_cards,
    draws_mask,
    mask_names,
)

# The stored columns, in store order. handId and playerId are supplied by the
# caller (they key the join). The names are the classification's own, in the
# camelCase the event and situation columns use.
STATE_FIELD_TO_COLUMN: Final[dict[str, str]] = {
    "action_no": "actionNo",
    "street": "street",
    "street_name": "streetName",
    "made_hand": "madeHand",
    "made_hand_rank": "madeHandRank",
    "made_hand_label": "madeHandLabel",
    "pair_detail": "pairDetail",
    "draws_mask": "drawsMask",
    "nutness": "nutness",
    "nutness_beats": "nutnessBeats",
    "nutness_holdings": "nutnessHoldings",
    "blockers_mask": "blockersMask",
}

# Columns after handId/playerId, in store order -- excluding the stateVersion
# stamp, which every writer appends last.
HAND_STATE_COLUMNS: Final[tuple[str, ...]] = tuple(STATE_FIELD_TO_COLUMN.values())

@dataclass(frozen=True)
class DecisionState:
    """One decision's hand state: the situation it belongs to, and the answer.

    ``street`` and ``street_name`` are the situation's own (the street numbers
    the actions and situations are keyed by), so a state row and the decision it
    describes cannot disagree about which street was being played.
    """

    hand_id: int
    action_no: int
    player: str
    street: int
    street_name: str
    state: HandState

    def as_dict(self) -> dict[str, Any]:
        return {
            "hand_id": self.hand_id,
            "action_no": self.action_no,
            "player": self.player,
            "street": self.street,
            "street_name": self.street_name,
            "state": self.state.as_dict(),
        }


def _two_cards(cards: Any) -> tuple[Any, Any] | None:
    """A player's two cards, from a stats row or from a bare sequence.

    The importer holds the ``HandsPlayers`` stats dict (``card1``/``card2`` are
    the encoded ints the database stores); the rebuild holds the same ints read
    straight back out. Both are accepted, as are card strings and the ``"0x"``
    placeholders an unknown card is spelled with -- the classifier's own
    normalization rejects the placeholders, which is what makes an unknown hand
    unknown instead of a made-up card.
    """
    if isinstance(cards, Mapping):
        return cards.get("card1"), cards.get("card2")
    if isinstance(cards, (str, bytes)) or not isinstance(cards, Sequence):
        return None
    values = list(cards)[:2]
    if len(values) != 2:
        return None
    return values[0], values[1]


def enumerate_hand_states(
    situations: Sequence[Any],
    hole_cards: Mapping[str, Any],
) -> list[DecisionState]:
    """The classified decisions of a hand, in situation order.

    A situation is classified when its game is Hold'em, its board holds cards
    for the street it names, and its actor's two cards are known. Everything
    else is left out -- there is no state to store, and storing a placeholder
    would make a distribution over states count hands that were never seen.
    """
    out: list[DecisionState] = []
    for situation in situations:
        if getattr(situation, "game", "holdem") != "holdem":
            continue
        board = tuple(getattr(situation, "board", ()) or ())
        street = str(getattr(situation, "street_name", "") or "").lower()
        if street not in BOARD_CARDS_BY_STREET or len(board) < BOARD_CARDS_BY_STREET[street]:
            continue
        two = _two_cards(hole_cards.get(getattr(situation, "player", "")))
        if two is None:
            continue
        try:
            state = classify_known_cards(two, board[: BOARD_CARDS_BY_STREET[street]])
        except EvaluatorUnavailable:
            # A missing evaluator is an environment fault, not a hand that
            # cannot be classified: re-derived rows for a whole database are
            # worth nothing if the reason is "no evaluator", and producing
            # none of them silently would hide it.
            raise
        except HandStateError:
            # Duplicated cards, or a board that is not a board: this decision
            # has no state, and a row saying otherwise would be a lie.
            continue
        if state is None:
            continue
        out.append(
            DecisionState(
                hand_id=int(getattr(situation, "hand_id", 0) or 0),
                action_no=int(getattr(situation, "action_no", 0) or 0),
                player=str(getattr(situation, "player", "")),
                street=int(getattr(situation, "street", 0) or 0),
                street_name=street,
                state=state,
            ),
        )
    return out


def state_row(decision: DecisionState, state_version: int) -> tuple[list[str], list[Any]]:
    """One classified decision as (column names, values), for a bulk append."""
    state = decision.state
    record: dict[str, Any] = {
        "action_no": decision.action_no,
        "street": decision.street,
        "street_name": decision.street_name,
        "made_hand": state.made_hand,
        "made_hand_rank": state.made_hand_rank,
        "made_hand_label": state.made_hand_label,
        "pair_detail": state.pair_detail,
        "draws_mask": draws_mask(state.draws),
        "nutness": state.nutness,
        "nutness_beats": state.beats,
        "nutness_holdings": state.holdings,
        "blockers_mask": blockers_mask(state.blockers),
    }
    columns = [*HAND_STATE_COLUMNS, "stateVersion"]
    values = [record.get(field) for field in STATE_FIELD_TO_COLUMN]
    return columns, [*values, int(state_version)]


def bulk_rows(
    hand_id: int,
    player_ids: Mapping[str, int],
    decisions: Sequence[DecisionState],
    state_version: int,
) -> list[list[Any]]:
    """Rows for store_hand_states, in column order, one per classified decision.

    A player the id map does not know (a malformed hand) drops the row: the
    state names a decision by a player who must exist in ``Players``.
    """
    rows: list[list[Any]] = []
    for decision in decisions:
        player_id = player_ids.get(decision.player)
        if player_id is None:
            continue
        _columns, values = state_row(decision, state_version)
        rows.append([hand_id, player_id, *values])
    return rows


def decode_state_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """One read-back row with its masks turned back into names.

    A row may come from SQLite (mask as an int, ``pairDetail`` as ``None``) or
    PostgreSQL; both normalize to the same shapes here, so the callers above the
    table do not branch per backend. ``draws`` and ``blockers`` are the names of
    the mask bits -- the same vocabulary the classifier uses, read back through
    the same bit maps.
    """
    out = dict(row)
    out["draws"] = list(mask_names(int(out.get("drawsMask") or 0), DRAW_BITS))
    out["blockers"] = list(mask_names(int(out.get("blockersMask") or 0), BLOCKER_BITS))
    for column in ("nutnessBeats", "nutnessHoldings", "madeHandRank"):
        if out.get(column) is not None:
            out[column] = int(out[column])
    return out


__all__ = [
    "BOARD_CARDS_BY_STREET",
    "HAND_STATE_COLUMNS",
    "STATE_FIELD_TO_COLUMN",
    "DecisionState",
    "bulk_rows",
    "decode_state_row",
    "enumerate_hand_states",
    "state_row",
]
