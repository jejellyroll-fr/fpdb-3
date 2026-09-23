"""The research browser's model: presets, a described result, drill-down rows (#303).

The query engine (#297) answers a question in one call -- but a browser is not
one call. It is a filter list that grows and shrinks without losing the
population, a result table whose every cell says what it counts and on what
denominator, a hand list that opens the *hands behind the row*, and a place to
keep the questions worth keeping. This module is that layer, deliberately Qt
free: the GUI reads it, a CLI uses it, the tests exercise it without a window.

Three responsibilities:

* **Filter specs** -- the query engine's filters, grouped and described, so a
  browser can offer them by name instead of hard-coding them twice;
* **Presets** -- named ``Query`` values stored as JSON next to the fpdb
  config, in the engine's own vocabulary, never a SQL fragment;
* **Drill-down rows** -- the *hands behind a result row*, with the columns a
  human needs to pick the interesting ones out of a list, and a per-row
  numerator switch so "the hands where the player folded" and "all the hands
  in the population" are both one call.

Nothing here writes to the database, and nothing here accepts SQL from
anyone: a preset is a metric name, filter names and dimension names, and
every one of the three is validated against the engine's own tables before
it is ever compiled.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final

from . import Card
from .analytics_query import (
    DIMENSIONS,
    FILTERS,
    KNOWN_METRICS,
    Query,
    _backend_name,
    _expand_sources,
    _from_clause,
    _placeholder,
    compile_filters,
    escape_literal_percent,
    run_hand_ids,
    run_query,
)
from .Configuration import CONFIG_PATH
from .db_rows import rows_by_alias
from .loggingFpdb import get_logger
from .research_labels import (
    BEGINNER_DIMENSIONS,
    Choice,
    describe_query,
    dimension_choices,
    dimension_label,
    filter_choices,
    filter_description,
    filter_example,
    filter_label,
    filter_unit,
    is_expert_only,
    value_label,
)

log = get_logger("research_browser")


# ---------------------------------------------------------------------------
# The filter vocabulary, grouped for a browser's picker.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FilterSpec:
    """One filter as a browser may offer it: engine metadata *and* user language.

    ``value_kind`` is what a GUI builds an input for -- ``bool`` a tri-state
    selector, ``set`` a list of choices, ``range`` two number fields, ``flags``
    a list of named flags -- and it comes from the engine's own ``kind`` rather
    than a second table: the browser shapes the input, the engine still
    validates the value.

    ``description`` stays the engine's column, for the expert view and for
    diagnostics; the issue is explicit that it must *not* be the user-facing
    description, so ``label`` and ``user_description`` carry poker language and
    ``choices`` carries the closed domain a selector can offer (issue #329).
    """

    name: str
    group: str
    value_kind: str
    description: str
    label: str = ""
    user_description: str = ""
    unit: str = ""
    choices: tuple[Choice, ...] = ()
    #: True when ``choices`` were read from this database rather than from the
    #: engine's own vocabulary. Such a list is a shortcut, not a closed set: it
    #: is only as fresh as the last time it was read, and an import can add a
    #: value to it while the pane is open (#355).
    from_database: bool = False
    examples: tuple[str, ...] = ()
    expert_only: bool = False

    @property
    def multi(self) -> bool:
        """Whether several values may be selected at once."""
        return self.value_kind in ("set", "flags", "scalar")


_GROUP_OF: Final = {
    "site": "game", "game": "game", "limit": "game", "currency": "game",
    "tournament": "game", "big_blind": "game", "stake_bb": "game",
    "seats": "game", "max_seats": "game", "session": "game",
    "hand_id": "game", "hand_id_from": "game", "hand_id_to": "game", "tournament_id": "game",
    "date_from": "game", "date_to": "game",
    "player": "who", "players": "who", "identity": "who", "hero": "who",
    "position": "seat", "opponent_position": "seat", "relative_position": "seat",
    "in_position": "seat", "effective_stack_bb": "seat", "effective_stack": "seat",
    "stack_bucket": "seat", "spr": "seat", "spr_bucket": "seat", "effective_stack_bucket": "seat", "players_in_hand": "seat",
    "multiway": "street", "street": "street", "street_index": "street",
    "pot_type": "street", "pot_before": "street", "to_call": "street",
    "pot_odds_bp": "street", "role": "street", "is_aggressor": "street",
    "is_preflop_aggressor": "street", "is_previous_aggressor": "street",
    "in_position_vs_previous_aggressor": "street", "in_position_vs_facing": "street",
    "facing_all_in": "street",
    "action_taken": "action", "action_faced": "action", "response": "action",
    "all_in": "action", "situation": "action", "primary_situation": "action",
    "situation_group": "action", "enum_key": "action", "enum_response": "action",
    "raisers_before": "action",
    "starting_hand": "cards", "hole_cards_known": "cards",
    "sizing_bp": "sizing", "facing_sizing_bp": "sizing",
    "sizing_bucket": "sizing", "facing_sizing_bucket": "sizing",
    "bet_sizing_pct": "sizing", "facing_sizing_pct": "sizing",
    "board_rank": "board", "board_suit": "board", "board_pairing": "board",
    "board_connectivity": "board", "board_present": "board", "board_texture": "board",
    "board_texture_all": "board", "board_runout": "board", "board_street": "board",
    "made_hand": "strength", "made_hand_rank": "strength", "pair_detail": "strength",
    "nutness": "strength", "nutness_beats": "strength", "nutness_holdings": "strength",
    "draw": "strength", "draw_all": "strength", "draw_none": "strength",
    "blocker": "strength", "blocker_all": "strength", "blocker_none": "strength",
    "hand_state_street": "strength", "hand_state_known": "strength",
}

_KIND_OF_ENGINE_KIND: Final = {
    "scalar": "scalar",
    "set": "set",
    "range": "range",
    "range_low": "range",
    "range_high": "range",
    "range_pct": "range",
    "bool": "bool",
    "hero": "bool",
    "null_check": "bool",
    "label": "set",
    "flagset": "flags",
    "flagset_all": "flags",
    "flagset_none": "flags",
    "identity_set": "set",
}


def _value_kind(filter_spec: Any) -> str:
    return _KIND_OF_ENGINE_KIND.get(filter_spec.kind, "scalar")


def _make_filter_spec(name: str, spec: Any) -> FilterSpec:
    """One engine filter, described in the vocabulary a browser offers."""
    example = filter_example(name)
    return FilterSpec(
        name=name,
        group=_GROUP_OF.get(name, "other"),
        value_kind=_value_kind(spec),
        description=spec.column,
        label=filter_label(name),
        user_description=filter_description(name),
        unit=filter_unit(name),
        choices=filter_choices(name),
        examples=(example,) if example else (),
        expert_only=is_expert_only(name),
    )


FILTER_SPECS: Final[tuple[FilterSpec, ...]] = tuple(
    sorted(
        (_make_filter_spec(name, spec) for name, spec in FILTERS.items()),
        key=lambda spec: (spec.group, spec.name),
    ),
)

FILTER_GROUPS: Final[tuple[str, ...]] = tuple(
    sorted({spec.group for spec in FILTER_SPECS}),
)


def filter_spec(name: str) -> FilterSpec:
    """The description of one filter, for a browser's picker and validator."""
    if name not in FILTERS:
        raise ValueError(f"Unknown filter {name!r}; known: {sorted(FILTERS)}")
    return next(item for item in FILTER_SPECS if item.name == name)


@dataclass(frozen=True)
class DimensionSpec:
    """One group-by dimension as the breakdown picker offers it (issue #329).

    A dimension is not a filter -- it decides *how a result is split*, not which
    decisions are in it -- so it gets its own spec: a label, the closed domain a
    value has when it has one, and whether Beginner mode should offer it.
    """

    name: str
    label: str
    group: str
    choices: tuple[Choice, ...] = ()
    beginner: bool = False


def _make_dimension_spec(name: str) -> DimensionSpec:
    return DimensionSpec(
        name=name,
        label=dimension_label(name),
        group=_GROUP_OF.get(name, "other"),
        choices=dimension_choices(name),
        beginner=name in BEGINNER_DIMENSIONS,
    )


DIMENSION_SPECS: Final[tuple[DimensionSpec, ...]] = tuple(
    sorted(
        (_make_dimension_spec(name) for name in DIMENSIONS),
        key=lambda spec: (spec.group, spec.name),
    ),
)


def dimension_spec(name: str) -> DimensionSpec:
    """The description of one group-by dimension, for the breakdown picker."""
    if name not in DIMENSIONS:
        raise ValueError(f"Unknown dimension {name!r}; known: {sorted(DIMENSIONS)}")
    return next(item for item in DIMENSION_SPECS if item.name == name)


# ---------------------------------------------------------------------------
# Presets: named queries, stored as JSON beside the fpdb config.
# ---------------------------------------------------------------------------

PRESET_VERSION: Final = 1


def validate_preset(payload: Mapping[str, Any]) -> dict[str, Any]:
    """One preset to its canonical form, or ``ValueError`` with the reason.

    A preset is a metric name, optional filters, an optional numerator, and
    optional group-by dimensions. Everything is checked against the engine's
    tables here -- the single place a typo can be caught before it becomes a
    broken query button.
    """
    if not isinstance(payload, Mapping):
        raise ValueError(f"A preset is a mapping, not {type(payload).__name__}")
    metric = payload.get("metric")
    if metric not in KNOWN_METRICS:
        raise ValueError(f"Unknown metric {metric!r}; known: {sorted(KNOWN_METRICS)}")
    filters = payload.get("filters", {})
    if not isinstance(filters, Mapping):
        raise ValueError(f"filters must be a mapping, not {type(filters).__name__}")
    unknown = [name for name in filters if name not in FILTERS]
    if unknown:
        raise ValueError(f"Unknown filters {sorted(unknown)}; known: {sorted(FILTERS)}")
    numerator = payload.get("numerator", {})
    if not isinstance(numerator, Mapping):
        raise ValueError(f"numerator must be a mapping, not {type(numerator).__name__}")
    unknown = [name for name in numerator if name not in FILTERS]
    if unknown:
        raise ValueError(f"Unknown numerator filters {sorted(unknown)}; known: {sorted(FILTERS)}")
    group_by = payload.get("group_by", ())
    if isinstance(group_by, str):
        group_by = (group_by,)
    unknown = [name for name in group_by if name not in DIMENSIONS]
    if unknown:
        raise ValueError(f"Unknown dimensions {sorted(unknown)}; known: {sorted(DIMENSIONS)}")
    return {
        "metric": metric,
        "filters": dict(filters),
        "numerator": dict(numerator),
        "group_by": tuple(group_by),
        "description": str(payload.get("description", "")).strip(),
    }


def describe_preset(preset: Mapping[str, Any]) -> str:
    """The preset's question in plain poker language (issue #329).

    Re-exported here so a browser has one import for "what the panes express"
    and "what that means in words": the summary is generated from the same
    filter metadata the controls are built from, never hand-written per preset.
    """
    return describe_query(preset)


@dataclass(frozen=True)
class ExampleQuestion:
    """A ready-made question the first-run screen can offer (issue #329).

    ``preset`` is engine vocabulary like any other preset -- it is validated by
    ``validate_preset`` before it is offered -- so an example question and a
    saved one run through exactly the same path.
    """

    name: str
    description: str
    preset: Mapping[str, Any]


# The first-run questions. A bare minimum on purpose: the shipped library of
# #330 is the real answer, and ``example_questions`` prefers it when it exists.
EXAMPLES: Final[tuple[ExampleQuestion, ...]] = (
    ExampleQuestion(
        "Fold versus a flop c-bet, by bet size",
        "How often do players fold to a continuation bet, split by how big it was?",
        {
            "metric": "fold_frequency",
            "filters": {"street": "flop", "primary_situation": "facing_cbet"},
            "group_by": ("facing_sizing_bucket",),
        },
    ),
    ExampleQuestion(
        "Open raise rate by position",
        "How often does each seat raise first in when nobody has entered the pot?",
        {
            "metric": "raise_frequency",
            "filters": {"pot_type": "unopened"},
            "group_by": ("position",),
        },
    ),
    ExampleQuestion(
        "Continuation bet frequency by board suit",
        "How often does the preflop raiser bet the flop, split by board suit structure?",
        {
            "metric": "bet_frequency",
            "filters": {"street": "flop", "primary_situation": "cbet"},
            "group_by": ("board_suit",),
        },
    ),
    ExampleQuestion(
        "Made hands when facing a turn bet",
        "What are players holding when they face a bet on the turn?",
        {
            "metric": "opportunities",
            "filters": {"street": "turn", "action_faced": "bets"},
            "group_by": ("made_hand",),
        },
    ),
)


def example_questions() -> tuple[ExampleQuestion, ...]:
    """The questions the first-run screen offers.

    The shipped preset library (#330) is the product answer and takes precedence
    as soon as it is available; this small set is what a build without it can
    still offer, so the first-run screen is never three empty panes.
    """
    try:
        from .research_presets import builtin_presets
    except ImportError:  # pragma: no cover - a build without the shipped library.
        return EXAMPLES
    shipped = builtin_presets()
    if not shipped:
        return EXAMPLES
    return tuple(
        ExampleQuestion(preset.name, preset.description, dict(preset.query))
        for preset in shipped[:6]
    )


def preset_to_query(preset: Mapping[str, Any]) -> Query:
    """A validated preset to the engine's ``Query``."""
    clean = validate_preset(preset)
    return Query(
        metric=clean["metric"],
        filters=clean["filters"],
        numerator=clean["numerator"],
        group_by=clean["group_by"],
    )


class ResearchPresets:
    """Named ``Query`` values, persisted as JSON, validated on every read.

    The format holds *engine vocabulary* -- a metric name, filter names with
    their values, dimension names -- never SQL. A file edited by hand is read
    through the same validation a GUI write went through, so a bad preset is
    refused with its reason at load time instead of blowing up mid-query. The
    default directory is the fpdb config directory; tests pass their own.
    """

    def __init__(self, directory: str | Path | None = None) -> None:
        self.directory = Path(directory) if directory is not None else Path(CONFIG_PATH)
        self.path = self.directory / "research_presets.json"

    @staticmethod
    def _write(path: Path, stored: Mapping[str, Mapping[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"version": PRESET_VERSION, "presets": stored}, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)

    def load(self) -> dict[str, dict[str, Any]]:
        """The stored presets, each validated against the engine vocabulary."""
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{self.path} is not valid JSON: {exc}") from exc
        if not isinstance(raw, dict) or raw.get("version") != PRESET_VERSION:
            raise ValueError(f"{self.path} is not a version-{PRESET_VERSION} presets file")
        stored = raw.get("presets")
        if not isinstance(stored, dict):
            raise ValueError(f"{self.path} has no presets map")
        out: dict[str, dict[str, Any]] = {}
        for name, payload in stored.items():
            try:
                out[str(name)] = validate_preset(payload)
            except ValueError as exc:
                # One bad entry does not sink the file: it is named, logged
                # and skipped, and the user's other presets still load.
                log.warning("Skipping preset %r: %s", name, exc)
        return out

    def save(self, name: str, preset: Mapping[str, Any]) -> None:
        """Validate and store one preset, rewriting the file atomically."""
        clean = validate_preset(preset)
        stored = self.load()
        stored[name] = clean
        self._write(self.path, stored)

    def delete(self, name: str) -> None:
        stored = self.load()
        if name not in stored:
            raise KeyError(name)
        del stored[name]
        self._write(self.path, stored)


# ---------------------------------------------------------------------------
# The result as the browser presents it.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultColumn:
    """One column of the result table, with the semantics the row carries.

    ``source`` is why the issue asks for honesty: ``dimension`` names a group
    key, ``denominator`` the decisions the row was computed over, ``numerator``
    the subset the metric counted, ``value`` the metric itself. The browser
    renders numerator/denominator for every frequency because the data says
    to, not because a column happened to be named that way.
    """

    key: str
    heading: str
    source: str
    unit: str = ""


_VALUE_UNITS: Final = {
    "total_profit": "cents",
    "profit_per_opportunity": "cents",
    "all_in_ev": "cents",
    "ev_per_opportunity": "cents",
    "average_sizing": "bp",
    "average_facing_sizing": "bp",
    "average_spr": "centi",
    "average_pot": "cents",
}


def result_columns(metric: str, group_by: tuple[str, ...]) -> tuple[ResultColumn, ...]:
    """The columns a metric/group-by pair produces, before any row exists.

    Used both to render the table and to build the empty state: a table whose
    shape is known can say "the query matched nothing" over its own headers.
    """
    columns = [ResultColumn(key, key.replace("_", " "), "dimension") for key in group_by]
    columns.append(ResultColumn("opportunities", "decisions", "denominator", "count"))
    columns.append(ResultColumn("actions", "numerator", "numerator", "count"))
    if metric == "frequency" or metric.endswith("_frequency"):
        columns.append(ResultColumn("frequency_bp", "frequency", "value", "bp"))
    elif metric in ("opportunities", "hands", "players", "action_count"):
        columns.append(ResultColumn("value", "count", "value", "count"))
    else:
        columns.append(
            ResultColumn("value", metric.replace("_", " "), "value", _VALUE_UNITS.get(metric, "")),
        )
    return tuple(columns)


@dataclass
class ResearchResult:
    """An executed preset: its rows, columns, sample size and timing.

    ``empty_reason`` is the issue's "empty states must explain" acceptance:
    ``None`` when rows came back, otherwise *why* -- no matching hands, or
    the known-but-not-computable refusal the engine raised, carried as text.
    """

    query: Query
    columns: tuple[ResultColumn, ...]
    rows: list[dict[str, Any]]
    total_opportunities: int
    total_actions: int
    elapsed_ms: float
    empty_reason: str | None = None
    sql_description: str = ""

    @property
    def sample_text(self) -> str:
        """The sample size, stated the way the issue asks: prominently."""
        if self.total_opportunities == 0:
            return "0 decisions"
        if self.total_opportunities == 1:
            return "1 decision"
        return f"{self.total_opportunities} decisions"


def execute_preset(db: Any, preset: Mapping[str, Any], limit: int | None = None) -> ResearchResult:
    """Compile and run a preset on the calling thread, as a result table.

    The GUI calls this from its worker thread, never from the Qt event loop;
    the CLI calls it directly. ``limit`` pages the *rows*, not the population:
    the totals come from the full run, so a browser can show the top rows and
    still state the real sample size.
    """
    query = preset_to_query(preset)
    if limit is not None:
        query = Query(
            metric=query.metric,
            filters=query.filters,
            numerator=query.numerator,
            group_by=query.group_by,
            limit=limit,
        )
    started = time.monotonic()
    try:
        result = run_query(db, query)
        # The engine's LIMIT pages the grouped *rows*, so the totals of a paged
        # run would be the totals of the page. The sample size the browser
        # states is the population's, from a separate ungrouped count.
        totals = result
        if limit is not None and query.group_by:
            totals = run_query(
                db,
                Query(metric=query.metric, filters=query.filters, numerator=query.numerator),
            )
    except ValueError as exc:
        # A known metric that this population cannot support: the refusal is
        # the result, stated where the table would have been.
        return ResearchResult(
            query=query,
            columns=result_columns(query.metric, query.group_by),
            rows=[],
            total_opportunities=0,
            total_actions=0,
            elapsed_ms=(time.monotonic() - started) * 1000.0,
            empty_reason=str(exc),
            sql_description="",
        )
    rows = result.as_dicts()
    # Ungrouped, the engine always returns one row -- even an all-zero one for
    # a population that matched nothing. The browser calls that what it is: an
    # empty state with the reason, not a row of zeros that reads like a result.
    is_empty = not totals.rows or all(
        not row.opportunities and not row.actions and not row.value
        for row in totals.rows
    )
    return ResearchResult(
        query=query,
        columns=result_columns(query.metric, query.group_by),
        rows=rows,
        total_opportunities=totals.total_opportunities,
        total_actions=totals.total_actions,
        elapsed_ms=(time.monotonic() - started) * 1000.0,
        empty_reason="no matching hands" if is_empty else None,
        sql_description=result.compiled.description,
    )


# ---------------------------------------------------------------------------
# Drill-down: the hands behind a result row.
# ---------------------------------------------------------------------------

DRILL_COLUMNS: Final[tuple[ResultColumn, ...]] = (
    ResultColumn("handId", "hand", "id"),
    ResultColumn("startTime", "time", "hand"),
    ResultColumn("siteName", "site", "hand"),
    ResultColumn("category", "game", "hand"),
    ResultColumn("bigBlind", "bb", "hand", "cents"),
    ResultColumn("maxSeats", "seats", "hand"),
    ResultColumn("heroName", "hero", "hand"),
    ResultColumn("heroProfit", "hero profit", "hand", "cents"),
    ResultColumn("heroCards", "hero cards", "hand"),
    ResultColumn("board", "board", "hand"),
    ResultColumn("finalPot", "pot", "hand", "cents"),
)


def drill_query(row_query: Query, group: Mapping[str, Any], numerator_only: bool) -> Query:
    """The population query narrowed to one result row's group key.

    Grouping by ``street`` produces rows keyed by that street; asking for the
    hands behind the ``flop`` row is the population query plus
    ``street='flop'``. That is the whole mapping -- a row *is* a filter, so
    the drill-down cannot select a different population than the result did.
    ``numerator_only`` narrows further to the numerator, for "show me the
    hands where the fold happened".
    """
    return Query(
        metric=row_query.metric,
        filters={**row_query.filters, **dict(group)},
        numerator=row_query.numerator if numerator_only else {},
        group_by=(),
    )


@dataclass
class DrillDown:
    """The hands behind a result row, each with the columns a human scans."""

    hand_ids: list[int]
    rows: list[dict[str, Any]]
    truncated: bool
    limit: int
    total_matches: int


def _hero_join() -> str:
    """The extra join that names the hand's hero.

    The engine's ``HP`` row is scoped to the matching action's player.  The
    drill-down's hero columns must instead follow the hand's recorded hero
    seat, independently of whether the query is hero-filtered.
    """
    return (
        "JOIN HandsPlayers HERO_HP ON HERO_HP.handId = H.id AND HERO_HP.seatNo = H.heroSeat "
        "JOIN Players HERO ON HERO.id = HERO_HP.playerId"
    )


def _cards_text(*cards: Any) -> str:
    """Render every known private card, supporting Hold'em and Omaha alike."""
    return "".join(Card.valueSuitFromCard(int(card)) for card in cards if card)


def _board_text(raw: Mapping[str, Any]) -> str:
    """The board as the short text a list shows, '' when there was none."""
    codes = [raw.get(f"boardcard{i}") for i in range(1, 6)]
    return "".join(Card.valueSuitFromCard(int(code)) for code in codes if code)


#: Filters whose values are a closed domain the database itself holds, and the
#: SELECT that lists them. Shipped with no ``choices``, they rendered as an
#: empty text box in which a user had to guess that the stored token is
#: ``omahahi`` rather than "Omaha" or "PLO" -- a closed domain offered as free
#: text (#355). What a database actually holds is a better list than anything
#: hard-coded here, and it is short.
#: Each one joins through Hands on purpose. Gametypes and Sites are reference
#: tables -- Sites holds every room fpdb can parse, roughly a hundred and thirty
#: of them -- so listing them directly offers a user every room in the world
#: instead of the two they play. A picker is only an improvement on free text
#: when it is shorter than the alphabet.
DATABASE_CHOICES: Final[dict[str, str]] = {
    "game": (
        "SELECT DISTINCT G.category FROM Gametypes G"
        " JOIN Hands H ON H.gametypeId = G.id ORDER BY G.category"
    ),
    "limit": (
        "SELECT DISTINCT G.limitType FROM Gametypes G"
        " JOIN Hands H ON H.gametypeId = G.id ORDER BY G.limitType"
    ),
    "currency": (
        "SELECT DISTINCT G.currency FROM Gametypes G"
        " JOIN Hands H ON H.gametypeId = G.id ORDER BY G.currency"
    ),
    "site": (
        "SELECT DISTINCT S.name FROM Sites S"
        " JOIN Gametypes G ON G.siteId = S.id"
        " JOIN Hands H ON H.gametypeId = G.id ORDER BY S.name"
    ),
}


def database_choices(db: Any, name: str) -> tuple[Choice, ...]:
    """The values this database actually holds for a closed-domain filter.

    Answers ``()`` for anything else, and for any failure: a filter that cannot
    list its values is still usable as free text, and a picker must never cost
    the pane its window.
    """
    query = DATABASE_CHOICES.get(name)
    if query is None or db is None:
        return ()
    try:
        cursor = db.get_cursor()
        # Escaped like every other statement these modules run, although these
        # hold no ``%`` today: the rule is what makes a fourth site impossible
        # to get wrong, and a constant that grows a LIKE later is exactly how
        # the last one happened (#349).
        cursor.execute(escape_literal_percent(query, _placeholder(db)))
        values = [row[0] for row in cursor.fetchall() if row and row[0] not in (None, "")]
    except Exception:  # noqa: BLE001 - an empty picker is a degradation, not a fault
        log.debug("Could not list the values of filter %r", name, exc_info=True)
        return ()
    return tuple(Choice(str(value), value_label(name, str(value))) for value in values)


def spec_for_database(db: Any, name: str) -> FilterSpec:
    """A filter's spec, with the values this database holds when it has them."""
    spec = filter_spec(name)
    if spec.choices:
        return spec
    choices = database_choices(db, name)
    return replace(spec, choices=choices, from_database=True) if choices else spec


@dataclass(frozen=True)
class PopulationScope:
    """What games, limits and rooms one question's population spans (#355).

    A single number over two games is two answers averaged, and nothing on
    screen said so: one database's "fold to a 3-bet = 47.5%" covered Hold'em at
    49.2% over 63 decisions and Omaha at 46.5% over 99, in two different limits.

    Stakes are not here, and deliberately: the engine has no stake dimension to
    group by, so a claim about them would be guesswork. This says what it can
    check.
    """

    games: tuple[str, ...] = ()
    limits: tuple[str, ...] = ()
    sites: tuple[str, ...] = ()
    #: The dimensions the question already splits into rows. A query grouped by
    #: game gives one row per game, so warning that it averages them is simply
    #: wrong: the reader is looking at the split.
    grouped: tuple[str, ...] = ()

    def _mixed(self, name: str, values: tuple[str, ...]) -> bool:
        return len(values) > 1 and name not in self.grouped

    @property
    def is_mixed(self) -> bool:
        return (
            self._mixed("game", self.games)
            or self._mixed("limit", self.limits)
            or self._mixed("site", self.sites)
        )

    def describe(self) -> str:
        """The mixture, named, or ``""`` when there is nothing to warn about."""
        parts = []
        if self._mixed("game", self.games):
            parts.append("games (" + ", ".join(value_label("game", game) for game in self.games) + ")")
        if self._mixed("limit", self.limits):
            parts.append("limits (" + ", ".join(value_label("limit", limit) for limit in self.limits) + ")")
        if self._mixed("site", self.sites):
            parts.append("rooms (" + ", ".join(self.sites) + ")")
        if not parts:
            return ""
        return (
            "This answer averages " + " and ".join(parts)
            + ". Add the matching filter to ask about one of them."
        )


def population_scope(db: Any, query: Query) -> PopulationScope:
    """The games, limits and rooms a query's filters actually select.

    One extra grouped query per run, which is the same shape the 13x13 grid
    already runs to refuse a non-Hold'em population. A failure answers an empty
    scope: a warning that cannot be computed must not cost the answer it was
    going to annotate.
    """
    try:
        result = run_query(
            db,
            Query(metric="opportunities", filters=dict(query.filters), group_by=("game", "limit", "site")),
        )
    except Exception:  # noqa: BLE001 - an annotation is never worth an exception
        log.debug("Could not read the population's scope", exc_info=True)
        # The grouping is a property of the question, not of the population, so
        # it survives a population that could not be read.
        return PopulationScope(grouped=tuple(query.group_by))
    rows = [row for row in result.rows if row.opportunities]
    return PopulationScope(
        games=tuple(sorted({str(row.group["game"]) for row in rows})),
        limits=tuple(sorted({str(row.group["limit"]) for row in rows})),
        sites=tuple(sorted({str(row.group["site"]) for row in rows})),
        grouped=tuple(query.group_by),
    )


@dataclass(frozen=True)
class ComparisonRow:
    """One group, answered twice: by hero and by everyone else."""

    group: dict[str, Any]
    hero_opportunities: int
    hero_actions: int
    field_opportunities: int
    field_actions: int
    hero_value: float | None = None
    field_value: float | None = None
    unit: str = ""
    frequency: bool = False

    @staticmethod
    def _rate(actions: int, opportunities: int) -> float | None:
        return None if not opportunities else actions / opportunities

    @property
    def hero_rate(self) -> float | None:
        return self._rate(self.hero_actions, self.hero_opportunities) if self.frequency else None

    @property
    def field_rate(self) -> float | None:
        return self._rate(self.field_actions, self.field_opportunities) if self.frequency else None

    @property
    def hero_measure(self) -> float | None:
        """The metric value to display for the hero side."""
        return self.hero_rate if self.frequency else self.hero_value

    @property
    def field_measure(self) -> float | None:
        """The metric value to display for the field side."""
        return self.field_rate if self.frequency else self.field_value

    @property
    def gap(self) -> float | None:
        """Hero minus field, or ``None`` when either side has no sample.

        A gap against nothing is not a small gap, it is no reading at all --
        the one thing a comparison must never round to zero.
        """
        hero, field = self.hero_measure, self.field_measure
        return None if hero is None or field is None else hero - field


@dataclass(frozen=True)
class Comparison:
    """A question answered for hero and for the field, side by side (#357).

    The browser could answer either -- ``hero`` says which -- but never both at
    once, so a reader had to run the question twice and hold the first answer in
    their head. A frequency without a baseline is a measurement; beside one it
    is a read, which is what the tool is for.
    """

    rows: tuple[ComparisonRow, ...]
    metric: str
    group_by: tuple[str, ...]
    unit: str = ""
    frequency: bool = False

    @property
    def hero_total(self) -> ComparisonRow:
        return ComparisonRow(
            group={},
            hero_opportunities=sum(row.hero_opportunities for row in self.rows),
            hero_actions=sum(row.hero_actions for row in self.rows),
            field_opportunities=sum(row.field_opportunities for row in self.rows),
            field_actions=sum(row.field_actions for row in self.rows),
            unit=self.unit,
            frequency=self.frequency,
        )


def run_comparison(db: Any, preset: Mapping[str, Any]) -> Comparison:
    """Run one question twice: as hero, and as everyone else.

    The ``hero`` filter is replaced rather than merged, so a preset that already
    picks a side still yields both: a comparison whose two halves are the same
    population would answer itself.
    """
    query = preset_to_query(preset)
    spec, _filters, _numerator = query.resolved()
    frequency = spec.frequency
    sides = {}
    for name, hero in (("hero", True), ("field", False)):
        filters = dict(query.filters)
        filters["hero"] = hero
        sides[name] = run_query(
            db,
            Query(
                metric=query.metric,
                filters=filters,
                numerator=dict(query.numerator),
                group_by=tuple(query.group_by),
            ),
        )

    def _by_group(result: Any) -> dict[tuple, Any]:
        return {tuple(sorted(row.group.items())): row for row in result.rows}

    hero_rows, field_rows = _by_group(sides["hero"]), _by_group(sides["field"])

    def _metric_value(row: Any | None) -> float | None:
        if row is None:
            return None
        if frequency:
            return None if row.frequency_bp is None else row.frequency_bp / 10000
        return row.value

    rows = []
    # Union, not intersection: a spot hero never reached is a fact about hero,
    # and dropping it would quietly flatter the comparison.
    for key in sorted(set(hero_rows) | set(field_rows), key=lambda item: [str(part) for part in item]):
        hero_row, field_row = hero_rows.get(key), field_rows.get(key)
        source = hero_row if hero_row is not None else field_row
        if source is None:  # The union above is non-empty, but keep this total.
            continue
        rows.append(
            ComparisonRow(
                group=dict(source.group),
                hero_opportunities=hero_row.opportunities if hero_row is not None else 0,
                hero_actions=hero_row.actions if hero_row is not None else 0,
                field_opportunities=field_row.opportunities if field_row is not None else 0,
                field_actions=field_row.actions if field_row is not None else 0,
                hero_value=_metric_value(hero_row),
                field_value=_metric_value(field_row),
                unit=spec.unit,
                frequency=frequency,
            ),
        )
    return Comparison(
        rows=tuple(rows),
        metric=query.metric,
        group_by=tuple(query.group_by),
        unit=spec.unit,
        frequency=frequency,
    )


#: The display columns a drill-down page carries, in the order a list shows
#: them. The player columns are named for the *side* rather than for the hero,
#: because a Hero-versus-Field drill shows a different player on each side
#: (#366); ``run_drill_down`` renames them to its own hero columns.
DRILL_ROW_KEYS: Final[tuple[str, ...]] = (
    "handId",
    "startTime",
    "siteName",
    "category",
    "bigBlind",
    "maxSeats",
    "playerName",
    "playerProfit",
    "playerCards",
    "board",
    "finalPot",
)


def drill_display_rows(
    db: Any,
    query: Query,
    page_ids: Sequence[int],
    *,
    actor: bool = False,
    numerator_only: bool = False,
) -> list[dict[str, Any]]:
    """The columns a human scans, for one page of already-selected hand ids.

    The page reuses the engine's compiled ``WHERE`` (the same filters, plus the
    page's ids), so a row, its ids and the answer above it cannot disagree
    about which hands belong to them.

    ``actor`` says whose name, cards and profit the page shows. The default is
    the hand's recorded hero seat, which is what a hero-filtered drill has
    always shown. A Hero-versus-Field drill passes ``True`` to follow the
    player who *made the decision the query counted* instead: on the field side
    the hand's hero is not the player the row is about, and their cards are not
    the ones that row is entitled to show (#366).
    """
    if not page_ids:
        return []
    placeholder = _placeholder(db)
    filters = {**query.filters, "hand_id": list(page_ids)}
    if numerator_only:
        filters.update(query.numerator)
    where, params, aliases = compile_filters(filters, placeholder, _backend_name(db))
    sources = aliases | {"A", "H", "G", "S", "HP"}
    if actor:
        sources.add("P")
    from_clause = _from_clause(_expand_sources(sources))
    player_columns = (
        [
            "  P.name AS playerName,",
            "  HP.totalProfit AS playerProfit,",
            "  HP.card1 AS card1, HP.card2 AS card2, HP.card3 AS card3, HP.card4 AS card4,",
        ]
        if actor
        else [
            "  HERO.name AS playerName,",
            "  HERO_HP.totalProfit AS playerProfit,",
            "  HERO_HP.card1 AS card1, HERO_HP.card2 AS card2, "
            "HERO_HP.card3 AS card3, HERO_HP.card4 AS card4,",
        ]
    )
    sql = "\n".join(
        [
            "SELECT DISTINCT A.handId AS handId,",
            "  H.startTime AS startTime,",
            "  S.name AS siteName,",
            "  G.category AS category,",
            "  G.bigBlind AS bigBlind,",
            "  H.seats AS maxSeats,",
            *player_columns,
            "  H.boardcard1 AS boardcard1, H.boardcard2 AS boardcard2,",
            "  H.boardcard3 AS boardcard3, H.boardcard4 AS boardcard4,",
            "  H.boardcard5 AS boardcard5,",
            "  H.finalPot AS finalPot",
            from_clause,
            *([] if actor else [_hero_join()]),
            "WHERE " + " AND ".join(f"({condition})" for condition in where),
            "ORDER BY A.handId",
        ],
    )
    cursor = db.get_cursor()
    # Assembled here rather than by compile_query, so it needs the escaping
    # the compilers do: a drill-down filtered by starting hand -- which is
    # every range-grid cell -- carries the class expression's modulo
    # operators in its WHERE (#349).
    cursor.execute(escape_literal_percent(sql, placeholder), tuple(params))
    return [
        {
            "handId": int(row["handId"]),
            "startTime": row["startTime"],
            "siteName": row["siteName"],
            "category": row["category"],
            "bigBlind": row["bigBlind"],
            "maxSeats": row["maxSeats"],
            "playerName": row["playerName"],
            "playerProfit": row["playerProfit"],
            "playerCards": _cards_text(*(row.get(f"card{i}") for i in range(1, 5))),
            "board": _board_text(row),
            "finalPot": row["finalPot"],
        }
        for row in rows_by_alias(cursor)
    ]


def run_drill_down(
    db: Any,
    row_query: Query,
    group: Mapping[str, Any] | None = None,
    numerator_only: bool = False,
    limit: int = 200,
) -> DrillDown:
    """The hands behind a result row: ids, a page of display rows, a count.

    The ids come from the engine's own ``run_hand_ids`` -- the *population*
    by default, the numerator's hands with ``numerator_only``. The page's
    display columns reuse the engine's compiled ``WHERE`` (same filters, plus
    the page's ids), so a row, its ids and its rows cannot disagree about
    which hands belong to it. The count is over the whole population, so
    ``truncated`` is a fact, not a guess.
    """
    query = drill_query(row_query, group or {}, numerator_only)
    hand_ids = run_hand_ids(db, query, include_numerator=numerator_only)
    total_matches = len(hand_ids)
    page_ids = hand_ids[-limit:] if limit and len(hand_ids) > limit else hand_ids
    truncated = total_matches > len(page_ids)
    # This drill names the hand's hero, so its columns keep their hero names;
    # the shared page speaks of "the player" because the field side has one.
    rows = [
        {
            "handId": row["handId"],
            "startTime": row["startTime"],
            "siteName": row["siteName"],
            "category": row["category"],
            "bigBlind": row["bigBlind"],
            "maxSeats": row["maxSeats"],
            "heroName": row["playerName"],
            "heroProfit": row["playerProfit"],
            "heroCards": row["playerCards"],
            "board": row["board"],
            "finalPot": row["finalPot"],
        }
        for row in drill_display_rows(db, query, page_ids, numerator_only=numerator_only)
    ]
    return DrillDown(
        hand_ids=hand_ids,
        rows=rows,
        truncated=truncated,
        limit=limit,
        total_matches=total_matches,
    )


__all__ = [
    "DIMENSION_SPECS",
    "DRILL_COLUMNS",
    "DRILL_ROW_KEYS",
    "EXAMPLES",
    "FILTER_GROUPS",
    "FILTER_SPECS",
    "PRESET_VERSION",
    "DimensionSpec",
    "DrillDown",
    "ExampleQuestion",
    "FilterSpec",
    "ResearchPresets",
    "ResearchResult",
    "ResultColumn",
    "describe_preset",
    "dimension_spec",
    "drill_display_rows",
    "drill_query",
    "example_questions",
    "execute_preset",
    "filter_spec",
    "preset_to_query",
    "result_columns",
    "run_drill_down",
    "validate_preset",
]
