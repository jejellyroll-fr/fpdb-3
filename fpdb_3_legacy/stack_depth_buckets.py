"""Effective stack as the bands a tournament is actually played in (#369).

``A.effectiveStackBB`` is stored in hundredths of a big blind, so grouping a
panel by it directly produces one row per hundredth of a blind -- a few hundred
rows of noise where a reader wanted seven. Cash play has coarse bands already
(``SI.stackBucket``: short, medium, deep, very deep), and they are useless for
tournaments, where the whole game changes between 12 big blinds and 22.

The bands are data rather than query semantics: a :class:`StackDepthBuckets`
carries its own boundaries, the engine's dimension uses the default table, and
a caller studying 18-22bb specifically can build another one without touching
the compiler. :data:`DEFAULT_MTT_STACKS` is the table issue #369 proposes.

Boundaries are inclusive upper bounds, the way a player reads them: "40-60bb"
holds exactly 60 big blinds, and a stack of exactly 100bb is the top of
``60_to_100`` rather than the bottom of ``100_plus``. A decision whose
effective stack was never recorded lands in ``unknown``, because an unknown
depth is not a short one.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

#: The stored column is ``effective * 100 // big_blind``: 12.5bb is 1250.
STACK_SCALE: Final[int] = 100

UNKNOWN_STACK_BUCKET: Final[str] = "unknown"


@dataclass(frozen=True)
class StackDepthBuckets:
    """One table of effective-stack bands, in hundredths of a big blind."""

    name: str
    upper_bounds: tuple[int, ...]
    labels: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.upper_bounds) + 1 != len(self.labels):
            raise ValueError(
                f"{self.name}: {len(self.upper_bounds)} upper bounds for "
                f"{len(self.labels)} labels (need one more label than bounds)",
            )
        if any(bound <= 0 for bound in self.upper_bounds):
            raise ValueError(f"{self.name}: upper bounds must be positive")
        # The bands have to tile the domain, which they only do when each one
        # starts where the previous ended: an unordered or repeated bound
        # gives a label ``bucket_of`` can never return.
        if any(b <= a for a, b in zip(self.upper_bounds, self.upper_bounds[1:], strict=False)):
            raise ValueError(f"{self.name}: upper bounds must be strictly increasing")
        if UNKNOWN_STACK_BUCKET in self.labels:
            raise ValueError(f"{self.name}: {UNKNOWN_STACK_BUCKET!r} is reserved for unrecorded depths")
        for label in self.labels:
            # The labels are written into SQL as literals, so they are
            # identifiers rather than free text: refused here rather than
            # quoted, because nothing needs a quote in a band name.
            if not label.replace("_", "").isalnum():
                raise ValueError(f"{self.name}: band label must be alphanumeric: {label!r}")

    @property
    def names(self) -> tuple[str, ...]:
        """Every band this table can return, ``unknown`` last."""
        return (*self.labels, UNKNOWN_STACK_BUCKET)

    def bucket_of(self, stored: int | None) -> str:
        """The band one stored effective stack falls in."""
        if not stored or stored <= 0:
            return UNKNOWN_STACK_BUCKET
        for bound, label in zip(self.upper_bounds, self.labels, strict=False):
            if stored <= bound:
                return label
        return self.labels[-1]

    def case_expression(self, qualifier: str = "A.") -> str:
        """The same bands as a SQL ``CASE``, so Python and the database agree."""
        ref = f"{qualifier}effectiveStackBB"
        whens = " ".join(
            f"WHEN {ref} <= {bound} THEN '{label}'"
            for bound, label in zip(self.upper_bounds, self.labels, strict=False)
        )
        return (
            f"CASE WHEN {ref} IS NULL OR {ref} <= 0 THEN '{UNKNOWN_STACK_BUCKET}' "
            f"{whens} ELSE '{self.labels[-1]}' END"
        )


#: The tournament table from #369: the depths at which a tournament is a
#: different game. Nothing here knows about stage or payouts -- a stack is a
#: stack, and fpdb does not store what it was worth.
DEFAULT_MTT_STACKS: Final[StackDepthBuckets] = StackDepthBuckets(
    name="mtt",
    upper_bounds=(1000, 1500, 2500, 4000, 6000, 10000),
    labels=(
        "under_10",
        "10_to_15",
        "15_to_25",
        "25_to_40",
        "40_to_60",
        "60_to_100",
        "100_plus",
    ),
)

STACK_DEPTH_BUCKETS: Final[tuple[str, ...]] = DEFAULT_MTT_STACKS.names

STACK_DEPTH_LABELS: Final[dict[str, str]] = {
    "under_10": "10 BB or less",
    "10_to_15": "10-15 BB",
    "15_to_25": "15-25 BB",
    "25_to_40": "25-40 BB",
    "40_to_60": "40-60 BB",
    "60_to_100": "60-100 BB",
    "100_plus": "100 BB+",
    UNKNOWN_STACK_BUCKET: "Depth not recorded",
}

#: Bands whose play is materially different from their neighbours' -- the
#: reason an answer that averages several of them needs to say so (#369).
#: Below 25bb a raise is a commitment decision; above it, it is an opening
#: range. Anything that reports one number over a mixture of the two is
#: reporting a number about two different games.
SHALLOW_STACK_BUCKETS: Final[frozenset[str]] = frozenset({"under_10", "10_to_15", "15_to_25"})


def stack_bucket_of(stored: int | None, buckets: StackDepthBuckets = DEFAULT_MTT_STACKS) -> str:
    """The default table's band for one stored effective stack."""
    return buckets.bucket_of(stored)


def stack_bucket_expression(
    qualifier: str = "A.",
    buckets: StackDepthBuckets = DEFAULT_MTT_STACKS,
) -> str:
    """The default table's bands as SQL."""
    return buckets.case_expression(qualifier)


def mixes_stack_depths(bands: Iterable[str]) -> bool:
    """Whether a set of observed bands spans the shallow/deep divide.

    Two bands are "materially different" here in one specific sense: one of
    them is played for stacks and the other is not. An answer covering both
    is an average over two games, and the caller is expected to say so rather
    than print the mean and move on.
    """
    observed = {band for band in bands if band != UNKNOWN_STACK_BUCKET}
    if len(observed) < 2:
        return False
    return bool(observed & SHALLOW_STACK_BUCKETS) and bool(observed - SHALLOW_STACK_BUCKETS)


__all__ = [
    "DEFAULT_MTT_STACKS",
    "SHALLOW_STACK_BUCKETS",
    "STACK_DEPTH_BUCKETS",
    "STACK_DEPTH_LABELS",
    "STACK_SCALE",
    "UNKNOWN_STACK_BUCKET",
    "StackDepthBuckets",
    "mixes_stack_depths",
    "stack_bucket_expression",
    "stack_bucket_of",
]
