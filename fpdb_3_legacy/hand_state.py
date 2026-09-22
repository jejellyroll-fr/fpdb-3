"""Postflop hand-state classification: strength, draws, nutness, blockers (#302).

A range is a set of starting hands; this module answers what those hands *are*
once the board is out. It classifies a player's known hole cards against the
board as of a street -- flop, turn or river -- and it classifies nothing else:
a hand whose cards were never shown has no state, and the module refuses it
rather than guessing, exactly as the range explorer refuses it (#301).

Four things, each with a definition that can be checked:

* **The made hand** comes from the project's own evaluator, ``pokereval`` (the
  ``pypoker-eval`` dependency that :mod:`fpdb_3_legacy.equity` and
  ``DerivedStats`` already use for all-in equity), named with ``Card``'s hand
  vocabulary. There is no second evaluator here: when the native library cannot
  load, :func:`classify` raises rather than answering differently.
* **The pair detail** -- overpair, top pair, middle pair, bottom pair, a pocket
  pair under the board, top two, bottom two, a set or trips -- is read off the
  board's own ranks, because "top pair" is a statement about the board.
* **The draws** are read off the ranks and suits that are visible. A draw is
  named only when the hand can actually improve: on the river every draw is
  empty by definition, and the backdoor draws exist only on the flop.
* **Nutness** is measured against *the deck on this board*, not against an
  opponent's range: every one of the 990-odd two-card holdings the remaining
  cards allow is evaluated once per board and cached, so "the nuts" means
  exactly "nothing beats it", "near nuts" means "only the nuts does", and
  strong/medium/weak are explicit percentiles of that same distribution. The
  raw numbers (``beats`` and ``holdings``) travel with the label, so a caller
  never has to trust the band.

What it deliberately does **not** do: it does not infer hole cards, it does not
model a range, and it does not claim theoretical equity -- that is the equity
engine's job (``fpdb_3_legacy.equity``) and the profitability report's caveat
(#300). This module says what is on the table.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Final

from . import Card, board_features
from .equity import load_poker_eval

HAND_NAMES = Card.hands
_RANK_LETTERS: Final = frozenset("23456789TJQKA")
_SUIT_LETTERS: Final = frozenset("hdcs")

# --------------------------------------------------------------------------- #
# The vocabulary. Every name below is contract: it is what a filter, a report
# or an AutoNote will store, so it is short, stable and spelled once.
# --------------------------------------------------------------------------- #

#: Board cards visible on each street, and the street's name.
STREETS_BY_BOARD_SIZE: Final[dict[int, str]] = {3: "flop", 4: "turn", 5: "river"}

#: How many board cards are visible at the end of each street.
BOARD_CARDS_BY_STREET: Final[dict[str, int]] = {name: size for size, name in STREETS_BY_BOARD_SIZE.items()}

#: The made hands, weakest first. ``pokereval`` names them as ``Card.hands``
#: does; these are the canonical spellings this project stores and compares.
MADE_HANDS: Final[tuple[str, ...]] = (
    "high_card",
    "one_pair",
    "two_pair",
    "three_of_a_kind",
    "straight",
    "flush",
    "full_house",
    "four_of_a_kind",
    "straight_flush",
)
_MADE_HAND_BY_EVALUATOR_NAME: Final[dict[str, str]] = {
    "NoPair": "high_card",
    "OnePair": "one_pair",
    "TwoPair": "two_pair",
    "Trips": "three_of_a_kind",
    "Straight": "straight",
    "Flush": "flush",
    "FlHouse": "full_house",
    "Quads": "four_of_a_kind",
    "StFlush": "straight_flush",
}

#: How the made hand is made, when it is a pair, two pair or trips.
PAIR_DETAILS: Final[tuple[str, ...]] = (
    "overpair",
    "top_pair",
    "middle_pair",
    "bottom_pair",
    "pocket_pair_below_board",
    "top_two",
    "middle_two",
    "bottom_two",
    "set",
    "trips",
)

#: The draw vocabulary, and what each one means.
DRAW_CATEGORIES: Final[tuple[str, ...]] = (
    "flush_draw",
    "nut_flush_draw",
    "backdoor_flush_draw",
    "open_ended_straight_draw",
    "gutshot",
    "double_gutshot",
    "backdoor_straight_draw",
    "combo_draw",
)
_DRAW_DEFINITIONS: Final[dict[str, str]] = {
    "flush_draw": "exactly four cards of one suit are visible (the hole contributes at least one)",
    "nut_flush_draw": "a flush draw whose highest card of the suit is the ace, held in the hole",
    "backdoor_flush_draw": "on the flop, exactly three cards of one suit are visible",
    "open_ended_straight_draw": "four visible ranks are consecutive, so either end completes a straight",
    "gutshot": "exactly one or two completing ranks, none of them the end of four consecutive ranks",
    "double_gutshot": "two different interior ranks each complete a straight",
    "backdoor_straight_draw": "on the flop, no straight draw yet but two ranks would complete one",
    "combo_draw": "a straight draw and a flush draw at once",
}

#: Nutness bands. ``nuts`` and ``near_nuts`` are exact; the other three are
#: explicit percentiles of the same hands-the-deck-can-hold distribution.
NUTNESS_LEVELS: Final[tuple[str, ...]] = ("nuts", "near_nuts", "strong", "medium", "weak")
STRONG_PERCENTILE: Final = 0.90
MEDIUM_PERCENTILE: Final = 0.50

#: The number of cards of one suit a flush draw shows on the flop or turn, and
#: the number a backdoor flush shows on the flop.
_FLUSH_DRAW_CARDS: Final = 4
_BACKDOOR_SUIT_CARDS: Final = 3

#: The draws a made hand already beats: a straight is not drawing to one, and a
#: flush, full house, quads or straight flush is past caring about them.
_STRAIGHT_DRAW_BLOCKERS: Final = frozenset({"straight", "flush", "full_house", "four_of_a_kind", "straight_flush"})

#: The draws that combine into a combo draw.
_FLUSH_DRAWS: Final = frozenset({"flush_draw", "nut_flush_draw"})
_STRAIGHT_DRAWS: Final = frozenset({"open_ended_straight_draw", "gutshot", "double_gutshot"})

#: Blocker categories, each a statement about a card in the hole.
BLOCKER_CATEGORIES: Final[tuple[str, ...]] = (
    "nut_flush_blocker",
    "paired_board_blocker",
    "straight_blocker",
    "overcard_blocker",
)

# The draws and blockers are stored as bitmasks, exactly like the board
# texture flags (#295): a mask keeps the row flat, lets one column answer "any
# of these" and "all of these" with the same portable ``&``, and gives the
# vocabulary a single source. Bit *i* is the *i*-th name, so the two must not
# be reordered without bumping the extractor version.
DRAW_BITS: Final[dict[str, int]] = {name: 1 << index for index, name in enumerate(DRAW_CATEGORIES)}
BLOCKER_BITS: Final[dict[str, int]] = {name: 1 << index for index, name in enumerate(BLOCKER_CATEGORIES)}


#: The games whose postflop hand state this module classifies, and the only
#: honest answer to "can a study show hand strength for this variant". Hold'em
#: only: an Omaha hand's best two cards are not a Hold'em hand, a short-deck
#: board does not rank hands the same way, and a four-card holding read as two
#: would produce a confident answer to a question nothing here can answer
#: (#368). Anything that gates a hand-state panel asks this set rather than
#: spelling the rule out a second time.
CLASSIFIED_GAMES: Final[frozenset[str]] = frozenset({"holdem"})


class HandStateError(ValueError):
    """A hand that cannot be classified, with the reason."""


class UnknownHoleCards(HandStateError):
    """The hole cards are not known: there is no state to classify."""


class NotPostflop(HandStateError):
    """Fewer than three board cards: there is no board to play against."""


class EvaluatorUnavailable(HandStateError):
    """``pokereval`` could not be loaded, and this project has one evaluator."""


# --------------------------------------------------------------------------- #
# Cards.
# --------------------------------------------------------------------------- #


def _normalize(cards: Any) -> tuple[str, ...]:
    """Card strings from whatever the caller has, with the project's parser.

    ``board_features.card_string`` already knows every shape a card arrives in
    (a string, a pair, an encoded int, a blank), so a second parser here would
    be a second truth about what "As" means. What it does not do is reject a
    longer string, so the two-character check is here: a hand-histories file's
    "AsKh" is two cards, not one unreadable one. The output is canonical, the
    same spelling the database and ``Card.valueSuitFromCard`` use.
    """
    out: list[str] = []
    for card in cards if isinstance(cards, (list, tuple, set)) else [cards]:
        text = board_features.card_string(card)
        if text.startswith("10"):  # noqa: PLR2004 - "10h" is a way of writing "Th"
            text = "T" + text[2:]
        if len(text) != 2 or text[0].upper() not in _RANK_LETTERS or text[1].lower() not in _SUIT_LETTERS:
            raise UnknownHoleCards(f"Not a card: {card!r}")
        out.append(text[0].upper() + text[1].lower())
    return tuple(out)


def _ranks(cards: Sequence[str]) -> tuple[int, ...]:
    return tuple(board_features.card_rank(card) for card in cards)


def _suits(cards: Sequence[str]) -> tuple[str, ...]:
    return tuple(board_features.card_suit(card) for card in cards)


def street_of(board: Sequence[str]) -> str:
    """``flop``, ``turn`` or ``river`` from how many board cards are visible."""
    size = len(_normalize(board))
    if size not in STREETS_BY_BOARD_SIZE:
        raise NotPostflop(
            f"A board of {size} card(s) is not a postflop street; a hand state needs three to five",
        )
    return STREETS_BY_BOARD_SIZE[size]


def board_through_street(board: Any, street: str) -> tuple[str, ...]:
    """The cards of a full board that are visible by the end of a street.

    A caller that holds one board and wants the flop state asks for the flop
    explicitly instead of passing the first three cards itself: the street name
    is the thing that says how much of the board the player had seen, and a
    hand state classified against cards that were not dealt yet is wrong.
    """
    if street not in BOARD_CARDS_BY_STREET:
        raise NotPostflop(f"Unknown street {street!r}; known: {sorted(BOARD_CARDS_BY_STREET)}")
    return _normalize(board)[: BOARD_CARDS_BY_STREET[street]]


def draws_mask(draws: Iterable[str]) -> int:
    """The draw names of a state as the mask the stored row keeps."""
    return _mask(draws, DRAW_BITS)


def blockers_mask(blockers: Iterable[str]) -> int:
    """The blocker names of a state as the mask the stored row keeps."""
    return _mask(blockers, BLOCKER_BITS)


def _mask(names: Iterable[str], bits: dict[str, int]) -> int:
    mask = 0
    for name in names:
        try:
            mask |= bits[name]
        except KeyError:
            raise ValueError(f"Unknown classification {name!r}; known: {sorted(bits)}") from None
    return mask


def mask_names(mask: int, bits: dict[str, int]) -> tuple[str, ...]:
    """The names a mask stands for, in catalogue order -- the inverse of it."""
    return tuple(name for name, bit in bits.items() if mask & bit)


# --------------------------------------------------------------------------- #
# Straight arithmetic, shared by the made hand's detail and by the draws.
# --------------------------------------------------------------------------- #

_STRAIGHT_RANKS: Final[tuple[tuple[int, ...], ...]] = tuple(
    tuple(range(low, low + 5)) for low in range(2, 11)
) + ((14, 2, 3, 4, 5),)  # the wheel: an ace plays low exactly once


def has_straight(ranks: Iterable[int]) -> bool:
    """Whether five consecutive ranks (or the wheel) are present."""
    present = set(ranks)
    return any(set(stretch) <= present for stretch in _STRAIGHT_RANKS)


def completing_ranks(ranks: Iterable[int]) -> tuple[int, ...]:
    """The ranks that would complete a straight for these visible ranks.

    A rank completes when adding it produces five consecutive ranks; the ace is
    tried both high and low, because it plays both ways in real hands and a
    classifier that picks one of them is wrong half the time.
    """
    return tuple(
        rank
        for rank in range(2, 15)
        if rank not in set(ranks) and has_straight((*ranks, rank))
    )


def _open_ended(ranks: Iterable[int], completions: Iterable[int]) -> bool:
    """Whether four consecutive ranks are visible with *both* ends drawable.

    Two live ends is what makes a draw open-ended rather than one-way: 8-9-T-J
    draws to a seven or a queen, while A-K-Q-J draws only to a ten and is a
    gutshot however consecutive it looks. The low end of 2-3-4-5 is the ace,
    which plays there exactly as it does in a real wheel.
    """
    present = set(ranks)
    live = set(completions)
    # Every four-run there is, from 2-3-4-5 up to J-Q-K-A. The high end of the
    # last one does not exist -- nothing is above an ace -- so a run whose only
    # live end is the low one is one-way, and one-way is a gutshot.
    for low in range(2, 12):
        if not set(range(low, low + 4)) <= present:
            continue
        low_end = 14 if low == 2 else low - 1  # noqa: PLR2004 - the ace plays below the two
        if low_end in live and (low + 4) in live:
            return True
    return False


# --------------------------------------------------------------------------- #
# The board's own possibilities, for nutness.
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=128)
def _board_pool(board: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[int, ...], Counter[int]]:
    """The cards the board leaves, every hand value the deck can hold, and their counts.

    The pool is what is *not* on the board; the values are the evaluator's own,
    over every two-card holding from that pool, sorted. Deliberately cached
    against the board alone and *not* against the hole cards: the expensive part
    is the 1081-or-so evaluations, and the two cards in one player's hand only
    remove 95 of the holdings -- which :func:`_nutness` subtracts exactly rather
    than recomputing the whole distribution per player. 990 to 1176 hands, half
    a millisecond, once per board.
    """
    evaluator = _evaluator()
    deck = tuple(evaluator.card2string(card) for card in evaluator.deck())
    pool = tuple(card for card in deck if card not in set(board))
    ranked = tuple(
        sorted(
            int(evaluator.best_hand_value("holdem", [first, second, *board]))
            for index, first in enumerate(pool)
            for second in pool[index + 1 :]
        ),
    )
    return pool, ranked, Counter(ranked)


def _evaluator() -> Any:
    evaluator = load_poker_eval()
    if evaluator is None:
        raise EvaluatorUnavailable(
            "pokereval (pypoker-eval) could not be loaded; the project evaluates hands with it "
            "and has no second evaluator",
        )
    return evaluator


def _made_hand(hole: Sequence[str], board: Sequence[str]) -> tuple[str, str, tuple[str, ...], int]:
    """(canonical name, evaluator label, the five cards that make it, its value)."""
    evaluator = _evaluator()
    cards = [*hole, *board]
    handtype, *used = evaluator.best_hand("holdem", cards)
    if handtype not in _MADE_HAND_BY_EVALUATOR_NAME:
        raise HandStateError(f"pokereval returned an unknown hand type {handtype!r}")
    named = tuple(evaluator.card2string(card) for card in used)
    return (
        _MADE_HAND_BY_EVALUATOR_NAME[handtype],
        _hand_label(handtype, named),
        named,
        int(evaluator.best_hand_value("holdem", cards)),
    )


def _hand_label(handtype: str, used: Sequence[str]) -> str:
    """The hand's name, through ``Card.hands``' templates and ``Card.names``.

    The evaluator returns the five cards that make the hand but not in a
    documented order, so the ranks are grouped here -- a pair is the rank that
    appears twice, a full house is the tripled rank over the paired one. The
    two vocabularies are the project's own (``Card.names`` spells "Ace"/"Aces",
    which is exactly the singular/plural a label needs).
    """
    template = HAND_NAMES[handtype][1]
    if not template:
        # ``Card.hands``' one unnamed entry: the evaluator's own name is the
        # only true label there is, and it is a string rather than an index.
        return handtype
    counts = Counter(card[0] for card in used)
    groups = sorted(((count, rank) for rank, count in counts.items()), reverse=True)

    def plural(rank: str) -> str:
        return Card.names[rank][1]

    if handtype == "NoPair":
        return template % Card.names[groups[0][1]][0]
    if handtype in ("OnePair", "Trips", "Quads"):
        return template % plural(groups[0][1])
    if handtype == "TwoPair":
        return template % " and ".join(plural(rank) for _, rank in groups[:2])
    if handtype == "FlHouse":
        return template % f"{plural(groups[0][1])} full of {plural(groups[1][1])}"
    # A straight, a flush or a straight flush: named by its highest card, and the
    # wheel is a five-high straight whichever way the ace is written. ``names``
    # is keyed by rank letters, so the wheel's five is the letter, not the number.
    letters = {card[0] for card in used}
    high = (
        "5"
        if letters == {"A", "5", "4", "3", "2"}
        else max(letters, key=lambda letter: Card.names[letter][2])
    )
    return template % f"{Card.names[high][0]} high"


# --------------------------------------------------------------------------- #
# Pair detail.
# --------------------------------------------------------------------------- #


def _pair_detail(
    made_hand: str,
    hole: Sequence[str],
    board: Sequence[str],
) -> str | None:
    """What the made hand is made of, board-first.

    "Top pair" is a statement about the board's highest rank, so the board is
    what decides: a hole card that pairs the board's highest rank is top pair,
    one that pairs its lowest is bottom pair, and anything in between is middle
    pair. A pocket pair above the whole board is an overpair; below it, it is a
    pocket pair under the board -- and the two are very different hands.
    """
    hole_ranks = _ranks(hole)
    board_ranks = _ranks(board)
    board_sorted = sorted(set(board_ranks), reverse=True)
    if made_hand not in ("one_pair", "two_pair", "three_of_a_kind"):
        return None
    if made_hand == "three_of_a_kind":
        if hole_ranks[0] == hole_ranks[1]:
            return "set"
        return "trips"
    if made_hand == "two_pair":
        return _two_pair_detail(hole_ranks, board_ranks, board_sorted)
    # one pair
    if hole_ranks[0] == hole_ranks[1]:
        highest = board_sorted[0] if board_sorted else 0
        return "overpair" if hole_ranks[0] > highest else "pocket_pair_below_board"
    pairing = [rank for rank in hole_ranks if rank in set(board_ranks)]
    if not pairing or not board_sorted:
        return None
    rank = pairing[0]
    if rank == board_sorted[0]:
        return "top_pair"
    if len(board_sorted) > 1 and rank == board_sorted[-1]:
        return "bottom_pair"
    return "middle_pair"


def _two_pair_detail(
    hole_ranks: Sequence[int],
    board_ranks: Sequence[int],
    board_sorted: Sequence[int],
) -> str | None:
    """Which two pair it is, by where its two pairs sit on the board.

    Both pairs count, the board's own included: holding kings over aces-and-
    kings board is top two just as much as holding ace-king is. The higher of
    the two pairs decides top two, the lower decides bottom two, and a pair that
    is neither the board's highest nor its lowest is named middle two rather
    than being folded into a band it does not belong to.
    """
    counts = Counter([*hole_ranks, *board_ranks])
    pairs = sorted((rank for rank, count in counts.items() if count >= 2), reverse=True)
    if len(pairs) < 2 or not board_sorted:  # pragma: no cover - a two-pair made hand has two pairs
        return None
    if pairs[0] >= board_sorted[0]:
        return "top_two"
    if pairs[-1] <= board_sorted[-1]:
        return "bottom_two"
    return "middle_two"


# --------------------------------------------------------------------------- #
# Draws.
# --------------------------------------------------------------------------- #


def _draws(
    made_hand: str,
    hole: Sequence[str],
    board: Sequence[str],
    street: str,
) -> frozenset[str]:
    """The draws the visible cards actually give, on the street being played.

    Nothing draws on the river: the last card is out, so a "draw" there would be
    a hand that has already missed. Backdoors need two cards to come, which is
    why they only exist on the flop.
    """
    if street == "river":
        return frozenset()
    ranks = _ranks([*hole, *board])
    draws = _suit_draws(made_hand, hole, board, street) | _straight_draws(made_hand, ranks, street)
    if draws & _FLUSH_DRAWS and draws & _STRAIGHT_DRAWS:
        draws.add("combo_draw")
    return frozenset(draws)


def _suit_draws(
    made_hand: str,
    hole: Sequence[str],
    board: Sequence[str],
    street: str,
) -> set[str]:
    """The flush draws and backdoors: four of a suit, or three with two to come."""
    if made_hand == "flush":
        return set()
    suits = Counter(_suits([*hole, *board]))
    draws: set[str] = set()
    four = next((suit for suit, count in suits.items() if count == _FLUSH_DRAW_CARDS), None)
    if four is not None:
        hole_ace = any(
            board_features.card_rank(card) == 14 and board_features.card_suit(card) == four for card in hole
        )
        draws.add("nut_flush_draw" if hole_ace else "flush_draw")
    if street == "flop" and four is None:
        three = next((suit for suit, count in suits.items() if count == _BACKDOOR_SUIT_CARDS), None)
        if three is not None and three in set(_suits(hole)):
            draws.add("backdoor_flush_draw")
    return draws


def _straight_draws(made_hand: str, ranks: Sequence[int], street: str) -> set[str]:
    """The straight draws: an open end, a gutshot, or a backdoor with two to come."""
    if made_hand in _STRAIGHT_DRAW_BLOCKERS:
        return set()
    completions = completing_ranks(ranks)
    if completions:
        if _open_ended(ranks, completions):
            return {"open_ended_straight_draw"}
        return {"double_gutshot"} if len(completions) > 1 else {"gutshot"}
    if street != "flop":
        return set()
    # Two cards to come: a backdoor straight needs a pair of ranks that would
    # complete one between them.
    if any(
        has_straight((*ranks, first, second)) for first in range(2, 15) for second in range(first + 1, 15)
    ):
        return {"backdoor_straight_draw"}
    return set()


# --------------------------------------------------------------------------- #
# Nutness.
# --------------------------------------------------------------------------- #


def _nutness(value: int, board: tuple[str, ...], hole: Sequence[str]) -> tuple[str, int, int]:
    """(band, holdings this hand beats, holdings the opponent can hold).

    The bands are statements about *the opponent's possible hands*, so a holding
    that uses a card in this player's own hand is not one of them: it is
    subtracted by value, which also keeps ``nuts`` exact. Without that, quad
    aces on a three-ace board came out as merely ``strong``, because the best
    "opponent" hand the evaluator found was one holding the fourth ace -- the
    one the player was holding. 1081 holdings on a flop, 95 of them impossible.

    ``nuts`` and ``near_nuts`` are then exact (nothing beats it; only the nuts
    does); the other three bands are percentiles of the same available
    distribution, and the counts are returned so the label can be audited.
    """
    pool, values, counts = _board_pool(board)
    excluded = Counter(_values_using(pool, board, hole))
    total = len(values) - sum(excluded.values())
    beats = bisect_left(values, value) - sum(count for candidate, count in excluded.items() if candidate < value)
    better = {candidate for candidate, count in counts.items() if candidate > value and count > excluded[candidate]}
    if not better:
        return "nuts", beats, total
    best = max(candidate for candidate, count in counts.items() if count > excluded[candidate])
    if better == {best}:
        return "near_nuts", beats, total
    fraction = beats / total if total else 0.0
    if fraction >= STRONG_PERCENTILE:
        return "strong", beats, total
    if fraction >= MEDIUM_PERCENTILE:
        return "medium", beats, total
    return "weak", beats, total


def _values_using(pool: Sequence[str], board: tuple[str, ...], hole: Sequence[str]) -> list[int]:
    """The values of the holdings this player's own cards make impossible.

    Enumerated over pool *pairs*, not over "each of my cards times the pool":
    the two-loop shorthand counts the player's own hand twice, which is one
    holding too many and put ``beats`` above ``holdings`` on a nut hand. It is
    also the reason the counts are exact instead of approximate -- C(49,2) - 95
    is C(47,2), the hands an opponent can actually have.
    """
    evaluator = _evaluator()
    mine = set(hole) & set(pool)
    out: list[int] = []
    for index, first in enumerate(pool):
        for second in pool[index + 1 :]:
            if first in mine or second in mine:
                out.append(int(evaluator.best_hand_value("holdem", [first, second, *board])))
    return out


# --------------------------------------------------------------------------- #
# Blockers.
# --------------------------------------------------------------------------- #


def _blockers(hole: Sequence[str], board: Sequence[str]) -> frozenset[str]:
    """What the hole cards block, each by an explicit rule.

    A blocker is a statement about the cards you hold and the draws they were
    needed for -- never about an opponent's range, which this project does not
    have for hands that were not shown.
    """
    blockers: set[str] = set()
    board_ranks = _ranks(board)
    hole_ranks = _ranks(hole)
    # The visible cards of each suit, the hole's included: an ace blocks the nut
    # flush of a suit when the flush is *drawable*, which takes three of them.
    suits = Counter(_suits([*hole, *board]))
    hole_cards = tuple(zip(hole_ranks, _suits(hole), strict=True))

    for rank, suit in hole_cards:
        if rank == 14 and suits[suit] >= 3:  # noqa: PLR2004 - three cards make a flush draw
            blockers.add("nut_flush_blocker")

    # A paired board's rank in the hole blocks the quads and the full houses of
    # that rank -- the hand you hold a card of is the hand they cannot have.
    counts = Counter(board_ranks)
    board_pairs = {rank for rank, count in counts.items() if count >= 2}
    if board_pairs & set(hole_ranks):
        blockers.add("paired_board_blocker")

    # A rank the board's own ranks are waiting for: holding it takes away the
    # card that would complete the straight, which is what a blocker means.
    # The board has to be four cards into a straight for there to be one at all.
    if set(hole_ranks) & set(completing_ranks(board_ranks)):
        blockers.add("straight_blocker")

    # An overcard above the whole board blocks the top of an opponent's range.
    if hole_ranks and board_ranks and max(hole_ranks) > max(board_ranks):
        blockers.add("overcard_blocker")
    return frozenset(blockers)


# --------------------------------------------------------------------------- #
# The classifier.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class HandState:
    """One player's known hand on one street: what it is, and what it could do."""

    street: str
    hole_cards: tuple[str, str]
    board: tuple[str, ...]
    made_hand: str
    made_hand_label: str
    made_cards: tuple[str, ...]
    pair_detail: str | None
    draws: frozenset[str]
    nutness: str
    beats: int
    holdings: int
    blockers: frozenset[str]

    @property
    def made_hand_rank(self) -> int:
        """The made hand's position in :data:`MADE_HANDS`, 1 for high card."""
        return MADE_HANDS.index(self.made_hand) + 1

    @property
    def beat_fraction(self) -> float:
        """The share of the deck's holdings this hand beats, on this board."""
        return self.beats / self.holdings if self.holdings else 0.0

    @property
    def is_drawing(self) -> bool:
        return bool(self.draws)

    def has(self, *categories: str) -> bool:
        """Whether the hand matches any of the given classifications."""
        for name in categories:
            if name in (self.made_hand, self.pair_detail, self.nutness) or name in self.draws or name in self.blockers:
                return True
        return False

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "street": self.street,
            "hole_cards": list(self.hole_cards),
            "board": list(self.board),
            "made_hand": self.made_hand,
            "made_hand_label": self.made_hand_label,
            "made_cards": list(self.made_cards),
            "made_hand_rank": self.made_hand_rank,
            "pair_detail": self.pair_detail,
            "draws": sorted(self.draws),
            "draws_mask": draws_mask(self.draws),
            "nutness": self.nutness,
            "beats": self.beats,
            "holdings": self.holdings,
            "beat_fraction": round(self.beat_fraction, 6),
            "blockers": sorted(self.blockers),
            "blockers_mask": blockers_mask(self.blockers),
        }
        return out

    def describe(self) -> str:
        """One line a hand review or an AutoNote can print."""
        parts = [f"{self.street.capitalize()}: {self.made_hand_label}"]
        if self.pair_detail:
            parts.append(self.pair_detail.replace("_", " "))
        parts.append(f"{self.nutness} ({self.beats}/{self.holdings} holdings beaten)")
        if self.draws:
            parts.append("drawing: " + ", ".join(sorted(self.draws)))
        if self.blockers:
            parts.append("blocking: " + ", ".join(sorted(self.blockers)))
        return " | ".join(parts)


def classify(hole_cards: Any, board: Any, *, game: str = "holdem") -> HandState:
    """Classify a known hand against a postflop board.

    Refuses anything it cannot honestly classify: fewer than three board cards
    (there is no state before the flop), more than five, duplicate cards, a card
    it cannot read, or a game whose hand this is not -- an Omaha hand's two best
    cards are not a Hold'em hand.
    """
    hole = _normalize(hole_cards)
    visible = _normalize(board)
    if len(hole) != 2:
        raise UnknownHoleCards(f"A Hold'em hand state needs exactly two hole cards, not {len(hole)}")
    if game not in CLASSIFIED_GAMES:
        raise HandStateError(
            f"Only {sorted(CLASSIFIED_GAMES)} hands are classified, not {game!r}",
        )
    street = street_of(visible)
    cards = [*hole, *visible]
    if len(set(cards)) != len(cards):
        raise HandStateError(f"Duplicate cards cannot be classified: {cards}")
    made_hand, label, made_cards, value = _made_hand(hole, visible)
    nutness, beats, holdings = _nutness(value, visible, hole)
    return HandState(
        street=street,
        hole_cards=(hole[0], hole[1]),
        board=visible,
        made_hand=made_hand,
        made_hand_label=label,
        made_cards=made_cards,
        pair_detail=_pair_detail(made_hand, hole, visible),
        draws=_draws(made_hand, hole, visible, street),
        nutness=nutness,
        beats=beats,
        holdings=holdings,
        blockers=_blockers(hole, visible),
    )


def classify_known_cards(
    hole_cards: Any,
    board: Any,
    *,
    game: str = "holdem",
) -> HandState | None:
    """Classify when the cards are known, and say nothing when they are not.

    The caller that walks a population uses this: a hand nobody showed has no
    state, and returning ``None`` is how it stays out of a distribution instead
    of being counted in a bucket it was never in.
    """
    try:
        return classify(hole_cards, board, game=game)
    except UnknownHoleCards:
        return None


def categories() -> dict[str, tuple[str, ...]]:
    """Every classification this module can produce, for a legend or a filter UI."""
    return {
        "made_hand": MADE_HANDS,
        "pair_detail": PAIR_DETAILS,
        "draw": DRAW_CATEGORIES,
        "nutness": NUTNESS_LEVELS,
        "blocker": BLOCKER_CATEGORIES,
    }


def draw_definitions() -> dict[str, str]:
    """What each draw means, in one sentence, as the doc and the UI print it."""
    return dict(_DRAW_DEFINITIONS)


__all__ = [
    "BLOCKER_BITS",
    "BLOCKER_CATEGORIES",
    "BOARD_CARDS_BY_STREET",
    "CLASSIFIED_GAMES",
    "DRAW_BITS",
    "DRAW_CATEGORIES",
    "MADE_HANDS",
    "MEDIUM_PERCENTILE",
    "NUTNESS_LEVELS",
    "PAIR_DETAILS",
    "STREETS_BY_BOARD_SIZE",
    "STRONG_PERCENTILE",
    "EvaluatorUnavailable",
    "HandState",
    "HandStateError",
    "NotPostflop",
    "UnknownHoleCards",
    "blockers_mask",
    "board_through_street",
    "categories",
    "classify",
    "classify_known_cards",
    "completing_ranks",
    "draw_definitions",
    "draws_mask",
    "has_straight",
    "mask_names",
    "street_of",
]
