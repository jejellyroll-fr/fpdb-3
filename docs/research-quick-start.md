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

Click a row and the line under the filters restates which slice it stands for.
**Double-click the row** to fill the right-hand pane with the hands behind it.
The selector above that list chooses between *All hands in the population* —
every hand the question was asked about — and *Only the hands where the metric
fired*. **Double-click a hand to open it in the replayer.**

## Save your own question

**Save preset** writes your question as a named preset next to your fpdb
configuration. It is stored as the same vocabulary the built-ins use, never as
SQL, so it keeps working as the engine changes and can be shared as a file.

## Worked examples

### 1. Is my button open too loose?

1. Preset **Open raise (RFI) by position**.
2. Set **Hero** to *Yes*. The preset asks the question of everyone at the
   table, so without this the rows are the pool's opens and not your own.
3. Breakdown **Position**.
4. Look at the **BTN** row: the numerator over the denominator is your opens
   out of the times it folded to you. Compare with the **CO** row above it.

Leaving **Hero** at *Any* is a perfectly good question too — it is just a
different one, and the sentence under the filters says which you asked.

### 2. Do I fold too much to c-bets on wet boards?

1. Preset **Fold versus a flop c-bet, by bet size**. Its metric is *fold
   frequency* and its situation is *facing a continuation bet* — the seat that
   faced the bet is the only one that can fold to it, which is what makes the
   question answerable.
2. Set **Hero** to *Yes*.
3. Replace the breakdown **Bet size faced** with **Board connectivity** (or
   **Board suit structure**) to read the fold on each texture.

The mirror question — how often the c-bet you *made* is respected — is a
different population: start from **Flop c-bet by board suit structure**, whose
situation is the c-bet opportunity rather than the defence.

### 3. How deep can I 3-bet?

1. Preset **3-bet by position**. Its denominator is the times you faced a
   single open raise.
2. Set **Hero** to *Yes*.
3. Add the filter **Effective stack (BB)** with a range such as `40` to `100`.
4. Breakdown **Stack depth** to see where the 3-bet rate drops.

Raising over a *limper* is a different spot — an iso-raise, not a 3-bet — so it
is a different question rather than a filter on this one: change the
**Situation** to *facing limpers* and ask it on its own.

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
