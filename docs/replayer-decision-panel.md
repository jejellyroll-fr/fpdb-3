# The replayer's action inspector

The replayer shows a side inspector beside the table (`fpdb_3_legacy/replay_inspector.py`):
the decision at the replayed step at the top, the hand's actions below. It is a post-session
study screen, like the rest of the replayer (`docs/fair-play.md`): it gives figures and their
assumptions, not advice to act on. The figures are drawn in neutral colours, with no green or
red "do this" signal.

`fpdb_3_legacy/replayer_panel.py` builds the decision as data: sections of labelled rows, each
row with a tooltip that explains it. `GuiReplayer` only paints it. The arithmetic comes from
`replayer_decision.py` (calls, pots, SPR, sizing, MDF), the replayer's equity engine,
`hand_icm.py` and `hand_bounty.py`.

## The action timeline's colour grammar

The history lines come from `replay_history.py` as `ReplayHistoryEntry` objects, and each one
carries its action verb (`folds`, `checks`, `calls`, `bets`, `raises`, `collected`). The colours
and the glyph of a line come from that verb — `action_style()` / `action_icon()` in
`replay_history.py`, shared by the inspector's timeline and the history window — never from
parsing the translated text:

| Action | Glyph | Text | Chip |
| --- | --- | --- | --- |
| folds | ✕ | `#FF7186` | `#40202D` |
| checks | ✓ | `#A2C5D4` | `#263847` |
| calls | ↳ | `#32D5EA` | `#103946` |
| bets | ● | `#F7D54A` | `#43391B` |
| raises | ⇈ | `#FFAC57` | `#45301E` |
| collected | + | `#53DF9B` | `#173B31` |

The same pairs on every street, in cash games and tournaments. Posts, phase headings and plain
results use the default pair (`#B9C6D1` on `#24313E`).

The selected line is drawn independently of its action's type: it keeps its own chip colour and
glyph, and gets a bright frame (`#41E6FF`) plus a marker on its left edge. The slider is the
single source of truth: clicking a line only moves the slider, and every slider change rebuilds
the panel and re-selects the row of the step shown.

Folded, the inspector retracts to a thin strip on the **right edge**, where the panel lives,
and the table takes the width it frees. Opened again, it gets back the width it had.

A row can carry a functional *tone* — the SPR's band: below 3 the stack is shallow against the
pot (the whole row turns amber), above 10 it is deep (cyan). Descriptive bands, not advice, and
they never change the action colours.

In the history, an action by a player whose cards are shown reads as those cards instead of the
bet's amount (`Player1: raises [Ah Kh]`); posts and uncalled amounts keep their figure, and the
amount stays on the entry either way.
With **Hide Cards** checked, the history follows the table: only the hero's cards are shown, and
an opponent's actions keep their amount until the showdown, so the history never gives away a
hand the table still hides.

## Key figures as tiles

A `PanelRow` with a `key` is one of a section's key figures, shown first and as a tile. The key
is a stable semantic id, so the tile's colour never depends on the translated label:

| Key | Tile |
| --- | --- |
| `bet_size` | cyan |
| `call_amount` | teal |
| `required_equity`, `required_chip_equity` | yellow (the tournament's chip equity keeps its own id) |
| `pot_odds` | mint |
| `chip_ev`, `icm_ev`, `icm_result`, `bounty_ev`, `head_ev`, `adjusted_chip_ev` | neutral |

`spr`, `mdf` and `fold_equity` stay ordinary rows, and the detailed-only figures stay folded
until *Detailed analysis* is on.

## Sections

Each section appears only when it applies.

- **The bet just made.** The bettor's size in % of the pot before it.
- **The player about to act** (the hero by default, every player with *Odds for all
  players*):
  - **Call amount**: capped at the player's stack.
  - **Effective pot after call**: everything the call can win, the call included.
  - **Required equity**: the pot odds, as the share of that pot the call costs. In a
    tournament it is labelled **Required chip equity**: chips are not prize money, so it is
    never an ICM calling threshold.
  - **Estimated hand equity** (the hero, when every live hand is known): one figure. The
    panel used to show the same value twice, as "Call Eq" and "Push Eq", as if two actions
    had been priced.
  - **Equity difference**: the equity less the required equity, in percentage points. It
    describes the spot and is not a fold, call or raise recommendation. Next to it, a muted
    note says the equity is against the shown hands only — the cards were hidden at the table —
    and is not an action recommendation.
  - **SPR**: from the second betting round on.
  - a call in a multiway pot carries a muted note: the pot odds and the equity are
    against all the opponents still in, and the pot odds already count the whole pot.
- **Cash — all-in**: once the hero is in an all-in of a cash hand, the all-in priced in
  chips (money): all-in EV, the equity share of the pot less what was put in, and the
  equity at the all-in. A multiway all-in on a single pot is priced like the tournament
  one, with the same split-pot note; a side pot is not priced and says why. In a cash
  game the pot itself is the prize, so there is no ICM on top.
- **Tournament — ICM**: chip EV in chips, then ICM $EV and ICM result in the payout's unit,
  and the model's status (see `docs/icm.md`).
- **Knockout bounty**: bounty EV, the part added to the player's own bounty, the
  bounty-adjusted chip EV, and the model's status (see `docs/profitability-ev.md`). It is
  never added to ICM $EV: together they are not a complete PKO model.

When an all-in cannot be priced, the cash, ICM or bounty section shows **Unavailable**
and the reason: a field larger than the table, a side pot, unknown cards. A cash hand or
a freezeout shows no ICM or bounty section.

Missing payouts get their own state, **Payouts needed**: the hand history never carries the
payout structure and a summary often lists only your own result, so nothing out of the
money settles it (`docs/icm.md`). The section says so and offers an **Enter the payouts…**
button. A `PanelRow` with an `action` is drawn as that button, and the inspector emits
`action_requested("payouts")`, which opens the replayer's payouts dialog. Once a structure
is stored, the hand is priced again.

## Compact and detailed

The panel is compact by default. **Detailed analysis** adds:

- the pot odds as a ratio, and the size of the bet faced;
- the pot breakdown: the pot drawn on the table, the money the call cannot win (an uncalled
  excess or side money), and the effective pot before the call;
- MDF and fold equity needed for a bet. Both use a simplified heads-up model, where a bluff
  never wins when called. They are not a solver prescription;
- where the equity comes from: every remaining board enumerated, or simulated boards;
- the ICM model's assumptions, the cash all-in's model notes, and the equity at the all-in.

## A short all-in against a larger raise

PokerStars PLO5 hand 262648475894: the hero has $29.65 left and faces a raise to $93.75.

| Row | Amount |
| --- | --- |
| Pot on the table | $150.75 |
| Call amount | $29.65 |
| Uncalled or side money | $45.35 |
| Effective pot before call | $105.40 |
| Effective pot after call | $135.05 |
| Required equity | 22.0% |

The $45.35 the hero cannot match goes back to the raiser, so the call is priced against the
$135.05 it can win, not against the $150.75 on the table.
