"""Composable stat/filter query engine over the analytics rows (#297).

The analytics epic stores, per decision: the normalized event (#293), the
named situation (#294), the board it was made against (#295) and the sizing
distribution (#296). What it does not have -- and what this module is -- is a
way to *ask a question* of those rows without writing a dedicated Python
function and a dedicated SQL string per stat.

The engine has three composable pieces:

* **Filters** name a condition on one of the joined tables -- ``street``,
  ``position``, ``facing_3bet``, ``board_texture``, ``effective_stack_bb`` and
  so on -- and every filter carries its own SQL translation. A query is a
  dict of them, and they AND together.
* **Metrics** name what to compute over the filtered population. A frequency
  metric returns its numerator *and* denominator (the issue is explicit that a
  frequency without its sample size is a lie); profit metrics sum the
  per-hand-player money over the distinct players in the population.
* **Dimensions** name what to group by, from the same vocabulary as the
  filters.

The engine compiles that to parameterized SQL. Values never become SQL text --
every one is bound through the backend's placeholder -- and identifiers come
only from the registries in this file, so a filter or dimension name that is
not declared is a ``ValueError``, not a query. The compiled statement (and a
readable description of it) is returned for inspection, which is what #303's
research browser will show and what makes a result explainable.

Units are the event model's: money in cents, sizing and frequencies in basis
points, effective stack in hundredths of a big blind (``docs/action-event-model.md``).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from .board_features import FLAG_BITS
from .sizing_buckets import bucket_case_expression

# ---------------------------------------------------------------------------
# Sources: the tables a query can join, and how.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Source:
    """One table in the FROM clause, its alias and its join clause.

    ``join`` is relative to the fact alias ``A`` (``HandsActions``); an empty
    join means the source *is* the base. ``requires`` names the sources that
    must be joined first -- board features join on the situation's street, so
    they cannot be added without it.
    """

    alias: str
    table: str
    join: str = ""
    requires: tuple[str, ...] = ()


# Declaration order is join order: a source is only ever appended after the
# sources it requires, which is why ``requires`` pointing at SI is enough.
SOURCES: Final[dict[str, _Source]] = {
    "A": _Source("A", "HandsActions"),
    "H": _Source("H", "Hands", "JOIN Hands H ON H.id = A.handId", ("A",)),
    "G": _Source("G", "Gametypes", "JOIN Gametypes G ON G.id = H.gametypeId", ("H",)),
    "S": _Source("S", "Sites", "JOIN Sites S ON S.id = G.siteId", ("G",)),
    "P": _Source("P", "Players", "JOIN Players P ON P.id = A.playerId", ("A",)),
    "HP": _Source(
        "HP",
        "HandsPlayers",
        "LEFT JOIN HandsPlayers HP ON HP.handId = A.handId AND HP.playerId = A.playerId",
        ("A",),
    ),
    "SI": _Source(
        "SI",
        "HandsSituations",
        "LEFT JOIN HandsSituations SI ON SI.handId = A.handId AND SI.actionNo = A.actionNo",
        ("A",),
    ),
    # The first board only: a run-it-twice hand stores a second set of rows and
    # joining it would double every decision. ``board_run`` can be added later
    # without changing this: the primary board is boardId 1.
    "BF": _Source(
        "BF",
        "BoardFeatures",
        "LEFT JOIN BoardFeatures BF ON BF.handId = A.handId AND BF.boardId = 1"
        " AND BF.streetName = SI.streetName",
        ("SI",),
    ),
}

BASE_ALIAS: Final = "A"


def _expand_sources(aliases: Iterable[str]) -> list[str]:
    """Close a set of aliases under ``requires``, in declaration order."""
    needed: set[str] = set()
    stack = list(aliases)
    while stack:
        alias = stack.pop()
        if alias in needed:
            continue
        if alias not in SOURCES:
            raise ValueError(f"Unknown query source: {alias!r}")
        needed.add(alias)
        stack.extend(SOURCES[alias].requires)
    return [alias for alias in SOURCES if alias in needed]


def _from_clause(needed: Sequence[str]) -> str:
    """The FROM clause for a closed alias set, base first and joins in order."""
    parts = [f"FROM {SOURCES[BASE_ALIAS].table} A"]
    for alias in needed:
        join = SOURCES[alias].join
        if join:
            parts.append(join)
    return "\n  ".join(parts)


# ---------------------------------------------------------------------------
# Value coercion: what a caller may write, and the shape it takes in SQL.
# ---------------------------------------------------------------------------


def _as_list(value: Any) -> list[Any]:
    """One value or a collection of values, as a list (strings stay whole)."""
    if isinstance(value, (str, bytes)):
        return [value]
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    return [value]


def _as_range(value: Any) -> tuple[Any, Any]:
    """A ``[low, high]`` pair, either end optional (``None`` means unbounded)."""
    if isinstance(value, Mapping):
        return value.get("min"), value.get("max")
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return value[0], value[1]
    raise ValueError(f"A range filter needs [low, high] or {{min, max}}, not {value!r}")


# Button-relative seat names, as the hand viewer spells them: 0 is the button,
# the numbers count backwards through the late seats, and the blinds are the
# two negatives the event model already uses.
POSITION_CODES: Final[dict[str, int]] = {
    "btn": 0,
    "bu": 0,
    "button": 0,
    "d": 0,
    "co": 1,
    "cutoff": 1,
    "hj": 2,
    "hijack": 2,
    "lj": 3,
    "lojack": 3,
    "mp": 4,
    "mp1": 4,
    "mp2": 5,
    "utg": 6,
    "sb": -1,
    "small blind": -1,
    "smallblind": -1,
    "bb": -2,
    "big blind": -2,
    "bigblind": -2,
}

# The words a sizing filter may be written in. Per cent of the pot is what a
# player says out loud; basis points are what the rows store.
_PCT_TO_BP: Final = 100


def _positions(values: Any) -> list[int]:
    """Position names or codes to the integer codes the rows store."""
    out: list[int] = []
    for value in _as_list(values):
        if isinstance(value, bool):
            raise ValueError(f"Not a position: {value!r}")
        if isinstance(value, int):
            out.append(value)
            continue
        text = str(value).strip().lower()
        if text in POSITION_CODES:
            out.append(POSITION_CODES[text])
            continue
        try:
            out.append(int(text))
        except ValueError:
            raise ValueError(
                f"Unknown position {value!r}; use a code or one of {sorted(POSITION_CODES)}",
            ) from None
    return out


def _to_bp(values: Any) -> list[int]:
    """Per-cent sizing bounds to the basis points the rows store."""
    out: list[int] = []
    for value in values:
        if value is None:
            out.append(None)  # type: ignore[arg-type]  # an unbounded range end
            continue
        out.append(int(round(float(value) * _PCT_TO_BP)))
    return out


# ---------------------------------------------------------------------------
# Filters.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Filter:
    """One composable condition: where it reads, and how a value becomes SQL.

    ``kind`` picks the translation: ``scalar`` (equality), ``set`` (IN),
    ``range`` (inclusive bounds, either optional), ``bool`` (a boolean column),
    ``null_check`` (a foreign key: True means "set", False "null"),
    ``flagset`` (a bitmask column matched against named flags) and ``pattern``
    (JSON text containing a quoted word, e.g. a situation label).
    """

    column: str
    aliases: tuple[str, ...]
    kind: str = "scalar"
    coerce: Any = None


def _flag_bits(names: Any) -> list[int]:
    """Named texture/runout flags to their bits, refusing unknown names."""
    bits: list[int] = []
    for name in _as_list(names):
        key = str(name).strip().lower()
        if key not in FLAG_BITS:
            raise ValueError(f"Unknown board flag {name!r}; known: {sorted(FLAG_BITS)}")
        bits.append(FLAG_BITS[key])
    return bits


FILTERS: Final[dict[str, _Filter]] = {
    # -- hand / game identity ----------------------------------------------
    "site": _Filter("S.name", ("S",), "set"),
    "game": _Filter("G.category", ("G",), "set"),
    "limit": _Filter("G.limitType", ("G",), "set"),
    "currency": _Filter("G.currency", ("G",), "set"),
    "tournament": _Filter("H.tourneyId", ("H",), "null_check"),
    "big_blind": _Filter("G.bigBlind", ("G",), "range"),
    "stake_bb": _Filter("G.bigBlind", ("G",), "range"),
    "seats": _Filter("H.seats", ("H",), "range"),
    "max_seats": _Filter("G.maxSeats", ("G",), "range"),
    "session": _Filter("H.sessionId", ("H",), "set"),
    "hand_id": _Filter("A.handId", ("A",), "set"),
    "date_from": _Filter("H.startTime", ("H",), "range_low"),
    "date_to": _Filter("H.startTime", ("H",), "range_high"),
    # -- who ---------------------------------------------------------------
    "player": _Filter("P.name", ("P",), "set"),
    "players": _Filter("P.name", ("P",), "set"),
    "hero": _Filter("SI.isHero", ("SI",), "bool"),
    # -- seat / stack ------------------------------------------------------
    "position": _Filter("A.position", ("A",), "set", _positions),
    "opponent_position": _Filter("SI.facingPosition", ("SI",), "set", _positions),
    "relative_position": _Filter("A.relativePosition", ("A",), "range"),
    "in_position": _Filter("A.inPosition", ("A",), "bool"),
    "effective_stack_bb": _Filter("A.effectiveStackBB", ("A",), "range"),
    "effective_stack": _Filter("A.effectiveStack", ("A",), "range"),
    "stack_bucket": _Filter("SI.stackBucket", ("SI",), "set"),
    "spr": _Filter("A.sprBefore", ("A",), "range"),
    "players_in_hand": _Filter("A.playersInHand", ("A",), "range"),
    "multiway": _Filter("SI.multiway", ("SI",), "bool"),
    # -- street / pot ------------------------------------------------------
    "street": _Filter("SI.streetName", ("SI",), "set"),
    "street_index": _Filter("A.street", ("A",), "range"),
    "pot_type": _Filter("SI.potType", ("SI",), "set"),
    "pot_before": _Filter("A.potBefore", ("A",), "range"),
    "to_call": _Filter("A.toCall", ("A",), "range"),
    "pot_odds_bp": _Filter("SI.potOddsBp", ("SI",), "range"),
    # -- role / aggressor --------------------------------------------------
    "role": _Filter("SI.role", ("SI",), "set"),
    "is_aggressor": _Filter("SI.isAggressor", ("SI",), "bool"),
    "is_preflop_aggressor": _Filter("SI.isPreflopAggressor", ("SI",), "bool"),
    "is_previous_aggressor": _Filter("SI.isPreviousAggressor", ("SI",), "bool"),
    "in_position_vs_previous_aggressor": _Filter(
        "SI.inPositionVsPreviousAggressor", ("SI",), "bool",
    ),
    "in_position_vs_facing": _Filter("SI.inPositionVsFacing", ("SI",), "bool"),
    "facing_all_in": _Filter("SI.facingAllIn", ("SI",), "bool"),
    # -- actions -----------------------------------------------------------
    "action_taken": _Filter("A.actionType", ("A",), "set"),
    "action_faced": _Filter("A.facingActionType", ("A",), "set"),
    "response": _Filter("SI.response", ("SI",), "set"),
    "all_in": _Filter("A.allIn", ("A",), "bool"),
    "situation": _Filter("SI.labels", ("SI",), "label"),
    "primary_situation": _Filter("SI.primaryLabel", ("SI",), "set"),
    "situation_group": _Filter("SI.groupName", ("SI",), "set"),
    "enum_key": _Filter("SI.enumKey", ("SI",), "set"),
    "enum_response": _Filter("SI.enumResponse", ("SI",), "set"),
    "raisers_before": _Filter("SI.raisesBefore", ("SI",), "range"),
    # -- sizing ------------------------------------------------------------
    "sizing_bp": _Filter("A.sizingBp", ("A",), "range"),
    "facing_sizing_bp": _Filter("A.facingSizingBp", ("A",), "range"),
    "bet_sizing_pct": _Filter("A.sizingBp", ("A",), "range_pct"),
    "facing_sizing_pct": _Filter("A.facingSizingBp", ("A",), "range_pct"),
    # -- board -------------------------------------------------------------
    "board_rank": _Filter("BF.rankBucket", ("BF",), "set"),
    "board_suit": _Filter("BF.suitStructure", ("BF",), "set"),
    "board_pairing": _Filter("BF.pairing", ("BF",), "set"),
    "board_connectivity": _Filter("BF.connectivity", ("BF",), "set"),
    "board_texture": _Filter("BF.textureMask", ("BF",), "flagset"),
    "board_texture_all": _Filter("BF.textureMask", ("BF",), "flagset_all"),
    "board_runout": _Filter("BF.runoutMask", ("BF",), "flagset"),
    "board_street": _Filter("BF.street", ("BF",), "range"),
}

# Filters whose value is a label present in the situation's JSON ``labels``
# text. The pattern is bound as a parameter -- the word is never concatenated
# into the SQL -- so a label name cannot smuggle syntax.
_LABEL_PATTERN: Final = '%"{}"%'


def _set_fragment(column: str, values: list[Any], placeholder: str) -> tuple[list[str], list[Any]]:
    """Equality for one value, ``IN`` for several, no rows for an empty set."""
    if not values:
        return ["1=0"], []
    if len(values) == 1:
        return [f"{column} = {placeholder}"], [values[0]]
    marks = ", ".join(placeholder for _ in values)
    return [f"{column} IN ({marks})"], list(values)


def _range_fragment(column: str, low: Any, high: Any, placeholder: str) -> tuple[list[str], list[Any]]:
    """Inclusive bounds, either end optional."""
    fragments: list[str] = []
    params: list[Any] = []
    if low is not None:
        fragments.append(f"{column} >= {placeholder}")
        params.append(low)
    if high is not None:
        fragments.append(f"{column} <= {placeholder}")
        params.append(high)
    return (["(" + " AND ".join(fragments) + ")"] if fragments else []), params


def _range_for(
    kind: str,
    column: str,
    value: Any,
    placeholder: str,
) -> tuple[list[str], list[Any]]:
    """A range filter in its four shapes: pair, pair of per cents, or one bound."""
    if kind == "range_low":
        return _range_fragment(column, value, None, placeholder)
    if kind == "range_high":
        return _range_fragment(column, None, value, placeholder)
    low, high = _as_range(value)
    if kind == "range_pct":
        low, high = _to_bp((low, high))
    return _range_fragment(column, low, high, placeholder)


def _flag_fragment(column: str, kind: str, value: Any) -> tuple[list[str], list[Any]]:
    """Named texture/runout flags matched against a bitmask column."""
    bits = _flag_bits(value)
    if not bits:
        return ["1=0"], []
    joiner = " AND " if kind == "flagset_all" else " OR "
    fragments = [f"({column} & {bit}) <> 0" for bit in bits]
    return ["(" + joiner.join(fragments) + ")"], []


def _label_fragment(column: str, value: Any, placeholder: str) -> tuple[list[str], list[Any]]:
    """A word present in the situation's JSON list, matched with quotes."""
    fragments: list[str] = []
    params: list[Any] = []
    for label in _as_list(value):
        fragments.append(f"{column} LIKE {placeholder}")
        params.append(_LABEL_PATTERN.format(label))
    if not fragments:
        return ["1=0"], []
    return ["(" + " OR ".join(fragments) + ")"], params


def _compile_filter(
    name: str,
    value: Any,
    placeholder: str,
    backend: str,
) -> tuple[list[str], list[Any]]:
    """One filter to (SQL fragments, bound parameters)."""
    spec = FILTERS.get(name)
    if spec is None:
        raise ValueError(f"Unknown filter {name!r}; known filters: {sorted(FILTERS)}")
    column = spec.column
    if spec.kind in ("scalar", "set"):
        values = _as_list(value)
        values = spec.coerce(values) if spec.coerce is not None else values
        return _set_fragment(column, values, placeholder)
    if spec.kind in ("range", "range_pct", "range_low", "range_high"):
        return _range_for(spec.kind, column, value, placeholder)
    if spec.kind == "bool":
        literal = "1" if backend == "sqlite" else "TRUE"
        return [f"{column} = {literal}" if value else f"(NOT {column} = {literal})"], []
    if spec.kind == "null_check":
        return ([f"{column} IS NOT NULL"] if value else [f"{column} IS NULL"]), []
    if spec.kind in ("flagset", "flagset_all"):
        return _flag_fragment(column, spec.kind, value)
    if spec.kind == "label":
        return _label_fragment(column, value, placeholder)
    raise ValueError(f"Unknown filter kind for {name!r}: {spec.kind!r}")


def compile_filters(
    filters: Mapping[str, Any],
    placeholder: str = "%s",
    backend: str = "mysql",
) -> tuple[list[str], list[Any], set[str]]:
    """Translate a filter dict to (conditions, parameters, needed sources)."""
    conditions: list[str] = []
    params: list[Any] = []
    aliases: set[str] = set()
    for name, value in filters.items():
        if value is None:
            continue
        fragments, values = _compile_filter(name, value, placeholder, backend)
        conditions.extend(fragments)
        params.extend(values)
        aliases.update(FILTERS[name].aliases)
    return conditions, params, aliases


def filter_sources(filters: Mapping[str, Any]) -> set[str]:
    """The sources a filter dict reads, for callers planning joins."""
    return {alias for name in filters for alias in FILTERS[name].aliases}


# ---------------------------------------------------------------------------
# Dimensions.
# ---------------------------------------------------------------------------

# A dimension is a grouped expression plus the sources it reads. The bucket
# dimensions reuse #296's CASE expression, so a histogram from Python and one
# from the database group by exactly the same boundaries.
DIMENSIONS: Final[dict[str, tuple[str, tuple[str, ...]]]] = {
    "street": ("SI.streetName", ("SI",)),
    "position": ("A.position", ("A",)),
    "opponent_position": ("SI.facingPosition", ("SI",)),
    "relative_position": ("A.relativePosition", ("A",)),
    "in_position": ("A.inPosition", ("A",)),
    "stack_bucket": ("SI.stackBucket", ("SI",)),
    "effective_stack_bb": ("A.effectiveStackBB", ("A",)),
    "spr": ("A.sprBefore", ("A",)),
    "pot_type": ("SI.potType", ("SI",)),
    "role": ("SI.role", ("SI",)),
    "response": ("SI.response", ("SI",)),
    "action_taken": ("A.actionType", ("A",)),
    "action_faced": ("A.facingActionType", ("A",)),
    "all_in": ("A.allIn", ("A",)),
    "multiway": ("SI.multiway", ("SI",)),
    "player": ("P.name", ("P",)),
    "site": ("S.name", ("S",)),
    "game": ("G.category", ("G",)),
    "limit": ("G.limitType", ("G",)),
    "tournament": ("H.tourneyId", ("H",)),
    "session": ("H.sessionId", ("H",)),
    "sizing_bucket": (bucket_case_expression("sizingBp"), ("A",)),
    "facing_sizing_bucket": (bucket_case_expression("facingSizingBp"), ("A",)),
    "board_rank": ("BF.rankBucket", ("BF",)),
    "board_suit": ("BF.suitStructure", ("BF",)),
    "board_pairing": ("BF.pairing", ("BF",)),
    "board_connectivity": ("BF.connectivity", ("BF",)),
    "primary_situation": ("SI.primaryLabel", ("SI",)),
    "enum_key": ("SI.enumKey", ("SI",)),
}


def _dimension(name: str) -> tuple[str, tuple[str, ...]]:
    if name not in DIMENSIONS:
        raise ValueError(f"Unknown group_by dimension {name!r}; known: {sorted(DIMENSIONS)}")
    return DIMENSIONS[name]


# ---------------------------------------------------------------------------
# Metrics.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Metric:
    """What a metric computes over the filtered population.

    ``value_sql`` is an aggregate over the fact rows (``None`` means "count the
    rows matching the numerator filters"). ``player_expression`` marks a
    metric whose money is per hand-player: it is summed over the *distinct*
    (handId, playerId) pairs in the filtered population, so three decisions by
    one player do not triple their profit. ``per_opportunity`` divides that
    sum by the decision count, which is what "profit per opportunity" means.
    """

    name: str
    unit: str
    value_sql: str | None = None
    frequency: bool = False
    player_expression: str | None = None
    per_opportunity: bool = False
    ready: bool = True


METRICS: Final[dict[str, _Metric]] = {
    "opportunities": _Metric("opportunities", "count", value_sql="COUNT(*)"),
    "action_count": _Metric("action_count", "count"),
    "frequency": _Metric("frequency", "bp", frequency=True),
    "average_sizing": _Metric(
        "average_sizing",
        "bp",
        value_sql="AVG(CASE WHEN A.sizingBp > 0 THEN A.sizingBp END)",
    ),
    "average_facing_sizing": _Metric(
        "average_facing_sizing",
        "bp",
        value_sql="AVG(CASE WHEN A.facingSizingBp > 0 THEN A.facingSizingBp END)",
    ),
    "average_spr": _Metric("average_spr", "centi", value_sql="AVG(A.sprBefore)"),
    "average_pot": _Metric("average_pot", "cents", value_sql="AVG(A.potBefore)"),
    "total_profit": _Metric("total_profit", "cents", player_expression="HP.totalProfit"),
    "profit_per_opportunity": _Metric(
        "profit_per_opportunity", "cents", player_expression="HP.totalProfit", per_opportunity=True,
    ),
    "all_in_ev": _Metric("all_in_ev", "cents", player_expression="HP.allInEV"),
    "ev_per_opportunity": _Metric(
        "ev_per_opportunity", "cents", player_expression="HP.allInEV", per_opportunity=True,
    ),
}

# Named frequency metrics carry their numerator so the caller does not have to
# restate it. ``frequency`` itself takes the numerator from the query, which is
# how an unanticipated split ("fold to a check-raise by a short stack") stays
# expressible without a new metric.
IMPLIED_NUMERATORS: Final[dict[str, dict[str, Any]]] = {
    "fold_frequency": {"response": "fold"},
    "call_frequency": {"response": "call"},
    "raise_frequency": {"response": ["raise", "complete"]},
    "bet_frequency": {"response": "bet"},
    "check_frequency": {"response": "check"},
}

KNOWN_METRICS: Final[tuple[str, ...]] = tuple(
    sorted(set(METRICS) | set(IMPLIED_NUMERATORS)),
)


# ---------------------------------------------------------------------------
# The query and its compiled form.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Query:
    """A metric, its filters, the dimensions to group by and a page window."""

    metric: str
    filters: Mapping[str, Any] = field(default_factory=dict)
    numerator: Mapping[str, Any] = field(default_factory=dict)
    group_by: tuple[str, ...] = ()
    limit: int | None = None
    offset: int = 0

    def resolved(self) -> tuple[_Metric, dict[str, Any], dict[str, Any]]:
        """The metric spec, the filters and the numerator, with implied parts added."""
        if self.metric in IMPLIED_NUMERATORS:
            spec = METRICS["frequency"]
            numerator = {**IMPLIED_NUMERATORS[self.metric], **self.numerator}
        elif self.metric in METRICS:
            spec = METRICS[self.metric]
            numerator = dict(self.numerator)
        else:
            raise ValueError(f"Unknown metric {self.metric!r}; known metrics: {list(KNOWN_METRICS)}")
        return spec, dict(self.filters), numerator


@dataclass(frozen=True)
class CompiledQuery:
    """A compiled query: the SQL, its parameters and a readable description."""

    sql: str
    params: tuple[Any, ...]
    group_by: tuple[str, ...]
    metric: str
    player_sql: str | None = None
    player_params: tuple[Any, ...] = ()
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "group_by": list(self.group_by),
            "sql": self.sql,
            "params": list(self.params),
            "player_sql": self.player_sql,
            "player_params": list(self.player_params),
            "description": self.description,
        }


def _numerator_case(
    numerator: Mapping[str, Any],
    placeholder: str,
    backend: str,
) -> tuple[str, list[Any]]:
    """The CASE condition counting a numerator, and its parameters.

    With no numerator filters the condition is a constant, so a plain
    ``action_count`` over a filtered population counts the whole population.
    """
    conditions, params, _aliases = compile_filters(numerator, placeholder, backend)
    if not conditions:
        return "1=1", params
    return " AND ".join(f"({condition})" for condition in conditions), params


def _describe(
    metric: str,
    filters: Mapping[str, Any],
    numerator: Mapping[str, Any],
    group_by: tuple[str, ...],
    limit: int | None,
    offset: int,
) -> str:
    """A readable rendering of what the query asks, for logs and the browser."""
    lines = [f"metric: {metric}"]
    if filters:
        rendered = ", ".join(f"{name}={value!r}" for name, value in sorted(filters.items()))
        lines.append(f"filters: {rendered}")
    if numerator:
        rendered = ", ".join(f"{name}={value!r}" for name, value in sorted(numerator.items()))
        lines.append(f"numerator: {rendered}")
    lines.append(f"group_by: {', '.join(group_by) if group_by else '(none)'}")
    if limit is not None:
        lines.append(f"page: limit={limit} offset={offset}")
    return "\n".join(lines)


def compile_query(
    query: Query,
    placeholder: str = "%s",
    backend: str = "mysql",
) -> CompiledQuery:
    """Translate a :class:`Query` into parameterized SQL, nothing executed."""
    if backend not in ("mysql", "postgresql", "sqlite"):
        raise ValueError(f"Unknown backend {backend!r}")
    spec, filters, numerator = query.resolved()

    where, where_params, aliases = compile_filters(filters, placeholder, backend)
    for dimension in query.group_by:
        _expression, dimension_aliases = _dimension(dimension)
        aliases.update(dimension_aliases)

    needed = _expand_sources(aliases | {"A"})
    from_clause = _from_clause(needed)

    params: list[Any] = []
    select: list[str] = []
    group_expressions: list[str] = []
    for dimension in query.group_by:
        expression, _ = _dimension(dimension)
        select.append(f"{expression} AS {dimension}")
        group_expressions.append(expression)

    select.append("COUNT(*) AS opportunities")

    case_condition, case_params = _numerator_case(numerator, placeholder, backend)
    params.extend(case_params)
    if spec.value_sql is not None:
        select.append(f"{spec.value_sql} AS value")
    else:
        select.append(f"SUM(CASE WHEN {case_condition} THEN 1 ELSE 0 END) AS actions")

    sql_parts = ["SELECT\n  " + ",\n  ".join(select), from_clause]
    if where:
        sql_parts.append("WHERE " + " AND ".join(f"({condition})" for condition in where))
    if group_expressions:
        sql_parts.append("GROUP BY " + ", ".join(group_expressions))
        sql_parts.append("ORDER BY " + ", ".join(query.group_by))
    if query.limit is not None:
        sql_parts.append(f"LIMIT {placeholder}")
        params.append(int(query.limit))
        sql_parts.append(f"OFFSET {placeholder}")
        params.append(int(query.offset))
    sql = "\n".join(sql_parts)
    params.extend(where_params)

    player_sql: str | None = None
    player_params: list[Any] = []
    if spec.player_expression is not None:
        # Sum the money over the distinct (handId, playerId) pairs the filters
        # select: a player's hand profit is a property of the hand, not of each
        # decision they made in it.
        inner_group = [f"{_dimension(name)[0]} AS {name}" for name in query.group_by]
        inner_select = ", ".join([*inner_group, "A.handId AS handId", "A.playerId AS playerId"])
        inner_where = " AND ".join(f"({condition})" for condition in where) or "1=1"
        player_columns = [f"P.{name}" for name in query.group_by]
        player_sql = "\n".join(
            [
                "SELECT\n  " + (",\n  ".join(player_columns + [f"SUM(HP.{_player_column(spec)}) AS value"]))
                if player_columns
                else f"SELECT SUM(HP.{_player_column(spec)}) AS value",
                "FROM (",
                f"  SELECT DISTINCT {inner_select}",
                f"  {from_clause}",
                f"  WHERE {inner_where}",
                ") P",
                "JOIN HandsPlayers HP ON HP.handId = P.handId AND HP.playerId = P.playerId",
                ("GROUP BY " + ", ".join(player_columns)) if player_columns else "",
            ],
        )
        player_params.extend(where_params)

    return CompiledQuery(
        sql=sql,
        params=tuple(params),
        group_by=tuple(query.group_by),
        metric=query.metric,
        player_sql=player_sql,
        player_params=tuple(player_params),
        description=_describe(query.metric, filters, numerator, tuple(query.group_by), query.limit, query.offset),
    )


def _player_column(spec: _Metric) -> str:
    """The HandsPlayers column a player-scoped metric sums."""
    assert spec.player_expression is not None
    return spec.player_expression.split(".", 1)[1]


def compile_hand_ids(
    query: Query,
    placeholder: str = "%s",
    backend: str = "mysql",
    include_numerator: bool = False,
) -> CompiledQuery:
    """The matching hand ids, distinct and ordered -- the drill-down query.

    The hands behind a result row are the *population* the metric was computed
    over (the denominator), not only the hands where the numerator fired: a
    fold frequency is "these hands, of which N folds". Pass
    ``include_numerator=True`` to narrow to the numerator.
    """
    _spec, filters, numerator = query.resolved()
    combined = {**filters, **numerator} if include_numerator else dict(filters)
    where, where_params, aliases = compile_filters(combined, placeholder, backend)
    needed = _expand_sources(aliases | {"A"})
    sql_parts = [
        "SELECT DISTINCT A.handId AS handId",
        _from_clause(needed),
    ]
    if where:
        sql_parts.append("WHERE " + " AND ".join(f"({condition})" for condition in where))
    sql_parts.append("ORDER BY A.handId")
    params = list(where_params)
    if query.limit is not None:
        sql_parts.append(f"LIMIT {placeholder}")
        params.append(int(query.limit))
        sql_parts.append(f"OFFSET {placeholder}")
        params.append(int(query.offset))
    return CompiledQuery(
        sql="\n".join(sql_parts),
        params=tuple(params),
        group_by=(),
        metric=f"{query.metric} (hand ids)",
        description=_describe(f"{query.metric} (hand ids)", combined, {}, (), query.limit, query.offset),
    )


# ---------------------------------------------------------------------------
# Execution.
# ---------------------------------------------------------------------------


@dataclass
class QueryRow:
    """One grouped result: the numerator, the denominator and the metric."""

    group: dict[str, Any]
    opportunities: int
    actions: int
    value: float | None
    unit: str
    frequency_bp: int | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = dict(self.group)
        out["opportunities"] = self.opportunities
        out["actions"] = self.actions
        out["value"] = self.value
        out["unit"] = self.unit
        if self.frequency_bp is not None:
            out["frequency_bp"] = self.frequency_bp
        return out


@dataclass
class QueryResult:
    """A query's rows, plus the statement and description that produced them."""

    rows: list[QueryRow]
    compiled: CompiledQuery

    def as_dicts(self) -> list[dict[str, Any]]:
        return [row.as_dict() for row in self.rows]

    @property
    def total_opportunities(self) -> int:
        return sum(row.opportunities for row in self.rows)

    @property
    def total_actions(self) -> int:
        return sum(row.actions for row in self.rows)


def _backend_name(db: Any) -> str:
    """The Database backend constant as the compiler's name."""
    backend = getattr(db, "backend", None)
    names: dict[int, str] = {2: "mysql", 3: "postgresql", 4: "sqlite"}
    return names[backend] if isinstance(backend, int) and backend in names else "mysql"


def _placeholder(db: Any) -> str:
    try:
        return str(db.sql.query["placeholder"])
    except (AttributeError, KeyError):
        return "%s"


def run_query(db: Any, query: Query) -> QueryResult:
    """Compile and execute a query against a Database, merging player money."""
    backend = _backend_name(db)
    placeholder = _placeholder(db)
    compiled = compile_query(query, placeholder, backend)
    cursor = db.get_cursor()
    cursor.execute(compiled.sql, compiled.params)
    columns = [description[0] for description in cursor.description]
    rows = [dict(zip(columns, raw)) for raw in cursor.fetchall()]

    player_totals: dict[tuple[Any, ...], float] = {}
    if compiled.player_sql is not None:
        cursor.execute(compiled.player_sql, compiled.player_params)
        player_columns = [description[0] for description in cursor.description]
        for raw in cursor.fetchall():
            row = dict(zip(player_columns, raw))
            key = tuple(row[name] for name in query.group_by)
            player_totals[key] = float(row["value"] or 0)

    spec, _filters, _numerator = query.resolved()
    result_rows: list[QueryRow] = []
    for row in rows:
        key = tuple(row[name] for name in query.group_by)
        group = {name: row[name] for name in query.group_by}
        opportunities = int(row["opportunities"] or 0)
        actions = int(row.get("actions") or 0)
        value: float | None
        if spec.player_expression is not None:
            total = player_totals.get(key, 0.0)
            value = round(total / opportunities, 4) if spec.per_opportunity and opportunities else total
        elif spec.frequency:
            value = actions
        elif spec.value_sql is None:
            value = actions
        else:
            value = row.get("value")
        frequency_bp = actions * 10000 // opportunities if spec.frequency and opportunities else None
        result_rows.append(
            QueryRow(
                group=group,
                opportunities=opportunities,
                actions=actions,
                value=value,
                unit=spec.unit,
                frequency_bp=frequency_bp,
            ),
        )
    return QueryResult(rows=result_rows, compiled=compiled)


def run_hand_ids(db: Any, query: Query, include_numerator: bool = False) -> list[int]:
    """The matching hand ids, the drill-down entry point of a result row."""
    compiled = compile_hand_ids(query, _placeholder(db), _backend_name(db), include_numerator)
    cursor = db.get_cursor()
    cursor.execute(compiled.sql, compiled.params)
    return [int(row[0]) for row in cursor.fetchall()]


__all__ = [
    "BASE_ALIAS",
    "DIMENSIONS",
    "FILTERS",
    "IMPLIED_NUMERATORS",
    "KNOWN_METRICS",
    "METRICS",
    "POSITION_CODES",
    "SOURCES",
    "CompiledQuery",
    "Query",
    "QueryResult",
    "QueryRow",
    "compile_filters",
    "compile_hand_ids",
    "compile_query",
    "filter_sources",
    "run_hand_ids",
    "run_query",
]
