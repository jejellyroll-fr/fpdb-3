# #680 — Live HUD freezes at high table counts: investigation kit and first remediations

Status: instrumentation + benchmark harness + three measured remediations landed.
The PokerStars-side reproduction (P0 checklist below) still needs the reporter's
machine; everything else is runnable from this branch.

## What this branch delivers

### 1. Latency instrumentation — `fpdb_3_legacy/latency_profile.py`

Off by default. Enable in the HUD / auto-import process with:

```
FPDB_LATENCY_PROFILE=1                 # record metrics
FPDB_LATENCY_REPORT=C:\logs\hud-latency.json   # JSON snapshot written at exit and on demand
FPDB_LATENCY_LOG_INTERVAL=60           # text report to the log every N seconds when metrics moved
```

Every metric is reported as **count / mean / p50 / p95 / p99 / max** (durations in
seconds in the JSON, ms in the text report) — averages hide exactly the
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

### 2. Benchmark harness — `tools/benchmark_hud_live.py`

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

* **R1 — grouped HudCache flush** (`database_caches.storeHudCache`): one
  `SELECT ... IN (<tuples>)` per cache family (ring / tourney) plus one batched
  `UPDATE` and one batched `INSERT`, instead of a `SELECT` + `UPDATE` per cache
  entry. Accumulation semantics unchanged (`update_hudcache` still adds the
  buffered line; the ring/tour split with `tourneyTypeId IS NULL` is preserved,
  and a falsy id in the key — `None` or `0` — maps to the ring family).
  Measured on a 30-file Stars corpus with round-trip profiling: **155 individual
  `select_hudcache_ring` + 29 `insert_hudcache` → 29 `select_hudcache_ring_bulk`
  + 29 `insert_hudcache`**. On a LAN database each removed statement is one
  network round trip per player per table per imported file.
* **R2 — MySQL session bounds on the HUD worker** (`HudReadWorker._configure_session`):
  the worker connection now sets `max_execution_time = 10000` (statement
  timeout) and `innodb_lock_wait_timeout = 2` (lock wait), the equivalents of
  the PostgreSQL `statement_timeout` / `lock_timeout` that were already applied.
  Previously a slow or lock-blocked read on a remote MySQL server could stall
  the serial worker queue indefinitely.
* **R3 — coalescing of superseded HUD batches** (`HudReadWorker.submit`): a new
  batch arriving while another batch is still queued is folded into it (union of
  hand ids and table contexts, highest sequence) instead of being queued behind
  it. At six tables a burst of new hands used to cost one full database read per
  hand, each superseding the last; the GUI already ignores snapshots older than
  the last applied sequence, so only the database work is saved, never the
  displayed result. Fast-Fold requests keep their existing per-table supersede
  logic and are untouched.

### 4. Tests

* `tests/test_latency_profile.py` — percentile math, counters, scopes, JSON
  report, inert-when-off, reservoir cap.
* `tests/test_hud_batch_coalescing.py` — merge semantics, queue behaviour,
  drain resolves to the merged request.
* `tests/test_store_hud_cache_bulk_writes.py` — flush insert/update
  accumulation, ring-vs-tour rows, falsy `tourneyTypeId` handling, statement
  count per flush, latency counters.
* `tests/test_hud_worker_session_timeouts.py` — PG unchanged, MySQL bounded,
  SQLite untouched.
* `tests/test_benchmark_hud_live.py` (perf) — smoke: the harness reports
  percentiles and round trips.

## Local benchmark results (this branch, SQLite file, 40-file Stars corpus = 113 hands / 37 tables)

Full data: `docs/bench-680-sample.json`, log: `docs/bench-680-sample.log`.

| tables | range | import concurrent | batch wall p50 | p95 | max | round trips / 10 rounds |
|---|---|---|---|---|---|---|
| 1 | A | off | 0.9 ms | 13.4 ms | 23.6 ms | 380 |
| 4 | A | off | 1.5 ms | 3.3 ms | 4.6 ms | 590 |
| 8 | A | off | 2.3 ms | 4.1 ms | 5.5 ms | 870 |
| 1 | A | on | 2.8 ms | 16.6 ms | 19.4 ms | 443 |
| 8 | A | on | 7.8 ms | 20.1 ms | 20.1 ms | 955 |

Reading:

* **Round trips scale linearly with table count** (~11 statements per table per
  batch round: 38 → 87 per round from 1 to 8 tables). On a LAN database each
  statement costs one network latency, so this is the term that grows with the
  table count even when every query is fast. This is the strongest candidate for
  the reported scaling; R1 removes the per-entry part of it on the import side,
  R3 removes superseded whole batches on the HUD side.
* **Import concurrency multiplies the tail even on local SQLite**: with the
  writer active, batch p50 goes 0.9 → 7.8 ms and p95 reaches ~20 ms at 8 tables,
  and `db_txn_total` p99 reaches ~25 ms — the single-writer lock contention is
  visible locally and will be worse over a network. This matches "HUD +
  auto-import together are unplayable, each alone is fine".
* Session (`S`) vs all-hands (`A`) made no difference on this small corpus; on a
  real long history `hud_session_rows` and the per-hand session path are the
  things to watch (the issue's session-range hypothesis).

Caveat recorded as the issue requires: a local SQLite run changes both backend
and location, so these numbers motivate, but do not by themselves prove, the
remote-database behaviour.

## P0 reproduction checklist for the reporter (same six-table workload, one change at a time)

1. HUD off, auto-import on. 2. HUD on, auto-import off. 3. Both on.
4. Repeat against a local SQLite database and compare (record that this changes
   backend *and* location).
5. While a freeze happens, note whether PokerStars' clock/animations keep moving
   and whether keyboard shortcuts still work — this separates a general client
   slowdown from overlay/input handling.
6. With `FPDB_LATENCY_PROFILE=1 FPDB_LATENCY_REPORT=... FPDB_LATENCY_LOG_INTERVAL=30`
   on the HUD process (and `FPDB_DB_PROFILE=1` for round trips), attach the JSON
   report after a six-table session: the dominant delay shows up as
   `hud_queue_wait` (worker saturated), `hud_query_execute`/`hud_query_fetch`
   (database execution/fetch or network wait), `hud_python_aggregate` /
   `hud_session_rows` (session path), `hud_snapshot_apply` (Qt/render side), or
   `db_txn_total`/`db_commit` on the import side (writer contention).

## Query-plan review (P1)

Use the existing `tools/explain_hud_queries.py` against the production PostgreSQL
(or `EXPLAIN (ANALYZE, BUFFERS)` on MySQL) at realistic database size for
`get_stats_from_hand_aggregated` and `get_stats_from_hand_session`. Watch for:
sequential scans over HudCache (the compound index cannot serve the join —
already flagged by the tool), rows scanned vs estimated, and the
`playerId + 0` / `gametypeId + 0` expressions in
`sql_queries_hud_aggregated_stats.py` / `sql_queries_hud_session_stats.py`, which
force the planner to evaluate the expression per row and can defeat index
selection on some backends/statistics. Do not change indexes or narrow the
queries before the plans and the latency report say which query is actually
slow.

## Backend guidance (provisional, unchanged from the issue)

For multi-tabling with the database on a separate server, PostgreSQL remains
the provisional recommendation (concurrent server workload; the HUD reader
connection already has statement/lock timeouts, and now MySQL has equivalents —
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
