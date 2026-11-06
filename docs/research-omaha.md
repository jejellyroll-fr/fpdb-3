# Research Browser for Omaha

The [quick start](research-quick-start.md) teaches the browser with Hold'em
examples. This guide is the same tool read from an Omaha seat: what every group
of options is for, which ones carry the weight in a four-card game, and the two
that cannot work at all.

Nothing here is Omaha-only in the engine. The situations, the board features and
the hand states are derived for every game fpdb stores — an Omaha database is a
first-class citizen, not a degraded Hold'em one.

## Start from the PLO study pack, not from a blank question

The browser answers one question at a time. **Research → Study Explorer** is the
other way in: it names the spot first, and a study then reads that one
population through several coordinated panels. fpdb ships a Pot-Limit Omaha pack,
so you do not have to build any of the questions below by hand.

Open the Study Explorer, set **Game** to *Pot-Limit Omaha*, and the spots, the
list and the counts are all the PLO ones — Hold'em studies are not offered,
because a study declares the game it is about.

| Spot | What the shipped studies cover |
| --- | --- |
| **Preflop** | first in, facing an open, the opener facing a 3-bet, squeezing, blind defence |
| **Single-Raised Pots** | the raiser and the caller, in and out of position, flop and turn |
| **3-bet Pots** | the aggressor in and out of position, the defender, flop and turn |

Every postflop study reads the same population through the axes a four-card game
turns on, in this order: **SPR band**, **heads-up versus multiway**, **board suit
and pairing**, **board connectivity**, **sizing**, **effective stack**, the
**result**, and the **source hands** behind any of it.

`SPR band` is new here and is the one to look at first. The stored ratio is a
number, so grouping by it raw gives one row per value; the band groups it the
way the game does — under 1 (committed), 1–2, 2–4, 4–7, 7–13, 13+ — and an
unrecorded pot says `SPR not recorded` rather than pretending to be the lowest
band.

Each study opens in Hero-versus-Field by default, and any selection you make on
a chart narrows **both** sides identically, so the hands behind your number and
the hands behind the field's are one click apart.

### What the PLO pack deliberately does not ship

No 13x13 range grid and no hand-strength panel. Both read two hole cards, and a
four-card hand has no honest two-card reading. A Hold'em study opened against an
Omaha population disables those panels and says which and why, rather than
drawing an empty one.

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

### Hand strength (`strength`) — Hold'em only, for now

`Made hand`, `Draw (any of)`, `Blocker (any of)`, `Hand strength`, `Pair detail`
all read the postflop hand state, and that classifier takes exactly two hole
cards: an Omaha hand's best two are not a Hold'em holding, so it refuses rather
than inventing a class. No Omaha decision is classified, and these filters
return nothing on an Omaha population.

This is a gap rather than a decision — Omaha is where hand strength matters most
— but an honest empty answer beats a plausible wrong one, which is what
classifying the first two of four cards would produce.

The Study Explorer applies the same rule to whole panels: a hand-strength panel
is offered only for a game the classifier reads, and is otherwise disabled with
the reason on the tab. The rule lives in one place, so a variant the classifier
learns later becomes available without anything here changing.

### Street and action context (`street`)

`Is the preflop aggressor`, `In position versus the bettor`, `Multiway`,
`Pot odds`, `Pot before the action`, `Facing an all-in`.

### Who (`who`)

`Hero` and `Player`. Leaving `Hero` at *Any* is a real question — the whole
population — it is just not the question "how do **I** play". The sentence under
the filters says which one you asked.

## What does not work in Omaha

Three things, all for the same reason: two of a four-card hand are not a
Hold'em holding, and the engine refuses to classify them rather than producing a
full, well-formed and meaningless answer.

- **The 13x13 range grid** and the **`Starting hand`** filter. The grid is not
  broken when it declines your population; it is declining.
- **The hand-strength filters** above: `Made hand`, `Draw`, `Blocker`,
  `Hand strength`, `Pair detail`.

Everything else — situations, positions, stacks, boards, sizings,
profitability — is yours, and those are the majority.

## Three questions worth asking of an Omaha database

### 1. What do I do when someone has limped in front of me?

1. **Situation family** `POT_LIMPED`
2. **Hero** *Yes*
3. **Metric** `call_frequency` — then run it again with `raise_frequency` and
   `fold_frequency`
4. **Breakdown** `Position`

The family is the denominator on purpose: it holds every decision taken in a
limped pot, so calling, raising and folding are three answers to one question
and add up like they should.

Asking it the other way round does not work. *Situation* is the **most
specific** label a decision matched, and `over_limp` is only assigned to a
decision that called — so "Situation = over-limp, metric = frequency" measures
over-limps out of over-limps and reports 100% in every populated row. A
frequency whose denominator is its own numerator is not a statistic.

### 2. Do I fold too much to c-bets on connected boards?

1. **Situation** `facing a continuation bet`
2. **Hero** *Yes*
3. **Metric** `fold_frequency`
4. **Breakdown** `Board connectivity`

The seat facing the bet is the only one that can fold to it, which is what makes
the question answerable. Compare the connected row with the dry one.

### 3. Does stack depth change my aggression against limpers?

1. **Situation family** `POT_LIMPED`
2. **Hero** *Yes* — the question says *my*, and the default *Any* answers for
   the whole table instead
3. **Metric** `raise_frequency`
4. **Breakdown** `Stack depth`

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
