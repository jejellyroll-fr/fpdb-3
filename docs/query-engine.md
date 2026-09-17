# Composable stat/filter query engine (#297)

## What it is

The analytics layers below this one answer fixed questions. The event model
(#293) stores what happened, the situation model (#294) names the spot, the
board features (#295) classify the texture, and the sizing buckets (#296)
sort the sizings. None of them can answer a question nobody anticipated.

`fpdb_3_legacy/analytics_query.py` is the layer that can: a **metric**, a
dict of **filters** and a list of **dimensions**, composed at call time and
compiled to parameterized SQL. A new stat is a new combination, not a new
Python function and a new SQL string.

```python
from fpdb_3_legacy.analytics_query import Query, run_query

result = run_query(db, Query(
    metric="fold_frequency",
    filters={
        "street": "flop",
        "pot_type": "single_raised",
        "role": "defender",
        "in_position": True,
        "board_rank": "ace-high",
        "facing_sizing_pct": [25, 40],
    },
    group_by=["response"],
))
```

## The three pieces

### Filters

A filter names a condition on one of the joined tables and carries its own
SQL translation. Filters AND together; a value of `None` is ignored, so a
form can pass an unset field without branching. Values are always bound as
parameters.

| Filter | Reads | Kind |
| --- | --- | --- |
| `site` | `Sites.name` | set |
| `game` | `Gametypes.category` (`holdem`, `omaha`, …) | set |
| `limit` | `Gametypes.limitType` (`nl`, `pl`, `fl`) | set |
| `currency` | `Gametypes.currency` | set |
| `tournament` | `Hands.tourneyId` (`False` = ring game) | null check |
| `big_blind`, `stake_bb` | `Gametypes.bigBlind`, cents | range |
| `seats` | `Hands.seats` | range |
| `max_seats` | `Gametypes.maxSeats` | range |
| `session` | `Hands.sessionId` | set |
| `hand_id` | `HandsActions.handId` | set |
| `hand_id_from`, `hand_id_to` | `HandsActions.handId` | bound |
| `date_from`, `date_to` | `Hands.startTime` | bound |
| `player`, `players` | `Players.name` | set |
| `identity` | `(Sites.name, Players.name)` pairs | set of pairs |
| `hero` | `HandsSituations.isHero` | bool (see below) |
| `position` | `HandsActions.position` (codes or names: `BTN`, `CO`, `SB`, `BB`, …) | set |
| `opponent_position` | `HandsSituations.facingPosition` | set |
| `relative_position` | `HandsActions.relativePosition` (players left to act) | range |
| `in_position` | `HandsActions.inPosition` | bool |
| `effective_stack_bb` | `HandsActions.effectiveStackBB` (100 = 1bb) | range |
| `stack_bucket` | `HandsSituations.stackBucket` (`short`, `medium`, `deep`, `very_deep`) | set |
| `spr` | `HandsActions.sprBefore` | range |
| `players_in_hand` | `HandsActions.playersInHand` | range |
| `multiway` | `HandsSituations.multiway` | bool |
| `street` | `HandsSituations.streetName` (`preflop`, `flop`, `turn`, `river`) | set |
| `pot_type` | `HandsSituations.potType` (`unopened`, `limped`, `single_raised`, `three_bet`, `four_bet_plus`) | set |
| `pot_before`, `to_call`, `pot_odds_bp` | event / situation columns | range |
| `role` | `HandsSituations.role` (`aggressor`, `defender`, `passive`) | set |
| `is_aggressor`, `is_preflop_aggressor`, `is_previous_aggressor` | situation flags | bool |
| `in_position_vs_facing`, `in_position_vs_previous_aggressor` | situation flags | bool |
| `facing_all_in` | `HandsSituations.facingAllIn` | bool |
| `action_taken` | `HandsActions.actionType` (`bets`, `raises`, `calls`, `folds`, `checks`, …) | set |
| `action_faced` | `HandsActions.facingActionType` | set |
| `response` | `HandsSituations.response` (`fold`, `call`, `raise`, `bet`, `check`, `complete`) | set |
| `all_in` | `HandsActions.allIn` | bool |
| `situation` | `HandsSituations.labels` (JSON list; `open_raise`, `facing_cbet`, `three_bet`, …) | label |
| `primary_situation` | `HandsSituations.primaryLabel` | set |
| `situation_group` | `HandsSituations.groupName` | set |
| `enum_key`, `enum_response` | situation enum columns | set |
| `sizing_bp`, `facing_sizing_bp` | `HandsActions.sizingBp` / `facingSizingBp` | range |
| `bet_sizing_pct`, `facing_sizing_pct` | the same columns, written in % of pot | range |
| `board_rank`, `board_suit`, `board_pairing`, `board_connectivity` | `BoardFeatures` words | set |
| `board_texture`, `board_texture_all` | `BoardFeatures.textureMask` flags (any / all) | flag set |
| `board_runout` | `BoardFeatures.runoutMask` flags | flag set |
| `board_street` | `BoardFeatures.street` (1 = flop) | range |

Position names are the hand viewer's: `BTN`/`BU`/`D` → 0, `CO` → 1, `HJ` → 2,
then `LJ`, `MP`, `UTG`; the blinds are `SB` → −1 and `BB` → −2.

A range is `[low, high]`, inclusive, either end optional as `None`, or a dict
`{"min": …, "max": …}`. A percentage filter is converted to basis points on
the way in, so `bet_sizing_pct=[25, 40]` and `sizing_bp=[2500, 4000]` compile
to the same query.

### Metrics

A metric says what to compute over the filtered population. Every result row
carries the numerator, the denominator and — when the metric is a frequency —
the rate.

| Metric | Value | Unit |
| --- | --- | --- |
| `opportunities` | `COUNT(*)` over the filtered population | count |
| `hands` | `COUNT(DISTINCT HandsActions.handId)` | count |
| `players` | `COUNT(DISTINCT HandsActions.playerId)` | count |
| `action_count` | `COUNT(*)` of the rows matching the query's `numerator` | count |
| `frequency` | numerator / denominator, both returned | bp |
| `fold_frequency`, `call_frequency`, `raise_frequency`, `bet_frequency`, `check_frequency` | `frequency` with the numerator already supplied | bp |
| `average_sizing` | mean `sizingBp` over rows with a size | bp |
| `average_facing_sizing` | mean `facingSizingBp` over rows with a size | bp |
| `average_spr` | mean `sprBefore` (centi-SPR) | centi |
| `average_pot` | mean `potBefore` | cents |
| `total_profit` | summed `HandsPlayers.totalProfit` | cents |
| `profit_per_opportunity` | that sum divided by the decision count | cents |
| `all_in_ev` | summed `HandsPlayers.allInEV` | cents |
| `ev_per_opportunity` | that sum divided by the decision count | cents |

Three conventions make the numbers mean something:

* **A population metric is a distinct count, not the row count.**
  `opportunities` counts decisions, `hands` and `players` count what those
  decisions came from; on a 30-hand corpus that is 326 / 30 / 6, and reading
  the last two as "the sample" is exactly the mistake they exist to prevent
  ([cohorts and sample sizes](cohorts.md)).
* **`hero: False` keeps decisions whose situation is unknown.** Excluding the
  hero is how a *population* is built, so the filter is
  `(isHero IS NULL OR NOT isHero)`: the situation join is a `LEFT JOIN`, and an
  actor the database cannot classify is not the hero. `hero: True` still
  requires the situation row.
* **A frequency always carries its sample.** A row is
  `{opportunities, actions, value, frequency_bp}` — the denominator, the
  numerator, the numerator again and the rate — so "folds 40%" can never be
  shown without the "of 250" behind it.
* **Profit is per hand, not per decision.** Money metrics sum over the
  *distinct* `(handId, playerId)` pairs the filters select, so a player who
  made three decisions in one hand does not have their hand profit counted
  three times. `profit_per_opportunity` then divides by the decision count,
  which is what "per opportunity" reads as.

The denominator for a money metric is still the decision count of the
population; the numerator is the money. A caller who wants profit per
*hand* can group by `hand_id` through the drill-down instead.

### Dimensions

Grouping uses the same vocabulary as the filters:

`street`, `position`, `opponent_position`, `relative_position`, `in_position`,
`stack_bucket`, `effective_stack_bb`, `spr`, `pot_type`, `role`, `response`,
`action_taken`, `action_faced`, `all_in`, `multiway`, `player`, `site`,
`game`, `limit`, `tournament`, `session`, `sizing_bucket`,
`facing_sizing_bucket`, `board_rank`, `board_suit`, `board_pairing`,
`board_connectivity`, `primary_situation`, `enum_key`.

`sizing_bucket` and `facing_sizing_bucket` reuse #296's `CASE` expression, so
a histogram from the database and one from Python group by exactly the same
boundaries. Results are ordered by the dimensions, which makes a page stable.

## Running a query

```python
result = run_query(db, Query(metric="fold_frequency", filters={...}, group_by=["position"]))
for row in result.as_dicts():
    print(row["position"], row["actions"], "/", row["opportunities"], row["frequency_bp"])
```

`run_query` uses the connection's placeholder style, so the same `Query`
works on MySQL, PostgreSQL and SQLite. `compile_query(query, placeholder,
backend)` returns the statement without executing it, for a caller that wants
to run it elsewhere or show it.

### Drill-down

`run_hand_ids(db, query)` returns the distinct hand ids behind a population,
ordered, with `limit`/`offset` for paging. By default it returns the
*denominator* — the hands the metric was computed over ("these 26 hands, of
which 15 folds"); pass `include_numerator=True` to narrow to the hands where
the numerator fired.

### Explainability

A compiled query carries its SQL, its bound parameters and a readable
description:

```
metric: fold_frequency
filters: pot_type='single_raised', street='flop'
numerator: response='fold'
group_by: response
```

`CompiledQuery.as_dict()` returns the same as a JSON-friendly payload, which
is what a report or the research browser (#303) can show beside a result.

## SQL safety and backend neutrality

* **Values are bound, never interpolated.** Every filter value goes through
  the backend placeholder. A value containing quotes, semicolons or `--` is a
  parameter, not syntax.
* **Identifiers come only from the registries.** Filter, metric and dimension
  names are looked up in tables in this module; an undeclared name raises
  `ValueError` before any SQL is built. There is no code path where user text
  becomes a column, table or clause.
* **Backend differences are isolated to two spots**: the placeholder
  (`%s` vs `?`) and the boolean literal (`TRUE` vs `1`), both chosen from an
  explicit `backend` argument.
* **Every condition names its own sources.** A filter, a `group_by` dimension
  and the query's `numerator` each contribute the joins they read, so
  `fold_frequency` with no street filter still joins `HandsSituations` for its
  implied `response` numerator — a condition on an unjoined alias is invalid
  SQL, not a missing join to discover at run time.

## Tests

`tests/test_analytics_query.py` walks the acceptance criteria in order:

* filters compose, ranges are inclusive and open-ended, names resolve, and an
  unknown filter, metric, dimension or backend is refused;
* metrics return both sides of a frequency, money metrics sum distinct
  hand-players, and the implied numerators match the explicit ones;
* grouping partitions the population exactly (the two-dimension split
  recomposes into the one-dimension totals);
* hand ids match the population and paginate;
* hostile values are bound, not executed, and the `Hands` table survives;
* and where a query overlaps an existing predefined stat —
  `fold_frequency` over flop c-bets versus `HudCache.foldToStreet1CBDone` —
  the two agree for every player except the hand the golden corpus already
  documents as a deviation (`fold_to_cbet_counts_a_raise_as_cbet`). The
  engine re-derives the predicted answer and surfaces the known wrong one.

## Where this goes

The engine is the substrate for the rest of Phase 2:

* **#306** layers a declarative stat/filter DSL on top — named stat
  definitions instead of raw dicts.
* **#304** adds aggregate caches, indexes and query profiling for large
  databases; the compiled SQL is where those hooks attach.
* **#307** builds player populations and cohorts as reusable filter sets
  ([cohorts.md](cohorts.md)) — the `hands`/`players` metrics, the `identity`
  filter and the `hero` semantics above are what that layer stands on.
* **#303** renders a result and its drill-down hands in the research browser.
