# ICM in fpdb

The Independent Chip Model turns tournament chips into prize equity. fpdb uses the
Malmuth-Harville form: a player finishes first with probability *their stack / all chips
in play*, and each later place is drawn the same way among the players still in. The
engine is `fpdb_3_legacy/icm.py`. It prices a hand's all-in in the replayer, adds an ICM line to
the tournament graph, and gives the tournament study pack a bubble factor band.

The AoF analysis gets no ICM: All-in or Fold is a cash format in every room fpdb reads it
from (GGPoker's AFO tables, CoinPoker's and KingsClub's AoF games), so its hands carry no
prize equity to price.

## Where a tournament's payouts come from

ICM needs what each place pays. `fpdb_3_legacy/tourney_payouts.py` answers
`payouts_for_tourney(db, tourney_id)` and `payouts_for_hand(db, hand_id)` from three
sources, in this order:

1. **A structure stored for the tournament**, in the `TourneyPayouts` table: one entered
   by hand (`store_payouts`), or a preset applied to its prize pool (`apply_preset`).
   Presets: `winner_take_all` (heads-up, most Spins), `sng_6max` 65/35, `sng_9max` and
   `sng_10max` 50/30/20, `sng_18max` 40/30/20/10, and `double_or_nothing`. The prize
   pool is split to the hundredth, so the amounts always add up to it.
2. **The tournament's results**, when an imported summary settles every paid place:
   the winnings of places 1..k, and proof that place k+1 pays nothing (a known place
   k+1 that won nothing, or a field of exactly k entries). A summary of the hero alone
   settles nothing. Knockout tournaments are never read this way, because their
   winnings include bounties.
3. **Otherwise, nothing**, and the lookup says why. No structure is ever guessed.

### Entering a structure

The replayer's **Payouts...** button, on a stored tournament hand, opens the tournament's
structure (`fpdb_3_legacy/tourney_payouts_dialog.py`). It shows the field, the prize pool,
the structure in use and where it comes from. From there you can:

- **apply a preset** to the prize pool. When the pool is unknown, the preset applies to
  buy-in × entries, with any knockout bounty taken out;
- **paste the lobby's payouts**, first place first. Put one place per line, in which case
  a leading rank (`1`, `#1`, `1st`, `1.`) is skipped and the last number of each line is read,
  so `1st  $1,250.00`, `1 500.00` or `2: 30%` all work and a decimal comma is fine. A single
  labelled line such as `1st $45.00` is one paid place. Or put them on one line separated by spaces, commas or semicolons,
  with decimal points. The places are either all prizes in currency units, or all
  percentages of the prize pool adding up to 100 (`parse_structure`, `store_entered`);
- **forget the stored structure**, to go back to the imported results.

The hand is priced again as soon as the structure changes.

`TourneyPayouts` is a feature table: databases from before it get it on connection,
with no `DB_VERSION` bump. Amounts are in hundredths, like fpdb's winnings.

One summary-import bug keeps some results from settling a structure: a PokerStars.EU SnG
stored with the wrong buy-in and prize pool (#625). Dollar winnings read as 0 (#624) are
fixed; summaries imported before the fix need importing again.

## A hand's all-in, in the replayer

`fpdb_3_legacy/hand_icm.py` prices a tournament hand's all-in. The replayer shows the result
under its summary as soon as the hero is all-in. For each of the two players, it computes:

- **equity** when the money went in, on the board known at that street: wins, losses and
  ties, with a split pot as its own outcome;
- **chip EV**: that equity's share of the pot, less what the player put in, as the import's
  `allInEV` computes it;
- **ICM $EV**: the prize equity expected after the hand, less the prize equity the stacks
  held when it began;
- **ICM result**: the prize equity the hand actually moved. $EV and result therefore read
  side by side, like chip EV and winnings.

A hand is only priced when its numbers are sound; otherwise the replayer says why:

- **heads-up only**: a multiway all-in has side pots and more outcomes than this prices yet, and so does a side pot
  one of the two cannot win (a short stack all-in, then a deeper player folding);
- **flop games, one winner per pot**: stud and draw are outside the equity engine, and hi/lo
  split pots are not priced yet;
- **both hands shown**;
- **a payout structure known** for the tournament (see above);
- **every remaining player's stack**: the players at the table must be the whole field.
  - A single-table tournament is priced as is.
  - A field larger than the table is refused, because the other tables' stacks are unknown.
  - When the field size is unknown (no summary imported), the hand is priced and the line
    says that this table was taken as the whole field.

## The tournament graph's ICM line

The tournament graph's **ICM $EV-adjusted line** option (`fpdb_3_legacy/tourney_icm_line.py`)
draws the results with the all-in luck taken out. For each hand where the hero saw a
showdown after someone was all-in, the luck is the prize equity the hand actually moved
less its ICM $EV, priced as the replayer prices it. The line is the profit less that luck,
tournament after tournament.

It adjusts only what is priced. A tournament with no known payout structure, and an all-in
the pricing refuses, keep their actual result. The legend says how many of the hero's
all-ins were priced: a line that priced 3 all-ins out of 40 is mostly the profit line.

The option is off by default, because it rebuilds and prices every all-in hand of the
graph's tournaments. Each hand is priced once per payout structure while the tab is open.
Equity is the replayer's Monte Carlo estimate (20,000 boards), so the line can move by a
few cents between two runs.

## Bubble factors in the study pack

The tournament study pack's two all-in studies (facing an all-in, shove spots) have a
**By bubble factor** panel, and `bubble_factor_bucket` is a filter and breakdown in the
Research Browser. A preflop decision's bubble factor says how much more prize equity
an all-in risks than it wins. It comes from the stacks at the start of the hand,
priced against one opponent:

- **facing an action**: the player who made it (the shover, the opener);
- **first in**: whoever is still to act and makes the all-in most expensive, that is,
  the highest factor among them.

The bands are: 1.2 or less (close to chip EV), 1.2–1.5, 1.5–2, 2–3, 3 and over, and
*not known*.

Factors are stored only where fpdb knows every remaining stack and the structure:

- the tournament's payout structure is known (see above);
- its field size is known and fits at one table, as in a sit-and-go or a Spin.

A multi-table tournament's other tables are not in the hand history, so its decisions
read *not known*, as do postflop decisions and tournaments whose field size is unknown.

`ActionBubbleFactors` holds the factors, keyed like `HandsSituations`. It is a feature
table with derived rows, replaced a tournament at a time (`fpdb_3_legacy/bubble_factors.py`)
whenever:

- an import touches the tournament (hands or a summary);
- the replayer's payouts dialog changes its structure;
- `python tools/backfill_bubble_factors.py` runs. Run it once on a database imported before
  this feature.

## What the engine computes

| Function | Answers |
|---|---|
| `icm_equities(stacks, payouts)` | Each player's prize equity, in the payout's unit, in the order of `stacks`. `payouts[0]` is first prize. A player with no chips has finished and wins nothing more. |
| `outcome_equities(before, after, payouts)` | Each player's equity once a hand has ended. A player who busts in it takes the place right below the survivors, and collects that place's prize. The larger starting stack finishes higher, and equal starting stacks share their places' prizes. |
| `allin_icm_ev(before, outcomes, payouts, player)` | A player's ICM $EV for an all-in: expected equity after it (over its outcomes and their probabilities, from the equity engine) minus equity before. |
| `bubble_factor(stacks, payouts, player, opponent)` | Equity lost on losing an all-in against `opponent`, divided by equity gained on winning it. 1.0 is a chip-EV spot. A call needs `BF / (1 + BF)` equity. |

Stacks can be in any chip unit, since only their ratios count. Payouts can be in any
currency, or in fractions of the prize pool.

## How it is checked (`tests/test_icm.py`)

- **The classic 3-handed example**: stacks 5000/3000/2000 for 50/30/20. Worked out by hand
  with exact fractions, it gives **38.39 / 32.75 / 28.86**.
- **An independent brute force**: every order in which the paid places can be filled, each
  weighted by Harville's probability. It is checked on 6- and 9-handed tables, including a
  final table paying all nine places.
- **The properties any ICM must keep**, under `hypothesis`:
  - equities add up to the prizes left;
  - equal stacks get equal equity;
  - more chips never means less equity;
  - neither the chip unit nor the seat order changes anything;
  - nobody is worth more than first prize, or less than the last prize they are sure of.
- **Prize money is conserved**: after any all-in, survivors' equity plus the prizes of the players it busted add up to
  the prizes left before it. That is why a heads-up coinflip is worth exactly 0.
- **Winner-take-all is the chip share**, so its ICM $EV is the chip EV in prize terms, and
  its bubble factor is exactly 1.

## Cost, and the limit

The exact model works through every set of players still in the running when a prize is
awarded. With *n* players and *k* paid places, these are the sets with fewer than *k*
players gone. Each costs up to *n²* steps and is cached as *n* values. Sets past the last
paid place award nothing, so they are neither walked nor cached.

- A SNG, a Spin, a final table, or a large field paying few places is quick: 10 players
  paying all 10 places take about 2 ms, 45 players paying 3 take about 50 ms, and 1,000
  players paying 2 take about 0.1 s.
- A large field paying deep is not. `exact_cost(n, k)` gives the steps and cached values in
  advance. Beyond `MAX_WORK` (30 million steps, about a second) or `MAX_CELLS` (2 million
  values, about 64 MB), the engine raises `ICMTooLarge` before allocating anything, rather
  than answer slowly, approximately, or out of memory. A caller then shows "ICM not
  computed" for that spot, never a made-up number.

An approximation for large fields, such as Monte Carlo finishing orders or the top places
only, can come later behind the same functions, if a report needs one.
