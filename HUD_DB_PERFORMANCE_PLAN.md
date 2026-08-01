# HUD database performance — done, and what is left

Status: 2026-08-01. Branch `fix/db-vpn-reconnect`.
Open item: **resolve the aggregate's gametype set in the application** — see
"What EXPLAIN actually said" below, which corrects the hypothesis this document
first carried.

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

## What EXPLAIN actually said

Run locally against PostgreSQL 16 in a container, with `HudCache` grown to
1.07M rows / 1.5GB and each seated player carrying ~365 rows, which is the size
at which the question stops being hypothetical. See "Reproducing the fixture"
below.

**The hypothesis this document first carried was wrong.** It said the aggregate's
`hc.gametypeId+0` — an old MySQL idiom for discouraging index use — was
stopping PostgreSQL using an index, and that removing it was the thing to try.
Measured, that changes nothing:

| variant | median | rows discarded per player |
|---|---:|---:|
| current (`gametypeId+0`, subquery) | 1.42ms | 378 |
| without `+0` | 1.09ms | 378 |
| without `+0`, plus index `(playerId, gametypeId)` | 1.06ms | 378 |
| with `+0`, plus index `(playerId, gametypeId)` | 1.03ms | 378 |

`Rows Removed by Filter: 378` is identical in all four. There is no sequential
scan either: the join already uses `hudcache_playerid_idx`. The `+0` is a red
herring on PostgreSQL — **do not spend a risky change on it.**

The real blocker is that the "gametypes similar to this one" set is an
uncorrelatable subquery, so PostgreSQL evaluates it into a hashed SubPlan and
applies it as a **filter after fetching each row from the heap**. No index on
`gametypeId`, compound or otherwise, can be used for something the planner only
knows at run time.

That set depends only on the gametype and the blind multiplier, so the
application can resolve it once and pass the ids as an array. Then it becomes
an index condition:

```
Index Cond: ((playerid = p.id) AND (gametypeid = ANY ('{3,4,7,...,60}'::smallint[])))
```

| | median | HudCache buffers | rows discarded |
|---|---:|---:|---:|
| current | 1.07ms | 2414 | 378 |
| gametype set passed as an array | 0.78ms | **502** | **0** |

4.8x less of `HudCache` touched, nothing fetched only to be thrown away. And it
uses the **existing** `HudCache_Compound_idx` — no new index needed, because
with the gametype ids known the leading column is finally usable.

### What to do with that

- Resolve the set in `database_hud_stats`, cache it per
  `(gametypeId, agg_bb_mult)` — it changes only when a new gametype appears —
  and pass it as an array. Both the per-hand and the batched path go through
  the same query, so this is one change.
- Keep it PostgreSQL-shaped: `sql_queries_hud_aggregated_stats.py` can branch on
  `db_server` as other queries already do, leaving MySQL's `+0` alone.
- `tests/test_hud_stats_batching.py` already compares stat dicts between two
  query paths; the same harness answers whether this one is equivalent.

### Keep the magnitude in perspective

0.3ms per query on a warm cache, and after batching there is now one aggregate
per hand rather than twelve — so this is worth far less than the round-trip
work above, and nothing like it on a fast local link. It matters where I/O
does: a database larger than RAM, or a cold cache, where 4.8x fewer buffers is
4.8x less to read. Confirm on the real database before deciding it is worth the
change:

```bash
python tools/explain_hud_queries.py --plans
```

Re-run `tools/measure_hud_round_trips.py` after any change: it is the same
harness that produced the table above.

## Reproducing the fixture

```bash
docker run -d --name fpdb-explain -e POSTGRES_PASSWORD=fpdb -e POSTGRES_USER=fpdb \
    -e POSTGRES_DB=fpdb -p 55432:5432 postgres:16
```

Point a config at `127.0.0.1:55432` with `db-server=postgresql` / `db-backend=3`,
run `Database.recreate_tables()`, bulk-import
`regression-test-files/cash/Stars/Flop`, then grow the cache — a plan over the
955 rows the import produces says only that PostgreSQL prefers a sequential
scan on a tiny table, which is true and useless:

```sql
-- 40k opponents with ~25 cache rows each, cloned from imported rows so every
-- NOT NULL column and foreign key is satisfied without enumerating 200 columns
INSERT INTO Players (name, siteId, hero)
SELECT 'synth_' || g, 1, FALSE FROM generate_series(1, 40000) g;

INSERT INTO HudCache (<every column except id>)
SELECT <playerid := p.id, gametypeid := gt.id, rest from src>
FROM (SELECT * FROM HudCache ORDER BY id LIMIT 25) src
CROSS JOIN LATERAL (SELECT id FROM Players WHERE name LIKE 'synth_%' ORDER BY id LIMIT 40000) p
CROSS JOIN LATERAL (SELECT id FROM Gametypes ORDER BY random() LIMIT 1) gt;

-- and give the players who are actually seated a real history, which is what
-- makes the gametype filter discard work rather than be free
INSERT INTO HudCache (playerid, gametypeid, seats, position, tourneytypeid,
                      stylekey, n, street0vpichance, street0vpi,
                      street0aggrchance, street0aggr)
SELECT hp.playerid, gt.id, s.seats, pos.p, NULL, '0000000', 50, 50, 20, 50, 15
FROM (SELECT DISTINCT playerid FROM HandsPlayers) hp
CROSS JOIN (SELECT id FROM Gametypes ORDER BY id LIMIT 20) gt
CROSS JOIN (SELECT unnest(ARRAY[6,9,10]) AS seats) s
CROSS JOIN (SELECT unnest(ARRAY['B','S','D','C','M','E']) AS p) pos;

ANALYZE HudCache;
```

`TourneyTypes` is empty in a cash-only fixture, so `tourneytypeid` must be NULL
or the foreign key rejects the insert.

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
