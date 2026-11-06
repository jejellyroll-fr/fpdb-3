"""Reproducible analytics benchmarks: a dataset generator and a timing harness (#304).

"A million hands" is not a number anyone can test against a fixture. This
module makes the dataset instead: it clones one real hand -- its players,
actions, boards and situations -- into as many hands as asked, so a benchmark
database has the *shape* of real data (the same joins, the same cardinalities
per hand) at whatever scale is wanted, and is byte-for-byte reproducible
because every clone is derived from the same source row.

The harness then times the query shapes the issue names -- a simple filtered
frequency, a grouped positional query, a sizing histogram, a texture
breakdown -- against :data:`DEFAULT_BENCHMARKS`, and the CLI
(``tools/benchmark_analytics.py``) prints the result beside the latency
targets recorded in ``docs/analytics-performance.md``.

Cloning is deliberately limited to the analytics tables (``HandsPlayers``,
``HandsActions``, ``Boards``, ``BoardFeatures``, ``HandsSituations``): the HUD
cache and the summary tables are per-hand aggregates whose unique keys would
collide, and none of them is what the analytics queries read.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final

from .analytics_query import Query, run_query

# Tables cloned per generated hand, and the fact that each is keyed by handId.
CLONED_TABLES: Final[tuple[str, ...]] = (
    "HandsPlayers",
    "HandsActions",
    "Boards",
    "BoardFeatures",
    "HandsSituations",
)

# The query shapes the issue asks to track. Targets are the p95 budgets
# recorded in docs/analytics-performance.md; they are goals, not assertions.
DEFAULT_BENCHMARKS: Final[tuple[tuple[str, Query], ...]] = (
    ("filtered_frequency", Query(metric="fold_frequency", filters={"street": "flop", "situation": "facing_cbet"})),
    ("grouped_positional", Query(metric="fold_frequency", filters={"street": "preflop"}, group_by=("position", "response"))),
    ("sizing_histogram", Query(metric="average_sizing", filters={"street": "flop"}, group_by=("sizing_bucket",))),
    ("texture_breakdown", Query(metric="opportunities", filters={"street": "flop"}, group_by=("board_suit",))),
    ("profit_by_position", Query(metric="total_profit", filters={"street": "preflop"}, group_by=("position",))),
)

# p95 budgets in milliseconds, per benchmark name. A dataset of a few thousand
# cloned hands is far below these; the number is here so a regression is a
# numeric claim rather than "it felt slower".
LATENCY_TARGETS_MS: Final[dict[str, float]] = {
    "filtered_frequency": 50.0,
    "grouped_positional": 75.0,
    "sizing_histogram": 75.0,
    "texture_breakdown": 75.0,
    "profit_by_position": 100.0,
}


@dataclass(frozen=True)
class BenchmarkResult:
    """One query shape timed over a dataset."""

    name: str
    repeats: int
    best_ms: float
    mean_ms: float
    rows_returned: int
    target_ms: float | None

    @property
    def within_target(self) -> bool:
        return self.target_ms is None or self.best_ms <= self.target_ms

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "repeats": self.repeats,
            "best_ms": round(self.best_ms, 3),
            "mean_ms": round(self.mean_ms, 3),
            "rows_returned": self.rows_returned,
            "target_ms": self.target_ms,
            "within_target": self.within_target,
        }


def _placeholder(db: Any) -> str:
    try:
        return str(db.sql.query["placeholder"])
    except (AttributeError, KeyError):
        return "%s"


def _source_hand(db: Any, source_hand_id: int | None) -> int:
    cursor = db.get_cursor()
    if source_hand_id is not None:
        return int(source_hand_id)
    # The richest hand is the best template: one with players, actions, boards
    # and situations all present, so every populated analytics table has rows.
    # ``Boards`` is only populated for run-it-twice boards; ordinary hands keep
    # their main board on ``Hands`` while ``BoardFeatures`` is the analytics
    # fact table. Requiring ``Boards`` here would reject the normal corpus.
    cursor.execute(
        "SELECT H.id FROM Hands H"
        " JOIN HandsActions A ON A.handId = H.id"
        " JOIN HandsPlayers P ON P.handId = H.id"
        " JOIN BoardFeatures BF ON BF.handId = H.id"
        " JOIN HandsSituations S ON S.handId = H.id"
        " GROUP BY H.id ORDER BY COUNT(S.id) DESC, H.id DESC LIMIT 1",
    )
    row = cursor.fetchone()
    if row is None:
        raise ValueError("Cannot synthesize a benchmark dataset: the database has no hands")
    return int(row[0])


def _read_rows(cursor: Any, table: str, where: str, params: Sequence[Any]) -> tuple[list[str], list[tuple[Any, ...]]]:
    """One table's rows and column names, for a where clause the caller wrote."""
    cursor.execute(f"SELECT * FROM {table} WHERE {where}", tuple(params))  # nosec B608  # nosemgrep
    columns = [description[0] for description in cursor.description]
    return columns, [tuple(row) for row in cursor.fetchall()]


def _clone_children(db: Any, source_hand_id: int, new_ids: Sequence[int]) -> None:
    """Copy every analytics row of the source hand onto each new hand id."""
    cursor = db.get_cursor()
    placeholder = _placeholder(db)
    for table in CLONED_TABLES:
        try:
            columns, rows = _read_rows(cursor, table, f"handId = {placeholder}", (source_hand_id,))
        except Exception:  # noqa: BLE001 - a feature table this database does not have
            db.rollback()
            continue
        if not rows or "handId" not in columns:
            continue
        hand_index = columns.index("handId")
        # The autoincrement ``id`` is the only column not carried over; keep the
        # value indices so the payload lines up with the insert column list.
        keep = [index for index, name in enumerate(columns) if name != "id"]
        insert_columns = [columns[index] for index in keep]
        payload: list[tuple[Any, ...]] = []
        for new_id in new_ids:
            for row in rows:
                payload.append(tuple(new_id if index == hand_index else row[index] for index in keep))
        marks = ", ".join(placeholder for _ in insert_columns)
        cursor.executemany(  # nosec B608  # nosemgrep
            f"INSERT INTO {table} ({', '.join(insert_columns)}) VALUES ({marks})",  # nosec B608  # nosemgrep
            payload,
        )
    db.commit()


def synthesize_hands(db: Any, count: int, source_hand_id: int | None = None) -> int:
    """Clone the analytics rows of one hand into ``count`` new hands.

    Returns the number of hands created. The new ``siteHandNo`` values are
    offset past the current maximum so the unique index holds, and every clone
    is an exact copy of the source hand -- which is what makes the dataset
    reproducible.
    """
    if count <= 0:
        return 0
    cursor = db.get_cursor()
    placeholder = _placeholder(db)
    source_hand_id = _source_hand(db, source_hand_id)

    hand_columns, hand_rows = _read_rows(cursor, "Hands", f"id = {placeholder}", (source_hand_id,))
    if not hand_rows:
        raise ValueError(f"Cannot synthesize: hand {source_hand_id} does not exist")
    source = dict(zip(hand_columns, hand_rows[0], strict=True))

    cursor.execute("SELECT COALESCE(MAX(siteHandNo), 0) FROM Hands")
    base = int(cursor.fetchone()[0] or 0) + 1000

    insert_columns = [name for name in hand_columns if name != "id"]
    marks = ", ".join(placeholder for _ in insert_columns)
    hands_payload = []
    for offset in range(count):
        values = dict(source)
        values["siteHandNo"] = base + offset
        hands_payload.append(tuple(values[name] for name in insert_columns))
    cursor.executemany(  # nosec B608  # nosemgrep
        f"INSERT INTO Hands ({', '.join(insert_columns)}) VALUES ({marks})",  # nosec B608  # nosemgrep
        hands_payload,
    )
    db.commit()

    range_query = (
        "SELECT id FROM Hands WHERE siteHandNo >= ? AND siteHandNo <= ? ORDER BY siteHandNo"
        if placeholder == "?"
        else "SELECT id FROM Hands WHERE siteHandNo >= %s AND siteHandNo <= %s ORDER BY siteHandNo"
    )
    cursor.execute(range_query, (base, base + count - 1))
    new_ids = [int(row[0]) for row in cursor.fetchall()]
    _clone_children(db, source_hand_id, new_ids)
    return len(new_ids)


def benchmark_queries(
    db: Any,
    queries: Sequence[tuple[str, Query]] = DEFAULT_BENCHMARKS,
    repeats: int = 3,
    clock: Callable[[], float] = time.perf_counter,
) -> list[BenchmarkResult]:
    """Time each query shape ``repeats`` times and report best and mean."""
    results: list[BenchmarkResult] = []
    for name, query in queries:
        timings: list[float] = []
        rows_returned = 0
        for _ in range(max(1, repeats)):
            started = clock()
            result = run_query(db, query)
            timings.append((clock() - started) * 1000.0)
            rows_returned = len(result.rows)
        results.append(
            BenchmarkResult(
                name=name,
                repeats=max(1, repeats),
                best_ms=min(timings),
                mean_ms=sum(timings) / len(timings),
                rows_returned=rows_returned,
                target_ms=LATENCY_TARGETS_MS.get(name),
            ),
        )
    return results


def format_results(results: Sequence[BenchmarkResult]) -> str:
    """A fixed-width table, so two runs can be diffed."""
    lines = [f"{'benchmark':<22} {'best ms':>9} {'mean ms':>9} {'rows':>6} {'target':>8}  ok"]
    for result in results:
        target = "-" if result.target_ms is None else f"{result.target_ms:.0f}"
        lines.append(
            f"{result.name:<22} {result.best_ms:>9.2f} {result.mean_ms:>9.2f}"
            f" {result.rows_returned:>6} {target:>8}  {'yes' if result.within_target else 'NO'}",
        )
    return "\n".join(lines)


__all__ = [
    "CLONED_TABLES",
    "DEFAULT_BENCHMARKS",
    "LATENCY_TARGETS_MS",
    "BenchmarkResult",
    "benchmark_queries",
    "format_results",
    "synthesize_hands",
]
