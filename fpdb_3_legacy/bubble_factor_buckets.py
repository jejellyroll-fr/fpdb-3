"""The bubble factor as bands a tournament player reads (#446).

``IB.bubbleFactor`` is stored in hundredths: 1.35 is 135. A bubble factor of 1
is a chip-EV spot; the higher it is, the more equity a call needs
(``BF / (1 + BF)``), so the bands follow what that does to a calling range
rather than round numbers.

A decision with no stored factor lands in ``unknown``: its tournament has no
known payout structure, or its field did not fit at one table (fpdb sees only
this table's stacks), or it was not a preflop decision. Unknown is not 1.
"""

from __future__ import annotations

from typing import Final

#: The stored column is ``round(bubble factor * 100)``.
BUBBLE_FACTOR_SCALE: Final[int] = 100

#: A factor this large or infinite (winning gains nothing) is stored as this.
BUBBLE_FACTOR_CAP: Final[int] = 99_999

UNKNOWN_BUBBLE_FACTOR_BUCKET: Final[str] = "unknown"

#: ``(inclusive upper bound in stored units, label)``, ascending. The last band is open.
BUBBLE_FACTOR_BUCKET_BOUNDS: Final[tuple[tuple[int, str], ...]] = (
    (120, "up_to_1_2"),
    (150, "1_2_to_1_5"),
    (200, "1_5_to_2"),
    (300, "2_to_3"),
)
BUBBLE_FACTOR_OPEN_BUCKET: Final[str] = "3_plus"

BUBBLE_FACTOR_BUCKETS: Final[tuple[str, ...]] = (
    *(label for _bound, label in BUBBLE_FACTOR_BUCKET_BOUNDS),
    BUBBLE_FACTOR_OPEN_BUCKET,
    UNKNOWN_BUBBLE_FACTOR_BUCKET,
)

BUBBLE_FACTOR_LABELS: Final[dict[str, str]] = {
    "up_to_1_2": "Bubble factor 1.2 or less (close to chip EV)",
    "1_2_to_1_5": "Bubble factor 1.2-1.5",
    "1_5_to_2": "Bubble factor 1.5-2",
    "2_to_3": "Bubble factor 2-3",
    "3_plus": "Bubble factor 3+",
    UNKNOWN_BUBBLE_FACTOR_BUCKET: "Bubble factor not known",
}


def bubble_factor_bucket_of(stored: int | None) -> str:
    """The band one stored bubble factor falls in, ``unknown`` when there is none."""
    if stored is None or stored <= 0:
        return UNKNOWN_BUBBLE_FACTOR_BUCKET
    for bound, label in BUBBLE_FACTOR_BUCKET_BOUNDS:
        if stored <= bound:
            return label
    return BUBBLE_FACTOR_OPEN_BUCKET


def bubble_factor_bucket_expression(qualifier: str = "IB.") -> str:
    """The same bands as a SQL ``CASE``, so Python and the database agree.

    The labels are fixed identifiers in this module, so there is nothing to escape.
    """
    ref = f"{qualifier}bubbleFactor"
    whens = " ".join(f"WHEN {ref} <= {bound} THEN '{label}'" for bound, label in BUBBLE_FACTOR_BUCKET_BOUNDS)
    return (
        f"CASE WHEN {ref} IS NULL OR {ref} <= 0 THEN '{UNKNOWN_BUBBLE_FACTOR_BUCKET}' "
        f"{whens} ELSE '{BUBBLE_FACTOR_OPEN_BUCKET}' END"
    )


__all__ = [
    "BUBBLE_FACTOR_BUCKETS",
    "BUBBLE_FACTOR_BUCKET_BOUNDS",
    "BUBBLE_FACTOR_CAP",
    "BUBBLE_FACTOR_LABELS",
    "BUBBLE_FACTOR_OPEN_BUCKET",
    "BUBBLE_FACTOR_SCALE",
    "UNKNOWN_BUBBLE_FACTOR_BUCKET",
    "bubble_factor_bucket_expression",
    "bubble_factor_bucket_of",
]
