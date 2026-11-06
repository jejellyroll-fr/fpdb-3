# The Advanced HUD guide

> The presentation rules this package follows — the popup navigation order, what each
> colour means, and how to preview it without a table — are in
> [the reference HUD design system](hud-design-system.md).

fpdb ships reference HUDs you can import and play with immediately. They
are starting points, not a replacement for the HUD you already have: importing
one never binds itself to a game, so your tables keep the profile they had until
you choose another.

| Package | For | Surface |
| --- | --- | --- |
| `nlhe_6max_basic` | Your first hands | Eight numbers, two popups |
| `nlhe_6max_advanced` | Everyday play | The Basic numbers plus 4-bet, popups one click deep |
| `nlhe_6max_dynamic` | Context-aware play | Blocks that change with the situation |
| `plo_6max_dynamic` | Pot-Limit Omaha | Omaha stats in context-aware blocks |

## Import one

1. **Preferences → HUD → Import HUD** (📥).
2. Pick the `.fpdbhud` file from the `hud-packages/` directory.
3. fpdb adds the package's profile and its stats, popups and blocks. It does
   **not** change which profile your tables use.

The filename is the profile name: after import, the **Active Profile** list has
`nlhe_6max_basic`, `nlhe_6max_advanced`, `nlhe_6max_dynamic` or
`plo_6max_dynamic` in it.

## Choose which profile applies to a game

A profile is chosen for a table by a **rule**: a table shape (site, game, seats,
speed) that resolves to one profile. On the **Profile Select** tab you can see
and edit those rules, so "Hold'em, 6 seats" resolves to `nlhe_6max_advanced`
while "Hold'em, full ring" keeps your own profile.

If your main HUD is one you built yourself, leave its rule alone and add the
reference profile only to the table shapes you want to try it on. Nothing else
changes.

## Read the numbers

Every stat carries its sample. A percentage over four hands is noise, so the
name is drawn red under 25 hands and the sample sits beside the name. In popups,
each row renders **its own** sample column, so a row cannot travel without the
hands behind it.

## Open the popups

- **Basic:** two popups — preflop and postflop.
- **Advanced:** every cell opens a popup, and those popups navigate into the
  shipped library: preflop (with position-specific open raises), single-raised
  pot, 3-bet pot, 4-bet pot. The grid stays twelve cells; the depth is one click
  away.

Hover for the popup name; click to open it; the popup itself has links to the
next one, so you can walk from "the flop c-bet" down to "the fold on the turn"
without closing the window.

## Change blocks without breaking popups

A block is a group of stat cells; a popup is bound to a *stat name*, not to a
position. So:

- **Moving a cell** inside a block is safe — popups follow the name.
- **Renaming a stat** breaks the popup that addressed the old name. The popup
  editor flags a binding it can no longer resolve instead of silently showing an
  empty row.
- **Deleting a block** removes its cells; any popup still pointing at those stat
  names reports the missing stat.

When in doubt, duplicate the profile first (📋 **Duplicate**) and edit the copy.

### Tune dynamic-panel labels in a package

Panel typography and visible stat headings belong in the `.fpdbhud` package,
not in renderer-specific code. Set `title_font_scale` and
`heading_font_scale` on `<ss>` to scale panel titles and stat headings relative
to the profile font size (for example, `0.82` and `0.60`). A `<block>` can
override either scale. Values are clamped to the supported range `0.5`–`2.0`.

For a compact visible heading, add `display_label` to a `<stat>` while keeping
`tip` as the full explanation:

```xml
<stat _rowcol="(1,1)" _stat_name="a_freq2"
      tip="Turn aggression frequency" display_label="Turn aggression" />
```

The compact heading is shown in the panel; hovering it still reveals the full
`tip`. If `display_label` is omitted, the renderer uses `tip` unchanged. The
shipped Dynamic NLHE package supplies compact labels across its contextual
panels. Existing profiles are preserved when a package is imported; customize
the active profile in HUD Preferences (or import into a clean profile) if it
was created from an older package version.

## Restore the package behaviour

Re-importing a package a second time does not duplicate its stats: the importer
merges what is missing and leaves what is already there. To get back exactly
what the package ships, duplicate your edited profile, delete the edited one, and
re-import — or **Export HUD** the package, keep the file as your reference, and
**Import HUD** it onto a clean profile.

## The Dynamic HUD

`nlhe_6max_dynamic` is the reference package for context-aware panels. It has its
own guide, because what is live and what is derived needs saying carefully:
[Dynamic HUD guide](hud-dynamic-guide.md).

For Pot-Limit Omaha, import `plo_6max_dynamic` and add it to the Omaha table
shape in **Profile Select**. Importing it does not change the existing Omaha
profile binding. The package reuses the shipped spot rules but supplies
Omaha-oriented stats; it does not convert Hold'em stats or change hand parsing.

## Where to go next

- [Dynamic HUD guide](hud-dynamic-guide.md)
- [Analytics concepts](analytics-concepts.md)
- Developer/reference: [popup-packs.md](popup-packs.md),
  [dynamic-panels.md](dynamic-panels.md).
