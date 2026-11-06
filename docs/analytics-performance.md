# Analytics performance: indexes, aggregate cache, profiling, benchmarks (#304)

The analytics layers add real work to a real database: a "player × position ×
situation" breakdown over a million hands is a scan of the decision stream, and
a popup that recomputes it on every hand is a scan per hand. This page records
what makes those queries usable, why each piece is there, and how to check it
on your own data.

Three mechanisms, each answering a different question:

| Question | Mechanism |
| --- | --- |
| Is the query plan reasonable? | the analytics indexes + `tools/explain_analytics_query.py` |
| Must it rescan everything every time? | the incremental aggregate cache |
| Is a change a regression? | the benchmark generator + harness |

## 1. Index strategy

`fpdb_3_legacy/sql_indexes.py` carries the analytics indexes; every connection
installs them best-effort through the feature migrations
(`Database.ensure_feature_tables`), so an existing database gains them without
a rebuild.

They are chosen by query shape, not by column:

| Index | Table | Serves |
| --- | --- | --- |
| `handactions_hand_idx` | HandsActions | the situation join key and the watermark range scan |
| `handactions_player_idx` | HandsActions | a player-filtered scan |
| `handactions_street_position_idx` | HandsActions | street × position groupings |
| `handactions_action_street_idx` | HandsActions | action-taken filters with a street |
| `handactions_sizing_idx` | HandsActions | sizing histograms and sizing ranges |
| `handssituations_hand_idx` | HandsSituations | the join back to the action row |
| `handssituations_player_idx` | HandsSituations | player-filtered situations |
| `handssituations_street_response_idx` | HandsSituations | street × response (fold-to-c-bet and friends) |
| `handssituations_pot_role_idx` | HandsSituations | pot-type and role filters |
| `handssituations_aggressor_idx` | HandsSituations | "as the preflop aggressor" |
| `handsplayers_hand_player_idx` | HandsPlayers | the profit/EV join |
| `hands_start_time_idx` | Hands | date filters |
| `hands_gametype_time_idx` | Hands | game type + date |

Board texture keeps the two indexes #295 already added (`boardfeatures_hand_idx`,
`boardfeatures_texture_idx`). Deliberately **not** indexed are the
low-cardinality words that only ever appear inside a full fact scan
(`stackBucket`, `pairing`, `connectivity`, …): a planner does not choose them,
and the write cost buys nothing. That is the issue's "texture/sizing only when
justified by real plans" taken literally -- `tools/explain_analytics_query.py`
is how a plan is checked before another index is added.

SQLite confirms the choices on the golden corpus: a fold-to-flop-c-bet query
plans as `SEARCH SI USING INDEX handssituations_street_response_idx` and
`SEARCH A USING COVERING INDEX handactions_hand_idx`.

## 2. Aggregate cache

`fpdb_3_legacy/analytics_cache.py` stores the counters behind an additive
metric in `AnalyticsAggregates`, one row per (query fingerprint, group), and
keeps them current without a rebuild.

- **Cacheable:** `opportunities`, `action_count`, `frequency` (and the named
  frequencies), `total_profit`, `all_in_ev`, and the per-opportunity variants.
- **Not cached:** the `average_*` metrics. An average cannot be combined from
  group means, and a silent wrong number is worse than a slow one, so they
  bypass the cache and run directly.

The query fingerprint is a hash of the metric, the sorted filters, the
numerator and the grouping, so two spellings of the same question share an
entry and two different questions never collide. Limits and offsets do not
change the fingerprint (the cache stores the whole result; paging is the
caller's).

### Staying current

Each cached query records the highest `Hands.id` it has seen in
`AnalyticsMeta` (the lifecycle table from #305). A refresh re-runs the query
with `hand_id_from = watermark + 1` and **adds** the delta to the stored
counters:

```
import 1 000 hands  →  scan of 1 000 hands, not of the database
```

That is the "no full rebuild after every import" requirement, and it is why
the per-opportunity metrics store the raw total and divide on read: the stored
sum is what makes the addition correct.

### Invalidation

| Event | What happens |
| --- | --- |
| New hands imported | the next read scans the delta and advances the watermark |
| Hands deleted or reimported | call `invalidate_aggregates` (ids can move or be reused; the watermark cannot see it) |
| Player aliases change | call `invalidate_aggregates` (the player dimension changed) |
| `ANALYTICS_CACHE_VERSION` bumped | dropped and rebuilt on the next read |
| A derived subsystem (#305) is stale | dropped and rebuilt on the next read |

`tools/analytics_cache.py --stats` shows the version, the cached row count and
each query's watermark; `--invalidate "reason"` drops everything.

## 3. Query planner tooling

`fpdb_3_legacy/analytics_profiling.py` compiles a query, runs the backend's
EXPLAIN, times the statement and counts the rows:

- **SQLite:** `EXPLAIN QUERY PLAN`, reported as index use or a table scan.
- **PostgreSQL:** `EXPLAIN (ANALYZE, BUFFERS)`, reported with actual rows,
  row-estimate error and blocks read.
- **MySQL:** a plain `EXPLAIN`.

Nothing is written: `EXPLAIN ANALYZE` executes the statement, so every profile
runs inside a transaction that is rolled back.

```
python tools/explain_analytics_query.py --all --plans
python tools/explain_analytics_query.py --metric fold_frequency \
    --filter street=flop --filter situation=facing_cbet --group-by position
```

Findings worth acting on are flagged: a sequential scan over a big table, a
row estimate off by more than 10×, blocks read from disk, and (on SQLite) a
filter that fell back to a table scan.

The existing HUD explain tool (`tools/explain_hud_queries.py`) is unchanged;
this one covers the analytics engine's statements.

## 4. Benchmarks

`fpdb_3_legacy/analytics_benchmark.py` makes the dataset and times the shapes
the issue names.

`synthesize_hands` clones the richest hand in the database -- its players,
actions, boards and situations -- into as many hands as asked. The dataset has
the joins and the per-hand cardinality of real data, scales to whatever the
machine can hold, and is **reproducible**: every clone is derived from the
same source row, so two runs at the same size have the same shape. The HUD
cache and summary tables are deliberately not cloned (their unique keys are
per hand and no analytics query reads them).

```
python tools/benchmark_analytics.py --generate 100000 --repeats 5
```

`--generate` writes to the configured database, so it is opt-in and off by
default. Without it the harness times the query shapes against the database as
it stands.

| Benchmark | Query shape | p95 target |
| --- | --- | --- |
| `filtered_frequency` | fold frequency, street + situation | 50 ms |
| `grouped_positional` | preflop frequency grouped by position and response | 75 ms |
| `sizing_histogram` | average sizing by bucket | 75 ms |
| `texture_breakdown` | flop opportunities by suit structure | 75 ms |
| `profit_by_position` | total profit grouped by position | 100 ms |

The targets are goals recorded here so a regression is a number rather than a
feeling; the CLI flags a miss. On a development database of a few thousand
cloned hands every shape is well inside them.

## Where this goes

- **#299 / #298** drive popups from definitions; the cache is what keeps a
  popup's per-hand query cheap.
- **#303** renders drill-down; the profiling tool is how a slow panel is
  diagnosed.
- **#307** adds populations; their queries share the same cache and indexes.
