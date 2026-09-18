"""Normalized per-action event model for the analytics layer (issue #293).

``HandsPlayers`` and ``HudCache`` store aggregates -- VPIP, RFI, c-bet, a
squeeze flag, a bet-sizing total -- and those do not compose. "BTN vs BB, in a
single raised pot, as the preflop aggressor, in position, betting 25-40% pot on
an ace-high board, facing a raise" is not a combination of columns that exist;
it is a sentence about decisions. This module turns a parsed hand into one row
per decision, carrying the context that decision was made in, so the layers
above (situations, filters, sizing, EV, research) can compose the sentence
instead.

The rows are *derived*, never parsed: everything here reads the action stream
``HandHistoryConverter`` already produced plus the per-player context
``DerivedStats.assembleHandsPlayers`` already computed, and adds no parser
knowledge of its own. Where the aggregate calculators already know a rule --
the chips a raise pushes in, the basis-point convention for bet sizing, the
effective-stack formula -- this module holds the single copy and the
calculators call it, rather than the two drifting apart.

Units and the meaning of every column: ``docs/action-event-model.md``.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

# Money is stored in cents everywhere in fpdb-3, and so is every amount here.
CENTS = 100

# Basis points: 1% of the pot is 100bp, so 10000 divides a whole pot.
BASIS_POINTS = 10000

# Action words as the parsers spell them (Hand.ACTION). Forced bets are money
# the player had no choice about: they never make a player the aggressor, and
# they are never a bet somebody "faces".
FORCED_ACTIONS = frozenset(
    {
        "ante",
        "small blind",
        "secondsb",
        "big blind",
        "both",
        "bringin",
        "straddle",
        "button blind",
    },
)
AGGRESSIVE_ACTIONS = frozenset({"bets", "raises", "completes"})
RAISE_ACTIONS = frozenset({"raises", "completes"})
NO_MONEY_ACTIONS = frozenset({"folds", "checks", "stands pat", "discards", "cashout"})

PREFLOP_STREET = "PREFLOP"
# The blinds and antes street is not a betting round of its own: it holds the
# forced part of the round that follows it, which is why the blind is the bet
# level the first voluntary action has to call. Hold'em preflop is the case
# everyone knows; draw games deal on "DEAL" and stud opens on "SECOND"/
# "THIRD", and their blinds belong to that first betting round just the same
# (Codex review of #293) -- listing them here keeps the live blind commitments
# and the bet level alive across the street boundary instead of restarting
# the round with toCall = 0.
FIRST_ROUND_STREETS = frozenset({"BLINDSANTES", PREFLOP_STREET, "DEAL", "SECOND", "THIRD"})
# Dead money is in the pot but is not part of the bet level: an ante does not
# make the player any less behind the big blind. Blinds and straddles are live.
DEAD_MONEY_ACTIONS = frozenset({"ante"})

# Position encoding of the events' ``position`` column. It is the
# HandsPlayers position code (0 = button, 1 = cutoff, 2 = hijack ...) with the
# two blind seats written as the only negative values it can take.
SMALL_BLIND_POSITION = -1
BIG_BLIND_POSITION = -2

# Action tuple indices, shared with DerivedStats.
ACTION_TYPE_IDX = 1
ACTION_AMOUNT_IDX = 2
ACTION_RAISETO_IDX = 3
ACTION_CALLED_IDX = 4

# The normalized event columns of HandsActions, in persistence order. They are
# appended after the original columns so that an older database upgraded in
# place, an older row and the insert all stay aligned (see store_hands_actions).
ACTION_EVENT_COLUMNS: tuple[str, ...] = (
    "actionType",
    "toCall",
    "potBefore",
    "potAfter",
    "sizingBp",
    "position",
    "relativePosition",
    "inPosition",
    "effectiveStack",
    "effectiveStackBB",
    "sprBefore",
    "isAggressor",
    "facingActionType",
    "facingAmount",
    "facingSizingBp",
    "raiserCount",
    "callerCount",
    "playersInHand",
)

ACTION_EVENT_DEFAULTS: dict[str, Any] = dict.fromkeys(ACTION_EVENT_COLUMNS, 0)
ACTION_EVENT_DEFAULTS.update(
    {
        "actionType": None,
        "position": None,
        "inPosition": False,
        "isAggressor": False,
        "facingActionType": None,
    },
)


def _decimal(value: Any) -> Decimal:
    """Best-effort Decimal conversion; 0 for anything that is not a number."""
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return Decimal(0)


def chips_to_cents(value: Any) -> int:
    """Chips (Decimal, string or number) to the integer cents stored in the db."""
    return int(CENTS * _decimal(value))


def action_chips(action: Sequence[Any]) -> int:
    """Cents one action pushes into the pot.

    A raise tuple carries the raise-by amount *and* the call it made --
    ``("name", "raises", raise_by, raise_to, amount_called, all_in)`` -- so its
    chips are the sum of the two, while a bet or a call carries its amount
    directly and a fold or a check carries none. This is the one copy of that
    rule: ``DerivedStats.calcRaiseMade`` and ``calcStreetSPR`` used to each
    carry their own closure for it.
    """
    word = action[ACTION_TYPE_IDX] if len(action) > ACTION_TYPE_IDX else None
    if word in NO_MONEY_ACTIONS:
        return 0
    if word in RAISE_ACTIONS and len(action) > ACTION_CALLED_IDX:
        return chips_to_cents(action[ACTION_AMOUNT_IDX]) + chips_to_cents(action[ACTION_CALLED_IDX])
    if len(action) > ACTION_AMOUNT_IDX:
        return chips_to_cents(action[ACTION_AMOUNT_IDX])
    return 0


def effective_stack_cents(remaining: dict[str, int], player: str, contenders: Sequence[str]) -> int:
    """Effective stack: the smaller of the player's stack and the deepest opponent's.

    ``remaining`` is what each player still has behind, in cents, at the moment
    being measured. The same formula ``calcStreetSPR`` and ``calcEffectiveStack``
    use, so a per-action effective stack and the per-street SPR cannot disagree.
    """
    own = remaining.get(player, 0)
    others = [remaining.get(other, 0) for other in contenders if other != player]
    if not others:
        return own
    return min(own, max(others))


def position_code(value: Any) -> int | None:
    """Encode a HandsPlayers position code the way the event rows store it.

    ``0`` is the button and the numbers count backwards from it through the
    cutoff, hijack, ...; the small blind is ``-1`` and the big blind ``-2``.
    A player whose position was never worked out stays ``None``.
    """
    if value == "S":
        return SMALL_BLIND_POSITION
    if value == "B":
        return BIG_BLIND_POSITION
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _max_numeric_position(handsplayers: dict[str, dict[str, Any]]) -> int:
    """Highest button-relative seat in the hand, or -1 when there is none."""
    seats = [
        code
        for code in (position_code(row.get("position")) for row in handsplayers.values())
        if code is not None and code >= 0
    ]
    return max(seats) if seats else -1


def round_order(handsplayers: dict[str, dict[str, Any]], preflop: bool) -> dict[str, int]:
    """Who acts before whom in one betting round; a lower key acts earlier.

    Preflop the action moves *towards* the button and then to the blinds; from
    the flop on it starts with the small blind and moves away from the button.
    Both are expressed against the same seat numbering, which is why one table
    cannot be used for both.

    Heads-up is the exception the rules make: the button is also the small
    blind and acts *first* preflop but *last* on every later street, so the
    postflop order of the two blind seats is reversed when only they are
    seated (Codex review of #293).
    """
    seats = _max_numeric_position(handsplayers)
    heads_up = _is_heads_up(handsplayers)
    sb_first, bb_first = (0, 1) if preflop else ((0, 1) if not heads_up else (1, 0))
    order: dict[str, int] = {}
    for name, row in handsplayers.items():
        code = row.get("position")
        numeric = position_code(code)
        if code == "S":
            order[name] = seats + 2 if preflop else sb_first
        elif code == "B":
            order[name] = seats + 3 if preflop else bb_first
        elif numeric is None:
            # No position was derived for this player: assume they act last,
            # which keeps them out of everybody else's "still to act behind me"
            # count instead of silently making them the in-position one.
            order[name] = seats + 4 if preflop else seats + 2
        else:
            order[name] = seats - numeric if preflop else 2 + (seats - numeric)
    return order


def _is_heads_up(handsplayers: dict[str, dict[str, Any]]) -> bool:
    """Two players seated: the button is the small blind, not a third seat."""
    return len(handsplayers) == 2


def round_name(street: str) -> str:
    """The betting round a street belongs to (the blinds count as preflop)."""
    return PREFLOP_STREET if street in FIRST_ROUND_STREETS else street


def _streets(hand: Any) -> list[str]:
    """The betting rounds of this hand, in order, or [] if there are none."""
    streets = getattr(hand, "actionStreets", None)
    if streets is None or isinstance(streets, str):
        return []
    try:
        return list(streets)
    except TypeError:
        return []


def _actions(hand: Any) -> dict[str, Any]:
    actions = getattr(hand, "actions", None)
    return actions if isinstance(actions, dict) else {}


def big_blind_cents(hand: Any) -> int:
    """The big blind in cents, from the gametype (0 when it is not known)."""
    gametype = getattr(hand, "gametype", None)
    big_blind = gametype.get("bb") if isinstance(gametype, dict) else None
    if big_blind is None:
        big_blind = getattr(hand, "bb", None)
    return chips_to_cents(big_blind)


def pot_seed_cents(hand: Any) -> int:
    """Bomb / "Escape to Pot" money that is in the pot before anyone acts."""
    return chips_to_cents(getattr(getattr(hand, "pot", None), "stp", 0))


class _EventWalk:
    """One hand's worth of state, walked action by action.

    The pot arithmetic, the betting-round state and the per-decision context
    are kept apart on purpose: they are three different kinds of fact, and the
    round state is the one that has to survive the step from the blinds to
    preflop.
    """

    def __init__(self, hand: Any, handsplayers: dict[str, dict[str, Any]]) -> None:
        self.handsplayers = handsplayers
        self.actions_by_street = _actions(hand)
        self.start_cash = {name: int(row.get("startCash") or 0) for name, row in handsplayers.items()}
        self.big_blind = big_blind_cents(hand)
        self.seed = pot_seed_cents(hand)
        self.events: dict[int, dict[str, Any]] = {}
        self.committed: dict[str, int] = dict.fromkeys(handsplayers, 0)
        self.in_hand = set(handsplayers)
        self.number = 0
        self.order: dict[str, int] = {}
        self.round_bet: dict[str, int] = dict.fromkeys(handsplayers, 0)
        self.bet_level = 0
        self.raise_count = 0
        self.call_count = 0
        self.aggressor: tuple[str, str, int] | None = None
        self.started_round: str | None = None

    def run(self, streets: list[str]) -> dict[int, dict[str, Any]]:
        for street in streets:
            self.walk_street(street)
        return self.events

    def walk_street(self, street: str) -> None:
        actions = list(self.actions_by_street.get(street, []) or [])
        if not actions:
            return
        betting_round = round_name(street)
        self.order = round_order(self.handsplayers, betting_round == PREFLOP_STREET)
        if betting_round != self.started_round:
            self.start_round(betting_round)
        for action in actions:
            self.number += 1
            self.events[self.number] = self.context(action)
            self.advance(action)

    def start_round(self, betting_round: str) -> None:
        """Forget the previous round's betting, keeping the pot as it stands.

        The blind is the price of the first round, so the bet level starts at
        the big blind whenever the round being entered is one the blinds feed
        -- hold'em's PREFLOP, draw's DEAL, stud's SECOND/THIRD. A later round
        starts fresh at zero: there, a bet is what creates the price.
        """
        self.started_round = betting_round
        self.round_bet = dict.fromkeys(self.handsplayers, 0)
        self.bet_level = self.big_blind if betting_round == PREFLOP_STREET else 0
        self.raise_count = 0
        self.call_count = 0
        self.aggressor = None

    def pot_cents(self) -> int:
        return self.seed + sum(self.committed.values())

    def remaining(self) -> dict[str, int]:
        """Chips still behind, in cents, for the players still in the hand."""
        return {
            player: max(0, self.start_cash.get(player, 0) - self.committed.get(player, 0))
            for player in self.in_hand
        }

    def relative_position(self, name: str, remaining: dict[str, int]) -> int:
        """How many players still in the hand act after this one.

        Seat order, not who happened to act last: the cutoff is behind the
        hijack on every street, whoever folded in between. A player with no
        chips left is all-in and cannot act, folded players have left the hand.
        """
        behind = [
            other
            for other in self.in_hand
            if other != name
            and self.order.get(other, 0) > self.order.get(name, 0)
            and remaining.get(other, 0) > 0
        ]
        return len(behind)

    def sizing_bp(self, action: Sequence[Any], word: str | None, pot_before: int) -> int:
        """The action's size as basis points of the pot it faced.

        Bets are measured by the bet and raises by the raise-to amount -- the
        convention ``HandsPlayers.val_*_bet_made_bp`` and
        ``val_*_raise_made_bp`` already use, so an event and the aggregate
        column it feeds cannot drift apart.
        """
        if pot_before <= 0:
            return 0
        if word == "bets":
            return chips_to_cents(action[ACTION_AMOUNT_IDX]) * BASIS_POINTS // pot_before
        if word in RAISE_ACTIONS and len(action) > ACTION_RAISETO_IDX:
            return chips_to_cents(action[ACTION_RAISETO_IDX]) * BASIS_POINTS // pot_before
        return 0

    @staticmethod
    def acting_player(action: Sequence[Any]) -> str:
        """The name of the player making an action (empty for a malformed one)."""
        return str(action[0]) if action else ""

    def context(self, action: Sequence[Any]) -> dict[str, Any]:
        """The event of one action, measured before its chips go in."""
        name = self.acting_player(action)
        word = action[ACTION_TYPE_IDX] if len(action) > ACTION_TYPE_IDX else None
        forced = word in FORCED_ACTIONS
        pot_before = self.pot_cents()
        # The price of continuing. Forced money raises the bar -- the blinds are
        # what an opener calls -- but is not itself a bet that anybody faces.
        to_call = 0 if forced else max(0, self.bet_level - self.round_bet.get(name, 0))
        sizing = self.sizing_bp(action, word, pot_before)

        facing_action, facing_amount, facing_sizing = None, 0, 0
        if not forced and to_call > 0 and self.aggressor is not None:
            facing_action, facing_amount, facing_sizing = self.aggressor[1], to_call, self.aggressor[2]

        remaining = self.remaining()
        relative = self.relative_position(name, remaining)
        effective = effective_stack_cents(remaining, name, list(remaining))

        event = dict(ACTION_EVENT_DEFAULTS)
        event.update(
            {
                "actionType": word,
                "toCall": to_call,
                "potBefore": pot_before,
                "potAfter": pot_before + action_chips(action),
                "sizingBp": sizing,
                "position": position_code(self.handsplayers.get(name, {}).get("position")),
                "relativePosition": relative,
                "inPosition": relative == 0,
                "effectiveStack": effective,
                "effectiveStackBB": effective * 100 // self.big_blind if self.big_blind > 0 else 0,
                "sprBefore": effective * 100 // pot_before if pot_before > 0 else 0,
                "isAggressor": word in AGGRESSIVE_ACTIONS,
                "facingActionType": facing_action,
                "facingAmount": facing_amount,
                "facingSizingBp": facing_sizing,
                "raiserCount": self.raise_count,
                "callerCount": self.call_count,
                "playersInHand": len(self.in_hand),
            },
        )
        return event

    def advance(self, action: Sequence[Any]) -> None:
        """Fold this action into the state the next event is measured against."""
        name = self.acting_player(action)
        word = action[ACTION_TYPE_IDX] if len(action) > ACTION_TYPE_IDX else None
        put_in = action_chips(action)
        self.committed[name] = self.committed.get(name, 0) + put_in
        if word not in DEAD_MONEY_ACTIONS:
            self.round_bet[name] = self.round_bet.get(name, 0) + put_in
            self.bet_level = max(self.bet_level, self.round_bet[name])
        if word in AGGRESSIVE_ACTIONS:
            self.raise_count += 1
            self.aggressor = (name, str(word), self.events[self.number]["sizingBp"])
        elif word == "calls":
            self.call_count += 1
        elif word == "folds":
            self.in_hand.discard(name)


def derive_action_events(hand: Any, handsplayers: dict[str, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Build the normalized event of every action of one hand.

    Returns ``{actionNo: {column: value}}`` keyed by the same global action
    number ``assembleHandsActions`` uses, so the caller can merge each event
    into the row it already wrote for that action. The action order is the
    parser's: nothing is reordered, merged or dropped.
    """
    streets = _streets(hand)
    if not streets:
        return {}
    return _EventWalk(hand, handsplayers).run(streets)


def attach_action_events(
    handsactions: dict[Any, dict[str, Any]],
    hand: Any,
    handsplayers: dict[str, dict[str, Any]],
) -> None:
    """Merge the derived events into the action rows ``assembleHandsActions`` built.

    Rows the derivator does not know about are left alone, so a hand whose
    actions have already been condensed by a calculator keeps whatever the
    action pass wrote.
    """
    for number, event in derive_action_events(hand, handsplayers).items():
        row = handsactions.get(number)
        if isinstance(row, dict):
            row.update(event)
