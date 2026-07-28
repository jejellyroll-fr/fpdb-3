"""Automatic notes for All-in or Fold Omaha.

The other rule sets read a hand as a sequence of decisions; this game has one.
That single decision is also the only thing a player ever reveals about
themselves, so the useful note is not *that* they moved in -- everyone does,
constantly -- but *what they moved in with*, on the flop everyone could see.

That is only knowable when the hand was shown down, which is why the note is
attached to the shove rather than to the fold: a fold shows nothing. Over a
session the notes accumulate into the one read this format allows, namely how
thin this player is willing to get their stack in.

Nothing here estimates equity. Classifying a holding is reading the cards;
saying it was a bad shove is a claim about how often it wins, which needs a
range and an evaluation neither of which this does. A wrap with two backdoors
and a blocker looks poor written down and is not, and a note that called it
poor would be worse than no note. So the note records what was held, and
leaves the judgement to whoever reads it.
"""

from __future__ import annotations

from typing import Any

RULE_SET_AOF_OMAHA = "aof_omaha_allin"

AOF_OMAHA_CATEGORY = "aof_omaha"
_OMAHA_HOLE_CARDS = 4
_FLOP_CARDS = 3
_PAIR = 2
_TRIPS = 3
_RANK_ORDER = "23456789TJQKA"
_FIVE_CARDS = 5
_QUADS = 4
_CARDS_PER_RANK = 4


def is_aof_omaha(hand: Any) -> bool:
    """True for a hand of All-in or Fold Omaha."""
    gametype = getattr(hand, "gametype", {}) or {}
    return str(gametype.get("category", "")).lower() == AOF_OMAHA_CATEGORY


def _decision_street(hand: Any) -> str:
    """The street the single decision is taken on.

    fpdb models this game with the flop as street zero, so the one round of
    betting is the flop -- there is no preflop to look on.
    """
    streets = list(getattr(hand, "actionStreets", []) or [])
    return streets[1] if len(streets) > 1 else "FLOP"


def _went_all_in(hand: Any, player: str) -> bool:
    street = _decision_street(hand)
    for raw in (getattr(hand, "actions", {}) or {}).get(street, []):
        if len(raw) >= _PAIR and raw[0] == player and isinstance(raw[-1], bool) and raw[-1]:
            return True
    return False


def _cards(hand: Any, player: str) -> list[str]:
    try:
        return [card for card in hand.join_holecards(player, asList=True) if card and card != "0x"]
    except (AttributeError, KeyError, TypeError, ValueError):
        return []


def _flop(hand: Any) -> list[str]:
    board = getattr(hand, "board", {}) or {}
    return [str(card) for card in board.get("FLOP", []) if str(card) and str(card) != "0x"][:_FLOP_CARDS]


def _made_hand(hole: list[str], flop: list[str]) -> str:
    """The best five-card hand available, named plainly.

    Omaha plays exactly two hole cards and three board cards, so the six
    combinations are enumerated and the best one kept. Reasoning about which
    ranks pair the board instead got two things wrong: a made straight or
    flush was never noticed at all, and one card matching a board that was
    already paired was announced as a full house -- a single five with 5-5-4
    down makes trips, not a boat.
    """
    best = 0
    for i, first in enumerate(hole):
        for second in hole[i + 1 :]:
            best = max(best, _rank_five([first, second, *flop]))
    return _MADE_HAND_NAMES[best]


def _rank_five(cards: list[str]) -> int:
    """Score one five-card hand; bigger is better, on the scale below."""
    ranks = [card[0].upper() for card in cards if len(card) >= _PAIR]
    suits = [card[-1].lower() for card in cards if len(card) >= _PAIR]
    if len(ranks) < _FIVE_CARDS:
        return 0
    counts = sorted((ranks.count(rank) for rank in set(ranks)), reverse=True)
    flush = len(set(suits)) == 1
    straight = _is_run(ranks)

    if straight and flush:
        return 8
    if counts[0] >= _QUADS:
        return 7
    if counts[0] == _TRIPS and len(counts) > 1 and counts[1] >= _PAIR:
        return 6
    if flush:
        return 5
    if straight:
        return 4
    if counts[0] == _TRIPS:
        return 3
    if counts.count(_PAIR) >= _PAIR:
        return 2
    if counts[0] == _PAIR:
        return 1
    return 0


_MADE_HAND_SCORES: dict[str, int] = {}
_MADE_HAND_NAMES = {
    0: "no made hand",
    1: "a pair",
    2: "two pair",
    3: "trips",
    4: "a straight",
    5: "a flush",
    6: "a full house",
    7: "quads",
    8: "a straight flush",
}
_MADE_HAND_SCORES.update({name: score for score, name in _MADE_HAND_NAMES.items()})


def _flush_draw(hole: list[str], flop: list[str]) -> str | None:
    """The flush draw, and whether it is the nut one.

    Two hole cards of a suit are needed, and two on the board: Omaha allows no
    other flush. Whether it is the nuts is the difference between a draw worth
    a stack and one that mostly wins small and loses big, so it is named.
    """
    for suit in {card[-1].lower() for card in flop if len(card) >= _PAIR}:
        if [card for card in flop if card[-1].lower() == suit].__len__() < _PAIR:
            continue
        suited = [card for card in hole if len(card) >= _PAIR and card[-1].lower() == suit]
        if len(suited) < _PAIR:
            continue
        seen = {card[0].upper() for card in flop if card[-1].lower() == suit}
        top = next(rank for rank in reversed(_RANK_ORDER) if rank not in seen)
        held = {card[0].upper() for card in suited}
        return "nut flush draw" if top in held else "non-nut flush draw"
    return None


def _straight_outs(hole: list[str], flop: list[str]) -> int:
    """How many cards complete a straight, counted by trying them all.

    Cheaper to enumerate the thirteen ranks than to reason about wraps and
    gutshots separately, and it gets the wraps right, which is where Omaha
    straight draws differ from Hold'em ones.

    Counted in cards, not ranks. An open-ender completed by two ranks is eight
    outs and everyone calls it eight; calling it two would read as a gutshot
    and get the holding backwards. Cards already visible in the hand or on the
    flop are not outs, so they are taken off.
    """
    board = [card[0].upper() for card in flop if len(card) >= _PAIR]
    held = [card[0].upper() for card in hole if len(card) >= _PAIR]
    seen = board + held
    outs = 0
    for candidate in _RANK_ORDER:
        if _makes_straight(held, [*board, candidate]):
            outs += _CARDS_PER_RANK - seen.count(candidate)
    return outs


def _makes_straight(held: list[str], board_ranks: list[str]) -> bool:
    """True when two held cards and three board cards make a straight."""
    for i, first in enumerate(held):
        for second in held[i + 1 :]:
            for a in range(len(board_ranks)):
                for b in range(a + 1, len(board_ranks)):
                    for c in range(b + 1, len(board_ranks)):
                        five = [first, second, board_ranks[a], board_ranks[b], board_ranks[c]]
                        if _is_run(five):
                            return True
    return False


def _is_run(ranks: list[str]) -> bool:
    values = sorted({_RANK_ORDER.index(rank) for rank in ranks if rank in _RANK_ORDER})
    if len(values) != len(ranks):
        return False
    if values == [0, 1, 2, 3, 12]:  # the wheel, where the ace plays low
        return True
    return values[-1] - values[0] == len(values) - 1


def classify_all_in(hand: Any, player: str) -> dict[str, Any] | None:
    """What this player moved all in with, or None when it cannot be seen.

    Returns None rather than a guess whenever the four cards were not
    revealed: an unshown shove is the great majority of them, and a note built
    on two visible cards would read exactly like one built on four.
    """
    if not _went_all_in(hand, player):
        return None
    hole = _cards(hand, player)
    flop = _flop(hand)
    if len(hole) < _OMAHA_HOLE_CARDS or len(flop) < _FLOP_CARDS:
        return None
    hole = hole[:_OMAHA_HOLE_CARDS]
    made = _made_hand(hole, flop)
    # A draw is something the hand is still missing. Reported next to the hand
    # it already holds it is at best noise and at worst nonsense: counting the
    # cards that "complete" a straight already made counts nearly the whole
    # deck, and a made straight was coming out with forty-five outs.
    drawing = _MADE_HAND_SCORES[made] < _MADE_HAND_SCORES["a straight"]
    return {
        "hole": " ".join(hole),
        "flop": " ".join(flop),
        "made": made,
        "flush_draw": _flush_draw(hole, flop) if _MADE_HAND_SCORES[made] < _MADE_HAND_SCORES["a flush"] else None,
        "straight_outs": _straight_outs(hole, flop) if drawing else 0,
    }


def describe_all_in(detail: dict[str, Any]) -> str:
    """One line naming what was held, for the note itself."""
    parts = [detail["made"]]
    if detail["flush_draw"]:
        parts.append(detail["flush_draw"])
    if detail["straight_outs"]:
        parts.append(f"{detail['straight_outs']} straight outs")
    return ", ".join(parts)
