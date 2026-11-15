# Moving from PokerTracker 4 or Holdem Manager 3

This guide brings your hand history over from PokerTracker 4 (PT4) or Holdem Manager 3 (HM3). The
tracker's **archive folder** holds each poker room's original files. fpdb's room parsers read those
files as they are, so moving over amounts to one import of the right folder.

| What | Comes over today | Tracked in |
|---|---|---|
| Hands | Yes, with this guide | #612 |
| Stats (`.pt4stat`) | ChipEV and the common cash stats (VPIP, PFR, 3-bet, c-bet, WTSD, W$SD, AF, steal and the folds to them); see [the coverage of PT4's stock stats](pt4-stock-stat-coverage.md) | #613 |
| HUD layout (`.pt4hud`) | Yes: *Configure ▸ Import PT4 HUD*. Stats with no fpdb equivalent are listed; *Convert PT4 HUD to .fpdbhud* makes a shareable package | #614 |
| Reading the tracker's database directly | Being evaluated | #615 |
| Player notes | PT4: yes, *Import ▸ PokerTracker 4 Notes…* (section 5). HM3: not yet | #618 |

## 1. Find the hand histories

**The tracker's archive folder is the best source.** After importing a file, both trackers can move it
to an archive folder, unchanged. That folder holds every room's original files, which is exactly what
fpdb reads.

- **PokerTracker 4**: the archive folder is set in *Configure ▸ Site & Import Options ▸ Preferences*.
- **Holdem Manager 3**: its import settings show where processed hand histories are archived.

Menu names move between tracker versions. If yours differ, look for the setting that names where
*processed* or *archived* hand histories go.

**No archive?** Use the tracker's hand export instead (in PT4, *Database ▸ Export Hands*). An export
may not be in the room's original format: PT4 writes iPoker hands as text starting with `GAME #`, not
as the room's XML. fpdb reads that text too. Each tournament also gets a summary file, which the import
counts apart from the hands. The import summary lists every file fpdb could not read, so nothing goes
missing silently. If a whole export is refused, please open an issue and attach a
few hands, with the names anonymised if you prefer.

## 2. Set your screen names first

fpdb tells your own hands from your opponents' by the screen name configured for each room. Before
importing, enter yours in *Configure ▸ Site Settings* for every room you played. The wizard warns you
when a room's screen name is missing, or does not match the hero found in the files.

## 3. Run the import

*Import ▸ From Another Tracker…* opens a wizard:

1. Pick the tracker.
2. Choose the folder from step 1.
3. Check what the folder holds: files per room, the hero names found in them, the screen name fpdb
   will use, and the files no parser recognises. Nothing has been written yet.
4. Import. The tracker's files are only read: the wizard never moves them, even when *Bulk Import* is
   set to move imported files. The tracker keeps its archive intact.
5. Read the summary, room by room: hero, files, hands imported, duplicates, partial hands and errors.

Importing the same folder twice is safe: hands fpdb already holds are counted as duplicates and are
not stored again.

### iPoker rooms

iPoker files do not name the room they were played on, and PT4 files them all under *iPoker Network*.
fpdb places each file in this order:

1. a file under the hand history folder configured for a room belongs to that room;
2. the hero's name is the screen name, or a hero alias, of one room;
3. only one iPoker room is enabled.

Otherwise the wizard asks which room each hero played on, at step 3. Entering your screen name for
each room in *Configure ▸ Site Settings* before you import spares you the question. A plain *Bulk
Import* cannot ask, so those hands stay under `iPoker`.

A hand is a duplicate only within its room. If you imported iPoker hands before fpdb placed them this
way, importing them again stores them a second time under the right room. Start from a recreated
database (*Database ▸ Create or Recreate Tables*) rather than importing on top of the old rows.

## 4. After the import

- **Stats**: fpdb computes its own stats from the imported hands. Definitions can differ slightly from
  your tracker's. `docs/stat-definitions.md` documents the differences as they are measured (#616).
- **HUD**: import a PT4 layout with *Configure ▸ Import PT4 HUD (.pt4hud)*. The report lists every
  PT4 stat that has no fpdb equivalent. *Configure ▸ Convert PT4 HUD to .fpdbhud…* writes a layout as a
  package. You can share that package or re-import it in *HUD Preferences* without the PT4 file, and
  whoever imports it is told which stats it is missing. Range charts and info popups stay out of the
  package: import the `.pt4hud` itself to get them. From the command line:
  `python -m fpdb_3_legacy.pt4hud layout.pt4hud --package out.fpdbhud`.
- **Large archives**: a few hundred thousand hands take a while. Bulk import runs its equity workers
  in parallel, and PostgreSQL is faster than SQLite for very large databases.

## 5. Player notes (PokerTracker 4)

PT4 keeps its notes in its PostgreSQL database, not in a file. *Import ▸ PokerTracker 4 Notes…*
reads them there, read-only, together with the player tags (*Fish*, *Regular*, your own tags…).
Import your hands first: a note goes to a player fpdb already knows.

1. Enter PT4's database connection, as PT4's *Database Management* window shows it. The
   defaults are PT4's own: `localhost`, port `5432`, user `postgres`, database `PT4 DB`. The password
   is the one you chose when PT4 created its database. fpdb does not save it.
2. *Preview* lists what would change and writes nothing.
3. *Import* adds the notes.

fpdb keeps one note per player, the one the HUD shows when you double-click a player. Each PT4 note
becomes a block in it. The block names where the note came from, its date, the player's tags and
the colour number PT4 gave the note:

```
[PokerTracker 4 | 2024-03-01 | Fish | colour 3]
3-bets light from the blinds.
```

- **An fpdb note is never overwritten.** The PT4 block goes after the note you already have. Tick
  *Leave players who already have an fpdb note alone* to skip those players instead. The report
  names every player whose note was appended to, updated or skipped.
- **Importing again is safe.** A block already in the note is not added a second time, so only new
  PT4 notes come over.
- **Players fpdb does not know are listed, not created.** Import the hands they played, then import
  the notes again.
- **iPoker**: PT4 files every iPoker skin under *iPoker*. A note goes to the player of that name on
  each iPoker room configured in fpdb, since an iPoker name belongs to the whole network.
- fpdb has no note colours, so a colour is kept as its PT4 number in the block's header: PT4's
  database stores only that number, not the colour.

### PT4's automatic notes

PT4's auto-note rules write notes of their own, apart from the ones you type. On some databases
they are the only notes there are. Tick *Also import PT4's automatic notes* to bring them too. PT4
rewrites them as it imports hands, a count going up for instance, so fpdb keeps them in a section
of their own, one line per auto-note with how often it was seen and when:

```
[PokerTracker 4 auto-notes]
- Folds to 3-bet out of position (x4, 2024-03-02)
[end of PokerTracker 4 auto-notes]
```

Each import replaces that section with what PT4 holds now, so it never piles up. Everything
outside the section, your own text and your imported PT4 notes, is left as it is. Do not edit
inside the section: the next import replaces it. With *Leave players who already have an fpdb
note alone*, a player with a note of their own gets no new section, but a section an earlier
import added is still kept up to date.

From the command line, with the fpdb configuration of the current user:

```
python -m fpdb_3_legacy.tracker_notes --dry-run
python -m fpdb_3_legacy.tracker_notes --skip-existing
python -m fpdb_3_legacy.tracker_notes --auto-notes
python -m fpdb_3_legacy.tracker_notes --auto-notes --dry-run --show 5
```

`--show N` prints the first N notes the import changes, as they will read afterwards, so a dry run
shows the text itself and not only the counts.

It asks for the PT4 password, or reads it from `PT4_PASSWORD`. `--host`, `--port`, `--user` and
`--database` default to `PT4_HOST`, `PT4_PORT`, `PT4_USER` and `PT4_DATABASE`, then to PT4's defaults.

**Holdem Manager 3** exports its notes as a `.playernotes` file (*Tools ▸ Export Player Notes*).
Its format is not documented, and fpdb cannot read it yet. If you can share an export, with the
names anonymised if you prefer, please attach it to #618.

## Privacy

The wizard reads files from the folder you choose and writes only to your fpdb database. The notes
import reads PT4's database without writing to it, and writes only player notes in fpdb's. Neither
sends anything anywhere.
