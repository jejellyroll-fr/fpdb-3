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

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any

__all__ = [
    "PRESETS",
    "EnteredStructure",
    "Payouts",
    "PayoutsLookup",
    "TourneyFacts",
    "apply_preset",
    "clear_payouts",
    "field_size_for_hand",
    "from_results",
    "parse_structure",
    "payouts_for_hand",
    "payouts_for_tourney",
    "preset_shares",
    "split_prize_pool",
    "store_entered",
    "store_payouts",
    "stored_payouts",
    "tourney_facts",
    "tourney_for_hand",
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
# Presets whose paid places depend on the field: refused when its size is unknown.
FIELD_SIZED_PRESETS = frozenset({"double_or_nothing"})


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

    Winnings that are not known -- NULL, or the -1 the importer keeps for a
    prize it could not read -- are no result at all: such a place neither pays
    nor proves the next one unpaid (#626).
    """
    winnings: dict[int, int] = {}
    for place, won in results:
        if place is None or place < 1 or won is None or int(won) < 0:
            continue
        winnings[int(place)] = max(winnings.get(int(place), 0), int(won))
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
    return Payouts(
        tuple(places[p][0] for p in range(1, len(places) + 1)), places[1][1], tourney_facts(db, tourney_id).currency
    )


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


@dataclass(frozen=True)
class TourneyFacts:
    """What fpdb knows of a tournament that bears on its payouts; amounts in hundredths."""

    entries: int | None = None
    prize_pool: int | None = None
    buy_in: int | None = None
    currency: str | None = None
    knockout: bool = False
    bounty: int | None = None
    number: int | None = None  # the room's tournament number


def tourney_facts(db: Any, tourney_id: int) -> TourneyFacts:
    """The tournament's field size, prize pool, buy-in and currency, as far as they are stored."""
    rows = _query(db, "selectTourneyFacts", (tourney_id,))
    if not rows:
        return TourneyFacts()
    entries, prize_pool, buy_in, currency, knockout, bounty, number = rows[0]
    return TourneyFacts(
        int(entries) if entries else None,
        int(prize_pool) if prize_pool else None,
        int(buy_in) if buy_in else None,
        currency,
        bool(knockout),
        int(bounty) if bounty else None,
        int(number) if number else None,
    )


def _prize_pool(facts: TourneyFacts) -> int:
    """The pool the places share: the known one, else buy-ins less any bounty they carry."""
    if facts.prize_pool is not None:
        return facts.prize_pool
    if facts.buy_in is None or not facts.entries:
        raise ValueError("the tournament has no known prize pool, nor buy-in and entries to make one")
    buy_in = facts.buy_in
    if facts.knockout:
        # The stored buy-in includes the bounty, which goes to whoever knocks a
        # player out, not to the places (#626).
        if not facts.bounty:
            raise ValueError("a knockout buy-in includes a bounty of unknown size: enter the prize pool")
        buy_in -= facts.bounty
    return buy_in * facts.entries


def apply_preset(db: Any, tourney_id: int, preset: str) -> Payouts:
    """Store ``preset`` applied to the tournament's prize pool (or buy-in x entries when none is known)."""
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r}; known: {sorted(PRESETS)}")
    facts = tourney_facts(db, tourney_id)
    if preset in FIELD_SIZED_PRESETS and not facts.entries:
        raise ValueError(f"{preset} pays by field size, and the tournament's field size is unknown")
    return _store_split(db, tourney_id, facts, PRESETS[preset](facts.entries or 0), f"{SOURCE_PRESET}:{preset}")


def _store_split(db: Any, tourney_id: int, facts: TourneyFacts, shares: Sequence[Fraction], source: str) -> Payouts:
    amounts = split_prize_pool(_prize_pool(facts), shares)
    store_payouts(db, tourney_id, amounts, source)
    return Payouts(amounts, source, facts.currency)


@dataclass(frozen=True)
class EnteredStructure:
    """A structure as the user typed or pasted it: prizes (hundredths) or shares of the prize pool."""

    amounts: tuple[int, ...] = ()
    shares: tuple[Fraction, ...] = ()


# A number, its decimals after "." or ",", and an optional percent sign.
_NUMBER = re.compile(r"(\d+(?:[.,]\d+)?)\s*(%?)")
# A thousands separator: a comma or space between digits, before exactly three digits.
_THOUSANDS = re.compile(r"(?<=\d)[, \u00a0\u202f](?=\d{3}(?!\d))")


# A line's leading rank: "1", "#1", "1st", "1er", "1.", "1:", "1)", followed by more digits.
_RANK = re.compile(r"^\s*(#?)(\d+)(?![\d.,]\d)\s*(st|nd|rd|th|er|re|ème|e|º|°|[.:)\-–])?\s*(?=\D*\d)", re.IGNORECASE)


def _rank(line: str) -> tuple[int, str, bool] | None:
    """The line's leading rank, what follows it, and whether a label ("#", "st", ":") marks it as one."""
    match = _RANK.match(line)
    if match is None:
        return None
    return int(match.group(2)), line[match.end() :], bool(match.group(1) or match.group(3))


def _without_ranks(lines: list[str]) -> list[str]:
    """The lines without their ranks, when every line starts with its own: 1, 2, 3...

    Codex (#629): the rank goes first, or the thousands cleanup reads "1 500.00"
    as 1500.
    """
    ranks = [_rank(line) for line in lines]
    if any(rank is None for rank in ranks) or [rank[0] for rank in ranks if rank] != list(range(1, len(lines) + 1)):
        return lines
    return [rank[1] for rank in ranks if rank]


def _places(text: str) -> list[tuple[str, str]]:
    """Each place's number and percent sign, as typed: one place per line, or all on one line."""
    lines = [line for line in text.splitlines() if line.strip()]
    first = _rank(lines[0]) if len(lines) == 1 else None
    if first is not None and first[2] and first[0] == 1:
        # Codex (#629): "1st $45.00" is one place that pays, not two.
        if len(_NUMBER.findall(_THOUSANDS.sub("", first[1]))) > 1:
            raise ValueError("put one place per line when places are labelled")
        items = [_THOUSANDS.sub("", first[1])]
    elif len(lines) == 1:
        items = [item for item in re.split(r"[;,\s]+", lines[0]) if item]
    else:
        items = [_THOUSANDS.sub("", line) for line in _without_ranks(lines)]
    found = []
    for item in items:
        numbers = _NUMBER.findall(item)
        if not numbers:
            raise ValueError(f"no amount in {item.strip()!r}")
        found.append(numbers[-1])
    if not found:
        raise ValueError("enter at least one place")
    return found


def parse_structure(text: str) -> EnteredStructure:
    """Read a payout structure typed or pasted from a lobby, first place first.

    One place per line takes the last number of each line, so "1st  $1,250.00"
    and "2: 30%" both read; a decimal comma is fine there. On a single line,
    places are separated by spaces, commas or semicolons, and decimals use a
    point. Either all places are percentages of the prize pool, adding up to
    100, or all are prizes in currency units.
    """
    found = _places(text)
    percent = {bool(sign) for _value, sign in found}
    if len(percent) > 1:
        raise ValueError("enter either percentages or amounts, not both")
    try:
        values = [Decimal(value.replace(",", ".")) for value, _sign in found]
    except InvalidOperation as exc:  # pragma: no cover - the pattern only lets numbers through
        raise ValueError(str(exc)) from exc
    if not any(values):
        raise ValueError("no place pays anything")
    if percent == {True}:
        if sum(values) != 100:
            raise ValueError(f"the percentages add up to {sum(values)}%, not 100%")
        return EnteredStructure(shares=tuple(Fraction(value) / 100 for value in values))
    if any(value != value.quantize(Decimal("0.01")) for value in values):
        raise ValueError("a prize has more than two decimals")
    return EnteredStructure(amounts=tuple(int(value * 100) for value in values))


def store_entered(db: Any, tourney_id: int, entered: EnteredStructure) -> Payouts:
    """Store a structure the user entered: prizes as they are, percentages applied to the prize pool."""
    if entered.shares:
        return _store_split(db, tourney_id, tourney_facts(db, tourney_id), entered.shares, SOURCE_MANUAL)
    store_payouts(db, tourney_id, entered.amounts, SOURCE_MANUAL)
    return Payouts(entered.amounts, SOURCE_MANUAL, tourney_facts(db, tourney_id).currency)


def payouts_for_tourney(db: Any, tourney_id: int) -> PayoutsLookup:
    """The tournament's payout structure: stored first, else settled by its results, else none and why."""
    stored = stored_payouts(db, tourney_id)
    if stored is not None:
        return PayoutsLookup(stored)
    facts = tourney_facts(db, tourney_id)
    if facts.knockout:
        return PayoutsLookup(None, "knockout winnings include bounties: enter the payout structure")
    results = [(place, won) for place, won in _query(db, "selectTourneyResults", (tourney_id,))]
    settled = from_results(results, facts.entries)
    if settled is None:
        return PayoutsLookup(None, "no payout structure known: import the summary, enter one or apply a preset")
    return PayoutsLookup(Payouts(settled, SOURCE_SUMMARY, facts.currency))


def tourney_for_hand(db: Any, hand_id: int) -> int | None:
    """The tournament ``hand_id`` was played in; None for a cash hand."""
    rows = _query(db, "selectHandTourneyId", (hand_id,))
    if not rows or rows[0][0] is None:
        return None
    return int(rows[0][0])


def payouts_for_hand(db: Any, hand_id: int) -> PayoutsLookup:
    """The payout structure of the tournament ``hand_id`` was played in; none for a cash hand."""
    tourney_id = tourney_for_hand(db, hand_id)
    if tourney_id is None:
        return PayoutsLookup(None, "not a tournament hand")
    return payouts_for_tourney(db, tourney_id)


def field_size_for_hand(db: Any, hand_id: int) -> int | None:
    """How many entered the tournament ``hand_id`` was played in, when known."""
    tourney_id = tourney_for_hand(db, hand_id)
    return None if tourney_id is None else tourney_facts(db, tourney_id).entries


def preset_shares(preset: str, entries: int) -> Mapping[int, Fraction]:
    """A preset's share of the prize pool by place, for display."""
    return dict(enumerate(PRESETS[preset](entries), start=1))
