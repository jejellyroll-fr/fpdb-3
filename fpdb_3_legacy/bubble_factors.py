"""Each preflop tournament decision's bubble factor, stored for the study pack (#446).

A bubble factor says how much more prize equity a player loses by losing an
all-in than they gain by winning it (:func:`fpdb_3_legacy.icm.bubble_factor`).
It needs every remaining player's stack and the payout structure, so it is
only computed where fpdb has both:

- the tournament's payout structure is known (:mod:`fpdb_3_legacy.tourney_payouts`);
- its field fits at one table, as in a sit-and-go or a Spin. In a multi-table
  tournament the other tables' stacks are not in the hand history, and a factor
  computed from this table alone would be wrong, so none is stored. A field of
  unknown size is treated the same way.

Each preflop decision is priced against one opponent, from the stacks at the
start of the hand:

- facing an action, the player who made it (the shover, the opener...);
- first in, the player still to act who makes the all-in most expensive: the
  highest factor among them.

The rows are derived data, replaced a tournament at a time by
:func:`refresh_tourney` whenever its hands, its results or its structure change.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from fpdb_3_legacy import icm, tourney_payouts
from fpdb_3_legacy.bubble_factor_buckets import BUBBLE_FACTOR_CAP, BUBBLE_FACTOR_SCALE
from fpdb_3_legacy.loggingFpdb import get_logger

__all__ = ["decision_bubble_factors", "refresh_all", "refresh_tourney", "refresh_tourneys"]

log = get_logger("bubble_factors")

# (action number, player, the player they faced or None)
Decision = tuple[int, str, str | None]


def _stored(factor: float) -> int:
    if factor != factor or factor * BUBBLE_FACTOR_SCALE >= BUBBLE_FACTOR_CAP:  # NaN, inf or huge
        return BUBBLE_FACTOR_CAP
    return max(1, round(factor * BUBBLE_FACTOR_SCALE))


def decision_bubble_factors(
    stacks: Mapping[str, float],
    decisions: Sequence[Decision],
    payouts: Sequence[float],
) -> list[tuple[int, str, int]]:
    """One hand's preflop decisions priced: (action number, opponent, stored factor).

    ``decisions`` are in action order. A decision without a priceable opponent is left out.
    """
    first_act: dict[str, int] = {}
    for action_no, player, _faced in decisions:
        first_act.setdefault(player, action_no)
    priced = []
    for action_no, player, faced in decisions:
        if stacks.get(player, 0) <= 0:
            continue
        if faced:
            opponents = [faced]
        else:
            opponents = [name for name, first in first_act.items() if first > action_no and name != player]
        best: tuple[float, str] | None = None
        for opponent in opponents:
            if opponent == player or stacks.get(opponent, 0) <= 0:
                continue
            try:
                factor = icm.bubble_factor(stacks, payouts, player, opponent)
            except icm.ICMError:
                continue
            if best is None or factor > best[0]:
                best = (factor, opponent)
        if best is not None:
            priced.append((action_no, best[1], _stored(best[0])))
    return priced


def _rows(db: Any, name: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
    cursor = db.get_cursor()
    cursor.execute(db.sql.query[name], params)
    return list(cursor.fetchall())


def _priceable_payouts(db: Any, tourney_id: int) -> list[float] | None:
    """The tournament's payouts when its whole field fits at one table; None otherwise."""
    lookup = tourney_payouts.payouts_for_tourney(db, tourney_id)
    if lookup.payouts is None:
        return None
    entries = tourney_payouts.tourney_facts(db, tourney_id).entries
    seats = _rows(db, "selectTourneyMaxSeats", (tourney_id,))
    max_seats = int(seats[0][0]) if seats and seats[0][0] else 0
    if not entries or not max_seats or entries > max_seats:
        return None
    return lookup.payouts.as_money()


def refresh_tourney(db: Any, tourney_id: int) -> int:
    """Replace the tournament's stored bubble factors; how many decisions were priced."""
    cursor = db.get_cursor()
    cursor.execute(db.sql.query["deleteActionBubbleFactors"], (tourney_id,))
    payouts = _priceable_payouts(db, tourney_id)
    stored = 0
    if payouts is not None:
        stacks: dict[int, dict[str, float]] = {}
        for hand_id, name, start in _rows(db, "selectTourneyStartStacks", (tourney_id,)):
            stacks.setdefault(int(hand_id), {})[str(name)] = float(start or 0)
        decisions: dict[int, list[Decision]] = {}
        for hand_id, action_no, name, faced in _rows(db, "selectTourneyPreflopDecisions", (tourney_id,)):
            decisions.setdefault(int(hand_id), []).append((int(action_no), str(name), str(faced) if faced else None))
        insert = db.sql.query["insertActionBubbleFactor"]
        for hand_id, hand_decisions in decisions.items():
            for action_no, opponent, factor in decision_bubble_factors(
                stacks.get(hand_id, {}), hand_decisions, payouts
            ):
                cursor.execute(insert, (hand_id, action_no, tourney_id, opponent[:32], factor))
                stored += 1
    db.commit()
    return stored


def refresh_tourneys(db: Any, tourney_ids: Iterable[int]) -> int:
    """Refresh each tournament in turn; one that fails is logged and rolled back, never fatal."""
    stored = 0
    for tourney_id in sorted({int(tid) for tid in tourney_ids if tid is not None}):
        try:
            stored += refresh_tourney(db, tourney_id)
        except Exception:  # noqa: BLE001 - derived data: the import or the dialog must not fail on it
            log.warning("Bubble factors for tournament %s could not be refreshed", tourney_id, exc_info=True)
            db.rollback()
    return stored


def refresh_all(db: Any) -> int:
    """Refresh every tournament that has hands: the backfill."""
    return refresh_tourneys(db, [row[0] for row in _rows(db, "selectTourneysWithHands", ())])
