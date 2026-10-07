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
created in the database on first import. If id 150 already holds another source in a database, PHH files are refused (unsupported) rather than mixed with it. The database needs a site for every
hand and player; a dataset is not a poker room, so it gets none of a room's
configuration — no parser, no `supported_sites` entry, no HUD.

## Importing

- **Bulk Import** (and the command line, `GuiBulkImport.py -x -f <file|dir>`):
  `.phh` (one hand) and `.phhs` (several) files are recognised by their
  extension, in a file or anywhere in a directory, and never offered to the
  room detector. Each is recorded in the `Files` table by its whole path,
  `PHH/<path>` (past the 255 characters MySQL indexes, `PHH/<hash of the path>/<file name>`), never sharing the row of a room file named alike (`session.txt`) or of a
  PHH file of the same name in another directory.
- A `.phhs` file holds one hand per top-level table (`[1]`, `[2]`, `["session.1"]`, …); a dotted table (`[1.notes]`) is a sub-table of its hand, and a line inside a multiline string (a note), an array or an inline table is never taken for a table -- unless that value is never closed: the hand is then malformed, and the hands it swallowed are read again from the first table header inside it. It is read
  **line by line, one hand at a time**, so a large dataset is never loaded
  whole. Files are read as UTF-8: in a `.phhs`, a line that is not makes only its hand malformed.

The import reports, per run, how many hands were **found**, **imported**,
**duplicates**, **partial**, **unsupported** and **malformed**, and how long it took — in the
Bulk Import completion message and on the command line, which also prints each
refusal with its file, line and hand. In the generic totals, partial hands
count as *partial*, unsupported hands as *skipped* and malformed hands as
*errors*.

A hand is a duplicate when the same hand was imported before: its fpdb hand
number is a hash of its PHH content and of where it sits (the file's path and,
in a `.phhs`, its table), not the optional `hand` field. Two datasets that both
number their hands from 1 are never taken for each other, two hands that read
alike (anonymised, every card unknown) at two tables or in two files are both
kept, and importing a file again finds every hand a duplicate -- a copy moved
elsewhere is another file, its hands new ones.

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
| `antes` | an `ante` post per player (heads-up, like the blinds, the first two are assigned in reverse) |
| `blinds_or_straddles` | `small blind`, `big blind`, then `straddle`; only the last player posting is a `button blind` (short deck). Heads-up the first player posts the big blind and the second, who has the button, the small blind — PokerKit's convention. A blind posted all in for less sets the call at what it posted, as PokerKit plays it. The game's stakes are the small and big blind by position, never a straddle (half the big blind when there is no small one; the button blind when it is the only one) |
| `bring_in`, `pN pb` | a stud `bringin` on third street; the first `cbr` facing it, or made in its place, is a `completes` |
| `pN cbr X` | a bet when nothing is bet on the street, otherwise a raise **to** X (PHH's meaning) |
| `pN cc` | a check, or a call of what is owed — all in for less when the stack is short |
| `pN f` | a fold |
| `d dh pN cards` | hole cards, kept as soon as one is known (unknown ones stay blank): preflop in hold'em; per street in stud (third street: two down, one up; seventh: down); the deal and each draw in draw games |
| `d db cards` | the flop, turn and river |
| `pN sd [cards]` | in draw games, a discard (with the cards when known: each named card leaves the hand, each `??` one of its unknown cards) or standing pat; it opens the next draw, with or without betting in between (all-in runouts) |
| `pN sm cards`, `pN sm -`, `pN sm` | shown cards (a partly shown hand keeps its known cards, the hero's too, and fills a `??` with the card the deal named; every card keeps the place it was dealt in, whatever order the show lists them in; fewer cards than dealt is a partial show, the rest unknown, as PokerKit plays a cash game); shown, the cards the deal already named; mucked, which forfeits any share of the pot -- only at the showdown or once nobody is left to bet (an all-in runout), and in draw games only after the last draw |
| `players`, `seats`, `seat_count`, `table` / `event` | player names (for a name absent or empty, as PHH allows, `pN` -- or `pN#2`... when the file already uses that name), seats, table size (`seat_count`, which must hold every seat; else the highest seat), table name (`table`, even 0, else `event`, else the file name); absent `players` and `seats` are made up, given ones -- even empty -- need one entry per player |
| `currency` | the game's currency; `play` when absent (amounts are then chips) |
| `time`, `day`, `month`, `year`, `time_zone`, `time_zone_abbreviation` | the hand's start, converted to UTC; a partial date keeps every field it gives, each missing one being the epoch's (`year = 2009` alone is 2009-01-01, `month = 2` and `day = 3` alone 1970-02-03, a `time` alone that time on 1970-01-01); a time with no `time_zone` is UTC, unless the hand gives a full location (`city`, `region` and `country`), when it is refused; `time_zone_abbreviation` with a `time_zone` picks the repeated hour when summer time ends (`EST` or `EDT`); 1970-01-01 when PHH gives nothing (a date or a time zone that does not exist, or one that is not a number, is refused) |
| `_hero` (user-defined) | the hero, when it names one of the players; otherwise the hand has none |
| `winnings` | what each player collected |
| `finishing_stacks` | when there are no `winnings`: what each player collected, worked out from the stacks |

Ordering and amounts are kept exactly; uncalled bets are returned — on any
street, even when the board runs out after an all-in — and side pots built by
fpdb's own pot calculation.

## Refused hands

A hand that cannot be imported reliably is refused with a reason, never
stored with invented values:

| Kind | When |
| --- | --- |
| unsupported | a variant with no fpdb mapping; fixed-limit bets whose big bet is not twice the small one (fpdb's game row stores the small bet as the big blind, the big bet as twice it); an unknown starting stack (`null` or `inf`); a time zone where Python has no time-zone database to convert it; a `time_zone_abbreviation` without a `time_zone` (ambiguous: CST is America's or China's), other than UTC or GMT; a `time` with a full location (`city`, `region` and `country`) but no `time_zone` (PHH reads it as local to the location, which fpdb does not resolve); an amount finer than a hundredth (`0.005`), which fpdb's storage in hundredths would truncate; an ante trimmed to a short stack (`ante_trimming_status`), whose eligibility (an ante side pot) fpdb's pooled antes cannot represent -- untrimmed, the short player may win every ante, as fpdb books them; more than three board deals (run it twice); a shared stud card, dealt when the deck runs short (eight players on seventh street); a showdown with neither `winnings` nor `finishing_stacks` — fpdb does not pick winners itself |
| partial | the actions stop before the hand ends, as PHH allows (nothing dealt yet, a board not yet out, a last stud card or a draw replacement not dealt to every player, a street where a player who can still act has not had a turn) — decided from the actions, even when the file carries `winnings` or `finishing_stacks` so far: a hand without a final result is not stored, since it would bend every statistic it reached |
| malformed | invalid TOML; a missing required field (per family, plus `min_bet` for no and pot limit, `small_bet` and `big_bet` for fixed limit), or a bet size, bring-in or starting stack that is not positive; a card outside the variant's deck (2 to 5 in short deck); a street dealt before the previous one's betting is over (a flop before the big blind's option); an action out of turn in hold'em and draw games, or any action once a betting round is over; a starting hand of the wrong size (2 in hold'em, 4 in Omaha and badugi, 5 in 2-7); hole cards dealt twice, out of order (from the first player still in to the last) or not to everyone before the betting -- or an all-in runout -- begins, a draw's replacements included; a second bring-in, or a third street whose first action is neither the bring-in nor a completion (its player may not check or fold); a half-known card (`A?`, `?s`: PHH has only `??`); a card discarded twice, or a discard naming a card dealt to another player; a show that contradicts the deal (more cards than dealt, or a known card the deal did not give, beyond its unknown ones); a date or a time zone that does not exist (`2026-02-30`, `America/New_Yrok` -- checked even in an undated hand), a date field, `time` or time-zone field of the wrong type; an abbreviation that is not the `time_zone`'s at that time; a wall time the clocks skip when summer time begins (`2026-03-08 02:30` in New York); a `seat_count` smaller than a seat; a known card dealt or shown twice (discards may come back, as a reshuffled stub does); winnings larger than the pot, or larger than the main and side pots a player is in -- one by one and together, so two short stacks share their main pot -- antes being common money every player still in can win (nothing for a folded player, or one who mucked); a stud street that moves on before every live player got its card; a draw that moves on before every live player stood pat or discarded, or replacements dealt before everyone has drawn or out of order; a street dealt once everyone but one player folded; arrays that do not have one value per player; `players` that is not a list of names; an action by a folded or all-in player, or by a player who already acted with nothing changed since (stud, whose order is not checked otherwise); a show or muck before the showdown, by a folded player, or a second one by the same player; a bet or raise that does not exceed the current bet or the stack, or that the variant's limit does not allow (no limit: below the minimum bet or raise, the first raise to beat preflop being the largest blind or straddle; a raise by a player whom all-ins for less did not reopen the betting to -- several short all-ins that together make a full raise do reopen it, in fixed limit too (a full raise being the street's bet), and a completion reopens it to the bring-in; a raise when every other player still in is all in; pot limit: above the pot; fixed limit: not the street's bet size, the big bet being allowed on fourth street only over an open pair in stud high (not stud hi/lo or razz), every raise after a big bet being a big bet too — all in for less is always allowed, the raise cap is not checked); a board of the wrong size; an unknown action, player or card; content before the first `[hand]` table of a `.phhs`, or a table of another hand inside one (`[2.notes]` under `[1]`); a hand the database refuses |

Only a hand where everyone folded to one player gets its winner without
`winnings` or `finishing_stacks`: the last player in takes the pot.

## Known limits

- Showdown results come from the file (`winnings` or `finishing_stacks`); fpdb
  does not evaluate hands to find the winners of a PHH showdown.
- PHH does not mark tournament hands: every hand is imported as a ring game.
- The order of play is checked in hold'em and draw games; in stud it follows the
  best hand showing on each street, which would take evaluating the upcards, so
  only the end of each betting round is checked there.
- Hands are stored one at a time, each committed on its own.
- PHH is TOML, read with `tomllib` (Python 3.11+) or, on the Python 3.10 the
  PyOxidizer builds embed, its backport `tomli`, which those builds ship.
  Without either, PHH files are refused as unsupported; nothing else is
  affected.

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
