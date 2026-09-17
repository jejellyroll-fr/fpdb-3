# Declarative stat and filter definitions (#306)

## What it is

The query engine (#297) lets a new question be asked at call time — a metric,
a dict of filters, a list of dimensions. This layer lets the question be
**stored**: `fpdb_3_legacy/analytics_definitions.py` loads a stat as data
(JSON, or YAML when PyYAML is installed), validates it before anything runs,
and compiles it into exactly the `Query` the engine already executes.

A definition keeps three things apart on purpose:

| Part | Fields | Role |
| --- | --- | --- |
| Query semantics | `metric`, `filters`, `numerator`, `group_by` | the whole meaning of the stat |
| Display metadata | `label`, `description`, `format`, `precision`, `min_sample`, `category`, `tags` | presentation only; never changes which rows the metric sees |
| Reuse | `fragments` | named filter bundles shared between definitions |

```json
{
  "name": "fold_to_3bet_preflop",
  "metric": "fold_frequency",
  "fragments": ["preflop", "facing_3bet"],
  "label": {"en": "Fold to 3-bet (preflop)", "fr": "Fold face au 3-bet (préflop)"},
  "format": "percentage",
  "min_sample": 5,
  "category": "Preflop defence"
}
```

## Vocabulary

A definition writes the issue's prose, not the schema. Names are resolved
through registries in the module, and anything unknown is a `ValueError` naming
the field and listing what is allowed.

**Metrics** — the engine's names plus shorthand: `action_frequency` →
`frequency`, `sample_size` / `opportunity_count` → `opportunities`, `count` →
`action_count`, `profit` → `total_profit`, `ev` → `all_in_ev`,
`mean_sizing` → `average_sizing`. The `*_frequency` metrics already carry
their numerator.

**Filters** — every engine filter (see `docs/query-engine.md`), with a few
name aliases (`game_type`, `tourney`, `blind_level`, `stake`) and value
shorthand that is resolved case-insensitively:

| Filter | Shorthand → stored |
| --- | --- |
| `pot_type` | `SRP` → `single_raised`, `3BP` → `three_bet`, `4BP` → `four_bet_plus` |
| `role` | `PFR` → `aggressor`, `PFC` / `caller` → `defender` |
| `game` | `NLHE` → `holdem`, `PLO` → `omaha` |

`position` and `opponent_position` accept the hand viewer's names (`BTN`,
`CO`, `SB`, `BB`, …) directly, because the engine already does.

**Dimensions** — the engine's names plus `bet_size_bucket` / `sizing` →
`sizing_bucket` and `board_texture` → `board_suit`.

## Reusable filter fragments

`fragments` names a bundle of filters written once and shared. The built-in
library includes `ring`, `tournament`, `preflop`, `flop`, `turn`, `river`,
`unopened_pot`, `limped_pot`, `single_raised_pot`, `three_bet_pot`,
`in_position`, `out_of_position`, `pfr`, `pfc`, `facing_3bet`, `facing_4bet`,
`facing_cbet`, `facing_raise`, `short_stack`, `deep_stack`.

A fragment may reference other fragments through its own `fragments` key; a
cycle is refused. When a fragment and the definition set the same filter, the
**definition wins**, so `{"fragments": ["single_raised_pot"], "filters":
{"pot_type": "three_bet"}}` is a three-bet pot.

A registry can add fragments (`add_fragment`) for an application's own
vocabulary.

## Formats

| Format | Meaning | Precedence |
| --- | --- | --- |
| `percentage` | rate in percent | zero decimal places |
| `count` | integer | zero |
| `bb` | cents divided by the big blind | two |
| `currency` | cents as currency units | two |
| `decimal` | plain number | two |
| `ratio` | plain number | two |

`precision` overrides the default. A `percentage` renders the row's
`frequency_bp`, not its raw value, so a frequency definition never shows the
numerator as if it were the rate.

`min_sample` is the threshold below which the value is not shown (`-`). A rate
on three hands is noise, and a definition is where that rule belongs.

`label` and `description` may be a plain string or a mapping of locale to
text; lookup falls back to English, then to any value.

## The bundled library

`fpdb_3_legacy/analytics_definitions.d/core.json` ships four definitions that
work on the golden corpus out of the box — two preflop
(`fold_to_3bet_preflop`, `preflop_raise_frequency_by_position`) and two
postflop (`fold_to_cbet_flop`, `fold_to_cbet_flop_by_size`).

## Consuming a definition

```python
from fpdb_3_legacy.analytics_definitions import build_report, get_registry, run_definition

definition = get_registry().resolve("fold_to_cbet_flop")

# One result (a popup, narrowed to the player at the table):
result = run_definition(db, definition, {"player": "Cara"})

# A report (localized labels, formatted values, grouped rows):
for entry in build_report(db, get_registry().all(), locale="fr"):
    print(entry["label"], "=", entry["value"], "(n =", entry["opportunities"], ")")
```

`to_query(context)` and `compile_definition(...)` expose the compiled #297
query for a caller that wants to run it elsewhere or show it.

`context` is extra filters supplied at call time — a popup's player, a research
window's date range — merged *over* the definition's own filters, so a caller
can narrow a stat without editing it.

Adding a new filter-based stat is adding a definition: no `Stats.py` change,
no Python. The bundled library is loaded from disk, and an application can
point the registry at its own directory.

## Schema versioning

Every definition and every file may carry a `schema_version` (default 1). A
definition or file written for a newer schema than the code understands is
refused, rather than silently half-understood. Bumping
`DEFINITION_SCHEMA_VERSION` is a compatibility claim: older definitions keep
loading unchanged.

## Security

A definition names things that already exist; it cannot compute or execute.

* No `eval`, no SQL text, no Python. Unlike the column-oriented
  `StatDescriptor` (which has a sandboxed arithmetic `value`), a filter
  definition has no expression field at all — `value` is rejected as an
  unsupported field.
* Unsupported fields, filters, metrics, dimensions, formats and fragments are
  refused with a message that lists the allowed values.
* Every filter value becomes a bound parameter in the compiled SQL; a value
  containing quotes or `--` is data, never syntax.

## Tests

`tests/test_analytics_definitions.py` covers parsing (single object, list,
`stats` list, directory, suffixes, YAML presence/absence), validation of every
unsupported field, schema versioning (definition-level and file-level),
fragments (order, override, nesting, cycles), aliases, compilation (fragments
in the SQL, context narrowing, parameterization), display (localization,
formatting, minimum sample), and the consumers: the bundled preflop and
postflop definitions run end to end on the golden corpus, the report renders
localized grouped rows, a popup context narrows to one player, and a definition
added at runtime runs with no Python change.

## Where this goes

The definition layer is what the advanced HUD needs next:

* **#299** positional and role-based popup packs become definition sets.
* **#298** context-aware dynamic panels select definitions from the live hand
  state.
* **#309** the GUI editor edits these definitions.
* **#307** populations and cohorts become reusable fragments and contexts.
