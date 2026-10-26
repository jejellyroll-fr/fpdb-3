# ICM in fpdb

The Independent Chip Model turns tournament chips into prize equity. fpdb uses the
Malmuth-Harville form: a player finishes first with probability *their stack / all chips
in play*, and each later place is drawn the same way among the players still in. The
engine is `fpdb_3_legacy/icm.py`. Showing ICM in the application is the rest of #446:
payout structures, ICM $EV in the replayer and the AoF analysis, and an ICM line in the
tournament graph.

## What the engine computes

| Function | Answers |
|---|---|
| `icm_equities(stacks, payouts)` | Each player's prize equity, in the payout's unit, in the order of `stacks`. `payouts[0]` is first prize. A player with no chips has finished and wins nothing more. |
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
- **Winner-take-all is the chip share**, so its ICM $EV is the chip EV in prize terms, and
  its bubble factor is exactly 1.

## Cost, and the limit

The exact model visits every set of players that can still be in the running when a prize
is awarded. With *n* players and *k* paid places, that is C(n, 0) + … + C(n, k) sets.

- A SNG, a Spin or a final table costs nothing: 10 players paying all 10 places take about
  2 ms, and 45 players paying 3 take about 50 ms.
- A deep MTT field does not fit. Beyond about 1.1 million sets (`MAX_STATES`), the engine
  raises `ICMTooLarge` rather than answer slowly or approximately. A caller then shows
  "ICM not computed" for that spot, never a made-up number.

An approximation for large fields, such as Monte Carlo finishing orders or the top places
only, can come later behind the same functions, if a report needs one.
