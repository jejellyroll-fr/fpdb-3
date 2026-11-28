# FPDB 3.11.0

A minor release: 3.11.0 adds rooms, a redesigned HUD editor, a much richer
replayer and new reports on top of the fixes, so it takes the minor number
rather than a patch.

## New rooms and clients

- **PokerStars skins as rooms of their own**: PokerStars on Betfair, on Paddy
  Power, on Sky, on Sisal and on SNAI, each with its own site and folders, and
  a legacy **PokerStars.UK** room for the retired UK client's histories.
- **iPoker**: bet365.fr (its client found without hardcoded paths), win2day
  (its Boss Media era files keep their route; Sökö hands are refused, never
  misread as five-card stud) and **ChampionPoker**, whose folders Detect finds
  on macOS and Windows.
- **Betclic's 2025+ client**: its native `*** HEADER ***` hand histories, cash
  games, Spin & Rush lotteries and progressive knockout tournaments.
- **Unibet.fr's 2026 client** (Relax Gaming): its exports are found, Power Spins filed as
  lotteries, Banzai as shallow, truncated exports re-read from the start, and
  the Windows HUD window detection no longer crashes.
- **BetRivers** and **CoinPoker** (2026 text histories): import only, nothing
  live. CoinPoker's live capture is removed now that the room is import-only.
- **GGPoker**: tournament summaries, tournament headers with the ante in the
  level, Omaha5 and Omaha6, hand times in the player's own zone, EV Cashouts
  settled. Files from third-party converters (`Poker Hand #ring_...`) are
  refused as an unsupported variant.

Some of these rooms are not fully confirmed yet; their issues stay open:
PokerStars on Sky needs real fixtures (#900), win2day a real export (#891),
ChampionPoker a Windows install and a tournament export (#926).

## Importing from PokerTracker 4

- Import hands straight from a PokerTracker 4 database, read-only, without an
  export step.
- Import PokerTracker 4 player notes into fpdb's notes.
- Read PT4 4.19's VPIP, which leaves bomb pots out.
- The acceptance run against a 10k-hand export compared with Holdem Manager 3
  (#811) has not been done yet: treat the HM3 path as experimental.

## Replayer and hand review

- A side inspector beside the table, with a synchronized action history:
  click an action to seek to it, Enter seeks on macOS too.
- A structured decision panel for cash, MTT, ICM and bounty spots, with SPR,
  bet sizing, MDF and fold equity for the player facing a decision.
- Amounts in big blinds.
- All-in EV for each side pot of a hold'em hand, real seeded equity for Omaha
  showdowns, and all-in EV after the last draw in five-card draw games.
- The Winamax/BetRivers splash goes back in the pot on reload.

## Reports

- **Results Calendar**: cash results per day, week, month and year, with VPIP
  and PFR, and exact decimal totals.
- **Tourney Stats**: a PokerTracker-like results overview with in-place
  drill-down.
- **Hand Viewer**: a bounded hand cache, hand-number search, abortable paging,
  downsampled profit curves, and preferences that persist.
- **Research**: shared four- and five-card PLO studies.
- All-in EV statistics, and BB graph units fixed.
- Graph, table and filter colours come from the theme.

## HUD

- **A redesigned HUD editor**: a Design canvas at the centre of the Statistics
  tab with drag and drop, rows, columns and undo; drag and drop on the Popup
  Windows canvas for classic and PT4 popups; a stat catalogue to pick stats and
  popups from lists; stable selection, Cancel asks first, profiles can be
  renamed; xpad and ypad applied in the HUD. Edits survive a profile switch and
  items are no longer lost or doubled on save.
- **Room policies**: positional and dynamic panels are kept off where a room
  forbids or has not reviewed them (PokerStars, Winamax, the iPoker network,
  Unibet.fr...). See `docs/fair-play.md` and `docs/hud-room-compatibility.md`.
- **ACR/WPN**: HUD statistics and auto-notes come from the user's own completed
  hands only, as ACR's policy requires; the hand in play reaches nothing.
- The MTT all-time scope is kept across table changes.
- Total Profit is shown in the game type's currency.
- Stack-based stats use the capped effective stack on WPN cap tables.
- The HUD Stats Guide is generated from the code.

## Statistics fixes

- A c-bet chance is given only on a street the raiser played.
- Raise first in counts only a raise into an unopened pot.
- The HUD queries select the columns their stats read.

## Parsers and import

- A **Parser Debugger** (`tools/parser_debugger.py`) shows everything a
  converter did with a file, flags redundant lines, and writes an anonymized
  bug report.
- English hand-history dates are read whatever the system locale is.
- Every iPoker hand's gametype is read like the first one's.
- WPN current-format cash hands are filed by their currency and table.
- Lottery SnG summaries are imported as the tournament their hands are.
- PokerStars summaries take their start time from their own line and their end
  time from "Tournament finished".
- Stud records a five-card showdown (all-in on 5th street).
- Unibet reads "posts new player's blind" and "posts missed small blind".
- SwC: player names with non-word characters, native seat arrays and amounts,
  tournament stud and its table descriptor, both boards of a double-board bomb
  pot.
- OnGame draw hands are split at the first discard line.
- PHH: a trimmed ante's side pot is imported and kept when reloading.
- Imports yield between hands, run interactive work first, and can be
  cancelled safely; superseded research queries are cancelled too.
- The import log no longer reports normal data as problems.
- Real hand histories can be anonymized into fixtures (`tools/anonymize_hh.py`).

## Configuration

- `Configuration` reads and writes `HUD_config.xml` through ElementTree instead
  of minidom, behind a single XML adapter, with round-trip tests.
- Existing configurations are upgraded in place (config version 104): they gain
  the new rooms, switched off, and keep everything the user set.
- Site Settings lists disabled rooms so they can be turned on, and a config
  reload keeps the Sites table's rooms.

## Interface

- On Linux and Windows the main window's title bar sits on the top row with the
  menus under it.

## Packaging

- The PyOxidizer builds embed CPython 3.11, and the 3.10 workarounds are gone.
- A one-step macOS source installer.
- The macOS bundle is still ad-hoc signed (#441).
- The offscreen Qt steps of the CI are bounded, so a hang fails in minutes.
