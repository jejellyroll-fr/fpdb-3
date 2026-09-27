# Stat packs (#403)

A **stat pack** shares [declarative stat definitions](stat-definitions.md) —
and, optionally, Research presets — as one file another fpdb can install. It is
the safe equivalent of a custom-stat plugin: a pack is data only, read through
the same validators as the definitions fpdb ships, so it can add stats but can
never run code or SQL.

Manage packs from **Configure → Stat Packs**: import a `.fpdbstats` file (or a
pack folder's `manifest.json`), enable or disable a pack, uninstall it, export
it to share, and read why an invalid pack is not loaded.

## A minimal pack

The complete example lives in
[`docs/examples/example-preflop-pack/`](examples/example-preflop-pack) and is
installed by the test suite, so it is known to work.

```text
example-preflop-pack/
├── manifest.json
├── stats/steals.json
└── presets/steals.json      (optional)
```

`manifest.json`:

```json
{
  "schema": "fpdb_stat_pack",
  "version": 1,
  "id": "example.preflop",
  "name": "Example Preflop Pack",
  "author": "fpdb",
  "description": "Button and small-blind steal stats.",
  "pack_version": "1.0.0",
  "definition_schema_version": 1,
  "min_fpdb_version": "3.9",
  "fragments": {
    "example.preflop.unopened": { "street": "preflop", "pot_type": "unopened" }
  },
  "definitions": ["stats/steals.json"],
  "presets": ["presets/steals.json"]
}
```

`stats/steals.json` is an ordinary definition file:

```json
{
  "schema_version": 1,
  "stats": [
    {
      "name": "example.preflop.btn_open",
      "metric": "raise_frequency",
      "fragments": ["example.preflop.unopened"],
      "filters": { "position": ["BTN"] },
      "label": { "en": "Button open", "fr": "Ouverture au bouton" },
      "format": "percentage",
      "min_sample": 20,
      "category": "Example steals"
    }
  ]
}
```

To share it, zip the folder (with or without the top-level directory) and
rename the archive to `.fpdbstats`, or export it from the manager, which writes
a deterministic archive: the same pack always gives the same bytes.

## Manifest fields

| Field | Required | Meaning |
| --- | --- | --- |
| `schema` | yes | always `fpdb_stat_pack` |
| `version` | yes | pack schema version; a newer one is refused before installation |
| `id` | yes | a dotted lower-case namespace, e.g. `author.topic`; `fpdb.*`, `builtin.*` and `core.*` are reserved |
| `name`, `author`, `description`, `pack_version` | no | shown in the manager |
| `definition_schema_version` | no | the definition schema the pack was written for (default 1) |
| `min_fpdb_version` | no | the oldest fpdb that can load the pack |
| `fragments` | no | reusable filter bundles, `name → filters` |
| `definitions` | no* | definition files, relative to the manifest |
| `presets` | no* | Research preset files, in the shipped preset format |

\* A pack must add at least one definition or preset. Any other field is refused.

## Namespacing

Every definition, fragment and preset a pack adds must start with
`<pack id>.`. A pack can therefore never replace a built-in stat, and a name
already taken by another installed pack is refused at installation, with the
clashing names listed.

## What a pack cannot do

* **No code, no SQL.** Definitions only name registered metrics, filters,
  dimensions, fragments and formats; unknown fields (`sql`, `script`, …) are
  refused, and every definition is compiled at install exactly as the engine
  will run it, so a bad filter value is caught there too.
* **No filesystem reach.** Listed files must be relative paths inside the pack
  with a `.json` suffix; absolute paths, `..`, symbolic
  links and archive entries that escape the pack are refused. Files the
  manifest does not list are neither installed nor re-exported.
* **No network.** Nothing is fetched, at install or at evaluation.

Every problem found is reported at once, so an author fixes a pack in one pass.

Packs are **JSON only**. A pack is made to be shared, so it must install on any
fpdb; YAML would need PyYAML, which fpdb does not ship. (Definitions kept in a
local definitions folder may still be YAML when PyYAML is installed.)

## Where packs live

Installed packs are copied to `<fpdb data directory>/stat-definitions.d/<pack
id>/` (for example `~/.fpdb/stat-definitions.d/` on Linux and macOS), never
into the application. The enabled/disabled state is `state.json` beside them.
A pack edited into an invalid state after installation is listed as
**Invalid** with its errors and skipped; the other packs keep loading.

## Where the stats appear

* **HUD** — the stat picker in HUD Preferences lists pack stats next to the
  built-in ones, labelled with their pack (`[analytics: example.preflop]`).
* **Research** — pack presets appear in the preset picker with the shipped
  ones, read-only.

The registries read packs when they are built. The HUD keeps the registry it
started with, so after a change **restart fpdb and the HUD**; the manager says
so after every change.
