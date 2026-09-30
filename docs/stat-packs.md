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
a deterministic archive: the same pack always gives the same bytes. In a zipped
folder the pack is the one top-level directory holding `manifest.json`. As for
a folder, only the manifest and the files it lists are read: anything else in
the archive, such as the `__MACOSX/` folder Finder adds or a README, is never
read and does not count against the pack's file or byte limits. One archive holds one pack.

## Manifest fields

| Field | Required | Meaning |
| --- | --- | --- |
| `schema` | yes | always `fpdb_stat_pack` |
| `version` | yes | pack schema version; a newer one is refused before installation |
| `id` | yes | a dotted lower-case namespace, e.g. `author.topic`; `fpdb.*`, `builtin.*` and `core.*` are reserved |
| `name`, `author`, `description`, `pack_version` | no | shown in the manager |
| `definition_schema_version` | no | the definition schema the pack was written for (default 1) |
| `min_fpdb_version` | no | the oldest fpdb that can load the pack: `"3.9"` or `"3.9.1"`, each part at most 9 digits |
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

Every problem found is reported at once, so an author fixes a pack in one pass —
up to 50: past that, reading stops and the report says so. A long problem is
shortened in the middle, where it quotes the value it refuses.

Packs are **JSON only**. A pack is made to be shared, so it must install on any
fpdb; YAML would need PyYAML, which fpdb does not ship. (Definitions kept in a
local definitions folder may still be YAML when PyYAML is installed.)
An object may not name the same key twice, and every string must be valid
Unicode — an escaped lone surrogate such as `"\ud800"` is refused.

## Validation rules

A pack is checked as a whole when it is imported, and every problem is listed
at once. Beyond the definition schema itself, these are the rules a pack
author is most likely to meet.

**Names.** The pack id is a dotted lower-case namespace (`author.topic`) that
also names its install folder: at most 245 characters, not a Windows device
name (`con.x`, `nul.x`, …). Every stat, fragment and preset id starts with
`<pack id>.` and uses only letters, digits, `_`, `.` and `-` — the name is
written into `HUD_config.xml` when the stat is put on a HUD.

**Files.** Only `.json` files the manifest lists are read, each written the one
way it is stored (`stats/a.json`, not `./stats/a.json`). A path has at most 8
levels and 512 bytes, each name at most 255 bytes, without a trailing dot or
space, a character Windows forbids (`<>:"|?*`), or a name that differs from
another only by letter case or Unicode normalization, or that is also the
folder of another listed file (`stats/a.json` and `stats/a.json/b.json`). A pack holds at most 200
files, `manifest.json` included, and 5 MB of content (an archive may be up to
1 MB larger for the zip format's own headers); the manifest's `definitions` and
`presets` lists together hold at most 199 entries, and a pack declares at most
500 fragments, 500 stats and 500 presets; its fragments name other fragments
at most 2000 times in all.

**Filter values.** Each definition is compiled exactly as the engine runs it,
then its values are checked where the engine is lenient:

| Filter kind | Takes |
| --- | --- |
| yes/no (`in_position`, `multiway`, `tournament`, …) | JSON `true` or `false` — never `"false"` |
| list (`site`, `position`, `situation`, …) | a value or a list of values |
| range (`effective_stack_bb`, `bet_sizing_pct`, …) | `[low, high]` or `{"min": …, "max": …}`, at least one bound, numbers only, low not above high |
| one-sided dates (`date_from`, `date_to`) | one date, `"YYYY-MM-DD"` or `"YYYY-MM-DD HH:MM[:SS]"` |
| one-sided hand ids (`hand_id_from`, `hand_id_to`) | one whole number |
| any | `{"is_null": true}` / `{"is_null": false}` |

A list-valued filter holds at most 200 values, and a stat's or preset's query
binds at most 999 values in all. Numbers must be finite and at most 2⁵³ in size, including a number the
filter turns its value into (a position written `"100000000000000000000"`);
`precision` is at most 10.
`filters` and `numerator` are checked separately.

**Presets.** A preset's `filters` are loaded into the Research filter controls
and read back before it runs, so they may only hold what those controls keep
(its `numerator` is kept as written and follows the definition rules above):

* ranges as `[low, high]`, with at least one bound, above −10,000,000 and up to
  10,000,000, to two decimals;
* at least one value in a list — the row reads `[]` back as no filter, where
  the engine reads it as "none of these";
* text values the filter row reads back unchanged. The row writes a list as
  one field joined with `, ` and reads the whole field back: a field with a
  comma is a list of words, so `["007", "Hero"]` is kept but `[1, 2]` comes
  back as the words `"1"` and `"2"`; a field without one is a single value,
  where a digit-only word (`"001"`) comes back as the number 1, `"true"` as a
  condition, and an empty or space-padded word as no filter at all. A single
  number is written as a number; a player identity is written `Site:alias`;
* `true` for `draw_none` and `blocker_none`, their "no flag at all";
* no `{"is_null": …}` and no `date_from`/`date_to`/`hand_id_from`/`hand_id_to`
  — list those under the preset's `variables` for the user to fill in.
  `variables` and `tags` are lists of strings, and each variable is a filter
  name (`player`, `date_from`, …).

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
