# Research Browser for Omaha

The [quick start](research-quick-start.md) teaches the browser with Hold'em
examples. This guide is the same tool read from an Omaha seat: what every group
of options is for, which ones carry the weight in a four-card game, and the two
that cannot work at all.

Nothing here is Omaha-only in the engine. The situations, the board features and
the hand states are derived for every game fpdb stores — an Omaha database is a
first-class citizen, not a degraded Hold'em one.

## Read the value, not the selector

One thing to learn before anything else, because it silently changes answers.

A filter with a closed set of values has **two** controls: a selector, and a
field beside it. The selector is a multi-choice — click a line in its list to
tick it (`＋ facing a c-bet` becomes `✔ facing a c-bet`), and the chosen value
appears in the field. **The field is what the query reads.**

If the field is empty, the filter does not exist, whatever the selector shows.
The sentence under **Run** is the other half of the check: it restates the
question in plain language, and a filter that is not applied simply is not in
it.

## The four parts of a question

| Part | What goes in it |
| --- | --- |
| **Who** | `Hero` — *Yes* for your own decisions, *No* for the pool, *Any* for both |
| **Situation** | the spot: facing a c-bet, facing limpers, a donk-bet opportunity… |
| **Metric** | what you count: a frequency, money, a size, an SPR |
| **Breakdown** | how the answer splits into rows: by position, by texture, by depth |

The **Situation** is the spine. Without it you are measuring every decision in
the database at once, which is a number, not an answer.

## The filter groups, and what they are worth here

### Situation (`action`)

The vocabulary is the same for every game, and the Omaha spots are all in it:
`open_limp`, `over_limp`, `facing_limpers`, `facing_open`, `facing_cbet`,
`donk_spot`, `squeeze`, `facing_3bet`.

Limping is where Omaha differs most from modern Hold'em. If `open_limp`,
`over_limp` and `facing_limpers` are among your most frequent situations, that
is not noise — it is the game. Study the limped pot as a pot type of its own,
not as a mistake.

### Seat and stack (`seat`)

`Position`, `In position`, `Players in the hand`, `Effective stack (BB)`,
`Stack depth`, **`SPR`**.

SPR earns its place at the top in Omaha. Stack-to-pot ratio decides whether a
made hand can play for stacks or is drawing thin against the field: at SPR 2 a
top pair with a draw is a shove, at SPR 10 it is a trap. Filter on it, or break
down by `Stack depth` and read the shape of the answer.

`Players in the hand` and `Multiway` matter more than in Hold'em for the same
reason: equities run closer, so the number of opponents changes the right answer
rather than just the variance.

### Board (`board`)

`Board texture`, `Board connectivity`, `Board pairing`, `Board suit structure`,
`Board high card`, `Runout`.

Four cards see more of every board, so texture moves the answer further than it
does in Hold'em. A connected or two-tone flop changes who is ahead far more
sharply. `Board connectivity` is the most useful single breakdown in an Omaha
postflop study.

### Sizing (`sizing`)

`Bet size (% of pot)`, `Bet size faced (% of pot)`, and their buckets.

Pot-limit constrains the sizes available, which makes the distribution
informative rather than arbitrary: a player who only ever bets pot is telling
you something a no-limit player would not.

### Hand strength (`strength`)

`Made hand`, `Draw (any of)`, `Blocker (any of)`, `Hand strength`, `Pair detail`.

This is where Omaha is actually played, and the hand states are derived for it.
Only decisions whose cards were shown are classified — nobody's holding is
guessed at — so these filters narrow the population to the hands you can
genuinely reason about.

### Street and action context (`street`)

`Is the preflop aggressor`, `In position versus the bettor`, `Multiway`,
`Pot odds`, `Pot before the action`, `Facing an all-in`.

### Who (`who`)

`Hero` and `Player`. Leaving `Hero` at *Any* is a real question — the whole
population — it is just not the question "how do **I** play". The sentence under
the filters says which one you asked.

## What does not work in Omaha

**The 13x13 range grid, and the `Starting hand` filter.** Two of a four-card
hand are not a starting hand: classifying them would produce a full, well-formed
and meaningless picture. The engine refuses a population that is not Hold'em
rather than drawing it, and says so. Ignore the *Range 13x13* view; it is not
broken, it is declining.

Everything else — situations, positions, boards, sizings, strengths,
profitability — is yours.

## Three questions worth asking of an Omaha database

### 1. Do I over-limp too much?

1. **Situation** `over-limp behind limpers`
2. **Hero** *Yes*
3. **Metric** `frequency`
4. **Breakdown** `Position`

Read the late-position rows against the early ones. Over-limping on the button is
a different decision from over-limping under the gun.

### 2. Do I fold too much to c-bets on connected boards?

1. **Situation** `facing a continuation bet`
2. **Hero** *Yes*
3. **Metric** `fold_frequency`
4. **Breakdown** `Board connectivity`

The seat facing the bet is the only one that can fold to it, which is what makes
the question answerable. Compare the connected row with the dry one.

### 3. Does stack depth change my aggression against limpers?

1. **Situation** `facing limpers`
2. **Metric** `raise_frequency`
3. **Breakdown** `Stack depth`

An iso-raise is a different proposition at 40 big blinds and at 200. This asks
whether your game knows that.

## Before you trust any of it

Read the **denominator**. A frequency over 12 decisions is a rumour; the same
frequency over 12,000 is a fact. Both numbers sit beside every percentage for
that reason, and a row under the sample threshold says so instead of colouring
itself.

If every question answers zero, the database's analytics rows have not been
derived yet: **Database → Rebuild Analytics Data**. The browser says so under an
empty answer rather than leaving you to guess.
