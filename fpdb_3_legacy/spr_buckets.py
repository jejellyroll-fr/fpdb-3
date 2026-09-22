"""Stack-to-pot ratio as bands a person reads, not as a number (#368).

``A.sprBefore`` is stored in hundredths of an SPR, so grouping a panel by it
directly produces one group per distinct ratio -- a few hundred rows of noise
rather than a reading. Every other continuous axis in the engine already has a
banded form (sizing, stacks); SPR did not, because no shipped study asked it
to. Pot-limit Omaha does: it is the variant where the commitment threshold,
not the hand, decides most flop lines.

The bands are the ones the game itself uses -- under 1 is committed, 1 to 2 is
one bet from committed, 13 and up is deep -- and an unrecorded pot lands in
``unknown`` rather than in the lowest band, because a missing SPR is not an
SPR of nought.
"""

from __future__ import annotations

from typing import Final

#: The stored column is ``effective * 100 // pot``: an SPR of 3.5 is 350.
SPR_SCALE: Final[int] = 100

UNKNOWN_SPR_BUCKET: Final[str] = "unknown"

#: ``(upper bound in stored units, label)``, ascending and half-open: a row
#: belongs to the first band whose bound it is under. The last band is open.
SPR_BUCKET_BOUNDS: Final[tuple[tuple[int, str], ...]] = (
    (100, "under_1"),
    (200, "1_to_2"),
    (400, "2_to_4"),
    (700, "4_to_7"),
    (1300, "7_to_13"),
)
SPR_OPEN_BUCKET: Final[str] = "13_plus"

SPR_BUCKETS: Final[tuple[str, ...]] = (
    *(label for _bound, label in SPR_BUCKET_BOUNDS),
    SPR_OPEN_BUCKET,
    UNKNOWN_SPR_BUCKET,
)

SPR_BUCKET_LABELS: Final[dict[str, str]] = {
    "under_1": "SPR under 1 (committed)",
    "1_to_2": "SPR 1-2",
    "2_to_4": "SPR 2-4",
    "4_to_7": "SPR 4-7",
    "7_to_13": "SPR 7-13",
    "13_plus": "SPR 13+",
    UNKNOWN_SPR_BUCKET: "SPR not recorded",
}


def spr_bucket_of(stored: int | None) -> str:
    """The band one stored SPR falls in, ``unknown`` when there is none."""
    if not stored or stored <= 0:
        return UNKNOWN_SPR_BUCKET
    for bound, label in SPR_BUCKET_BOUNDS:
        if stored < bound:
            return label
    return SPR_OPEN_BUCKET


def spr_bucket_expression(qualifier: str = "A.") -> str:
    """The same bands as a SQL ``CASE``, so Python and the database agree.

    The labels are fixed identifiers in this module rather than configuration,
    so there is nothing here to escape and nothing a caller can inject.
    """
    ref = f"{qualifier}sprBefore"
    whens = " ".join(f"WHEN {ref} < {bound} THEN '{label}'" for bound, label in SPR_BUCKET_BOUNDS)
    return (
        f"CASE WHEN {ref} IS NULL OR {ref} <= 0 THEN '{UNKNOWN_SPR_BUCKET}' "
        f"{whens} ELSE '{SPR_OPEN_BUCKET}' END"
    )


__all__ = [
    "SPR_BUCKETS",
    "SPR_BUCKET_BOUNDS",
    "SPR_BUCKET_LABELS",
    "SPR_OPEN_BUCKET",
    "SPR_SCALE",
    "UNKNOWN_SPR_BUCKET",
    "spr_bucket_expression",
    "spr_bucket_of",
]
