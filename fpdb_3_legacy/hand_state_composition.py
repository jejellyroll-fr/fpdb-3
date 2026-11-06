"""What a filtered population was holding: range composition (#302).

The query engine answers "how often did this action happen"; the profit report
answers "for how much" (#300); the range explorer draws the 13x13 grid of the
cards a player was *dealt* (#301). This module answers the postflop question:
given a population of decisions, what were they holding when they made them --
made hands, pair detail, nutness, draws, blockers.

It is a thin layer on purpose. Every count comes from ``run_query`` over the
stored ``HandStates`` rows, using the engine's own filters, so a composition
figure and the drill-down under it are the same rows by construction:

* **compose(db, query, "made_hand")** groups the classified decisions by the
  column the classifier wrote and reports each category with its count and its
  share of the classified population;
* **compose(db, query, "draw")** counts one engine filter per draw name, because
  a decision can have several draws at once: those rows *overlap*, and the
  report says so instead of letting them be added up;
* the decisions that were **not classified** -- no board yet, or cards that were
  never shown -- are reported as their own number, never spread across the
  categories. A population of 300 decisions whose composition is 35 is a
  statement about 35 decisions, and the report says which.

Shares are in basis points of the classified population (the unit the rest of
the analytics layers use), rows below ``min_sample`` are flagged rather than
hidden, and nothing here writes to the database.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, NamedTuple

from .analytics_profit import matching_hand_ids, narrow_query
from .analytics_query import Query, run_query
from .hand_state import BLOCKER_BITS, DRAW_BITS, MADE_HANDS

BP: Final = 10000


class DimensionSpec(NamedTuple):
    """One composition dimension: what it means, and how its rows add up."""

    name: str
    label: str
    none_means: str
    kind: str  # "partition" (rows add up), "subset" (None is a category), "multi" (rows overlap)


#: The dimensions a composition can be read by, each with the meaning of a
#: missing value. ``partition`` rows partition the classified population;
#: ``subset`` has a bucket that is a real answer ("this made hand has no pair to
#: detail"); ``multi`` counts a decision under every flag it has, so the rows
#: overlap and the shares do not sum.
DIMENSIONS: Final[dict[str, DimensionSpec]] = {
    "made_hand": DimensionSpec("made_hand", "Made hand", "", "partition"),
    "made_hand_rank": DimensionSpec("made_hand_rank", "Made hand (by strength)", "", "partition"),
    "pair_detail": DimensionSpec(
        "pair_detail",
        "Pair detail",
        "no pair to detail",
        "subset",
    ),
    "nutness": DimensionSpec("nutness", "Nutness", "", "partition"),
    "hand_state_street": DimensionSpec("hand_state_street", "Street", "", "partition"),
    "draw": DimensionSpec("draw", "Draw", "no draw", "multi"),
    "blocker": DimensionSpec("blocker", "Blocker", "no blocker", "multi"),
}

#: The flag vocabularies the multi-label dimensions read, from the classifier.
FLAGS: Final[dict[str, Mapping[str, int]]] = {"draw": DRAW_BITS, "blocker": BLOCKER_BITS}


@dataclass(frozen=True)
class CategoryCount:
    """One row of a composition: a category, how many decisions, how often."""

    key: str | None
    label: str
    decisions: int
    share_bp: int | None
    flagged: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "decisions": self.decisions,
            "share_bp": self.share_bp,
            "flagged": self.flagged,
        }


@dataclass(frozen=True)
class Composition:
    """The composition of one population over one dimension."""

    dimension: str
    label: str
    total: int
    classified: int
    unclassified: int
    rows: tuple[CategoryCount, ...]
    kind: str
    min_sample: int = 0
    notes: tuple[str, ...] = field(default=())
    compiled: tuple[Any, ...] = field(default=())

    @property
    def partitions(self) -> bool:
        """Whether the rows add up to the classified population (no double counting)."""
        return self.kind == "partition"

    @property
    def coverage_bp(self) -> int:
        """The share of the population the composition actually describes."""
        return round(self.classified * BP / self.total) if self.total else 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "label": self.label,
            "total": self.total,
            "classified": self.classified,
            "unclassified": self.unclassified,
            "coverage_bp": self.coverage_bp,
            "partitions": self.partitions,
            "kind": self.kind,
            "min_sample": self.min_sample,
            "rows": [row.as_dict() for row in self.rows],
            "notes": list(self.notes),
        }

    def render(self, limit: int | None = None) -> str:
        lines = [
            f"{self.label} composition: {self.classified} classified decisions "
            f"of {self.total} ({self.coverage_bp / 100:.1f}%), {self.unclassified} not classified",
        ]
        if self.kind == "multi":
            lines.append("  rows overlap: a decision is counted under every flag it has")
        elif self.kind == "subset":
            lines.append("  the first row is a category too: those decisions have no value here")
        lines.append(f"  {'category':<44} {'decisions':>9} {'share':>8}")
        rows = self.rows[:limit] if limit is not None else self.rows
        for row in rows:
            share = "  n/a" if row.share_bp is None else f"{row.share_bp / 100:.1f}%"
            mark = " !" if row.flagged else ""
            lines.append(f"  {row.label:<44} {row.decisions:>9} {share:>8}{mark}")
        for note in self.notes:
            lines.append(f"  note: {note}")
        return "\n".join(lines)


def _dimension(name: str) -> DimensionSpec:
    if name not in DIMENSIONS:
        raise ValueError(f"Unknown composition dimension {name!r}; known: {sorted(DIMENSIONS)}")
    return DIMENSIONS[name]


def _with_filters(query: Query, extra: Mapping[str, Any]) -> Query:
    """The query with extra filters ANDed on, leaving the caller's alone."""
    filters = dict(query.filters)
    filters.update(extra)
    return Query(
        metric=query.metric,
        filters=filters,
        group_by=query.group_by,
        numerator=dict(query.numerator),
        limit=query.limit,
    )


def _count(db: Any, query: Query) -> int:
    return int(run_query(db, _with_filters(query, {"hand_state_known": True})).total_opportunities)


def _compiled(result: Any) -> tuple[Any, ...]:
    """The compiled statements behind a result, however the engine wrapped them.

    ``run_query`` returns one statement for a grouped query and a tuple for a
    multi-part one; the report carries whichever it got, flattened, so ``--sql``
    can print all of them.
    """
    compiled = result.compiled
    return tuple(compiled) if isinstance(compiled, (tuple, list)) else (compiled,)


def _opportunities(db: Any, query: Query) -> int:
    return int(run_query(db, query).total_opportunities)


def _shares(decisions: Sequence[int], total: int, *, exact: bool) -> list[int | None]:
    """Whole basis points per row, without the rounding leaving a hole.

    A partition that is rounded row by row sums to 100.1% often enough that a
    reader notices, and the column is meant to be added up. The rounding
    remainder is handed to the rows with the largest fractions (the largest
    remainder method), so a dimension whose rows partition the population sums
    to exactly 10000 -- and an overlapping one does not pretend to.
    """
    if not total:
        return [None] * len(decisions)
    exact_values = [count * BP / total for count in decisions]
    if not exact:
        return [round(value) for value in exact_values]
    floors = [int(value) for value in exact_values]
    order = sorted(range(len(decisions)), key=lambda index: exact_values[index] - floors[index], reverse=True)
    for index in order[: BP - sum(floors)]:
        floors[index] += 1
    return list(floors)


def _rank_label(key: Any) -> str:
    """A made-hand rank as the name of the hand, so a table reads as poker."""
    try:
        rank = int(key)
    except (TypeError, ValueError):
        return str(key)
    return MADE_HANDS[rank - 1] if 1 <= rank <= len(MADE_HANDS) else f"rank {rank}"


def _category_label(spec: DimensionSpec, key: Any) -> str:
    """The label of a category: the vocabulary value, so it can be filtered again."""
    if key is None or key == "":
        return "(not classified)" if not spec.none_means else f"({spec.none_means})"
    if spec.name == "made_hand_rank":
        return _rank_label(key)
    return str(key)


def _partition_rows(
    db: Any,
    spec: DimensionSpec,
    query: Query,
    classified: int,
    min_sample: int,
) -> tuple[list[CategoryCount], tuple[Any, ...]]:
    """The rows of a single-label dimension: one GROUP BY over its column."""
    grouped = _with_filters(query, {"hand_state_known": True})
    grouped = Query(
        metric="opportunities",
        filters=dict(grouped.filters),
        group_by=(spec.name,),
        limit=None,
    )
    result = run_query(db, grouped)
    keys = [row.group.get(spec.name) for row in result.rows]
    counts = [int(row.opportunities) for row in result.rows]
    shares = _shares(counts, classified, exact=spec.kind == "partition")
    rows = [
        CategoryCount(
            key=None if key is None else str(key),
            label=_category_label(spec, key),
            decisions=decisions,
            share_bp=share,
            flagged=bool(min_sample and decisions < min_sample),
        )
        for key, decisions, share in zip(keys, counts, shares, strict=True)
    ]
    return rows, (grouped,)


def _multi_rows(
    db: Any,
    spec: DimensionSpec,
    query: Query,
    classified: int,
    min_sample: int,
) -> tuple[list[CategoryCount], tuple[Any, ...]]:
    """The rows of a multi-label dimension: one engine filter per flag.

    One filter per flag rather than one SQL with a bit test per flag: the count
    of behaviours a flag catches is then the count the same filter returns to
    anyone else, and the two cannot drift.
    """
    flags = FLAGS[spec.name]
    rows: list[CategoryCount] = []
    compiled: list[Any] = []
    for name in flags:
        result = run_query(db, _with_filters(query, {"hand_state_known": True, spec.name: [name]}))
        decisions = int(result.total_opportunities)
        rows.append(
            CategoryCount(
                key=name,
                label=name,
                decisions=decisions,
                share_bp=round(decisions * BP / classified) if classified else None,
                flagged=bool(min_sample and 0 < decisions < min_sample),
            ),
        )
        compiled.extend(_compiled(result))
    # "No draw at all" is its own engine filter rather than the classified
    # population minus the flags: a decision with two draws would otherwise be
    # subtracted twice, and the row would count decisions that were never there.
    result = run_query(db, _with_filters(query, {"hand_state_known": True, f"{spec.name}_none": True}))
    none_count = int(result.total_opportunities)
    compiled.extend(_compiled(result))
    rows.append(
        CategoryCount(
            key=None,
            label=f"({spec.none_means})",
            decisions=none_count,
            share_bp=round(none_count * BP / classified) if classified else None,
            flagged=bool(min_sample and 0 < none_count < min_sample),
        ),
    )
    rows.sort(key=lambda row: (-row.decisions, row.label))
    return rows, tuple(compiled)


def compose(
    db: Any,
    query: Query | None = None,
    dimension: str = "made_hand",
    min_sample: int = 0,
) -> Composition:
    """The composition of a population over one hand-state dimension.

    The population is the query's, unchanged: a composition of ``cbet`` flops is
    the composition of the decisions that c-bet, not of the hands that did. The
    query's own ``group_by`` is refused rather than ignored -- the dimension
    *is* the grouping, and a caller who passed one meant it.
    """
    spec = _dimension(dimension)
    query = query or Query(metric="opportunities")
    if query.group_by:
        raise ValueError(
            f"A composition groups by its dimension, not by {query.group_by}; "
            "pass filters only, or call it once per group",
        )
    total = _opportunities(db, query)
    classified = _count(db, query)
    unclassified = max(total - classified, 0)
    if spec.kind == "multi":
        rows, compiled = _multi_rows(db, spec, query, classified, min_sample)
    else:
        rows, compiled = _partition_rows(db, spec, query, classified, min_sample)
    notes = tuple(_notes(spec, classified, unclassified))
    return Composition(
        dimension=spec.name,
        label=spec.label,
        total=total,
        classified=classified,
        unclassified=unclassified,
        rows=tuple(rows),
        kind=spec.kind,
        min_sample=min_sample,
        notes=notes,
        compiled=tuple(compiled),
    )


def _notes(spec: DimensionSpec, classified: int, unclassified: int) -> list[str]:
    """The caveats a reader has to know to use the numbers above."""
    notes: list[str] = []
    if unclassified:
        notes.append(
            f"{unclassified} decisions carry no hand state (no postflop board, or cards never shown) "
            "and are counted nowhere above",
        )
    if not classified:
        notes.append("no decision in this population has a stored hand state")
    if spec.kind == "subset":
        notes.append(f"a missing value is a category, and it means {spec.none_means}")
    if spec.kind == "multi":
        notes.append(
            "the rows overlap: a decision is counted under every flag it has, so the shares are of "
            "the classified population and sum to well over 100%",
        )
    return notes


def compose_hands(
    db: Any,
    dimension: str,
    key: str | None,
    query: Query | None = None,
    limit: int | None = None,
) -> tuple[int, ...]:
    """The hands behind one composition row -- the drill-down of a category.

    Built by narrowing the same query with the same-named filter, so the hands
    are the decisions the row counted and not a re-implementation of it.
    """
    spec = _dimension(dimension)
    query = query or Query(metric="opportunities")
    narrowed = Query(
        metric="opportunities",
        filters=dict(_with_filters(query, {"hand_state_known": True}).filters),
        group_by=(),
        limit=None,
    )
    if key is None:
        if spec.kind != "multi":
            raise ValueError(
                f"Only an overlapping dimension has a 'no flag' row to drill into; "
                f"{spec.name}'s missing values are read as {spec.none_means or 'a row of their own'} ",
                "by filtering the categories themselves",
            )
        narrowed = _with_filters(narrowed, {f"{spec.name}_none": True})
    else:
        narrowed = narrow_query(narrowed, {spec.name: key})
    return matching_hand_ids(db, narrowed, limit=limit)


def categories() -> dict[str, Sequence[str]]:
    """The category values each dimension can produce, for a legend or a filter UI."""
    return {
        "made_hand": MADE_HANDS,
        "nutness": ("nuts", "near_nuts", "strong", "medium", "weak"),
        "draw": tuple(DRAW_BITS),
        "blocker": tuple(BLOCKER_BITS),
    }


__all__ = [
    "BP",
    "DIMENSIONS",
    "FLAGS",
    "CategoryCount",
    "Composition",
    "DimensionSpec",
    "categories",
    "compose",
    "compose_hands",
]
