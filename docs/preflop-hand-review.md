# Preflop hand review for PreflopAdvisor

fpdb-3 owns the hands that were played; [PreflopAdvisor](https://github.com/jejellyroll-fr/PreflopAdvisor)
owns the solver strategies and the trainer. The solver review sends the factual
description of a hand's preflop from fpdb-3 to PreflopAdvisor, which matches
each hero decision to a node of a compatible simulation, compares it with the
solver's frequencies and EVs, and can turn the costly ones into training spots.

fpdb-3 never names a solver node, computes an EV or picks a simulation: that
is PreflopAdvisor's side ([PreflopAdvisor#22](https://github.com/jejellyroll-fr/PreflopAdvisor/issues/22)).

## Using it

- **Replayer**: *Solver review...* next to *Share...*. The review points at the
  hero's preflop decision on screen (the one just played, else the next one;
  once past preflop, the last one), or at every hero decision of the hand.
- **Hand Viewer** and **tournament hand viewer**: right-click a hand,
  *Solver review (PreflopAdvisor)...*.

The dialog shows the preflop line with the hero's decisions marked. Then:

- **Open in PreflopAdvisor** writes the document to a temporary folder
  private to the user and made once per session (`fpdb-hand-reviews-<random>/`,
  by `tempfile.mkdtemp`: never a fixed name in the shared temporary directory),
  as a new `fpdb-hand-review-<id>-<random>.json` for every launch, so a
  PreflopAdvisor still starting never finds its document rewritten by a second
  click. It then starts PreflopAdvisor on it with
  `--review <file>` (PreflopAdvisor's own option), which opens *Review Hands*
  with the document loaded. Each click starts a new PreflopAdvisor window.
- **Save for PreflopAdvisor...** saves the JSON (or **Copy JSON** copies it), to
  load in PreflopAdvisor with *Review Hands > Load a hand review*.

### Where PreflopAdvisor is

fpdb-3 starts, in this order:

1. the program the user located, remembered as the optional `preflop_advisor`
   attribute of `<general>` in `HUD_config.xml` (the shipped templates do not
   carry it), as long as it is still there;
2. the `preflop_advisor` console script on the PATH (`uv tool install`,
   `pip install`).

A file counts as a program only if it may be executed (Windows has no such
bit). When neither can be found, or the program does not start, the dialog
asks where PreflopAdvisor is; the answer is remembered once it has started, so
a program that does not start is never retried on later reviews. A review that
cannot be written (a full or missing temporary folder) is reported as such,
without asking for another program. On macOS a `PreflopAdvisor.app` bundle can
be chosen; it is started through `open -n -a … --args`.

## The document

Code: `fpdb_3_legacy/hand_review_payload.py` (`build_hand_review`,
`review_document`). One document holds one hand or many, so a batch review of
selected hands writes the same format: `review_hands(hands)` describes each
hand and returns the refused ones with their code, which `review_document(...,
skipped=...)` lists under `skipped` (`{"hand", "code", "message"}`) beside the
hands it could describe.

```json
{
  "version": 1,
  "schema": "fpdb-3/preflop-hand-review",
  "source": "fpdb-3",
  "generated_at": "2026-10-02T12:00:00+00:00",
  "hands": [ { ... one hand ... } ]
}
```

`version` is the one PreflopAdvisor's reader checks (`PAYLOAD_VERSION` in
`preflop_advisor/hand_review.py`); it refuses any other. A change a version-1
reader would misread needs a new number. Fields may be added: readers ignore
the ones they do not know.

### One hand

The fields PreflopAdvisor reads:

| Field | Meaning |
| --- | --- |
| `hand_id` | The fpdb database id of the hand (as a string), or `site#hand number` when the hand was not loaded from the database. |
| `played_at` | Start time, ISO 8601. |
| `hero` | The hero's seat, named as below. |
| `hero_cards` | The hero's hole cards, concatenated (`AhQd`, `AsAdKhQh`). |
| `game` | `NL` (no-limit hold'em), `PLO`, `PLO8`, `PLO5` (pot-limit). |
| `table_size` | Players dealt in. |
| `effective_stack_bb` | The hero's starting stack capped by the deepest opponent's, in big blinds. |
| `ante_bb` | The ante per seat, in big blinds (a big-blind ante paid for the table is spread over the seats). |
| `site`, `stake_label` | Labels only. |
| `seats` | Seat names in preflop acting order, blinds last. |
| `actions` | Every preflop action in order, folds included: `{"seat", "action", "to_bb"}`. `action` is `Fold`, `Check`, `Call`, `Raise` or `AllIn` (a raise that puts the seat all in). `to_bb` is the seat's street total after the action, in big blinds, antes excluded: for a raise, what it raises *to*. It is given for calls too, because PreflopAdvisor reads `amount_bb` in its place when it is missing. EV cash-outs are not decisions and are left out. |

Factual context beside them, for auditing and later readers:

| Field | Meaning |
| --- | --- |
| `fpdb_hand_id`, `site_hand_no`, `table`, `max_seats` | Where the hand comes from. `max_seats` is `null` for a hand read back from the database, which only stores a placeholder. |
| `category`, `limit_type`, `game_type`, `currency`, `tournament` | The game as fpdb stores it; `tournament` holds `tourney_no`, `level`, `buyin`, `knockout` for tournament hands, else `null`. |
| `blinds`, `ante` | Stakes in the hand's own chips or money; `blinds.sb_bb` is the small blind in big blinds. |
| `hero_name`, `hero_seat_no` | Who the hero is, explicitly. |
| `position_scheme` | `preflop-advisor-default`: how seats are named. |
| `players` | Per seat dealt in: `position`, raw `seat_no`, starting `stack` and `stack_bb`, `is_hero`. |
| `hero_decisions` | Indices into `actions` of the hero's turns. |
| `selected_decision` | The hero decision the review points at, or `null` for the whole hand. |

Each action also carries `index`, `street` (`PREFLOP`), `seat_no`, `is_hero`,
the fpdb action (`fpdb_action`), what it put in (`amount`, `amount_bb`), the
seat's street total after it (`to`), `all_in`, the pot before it
(`pot_before`, `pot_before_bb`, antes included), what it faced (`to_call`,
`to_call_bb`) and the effective stack at that moment (`effective_stack`,
`effective_stack_bb`: what the actor had behind, capped by the deepest
opponent still in the hand).

### Amounts

Chip and money amounts are the hand's own values; big-blind values are
computed from them and **never rounded**: a raise to 2.47 BB stays 2.47, and
PreflopAdvisor's matcher decides with its own tolerance whether that is the
tree's 2.5 BB branch.

### Seat names

PreflopAdvisor's default seat names, in preflop acting order:

| Players | Seats |
| --- | --- |
| 2 | SB, BB (the button posts the small blind) |
| 3 | BU, SB, BB |
| 4 | CO, BU, SB, BB |
| 5 | MP, CO, BU, SB, BB |
| 6 | UTG, MP, CO, BU, SB, BB |
| 7 | UTG, MP, HJ, CO, BU, SB, BB |
| 8 | UTG, MP, LJ, HJ, CO, BU, SB, BB |
| 9 | UTG, UTG1, MP, LJ, HJ, CO, BU, SB, BB |

Only the players dealt in count: empty seats and players sitting out do not
shift the positions. The order is fixed by who posted the blinds; the button
is checked against it. The raw seat numbers are kept in `players` and in each
action so the mapping can be audited.

## Hands that are refused

A hand that cannot be described reliably is refused with a reason rather than
sent with invented values (`HandReviewError.code`):

| Code | When |
| --- | --- |
| `unsupported_game` | Not no-limit hold'em or pot-limit Omaha (PLO, PLO8, PLO5). |
| `no_hero`, `hero_not_dealt` | The hand names no hero, or the hero was not dealt in. |
| `hero_cards` | The hero's hole cards are not all known. |
| `unsupported_posts` | A straddle, a dead small blind posted with the big one, a button blind: PreflopAdvisor's model has the two blinds and antes only. Also a blind posted short of the declared stakes (all in for less) and antes of different sizes, which one number per table cannot describe. |
| `ambiguous_position` | Not exactly one small and one big blind, blinds out of order, a button that contradicts them, a listed player who never acts preflop (not dealt in?), or a player sitting out who posts. Heads-up the button is not checked: the seats are named after the blinds, and parsers record the heads-up button inconsistently. |
| `unsupported_table_size` | Fewer than 2 or more than 9 players dealt in. |
| `missing_stacks` | A starting stack or the blinds are missing, or an action puts in more than the stack. |
| `invalid_amount` | An amount in the hand cannot be read as a number. |
| `missing_preflop`, `unsupported_action` | No preflop action recorded, or one a review cannot describe. |
| `no_hero_decision` | The hero never acted preflop (a walk). |

## Transport

The document goes through a `HandReviewTransport` (`send(document) -> str`):

- `JsonFileTransport` writes the file PreflopAdvisor loads;
- `PreflopAdvisorTransport` writes it, then starts PreflopAdvisor on it with
  `--review`, detached and without a shell. A write failure raises the
  write's `OSError`; a program that does not start raises `LaunchError`. The launcher is injected
  (`QProcess.startDetached` in the dialog), so the module stays free of Qt.

A local API, or handing the document to a PreflopAdvisor already running,
would be another transport; the normalization does not change.
