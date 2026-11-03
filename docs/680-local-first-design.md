# #680 — Local-first design (HUD reads an embedded SQLite on the playing machine, async push to the LAN server)

Trigger: the reporter's `FPDB_LATENCY_PROFILE` report shows LAN RTT > ~2-3 ms.
Measured justification (same dataset, 8 tables, after R4): PostgreSQL over a
simulated 3 ms RTT costs **322-331 ms p50 per HUD refresh round** at 8 tables
(`tools/benchmark_hud_live.py --simulate-rtt-ms 3`, 413-617 round trips per 5
rounds), while the same workload on local SQLite costs **16-43 ms p50** — an 8-20x gap that grows
linearly with RTT and table count (each statement pays one RTT).

## Current flow vs local-first

```
TODAY:  PokerStars -> auto-import --write--> DB on LAN server --ZMQ hand id--> HUD --read--> LAN DB (1 RTT/statement)
LOCAL-FIRST: auto-import --write--> local SQLite (0 RTT) --mark--> outbox --async push--> LAN server (source of truth)
             HUD --read--> local SQLite (0 RTT)
```

The HUD process needs **no change**: it already reads whatever database the
config points at. Pointing the HUD's config at the local SQLite file is the
whole client-side change. The new part is the import side and the sync worker.

## Components

1. **Local database**: an embedded SQLite file on the playing machine, schema
   identical to today's (`recreate_tables`), written by the auto-import
   process exactly as now (same Importer, same transactions, same HudCache).
2. **Outbox** (`fpdb_sync_outbox`, created by `LocalFirstSync`): one row per
   locally imported hand — `local_hand_id, server_hand_id, pushed, pushed_at`.
   Written in the same transaction as the import, so a crash never loses a
   hand without a trace.
3. **`LocalFirstSync`** (`fpdb_3_legacy/local_first_sync.py`, POC shipped in
   this PR): daemon thread, polls the outbox every `poll_s`, pushes batches of
   `batch_size` hands in one server transaction. Idempotent: dedup on the
   server by the unique `(siteHandNo, gametypeId)` index on Hands; referentials
   deduped by their natural keys (Sites.name, Players.(name,siteId), Files.file,
   Gametypes.(siteId,type,base,...)). The server assigns hand ids; the mapping
   `local_hand_id -> server_hand_id` is stored in the outbox. Boolean columns
   are cast per server dialect (SQLite 0/1 -> PG boolean). Failures roll back
   the batch and retry on the next poll; the outbox persists across restarts.
4. **Referentials pushed first** (Sites, Players, Files, Gametypes, then
   TourneyTypes) so the server's foreign keys hold.

## Tables to sync (production list)

Referentials: Sites, Players, Gametypes, Files, TourneyTypes.
Facts per hand: Hands, HandsPlayers, HandsActions, HandsPots, HandsStove,
HandsShowdown, HandsCashout, Boards, plus tournament tables when MTTs are in
scope. Caches (HudCache, CardsCache, PositionsCache, Sessions, SessionsCache,
TourneysCache) are **recomputed server-side** from the pushed facts (the server
runs its own storeHudCache on ingest), never pushed — avoids counter-merge
conflicts.

## Conflict and consistency rules

* The server is the source of truth. A hand already there (same siteHandNo +
  gametypeId) is not re-inserted; the existing server id is recorded in the
  outbox (that is also how a re-imported file dedups).
* Two machines importing the same hand: both push, the server keeps the first,
  both outboxes record the same server id. No conflict.
* The HUD on the playing machine always reads its local file: it sees its own
  hands immediately (0 RTT), other machines' hands appear when their owners'
  sync pushes them (eventual consistency, seconds on a LAN).
* Reports/other tools keep reading the server database, unchanged.

## Metrics to watch (extend latency_profile if needed)

`sync_outbox_pending` (gauge), `sync_push_batch` (duration p50/p95/p99),
`sync_push_errors` (counter), plus the existing `hud_queue_wait` should collapse
to ~0 on the playing machine.

## Risks / costs

* Local SQLite grows on the playing machine: prune synced hands periodically
  (keep the outbox row, drop the fact rows older than N days) or keep all —
  SQLite handles millions of rows fine locally.
* If the server is unreachable, the outbox grows and the local DB keeps
  serving the HUD — that is the point; push resumes when the LAN is back.
* Multi-machine play on the *same* tables needs the server as arbiter (as
  above); single-machine play (the reported case) is trivially consistent.

## Status in this PR (wired, off by default)

* `fpdb_3_legacy/local_first_sync.py` + `tests/test_local_first_sync.py`:
  push from local SQLite to a server SQLite file and to a **live PostgreSQL
  18.3** (integration-marked), covering referentials, FK-safe insert order,
  boolean casts, dedup/idempotence and the id mapping.
* **Config switch**: `local_first="1"` + `local_path="..."` on the `<database>`
  node (shipped in HUD_config.xml.example, default `0`). When on,
  `get_db_parameters()` returns the local SQLite params (HUD and importer read
  it, 0 RTT) and `get_server_db_parameters()` returns the server params used by
  the push.
* **Outbox hook**: `Importer._mark_outbox()` registers `database.hids` after
  every successfully imported file, in the import process.
* **Lifecycle**: the sync thread starts in `Importer.runImport()` and stops in
  `Importer.close()`.
* **Metrics** (in the `FPDB_LATENCY_PROFILE` report): `sync_outbox_pending`
  (gauge), `sync_push_batch` (p50/p95/p99), `sync_push_errors` (counter); plus
  `hud_queue_wait`, which should collapse on the playing machine.

Activation rule: turn `local_first="1"` on only when the reporter's latency
report shows LAN RTT > ~2-3 ms (see the simulated-RTT numbers above).
