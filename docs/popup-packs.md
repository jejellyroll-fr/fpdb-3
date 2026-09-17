# Popup packs: hierarchical HUD popups as data (#299)

The HUD's popups were already data — `<pu pu_name="...">` elements in
`HUD_config.xml`, each a class and a list of stat names, with
`pu_stat_submenu` nesting one inside another. What this layer adds is a **pack**:
a versioned, validated, shipped hierarchy — preflop, single-raised pots, 3-bet
pots, 4-bet pots, street by street — that can be edited without touching Python.

## What ships

`fpdb_3_legacy/popup_packs.d/*.json` holds five packs and 28 popups:

| Pack | Root popup | Covers |
| --- | --- | --- |
| `analytics` | `analytics` | the entry point: one row per branch below |
| `preflop` | `preflop` | RFI by position, facing an open, 3-bet by position, facing a 3-bet, 4-bet, facing a 4-bet, squeeze, blind defence, limps, sizing, stack depth |
| `srp` | `srp` | single-raised pots: PFR IP/OOP, caller on the flop, flop aggression, turn, river |
| `threebet_pot` | `threebet_pot` | 3-bet pots: IP/OOP, aggressor's and caller's streets |
| `fourbet_pot` | `fourbet_pot` | 4-bet pots: aggressor's and caller's streets |

They are installed into `config.popup_windows` when the configuration loads, so
a HUD stat block can point at `preflop`, `srp`, `analytics` — or any of the 28 —
by name. **Installing is additive**: a popup `HUD_config.xml` defines is never
replaced, and re-installing a pack replaces its own popups instead of
duplicating them.

## The shape of a pack

```json
{
  "schema_version": 1,
  "packs": [
    {
      "name": "preflop",
      "label": { "en": "Preflop pack", "fr": "Pack préflop" },
      "description": "…",
      "tags": ["popup", "preflop"],
      "root": "preflop",
      "nodes": [
        {
          "name": "preflop",
          "class": "ModernSubmenu",
          "title": "{player}: preflop",
          "entries": [
            "n",
            { "stat": "vpip", "label": "VPIP", "category": "Preflop" },
            { "stat": "RFI by position", "submenu": "preflop_rfi" }
          ]
        },
        { "name": "preflop_rfi", "require_sample": true, "entries": ["rfi_total", "open_limp"] }
      ]
    }
  ]
}
```

* **`class`** must be a popup class the HUD can resolve (`default`, `Submenu`,
  `Multicol`, `ModernSubmenu`, `ModernSubmenuLight`, `ModernSubmenuClassic`,
  `CategorizedPopup`, `RangeChartPopup`, `BlockPopup`); a test keeps that list
  equal to what `Popup.resolve_popup_class` finds, in both directions.
* **`entries`** are stat names or objects. A **navigation row** carries
  `submenu`, and its row text is the `stat` field — exactly as the classic XML
  puts it in `pu_stat_name`.
* **`require_sample`** on a node means "every rate here must show a
  denominator"; the loader refuses the pack when one cannot.
* **`params`** are the optional `<pu>` attributes `Configuration.Popup` reads
  (`theme`, `icon_provider`, `width`, `max_height`, `title`, `source`, `group`).

Compiled, a node becomes a real `Configuration.Popup` built from a generated
`<pu>` node — there is one popup type in the system, and the HUD code is
untouched.

## What a load refuses

A pack that loads is a pack that renders, because anything unknown is a
`ValueError` naming the field and listing what is allowed:

* a stat that is neither in the native catalogue (`Stats.STATLIST`) nor in the
  declarative descriptor registry (`stat_registry`);
* a popup class the HUD cannot resolve, an unknown field, an unknown param, a
  duplicate popup, a missing/invalid `root`, an entry with no stat;
* a `submenu` that points at nothing — neither another node of the pack, nor a
  popup the configuration defines, nor (for a sibling file) a popup another
  pack declares;
* a cycle in the submenu graph, which the HUD would follow into unbounded
  windows;
* a file whose `schema_version` is newer than this build understands.

A missing **sample** is not fatal: `--validate` reports it, which is how a pack
author notices a rate quietly presented without its denominator. The shipped
library's only warnings are `playername`, which is a name.

## Sample sizes

The modern popup renders a stat's sample in its own column: field 4 of the
six-tuple `Stats.do_stat` returns. Two things make that column trustworthy:

* **native stats** already carry it (`(done/chances)`);
* **descriptor stats** now declare one — `sample = "street0VPIChance"` in the
  `.toml` — and `HudAdapter.stat_tuple` puts `(1200)` there. It used to put the
  *value expression* in the sample slot, so the column read
  `100 * street0VPI / street0VPIChance`.

All 17 shipped descriptors declare their denominator.

## Nested submenus

`Popup.py`'s classic `Submenu` has always opened submenus. The modern renderers
now do too, so a hierarchy looks and behaves the same in either:

* `ModernSubmenu`: a navigation row shows `›`, hides its progress bar, takes a
  pointing-hand cursor, and opens the target beside the parent — one child at a
  time per level, like the classic popup;
* `CategorizedPopup`: a navigation row is a `submenu:` anchor in the rich-text
  browser, and following it opens the target.

A link that does not resolve at runtime (a pack removed after a profile pointed
at it) is logged and leaves a dead row rather than raising on the table.

## Editing and composing

```bash
python tools/popup_packs.py --list
python tools/popup_packs.py --show srp                 # the tree
python tools/popup_packs.py --show preflop_rfi --samples
python tools/popup_packs.py --validate                 # plus --dir for your own
python tools/popup_packs.py --export-xml srp_river     # paste into HUD_config.xml
python tools/popup_packs.py --link-into holdring_modern --pack analytics
```

```python
from fpdb_3_legacy import popup_packs as packs

config = Config()                                     # packs already installed
report = packs.install_packs(config, extra_packs)      # extra dirs, or your own
packs.link_pack(config, "holdring_modern", packs.get_registry().get("analytics"))
```

`link_pack` adds exactly one row to an existing popup — the way a *profile*
reaches a pack without re-authoring it — and is idempotent, so linking twice is
not two rows. A pack file is written only by `PackRegistry.save`, which
validates first, so what it writes is what it can read back.

## Compatibility

The classic popups are untouched: `default`, `hold_pre`, `holdring_modern`,
`aof_profile` and the rest keep the class and rows `HUD_config.xml` gives them,
and the shipped stat sets still point at them. The packs are additions to the
same registry, which is why `test_shipped_config_popup_references.py` still
finds every referenced popup defined.

## What this layer does not do

* **It does not rewrite `HUD_config.xml`.** Installation happens in the loaded
  `Config`; a permanent entry is a paste from `--export-xml` or one
  `link_pack` row. Rewriting the user's config file is a different change with
  a different blast radius.
* **It does not invent stats.** Every row names something that exists — the
  native catalogue has the position/street families this pack needs
  (`three_bet_btn`, `check_raise_frequency`, `fold_to_three_B_turn`, …), and
  anything new is a descriptor, which is data too.
* **It does not make a `Submenu` row carry a sample.** Samples are a property of
  the statistic, not of the surface; the classic renderer shows the long label
  it always did.
