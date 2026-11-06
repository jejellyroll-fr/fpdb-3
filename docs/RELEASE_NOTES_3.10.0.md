# FPDB 3.10.0

A minor release: 3.10.0 adds new features (tournament ICM, imports from other
trackers, research and study tools, pack sharing) on top of the fixes, so it
takes the minor number rather than a patch.

## Tournaments and ICM

- Add an ICM engine: Malmuth-Harville equities, all-in $EV and bubble factor.
- Know what each place of a tournament pays, enter or apply a payout structure
  from the replayer, and price an all-in in prize equity.
- Draw an ICM $EV-adjusted line in the tournament graph, and add a bubble
  factor band to the tournament study pack.
- Knockouts: price a bounty in the replayer, count bounty money in the reports,
  filter tournaments by knockout or freezeout, and show a player's bounty and
  who covers whom in the HUD.
- Read dollar prizes from PokerStars summaries, and read those summaries as
  UTF-8 before cp1252.
- Apply the Category, Limit, Buy-In and Number of Players filters in the
  tournament viewers, and show net rather than gross winnings.

## Importing from other trackers and formats

- Import hands from PokerTracker 4 and Holdem Manager 3 through a wizard, and
  read what PT4's Export Hands writes today. **Experimental**: the acceptance
  run against 10k-hand exports compared with the source tracker (#616) has not
  been done yet.
- Translate PT4's common cash stats and save an imported PT4 HUD as an
  `.fpdbhud` package, listing the stats that do not translate.
- File PT4 iPoker hands under the room their hero plays on, and name a PT4
  summary after its room.
- Import PHH hand histories, resolving their players through the room alias
  machinery.

## Research, study and analytics

- Add the Research Browser: filters, results and drill-down on one screen,
  hero-vs-field comparison, biggest differences against the field, sizing,
  position, board and hand-strength visualisations. Works on PostgreSQL.
- Add a spot-first Study Explorer with NLHE 6-max, PLO and MTT study packs.
- Build the analytics foundation underneath: a per-action event model, named
  player situations, board texture, sizing buckets, a declarative stat and
  filter language, populations and cohorts, and in-place rebuild of stale
  analytics rows.
- Export the hands in view as one solver-review document, describe every street
  for postflop study tools, and send replayed hands to PreflopAdvisor.
- Composable Hand Viewer filters, session analytics in the Session Viewer,
  CSV/TSV export of report tables, and readable hand-sharing renderers.

## HUD

- Dynamic panels that follow the hand, analytics-backed stats, hierarchical
  popup packs, and Basic, Advanced and Dynamic reference HUDs. Dynamic panels
  ask before running and stay off at PokerStars tables.
- Install, update and uninstall packs from Tools > Get packs, and share a HUD
  profile or stat pack as a folder ready for the gallery.
- Make the HUD follow the fpdb theme, with compact table options reachable from
  the main window.
- Reduce live HUD latency at high table counts, stop the note cell blocking the
  Qt thread on a remote database, and collect Python garbage on the Qt main
  thread only, which removes a deadlock.
- Make the popup buttons work and let the popup reopen after Alt+F4.
- Add a Session Guard for the session being played.
- Keep VPIP for a blind who called or raised, then folded.

## Live capture

- Native SwC Poker capture on Windows, with bomb pots and double boards parsed
  and stored.
- Captures that reach into a poker client stay off until the user turns them
  on, and fpdb says what it does while you play.

## Reliability and diagnostics

- Keep local traces of crashes and uncaught exceptions in fpdb and the HUD,
  including the stacks of a native HUD crash.
- SQLite crash safety, atomic saves of `HUD_config.xml`, and repairs for iPoker
  hands stored under the wrong gametype.
- Rebuild Sessions, SessionsCache, TourneysCache and the statistics caches from
  the hands, and bucket HudCache days by each hand's own UTC offset.
- Ask PostgreSQL less during a bulk import, and compute its all-in equities in
  worker processes.
- Tell the user when a newer release is available.
- Local-first sync to a reporting server exists but is **off by default**; the
  gaps left before it becomes the normal path are listed in #684.

## Rooms and parsers

- Keep all five hole cards of 888 5-card Omaha hands.
- Recognise PokerStars.it tournament table titles.
- Detect the Bwin.fr hands macOS lets fpdb check but not list, and say so when
  macOS refuses to auto-import a watched folder.

## Internationalisation

- Complete the French catalogue, merge every catalogue with the source, and
  offer the other thirteen locales as fuzzy translations.

## Packaging and code base

- Release artefacts are built only for releases (or on demand), not on every
  push. This release ships five archives: PyInstaller for Linux x64 and
  Windows x64, PyOxidizer for Linux x64, Windows x64 and macOS ARM64.
- Pushing a version tag now cuts the release: CI drafts it with these notes,
  attaches the archives, and publishes it once the builds and tests pass.
  Before, only publishing a GitHub release started the builds.
- The macOS bundle is still ad-hoc signed (#441).
- Split `Database.py`, `Configuration.py`, `HUD_main.pyw` and `DerivedStats.py`
  into modules by concern, merge the `test/` tree into `tests/`, and type-check
  the application with mypy.
- Lock patched releases of aiohttp, anyio, multidict and soupsieve.
