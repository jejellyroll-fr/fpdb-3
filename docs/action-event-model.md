# The action event model

`HandsPlayers` and `HudCache` store aggregates: VPIP, RFI, a squeeze flag, a
c-bet flag, a bet-sizing total. Aggregates do not compose, and the questions the
analytics epic (#310) exists to answer are compositions:

> BTN vs BB, single raised pot, preflop aggressor, in position, flop bet 25-40%
> pot, ace-high rainbow board, facing a raise, 80-120bb effective.

No set of columns describes that sentence, and adding one column per phrase
never converges: the phrases are combinations of a handful of *facts about a
decision*. This is the deliverable of **#293**: one row per decision, carrying
the context that decision was made in.

## Where it lives

| Where | What |
| --- | --- |
| `HandsActions` | the rows: the parser's columns plus the 18 normalized event columns |
| `fpdb_3_legacy/action_events.py` | the derivation, and the column vocabulary |
| `DerivedStats.assembleHandsActions` | calls it, once, after the players are assembled |
| `docs/action-event-model.md` | this file |

The events are **derived, never parsed**:

```
HandHistoryConverter ── actions ──┐
                                  ├─> DerivedStats.assembleHandsActions ─┬─> HandsActions rows (replayer, HUD history)
HandsPlayers (positions, stacks) ─┘                                      └─> event columns (#293)
```

`assembleHandsActions` already wrote one row per action for the replayer; the
event pass fills in the context on those same rows. Nothing was reshaped,
reordered or duplicated, so the replayer, the HUD and the analytics layers read
one table. `action_events` adds no parser knowledge: everything comes from the
action tuples and from the per-player context `assembleHandsPlayers` computed a
moment earlier. Where the aggregate calculators already knew a rule -- the chips
a raise pushes in (`action_chips`), bet sizing in basis points
(`_EventWalk.sizing_bp`), the effective-stack formula
(`effective_stack_cents`) -- this module holds the single copy and
`calcRaiseMade` / `calcStreetSPR` call it.

## Columns

Money is **cents** (`BIGINT`), sizes are **basis points** (`INT`), so 1% of a pot
is 100 and a pot-sized bet is 10000. Streets are the pipeline's: `-1` blinds and
antes, `0` preflop, `1` flop, `2` turn, `3` river. Every context column is
measured **before the chips of that action go in** -- what the player had to
decide with.

| Column | Type | Meaning |
| --- | --- | --- |
| `actionType` | `VARCHAR(24)` | the action word, as the parser spells it (`folds`, `checks`, `calls`, `bets`, `raises`, `completes`, `ante`, `small blind`, `big blind`, `straddle`, `bringin`, ...) |
| `toCall` | `BIGINT` | chips needed to continue: `bet level − already in this round`. 0 for a check and for a forced bet, which is the price to decline or meet |
| `potBefore` | `BIGINT` | chips in the pot before this action, bomb-pot money included |
| `potAfter` | `BIGINT` | `potBefore` plus the chips this action puts in (for a raise, the raise-by plus the call) |
| `sizingBp` | `INT` | the action's size against the pot it faced: the bet for a `bets`, the raise-to amount for a `raises`. 0 for anything else |
| `position` | `SMALLINT` | the `HandsPlayers.position` seat code: `0` button, `1` cutoff, `2` hijack, ..., `-1` small blind, `-2` big blind. `NULL` when no position was derived |
| `relativePosition` | `SMALLINT` | how many players **still in the hand act after this one**, by seat order. 0 means this player acts last |
| `inPosition` | `BOOLEAN` | `relativePosition = 0` |
| `effectiveStack` | `BIGINT` | chips this player still has behind, capped by the deepest opponent who is still in the hand. 0 when the only opponent left is all-in |
| `effectiveStackBB` | `INT` | `effectiveStack` in centi-big-blinds, so 100bb is 10000 |
| `sprBefore` | `INT` | centi-SPR: `effectiveStack / potBefore × 100`, the same encoding as `val_f_spr` |
| `isAggressor` | `BOOLEAN` | this action is a bet, raise, complete or all-in raise, making the player the last aggressor |
| `facingActionType` | `VARCHAR(24)` | the word of the bet or raise being faced (`bets`, `raises`, `completes`), `NULL` when the price is only a forced bet or nothing |
| `facingAmount` | `BIGINT` | the same number as `toCall`, kept so a query can read the facing pair without a second rule |
| `facingSizingBp` | `INT` | that bet's or raise's own `sizingBp` |
| `raiserCount` | `SMALLINT` | bets and raises already made on this street before this action (0 = nobody has bet) |
| `callerCount` | `SMALLINT` | calls already made on this street before this action |
| `playersInHand` | `SMALLINT` | players still in the hand, the acting player included |

### Conventions worth stating twice

* **The blinds and antes street is the forced part of preflop.** `small blind`,
  `big blind` and `straddle` are live: they set the bet level, which is why an
  opener's `toCall` is the big blind. `ante` is dead money: it goes into the pot
  and nowhere else, so handing everyone an ante does not change what the opener
  owes. A forced bet never makes an aggressor and is never something a player is
  said to face -- `facingActionType` stays `NULL` for them.
* **`toCall` is the price, `facingActionType` is who set it.** Preflop the opener
  has `toCall = 200` (the big blind) with `facingActionType = NULL`. Facing a
  raise, both are set.
* **Position is seat order, not who acted last.** The cutoff is behind the
  hijack on every street of the hand, whichever of them checked, bet or folded
  first, and `inPosition` does not flicker within a street. A player with no
  chips behind is all-in and cannot act, so they never count as being behind
  anybody; folded players have left the hand.
* **Order is preserved exactly.** `actionNo` is the hand-wide sequence, in the
  parser's order, and `streetActionNo` restarts on each street.

### Reading one hand

Scenario `04_open_3bet` from the golden corpus of
[#308](analytics-golden-datasets.md) (`$1/$2`, 100bb, button on seat 3), preflop
and flop:

| `actionNo` | player | `actionType` | `toCall` | `potBefore→After` | `sizingBp` | `pos` | `relPos` | `effStack` | `raiser`/`caller` | facing |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Dave | small blind | 0 | 0 → 100 | 0 | -1 | 1 | 20000 | 0 / 0 | — |
| 2 | Erin | big blind | 0 | 100 → 300 | 0 | -2 | 0 | 20000 | 0 / 0 | — |
| 3 | Frank | folds | 200 | 300 → 300 | 0 | 3 | 5 | 20000 | 0 / 0 | — |
| 4 | Anna | raises | 200 | 300 → 800 | 16666 | 2 | 4 | 20000 | 0 / 0 | — |
| 5 | Boris | raises | 500 | 800 → 2400 | 20000 | 1 | 3 | 20000 | 1 / 0 | `raises` 500 @ 16666 |
| 6 | Cara | folds | 1600 | 2400 → 2400 | 0 | 0 | 2 | 19900 | 2 / 0 | `raises` 1600 @ 20000 |
| 7 | Dave | folds | 1500 | 2400 → 2400 | 0 | -1 | 1 | 19800 | 2 / 0 | `raises` 1500 @ 20000 |
| 8 | Erin | folds | 1400 | 2400 → 2400 | 0 | -2 | 0 | 19500 | 2 / 0 | `raises` 1400 @ 20000 |
| 9 | Anna | calls | 1100 | 2400 → 3500 | 0 | 2 | 1 | 18400 | 2 / 0 | `raises` 1100 @ 20000 |
| 10 | Anna | checks | 0 | 3500 → 3500 | 0 | 2 | 1 | 18400 | 0 / 0 | — |
| 11 | Boris | bets | 0 | 3500 → 5200 | 4857 | 1 | 0 | 18400 | 0 / 0 | — |
| 12 | Anna | folds | 1700 | 5200 → 5200 | 0 | 2 | 1 | 16700 | 1 / 0 | `bets` 1700 @ 4857 |

The blind posts are the 100 and the 200 the blinds actually paid; the small
blind folding has to find 1500 because 100 is already in; Anna's 3-bet call is
1100 because her open (500) is at the raise level already. Anna opened from the
hijack and Boris called in position, which is why the hijack has `relPos = 1` on
the flop while the cutoff has `relPos = 0`.

## Querying it

The event table is what the rest of the epic reads, so the useful queries are
mostly "filter by context, group by outcome":

```sql
-- flop bets as a share of the pot, split by whether anybody was still to act
SELECT ha.relativePosition = 0 AS in_position, COUNT(*) AS bets, AVG(ha.sizingBp)
FROM HandsActions ha
WHERE ha.street = 1 AND ha.actionType = 'bets'
GROUP BY ha.relativePosition = 0;
```

```sql
-- how a flop bet is answered, by the size that was bet
SELECT ha.facingSizingBp / 1000 AS size_in_percent, ha.actionType AS response, COUNT(*) AS times
FROM HandsActions ha
WHERE ha.street = 1 AND ha.facingActionType = 'bets'
GROUP BY ha.facingSizingBp / 1000, ha.actionType;
```

Both run on SQLite, PostgreSQL and MySQL unchanged: no casts, no date
functions, no window functions.

## Schema migration and rebuild

The columns are **additive**, exactly like the `HandsPlayers` stat columns:

* **Fresh database** -- `sql_schema_hand.createHandsActionsTable` creates them,
  and `createAllIndexes` adds `HandsActions_street_idx` and
  `HandsActions_actionType_idx` next to the existing `handId` / `playerId`
  indexes, because the event queries are "this street, this action type".
* **Existing database** -- `DatabaseSchemaMixin.ensure_handsactions_columns`
  runs on the next connection (from `ensure_feature_tables`, alongside the
  HudCache / HandsPlayers / Hands upgrades) and `ALTER TABLE`s the missing
  columns in. It is additive and best-effort: no data is rewritten, an old row
  reads back with the new columns empty, and a lock race is retried on the next
  connection rather than blocking the GUI. `DB_VERSION` is deliberately *not*
  bumped -- that flag means "recreate the tables and reimport everything", and
  nothing here requires it.
* **Rebuild path** -- a database upgraded in place has events only for the hands
  imported after the upgrade. Filling the history in means re-importing those
  hands (they are the same derived values, deterministically:
  `tests/test_analytics_golden_datasets.py` imports the corpus twice and asserts
  the two passes agree). Re-deriving events in the database, without the hand
  text, is the job of the rebuild/backfill tooling in #305, which owns
  versioning the derived data and knows how to schedule a full pass; it is not
  attempted here.

## What is deliberately not here

* **Situations** ("facing a 3-bet as the opener, in position, 100bb") -- #294.
  This model has the facts; naming the situation is a rule over them.
* **Board texture and runouts** -- #295.
* **Sizing buckets** -- #296. `sizingBp` is the raw measurement; the buckets cut
  it, and scenario `17_bet_sizing` has one hand per default bucket to cut.
* **Profitability** -- #300, which needs the event row joined to `HandsPlayers`.

## What the tests check

`tests/test_action_events.py`:

* the vocabulary, the DDL of all three backends, the in-place upgrade and the
  insert agree column for column, and the insert actually executes;
* every golden hand converts, in parser order, with dense `actionNo` and
  `streetActionNo` restarting per street;
* the pot is a running total: each event starts from the pot the previous one
  ended, and grows by exactly what that action put in;
* the deepest `potAfter` of a hand equals its final pot plus the uncalled bet,
  where the uncalled bet is read from the hand history **text**, not from
  `DerivedStats` -- an independent witness that no action was dropped or double
  counted;
* `sizingBp` equals the aggregate column the HUD already averages
  (`val_*_bet_made_bp`, `val_*_raise_made_bp`) for the same player and street,
  and `sprBefore` equals `val_*_spr` at street entry, so the event cannot
  disagree with the aggregates it replaces;
* the poker per spot: open, limp vs over-limp (the `callerCount` the pipeline
  never had), iso-raise, 3-bet, squeeze, 4-bet, 5-bet all-in, c-bet,
  check-raise, probe, barrel, river bet, three-way, all-in before the river;
* the cases the corpus does not contain, hand-built: antes as dead money, a live
  straddle, stud's bring-in, an all-in who cannot act behind, a player with no
  derived position, an unknown room-specific action word, a bomb-pot seed, and a
  hand with no actions at all.
