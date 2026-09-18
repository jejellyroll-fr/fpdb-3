"""Filtered 13x13 Hold'em range exploration (#301).

The grid answers one question in 169 cells: *with which hands did this
population do this?* Every cell is a starting-hand class from
:mod:`fpdb_3_legacy.holdem_classes`, and the numbers in it come from the query
engine (#297) grouped by ``starting_hand_id`` -- so a cell and a hand list are
the same population by construction, and the whole grid adds up to the query it
was built from.

One cell is not like the others, and it is the reason this module exists rather
than a one-liner over the grid: **``xx``, the hands whose cards were never
shown.** A hand history knows the hero's cards and the cards of whoever reached
a showdown; for everyone else the hole cards are simply not in the database.
Those decisions are counted, in their own cell, and are never distributed across
the other 169: a range that borrows from hands nobody saw is a made-up range,
and it would make every other cell quietly wrong.

Money follows #300's rule, because it is #300's report underneath: the result of
a hand belongs to the hand, not to each of its decisions, so a cell's profit is
the money of the hand-players whose filtered decisions fall in that class.
Grouping by a class is a *decision* split, so the cells overlap exactly as a
sizing split does -- the matrix says so, and the total comes from the ungrouped
report.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Final

from . import analytics_profit as profit
from .analytics_query import DIMENSIONS, Query, QueryResult, QueryRow, run_query
from .holdem_classes import (
    DEALT_COMBOS,
    RANKS,
    UNKNOWN_ID,
    UNKNOWN_LABEL,
    UnknownClass,
    class_id_of_label,
    combos,
    grid_ids,
    grid_labels,
    is_unknown,
    kind,
    label,
    share_of_dealt,
)

# The dimension the grid groups by. Named here once, so the engine, the widget,
# the CLI and the drill-down cannot drift apart.
CLASS_DIMENSION: Final = "starting_hand_id"

# What a range question has a name for. Hold'em only: an Omaha hand's first two
# cards are not a Hold'em starting hand.
HOLDEM_MARKER: Final = "holdem"


class NotHoldem(ValueError):
    """A population that contains a game whose two cards are not a Hold'em hand."""


class UnknownView(KeyError):
    """A grid view that does not exist."""


@dataclass(frozen=True)
class RangeMetric:
    """One way of reading the grid, with the unit it is read in."""

    name: str
    label: str
    unit: str
    definition: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "label": self.label, "unit": self.unit, "definition": self.definition}


METRICS: Final[dict[str, RangeMetric]] = {
    "frequency": RangeMetric(
        "frequency",
        "Action frequency",
        "bp",
        "How often the query's numerator fired in this class, in basis points of its decisions.",
    ),
    "sample": RangeMetric(
        "sample",
        "Occurrences",
        "count",
        "How many decisions the population holds in this class: the cell's sample, not its strength.",
    ),
    "profit": RangeMetric(
        "profit",
        "Realized profit",
        "cents",
        "The hand result of the hand-players whose decisions fall in this class (#300).",
    ),
    "ev_adjusted": RangeMetric(
        "ev_adjusted",
        "EV-adjusted profit",
        "cents",
        "The same money with the priced all-in pots marked to equity; non-all-in hands unchanged.",
    ),
}
DEFAULT_VIEW: Final = "sample"


def metric(name: str) -> RangeMetric:
    """One grid view, refusing an unknown name with the known ones."""
    try:
        return METRICS[name]
    except KeyError:
        raise UnknownView(f"Unknown grid view {name!r}; known: {sorted(METRICS)}") from None


def _number(value: Any, default: int = 0) -> int:
    return int(round(float(value))) if value is not None else default


@dataclass(frozen=True)
class RangeCell:
    """One class of the grid: its sample, its money and the query's own metric."""

    class_id: int
    opportunities: int
    actions: int
    hands: int
    players: int
    hand_players: int
    frequency_bp: int | None
    value: float | None
    unit: str
    realized_cents: int
    ev_adjusted_cents: int
    all_in_luck_cents: int
    ev_adjusted_pairs: int
    sample_sufficient: bool

    @property
    def label(self) -> str:
        return label(self.class_id)

    @property
    def kind(self) -> str:
        return kind(self.class_id)

    @property
    def combos(self) -> int:
        return combos(self.class_id)

    @property
    def is_unknown(self) -> bool:
        return is_unknown(self.class_id)

    @property
    def combos_share(self) -> float:
        """The share of all 1326 dealt combinations this one class covers."""
        return self.combos / DEALT_COMBOS

    def share_bp(self, total_opportunities: int) -> int | None:
        """This cell's share of the selected population, in basis points."""
        if not total_opportunities:
            return None
        return self.opportunities * 10000 // total_opportunities

    def metric_value(self, view: str) -> float | None:
        """The cell's number in one view of the grid."""
        if view == "frequency":
            return float(self.frequency_bp) if self.frequency_bp is not None else None
        if view == "sample":
            return float(self.opportunities)
        if view == "profit":
            return float(self.realized_cents)
        if view == "ev_adjusted":
            return float(self.ev_adjusted_cents)
        raise UnknownView(f"Unknown grid view {view!r}; known: {sorted(METRICS)}")

    def tooltip(self, view: str = DEFAULT_VIEW, total_opportunities: int = 0) -> str:
        """The raw counts behind the cell, for the widget's hover text.

        A colour is a summary; this is the evidence. The sample and the money
        are shown whether or not they are what the cell is coloured by, and an
        unknown cell says so in words instead of showing a class.
        """
        spec = metric(view)
        lines = [f"<b>{self.label}</b>" if not self.is_unknown else f"<b>{UNKNOWN_LABEL}</b> (cards not known)"]
        if not self.is_unknown:
            lines.append(f"{self.kind}, {self.combos} combinations")
        shown = self.metric_value(view)
        if shown is not None:
            lines.append(f"{spec.label}: {_format_value(shown, spec.unit)}")
        lines.append(f"Decisions: {self.opportunities}")
        if self.opportunities:
            share = self.share_bp(total_opportunities)
            if share is not None:
                lines.append(f"Share of the selection: {share / 100:.2f}%")
        lines.append(f"Hands: {self.hands} &middot; players: {self.players} &middot; hand-players: {self.hand_players}")
        if self.realized_cents or self.ev_adjusted_cents:
            lines.append(f"Realized profit: {self.realized_cents} cents")
            lines.append(f"EV-adjusted: {self.ev_adjusted_cents} cents")
        if not self.sample_sufficient:
            lines.append("<i>Below the sample threshold</i>")
        return "<br/>".join(lines)

    def as_dict(self, view: str = DEFAULT_VIEW, total_opportunities: int = 0) -> dict[str, Any]:
        return {
            "class_id": self.class_id,
            "label": self.label,
            "kind": self.kind,
            "combos": self.combos,
            "is_unknown": self.is_unknown,
            "opportunities": self.opportunities,
            "actions": self.actions,
            "hands": self.hands,
            "players": self.players,
            "hand_players": self.hand_players,
            "frequency_bp": self.frequency_bp,
            "value": self.value,
            "unit": self.unit,
            "realized_cents": self.realized_cents,
            "ev_adjusted_cents": self.ev_adjusted_cents,
            "all_in_luck_cents": self.all_in_luck_cents,
            "share_bp": self.share_bp(total_opportunities),
            "sample_sufficient": self.sample_sufficient,
            "shown": self.metric_value(view),
        }


def _format_value(value: float, unit: str) -> str:
    """A grid number in its unit, as the legend and the CLI print it."""
    if unit == "bp":
        return f"{value / 100:.1f}%"
    if unit == "cents":
        return f"{value:+.0f}c" if value else "0c"
    return f"{value:.0f}"


@dataclass(frozen=True)
class RangeMatrix:
    """The 13x13 grid of a filtered population, plus the hands it could not see."""

    query: Query
    engine_metric: str
    unit: str
    min_sample: int
    cells: tuple[RangeCell, ...]
    unknown_cells: Mapping[int, RangeCell]
    total_opportunities: int
    total_hands: int
    total_hand_players: int
    total_realized_cents: int
    total_ev_adjusted_cents: int
    notes: tuple[str, ...] = ()
    _by_id: dict[int, RangeCell] = field(default_factory=dict, repr=False)

    def cell(self, value: str | int) -> RangeCell:
        """One cell by label (``AKs``, ``xx``) or class id."""
        class_id = value if isinstance(value, int) else _id_of_label(str(value))
        try:
            return self._by_id[class_id]
        except KeyError:
            raise UnknownClass(f"No cell for {value!r} in this matrix") from None

    def grid(self) -> tuple[tuple[RangeCell, ...], ...]:
        """The 169 cells in the 13x13 layout, ranks descending."""
        return tuple(tuple(self._by_id[class_id] for class_id in row) for row in grid_ids())

    def labels(self) -> tuple[tuple[str, ...], ...]:
        """The grid's labels, from the one definition of the 169 classes."""
        return grid_labels()

    def values(self, view: str = DEFAULT_VIEW) -> tuple[tuple[float | None, ...], ...]:
        """The grid's numbers in one view, ``None`` where a class has no data."""
        metric(view)
        return tuple(tuple(cell.metric_value(view) for cell in row) for row in self.grid())

    def remarked(self, min_sample: int) -> RangeMatrix:
        """The same grid with the sample threshold re-applied.

        Whether a cell is *flagged* is a display decision, and a widget that
        lets a reader move the threshold must not need the database again to
        answer it. Only the flag changes: every count and every cent is the
        population's, unchanged.
        """

        def flag(cell: RangeCell) -> RangeCell:
            return replace(cell, sample_sufficient=cell.opportunities >= min_sample and cell.opportunities > 0)

        cells = tuple(flag(cell) for cell in self.cells)
        unknown = {class_id: flag(cell) for class_id, cell in self.unknown_cells.items()}
        return RangeMatrix(
            query=self.query,
            engine_metric=self.engine_metric,
            unit=self.unit,
            min_sample=min_sample,
            cells=cells,
            unknown_cells=unknown,
            total_opportunities=self.total_opportunities,
            total_hands=self.total_hands,
            total_hand_players=self.total_hand_players,
            total_realized_cents=self.total_realized_cents,
            total_ev_adjusted_cents=self.total_ev_adjusted_cents,
            notes=self.notes,
            # The re-marked cells, not the ones this matrix was built from:
            # pointing the lookup at the originals would show the old flags.
            _by_id={cell.class_id: cell for cell in (*cells, *unknown.values())},
        )

    def known_cells(self) -> tuple[RangeCell, ...]:
        """The 169 real classes, in grid order."""
        return tuple(cell for row in self.grid() for cell in row)

    def every_cell(self) -> tuple[RangeCell, ...]:
        """Every cell of the population: the 169 classes and the unknown one."""
        return (*self.known_cells(), *self.unknown_cells.values())

    def unknown_opportunities(self) -> int:
        """Decisions whose cards were never seen -- reported, never distributed."""
        return sum(cell.opportunities for cell in self.unknown_cells.values())

    def unknown_hands(self) -> int:
        return sum(cell.hands for cell in self.unknown_cells.values())

    def sample_below_threshold(self) -> int:
        """How many classes hold data but less of it than the threshold asks."""
        return sum(
            1
            for cell in self.known_cells()
            if cell.opportunities and not cell.sample_sufficient
        )

    def reconcile(self) -> tuple[str, ...]:
        """What disagrees with the query the matrix was built from, if anything.

        Two things are exact and are checked as such: **decisions** partition the
        population (a decision has one class, and the cards nobody saw have their
        own place), and the grid covers precisely the 169 classes once each.

        The **money** is deliberately not required to add up. A hand-player is
        counted in every class their decisions reach, so a hand that opened with
        ``AKs`` and barrelled a turn with a class of its own is in two cells --
        the same overlap #300 reports, one level up. What must hold is the weaker
        fact that every pair behind the grid is a pair of the population, which
        is why the sums are compared as a floor, and exactly once the cells stop
        sharing pairs.
        """
        problems: list[str] = []
        known = sum(cell.opportunities for cell in self.known_cells())
        unknown = self.unknown_opportunities()
        if known + unknown != self.total_opportunities:
            problems.append(f"cells hold {known + unknown} decisions, the query returned {self.total_opportunities}")
        seen = {cell.class_id for cell in self.cells}
        if len(seen) != len(self.cells):
            problems.append("a class appears in more than one cell")
        if seen != set(range(1, UNKNOWN_ID)):
            problems.append("the grid does not cover exactly the 169 classes")
        pairs = sum(cell.hand_players for cell in self.every_cell())
        if pairs < self.total_hand_players:
            problems.append(
                f"the cells hold {pairs} hand-players, fewer than the population's {self.total_hand_players}",
            )
        money = sum(cell.realized_cents for cell in self.every_cell())
        if pairs == self.total_hand_players and money != self.total_realized_cents:
            problems.append(
                f"no cell shares a pair, yet the cells sum to {money} cents where the report says "
                f"{self.total_realized_cents}",
            )
        return tuple(problems)

    def render(self, view: str = DEFAULT_VIEW, *, hide_small: bool = False) -> str:
        """The grid as text: 13 rows of 13 cells, then its legend and its caveats."""
        spec = metric(view)
        width = 6
        lines = [f"{spec.label} per starting hand ({spec.unit}) -- {spec.definition}"]
        header = "      " + " ".join(f"{rank:>{width}}" for rank in RANKS)
        lines.append(header)
        for row_rank, row in zip(RANKS, self.grid()):
            cells: list[str] = []
            for cell in row:
                # No decision in a class is not a zero: it is the absence of an
                # observation, and a grid that prints 0 there invites reading a
                # missing hand as a hand that never acted.
                if not cell.opportunities or (hide_small and not cell.sample_sufficient):
                    cells.append(f"{'.':>{width}}")
                    continue
                shown = cell.metric_value(view)
                if shown is None:
                    cells.append(f"{'.':>{width}}")
                    continue
                marker = "*" if not cell.sample_sufficient else ""
                cells.append(f"{_format_value(shown, spec.unit) + marker:>{width}}")
            lines.append(f"{row_rank:>5} " + " ".join(cells))
        legend = [
            "* below the sample threshold",
            ". no decision in this class",
            f"{UNKNOWN_LABEL} = {self.unknown_opportunities()} decisions whose cards were never shown, "
            "kept apart and never spread over the other classes",
        ]
        if self.notes:
            legend.extend(f"-- {note}" for note in self.notes)
        return "\n".join([*lines, "", *legend])

    def as_dict(self, view: str = DEFAULT_VIEW) -> dict[str, Any]:
        return {
            "engine_metric": self.engine_metric,
            "view": view,
            "unit": metric(view).unit,
            "group_by": CLASS_DIMENSION,
            "filters": dict(self.query.filters),
            "numerator": dict(self.query.numerator),
            "min_sample": self.min_sample,
            "grid": [list(row) for row in self.labels()],
            "values": [list(row) for row in self.values(view)],
            "cells": [cell.as_dict(view, self.total_opportunities) for cell in self.known_cells()],
            "unknown": [cell.as_dict(view, self.total_opportunities) for cell in self.unknown_cells.values()],
            "total_opportunities": self.total_opportunities,
            "total_hands": self.total_hands,
            "total_hand_players": self.total_hand_players,
            "total_realized_cents": self.total_realized_cents,
            "total_ev_adjusted_cents": self.total_ev_adjusted_cents,
            "unknown_opportunities": self.unknown_opportunities(),
            "notes": list(self.notes),
            "views": [spec.as_dict() for spec in METRICS.values()],
        }


def _id_of_label(text: str) -> int:
    """A label (or the unknown label) as a class id."""
    token = text.strip()
    return UNKNOWN_ID if token.lower() == UNKNOWN_LABEL else class_id_of_label(token)


def game_categories(db: Any, query: Query) -> tuple[str, ...]:
    """The game categories a filter set selects, for the Hold'em scope check."""
    result = run_query(db, Query(metric="opportunities", filters=dict(query.filters), group_by=("game",)))
    return tuple(str(row.group["game"]) for row in result.rows if row.opportunities)


def check_holdem(db: Any, query: Query) -> tuple[str, ...]:
    """Refuse a population that is not Hold'em, naming the categories that are not.

    Two of an Omaha hand's cards are not a starting hand, and neither are the
    cards of a draw game: the 13x13 grid would classify them anyway and produce
    a full, well-formed, meaningless picture. The check is on the population the
    filters select, not on the database.
    """
    categories = game_categories(db, query)
    foreign = [category for category in categories if HOLDEM_MARKER not in category.lower()]
    if foreign:
        raise NotHoldem(
            f"The 13x13 grid is a Hold'em range; this population also holds {foreign}. "
            "Narrow the filters to a Hold'em game (filter game=holdem).",
        )
    return categories


def _cell_from(
    class_id: int,
    counts: QueryRow | None,
    money: profit.ProfitRow | None,
) -> RangeCell:
    """One cell from the engine's count row and the report's money row."""
    return RangeCell(
        class_id=class_id,
        opportunities=counts.opportunities if counts else 0,
        actions=counts.actions if counts else 0,
        hands=_number(money.hands if money else 0),
        players=_number(money.players if money else 0),
        hand_players=_number(money.hand_players if money else 0),
        frequency_bp=counts.frequency_bp if counts else None,
        value=counts.value if counts else None,
        unit=counts.unit if counts else "",
        realized_cents=_number(money.realized_cents if money else 0),
        ev_adjusted_cents=_number(money.ev_adjusted_cents if money else 0),
        all_in_luck_cents=_number(money.all_in_luck_cents if money else 0),
        ev_adjusted_pairs=_number(money.ev_adjusted_pairs if money else 0),
        sample_sufficient=bool(money.sample_sufficient) if money else False,
    )


def _class_of(value: Any) -> int:
    """A ``starting_hand_id`` value as an int class id."""
    try:
        return int(value)
    except (TypeError, ValueError):
        raise UnknownClass(f"The grid's dimension returned {value!r}, which is not a class id") from None


def build_range(
    db: Any,
    query: Query,
    *,
    min_sample: int = 0,
    require_holdem: bool = True,
) -> RangeMatrix:
    """Build the grid of a filtered population.

    Two grouped queries and one ungrouped report, all over the caller's filters:
    the engine's own metric per class (the frequency the caller asked for), the
    money per class (#300), and the population total that the cells must add up
    to. The cells are then the *same* population as the query, which is what the
    reconciliation check asserts.
    """
    if CLASS_DIMENSION not in DIMENSIONS:
        raise RuntimeError(f"The engine has no {CLASS_DIMENSION!r} dimension")
    if require_holdem:
        check_holdem(db, query)

    grouped = Query(
        metric=query.metric,
        filters=dict(query.filters),
        numerator=dict(query.numerator),
        group_by=(CLASS_DIMENSION,),
    )
    counts: QueryResult = run_query(db, grouped)
    report = profit.profit_report(
        db,
        Query(metric="total_profit", filters=dict(query.filters), numerator=dict(query.numerator), group_by=(CLASS_DIMENSION,)),
        min_sample=min_sample,
        with_hand_ids=False,
    )

    counts_by_class = {_class_of(row.group[CLASS_DIMENSION]): row for row in counts.rows}
    money_by_class = {_class_of(row.group[CLASS_DIMENSION]): row for row in report.rows}

    cells: list[RangeCell] = []
    unknown: dict[int, RangeCell] = {}
    for class_id in _all_class_ids():
        cell = _cell_from(class_id, counts_by_class.get(class_id), money_by_class.get(class_id))
        if cell.is_unknown:
            unknown[class_id] = cell
        else:
            cells.append(cell)

    notes = (
        "each decision is counted in the class of the acting player's own cards; the hands of the "
        "players who never showed are not guessed, they are the 'xx' line",
        "a class is a set of combinations, not a strength: 22 and AA are six combinations each",
        "money follows the hand: a class's profit is the hand result of the hand-players whose "
        "decisions reach it, not the expected value of the class",
        "EV-adjusted profit marks only the all-in pots fpdb could price "
        f"({report.total.ev_adjusted_pairs} of {report.total.hand_players} pairs)",
        f"grid cells never sum to the total: a hand-player counts in every class its decisions reach "
        f"({report.total.hand_players} pairs, {report.total.opportunities} decisions)",
    )
    matrix = RangeMatrix(
        query=query,
        engine_metric=query.metric,
        unit=counts.rows[0].unit if counts.rows else "",
        min_sample=min_sample,
        cells=tuple(cells),
        unknown_cells=unknown,
        total_opportunities=report.total.opportunities,
        total_hands=report.total.hands,
        total_hand_players=report.total.hand_players,
        total_realized_cents=report.total.realized_cents,
        total_ev_adjusted_cents=report.total.ev_adjusted_cents,
        notes=notes,
        _by_id={cell.class_id: cell for cell in [*cells, *unknown.values()]},
    )
    problems = matrix.reconcile()
    if problems:
        raise AssertionError(f"The grid does not reconcile with its query: {'; '.join(problems)}")
    return matrix


def _all_class_ids() -> tuple[int, ...]:
    """The 169 classes in grid order, then the unknown class."""
    return tuple(class_id for row in grid_ids() for class_id in row) + (UNKNOWN_ID,)


def cell_query(query: Query, value: str | int) -> Query:
    """One cell as a query of its own, for its hands and its own statistics.

    The cell's class *is* a filter value, so the drill-down is the same
    population the cell counted -- not a re-derivation of it.
    """
    class_id = value if isinstance(value, int) else _id_of_label(str(value))
    return profit.narrow_query(query, {"starting_hand": class_id})


def cell_hand_ids(db: Any, query: Query, value: str | int, limit: int | None = None) -> tuple[int, ...]:
    """The hands behind one cell, for the viewer."""
    return profit.matching_hand_ids(db, cell_query(query, value), limit=limit)


def share_of_range(values: Sequence[str | int]) -> float:
    """The share of all 1326 dealt combinations a selection covers."""
    return share_of_dealt(values)


__all__ = [
    "CLASS_DIMENSION",
    "DEFAULT_VIEW",
    "METRICS",
    "NotHoldem",
    "RangeCell",
    "RangeMatrix",
    "RangeMetric",
    "UnknownView",
    "build_range",
    "cell_hand_ids",
    "cell_query",
    "check_holdem",
    "game_categories",
    "metric",
    "share_of_range",
]
