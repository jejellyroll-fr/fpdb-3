# Sisal and SNAI on the PokerStars Italy network

Two Italian rooms left the iPoker network for the PokerStars Italy network,
keeping their own brand: **Sisal in December 2024** and **SNAI in May 2026**.
fpdb keeps each new client apart from the old one, and from PokerStars' own
Italian client:

| Room in fpdb | Site id | Client | Hands |
| --- | --- | --- | --- |
| `Sisal Poker` | 73 | Sisal's old iPoker client (XML histories) | Everything it wrote, unchanged |
| `PokerStars on Sisal` | 148 | Sisal's client on PokerStars software | Native PokerStars text histories and tournament summaries, from 1 December 2024 |
| `Snai Poker` | 76 | SNAI's old iPoker client (XML histories) | Everything it wrote, unchanged |
| `PokerStars on SNAI` | 149 | SNAI's client on PokerStars software | Native PokerStars text histories and tournament summaries, from 1 May 2026 |
| `PokerStars.IT` | 34 | PokerStars' own Italian client | Unchanged; also every Italian history with no provenance |

Hands already imported under `Sisal Poker` or `Snai Poker` stay there, and old
iPoker files still import under sites 73 and 76, whatever folder they are in.
Nothing is migrated, and nothing is reassigned by brand name.

## Status

- **No authentic export from either new client is in the test corpus yet.**
  The tests run PokerStars' own fixtures, re-dated and given an Italian
  (`ADM ID`) header, from a configured folder: they check how hands are
  *filed*, not that the parser reads every line the new clients write. They are
  labelled provisional. If a client's format turns out to differ from
  PokerStars', the parser rejects the file; nothing is filed under the wrong
  room.
- **The new clients' folders are not documented.** fpdb ships both rooms with
  no folder and does not look for one, so it guesses no default and its
  installed-sites detection does not offer them. The iPoker dispatcher's
  existing `sisal` and `snai` folder matches are the iPoker rooms', for the old
  clients' XML files.
- **The move dates are known to the month.** Sisal's players were migrated
  through December 2024; SNAI's client is reported on the network from 2 May
  2026. Each room's first day is the first of that month, so no hand of the new
  client is turned away.
- **The PokerStars.Italy / Sisal `.xlsx` hand-history export is not
  supported.** What it holds (hands, summaries or something else), and whether
  SNAI offers it too, needs a real file first.

## What files a hand under the new rooms

An Italian PokerStars history carries an ADM ID, but so do PokerStars.IT's:
nothing in it is known to name Sisal or SNAI. Only explicit provenance counts:

1. **The folder you configured for the room.** In *Sites*, set the
   `PokerStars on Sisal` or `PokerStars on SNAI` hand-history and
   tournament-summary paths to the folders the client saves to. A file inside
   one of those folders is filed under the room; a sibling folder whose name
   merely starts the same way is not. If another room's configured folder sits
   inside it, the more specific folder wins.
2. **A hero mapped to the room** in `pokerstars_skin_mapping.conf`, next to
   `PokerStarsToFpdb.py`:

   ```ini
   [hero_mapping]
   yourname = PokerStars on Sisal
   ```

   This is the way to file copied histories (an e-mailed export, a backup) that
   sit outside the configured folders.

Either way, **a hand dated before the room's first day is never filed there**:
it cannot come from the new client. The latest date in the header counts, so a
hand dealt on the first evening, still the day before in ET, is accepted. A
hand with no readable date goes by its folder or hero mapping. The date is read
hand by hand and, in an export of several tournament summaries, summary by
summary.

## What does not

- **EUR stakes, an `ADM ID`, Italian table names** or a plain
  `PokerStars Hand #` header: PokerStars.IT's histories have them too.
- **A player name**, or a folder merely named after Sisal or SNAI: the
  clients' folder names are not known, so none is assumed.
- **A copy outside the configured folders** with no hero mapping: it is filed
  by its content like any PokerStars file, as PokerStars.IT for an Italian
  header.
- **A Sisal hand in SNAI's folder dated before SNAI's move**, and the other way
  round: each room has its own first day.

## Configuration and database

- Configuration **v102** adds both rooms, switched off, on the PokerStars
  network and its layouts, with empty paths. They have no `<hhc>` of their own:
  their files go through the PokerStars converter entry the configuration
  already has. A configuration that already declares a room keeps it as it is.
  The iPoker `Sisal Poker` and `Snai Poker` rooms, and `PokerStars.IT`, are
  left untouched.
- The `Sites` rows (148 and 149, code `PS`) are in new databases, and an
  existing database gains them when fpdb connects.

## HUD

Both rooms are on the PokerStars network, so PokerStars' policy applies: the
static HUD only, no positional or dynamic panels and no live context (see
[HUD room compatibility](hud-room-compatibility.md)). The rooms arrive switched
off; turn one on only after checking its current rules on third-party tools.

## Still to do (#893)

- Authentic, anonymised cash, Zoom, tournament and summary files written by
  each new client, and a check of whether anything in them names the skin.
- The clients' actual hand-history and summary folders on Windows and macOS.
  Then: installed-sites detection and a default path.
- A real PokerStars.Italy / Sisal `.xlsx` export, to decide whether it is worth
  an import flow of its own.

## Related

- #887: PokerStars on Sky (147), and #888: PokerStars on Paddy Power (146),
  filed the same way.
- #733: PokerStars on Betfair (143).
