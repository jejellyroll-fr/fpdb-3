# Sky Poker on the PokerStars network

Sky Poker left the iPoker network for the PokerStars network on
**19 November 2026**. fpdb keeps the two clients apart:

| Room in fpdb | Site id | Client | Hands |
| --- | --- | --- | --- |
| `Sky Poker` | 72 | The old iPoker client (XML histories) | Everything it wrote, unchanged |
| `PokerStars on Sky` | 147 | The client on PokerStars software | Native PokerStars text histories and tournament summaries, from 19 November 2026 |

Hands already imported under `Sky Poker` stay there, and old iPoker files still
import under site 72, whatever folder they are in. Nothing is migrated.

## Status

- **No authentic export from the new client is in the test corpus yet.** The
  tests run PokerStars' own fixtures, re-dated, from a configured folder: they
  check how hands are *filed*, not that the parser reads every line the new
  client writes. They are labelled provisional. If the client's format turns
  out to differ from PokerStars', the parser rejects the file; nothing is filed
  under the wrong room.
- **The new client's folders are not documented.** fpdb ships the room with no
  folder and does not look for one, so it guesses no default and its installed-
  sites detection does not offer the room. The detector's existing `sky` folder
  match is the iPoker room's, for the old client.

## What files a hand under `PokerStars on Sky`

Nothing in a PokerStars history is known to name the skin, so only explicit
provenance counts:

1. **The folder you configured for the room.** In *Sites*, set the
   `PokerStars on Sky` hand-history and tournament-summary paths to the folders
   the client saves to (Sky's support page explains how to save hand histories
   in the client). A file inside one of those folders is filed under the room;
   a sibling folder whose name merely starts the same way is not. If another
   room's configured folder sits inside Sky's, the more specific folder wins.
2. **A hero mapped to the room** in `pokerstars_skin_mapping.conf`, next to
   `PokerStarsToFpdb.py`:

   ```ini
   [hero_mapping]
   yourname = PokerStars on Sky
   ```

   This is the way to file copied histories (an e-mailed export, a backup) that
   sit outside the configured folders.

Either way, **a hand dated before 19 November 2026 is never filed there**: it
cannot come from the new client. The latest date in the header counts, so a
hand dealt on the first evening, still the 18th in ET, is accepted. A hand with
no readable date goes by its folder or hero mapping. The date is read hand by
hand and, in an export of several tournament summaries, summary by summary.

## What does not

- **GBP stakes.** PokerStars.COM, PokerStars on Betfair and PokerStars on
  Paddy Power also deal in pounds.
- **A plain `PokerStars Hand #` header**, a player name, or a folder merely
  named after Sky: the client's folder name is not known, so none is assumed.
- **A copy outside the configured folders** with no hero mapping: it is filed
  by its content like any PokerStars file, as PokerStars.COM for GBP stakes.
- **A `Betfair Hand #` history**, wherever it lies: Betfair's client names
  itself, and its hands stay under PokerStars on Betfair (143).

## Configuration and database

- Configuration **v101** adds the room, switched off, on the PokerStars network
  and its layouts, with empty paths. It has no `<hhc>` of its own: its files go
  through the PokerStars converter entry the configuration already has. A
  configuration that already declares the room keeps it as it is. The iPoker
  `Sky Poker` room is left untouched.
- The `Sites` row (147, code `PS`) is in new databases, and an existing database
  gains it when fpdb connects.

## HUD

The room is on the PokerStars network, so PokerStars' policy applies: the
static HUD only, no positional or dynamic panels and no live context (see
[HUD room compatibility](hud-room-compatibility.md)). The room arrives switched
off; turn it on only after checking Sky's current rules on third-party tools.

## Still to do (#887)

- Authentic, anonymised cash, tournament and summary files written by the new
  client after 19 November 2026, and a check of whether anything in them names
  the skin.
- The client's actual hand-history and summary folders on Windows and macOS.
  Then: installed-sites detection and a default path.

## Related

- #888: PokerStars on Paddy Power (146), filed the same way.
- #733: PokerStars on Betfair (143).
- #889: the retired PokerStars.UK client (145).
- #893: PokerStars on Sisal (148) and PokerStars on SNAI (149), the Italian
  skins, filed the same way; see [their page](pokerstars-italy-skins.md).
