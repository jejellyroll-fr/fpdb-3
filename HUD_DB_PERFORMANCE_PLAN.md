# HUD database performance — done, and what is left

Status: 2026-08-01. Branch `fix/db-vpn-reconnect`.
Open item: **run `tools/explain_hud_queries.py` against the real PostgreSQL
database.** Everything else below is landed and measured.

## Why round trips, not query time

The HUD reads its database on the Qt thread that repaints it, once per open
table per hand dealt. When the database is remote — the case this work started
from, a home PostgreSQL reached over a VPN — every statement costs one network
latency whatever the server does with it. A query that runs in 200µs locally
still costs 40ms from a hotel. So the number that decides how the HUD feels is
how many statements it sends, which no CPU-time benchmark reports.

`fpdb_3_legacy/db_profile.py` counts them and attributes each one to the work
that asked for it. Off unless `FPDB_DB_PROFILE=1`.

```bash
FPDB_DB_PROFILE=1 fpdb                                    # profile a real session
python tools/measure_hud_round_trips.py --tables 12       # reproduce the numbers below
```

## What landed

Measured with `tools/measure_hud_round_trips.py`, twelve tables at one stake,
steady state (the first batch pays cache misses and costs more):

| | statements per hand dealt | at 40ms RTT |
|---|---:|---:|
| before | 41 | 1.64s |
| after read caches (`446defb8`) | 17 | 0.68s |
| after batching (`3a14d517`) | **7** | **0.28s** |

Three statements dominated, each issued once per open table per hand:

- `get_hand_1day_ago` — a 24-hour boundary hand id that moves once a day. Now
  re-read at most every five minutes. It is a sliding boundary, so it is
  always a little stale by construction.
- `get_gameinfo_from_hid` — a hand's gametype, settled when the hand is written
  and never changed. Now cached by hand id. A **miss** is deliberately not
  cached: it means the hand is not committed yet, and caching it would keep
  denying the hand after the import lands.
- `get_stats_from_hand_aggregated` — the one doing real work. Now answered for
  every refreshing table in a single query (`get_stats_from_hands`).

Both caches are dropped by `resetCache`, which `recreate_tables` goes through:
that restarts hand ids from 1, so an entry kept across it would be served for a
different hand.

The batched query is the per-hand one **rewritten**, not a second copy — the
aggregate is 300 lines of stat columns and two copies would drift into the HUD
reporting different numbers depending on which path served a table. Each
rewrite is checked; any that no longer applies drops back to asking per hand.
`tests/test_hud_stats_batching.py` compares the two paths stat by stat over the
imported corpus.

## Open: run EXPLAIN against the real database

Counting round trips says nothing about what each one costs once it arrives.
Only a database with real volume and real planner statistics can say that, so
this has to run against the PostgreSQL instance the HUD actually uses.

```bash
python tools/explain_hud_queries.py --plans
```

It runs `EXPLAIN (ANALYZE, BUFFERS)` over the HUD's statements with parameters
taken from real rows, inside a transaction it rolls back, and flags:

- sequential scans over `HudCache`, `HandsPlayers`, `Hands`, `Players`
- row estimates off by more than 10x — what makes the planner choose a nested
  loop over a hash join and lose an order of magnitude
- blocks read from disk rather than served from cache

### The hypothesis to test first

The aggregate reaches `HudCache` like this:

```sql
INNER JOIN HudCache hc ON (hc.playerId = hp.playerId)
...
AND hc.gametypeId+0 in (SELECT ...)
```

and the compound index is:

```sql
CREATE UNIQUE INDEX HudCache_Compound_idx
    ON HudCache(gametypeId, playerId, seats, position, tourneyTypeId, styleKey)
```

Two things follow. The join is on `playerId`, which is not the leading column,
so the compound index cannot serve it and the join falls back to the plain
`HudCache(playerId)` index. And `gametypeId+0` is an old MySQL idiom for
*discouraging* the optimiser from using an index — on PostgreSQL it buys
nothing and stops any index on `gametypeId` being used at all, turning what
could be an index condition into a filter applied after the fact.

**Do not remove the `+0` blind.** It may have earned its place on MySQL, and
how much it costs depends entirely on how large `HudCache` has grown. Decide
from the plan:

- If `HudCache` is scanned sequentially, or the filter on `gametypeId` discards
  most of what the join produced, dropping `+0` on the PostgreSQL variant of
  the query is the first thing to try. `sql_queries_hud_aggregated_stats.py`
  can branch on `db_server`, as several other queries already do.
- If the plan already uses `HudCache(playerId)` and discards little, `+0` is
  not the problem and the next candidate is an index leading with `playerId`
  and covering `styleKey`/`seats`.
- If row estimates are far out, `ANALYZE HudCache` (or raising its statistics
  target) may be all that is needed.

Re-run `tools/measure_hud_round_trips.py` after any change: it is the same
harness that produced the table above.

## Not pursued

- **Moving the HUD's reads off the Qt thread.** It would mean splitting
  `read_stdin`, `_update_existing_hud`, `_refresh_secondary_hud` and
  `_create_new_hud` into fetch and apply phases, on the hottest path in the
  HUD, with no way to exercise it against a live client. The circuit breaker in
  `HUD_main` (`0ac7eb58`) removes the freeze this was meant to address without
  that risk.
- **A local staging database that syncs to the remote one.** The write path
  already has a durable queue — the hand-history files themselves — so a
  staging database would duplicate it. The read path cannot be fixed by a
  cache: serving an unknown villain offline needs all of `HudCache`, which is a
  replica, not a cache, and a replica while you are also writing locally is a
  merge problem on integer surrogate keys. Running PostgreSQL locally and
  replicating *to* the remote machine is the better shape for the travelling
  case.
- **A global `statement_timeout`.** It would abort bulk imports, `VACUUM` and
  index rebuilds. TCP keepalives (`a1fca458`, `f9c74a3d`) address the failure
  mode this was proposed for.
