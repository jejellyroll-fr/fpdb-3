# Moving from PokerTracker 4 or Holdem Manager 3

This guide brings your hand history over from PokerTracker 4 (PT4) or Holdem Manager 3 (HM3). The
tracker's **archive folder** holds each poker room's original files. fpdb's room parsers read those
files as they are, so moving over amounts to one import of the right folder.

| What | Comes over today | Tracked in |
|---|---|---|
| Hands | Yes, with this guide | #612 |
| Stats (`.pt4stat`) | ChipEV and the common cash stats (VPIP, PFR, 3-bet, c-bet, WTSD, W$SD, AF, steal and the folds to them); see [the coverage of PT4's stock stats](pt4-stock-stat-coverage.md) | #613 |
| HUD layout (`.pt4hud`) | Yes: *Configure ▸ Import PT4 HUD*. Stats with no fpdb equivalent are listed; *Convert PT4 HUD to .fpdbhud* makes a shareable package | #614 |
| Reading the tracker's database directly | PokerTracker 4: yes, see [below](#from-the-pokertracker-4-database) and [the findings](pt4-database-spike.md). Holdem Manager 3: not yet | #615, #814 |
| Player notes | Not yet | #618 |

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

### From the PokerTracker 4 database

PokerTracker 4 also keeps every hand it imported in its PostgreSQL database, so fpdb can read them
from there, without an archive or an export. In the wizard, pick *PokerTracker 4*, then *From the
PokerTracker 4 database*, and enter where the database is. PT4's defaults are filled in: server
`localhost`, port `5432`, database `PT4 DB`, user `postgres`. PT4 shows its own settings in
*Database ▸ Database Management*.

- **Read-only.** The connection refuses every write, so PT4's database cannot be changed by fpdb.
- **The password** is used for that import only. It is not saved, and fpdb never reads it from PT4's
  settings.
- **Only new hands.** fpdb remembers the last hand it read from each database
  (`pt4_import_marks.json`, next to `HUD_config.xml`). The next import reads only the hands PT4
  added since then. If a hand failed to import, the next import starts again from the file it was
  in, so it comes over once the cause is fixed. Untick *Only the hands added since the last import* to
  read them all again; hands fpdb already holds are counted as duplicates.
- **What comes over** is what an archive would give. fpdb writes the hands to a temporary folder,
  room by room, and imports it as it imports any folder: the same preview, the same iPoker question,
  the same summary. The folder is deleted when the wizard closes. A database of a million hands
  needs about a gigabyte of free disk space while the wizard is open.
- **Euro signs.** On macOS, PT4 stored some cp1252 files with the wrong character set: a euro sign
  reads `Ä`. fpdb puts the room's own text back before importing, and the preview says how many
  hands it repaired.
- **Tournament results** come over when PT4 kept the room's tournament summary: PokerStars,
  Winamax, Full Tilt, Pacific, Merge, Microgaming and Unibet do. fpdb reads them as it reads summary
  files. For iPoker, PT4 keeps only your own finish, in a form fpdb does not read yet, and fpdb has
  no GGPoker summary reader at all; those tournaments come over with their hands but without
  results.
- **What PT4 added is taken off.** PT4 appends the original file name to a Winamax summary's first
  line, and the tournament number to an old-format Winning (Yatahay) hand's. fpdb removes both, so
  the room's parser reads the text it expects.
- **iPoker** hands are stored by PT4 in its own text format, which fpdb reads; their room is placed
  from your screen names, as for an export.
- **Measured on a 37,657-hand PT4 database:** 99.65% of the hands came over at the first run, and
  all but a few dozen once the fixes above were in. What stays out: rooms fpdb has no parser for
  (Boss Media, PPPoker), Merge tournaments in PT4's text form, and one invitation-only iPoker
  tournament. The summary lists them.

Holdem Manager 3's database is not supported yet: use its archive folder.

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

## Privacy

The wizard reads files from the folder you choose and writes only to your fpdb database. It sends
nothing anywhere.
