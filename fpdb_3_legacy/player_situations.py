"""Generic player situation model for the analytics layer (issue #294).

``DerivedStats`` answers "how often did this player do X" with a column per
answer: ``raisedFirstIn``, ``squeezeChance``, ``street1CBDone``, twenty
``enum_*_action`` chars, and so on. Every one of those columns is a bespoke
procedure over the action stream, and each new question -- "open-raise from the
cutoff at 40bb", "fold to a turn probe in position" -- needs another procedure,
because the *situation* was never a value that could be queried, only a stretch
of code that happened to compute it.

This module makes the situation a value. A :class:`PlayerSituation` is one
decision a player made, with the context they made it in: the game, the player's
seat and stack, the shape of the pot, what was in front of them, what they had
already seen, and what they did. Situations come from the normalized per-action
events of ``HandsActions`` (issue #293) plus the per-player context
``assembleHandsPlayers`` computed, so this module contains no parser knowledge
of its own and cannot disagree with the events it reads.

Naming a situation is then a *rule table* (:data:`SITUATION_RULES`), not a
procedure: a squeeze and a 3-bet defence and a defence against an open are three
rows in one table over the same context, so a spot is expressible as soon as its
predicate is -- no new function per combination. A decision usually matches
several rules at once (an open-raise from the cutoff in an unopened pot is a
"steal", a "raise first in" and an "open"), so every match is kept in
``labels`` and ``primary`` is the first, most specific one.

The PT4 ``enum_*_action`` columns are projected from the same rules
(:func:`enum_responses`), which is the migration path for the existing stats:
the projection reproduces the validated legacy semantics on the golden corpus
(see ``tests/test_player_situations.py``), so a calculator can be flipped from
its bespoke procedure to the model with the test as the safety net.

Units, the fact-by-fact vocabulary and the rule table: ``docs/situation-model.md``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, replace
from decimal import Decimal
from typing import Any

# Action words as the parsers spell them (Hand.ACTION). Forced money is context,
# never a decision: a blind is not something a player chose to do.
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

# A decision, in the terms the model names the response in. ``completes`` is a
# stud raise; it is kept apart so the draw/stud stream stays readable.
RESPONSES: dict[str, str] = {
    "folds": "fold",
    "checks": "check",
    "calls": "call",
    "bets": "bet",
    "raises": "raise",
    "completes": "complete",
}
# Actions as the parsers spell them (raw), and responses as this model names
# them (normalized). Rules over a decision read the response; the walk over the
# hand reads the action, and the two are not interchangeable.
DECISION_ACTIONS = frozenset(RESPONSES)
AGGRESSIVE_ACTIONS = frozenset({"bets", "raises", "completes"})
AGGRESSIVE_RESPONSES = frozenset({"bet", "raise", "complete"})

# The response char the PT4 enums store. A check answers nothing: it is what a
# player does when the spot never actually arose for them.
ENUM_RESPONSE_CHARS: dict[str, str] = {
    "fold": "F",
    "call": "C",
    "complete": "C",
    "bet": "R",
    "raise": "R",
}

# Street naming. Hold'em and Omaha have the four names everything else speaks
# in; stud and the draw games have rounds of their own, and their hands carry
# the names, so a situation is never labelled "turn" when it is fifth street.
STREET_NAMES = ("preflop", "flop", "turn", "river")
# The rounds that are the preflop round: the forced bets and the first one.
FIRST_ACTION_STREETS = frozenset({"BLINDSANTES", "ANTES", "PREFLOP"})
# The street letters the postflop PT4 columns use: flop, turn, river.
STREET_LETTERS = {1: "f", 2: "t", 3: "r"}

# The shape of the pot, as the player met it. Preflop this is the round as it
# stands ("the pot is unopened and it is on me"); postflop it is the shape the
# preflop round ended in ("this is a single raised pot").
POT_UNOPENED = "unopened"
POT_LIMPED = "limped"
POT_SINGLE_RAISED = "single_raised"
POT_THREE_BET = "three_bet"
POT_FOUR_BET_PLUS = "four_bet_plus"

# Effective stack in big blinds, two decimals (100 = 1bb, 10000 = 100bb). The
# bands are the usual 20/50/100 bucket boundaries.
SHORT_STACK_BB = 2000
MEDIUM_STACK_BB = 5000
DEEP_STACK_BB = 10000

# Button-relative seat codes a steal can come from: the button, the cutoff and
# the small blind.
STEAL_POSITIONS = frozenset({0, 1, -1})

# Hand categories with a flop and five community cards, where the positional
# vocabulary of this module (button, blinds, relative seats) applies as-is.
BOARD_GAMES = frozenset({"holdem", "omaha"})


@dataclass(frozen=True)
class PlayerSituation:
    """One decision a player made, with the context they made it in.

    Every amount is in cents and every ratio in basis points or centi-units,
    exactly as the event rows store them (``docs/action-event-model.md``).
    The context describes what the player had in front of them *before* their
    action: a decision is never explained by its own chips.
    """

    # --- identity ---------------------------------------------------------
    hand_id: int
    action_no: int
    street: int
    street_name: str
    player: str

    # --- game context -----------------------------------------------------
    site: str
    game: str
    limit_type: str
    is_tournament: bool
    table_size: int
    players_dealt: int
    small_blind: int
    big_blind: int
    currency: str

    # --- player context ---------------------------------------------------
    position: int | None
    relative_position: int
    in_position: bool
    effective_stack: int
    effective_stack_bb: int
    stack_bucket: str
    spr_before: int
    is_hero: bool

    # --- pot context ------------------------------------------------------
    pot_type: str
    multiway: bool
    players_in_hand: int
    preflop_aggressor: str | None
    is_preflop_aggressor: bool
    street_aggressor: str | None
    is_aggressor: bool
    first_aggressor: str | None
    previous_aggressor: str | None
    is_previous_aggressor: bool
    previous_aggressor_led: bool
    previous_aggressor_checked: bool
    previous_aggressor_position: int | None
    in_position_vs_previous_aggressor: bool | None
    aggressor_checked_this_street: bool
    previous_raiser: str | None
    is_previous_raiser: bool

    # --- decision context -------------------------------------------------
    to_call: int
    pot_before: int
    pot_after: int
    pot_odds_bp: int
    facing_action: str | None
    facing_player: str | None
    facing_position: int | None
    in_position_vs_facing: bool | None
    facing_amount: int
    facing_sizing_bp: int
    facing_all_in: bool
    bet_level_faced: int
    raises_before: int
    calls_before: int
    callers_between_raises: int
    callers_since_raise: int

    # --- what the player had already seen and done ------------------------
    street_actions: tuple[tuple[str, str], ...]
    previous_street_actions: tuple[str, ...]

    # --- board ------------------------------------------------------------
    board: tuple[str, ...]

    # --- response ---------------------------------------------------------
    response: str
    is_all_in: bool
    role: str

    # --- names (filled by the rule table) ---------------------------------
    labels: tuple[str, ...] = ()
    primary: str = ""
    group: str = ""
    enum_key: str | None = None
    enum_response: str | None = None
    enum_answers: tuple[tuple[str, str], ...] = ()

    @property
    def voluntary_actions(self) -> tuple[tuple[str, str], ...]:
        """This round's voluntary actions before the decision, in order."""
        return tuple((player, action) for player, action in self.street_actions if action not in FORCED_ACTIONS)

    @property
    def my_actions(self) -> tuple[str, ...]:
        """This player's own voluntary actions on this round, before now."""
        return tuple(action for player, action in self.voluntary_actions if player == self.player)

    @property
    def is_preflop(self) -> bool:
        return self.street == 0

    @property
    def is_facing(self) -> bool:
        """True when the player faced a real bet or raise, not a blind level."""
        return self.facing_action is not None

    def in_group(self, group: str) -> bool:
        return self.group == group

    def has_label(self, label: str) -> bool:
        return label in self.labels

    def as_dict(self) -> dict[str, Any]:
        """Flat record, for logging, docs and any future persisted form (#305)."""
        return asdict(self)


@dataclass(frozen=True)
class SituationRule:
    """One nameable spot, expressed as a predicate over the situation context.

    ``response`` narrows the rule to the decisions that took a particular line
    (``("raise", "complete")`` = a raise); ``None`` means the rule describes the
    *opportunity* itself, and the response is whatever the player did with it --
    which is how a chance/done pair of aggregate columns falls out of one rule.
    ``enum_key`` is the PT4 column this spot answers, if any; ``{s}`` is
    substituted with the street letter (f/t/r) for the postflop families.
    """

    name: str
    group: str
    label: str
    applies: Callable[[PlayerSituation], bool]
    response: tuple[str, ...] | None = None
    streets: tuple[int, ...] | None = None
    enum_key: str | None = None

    def matches(self, situation: PlayerSituation) -> bool:
        if self.streets is not None and situation.street not in self.streets:
            return False
        if self.response is not None and situation.response not in self.response:
            return False
        return self.applies(situation)


def _enum_key(rule: SituationRule, situation: PlayerSituation) -> str | None:
    """The PT4 column a rule answers, with the street letter substituted."""
    if rule.enum_key is None:
        return None
    letter = STREET_LETTERS.get(situation.street)
    if "{s}" in rule.enum_key and letter is None:
        return None
    return rule.enum_key.format(s=letter or "")


# ---------------------------------------------------------------------------
# Rule predicates. Each is a statement about context, never about a procedure:
# "the pot is unopened and I am the first to enter it", "I am facing the third
# bet of this round". Every spot in the table below is built from these.
# ---------------------------------------------------------------------------


def _unopened(situation: PlayerSituation) -> bool:
    """Nobody has voluntarily entered the pot yet; it is on this player."""
    return situation.pot_type == POT_UNOPENED


def _limped(situation: PlayerSituation) -> bool:
    """There are limpers (voluntary calls) and no raise in front."""
    return situation.pot_type == POT_LIMPED


def _raised(situation: PlayerSituation) -> bool:
    """A raise is in front of this player on the preflop round."""
    return situation.facing_action == "raises"


def _facing_bet(situation: PlayerSituation) -> bool:
    return situation.facing_action == "bets"


def _bet_level(level: int) -> Callable[[PlayerSituation], bool]:
    """Predicate for facing the ``level``-th bet/raise of the round.

    Counting from the forced bet: preflop the big blind is the first bet, so
    "facing the open" is level 2 and "facing a 3-bet" is level 3; postflop the
    first bet is level 1, so a 3-bet (bet, raise, re-raise) is level 3 as well.
    """

    def applies(situation: PlayerSituation) -> bool:
        return situation.bet_level_faced == level

    return applies


def _bet_level_at_least(level: int) -> Callable[[PlayerSituation], bool]:
    def applies(situation: PlayerSituation) -> bool:
        return situation.bet_level_faced >= level

    return applies


def _squeeze_defence(situation: PlayerSituation) -> bool:
    """Facing a raise that already has a cold caller behind it.

    This is the spot as the *defender* meets it, which is what the PT4
    ``enum_p_squeeze_action`` column records -- the opener faces it too.
    """
    return (
        situation.is_preflop
        and _raised(situation)
        and situation.bet_level_faced == 3
        and situation.callers_between_raises >= 1
    )


def _squeeze_spot(situation: PlayerSituation) -> bool:
    """Cold-calling or re-raising a raise that already has callers behind it.

    The player must not have put money in voluntarily yet: a player who opened
    and is now facing a 3-bet is defending (their re-raise is a 4-bet), which is
    why the opener and the cold player get different spots out of the same
    raise-plus-caller shape.
    """
    return (
        situation.is_preflop
        and _raised(situation)
        and situation.bet_level_faced >= 2
        and situation.callers_since_raise >= 1
        and not _has_voluntary_money_in(situation)
    )


def _has_voluntary_money_in(situation: PlayerSituation) -> bool:
    return any(
        player == situation.player and action in ("calls", "bets", "raises", "completes")
        for player, action in situation.voluntary_actions
    )


def _first_aggression_is_faced(situation: PlayerSituation) -> bool:
    """The aggression in front of the player is the street's first one.

    Facing a raise that answers an earlier bet is a different spot -- a 3-bet,
    not a bet -- and gets its own rule.
    """
    return situation.is_facing and situation.facing_player == situation.first_aggressor


def _no_aggression_in_front(situation: PlayerSituation) -> bool:
    """No one has bet or raised before this player on this round."""
    return situation.first_aggressor is None


def _previous_aggressor_bets(situation: PlayerSituation) -> bool:
    """The player in front is the one who last showed aggression on the previous street."""
    return situation.is_facing and situation.facing_player == situation.previous_aggressor


def _i_am_previous_aggressor(situation: PlayerSituation) -> bool:
    return situation.is_previous_aggressor


def _postflop(situation: PlayerSituation) -> bool:
    return situation.street >= 1


def _cbet_spot(situation: PlayerSituation) -> bool:
    """The previous street's aggressor, with no bet in front on this street.

    Postflop the aggressor of a street is whoever raised last on it, or the
    previous street's aggressor if they made the first bet; the chain is what
    "continuation bet" means. With no bet in front, the player may lead or
    decline, which is why this predicate is the opportunity for both. The flop
    is the continuation by definition; later streets additionally require that
    the player actually led the street before (a player who checked the flop
    and bets the turn is making a *delayed* continuation bet, whose own rule is
    more specific and must win).
    """
    return (
        _postflop(situation)
        and _i_am_previous_aggressor(situation)
        and _no_aggression_in_front(situation)
        and situation.to_call == 0
        and _continued_aggression(situation)
    )


def _continued_aggression(situation: PlayerSituation) -> bool:
    """The player led the previous street (a flop c-bet needs no history)."""
    if situation.street == 1:
        return True
    return any(action in AGGRESSIVE_ACTIONS for action in situation.previous_street_actions)


def _facing_cbet_spot(situation: PlayerSituation) -> bool:
    """Facing the previous street's aggressor, who led it and leads this one."""
    return (
        _postflop(situation)
        and _facing_bet(situation)
        and _previous_aggressor_bets(situation)
        and _first_aggression_is_faced(situation)
        and situation.previous_aggressor_led
    )


def _facing_delayed_cbet_spot(situation: PlayerSituation) -> bool:
    """Facing the previous street's aggressor, who checked it and now bets."""
    return (
        _postflop(situation)
        and _facing_bet(situation)
        and _previous_aggressor_bets(situation)
        and _first_aggression_is_faced(situation)
        and situation.previous_aggressor_checked
    )


def _leads_into_aggressor(situation: PlayerSituation) -> bool:
    """Opening the street's betting without being the previous street's aggressor."""
    return (
        _postflop(situation)
        and _no_aggression_in_front(situation)
        and situation.previous_aggressor is not None
        and not _i_am_previous_aggressor(situation)
    )


def _float_bet_spot(situation: PlayerSituation) -> bool:
    """Betting because the aggressor just gave up, having called them before.

    The third way of leading into an aggressor, and the only one that is about
    *this* street: they bet the last one, the player called in position, and
    they have now checked in front of the player. The legacy code calls this a
    float as well; the model keeps it apart from the continuation-bet response,
    because they are two different players taking two different lines.
    """
    return (
        situation.street >= 2
        and _leads_into_aggressor(situation)
        and situation.aggressor_checked_this_street
        and "calls" in situation.previous_street_actions
        and situation.in_position_vs_previous_aggressor is True
    )


def _donk_spot(situation: PlayerSituation) -> bool:
    """Betting into an aggressor who has not shown weakness yet.

    The remainder of the leading-into-an-aggressor cases: they bet the previous
    street and have not given up on this one yet.
    """
    return (
        _leads_into_aggressor(situation)
        and not situation.previous_aggressor_checked
        and not _float_bet_spot(situation)
    )


def _facing_donk_spot(situation: PlayerSituation) -> bool:
    """The previous street's aggressor facing a bet from someone else.

    On the turn this is the probe: the aggressor declined the flop and someone
    now bets into the weakness. The street letter tells the two apart.
    """
    return (
        _facing_bet(situation)
        and _i_am_previous_aggressor(situation)
        and _first_aggression_is_faced(situation)
        and situation.facing_player is not None
        and situation.facing_player != situation.player
    )


def _checked_previous_street(situation: PlayerSituation) -> bool:
    """The player's only voluntary action on the previous street was a check."""
    return situation.previous_street_actions == ("checks",)


def _delayed_cbet_spot(situation: PlayerSituation) -> bool:
    """Declined the lead on the previous street, now able to open this one."""
    return (
        _postflop(situation)
        and situation.street >= 2
        and situation.is_preflop_aggressor
        and _checked_previous_street(situation)
        and _no_aggression_in_front(situation)
        and situation.to_call == 0
    )


def _probe_spot(situation: PlayerSituation) -> bool:
    """The mirror of the delayed c-bet: opening after the aggressor declined.

    A donk bet goes *into* the aggressor; a probe bet follows the check they
    showed on the previous street. Same action, different situation, and the
    only difference in the context is whether that aggressor checked.
    """
    return _leads_into_aggressor(situation) and situation.previous_aggressor_checked


def _float_spot(situation: PlayerSituation) -> bool:
    """Facing the second barrel after floating the previous street in position.

    The float is the caller's line, so the situation is recorded on the caller:
    they answered the first bet with a call, in position, and now the same
    player is betting again. Their reply -- fold, call or raise -- is the PT4
    float action.
    """
    return (
        _facing_cbet_spot(situation)
        and situation.street >= 2
        and "calls" in situation.previous_street_actions
        and situation.in_position_vs_facing is True
    )


def _check_raise(situation: PlayerSituation) -> bool:
    return (
        _postflop(situation)
        and situation.response == "raise"
        and "checks" in situation.my_actions
    )


def _facing_all_in(situation: PlayerSituation) -> bool:
    return situation.is_facing and situation.facing_all_in


def _heads_up(situation: PlayerSituation) -> bool:
    return situation.players_in_hand == 2


def _multiway(situation: PlayerSituation) -> bool:
    return situation.multiway


def _steal_position(situation: PlayerSituation) -> bool:
    return situation.position is not None and situation.position in STEAL_POSITIONS


SITUATION_RULES: tuple[SituationRule, ...] = (
    # -- preflop: the line the player took ---------------------------------
    SituationRule(
        "open_raise",
        "POT_OPEN",
        "open raise (raise first in)",
        _unopened,
        response=("raise", "complete"),
        streets=(0,),
    ),
    SituationRule(
        "open_limp",
        "POT_OPEN",
        "open limp",
        _unopened,
        response=("call",),
        streets=(0,),
    ),
    SituationRule(
        "open_fold",
        "POT_OPEN",
        "folds an unopened pot",
        _unopened,
        response=("fold",),
        streets=(0,),
    ),
    SituationRule(
        "isolation_raise",
        "POT_LIMPED",
        "iso-raise over limpers",
        _limped,
        response=("raise", "complete"),
        streets=(0,),
    ),
    SituationRule(
        "over_limp",
        "POT_LIMPED",
        "over-limp behind limpers",
        _limped,
        response=("call",),
        streets=(0,),
    ),
    # -- preflop: raising and defending a raise ----------------------------
    SituationRule(
        "squeeze",
        "PREFLOP_SQUEEZE",
        "squeeze",
        _squeeze_spot,
        response=("raise", "complete"),
        streets=(0,),
    ),
    SituationRule(
        "three_bet",
        "PREFLOP_DEFENCE",
        "3-bet",
        lambda situation: _raised(situation) and situation.bet_level_faced == 2,
        response=("raise", "complete"),
        streets=(0,),
    ),
    SituationRule(
        "four_bet",
        "PREFLOP_DEFENCE",
        "4-bet",
        _bet_level(3),
        response=("raise", "complete"),
        streets=(0,),
    ),
    # -- postflop: taking the lead -----------------------------------------
    SituationRule(
        "cbet",
        "POSTFLOP_AGGRESSION",
        "continuation bet",
        _cbet_spot,
        response=("bet",),
        streets=(1, 2, 3),
    ),
    SituationRule(
        "delayed_cbet",
        "POSTFLOP_AGGRESSION",
        "delayed continuation bet",
        _delayed_cbet_spot,
        response=("bet",),
        streets=(2, 3),
    ),
    SituationRule(
        "probe",
        "POSTFLOP_AGGRESSION",
        "probe bet",
        _probe_spot,
        response=("bet",),
        streets=(2, 3),
    ),
    SituationRule(
        "float_bet",
        "POSTFLOP_AGGRESSION",
        "float bet after the aggressor gave up",
        _float_bet_spot,
        response=("bet",),
        streets=(2, 3),
    ),
    SituationRule(
        "donk",
        "POSTFLOP_AGGRESSION",
        "donk bet",
        _donk_spot,
        response=("bet",),
        streets=(1, 2, 3),
    ),
    SituationRule(
        "check_raise",
        "POSTFLOP_AGGRESSION",
        "check-raise",
        _check_raise,
        streets=(1, 2, 3),
    ),
    # -- the spot the player was up against --------------------------------
    SituationRule(
        "squeeze_defence",
        "PREFLOP_SQUEEZE",
        "facing a raise with cold callers behind it",
        _squeeze_defence,
        streets=(0,),
        enum_key="enum_p_squeeze_action",
    ),
    SituationRule(
        "facing_delayed_cbet",
        "POSTFLOP_DEFENCE",
        "facing a delayed continuation bet",
        _facing_delayed_cbet_spot,
        streets=(2, 3),
    ),
    SituationRule(
        "facing_cbet",
        "POSTFLOP_DEFENCE",
        "facing a continuation bet",
        _facing_cbet_spot,
        enum_key="enum_{s}_cbet_action",
        streets=(1, 2, 3),
    ),
    SituationRule(
        "facing_donk",
        "POSTFLOP_DEFENCE",
        "facing a donk/probe bet",
        _facing_donk_spot,
        enum_key="enum_{s}_donk_action",
        streets=(1, 2, 3),
    ),
    SituationRule(
        "facing_float",
        "POSTFLOP_DEFENCE",
        "facing the second barrel after a float in position",
        _float_spot,
        enum_key="enum_{s}_float_action",
        streets=(2, 3),
    ),
    SituationRule(
        "facing_raise",
        "POSTFLOP_DEFENCE",
        "facing a raise (second bet of the street)",
        lambda situation: _postflop(situation) and _raised(situation) and situation.bet_level_faced == 2,
        streets=(1, 2, 3),
    ),
    SituationRule(
        "facing_3bet",
        "PREFLOP_DEFENCE",
        "facing a 3-bet",
        _bet_level(3),
        streets=(0,),
        enum_key="enum_p_3bet_action",
    ),
    SituationRule(
        "facing_3bet",
        "POSTFLOP_DEFENCE",
        "facing a 3-bet",
        lambda situation: _postflop(situation) and _bet_level(3)(situation),
        enum_key="enum_{s}_3bet_action",
        streets=(1, 2, 3),
    ),
    SituationRule(
        "facing_4bet",
        "PREFLOP_DEFENCE",
        "facing a 4-bet",
        _bet_level(4),
        streets=(0,),
        enum_key="enum_p_4bet_action",
    ),
    SituationRule(
        "facing_4bet",
        "POSTFLOP_DEFENCE",
        "facing a 4-bet",
        lambda situation: _postflop(situation) and _bet_level(4)(situation),
        enum_key="enum_{s}_4bet_action",
        streets=(1, 2, 3),
    ),
    SituationRule(
        "five_bet_plus",
        "PREFLOP_DEFENCE",
        "facing a 5-bet or more",
        _bet_level_at_least(5),
        streets=(0,),
    ),
    SituationRule(
        "opener_vs_3bet",
        "PREFLOP_DEFENCE",
        "opener facing a 3-bet",
        lambda situation: _bet_level(3)(situation) and situation.is_previous_raiser,
        streets=(0,),
    ),
    SituationRule(
        "three_bettor_vs_4bet",
        "PREFLOP_DEFENCE",
        "3-bettor facing a 4-bet",
        lambda situation: _bet_level(4)(situation) and situation.is_previous_raiser,
        streets=(0,),
    ),
    SituationRule(
        "facing_limpers",
        "POT_LIMPED",
        "facing limpers",
        _limped,
        streets=(0,),
    ),
    SituationRule(
        "facing_open",
        "PREFLOP_DEFENCE",
        "facing an open raise",
        lambda situation: _raised(situation) and situation.bet_level_faced == 2,
        streets=(0,),
        enum_key=None,
    ),
    # -- the opportunity the player declined -------------------------------
    SituationRule(
        "cbet_spot",
        "POSTFLOP_AGGRESSION",
        "continuation bet opportunity",
        _cbet_spot,
        enum_key=None,
        streets=(1, 2, 3),
    ),
    SituationRule(
        "delayed_cbet_spot",
        "POSTFLOP_AGGRESSION",
        "delayed continuation bet opportunity",
        _delayed_cbet_spot,
        streets=(2, 3),
    ),
    SituationRule(
        "probe_spot",
        "POSTFLOP_AGGRESSION",
        "turn probe opportunity",
        _probe_spot,
        streets=(2, 3),
    ),
    SituationRule(
        "float_bet_spot",
        "POSTFLOP_AGGRESSION",
        "float bet opportunity after the aggressor gave up",
        _float_bet_spot,
        streets=(2, 3),
    ),
    SituationRule(
        "donk_spot",
        "POSTFLOP_AGGRESSION",
        "donk bet opportunity",
        _donk_spot,
        streets=(1, 2, 3),
    ),
    SituationRule(
        "squeeze_spot",
        "PREFLOP_SQUEEZE",
        "cold spot against a raise with callers",
        _squeeze_spot,
        streets=(0,),
    ),
    SituationRule(
        "steal_spot",
        "POT_OPEN",
        "unopened pot from a steal seat (CO/BTN/SB)",
        lambda situation: _unopened(situation) and _steal_position(situation),
        streets=(0,),
    ),
    SituationRule(
        "preflop_unopened",
        "POT_OPEN",
        "unopened pot, first to enter",
        _unopened,
        streets=(0,),
    ),
    # -- facts worth naming ------------------------------------------------
    SituationRule(
        "facing_all_in",
        "ALL_IN",
        "facing an all-in bet or raise",
        _facing_all_in,
    ),
    SituationRule(
        "all_in_raise",
        "ALL_IN",
        "moving all-in",
        lambda situation: situation.is_all_in and situation.response in AGGRESSIVE_RESPONSES,
    ),
    # -- the plain lines, so that every decision carries a name -------------
    SituationRule(
        "check_no_bet",
        "RESPONSE",
        "check with no bet in front",
        _no_aggression_in_front,
        response=("check",),
    ),
    SituationRule(
        "call_no_raise",
        "RESPONSE",
        "call with no raise in front",
        lambda situation: situation.facing_action == "bets",
        response=("call",),
    ),
    SituationRule(
        "fold_no_raise",
        "RESPONSE",
        "fold to a bet (not a raise)",
        lambda situation: situation.facing_action == "bets",
        response=("fold",),
    ),
    # -- structure ----------------------------------------------------------
    SituationRule(
        "heads_up",
        "STRUCTURE",
        "heads-up pot",
        _heads_up,
    ),
    SituationRule(
        "multiway",
        "STRUCTURE",
        "three or more players still in",
        _multiway,
    ),
)



def classify(situation: PlayerSituation) -> PlayerSituation:
    """Name a situation through the rule table.

    Every matching rule contributes a label, the first (most specific) match
    becomes the primary spot, and its group and PT4 column travel with it. The
    result is a new frozen situation; the facts are never rewritten.
    """
    labels = []
    answers: list[tuple[str, str]] = []
    primary = ""
    group = ""
    enum_key = None
    response = ENUM_RESPONSE_CHARS.get(situation.response)
    for rule in SITUATION_RULES:
        if not rule.matches(situation):
            continue
        labels.append(rule.name)
        key = _enum_key(rule, situation)
        if key is not None and response is not None:
            answers.append((key, response))
        if not primary and rule.group != "STRUCTURE":
            primary = rule.name
            group = rule.group
            enum_key = key if response is not None else None
    return replace(
        situation,
        labels=tuple(labels),
        primary=primary,
        group=group,
        enum_key=enum_key,
        enum_response=response if enum_key is not None else None,
        enum_answers=tuple(answers),
    )


@dataclass
class _RoundState:
    """What the round has seen so far, for the situations still to come."""

    street: int
    actions: list[tuple[str, str]]
    first_aggressor: str | None
    last_aggressor: str | None
    last_aggression_all_in: bool
    raises: list[tuple[str, int]]
    player_actions: dict[str, list[str]]

    def reset(self) -> None:
        self.actions = []
        self.first_aggressor = None
        self.last_aggressor = None
        self.last_aggression_all_in = False
        self.raises = []
        self.player_actions = {}


class _SituationWalk:
    """Walks one hand's event rows and emits the decision they contain.

    The event rows already carry the price, the pot, the seat and the stack at
    every action (issue #293); this walk adds the few facts a decision needs
    that are about *history* rather than about the moment -- who opened the
    pot, who last showed aggression, what the player did on the previous
    street, how many callers sat between two raises.
    """

    def __init__(
        self,
        hand: Any,
        handsplayers: dict[str, dict[str, Any]],
        rows: Sequence[dict[str, Any]],
    ) -> None:
        self.hand = hand
        self.handsplayers = handsplayers
        self.rows = rows
        self.gametype = getattr(hand, "gametype", None) or {}
        self.board = getattr(hand, "board", None) or {}
        self.hero = getattr(hand, "hero", "") or ""
        self.street_names = _street_names(hand)
        self.boards = _boards(hand, self.board)
        self.situations: list[PlayerSituation] = []
        self.round = _round_state(0)
        self.preflop_aggressor: str | None = None
        self.preflop_pot_type = POT_UNOPENED
        self.preflop_seen = False
        self.chain_aggressor: str | None = None
        self.previous_street_actions: dict[str, tuple[str, ...]] = {}

    # -- round bookkeeping -------------------------------------------------

    def _advance_street(self, street: int) -> None:
        if self.round.street == street:
            return
        self._finish_round()
        self.round = _round_state(street)

    def _finish_round(self) -> None:
        """Close the finished round: settle the pot shape and the aggressor chain."""
        if not self.round.actions:
            return
        # The previous street's aggressor chain, as the c-bet/facing rules read
        # it: the last raiser on the street, or the street before it owner if
        # they were the one who opened this street's betting.
        last_raiser = self.round.raises[-1][0] if self.round.raises else None
        if last_raiser is not None:
            self.chain_aggressor = last_raiser
        elif self.round.first_aggressor is not None and self.round.first_aggressor == self.chain_aggressor:
            pass  # the chain owner led the street: they stay the aggressor
        elif self.round.first_aggressor is None:
            pass  # nobody bet: the street carried no aggression and the lead stands
        else:
            self.chain_aggressor = None
        self.previous_street_actions = {
            player: tuple(actions) for player, actions in self.round.player_actions.items()
        }
        if self.round.street == 0:
            self.preflop_aggressor = last_raiser
            self.preflop_pot_type = _final_pot_type(self.round)
            self.preflop_seen = True

    def _record(self, row: dict[str, Any], word: str) -> None:
        player = str(row.get("player") or "")
        self.round.actions.append((player, word))
        self.round.player_actions.setdefault(player, []).append(word)
        if word in AGGRESSIVE_ACTIONS:
            if self.round.first_aggressor is None:
                self.round.first_aggressor = player
            self.round.last_aggressor = player
            self.round.last_aggression_all_in = bool(row.get("allIn"))
            self.round.raises.append((player, int(row.get("callerCount") or 0)))

    # -- facts -------------------------------------------------------------

    def _fact_value(self, row: dict[str, Any], key: str, default: Any) -> Any:
        value = row.get(key, default)
        return default if value is None else value

    def _pot_type(self) -> str:
        """The shape of the pot as the player meets it, before this action."""
        if self.round.street != 0:
            return self.preflop_pot_type
        raises = len([True for _player, action in self.round.actions if action in ("raises", "completes")])
        calls = len([True for _player, action in self.round.actions if action == "calls"])
        if raises == 0:
            return POT_LIMPED if calls else POT_UNOPENED
        if raises == 1:
            return POT_SINGLE_RAISED
        if raises == 2:
            return POT_THREE_BET
        return POT_FOUR_BET_PLUS

    def _facing_player(self, word: str, to_call: int) -> str | None:
        if to_call <= 0 or word in FORCED_ACTIONS:
            return None
        return self.round.last_aggressor

    def _facing_all_in(self) -> bool:
        """Whether the aggression in front of the player was an all-in."""
        return self.round.last_aggression_all_in

    def _previous_aggressor_actions(self) -> tuple[str, ...]:
        """What the previous street's aggressor did on it.

        One player's decision is often about somebody else's: a probe bet only
        means something because the aggressor showed weakness first, and a
        second barrel only counts as one if they fired the first.
        """
        if self.chain_aggressor is None:
            return ()
        return self.previous_street_actions.get(self.chain_aggressor, ())

    def _previous_aggressor_checked(self) -> bool:
        """The previous street's aggressor only checked it (they declined the lead)."""
        return self._previous_aggressor_actions() == ("checks",)

    def _aggressor_checked_this_street(self) -> bool:
        """The previous street's aggressor has checked in front on this street."""
        if self.chain_aggressor is None:
            return False
        actions = self.round.player_actions.get(self.chain_aggressor, [])
        return "checks" in actions and not any(a in AGGRESSIVE_ACTIONS for a in actions)

    def _previous_raiser(self) -> str | None:
        """Whoever raised just before the raise in front of this player.

        The opener facing a 3-bet and the 3-bettor facing a 4-bet are the same
        fact about the raise history, which is why one lookup answers both.
        """
        if len(self.round.raises) < 2:
            return None
        return self.round.raises[-2][0]

    def _previous_aggressor_led(self) -> bool:
        return any(action in AGGRESSIVE_ACTIONS for action in self._previous_aggressor_actions())

    def _callers_between_raises(self) -> int:
        """Cold callers who sat between the two raises in front of this player.

        What an aggressive defender of a 3-bet met: everybody who called between
        the open and the 3-bet. The PT4 squeeze column counts exactly this.
        """
        counts = [count for _player, count in self.round.raises]
        if len(counts) < 2:
            return 0
        return max(0, counts[-1] - counts[-2])

    def _callers_since_raise(self, calls_before: int) -> int:
        """Callers who have already called the raise in front of this player.

        What the squeezer met: the raise they are re-raising already has cold
        money in it before their turn.
        """
        if not self.round.raises:
            return 0
        return max(0, calls_before - self.round.raises[-1][1])

    def _bet_level_faced(self, word: str, raises_before: int, facing: bool) -> int:
        if not facing:
            return 0
        # Preflop the big blind is the first bet, so the k-th raise faces level
        # k + 1; postflop each aggressive action is a bet of its own.
        return raises_before + (1 if self.round.street == 0 else 0)

    def _board(self, street: int) -> tuple[str, ...]:
        """The community cards visible at a decision, cumulated street by street."""
        if not self.boards:
            return ()
        return self.boards[min(max(street, 0), len(self.boards) - 1)]

    def _street_name(self, street: int) -> str:
        if 0 <= street < len(self.street_names):
            return self.street_names[street]
        return f"street{street}"

    def _stack_bucket(self, effective_bb: int) -> str:
        if effective_bb < SHORT_STACK_BB:
            return "short"
        if effective_bb < MEDIUM_STACK_BB:
            return "medium"
        if effective_bb < DEEP_STACK_BB:
            return "deep"
        return "very_deep"

    def _role(self, word: str, facing: bool) -> str:
        if RESPONSES.get(word) in AGGRESSIVE_RESPONSES:
            return "aggressor"
        if facing:
            return "defender"
        return "passive"

    # -- the walk ----------------------------------------------------------

    def run(self) -> list[PlayerSituation]:
        for index, row in enumerate(self.rows):
            word = _word(row)
            if word is None:
                continue
            street = _round_street(row.get("street"))
            self._advance_street(street)
            if word in DECISION_ACTIONS:
                self.situations.append(self._situation(row, word, index, street))
            self._record(row, word)
        self._finish_round()
        return self.situations

    def _situation(self, row: dict[str, Any], word: str, index: int, street: int) -> PlayerSituation:
        player = str(row.get("player") or "")
        to_call = int(self._fact_value(row, "toCall", 0) or 0)
        pot_before = int(self._fact_value(row, "potBefore", 0) or 0)
        raises_before = int(self._fact_value(row, "raiserCount", 0) or 0)
        facing = self._facing_player(word, to_call)
        facing_position = _position_of(self.handsplayers, facing) if facing else None
        position = _position_code(row.get("position"))
        calls_before = int(self._fact_value(row, "callerCount", 0) or 0)
        aggressor_position = _position_of(self.handsplayers, self.chain_aggressor)
        effective_bb = int(self._fact_value(row, "effectiveStackBB", 0) or 0)
        pot_odds = to_call * 10000 // (pot_before + to_call) if to_call > 0 else 0
        situation = PlayerSituation(
            hand_id=int(getattr(self.hand, "handid", 0) or 0),
            action_no=int(row.get("actionNo") or index + 1),
            street=street,
            street_name=self._street_name(street),
            player=player,
            site=str(getattr(self.hand, "sitename", "") or ""),
            game=str(self.gametype.get("category") or ""),
            limit_type=str(self.gametype.get("limitType") or ""),
            is_tournament=str(self.gametype.get("type") or "") == "tour",
            table_size=int(getattr(self.hand, "maxseats", None) or len(self.handsplayers)),
            players_dealt=len(self.handsplayers),
            small_blind=_cents(self.gametype.get("sb")),
            big_blind=_cents(self.gametype.get("bb")),
            currency=str(self.gametype.get("currency") or ""),
            position=position,
            relative_position=int(self._fact_value(row, "relativePosition", 0) or 0),
            in_position=bool(self._fact_value(row, "inPosition", False)),
            effective_stack=int(self._fact_value(row, "effectiveStack", 0) or 0),
            effective_stack_bb=effective_bb,
            stack_bucket=self._stack_bucket(effective_bb),
            spr_before=int(self._fact_value(row, "sprBefore", 0) or 0),
            is_hero=player == self.hero,
            pot_type=self._pot_type(),
            multiway=int(self._fact_value(row, "playersInHand", 0) or 0) >= 3,
            players_in_hand=int(self._fact_value(row, "playersInHand", 0) or 0),
            preflop_aggressor=self.round.last_aggressor if street == 0 else self.preflop_aggressor,
            is_preflop_aggressor=player == (self.round.last_aggressor if street == 0 else self.preflop_aggressor),
            street_aggressor=self.round.last_aggressor,
            is_aggressor=player == self.round.last_aggressor,
            first_aggressor=self.round.first_aggressor,
            previous_aggressor=self.chain_aggressor,
            is_previous_aggressor=player == self.chain_aggressor,
            previous_aggressor_led=self._previous_aggressor_led(),
            previous_aggressor_checked=self._previous_aggressor_checked(),
            previous_aggressor_position=aggressor_position,
            in_position_vs_previous_aggressor=_in_position_vs(position, aggressor_position),
            aggressor_checked_this_street=self._aggressor_checked_this_street(),
            previous_raiser=self._previous_raiser(),
            is_previous_raiser=player == self._previous_raiser(),
            to_call=to_call,
            pot_before=pot_before,
            pot_after=int(self._fact_value(row, "potAfter", 0) or 0),
            pot_odds_bp=pot_odds,
            facing_action=row.get("facingActionType") if facing else None,
            facing_player=facing,
            facing_position=facing_position,
            in_position_vs_facing=_in_position_vs(position, facing_position),
            facing_amount=int(self._fact_value(row, "facingAmount", 0) or 0),
            facing_sizing_bp=int(self._fact_value(row, "facingSizingBp", 0) or 0),
            facing_all_in=self._facing_all_in() if facing else False,
            bet_level_faced=self._bet_level_faced(word, raises_before, bool(facing)),
            raises_before=raises_before,
            calls_before=calls_before,
            callers_between_raises=self._callers_between_raises(),
            callers_since_raise=self._callers_since_raise(calls_before),
            street_actions=tuple(self.round.actions),
            previous_street_actions=self.previous_street_actions.get(player, ()),
            board=self._board(street),
            response=RESPONSES[word],
            is_all_in=bool(row.get("allIn")),
            role=self._role(word, bool(facing)),
        )
        return classify(situation)


def _word(row: dict[str, Any]) -> str | None:
    """The action word of an event row, or None when the row has no context."""
    word = row.get("actionType")
    return str(word) if isinstance(word, str) and word else None


def _round_street(street: Any) -> int:
    """Situation street: the blinds are part of preflop, not a round of their own."""
    try:
        value = int(street)
    except (TypeError, ValueError):
        return 0
    return max(0, value)


def _action_streets(hand: Any) -> list[str]:
    streets = getattr(hand, "actionStreets", None)
    if streets is None or isinstance(streets, str):
        return []
    try:
        return [str(street) for street in streets]
    except TypeError:
        return []


def _street_names(hand: Any) -> tuple[str, ...]:
    """One name per situation street, from the hand's own rounds.

    Hold'em and Omaha name their rounds the way the rest of this module does;
    stud, razz and the draw games have third/fourth/fifth streets and draw
    rounds of their own, and calling those "flop" and "turn" would be a lie.
    """
    names = []
    for street in _action_streets(hand)[1:]:
        names.append("preflop" if street in FIRST_ACTION_STREETS else street.lower())
    return tuple(names) or STREET_NAMES


def _boards(hand: Any, board: dict[str, Any]) -> list[tuple[str, ...]]:
    """The cards visible entering each street, cumulated from the hand's rounds."""
    cards: tuple[str, ...] = ()
    cumulative = []
    for street in _action_streets(hand)[1:]:
        cards = cards + tuple(board.get(street) or ())
        cumulative.append(cards)
    return cumulative


def _cents(amount: Any) -> int:
    try:
        return int(100 * Decimal(str(amount)))
    except (TypeError, ValueError, ArithmeticError):
        return 0


def _position_code(value: Any) -> int | None:
    """Seat code as ``action_events`` stores it: 0 = button, -1 = SB, -2 = BB."""
    if value == "S":
        return -1
    if value == "B":
        return -2
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _position_of(handsplayers: dict[str, dict[str, Any]], player: str | None) -> int | None:
    if player is None:
        return None
    return _position_code(handsplayers.get(player, {}).get("position"))


def _in_position_vs(position: int | None, other: int | None) -> bool | None:
    """Whether the player's seat acts after the other player's, on every street.

    A lower code is closer to the button, i.e. later to act; the blinds rank
    behind every numbered seat. Unknown seats give None rather than a guess.
    """
    if position is None or other is None:
        return None
    return position < other


def _round_state(street: int) -> _RoundState:
    return _RoundState(
        street=street,
        actions=[],
        first_aggressor=None,
        last_aggressor=None,
        last_aggression_all_in=False,
        raises=[],
        player_actions={},
    )


def _final_pot_type(round_state: _RoundState) -> str:
    """The shape a finished round ended in, for the streets that follow it."""
    raises = len([True for _player, action in round_state.actions if action in ("raises", "completes")])
    calls = len([True for _player, action in round_state.actions if action == "calls"])
    if raises == 0:
        return POT_LIMPED if calls else POT_UNOPENED
    if raises == 1:
        return POT_SINGLE_RAISED
    if raises == 2:
        return POT_THREE_BET
    return POT_FOUR_BET_PLUS


def enumerate_situations(
    hand: Any,
    handsplayers: dict[str, dict[str, Any]] | None = None,
    handsactions: dict[Any, dict[str, Any]] | Sequence[dict[str, Any]] | None = None,
) -> tuple[PlayerSituation, ...]:
    """Every decision of one hand, as a named situation.

    Reads the normalized event rows of ``HandsActions`` (issue #293) and the
    per-player context of ``assembleHandsPlayers``; both default to what the
    hand's own ``DerivedStats`` holds, so a caller that has just assembled a
    hand needs to pass nothing. Rows without event context (a database written
    before #293) yield no situations rather than a guess.
    """
    stats = getattr(hand, "stats", None)
    if handsplayers is None:
        handsplayers = stats.getHandsPlayers() if stats is not None else {}
    if handsactions is None:
        handsactions = stats.getHandsActions() if stats is not None else {}
    rows = _ordered_rows(handsactions)
    if not rows or not handsplayers:
        return ()
    return tuple(_SituationWalk(hand, handsplayers, rows).run())


def _ordered_rows(handsactions: Any) -> list[dict[str, Any]]:
    """The event rows in action order, whichever shape the caller holds."""
    if isinstance(handsactions, dict):
        items: Iterable[Any] = sorted(handsactions.items(), key=lambda item: _sort_key(item[0]))
        rows = [row for _key, row in items if isinstance(row, dict)]
    elif isinstance(handsactions, Sequence):
        rows = [row for row in handsactions if isinstance(row, dict)]
    else:
        return []
    if rows and "actionNo" not in rows[0]:
        rows = [dict(row, actionNo=index + 1) for index, row in enumerate(rows)]
    return rows


def _sort_key(key: Any) -> tuple[int, str]:
    try:
        return (0, f"{int(key):020d}")
    except (TypeError, ValueError):
        return (1, str(key))


def situations_for(
    situations: Iterable[PlayerSituation],
    player: str,
    label: str | None = None,
) -> list[PlayerSituation]:
    """One player's situations, optionally only those carrying a given label."""
    return [
        situation
        for situation in situations
        if situation.player == player and (label is None or situation.has_label(label))
    ]


def situations_by_player(
    situations: Iterable[PlayerSituation],
) -> dict[str, list[PlayerSituation]]:
    grouped: dict[str, list[PlayerSituation]] = {}
    for situation in situations:
        grouped.setdefault(situation.player, []).append(situation)
    return grouped


def situations_by_label(
    situations: Iterable[PlayerSituation],
) -> dict[str, list[PlayerSituation]]:
    grouped: dict[str, list[PlayerSituation]] = {}
    for situation in situations:
        for label in situation.labels:
            grouped.setdefault(label, []).append(situation)
    return grouped


def enum_responses(
    situations: Iterable[PlayerSituation],
) -> dict[str, dict[str, str]]:
    """Project the situations onto the PT4 ``enum_*_action`` columns.

    One char per column per player: F, C or R for the first answer they gave in
    that spot, and no entry at all when the spot never arose -- which is exactly
    what ``DerivedStats.calcActionEnums`` fills, so the two can be compared
    hand by hand (see the equivalence test) and a calculator can move onto this
    projection without changing what the HUD reads.
    """
    responses: dict[str, dict[str, str]] = {}
    for situation in situations:
        if not situation.enum_answers:
            continue
        player_responses = responses.setdefault(situation.player, {})
        for key, answer in situation.enum_answers:
            player_responses.setdefault(key, answer)
    return responses


def enum_fold_street(situations: Iterable[PlayerSituation]) -> dict[str, str]:
    """The ``enum_folded`` column: the street letter a player folded on."""
    letters = {0: "P", 1: "F", 2: "T", 3: "R"}
    folded: dict[str, str] = {}
    for situation in situations:
        if situation.response == "fold":
            folded.setdefault(situation.player, letters[situation.street])
    return folded
