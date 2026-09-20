"""Action-by-action live context for the dynamic HUD panels (#336).

The dynamic-panel layer (#298) decides *which panels a seat shows* from a
:class:`~fpdb_3_legacy.hud_situation.HudSituationContext`. In the classic path
that context comes from the last *assembled* hand, so a table that can only tell
fpdb about completed hands can never describe the decision in front of a player
*now* -- it describes the hand one behind.

This module is the missing half: a room-independent contract for what a live
feed knows as actions arrive, adapters that fill it from a room's own event
stream, and a session that publishes it into the HUD through the hook that
already exists (``Hud.set_live_state``). It deliberately adds **no** second
resolver: the context it publishes is consumed by
:meth:`HudSituationContext.from_stat_dict` and the same
:class:`HudSituationResolver` every other path uses.

Two things it refuses to do
---------------------------

* **Invent.** Every field of :class:`LiveContext` is optional, and a fact the
  feed has not stated stays absent. Absent is what makes the existing per-row
  fallback (``hud_situation.entry_facts``) answer for a seat instead of a guess
  answering for it. :func:`context_to_live_state` therefore emits only the keys
  it actually knows.
* **Leak.** A context belongs to one hand: :meth:`ActionStreamAdapter.reset` is
  called when a new hand starts, and an action stamped with another hand is
  ignored rather than folded into this one. Duplicate and out-of-order events
  (a replayed segment, a repeated seat snapshot) are dropped by sequence, so the
  panel state never moves backwards.

What is action-live and what is not
-----------------------------------

:data:`SOURCE_ACTION_STREAM` means the panels can follow the current decision;
:data:`SOURCE_HAND_REFRESH` means they are based on the latest assembled hand.
:func:`describe_source` is what the UI and the docs say out loud, so a source
that cannot provide actions is never shown as if it could.

Units and the shipped rules: ``docs/live-context.md``.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from .loggingFpdb import get_logger

log = get_logger("hud_live_context")

#: The panels can follow the decision the table is actually in.
SOURCE_ACTION_STREAM: Final = "action_stream"
#: The panels are based on the latest assembled/imported hand.
SOURCE_HAND_REFRESH: Final = "hand_refresh"

#: The streets, in the order a hand walks them (``hud_situation.STREETS``).
STREETS: Final[tuple[str, ...]] = ("preflop", "flop", "turn", "river")
_STREET_INDEX: Final[dict[str, int]] = {street: index for index, street in enumerate(STREETS)}

#: The pot shapes ``player_situations.POT_*`` names, by the number of preflop
#: raises that produced them. Level one is a single raise, two a 3-bet, three or
#: more a 4-bet-plus.
_POT_BY_RAISE_LEVEL: Final[dict[int, str]] = {
    0: "unopened",
    1: "single_raised",
    2: "three_bet",
    3: "four_bet_plus",
}

#: Actions that put money in and are not a call: they raise the street's high
#: water mark, so they are the actions that make a seat "the aggressor".
_AGGRESSIVE: Final[frozenset[str]] = frozenset({"bets", "raises"})
#: Actions that remove the seat from the hand.
_FOLDING: Final[frozenset[str]] = frozenset({"folds"})

_UNKNOWN: Final = "unknown"


def describe_source(source: str) -> str:
    """The product-facing sentence for how fresh a source's context is."""
    if source == SOURCE_ACTION_STREAM:
        return "Live context available: panels follow the current decision."
    return "Hand-refresh context: panels follow the latest assembled hand."


def is_action_live(source: str) -> bool:
    """Whether panels built from ``source`` may claim action-by-action freshness."""
    return source == SOURCE_ACTION_STREAM


def _cents(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# The action, normalized above the adapter boundary.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LiveAction:
    """One action the room announced, in the vocabulary every adapter speaks.

    ``sequence`` is the source's own ordering -- an event timestamp or a counter
    -- and is what makes a replay or a repeated snapshot idempotent rather than a
    second bet. ``to_cents`` is a raise-to total where the room gives one and
    ``amount_cents`` is the chips this action adds otherwise, matching how
    ``Hand`` spells the two.
    """

    actor: str
    action: str
    street: str = "preflop"
    amount_cents: int = 0
    to_cents: int | None = None
    all_in: bool = False
    hand_id: str = ""
    sequence: int = 0

    def normalized_street(self) -> str:
        street = str(self.street or "").strip().lower()
        return street if street in _STREET_INDEX else "preflop"

    def committed_cents(self) -> int:
        """The chips this action adds to the actor's street commitment."""
        if self.action in _AGGRESSIVE:
            return self.to_cents if self.to_cents is not None else self.amount_cents
        return self.amount_cents


# ---------------------------------------------------------------------------
# The context every source fills.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LiveContext:
    """What a live feed knows about the decision, with unknown kept explicit.

    Every field is optional: a source that cannot state the board says nothing
    about it, and nothing is inferred. ``to_situation`` is the projection onto
    the canonical model the resolver consumes, so the live path and the classic
    path cannot drift.
    """

    source: str = SOURCE_ACTION_STREAM
    hand_id: str = ""
    table: str = ""

    # -- table shape -------------------------------------------------------
    site: str = ""
    game: str = ""
    limit: str = ""
    seats: int = 0
    tournament: bool | None = None

    # -- the decision ------------------------------------------------------
    street: str = ""
    street_index: int = 0
    players_in_hand: int = 0
    pot_before_cents: int = 0
    to_call_cents: int = 0

    # -- the aggressors ----------------------------------------------------
    actor: str = ""
    last_aggressive_action: str = ""
    aggressor: str = ""
    preflop_aggressor: str = ""
    pot_type: str = ""
    raise_level: int = 0

    # -- per-seat facts ----------------------------------------------------
    positions: Mapping[str, str] = field(default_factory=dict)
    stacks_bb: Mapping[str, int] = field(default_factory=dict)
    effective_stack_bb: int = 0
    all_in_seats: tuple[str, ...] = ()

    # -- unknowns, named so a log or a UI can say what is missing ----------
    unknown: tuple[str, ...] = ()

    def to_situation(self) -> Any:
        """The canonical :class:`HudSituationContext` for the resolver."""
        from fpdb_3_legacy import hud_situation

        return hud_situation.HudSituationContext(
            site=self.site or "all",
            game=self.game or "all",
            limit=self.limit or "all",
            seats=self.seats,
            players=self.players_in_hand,
            tournament=bool(self.tournament),
            street=self.street or "preflop",
            street_index=self.street_index,
            pot_type=self.pot_type,
            players_in_hand=self.players_in_hand,
            multiway=self.players_in_hand > 2,
            effective_stack_bb=self.effective_stack_bb,
            is_preflop_aggressor=bool(self.preflop_aggressor),
            # ``facing_action`` is deliberately *not* set: it is what one seat
            # faces, and a context is table-wide, so applying the last aggressive
            # action to every seat would be a per-seat guess. The seat's own row
            # answers it (hud_situation.entry_facts).
        )

    def describe(self) -> str:
        """One line naming the decision, for a log or a debug panel."""
        parts = [
            f"street={self.street or _UNKNOWN}",
            f"pot={self.pot_type or _UNKNOWN}",
            f"players={self.players_in_hand or _UNKNOWN}",
            f"actor={self.actor or _UNKNOWN}",
        ]
        if self.aggressor:
            parts.append(f"aggressor={self.aggressor}")
        if self.unknown:
            parts.append(f"unknown={','.join(self.unknown)}")
        return " ".join(parts)


def context_to_live_state(context: LiveContext) -> dict[str, Any]:
    """The ``Hud.live_state`` keys a context actually knows.

    Only stated facts are emitted. A key left out is read by the resolver as
    *absent*, which is what lets the seat's own aggregate row answer for it --
    the fallback the issue asks for.
    """
    state: dict[str, Any] = {
        "street": context.street or "preflop",
        "street_index": context.street_index,
        "source": context.source,
    }
    optional: dict[str, Any] = {
        "site": context.site,
        "game": context.game,
        "limit": context.limit,
        "seats": context.seats,
        "tournament": context.tournament,
        "pot_type": context.pot_type,
        "players_in_hand": context.players_in_hand,
        "aggressor": context.aggressor,
        "preflop_aggressor": context.preflop_aggressor,
        "effective_stack_bb": context.effective_stack_bb,
    }
    for key, value in optional.items():
        if value is None or value == "":
            continue
        # A stated ``False`` is a fact (this is a ring game), so it is published;
        # a numeric zero is the absence of a fact, so it is not. ``bool`` is an
        # ``int`` in Python, which is exactly why this is spelled out.
        if value == 0 and not isinstance(value, bool):
            continue
        state[key] = value
    if context.players_in_hand:
        state["multiway"] = context.players_in_hand > 2
    return state


# ---------------------------------------------------------------------------
# The adapter: an action stream becomes a context.
# ---------------------------------------------------------------------------


@dataclass
class ActionStreamAdapter:
    """Folds one hand's actions into a :class:`LiveContext`, idempotently.

    One adapter follows one hand. :meth:`reset` is how a new hand starts, and an
    action stamped with a different hand is refused, so live state cannot cross
    a hand boundary. Sequence numbers make a replayed or repeated event a no-op.
    """

    hand_id: str = ""
    table: str = ""
    site: str = ""
    game: str = ""
    limit: str = ""
    seats: int = 0
    tournament: bool | None = None
    positions: dict[str, str] = field(default_factory=dict)
    stacks_bb: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._street = "preflop"
        self._street_index = 0
        self._pot_cents = 0
        self._to_call_cents = 0
        self._raises = 0
        self._limped = False
        self._aggressor = ""
        self._preflop_aggressor = ""
        self._last_aggressive_action = ""
        self._actor = ""
        self._active: set[str] = set()
        self._folded: set[str] = set()
        self._all_in: set[str] = set()
        self._last_sequence = -1
        self._seen: set[int] = set()
        self._ignored = 0
        self._street_commits: dict[str, int] = {}

    # -- lifecycle ----------------------------------------------------------

    def note_seat(self, actor: str, *, position: str = "", stack_bb: int = 0) -> None:
        """Record a seat seen at the table, so folds can be counted out of it."""
        actor = str(actor or "").strip()
        if not actor:
            return
        if actor not in self._active and actor not in self._folded:
            self._active.add(actor)
        if position:
            self.positions[actor] = position
        if stack_bb:
            self.stacks_bb[actor] = int(stack_bb)

    def reset(self, hand_id: str = "", *, seats: Iterable[str] = ()) -> None:
        """Start a new hand: nothing of the previous one survives."""
        self.hand_id = str(hand_id or "")
        self._street = "preflop"
        self._street_index = 0
        self._pot_cents = 0
        self._to_call_cents = 0
        self._raises = 0
        self._limped = False
        self._aggressor = ""
        self._preflop_aggressor = ""
        self._last_aggressive_action = ""
        self._actor = ""
        self._active = {str(seat) for seat in seats}
        self._folded = set()
        self._all_in = set()
        self._last_sequence = -1
        self._seen = set()
        self._ignored = 0
        self._street_commits = {}

    # -- folding ------------------------------------------------------------

    def apply(self, action: LiveAction) -> LiveContext | None:
        """Fold one action in, or answer ``None`` when it must be ignored.

        ``None`` means the action belonged to another hand, repeated a sequence
        already folded, or named an empty actor -- all of which are dropped
        rather than guessed at, because the panel state must never move
        backwards on a resync.
        """
        if action.hand_id and self.hand_id and action.hand_id != self.hand_id:
            self._ignored += 1
            log.debug("Live action for hand %s ignored: this adapter follows %s", action.hand_id, self.hand_id)
            return None
        actor = str(action.actor or "").strip()
        if not actor:
            self._ignored += 1
            return None
        if not self._accept_sequence(action.sequence):
            self._ignored += 1
            return None

        self._enter_street(action.normalized_street())
        self._actor = actor
        if actor not in self._active and actor not in self._folded:
            self._active.add(actor)
        street_to_before = self._to_call_cents
        prior_commit = self._street_commit(actor)
        committed = action.committed_cents()
        self._pot_cents += max(committed - prior_commit, 0)
        self._commit(actor, committed)

        kind = action.action
        if kind == "raises" and not self._last_aggressive_action and street_to_before <= prior_commit:
            # A room that calls a raise "RAISE" without saying whether anyone had
            # bet: with nobody ahead of it on this street it is an opening bet,
            # which is what the hand builder's own reader concludes too.
            kind = "bets"

        if kind in _FOLDING:
            self._fold(actor)
        elif kind in _AGGRESSIVE:
            self._raise(actor, kind)
        elif kind == "calls" and self._street == "preflop" and not self._raises:
            # Calling the big blind with nobody raised is a limp, which is the
            # pot shape the shipped rules call ``limped``.
            self._limped = True
        if action.all_in:
            self._all_in.add(actor)
        return self.context

    def _accept_sequence(self, sequence: int) -> bool:
        """Whether an event's sequence has not been folded yet.

        A ``0`` sequence means the source gave no ordering, so the event is
        trusted; that is the case for a builder that replays rows in order.
        """
        if not sequence:
            return True
        if sequence in self._seen:
            log.debug("Live action sequence %s ignored: duplicate", sequence)
            return False
        if sequence <= self._last_sequence:
            log.debug("Live action sequence %s ignored: out of order", sequence)
            return False
        self._seen.add(sequence)
        self._last_sequence = sequence
        return True

    def _enter_street(self, street: str) -> None:
        if street == self._street:
            return
        index = _STREET_INDEX[street]
        if index < self._street_index:
            # A capture that began mid-hand, or a replayed preflop packet after
            # the flop: the street the table is on cannot go backwards.
            log.debug("Live street %s ignored: the table is already on %s", street, self._street)
            return
        self._street = street
        self._street_index = index
        self._to_call_cents = 0
        self._last_aggressive_action = ""
        self._aggressor = ""
        # ``_limped`` is a preflop pot shape, so it survives the street change:
        # a limped pot is still limped on the flop, and the shipped rules have a
        # panel for exactly that.
        if index > 0:
            # A new street starts with nobody having bet it yet.
            self._street_commits.clear()

    def _commit(self, actor: str, total: int) -> None:
        self._street_commits[actor] = total
        if total > self._to_call_cents:
            self._to_call_cents = total

    def _street_commit(self, actor: str) -> int:
        return self._street_commits.get(actor, 0)

    def _raise(self, actor: str, kind: str) -> None:
        self._last_aggressive_action = kind
        self._aggressor = actor
        if self._street == "preflop":
            self._raises += 1
            # The last player to put in a raise preflop is the preflop aggressor,
            # whether the room spelled that opening raise a bet or a raise.
            self._preflop_aggressor = actor

    def _fold(self, actor: str) -> None:
        self._active.discard(actor)
        self._folded.add(actor)

    # -- output -------------------------------------------------------------

    def _pot_type(self) -> str:
        """The preflop shape, on every street.

        The pot type is decided preflop and then carries: a three-bet pot is a
        three-bet pot on the river. Deriving it from the preflop raise level (and
        the limp) on every street is what lets a postflop rule ask for it.
        """
        if self._raises:
            return _POT_BY_RAISE_LEVEL.get(min(self._raises, 3), "four_bet_plus")
        return "limped" if self._limped else "unopened"

    def _unknown(self) -> tuple[str, ...]:
        missing = []
        if not self.seats:
            missing.append("seats")
        if not self.site:
            missing.append("site")
        if not self.game:
            missing.append("game")
        if self._street != "preflop" and not self.effective_stack_bb():
            missing.append("effective_stack_bb")
        if not self.positions:
            missing.append("positions")
        return tuple(missing)

    def effective_stack_bb(self) -> int:
        """The shortest live stack, in big blinds, when one is known."""
        stacks = [stack for actor, stack in self.stacks_bb.items() if actor in self._active and stack > 0]
        return min(stacks) if stacks else 0

    @property
    def context(self) -> LiveContext:
        """The decision as the actions so far describe it."""
        return LiveContext(
            source=SOURCE_ACTION_STREAM,
            hand_id=self.hand_id,
            table=self.table,
            site=self.site,
            game=self.game,
            limit=self.limit,
            seats=self.seats,
            tournament=self.tournament,
            street=self._street,
            street_index=self._street_index,
            players_in_hand=len(self._active),
            pot_before_cents=self._pot_cents,
            to_call_cents=self._to_call_cents,
            actor=self._actor,
            last_aggressive_action=self._last_aggressive_action,
            aggressor=self._aggressor,
            preflop_aggressor=self._preflop_aggressor,
            pot_type=self._pot_type(),
            raise_level=self._raises,
            positions=dict(self.positions),
            stacks_bb=dict(self.stacks_bb),
            effective_stack_bb=self.effective_stack_bb(),
            all_in_seats=tuple(sorted(self._all_in)),
            unknown=self._unknown(),
        )


# ---------------------------------------------------------------------------
# Adapters from a room's own stream.
# ---------------------------------------------------------------------------


def actions_from_normalized(actions: Iterable[Mapping[str, Any]], *, hand_id: str = "") -> Iterator[LiveAction]:
    """Adapt the hand-builder's own normalized action rows to the contract.

    The room-independent shape ``{"type", "player", "street", "amount"/"to"}``
    is what :func:`coinpoker_hand_builder._explicit_betting_actions` already
    produces and what the assembled hand stores, so every builder fpdb has can
    feed the contract without a second parser.
    """
    # Sequenced from 1: the adapter reads a ``0`` sequence as "the source gave no
    # ordering" and trusts the event, so starting at 0 would make the first
    # action of every replay un-deduplicable while the rest matched.
    for sequence, row in enumerate(actions, start=1):
        yield normalized_action(row, hand_id=hand_id, sequence=sequence)


def normalized_action(row: Mapping[str, Any], *, hand_id: str = "", sequence: int = 0) -> LiveAction:
    """One builder-shaped action row as a :class:`LiveAction`."""
    kind = str(row.get("type") or "").strip().lower()
    amount = _cents(row.get("amount"))
    to_value = row.get("to")
    return LiveAction(
        actor=str(row.get("player") or "").strip(),
        action=kind,
        street=str(row.get("street") or "preflop"),
        amount_cents=amount,
        to_cents=_cents(to_value) if to_value is not None else None,
        all_in=kind in {"all in", "allin", "all_in"},
        hand_id=hand_id,
        sequence=sequence,
    )


#: CoinPoker's authoritative action record, by the field it arrives in.
_COINPOKER_ACTION_FIELDS: Final[tuple[str, ...]] = ("newPlayerAction", "action")


def coinpoker_action(record: Mapping[str, Any], *, hand_id: str = "", sequence: int = 0) -> LiveAction | None:
    """One CoinPoker ``game.dealer_chat_action`` record as a :class:`LiveAction`.

    The room spells a bet and a raise apart by the record's own ``action`` field
    and gives the raise-to total where it has one, so the adapter reads both
    rather than guessing which a number means.
    """
    raw = str(record.get("action") or "").strip().upper()
    effective = str(record.get("newPlayerAction") or raw).strip().upper()
    actor = str(record.get("username") or record.get("player") or "").strip()
    if not actor or not (raw or effective):
        return None
    amount = _cents(record.get("actionAmount"))
    street = str(record.get("roundName") or "PREFLOP")
    all_in = effective in {"ALLIN", "ALL_IN"} or raw in {"ALLIN", "ALL_IN"}
    if effective == "FOLD":
        kind, amount = "folds", 0
    elif effective == "CHECK":
        kind, amount = "checks", 0
    elif effective == "CALL":
        kind = "calls"
    elif raw == "RAISE" and effective in {"BET", ""}:
        kind = "bets"
    elif raw == "RAISE":
        kind = "raises"
    elif all_in:
        kind = "raises" if raw == "RAISE" else "calls"
    else:
        kind = effective.lower() or "checks"
    return LiveAction(
        actor=actor,
        action=kind,
        street=street,
        amount_cents=amount,
        to_cents=amount if kind in _AGGRESSIVE else None,
        all_in=all_in,
        hand_id=hand_id,
        sequence=sequence,
    )


def coinpoker_actions(events: Iterable[tuple], *, hand_id: str = "") -> Iterator[LiveAction]:
    """Every CoinPoker live action in a capture's event stream, in order.

    Reads ``game.dealer_chat_action`` payloads, which the room publishes as each
    action is taken -- this is the live source #336 asks the adapter boundary to
    accept.

    Duplicate records are dropped here, by the same key the hand builder dedupes
    on (``initTimestamp``/player/action/round/amount), and the sequence handed to
    the adapter is a strict ordinal. Using the room's ``initTimestamp`` directly
    would have made two *distinct* actions taken in the same millisecond share a
    sequence -- and the adapter would have dropped the second as a duplicate.
    """
    seen: set[tuple] = set()
    sequence = 0
    for name, _hid, payload in events:
        if name != "game.dealer_chat_action" or not isinstance(payload, Mapping):
            continue
        for record in payload.get("gameActionMessagesHistory") or []:
            if not isinstance(record, Mapping):
                continue
            key = (
                record.get("initTimestamp"),
                record.get("username"),
                record.get("action"),
                record.get("roundName"),
                record.get("actionAmount"),
            )
            if key in seen:
                continue
            seen.add(key)
            sequence += 1
            action = coinpoker_action(record, hand_id=hand_id, sequence=sequence)
            if action is not None:
                yield action


# ---------------------------------------------------------------------------
# Observability: why a panel moved.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LiveTrace:
    """One live update, explained: what arrived, what it became, what changed."""

    action: str
    context_key: str
    changed: tuple[str, ...]
    unknown: tuple[str, ...]
    panels_before: tuple[str, ...] = ()
    panels_after: tuple[str, ...] = ()

    @property
    def panel_change(self) -> tuple[str, ...]:
        """The panels whose selection actually changed."""
        before, after = set(self.panels_before), set(self.panels_after)
        return tuple(sorted(before ^ after))

    def describe(self) -> str:
        """A one-line trace, for the HUD log and the debug view."""
        lines = [f"live {self.action} -> {self.context_key}"]
        if self.unknown:
            lines.append(f"unknown={','.join(self.unknown)}")
        if self.panels_before or self.panels_after:
            lines.append(f"panels {','.join(self.panels_before) or '-'} -> {','.join(self.panels_after) or '-'}")
        if self.changed:
            lines.append(f"changed={','.join(self.changed)}")
        return " | ".join(lines)


def trace_update(
    action: LiveAction,
    before: LiveContext | None,
    after: LiveContext,
    *,
    panels_before: Iterable[str] = (),
    panels_after: Iterable[str] = (),
) -> LiveTrace:
    """A trace comparing the context before and after one action."""
    changed: list[str] = []
    if before is None or before.street != after.street:
        changed.append("street")
    if before is None or before.pot_type != after.pot_type:
        changed.append("pot_type")
    if before is None or before.players_in_hand != after.players_in_hand:
        changed.append("players_in_hand")
    if before is None or before.aggressor != after.aggressor:
        changed.append("aggressor")
    if before is None or before.to_call_cents != after.to_call_cents:
        changed.append("to_call")
    return LiveTrace(
        action=f"{action.actor}:{action.action}",
        context_key=after.describe(),
        changed=tuple(changed),
        unknown=tuple(after.unknown),
        panels_before=tuple(panels_before),
        panels_after=tuple(panels_after),
    )


# ---------------------------------------------------------------------------
# The HUD session: one table's action stream, published through set_live_state.
# ---------------------------------------------------------------------------


class LiveContextSession:
    """Feeds one HUD's dynamic panels from a live action stream (#336).

    Holds the adapter, the last published context and the trace of the last
    update. It calls ``hud.set_live_state`` -- the hook #298 already exposes --
    so the resolver, the panel state and the position-preserving redraw are
    exactly the ones the classic path uses. A HUD with dynamic panels disabled
    is untouched: it has no resolver, so nothing here changes anything.
    """

    def __init__(
        self,
        hud: Any = None,
        adapter: ActionStreamAdapter | None = None,
        *,
        source: str = SOURCE_ACTION_STREAM,
        clock: Any = time.monotonic,
    ) -> None:
        self.hud = hud
        self.adapter = adapter if adapter is not None else ActionStreamAdapter()
        self.source = source
        self.last_context: LiveContext | None = None
        self.last_trace: LiveTrace | None = None
        self.updates = 0
        self.ignored = 0
        self._clock = clock

    # -- lifecycle ----------------------------------------------------------

    def start_hand(self, hand_id: str, *, seats: Iterable[str] = ()) -> LiveContext:
        """A new hand began: reset, so nothing of the last one can leak in."""
        self.adapter.reset(hand_id, seats=seats)
        self.last_context = self.adapter.context
        return self.last_context

    def seat(self, actor: str, **facts: Any) -> None:
        """Record a seat (position, stack) without treating it as an action."""
        self.adapter.note_seat(actor, **facts)

    def update(self, action: LiveAction) -> LiveTrace | None:
        """Fold one action in and publish the context it describes."""
        before = self.last_context
        context = self.adapter.apply(action)
        if context is None:
            self.ignored += 1
            return None
        self.last_context = context
        self.updates += 1
        if self.hud is not None:
            publish = getattr(self.hud, "set_live_state", None)
            if publish is not None:
                try:
                    publish(**context_to_live_state(context))
                except Exception:  # intentional broad catch: a live update must not break the HUD
                    log.exception("Could not publish the live context to the HUD")
        trace = trace_update(action, before, context)
        self.last_trace = trace
        log.debug(trace.describe())
        return trace

    def close(self) -> None:
        """The table closed or the source stopped: clear what it published."""
        self.last_context = None
        self.last_trace = None
        if self.hud is not None:
            publish = getattr(self.hud, "set_live_state", None)
            if publish is not None:
                for key in ("street", "street_index", "pot_type", "players_in_hand", "multiway", "source"):
                    try:
                        publish(**{key: None})
                    except Exception:  # intentional broad catch: teardown must not raise
                        log.debug("Could not clear live key %s", key, exc_info=True)

    @property
    def source_note(self) -> str:
        """What the UI should say about this session's freshness."""
        return describe_source(self.source)


__all__ = [
    "SOURCE_ACTION_STREAM",
    "SOURCE_HAND_REFRESH",
    "STREETS",
    "ActionStreamAdapter",
    "LiveAction",
    "LiveContext",
    "LiveContextSession",
    "LiveTrace",
    "actions_from_normalized",
    "coinpoker_action",
    "coinpoker_actions",
    "context_to_live_state",
    "describe_source",
    "is_action_live",
    "normalized_action",
    "trace_update",
]
