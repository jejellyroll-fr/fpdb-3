"""Surface adapters that compile :class:`StatDescriptor` objects to native shapes.

A descriptor is surface-agnostic. Each adapter here turns it into what a
specific FPDB view needs:

* :class:`GridAdapter` -> SQL aggregate fragments + report-column metadata for
  the tournament/ring player-stats grids.
* :class:`GraphAdapter` -> per-event series fragments for the graph viewers
  (see :mod:`fpdb_3_legacy` graph wiring).

Both query ``HandsPlayers`` (raw per-hand rows) joined to ``Hands``. In the real
schema ``position`` lives on ``HandsPlayers`` (button ``'0'``, small blind
``'S'``, big blind ``'B'``) while the table-size count lives on ``Hands.seats``
— so the dimension predicate uses a *per-column* alias map (default
``{"seats": "h", "position": "hp"}``). This differs again from ``HudCache``,
which stores position as a letter bucket (button ``'D'``); the HUD adapter
(added later) owns that translation. Centralising the encoding here is what lets
one descriptor feed every surface.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.stat_registry import StatDescriptor

log = get_logger("stat_adapters")

# Default table alias for each dimension column. ``seats`` is on Hands (alias
# ``h``); ``position`` is on HandsPlayers (alias ``hp``).
DEFAULT_DIM_ALIASES: dict[str, str] = {"seats": "h", "position": "hp"}


def _sql_str_literal(value: Any) -> str:
    """Quote ``value`` as a SQL string literal (HandsPlayers.position is CHAR)."""
    return "'" + str(value).replace("'", "''") + "'"


def dimension_predicate(descriptor: StatDescriptor, dim_aliases: Mapping[str, str] | None = None) -> str:
    """Build a SQL boolean predicate for a descriptor's ``dimension`` filter.

    ``dim_aliases`` maps each dimension column to its table alias (defaults to
    :data:`DEFAULT_DIM_ALIASES`). ``position`` is always rendered as a quoted
    character because the column is ``CHAR(1)`` — so the logical button value
    ``0`` becomes ``position = '0'``. Returns ``""`` when there is no dimension.
    """
    dim = descriptor.dimension
    if not dim:
        return ""
    aliases = dict(DEFAULT_DIM_ALIASES)
    if dim_aliases:
        aliases.update(dim_aliases)
    parts: list[str] = []
    if "seats" in dim:
        parts.append(f"{aliases['seats']}.seats = {int(dim['seats'])}")
    if "position" in dim:
        parts.append(f"{aliases['position']}.position = {_sql_str_literal(dim['position'])}")
    return " AND ".join(parts)


def _column_alias(descriptor: StatDescriptor, input_name: str) -> str:
    """Unique result-set alias for one aggregated input of a descriptor."""
    return f"{descriptor.name}__{input_name}"


class GridAdapter:
    """Compiles descriptors into report-grid SQL fragments and column specs.

    Wiring into a grid is two steps:

    1. Add :meth:`select_fragments` to the detailed-stats query's SELECT list
       (these aggregate each fact input, dimension-filtered, per result group).
    2. After fetching each row, call :meth:`augment_row` to compute the derived,
       formatted value, and use :meth:`column_specs` for the column metadata so
       the grid renders it like any native column.

    Context inputs (e.g. ``cnt_tourneys``) are read from the row by their own
    name and must already be selected by the surrounding query.
    """

    def __init__(self, alias: str = "hp", dim_aliases: Mapping[str, str] | None = None) -> None:
        self.alias = alias
        self.dim_aliases = dim_aliases

    def select_fragments(self, descriptor: StatDescriptor) -> list[str]:
        """``SUM(CASE WHEN <dim> THEN hp.<input> ELSE 0 END) AS "name__input"``.

        One fragment per *fact* input. With no dimension it degrades to a plain
        ``SUM(hp.<input>)``. Boolean inputs use ``SUM(CASE WHEN <input> THEN 1
        ELSE 0 END)`` because PostgreSQL has no ``SUM(boolean)`` overload.
        """
        predicate = dimension_predicate(descriptor, self.dim_aliases)
        fragments: list[str] = []
        for input_name in descriptor.fact_inputs():
            col = f"{self.alias}.{input_name}"
            if input_name in descriptor.boolean_inputs:
                condition = f"{predicate} AND {col}" if predicate else col
                expr = f"SUM(CASE WHEN {condition} THEN 1 ELSE 0 END)"
            elif predicate:
                expr = f"SUM(CASE WHEN {predicate} THEN {col} ELSE 0 END)"
            else:
                expr = f"SUM({col})"
            fragments.append(f'{expr} AS "{_column_alias(descriptor, input_name)}"')
        return fragments

    def select_clause(self, descriptors: Sequence[StatDescriptor]) -> str:
        """Comma-joined SELECT additions for several descriptors (leading comma)."""
        frags: list[str] = []
        for descriptor in descriptors:
            frags.extend(self.select_fragments(descriptor))
        return (", " + ", ".join(frags)) if frags else ""

    def column_spec(self, descriptor: StatDescriptor) -> list[Any]:
        """A column-definition row matching ``GuiTourneyPlayerStats.columns``.

        Shape: ``[alias, visible, title, xalignment, format, type]``. The value
        is pre-formatted by :meth:`augment_row`, so ``format`` is ``"%s"`` and
        ``type`` is ``"str"`` here.
        """
        return [descriptor.name, True, descriptor.label, 1.0, "%s", "str"]

    def column_specs(self, descriptors: Sequence[StatDescriptor]) -> list[list[Any]]:
        return [self.column_spec(d) for d in descriptors]

    def compute(self, descriptor: StatDescriptor, row: Mapping[str, Any]) -> float | None:
        """Evaluate the descriptor's raw value from a fetched result ``row``.

        ``row`` is a mapping of column alias -> value. Lookups are
        case-insensitive because database drivers may fold unquoted result
        aliases. Fact inputs are read from their ``name__input`` aggregate
        alias; context inputs from their own name.
        """
        lowered = {str(key).casefold(): value for key, value in row.items()}
        variables: dict[str, Any] = {}
        for input_name in descriptor.inputs:
            if input_name in descriptor.context:
                variables[input_name] = lowered.get(input_name.casefold(), 0)
            else:
                variables[input_name] = lowered.get(_column_alias(descriptor, input_name).casefold(), 0)
        return descriptor.compute(variables)

    def augment_row(
        self,
        descriptors: Sequence[StatDescriptor],
        row: Mapping[str, Any],
    ) -> dict[str, str]:
        """Return ``{descriptor.name: formatted_value}`` for each descriptor."""
        out: dict[str, str] = {}
        for descriptor in descriptors:
            out[descriptor.name] = descriptor.format(self.compute(descriptor, row))
        return out


class GraphAdapter:
    """Compiles ``series == "cumulative"`` descriptors into graph curves.

    Wiring into a graph viewer is three steps:

    1. Add :meth:`select_fragments` to the per-event (time-ordered, NOT grouped)
       query so each matching hand exposes its dimension-gated fact value.
    2. Fetch rows ordered by time.
    3. For each descriptor, call :meth:`series_values` to get the cumulative
       curve, then plot it with :attr:`StatDescriptor.label` as the legend.

    Unlike the grid, fragments here are *per-event* (no ``SUM``); a hand that
    does not match the dimension contributes ``0`` to that curve's increment.
    """

    def __init__(self, alias: str = "hp", dim_aliases: Mapping[str, str] | None = None) -> None:
        self.alias = alias
        self.dim_aliases = dim_aliases

    def select_fragments(self, descriptor: StatDescriptor) -> list[str]:
        """``CASE WHEN <dim> THEN hp.<input> ELSE 0 END AS "name__input"`` per input."""
        predicate = dimension_predicate(descriptor, self.dim_aliases)
        fragments: list[str] = []
        for input_name in descriptor.fact_inputs():
            col = f"{self.alias}.{input_name}"
            expr = f"CASE WHEN {predicate} THEN {col} ELSE 0 END" if predicate else col
            fragments.append(f'{expr} AS "{_column_alias(descriptor, input_name)}"')
        return fragments

    def select_clause(self, descriptors: Sequence[StatDescriptor]) -> str:
        """Comma-joined SELECT additions for several descriptors (leading comma)."""
        frags: list[str] = []
        for descriptor in descriptors:
            frags.extend(self.select_fragments(descriptor))
        return (", " + ", ".join(frags)) if frags else ""

    def event_value(self, descriptor: StatDescriptor, row: Mapping[str, Any]) -> float:
        """Per-event contribution of one row to the descriptor's curve."""
        variables = {name: row.get(_column_alias(descriptor, name), 0) for name in descriptor.fact_inputs()}
        raw = descriptor.compute(variables)
        return 0.0 if raw is None else float(raw)

    def series_values(
        self,
        descriptor: StatDescriptor,
        rows: Sequence[Mapping[str, Any]],
    ) -> list[float]:
        """Cumulative curve: running sum of :meth:`event_value` over ``rows``."""
        total = 0.0
        out: list[float] = []
        for row in rows:
            total += self.event_value(descriptor, row)
            out.append(total)
        return out


# HudCache stores position as a letter bucket (see SQL.py storeHudCache):
# D=button, C=cutoff, M=middle, E=early, B/S=blinds. Logical descriptor
# positions map onto those buckets here.
HUDCACHE_POSITION_BUCKET: dict[Any, str] = {
    0: "D",  # Button
    "S": "S",  # Small blind
    "B": "B",  # Big blind
    1: "C",  # Cutoff
    2: "M",  # Middle
    3: "M",
}


class HudAdapter:
    """Renders descriptor stats in the live HUD.

    The HUD reads pre-aggregated ``HudCache`` columns: ``do_stat`` receives a
    ``stat_dict[player]`` whose keys are the (lower-cased) column names summed by
    the HUD query. Two cases:

    * **Ratio/sum stats over existing HudCache columns** (e.g. a custom VPIP):
      every input is already a key in ``stat_dict[player]`` -> :meth:`compute`
      works immediately, no query change. This is the real plug-and-play HUD win.
    * **Dimensioned stats** (ChipEV-by-position): the per-position value is not a
      raw column. :meth:`select_fragments` emits the bucket-encoded
      ``SUM(CASE WHEN hc.seats=.. AND hc.position='D' ...)`` columns that must be
      added to the HUD aggregation query for these to appear live; once injected
      under their ``name__input`` alias they compute like the others.
    """

    def __init__(self, alias: str = "hc") -> None:
        self.alias = alias

    def dimension_predicate(self, descriptor: StatDescriptor) -> str:
        """HudCache predicate using the position *bucket* encoding (button='D')."""
        dim = descriptor.dimension
        if not dim:
            return ""
        parts: list[str] = []
        if "seats" in dim:
            parts.append(f"{self.alias}.seats = {int(dim['seats'])}")
        if "position" in dim:
            bucket = HUDCACHE_POSITION_BUCKET.get(dim["position"])
            if bucket is None:
                raise ValueError(f"no HudCache bucket for position {dim['position']!r}")
            parts.append(f"{self.alias}.position = {_sql_str_literal(bucket)}")
        return " AND ".join(parts)

    def select_fragments(self, descriptor: StatDescriptor) -> list[str]:
        """Bucket-encoded ``SUM(CASE WHEN <dim> THEN hc.<input> ELSE 0 END)`` columns.

        Aliases are emitted *unquoted* (the alias is a plain identifier) because
        the HUD aggregation query is shared across SQLite/MySQL/PostgreSQL and
        double-quoting is not portable. Identifiers are case-insensitive, and
        :meth:`compute` looks them up case-insensitively, so this is safe.
        """
        predicate = self.dimension_predicate(descriptor)
        fragments: list[str] = []
        for input_name in descriptor.fact_inputs():
            col = f"{self.alias}.{input_name}"
            expr = f"SUM(CASE WHEN {predicate} THEN {col} ELSE 0 END)" if predicate else f"SUM({col})"
            fragments.append(f"{expr} AS {_column_alias(descriptor, input_name)}")
        return fragments

    def select_clause(self, descriptors: Sequence[StatDescriptor]) -> str:
        """Comma-joined SELECT additions for several descriptors (leading comma)."""
        frags: list[str] = []
        for descriptor in descriptors:
            frags.extend(self.select_fragments(descriptor))
        return (", " + ", ".join(frags)) if frags else ""

    def compute(self, descriptor: StatDescriptor, player_stats: Mapping[str, Any]) -> float | None:
        """Evaluate the descriptor from a ``stat_dict[player]`` mapping.

        Inputs are read case-insensitively. A dimensioned input is read from its
        injected ``name__input`` alias if present, else from its own column name
        (so ratio stats over existing HudCache columns work without any change).
        """
        lowered = {str(k).lower(): v for k, v in player_stats.items()}
        variables: dict[str, Any] = {}
        for input_name in descriptor.inputs:
            alias_key = _column_alias(descriptor, input_name).lower()
            if alias_key in lowered:
                variables[input_name] = lowered[alias_key]
            else:
                variables[input_name] = lowered.get(input_name.lower(), 0)
        return descriptor.compute(variables)

    def stat_tuple(self, descriptor: StatDescriptor, player_stats: Mapping[str, Any]) -> tuple:
        """Build the 6-element tuple ``do_stat`` returns for HUD rendering."""
        raw = self.compute(descriptor, player_stats)
        formatted = descriptor.format(raw)
        numeric = raw if raw is not None else 0
        return (
            numeric,
            formatted,
            f"{descriptor.name}={formatted}",
            f"{descriptor.name}={formatted}",
            descriptor.value,
            descriptor.label,
        )
