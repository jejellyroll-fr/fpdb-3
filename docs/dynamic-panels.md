# Dynamic HUD panels: the panels that fit the hand (#298)

The HUD draws one fixed grid of stats per seat and, at most, hides a
position-bound panel when the seat is not in that position. The analytics epic
adds a second question the HUD cannot answer: *which panels are worth showing
**right now*** — the street, the roles, the pot shape, the aggressors, the stack
depth, the sizing faced.

`fpdb_3_legacy/hud_situation.py` answers it. The layer is deliberately separate
from `hud_profiles`:

| | decides | changes |
| --- | --- | --- |
| `HudProfileResolver` | which **stat set** a table gets | at most once per table |
| `HudSituationResolver` | which **panels** a seat shows | street by street |

Folding the two together would make every table-shape rule a live rule and every
live rule a table rule. Keeping them apart keeps each resolver's precedence
explainable.

## The context

`HudSituationContext` is a frozen snapshot of the decision in front of one seat.
Every field describes what the seat had **before** acting, matching the
situation model's rule: a decision is never explained by its own chips.

Two constructors matter, and they are the two ends of the same idea:

```python
# From the canonical situation of #294 -- the mapping that keeps the HUD and
# the analytics layer describing a spot the same way:
context = hs.HudSituationContext.from_situation(situation)

# From the live HUD, per seat:
context = hs.HudSituationContext.from_stat_dict(stat_dict[player_id], hud.live_state)
```

`context.filters()` projects the context onto the **filter vocabulary of the
query engine** (#297). That is the point of the mapping: a panel rule's
condition is written in the words a research query uses, and a rule is validated
against `analytics_query.FILTERS` rather than against a second list that would
drift from it.

## The live state, and what a live HUD can honestly know

The classic HUD is refreshed **once per hand**, so the most it can know about the
table in front of it is the shape of the hand it has just assembled — the same
assumption `HUD_main._advance_live_positions` already makes about the seats, for
the same reason. `Hud.update` publishes that shape:

```python
# fpdb_3_legacy/Hud.py, on every hand update:
self.set_live_state(**hud_situation.live_state_from_hand(self.hand_instance))
```

`live_state_from_hand` returns the **table-wide** half: the deepest street the
hand reached with an action, the shape the preflop round ended in, and how many
players started that street. `Hud.set_live_state` is a partial update (`None`
clears a key), and it wakes every aux window's panel memory, so a new hand is
never drawn with the old hand's panels.

The **per-seat** half comes from the seat's own aggregate row. `stat_dict[pid]`
is the HudCache row of the *same hand*, so its per-street columns answer "did
*this* seat raise, act last, face a raise, face a c-bet, and how big was the
sizing" — see `entry_facts`:

| question | column |
| --- | --- |
| did this seat raise preflop | `street0Aggr` |
| did this seat take the aggression on that street | `street{0..3}Aggr` |
| does this seat act last on that street | `street{0..3}InPosition` |
| did this seat face a raise / a bet | `street{0..3}FaceRaise` / `foldToStreet{1..3}CBChance` |
| how big was the sizing faced | `val_{p,f,t,r}_*bet_facing_bp` |

A value the feed pushed wins; the row is the floor, not the ceiling. A feed that
follows a hand action by action knows far more and can publish it directly.

This is why the panels are honest about the **granularity** they claim: they
describe the spot the table is in, one hand stale, exactly as the position-bound
panels already do. Nothing in this layer pretends to know a decision that has
not happened yet.

## The rules

A `PanelRule` is data: a panel name, `when` conditions in the engine's
vocabulary, `min_sample`, `sample`, `fallback`, `substitutions`, `priority`,
`profile` and `enabled`. Loading validates every condition name, so a typo is a
`ValueError` naming the condition and listing what exists.

The shipped library (`hud_situation.d/core.json`) covers the issue's contexts:

| panel | spot |
| --- | --- |
| `core` | the static row, always right (`when: {}`) |
| `preflop_open` | unopened pot, RFI by position |
| `preflop_facing_open` | one raise in front |
| `preflop_facing_three_bet` | you opened and got 3-bet |
| `preflop_squeeze` | a raise with callers behind |
| `blinds_defence` / `blinds_steal` | raising while in the blinds / unopened from a steal seat |
| `srp_cbet_ip` / `srp_cbet_oop` | single raised pot, you raised preflop |
| `srp_face_cbet_ip` / `srp_face_cbet_oop` | facing the c-bet, by position |
| `srp_probe_ip` | the preflop raiser checked |
| `threebet_pot_ip` / `threebet_pot_oop` / `fourbet_pot` | the pot shape, by position |
| `ssh_stack` | under 20bb |
| `overbet_river` / `minbet_faced` | the sizing faced |
| `preflop_deep` | 150bb or deeper, withheld under 200 hands |

Precedence, in order: **most conditions wins**, then `priority`, then file
order. `PanelSelection` reports which rule decided each panel and which panels
were withheld for want of sample:

```python
selection = resolver.resolve(context, "holdring_modern")
selection.panels            # ('srp_cbet_ip', 'core') -- in display order
selection.decided_by("srp_cbet_ip").rule_id
selection.suppressed        # panels withheld: min_sample not met
selection.describe()        # one line, for logs and the CLI
```

`min_sample` compares the seat's own aggregate column (`sample`, default `n`) and
is a **display** rule: below the threshold the panel is withheld (or its
`fallback` shown) and the reason is reported. `substitutions` renames the panel
per position (`{"BB": "srp_bb_flop"}`) without copying the rule.

## Change detection

The HUD must not rebuild itself on every action. `PanelState` keeps the last
selection per seat and answers `update` with a `PanelChange` naming exactly what
appeared and disappeared, so only those panels redraw. Nothing here ever reads or
writes a **window position**: a panel that becomes visible appears where the
player already dragged that block, which is what keeps a dynamic panel from
moving a static one.

`block_visible_for` is the one decision the renderer makes per block:

* a block the selection **names** is shown, whatever its position binding says —
  the rule already describes the spot;
* a block the selection does **not** name keeps the old position rule, so the
  static core of the HUD is untouched by turning the feature on.

## Turning it on

Off by default. `HUD_config.xml` needs one section — and an existing
configuration gains it (with its documentation) on first run:

```xml
<hud_panel_rules enabled="true" source="builtin" fallback="core">
  <hud_panel_rule panel="srp_cbet_ip" street="flop" pot_type="single_raised"
                 is_preflop_aggressor="true" in_position="true" to_call="[null, 0]"/>
</hud_panel_rules>
```

* `enabled="false"` (the shipped default) or a missing section: the section is
  **not read at all**, so a source that has since moved cannot turn a
  configuration the user turned off into one that fails to load.
* `source="builtin"` prepends the shipped library; any other value is a path to
  a `.json` file or a directory of them.
* `fallback="core"` is the panel shown when the profile has rules and none of
  them matches. A profile with *no* rules is the static HUD — which is why
  `Config.get_hud_panel_rules()` returns `[]` for both the disabled and the
  unconfigured case: off and never-configured are the same code path.

## Command line

```bash
python tools/hud_panels.py --list                  # the shipped rules and their conditions
python tools/hud_panels.py --show srp-cbet-ip      # one rule, in full
python tools/hud_panels.py --validate              # rules that load but cannot do what they say
python tools/hud_panels.py --enable                # the section, ready to paste
python tools/hud_panels.py --export my-panels.json # the rules as JSON
python tools/hud_panels.py --resolve --street flop --pot-type single_raised \
    --is-preflop-aggressor --out-of-position       # what a spot resolves to, and why
```

## Limits

* The street and the aggressors come from the **last imported hand**, not from
  the action being played. A feed that knows the live action can publish more
  through `Hud.set_live_state`; nothing else in this layer needs to change.
* Stack buckets come from the seat's `bbstack`; a table with no stack column
  falls back to the big-blind bands (20/50/100).
* A rule never calls out to SQL: it is evaluated in memory against the context,
  so showing a panel costs no query.
