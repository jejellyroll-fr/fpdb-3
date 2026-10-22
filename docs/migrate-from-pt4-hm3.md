# Moving from PokerTracker 4 or Holdem Manager 3

This guide brings your hand history over from PokerTracker 4 (PT4) or Holdem Manager 3 (HM3). Both
trackers keep the hands they import in each poker room's **own** format. fpdb's room parsers read those
files as they are, so moving over amounts to one import of the right folder.

| What | Comes over today | Tracked in |
|---|---|---|
| Hands | Yes, with this guide | #612 |
| Stats (`.pt4stat`) | ChipEV and the common cash stats (VPIP, PFR, 3-bet, c-bet, WTSD, W$SD, AF, steal and the folds to them); see [the coverage of PT4's stock stats](pt4-stock-stat-coverage.md) | #613 |
| HUD layout (`.pt4hud`) | Yes: *Configure ▸ Import PT4 HUD*. Stats with no fpdb equivalent are listed; *Convert PT4 HUD to .fpdbhud* makes a shareable package | #614 |
| Reading the tracker's database directly | Being evaluated | #615 |
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
may not be in the room's original format. The import summary lists every file fpdb could not read,
so nothing goes missing silently. If a whole export is refused, please open an issue and attach a
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
