# Paddy Power Poker on the PokerStars network

Paddy Power Poker left the iPoker network for the PokerStars network on
**28 October 2026**. fpdb keeps the two clients apart:

| Room in fpdb | Site id | Client | Hands |
| --- | --- | --- | --- |
| `Paddy Power Poker` | 65 | The old iPoker client (XML histories) | Everything it wrote, unchanged |
| `PokerStars on Paddy Power` | 146 | The client on PokerStars software | Native PokerStars text histories and tournament summaries, from 28 October 2026 |

Hands already imported under `Paddy Power Poker` stay there. Old iPoker files
still import under site 65, whatever folder they are in.

## Status

- **No authentic export from the new client is in the test corpus yet.** The
  tests run PokerStars' own fixtures, re-dated, from a configured folder: they
  check how hands are *filed*, not that the parser reads every line the new
  client writes. If its format turns out to differ from PokerStars', the
  parser rejects the file; nothing is filed under the wrong room.
- **The new client's folders are not documented** (Poker Copilot 8.27 supports
  the client on Windows and Mac but gives no path). fpdb ships the room with no
  folder and does not look for one, so it guesses no default and its installed-
  sites detection does not offer the room.

## What files a hand under `PokerStars on Paddy Power`

Nothing in a PokerStars history names the skin, so only explicit provenance
counts:

1. **The folder you configured for the room.** In *Sites*, set the
   `PokerStars on Paddy Power` hand-history and tournament-summary paths to the
   folders the client saves to (in the client: *Settings → Playing History*).
   A file inside one of those folders is filed under the room; a sibling folder
   whose name merely starts the same way is not.
2. **A hero mapped to the room** in `pokerstars_skin_mapping.conf`, next to
   `PokerStarsToFpdb.py`:

   ```ini
   [hero_mapping]
   yourname = PokerStars on Paddy Power
   ```

   This is the way to file copied histories (an e-mailed export, a backup) that
   sit outside the configured folders.

Either way, **a hand dated before 28 October 2026 is never filed there**: it
cannot come from the new client. The latest date in the header counts, so a
hand dealt on the first evening, still the 27th in ET, is accepted. A hand with
no readable date goes by its folder or hero mapping. The date is read hand by
hand and, in an export of several tournament summaries, summary by summary:
an export spanning the move files its older tournaments as their own text says.

## What does not

- **GBP stakes.** PokerStars.COM, PokerStars on Betfair and Sky's client also
  deal in pounds.
- **A plain `PokerStars Hand #` header**, or a folder merely named after Paddy
  Power: the client's folder name is not known, so none is assumed.
- **A copy outside the configured folders** with no hero mapping: it is filed
  by its content like any PokerStars file, as PokerStars.COM for GBP stakes.

## Configuration and database

- Configuration **v97** adds the room, switched off, on the PokerStars network
  and its layouts, with empty paths. It has no `<hhc>` of its own: its files go
  through the PokerStars converter entry the configuration already has (the
  HUD's table lookup borrows the same entry, through the room's `network`). A
  configuration that already declares the room keeps it as it is.
- The `Sites` row (146, code `PS`) is in new databases, and an existing database
  gains it when fpdb connects.

## HUD

The room is on the PokerStars network, so PokerStars' policy applies: the
static HUD only, no positional or dynamic panels and no live context (see
[HUD room compatibility](hud-room-compatibility.md)). The room arrives switched
off; turn it on only after checking the room's current rules on third-party
tools.

## Related

- #733 / PR #805: PokerStars on Betfair (143).
- #889 / PR #890: the retired PokerStars.UK client (145).
- #887: Sky Poker's move to the PokerStars network; Sky's iPoker room is 72.
