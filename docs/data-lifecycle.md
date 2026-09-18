# Analytics data lifecycle: versioning, staleness, rebuild (#305)

## The problem

The analytics layers store *derived* rows: the normalized events (#293), the
named situations (#294), the board features (#295) and the sizing buckets
(#296). A change of rules in any extractor can make stored rows lie without
anything being wrong again — the parser did nothing, the database did
nothing, and the rows still describe the old rules. Re-importing every file
to fix that is the sledgehammer: it needs the original files, it moves hand
ids, and it rebuilds the HUD cache from scratch.

This module answers with three things that work together:

1. **Versions** — every extractor declares its rule version, recorded per
   subsystem in an `AnalyticsMeta` table;
2. **Staleness** — a subsystem whose recorded version differs from the
   code's version is stale and must not be read as current;
3. **Rebuild** — a tool that re-derives the rows *in place*, from the rows
   the database already stores, one transaction per hand, with progress,
   cancellation and scopes.

## Version registry (`analytics_lifecycle.py`)

`SUBSYSTEMS` and `EXTRACTOR_VERSIONS` are the single registry:

| Subsystem | Version | Notes |
| --- | --- | --- |
| `action_events` | 1 | the #293 event derivation |
| `situations` | 1 | the #294 rule table |
| `board_features` | 1 | the #295 classifier |
| `sizing_buckets` | 1 | the #296 bucket tables |
| `hand_strength` | 0 | declared for #302; version 0 means "never current" |

Bumping a version is a semantic claim: it says the rows already stored were
derived by different rules. The place that changes the rule is the place
that bumps the number.

`AnalyticsMeta` is key/value on purpose — adding a subsystem must never be
a schema migration. The table is created on every connection (under the
same bounded DDL lock as the other feature migrations); a database that
predates it simply has unrecorded versions, which *is* the stale state.
`Settings.version` (DB_VERSION) still means only "recreate and reimport
everything" and is deliberately untouched.

Three properties, all tested:

* a fresh `recreate_tables` database is **born current** — everything in it
  will be written by the running code;
* a missing, unparseable or *newer* recorded version is stale — older code
  must not present newer-rule rows as current;
* nothing ever rewinds a stamp — downgrade of derived rows is absent on
  purpose, because keeping every old extractor alive forever is the price
  the other path pays.

## Situations get their table

Until now the #294 situations existed only for the hand being parsed. Since
this change the importer writes **`HandsSituations`**: one row per decision,
keyed `(handId, actionNo)` exactly like `HandsActions` (the situation is the
name of that decision, so the tables read side by side). The column list is
`situation_store.HANDS_SITUATION_COLUMNS` behind the two id columns plus a
`situationVersion` stamp; the DDL (three backends), the store query and the
bulk writer are guarded against drift by `tests/test_analytics_lifecycle.py`.

Scalar fields store as scalars; the history fields (`streetActions`,
`previousStreetActions`, `board`, `labels`, `enumAnswers`) store as JSON
text — they are history, not dimensions anyone aggregates by.

## Rebuild (`analytics_rebuild.py`)

The rebuild re-derives rows **from the rows the database already stores**.
The action stream, seats, stacks, positions, board cards and gametype are
read back and assembled into a hand-like adapter (`backfill_autonotes`
does the same for AutoNotes), and the extractors run over it unchanged —
one set of rules against either a fresh parse or the stored rows. There is
deliberately no re-parse from raw text: `RawHands` is never written by this
codebase, so the stored rows are the only available source of truth.

Per subsystem: `board_features` re-classifies from the stored cards and
overwrites `BoardFeatures` + `Hands.texture`; `action_events` re-derives
the context and updates the event columns in place; `situations`
overwrites the hand's `HandsSituations` rows; `sizing_buckets` needs no
pass (pure functions of the event columns — it is marked current with
`action_events`, its `GROUPED_WITH` parent).

### Resilience contract

* **one transaction per hand** — a cancelled run leaves every finished hand
  complete; there is never a half-written hand;
* **cancellation is checked before each hand** and reported
  (`result.cancelled`); a cancelled run does *not* stamp versions current —
  the untouched hands remain stale and say so;
* **one bad hand fails alone** (`result.failed`, `result.failures`); the
  run continues and the subsystem can still be marked current;
* **progress** is `(done, total, hand_id)` once per hand;
* **scopes** (`site`, `date_from`/`date_to`, `hand_ids`, `limit`) shrink
  the work instead of filtering the truth afterwards, and a scoped run does
  *not* stamp versions current: "current" is a claim about every hand in the
  database, and only a run that looked at every hand can make it.

## CLI

```
uv run tools/analytics_rebuild.py --status
uv run tools/analytics_rebuild.py --all
uv run tools/analytics_rebuild.py --subsystems board_features
uv run tools/analytics_rebuild.py --all --site PokerStars.COM --limit 500
uv run tools/analytics_rebuild.py --all --hand-id 42 --hand-id 43
uv run tools/analytics_rebuild.py --all --dry-run
```

`--status` prints the recorded vs code version per subsystem and the hand
count in scope; `--dry-run` does the same without writing. The rebuild is
also callable from the GUI through `rebuild_subsystems(db, config,
subsystems, scope=..., progress=..., should_cancel=...)`.

## Import integration

New imports populate the current analytics data incrementally — events and
board features since #293/#295, situations since this change — and a fresh
database is born with current version stamps. An existing database keeps
its staleness; only a completed rebuild moves it.

## What is deliberately not here

* **Downgrade**: re-deriving from older rules would mean keeping every old
  extractor alive forever; the version record marks the rows stale instead.
* **Raw-text re-parse**: `RawHands` is never written, so the stored rows
  are the rebuild's source; the extractors accept stored rows by design.
* **Hand-strength rebuild**: declared in the registry (version 0), built
  with #302; asking for it fails loudly instead of stamping it current.
