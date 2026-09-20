# Research Browser in five minutes

This is the *user* guide. It leads with the question you want answered, not with
how the engine stores it. For the implementation, follow the links at the end.

You need a database with some hands in it. If you just want to look around
first, build the demo workspace, which invents everything:

```sh
python tools/make_demo_workspace.py          # writes ~/fpdb-demo
```

then open `~/fpdb-demo/HUD_config.xml` in fpdb. Every player in it is fictional.

## Open it

**Cash → Research Browser**. Three panes: the question on the left, the answer
in the middle, the hands behind a row on the right. Nothing you do here changes
your hands or your configuration — it only reads.

## The four words you need

| Word | What it means in poker |
| --- | --- |
| **Population** | *Who the question is about.* "Everyone at 6-max", "only the button", "only hero". |
| **Situation** | *The spot.* "Facing a flop c-bet", "opening the pot", "big blind facing a button open". |
| **Metric** | *What you measure.* "How often" (a frequency), "how much money" (profit), "how big" (sizing). |
| **Breakdown** | *How the answer is split into rows.* "By position", "by street", "by bet size". |

A complete question is those four. The plain-language sentence under the
filters restates what you have chosen, so you can check you asked the right
thing before running it.

## Run a built-in preset

The **Presets** menu ships with the library — more than forty questions,
grouped into *preflop*, *postflop*, *pot type*, *board*, *range*, *population*
and *profit*. Examples you can click straight away:

- **Open raise (RFI) by position** — who opens, seat by seat.
- **Fold versus a flop c-bet, by bet size** — how the c-bet size changes the fold.
- **Flop c-bet by board suit structure** — rainbow vs two-tone vs monotone.
- **Population: 3-bet by position** — the pool's baseline, not just yours.
- **EV-adjusted result by position (all-in EV)** — luck removed from the money.

Pick one and press **Run**. The table shows one row per breakdown value, with
the denominator (decisions) and numerator always beside the percentage.

## Read the answer

- **Sample size** above the table is the number of decisions behind the whole
  population, not just the page you can see. "40% over 12 decisions" is a rumour;
  "40% over 12,000" is a fact. The cell that is too thin says so.
- **Denominator** is how many times the question applied (the chances).
- **Numerator** is how many of those it fired (the folds, the raises, the calls).
- A frequency is numerator ÷ denominator. Both are shown so you never have to
  trust a bare percentage.

## Change a preset

Edit any filter, metric or breakdown and press **Run** again. The pickers are
the engine's own vocabulary written as poker words: *Position*, *Opponent
position*, *In position*, *Facing action*, *Effective stack (bb)*, *Bet size*,
*Board* — the beginner view offers the common ones, and **Expert** reveals the
rest.

## Look at the hands

Click a row to see which slice it stands for, then **Show hands**. The list is
the population of that row — every hand the question was asked about — or switch
to the numerator to see only the ones where it fired. **Double-click a hand to
open it in the replayer.**

## Save your own question

**Save preset** writes your question as a named preset next to your fpdb
configuration. It is stored as the same vocabulary the built-ins use, never as
SQL, so it keeps working as the engine changes and can be shared as a file.

## Worked examples

### 1. Is my button open too loose?

1. Preset **Open raise (RFI) by position**.
2. Breakdown **By position**.
3. Look at the **BTN** row: the numerator over the denominator is your opens
   out of the times it folded to you. Compare with the **CO** row above it.

### 2. Do my c-bets get respect on wet boards?

1. Preset **Flop c-bet by board suit structure**.
2. Run it, then change the breakdown to **This player's response** to see how
   often you are *folding* to a c-bet on each texture, rather than making one.

### 3. How deep can I 3-bet a limper?

1. Preset **3-bet by position**.
2. Add the filter **Effective stack (bb)** with a range such as `40` to `100`.
3. Breakdown **By effective stack bucket** to see where the 3-bet rate drops.

### 4. Which pot types actually pay me?

1. Preset **Realized profit per decision, by pot type**.
2. Read the rows as money per decision, not per hand — a single big pot cannot
   make a losing spot look profitable.

### 5. What do I hold when I face a flop bet?

1. Preset **Made-hand distribution when facing a flop bet**.
2. The rows are *air*, *pairs*, *sets*, draws — the strength composition of your
   continuing range. Cells that only know some of the cards say so rather than
   guessing.

## Two things this view will not pretend

- **Unknown hole cards.** Range and hand-strength views only use cards the
  database actually stored. A cell that mixes known and unknown cards is
  labelled, so a "range" is never silently drawn from half the sample.
- **Realized money vs EV.** *Realized* profit is what you actually won.
  *EV-adjusted* (all-in EV) is what the same all-ins were worth on average.
  They answer different questions; the profit presets name which one they use.

## Where to go next

- [Analytics concepts](analytics-concepts.md) — the glossary this guide uses.
- [Screenshots and the demo workspace](screenshots.md) — what each picture shows.
- Developer/reference material: [research-browser.md](research-browser.md),
  [query-engine.md](query-engine.md), [stat-definitions.md](stat-definitions.md).
