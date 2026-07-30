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

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

RULE_SET_AOF_OMAHA = "aof_omaha_allin"

AOF_OMAHA_CATEGORY = "aof_omaha"
AOF_HOLDEM_CATEGORY = "aof_holdem"
AOF_CATEGORIES = frozenset({AOF_OMAHA_CATEGORY, AOF_HOLDEM_CATEGORY})
AOF_CLASSIFIER_VERSION = 1
KNOWN_BACKEND = "pypoker-eval"
KNOWN_BACKEND_VERSION: str = "engine-1"
_OMAHA_HOLE_CARDS = 4
_HOLDEM_HOLE_CARDS = 2
_FLOP_CARDS = 3
_PAIR = 2
_TRIPS = 3
_RANK_ORDER = "23456789TJQKA"
_FIVE_CARDS = 5
_QUADS = 4
_CARDS_PER_RANK = 4


@dataclass(frozen=True)
class AofDecision:
    """One observable All-in or Fold decision, ready for persistence."""

    hand_id: int
    player_id: int
    category: str
    decision: str
    role: str
    active_opponents: int
    pot_before: int
    amount_to_commit: int
    blind_committed: int
    cards_observable: bool
    hole_cards: str | None
    flop_cards: str | None
    made_hand: str | None
    flush_draw: str | None
    straight_outs: int | None
    classifier_version: int = AOF_CLASSIFIER_VERSION

    @property
    def idempotency_key(self) -> tuple[int, int, int]:
        return (self.hand_id, self.player_id, self.classifier_version)


@dataclass(frozen=True)
class AofDecisionAnalysis:
    """A recalculable equity/EV result kept separate from the decision."""

    decision_id: int
    backend: str
    backend_version: str
    range_model: str
    range_version: int
    analysis_version: int
    equity_ppm: int | None
    ev_chips: int | None
    ev_bb_ppm: int | None
    break_even_ppm: int | None
    samples: int | None
    stderr_ppm: int | None
    status: str
    error_text: str | None = None

    @property
    def idempotency_key(self) -> tuple[int, str, str, str, int, int]:
        return (
            self.decision_id,
            self.backend,
            self.backend_version,
            self.range_model,
            self.range_version,
            self.analysis_version,
        )


def is_aof_omaha(hand: Any) -> bool:
    """True for a hand of All-in or Fold Omaha."""
    gametype = getattr(hand, "gametype", {}) or {}
    return str(gametype.get("category", "")).lower() == AOF_OMAHA_CATEGORY


def is_aof(hand: Any) -> bool:
    """True for an imported All-in or Fold category."""
    gametype = getattr(hand, "gametype", {}) or {}
    return str(gametype.get("category", "")).lower() in AOF_CATEGORIES


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
    cached = getattr(hand, "aof_decisions", None)
    if cached is not None:
        player_id = (getattr(hand, "playerIds", {}) or {}).get(player)
        for decision in cached:
            if decision.player_id == player_id and decision.decision == "allin" and decision.cards_observable:
                return {
                    "hole": decision.hole_cards,
                    "flop": decision.flop_cards,
                    "made": decision.made_hand,
                    "flush_draw": decision.flush_draw,
                    "straight_outs": decision.straight_outs,
                }
        return None
    return _classify_all_in_uncached(hand, player)


def _classify_all_in_uncached(hand: Any, player: str) -> dict[str, Any] | None:
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


def extract_decisions(hand: Any) -> list[AofDecision]:
    """Extract the single decision reached by each acting AoF player.

    Blind and ante money is tracked separately because it is already lost at
    the decision point. Hidden all-ins are retained as decisions but never
    classified; folds have no cards to observe by definition.
    """
    if not is_aof(hand):
        return []
    hand_id = getattr(hand, "dbid_hands", None)
    player_ids = getattr(hand, "playerIds", {}) or {}
    if hand_id is None or not player_ids:
        return []

    category = str((getattr(hand, "gametype", {}) or {}).get("category", "")).lower()
    decision_street = _decision_street(hand)
    actions = getattr(hand, "actions", {}) or {}
    committed, forced = _forced_commitments(hand, decision_street, player_ids)
    stacks = _starting_stacks(hand)

    active = set(player_ids)
    acted: set[str] = set()
    all_ins = 0
    decisions = []
    for raw in actions.get(decision_street, ()):
        player = _action_player(raw)
        if player is None or player not in active or player not in player_ids or player in acted:
            continue
        action = _action_name(raw)
        is_fold = action == "folds"
        is_all_in = _action_is_all_in(raw)
        if not is_fold and not is_all_in:
            continue
        amount_to_commit = (
            0
            if is_fold
            else _remaining_stack(
                raw,
                committed.get(player, 0),
                stacks.get(player),
            )
        )
        decision = _build_decision(
            hand,
            hand_id=int(hand_id),
            player=player,
            player_id=int(player_ids[player]),
            category=category,
            role=_decision_role(all_ins),
            active_opponents=max(0, len(active) - 1),
            pot_before=sum(committed.values()),
            blind_committed=forced.get(player, 0),
            amount_to_commit=amount_to_commit,
            is_fold=is_fold,
            is_all_in=is_all_in,
        )
        decisions.append(decision)
        acted.add(player)
        if is_fold:
            active.remove(player)
        else:
            committed[player] += decision.amount_to_commit
            all_ins += 1
    hand.aof_decisions = decisions
    return decisions


def _forced_commitments(
    hand: Any,
    decision_street: str,
    player_ids: dict[str, int],
) -> tuple[dict[str, int], dict[str, int]]:
    actions = getattr(hand, "actions", {}) or {}
    committed = {name: 0 for name in player_ids}
    forced = {name: 0 for name in player_ids}
    for street in getattr(hand, "actionStreets", ()) or ():
        if street == decision_street:
            break
        for raw in actions.get(street, ()):
            player = _action_player(raw)
            amount = _action_amount(raw)
            if player in committed and amount:
                committed[player] += amount
                forced[player] += amount
    return committed, forced


def _build_decision(
    hand: Any,
    *,
    hand_id: int,
    player: str,
    player_id: int,
    category: str,
    role: str,
    active_opponents: int,
    pot_before: int,
    blind_committed: int,
    amount_to_commit: int,
    is_fold: bool,
    is_all_in: bool,
) -> AofDecision:
    detail = _classify_all_in_uncached(hand, player) if is_all_in and category == AOF_OMAHA_CATEGORY else None
    hole = _cards(hand, player)
    flop = _flop(hand)
    required_hole_cards = _OMAHA_HOLE_CARDS if category == AOF_OMAHA_CATEGORY else _HOLDEM_HOLE_CARDS
    observable = bool(is_all_in and len(hole) >= required_hole_cards and len(flop) >= _FLOP_CARDS)
    return AofDecision(
        hand_id=hand_id,
        player_id=player_id,
        category=category,
        decision="fold" if is_fold else "allin",
        role=role,
        active_opponents=active_opponents,
        pot_before=pot_before,
        amount_to_commit=amount_to_commit,
        blind_committed=blind_committed,
        cards_observable=observable,
        hole_cards=" ".join(hole[:required_hole_cards]) if observable else None,
        flop_cards=" ".join(flop[:_FLOP_CARDS]) if observable else None,
        made_hand=detail["made"] if detail else None,
        flush_draw=detail["flush_draw"] if detail else None,
        straight_outs=detail["straight_outs"] if detail else None,
    )


def _decision_role(prior_all_ins: int) -> str:
    if prior_all_ins == 0:
        return "open_shove"
    if prior_all_ins == 1:
        return "call_shove"
    return "overcall"


def _action_player(raw: Any) -> str | None:
    return str(raw[0]) if isinstance(raw, (tuple, list)) and raw else None


def _action_name(raw: Any) -> str:
    if not isinstance(raw, (tuple, list)) or len(raw) < _PAIR:
        return ""
    return str(raw[1]).lower()


def _action_is_all_in(raw: Any) -> bool:
    if not isinstance(raw, (tuple, list)) or len(raw) < _PAIR:
        return False
    return _action_name(raw) in {"allin", "all-in"} or (isinstance(raw[-1], bool) and raw[-1])


def _action_amount(raw: Any) -> int:
    if not isinstance(raw, (tuple, list)) or len(raw) < 3 or isinstance(raw[2], bool):
        return 0
    try:
        return int(Decimal(str(raw[2])) * Decimal("100"))
    except (InvalidOperation, TypeError, ValueError):
        return 0


def _starting_stacks(hand: Any) -> dict[str, int]:
    """Return the chips each player had before blinds, in integer cents."""
    stacks = {}
    for player in getattr(hand, "players", ()) or ():
        if not isinstance(player, (tuple, list)) or len(player) < 3:
            continue
        try:
            stacks[str(player[1])] = int(Decimal(str(player[2])) * Decimal("100"))
        except (InvalidOperation, TypeError, ValueError):
            continue
    return stacks


def _remaining_stack(raw: Any, committed: int, starting_stack: int | None) -> int:
    """Return the actual incremental all-in cost at the decision point.

    ``Hand.actions`` stores a call as an increment but a raise tuple starts
    with the raise-by amount.  The latter is not what the player still had to
    put in.  AoF actions are all-in, so the initial stack minus forced money
    is the authoritative increment; the raw action remains a compatibility
    fallback for incomplete captures.
    """
    if starting_stack is not None and starting_stack >= committed:
        return starting_stack - committed
    return _action_amount(raw)


def describe_all_in(detail: dict[str, Any]) -> str:
    """One line naming what was held, for the note itself."""
    parts = [detail["made"]]
    if detail["flush_draw"]:
        parts.append(detail["flush_draw"])
    if detail["straight_outs"]:
        parts.append(f"{detail['straight_outs']} straight outs")
    return ", ".join(parts)
