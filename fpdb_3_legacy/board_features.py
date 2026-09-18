"""Board texture and runout features, derived once and persisted (issue #295).

A board is not one number. "Ace-high rainbow disconnected" and "paired two-tone
connected" are *sentences* about independent facts -- the suit structure, the
pairing, the rank shape, whether the board is clustered enough for a straight --
and a single mutually exclusive ``texture`` integer can only ever say one of
them. So this module classifies a board twice over:

* ``textureMask`` / ``runoutMask``: orthogonal flags, one bit per fact, so a
  filter can compose "ace-high and rainbow and not connected" with ``&``;
* four vocabulary columns (``suitStructure``, ``pairing``, ``rankBucket``,
  ``connectivity``): the same classification projected onto mutually exclusive
  names, because ``GROUP BY suitStructure`` and a popup label are not bit
  arithmetic.

Both projections come from the same functions here, so they cannot disagree,
and ``test_board_features.py`` pins that they describe the same cards. This is
the single source of truth the epic asked for: ``AutoNotes`` and the custom
auto-note parser delegate their flop vocabulary to ``autonote_flop_texture`` and
``autonote_flop_texture_word`` rather than keeping classifiers of their own.

Facts are about the cards *visible on the board*: no hole cards, no inference
about what anyone holds. ``Hands.texture`` keeps one column only because it
predates this module, and is now formally redefined as the flop texture mask --
see ``docs/board-features.md``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from fpdb_3_legacy import Card
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("board_features")

# --------------------------------------------------------------------------
# The flag catalogue.
#
# Bits are append-only: a stored mask has to keep meaning what it meant when it
# was written, so a flag may be added but never renumbered or reused. The
# catalogue is split in two halves, and the split is meaningful: a texture flag
# describes the board as it stands, a runout flag describes what the last street
# *changed*.
# --------------------------------------------------------------------------
RAINBOW = 1 << 0
TWO_TONE = 1 << 1
MONOTONE = 1 << 2
FLUSH_POSSIBLE = 1 << 3
FOUR_FLUSH = 1 << 4
UNPAIRED = 1 << 5
PAIRED = 1 << 6
TWO_PAIR_BOARD = 1 << 7
TRIPS = 1 << 8
QUADS = 1 << 9
FULL_HOUSE_BOARD = 1 << 10
BROADWAY_HEAVY = 1 << 11
CONNECTED = 1 << 12
SEMI_CONNECTED = 1 << 13
DISCONNECTED = 1 << 14
FOUR_STRAIGHT = 1 << 15

RUNOUT_PAIRED_BOARD = 1 << 16
RUNOUT_FLUSH_COMPLETED = 1 << 17
RUNOUT_STRAIGHT_COMPLETED = 1 << 18
RUNOUT_OVERCARD = 1 << 19
RUNOUT_UNDERCARD = 1 << 20
RUNOUT_BRICK = 1 << 21

TEXTURE_FLAGS: tuple[tuple[str, int], ...] = (
    ("rainbow", RAINBOW),
    ("two_tone", TWO_TONE),
    ("monotone", MONOTONE),
    ("flush_possible", FLUSH_POSSIBLE),
    ("four_flush", FOUR_FLUSH),
    ("unpaired", UNPAIRED),
    ("paired", PAIRED),
    ("two_pair_board", TWO_PAIR_BOARD),
    ("trips", TRIPS),
    ("quads", QUADS),
    ("full_house_board", FULL_HOUSE_BOARD),
    ("broadway_heavy", BROADWAY_HEAVY),
    ("connected", CONNECTED),
    ("semi_connected", SEMI_CONNECTED),
    ("disconnected", DISCONNECTED),
    ("four_straight", FOUR_STRAIGHT),
)

RUNOUT_FLAGS: tuple[tuple[str, int], ...] = (
    ("runout_paired_board", RUNOUT_PAIRED_BOARD),
    ("runout_flush_completed", RUNOUT_FLUSH_COMPLETED),
    ("runout_straight_completed", RUNOUT_STRAIGHT_COMPLETED),
    ("runout_overcard", RUNOUT_OVERCARD),
    ("runout_undercard", RUNOUT_UNDERCARD),
    ("runout_brick", RUNOUT_BRICK),
)

FLAGS: tuple[tuple[str, int], ...] = TEXTURE_FLAGS + RUNOUT_FLAGS
FLAG_BITS: dict[str, int] = dict(FLAGS)
FLAG_NAMES: dict[int, str] = {bit: name for name, bit in FLAGS}

# The words the mutually exclusive columns use, so a reader of a stored row and
# a caller of :func:`describe` see the same vocabulary.
SUIT_RAINBOW = "rainbow"
SUIT_TWO_TONE = "two-tone"
SUIT_MONOTONE = "monotone"
SUIT_THREE_FLUSH = "three-flush"
SUIT_FOUR_FLUSH = "four-flush"

PAIRING_UNPAIRED = "unpaired"
PAIRING_PAIRED = "paired"
PAIRING_TWO_PAIR = "two-pair"
PAIRING_TRIPS = "trips"
PAIRING_FULL_HOUSE = "full-house"
PAIRING_QUADS = "quads"

BUCKET_ACE_HIGH = "ace-high"
BUCKET_KING_HIGH = "king-high"
BUCKET_BROADWAY = "broadway"
BUCKET_MIDDLE = "middle"
BUCKET_LOW = "low"

CONNECTIVITY_CONNECTED = "connected"
CONNECTIVITY_SEMI = "semi-connected"
CONNECTIVITY_DISCONNECTED = "disconnected"

# The structure word a board gets and the flag that *is* that word. How deep a
# suit runs is counted separately, because three of a suit is a monotone flop
# and also, always, a flush-possible board: the count is a fact about the
# cards, the word is what a reader calls them.
# The vocabulary each mutually exclusive column may hold, in the order the
# classifier prefers them. Exported so a reader -- a test, a query builder, a
# preferences page -- has one place to learn the whole set.
SUIT_STRUCTURES = (
    SUIT_RAINBOW,
    SUIT_TWO_TONE,
    SUIT_MONOTONE,
    SUIT_THREE_FLUSH,
    SUIT_FOUR_FLUSH,
)
PAIRINGS = (
    PAIRING_UNPAIRED,
    PAIRING_PAIRED,
    PAIRING_TWO_PAIR,
    PAIRING_TRIPS,
    PAIRING_FULL_HOUSE,
    PAIRING_QUADS,
)
RANK_BUCKETS = (
    BUCKET_ACE_HIGH,
    BUCKET_KING_HIGH,
    BUCKET_BROADWAY,
    BUCKET_MIDDLE,
    BUCKET_LOW,
)
CONNECTIVITIES = (
    CONNECTIVITY_CONNECTED,
    CONNECTIVITY_SEMI,
    CONNECTIVITY_DISCONNECTED,
)

_SUIT_STRUCTURE_BITS = {
    "": 0,
    SUIT_RAINBOW: RAINBOW,
    SUIT_TWO_TONE: TWO_TONE,
    SUIT_MONOTONE: MONOTONE,
    SUIT_THREE_FLUSH: 0,
    SUIT_FOUR_FLUSH: 0,
}

# The columns a stored feature row carries, in the order the insert statement
# spells them out. ``boardId`` is the run (1 unless the hand was run several
# times) and ``street`` is the position of the community street in the hand's
# own round list, so 1 is the flop and 3 the river in Hold'em and Omaha.
BOARD_FEATURE_COLUMNS: tuple[str, ...] = (
    "boardId",
    "street",
    "streetName",
    "cardCount",
    "textureMask",
    "runoutMask",
    "topRank",
    "suitStructure",
    "pairing",
    "rankBucket",
    "connectivity",
)

BOARD_FEATURE_DEFAULTS: dict[str, Any] = {
    "boardId": 1,
    "street": 0,
    "streetName": "",
    "cardCount": 0,
    "textureMask": 0,
    "runoutMask": 0,
    "topRank": 0,
    "suitStructure": "",
    "pairing": "",
    "rankBucket": "",
    "connectivity": "",
}

# Ranks a board can be made of, and the rank of a Broadway card.
CARD_RANKS = {
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "T": 10,
    "J": 11,
    "Q": 12,
    "K": 13,
    "A": 14,
}
BROADWAY_FLOOR = 10
ACE = 14
# A straight needs five consecutive ranks; a board is clustered when that many
# or more of its own ranks fall inside one such window.
STRAIGHT_WINDOW = 5
MIN_DISTINCT_FOR_STRAIGHT = 3
MAX_DISTINCT_FOR_STRAIGHT = 4
EMPTY_CARD_MARKERS = frozenset({"", "0", "0x", "-", "none", "null", "??"})

# Suit structure words by the number of cards they describe: "monotone" is a
# three-card word, so a four- or five-card board gets a flush-shaped word
# instead and keeps the count out of the sentence.
THREE_CARD_STRUCTURES = 3


def card_string(card: Any) -> str:
    """The two-character form of a card, or ``""`` when there is no card.

    Accepts what the pipeline actually carries around: the two-character string
    a parser produces, the 1..52 integer the database stores, a ``(rank, suit)``
    pair, and every spelling of "no card" (``None``, ``"0x"``, ``0``).
    """
    if card is None or isinstance(card, bool):
        return ""
    if isinstance(card, int):
        return Card.valueSuitFromCard(card)
    if isinstance(card, (tuple, list)):
        return _card_string_from_pair(card)
    text = str(card).strip()
    if not text or text.lower() in EMPTY_CARD_MARKERS:
        return ""
    if text.isdigit():
        return Card.valueSuitFromCard(int(text))
    return text


def _card_string_from_pair(card: Any) -> str:
    if len(card) != 2 or not isinstance(card[1], str):  # noqa: PLR2004 - a card pair is two long
        return ""
    try:
        encoded = Card.cardFromValueSuit(int(card[0]), card[1].lower())
    except (TypeError, ValueError):
        return ""
    return Card.valueSuitFromCard(encoded)


def visible_cards(cards: Any) -> tuple[str, ...]:
    """Normalize a sequence of cards, dropping the placeholders for "not dealt"."""
    if cards is None or isinstance(cards, (str, bytes)):
        return ()
    try:
        iterable = list(cards)
    except TypeError:
        return ()
    return tuple(text for text in (card_string(card) for card in iterable) if text)


def card_rank(card: str) -> int:
    """The rank of a normalized card: 2..14, or 0 when it is not a card."""
    return CARD_RANKS.get(card[0].upper(), 0) if card else 0


def card_suit(card: str) -> str:
    """The suit letter of a normalized card, or ``""`` when there is none."""
    return card[-1].lower() if card and card[-1].lower() in {"h", "d", "c", "s"} else ""


def flag_names(mask: int) -> tuple[str, ...]:
    """The names of every flag set in ``mask``, in catalogue order."""
    return tuple(name for name, bit in FLAGS if mask & bit)


def suit_structure(cards: Sequence[str]) -> str:
    """Suit structure of a three-card board, or the flush shape of a longer one."""
    if not cards:
        return ""
    counted = Counter(suit for suit in (card_suit(card) for card in cards) if suit)
    most = max(counted.values(), default=0)
    if len(cards) <= THREE_CARD_STRUCTURES:
        if most == 3:  # noqa: PLR2004 - three of a suit is a monotone flop
            return SUIT_MONOTONE
        if most == 2:  # noqa: PLR2004 - two of a suit is a two-tone flop
            return SUIT_TWO_TONE
        return SUIT_RAINBOW
    if most >= 4:  # noqa: PLR2004 - four of a suit is a four-flush
        return SUIT_FOUR_FLUSH
    if most == 3:  # noqa: PLR2004 - three of a suit, four or five cards seen
        return SUIT_THREE_FLUSH
    if most == 2:  # noqa: PLR2004
        return SUIT_TWO_TONE
    return SUIT_RAINBOW


def pairing(cards: Sequence[str]) -> str:
    """How the board pairs itself, strongest pairing first."""
    ranks = Counter(rank for rank in (card_rank(card) for card in cards) if rank)
    counts = sorted(ranks.values(), reverse=True)
    most = counts[0] if counts else 0
    paired_ranks = sum(1 for count in counts if count >= 2)  # noqa: PLR2004
    if most >= 4:  # noqa: PLR2004 - quad
        return PAIRING_QUADS
    if most == 3 and paired_ranks >= 2:  # noqa: PLR2004 - trips plus a pair
        return PAIRING_FULL_HOUSE
    if most == 3:  # noqa: PLR2004
        return PAIRING_TRIPS
    if paired_ranks >= 2:  # noqa: PLR2004 - two different ranks paired
        return PAIRING_TWO_PAIR
    if most == 2:  # noqa: PLR2004
        return PAIRING_PAIRED
    return PAIRING_UNPAIRED


def rank_bucket(cards: Sequence[str]) -> str:
    """The bucket of the board's highest card.

    Boundaries: ace, king, then Broadway (T/Q/J-high), middle (8/9-high) and low
    (7-high or lower) -- a seven-high board is the "low connected" flop of the
    #308 corpus, not a middle one.
    """
    ranks = [rank for rank in (card_rank(card) for card in cards) if rank]
    if not ranks:
        return ""
    top = max(ranks)
    if top == ACE:
        return BUCKET_ACE_HIGH
    if top == 13:  # noqa: PLR2004 - the king
        return BUCKET_KING_HIGH
    if top >= BROADWAY_FLOOR:
        return BUCKET_BROADWAY
    if top >= 8:  # noqa: PLR2004 - 8 or 9 high
        return BUCKET_MIDDLE
    return BUCKET_LOW


def _rank_values(cards: Sequence[str]) -> list[int]:
    """The board's distinct ranks, with the ace counted low as well as high."""
    values = {rank for rank in (card_rank(card) for card in cards) if rank}
    if ACE in values:
        values.add(1)
    return sorted(values)


def _longest_cluster(values: Sequence[int]) -> int:
    """How many distinct ranks the fullest five-rank window holds."""
    best = 0
    for low in range(1, ACE - STRAIGHT_WINDOW + 2):
        held = sum(1 for value in values if low <= value < low + STRAIGHT_WINDOW)
        best = max(best, held)
    return best


def _cluster_span(cards: Sequence[str]) -> int:
    """Span of the board's ranks, taking the wheel reading of an ace when shorter.

    An ace reads high or low but not both at once, which is why the wheel span
    replaces the fourteen rather than adding a one beside it: A-2-3 spans 2 as a
    wheel, and 12 as an ace-high board, and the shorter reading is the one that
    says whether the board clusters.
    """
    ranks = [rank for rank in (card_rank(card) for card in cards) if rank]
    if not ranks:
        return 0
    wheel = sorted({1 if rank == ACE else rank for rank in ranks})
    return min(max(ranks) - min(ranks), wheel[-1] - wheel[0])


def connectivity(cards: Sequence[str]) -> str:
    """How clustered the board is, and therefore whether a straight is reachable.

    ``connected`` -- the whole board fits one five-rank window, so the flop alone
    has three ranks to a straight. ``semi-connected`` -- some window holds three
    board ranks while the board as a whole does not cluster, which is what a
    turn or river adds to a board whose straight chances survived. Anything else
    is ``disconnected``: no five-rank window holds three of the board's ranks,
    so no two hole cards can complete a straight.
    """
    values = _rank_values(cards)
    distinct = len({rank for rank in (card_rank(card) for card in cards) if rank})
    if _longest_cluster(values) < MIN_DISTINCT_FOR_STRAIGHT:
        return CONNECTIVITY_DISCONNECTED
    if distinct >= MIN_DISTINCT_FOR_STRAIGHT and _cluster_span(cards) <= STRAIGHT_WINDOW - 1:
        return CONNECTIVITY_CONNECTED
    return CONNECTIVITY_SEMI


def texture_mask(cards: Sequence[str]) -> int:
    """The orthogonal texture flags of the board as it stands.

    Every flag is the meaning of one word the vocabulary columns already say,
    through the dictionaries below, plus the two facts those words cannot
    express: how many Broadway cards the board holds, and whether it holds four
    ranks inside one five-rank window. Sharing the words is what keeps the mask
    and the columns from describing the same cards differently.

    No cards, no facts: an empty board carries no flag rather than the flags an
    empty set of ranks would trivially satisfy.
    """
    if not cards:
        return 0
    ranks = [rank for rank in (card_rank(card) for card in cards) if rank]
    mask = (
        _SUIT_STRUCTURE_BITS[suit_structure(cards)]
        | _suit_depth_bits(_suit_depth(cards))
        | _PAIRING_BITS[pairing(cards)]
        | _CONNECTIVITY_BITS[connectivity(cards)]
    )
    if sum(1 for rank in ranks if rank >= BROADWAY_FLOOR) >= 3:  # noqa: PLR2004
        mask |= BROADWAY_HEAVY
    if _longest_cluster(_rank_values(cards)) >= MAX_DISTINCT_FOR_STRAIGHT:
        mask |= FOUR_STRAIGHT
    return mask


def _suit_depth_bits(depth: int) -> int:
    """How deep the longest suit runs: three of a suit is a flush draw, four a four-flush."""
    mask = 0
    if depth >= 3:  # noqa: PLR2004
        mask |= FLUSH_POSSIBLE
    if depth >= 4:  # noqa: PLR2004
        mask |= FOUR_FLUSH
    return mask


# What each pairing word means as flags. Two pair and trips both imply a pair,
# and a full house is a triple with a separate pair, so the words carry their
# own consequences -- which is exactly why the flag set is defined here once.
_PAIRING_BITS = {
    PAIRING_UNPAIRED: UNPAIRED,
    PAIRING_PAIRED: PAIRED,
    PAIRING_TWO_PAIR: PAIRED | TWO_PAIR_BOARD,
    PAIRING_TRIPS: PAIRED | TRIPS,
    PAIRING_FULL_HOUSE: PAIRED | TRIPS | FULL_HOUSE_BOARD,
    PAIRING_QUADS: PAIRED | QUADS,
}

_CONNECTIVITY_BITS = {
    CONNECTIVITY_CONNECTED: CONNECTED,
    CONNECTIVITY_SEMI: SEMI_CONNECTED,
    CONNECTIVITY_DISCONNECTED: DISCONNECTED,
}


@dataclass(frozen=True)
class BoardFeatures:
    """One board as it stands, with what the last street changed."""

    cards: tuple[str, ...]
    textureMask: int
    runoutMask: int
    suitStructure: str
    pairing: str
    rankBucket: str
    connectivity: str
    topRank: int

    @property
    def cardCount(self) -> int:
        return len(self.cards)

    @property
    def flags(self) -> tuple[str, ...]:
        return flag_names(self.textureMask | self.runoutMask)

    @property
    def straightPossible(self) -> bool:
        """Whether two hole cards can make a straight with this board."""
        return self.connectivity != CONNECTIVITY_DISCONNECTED

    @property
    def label(self) -> str:
        return describe(self)

    def row(self) -> dict[str, Any]:
        """The classified columns, keyed like the stored columns."""
        return {
            "cardCount": self.cardCount,
            "textureMask": self.textureMask,
            "runoutMask": self.runoutMask,
            "topRank": self.topRank,
            "suitStructure": self.suitStructure,
            "pairing": self.pairing,
            "rankBucket": self.rankBucket,
            "connectivity": self.connectivity,
        }


def classify_visible(cards: Sequence[str]) -> BoardFeatures:
    """Classify a board that has already been normalized.

    The runout mask stays 0: a board on its own has nothing to compare against,
    and :func:`classify_street` is what adds the deltas.
    """
    return BoardFeatures(
        cards=tuple(cards),
        textureMask=texture_mask(cards),
        runoutMask=0,
        suitStructure=suit_structure(cards),
        pairing=pairing(cards),
        rankBucket=rank_bucket(cards),
        connectivity=connectivity(cards),
        topRank=max((card_rank(card) for card in cards), default=0),
    )


def classify_board(cards: Any) -> BoardFeatures:
    """Classify a board given as card strings, encoded integers or both."""
    return classify_visible(visible_cards(cards))


def classify_street(previous: Any, cards: Any) -> BoardFeatures:
    """Classify the board after ``cards`` were added to ``previous``.

    ``previous`` is the board entering the street and ``cards`` only what the
    street dealt, so the runout flags can say what changed rather than what is.
    """
    before = visible_cards(previous)
    added = visible_cards(cards)
    after = before + added
    features = classify_visible(after)
    runout = runout_mask(before, added, after)
    return BoardFeatures(
        cards=features.cards,
        textureMask=features.textureMask,
        runoutMask=runout,
        suitStructure=features.suitStructure,
        pairing=features.pairing,
        rankBucket=features.rankBucket,
        connectivity=features.connectivity,
        topRank=features.topRank,
    )


def runout_mask(previous: Sequence[str], added: Sequence[str], visible: Sequence[str]) -> int:
    """What the newly dealt cards are, on the board they made.

    Every flag here is about the cards this street dealt -- what they paired,
    which flush and straight chances they brought with them, whether they moved
    the top or the bottom of the board -- while the texture mask describes the
    board as a whole. That split is what lets a filter ask both "what did the
    turn card do" and "what does this board look like", and it is why the depth
    of a draw lives in the texture flags (``four_flush``, ``four_straight``)
    rather than being restated here.
    """
    if not previous or not added:
        return 0
    before_ranks = {rank for rank in (card_rank(card) for card in previous) if rank}
    added_ranks = [rank for rank in (card_rank(card) for card in added) if rank]
    if not added_ranks or not before_ranks:
        return 0
    mask = 0
    if any(rank in before_ranks for rank in added_ranks):
        mask |= RUNOUT_PAIRED_BOARD
    if _joins_a_flush(added, visible):
        mask |= RUNOUT_FLUSH_COMPLETED
    if _joins_a_straight(added, visible):
        mask |= RUNOUT_STRAIGHT_COMPLETED
    highest = max(added_ranks)
    if highest > max(before_ranks):
        mask |= RUNOUT_OVERCARD
    if highest < min(before_ranks):
        mask |= RUNOUT_UNDERCARD
    # A brick is defined by exclusion: it is the card that paired nothing,
    # brought no flush or straight chance, and did not even move the top or the
    # bottom of the board. Every other runout flag is decided above it, so the
    # two can never be set together.
    if not mask:
        mask |= RUNOUT_BRICK
    return mask


def _suit_depth(cards: Sequence[str]) -> int:
    """How many cards the board's longest suit holds."""
    counted = Counter(suit for suit in (card_suit(card) for card in cards) if suit)
    return max(counted.values(), default=0)


def _flush_possible(cards: Sequence[str]) -> bool:
    return _suit_depth(cards) >= 3  # noqa: PLR2004 - three of a suit


def _joins_a_flush(added: Sequence[str], visible: Sequence[str]) -> bool:
    """Whether a card just dealt is of the suit the board now holds three of.

    True both when the street opened the flush (the third card of a suit) and
    when it deepened one (the fourth), because both are ways for the street's
    card to be a flush card.
    """
    if not _flush_possible(visible):
        return False
    counted = Counter(suit for suit in (card_suit(card) for card in visible) if suit)
    deepest = max(counted.values(), default=0)
    deepest_suits = {suit for suit, count in counted.items() if count == deepest}
    return any(card_suit(card) in deepest_suits for card in added)


def _joins_a_straight(added: Sequence[str], visible: Sequence[str]) -> bool:
    """Whether a card just dealt sits in a five-rank window the board now fills.

    The window has to hold three or more of the board's ranks, which is exactly
    when two hole cards can complete a straight: the new card is part of the
    draw, whether it opened it or joined one that was already live.
    """
    values = set(_rank_values(visible))
    added_values = {rank for rank in (card_rank(card) for card in added) if rank}
    if ACE in added_values:
        added_values.add(1)
    if not added_values:
        return False
    for low in range(1, ACE - STRAIGHT_WINDOW + 2):
        window = set(range(low, low + STRAIGHT_WINDOW))
        if not added_values & window:
            continue
        if len(values & window) >= MIN_DISTINCT_FOR_STRAIGHT:
            return True
    return False


def describe(features: BoardFeatures) -> str:
    """A sentence about the board, for a popup or a log line."""
    parts = [features.rankBucket, features.suitStructure, features.connectivity]
    if features.pairing != PAIRING_UNPAIRED:
        parts.append(features.pairing)
    if features.textureMask & BROADWAY_HEAVY:
        parts.append("broadway-heavy")
    sentence = ", ".join(part for part in parts if part)
    runout = [name for name in flag_names(features.runoutMask)]
    if runout:
        sentence = f"{sentence} -- {', '.join(runout)}"
    return sentence


# --------------------------------------------------------------------------
# Reading a hand: one row per board and community street.
# --------------------------------------------------------------------------
def _board_dict(hand: Any) -> dict[str, Any]:
    board = getattr(hand, "board", None)
    return board if isinstance(board, dict) else {}


def _community_streets(hand: Any) -> list[str]:
    streets = getattr(hand, "communityStreets", None)
    if not streets or isinstance(streets, str):
        return []
    try:
        return [str(street) for street in streets]
    except TypeError:
        return []


def _run_count(hand: Any) -> int:
    run_it_times = getattr(hand, "runItTimes", 1)
    if isinstance(run_it_times, bool) or not isinstance(run_it_times, int):
        return 1
    return max(1, run_it_times)


def _street_cards(board: dict[str, Any], street: str, run: int) -> tuple[str, ...]:
    """The cards a street dealt on one run.

    Running a board twice deals onto numbered streets (``TURN1``/``TURN2``),
    while a street shared by every run keeps its plain name; the fallback is the
    one ``DerivedStats.getBoardsList`` already uses to rebuild complete boards
    for equity, so both agree on what each run was dealt.
    """
    numbered = visible_cards(board.get(f"{street}{run}"))
    if numbered:
        return numbered
    return visible_cards(board.get(street))


def derive_board_rows(hand: Any) -> list[dict[str, Any]]:
    """One row per board and community street that was dealt.

    Stud, razz and the draw games deal no community cards, so they produce no
    rows -- their boards are per player and this dimension does not apply.
    """
    board = _board_dict(hand)
    streets = _community_streets(hand)
    if not board or not streets:
        return []
    rows: list[dict[str, Any]] = []
    for run in range(1, _run_count(hand) + 1):
        previous: tuple[str, ...] = ()
        for position, street in enumerate(streets, start=1):
            cards = _street_cards(board, street, run)
            if not cards:
                continue
            features = classify_street(previous, cards)
            previous = features.cards
            rows.append(
                {
                    "boardId": run,
                    "street": position,
                    "streetName": street.lower(),
                    **features.row(),
                },
            )
    return rows


def flop_texture_mask(rows: Sequence[dict[str, Any]]) -> int:
    """The flop texture mask of the first board, or 0 when no flop was seen.

    0 is unambiguous: every three-card flop sets a suit structure flag, so a
    board with no flop cannot be confused with a board without features.
    """
    for row in rows:
        if row.get("street") == 1 and row.get("boardId") == 1:
            return int(row.get("textureMask") or 0)
    return 0


# --------------------------------------------------------------------------
# The projections AutoNotes already reads. Same classifier, old vocabulary.
# --------------------------------------------------------------------------
def autonote_flop_texture(cards: Any) -> dict[str, Any] | None:
    """The flop texture dict the AutoNotes rules consume."""
    visible = visible_cards(cards)
    if len(visible) < 3:  # noqa: PLR2004 - a flop is three cards
        return None
    flop = visible[:3]
    mask = classify_visible(flop).textureMask
    monotone = bool(mask & MONOTONE)
    two_tone = bool(mask & TWO_TONE)
    connected = bool(mask & CONNECTED)
    paired = bool(mask & (PAIRED | TWO_PAIR_BOARD | TRIPS | QUADS))
    labels = []
    if paired:
        labels.append("paired")
    if monotone:
        labels.append("monotone")
    elif two_tone:
        labels.append("two-tone")
    if connected:
        labels.append("connected")
    return {
        "board": " ".join(flop),
        "paired": paired,
        "monotone": monotone,
        "two_tone": two_tone,
        "connected": connected,
        "wet": bool(monotone or two_tone or connected),
        "label": ", ".join(labels) or "dry",
    }


def autonote_flop_texture_word(cards: Any) -> str:
    """The single word ``board.flop_texture`` yields in a custom rule."""
    visible = visible_cards(cards)
    if len(visible) < 3:  # noqa: PLR2004 - no flop, no texture
        return "dry"
    mask = classify_visible(visible[:3]).textureMask
    if mask & (PAIRED | TWO_PAIR_BOARD | TRIPS | QUADS):
        return "paired"
    if mask & MONOTONE:
        return "monotone"
    if mask & TWO_TONE:
        return "twotone"
    return "rainbow"
