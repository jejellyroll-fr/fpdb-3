"""User-facing vocabulary for the research browser (issue #329).

The query engine speaks its own names: ``primary_situation``, ``facing_sizing_bp``,
``effective_stack_bb``. Those names are load-bearing -- they are what a preset
stores, what a saved query round-trips, what the CLI accepts -- and the epic is
explicit that the engine stays their source of truth. What was missing is a
*translation layer* between them and the words a poker player uses, so the
browser can offer "Situation" instead of ``primary_situation`` and a dropdown of
the spots the situation model actually knows instead of a text box.

This module is that layer, and it is deliberately Qt free:

* **Labels, descriptions and units** for every filter, dimension and metric the
  engine declares. The engine's own column name is never the user-facing
  description -- ``description`` stays available for the expert view.
* **Choices** for the domains that are closed: positions, streets, pot types,
  board structure, made hands, draws, sizing buckets, situation labels. They are
  derived from the modules that *define* those vocabularies
  (``player_situations``, ``board_features``, ``hand_state``, ``hud_situation``,
  ``sizing_buckets``), so a choice list cannot drift from what the classifier
  writes -- there is exactly one place per vocabulary.
* **``describe_query``**: the active question in plain poker language, built
  from the same labels the controls use. It is presentation, not semantics: it
  never filters anything, and an unknown filter still gets an honest clause
  rather than being dropped.

Nothing here writes SQL, and nothing here validates: a caller still compiles
through ``analytics_query`` with the engine's vocabulary. The labels only decide
what the user reads.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from . import player_situations as situations
from .analytics_query import POSITION_CODES
from .board_features import (
    CONNECTIVITIES,
    PAIRINGS,
    RANK_BUCKETS,
    RUNOUT_FLAGS,
    SUIT_STRUCTURES,
    TEXTURE_FLAGS,
)
from .hand_state import (
    BLOCKER_CATEGORIES,
    DRAW_CATEGORIES,
    MADE_HANDS,
    NUTNESS_LEVELS,
    PAIR_DETAILS,
)
from .hud_situation import POT_TYPES, STREETS
from .i18n import N_
from .sizing_buckets import DEFAULT_BUCKETS
from .spr_buckets import SPR_BUCKET_LABELS, SPR_BUCKETS


@dataclass(frozen=True)
class Choice:
    """One selectable value of a closed domain: the engine token and its label.

    ``value`` is what the query stores and compiles; ``label`` is what the user
    reads. Keeping both on one object is what lets a selector send engine
    vocabulary while showing poker language, and what lets ``describe_query``
    render a value the same way the control does.
    """

    value: str
    label: str


def _choices(*pairs: tuple[str, str]) -> tuple[Choice, ...]:
    return tuple(Choice(value, N_(label)) for value, label in pairs)


# ---------------------------------------------------------------------------
# Filter metadata: what a control shows, per engine filter name.
# ---------------------------------------------------------------------------

# The label a *beginner* control displays. Every engine filter is listed here:
# a filter with no label would fall back to its internal name, which is exactly
# what this issue exists to stop.
FILTER_LABELS: Final[dict[str, str]] = {
    # -- game ---------------------------------------------------------------
    "site": N_("Poker room"),
    "game": N_("Game"),
    "limit": N_("Limit"),
    "currency": N_("Currency"),
    "tournament": N_("Tournament or cash"),
    "tournament_id": N_("Tournament"),
    "big_blind": N_("Big blind (chips)"),
    "stake_bb": N_("Stake (big blinds)"),
    "seats": N_("Seats dealt in"),
    "max_seats": N_("Table size"),
    "session": N_("Session"),
    "hand_id": N_("Hand"),
    "hand_id_from": N_("Hands after"),
    "hand_id_to": N_("Hands before"),
    "date_from": N_("Played since"),
    "date_to": N_("Played until"),
    # -- who ----------------------------------------------------------------
    "player": N_("Player"),
    "players": N_("Players"),
    "identity": N_("Linked player identity"),
    "hero": N_("Hero"),
    # -- seat / stack -------------------------------------------------------
    "position": N_("Position"),
    "opponent_position": N_("Opponent position"),
    "relative_position": N_("Relative position"),
    "in_position": N_("In position"),
    "effective_stack_bb": N_("Effective stack (BB)"),
    "effective_stack": N_("Effective stack (chips)"),
    "stack_bucket": N_("Stack depth"),
    "spr": N_("SPR"),
    "spr_bucket": N_("SPR band"),
    "players_in_hand": N_("Players in the hand"),
    "multiway": N_("Multiway"),
    # -- street / pot -------------------------------------------------------
    "street": N_("Street"),
    "street_index": N_("Street number"),
    "pot_type": N_("Pot type"),
    "pot_before": N_("Pot before the action"),
    "to_call": N_("Amount to call"),
    "pot_odds_bp": N_("Pot odds"),
    "role": N_("Role"),
    "is_aggressor": N_("Is the aggressor"),
    "is_preflop_aggressor": N_("Is the preflop aggressor"),
    "is_previous_aggressor": N_("Was the previous aggressor"),
    "in_position_vs_previous_aggressor": N_("In position versus the previous aggressor"),
    "in_position_vs_facing": N_("In position versus the bettor"),
    "facing_all_in": N_("Facing an all-in"),
    # -- action -------------------------------------------------------------
    "action_taken": N_("Action taken"),
    "action_faced": N_("Action faced"),
    "response": N_("Response"),
    "all_in": N_("All-in"),
    "situation": N_("Situation, including the ones it led to"),
    "primary_situation": N_("Situation"),
    "situation_group": N_("Situation family"),
    "enum_key": N_("Legacy stat column"),
    "enum_response": N_("Legacy stat response"),
    "raisers_before": N_("Raises before"),
    # -- cards --------------------------------------------------------------
    "starting_hand": N_("Starting hand"),
    "hole_cards_known": N_("Hole cards known"),
    # -- sizing -------------------------------------------------------------
    "sizing_bp": N_("Bet size (basis points)"),
    "facing_sizing_bp": N_("Bet size faced (basis points)"),
    "bet_sizing_pct": N_("Bet size (% of pot)"),
    "facing_sizing_pct": N_("Bet size faced (% of pot)"),
    "sizing_bucket": N_("Bet size bucket"),
    "facing_sizing_bucket": N_("Bet size faced bucket"),
    # -- board --------------------------------------------------------------
    "board_rank": N_("Board high card"),
    "board_suit": N_("Board suit structure"),
    "board_pairing": N_("Board pairing"),
    "board_connectivity": N_("Board connectivity"),
    "board_present": N_("Board dealt"),
    "board_texture": N_("Board texture"),
    "board_texture_all": N_("Board texture (all of)"),
    "board_runout": N_("Runout"),
    "board_street": N_("Board street"),
    # -- hand strength ------------------------------------------------------
    "made_hand": N_("Made hand"),
    "made_hand_rank": N_("Made hand rank"),
    "pair_detail": N_("Pair detail"),
    "nutness": N_("Hand strength"),
    "nutness_beats": N_("Beats how much of the range"),
    "nutness_holdings": N_("Range holdings"),
    "draw": N_("Draw (any of)"),
    "draw_all": N_("Draw (all of)"),
    "draw_none": N_("Draw (none of)"),
    "blocker": N_("Blocker (any of)"),
    "blocker_all": N_("Blocker (all of)"),
    "blocker_none": N_("Blocker (none of)"),
    "hand_state_street": N_("Hand-classified street"),
    "hand_state_known": N_("Hand state known"),
}

# The sentence a control's tooltip and the summary use. These describe the
# *question*, not the schema: no column names, no table names.
FILTER_DESCRIPTIONS: Final[dict[str, str]] = {
    "site": N_("Which poker room the hands were played on."),
    "game": N_("The game variant, such as Hold'em or Omaha."),
    "limit": N_("Fixed limit, no limit and the other betting structures."),
    "currency": N_("The currency the game was played in."),
    "tournament": N_("Yes for tournament hands, No for cash game hands."),
    "tournament_id": N_("One specific tournament."),
    "big_blind": N_("The big blind in chips, for mixed stakes."),
    "stake_bb": N_("The size of the game, expressed in big blinds."),
    "seats": N_("How many players were dealt into the hand."),
    "max_seats": N_("The table size, such as 6-max or full ring."),
    "session": N_("One import session."),
    "hand_id": N_("One specific hand."),
    "hand_id_from": N_("Only hands imported after this hand id."),
    "hand_id_to": N_("Only hands imported before this hand id."),
    "date_from": N_("Only decisions played on or after this date."),
    "date_to": N_("Only decisions played on or before this date."),
    "player": N_("Restrict the population to one player."),
    "players": N_("Restrict the population to a set of players."),
    "identity": N_("Restrict to a linked (site, alias) identity."),
    "hero": N_("Hero's own decisions, or everyone except hero. Any keeps both."),
    "position": N_("The seat of the player who acted."),
    "opponent_position": N_("The seat of the player the action was against."),
    "relative_position": N_("Seats between the actor and the button."),
    "in_position": N_("Whether the actor was in position."),
    "effective_stack_bb": N_("The smaller of the two stacks, in big blinds."),
    "effective_stack": N_("The smaller of the two stacks, in chips."),
    "stack_bucket": N_("Short, medium, deep or very deep stacks."),
    "spr": N_("Stack-to-pot ratio before the action."),
    "spr_bucket": N_("The same ratio as the bands a player thinks in."),
    "players_in_hand": N_("How many players were still in the hand."),
    "multiway": N_("Three or more players saw the decision."),
    "street": N_("Preflop, flop, turn or river."),
    "street_index": N_("The street as a number, preflop being zero."),
    "pot_type": N_("The shape of the pot: unopened, limped, single-raised, 3-bet, 4-bet."),
    "pot_before": N_("The pot size before the action, in chips."),
    "to_call": N_("How much the actor had to call."),
    "pot_odds_bp": N_("The pot odds offered, in basis points."),
    "role": N_("Aggressor, defender or passive."),
    "is_aggressor": N_("Whether the actor was the aggressor on this street."),
    "is_preflop_aggressor": N_("Whether the actor raised preflop."),
    "is_previous_aggressor": N_("Whether the actor was the aggressor on the previous street."),
    "in_position_vs_previous_aggressor": N_("Whether the actor has position on the previous aggressor."),
    "in_position_vs_facing": N_("Whether the actor has position on the bettor."),
    "facing_all_in": N_("Whether the action in front of the actor was an all-in."),
    "action_taken": N_("What the actor did: folded, checked, called, bet or raised."),
    "action_faced": N_("What the actor was facing."),
    "response": N_("The decision, normalized: fold, check, call, bet or raise."),
    "all_in": N_("Whether the action put the player all-in."),
    "situation": N_(
        "Every situation the decision matched, not only the most specific one. "
        "Use this to ask how often an opportunity was taken: raising an open makes "
        "the decision a 3-bet, so only this keeps it among the opens faced.",
    ),
    "primary_situation": N_("The most specific situation the decision matched."),
    "situation_group": N_("A family of situations, such as postflop defence."),
    "enum_key": N_("A legacy PT4 stat column the decision feeds."),
    "enum_response": N_("The letter a legacy PT4 stat column records."),
    "raisers_before": N_("How many raises came before this decision."),
    "starting_hand": N_("The 169 Hold'em starting-hand classes."),
    "hole_cards_known": N_("Yes only for decisions whose cards were shown."),
    "sizing_bp": N_("The size of the bet made, in basis points of the pot."),
    "facing_sizing_bp": N_("The size of the bet faced, in basis points of the pot."),
    "bet_sizing_pct": N_("The size of the bet made, as a percentage of the pot."),
    "facing_sizing_pct": N_("The size of the bet faced, as a percentage of the pot."),
    "sizing_bucket": N_("The bet size made, in the configured sizing buckets."),
    "facing_sizing_bucket": N_("The bet size faced, in the configured sizing buckets."),
    "board_rank": N_("The highest card of the board."),
    "board_suit": N_("Rainbow, two-tone, monotone and the deeper flush boards."),
    "board_pairing": N_("Whether the board is unpaired, paired, or more."),
    "board_connectivity": N_("Whether the board is connected, semi-connected or disconnected."),
    "board_present": N_("Yes on the flop and later, No before the flop."),
    "board_texture": N_("Named texture flags such as monotone or connected (any of them)."),
    "board_texture_all": N_("Board texture flags the board must have all of."),
    "board_runout": N_("What the turn or river card changed."),
    "board_street": N_("The board street as a number, the flop being one."),
    "made_hand": N_("The made hand the actor held: pairs, sets, straights and so on."),
    "made_hand_rank": N_("The strength of the made hand, as a number."),
    "pair_detail": N_("Which pair the actor held: overpair, top pair, set and so on."),
    "nutness": N_("How strong the holding is: nuts, near nuts, strong, medium or weak."),
    "nutness_beats": N_("The share of the range the holding beats."),
    "nutness_holdings": N_("How many holdings the holding beats."),
    "draw": N_("Draws the actor had: flush draws, gutshots and the rest (any of them)."),
    "draw_all": N_("Draws the actor must have all of."),
    "draw_none": N_("Only decisions with none of the named draws."),
    "blocker": N_("Blockers the actor held (any of them)."),
    "blocker_all": N_("Blockers the actor must have all of."),
    "blocker_none": N_("Only decisions with none of the named blockers."),
    "hand_state_street": N_("The street the hand state was classified on."),
    "hand_state_known": N_("Yes only where the cards were known and classified."),
}

# The unit a numeric control labels its fields with. Empty when the value is a
# name, a token or a date.
FILTER_UNITS: Final[dict[str, str]] = {
    "big_blind": N_("chips"),
    "stake_bb": N_("BB"),
    "effective_stack": N_("chips"),
    "effective_stack_bb": N_("BB"),
    "spr": N_("SPR"),
    "pot_before": N_("chips"),
    "to_call": N_("chips"),
    "pot_odds_bp": N_("bp"),
    "sizing_bp": N_("bp"),
    "facing_sizing_bp": N_("bp"),
    "bet_sizing_pct": N_("% of pot"),
    "facing_sizing_pct": N_("% of pot"),
    "nutness_beats": N_("holdings"),
    "nutness_holdings": N_("holdings"),
    "relative_position": N_("seats"),
    "hand_id": N_("id"),
    "street_index": N_("street"),
    "board_street": N_("street"),
}

# The filters whose value is only meaningful to someone who already knows the
# engine. They stay available in Expert mode and are not offered in Beginner
# mode's picker -- never removed, never renamed.
EXPERT_ONLY_FILTERS: Final[frozenset[str]] = frozenset(
    {
        "hand_id",
        "hand_id_from",
        "hand_id_to",
        "session",
        "tournament_id",
        "enum_key",
        "enum_response",
        # "situation" is deliberately NOT here. It is the only way to ask about
        # an *opportunity*: primary_situation is the most specific label a
        # decision matched, so raising against an open relabels the decision
        # three_bet and takes it out of facing_open. A beginner asking "how
        # often do I 3-bet" needs this column, and hiding it is what made a
        # third of the shipped presets answer 0% (#355).
        "street_index",
        "board_street",
        "hand_state_street",
        "sizing_bp",
        "facing_sizing_bp",
        "effective_stack",
        "big_blind",
        "relative_position",
        "players",
        "identity",
        "board_texture_all",
        "made_hand_rank",
        "nutness_beats",
        "nutness_holdings",
        "draw_all",
        "draw_none",
        "blocker_all",
        "blocker_none",
    },
)

# A worked example per filter, for the tooltip and for tests: an untouched
# control with no example is a control a user cannot fill in.
FILTER_EXAMPLES: Final[dict[str, str]] = {
    "max_seats": "6",
    "stake_bb": "100",
    "effective_stack_bb": "80-120",
    "position": "BTN",
    "opponent_position": "BB",
    "street": "flop",
    "pot_type": "single_raised",
    "primary_situation": "facing_cbet",
    "facing_sizing_pct": "66-100",
    "sizing_bucket": "66-80",
    "board_suit": "two-tone",
    "made_hand": "one_pair",
    "player": "VillainOne",
}


#: The seat a button-relative code names. ``_position_choices`` renders the
#: filter from this too, so a code cannot be labelled one way in a picker and
#: another in a result row.
_POSITION_CODE_LABELS: Final[dict[str, str]] = {
    "0": "BTN",
    "1": "CO",
    "2": "HJ",
    "3": "LJ",
    "4": "MP",
    "5": "MP2",
    "6": "UTG",
    "-1": "SB",
    "-2": "BB",
}


def _position_choices() -> tuple[Choice, ...]:
    """The button-relative seats, one entry per code, in table order.

    ``POSITION_CODES`` is an aliases table (``btn``, ``bu``, ``button`` and ``d``
    all mean the button), so the choices are built from it rather than copied:
    the selector offers one label per *seat* and sends the canonical token.
    """
    preferred = ("btn", "co", "hj", "lj", "mp", "mp2", "utg", "sb", "bb")
    seen: dict[int, str] = {}
    labels = {int(code): label for code, label in _POSITION_CODE_LABELS.items()}
    for name in preferred:
        code = POSITION_CODES[name]
        seen.setdefault(code, name)
    return tuple(
        Choice(token, N_(labels[code]))
        for code, token in sorted(seen.items(), key=lambda item: (-item[0], item[1]))
    )


def _stack_bucket_choices() -> tuple[Choice, ...]:
    """The effective-stack bands ``player_situations._stack_bucket`` writes."""
    return _choices(
        ("short", "Short (< 20 BB)"),
        ("medium", "Medium (20-50 BB)"),
        ("deep", "Deep (50-100 BB)"),
        ("very_deep", "Very deep (100 BB+)"),
    )


def _spr_bucket_choices() -> tuple[Choice, ...]:
    """The SPR bands, named from the module that also writes their SQL."""
    return tuple(Choice(name, N_(SPR_BUCKET_LABELS[name])) for name in SPR_BUCKETS)


def _situation_group_choices() -> tuple[Choice, ...]:
    """The situation families of the rule table, in table order."""
    labels = {
        "POT_OPEN": "Opening the pot",
        "POT_LIMPED": "Limped pots",
        "PREFLOP_SQUEEZE": "Squeeze",
        "PREFLOP_DEFENCE": "Preflop defence",
        "POSTFLOP_AGGRESSION": "Postflop aggression",
        "POSTFLOP_DEFENCE": "Postflop defence",
        "ALL_IN": "All-in",
        "RESPONSE": "Passive response",
        "STRUCTURE": "Pot structure",
    }
    order: list[str] = []
    for rule in situations.SITUATION_RULES:
        if rule.group not in order:
            order.append(rule.group)
    return tuple(Choice(group, N_(labels.get(group, group))) for group in order)


def _situation_choices() -> tuple[Choice, ...]:
    """Every named situation, labelled with the rule table's own description.

    A ``primary_situation`` value *is* a rule name, and the rule table already
    carries the sentence a human reads (``"facing a continuation bet"``), so the
    selector and the summary share one source instead of a second glossary.
    """
    return tuple(Choice(rule.name, N_(rule.label)) for rule in situations.SITUATION_RULES)


def _response_choices() -> tuple[Choice, ...]:
    """The normalized responses, from the words the situation model normalizes."""
    order = ("fold", "check", "call", "bet", "raise")
    labels = {"fold": "Fold", "check": "Check", "call": "Call", "bet": "Bet", "raise": "Raise"}
    present = set(situations.RESPONSES.values())
    return tuple(Choice(word, N_(labels[word])) for word in order if word in present)


def _action_choices() -> tuple[Choice, ...]:
    """The raw action words the event rows store (parser spelling)."""
    return tuple(
        Choice(word, N_(word))
        for word in ("folds", "checks", "calls", "bets", "raises", "completes")
    )


def _bucket_choices() -> tuple[Choice, ...]:
    """The configured sizing buckets, read from the sizing module itself."""
    return tuple(Choice(label, N_(label)) for label in DEFAULT_BUCKETS.labels)


def _flag_choices(flags: tuple[tuple[str, int], ...]) -> tuple[Choice, ...]:
    return tuple(Choice(name, N_(name.replace("_", " "))) for name, _bit in flags)


# The closed domains a beginner selector offers. A filter missing from this
# table is free text -- ``player`` really is open-ended -- and the engine still
# validates whatever is typed.
FILTER_CHOICES: Final[dict[str, tuple[Choice, ...]]] = {
    "position": _position_choices(),
    "opponent_position": _position_choices(),
    "street": tuple(Choice(name, N_(name)) for name in STREETS),
    "board_street": tuple(Choice(name, N_(name)) for name in STREETS),
    "hand_state_street": tuple(Choice(name, N_(name)) for name in STREETS),
    "pot_type": _choices(
        *[
            (name, name.replace("_", "-") + " pots")
            for name in POT_TYPES
        ],
    ),
    "role": _choices(("aggressor", "Aggressor"), ("defender", "Defender"), ("passive", "Passive")),
    "response": _response_choices(),
    "action_taken": _action_choices(),
    "action_faced": _action_choices(),
    "stack_bucket": _stack_bucket_choices(),
    "situation_group": _situation_group_choices(),
    "primary_situation": _situation_choices(),
    "situation": _situation_choices(),
    "starting_hand": (),  # 169 classes: the range grid is the picker, not a combo.
    "board_rank": tuple(Choice(name, N_(name.replace("-", " "))) for name in RANK_BUCKETS),
    "board_suit": tuple(Choice(name, N_(name.replace("-", " "))) for name in SUIT_STRUCTURES),
    "board_pairing": tuple(Choice(name, N_(name.replace("-", " "))) for name in PAIRINGS),
    "board_connectivity": tuple(Choice(name, N_(name.replace("-", " "))) for name in CONNECTIVITIES),
    "board_texture": _flag_choices(TEXTURE_FLAGS),
    "board_texture_all": _flag_choices(TEXTURE_FLAGS),
    "board_runout": _flag_choices(RUNOUT_FLAGS),
    "made_hand": tuple(Choice(name, N_(name.replace("_", " "))) for name in MADE_HANDS),
    "pair_detail": tuple(Choice(name, N_(name.replace("_", " "))) for name in PAIR_DETAILS),
    "nutness": tuple(Choice(name, N_(name.replace("_", " "))) for name in NUTNESS_LEVELS),
    "draw": tuple(Choice(name, N_(name.replace("_", " "))) for name in DRAW_CATEGORIES),
    "draw_all": tuple(Choice(name, N_(name.replace("_", " "))) for name in DRAW_CATEGORIES),
    "draw_none": tuple(Choice(name, N_(name.replace("_", " "))) for name in DRAW_CATEGORIES),
    "blocker": tuple(Choice(name, N_(name.replace("_", " "))) for name in BLOCKER_CATEGORIES),
    "blocker_all": tuple(Choice(name, N_(name.replace("_", " "))) for name in BLOCKER_CATEGORIES),
    "blocker_none": tuple(Choice(name, N_(name.replace("_", " "))) for name in BLOCKER_CATEGORIES),
    "sizing_bucket": _bucket_choices(),
    "facing_sizing_bucket": _bucket_choices(),
    "spr_bucket": _spr_bucket_choices(),
}

# The human name of each engine filter group (``research_browser.FILTER_GROUPS``).
FILTER_GROUP_LABELS: Final[dict[str, str]] = {
    "game": N_("Game and stake"),
    "who": N_("Players"),
    "seat": N_("Position and stack"),
    "street": N_("Street and pot"),
    "action": N_("Action"),
    "cards": N_("Hole cards"),
    "sizing": N_("Bet sizing"),
    "board": N_("Board"),
    "strength": N_("Hand strength"),
    "other": N_("Other"),
}


def filter_label(name: str) -> str:
    """The user-facing label of one engine filter (its name if unlabelled)."""
    return FILTER_LABELS.get(name, name)


def filter_description(name: str) -> str:
    """What the filter asks, in poker language (empty when undescribed)."""
    return FILTER_DESCRIPTIONS.get(name, "")


def filter_unit(name: str) -> str:
    """The unit a numeric control labels itself with (may be empty)."""
    return FILTER_UNITS.get(name, "")


def filter_choices(name: str) -> tuple[Choice, ...]:
    """The closed domain of a filter, or ``()`` when it is open-ended."""
    return FILTER_CHOICES.get(name, ())


def filter_example(name: str) -> str:
    """A worked example value, for a placeholder or a tooltip."""
    return FILTER_EXAMPLES.get(name, "")


def is_expert_only(name: str) -> bool:
    """Whether Beginner mode's picker hides this filter."""
    return name in EXPERT_ONLY_FILTERS


# ---------------------------------------------------------------------------
# Dimensions: the breakdown picker.
# ---------------------------------------------------------------------------

DIMENSION_LABELS: Final[dict[str, str]] = {
    "street": N_("Street"),
    "position": N_("Position"),
    "opponent_position": N_("Opponent position"),
    "relative_position": N_("Relative position"),
    "in_position": N_("In position"),
    "stack_bucket": N_("Stack depth"),
    "effective_stack_bb": N_("Effective stack"),
    "spr": N_("SPR"),
    "spr_bucket": N_("SPR band"),
    "pot_type": N_("Pot type"),
    "role": N_("Role"),
    "response": N_("Response"),
    "action_taken": N_("Action taken"),
    "action_faced": N_("Action faced"),
    "all_in": N_("All-in"),
    "multiway": N_("Multiway"),
    "player": N_("Player"),
    "site": N_("Poker room"),
    "game": N_("Game"),
    "limit": N_("Limit"),
    "tournament": N_("Tournament"),
    "session": N_("Session"),
    "sizing_bucket": N_("Bet size"),
    "facing_sizing_bucket": N_("Bet size faced"),
    "board_rank": N_("Board high card"),
    "board_suit": N_("Board suit structure"),
    "board_pairing": N_("Board pairing"),
    "board_connectivity": N_("Board connectivity"),
    "primary_situation": N_("Situation"),
    "enum_key": N_("Legacy stat column"),
    "starting_hand_id": N_("Starting hand"),
    "made_hand": N_("Made hand"),
    "made_hand_rank": N_("Made hand rank"),
    "pair_detail": N_("Pair detail"),
    "nutness": N_("Hand strength"),
    "hand_state_street": N_("Hand-classified street"),
}

# The dimensions a beginner breakdown picker offers, in a sensible order.
# Grouping by a raw player id or a session is an expert move.
BEGINNER_DIMENSIONS: Final[tuple[str, ...]] = (
    "street",
    "position",
    "opponent_position",
    "pot_type",
    "response",
    "sizing_bucket",
    "facing_sizing_bucket",
    "board_suit",
    "board_pairing",
    "board_connectivity",
    "made_hand",
    "pair_detail",
    "nutness",
    "stack_bucket",
    "effective_stack_bb",
    "spr_bucket",
    "in_position",
    "multiway",
    "all_in",
    "primary_situation",
    "player",
)

DIMENSION_CHOICES: Final[dict[str, tuple[Choice, ...]]] = {
    "street": tuple(Choice(name, N_(name)) for name in STREETS),
    "board_street": tuple(Choice(name, N_(name)) for name in STREETS),
    "hand_state_street": tuple(Choice(name, N_(name)) for name in STREETS),
    "sizing_bucket": _bucket_choices(),
    "facing_sizing_bucket": _bucket_choices(),
    "spr_bucket": _spr_bucket_choices(),
}


def dimension_label(name: str) -> str:
    """The user-facing label of one group-by dimension."""
    return DIMENSION_LABELS.get(name, name)


def dimension_choices(name: str) -> tuple[Choice, ...]:
    """The closed domain of a dimension, when grouping by it has one."""
    return DIMENSION_CHOICES.get(name, ())


# ---------------------------------------------------------------------------
# Metrics: the question being measured.
# ---------------------------------------------------------------------------

METRIC_LABELS: Final[dict[str, str]] = {
    "opportunities": N_("how many decisions"),
    "hands": N_("how many hands"),
    "players": N_("how many players"),
    "action_count": N_("how many actions"),
    "frequency": N_("how often the decision is taken"),
    "hand_frequency": N_("per-hand frequency"),
    "fold_frequency": N_("fold frequency"),
    "call_frequency": N_("call frequency"),
    "raise_frequency": N_("raise frequency"),
    "bet_frequency": N_("bet frequency"),
    "check_frequency": N_("check frequency"),
    "average_sizing": N_("average bet size (basis points of the pot)"),
    "average_facing_sizing": N_("average bet size faced (basis points of the pot)"),
    "average_spr": N_("average SPR"),
    "average_pot": N_("average pot size"),
    "total_profit": N_("realized profit"),
    "profit_per_opportunity": N_("realized profit per decision"),
    "all_in_ev": N_("EV-adjusted result (all-in EV)"),
    "ev_per_opportunity": N_("EV-adjusted result per decision"),
}

# Metrics whose value is a frequency: the result states a numerator over a
# denominator, and the summary says so, because the epic's honesty rule is that
# a frequency never travels without its sample.
FREQUENCY_METRICS: Final[frozenset[str]] = frozenset(
    {
        "frequency",
        "hand_frequency",
        "fold_frequency",
        "call_frequency",
        "raise_frequency",
        "bet_frequency",
        "check_frequency",
    },
)

# The frequencies whose denominator is hands rather than decisions. The reader
# is told which one a question used, because the two disagree exactly where a
# player acted twice in the counted street (limping and then calling a raise is
# one hand and two decisions, and VPIP counts the hand).
HAND_FREQUENCY_METRICS: Final[frozenset[str]] = frozenset({"hand_frequency"})

# The metrics whose labels are money, and one of them is not realized money:
# keeping the two apart is the profitability rule of #300.
EV_METRICS: Final[frozenset[str]] = frozenset({"all_in_ev", "ev_per_opportunity"})


def metric_label(name: str) -> str:
    """The user-facing name of one metric (its name if unknown)."""
    return METRIC_LABELS.get(name, name)


# ---------------------------------------------------------------------------
# The active question, in plain language.
# ---------------------------------------------------------------------------

# Which filters read as one clause, and how that clause is worded. ``{v}`` is
# the rendered value, already translated through FILTER_CHOICES. A filter not
# listed here still gets a clause (see ``_generic_clause``) -- an unworded
# filter must never silently vanish from the summary.
_CLAUSES: Final[dict[str, str]] = {
    "site": "on {v}",
    "game": "{v}",
    "limit": "{v}",
    "currency": "played in {v}",
    "stake_bb": "{v} stakes",
    "big_blind": "{v} big blind",
    "seats": "{v} seats dealt in",
    "max_seats": "{v}-max tables",
    "date_from": "played since {v}",
    "date_to": "played until {v}",
    "player": "for {v}",
    "players": "for {v}",
    "identity": "for the linked identity {v}",
    "position": "from {v}",
    "opponent_position": "versus {v}",
    "relative_position": "sitting {v} from the button",
    "effective_stack_bb": "{v} effective",
    "effective_stack": "{v} effective",
    "stack_bucket": "{v} stacks",
    "spr": "{v}",
    "players_in_hand": "{v} players in the hand",
    "street": "on the {v}",
    "pot_type": "{v}",
    "pot_before": "with {v} in the pot",
    "to_call": "facing {v} to call",
    "pot_odds_bp": "at {v} of pot odds",
    "role": "as the {v}",
    "action_taken": "taking {v}",
    "action_faced": "facing {v}",
    "response": "responding with {v}",
    "situation": "{v}",
    "primary_situation": "{v}",
    "situation_group": "in {v} situations",
    "raisers_before": "after {v} raises",
    "starting_hand": "holding {v}",
    "bet_sizing_pct": "betting {v}",
    "facing_sizing_pct": "facing {v}",
    "sizing_bp": "betting {v} of the pot",
    "facing_sizing_bp": "facing {v} of the pot",
    "sizing_bucket": "betting {v} of the pot",
    "facing_sizing_bucket": "facing {v} of the pot",
    "board_rank": "on {v} boards",
    "board_suit": "on {v} boards",
    "board_pairing": "on {v} boards",
    "board_connectivity": "on {v} boards",
    "board_texture": "on boards that are {v}",
    "board_texture_all": "on boards that are {v}",
    "board_street": "with the board {v} cards deep",
    "made_hand": "holding {v}",
    "made_hand_rank": "with a made-hand rank of {v}",
    "pair_detail": "holding {v}",
    "nutness": "with {v} hand strength",
    "draw": "drawing to {v}",
    "draw_all": "holding all of {v}",
    "blocker": "blocking {v}",
    "blocker_all": "blocking all of {v}",
    "hand_state_street": "classified on the {v}",
}

# Boolean filters read better as a phrase than as "Yes"/"No".
_BOOL_CLAUSES: Final[dict[str, tuple[str, str]]] = {
    "in_position": ("in position", "out of position"),
    "multiway": ("in multiway pots", "heads-up pots"),
    "all_in": ("on all-in actions", "on non-all-in actions"),
    "is_aggressor": ("as the aggressor", "not as the aggressor"),
    "is_preflop_aggressor": ("as the preflop raiser", "not as the preflop raiser"),
    "is_previous_aggressor": (
        "as the previous street's aggressor",
        "not as the previous street's aggressor",
    ),
    "in_position_vs_previous_aggressor": (
        "in position on the previous aggressor",
        "out of position against the previous aggressor",
    ),
    "in_position_vs_facing": ("in position on the bettor", "out of position against the bettor"),
    "facing_all_in": ("facing an all-in", "not facing an all-in"),
    "tournament": ("in tournaments", "in cash games"),
    "hole_cards_known": ("with known hole cards", "with unknown hole cards"),
    "board_present": ("on the flop or later", "preflop"),
    "hand_state_known": ("with a classified hand state", "without a classified hand state"),
}

# The order clauses are read in. Game first, then who, then where they sat and
# what was in front of them, then what they held -- the way a player would say
# the spot out loud. A filter not named here keeps its group's place and is
# appended inside that group, alphabetically, so nothing can be dropped.
_CLAUSE_ORDER: Final[tuple[str, ...]] = (
    # -- game ---------------------------------------------------------------
    "site", "game", "limit", "currency", "max_seats", "seats", "stake_bb",
    "big_blind", "tournament", "date_from", "date_to",
    # -- who ----------------------------------------------------------------
    "player", "players", "identity",
    # -- seat and stack ------------------------------------------------------
    "position", "opponent_position", "relative_position", "in_position",
    "effective_stack_bb", "effective_stack", "stack_bucket", "spr",
    "players_in_hand", "multiway",
    # -- street and pot ------------------------------------------------------
    "street", "pot_type", "pot_before", "to_call", "pot_odds_bp", "role",
    "is_aggressor", "is_preflop_aggressor", "is_previous_aggressor",
    "in_position_vs_previous_aggressor", "in_position_vs_facing", "facing_all_in",
    # -- action --------------------------------------------------------------
    "primary_situation", "situation", "situation_group", "action_taken",
    "action_faced", "response", "all_in", "raisers_before",
    # -- sizing --------------------------------------------------------------
    "facing_sizing_pct", "facing_sizing_bucket", "bet_sizing_pct", "sizing_bucket",
    "facing_sizing_bp", "sizing_bp",
    # -- board ---------------------------------------------------------------
    "board_suit", "board_pairing", "board_connectivity", "board_rank",
    "board_texture", "board_texture_all", "board_runout", "board_present",
    # -- hand strength -------------------------------------------------------
    "made_hand", "pair_detail", "nutness", "draw", "draw_all", "draw_none",
    "blocker", "blocker_all", "blocker_none", "hole_cards_known", "hand_state_known",
    "starting_hand",
)

# The groups the clauses are read in, for the filters _CLAUSE_ORDER does not name.
_CLAUSE_GROUPS: Final[tuple[str, ...]] = (
    "game",
    "who",
    "seat",
    "street",
    "action",
    "cards",
    "sizing",
    "board",
    "strength",
)


# Tokens whose stored spelling is not what a reader calls them. These are
# *not* choices -- the value really is open (a room's own game category) -- so
# they only affect how a value that matches is rendered.
VALUE_LABELS: Final[dict[str, dict[str, str]]] = {
    # The stored tokens, not their families: a database holds ``omahahi``, and
    # a picker built from it offered that back at the reader unchanged (#355).
    "game": {
        "holdem": "Hold'em",
        "6_holdem": "Six-plus Hold'em",
        "omaha": "Omaha",
        "omahahi": "Omaha",
        "omahahilo": "Omaha Hi/Lo",
        "5_omahahi": "5-card Omaha",
        "5_omaha8": "5-card Omaha Hi/Lo",
        "6_omahahi": "6-card Omaha",
        "cour_hi": "Courchevel",
        "cour_hilo": "Courchevel Hi/Lo",
        "stud": "Seven-card stud",
        "studhi": "Seven-card stud",
        "studhilo": "Seven-card stud Hi/Lo",
        "razz": "Razz",
        "draw": "Draw",
        "fivedraw": "Five-card draw",
        "27_1draw": "2-7 single draw",
        "27_3draw": "2-7 triple draw",
        "a5_1draw": "A-5 single draw",
        "a5_3draw": "A-5 triple draw",
        "badugi": "Badugi",
        "badacey": "Badacey",
        "badeucey": "Badeucey",
    },
    "limit": {
        "nl": "no limit",
        "pl": "pot limit",
        "fl": "fixed limit",
        "limit": "fixed limit",
    },
    "response": {"complete": "complete"},
    # Seats are stored as button-relative codes, and the filter's own selector
    # offers them as BTN/CO/SB/BB -- but a grouped result printed the codes, so
    # one pane spoke two languages about the same value (#355). Keyed by the
    # stored code rather than by the filter token, which is what a row holds.
    "position": _POSITION_CODE_LABELS,
    "opponent_position": _POSITION_CODE_LABELS,
}


def _tokens(value: Any) -> list[Any]:
    """One filter value as the list of tokens a reader would say."""
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    return [value]


def _choice_labels(name: str) -> dict[str, str]:
    """The labels a token renders as: the closed choices, then the overrides."""
    labels = {choice.value: choice.label for choice in filter_choices(name)}
    labels.update(VALUE_LABELS.get(name, {}))
    return labels


def _render_value(name: str, value: Any) -> str:
    """One token, in the label the matching control would show."""
    label = _choice_labels(name).get(str(value))
    return label if label is not None else str(value)


def value_label(name: str, value: Any) -> str:
    """One stored value, as a reader would say it.

    The same rendering the filter controls and the query sentence use, exposed
    so a result row can use it too: a seat that reads ``-1`` in a table while
    its own filter offers ``SB`` is the table asking the reader to translate
    (#355). Anything with no label renders as itself.
    """
    return _render_value(name, value)


def _render_values(name: str, value: Any) -> str:
    """A filter's value, tokens joined the way a sentence reads."""
    tokens = [_render_value(name, token) for token in _tokens(value)]
    if len(tokens) == 1:
        return tokens[0]
    if not tokens:
        return "nothing"
    return ", ".join(tokens[:-1]) + " or " + tokens[-1]


def _render_range(name: str, value: Any) -> str:
    """A range as "80-120 BB" / "up to 100 BB" / "80% of pot or more"."""
    unit = filter_unit(name)
    if isinstance(value, Mapping):
        low, high = value.get("min"), value.get("max")
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        low, high = value
    else:
        return _render_values(name, value)
    suffix = f" {unit}" if unit else ""
    if low is None and high is None:
        return "any size"
    if low is None:
        return f"up to {high}{suffix}"
    if high is None:
        return f"{low}{suffix} or more"
    return f"{low}-{high}{suffix}"


def _clause(name: str, value: Any, kind: str) -> str | None:
    """One filter as a clause, or ``None`` when it says nothing.

    ``None`` values and empty token lists are *no filter*: the engine skips them,
    so the summary must too, or the sentence would describe a query nobody built.
    """
    if value is None or name == "hero":
        # ``hero`` is the population, not a clause; see _population_phrase.
        return None
    if isinstance(value, (list, tuple, set, frozenset)) and not value:
        return None
    if kind == "bool":
        boolean = bool(value)
        pair = _BOOL_CLAUSES.get(name)
        if pair is not None:
            return pair[0 if boolean else 1]
        label = filter_label(name)
        return label if boolean else f"not {label.lower()}"
    if kind == "range":
        rendered = _render_range(name, value)
        template = _CLAUSES.get(name)
        return template.format(v=rendered) if template else f"{filter_label(name).lower()} {rendered}"
    rendered = _render_values(name, value)
    template = _CLAUSES.get(name)
    if template is None:
        return f"{filter_label(name).lower()} {rendered}"
    return template.format(v=rendered)


def _population_phrase(filters: Mapping[str, Any]) -> str:
    """Who the question is about: hero, everyone else, or the whole population."""
    hero = filters.get("hero")
    if hero is True:
        return "Hero's decisions"
    if hero is False:
        return "All players except hero"
    return "All decisions"


def _measure_phrase(metric: str) -> str:
    """What the question measures, stated with its denominator when it has one."""
    label = metric_label(metric)
    if metric in HAND_FREQUENCY_METRICS:
        return f"{label} (hands where it happened \u00f7 hands with the chance)"
    if metric in FREQUENCY_METRICS:
        return f"{label} (matching decisions \u00f7 opportunities)"
    if metric in EV_METRICS:
        return f"{label} (a separate figure from realized profit)"
    return label


def _breakdown_phrase(group_by: Any) -> str:
    """The breakdown, in the dimensions' own labels."""
    if isinstance(group_by, str):
        group_by = (group_by,)
    names = [name for name in (group_by or ()) if name]
    if not names:
        return ""
    rendered = [dimension_label(name).lower() for name in names]
    if len(rendered) == 1:
        return f", broken down by {rendered[0]}"
    return ", broken down by " + " and ".join([", ".join(rendered[:-1]), rendered[-1]])


def _ordered_clauses(filters: Mapping[str, Any], by_name: Mapping[str, Any]) -> list[str]:
    """Every filter that says something, in reading order.

    Three passes, and the third is the one that matters: a filter this module
    has never heard of is *named* rather than dropped, because a sentence that
    claims to describe a query must not quietly omit part of it.
    """
    described: set[str] = set()
    clauses: list[str] = []
    for name in _CLAUSE_ORDER:
        spec = by_name.get(name)
        if spec is not None and name in filters:
            described.add(name)
            clauses.append(_clause_or_empty(name, filters[name], spec.value_kind))
    # Then whatever _CLAUSE_ORDER does not name, in its group's place.
    for group in _CLAUSE_GROUPS:
        for name, spec in by_name.items():
            if spec.group == group and name not in described and name in filters:
                described.add(name)
                clauses.append(_clause_or_empty(name, filters[name], spec.value_kind))
    for name, value in filters.items():
        if name in described:
            continue
        spec = by_name.get(name)
        if spec is None:
            clauses.append(f"with the unrecognised filter {name}")
        else:
            clauses.append(_clause_or_empty(name, value, spec.value_kind))
    return [clause for clause in clauses if clause]


def _clause_or_empty(name: str, value: Any, kind: str) -> str:
    """``_clause`` as a string, since an unspoken filter is simply absent."""
    return _clause(name, value, kind) or ""


def describe_query(preset: Mapping[str, Any]) -> str:
    """The active question in plain poker language, before anything runs.

    One sentence built from the same labels the controls show: the population,
    the context clauses in reading order, then the measurement and the
    breakdown. It is a *description* -- it never decides what the query is --
    but it is generated from the filter metadata rather than hand-written per
    preset, so a query the UI can express is a question the summary can say.
    """
    metric = str(preset.get("metric") or "")
    if not metric:
        return ""
    filters = preset.get("filters") or {}
    if not isinstance(filters, Mapping):
        return ""
    # Deferred import: the browser imports this module, so the dependency runs
    # the other way only inside the call, never at import time.
    from .research_browser import FILTER_SPECS

    clauses = _ordered_clauses(filters, {spec.name: spec for spec in FILTER_SPECS})
    head = _population_phrase(filters)
    context = ", ".join(clauses)
    sentence = f"{head}: {context}." if context else f"{head}."
    return f"{sentence} Measure {_measure_phrase(metric)}{_breakdown_phrase(preset.get('group_by') or ())}."


__all__ = [
    "BEGINNER_DIMENSIONS",
    "Choice",
    "VALUE_LABELS",
    "value_label",
    "DIMENSION_CHOICES",
    "DIMENSION_LABELS",
    "EV_METRICS",
    "EXPERT_ONLY_FILTERS",
    "FILTER_CHOICES",
    "FILTER_DESCRIPTIONS",
    "FILTER_EXAMPLES",
    "FILTER_GROUP_LABELS",
    "FILTER_LABELS",
    "FILTER_UNITS",
    "FREQUENCY_METRICS",
    "HAND_FREQUENCY_METRICS",
    "METRIC_LABELS",
    "describe_query",
    "dimension_choices",
    "dimension_label",
    "filter_choices",
    "filter_description",
    "filter_example",
    "filter_label",
    "filter_unit",
    "is_expert_only",
    "metric_label",
]
