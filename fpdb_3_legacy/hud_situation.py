"""Context-aware dynamic HUD panels (issue #298).

The HUD draws one fixed grid of stats per seat and, at most, hides a
position-bound panel when the seat is not in that position. The analytics epic
adds a second question the HUD cannot currently answer: *which panels are worth
showing **right now***, given the hand in front of the player -- the street, the
roles, the pot shape, the aggressors, the stack depth and the sizing faced.

This module answers it, and it is deliberately separate from
:mod:`fpdb_3_legacy.hud_profiles`. ``HudProfileResolver`` decides **which HUD
profile applies to a table** from the table's shape (site, game, seats, speed)
and changes at most once per table. This module decides **which panels to show
in the live decision context**, and changes street by street. Folding the two
together would make every table-shape rule a live rule and every live rule a
table rule; keeping them apart keeps each resolver's precedence explainable.

The context
-----------

:class:`HudSituationContext` is a frozen snapshot of the decision in front of
one seat: street, positions, roles, pot type, what is being faced, the
aggressors and the effective stack. Two constructors matter:

* :meth:`HudSituationContext.from_situation` builds it from the canonical
  :class:`~fpdb_3_legacy.player_situations.PlayerSituation` of #294, so the HUD
  and the analytics layer describe a spot the same way and cannot drift;
* :meth:`HudSituationContext.from_stat_dict` builds it from the live HUD
  ``stat_dict`` entry plus whatever live state the HUD feed knows
  (``Hud.live_state``), so a panel can be chosen from the state the table is
  actually in.

:meth:`HudSituationContext.filters` projects the context onto the **filter
vocabulary of the query engine** (#297). That is the whole point of the
mapping: a panel rule's condition is written in the same words a research query
would use, and validating a rule can consult the engine's own registry instead
of a second list that would drift from it.

The rules
---------

A :class:`PanelRule` is data: a panel name plus ``when`` conditions in that
vocabulary, a minimum sample, an optional position substitution, an optional
fallback panel, a priority and a profile scope. Loading validates every
condition name against ``analytics_query.FILTERS``, so a typo is a ``ValueError``
naming the condition and listing what exists -- a rule that loads is a rule that
can be evaluated.

:class:`HudSituationResolver` adds the precedence the issue asks for: most
conditions wins, then the explicit priority, then file order, and
``PanelSelection`` reports **which rule decided each panel** and which panels
were withheld for want of sample.

Change detection
----------------

The HUD must not rebuild itself on every action. :class:`PanelState` keeps the
last selection per seat and answers :meth:`PanelState.update` with a
:class:`PanelChange` that names exactly what appeared and disappeared, so only
those panels redraw. Nothing in this module ever touches a window position --
positions stay wherever the player dragged them, which is what keeps a dynamic
panel from moving a static one.

Units, the shipped panel library and the configuration section:
``docs/dynamic-panels.md``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Final, NamedTuple, NoReturn

# The panel-rule file schema this module understands. A file written for a newer
# schema is refused rather than half-read.
PANEL_SCHEMA_VERSION: Final = 1

# The streets a rule may name, in the order the HUD walks them. This is the
# vocabulary ``player_situations.PlayerSituation.street_name`` uses.
STREETS: Final[tuple[str, ...]] = ("preflop", "flop", "turn", "river")

# The pot shapes the situation model names (``player_situations.POT_*``).
POT_TYPES: Final[tuple[str, ...]] = (
    "unopened",
    "limped",
    "single_raised",
    "three_bet",
    "four_bet_plus",
)

# The roles a decision is classified into (``player_situations._role``).
ROLES: Final[tuple[str, ...]] = ("aggressor", "defender", "passive")

# The name a configuration writes to mean "the rules that ship with fpdb", so
# enabling dynamic panels is one attribute rather than a copy of the library.
BUILTIN_SOURCE: Final = "builtin"
# The Omaha reference HUD shows the relevant panel even for a new opponent;
# its visible hand count still communicates how little evidence backs the stats.
PLO_BUILTIN_SOURCE: Final = "builtin_plo"

# The ``position`` binding a block whose panel the rules select carries.
#
# A block is shown when a selection *names* its panel, and otherwise keeps the
# position rule every block has always had -- so a panel that is not selected
# has to be bound to a seat that cannot exist, or it would sit on screen for
# every seat that has no binding. ``normalize_position`` maps no seat to this,
# which is exactly what makes it unreachable, and the always-visible fallback
# block simply carries no binding at all.
DYNAMIC_ONLY_POSITION: Final = "dynamic"

# Effective-stack bands in big blinds (``player_situations.SHORT_STACK_BB``),
# used when a context has no bucket of its own.
SHORT_STACK_BB: Final = 20
MEDIUM_STACK_BB: Final = 50
DEEP_STACK_BB: Final = 100

# The rule fields, kept as data so an unknown field is refused with the list.
_RULE_FIELDS: Final = frozenset(
    {
        "panel",
        "id",
        "profile",
        "when",
        "min_sample",
        "sample",
        "fallback",
        "priority",
        "enabled",
        "substitutions",
        "section",
        "label",
        "description",
    },
)


def _fail(message: str, source: str = "") -> NoReturn:
    raise ValueError(f"{message} [{source}]" if source else message)


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text.casefold() if text else default


def _list(value: Any) -> tuple[Any, ...]:
    """A condition value as a list: one value, or the sequence as written."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(value)
    return (value,)


def _number(value: Any) -> int | None:
    if value in (None, "", "all", "ANY"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Position vocabulary.
# --------------------------------------------------------------------------- #


def normalize_position(raw: Any) -> str:
    """Map a stored/labelled position to a canonical panel code.

    Accepts the values DerivedStats stores in HandsPlayers.position (0 = button,
    ``"S"`` = small blind, ``"B"`` = big blind, 1.. = seats after the BB) and
    the panel labels used in configs (``"BU"``/``"SB"``/``"BB"``/...). Returns
    one of BTN/SB/BB/CO/MP/EP (or ``""`` when unknown/empty).

    This is the single implementation: ``Aux_Hud.normalize_position`` re-exports
    it, so the dynamic panel layer and the position-bound block layer cannot
    disagree about what ``"B"`` means.
    """
    if raw is None or raw == "":
        return ""
    text = str(raw).strip().upper()
    if text in ("0", "BTN", "BU", "D", "BUTTON"):
        return "BTN"
    if text in ("S", "SB"):
        return "SB"
    if text in ("B", "BB"):
        return "BB"
    after_bb = {
        "1": "CO",
        "2": "MP",
        "3": "MP",
        "4": "EP",
        "5": "EP",
        "6": "EP",
        "7": "EP",
        "8": "EP",
        "9": "EP",
    }
    return after_bb.get(text, text)


def block_visible(block_position: str, player_position: Any) -> bool:
    """Whether a panel bound to ``block_position`` shows for ``player_position``.

    A block with no position binding is always visible; otherwise the player's
    normalized position must match the block's. This is the position-bound rule
    the HUD has always used -- ``Aux_Hud.block_visible`` re-exports it -- and the
    static half of :func:`block_visible_for`.
    """
    if not block_position:
        return True
    return normalize_position(block_position) == normalize_position(player_position)


def stack_bucket_for(effective_stack_bb: int) -> str:
    """The stack band a depth in big blinds falls in (``short``/<20bb etc.)."""
    if effective_stack_bb < SHORT_STACK_BB:
        return "short"
    if effective_stack_bb < MEDIUM_STACK_BB:
        return "medium"
    return "deep"


# --------------------------------------------------------------------------- #
# The live context.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class HudSituationContext:
    """A stable snapshot of the decision in front of one seat.

    Every field describes what the seat had in front of them **before** acting,
    matching the situation model's rule: a decision is never explained by its own
    chips. The defaults describe "we know nothing yet", which is a valid context
    and resolves to the fallback panel.
    """

    # -- table shape -------------------------------------------------------
    site: str = "all"
    game: str = "all"
    limit: str = "all"
    seats: int = 0
    players: int = 0
    tournament: bool = False

    # -- who is being drawn -------------------------------------------------
    position: str = ""
    opponent_position: str = ""
    relative_position: int = 0
    in_position: bool | None = None

    # -- the decision -------------------------------------------------------
    street: str = "preflop"
    street_index: int = 0
    pot_type: str = ""
    role: str = ""
    players_in_hand: int = 0
    multiway: bool = False
    spr: int = 0

    # -- stacks -------------------------------------------------------------
    effective_stack_bb: int = 0
    stack_bucket: str = ""

    # -- aggressions --------------------------------------------------------
    is_aggressor: bool = False
    is_preflop_aggressor: bool = False
    is_previous_aggressor: bool = False
    in_position_vs_facing: bool | None = None
    facing_action: str = ""
    facing_all_in: bool = False
    action_taken: str = ""

    # -- sizing (basis points of the pot, as the event rows store them) -----
    facing_sizing_bp: int = 0
    sizing_bp: int = 0
    to_call: int = 0
    pot_before: int = 0

    # -- names --------------------------------------------------------------
    labels: tuple[str, ...] = ()
    primary: str = ""
    group: str = ""

    def normalized(self) -> HudSituationContext:
        """Coerce to the canonical spelling, so two equal contexts compare equal."""
        return replace(
            self,
            site=_text(self.site, "all"),
            game=_text(self.game, "all"),
            limit=_text(self.limit, "all"),
            position=normalize_position(self.position),
            opponent_position=normalize_position(self.opponent_position),
            street=_text(self.street, "preflop"),
            pot_type=_text(self.pot_type),
            role=_text(self.role),
            stack_bucket=_text(self.stack_bucket) or (stack_bucket_for(self.effective_stack_bb) if self.effective_stack_bb else ""),
        )

    @property
    def is_preflop(self) -> bool:
        return self.street == "preflop"

    def facing_sizing_pct(self) -> int | None:
        """The sizing faced as a percentage of the pot, or None when unknown."""
        return self.facing_sizing_bp // 100 if self.facing_sizing_bp else None

    def key(self) -> tuple[Any, ...]:
        """A hashable identity of this context, for change detection.

        Two contexts with the same key resolve to the same panels, so a
        :class:`PanelState` can tell "the context did not move" from "the
        context moved but resolves the same way" without deep comparison.
        """
        ctx = self.normalized()
        return (
            ctx.site,
            ctx.game,
            ctx.limit,
            ctx.position,
            ctx.opponent_position,
            ctx.in_position,
            ctx.street,
            ctx.pot_type,
            ctx.role,
            ctx.effective_stack_bb,
            ctx.stack_bucket,
            ctx.is_aggressor,
            ctx.is_preflop_aggressor,
            ctx.is_previous_aggressor,
            ctx.in_position_vs_facing,
            ctx.facing_action,
            ctx.facing_all_in,
            ctx.facing_sizing_bp,
            ctx.sizing_bp,
            ctx.to_call,
            ctx.pot_before,
            ctx.primary,
            ctx.multiway,
        )

    def filters(self) -> dict[str, Any]:
        """The context in the query engine's **filter vocabulary** (#297).

        A panel rule is written against these names, so the words that select a
        live panel are the words that select a research query, and validating a
        rule consults ``analytics_query.FILTERS`` rather than a second list.
        """
        ctx = self.normalized()
        values: dict[str, Any] = {
            "site": ctx.site,
            "game": ctx.game,
            "limit": ctx.limit,
            "seats": ctx.seats,
            "tournament": ctx.tournament,
            "position": ctx.position,
            "opponent_position": ctx.opponent_position,
            "relative_position": ctx.relative_position,
            "in_position": ctx.in_position,
            "street": ctx.street,
            "street_index": ctx.street_index,
            "pot_type": ctx.pot_type,
            "role": ctx.role,
            "players_in_hand": ctx.players_in_hand,
            "multiway": ctx.multiway,
            "spr": ctx.spr,
            "effective_stack_bb": ctx.effective_stack_bb,
            "stack_bucket": ctx.stack_bucket,
            "is_aggressor": ctx.is_aggressor,
            "is_preflop_aggressor": ctx.is_preflop_aggressor,
            "is_previous_aggressor": ctx.is_previous_aggressor,
            "in_position_vs_facing": ctx.in_position_vs_facing,
            "action_faced": ctx.facing_action,
            "action_taken": ctx.action_taken,
            "facing_all_in": ctx.facing_all_in,
            # Nothing to call is a real value, not a missing one: it is what
            # makes "the preflop raiser checked and it is on me" expressible as
            # ``to_call: [null, 0]`` in the engine's own vocabulary.
            "to_call": ctx.to_call,
            "pot_before": ctx.pot_before,
            # Both sizing names read the basis-point column, exactly as the
            # engine's registry does: ``*_pct`` compares a pair written in per
            # cent against the stored bp value (see ``condition_matches``).
            "facing_sizing_bp": ctx.facing_sizing_bp,
            "facing_sizing_pct": ctx.facing_sizing_bp,
            "sizing_bp": ctx.sizing_bp,
            "bet_sizing_pct": ctx.sizing_bp,
            "situation": list(ctx.labels),
            "primary_situation": ctx.primary,
            "situation_group": ctx.group,
        }
        # A value the live feed did not supply is *absent*, not falsy: a rule
        # asking ``role: defender`` must not match a decision whose role is
        # unknown, and ``in_position: false`` must still be answerable, so a
        # boolean is kept when it is known. The numeric names below are the ones
        # where zero means "unknown" rather than a magnitude -- nobody bets or
        # raises for 0% of the pot, and nobody has a 0bb stack -- so a rule
        # asking for a small bet cannot match a sizing the feed never saw.
        zero_is_unknown = (
            "relative_position",
            "spr",
            "effective_stack_bb",
            "stack_bucket",
            "players_in_hand",
            "facing_sizing_bp",
            "facing_sizing_pct",
            "sizing_bp",
            "bet_sizing_pct",
        )
        return {
            name: value
            for name, value in values.items()
            if value not in (None, "", [], ()) and not (name in zero_is_unknown and not value)
        }

    @classmethod
    def from_filters(cls, values: Mapping[str, Any], **overrides: Any) -> HudSituationContext:
        """A context from a mapping in the **query engine's filter vocabulary**.

        Accepts exactly what :meth:`filters` produces, which is the vocabulary a
        panel rule is written in -- so a caller that has selectors (a
        configuration section, a command line, a preview form) can build the
        context the rule will be evaluated against without knowing the two
        vocabularies differ. Two conversions happen here and only here:

        * ``situation`` is the label tuple, not a scalar;
        * ``*_pct`` names are basis points of the pot, as the engine compares
          them, so ``facing_sizing_pct=6600`` is a 66% pot-bet.

        Unknown names are ignored rather than guessed at, so a caller can hand
        this a whole filter dict. ``street_index`` follows ``street`` when it is
        not given, because a rule keyed on the index must not read 0 for a flop.
        """
        street = _text(values.get("street"), "preflop")
        labels = values.get("situation")
        fields: dict[str, Any] = {
            "site": values.get("site", "all"),
            "game": values.get("game", "all"),
            "limit": values.get("limit", "all"),
            "seats": _number(values.get("seats")) or 0,
            "tournament": bool(values.get("tournament", False)),
            "position": values.get("position", ""),
            "opponent_position": values.get("opponent_position", ""),
            "relative_position": _number(values.get("relative_position")) or 0,
            "in_position": _boolean(values.get("in_position")),
            "street": street,
            "street_index": (
                _number(values.get("street_index"))
                if _number(values.get("street_index")) is not None
                else STREETS.index(street)
                if street in STREETS
                else 0
            ),
            "pot_type": values.get("pot_type", ""),
            "role": values.get("role", ""),
            "players_in_hand": _number(values.get("players_in_hand")) or 0,
            "multiway": bool(values.get("multiway", False)),
            "spr": _number(values.get("spr")) or 0,
            "effective_stack_bb": _number(values.get("effective_stack_bb")) or 0,
            "stack_bucket": values.get("stack_bucket", ""),
            "is_aggressor": bool(values.get("is_aggressor", False)),
            "is_preflop_aggressor": bool(values.get("is_preflop_aggressor", False)),
            "is_previous_aggressor": bool(values.get("is_previous_aggressor", False)),
            "in_position_vs_facing": _boolean(values.get("in_position_vs_facing")),
            "facing_action": values.get("action_faced", ""),
            "facing_all_in": bool(values.get("facing_all_in", False)),
            "action_taken": values.get("action_taken", ""),
            "facing_sizing_bp": _number(values.get("facing_sizing_bp") or values.get("facing_sizing_pct")) or 0,
            "sizing_bp": _number(values.get("sizing_bp") or values.get("bet_sizing_pct")) or 0,
            "to_call": _number(values.get("to_call")) or 0,
            "pot_before": _number(values.get("pot_before")) or 0,
            "labels": tuple(_list(labels)) if labels is not None else (),
            "primary": values.get("primary_situation", ""),
            "group": values.get("situation_group", ""),
        }
        fields.update(overrides)
        return cls(**fields).normalized()

    @classmethod
    def from_situation(cls, situation: Any, **overrides: Any) -> HudSituationContext:
        """Build the context of a canonical :class:`PlayerSituation` (#294).

        The mapping is the point of contact between the HUD and the analytics
        layer: one constructor, so a panel rule sees the same street, role, pot
        type and sizing a research query would filter on.
        """
        fields: dict[str, Any] = {
            "site": getattr(situation, "site", "all"),
            "game": getattr(situation, "game", "all"),
            "limit": getattr(situation, "limit_type", "all"),
            "seats": getattr(situation, "table_size", 0),
            "players": getattr(situation, "players_dealt", 0),
            "tournament": bool(getattr(situation, "is_tournament", False)),
            "position": getattr(situation, "position", None),
            "opponent_position": getattr(situation, "facing_position", None),
            "relative_position": getattr(situation, "relative_position", 0),
            "in_position": getattr(situation, "in_position", None),
            "street": getattr(situation, "street_name", "preflop"),
            "street_index": getattr(situation, "street", 0),
            "pot_type": getattr(situation, "pot_type", ""),
            "role": getattr(situation, "role", ""),
            "players_in_hand": getattr(situation, "players_in_hand", 0),
            "multiway": bool(getattr(situation, "multiway", False)),
            "spr": getattr(situation, "spr_before", 0),
            "effective_stack_bb": centi_to_bb(getattr(situation, "effective_stack_bb", 0)),
            "stack_bucket": getattr(situation, "stack_bucket", ""),
            "is_aggressor": bool(getattr(situation, "is_aggressor", False)),
            "is_preflop_aggressor": bool(getattr(situation, "is_preflop_aggressor", False)),
            "is_previous_aggressor": bool(getattr(situation, "is_previous_aggressor", False)),
            "in_position_vs_facing": getattr(situation, "in_position_vs_facing", None),
            "facing_action": getattr(situation, "facing_action", None) or "",
            "facing_all_in": bool(getattr(situation, "facing_all_in", False)),
            "action_taken": getattr(situation, "response", ""),
            "facing_sizing_bp": getattr(situation, "facing_sizing_bp", 0),
            "sizing_bp": getattr(situation, "sizing_bp", 0),
            "to_call": getattr(situation, "to_call", 0),
            "pot_before": getattr(situation, "pot_before", 0),
            "labels": tuple(getattr(situation, "labels", ()) or ()),
            "primary": getattr(situation, "primary", ""),
            "group": getattr(situation, "group", ""),
        }
        fields.update(overrides)
        # Canonical from the start: the model's spellings (``"PokerStars.COM"``,
        # position ``"B"``) are not the context's, and a context that has to be
        # normalised before it compares equal to the live one is a context that
        # will eventually be compared without normalising it.
        return cls(**fields).normalized()

    @classmethod
    def from_stat_dict(cls, entry: Mapping[str, Any] | None, live: Mapping[str, Any] | None = None) -> HudSituationContext:
        """Build the context of one seat from the live HUD state.

        ``entry`` is ``stat_dict[player_id]``: the HudCache aggregate row, whose
        ``live_position``/``position`` is where the seat actually sits this hand.
        ``live`` is ``Hud.live_state`` -- whatever the table feed knows about the
        hand in progress (``street``, ``pot_type``, ``role``, the aggressors, the
        sizing). Anything the feed does not know stays unset, which a rule sees
        as "absent" rather than as a value, so an unknown street never matches a
        flop rule by accident.
        """
        entry = entry or {}
        live = live or {}
        position = entry.get("live_position") or entry.get("position") or live.get("position") or ""
        street = _text(live.get("street"), "preflop")
        # The row and the live state describe the same hand, so the row's own
        # per-street columns answer the per-seat half of the question -- did
        # *this* seat raise, act last, face a raise -- whenever the feed has not
        # pushed an answer. The feed wins where it has one.
        # HudCache rows are aggregates over many *finished* hands. Their
        # aggressor/position flags cannot describe the current Winamax round.
        facts = {} if live.get("source") == "street_live" else entry_facts(entry, street)
        context = cls(
            site=live.get("site", "all"),
            game=live.get("game", "all"),
            limit=live.get("limit", "all"),
            seats=_number(live.get("seats")) or 0,
            players=_number(entry.get("players") or live.get("players")) or 0,
            tournament=bool(live.get("tournament", False)),
            position=position,
            opponent_position=live.get("opponent_position", ""),
            relative_position=_number(live.get("relative_position")) or 0,
            in_position=_boolean(_first(live.get("in_position"), facts.get("in_position"))),
            street=street,
            street_index=_number(live.get("street_index")) or facts.get("street_index", 0),
            pot_type=live.get("pot_type", ""),
            role=live.get("role", ""),
            players_in_hand=_number(live.get("players_in_hand")) or 0,
            multiway=bool(live.get("multiway", False)),
            spr=_number(live.get("spr")) or 0,
            effective_stack_bb=_number(live.get("effective_stack_bb") or entry.get("bbstack")) or 0,
            stack_bucket=live.get("stack_bucket", ""),
            is_aggressor=bool(_first(live.get("is_aggressor"), facts.get("is_aggressor")) or False),
            is_preflop_aggressor=bool(
                _first(live.get("is_preflop_aggressor"), facts.get("is_preflop_aggressor")) or False
            ),
            is_previous_aggressor=bool(live.get("is_previous_aggressor", False)),
            in_position_vs_facing=_boolean(live.get("in_position_vs_facing")),
            facing_action=_first(live.get("facing_action"), facts.get("facing_action")) or "",
            facing_all_in=bool(live.get("facing_all_in", False)),
            action_taken=live.get("action_taken", ""),
            facing_sizing_bp=_number(_first(live.get("facing_sizing_bp"), facts.get("facing_sizing_bp"))) or 0,
            sizing_bp=_number(live.get("sizing_bp")) or 0,
            to_call=_number(live.get("to_call")) or 0,
            pot_before=_number(live.get("pot_before")) or 0,
            labels=tuple(live.get("labels", ()) or ()),
            primary=live.get("primary", ""),
            group=live.get("group", ""),
        )
        return context.normalized()

    def describe(self) -> str:
        """A one-line human rendering, for logs and the CLI."""
        ctx = self.normalized()
        parts = [f"street={ctx.street}"]
        if ctx.position:
            parts.append(f"pos={ctx.position}")
        if ctx.opponent_position:
            parts.append(f"vs={ctx.opponent_position}")
        if ctx.role:
            parts.append(f"role={ctx.role}")
        if ctx.pot_type:
            parts.append(f"pot={ctx.pot_type}")
        if ctx.stack_bucket:
            parts.append(f"stack={ctx.stack_bucket}")
        if ctx.facing_action:
            parts.append(f"facing={ctx.facing_action}")
        if ctx.primary:
            parts.append(f"primary={ctx.primary}")
        return " ".join(parts)


def centi_to_bb(raw: Any) -> int:
    """Whole big blinds from the model's centi-unit.

    ``PlayerSituation.effective_stack_bb`` is hundredths of a big blind
    (100 = 1bb, 10000 = 100bb), so a context built from a situation converts
    here; a context built from the HUD's ``bbstack`` is already in big blinds.
    """
    return (_number(raw) or 0) // 100


# The HudCache column that holds one per-seat fact for each street the hand
# reached: whether the seat took the aggression, whether it acts last, whether
# it faced a raise, whether it faced a bet, and how big the sizing faced was (in
# basis points of the pot). One row per street, keyed by the situation model's
# street index (0 = preflop, 1 = flop, ...).
_STREET_COLUMNS: Final[dict[int, dict[str, Any]]] = {
    0: {
        "aggressor": "street0Aggr",
        "in_position": "street0InPosition",
        "faced_raise": ("street0FaceRaise",),
        "faced_bet": (),
        "faced_sizing": ("val_p_2bet_facing_bp", "val_p_3bet_facing_bp", "val_p_4bet_facing_bp"),
    },
    1: {
        "aggressor": "street1Aggr",
        "in_position": "street1InPosition",
        "faced_raise": ("street1FaceRaise",),
        "faced_bet": ("foldToStreet1CBChance",),
        "faced_sizing": ("val_f_bet_facing_bp", "val_f_2bet_facing_bp", "val_f_3bet_facing_bp"),
    },
    2: {
        "aggressor": "street2Aggr",
        "in_position": "street2InPosition",
        "faced_raise": ("street2FaceRaise",),
        "faced_bet": ("foldToStreet2CBChance",),
        "faced_sizing": ("val_t_bet_facing_bp", "val_t_2bet_facing_bp", "val_t_3bet_facing_bp"),
    },
    3: {
        "aggressor": "street3Aggr",
        "in_position": "street3InPosition",
        "faced_raise": ("street3FaceRaise",),
        "faced_bet": ("foldToStreet3CBChance",),
        "faced_sizing": ("val_r_bet_facing_bp", "val_r_2bet_facing_bp", "val_r_3bet_facing_bp"),
    },
}


def _entry_value(entry: Mapping[str, Any], lowered: Mapping[str, Any], *names: str) -> Any:
    """Read a value from legacy HudCache keys or lower-cased SQL aliases."""
    for name in names:
        if name in entry:
            return entry[name]
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def entry_facts(entry: Mapping[str, Any], street: str) -> dict[str, Any]:
    """The per-seat facts of one aggregate row, for the street it reached.

    A panel rule asks two kinds of question: table-wide ones ("this is a single
    raised pot that reached the flop") that come from the live state, and
    per-seat ones ("this seat raised preflop", "this seat acts last", "this seat
    faced the c-bet") that a table-wide feed does not usually know. The
    HudCache row of that same hand answers the second kind: it *is* the seat's
    record of the hand the live state describes. A value the feed did push
    wins; this is the floor, not the ceiling.

    A flag that is false is a real answer ("this seat did not raise"), so an
    explicit false is kept rather than treated as unknown.
    """
    index = STREETS.index(street) if street in STREETS else 0
    columns = _STREET_COLUMNS[index]
    lowered = {str(key).lower(): value for key, value in entry.items()}

    facts: dict[str, Any] = {"street_index": index}
    aggr_alias = "pfr" if index == 0 else f"aggr_{index}"
    aggressor = _boolean(_entry_value(entry, lowered, columns["aggressor"], aggr_alias))
    if aggressor is not None:
        facts["is_aggressor"] = aggressor
    # The row describes one whole hand, so the preflop fact is readable whatever
    # street the hand reached -- and it is the fact most rules ask about: "this
    # seat raised preflop" is what makes a c-bet panel theirs on the flop.
    preflop_aggressor = _boolean(_entry_value(entry, lowered, _STREET_COLUMNS[0]["aggressor"], "pfr"))
    if preflop_aggressor is not None:
        facts["is_preflop_aggressor"] = preflop_aggressor
    in_position = _boolean(_entry_value(entry, lowered, columns["in_position"], f"street{index}inposition"))
    if in_position is not None:
        facts["in_position"] = in_position
        facts["in_position_vs_facing"] = in_position
    raise_alias = ("p_face_raise",) if index == 0 else (f"{'ftr'[index - 1]}_face_raise",)
    if any(_boolean(_entry_value(entry, lowered, name, *raise_alias)) for name in columns["faced_raise"]):
        facts["facing_action"] = "raises"
    bet_alias = () if index == 0 else (f"{'ftr'[index - 1]}_cb_opp_{index}",)
    if "facing_action" not in facts and any(
        _boolean(_entry_value(entry, lowered, name, *bet_alias)) for name in columns["faced_bet"]
    ):
        facts["facing_action"] = "bets"
    # The deepest level the seat actually faced: a hand cannot face a 3-bet
    # without having faced the 2-bet first, but the columns do not add up, so
    # the largest non-zero one is the level the money stopped at.
    sizing_alias = () if index == 0 else (f"{'ftr'[index - 1]}_bet_facing_bp",)
    sizing = max((_number(_entry_value(entry, lowered, name, *sizing_alias)) or 0) for name in columns["faced_sizing"])
    if sizing:
        facts["facing_sizing_bp"] = sizing
    return facts


def _winamax_position_order(row: Mapping[str, Any]) -> int | None:
    raw = str(row.get("live_position") or row.get("position") or "").strip().upper()
    if raw in ("S", "SB"):
        return 0
    if raw in ("B", "BB"):
        return 1
    if raw in ("0", "BTN", "BU", "D", "BUTTON"):
        return 100
    if raw.isdigit():
        # Winamax numbers seats outwards from the button: a lower number acts
        # later postflop. Keep the button above every numbered seat.
        return 100 - int(raw)
    return {"EP": 2, "UTG": 2, "MP": 3, "HJ": 3, "CO": 4}.get(raw)


def winamax_live_state_for_player(
    entry: Mapping[str, Any],
    entries: Iterable[Mapping[str, Any]],
    live: Mapping[str, Any],
) -> dict[str, Any]:
    """Add seat facts that the Winamax round log and HUD positions establish.

    The log names the actual preflop raiser but no seat number. Imported HUD
    rows supply each player's current estimated position. Only publish an IP
    answer when every remaining opponent has a usable position; aggregate
    HudCache flags must never be mistaken for facts of the live hand.
    """
    state = dict(live)
    if state.get("source") != "street_live":
        return state
    player = str(entry.get("screen_name") or "").casefold()
    aggressor = str(state.get("preflop_aggressor") or "").casefold()
    if not player or not aggressor:
        return state
    state["is_preflop_aggressor"] = player == aggressor

    own_order = _winamax_position_order(entry)
    if own_order is None:
        return state
    folded = {str(name).casefold() for name in state.get("folded_players", ())}
    active = [
        row for row in entries
        if isinstance(row, Mapping)
        and str(row.get("screen_name") or "").casefold()
        not in folded
    ]
    by_name = {str(row.get("screen_name") or "").casefold(): row for row in active}
    if player == aggressor:
        other_orders = [_winamax_position_order(row) for name, row in by_name.items() if name != player]
        if other_orders and all(value is not None for value in other_orders):
            state["in_position"] = own_order > max(value for value in other_orders if value is not None)
    elif aggressor in by_name and (aggressor_order := _winamax_position_order(by_name[aggressor])) is not None:
        state["in_position"] = own_order > aggressor_order
    return state


def live_state_from_hand(hand: Any) -> dict[str, Any]:
    """What one assembled hand says about the table, for ``Hud.live_state``.

    The classic HUD is refreshed once per hand, so the most it can know about
    the table in front of it is the shape of the hand it has just assembled --
    the same assumption ``HUD_main._advance_live_positions`` already makes about
    the seats, for the same reason. This publishes the table-wide half of that
    shape: how deep the hand went, how the preflop round was shaped and how many
    players are still in. Per-seat facts are read off each seat's aggregate row
    instead (see :func:`entry_facts`).

    A feed that follows a hand action by action knows far more than this, and
    publishes it through ``Hud.set_live_state``: this is the floor, not the
    ceiling. An empty mapping means "nothing known", which a rule reads as
    absent rather than as a value.
    """
    actions = getattr(hand, "actions", None)
    if not isinstance(actions, Mapping):
        return {}
    preflop = _action_rows(actions.get("PREFLOP"))
    reached = [index for index, street in enumerate(STREETS) if _action_rows(actions.get(street.upper()))]
    # A hand with no postflop action is a preflop hand: the street the table is
    # about to play is at least the preflop one.
    street_index = max(reached) if reached else 0
    players = len(getattr(hand, "players", ()) or ())
    # Who started the street the hand got to: the folds *before* it are out, the
    # folds on it are not counted out yet, because the decision at the start of
    # a street is made with everyone who reached it still in.
    folded = sum(
        1
        for index in range(street_index)
        for row in _action_rows(actions.get(STREETS[index].upper()))
        if _action_word(row) == "folds"
    )
    state: dict[str, Any] = {
        "street": STREETS[street_index],
        "street_index": street_index,
        "pot_type": _pot_type_from_preflop(preflop),
    }
    if players:
        state["players_in_hand"] = max(0, players - folded)
        state["multiway"] = state["players_in_hand"] >= 3
    return state


def _action_rows(rows: Any) -> list[Any]:
    """One street's actions as a list, whatever the parser stored there."""
    if rows is None or isinstance(rows, str):
        return []
    return [row for row in rows if row]


def _action_word(row: Any) -> str:
    """The verb of one action row (``("Anna", "raises", 400)``)."""
    if isinstance(row, (list, tuple)) and len(row) > 1:
        return str(row[1]).strip().casefold()
    return ""


def _pot_type_from_preflop(preflop: Sequence[Any]) -> str:
    """The shape the preflop round ended in, in the model's vocabulary.

    The same rule ``player_situations`` applies at the end of the round, read
    off the action stream: no raise with a call is a limped pot, one raise is a
    single raised pot, and so on. The pot shape does not move street to street,
    which is why it is the most useful thing a per-hand HUD can publish.
    """
    raises = sum(1 for row in preflop if _action_word(row) in ("raises", "completes"))
    calls = sum(1 for row in preflop if _action_word(row) == "calls")
    if raises == 0:
        return "limped" if calls else "unopened"
    if raises == 1:
        return "single_raised"
    if raises == 2:
        return "three_bet"
    return "four_bet_plus"


def _first(*values: Any) -> Any:
    """The first value that is not None: the feed's answer, else the row's."""
    for value in values:
        if value is not None:
            return value
    return None


def _boolean(raw: Any) -> bool | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().casefold()
    if text in ("true", "yes", "1", "on"):
        return True
    if text in ("false", "no", "0", "off"):
        return False
    return None


# --------------------------------------------------------------------------- #
# Rules.
# --------------------------------------------------------------------------- #


def filter_registry() -> Mapping[str, Any]:
    """The query engine's filter registry, imported lazily.

    A panel condition is validated against it, so the two vocabularies cannot
    drift: a name that selects a live panel is a name that selects a query.
    """
    from fpdb_3_legacy.analytics_query import FILTERS  # noqa: PLC0415 - keeps this module import-light

    return FILTERS


def condition_matches(name: str, expected: Any, context: HudSituationContext) -> bool:
    """Whether one condition holds for ``context``, by the filter's own kind.

    The semantics follow ``analytics_query``: a set matches equality or
    membership, a range is inclusive with either bound optional, ``*_pct``
    compares percentages against the basis-point column, a boolean is equality,
    and a label matches any word the situation carries.
    """
    spec = filter_registry().get(name)
    if spec is None:
        raise ValueError(f"Unknown panel condition {name!r}; known conditions: {sorted(filter_registry())}")
    actual = context.filters().get(name)
    kind = spec.kind
    if kind == "label":
        if actual is None:
            return False
        wanted = {_text(word) for word in _list(expected)}
        return bool(wanted & {_text(word) for word in actual})
    if kind in _RANGE_KINDS:
        return _range_matches(actual, expected, kind)
    if kind in ("bool", "hero"):
        return actual is not None and bool(actual) == bool(expected)
    if kind == "null_check":
        return (actual is None) != bool(expected)
    wanted = {_text(value) for value in _list(expected)}
    return actual is not None and _text(actual) in wanted


_RANGE_KINDS: Final = ("range", "range_pct", "range_low", "range_high")


def _range_matches(actual: Any, expected: Any, kind: str) -> bool:
    """An inclusive range condition, either bound optional."""
    if actual is None:
        return False
    low, high = _bounds(expected, kind)
    if low is not None and actual < low:
        return False
    return not (high is not None and actual > high)


def _bounds(expected: Any, kind: str) -> tuple[int | None, int | None]:
    """A range condition as inclusive bounds.

    A pair is ``[low, high]`` with either end optional; a bare number means
    ``["low only"]`` for a lower-bound filter (``range_low``) and the same as a
    pair otherwise. ``*_pct`` conditions are written in per cent and compared in
    basis points, exactly as the query engine converts them.
    """
    scale = 100 if kind == "range_pct" else 1
    if isinstance(expected, (list, tuple)) and len(expected) == 2:
        low = _number(expected[0])
        high = _number(expected[1])
    elif kind == "range_high":
        low, high = None, _number(expected)
    elif kind == "range_low":
        low, high = _number(expected), None
    else:
        low, high = _number(expected), None
    return (None if low is None else low * scale, None if high is None else high * scale)


@dataclass(frozen=True)
class PanelRule:
    """One "show this panel when..." rule, as data.

    ``when`` is a mapping in the query engine's filter vocabulary. Every entry
    must hold for the rule to match, and every name is validated against the
    engine's registry at load time, so a misspelled condition is refused rather
    than silently never matching.
    """

    panel: str
    rule_id: str = ""
    profile: str = "all"
    when: Mapping[str, Any] = field(default_factory=dict)
    min_sample: int = 0
    sample: str = "n"
    fallback: str = ""
    priority: int = 0
    enabled: bool = True
    substitutions: Mapping[str, str] = field(default_factory=dict)
    section: str = ""
    label: str = ""
    description: str = ""
    order: int = field(default=0, compare=False)

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any], order: int = 0) -> PanelRule:
        unknown = set(values) - _RULE_FIELDS
        if unknown:
            raise ValueError(f"Unknown panel rule field(s) {sorted(unknown)}; known: {sorted(_RULE_FIELDS)}")
        panel = str(values.get("panel", "")).strip()
        if not panel:
            raise ValueError("A panel rule needs a 'panel' name")
        when = values.get("when") or {}
        if not isinstance(when, Mapping):
            raise ValueError(f"Panel rule {panel!r}: 'when' must be a mapping of conditions")
        for name in when:
            spec = filter_registry().get(str(name))
            if spec is None:
                raise ValueError(
                    f"Panel rule {panel!r}: unknown condition {name!r}; "
                    f"known conditions: {sorted(filter_registry())}"
                )
        substitutions = values.get("substitutions") or {}
        if not isinstance(substitutions, Mapping):
            raise ValueError(f"Panel rule {panel!r}: 'substitutions' must be a mapping of position to panel")
        return cls(
            panel=panel,
            rule_id=str(values.get("id", "") or "").strip(),
            profile=_text(values.get("profile"), "all"),
            when={str(name): value for name, value in when.items()},
            min_sample=_number(values.get("min_sample")) or 0,
            sample=str(values.get("sample", "n") or "n"),
            fallback=str(values.get("fallback", "") or "").strip(),
            priority=int(values.get("priority", 0) or 0),
            enabled=_flag(values.get("enabled"), default=True),
            substitutions={_position_key(key): str(value) for key, value in substitutions.items()},
            section=str(values.get("section", "") or "").strip(),
            label=str(values.get("label", "") or "").strip(),
            description=str(values.get("description", "") or "").strip(),
            order=order,
        )

    def matches(self, context: HudSituationContext) -> bool:
        if not self.enabled:
            return False
        return all(condition_matches(name, expected, context) for name, expected in self.when.items())

    @property
    def specificity(self) -> int:
        """How many conditions this rule states: the first precedence key."""
        return len(self.when)

    def selector(self) -> tuple[Any, ...]:
        """The key two rules must share to be duplicates of one another."""
        return (self.profile, self.panel, tuple(sorted((name, _freeze(value)) for name, value in self.when.items())))

    def panel_for(self, context: HudSituationContext) -> str:
        """The panel this rule names, after position substitution.

        ``substitutions`` lets one rule serve several positions without being
        copied: a rule keyed on the flop with ``{"BB": "srp_bb_flop"}`` shows a
        blind-specific panel for the blind and its own name for everyone else.
        """
        if not self.substitutions:
            return self.panel
        position = context.normalized().position
        return self.substitutions.get(position, self.panel)

    def sample_value(self, context: HudSituationContext, samples: Mapping[str, Any] | None) -> int | None:
        """The sample this rule measures, from the seat's aggregate row."""
        if samples is None:
            return None
        for key in (self.sample, self.sample.casefold()):
            if key in samples:
                return _number(samples[key])
        return None

    def suppressed(self, context: HudSituationContext, samples: Mapping[str, Any] | None) -> bool:
        """True when the rule matches but its sample is below the threshold.

        The rule is the right rule and the seat is in the right spot; there is
        simply not enough history yet to draw a rate there. The panel is
        withheld (or its fallback shown), and the reason is reported, because a
        pane that silently vanishes is worse than one that says why.
        """
        if self.min_sample <= 0:
            return False
        value = self.sample_value(context, samples)
        if value is None:
            # No sample to consult is not a sample of zero: a rule that asks for
            # one cannot be checked, so it is withheld rather than guessed at.
            return True
        return value < self.min_sample

    def as_xml_attributes(self) -> dict[str, str]:
        """The rule as flat attributes, the shape the configuration reads.

        Non-scalar condition values are JSON-encoded, so a list or a two-ended
        range survives a write and a read; a scalar stays bare, so the XML is
        readable by hand.
        """
        attributes: dict[str, str] = {"panel": self.panel}
        if self.rule_id:
            attributes["id"] = self.rule_id
        if self.profile != "all":
            attributes["profile"] = self.profile
        for name, value in self.when.items():
            attributes[str(name)] = value if isinstance(value, str) else json.dumps(value)
        for name, value in (
            ("priority", self.priority or ""),
            ("min_sample", self.min_sample or ""),
            ("sample", "" if self.sample == "n" else self.sample),
            ("fallback", self.fallback),
            ("section", self.section),
            ("label", self.label),
        ):
            if value:
                attributes[name] = str(value)
        if not self.enabled:
            attributes["enabled"] = "false"
        if self.substitutions:
            attributes["substitutions"] = json.dumps(dict(self.substitutions))
        return attributes

    def as_dict(self) -> dict[str, Any]:
        """The rule back as data, so a saved file round-trips through a load."""
        payload: dict[str, Any] = {"panel": self.panel, "when": dict(self.when)}
        for key, value in (
            ("id", self.rule_id),
            ("profile", "" if self.profile == "all" else self.profile),
            ("fallback", self.fallback),
            ("sample", "" if self.sample == "n" else self.sample),
            ("section", self.section),
            ("label", self.label),
            ("description", self.description),
        ):
            if value:
                payload[key] = value
        if self.min_sample:
            payload["min_sample"] = self.min_sample
        if self.priority:
            payload["priority"] = self.priority
        if not self.enabled:
            payload["enabled"] = False
        if self.substitutions:
            payload["substitutions"] = dict(self.substitutions)
        return payload


def panel_rule_from_attributes(values: Mapping[str, Any], order: int = 0) -> PanelRule:
    """A rule from flat attributes: the rule's own fields, then conditions.

    This is what makes a rule hand-editable in ``HUD_config.xml``: the known
    rule fields are read as fields and *everything else* is a condition in the
    query engine's vocabulary, so ``<hud_panel_rule panel="srp_cbet_ip"
    street="flop" pot_type="single_raised"/>`` needs no nesting. A value is
    JSON-decoded when it parses as JSON, which is how a list, a boolean or a
    two-ended range is written in an attribute.
    """
    fields: dict[str, Any] = {}
    conditions: dict[str, Any] = {}
    for name, raw in values.items():
        if name == "when":
            decoded = _json_value(raw)
            if not isinstance(decoded, Mapping):
                raise ValueError(f"The 'when' attribute must be a JSON object, got {raw!r}")
            conditions.update({str(key): value for key, value in decoded.items()})
            continue
        if name in _RULE_FIELDS:
            # Every rule field but ``substitutions`` is a scalar, so an attribute
            # holds it as written; ``substitutions`` is a mapping and is written
            # as JSON (see ``as_xml_attributes``), so it has to be decoded back.
            fields[name] = _json_value(raw) if name == "substitutions" else raw
        else:
            conditions[name] = _json_value(raw)
    if conditions:
        fields["when"] = conditions
    return PanelRule.from_mapping(fields, order)


def _json_value(raw: Any) -> Any:
    """An attribute value: JSON when it is JSON, the raw string otherwise."""
    if not isinstance(raw, str):
        return raw
    text = raw.strip()
    if not text:
        return text
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return raw


def _position_key(raw: Any) -> str:
    """A substitution key: the canonical position code when it names one.

    ``substitutions`` maps *position* to panel, and a position has several
    spellings (``"B"``, ``"bb"``, ``"BB"``). The keys are canonicalised exactly
    as the context's own position is, so a rule written ``{"B": ...}`` fires for
    a big blind whose normalised position is ``"BB"`` -- otherwise the rule
    would load cleanly and then never match.
    """
    return normalize_position(raw) or _text(raw)


def _flag(value: Any, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().casefold() not in ("false", "no", "0", "off")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple(sorted((str(k), _freeze(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(_freeze(item) for item in value)
    return value


# --------------------------------------------------------------------------- #
# Selection.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PanelSelection:
    """Which panels are active right now, and why.

    ``panels`` is in display order (most specific rule first), ``rules`` is the
    deciding rule per panel -- ``runs`` is the same list filtered to the panels
    that are actually shown -- ``suppressed`` names the panels withheld for
    sample, and ``fallback`` is the panel used because no rule matched.
    """

    panels: tuple[str, ...] = ()
    rules: tuple[PanelRule, ...] = ()
    suppressed: tuple[str, ...] = ()
    fallback: str = ""
    profile: str = "all"
    context: HudSituationContext | None = None
    enabled: bool = True

    @property
    def rules_by_panel(self) -> dict[str, PanelRule]:
        """The deciding rule per shown panel."""
        return {rule.panel_for(self.context): rule for rule in self.rules} if self.context else {}

    def decided_by(self, panel: str) -> PanelRule | None:
        """The rule that put ``panel`` on screen, or None if none did."""
        for rule in self.rules:
            named = rule.panel_for(self.context) if self.context else rule.panel
            if named == panel:
                return rule
        return None

    def contains(self, panel: str) -> bool:
        """Whether a panel (or its substituted name) is active."""
        return _text(panel) in {_text(name) for name in self.panels}

    def with_panels(self, panels: Iterable[str]) -> PanelSelection:
        return replace(self, panels=tuple(panels))

    def describe(self) -> str:
        if not self.enabled:
            return "dynamic panels disabled"
        shown = ", ".join(self.panels) or "(none)"
        parts = [f"panels: {shown}"]
        if self.fallback:
            parts.append(f"fallback: {self.fallback}")
        if self.suppressed:
            parts.append(f"withheld for sample: {', '.join(self.suppressed)}")
        return " | ".join(parts)


@dataclass(frozen=True)
class PanelChange:
    """What a context transition did to the visible panels.

    ``added`` and ``removed`` are exactly the panels that must redraw: the HUD
    re-renders those and leaves the rest alone, which is what keeps a live
    context change from flickering the whole grid.
    """

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    unchanged: tuple[str, ...] = ()

    @property
    def changed(self) -> tuple[str, ...]:
        return self.added + self.removed

    @property
    def dirty(self) -> bool:
        return bool(self.added or self.removed)

    def describe(self) -> str:
        if not self.dirty:
            return "unchanged"
        parts = []
        if self.added:
            parts.append(f"+{', '.join(self.added)}")
        if self.removed:
            parts.append(f"-{', '.join(self.removed)}")
        return " ".join(parts)


def diff_selections(previous: PanelSelection | None, current: PanelSelection) -> PanelChange:
    """The panels that differ between two selections.

    Works on the shown panels only, so a change of *rule* that keeps the same
    panel on screen is not a redraw -- the panel is already correct.
    """
    before = set(previous.panels) if previous is not None else set()
    after = set(current.panels)
    order = {name: index for index, name in enumerate(current.panels)}
    added = tuple(sorted(after - before, key=lambda name: order.get(name, 0)))
    removed = tuple(sorted(before - after))
    unchanged = tuple(sorted(before & after, key=lambda name: order.get(name, 0)))
    return PanelChange(added=added, removed=removed, unchanged=unchanged)


def profile_matches(scope: str, wanted: str) -> bool:
    """Whether a rule scoped to ``scope`` belongs to the profile ``wanted``.

    ``all`` (and an unset scope) means every profile: a rule with no scope is a
    rule about the hand, not about the HUD layout it happens to be shown in.
    """
    return scope in ("all", "", wanted)


class HudSituationResolver:
    """Which panels to show, from the live context.

    Precedence: a panel named by a matching rule, ordered by specificity (most
    conditions first), then by explicit priority, then by file order -- the same
    shape as ``HudProfileResolver``, so a hand-edited configuration behaves the
    way it reads. When nothing matches, the resolver's ``fallback`` panel shows,
    which is how a table never ends up with an empty seat.
    """

    def __init__(
        self,
        rules: Iterable[PanelRule] = (),
        *,
        fallback: str = "",
        enabled: bool = True,
    ) -> None:
        self.rules = list(rules)
        self.fallback = fallback
        self.enabled = enabled

    def for_profile(self, profile: str | None) -> HudSituationResolver:
        """This resolver restricted to one HUD profile.

        Table/profile selection is ``HudProfileResolver``'s job; this only
        narrows *which panel rules* the chosen profile has enabled, which is the
        per-profile enable/disable the issue asks for.
        """
        wanted = _text(profile, "all")
        return HudSituationResolver(
            [rule for rule in self.rules if self._profile_matches(rule.profile, wanted)],
            fallback=self.fallback,
            enabled=self.enabled,
        )

    def is_enabled(self, profile: str | None = None) -> bool:
        """False when dynamic panels are off, or the profile has no rules."""
        if not self.enabled:
            return False
        if profile is None:
            return bool(self.rules)
        return bool(self.for_profile(profile).rules)

    @staticmethod
    def _profile_matches(scope: str, wanted: str) -> bool:
        return profile_matches(scope, wanted)

    def matching_rules(self, context: HudSituationContext, profile: str | None = None) -> list[PanelRule]:
        """Every enabled rule that matches, in precedence order."""
        resolver = self if profile is None else self.for_profile(profile)
        matches = [rule for rule in resolver.rules if rule.matches(context)]
        return sorted(matches, key=lambda rule: (-rule.specificity, -rule.priority, rule.order))

    def resolving_rule(self, context: HudSituationContext, profile: str | None = None) -> PanelRule | None:
        """The single winning rule, for callers that show only one panel.

        Exposed separately from :meth:`resolve` so a preview can show *which*
        rule decided, using the same precedence the HUD uses rather than a
        second implementation of it.
        """
        matches = self.matching_rules(context, profile)
        return matches[0] if matches else None

    def resolve(
        self,
        context: HudSituationContext,
        profile: str | None = None,
        *,
        samples: Mapping[str, Any] | None = None,
    ) -> PanelSelection:
        """The active panels for ``context``.

        ``samples`` is the seat's aggregate row (the HUD's ``stat_dict`` entry),
        consulted by a rule's ``min_sample``. A rule that matches but is below
        its threshold contributes its ``fallback`` panel, if it names one, and
        its panel is reported in ``suppressed`` either way.
        """
        resolver = self if profile is None else self.for_profile(profile)
        if not resolver.enabled or not resolver.rules:
            return PanelSelection(profile=_text(profile, "all"), context=context.normalized(), enabled=False)

        panels: list[str] = []
        rules: list[PanelRule] = []
        suppressed: list[str] = []
        for rule in resolver.matching_rules(context, profile):
            panel = rule.panel_for(context)
            if rule.suppressed(context, samples):
                suppressed.append(panel)
                if rule.fallback and rule.fallback not in panels:
                    panels.append(rule.fallback)
                    rules.append(replace(rule, panel=rule.fallback, substitutions={}))
                continue
            if panel not in panels:
                panels.append(panel)
                rules.append(rule)

        fallback = ""
        if not panels and resolver.fallback:
            fallback = resolver.fallback
            panels.append(fallback)
        return PanelSelection(
            panels=tuple(panels),
            rules=tuple(rules),
            suppressed=tuple(dict.fromkeys(suppressed)),
            fallback=fallback,
            profile=_text(profile, "all"),
            context=context.normalized(),
        )

    def duplicate_selectors(self) -> list[tuple[Any, ...]]:
        """Selectors two rules share, which means one can never win."""
        seen: set[tuple[Any, ...]] = set()
        duplicates: list[tuple[Any, ...]] = []
        for rule in self.rules:
            selector = rule.selector()
            if selector in seen and selector not in duplicates:
                duplicates.append(selector)
            seen.add(selector)
        return duplicates


class PanelState:
    """Which panels each seat currently shows, and what changed since last time.

    The HUD calls :meth:`update` whenever the live context moves. It returns the
    selection and a :class:`PanelChange` naming only the panels that appeared or
    disappeared, so the renderer redraws those and nothing else. Window
    positions are never read or written here: a panel that becomes visible
    appears where the player already put that block.
    """

    def __init__(self, resolver: HudSituationResolver, profile: str | None = None) -> None:
        self.resolver = resolver
        self.profile = profile
        self._selections: dict[Any, PanelSelection] = {}
        self._contexts: dict[Any, HudSituationContext] = {}

    def context_for(self, key: Any) -> HudSituationContext | None:
        return self._contexts.get(key)

    def selection_for(self, key: Any) -> PanelSelection | None:
        return self._selections.get(key)

    def active_panels(self, key: Any) -> tuple[str, ...]:
        """The panels a seat is showing right now."""
        selection = self._selections.get(key)
        return selection.panels if selection else ()

    def update(
        self,
        key: Any,
        context: HudSituationContext,
        *,
        samples: Mapping[str, Any] | None = None,
        profile: str | None = None,
    ) -> tuple[PanelSelection, PanelChange]:
        """Resolve ``context`` for ``key`` and report what changed.

        A seat whose context is identical to last time is a no-op: the same
        selection, an empty change. That is what makes repeated HUD refreshes
        within one street free.
        """
        profile = self.profile if profile is None else profile
        context = context.normalized()
        previous = self._selections.get(key)
        if previous is not None and self._contexts.get(key) == context:
            current = self.resolver.resolve(context, profile, samples=samples)
            if current == previous:
                return current, PanelChange(unchanged=current.panels)
        current = self.resolver.resolve(context, profile, samples=samples)
        self._selections[key] = current
        self._contexts[key] = context
        return current, diff_selections(previous, current)

    def forget(self, key: Any = None) -> None:
        """Drop one seat's memory, or every seat's, after a profile switch."""
        if key is None:
            self._selections.clear()
            self._contexts.clear()
            return
        self._selections.pop(key, None)
        self._contexts.pop(key, None)


# --------------------------------------------------------------------------- #
# Rendering helpers.
# --------------------------------------------------------------------------- #


def panel_matches_block(panel: str, block: Mapping[str, Any]) -> bool:
    """Whether a panel name refers to a rendered block.

    A panel is matched against the block's ``id``, its ``label`` and its
    position binding, case-insensitively, so a rule can name a block however the
    configuration spells it and never has to know which of the three it used.
    """
    wanted = _text(panel)
    if not wanted:
        return False
    candidates = (
        block.get("id", ""),
        block.get("label", ""),
        block.get("position", ""),
        block.get("name", ""),
    )
    return any(_text(candidate) == wanted for candidate in candidates)


def block_visible_for(block: Mapping[str, Any], selection: PanelSelection | None, player_position: Any) -> bool:
    """Whether a block should be visible, given a dynamic selection.

    With no dynamic selection the block keeps the position-bound behaviour it
    always had. With one:

    * a block the selection names is shown, whatever its position binding says
      (the rule already describes the spot);
    * a block the selection does not name keeps the old position rule, so the
      static core of the HUD is untouched by turning dynamic panels on.
    """
    position_visible = block_visible(str(block.get("position", "") or ""), player_position)
    if selection is None or not selection.enabled:
        return position_visible
    for panel in selection.panels:
        if panel_matches_block(panel, block):
            return True
    return position_visible


# --------------------------------------------------------------------------- #
# Loading.
# --------------------------------------------------------------------------- #


def parse_rules(document: Any, source: str = "") -> tuple[list[PanelRule], str]:
    """The rules and the fallback panel of one panel document."""
    if not isinstance(document, Mapping):
        _fail("A panel document must be a JSON object", source)
    version = document.get("schema_version", PANEL_SCHEMA_VERSION)
    if not isinstance(version, int) or isinstance(version, bool):
        _fail(f"schema_version must be an integer, got {version!r}", source)
    if version > PANEL_SCHEMA_VERSION:
        _fail(
            f"panel schema {version} is newer than {PANEL_SCHEMA_VERSION}; "
            "upgrade fpdb-3 rather than reading it half-way",
            source,
        )
    raw_rules = document.get("rules", [])
    if not isinstance(raw_rules, list):
        _fail("'rules' must be a list", source)
    rules = [PanelRule.from_mapping(entry, order) for order, entry in enumerate(raw_rules)]
    fallback = str(document.get("fallback", "") or "").strip()
    return rules, fallback


def load_rules(path: str | Path) -> tuple[list[PanelRule], str]:
    """Every rule in one ``.json`` file, validated."""
    source = Path(path)
    return parse_rules(json.loads(source.read_text(encoding="utf-8")), str(source))


def default_rules_dir() -> Path:
    """The packaged panel-rule library."""
    return Path(__file__).resolve().parent / "hud_situation.d"


def load_directory(directory: str | Path) -> tuple[list[PanelRule], str]:
    """Every rule in every ``.json`` file of a directory, name-sorted.

    Rules are ordered across files so the resolver's file-order tie-break is
    deterministic no matter which filesystem handed the names over.
    """
    root = Path(directory)
    if not root.is_dir():
        return [], ""
    rules: list[PanelRule] = []
    fallback = ""
    for path in sorted(root.glob("*.json")):
        loaded, file_fallback = load_rules(path)
        rules.extend(loaded)
        fallback = fallback or file_fallback
    return number_rules(rules), fallback


def load_source(source: str | Path) -> tuple[list[PanelRule], str]:
    """Every rule of one source: a directory, a file, or the shipped library.

    ``"builtin"`` names the packaged library, which is what a configuration
    writes to turn the shipped rules on without copying nineteen rules into the
    user's file; anything else is a path, a directory being read file by file.
    A path that does not exist is an error rather than an empty rule set, so a
    typo in ``source`` is reported instead of silently disabling the panels.
    """
    text = str(source).strip()
    if text.casefold() == BUILTIN_SOURCE:
        return load_directory(default_rules_dir())
    if text.casefold() == PLO_BUILTIN_SOURCE:
        rules, fallback = load_directory(default_rules_dir())
        plo_rules = [replace(rule, min_sample=0) for rule in rules]
        # Limped Omaha pots have no raised-pot role to select a specific
        # panel. Give each street a useful overview without also drawing it
        # over a specific raised-pot panel (the resolver can show many panels).
        for street in ("flop", "turn", "river"):
            plo_rules.append(PanelRule.from_mapping({
                "panel": f"postflop_{street}",
                "id": f"plo-general-{street}",
                "when": {"street": street, "pot_type": "limped"},
                "priority": -100,
                "section": "postflop",
                "label": f"{street.title()} overview",
            }, order=len(plo_rules)))
        return plo_rules, fallback
    if not text:
        return [], ""
    return load_directory(text) if Path(text).is_dir() else load_rules(text)


def load_default_resolver(extra_dirs: Iterable[str | Path] = ()) -> HudSituationResolver:
    """The bundled rules plus every ``.json`` in ``extra_dirs``."""
    rules, fallback = load_directory(default_rules_dir())
    for directory in extra_dirs:
        extra, extra_fallback = load_directory(directory)
        rules.extend(extra)
        fallback = fallback or extra_fallback
    return HudSituationResolver(number_rules(rules), fallback=fallback)


def scope_rules(rules: Iterable[PanelRule], profile: str) -> list[PanelRule]:
    """Re-scope unscoped rules to one HUD profile.

    Used when a configuration enables the shipped library for a single profile
    (``<hud_panel_rules source="builtin" profile="..."/>``): the library's own
    rules carry no scope, and turning a whole nineteen-rule library into a
    per-profile one must not require copying it into the user's file. A rule
    that already names a profile keeps it -- an explicit scope is a statement
    about that rule, not a default to be overridden.
    """
    wanted = _text(profile, "all")
    return [rule if rule.profile != "all" else replace(rule, profile=wanted) for rule in rules]


def number_rules(rules: Iterable[PanelRule]) -> list[PanelRule]:
    """Renumber rules in sequence, so file order is the order they were read.

    The last tie-break in the resolver is file order, so it has to be a number
    even when the rules came from several files or were appended to the shipped
    library -- otherwise two sources would both claim order 0.
    """
    return [replace(rule, order=order) for order, rule in enumerate(rules)]


def save_rules(
    rules: Iterable[PanelRule],
    path: str | Path,
    *,
    fallback: str = "",
) -> Path:
    """Write rules as a validated document (save-then-load round trips)."""
    target = Path(path)
    document = {
        "schema_version": PANEL_SCHEMA_VERSION,
        "fallback": fallback,
        "rules": [rule.as_dict() for rule in rules],
    }
    parsed, parsed_fallback = parse_rules(document, str(target))
    if parsed_fallback != fallback:
        _fail("the fallback panel did not survive validation", str(target))
    target.write_text(json.dumps(document, indent=2, default=str) + "\n", encoding="utf-8")
    return target


class RuleWarning(NamedTuple):
    """One thing a rule set loads with but cannot do what it says.

    ``rule`` is the offending rule when the warning is about one (a duplicate is
    about a pair), and ``severity`` tells a caller whether it is a mistake
    (``duplicate``: one of the two can never win) or a suspicion (``warning``).
    """

    rule: PanelRule | None
    severity: str
    message: str


def rule_warnings(resolver: HudSituationResolver, panels: Iterable[str] = ()) -> tuple[RuleWarning, ...]:
    """Warnings for a rule set, each attributed to the rule it is about.

    A warning is never a refusal -- a panel that is merely suspicious may still
    be what the author meant. The three that matter:

    * a panel named by a rule that no known block carries (a typo that would
      show nothing);
    * a ``min_sample`` rule whose fallback is itself;
    * two rules with the same selector, where one can never win.

    Attribution is the point of the typed form: an editor has to mark the row a
    warning is about, and a message string is not a place to keep that.
    """
    warnings: list[RuleWarning] = []
    known = {_text(panel) for panel in panels}
    for rule in resolver.rules:
        if known and not any(
            panel_matches_block(rule.panel, {"id": panel}) or _text(panel) == _text(rule.panel) for panel in known
        ):
            warnings.append(
                RuleWarning(rule, "warning", f"panel {rule.panel!r} (rule {_rule_name(rule)}) is not a known block")
            )
        if rule.fallback and _text(rule.fallback) == _text(rule.panel):
            warnings.append(RuleWarning(rule, "warning", f"rule {_rule_name(rule)} falls back to its own panel {rule.panel!r}"))
        if rule.min_sample <= 0 and rule.fallback:
            warnings.append(
                RuleWarning(rule, "warning", f"rule {_rule_name(rule)} names a fallback but has no min_sample")
            )
    for selector in resolver.duplicate_selectors():
        for rule in resolver.rules:
            if rule.selector() == selector:
                warnings.append(
                    RuleWarning(
                        rule,
                        "duplicate",
                        f"rule {_rule_name(rule)} duplicates another rule: only the first can ever win",
                    )
                )
    return tuple(warnings)


def validate_rules(resolver: HudSituationResolver, panels: Iterable[str] = ()) -> tuple[str, ...]:
    """The messages of :func:`rule_warnings`, for a report that only prints."""
    return tuple(warning.message for warning in rule_warnings(resolver, panels))


def _rule_name(rule: PanelRule) -> str:
    return rule.rule_id or f"{rule.panel}@{rule.order}"
