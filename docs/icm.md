# ICM in fpdb

The Independent Chip Model turns tournament chips into prize equity. fpdb uses the
Malmuth-Harville form: a player finishes first with probability *their stack / all chips
in play*, and each later place is drawn the same way among the players still in. The
engine is `fpdb_3_legacy/icm.py`. What remains of #446 is the AoF analysis and an ICM line in
the tournament graph.

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

`TourneyPayouts` is a feature table: databases from before it get it on connection,
with no `DB_VERSION` bump. Amounts are in hundredths, like fpdb's winnings.

Two summary-import bugs currently keep some results from settling a structure: dollar
winnings read as 0 (#624), and a PokerStars.EU SnG stored with the wrong buy-in and
prize pool (#625).

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
