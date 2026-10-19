# Repairing iPoker hands stored under a session code (#440)

## What went wrong

Before 2026-07-25 the iPoker converter took a hand's id from the first
`code="..."` in its text. Every iPoker file opens with
`<session sessioncode="...">`, so the **first hand of each file** was stored
with the session code as its `siteHandNo` instead of its own `gamecode`.

The parser is fixed. A database imported before the fix is not:

| Your database | What it holds | What it does to your numbers |
| --- | --- | --- |
| The file was imported again after the fix | that hand twice, once under the session code and once under its gamecode | the hand is counted twice in reports, graphs and research |
| The file was not imported again | that hand once, under the wrong id | nothing yet; the next import of the file adds the duplicate |

## Repairing it

```bash
python tools/repair_ipoker_session_ids.py                         # report only
python tools/repair_ipoker_session_ids.py --hh-dir ~/iPokerHH     # report, reading the files too
python tools/repair_ipoker_session_ids.py --hh-dir ~/iPokerHH --rehearse   # run it, then roll back
python tools/repair_ipoker_session_ids.py --hh-dir ~/iPokerHH --apply      # write
```

- **Without `--hh-dir`** the tool finds the duplicates. Two hands on an iPoker
  site at the same table and start time, with the same players in the same
  seats, the same stacks and the same results, are one hand. The older row is
  the stale one.
- **With `--hh-dir`** (repeatable: a file or a directory) it also reads each
  file's session code and first gamecode. That confirms the duplicates by id
  and finds the hands stored only under their session code: those are given
  their gamecode, so a later import recognises them instead of adding them
  again.
- Anything it cannot decide (more than two hands at one table and time, a
  session whose files start with different hands) is listed under
  *Left alone* and not touched.

`--apply` copies a SQLite database next to itself before writing
(`<database>.before-440-<date>`), or to `--backup PATH`. PostgreSQL and MySQL
cannot be copied from here: back the database up with the server's own tools,
then add `--i-have-a-backup`.

## What it changes, and what it does not

It deletes the stale hands from every table keyed on a hand — the same list
`tools/cleanup_ipoker_anon_players.py` uses — renumbers the lone ones, drops
the analytics aggregates, which are recomputed from the hands on the next read,
and rebuilds **HudCache, CardsCache and PositionsCache** from the repaired
hands, which reproduces what a clean import writes (#591).

SessionsCache and TourneysCache have no rebuild yet
([#598](https://github.com/jejellyroll-fr/fpdb-3/issues/598)): they keep the
removed hand's contribution, **one extra hand per affected file**, in the
session statistics.
