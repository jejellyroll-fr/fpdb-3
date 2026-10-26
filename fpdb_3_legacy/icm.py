"""ICM: tournament chips turned into prize equity (#446).

The Independent Chip Model (Malmuth-Harville) prices a stack by the prizes it
is expected to win: a player finishes first with probability stack / total
chips, and each later place is drawn the same way among those still left. That
is what turns a chip result into money in a tournament, where chips won are
worth less than chips lost -- the reason a shove that wins chips can still lose
money near the bubble.

This module is the engine only, pure Python and free of fpdb's data: stacks in
any chip unit, payouts in any currency, finishing places counted from 1. Where
the payout structure of a hand comes from, and showing ICM $EV in the replayer
and the graphs, are the rest of #446.

Cost. The exact model visits every set of players that can still be in the
running when a prize is awarded: with ``n`` players and ``k`` paid places that
is C(n, 0) + ... + C(n, k) sets, each costing ``n``. A final table (9-10 players)
or a SNG is instant; a whole MTT field is not, and :func:`icm_equities` raises
:class:`ICMTooLarge` rather than answering slowly or approximately. Callers
show "ICM not computed" for such spots.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import groupby
from math import comb

__all__ = [
    "MAX_STATES",
    "AllInOutcome",
    "ICMError",
    "ICMTooLarge",
    "allin_icm_ev",
    "bubble_factor",
    "icm_equities",
    "outcome_equities",
    "state_count",
]

# Above this many player sets the exact model is refused: about a second of pure
# Python, enough for a 10-handed final table paying every place.
MAX_STATES = 1_100_000


class ICMError(ValueError):
    """Stacks or payouts the model cannot price (negative chips, no chips at all...)."""


class ICMTooLarge(ICMError):
    """The exact model would visit more than :data:`MAX_STATES` player sets."""


def state_count(players: int, paid_places: int) -> int:
    """How many player sets the exact model visits for ``players`` and ``paid_places``."""
    places = min(players, paid_places)
    return sum(comb(players, taken) for taken in range(places + 1))


def icm_equities(stacks: Sequence[float], payouts: Sequence[float]) -> list[float]:
    """Each player's prize equity, in the payout's unit, in the order of ``stacks``.

    ``payouts[0]`` goes to first place, ``payouts[1]`` to second, and so on;
    places beyond the list pay nothing. A player with no chips has finished and
    takes no further prize. Equities add up to the prizes still to be won: the
    first ``len(stacks with chips)`` payouts.
    """
    _validate(stacks, payouts)
    alive = [index for index, stack in enumerate(stacks) if stack > 0]
    equities = [0.0] * len(stacks)
    if not alive:
        if any(payouts):
            raise ICMError("no player has chips to win the prizes")
        return equities
    prizes = [float(prize) for prize in payouts[: len(alive)]]
    while prizes and prizes[-1] == 0:
        prizes.pop()  # unpaid places change nothing and only cost time
    if not prizes:
        return equities
    if state_count(len(alive), len(prizes)) > MAX_STATES:
        raise ICMTooLarge(f"{len(alive)} players and {len(prizes)} paid places are more than the exact model computes")
    for slot, value in zip(alive, _harville([float(stacks[index]) for index in alive], prizes), strict=True):
        equities[slot] = value
    return equities


def _validate(stacks: Sequence[float], payouts: Sequence[float]) -> None:
    if any(stack < 0 for stack in stacks):
        raise ICMError("a stack cannot be negative")
    if any(prize < 0 for prize in payouts):
        raise ICMError("a payout cannot be negative")


def _harville(chips: list[float], prizes: list[float]) -> list[float]:
    """Malmuth-Harville over players who all have chips: their expected prizes, in order."""
    players = len(chips)
    # remaining-set bitmask -> expected prize of each player in it, from the place now awarded on
    memo: dict[int, list[float]] = {}

    def expected(remaining: int) -> list[float]:
        found = memo.get(remaining)
        if found is not None:
            return found
        place = players - remaining.bit_count()
        result = [0.0] * players
        if place < len(prizes):
            members = [i for i in range(players) if remaining >> i & 1]
            total = sum(chips[i] for i in members)
            for winner in members:
                share = chips[winner] / total
                result[winner] += share * prizes[place]
                rest = expected(remaining & ~(1 << winner))
                for i in members:
                    if i != winner:
                        result[i] += share * rest[i]
        memo[remaining] = result
        return result

    return expected((1 << players) - 1)


@dataclass(frozen=True)
class AllInOutcome:
    """One way an all-in ends: its probability and every player's stack afterwards."""

    probability: float
    stacks: Mapping[str, float]


def allin_icm_ev(
    before: Mapping[str, float],
    outcomes: Sequence[AllInOutcome],
    payouts: Sequence[float],
    player: str,
) -> float:
    """``player``'s ICM $EV of an all-in: expected prize equity after it, less the equity before.

    ``outcomes`` are the ways the all-in can end (win, lose, split...), whose
    probabilities come from the equity engine and must add up to 1. Positive
    means the all-in gains money under ICM, whatever it does in chips.
    """
    if not outcomes:
        raise ICMError("an all-in needs at least one outcome")
    total = sum(outcome.probability for outcome in outcomes)
    if abs(total - 1.0) > 1e-6:
        raise ICMError(f"outcome probabilities add up to {total:g}, not 1")
    names = list(before)
    if player not in before:
        raise ICMError(f"{player!r} is not among the stacks")
    index = names.index(player)
    now = icm_equities([before[name] for name in names], payouts)[index]
    after = sum(outcome.probability * outcome_equities(before, outcome.stacks, payouts)[player] for outcome in outcomes)
    return after - now


def outcome_equities(
    before: Mapping[str, float], after: Mapping[str, float], payouts: Sequence[float]
) -> dict[str, float]:
    """Each player's prize equity once a hand has ended, prizes won by busting in it included.

    A survivor is worth their ICM equity on ``after``. A player the hand busts
    has finished: they take the place right below the survivors, the larger
    starting stack finishing higher, and players who started equal share their
    places' prizes. Without this, busting in a paid place would count as nothing
    (#623). A player already out before the hand stays at nothing.
    """
    names = list(before)
    if set(after) != set(names):
        raise ICMError("every outcome must give a stack to the same players")
    equities = dict(zip(names, icm_equities([after[name] for name in names], payouts), strict=True))
    place = sum(1 for name in names if after[name] > 0)
    busted = sorted((name for name in names if before[name] > 0 and after[name] <= 0), key=lambda n: -before[n])
    for _start, tied in groupby(busted, key=lambda name: before[name]):
        group = list(tied)
        prizes = [payouts[slot] if slot < len(payouts) else 0.0 for slot in range(place, place + len(group))]
        for name in group:
            equities[name] = float(sum(prizes)) / len(group)
        place += len(group)
    return equities


def bubble_factor(stacks: Mapping[str, float], payouts: Sequence[float], player: str, opponent: str) -> float:
    """How much more ``player`` loses than wins, in prize equity, by getting all-in against ``opponent``.

    The covered amount changes hands: the smaller of the two stacks. The factor
    is equity lost on losing over equity gained on winning; 1.0 is a chip-EV
    spot, and the higher it is, the more chips a call needs to be worth it
    (required equity = BF / (1 + BF)). ``inf`` when winning gains nothing.
    """
    if player == opponent:
        raise ICMError("a player cannot be all-in against themself")
    for name in (player, opponent):
        if stacks.get(name, 0) <= 0:
            raise ICMError(f"{name!r} has no chips to put in")
    names = list(stacks)
    at_risk = min(stacks[player], stacks[opponent])
    won = dict(stacks)
    won[player] += at_risk
    won[opponent] -= at_risk
    lost = dict(stacks)
    lost[player] -= at_risk
    lost[opponent] += at_risk

    now = icm_equities([stacks[name] for name in names], payouts)[names.index(player)]
    gain = outcome_equities(stacks, won, payouts)[player] - now
    loss = now - outcome_equities(stacks, lost, payouts)[player]
    return float("inf") if gain <= 0 else loss / gain
