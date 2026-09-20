# Analytics concepts, in plain words

A glossary for the user guides. Each entry is one paragraph and, where it helps,
a poker example. The implementation lives in the developer references linked at
the end — this page deliberately does not repeat it.

## opportunity
A chance to do the thing you are measuring. Folding to a flop c-bet has an
opportunity only when you *faced* a flop c-bet. **Opportunities are the
denominator of every frequency.**

## numerator
How many of those opportunities the action actually happened. If you faced 200
flop c-bets and folded 120, the numerator is 120.

## frequency
`numerator / denominator`. 120 of 200 is **60%**. A frequency is only meaningful
next to its sample: 3 of 5 is 60% too, and means nothing.

## population
*Who* the question is about. "Population" as a breakdown value usually means
*the opponents* — the pool you play against — as opposed to *hero*, so you can
compare your own numbers with the field's.

## cohort
A slice you define yourself — a named group of players or hands — used when you
want "how do these specific players behave", not "how does everyone behave".

## effective stack
The smaller of the two stacks still in the hand, because that is the most either
player can risk. A 200 bb stack against a 30 bb stack is a **30 bb** hand.

## SPR (stack-to-pot ratio)
The effective stack divided by the pot at the start of a street. SPR 1 means you
are committed; SPR 10 means there is room to manoeuvre. Computed **before** the
street's betting, never after.

## pot type
The shape the preflop betting left behind: **unopened** (nobody raised),
**limped** (only calls), **single-raised** (one raise), **three-bet** (a
re-raise), **four-bet-plus**. Most postflop questions mean something different in
each.

## IP / OOP (in position / out of position)
Who acts last on this street. *In position* acts after the other player; *out of
position* acts first. Being in position is worth money, which is why almost every
postflop preset can be broken down by it.

## sizing bucket
A band a bet size falls into — small, medium, large — using thresholds you
configure rather than fixed numbers. "Fold versus a flop c-bet, by bet size"
splits the answer across these bands.

## board texture
What the community cards look like: suit structure (rainbow / two-tone /
monotone), pairing, connectivity, whether an overcard fell. Textures change how
often people bet and fold, so they are a first-class breakdown.

## known / unknown cards
The database stores hole cards only when a hand went far enough to reveal them.
Views that need cards use **only the decisions whose cards are known**, and label
the result, so a range is never drawn from a half-known sample.

## realized profit
The money you actually won. It is a fact about what happened, including the times
you got it in behind and held.

## all-in EV / EV-adjusted result
The same hands valued at the moment the money went in, for all-in confrontations
only. It removes the luck of the runout from the total, and it is **not** the same
number as realized profit. Compare the two to see how much of a result was the
cards and how much was the running.

## conditional realized profit
Realized profit measured inside one spot — "profit per decision when facing a
c-bet" — rather than overall. It answers "does this spot pay", which a whole-hand
number hides behind everything else that happened.

## sample size
How many opportunities sit behind a number. The Research Browser shows it above
every result and refuses to colour a value that is below the threshold a preset
or a HUD cell asks for.

## Where the implementation lives

- [query-engine.md](query-engine.md) — metrics, filters, dimensions, compilation.
- [stat-definitions.md](stat-definitions.md) — declarative stats.
- [profitability-ev.md](profitability-ev.md) — the money semantics exactly.
- [situation-model.md](situation-model.md) and [hand-state.md](hand-state.md) —
  how a decision is classified.
- [board-features.md](board-features.md) and [sizing-buckets.md](sizing-buckets.md)
  — texture and size bands.
