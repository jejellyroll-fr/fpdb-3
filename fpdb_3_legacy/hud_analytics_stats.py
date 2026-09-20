"""The runtime value of an analytics-backed HUD stat (#335).

The HUD editor (#309) can already bind a declarative definition (#306) to a
cell:

.. code-block:: xml

   <stat _rowcol="(1,1)" _stat_name="fold_to_cbet_flop"
         data_source="analytics"
         data_definition="fold_to_cbet_flop"
         data_format="percentage"
         data_min_sample="5"/>

The binding round-trips, and every layer below it exists -- the definition
registry, the query engine, the aggregate cache -- but nothing joined them to
the live HUD: a cell could *say* it came from a definition and still render
nothing. This module is that join, and only that join.

What it deliberately is not
---------------------------

* **Not a second stats engine.** A definition is compiled and executed by the
  code the CLI, the report API and the research browser already use
  (:func:`analytics_definitions.resolve_query` /
  :func:`analytics_query.run_query`), so the number a HUD cell shows and the
  number ``analytics_definitions.build_report`` shows for the same definition
  are the same number by construction -- there is one code path.
* **Not a generator.** Nothing writes Python into ``Stats.py``; the definitions
  stay data, which is the whole point of #306.
* **Not on the UI thread.** :meth:`AnalyticsStatProvider.compute_batch` is a
  plain callable so it can run inside the HUD's existing batched read worker
  (:mod:`fpdb_3_legacy.hud_read_service`). The Qt side only ever *reads* what a
  finished batch stored (:meth:`AnalyticsStatProvider.text_for`).

Context: what can and cannot be injected
----------------------------------------

A HUD refresh knows the table, the seats and the players. It does not, in the
classic path, know the street, the board or the action in front of a player --
what it has is the last *assembled* hand. So the provider distinguishes the two
sets explicitly rather than passing a half-known context into the engine and
letting a filter silently mean something else:

:data:`INJECTABLE_CONTEXT`
    Facts a refresh can state truthfully. The important one is ``identity``: an
    analytics stat is *about someone*, and the only unambiguous way to say who
    is the ``(site, alias)`` pair the engine already models -- a bare screen
    name is two different people on two rooms.
:data:`NOT_INJECTABLE_CONTEXT`
    Facts only a live action feed has (``street``, ``board_*``, ``position``,
    ``sizing_bucket``, the aggressor, ...). Passing them from the imported hand
    would answer a *different* question than the cell claims to ask, so they are
    refused when a definition names them. Their absence is honest; inventing
    them is not. #336 is where those facts arrive, when a source can supply
    them.

Minimum sample, formats and failure
-----------------------------------

Formatting is the definition's own :class:`~fpdb_3_legacy.analytics_definitions.DisplaySpec`,
optionally overridden per cell by ``data_format``/``data_min_sample`` -- and a
cell below its minimum sample renders the HUD's existing no-data convention
(``-``) rather than a rate over three hands. An unknown definition, an
unresolvable player, a grouped definition asked for a single number, or a query
failure all render that same ``-`` and log an actionable diagnostic once per
window; none of them raise into the HUD, and none of them fall back to a native
stat that happens to share the name.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Final

from . import analytics_cache
from . import analytics_definitions as definitions
from .analytics_definitions import NO_DATA, StatDefinition
from .analytics_query import Query, QueryResult, QueryRow, run_query
from .loggingFpdb import get_logger

log = get_logger("hud_analytics_stats")

#: The ``data_source`` value that marks a cell as analytics-backed.
ANALYTICS_SOURCE: Final = "analytics"

#: The source every column-backed stat of ``Stats.py`` has (absent attribute).
NATIVE_SOURCE: Final = "registry"

# -- value states ----------------------------------------------------------

#: A real value, over a large enough sample.
STATE_OK: Final = "ok"
#: The definition ran and nothing matched: an empty population, not a zero.
STATE_NO_DATA: Final = "no_data"
#: The definition ran, but on fewer decisions than it asks for.
STATE_BELOW_SAMPLE: Final = "below_sample"
#: ``data_definition`` names nothing the installed registry knows.
STATE_UNKNOWN_DEFINITION: Final = "unknown_definition"
#: The binding itself is unusable (no definition named at all).
STATE_BAD_BINDING: Final = "bad_binding"
#: The seat could not be resolved to a player, so there is nobody to ask about.
STATE_UNKNOWN_PLAYER: Final = "unknown_player"
#: The definition asks for something a single HUD cell cannot show: a grouping,
#: or a fact only a live feed has.
STATE_UNSUPPORTED: Final = "unsupported"
#: The query itself failed (database, permissions, a broken definition).
STATE_ERROR: Final = "error"

# -- context classification ------------------------------------------------

#: Facts a HUD refresh states truthfully, and therefore injects.
INJECTABLE_CONTEXT: Final[tuple[str, ...]] = (
    "identity",
    "player",
    "players",
    "site",
    "hero",
    "game",
    "limit",
    "table_size",
    "date_from",
    "date_to",
)

#: Facts only a live action stream has, and which this provider therefore
#: refuses to *take as context*. Note the asymmetry with a definition's own
#: filters: ``fold_to_cbet_flop`` filtering on ``street=flop`` is fine, because
#: the engine evaluates that per stored decision and the answer is the same for
#: every refresh. What would not be fine is the *refresh* claiming the table is
#: on the flop and injecting that into every definition -- so the refusal is on
#: the injection, where the guess would be made.
NOT_INJECTABLE_CONTEXT: Final[tuple[str, ...]] = (
    "street",
    "position",
    "opponent_position",
    "relative_position",
    "in_position",
    "effective_stack_bb",
    "sizing_bucket",
    "facing_sizing_bucket",
    "facing_action",
    "facing_pot_type",
    "pot_type",
    "preflop_aggressor",
    "board_rank",
    "board_suit",
    "board_pairing",
    "board_high",
    "board_wetness",
    "starting_hand",
    "made_hand",
    "draws",
)

#: Why a cell is never asked these, in the words of the HUD's own docs.
CONTEXT_NOTE: Final = (
    "A HUD refresh knows the table, the seats and the players. It does not know "
    "the street, the board or the action in front of a player: those arrive "
    "from a live feed (#336), and until they do, an analytics cell that filters "
    "on them would describe a different question than the one it shows."
)

#: What one whole HUD refresh may spend on analytics, for a 6-max table with a
#: handful of them. The provider never blocks the UI on it -- this is the budget
#: the batched worker measures itself against, and exceeds at most with a log.
DEFAULT_LATENCY_BUDGET_MS: Final = 250.0

#: A failing binding logs once per window instead of once per seat per hand.
DIAGNOSTIC_REPEAT_SECONDS: Final = 60.0


# ---------------------------------------------------------------------------
# Binding: what a cell says about itself.
# ---------------------------------------------------------------------------


def _positive_int(raw: Any) -> int | None:
    """``data_min_sample`` as a number, or ``None`` when it is absent/unusable."""
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _known_format(raw: Any) -> str:
    """``data_format`` when the engine knows it, else ``""`` (definition's own)."""
    text = str(raw or "").strip()
    return text if text in definitions.VALID_FORMATS else ""


@dataclass(frozen=True)
class AnalyticsStatBinding:
    """One analytics-backed cell, as its configuration describes it.

    ``stat_name`` is the cell's display name (what ``Stats.py`` would be asked
    for if this were a native stat, and what the HUD's popups address);
    ``definition`` is the registry entry that actually runs. They are usually
    equal, and they are allowed to differ: a profile can bind two cells to one
    definition with different labels or formats.
    """

    stat_name: str
    definition: str
    fmt: str = ""
    min_sample: int | None = None

    @classmethod
    def from_attributes(cls, attributes: Mapping[str, Any]) -> AnalyticsStatBinding | None:
        """The binding one ``<stat>`` node's attributes declare, or ``None``.

        ``None`` is the honest answer for a native cell -- nearly every cell of
        nearly every profile -- so the caller can keep the fast path.
        """
        if str(attributes.get("data_source") or "").strip() != ANALYTICS_SOURCE:
            return None
        raw = {str(key).lstrip("_"): value for key, value in attributes.items()}
        definition = str(raw.get("data_definition") or "").strip()
        stat_name = str(raw.get("stat_name") or "").strip()
        if not definition:
            # A binding with no definition is a broken binding, kept as one so
            # the cell renders *why* instead of quietly becoming a native stat.
            definition = stat_name
        if not definition:
            return None
        return cls(
            stat_name=stat_name or definition,
            definition=definition,
            fmt=_known_format(raw.get("data_format")),
            min_sample=_positive_int(raw.get("data_min_sample")),
        )

    @classmethod
    def from_stat(cls, stat: Any) -> AnalyticsStatBinding | None:
        """The binding a :class:`~fpdb_3_legacy.Configuration.Stat` declares."""
        if stat is None:
            return None
        return cls.from_attributes(
            {
                "data_source": getattr(stat, "data_source", ""),
                "data_definition": getattr(stat, "data_definition", ""),
                "data_format": getattr(stat, "data_format", ""),
                "data_min_sample": getattr(stat, "data_min_sample", ""),
                "stat_name": getattr(stat, "stat_name", ""),
            },
        )

    def key(self) -> tuple[str, str, str, int | None]:
        """Identity of the binding, for looking one's own cell up in a batch."""
        return (self.stat_name, self.definition, self.fmt, self.min_sample)


def _stat_set_documents(document: Any, stat_set: str) -> list[Any]:
    """The ``<ss>`` containers a binding search should walk.

    A stat set is an ``<ss name="...">`` node; scoping to one is what keeps a
    profile from inheriting another profile's analytics cells. Names are compared
    the way ``Configuration.get_stat_set_node`` compares them. A named set that
    is not installed yields nothing rather than everything: showing a value under
    a cell the active profile does not bind is worse than showing none.
    """
    if not stat_set:
        return [document]
    return [node for node in document.getElementsByTagName("ss") if node.getAttribute("name") == stat_set]


def bindings_from_config(config: Any, *, stat_set: str = "") -> tuple[AnalyticsStatBinding, ...]:
    """The analytics-backed cells of a configuration, in document order.

    Read from the XML rather than from a parsed profile, because the binding
    lives on the ``<stat>`` node and must be seen the way it was written. A
    configuration that cannot be walked yields nothing -- a HUD with no
    analytics cells is the normal case, not an error.

    ``stat_set`` scopes the search to one ``<ss name="...">``; the render path
    passes the active profile so a cell that another profile declared as
    analytics is never taken over in a profile that has it as a native stat.
    """
    document = getattr(config, "doc", None)
    if document is None or not hasattr(document, "getElementsByTagName"):
        return ()
    found: list[AnalyticsStatBinding] = []
    seen: set[tuple[str, str, str, int | None]] = set()
    for container in _stat_set_documents(document, stat_set):
        _collect_bindings(container, found, seen)
    return tuple(found)


def _collect_bindings(
    container: Any,
    found: list[AnalyticsStatBinding],
    seen: set[tuple[str, str, str, int | None]],
) -> None:
    """Append the analytics bindings of one ``<ss>`` (or the whole document)."""
    for node in container.getElementsByTagName("stat"):
        attributes = {
            name: node.getAttribute(name)
            for name in ("_stat_name", "data_source", "data_definition", "data_format", "data_min_sample")
        }
        binding = AnalyticsStatBinding.from_attributes(attributes)
        if binding is None or binding.key() in seen:
            continue
        seen.add(binding.key())
        found.append(binding)


# ---------------------------------------------------------------------------
# Scope: who the stat is about.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlayerScope:
    """The player a cell's value belongs to, and how to name them to the engine.

    ``alias``/``site`` are the ``(site, screen name)`` pair the HUD's seats
    already resolve players by. A scope without an alias cannot be answered:
    the engine would have to guess who, and guessing would show one player's
    rate under another player's name.
    """

    alias: str = ""
    site: str = ""
    player_id: Any = None
    is_hero: bool = False

    def key(self) -> tuple[str, str]:
        return (self.alias, self.site)

    def is_resolved(self) -> bool:
        """Whether the seat is known well enough to ask a question about."""
        return bool(self.alias)

    def filters(self) -> dict[str, Any]:
        """The filters that scope any definition to this player.

        ``identity`` rather than ``player``: the same screen name on two rooms
        is two different people, and the engine's ``identity_set`` filter is the
        one that says so.
        """
        if self.site and self.alias:
            return {"identity": {self.site: self.alias}}
        if self.alias:
            return {"player": [self.alias]}
        return {}

    def describe(self) -> str:
        """The player in one line, for a diagnostic."""
        if self.site and self.alias:
            return f"{self.site}:{self.alias}"
        return self.alias or "unknown player"


#: The keys a HUD aggregate row may carry the screen name under. The HUD SQL
#: writes ``screen_name``; the others cover rows a feed or a replay assembled.
_ALIAS_KEYS: Final[tuple[str, ...]] = ("screen_name", "screenname", "screen name", "name", "playername")


def scope_for_entry(entry: Mapping[str, Any] | None, *, site: str = "", player_id: Any = None) -> PlayerScope:
    """The scope of one seat, read from its aggregate row.

    The row names the player by screen name and nothing else, so the scope is
    built from the same fields the seat is drawn from rather than from a second
    query. ``site`` is supplied by the caller when the table knows which room it
    is, which is what makes the filter an unambiguous ``identity`` instead of a
    name that two rooms could share.
    """
    values = entry or {}
    lowered = {str(key).lower(): value for key, value in values.items()}
    alias = ""
    for key in _ALIAS_KEYS:
        candidate = str(lowered.get(key) or "").strip()
        if candidate:
            alias = candidate
            break
    return PlayerScope(
        alias=alias,
        site=str(site or "").strip(),
        player_id=player_id,
    )


def scopes_for_stat_dict(stat_dict: Mapping[Any, Any] | None, *, site: str = "") -> dict[Any, PlayerScope]:
    """Every seat of one hand as a scope, keyed the way a HUD seat is keyed.

    A seat with no screen name still gets an entry -- an *unresolved* scope --
    so the provider answers it with "nobody to ask about" rather than dropping
    the cell and leaving a stale number on screen.
    """
    scopes: dict[Any, PlayerScope] = {}
    for player_id, entry in (stat_dict or {}).items():
        scopes[player_id] = scope_for_entry(entry if isinstance(entry, Mapping) else {}, site=site, player_id=player_id)
    return scopes


# ---------------------------------------------------------------------------
# Value: what the cell renders.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnalyticsStatValue:
    """One computed cell value, with everything the label and tooltip need."""

    stat_name: str
    definition: str
    state: str
    raw: float | None = None
    sample: int = 0
    numerator: int = 0
    unit: str = ""
    label: str = ""
    description: str = ""
    reason: str = ""
    fingerprint: str = ""
    elapsed_ms: float = 0.0
    from_aggregate_cache: bool = False
    rendered: str = NO_DATA

    @property
    def available(self) -> bool:
        """Whether this is a real number over a real sample."""
        return self.state == STATE_OK

    @property
    def text(self) -> str:
        """What the HUD cell shows, in the engine's no-data convention."""
        if not self.available or self.raw is None:
            return NO_DATA
        return self.rendered

    @property
    def sample_text(self) -> str:
        """``(12)`` when there is a sample worth stating, else ``""``."""
        return f"({self.sample})" if self.available and self.sample else ""

    def tooltip(self) -> str:
        """The label, the value, the sample and, when missing, why."""
        lines = [self.label or self.definition or self.stat_name]
        if self.description:
            lines.append(self.description)
        if self.available:
            lines.append(f"Value: {self.text}")
            lines.append(f"Sample: {self.sample} decisions, {self.numerator} counted")
        else:
            lines.append(f"No value: {self.reason or self.state}")
        return "\n".join(line for line in lines if line)

    def as_dict(self) -> dict[str, Any]:
        """The value as data, for a log line or a popup."""
        return {
            "stat": self.stat_name,
            "definition": self.definition,
            "state": self.state,
            "text": self.text,
            "raw": self.raw,
            "sample": self.sample,
            "numerator": self.numerator,
            "unit": self.unit,
            "reason": self.reason,
        }


def _unavailable(
    binding: AnalyticsStatBinding,
    state: str,
    reason: str,
    *,
    label: str = "",
    description: str = "",
) -> AnalyticsStatValue:
    """A cell that cannot show a number, and says why instead of inventing one."""
    return AnalyticsStatValue(
        stat_name=binding.stat_name,
        definition=binding.definition,
        state=state,
        label=label,
        description=description,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Cache.
# ---------------------------------------------------------------------------

#: ``(query fingerprint, cell format, cell minimum sample, (alias, site))``.
CacheKey = tuple[str, str, int | None, tuple[str, str]]

#: ``(binding identity, (alias, site))`` -- how a caller finds its own cell.
BatchKey = tuple[str, str, str, int | None, tuple[str, str]]


class AnalyticsStatCache:
    """Last-known values, keyed by query meaning, cell presentation *and* player.

    The key is the compiled query's fingerprint (which already includes the
    filters, so a definition and the same definition narrowed by a date window
    never collide), the cell's own format and minimum sample (two cells bound to
    one definition may legitimately be shown differently), and the player's
    identity. Two cells bound identically for the same player therefore share
    one entry -- which is what makes ``N(cells) x N(seats)`` cells cost one
    query per distinct ``(definition, player)`` instead of one each.

    The cache is per-session and bounded: a HUD that follows hundreds of players
    across a day must not grow without limit.
    """

    def __init__(self, max_entries: int = 2048) -> None:
        self.max_entries = max(1, int(max_entries))
        self._entries: dict[CacheKey, AnalyticsStatValue] = {}
        self._generation = 0

    @property
    def generation(self) -> int:
        """Bumped by every invalidation, so a stale value is never re-read."""
        return self._generation

    @staticmethod
    def key(fingerprint: str, binding: AnalyticsStatBinding, scope: PlayerScope) -> CacheKey:
        return (fingerprint, binding.fmt, binding.min_sample, scope.key())

    def get(self, fingerprint: str, binding: AnalyticsStatBinding, scope: PlayerScope) -> AnalyticsStatValue | None:
        return self._entries.get(self.key(fingerprint, binding, scope))

    def put(
        self,
        fingerprint: str,
        binding: AnalyticsStatBinding,
        scope: PlayerScope,
        value: AnalyticsStatValue,
    ) -> None:
        if len(self._entries) >= self.max_entries:
            # Oldest first: a refresh stores every seat of the hand it just
            # read, so the front of the dict is the oldest hand's worth.
            for stale in list(self._entries)[: max(1, self.max_entries // 8)]:
                self._entries.pop(stale, None)
        self._entries[self.key(fingerprint, binding, scope)] = value

    def invalidate(self) -> int:
        """Forget everything -- new hands were imported, so every value is behind."""
        count = len(self._entries)
        self._entries.clear()
        self._generation += 1
        return count

    def __len__(self) -> int:
        return len(self._entries)


# ---------------------------------------------------------------------------
# Provider.
# ---------------------------------------------------------------------------


@dataclass
class ProviderCounters:
    """What a provider did, for a log line and for the latency test."""

    queries: int = 0
    cache_hits: int = 0
    batch_reads: int = 0
    failures: int = 0
    last_batch_ms: float = 0.0
    worst_batch_ms: float = 0.0
    over_budget: int = 0


@dataclass(frozen=True)
class _Plan:
    """One cell, resolved down to the query it needs and how to show the answer."""

    binding: AnalyticsStatBinding
    definition: StatDefinition
    scope: PlayerScope
    query: Query
    fingerprint: str
    label: str
    description: str


class AnalyticsStatProvider:
    """Computes analytics-backed HUD values, off the UI thread.

    One provider serves every HUD in the process: the registry is read-only
    data, and sharing it is what lets two tables showing the same villain share
    a cached value for as long as that value is current.
    """

    def __init__(
        self,
        registry: Any = None,
        *,
        locale: str = "en",
        big_blind_cents: int | None = None,
        cache: AnalyticsStatCache | None = None,
        latency_budget_ms: float = DEFAULT_LATENCY_BUDGET_MS,
        use_aggregate_cache: bool = True,
        clock: Any = time.monotonic,
    ) -> None:
        self.registry = registry if registry is not None else definitions.get_registry()
        self.locale = locale
        self.big_blind_cents = big_blind_cents
        self.cache = cache if cache is not None else AnalyticsStatCache()
        self.latency_budget_ms = float(latency_budget_ms)
        #: The aggregate cache (#304) is *read* here, never refreshed: a HUD read
        #: runs in a transaction its caller rolls back, so a refresh triggered
        #: from this path would be undone and would leave the watermark claiming
        #: work that never landed. An empty or behind cache therefore costs a
        #: direct query, which is the same answer either way.
        self.use_aggregate_cache = use_aggregate_cache
        self.counters = ProviderCounters()
        self._clock = clock
        self._diagnostics: dict[str, float] = {}

    # -- definitions --------------------------------------------------------

    def definition(self, binding: AnalyticsStatBinding) -> StatDefinition | None:
        """The registry entry a binding names, or ``None``."""
        if not binding.definition:
            return None
        return self.registry.get(binding.definition)

    def capability(self, binding: AnalyticsStatBinding) -> str:
        """Why a binding cannot be computed, or ``""`` when it can.

        This is the editor's question, answered by the same code the HUD uses: a
        definition that is not runtime-capable here will not become capable when
        the table opens.
        """
        if not binding.definition:
            return "the cell says it is analytics-backed but names no definition"
        definition = self.definition(binding)
        if definition is None:
            known = ", ".join(self.registry.names()) or "none installed"
            return f"no definition named {binding.definition!r} is installed (known: {known})"
        return self._unsupported_reason(definition)

    @staticmethod
    def _unsupported_reason(definition: StatDefinition) -> str:
        """Why one cell cannot show this definition, or ``""``.

        Only one thing makes a *definition* unusable in a cell: a grouping. Its
        filters -- ``street``, ``board_*``, ``position`` -- are its meaning, and
        the engine evaluates them per stored decision, so a flop stat is exactly
        as answerable in a cell as any other.
        """
        if definition.group_by:
            return f"{definition.name} is grouped by {', '.join(definition.group_by)}, which one cell cannot show"
        return ""

    @staticmethod
    def _check_context(context: Mapping[str, Any] | None) -> str:
        """Why the caller's context cannot be injected, or ``""``.

        The policy of :data:`INJECTABLE_CONTEXT` made executable: a refresh that
        tries to pass ``street`` or ``board_rank`` is answered with a reason
        instead of a number, because the number would belong to a different
        question than the cell's.
        """
        if not context:
            return ""
        refused = sorted(set(context) & set(NOT_INJECTABLE_CONTEXT))
        if not refused:
            return ""
        return (
            f"this refresh cannot state {', '.join(refused)} truthfully, so the cell's "
            "question is not the one that would be answered"
        )

    def effective_definition(self, binding: AnalyticsStatBinding, definition: StatDefinition) -> StatDefinition:
        """The definition with the cell's own format/sample overrides applied."""
        display = definition.display
        if binding.fmt or binding.min_sample is not None:
            display = replace(
                display,
                fmt=binding.fmt or display.fmt,
                min_sample=display.min_sample if binding.min_sample is None else binding.min_sample,
            )
        return replace(definition, display=display)

    def query_for(
        self,
        binding: AnalyticsStatBinding,
        scope: PlayerScope,
        context: Mapping[str, Any] | None = None,
    ) -> Query:
        """The engine query one cell runs: the definition, scoped to a player."""
        definition = self.definition(binding)
        if definition is None:
            raise ValueError(f"unknown definition {binding.definition!r}")
        filters: dict[str, Any] = dict(scope.filters())
        if context:
            filters.update(context)
        return definitions.resolve_query(definition, filters, self.registry.fragments)

    def report_entry(
        self,
        db: Any,
        binding: AnalyticsStatBinding,
        scope: PlayerScope,
    ) -> dict[str, Any]:
        """The same definition through the *report* API, for cross-checking.

        The issue asks that a HUD cell's value match the definition executed
        through the report API. That comparison is worth being able to make
        without re-deriving the filters by hand, so both sides are one call.
        """
        definition = self.definition(binding)
        if definition is None:
            raise ValueError(f"unknown definition {binding.definition!r}")
        entries = definitions.build_report(
            db,
            [self.effective_definition(binding, definition)],
            context=scope.filters(),
            big_blind_cents=self.big_blind_cents,
            locale=self.locale,
        )
        return entries[0] if entries else {}

    # -- computing ----------------------------------------------------------

    def compute(
        self,
        db: Any,
        binding: AnalyticsStatBinding,
        scope: PlayerScope,
        context: Mapping[str, Any] | None = None,
    ) -> AnalyticsStatValue:
        """One cell's value, executing at most one query."""
        plan = self._plan(binding, scope, context)
        if isinstance(plan, AnalyticsStatValue):
            return plan
        cached = self.cache.get(plan.fingerprint, binding, scope)
        if cached is not None:
            self.counters.cache_hits += 1
            return cached
        started = self._clock()
        try:
            result, from_cache = self._execute(db, plan.query)
        except Exception as exc:  # noqa: BLE001 - a failing query must not reach the HUD
            return self._failure(plan, exc)
        value = self._render(plan, result, (self._clock() - started) * 1000.0, from_cache)
        self.cache.put(plan.fingerprint, binding, scope, value)
        return value

    def compute_batch(
        self,
        db: Any,
        requests: Iterable[tuple[AnalyticsStatBinding, PlayerScope]],
        context: Mapping[str, Any] | None = None,
    ) -> dict[BatchKey, AnalyticsStatValue]:
        """Every value a HUD refresh needs, with each query run **once**.

        This is the batching contract of the issue: sixty cells across six seats
        bound to four definitions cost four queries (times the number of
        distinct players), not sixty. Identical ``(definition, player)`` requests
        inside one call collapse into a single execution, and the cells bound to
        it are rendered from the one result -- so two cells that differ only in
        the format they show still cost one query.

        Returns a mapping keyed by ``(binding.key(), scope.key())`` so a caller
        that owns a grid of cells can look its own cell up directly.
        """
        started = self._clock()
        self.counters.batch_reads += 1
        values: dict[BatchKey, AnalyticsStatValue] = {}
        grouped: dict[tuple[str, tuple[str, str]], list[BatchKey]] = {}
        plans: dict[BatchKey, _Plan] = {}

        unique: dict[tuple[Any, Any], tuple[AnalyticsStatBinding, PlayerScope]] = {}
        for binding, scope in requests:
            unique.setdefault((binding.key(), scope.key()), (binding, scope))

        for binding, scope in unique.values():
            key: BatchKey = (*binding.key(), scope.key())
            plan = self._plan(binding, scope, context)
            if isinstance(plan, AnalyticsStatValue):
                # Not a query: the reason *is* the answer, so it costs nothing.
                values[key] = plan
                continue
            cached = self.cache.get(plan.fingerprint, binding, scope)
            if cached is not None:
                self.counters.cache_hits += 1
                values[key] = cached
                continue
            plans[key] = plan
            grouped.setdefault((plan.fingerprint, scope.key()), []).append(key)

        for keys in grouped.values():
            plan = plans[keys[0]]
            started_query = self._clock()
            try:
                result, from_cache = self._execute(db, plan.query)
            except Exception as exc:  # noqa: BLE001 - one failing cell, not a failed refresh
                for key in keys:
                    values[key] = self._failure(plans[key], exc)
                continue
            elapsed_ms = (self._clock() - started_query) * 1000.0
            for key in keys:
                member = plans[key]
                value = self._render(member, result, elapsed_ms, from_cache)
                self.cache.put(member.fingerprint, member.binding, member.scope, value)
                values[key] = value

        elapsed_ms = (self._clock() - started) * 1000.0
        self.counters.last_batch_ms = elapsed_ms
        self.counters.worst_batch_ms = max(self.counters.worst_batch_ms, elapsed_ms)
        if elapsed_ms > self.latency_budget_ms:
            self.counters.over_budget += 1
            self.diagnose(
                "over-budget",
                "HUD analytics refresh took %.0f ms for %d cells (%d queries), over the %.0f ms budget",
                elapsed_ms,
                len(values),
                self.counters.queries,
                self.latency_budget_ms,
            )
        return values

    def compute_for_stat_dict(
        self,
        db: Any,
        bindings: Iterable[AnalyticsStatBinding],
        stat_dict: Mapping[Any, Any] | None,
        *,
        site: str = "",
        context: Mapping[str, Any] | None = None,
    ) -> dict[Any, dict[str, AnalyticsStatValue]]:
        """One hand's whole HUD grid, computed and regrouped by player.

        The read worker's entry point: it turns a ``stat_dict`` into scopes,
        runs :meth:`compute_batch` once for every ``(binding, player)`` pair and
        hands back ``{player_id: {stat_name: value}}`` -- the order a seat reads
        its own grid in. An empty binding list is the normal case and costs
        nothing, which is what keeps a profile with no analytics cells exactly
        as fast as it was before.
        """
        bindings = tuple(bindings)
        scopes = scopes_for_stat_dict(stat_dict, site=site)
        if not bindings or not scopes:
            return {}
        requests = [(binding, scope) for binding in bindings for scope in scopes.values()]
        batch = self.compute_batch(db, requests, context)
        return publish_hand_values(batch, scopes, bindings)

    # -- internals ----------------------------------------------------------

    def _plan(
        self,
        binding: AnalyticsStatBinding,
        scope: PlayerScope,
        context: Mapping[str, Any] | None,
    ) -> _Plan | AnalyticsStatValue:
        """Resolve a cell to its query, or to the reason it cannot have one."""
        definition = self.definition(binding)
        if definition is None:
            known = ", ".join(self.registry.names()) or "none installed"
            reason = f"no definition named {binding.definition!r} is installed (known: {known})"
            self.diagnose(f"unknown:{binding.definition}", "HUD analytics stat %s: %s", binding.stat_name, reason)
            state = STATE_UNKNOWN_DEFINITION if binding.definition else STATE_BAD_BINDING
            return _unavailable(binding, state, reason)
        reason = self._unsupported_reason(definition)
        if reason:
            label = definition.display.label_for(self.locale) or binding.stat_name
            self.diagnose(f"unsupported:{definition.name}", "HUD analytics stat %s: %s", binding.stat_name, reason)
            return _unavailable(binding, STATE_UNSUPPORTED, reason, label=label)
        context_reason = self._check_context(context)
        if context_reason:
            label = definition.display.label_for(self.locale) or binding.stat_name
            self.diagnose(f"context:{definition.name}", "HUD analytics stat %s: %s", binding.stat_name, context_reason)
            return _unavailable(binding, STATE_UNSUPPORTED, context_reason, label=label)
        if not scope.is_resolved():
            reason = "the seat has no (site, screen name) identity to ask about"
            label = definition.display.label_for(self.locale) or binding.stat_name
            self.diagnose("unresolved-player", "HUD analytics stat %s: %s", binding.stat_name, reason)
            return _unavailable(binding, STATE_UNKNOWN_PLAYER, reason, label=label)

        effective = self.effective_definition(binding, definition)
        try:
            query = self.query_for(binding, scope, context)
        except (ValueError, KeyError) as exc:
            self.counters.failures += 1
            self.diagnose(f"bad-query:{binding.definition}", "HUD analytics stat %s: %s", binding.stat_name, exc)
            return _unavailable(binding, STATE_ERROR, str(exc))
        return _Plan(
            binding=binding,
            definition=effective,
            scope=scope,
            query=query,
            fingerprint=analytics_cache.query_fingerprint(query),
            label=effective.display.label_for(self.locale) or binding.stat_name,
            description=effective.display.description_for(self.locale),
        )

    def _execute(self, db: Any, query: Query) -> tuple[QueryResult, bool]:
        """Run the query, reading the aggregate cache when that is valid."""
        if self.use_aggregate_cache:
            cached = analytics_cache.cached_query_if_fresh(db, query)
            if cached is not None:
                return cached, True
        self.counters.queries += 1
        return run_query(db, query), False

    def _failure(self, plan: _Plan, exc: BaseException) -> AnalyticsStatValue:
        """A query that raised, named in the log once per window per definition."""
        self.counters.failures += 1
        self.diagnose(
            f"failed:{plan.fingerprint}",
            "HUD analytics stat %s (%s) failed for %s: %s",
            plan.binding.stat_name,
            plan.binding.definition,
            plan.scope.describe(),
            exc,
        )
        return _unavailable(
            plan.binding,
            STATE_ERROR,
            str(exc) or exc.__class__.__name__,
            label=plan.label,
            description=plan.description,
        )

    def _render(
        self,
        plan: _Plan,
        result: QueryResult,
        elapsed_ms: float,
        from_cache: bool,
    ) -> AnalyticsStatValue:
        """Turn rows into the one number a cell shows, or say why it cannot."""
        binding, definition, scope = plan.binding, plan.definition, plan.scope

        def value(state: str, **kwargs: Any) -> AnalyticsStatValue:
            return AnalyticsStatValue(
                stat_name=binding.stat_name,
                definition=binding.definition,
                state=state,
                label=plan.label,
                description=plan.description,
                fingerprint=plan.fingerprint,
                elapsed_ms=elapsed_ms,
                from_aggregate_cache=from_cache,
                **kwargs,
            )

        rows = result.rows
        if not rows:
            return value(
                STATE_NO_DATA,
                reason=f"no hand matching {definition.name} for {scope.describe()}",
            )
        if len(rows) > 1:
            # Several rows mean the query grouped; a single cell would have to
            # pick one, and picking one silently is how a HUD lies.
            return value(
                STATE_UNSUPPORTED,
                reason=f"{definition.name} returned {len(rows)} rows; bind it to a breakdown instead",
            )
        row: QueryRow = rows[0]
        sample = int(row.opportunities)
        if not definition.display.has_sample(sample):
            return value(
                STATE_BELOW_SAMPLE,
                sample=sample,
                numerator=int(row.actions),
                unit=row.unit,
                reason=f"{sample} decisions, below the minimum of {definition.display.min_sample}",
            )
        raw = definition.display.value_of(row)
        if raw is None:
            return value(STATE_NO_DATA, sample=sample, numerator=int(row.actions), unit=row.unit, reason="no value")
        return value(
            STATE_OK,
            raw=raw,
            sample=sample,
            numerator=int(row.actions),
            unit=row.unit,
            rendered=definitions.format_row(definition, row, self.big_blind_cents, self.locale),
        )

    def diagnose(self, key: str, message: str, *args: Any) -> None:
        """Log at most once per window per subject.

        A HUD redraws every hand: an unavailable cell that logged every time
        would drown the log the user needs in order to fix it.
        """
        now = self._clock()
        last = self._diagnostics.get(key)
        if last is not None and now - last < DIAGNOSTIC_REPEAT_SECONDS:
            return
        self._diagnostics[key] = now
        log.warning(message, *args)

    def invalidate(self, reason: str = "") -> int:
        """Forget every cached value, because new hands were imported."""
        count = self.cache.invalidate()
        if count:
            log.debug("HUD analytics cache invalidated (%s): %d values dropped", reason or "unspecified", count)
        return count

    # -- reading without computing -----------------------------------------

    @staticmethod
    def text_for(values: Any, stat_name: str) -> str | None:
        """The text a finished batch stored for a cell, or ``None``.

        The render path calls this and nothing else, so a HUD cell can never
        block on a query: it shows the last batch's value, or the no-data
        convention while the next one is on its way.
        """
        if not isinstance(values, Mapping):
            return None
        value = values.get(stat_name)
        if isinstance(value, AnalyticsStatValue):
            return value.text
        if isinstance(value, str):
            return value
        return None


# ---------------------------------------------------------------------------
# Session: one HUD's bindings and values.
# ---------------------------------------------------------------------------


class AnalyticsStatSession:
    """A HUD's handle on analytics-backed cells.

    Holds the bindings the profile declares, the values of the last finished
    batch, and the revision that says whether those values belong to the hand
    currently on screen. Deliberately *not* a query runner: the work happens in
    :class:`AnalyticsStatProvider`, on the reader's thread.
    """

    def __init__(
        self,
        provider: AnalyticsStatProvider | None = None,
        bindings: Iterable[AnalyticsStatBinding] = (),
        *,
        values: Mapping[Any, Any] | None = None,
    ) -> None:
        self.provider = provider if provider is not None else AnalyticsStatProvider()
        self._bindings: dict[str, AnalyticsStatBinding] = {}
        # Keyed by player, because one session serves every seat of a table and
        # "the fold-to-cbet of seat 3" is a different number from seat 5's.
        self.values: dict[Any, dict[str, AnalyticsStatValue]] = {}
        self.revision = 0
        self._bound_revision = -1
        self.publish(values or {})
        for binding in bindings:
            self.bind(binding)

    @classmethod
    def from_config(
        cls,
        config: Any,
        provider: AnalyticsStatProvider | None = None,
        *,
        stat_set: str = "",
    ) -> AnalyticsStatSession:
        """The session a configuration's profile asks for (empty is normal).

        ``stat_set`` is the active profile, so the session binds only the cells
        that profile declares as analytics.
        """
        return cls(provider, bindings_from_config(config, stat_set=stat_set))

    def bind(self, binding: AnalyticsStatBinding) -> None:
        """Register a cell as analytics-backed."""
        self._bindings[binding.stat_name] = binding

    @property
    def bindings(self) -> tuple[AnalyticsStatBinding, ...]:
        return tuple(self._bindings.values())

    def binding_for(self, stat_name: str) -> AnalyticsStatBinding | None:
        """The binding a cell name resolves to, or ``None`` for a native stat."""
        return self._bindings.get(str(stat_name))

    def __bool__(self) -> bool:
        return bool(self._bindings)

    def publish(self, values_by_player: Mapping[Any, Any]) -> None:
        """Adopt a finished batch's values for the hand now on screen.

        ``values_by_player`` is what :func:`publish_hand_values` returns:
        ``{player_id: {stat_name: value}}``. A mapping that is not nested is
        ignored rather than half-read, because showing a value under the wrong
        seat is worse than showing none.
        """
        adopted: dict[Any, dict[str, AnalyticsStatValue]] = {}
        for player_id, cells in values_by_player.items():
            if not isinstance(cells, Mapping):
                continue
            kept = {str(name): value for name, value in cells.items() if isinstance(value, AnalyticsStatValue)}
            if kept:
                adopted[player_id] = kept
        self.values = adopted
        self._bound_revision = self.revision

    def text_for(self, stat_name: str, player_id: Any = None) -> str | None:
        """The cell text for the published hand, or ``None`` when not bound.

        ``None`` means "this is not an analytics cell", which is what keeps the
        native path a single dict lookup away. A bound cell with no value yet
        answers :data:`~fpdb_3_legacy.analytics_definitions.NO_DATA`: it is
        bound, so falling through to ``Stats.py`` would show a different stat
        under this cell's name.
        """
        if self.binding_for(stat_name) is None:
            return None
        value = self.value_for(stat_name, player_id)
        return NO_DATA if value is None else value.text

    def value_for(self, stat_name: str, player_id: Any = None) -> AnalyticsStatValue | None:
        """The full value behind one seat's cell, for a tooltip."""
        return self.values.get(player_id, {}).get(str(stat_name))

    def on_import(self, reason: str = "new hands imported") -> int:
        """New hands landed: the displayed analytics are now behind."""
        self.revision += 1
        self.values = {}
        return self.provider.invalidate(reason)

    @property
    def is_stale(self) -> bool:
        """Whether the published values predate the current revision."""
        return self._bound_revision != self.revision

    def pending(self, stat_names: Iterable[str], player_id: Any = None) -> list[AnalyticsStatBinding]:
        """The bindings of ``stat_names`` that no published value answers yet."""
        cells = self.values.get(player_id, {})
        out: list[AnalyticsStatBinding] = []
        for name in stat_names:
            binding = self.binding_for(name)
            if binding is not None and str(name) not in cells:
                out.append(binding)
        return out


# ---------------------------------------------------------------------------
# Publishing a batch's values, the way the HUD read service needs them.
# ---------------------------------------------------------------------------


def publish_hand_values(
    batch: Mapping[BatchKey, AnalyticsStatValue],
    scopes: Mapping[Any, PlayerScope],
    bindings: Sequence[AnalyticsStatBinding],
) -> dict[Any, dict[str, AnalyticsStatValue]]:
    """Regroup a batch's values by player, the way the HUD looks them up.

    ``compute_batch`` answers by (binding, player) because that is what it
    executes; a HUD cell asks by (player, stat name) because that is how a seat
    reads its own grid. This is the one place the two orders meet, so the
    mapping is built once per batch instead of once per cell.
    """
    by_player: dict[Any, dict[str, AnalyticsStatValue]] = {}
    for binding in bindings:
        for player_id, scope in scopes.items():
            value = batch.get((*binding.key(), scope.key()))
            if value is None:
                continue
            by_player.setdefault(player_id, {})[binding.stat_name] = value
    return by_player


__all__ = [
    "ANALYTICS_SOURCE",
    "CONTEXT_NOTE",
    "DEFAULT_LATENCY_BUDGET_MS",
    "DIAGNOSTIC_REPEAT_SECONDS",
    "INJECTABLE_CONTEXT",
    "NATIVE_SOURCE",
    "NOT_INJECTABLE_CONTEXT",
    "STATE_BAD_BINDING",
    "STATE_BELOW_SAMPLE",
    "STATE_ERROR",
    "STATE_NO_DATA",
    "STATE_OK",
    "STATE_UNKNOWN_DEFINITION",
    "STATE_UNKNOWN_PLAYER",
    "STATE_UNSUPPORTED",
    "AnalyticsStatBinding",
    "AnalyticsStatCache",
    "AnalyticsStatProvider",
    "AnalyticsStatSession",
    "AnalyticsStatValue",
    "PlayerScope",
    "ProviderCounters",
    "bindings_from_config",
    "publish_hand_values",
    "scope_for_entry",
    "scopes_for_stat_dict",
]
