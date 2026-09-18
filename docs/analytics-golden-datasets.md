# Golden analytics datasets

The analytics epic (#310) adds an action event model, a player situation model,
a board/sizing dimension, a query engine and several reports on top of the hand
pipeline that already exists. Every one of those layers is only as trustworthy
as the poker semantics underneath, and until now those semantics were spread
across `DerivedStats`, `HudCache` and `Stats` with no single place that said
what a spot is supposed to mean.

This is that place. It is the deliverable of **#308** and the fixture set the
rest of the epic is validated against.

## What is in the corpus

| Where | What |
| --- | --- |
| `tests/fixtures/analytics/golden/*.txt` | 30 hand histories, one file per spot |
| `tests/fixtures/analytics/golden.json` | the manifest: poker logic, money, board and per-player expectations |
| `tests/helpers/analytics_golden.py` | vocabulary, corpus import, independent oracle |
| `tests/test_analytics_golden_datasets.py` | the checks |

The hands are six-handed `$1/$2` NLHE, every stack `$200` (100bb), rake free,
with the button always on seat 3. That gives each seat one role for the whole
corpus, which is what makes per-player aggregates reviewable by eye:

| Seat | Player | Role (position code) |
| --- | --- | --- |
| 1 | Anna | hijack (`2`) |
| 2 | Boris | cutoff (`1`), the recorded hero |
| 3 | Cara | button (`0`) |
| 4 | Dave | small blind (`S`) |
| 5 | Erin | big blind (`B`) |
| 6 | Frank | under the gun (`3`) |

Rake is zero on purpose. With rake in play, `winnings + rake == pot` and the
players' profits no longer sum to zero, so a wrong number stops being
unambiguous: a 2-cent gap would be either a rake or a mistake. Rake-free hands
make every amount exact.

## The scenarios

Each scenario is a spot from #308's list, and the manifest carries the prose
that goes with it. What each one pins:

| File | Spot | Pins |
| --- | --- | --- |
| `01_rfi_open.txt` | unopened pot / RFI | open from the cutoff, steal opportunity and success, both blinds folding to it |
| `02_limp_iso.txt` | limp / iso | open-limp vs over-limp, and an iso-raise over limpers (see deviations) |
| `03_open_call.txt` | open-call | opener out of position after a call, checks the flop and bets the turn: delayed c-bet, not c-bet |
| `04_open_3bet.txt` | open-3bet | 3-bet pot, fold-to-3-bet defence, c-bet in position, low SPR |
| `05_squeeze.txt` | squeeze | squeeze over a raise and a caller; the squeeze is also a 3-bet |
| `06_four_bet_five_bet_allin.txt` | 4-bet / 5-bet all-in | uncalled all-in: the shover wins the pot without showdown and the returned chips are not profit |
| `07_srp_cbet.txt` | SRP c-bet | the smallest continuation bet and the fold it gets |
| `08_delayed_cbet.txt` | delayed c-bet | checked flop, bet turn, called, checked river, showdown |
| `09_turn_probe.txt` | probe | the caller opens the turn once the aggressor has declined the flop and the turn |
| `10_check_raise.txt` | check-raise | donk bet met by a check-raise; response recorded on the player facing the donk |
| `11_float.txt` | float | in-position caller calls the flop c-bet and bets the turn when the aggressor checks |
| `12_turn_barrel.txt` | turn barrel | c-bet plus turn barrel; the same fold is a fold-to-turn-c-bet and a float defence |
| `13_river_barrel.txt` | river barrel | three-street barrel, per-street sizing, river fold |
| `14_multiway.txt` | multiway | three players to the flop, two to the turn, a float in a multiway pot |
| `15_allin_before_river.txt` | all-in before the river | both players all-in on the flop, set over set, board runs out, showdown money |
| `16_board_texture.txt` | representative textures | five identical pots differing only in the flop: ace-high rainbow, king-high two-tone, monotone, paired, low connected |
| `17_bet_sizing.txt` | representative size buckets | ten identical pots differing only in the flop bet: 23, 31, 38, 46, 62, 77, 92, 123, 138 and 154 percent of the pot, one per default bucket from #296 |

Because `16` and `17` hold the action constant and vary one dimension, any
difference between their hands comes from that dimension alone. They are the
datasets #295 (board texture) and #296 (sizing buckets) assert against.

## How an expectation is written

Expectations talk about poker, not about schema columns. The vocabulary is
`SEMANTIC_FIELDS` in `tests/helpers/analytics_golden.py`: `vpip`, `rfi`,
`open_limp`, `three_bet_done`, `cbet_flop_done`, `fold_to_cbet_flop_done`,
`probe_turn_done`, `float_turn_done`, `bet_made_bp_flop`, `spr_flop`,
`vs_cbet_flop_response`, `folded_street` and so on, each with the column that
holds it today and a one-line meaning. When the epic moves a concept to another
table, only that table changes and the expectations stay readable.

An expectation is usually a plain value:

```json
"Boris": {"expect": {"cbet_flop_done": true, "bet_made_bp_flop": 5384}}
```

Where the pipeline does not mean what the poker word means, it is written as
what poker says versus what fpdb stores today, plus the id of a documented
deviation:

```json
"open_limp": {"poker": false, "current": true, "deviation": "open_limp_counts_any_first_caller"}
```

The test asserts the `current` value and fails the moment it changes, so a fix
to the rule has to move the documentation with it instead of slipping through.
A deviation also carries the number of rows it affected when it was written
(`observed_true_rows`), which pins the blast radius rather than describing it.

## Known deviations found by this corpus

These are real findings, not stylistic notes. They are the reason the corpus
exists before the analytics layers do: each of them would otherwise be
inherited, invisible, by every filter and report built on top.

1. **`street0OpenLimp` is set for the first preflop caller, raised pot or not**
   (28 rows, of which exactly one is a genuine open-limp). A player who calls an
   open is recorded exactly like a player who limps an unraised pot.
2. **Over-limps are not recorded at all.** `street0Limp` is documented as the
   over-limp flag but is left false for an over-limper (`calcLimpStreet0`), so an
   over-limper cannot be told apart from a player who never entered the pot.
3. **An iso-raise over limpers is recorded as a raise-first-in**, while the same
   row reports `raiseFirstInChance = false`: the pipeline denies the opportunity
   and records the deed, so a stat computed as `raisedFirstIn /
   raiseFirstInChance` can exceed 100 percent.
4. **A check-raise is recorded as a continuation bet.** A preflop aggressor who
   checks the flop and raises a donk bet gets `street1CBDone = 1` next to
   `street1CheckRaiseDone = 1`, so c-bet frequencies count check-raises.
5. **Betting the flop and folding to a raise counts as folding to a c-bet.**
   The flag `foldToStreet1CBDone` is set even though the aggressor raised rather
   than continuation bet; the poker-correct record is
   `foldToOtherRaisedStreet1`.
6. **`effStack` is the remaining stacks, not the effective stack.** It is
   `min(own remaining, largest opponent remaining)` taken after the betting is
   in, so everyone on 100bb reports 19800 for a big blind and 19900 for a small
   blind, and an all-in player reports their whole stack. Every stack bucket
   built on it is shifted by the money already committed.
7. **Folding to a bet is recorded as folding to a raise** (6 rows on the turn).
   `foldToOtherRaisedStreetN` is fed by the aggression pass, which counts a bet
   as a raise, so a fold to an ordinary lead lands in the same column as a fold
   to a re-raise and nothing downstream can tell the two apart.

## Traps the corpus pins on purpose

* **`Hands` and `HandsPlayers` street indices are offset by one.** Hands
  carries the preflop raise count in `street1Raises` because its street 0 is the
  `BLINDSANTES` pseudo-street (`Hand.actionStreets[0]`), which is why a
  preflop-only hand reports `street0Raises = 0, street1Raises = 1`. Per-player
  columns are preflop-first. Anything joining the two has to know this, so
  `test_hand_raise_counts_are_indexed_from_the_blinds_street` asserts it for
  every hand.
* **Hands counts bets and raises together**, per-player columns split them
  (`streetNRaises` vs `streetNBets`).
* **`enum_folded` carries the street of the fold**: `N` none, `P` preflop,
  `F` flop, `T` turn, `R` river.
* **Sizing is basis points of the pot faced**: `val_f_bet_made_bp = 5384` is a
  7bb bet into a 13bb pot. SPR columns are SPR × 100 (`val_f_spr = 525` is 5.25).
* **HudCache is keyed by player *and* position bucket.** The corpus never moves
  the button, so each player has one row; the harness sums defensively anyway.

## What the tests check

* the manifest and the corpus stay in step, and every spot #308 requires exists;
* money: committed chips become the pot, winnings plus rake are the pot, profits
  sum to zero, and each player's profit is winnings minus contributions;
* the declared pot, rake, board and player counts are what the import produced;
* every manifest expectation holds (37 checks over 30 hands, parametrised by
  scenario so a failure names the spot);
* an **independent oracle** recomputes VPIP, PFR, RFI, 3-bets, who saw the flop
  and who c-bet it straight from the parsed action stream, and must agree with
  the stored flags everywhere except at the documented deviations;
* the **HudCache aggregates** equal the sums of the per-hand rows the HUD never
  reads, which is the aggregate contract the analytics caches will join;
* importing the same hands twice derives the same values, which is a
  precondition for the rebuild tooling in #305.

## Extending it as the epic lands

Each sub-issue should extend this corpus rather than build a private one:

* **#293** adds action events ([`action-event-model.md`](action-event-model.md),
  `tests/test_action_events.py`): the event list is asserted per hand against
  these same files -- ordering, `potBefore`/`potAfter` as a running total,
  `toCall`, `sizingBp`, position, facing context. The hands were chosen so each
  event shape -- check, call, bet, raise, fold, all-in, blinds, forced bets --
  appears at least once. Three of the deviations below are answered there
  without changing a single aggregate: `callerCount` separates an open-limp
  from an over-limp, `facingActionType` says a raise was raised rather than
  c-bet, and `effectiveStack` is measured before the chips go in. The corpus
  keeps pinning the aggregates, because the events complement them rather than
  replace them.
* **#294** adds situations: `16` and `17` vary one dimension each, so a
  situation extractor can be asserted dimension by dimension.
* **#295** adds board features: `16` already holds the action constant across
  five textures, and the manifest names the texture each flop is.
* **#296** adds sizing buckets: `17` already names the bucket each bet falls
  into, one hand per default bucket.
* **#297/#306** add the query engine and DSL: the same 30 hands are the
  reference for "this filter over this corpus returns this count".
* **#300** adds profitability: hand `15` is the all-in with known hole cards
  that EV has to agree with; the harness deliberately does not assert `allInEV`
  yet, because the value belongs to that issue.
* **#301/#302** add range and hand-strength views: every hand here has known
  hole cards, and the manifest says who showed what.

Adding a scenario means adding one file, one manifest entry with its prose and
expectations, and -- if it exposes a new discrepancy -- one deviation note.
