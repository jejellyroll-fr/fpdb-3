# Sizing buckets: distributions over the persisted decisions (#296)

## What it is

Since #293 every row of `HandsActions` carries the size of the aggression it
took (`sizingBp`) and of the aggression it responded to (`facingSizingBp`), in
basis points of the pot faced. The HUD's averaging stats collapse those
columns to sum/count — an average c-bet of 62% pot can hide half shoves and
half min-bets. `fpdb_3_legacy/sizing_buckets.py` is the queryable layer on
top: named buckets, histograms and per-bucket response frequencies, with the
boundaries configurable instead of hard-coded into every stat.

Nothing here changes what is parsed or stored. The buckets are derived
exactly like the situations of #294: read the persisted columns, name the
answer, keep the raw number untouched.

## Units and the two sizing columns

| Column | Meaning |
| --- | --- |
| `sizingBp` | The aggression this row took: the bet for a bet, the **raise-to** for a raise. Basis points of `potBefore` (1% = 100bp, a full pot = 10000). |
| `facingSizingBp` | The size of the aggression this row responded to, same unit and same convention. Zero for an open (nothing was ever bet into it) and for forced money. |

The raise is measured by the amount it raises **to**, not by — the
convention `HandsPlayers.val_*_bet_made_bp` / `val_*_raise_made_bp` already
use, so an event row and the aggregate column it feeds cannot drift apart.
A stored `0` is a real answer ("this decision carried no aggression, or no
measurable pot to size against") and is kept apart from the buckets as
`unknown`, never folded into the smallest bucket.

## Bucket tables

A `BucketConfig` is one named scale: an ordered tuple of upper bounds in bp
plus one more label than bounds (the last label catches everything at or
above the last bound). A size equal to a boundary belongs to the bucket that
starts there, so the buckets tile 1..+∞ with no gap and no overlap:

```python
from fpdb_3_legacy.sizing_buckets import BucketConfig

thirds = BucketConfig(
    name="thirds",
    upper_bounds_bp=(3300, 6600),   # 33% and 66% of pot
    labels=("low", "mid", "high"),
)
```

`DEFAULT_BUCKETS` is the table #296 suggests, in basis points:

| Label | bp range |
| --- | --- |
| 0-25 | 1 – 2499 |
| 25-33 | 2500 – 3299 |
| 33-40 | 3300 – 3999 |
| 40-50 | 4000 – 4999 |
| 50-66 | 5000 – 6599 |
| 66-80 | 6600 – 7999 |
| 80-100 | 8000 – 9999 |
| 100-125 | 10000 – 12499 |
| 125-150 | 12500 – 14999 |
| 150+ | 15000 and above |

Preflop opens are traditionally read in multiples of the big blind rather
than fractions of the blind-seeded pot, on a coarser scale:
`DEFAULT_OPEN_BB_BUCKETS` (1-2, 2-3, 3-4, 4+) over
`open_size_bb_bp(chips, big_blind)`, which converts a stored `raiseTo` into
hundredths of a big blind.

## The four decisions

`DECISION_BUCKETS` names the pairs the module works from — the persisted
source column and the derived bucket name:

| Decision | Source column | Read as |
| --- | --- | --- |
| `betMade` | `sizingBp` of a `bets` row | the bet the player made |
| `betFaced` | `facingSizingBp` | the bet the player is responding to |
| `raiseMade` | `sizingBp` of a `raises` row | the raise-to the player made |
| `raiseFaced` | `facingSizingBp` | the raise-to the player is responding to |

All-in shoves are not a special bucket: a 200bb shove over a 40bb 4-bet is a
`150+` raise like any other. Filter on `HandsActions.allIn` for the all-in
slice of a population. Calls and folds never carry a made size (`sizingBp`
is 0), so their made-side bucket is always `unknown`.

## Helpers

```python
from fpdb_3_legacy.sizing_buckets import (
    DEFAULT_BUCKETS, bucket_counts, bucket_response_stats, bucket_case_expression,
)

# A histogram over a filtered population: every size counted once,
# "unknown" last.
histogram = bucket_counts(sizes, DEFAULT_BUCKETS)

# Frequency of a yes/no response per bucket, for popups:
# "vs 66-80% c-bet: folds 40%, calls 35%, raises 25%" is three of these.
stats = bucket_response_stats(
    (row["facingSizingBp"], row["actionType"] == "folds") for row in rows
)
for stat in stats:
    print(stat.bucket, stat.chances, stat.frequency_bp)

# The SQL CASE expression for GROUP BY histograms straight in the database,
# guarded to the known sizing columns:
expression = bucket_case_expression("sizingBp")
sql = f"SELECT {expression} AS bucket, count(*) FROM HandsActions GROUP BY bucket"
```

The SQL expression mirrors `BucketConfig.bucket_of` exactly (a stored 0 is
`unknown` there too), so a Python-side histogram and a database-side
`GROUP BY` over the same rows agree. `bucket_case_expression` refuses any
column outside `SIZING_SOURCE_COLUMNS` — the analyser reads SQL assembled
from parts as an injection site, and refusing arbitrary identifiers is the
cheap half of that defence.

## HUD compatibility

The average-sizing stats (`FBet`, `TBet`, `RBet`, …) keep reading the raw
`val_*_bet_made_bp` / `val_*_raise_made_bp` totals in `HandsPlayers` and
`HudCache`; nothing writes a bucket anywhere. A histogram and the averages
are two views of the same rows, and `tests/test_sizing_buckets.py` pins both
together: the ten pinned sizes of the corpus scenario `17_bet_sizing` fall
one per bucket, made side and faced side, while the raw `sizingBp` values
keep equalling the aggregate columns the HUD averages.

## Tests

`tests/test_sizing_buckets.py` (26 tests) covers: the bucket vocabulary and
its invariants (one more label than bounds, positive bounds, `unknown` for
zero), custom tables, the preflop open-in-bb scale, the golden corpus pins,
histograms over filtered populations, per-bucket response frequencies, the
raise/all-in and multiway decisions of the other scenarios, and the HUD's
average-sizing query staying sum/count over the same bp columns.
