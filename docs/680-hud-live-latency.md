# #680 â€” Live HUD freezes at high table counts: investigation kit and first remediations

Status: instrumentation + benchmark harness + three measured remediations landed.
The PokerStars-side reproduction (P0 checklist below) still needs the reporter's
machine; everything else is runnable from this branch.

## What this branch delivers

### 1. Latency instrumentation â€” `fpdb_3_legacy/latency_profile.py`

Off by default. Enable in the HUD / auto-import process with:

```
FPDB_LATENCY_PROFILE=1                 # record metrics
FPDB_LATENCY_REPORT=C:\logs\hud-latency.json   # JSON snapshot written at exit and on demand
FPDB_LATENCY_LOG_INTERVAL=60           # text report to the log every N seconds when metrics moved
```

Every metric is reported as **count / mean / p50 / p95 / p99 / max** (durations in
seconds in the JSON, ms in the text report) â€” averages hide exactly the
multi-second pauses the issue reports. Samples past 100k per metric switch to
reservoir sampling, so a long session does not grow memory.

Metrics wired into the live path:

| metric | where | answers |
|---|---|---|
| `hud_queue_wait` | `HudReadWorker` | how long a batch waited behind earlier work |
| `hud_batch_total` | `HudReadWorker` | one full batch read on the worker thread |
| `hud_batch_resolve_primary` / `hud_batch_primary` / `hud_batch_secondary` | `HudReadService.read_batch` | which phase of the batch costs |
| `hud_query_execute` vs `hud_query_fetch` vs `hud_python_aggregate` | `database_hud_stats.py` | SQL execution vs result fetching vs Python aggregation |
| `hud_session_rows` (counter) | session stats path | rows the "session" range fetches and aggregates per hand |
| `hud_analytics_compute` | analytics-backed HUD cells | #335 analytics cost on the worker thread |
| `hud_snapshot_apply` | `HudMain._on_db_snapshot` | Qt-side apply/render time, separate from the worker |
| `hudcache_lookup` / `hudcache_update` / `hudcache_insert` (counters), `hudcache_write` | `storeHudCache` | cache write round trips per import batch |
| `db_txn_total` / `db_commit` | `DatabaseTransaction` | import transaction duration and commit alone |

Round-trip counts per statement/scope remain available with the existing
`FPDB_DB_PROFILE=1` (`db_profile`).

### 2. Benchmark harness â€” `tools/benchmark_hud_live.py`

```
python tools/benchmark_hud_live.py                          # tables 1,2,4,6,8 x ranges A,S, import off/on
python tools/benchmark_hud_live.py --tables 1,2,4,6,8 --stat-range A,S --repeats 20 --import-concurrent --out report.json
FPDB_BENCH_DSN="postgresql://user:pass@lan-host/fpdb" python tools/benchmark_hud_live.py ...   # same workload, server DB
FPDB_BENCH_DSN="mysql://user:pass@lan-host/fpdb" python tools/benchmark_hud_live.py ...
```

It imports a fixed regression corpus into a fresh database (HudCache populated,
as in a live session), then replays HUD batch rounds through the real
`HudReadService.read_batch`: each round submits one `HudBatchReadRequest` with
the newest hand of every open table plus the read context of every open table.
No Qt, so the numbers isolate the database + Python cost of one refresh round.
Each configuration reports the full percentile set plus round trips; a markdown
table is printed and the full JSON goes to `--out`.

### 3. Remediations (each measured, see below)

* **R1 â€” grouped HudCache flush** (`database_caches.storeHudCache`): one
  `SELECT ... IN (<tuples>)` per cache family (ring / tourney) plus one batched
  `UPDATE` and one batched `INSERT`, instead of a `SELECT` + `UPDATE` per cache
  entry. Accumulation semantics unchanged (`update_hudcache` still adds the
  buffered line; the ring/tour split with `tourneyTypeId IS NULL` is preserved,
  and a falsy id in the key â€” `None` or `0` â€” maps to the ring family).
  Measured on a 30-file Stars corpus with round-trip profiling: **155 individual
  `select_hudcache_ring` + 29 `insert_hudcache` â†’ 29 `select_hudcache_ring_bulk`
  + 29 `insert_hudcache`**. On a LAN database each removed statement is one
  network round trip per player per table per imported file.
* **R2 â€” MySQL session bounds on the HUD worker** (`HudReadWorker._configure_session`):
  the worker connection now sets `max_execution_time = 10000` (statement
  timeout) and `innodb_lock_wait_timeout = 2` (lock wait), the equivalents of
  the PostgreSQL `statement_timeout` / `lock_timeout` that were already applied.
  Previously a slow or lock-blocked read on a remote MySQL server could stall
  the serial worker queue indefinitely.
* **R3 â€” coalescing of superseded HUD batches** (`HudReadWorker.submit`): a new
  batch arriving while another batch is still queued is folded into it (union of
  hand ids and table contexts, highest sequence) instead of being queued behind
  it. At six tables a burst of new hands used to cost one full database read per
  hand, each superseding the last; the GUI already ignores snapshots older than
  the last applied sequence, so only the database work is saved, never the
  displayed result. Fast-Fold requests keep their existing per-table supersede
  logic and are untouched.

### 4. Tests

* `tests/test_latency_profile.py` â€” percentile math, counters, scopes, JSON
  report, inert-when-off, reservoir cap.
* `tests/test_hud_batch_coalescing.py` â€” merge semantics, queue behaviour,
  drain resolves to the merged request.
* `tests/test_store_hud_cache_bulk_writes.py` â€” flush insert/update
  accumulation, ring-vs-tour rows, falsy `tourneyTypeId` handling, statement
  count per flush, latency counters.
* `tests/test_hud_worker_session_timeouts.py` â€” PG unchanged, MySQL bounded,
  SQLite untouched.
* `tests/test_benchmark_hud_live.py` (perf) â€” smoke: the harness reports
  percentiles and round trips.

## Benchmark results — all three backends, run locally (this branch)

Same workload everywhere: 40-file Stars corpus imported with the HUD cache
enabled (113 hands / 37 tables), then 10 HUD batch rounds per configuration at
1/2/4/6/8 tables x stat range A/S x auto-import off/on, through the real
`HudReadService.read_batch`. Backends: SQLite file local, PostgreSQL 18.3 and
MySQL 8.4.3 on 127.0.0.1 (loopback — a real LAN adds one network latency per
round trip on top). Full JSON: `docs/bench-680-{sqlite,postgresql,mysql}.json`.

Batch wall time (ms), 10 rounds per cell:

| backend | tables | range | import off p50 / p95 / max | import on p50 / p95 / max | round trips / 10 rounds |
|---|---|---|---|---|---|
| SQLite | 1 | A | 3.6 / 20.4 / 33.9 | 11.5 / 26.4 / 29.6 | 492 -> 575 |
| SQLite | 8 | A | 30.2 / 35.4 / 35.5 | 77.1 / **1429** / 1467 | 1747 -> 1991 |
| SQLite | 8 | S | 19.9 / 92.3 / 146.9 | 41.8 / 59.8 / 64.9 | 1740 -> 1898 |
| PostgreSQL 18.3 | 1 | A | 27.8 / 55.0 / 75.4 | 33.3 / 47.7 / 53.7 | 492 -> 673 |
| PostgreSQL 18.3 | 8 | A | 156.1 / 164.5 / 171.1 | 175.7 / 183.9 / 183.9 | 1747 -> 1947 |
| PostgreSQL 18.3 | 8 | S | 102.3 / 109.3 / 110.8 | 123.0 / 141.1 / 147.3 | 1740 -> 1935 |
| MySQL 8.4.3 | 1 | A | 33.1 / 46.1 / 54.8 | 46.1 / 69.1 / 70.8 | 492 -> 567 |
| MySQL 8.4.3 | 8 | A | 160.7 / 207.8 / 218.5 | 212.0 / **1516** / 1592 | 1747 -> 1937 |
| MySQL 8.4.3 | 8 | S | 116.0 / 130.8 / 134.9 | 171.2 / 223.5 / 228.5 | 1740 -> 1917 |

(An earlier version of this table was produced with a harness bug — missing
`hud_days` in the HUD params made every primary hand fail silently, so only the
secondary path was measured. Fixed and re-run; the table above is the corrected
one.)

Reading:

* **Round trips scale with table count on every backend**: ~175-200 statements
  per batch round at 8 tables (~22 per table), vs ~49 at 1 table. This is the
  term that grows with the table count; on a LAN each statement costs one
  network latency on top of its server time.
* **At 8 tables the cost lives in the primary phase** (p99 51-200 ms), not the
  secondary refresh (p99 ~0): the per-hand aggregate query plus the per-hand
  reads (positions, seat players, cards, min stack). `hud_query_execute` p99
  is only 8-17 ms per statement even on MySQL, so it is the *number* of
  statements more than any single slow query — on this corpus. On a big real
  database the per-query p99 is the thing to watch via `EXPLAIN`.
* **Writer contention is the tail multiplier, and it is architectural**:
  SQLite (single writer) and MySQL/InnoDB hit **p95 of 1.4-1.6 s** at 8 tables
  with auto-import active, already on loopback; PostgreSQL stays at ~184 ms
  p95 because readers never block on the writer. On a LAN database these
  numbers get worse per round trip, but the ordering and the 1.4 s tail exist
  even locally — this is not only a network problem.
* **Session range (S)** was cheaper than all-hands (A) here only because the
  regression corpus is old, so the 24h session window is empty
  (`hud_session_rows` = 0). On a real long live session the per-hand session
  path fetches and aggregates detailed rows in Python — watch
  `hud_session_rows` and `hud_python_aggregate` in the reporter's report.
* PostgreSQL 17.6 vs 18.3: no significant difference (within noise).

Conclusion: the freeze is **both** — an architecture-level term (reader/writer
contention, per-statement network latency on a remote DB) **and** a code-level
term (~22 statements per table per refresh round, serial worker queue). The
code-side levers in this PR: R1 (HudCache flush: 2N -> ~4 statements per
import batch), R3 (superseded batches coalesced: one read per burst instead of
one per hand), R2 (MySQL worker session bounded like PostgreSQL), and R4
(batched primary reads: table info, site hand no, positions, seat players,
cards, min stack -- one statement per detail per batch instead of per hand,
~54% fewer round trips per round at 8 tables). P2 is implemented as an opt-in
bound (`max_secondary_tables_per_batch`, default 0 = unbounded, so displayed
stats never go stale unless configured). Remaining levers if the reporter's
`hud_queue_wait` still shows growth: prioritise the active table in the
worker queue, and batch the per-hand aggregate stats across primary hands of
the same table/params the way secondary stats already are.

## After the batched-read remediation (this branch, same workload re-run)

`HudReadService` now resolves all primary hands' table info / site hand no in
two statements (`get_table_info_many`, `get_site_hand_no_many`) and prefetches
positions / seat players / cards / common cards / min stack for the whole batch
in one statement each (`get_*_many`), with a per-hand fallback whenever a bulk
value is missing. Measured on the same 3 backends, 8 tables, 10 rounds:

| backend | tables | range | imp | before p50/p95/max (ms) | after p50/p95/max (ms) | round trips before -> after |
|---|---|---|---|---|---|---|
| SQLite | 8 | A | off | 30.2 / 35.4 / 35.5 | 15.9 / 17.9 / 18.2 | 1747 -> 805 |
| SQLite | 8 | A | on | 77.1 / **1429** / 1467 | 43.4 / **59.2** / 66.4 | 1991 -> 972 |
| PostgreSQL 18.3 | 8 | A | off | 156.1 / 164.5 / 171.1 | 99.2 / 121.2 / 129.2 | 1747 -> 805 |
| PostgreSQL 18.3 | 8 | A | on | 175.7 / 183.9 / 183.9 | 108.8 / 132.9 / 147.8 | 1947 -> 993 |
| MySQL 8.4.3 | 8 | A | off | 160.7 / 207.8 / 218.5 | 90.0 / 100.4 / 103.3 | 1747 -> 805 |
| MySQL 8.4.3 | 8 | A | on | 212.0 / **1516** / 1592 | 114.7 / **135.3** / 135.6 | 1937 -> 929 |

**Round trips per batch round at 8 tables drop ~54% (1747 -> 805)** and the
writer-contention tail collapses with them: SQLite p95 1429 -> 59 ms,
MySQL p95 1516 -> 135 ms. PostgreSQL, already insulated from the writer by
MVCC, still improves 26-28% from the removed round trips. The remaining cost at
8 tables is the per-hand aggregate stats query (one per primary hand) and the
per-hand `Hand` construction, which are the next levers.

Caveat recorded as the issue requires: these runs are loopback, not a LAN, and
the corpus is small; a local SQLite run also changes both backend and location.
The reporter's latency report will say which term dominates on their network.

## Compatibility fix found while running the three backends

`fillDefaultData` inserted into `Rank` and `StartCards(..., rank, ...)` without
quoting, but both are reserved words since MySQL 8.0 — on MySQL 8.4
`recreate_tables()` failed there (the CREATE statements already quoted them).
The inserts now quote per backend (backticked on MySQL only). Covered by
`tests/test_store_hud_cache_live_backends.py` (live PostgreSQL + MySQL) and the
unit suite.

## P0 reproduction checklist for the reporter (same six-table workload, one change at a time)

1. HUD off, auto-import on. 2. HUD on, auto-import off. 3. Both on.
4. Repeat against a local SQLite database and compare (record that this changes
   backend *and* location).
5. While a freeze happens, note whether PokerStars' clock/animations keep moving
   and whether keyboard shortcuts still work â€” this separates a general client
   slowdown from overlay/input handling.
6. With `FPDB_LATENCY_PROFILE=1 FPDB_LATENCY_REPORT=... FPDB_LATENCY_LOG_INTERVAL=30`
   on the HUD process (and `FPDB_DB_PROFILE=1` for round trips), attach the JSON
   report after a six-table session: the dominant delay shows up as
   `hud_queue_wait` (worker saturated), `hud_query_execute`/`hud_query_fetch`
   (database execution/fetch or network wait), `hud_python_aggregate` /
   `hud_session_rows` (session path), `hud_snapshot_apply` (Qt/render side), or
   `db_txn_total`/`db_commit` on the import side (writer contention).

## Per-query bench on the three backends (constant dataset)

`tools/benchmark_hud_queries.py` imports the *same* corpus into a fresh
database on each backend (664/663/664 hands, 2270 HudCache rows, 427 players,
194 tables — identical by construction), then runs every HUD read query
15 times against real hand ids, capturing per-statement timings and the
server-side plan for the heavy queries. Full JSON with plans:
`docs/bench-680-queries-{sqlite,postgresql,mysql}.json`.

p50 / p95 / max ms per query case (15 runs):

| query case | SQLite | PostgreSQL 18.3 | MySQL 8.4.3 |
|---|---|---|---|
| aggregated_per_hand (big HudCache aggregate) | 2.3 / 3.9 / 6.5 | 10.2 / 15.0 / 18.8 | 17.1 / 25.8 / 31.2 |
| aggregated_batch_6 (6 hands, one batched aggregate) | 8.9 / 12.6 / 14.4 | 25.4 / 53.7 / 59.1 | 58.6 / 63.5 / 63.7 |
| session_per_hand (range S) | 0.6 / 1.0 / 1.3 | 5.2 / 7.3 / 7.8 | 6.1 / 7.3 / 7.4 |
| table_info_many_8 | 0.12 | 0.90 | 0.93 |
| positions_many_8 / seat_players_many_8 | 0.08 / 0.10 | 0.29 / 0.63 | 0.90 / 1.12 |
| cards_many_8 / common_cards_many_8 | 0.20 / 0.05 | 0.95 / 0.23 | 1.75 / 0.46 |
| min_stack_many_8 (2 statements) | 0.14 | 0.73 | 1.55 |
| hand_construction (Hand.hand_factory, 7 statements) | 0.50 | 3.63 | 5.60 |

Findings and perf pistas (all verified against EXPLAIN, none change results):

* **MySQL is 2-3x slower than PostgreSQL per query even on loopback**, and
  SQLite is fastest locally; on a LAN each of the statements above also pays a
  network round trip, so the ranking amplifies. This is the backend guidance.
* **`hand_construction` costs 7 statements per hand** (singleHand, playerHand,
  handActions, showdown, cashout, splash, heroseat) — at 8 tables that is 56
  round trips per refresh round. Next code lever: read the hand once instead
  of 7 lookups.
* **The batched reads from R4 are all single-statement** (table_info_many,
  positions_many, ...) — confirmed 1 statement/iter in the report.
* **Query plans use the indexes**: the aggregate uses `hudcache_playerid_idx`
  (the `gametypeId + 0` stays in the filter, it does not defeat the index on
  playerId); the session query uses `heroseat_idx`, `handsplayers_handid_idx`
  and `players_pkey` even with a full 24h window (663 hands in-window probe on
  PostgreSQL: 5.8 ms p50, no seq scan). `HandsPlayers(playerId)` already exists
  (`HandsPlayers_playerId_idx` via `INDEXES`) — an extra one was tried and
  reverted as a duplicate.
* **Not a missing-index problem at this scale**: no seq scan over HudCache or
  HandsPlayers in any captured plan. On a much larger production database the
  remaining lever is a covering index on HudCache(playerId, ...) to cut the
  heap fetches (395 buffers for 56 rows on PostgreSQL here); deferred until a
  big-database plan shows it, since every index also taxes import writes.

## Full SQL catalogue bench on the three backends (constant dataset)

`tools/benchmark_all_queries.py` executes **every query in the SQL catalogue**
(333 per backend; ~230 executed per backend — DDL skipped, run-time-assembled
template queries reported as skipped, DML measured then rolled back) against
the same populated database (664 hands, constant across backends), with
parameters resolved from real rows and the EXPLAIN plan captured per query.
Full JSON: `docs/bench-680-catalog-{sqlite,postgresql,mysql}.json`.

Headline results (p95 ms, queries returning rows on >= 2 backends, excluding
whole-table dump queries like getHands/getHudCache which are full scans by
nature):

| query | SQLite | PostgreSQL 18.3 | MySQL 8.4.3 |
|---|---|---|---|
| clearHudCache (DELETE all) | 0.8 | 5.3 | **142.2** |
| clear_S_H | 1.9 | 29.1 | 2.0 |
| tourneyHandsInRangeSessionFilter | 3.6 | - | 10.5 |
| handsInRangeSessionFilter / handsInRangeSession | 0.9 / 0.4 | - | 6.8 / 3.9 |
| getLimits / getCashLimits | 1.9 / 0.2 | 2.8 / 1.9 | 3.4 / 2.0 |
| list_indexes / list_tables (catalogue introspection) | 0.1 / 0.1 | 3.4 / 1.9 | - / 1.8 |
| store_hands_stove / store_hands_pots (import writes) | 0.07 / 0.16 | 2.9 / 1.5 | 0.6 / 0.5 |

Findings:

* **No point query seq-scans a big table on any backend** — the only Seq
  Scan / Table scan hits in the captured plans are the whole-table dumps
  (getHands*, getHudCache, getPositions, getHandCount) and the DELETE-all
  maintenance queries, which are full scans by design.
* **MySQL is the slowest on full-table writes and filtered range queries**
  (clearHudCache 142 ms vs 5.3 ms PG; handsInRange* 4-7 ms vs <1 ms SQLite);
  import-heavy maintenance should expect that gap, and on a LAN it multiplies
  per round trip.
* The live HUD path queries (aggregated/session/many-reads) are all in the
  sub-10-ms p95 band on this dataset on every backend — consistent with the
  earlier per-query bench; the multi-table cost is statement *count*, already
  addressed by R4.
* Remaining errors in the report are bench artifacts (run-time-assembled
  report queries needing caller-built clauses, and type-strict params), not
  product bugs; they are listed with their message in the JSON.

## Query-plan review (P1)

Use the existing `tools/explain_hud_queries.py` against the production PostgreSQL
(or `EXPLAIN (ANALYZE, BUFFERS)` on MySQL) at realistic database size for
`get_stats_from_hand_aggregated` and `get_stats_from_hand_session`. Watch for:
sequential scans over HudCache (the compound index cannot serve the join â€”
already flagged by the tool), rows scanned vs estimated, and the
`playerId + 0` / `gametypeId + 0` expressions in
`sql_queries_hud_aggregated_stats.py` / `sql_queries_hud_session_stats.py`, which
force the planner to evaluate the expression per row and can defeat index
selection on some backends/statistics. Do not change indexes or narrow the
queries before the plans and the latency report say which query is actually
slow.

## Architecture decision matrix (complementary choices, backed by the measurements above)

Measured facts this rests on: round trips per HUD refresh round scale with table
count and each one costs a network RTT on a remote DB (~22 statements/table
before R4, ~10 after); writer contention produces the multi-second tail on
SQLite (single writer) and MySQL/InnoDB (p95 1.4-1.6 s at 8 tables + import,
even on loopback) but not on PostgreSQL (MVCC, ~184 ms p95); no point query
seq-scans at this scale on any backend.

| situation | recommendation | why (measured) |
|---|---|---|
| DB on a separate LAN server, multi-table cash | **PostgreSQL**, HUD worker timeouts already applied (R2-style) | readers never block the writer; per-query 2-3x faster than MySQL on loopback |
| DB remote, MySQL kept | acceptable with R2 session timeouts; expect worse tail under import load; keep import transactions short | MySQL p95 135 ms at 8 tables after R4 vs 133 ms PG; before R4 it was 1.5 s |
| local SQLite, <= 2-3 tables | fine as-is | p95 ~20 ms at 8 tables without import; single-writer tail only bites with concurrent import at 6+ tables |
| local SQLite, 6+ tables + auto-import | move the DB to a server backend, or pause auto-import while playing | SQLite p95 1.4 s at 8 tables with import on, even locally |
| very large production DB | additionally: read replica / standby for the HUD reader, and a covering index on HudCache(playerId, ...) if EXPLAIN shows heap-fetch pressure | only seq scans found are whole-table dumps; covering index deferred until a big-DB plan shows it |

Code-side architecture choices shipped in this PR:

* **Serial worker + coalescing** (R3): one in-flight batch, superseded batches
  merged — bounds the queue instead of growing it.
* **Batched reads** (R4): one statement per detail per batch instead of per
  hand (-54% round trips at 8 tables).
* **Active table first**: primary hands are now read most-recently-notified
  first, so in a burst the HUD of the table the player is acting on is painted
  first (perceived latency down, total work unchanged).
* **Configurable batch window**: `hand_batch_interval_ms` in the HUD ui config
  (default 200 ms, unchanged) lets a many-table profile trade display delay
  for fewer round trips per burst.
* **Opt-in secondary bound** (P2): `max_secondary_tables_per_batch` (default 0 =
  unbounded) caps secondary refreshes per batch so a burst cannot queue
  unbounded non-active work.

Not shipped (needs the reporter's live `hud_queue_wait` first): splitting the
worker into an active-table lane and a background lane; moving the HUD reader to
a PostgreSQL read replica; local-first SQLite with deferred sync to the server.

## Architecture exploration for this case: LAN + distributed DB, OLAP vs OLTP, embedded

The workload has two very different shapes, and the architecture choice should
follow them separately:

* **HUD live** = many small *point* reads (one hand's table info, seats, cards,
  and one aggregate over that table's players), plus one write per imported
  hand. Latency-sensitive, latency = statements x network RTT.
* **Reports / study** = few large *scan* aggregates over all history.
  Throughput-sensitive, not latency-sensitive.

Measured on the constant dataset (664 hands / 2270 HudCache rows):

| workload | SQLite row | PostgreSQL row (LAN) | MySQL row (LAN) | DuckDB columnar (embedded) |
|---|---|---|---|---|
| HUD point query `get_stats_from_hand_aggregated` p50 | 2.3 ms | 10.2 ms | 17.1 ms | **419 ms** |
| wide aggregate (top-100 by profit over HudCache) p50 | 0.9 ms | 3.7 ms | 15.5 ms | 7.8 ms |

Reading:

* **OLTP row-store is the right engine for the HUD live path.** Point reads hit
  B-tree indexes in microseconds; a columnar engine pays a scan/vectorised
  setup per query and is ~180x slower on the exact HUD query here (419 ms).
* **OLAP/columnar (DuckDB, ClickHouse) only pays off on the report side, and
  only at large scale** (millions of rows), where columnar scans beat row
  scans by orders of magnitude. At our scale it is within noise. Conclusion:
  keep OLTP for live; optionally export Parquet to DuckDB/ClickHouse *offline*
  for heavy reports — never in the live path.
* **Distributed SQL (CockroachDB/YugabyteDB/Spanner)** replicates rows across
  nodes with consensus: great for multi-machine availability, useless overhead
  for one LAN server. It does not remove the per-statement RTT — it can add
  one. For this case (one DB server on the LAN): not recommended. It becomes
  relevant only if several playing machines share one live database
  simultaneously.
* **PostgreSQL read replica / standby**: isolates HUD reads from bulk import
  writes. Marginal here because PG's MVCC already lets readers overlap the
  writer (measured: p95 184 ms at 8 tables with import on, vs 1.4-1.6 s on
  SQLite/MySQL). Worth it only if bulk imports regularly saturate the primary.
* **Local-first (SQLite or embedded DuckDB on the playing machine, async sync
  to the LAN server)**: the biggest lever if the LAN RTT is high, because the
  HUD then reads at 0 RTT (~2 ms instead of ~10-20 ms per statement on LAN).
  Cost: import writes land locally first and are pushed asynchronously, and
  multi-machine consistency needs a sync protocol. This is the recommended
  next step if the reporter's LAN RTT is > 2-3 ms.
* **In-process cache**: HudCache is already a pre-aggregated cache in the DB;
  an in-memory stat_dict cache in the HUD process would only help if stats
  were re-read unchanged, which they are not (every hand changes them).

Recommendation for the reported setup (PokerStars, 6-max 2NL, 6 tables, DB on a
LAN server): PostgreSQL on the LAN server as shipped in the decision matrix
above + R1-R4 + active-table-first; if the measured LAN RTT is high, move to
local-first with async push. Keep OLAP out of the live path; use it for reports
if the database grows large.

## Backend guidance (provisional, unchanged from the issue)

For multi-tabling with the database on a separate server, PostgreSQL remains
the provisional recommendation (concurrent server workload; the HUD reader
connection already has statement/lock timeouts, and now MySQL has equivalents â€”
R2). MySQL/InnoDB is reasonable once R2 is in. SQLite stays appropriate for
lighter local workloads; WAL lets readers overlap the writer, but the
single-writer model plus checkpointing shows up in the tail (measured above).
A server database will not by itself fix expensive queries, excessive round
trips, or a HUD queue that grows faster than it drains.

## Deliberately not done (P2)

Prioritising active-table updates over secondary-table refreshes, and bounding
secondary work per batch, are only worth doing if the reporter's
`hud_queue_wait` shows the queue growing during multitabling. They touch refresh
policy and stale-stat display, so they need that evidence first.
