"""The tournament graph's ICM line: results with the all-in luck taken out, in prize equity (#446).

The profit line says what each tournament paid. Part of that is how the
all-ins ran: a hand that held 80% and lost cost prize equity the decision did
not. For each all-in the replayer can price (see :mod:`fpdb_3_legacy.hand_icm`),
the luck is the prize equity the hand actually moved less its ICM $EV; this
line is the profit with that luck taken out.

It adjusts only what is priced. A tournament without a known payout structure,
or an all-in the pricing refuses (multiway, a hand not shown, a multi-table
field...), keeps its actual result, and the line says how many of the all-ins
it priced -- a line adjusted for 3 all-ins out of 40 is mostly the profit line.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from typing import Any

from fpdb_3_legacy import tourney_payouts
from fpdb_3_legacy.hand_icm import icm_with_payouts
from fpdb_3_legacy.loggingFpdb import get_logger

__all__ = ["IcmLine", "allin_hands", "icm_line"]

log = get_logger("tourney_icm_line")

# (hand id, player, payouts, field size) -> the player's luck in that hand, or None when it is not priced.
LuckCache = MutableMapping[tuple[int, str, tuple[float, ...], int | None], float | None]


@dataclass(frozen=True)
class IcmLine:
    """The cumulative ICM-adjusted results, and how much of them is priced."""

    values: tuple[float, ...]  # one per tournament, in the payouts' currency units
    priced: int  # the player's all-ins priced
    allins: int  # the player's all-ins found in these tournaments


def allin_hands(db: Any, player_ids: Iterable[int]) -> dict[int, list[tuple[int, str]]]:
    """Each tournament's hands where one of ``player_ids`` saw a showdown after an all-in: (hand id, name)."""
    hands: dict[int, list[tuple[int, str]]] = {}
    cursor = db.get_cursor()
    for player_id in player_ids:
        cursor.execute(db.sql.query["selectTourneyAllInHands"], (int(player_id),))
        for tourney_id, hand_id, name in cursor.fetchall():
            hands.setdefault(int(tourney_id), []).append((int(hand_id), str(name)))
    return hands


def _tourney_luck(
    db: Any,
    tourney_id: int,
    hands: Sequence[tuple[int, str]],
    load_hand: Callable[[int], Any],
    cache: LuckCache,
    equity_fn: Callable[..., Any] | None,
) -> tuple[float, int]:
    """The player's all-in luck in one tournament, and how many of its all-ins were priced."""
    lookup = tourney_payouts.payouts_for_tourney(db, tourney_id)
    if lookup.payouts is None:
        return 0.0, 0
    payouts = tuple(lookup.payouts.as_money())
    field_size = tourney_payouts.tourney_facts(db, tourney_id).entries
    luck, priced = 0.0, 0
    for hand_id, player in hands:
        key = (hand_id, player, payouts, field_size)
        if key not in cache:
            cache[key] = _hand_luck(load_hand(hand_id), player, payouts, field_size, equity_fn)
        hand_luck = cache[key]
        if hand_luck is not None:
            luck += hand_luck
            priced += 1
    return luck, priced


def _hand_luck(
    hand: Any,
    player: str,
    payouts: Sequence[float],
    field_size: int | None,
    equity_fn: Callable[..., Any] | None,
) -> float | None:
    if hand is None:
        return None
    allin = icm_with_payouts(hand, payouts, field_size, equity_fn=equity_fn).allin
    if allin is None or player not in allin.players:
        return None
    return allin.icm_result[player] - allin.icm_ev[player]


def icm_line(
    db: Any,
    results: Sequence[tuple[int, float]],
    hands: Mapping[int, Sequence[tuple[int, str]]],
    load_hand: Callable[[int], Any],
    *,
    cache: LuckCache | None = None,
    equity_fn: Callable[..., Any] | None = None,
) -> IcmLine:
    """The cumulative profit of ``results`` ((tournament id, profit in currency units), in graph order)
    with the luck of every priced all-in in ``hands`` (from :func:`allin_hands`) taken out.

    ``load_hand`` rebuilds a stored hand from its id (``Hand.hand_factory``), or None when it cannot.
    """
    cache = {} if cache is None else cache
    values: list[float] = []
    total, priced, allins = 0.0, 0, 0
    for tourney_id, profit in results:
        tourney_hands = hands.get(tourney_id, ())
        luck, tourney_priced = 0.0, 0
        if tourney_hands:
            try:
                luck, tourney_priced = _tourney_luck(db, tourney_id, tourney_hands, load_hand, cache, equity_fn)
            except Exception:  # noqa: BLE001 - one tournament's hands never take the line down
                log.warning("ICM line: tournament %s could not be priced", tourney_id, exc_info=True)
        total += profit - luck
        values.append(total)
        priced += tourney_priced
        allins += len(tourney_hands)
    return IcmLine(tuple(values), priced, allins)
