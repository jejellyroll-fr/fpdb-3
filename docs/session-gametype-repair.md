# Repairing hands imported with session caching (#595)

## Are you affected?

Only if you imported hands with **session caching on**
(`<import ... cacheSessions="True">` in `HUD_config.xml`) with a build between
2026-07-19 and the fix in #594. Session caching is off by default.

Each hand imported that way was stored with its **session id in place of its
game type**, on every site, and without its session. In practice:

- reports, graphs and filters file those hands under the wrong game — or under
  no game at all;
- tournaments lost their session;
- the tournament hands wrote no HUD cache rows;
- **re-importing the same files stores those hands a second time**, because
  the duplicate check cannot find them under their game type.

Separately, before #594 every iPoker 5 card Omaha hand after the first of a
session was read as another game, with blinds taken from the file name, so
its amounts are wrong too.

## Repairing it

```bash
python tools/repair_session_gametypes.py              # report only
python tools/repair_session_gametypes.py --rehearse   # run it, then roll back
python tools/repair_session_gametypes.py --apply      # write
```

The damaged columns are rebuilt from data the bug did not touch:

| Column | Rebuilt from |
| --- | --- |
| `Hands.sessionId` | the session whose time window contains the hand |
| `Hands.gametypeId` | the session cache, which was keyed on the right game type: the game every player of the hand agrees on |
| `Tourneys.sessionId` | the session of the tournament's last hand |

A hand whose players do not agree on one game type, or that falls in more than
one session, is listed under *Left alone* and not touched. Hands imported
without session caching are not affected and are not changed.

If you already imported the same files again, those hands are in the database
twice: the damaged row and a correct one. The tool keeps the correct one and
deletes the damaged copy.

After writing, `--apply` rebuilds **HudCache, CardsCache and PositionsCache**
from the repaired hands (#591): the HUD statistics follow the hands to their
right game, and the tournament rows the damaged import never wrote come back.

`--apply` copies a SQLite database next to itself before writing
(`<database>.before-595-<date>`), or to `--backup PATH`. PostgreSQL and MySQL
cannot be copied from here: back the database up with the server's own tools,
then add `--i-have-a-backup`.

## What it cannot repair

**iPoker 5 card Omaha hands filed under another game.** They are listed by
table. Their amounts were computed against the wrong blinds, so moving them is
not enough: they have to be imported again. The importer would skip them as
duplicates, so delete them first, then re-import those files with this version:

```bash
python tools/repair_session_gametypes.py --apply --delete-misclassified
```

**The session caches.** SessionsCache and TourneysCache have no rebuild yet
([#598](https://github.com/jejellyroll-fr/fpdb-3/issues/598)); a deleted
duplicate stays counted there.
