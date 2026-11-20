# The replayer's decision panel

The replayer draws a panel beside the action timeline. It describes the decision at the
replayed step. It is a post-session study screen, like the rest of the replayer
(`docs/fair-play.md`): it gives figures and their assumptions, not advice to act on. The
figures are drawn in neutral colours, with no green or red "do this" signal.

`fpdb_3_legacy/replayer_panel.py` builds the panel as data: sections of labelled rows, each
row with a tooltip that explains it. `GuiReplayer` only paints it. The arithmetic comes from
`replayer_decision.py` (calls, pots, SPR, sizing, MDF), the replayer's equity engine,
`hand_icm.py` and `hand_bounty.py`.

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
    describes the spot and is not a fold, call or raise recommendation.
  - **SPR**: from the second betting round on.
- **Tournament — ICM**: chip EV in chips, then ICM $EV and ICM result in the payout's unit,
  and the model's status (see `docs/icm.md`).
- **Knockout bounty**: bounty EV, the part added to the player's own bounty, the
  bounty-adjusted chip EV, and the model's status (see `docs/profitability-ev.md`). It is
  never added to ICM $EV: together they are not a complete PKO model.

When an all-in cannot be priced, the ICM or bounty section shows **Unavailable** and the
reason: missing payouts, a field larger than the table, a multiway all-in, unknown cards.
A cash hand or a freezeout shows no ICM or bounty section.

## Compact and detailed

The panel is compact by default. **Detailed analysis** adds:

- the pot odds as a ratio, and the size of the bet faced;
- the pot breakdown: the pot drawn on the table, the money the call cannot win (an uncalled
  excess or side money), and the effective pot before the call;
- MDF and fold equity needed for a bet. Both use a simplified heads-up model, where a bluff
  never wins when called. They are not a solver prescription;
- where the equity comes from: every remaining board enumerated, or simulated boards;
- the ICM model's assumptions, and the equity at the all-in.

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
