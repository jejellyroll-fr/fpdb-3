# The Dynamic HUD guide

> The presentation rules this package follows — the panel titles and the low-sample rule, what each
> colour means, and how to preview it without a table — are in
> [the reference HUD design system](hud-design-system.md).

A **dynamic panel** is a block of stats the HUD shows *only in the situation it is
about*. Instead of a fixed grid that shows the same twelve numbers at every
table, a seat can show the preflop panels while the hand is preflop, the
single-raised-pot panels once there is one caller, and the "facing a c-bet"
panels at the moment a c-bet is in front of them.

This is a *user* guide. The rules, the resolver and the file format are in
[dynamic-panels.md](dynamic-panels.md).

## Turn it on, safely

Either:

- import the reference package **`nlhe_6max_dynamic`** (**Preferences → HUD →
  Import HUD**) and select it as a profile; it enables the shipped rules for
  *that profile only*; or
- open **Preferences → HUD → Dynamic Panels** and turn the rules on for your own
  profile.

A table running any other profile resolves **no rule** and keeps the static grid
it always had. That is what makes turning dynamic panels off indistinguishable
from never having had them.

## What a panel is made of

Each rule says: *when* these conditions hold, show *this block*, and if the
player has fewer than *this many* hands behind them, show the *fallback* block
instead. The fallback (`core`) is always visible, so a seat is never blank.

The situations the shipped rules cover:

- **Preflop** — unopened pot, facing an open, facing a 3-bet, squeeze (a raise
  that has been called behind it), blind defence, steal spots.
- **Single-raised pot** — c-betting in and out of position, facing the c-bet in
  and out of position, probing the turn after a checked-through flop.
- **3-bet and 4-bet pots** — the aggressor and the caller, in and out of position.
- **Stack and sizing** — short stacks, deep stacks, a minimum bet faced, a river
  overbet.

## Samples and thresholds

A rule can ask for a minimum sample. A player with 12 hands facing a c-bet is not
a c-bet defender yet, so the rule is *withheld* and its fallback shows instead.
The preview tells you a rule was withheld and why, which is the difference
between "fpdb has no opinion" and "fpdb has too little evidence".

## What is live, and what is not

fpdb is honest about this, and so should the panels be:

- **Live context available** — on a source that publishes action by action, the
  panels follow the *current decision*. A c-bet panel can appear the moment the
  c-bet is made, not one hand later. Today this is fpdb's live seat/action feeds;
  the capture path that supports it is named in the guide for that source.
- **Hand-refresh context** — everywhere else, the resolver gets what the last
  *assembled* hand says. The panels are still right, they simply change when the
  hand is refreshed rather than mid-action.

fpdb never claims action-by-action behaviour for a source that cannot provide it.
If a live feed does not know a fact — the board, the effective stack — the panel
falls back to what the imported hand says rather than inventing a value.

## Preview a rule

**Preferences → HUD → Dynamic Panels → Preview** runs the *production* resolver
on the context your selectors describe and reports, for every rule:

```
profile: all
context: street=flop pot=single_raised
panels: srp_cbet_ip, core
✔ srp_cbet_ip: won on specificity (4 conditions)
✔ core: also shown
∅ preflop_open: condition street=preflop does not hold
⊘ preflop_deep: withheld: n=12 < min_sample 200
```

Because it is the same resolver that runs at the table, the preview cannot
disagree with what you will see. Conflicts and duplicates are flagged on the
rows themselves, using the same checks the command line reports.

## Turn it off

Untick the rules for the profile, or switch the table back to a profile with no
rules. The HUD returns to its static grid on the next refresh. **Window and
block positions are never moved by the resolver**, so nothing you dragged is
lost by turning panels on or off.

## Where to go next

- [Advanced HUD guide](hud-advanced-guide.md) — the reference packages.
- [Analytics concepts](analytics-concepts.md) — pot type, SPR, IP/OOP, sizing.
- Developer/reference: [dynamic-panels.md](dynamic-panels.md),
  [situation-model.md](situation-model.md).
