# The player situation model

`DerivedStats` answers "how often did this player do X" with one column per
answer, and every column is a procedure over the action stream:

```
calcCBets         -> street1CBChance / street1CBDone / foldToStreet1CBChance
calcSqueezeDefense-> street0_SqueezeChance / street0_SqueezeDone
calcActionEnums   -> twenty enum_*_action chars, each with its own scan and its
                     own bookkeeping of raise levels, cold callers and chains
calcTurnStats     -> flg_t_donk / flg_t_float / flg_t_float_def_opp
```

Each new question -- "open-raise from the cutoff at 40bb", "fold to a turn probe
in position" -- needs another procedure, because the *situation* was never a
value that could be queried, only a stretch of code that happened to compute it.
Worse, the procedures live in separate worlds: the c-bet pass never learns what
the squeeze pass knows about raise levels, and the six semantic defects the
golden corpus documented in #308 all come from a procedure reasoning about one
spot in isolation (an iso-raise posing as a raise first in, a check-raise posing
as a c-bet, a probe the turn chain cannot see).

This is the deliverable of **#294**: make the situation a value.

> One decision -> one `PlayerSituation`, carrying the context the player decided
> in. Naming it is a *rule table* over that context, not a procedure.

## Where it lives

| Where | What |
| --- | --- |
| `fpdb_3_legacy/player_situations.py` | the record, the rule table, the enum projection |
| `DerivedStats.getStats` | builds `self.situations` once, after the events of #293 |
| `DerivedStats.getSituations()` | the accessor |
| `docs/situation-model.md` | this file |

```
action events (#293) ─┐
HandsPlayers context ─┼─> player_situations.enumerate_situations ─> [PlayerSituation]
hand + game metadata ─┘
```

The extractor reads the normalized event rows (`HandsActions`) and the per-player
context `assembleHandsPlayers` computed, and adds only the facts that are about
*history* rather than about the moment: who opened the pot, who last showed
aggression, what the player did on the previous street, how many callers sat
between two raises, whether the aggressor has already given up on this street.
It contains no parser knowledge, and every amount it reports is the one the
event row already carries -- checked column by column in
`tests/test_player_situations.py`.

Situations are **not persisted** in this issue. They are deterministic and cheap
(one pass over the rows of one hand), so the working model is in process; making
them durable, with the versioning and the backfill of existing history, is the
schema work of #305.

## The record

Money is in cents and ratios in basis points or centi-units, exactly as the
event rows store them. Every context field describes what the player had in
front of them *before* their action: a decision is never explained by its own
chips.

| Group | Field | Meaning |
| --- | --- | --- |
| identity | `hand_id`, `action_no`, `street`, `street_name`, `player` | which decision this is; `action_no` is the `HandsActions.actionNo` it came from |
| game | `site`, `game`, `limit_type`, `is_tournament`, `table_size`, `players_dealt`, `small_blind`, `big_blind`, `currency` | the game the decision was made in |
| player | `position`, `relative_position`, `in_position`, `effective_stack`, `effective_stack_bb`, `stack_bucket`, `spr_before`, `is_hero` | the seat, the stack and the room behind |
| pot | `pot_type`, `multiway`, `players_in_hand`, `preflop_aggressor`, `is_preflop_aggressor`, `street_aggressor`, `is_aggressor`, `previous_aggressor`, `is_previous_aggressor`, `previous_aggressor_led`, `previous_aggressor_checked`, `previous_aggressor_position`, `in_position_vs_previous_aggressor`, `aggressor_checked_this_street`, `previous_raiser`, `is_previous_raiser` | the shape of the pot and who owns it |
| decision | `to_call`, `pot_before`, `pot_after`, `pot_odds_bp`, `facing_action`, `facing_player`, `facing_position`, `in_position_vs_facing`, `facing_amount`, `facing_sizing_bp`, `facing_all_in`, `bet_level_faced`, `raises_before`, `calls_before`, `callers_between_raises`, `callers_since_raise` | the price and the aggression in front |
| history | `street_actions`, `previous_street_actions` | this round's actions so far, and the player's own actions last street |
| board | `board` | the community cards visible at this decision |
| response | `response`, `is_all_in`, `role` | what the player did: `fold`, `check`, `call`, `bet`, `raise`, `complete` |
| names | `labels`, `primary`, `group`, `enum_key`, `enum_response`, `enum_answers` | what the table made of it |

Conventions worth stating:

* **The blinds are part of preflop.** A situation is numbered from the first
  *voluntary* round; a decision taken in the blinds or antes street is a preflop
  decision, because it is one.
* **Streets are named by the hand's own rounds.** Hold'em and Omaha get
  `preflop`, `flop`, `turn`, `river`; a stud or draw hand gets its own names
  (`third`, `firstdraw`, ...) rather than being called a flop it does not have.
  The spot vocabulary of this module is hold'em/Omaha today (see *deferred*).
* **The round index is not the street.** `street` is the street the round *is*,
  which is the round's index only because nearly every game opens preflop. All-in
  or fold Omaha deals the flop before anyone acts and has no preflop round at
  all: its first round is `street` 1, so its decisions are read as flop decisions
  instead of as open limps and steals.
* **`pot_type` is the pot as the player met it.** Preflop that is the round as it
  stands (`unopened`, `limped`, `single_raised`, `three_bet`, `four_bet_plus`),
  postflop it is the shape the preflop round ended in -- what kind of pot this
  street is being played in.
* **`bet_level_faced` counts from the forced bet.** Preflop the big blind is the
  first bet, so an open raise is level 2 and a 3-bet level 3; postflop the first
  bet is level 1, so a 3-bet (bet, raise, re-raise) is level 3 too. One number
  names every raise level on every street, which is what the PT4 enum family
  means and why it maps onto it.
* **`previous_aggressor` is the chain, not the last bet.** The aggressor of a
  street is whoever raised last on it, or the street before's aggressor if they
  made the first bet; a street nobody bet keeps the lead for the player who held
  it. That is what "continuation bet" means, and it survives a checked-through
  street (the legacy turn chain does not, which is one of the pinned differences
  below).
* **`role`** is `aggressor` if the player bet or raised, else `defender` if they
  faced a real bet or raise, else `passive`.

## The rule table

`SITUATION_RULES` is data: a name, a group, a human label, a predicate over the
situation, the responses it applies to (`None` = the opportunity itself), the
streets it can happen on, and the PT4 column it answers, if any. `classify` walks
the table once per decision and keeps every match in `labels`; the first match
becomes `primary`.

The order is deliberate and readable: **the line the player took**, then **the
spot they were up against**, then **the opportunity they declined**, then facts,
plain responses and structure.

| Rule | Spot |
| --- | --- |
| `open_raise`, `open_limp`, `open_fold` | an unopened pot, entered or declined |
| `isolation_raise`, `over_limp` | limpers in front, raised over or joined |
| `squeeze`, `three_bet`, `four_bet` | re-raising: with callers behind it, or not |
| `cbet`, `delayed_cbet`, `probe`, `float_bet`, `donk`, `check_raise` | leading out postflop, one name per reason |
| `limped_pot_bet` | the first bet of a pot nobody raised, which no aggressor-based name fits |
| `squeeze_defence`, `facing_cbet`, `facing_delayed_cbet`, `facing_donk`, `facing_float`, `facing_raise`, `facing_3bet`, `facing_4bet`, `five_bet_plus`, `facing_limpers`, `facing_open` | the spot faced |
| `opener_vs_3bet`, `three_bettor_vs_4bet` | the role inside it (opener, 3-bettor) |
| `squeeze_spot`, `cbet_spot`, `delayed_cbet_spot`, `probe_spot`, `float_bet_spot`, `donk_spot`, `steal_spot`, `preflop_unopened` | the opportunity declined, whatever the response |
| `facing_all_in`, `all_in_raise` | the all-in, as a fact |
| `check_no_bet`, `call_no_raise`, `fold_no_raise` | the plain lines, so every decision has a name |
| `heads_up`, `multiway` | the structure (never `primary` on their own) |

Two design points carry most of the value:

**A spot and its action are one predicate.** The aggregate columns that came in
pairs (`street1CBChance`/`street1CBDone`, `street0_SqueezeChance`/
`street0_SqueezeDone`) are one rule here: whoever can take the line is named by
the opportunity, and the action label is the *same predicate* narrowed to the
response. `test_a_spot_and_its_action_are_one_rule` asserts the sharing.

**A spot is expressible as soon as its sentence is.** The squeeze, the 3-bet
defence and the defence against an open are three rows over the same context --
`callers_since_raise`, `callers_between_raises` and `bet_level_faced` -- so
adding "cold 4-bet over a raise and a caller" is a row, not a function. The
corpus prints the difference: hands `04_open_3bet` and `05_squeeze` have the same
seats, the same opener and the same 3-bettor, and differ by one cold call; only
the second one has a squeeze spot in it.

## What "donk", "probe" and "float" mean here

Leading into the aggressor has three reasons, and the only difference in the
context is what that aggressor did:

| Situation | The aggressor | The bet is |
| --- | --- | --- |
| `donk` | bet the previous street and has not acted yet on this one | betting into strength |
| `probe` | checked the previous street through | betting into weakness |
| `float_bet` | bet the last street, the player called in position, and they have now checked in front | punishing the give-up |

The legacy code calls the third one a float as well, and the *facing* side of it
is `facing_float`: the caller who floated now meets the second barrel. Those are
two different players taking two different lines, so the model names them apart.

## The PT4 enum projection

`enum_responses(situations)` projects the model onto the `enum_*_action` columns
that `calcActionEnums` fills today -- one char per column per player, `F`/`C`/`R`,
first answer of the hand wins. That is the migration path: a calculator can be
moved onto the model with the HUD unable to tell, and
`test_the_projection_reproduces_the_legacy_columns` checks it cell by cell on the
golden corpus: **209 of the 215 cells identical**, and the six exceptions are
known:

| Cells | Why |
| --- | --- |
| `enum_face_allin`, `enum_face_allin_action` (4) | the legacy pass records the *first* all-in faced in the hand and then stops, so at most one player per hand is ever answered. The model knows every player who faced one (`test_facing_an_all_in_is_recorded_for_everyone`) but does not project a column whose legacy shape is that quirk. |
| `enum_t_donk_action` (2) | when the flop aggressor checks the turn the legacy chain has no aggressor left, so whoever bets into that weakness leaves them unanswered -- whether the flop was checked through or they led it themselves and gave up. The model names them `facing_donk`, which is what the column is for. |

`test_the_projection_answers_every_enum_column_the_hud_shows` keeps the other
direction honest: every column in the HUD's `SITUATIONS` table is answerable from
the rule table, so nothing is left behind when the flip happens.

## What the model says about #308's six defects

The corpus documented six places where the stored columns disagree with the poker
word. The model is expected to side with the word, and
`test_the_model_sides_with_poker_where_the_columns_document_a_deviation` asserts
it on the same hands:

| Defect | The model |
| --- | --- |
| `street0OpenLimp` is set for the first caller even in a raised pot | `open_limp` requires `pot_type == unopened` |
| the over-limp is recorded nowhere | `over_limp` is its own row |
| an iso-raise sets `raisedFirstIn` while `raiseFirstInChance` is false | `isolation_raise` is not `open_raise` |
| a check-raise is counted as a c-bet | `cbet` requires no aggression in front and a real lead last street; a check-raise is `check_raise` |
| bet-then-fold-to-a-raise is counted as a fold to the c-bet | the response is `facing_raise`, and `fold_no_raise` is only about bets |
| `effStack` measures what is left, not what was at stake | `effective_stack` is the event's, measured before the chips |

## Checking it

`tests/test_player_situations.py` pins four independent references:

* the model against the **parsed action stream** (every decision, in order, no
  more and no fewer), and against the **event rows** (no fact invented);
* the model against the **corpus manifest's poker semantics**: all 180 per-player
  expectations of #308, read back through the situations, including the six
  deviations;
* the model against the **legacy enum columns**: 204/209 cells, five documented;
* the table against itself: every declared rule is exercised by the corpus, every
  decision has a name, and no column is claimed twice.

Adding a spot means adding a row and a scenario that exercises it -- the corpus
is the reference dataset for the epic, and
`test_every_declared_spot_appears_in_the_corpus` fails until the hand exists.

## Deferred, on purpose

| Not here | Where it belongs |
| --- | --- |
| persisting situations, versioning them, backfilling history | #305 |
| board texture and runout features | #295 |
| bet/raise sizing buckets (the raw basis points are carried today) | #296 |
| the query engine and the filter DSL that read them | #297, #306 |
| positional and role-based popup packs | #299 |
| draw/stud-specific situations (`stand pat`, discards, bring-in) | not yet designed; those actions stay in the event stream and are not named as spots |
