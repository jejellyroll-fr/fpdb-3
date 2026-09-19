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
from collections.abc import Mapping
from dataclasses import dataclass
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
    run_hand_ids,
    run_query,
)
from .Configuration import CONFIG_PATH
from .loggingFpdb import get_logger

log = get_logger("research_browser")


# ---------------------------------------------------------------------------
# The filter vocabulary, grouped for a browser's picker.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FilterSpec:
    """One filter as a browser may offer it: its name, group and value shape.

    ``value_kind`` is what a GUI builds an input for -- ``bool`` a checkbox,
    ``set`` a list, ``range`` two number fields -- and it comes from the
    engine's own ``kind`` rather than a second table: the browser shapes the
    input, the engine still validates the value.
    """

    name: str
    group: str
    value_kind: str
    description: str


_GROUP_OF: Final = {
    "site": "game", "game": "game", "limit": "game", "currency": "game",
    "tournament": "game", "big_blind": "game", "stake_bb": "game",
    "seats": "game", "max_seats": "game", "session": "game",
    "hand_id": "game", "hand_id_from": "game", "hand_id_to": "game", "tournament_id": "game",
    "date_from": "game", "date_to": "game",
    "player": "who", "players": "who", "identity": "who", "hero": "who",
    "position": "seat", "opponent_position": "seat", "relative_position": "seat",
    "in_position": "seat", "effective_stack_bb": "seat", "effective_stack": "seat",
    "stack_bucket": "seat", "spr": "seat", "players_in_hand": "seat",
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


FILTER_SPECS: Final[tuple[FilterSpec, ...]] = tuple(
    sorted(
        (
            FilterSpec(
                name=name,
                group=_GROUP_OF.get(name, "other"),
                value_kind=_value_kind(spec),
                description=spec.column,
            )
            for name, spec in FILTERS.items()
        ),
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


def _cards_text(card1: Any, card2: Any) -> str:
    """The hero's two cards as the short text a list shows, '' when unknown."""
    if not card1 or not card2:
        return ""
    return Card.valueSuitFromCard(int(card1)) + Card.valueSuitFromCard(int(card2))


def _board_text(raw: Mapping[str, Any]) -> str:
    """The board as the short text a list shows, '' when there was none."""
    codes = [raw.get(f"boardcard{i}") for i in range(1, 6)]
    return "".join(Card.valueSuitFromCard(int(code)) for code in codes if code)


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

    rows: list[dict[str, Any]] = []
    if page_ids:
        placeholder = _placeholder(db)
        where, params, aliases = compile_filters(
            {**query.filters, "hand_id": page_ids}, placeholder, _backend_name(db),
        )
        from_clause = _from_clause(_expand_sources(aliases | {"A", "H", "G", "S", "HP"}))
        sql = "\n".join(
            [
                "SELECT DISTINCT A.handId AS handId,",
                "  H.startTime AS startTime,",
                "  S.name AS siteName,",
                "  G.category AS category,",
                "  G.bigBlind AS bigBlind,",
                "  H.seats AS maxSeats,",
                "  HERO.name AS playerName,",
                "  HERO_HP.totalProfit AS playerProfit,",
                "  HERO_HP.card1 AS card1, HERO_HP.card2 AS card2,",
                "  H.boardcard1 AS boardcard1, H.boardcard2 AS boardcard2,",
                "  H.boardcard3 AS boardcard3, H.boardcard4 AS boardcard4,",
                "  H.boardcard5 AS boardcard5,",
                "  H.finalPot AS finalPot",
                from_clause,
                _hero_join(),
                "WHERE " + " AND ".join(f"({condition})" for condition in where),
                "ORDER BY A.handId",
            ],
        )
        cursor = db.get_cursor()
        cursor.execute(sql, tuple(params))
        columns = [description[0] for description in cursor.description]
        for raw in cursor.fetchall():
            row = dict(zip(columns, raw))
            rows.append(
                {
                    "handId": int(row["handId"]),
                    "startTime": row["startTime"],
                    "siteName": row["siteName"],
                    "category": row["category"],
                    "bigBlind": row["bigBlind"],
                    "maxSeats": row["maxSeats"],
                    "heroName": row["playerName"],
                    "heroProfit": row["playerProfit"],
                    "heroCards": _cards_text(row["card1"], row["card2"]),
                    "board": _board_text(row),
                    "finalPot": row["finalPot"],
                },
            )
    return DrillDown(
        hand_ids=hand_ids,
        rows=rows,
        truncated=truncated,
        limit=limit,
        total_matches=total_matches,
    )


__all__ = [
    "DRILL_COLUMNS",
    "FILTER_GROUPS",
    "FILTER_SPECS",
    "PRESET_VERSION",
    "DrillDown",
    "FilterSpec",
    "ResearchPresets",
    "ResearchResult",
    "ResultColumn",
    "drill_query",
    "execute_preset",
    "filter_spec",
    "preset_to_query",
    "result_columns",
    "run_drill_down",
    "validate_preset",
]
