"""The 169 Hold'em starting-hand classes: ids, labels, combos, and the SQL (#301).

A range explorer needs one thing above all: a *single* definition of what a cell
means. "AKs" is a set of four exact combos, "AKo" a set of twelve, "AA" a set of
six, and a hand whose cards were never shown is not in any of them. This module
is that definition, on both sides of the wire:

* ``Card.twoStartCards`` is the codebase's canonical class id (1..169, with
  ``HOLDEM_UNKNOWN_HAND`` = 170 for "we do not know"), and ``twoStartCardString``
  is its canonical label. Both are reused, not re-invented -- the ids are the
  primary key of the ``StartCards`` table, so a second numbering would be a
  second truth.
* :func:`holdem_class_expression` is the same classification in SQL, over the
  ``card1``/``card2`` columns of a hand-player. It is verified exhaustively
  against the Python function for all 2 704 ordered card pairs, so a cell in the
  grid and a filter in a query cannot disagree about what a class contains.

Hold'em only, deliberately: an Omaha hand's first two cards are not a Hold'em
starting hand, so classifying one would produce a well-formed lie. The range
explorer refuses a population that is not Hold'em rather than showing that.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Final

from .Card import HOLDEM_UNKNOWN_HAND, decodeStartHandValue, twoStartCards, twoStartCardString

# The unknown class: two unknown cards, and the one cell that must never be
# distributed across the others.
UNKNOWN_ID: Final = HOLDEM_UNKNOWN_HAND
UNKNOWN_LABEL: Final = "xx"

# Ranks, strongest first, as every 13x13 grid is drawn. ``T`` is the ten.
RANKS: Final[tuple[str, ...]] = tuple("AKQJT98765432")
SUITS: Final[tuple[str, ...]] = ("h", "d", "c", "s")

ALL_IDS: Final[tuple[int, ...]] = tuple(range(1, UNKNOWN_ID))  # 1..169
RANK_CODES: Final[dict[str, int]] = {rank: 14 - index for index, rank in enumerate(RANKS)}
"""Rank letter to its card value 2..14, so ``RANK_CODES["A"] == 14``.

Not the same map as ``RANKS`` on purpose: ``RANKS`` is the *drawing* order
(strongest first), which is what a grid's rows and columns are, while two cards
are classified by their values (ace high). Confusing the two is how "AKs"
becomes an offsuit hand.
"""
RANK_ORDER: Final[dict[str, int]] = {rank: index for index, rank in enumerate(RANKS)}
"""Rank letter to its strength index 0..12, ``RANK_ORDER["A"] == 0``."""

# A pair is C(4,2) = 6 exact combinations, a suited class 4, an offsuit 12, and
# the whole deck deals C(52,2) = 1326.
COMBOS_BY_KIND: Final[dict[str, int]] = {"pair": 6, "suited": 4, "offsuit": 12}
DEALT_COMBOS: Final = 1326


class UnknownClass(ValueError):
    """A label that is not one of the 169 classes (or the unknown one)."""


def class_id_from_ranks(value1: int, suit1: str, value2: int, suit2: str) -> int:
    """The canonical class id of two ranks and suits, 170 when either is unknown."""
    return twoStartCards(value1, suit1, value2, suit2)


def rank_of_card(card: int) -> int:
    """The rank value (2..14) of a stored card int, 0 for an unknown card."""
    return 0 if card <= 0 else (card - 1) % 13 + 2


def suit_of_card(card: int) -> str:
    """The suit letter of a stored card int, empty for an unknown card."""
    return "" if card <= 0 else SUITS[(card - 1) // 13]


def class_id_from_cards(card1: int, card2: int) -> int:
    """The class id of two stored card ints, 170 when either card is unknown.

    Zero is fpdb's unknown card (a hand that was not shown), and it stays
    unknown here: the alternative -- picking a class for the cards we cannot
    see -- is how a range explorer starts inventing a range.
    """
    return class_id_from_ranks(rank_of_card(card1), suit_of_card(card1), rank_of_card(card2), suit_of_card(card2))


def is_unknown(class_id: int) -> bool:
    return class_id == UNKNOWN_ID


def label(class_id: int) -> str:
    """The label of a class id, ``xx`` for unknown and for anything outside 1..170."""
    if class_id == UNKNOWN_ID:
        return UNKNOWN_LABEL
    if class_id not in ALL_IDS:
        return UNKNOWN_LABEL
    return twoStartCardString(class_id)


def label_of_cards(card1: int, card2: int) -> str:
    """The label of two stored card ints."""
    return label(class_id_from_cards(card1, card2))


def kind(class_id: int) -> str:
    """``pair``, ``suited``, ``offsuit`` or ``unknown`` -- what the label says."""
    text = label(class_id)
    if text == UNKNOWN_LABEL:
        return "unknown"
    if len(text) == 2:
        return "pair"
    return "suited" if text.endswith("s") else "offsuit"


def combos(class_id: int) -> int:
    """How many exact two-card combinations the class stands for."""
    return COMBOS_BY_KIND.get(kind(class_id), 0)


def parse_label(text: str) -> tuple[str, str, str]:
    """Split a label into (high rank, low rank, kind), refusing anything else.

    ``AKs`` and ``AKo`` are the suited and offsuit forms; a pair is written
    ``AA``. A bare ``AK`` is refused rather than guessed: suitedness is half of
    what the class means, and silently reading it as offsuit would make one cell
    of the grid a different cell of the grid.
    """
    token = str(text).strip()
    if token.lower() == UNKNOWN_LABEL:
        return (UNKNOWN_LABEL, UNKNOWN_LABEL, "unknown")
    upper = token.upper()
    if len(upper) == 3 and upper[2] in ("S", "O"):
        high, low, suffix = upper[0], upper[1], upper[2].lower()
    elif len(upper) == 2:
        high, low, suffix = upper[0], upper[1], ""
    else:
        raise UnknownClass(f"Not a starting-hand class: {text!r} (write e.g. 'AKs', 'AKo' or 'AA')")
    if high not in RANK_CODES or low not in RANK_CODES:
        raise UnknownClass(f"Unknown rank in {text!r}; ranks are {''.join(RANKS)}")
    if RANK_CODES[low] > RANK_CODES[high]:
        raise UnknownClass(f"The high rank comes first: {text!r} should be {low}{high}{suffix}")
    if high == low:
        if suffix:
            raise UnknownClass(f"A pair has no suitedness: {text!r} should be {high}{low}")
        return (high, low, "pair")
    if not suffix:
        raise UnknownClass(
            f"Say whether {text!r} is suited or offsuit: write {upper}s or {upper}o",
        )
    return (high, low, "suited" if suffix == "s" else "offsuit")


def class_id_of_label(text: str) -> int:
    """The class id of a label, refusing a malformed one."""
    high, low, class_kind = parse_label(text)
    if class_kind == "unknown":
        return UNKNOWN_ID
    return class_id_from_ranks(RANK_CODES[high], "h", RANK_CODES[low], "h" if class_kind == "suited" else "s")


def class_ids(values: Iterable[str | int]) -> list[int]:
    """Labels (or ids) to class ids, in order, refusing an unknown label.

    Ids are accepted because the engine's ``starting_hand_id`` dimension returns
    them: a caller that grouped by the dimension can feed the value straight
    back in as a filter without a round trip through the labels.
    """
    out: list[int] = []
    for value in values:
        if isinstance(value, bool):
            raise UnknownClass(f"Not a starting-hand class: {value!r}")
        if isinstance(value, int):
            if value == UNKNOWN_ID or value in ALL_IDS:
                out.append(value)
            else:
                raise UnknownClass(f"Class id out of range: {value!r} (1..169, or {UNKNOWN_ID} for unknown)")
            continue
        out.append(class_id_of_label(str(value)))
    return out


def grid_ids() -> tuple[tuple[int, ...], ...]:
    """The 13x13 grid of class ids, ranks descending, pairs on the diagonal.

    Above the diagonal is suited (the two cards share a suit); below it is
    offsuit, with the label's ranks reversed so the high card still comes first.
    """
    return tuple(
        tuple(
            class_id_of_label(
                f"{row}{col}"
                if row == col
                else f"{row}{col}s"
                if RANK_ORDER[row] < RANK_ORDER[col]
                else f"{col}{row}o",
            )
            for col in RANKS
        )
        for row in RANKS
    )


def grid_labels() -> tuple[tuple[str, ...], ...]:
    """The 13x13 grid of labels -- the widget's cells, from the one definition."""
    return tuple(tuple(label(class_id) for class_id in row) for row in grid_ids())


def grid_position(text: str) -> tuple[int, int]:
    """A class's (row, column) in the grid, refusing a malformed label."""
    high, low, class_kind = parse_label(text)
    if class_kind == "unknown":
        raise UnknownClass("The unknown class has no place in the grid")
    row = RANK_ORDER[high]
    col = RANK_ORDER[low]
    return (row, col) if class_kind in ("pair", "suited") else (col, row)


def combos_of(values: Iterable[str | int]) -> int:
    """The exact combinations a set of classes stands for."""
    return sum(combos(class_id) for class_id in class_ids(values))


def share_of_dealt(values: Iterable[str | int]) -> float:
    """The share of all 1326 dealt combinations a set of classes covers."""
    return combos_of(values) / DEALT_COMBOS


def holdem_class_expression(alias: str = "HP.") -> str:
    """The class id of a hand-player's two cards, as portable SQL.

    Card ints are fpdb's ``1..52`` (``Card.encodeCard``), so a rank is
    ``(card - 1) % 13`` and a suit ``(card - 1) / 13``; zero means unknown, and
    an unknown card makes the whole hand unknown. The four branches below are
    ``twoStartCards`` with its ``MAX``/``MIN`` spelled out, because scalar
    ``MAX(a, b)`` is not portable across MySQL, PostgreSQL and SQLite.
    """
    rank1 = f"(({alias}card1 - 1) % 13)"
    rank2 = f"(({alias}card2 - 1) % 13)"
    # MySQL's ``/`` is decimal division, unlike SQLite's integer result for
    # these positive card values. Subtracting the remainder first makes the
    # numerator divisible by 13, so the quotient is identical on all three
    # supported backends without relying on a dialect-only FLOOR or DIV.
    suit1 = f"((({alias}card1 - 1) - (({alias}card1 - 1) % 13)) / 13)"
    suit2 = f"((({alias}card2 - 1) - (({alias}card2 - 1) % 13)) / 13)"
    return (
        f"CASE WHEN {alias}card1 > 0 AND {alias}card2 > 0 THEN\n"
        f"      CASE\n"
        f"        WHEN {rank1} = {rank2} THEN 14 * {rank1} + 1\n"
        f"        WHEN {suit1} = {suit2} AND {rank1} > {rank2} THEN 13 * {rank1} + {rank2} + 1\n"
        f"        WHEN {suit1} = {suit2} THEN 13 * {rank2} + {rank1} + 1\n"
        f"        WHEN {rank1} > {rank2} THEN 13 * {rank2} + {rank1} + 1\n"
        f"        ELSE 13 * {rank1} + {rank2} + 1\n"
        f"      END\n"
        f"    ELSE {UNKNOWN_ID} END"
    )


def decode(game: str, value: int) -> str:
    """A stored starting-hand value as a label, for callers that read the database.

    Delegates to ``Card.decodeStartHandValue`` so the range explorer and the
    existing reports decode the same column the same way.
    """
    return decodeStartHandValue(game, value)


def labels(values: Sequence[str | int]) -> list[str]:
    """A sequence of labels or ids as labels."""
    return [label(class_id) for class_id in class_ids(values)]


__all__ = [
    "ALL_IDS",
    "COMBOS_BY_KIND",
    "DEALT_COMBOS",
    "RANKS",
    "RANK_CODES",
    "RANK_ORDER",
    "SUITS",
    "UNKNOWN_ID",
    "UNKNOWN_LABEL",
    "UnknownClass",
    "class_id_from_cards",
    "class_id_from_ranks",
    "class_id_of_label",
    "class_ids",
    "combos",
    "combos_of",
    "decode",
    "grid_ids",
    "grid_labels",
    "grid_position",
    "holdem_class_expression",
    "is_unknown",
    "kind",
    "label",
    "label_of_cards",
    "labels",
    "parse_label",
    "rank_of_card",
    "share_of_dealt",
    "suit_of_card",
]
