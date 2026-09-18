# Profitability and EV reporting (#300)

The query engine (`docs/query-engine.md`) answers "how often". This layer answers
"for how much", and — more importantly — says which "for how much" it is. It is
`fpdb_3_legacy/analytics_profit.py`, driven by `tools/profit_report.py`.

```bash
python tools/profit_report.py --filter primary_situation=cbet --group-by sizing_bucket
python tools/profit_report.py --filter role=aggressor --group-by street --min-sample 10
python tools/profit_report.py --filter pot_type=three_bet --hand-ids
python tools/profit_report.py --filter hero=true --json
python tools/profit_report.py --semantics
```

## Four meanings of "profit", one of them refused

A hand history records what happened, once. That is enough for two of these and
not for a third.

| Name | What it is | Kind |
| --- | --- | --- |
| `realized` | The hand's final result, summed once per distinct (hand, player) pair in the filtered population: the money won or lost **in the hands where the filtered actions happened**. | hand result |
| `ev_adjusted` | The same hand-level money with the all-in pots marked to their equity. | hand result |
| `all_in_luck` | `realized - ev_adjusted`: what the cards gave beyond the priced all-in equity. | difference |
| `immediate_action_ev` | The chips the action itself wins or loses. | **not computable** |

`realized` is a **conditional hand result**, and calling it "the EV of a 3-bet"
would be wrong twice: the hand's outcome is decided by everything that happened
after the action too, and the hands that folded have no counterfactual range in
the file. `immediate_action_ev()` therefore raises `NotComputable` with the
reason, and `--metric immediate_action_ev` prints that reason and exits 2 —
there is no filter that makes the number exist.

The four definitions and their caveats live in `SEMANTICS` and travel with every
report (`--semantics`, and the `semantics` key of the JSON), so a consumer such
as the research browser (#303) can label a figure without restating it.

## Money is summed once per hand-player

The unit of money is the **hand**, not the decision. Every figure is summed over
the distinct `(handId, playerId)` pairs the filters select, so a player who makes
three filtered decisions in one hand contributes their hand result once.

That is not a detail — it is the difference between a number and a plausible
number. On the golden corpus (rake-free, so the whole 30-hand set is exactly
zero-sum), the naive sum over the 326 matching decision rows is **-29100** cents;
the report says **0**, and the six players' hand results add up to it (`Anna`
+20000, `Boris` +26500, `Cara` -11400, `Dave` -3000, `Erin` -6000, `Frank`
-26100). A per-decision attribution breaks the zero-sum identity that every
closed set of hands must satisfy, which is exactly how it is caught.

## All-in EV, kept apart

fpdb initialises `allInEV = totalProfit` and overwrites it only for the pots the
equity engine could price. `ev_adjusted` is therefore the same money with those
pots marked, and it is reported **next to** `realized`, never instead of it:

* on the whole corpus, `realized` is 0 and `ev_adjusted` is -40 cents, an
  adjustment that exists only because hand 15 had a priced all-in for two of its
  players (`ev_adjusted_pairs` says so: 2 of 180);
* `all_in_luck` is the difference, and it is labelled as a difference — adding it
  to a total, or reading it as a win rate, is meaningless.

A pair whose adjustment is exactly zero is either a hand that never went all-in
or a priced all-in that broke even; the stored columns cannot tell those apart,
so `ev_adjusted_pairs` is a floor on the all-in hands, not a count of them.

## Rake

Rake is charged to a hand, so it is attributed to the hand's players, not to the
action's group. fpdb stores three attributions of the same hand rake and they
disagree, so the report names which one it used:

| `--rake` | Column | Split by |
| --- | --- | --- |
| `dealt` | `rakeDealt` | everyone dealt in, evenly |
| `contributed` | `rakeContributed` | the players who put money in (the default) |
| `weighted` | `rakeWeighted` | what each player put in |

Every report carries all three; `rake_cents` is the chosen one, and the note says
which. A population with no rake is reported as such rather than as a zero that
might mean "missing".

## The sample, and the denominators

A money figure without its sample is a rumour, so each row carries three
denominators and each rate names the one it divides by:

* `opportunities` — decisions (the engine's denominator);
* `hands` — distinct hands that produced at least one of them;
* `players` — distinct players;
* `hand_players` — distinct (hand, player) pairs, which is what the money sums over.

`realized_per_hand_cents` divides by `hands`, `realized_per_opportunity_cents` by
`opportunities`, and `bb_per_100` by `hand_players` (the same thing as per hundred
hands when the population holds one player per hand). `--min-sample N` flags the
rows below the threshold with `*` instead of hiding them: a small sample is
information, and hiding it is how a 1-decision bucket gets quoted as a win rate.

## Big blinds

`bb_profit` is `Σ profitᵢ / bigBlindᵢ` over the pairs, so mixed stakes are
comparable, and `bb_per_100` scales it. The big blind lives on the game type, and
fixed-limit rows store `-1` there — a division that would flip the sign of a
result. Pairs without a usable stake are excluded, `bb_pairs` counts the rest, a
note reports the difference, and a population with none at all reports `None`
rather than a number.

## Splitting by action, sizing or texture

`--group-by` uses the engine's dimensions, so a report can be split by street,
position, role, response, pot type, stack bucket, sizing bucket (#296), board
texture (#295) or any other dimension, and filtered with everything the engine
filters on.

**The rows overlap by design.** A hand-player is counted in every group their
actions fall into, so grouping by a decision attribute partitions *decisions*, not
money: on the corpus, the c-bet buckets touch 23 pairs for a 21-pair population
and report 21700 cents for a 16900-cent total. The report says so in a note and
in `overlapping_groups`, and `total` always comes from a separate ungrouped
statement — never from adding the rows up. A dimension that is a property of the
hand-player (position, player, site) does partition the money, and the tests
assert both behaviours separately.

## Drill-down

`report.hand_ids` lists the hands behind the population, and `narrow_query(query,
group)` turns one row back into a query of its own — a group's value *is* a filter
value, which is why every reportable dimension has a filter of the same name
(including `sizing_bucket` / `facing_sizing_bucket`, added here so a bucket can be
opened as hands). A dimension without a filter is refused by name instead of
silently returning the whole population. `--hand-ids` prints the ids at the shell;
the hand viewer is the consumer.
