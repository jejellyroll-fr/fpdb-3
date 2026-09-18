# Cohorts: player populations and comparison groups (#307)

Every stat before this layer was asked *about a player*. A **cohort** asks it
about a group: all opponents, the regulars, one room, one stake, a set of tagged
players, a linked identity, the last 90 days versus the 90 before it.

A cohort is a **reusable saved filter object**, never a copy of hand ids. That
one decision is what makes the rest cheap: adding a hand to the database cannot
invalidate a cohort, and a cohort stays meaningful after an import, a rebuild
(#305) or a re-import.

## The object

```python
from fpdb_3_legacy import analytics_cohorts as cohorts
from fpdb_3_legacy.analytics_query import Query

cohort = cohorts.get_registry().get("nlhe_6max_opponents")

# What it resolves to -- explicit and inspectable, hero exclusion included:
cohort.resolved_filters()
# {'game': ['holdem'], 'limit': ['nl'], 'max_seats': [6, 6], 'hero': False}

# Compose it with any other analytics filter:
applied = cohort.apply({"street": "flop", "pot_type": "single_raised"})
applied.filters          # the merged filter dict
applied.overridden        # ('street',) if the caller's own filter won
applied.query(metric="fold_frequency", group_by=("position",))
```

`Cohort.apply` lets the **caller's** filters win on a collision and returns the
names it overrode, so a cohort never silently changes an explicit request.
`Cohort.combine` intersects two cohort definitions and *refuses* when they
disagree on a filter (`stakes(50).combine(stakes(200))` is an error, not a coin
toss).

## Population sources

| Source | Filters it contributes |
| --- | --- |
| `all_opponents()` | `hero: False` |
| `players([...])` | `player: [...]` |
| `linked_identities(config)` | `identity: [(site, alias), ...]` |
| `sites([...])` | `site: [...]` |
| `stakes(cents)` / `stakes((low, high))` | `big_blind` (in **cents**, the engine's unit) |
| `table_size(seats)` | `seats` |
| `date_window(days, offset_days=0)` | `date_from` / `date_to`, resolved at query time |
| `regular_tables_only()` | `tournament: False` |

A saved cohort can also carry `window_days` (and `window_offset_days`), which
resolves against "now" when it is applied. That is why `last_90_days` is a
*saved* cohort and not a frozen pair of dates: it does not go stale. Tests pass
an explicit `reference=` date, so the resolution is deterministic without
freezing it in the file.

## Hero exclusion

Hero exclusion is a field on the cohort (`exclude_hero`), not a filter dict that
happens to mention `hero`, so it is visible in `resolved_filters()`, in
`as_dict()`, in `--show`, and in the SQL.

It compiles to the engine's `hero: False`, whose semantics are precise:

* it drops the decisions whose **actor** is the hero;
* an opponent's decision in a hand the hero played is still an opponent
  decision, and stays;
* a decision whose situation row is missing is **kept** -- the situation join is
  a `LEFT JOIN`, and "we do not know this actor" is not "this actor is the
  hero". (`hero: True` still requires the situation row.)

On the golden corpus that is 341 decisions total, 69 by the hero, 272 by the
population -- and the two add up, which is the test.

A *comparison* requires both sides to agree on hero exclusion:
`comparison_group(a, b)` refuses an "all opponents" versus "everyone including
hero" pair, because that comparison measures the hero, not the cohorts.

## Weighting, and why it is explicit

A frequency pooled over decisions is not the mean of the players' frequencies:
a regular with 900 decisions should not outweigh a stranger with 9, unless you
say so. The caller chooses.

| `weighting` | What the number means |
| --- | --- |
| `decision` (default) | Every decision in the population is one observation -- "what happens in a typical spot between these players". Pooled numerators over denominators, so a breakdown by position cannot swing the answer the way an unweighted mean would. |
| `player` | The mean of the players' own values, each player one vote -- "what does a typical player in this population do". |

```python
by_decision = cohorts.population_stat(db, query, cohort)
by_player = cohorts.population_stat(db, query, cohort, weighting="player", min_player_sample=20)
by_player.players_used      # players with at least 20 decisions
by_player.players_skipped   # and how many were left out
by_player.per_player        # the breakdown the mean came from, always available
```

`min_player_sample` is the sample a rate needs before it is a rate, and which
players were **used** and which were **skipped** is part of the result -- a mean
over four regulars cannot pass for a population.

Money *totals* (`total_profit`, `all_in_ev`) and raw counts are refused for
`player` weighting: an average of averages of money answers no question anyone
asks. Rates (`profit_per_opportunity`, `ev_per_opportunity`) are allowed.

## Sample sizes

A sample size is three numbers, and all three are reported:

```python
sample = cohorts.population_sample(db, cohort.apply())
sample.decisions   # the engine's native denominator
sample.hands       # how many hands those decisions came from
sample.players     # and how many distinct players
```

"1,200 opportunities" hides whether that is 40 players or one. Every
`PopulationStat` and every comparison row carries its sample, so a cohort's
frequency can never be displayed without the population behind it.

## Comparing two populations

```python
comparison = cohorts.compare_cohorts(db, Query(metric="fold_frequency", filters={"street": "flop"}),
                                     last_90_days, previous_90_days)
print(cohorts.format_comparison(comparison))
# metric: fold_frequency (weighting: decision)
# filters: street='flop'
#   last_90_days: 56.66% [30 decisions, 26 hands, 3 players]
#   prior: 0.00% ...
#   delta (b - a): +23.34 pp
```

The same `query` object measures both sides, so a difference can only come from
the cohorts. Deltas are in percentage points for rates and in the metric's own
unit otherwise.

## Saving and editing cohorts

Cohorts are data: `fpdb_3_legacy/analytics_cohorts.d/*.json`, a `schema_version`
and a list of cohorts. A cohort may name only what the engine knows -- an
unknown filter is a `ValueError` naming the field and listing what is allowed --
and there is no SQL, `eval` or Python in a file, so an untrusted `.json` is safe
to load. A file written for a newer schema is refused rather than
half-understood.

```python
registry = cohorts.load_default_registry(["~/my_cohorts"])
registry.save(cohort, "~/my_cohorts/mine.json")   # validated before it is written
cohorts.load_cohorts("~/my_cohorts/mine.json")    # a round trip, by construction
```

```bash
python tools/cohorts.py --list
python tools/cohorts.py --show all_opponents
python tools/cohorts.py --dir ~/my_cohorts --validate
python tools/cohorts.py --cohort all_opponents --metric fold_frequency --filter street=flop
python tools/cohorts.py --compare last_90_days previous_90_days --metric fold_frequency \
    --filter street=flop --weighting player --min-player-sample 20
python tools/cohorts.py --cohort grinders --filter site=PokerStars --save ~/my_cohorts/grinders.json
```

`--save` is the only write, and it validates what it writes.

## For the research browser (#303)

The browser's cohort selector needs the registry (`load_default_registry`,
`load_directory`, `CohortRegistry.save`), the inspectable rendering
(`format_cohort`, `Cohort.as_dict`) and the two entry points:
`Cohort.apply(...).query(...)` for a breakdown, and `population_stat` /
`compare_cohorts` for the population-level number and its sample.

## What this layer does not do

* **Cohorts are filters, not player lists.** Nothing is materialised, so
  nothing needs invalidating after an import.
* **A "tagged players" population reads the selected names.** There is no
  player-tag table in the schema; if one is added, it becomes one more source
  constructor over the same filter dict.
* **Cross-site identity is a `(site, alias)` filter, not a name.** The engine's
  `identity` filter is an OR of `(site, name)` pairs precisely because the same
  screen name on two rooms is two different people.
* **Hand-weighted pooling is not offered.** The stored rows are decisions, so
  `decision` and `player` are the two weightings that exist; the distinct-hand
  count is reported alongside so a consumer can see the denominator they are
  not using.
