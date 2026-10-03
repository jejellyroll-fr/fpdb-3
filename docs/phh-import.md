# PHH import

[PHH (Poker Hand History)](https://phh.readthedocs.io) is a TOML interchange
format for poker hands, used by public hand datasets and by
[PokerKit](https://github.com/uoftcprg/pokerkit), its reference implementation.
fpdb imports PHH files as an **external format**
([#381](https://github.com/jejellyroll-fr/fpdb-3/issues/381), part of
[#380](https://github.com/jejellyroll-fr/fpdb-3/issues/380)):

- to use existing PHH datasets in fpdb (statistics, Hand Viewer, Replayer);
- to exercise fpdb's own hand, database and statistics pipeline independently
  of any room's text format;
- as a base for round-trip and cross-validation tests against PokerKit.

## What PHH is, and is not, in fpdb

A PHH hand is turned into fpdb's own model — `HoldemOmahaHand`, `StudHand` or
`DrawHand` — through the same `Hand.add*` calls a room parser makes, then
stored by the pipeline every hand goes through. PHH does **not** replace that
model, and the native room parsers keep their job: a PokerStars history is
still read by the PokerStars parser.

PHH hands are stored under a **`PHH` data source** (`Sites` id 150, code `PH`),
created in the database on first import. The database needs a site for every
hand and player; a dataset is not a poker room, so it gets none of a room's
configuration — no parser, no `supported_sites` entry, no HUD.

## Importing

- **Bulk Import** (and the command line, `GuiBulkImport.py -x -f <file|dir>`):
  `.phh` (one hand) and `.phhs` (several) files are recognised by their
  extension, in a file or anywhere in a directory, and never offered to the
  room detector.
- A `.phhs` file holds one hand per top-level table (`[1]`, `[2]`, …). It is read
  **line by line, one hand at a time**, so a large dataset is never loaded
  whole. Files are read as UTF-8.

The import reports, per run, how many hands were **found**, **imported**,
**duplicates**, **unsupported** and **malformed**, and how long it took — in the
Bulk Import completion message and on the command line, which also prints each
refusal with its file, line and hand. In the generic totals, unsupported hands
count as *skipped* and malformed hands as *errors*.

A hand is a duplicate when the same hand (the same PHH content) was imported
before: its fpdb hand number is a hash of the hand, not the optional `hand`
field, so two datasets that both number their hands from 1 are never taken for
each other.

## Capability matrix

| PHH | Name | fpdb game | Limit | Family |
| --- | --- | --- | --- | --- |
| `FT` | Fixed-limit Texas hold 'em | `holdem` | fl | hold |
| `NT` | No-limit Texas hold 'em | `holdem` | nl | hold |
| `NS` | No-limit short-deck hold 'em | `6_holdem` | nl | hold |
| `PO` | Pot-limit Omaha | `omahahi` | pl | hold |
| `FO/8` | Fixed-limit Omaha hi/lo | `omahahilo` | fl | hold |
| `F7S` | Fixed-limit seven card stud | `studhi` | fl | stud |
| `F7S/8` | Fixed-limit seven card stud hi/lo | `studhilo` | fl | stud |
| `FR` | Fixed-limit razz | `razz` | fl | stud |
| `N2L1D` | No-limit 2-7 single draw | `27_1draw` | nl | draw |
| `F2L3D` | Fixed-limit 2-7 triple draw | `27_3draw` | fl | draw |
| `FB` | Fixed-limit badugi | `badugi` | fl | draw |

Every PHH variant has a lossless fpdb mapping (`phh_import.GAMES`). Any other
`variant` is refused as **unsupported**, naming it: PHH has no OFC, Pineapple,
PLO5/PLO6, Drawmaha, Badacey/Badeucey or other fpdb game, and fpdb's support for
them is untouched — they keep their native parsers.

## How a hand is read

| PHH | fpdb |
| --- | --- |
| `antes` | an `ante` post per player |
| `blinds_or_straddles` | `small blind`, `big blind`, then `straddle`; only the last player posting is a `button blind` (short deck). Heads-up the first player posts the big blind and the second, who has the button, the small blind — PokerKit's convention |
| `bring_in`, `pN pb` | a stud `bringin` on third street |
| `pN cbr X` | a bet when nothing is bet on the street, otherwise a raise **to** X (PHH's meaning) |
| `pN cc` | a check, or a call of what is owed — all in for less when the stack is short |
| `pN f` | a fold |
| `d dh pN cards` | hole cards: preflop in hold'em; per street in stud (third street: two down, one up; seventh: down); the deal and each draw in draw games |
| `d db cards` | the flop, turn and river |
| `pN sd [cards]` | in draw games, a discard (with the cards when known) or standing pat; it opens the next draw |
| `pN sm cards`, `pN sm` / `sm -` | shown cards; mucked |
| `players`, `seats`, `seat_count`, `table` / `event` | player names (`p1`…`pN` when absent), seats, table size, table name |
| `currency` | the game's currency; `play` when absent (amounts are then chips) |
| `time`, `day`, `month`, `year`, `time_zone` | the hand's start, converted to UTC; 1970-01-01 when PHH gives no date |
| `_hero` (user-defined) | the hero, when it names one of the players; otherwise the hand has none |
| `winnings` | what each player collected |
| `finishing_stacks` | when there are no `winnings`: what each player collected, worked out from the stacks |

Ordering and amounts are kept exactly; uncalled bets are returned and side pots
built by fpdb's own pot calculation.

## Refused hands

A hand that cannot be imported reliably is refused with a reason, never
stored with invented values:

| Kind | When |
| --- | --- |
| unsupported | a variant with no fpdb mapping; more than three board deals (run it twice); a showdown with neither `winnings` nor `finishing_stacks` — fpdb does not pick winners itself |
| malformed | invalid TOML; a missing required field; arrays that do not have one value per player; an action by a folded or all-in player; a bet or raise that does not exceed the current bet or the stack; a board of the wrong size; an unknown action, player or card; content before the first `[hand]` table of a `.phhs`; a hand the database refuses |

Only a hand where everyone folded to one player gets its winner without
`winnings` or `finishing_stacks`: the last player in takes the pot.

## Known limits

- Showdown results come from the file (`winnings` or `finishing_stacks`); fpdb
  does not evaluate hands to find the winners of a PHH showdown.
- PHH does not mark tournament hands: every hand is imported as a ring game.
- Hands are stored one at a time, each committed on its own.

## Tests and fixtures

`tests/fixtures/phh/` holds one hand per variant, plus the all-in and side-pot,
heads-up and split-pot cases, and PHH's own two example hands. They were played
through PokerKit, which supplied their results and every player's net result
(`pokerkit_results.json`); `tests/test_phh_import.py` checks fpdb's stored
result for each player against it. To regenerate them (PokerKit is not an fpdb
dependency):

```
uv run --no-project --with pokerkit python tools/phh_fixture_results.py
```
