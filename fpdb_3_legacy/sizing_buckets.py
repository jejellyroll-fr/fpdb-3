"""Sizing buckets over the persisted per-decision sizing (#296).

``HandsActions`` already carries one row per decision with the size of the
aggression it made (``sizingBp``) and the size of the aggression it faced
(``facingSizingBp``) -- the raw decision-level sizing the averaging stats
flatten away. This module is the shared vocabulary on top of those columns:
the bucket boundaries, the pure functions that name the bucket of a decision,
and the histogram / response helpers the query engine builds on.

Two conventions, both inherited from the event model (#293) and documented in
``docs/action-event-model.md``:

- Sizes are basis points of the pot the action faced (1% is 100bp), so a
  bucket table is a list of ``(lower, upper)`` pairs in the same unit and the
  numbers 2307 or 15400 mean the same thing everywhere.
- Bets are measured by the bet, raises by the raise-to amount. A bucket of a
  raise therefore describes "raise-to X% pot", not "raised by X% pot", and
  the boundaries below are written for that reading.

Buckets are configurable: the boundaries live in ``BucketConfig`` objects and
never inside a stat, so a caller can study turn bets in thirds without
touching this file. ``DEFAULT_BUCKETS`` is the issue's suggested table.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from .action_events import ACTION_EVENT_COLUMNS

# The sentinel a sizing that cannot be bucketed maps to: zero (no aggression,
# or a pot the size could not be measured against) is a real answer -- "they
# did not size anything" -- and it is kept apart from the buckets rather than
# folded into the smallest one.
UNKNOWN_BUCKET: Final = "unknown"

# The four decisions the corpus (#308) holds sizing pins for. A decision
# names the pair the rest of the module works from: the persisted column the
# size is read from (made-side ``sizingBp`` names the aggression the row
# took, faced-side ``facingSizingBp`` the aggression it responded to) and
# the bucket column name derived from it. ``allIn`` (a HandsActions column)
# is the all-in marker: bucket the row like any other and filter on allIn
# for the all-in slice -- a shove of 300% pot is a 150%+ row, not a special
# bucket.
DECISION_BUCKETS: Final[dict[str, tuple[str, str]]] = {
    "betMade": ("sizingBp", "betMadeBucket"),
    "betFaced": ("facingSizingBp", "betFacedBucket"),
    "raiseMade": ("sizingBp", "raiseMadeBucket"),
    "raiseFaced": ("facingSizingBp", "raiseFacedBucket"),
}

# The HandsActions sizing columns a bucket column may be derived from, for
# callers that validate identifiers before they build SQL from one.
SIZING_SOURCE_COLUMNS: Final[frozenset[str]] = frozenset(source for source, _ in DECISION_BUCKETS.values())

# The derived bucket-column names, for callers that validate a requested
# bucket column the same way.
BUCKET_DECISION_COLUMNS: Final[frozenset[str]] = frozenset(bucket for _, bucket in DECISION_BUCKETS.values())


@dataclass(frozen=True)
class BucketConfig:
    """One configurable sizing scale: named ``[lower, upper)`` ranges in bp.

    Boundaries are basis points of the pot the sizing was measured against,
    matching ``HandsActions.sizingBp`` / ``facingSizingBp``. The first bucket
    starts at 1 (a stored 0 is ``unknown``), the last is open-ended, and the
    boundaries are shared -- a size equal to a boundary belongs to the bucket
    that starts there, so the ten default buckets tile 1..+oo without a gap
    or an overlap. One more label than bounds: every bound opens a bucket,
    the last label catches everything at or above the last bound.
    """

    name: str
    upper_bounds_bp: tuple[int, ...]
    labels: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.upper_bounds_bp) + 1 != len(self.labels):
            raise ValueError(
                f"{self.name}: {len(self.upper_bounds_bp)} upper bounds "
                f"for {len(self.labels)} labels (need one more label than bounds)",
            )
        if any(upper <= 0 for upper in self.upper_bounds_bp):
            raise ValueError(f"{self.name}: upper bounds must be positive bp")

    def bucket_of(self, sizing_bp: int) -> str | None:
        """The bucket label of one stored size, or None for zero.

        Zero means the decision carried no aggression (a call or fold, or a
        bet whose pot was unknowable) -- the honest answer is "no size to
        speak of", not "the smallest bucket".
        """
        if sizing_bp <= 0:
            return None
        for index, upper in enumerate(self.upper_bounds_bp):
            if sizing_bp < upper:
                return self.labels[index]
        return self.labels[-1]


# The default table from issue #296: ten buckets covering 1% of pot upwards,
# measured in basis points. 2500bp is 25%, 15400bp is 154%.
DEFAULT_BUCKETS: Final[BucketConfig] = BucketConfig(
    name="default",
    upper_bounds_bp=(2500, 3300, 4000, 5000, 6600, 8000, 10000, 12500, 15000),
    labels=(
        "0-25",
        "25-33",
        "33-40",
        "40-50",
        "50-66",
        "66-80",
        "80-100",
        "100-125",
        "125-150",
        "150+",
    ),
)

# Preflop opens are traditionally read in multiples of the big blind rather
# than fractions of the (blind-seeded) pot, on a coarser scale. A stored
# raise-to of 2.5bb lands in "2-3".
DEFAULT_OPEN_BB_BUCKETS: Final[BucketConfig] = BucketConfig(
    name="open_bb",
    upper_bounds_bp=(200, 300, 400),
    labels=("1-2", "2-3", "3-4", "4+"),
)


def open_size_bb_bp(chips: int, big_blind: int) -> int:
    """An opening size in hundredths of a big blind (the unit DEFAULT_OPEN_BB_BUCKETS buckets).

    ``chips`` is cents as stored in ``HandsActions.amount`` / ``raiseTo``, so
    a 5.00 raise at 2.00 blinds gives 250 -- "2.5x", bucket "2-3".
    """
    if chips <= 0 or big_blind <= 0:
        return 0
    return chips * 100 // big_blind


def bucket_counts(
    sizes: Iterable[int | None],
    buckets: BucketConfig = DEFAULT_BUCKETS,
) -> dict[str, int]:
    """Histogram of raw sizes, ordered by bucket then ``unknown`` last.

    ``sizes`` are basis-point values (or None for "no size"); the histogram
    counts every input exactly once, so callers can hand it a whole filtered
    population without pre-summarizing it.
    """
    histogram = dict.fromkeys(buckets.labels, 0)
    histogram[UNKNOWN_BUCKET] = 0
    for size in sizes:
        bucket = UNKNOWN_BUCKET if size is None else buckets.bucket_of(size)
        if bucket is None:  # a None input that is not a size at all
            histogram[UNKNOWN_BUCKET] += 1
        else:
            histogram[bucket] += 1
    return histogram


def bucket_case_expression(
    column: str,
    buckets: BucketConfig = DEFAULT_BUCKETS,
) -> str:
    """A SQL CASE expression bucketing one sizing column, for GROUP BY histograms.

    ``column`` must be one of the known bucket-able decision columns; the
    expression is otherwise plain SQL that any backend accepts. Rows with a
    stored 0 land in ``unknown``, mirroring ``BucketConfig.bucket_of``.
    """
    if column not in SIZING_SOURCE_COLUMNS:
        raise ValueError(f"column is not a bucketable sizing decision: {column!r}")
    whens = " ".join(
        f"WHEN {column} >= {lower} AND {column} < {upper} THEN '{label}'"
        for lower, upper, label in zip(
            (1, *buckets.upper_bounds_bp[:-1]),
            buckets.upper_bounds_bp,
            buckets.labels[:-1],
            strict=True,
        )
    )
    open_when = f"WHEN {column} >= {buckets.upper_bounds_bp[-1]} THEN '{buckets.labels[-1]}'"
    return f"CASE WHEN {column} <= 0 THEN '{UNKNOWN_BUCKET}' {whens} {open_when} ELSE {column} END"


class BucketResponseStat:
    """Frequency and response of one bucket, as the popup layer reads them.

    ``chances`` counts the decisions that landed in the bucket, ``actions``
    the ones that took the aggressive (or calling) response, so a HUD line
    "vs 66-80% c-bet: folds 40%, calls 35%, raises 25%" is three of these
    over the same chances with different responses.
    """

    __slots__ = ("actions", "bucket", "chances")

    def __init__(self, bucket: str) -> None:
        self.bucket = bucket
        self.chances = 0
        self.actions = 0

    @property
    def frequency_bp(self) -> int:
        """How often the response was taken, in basis points (0 when never faced)."""
        return self.actions * 10000 // self.chances if self.chances else 0

    def as_dict(self) -> dict[str, int | str]:
        return {
            "bucket": self.bucket,
            "chances": self.chances,
            "actions": self.actions,
            "frequency_bp": self.frequency_bp,
        }


def bucket_response_stats(
    responses: Iterable[tuple[int | None, bool]],
    buckets: BucketConfig = DEFAULT_BUCKETS,
) -> list[BucketResponseStat]:
    """Per-bucket frequency of a yes/no response over a filtered population.

    ``responses`` yields ``(sizing_bp, responded)`` pairs -- sizing of the
    aggression faced, and whether the player took the response being counted.
    The returned list is ordered by bucket; empty buckets are included with
    zero chances so a popup can render the whole scale.
    """
    stats = {label: BucketResponseStat(label) for label in buckets.labels}
    stats[UNKNOWN_BUCKET] = BucketResponseStat(UNKNOWN_BUCKET)
    for size, responded in responses:
        bucket = UNKNOWN_BUCKET if size is None else buckets.bucket_of(size)
        stat = stats[UNKNOWN_BUCKET] if bucket is None else stats[bucket]
        stat.chances += 1
        if responded:
            stat.actions += 1
    return list(stats.values())


def bucket_decision_rows(
    rows: Sequence[Mapping[str, Any]],
    column: str,
    buckets: BucketConfig = DEFAULT_BUCKETS,
) -> dict[str, int]:
    """Histogram of one bucket-able column over persisted HandsActions rows."""
    if column not in SIZING_SOURCE_COLUMNS:
        raise ValueError(f"column is not a bucketable sizing decision: {column!r}")
    return bucket_counts((row.get(column) for row in rows), buckets)


# Ensure callers that import the event columns alongside the buckets see a
# single consistent list (keeps mypy honest about the re-export).
__all__ = [
    "ACTION_EVENT_COLUMNS",
    "BUCKET_DECISION_COLUMNS",
    "DECISION_BUCKETS",
    "SIZING_SOURCE_COLUMNS",
    "UNKNOWN_BUCKET",
    "DEFAULT_BUCKETS",
    "DEFAULT_OPEN_BB_BUCKETS",
    "BucketConfig",
    "BucketResponseStat",
    "bucket_case_expression",
    "bucket_counts",
    "bucket_decision_rows",
    "bucket_response_stats",
    "open_size_bb_bp",
]
