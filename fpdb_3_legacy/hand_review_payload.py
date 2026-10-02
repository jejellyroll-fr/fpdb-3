"""Preflop hand-review payload for PreflopAdvisor (#328).

fpdb-3 owns the hands that were played; PreflopAdvisor owns the solver
strategies and the trainer. This module is the boundary between the two: it
turns a canonical :class:`Hand` into the factual description of its preflop
action that PreflopAdvisor's hand review reads, and nothing more. It never
names a solver node, never computes an EV and never guesses: a hand that
cannot be described reliably raises :class:`HandReviewError` with a reason,
instead of producing a plausible document about a table nobody played at.

The document is versioned and is the same for one hand or many, so the
replayer's "review this hand", a Hand Viewer export and a future batch review
all write one format. How the document reaches PreflopAdvisor is a
:class:`HandReviewTransport`, so a file export today can become a local API
or a deep link without touching the normalization below.

The format is documented in ``docs/preflop-hand-review.md``.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final, Protocol

#: The payload version, which is also the one PreflopAdvisor's hand review
#: reads (``PAYLOAD_VERSION`` in ``preflop_advisor/hand_review.py``). A
#: change a reader of version 1 would misread needs a new number.
PAYLOAD_VERSION: Final = 1
SCHEMA: Final = "fpdb-3/preflop-hand-review"
SOURCE: Final = "fpdb-3"
#: How seats are named: PreflopAdvisor's default seat names, so the hero and
#: the line of play arrive spelled the way its trees spell them.
POSITION_SCHEME: Final = "preflop-advisor-default"

#: (category, limit type) -> PreflopAdvisor's game name. Only the games it
#: has trees for: anything else is refused rather than reviewed against the
#: wrong game.
_GAMES: Final = {
    ("holdem", "nl"): "NL",
    ("omahahi", "pl"): "PLO",
    ("omahahilo", "pl"): "PLO8",
    ("5_omahahi", "pl"): "PLO5",
}
_HOLE_CARDS: Final = {"NL": 2, "PLO": 4, "PLO8": 4, "PLO5": 5}

#: Seat names in preflop acting order (blinds last), by players dealt in.
#: These are PreflopAdvisor's defaults (``TreeReader.Positions*``): up to six
#: the six-handed list is cut from the button outwards, seven to nine have
#: their own lists.
SEAT_NAMES: Final = {
    2: ("SB", "BB"),
    3: ("BU", "SB", "BB"),
    4: ("CO", "BU", "SB", "BB"),
    5: ("MP", "CO", "BU", "SB", "BB"),
    6: ("UTG", "MP", "CO", "BU", "SB", "BB"),
    7: ("UTG", "MP", "HJ", "CO", "BU", "SB", "BB"),
    8: ("UTG", "MP", "LJ", "HJ", "CO", "BU", "SB", "BB"),
    9: ("UTG", "UTG1", "MP", "LJ", "HJ", "CO", "BU", "SB", "BB"),
}

#: Forced bets the review can describe. A straddle, a dead small blind
#: posted with the big one, or a button blind changes who is in for what
#: before anyone acts, which PreflopAdvisor's model (two blinds on the last
#: two seats) cannot represent.
_POSTS: Final = ("small blind", "big blind", "ante")
_ACTIONS: Final = ("folds", "checks", "calls", "bets", "raises")

# Reasons a hand cannot be described.
NO_HERO: Final = "no_hero"
HERO_NOT_DEALT: Final = "hero_not_dealt"
HERO_CARDS: Final = "hero_cards"
UNSUPPORTED_GAME: Final = "unsupported_game"
UNSUPPORTED_TABLE: Final = "unsupported_table_size"
UNSUPPORTED_POSTS: Final = "unsupported_posts"
MISSING_STACKS: Final = "missing_stacks"
INVALID_AMOUNT: Final = "invalid_amount"
AMBIGUOUS_POSITION: Final = "ambiguous_position"
MISSING_PREFLOP: Final = "missing_preflop"
UNSUPPORTED_ACTION: Final = "unsupported_action"
NO_HERO_DECISION: Final = "no_hero_decision"


class HandReviewError(ValueError):
    """A hand that cannot be described for a solver review, and why."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ReviewSeat:
    """One player dealt into the hand."""

    position: str
    seat_no: int
    stack: Decimal
    is_hero: bool


@dataclass(frozen=True)
class ReviewAction:
    """One preflop action, as the history recorded it.

    ``amount`` is what the action put in, ``to`` the seat's total for the
    street after it (the raise-to of a raise), both in the hand's own chips
    or money, unrounded. Antes are not part of either: a raise to three is
    three whatever the ante was. ``effective_stack`` is what the actor had
    behind at that moment, capped by the deepest opponent still in the hand.
    """

    index: int
    position: str
    seat_no: int
    kind: str
    amount: Decimal
    to: Decimal | None
    all_in: bool
    pot_before: Decimal
    to_call: Decimal
    effective_stack: Decimal
    is_hero: bool

    @property
    def action(self) -> str:
        """The action as PreflopAdvisor spells it."""
        if self.kind in ("bets", "raises"):
            return "AllIn" if self.all_in else "Raise"
        return {"folds": "Fold", "checks": "Check", "calls": "Call"}[self.kind]

    @property
    def is_raise(self) -> bool:
        return self.kind in ("bets", "raises")


@dataclass(frozen=True)
class HandReview:
    """What PreflopAdvisor needs to review the hero's preflop decisions."""

    fpdb_hand_id: int | None
    site_hand_no: str
    site: str
    played_at: str
    game: str
    category: str
    limit_type: str
    game_type: str
    currency: str
    table_name: str
    max_seats: int | None
    small_blind: Decimal
    big_blind: Decimal
    ante: Decimal
    hero_name: str
    hero_position: str
    hero_seat_no: int
    hero_cards: tuple[str, ...]
    seats: tuple[ReviewSeat, ...]
    actions: tuple[ReviewAction, ...]
    selected_decision: int | None = None
    tournament: dict[str, Any] = field(default_factory=dict)

    @property
    def table_size(self) -> int:
        return len(self.seats)

    @property
    def hero_decisions(self) -> tuple[int, ...]:
        """Indices (into :attr:`actions`) of the hero's preflop turns."""
        return tuple(action.index for action in self.actions if action.is_hero)

    @property
    def effective_stack(self) -> Decimal:
        """The hero's starting stack capped by the deepest opponent's."""
        hero = next(seat.stack for seat in self.seats if seat.is_hero)
        deepest = max((seat.stack for seat in self.seats if not seat.is_hero), default=hero)
        return min(hero, deepest)

    def bb(self, amount: Decimal) -> float:
        """*amount* in big blinds, unrounded."""
        return float(amount / self.big_blind)

    def with_selected_decision(self, index: int | None) -> HandReview:
        """The same review, pointing at one of the hero's decisions (or none)."""
        if index is not None and index not in self.hero_decisions:
            msg = f"action {index} is not one of the hero's preflop decisions"
            raise ValueError(msg)
        return replace(self, selected_decision=index)

    def to_payload(self) -> dict[str, Any]:
        """The hand as one entry of the document's ``hands`` list."""
        hand_id = str(self.fpdb_hand_id) if self.fpdb_hand_id is not None else f"{self.site}#{self.site_hand_no}"
        return {
            # Read by PreflopAdvisor.
            "hand_id": hand_id,
            "played_at": self.played_at,
            "hero": self.hero_position,
            "hero_cards": "".join(self.hero_cards),
            "game": self.game,
            "table_size": self.table_size,
            "effective_stack_bb": self.bb(self.effective_stack),
            "ante_bb": self.bb(self.ante),
            "site": self.site,
            "stake_label": f"{_plain(self.small_blind)}/{_plain(self.big_blind)} {self.currency}".strip(),
            "seats": [seat.position for seat in self.seats],
            "actions": [self._action_payload(action) for action in self.actions],
            # Factual context, for auditing the above and for later readers.
            "fpdb_hand_id": self.fpdb_hand_id,
            "site_hand_no": self.site_hand_no,
            "table": self.table_name,
            "max_seats": self.max_seats,
            "category": self.category,
            "limit_type": self.limit_type,
            "game_type": self.game_type,
            "currency": self.currency,
            "tournament": self.tournament or None,
            "blinds": {
                "sb": _number(self.small_blind),
                "bb": _number(self.big_blind),
                "sb_bb": self.bb(self.small_blind),
            },
            "ante": _number(self.ante),
            "hero_name": self.hero_name,
            "hero_seat_no": self.hero_seat_no,
            "position_scheme": POSITION_SCHEME,
            "players": [
                {
                    "position": seat.position,
                    "seat_no": seat.seat_no,
                    "stack": _number(seat.stack),
                    "stack_bb": self.bb(seat.stack),
                    "is_hero": seat.is_hero,
                }
                for seat in self.seats
            ],
            "hero_decisions": list(self.hero_decisions),
            "selected_decision": self.selected_decision,
        }

    def _action_payload(self, action: ReviewAction) -> dict[str, Any]:
        entry: dict[str, Any] = {"seat": action.position, "action": action.action}
        # Given for calls too: PreflopAdvisor reads ``amount_bb`` as ``to_bb``
        # when ``to_bb`` is missing, and a call's amount is not a raise-to.
        if action.to is not None:
            entry["to_bb"] = self.bb(action.to)
        entry.update(
            {
                "index": action.index,
                "street": "PREFLOP",
                "seat_no": action.seat_no,
                "is_hero": action.is_hero,
                "fpdb_action": action.kind,
                "amount": _number(action.amount),
                "amount_bb": self.bb(action.amount),
                "to": None if action.to is None else _number(action.to),
                "all_in": action.all_in,
                "pot_before": _number(action.pot_before),
                "pot_before_bb": self.bb(action.pot_before),
                "to_call": _number(action.to_call),
                "to_call_bb": self.bb(action.to_call),
                "effective_stack": _number(action.effective_stack),
                "effective_stack_bb": self.bb(action.effective_stack),
            }
        )
        return entry


def _decimal(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        amount = None
    # "NaN" and "Infinity" read as Decimals but are no amount either. Either
    # way it is a refusal like any other, so the dialog shows it and a batch
    # skips the hand instead of stopping on it.
    if amount is None or not amount.is_finite():
        raise HandReviewError(INVALID_AMOUNT, f"{value!r} is not an amount")
    return amount


def _number(value: Decimal) -> float | int:
    """An exact chip amount as a JSON number (its shortest repr is the source text)."""
    return int(value) if value == value.to_integral_value() else float(value)


def _plain(value: Decimal) -> str:
    return format(value, "f")


def build_hand_review(
    hand: Any,
    *,
    hero: str | None = None,
    fpdb_hand_id: int | None = None,
    selected_decision: int | None = None,
) -> HandReview:
    """Describe *hand*'s preflop for a solver review.

    *hero* names the hero when the hand does not (a legacy import without a
    hero seat, resolved by the replayer); *fpdb_hand_id* is the database id
    the caller loaded the hand from, which the hand itself does not keep.

    :raises HandReviewError: when the hand cannot be described reliably.
    """
    gametype = getattr(hand, "gametype", {}) or {}
    category = str(gametype.get("category") or "")
    limit_type = str(gametype.get("limitType") or "")
    game = _game_of(category, limit_type)

    hero_name = hero or getattr(hand, "hero", "") or ""
    if not hero_name:
        raise HandReviewError(NO_HERO, "The hand does not say who the hero is")

    big_blind = _decimal(getattr(hand, "bb", None))
    small_blind = _decimal(getattr(hand, "sb", None))
    if big_blind <= 0 or small_blind <= 0:
        raise HandReviewError(MISSING_STACKS, "The hand has no blinds to count big blinds in")

    sitout = set(getattr(hand, "sitout", set()) or set())
    dealt = [player for player in hand.players if player[1] not in sitout]
    stacks = _starting_stacks(dealt)
    if hero_name not in stacks:
        raise HandReviewError(HERO_NOT_DEALT, f"The hero {hero_name} was not dealt into this hand")

    posts = list(hand.actions.get("BLINDSANTES", []) or [])
    small_blind_player, big_blind_player = _blind_posters(posts)
    _check_post_amounts(posts, small_blind, big_blind)
    order = _acting_order(hand, dealt, small_blind_player, big_blind_player)
    names = SEAT_NAMES.get(len(order))
    if names is None:
        raise HandReviewError(
            UNSUPPORTED_TABLE, f"{len(order)} players were dealt in; PreflopAdvisor names seats for 2 to 9"
        )
    position = {player[1]: label for player, label in zip(order, names, strict=True)}
    seat_no = {player[1]: int(player[0]) for player in order}

    # An EV cash-out (read back from the database on the street of the all-in)
    # is not a decision; it only ever follows the last one.
    preflop = [action for action in hand.actions.get("PREFLOP", []) or [] if action[1] != "cashout"]
    if not preflop:
        raise HandReviewError(MISSING_PREFLOP, "The hand records no preflop action")
    actions = _review_actions(preflop, posts, position, seat_no, hero_name, stacks)
    if not any(action.is_hero for action in actions):
        raise HandReviewError(NO_HERO_DECISION, f"The hero {hero_name} had no preflop decision in this hand")
    _check_everyone_acted(order, actions, posts, position, big_blind_player)

    hero_cards = _hero_cards(hand, hero_name, game)
    review = HandReview(
        fpdb_hand_id=fpdb_hand_id if fpdb_hand_id is not None else _stored_id(hand),
        site_hand_no=str(getattr(hand, "handid", "") or ""),
        site=str(getattr(hand, "sitename", "") or ""),
        played_at=_played_at(getattr(hand, "startTime", None)),
        game=game,
        category=category,
        limit_type=limit_type,
        game_type=str(gametype.get("type") or ""),
        currency=str(gametype.get("currency") or ""),
        table_name=str(getattr(hand, "tablename", "") or ""),
        # A hand read back from the database carries a placeholder table size.
        max_seats=_optional_int(getattr(hand, "maxseats", None)) if getattr(hand, "handText", None) else None,
        small_blind=small_blind,
        big_blind=big_blind,
        ante=_ante_per_seat(posts, len(order)),
        hero_name=hero_name,
        hero_position=position[hero_name],
        hero_seat_no=seat_no[hero_name],
        hero_cards=hero_cards,
        seats=tuple(
            ReviewSeat(position[player[1]], seat_no[player[1]], stacks[player[1]], player[1] == hero_name)
            for player in order
        ),
        actions=actions,
        tournament=_tournament(hand, gametype),
    )
    return review.with_selected_decision(selected_decision) if selected_decision is not None else review


def _game_of(category: str, limit_type: str) -> str:
    game = _GAMES.get((category, limit_type))
    if game is None:
        raise HandReviewError(
            UNSUPPORTED_GAME,
            f"{category or 'this game'} ({limit_type or 'unknown limit'}) is not a game PreflopAdvisor reviews: "
            "it reviews no-limit hold'em and pot-limit Omaha (PLO, PLO8, PLO5)",
        )
    return game


def _starting_stacks(dealt: list[Any]) -> dict[str, Decimal]:
    stacks: dict[str, Decimal] = {}
    for player in dealt:
        try:
            stacks[player[1]] = _decimal(player[2])
        except ValueError:
            raise HandReviewError(MISSING_STACKS, f"{player[1]}'s starting stack is not recorded") from None
        if stacks[player[1]] <= 0:
            raise HandReviewError(MISSING_STACKS, f"{player[1]}'s starting stack is not recorded")
    return stacks


def _blind_posters(posts: Sequence[tuple]) -> tuple[str, str]:
    """Who posted the small and the big blind; refuses any other kind of post."""
    for post in posts:
        if post[1] not in _POSTS:
            raise HandReviewError(
                UNSUPPORTED_POSTS,
                f"{post[0]} posts a {post[1]}: PreflopAdvisor's model has only the two blinds and antes",
            )
    small_blinds = [post[0] for post in posts if post[1] == "small blind"]
    big_blinds = [post[0] for post in posts if post[1] == "big blind"]
    if len(big_blinds) != 1 or len(small_blinds) != 1:
        raise HandReviewError(
            AMBIGUOUS_POSITION,
            f"The hand has {len(small_blinds)} small blind(s) and {len(big_blinds)} big blind(s) posted; "
            "positions are only defined with exactly one of each",
        )
    return small_blinds[0], big_blinds[0]


def _check_post_amounts(posts: Sequence[tuple], small_blind: Decimal, big_blind: Decimal) -> None:
    """The blinds are the declared ones and the antes one amount for everyone.

    The document says the stakes and the ante once, as numbers every seat
    shares. A blind posted short (all in for less) or antes of different sizes
    would make those numbers describe a table nobody played at, so the hand is
    refused rather than averaged.
    """
    declared = {"small blind": small_blind, "big blind": big_blind}
    antes = set()
    for post in posts:
        amount = _decimal(post[2])
        if post[1] in declared and amount != declared[post[1]]:
            raise HandReviewError(
                UNSUPPORTED_POSTS,
                f"{post[0]} posts a {post[1]} of {_plain(amount)}, not the declared {_plain(declared[post[1]])}",
            )
        if post[1] == "ante":
            antes.add(amount)
    if len(antes) > 1:
        amounts = ", ".join(_plain(amount) for amount in sorted(antes))
        raise HandReviewError(UNSUPPORTED_POSTS, f"The antes differ ({amounts}); one ante per seat cannot say that")


def _acting_order(hand: Any, dealt: list[Any], small_blind: str, big_blind: str) -> list[Any]:
    """The players dealt in, in preflop acting order: big blind last.

    The blinds decide the order; the button is only checked against it, since
    a dead button sits on an empty seat.
    """
    seats = sorted(dealt, key=lambda player: int(player[0]))
    names = [player[1] for player in seats]
    if big_blind not in names or small_blind not in names:
        raise HandReviewError(AMBIGUOUS_POSITION, "A blind was posted by a player who was not dealt in")
    after_big_blind = names.index(big_blind) + 1
    order = seats[after_big_blind:] + seats[:after_big_blind]
    if len(order) < 2 or order[-2][1] != small_blind:
        raise HandReviewError(
            AMBIGUOUS_POSITION,
            f"{small_blind} posts the small blind but is not the seat before the big blind {big_blind}",
        )
    button = getattr(hand, "buttonpos", None)
    # Heads-up the seats are named SB and BB after the blinds alone, so the
    # button is not checked there: parsers record it inconsistently heads-up
    # (Merge renumbers seats but not the dealer; the database puts it on the
    # big blind's seat), and it changes no name the document gives.
    if len(order) > 2 and button:
        seat_numbers = [int(player[0]) for player in order]
        if int(button) in seat_numbers and int(order[-3][0]) != int(button):
            raise HandReviewError(
                AMBIGUOUS_POSITION,
                f"The button (seat {button}) is not the seat before the small blind {small_blind}",
            )
    return order


def _review_actions(
    preflop: Sequence[tuple],
    posts: Sequence[tuple],
    position: dict[str, str],
    seat_no: dict[str, int],
    hero: str,
    stacks: dict[str, Decimal],
) -> tuple[ReviewAction, ...]:
    """Walk the preflop, tracking who is in for what, what is behind and what the pot is."""
    contributed: dict[str, Decimal] = dict.fromkeys(position, Decimal(0))
    behind: dict[str, Decimal] = {player: stacks[player] for player in position}
    folded: set[str] = set()
    pot = Decimal(0)
    for post in posts:
        if post[0] not in position:
            # A tournament player sitting out still antes; counting them as
            # dealt in or not would shift every position, so neither is done.
            raise HandReviewError(AMBIGUOUS_POSITION, f"{post[0]} posts a {post[1]} but was not dealt in")
        amount = _decimal(post[2])
        pot += amount
        behind[post[0]] -= amount
        if post[1] != "ante":
            contributed[post[0]] += amount
    level = max(contributed.values(), default=Decimal(0))

    actions: list[ReviewAction] = []
    for index, raw in enumerate(preflop):
        player, kind = raw[0], raw[1]
        if player not in position:
            raise HandReviewError(AMBIGUOUS_POSITION, f"{player} acts preflop but was not dealt in")
        if kind not in _ACTIONS:
            raise HandReviewError(UNSUPPORTED_ACTION, f"{player} {kind} preflop, which a review cannot describe")
        before = contributed[player]
        to_call = max(Decimal(0), level - before)
        amount, to, all_in = _put_in(raw, before)
        if amount < 0 or amount > behind[player]:
            raise HandReviewError(
                MISSING_STACKS, f"{player}'s preflop action puts in {amount}, which their stack does not cover"
            )
        opponents = [behind[other] for other in position if other != player and other not in folded]
        effective = min(behind[player], max(opponents, default=behind[player]))
        actions.append(
            ReviewAction(
                index=index,
                position=position[player],
                seat_no=seat_no[player],
                kind=kind,
                amount=amount,
                to=to,
                all_in=all_in,
                pot_before=pot,
                to_call=to_call,
                effective_stack=effective,
                is_hero=player == hero,
            )
        )
        if to is not None:
            contributed[player] = to
            level = max(level, to)
        if kind == "folds":
            folded.add(player)
        behind[player] -= amount
        pot += amount
    return tuple(actions)


def _put_in(raw: tuple, before: Decimal) -> tuple[Decimal, Decimal | None, bool]:
    """What an action adds, the seat's street total after it, and whether it is all in."""
    kind = raw[1]
    if kind == "raises":
        to = _decimal(raw[3])
        return to - before, to, len(raw) > 5 and raw[5] is True
    if kind in ("bets", "calls"):
        amount = _decimal(raw[2])
        return amount, before + amount, len(raw) > 3 and raw[3] is True
    return Decimal(0), None, False


def _check_everyone_acted(
    order: list[Any], actions: Sequence[ReviewAction], posts: Sequence[tuple], position: dict[str, str], big_blind: str
) -> None:
    """Every seat but the big blind acts preflop, unless a post put it all in.

    A listed player who never acts was most likely not dealt in (sitting out,
    waiting for the big blind), and counting them would shift every position.
    """
    acted = {action.position for action in actions}
    all_in_from_post = {position[post[0]] for post in posts if len(post) > 3 and post[3] is True}
    for player in order:
        label = position[player[1]]
        if player[1] == big_blind or label in acted or label in all_in_from_post:
            continue
        raise HandReviewError(
            AMBIGUOUS_POSITION,
            f"Seat {player[0]} never acts preflop, so it cannot be told whether it was dealt in",
        )


def _hero_cards(hand: Any, hero: str, game: str) -> tuple[str, ...]:
    try:
        cards = [str(card) for card in hand.join_holecards(hero, asList=True)]
    except (AttributeError, KeyError, TypeError, ValueError):
        cards = []
    known = [card for card in cards if card and card[0].upper() != "X" and card != "0x"]
    if len(known) != _HOLE_CARDS[game] or len(known) != len(cards):
        raise HandReviewError(
            HERO_CARDS, f"The hero's hole cards are not all known ({' '.join(cards) or 'none recorded'})"
        )
    return tuple(known)


def _ante_per_seat(posts: Sequence[tuple], players: int) -> Decimal:
    """Antes as one ante per seat: a big-blind ante paid for the table counts once per player."""
    total = sum((_decimal(post[2]) for post in posts if post[1] == "ante"), Decimal(0))
    return total / players if players else Decimal(0)


def _stored_id(hand: Any) -> int | None:
    """The database id the hand was read from (``hand_factory``) or stored under."""
    for attribute in ("handid_selected", "dbid_hands"):
        value = _optional_int(getattr(hand, attribute, None))
        if value:
            return value
    return None


def _played_at(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _tournament(hand: Any, gametype: dict) -> dict[str, Any]:
    if gametype.get("type") != "tour":
        return {}
    return {
        "tourney_no": str(getattr(hand, "tourNo", "") or ""),
        "level": str(getattr(hand, "level", "") or ""),
        "buyin": getattr(hand, "buyin", None),
        "knockout": bool(getattr(hand, "isKO", False)),
    }


def decision_at(review: HandReview, applied: int) -> int | None:
    """The hero decision a replayer showing *applied* preflop actions points at.

    The hero's action just played when there is one (the replay was paused on
    it), else the next one still to come, else the last one before.
    """
    decisions = review.hero_decisions
    if not decisions:
        return None
    if applied - 1 in decisions:
        return applied - 1
    upcoming = [index for index in decisions if index >= applied]
    return upcoming[0] if upcoming else decisions[-1]


def _bb_text(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".") + " BB"


def summary_lines(review: HandReview) -> list[str]:
    """What the review holds, for a person: the table, then the preflop line.

    The hero's turns are marked as the decisions PreflopAdvisor will review,
    and the selected one (if any) is pointed at. Amounts are in big blinds,
    rounded for reading only; the document keeps them exact.
    """
    hero_seat = next(seat for seat in review.seats if seat.is_hero)
    lines = [
        f"{review.game} - {review.table_size} players - {review.site or 'unknown site'}",
        f"Hero: {review.hero_position} [{' '.join(review.hero_cards)}] - "
        f"{_bb_text(review.bb(hero_seat.stack))} ({_bb_text(review.bb(review.effective_stack))} effective)",
    ]
    if review.ante:
        lines.append(f"Ante: {_bb_text(review.bb(review.ante))} per seat")
    lines.append("")
    for action in review.actions:
        text = f"{action.position}: {action.action}"
        if action.is_raise and action.to is not None:
            text += f" to {_bb_text(review.bb(action.to))}"
        elif action.kind == "calls":
            text += f" {_bb_text(review.bb(action.amount))}"
        if action.is_hero:
            marker = ">" if action.index == review.selected_decision else "*"
            text = f"{marker} {text}  (pot {_bb_text(review.bb(action.pot_before))}, solver review available)"
        else:
            text = f"  {text}"
        lines.append(text)
    return lines


def review_hands(hands: Iterable[Any], *, hero: str | None = None) -> tuple[list[HandReview], list[dict[str, Any]]]:
    """Describe many hands for a batch review; the ones refused say why.

    A refused hand is a ``{"hand", "code", "message"}`` entry rather than a
    failure of the whole batch.
    """
    reviews: list[HandReview] = []
    skipped: list[dict[str, Any]] = []
    for hand in hands:
        try:
            reviews.append(build_hand_review(hand, hero=hero))
        except HandReviewError as exc:
            ident = _stored_id(hand)
            label = (
                str(ident) if ident is not None else f"{getattr(hand, 'sitename', '')}#{getattr(hand, 'handid', '')}"
            )
            skipped.append({"hand": label, "code": exc.code, "message": str(exc)})
    return reviews, skipped


def review_document(
    reviews: Iterable[HandReview],
    *,
    generated_at: str = "",
    skipped: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    """The versioned document PreflopAdvisor reads, for one hand or many."""
    document: dict[str, Any] = {
        "version": PAYLOAD_VERSION,
        "schema": SCHEMA,
        "source": SOURCE,
        "hands": [review.to_payload() for review in reviews],
    }
    if skipped:
        document["skipped"] = list(skipped)
    if generated_at:
        document["generated_at"] = generated_at
    return document


def dumps(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


class HandReviewTransport(Protocol):
    """How a document reaches PreflopAdvisor."""

    def send(self, document: dict[str, Any]) -> str:
        """Deliver *document*; return a short description of where it went."""
        ...


@dataclass(frozen=True)
class JsonFileTransport:
    """Write the document to a JSON file, which PreflopAdvisor's "Load a hand review" opens."""

    path: Path

    def send(self, document: dict[str, Any]) -> str:
        Path(self.path).write_text(dumps(document), encoding="utf-8")
        return str(self.path)


#: The console script PreflopAdvisor installs (``uv tool install``, ``pip install``).
PREFLOP_ADVISOR_SCRIPT: Final = "preflop_advisor"
#: The option that starts PreflopAdvisor on a document (PreflopAdvisor#47).
REVIEW_OPTION: Final = "--review"


def preflop_advisor_command(
    configured: str | None = None,
    *,
    which: Callable[[str], str | None] | None = None,
    platform: str | None = None,
) -> list[str] | None:
    """How to start PreflopAdvisor, up to its ``--review`` argument; ``None`` when unknown.

    The path the user configured comes first, but only while it is still there: a program
    that was moved is looked for again rather than launched into an error. Then the console
    script on the PATH. A macOS application bundle is a folder, which ``open`` starts, a new
    instance each time (``-n``) so the document always reaches a window that reads it. A
    file is a program only if it may be executed (Windows has no such bit to check).
    """
    # Looked up when called, not when defined, so a test can stand in for either.
    which = which or shutil.which
    platform = platform or sys.platform
    if configured:
        path = Path(configured).expanduser()
        if platform == "darwin" and path.suffix == ".app" and path.is_dir():
            return ["/usr/bin/open", "-n", "-a", str(path), "--args"]
        if path.is_file() and (platform == "win32" or os.access(path, os.X_OK)):
            return [str(path)]
    found = which(PREFLOP_ADVISOR_SCRIPT)
    return [found] if found else None


class LaunchError(OSError):
    """PreflopAdvisor did not start; the document itself was written."""


@dataclass(frozen=True)
class PreflopAdvisorTransport:
    """Write the document, then start PreflopAdvisor on it with ``--review``.

    *start* launches a program with its arguments, detached and without a shell, and says
    whether it did; it is injected so this module needs no toolkit (the dialog passes
    ``QProcess.startDetached``). A document that cannot be written raises the plain
    :class:`OSError` of the write; a program that does not start raises :class:`LaunchError`,
    so a caller can ask for another program only when another program could help.
    """

    command: Sequence[str]
    path: Path
    start: Callable[[str, list[str]], bool]

    def send(self, document: dict[str, Any]) -> str:
        JsonFileTransport(self.path).send(document)
        program, *arguments = self.command
        if not self.start(program, [*arguments, REVIEW_OPTION, str(self.path)]):
            msg = f"{program} could not be started"
            raise LaunchError(msg)
        return str(self.path)
