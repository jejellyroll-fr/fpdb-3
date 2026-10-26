"""What each finishing place of a tournament pays (#446): the input ICM needs.

A hand's ICM $EV needs the tournament's payout structure, and fpdb kept none.
This module answers "what does place N pay in this tournament?" from three
sources, in order:

1. a structure stored for the tournament -- entered by the user, or a preset
   applied to its prize pool (``TourneyPayouts``);
2. the tournament's results, when an imported summary settles every paid place:
   the winnings of places 1..k, and proof that place k+1 pays nothing;
3. nothing -- and then it says so, instead of guessing a structure.

Amounts are in hundredths, as fpdb stores winnings and prize pools. Knockout
tournaments are never read from results: their winnings include bounties.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

__all__ = [
    "PRESETS",
    "Payouts",
    "PayoutsLookup",
    "apply_preset",
    "clear_payouts",
    "from_results",
    "payouts_for_hand",
    "payouts_for_tourney",
    "preset_shares",
    "split_prize_pool",
    "store_payouts",
    "stored_payouts",
]

SOURCE_SUMMARY = "summary"
SOURCE_MANUAL = "manual"
SOURCE_PRESET = "preset"  # stored as "preset:<name>"


@dataclass(frozen=True)
class Payouts:
    """The prize of each place, first place first, in hundredths of ``currency``."""

    amounts: tuple[int, ...]
    source: str
    currency: str | None = None

    def as_money(self) -> list[float]:
        """The amounts in currency units, as the ICM engine takes them."""
        return [amount / 100 for amount in self.amounts]


@dataclass(frozen=True)
class PayoutsLookup:
    """A tournament's payouts, or why there are none."""

    payouts: Payouts | None
    reason: str = ""


def _fixed(*shares: str) -> Callable[[int], tuple[Fraction, ...]]:
    fractions = tuple(Fraction(share) for share in shares)

    def shares_for(_entries: int) -> tuple[Fraction, ...]:
        return fractions

    return shares_for


def _double_or_nothing(entries: int) -> tuple[Fraction, ...]:
    paid = max(entries // 2, 1)
    return (Fraction(1, paid),) * paid


# The prize pool's shares by place, for a field of ``entries``. The common
# sit-and-go structures; a room that pays otherwise is entered by hand.
PRESETS: dict[str, Callable[[int], tuple[Fraction, ...]]] = {
    "winner_take_all": _fixed("1"),  # heads-up, and most Spin & Go
    "sng_6max": _fixed("65/100", "35/100"),
    "sng_9max": _fixed("50/100", "30/100", "20/100"),
    "sng_10max": _fixed("50/100", "30/100", "20/100"),
    "sng_18max": _fixed("40/100", "30/100", "20/100", "10/100"),
    "double_or_nothing": _double_or_nothing,
}


def split_prize_pool(prize_pool: int, shares: Sequence[Fraction]) -> tuple[int, ...]:
    """``prize_pool`` (hundredths) split by ``shares``, rounded so the amounts add up to it exactly.

    Largest remainder: every place gets its share rounded down, and the
    hundredths left over go to the places that lost the most in rounding.
    """
    if prize_pool < 0:
        raise ValueError("a prize pool cannot be negative")
    if not shares or sum(shares) != 1 or any(share < 0 for share in shares):
        raise ValueError("shares must be non-negative and add up to 1")
    exact = [prize_pool * share for share in shares]
    amounts = [int(value) for value in exact]
    left = prize_pool - sum(amounts)
    by_remainder = sorted(range(len(exact)), key=lambda i: (-(exact[i] - amounts[i]), i))
    for index in by_remainder[:left]:
        amounts[index] += 1
    return tuple(amounts)


def from_results(results: Sequence[tuple[int, int]], entries: int | None = None) -> tuple[int, ...] | None:
    """The payout structure a tournament's results settle, or None when they do not.

    ``results`` are ``(place, winnings)`` pairs. The paid places are 1..k, k the
    last place that won something; the structure is settled when every one of
    them is known and something shows that place k+1 pays nothing -- a known
    place k+1 that won nothing, or a field of exactly k entries. Results of
    only some finishers (a summary that lists the hero alone) settle nothing.
    """
    winnings: dict[int, int] = {}
    for place, won in results:
        if place is None or place < 1:
            continue
        winnings[int(place)] = max(winnings.get(int(place), 0), int(won or 0))
    paid = [place for place, won in winnings.items() if won > 0]
    if not paid:
        return None
    last = max(paid)
    if any(place not in winnings for place in range(1, last + 1)):
        return None
    if winnings.get(last + 1) != 0 and entries != last:
        return None
    return tuple(winnings[place] for place in range(1, last + 1))


# --- the database side --------------------------------------------------------------


def _query(db: Any, name: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
    cursor = db.get_cursor()
    cursor.execute(db.sql.query[name], params)
    return list(cursor.fetchall())


def stored_payouts(db: Any, tourney_id: int) -> Payouts | None:
    """The structure stored for ``tourney_id`` (entered or from a preset), if any."""
    rows = _query(db, "selectTourneyPayouts", (tourney_id,))
    if not rows:
        return None
    places = {int(place): (int(amount), str(source)) for place, amount, source in rows}
    if sorted(places) != list(range(1, len(places) + 1)):
        return None  # a gap: not a structure fpdb wrote
    return Payouts(tuple(places[p][0] for p in range(1, len(places) + 1)), places[1][1], _facts(db, tourney_id)[3])


def store_payouts(db: Any, tourney_id: int, amounts: Sequence[int], source: str = SOURCE_MANUAL) -> None:
    """Replace the structure stored for ``tourney_id``: ``amounts[0]`` is first place's prize, in hundredths."""
    if not amounts or any(int(amount) < 0 for amount in amounts):
        raise ValueError("a payout structure needs at least one place and no negative prize")
    cursor = db.get_cursor()
    cursor.execute(db.sql.query["deleteTourneyPayouts"], (tourney_id,))
    for place, amount in enumerate(amounts, start=1):
        cursor.execute(db.sql.query["insertTourneyPayout"], (tourney_id, place, int(amount), source))
    db.commit()


def clear_payouts(db: Any, tourney_id: int) -> None:
    """Forget the structure stored for ``tourney_id``; its results, if they settle one, apply again."""
    db.get_cursor().execute(db.sql.query["deleteTourneyPayouts"], (tourney_id,))
    db.commit()


def _facts(db: Any, tourney_id: int) -> tuple[int | None, int | None, int | None, str | None, bool]:
    rows = _query(db, "selectTourneyFacts", (tourney_id,))
    if not rows:
        return None, None, None, None, False
    entries, prize_pool, buy_in, currency, knockout = rows[0]
    return (
        int(entries) if entries else None,
        int(prize_pool) if prize_pool else None,
        int(buy_in) if buy_in else None,
        currency,
        bool(knockout),
    )


def apply_preset(db: Any, tourney_id: int, preset: str) -> Payouts:
    """Store ``preset`` applied to the tournament's prize pool (or buy-in x entries when none is known)."""
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r}; known: {sorted(PRESETS)}")
    entries, prize_pool, buy_in, currency, _knockout = _facts(db, tourney_id)
    if prize_pool is None and buy_in is not None and entries:
        prize_pool = buy_in * entries
    if prize_pool is None:
        raise ValueError("the tournament has no known prize pool, nor buy-in and entries to make one")
    amounts = split_prize_pool(prize_pool, PRESETS[preset](entries or 0))
    source = f"{SOURCE_PRESET}:{preset}"
    store_payouts(db, tourney_id, amounts, source)
    return Payouts(amounts, source, currency)


def payouts_for_tourney(db: Any, tourney_id: int) -> PayoutsLookup:
    """The tournament's payout structure: stored first, else settled by its results, else none and why."""
    stored = stored_payouts(db, tourney_id)
    if stored is not None:
        return PayoutsLookup(stored)
    entries, _prize_pool, _buy_in, currency, knockout = _facts(db, tourney_id)
    if knockout:
        return PayoutsLookup(None, "knockout winnings include bounties: enter the payout structure")
    settled = from_results([(place, won) for place, won in _query(db, "selectTourneyResults", (tourney_id,))], entries)
    if settled is None:
        return PayoutsLookup(None, "no payout structure known: import the summary, enter one or apply a preset")
    return PayoutsLookup(Payouts(settled, SOURCE_SUMMARY, currency))


def payouts_for_hand(db: Any, hand_id: int) -> PayoutsLookup:
    """The payout structure of the tournament ``hand_id`` was played in; none for a cash hand."""
    rows = _query(db, "selectHandTourneyId", (hand_id,))
    if not rows or rows[0][0] is None:
        return PayoutsLookup(None, "not a tournament hand")
    return payouts_for_tourney(db, int(rows[0][0]))


def preset_shares(preset: str, entries: int) -> Mapping[int, Fraction]:
    """A preset's share of the prize pool by place, for display."""
    return dict(enumerate(PRESETS[preset](entries), start=1))
