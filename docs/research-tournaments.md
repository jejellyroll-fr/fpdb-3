# Research for tournaments

The [quick start](research-quick-start.md) teaches the Research Browser with
cash-game examples, and the shipped cash studies are six-max, hundred-blind
questions. A tournament is not that question with one more filter on it: the
same seat plays a different game at twelve big blinds and at sixty, and an
answer that averages the two is the mean of two games rather than one number.

This guide is the tournament path: where the studies are, what they break down
by, and what fpdb deliberately does not claim to know about a tournament.

## Start from the tournament study pack

Open **Research → Study Explorer** and set **Format** to *Tournaments*. The
spots, the counts and the study list are the tournament ones from that point
on; the cash packs declare themselves cash and are not offered, in the same way
the Hold'em packs are not offered for an Omaha database.

| Spot | What the shipped studies cover |
| --- | --- |
| **Preflop** | first in · facing an open · the opener facing a 3-bet · blind defence · facing an all-in · shoving |
| **Single-Raised Pots** | the raiser in and out of position, the defender facing the bet, and the turn |

Every one of them opens in Hero-versus-Field, keeps its source hands, and can
be narrowed by seat, opposing seat, table size, stake, site and date.

## Effective stack is the axis, not a filter

Each tournament study carries a **stack depth** panel and a **stack depth ×
position** matrix, and most of them open on the depth breakdown rather than on
a single headline. The bands are the ones a tournament is actually played in:

| Band | Reading |
| --- | --- |
| 10 BB or less | a commitment decision; raising and shoving are the same move |
| 10–15 BB | still commitment, with one fold-equity lever |
| 15–25 BB | the last band where a raise can be called and folded to |
| 25–40 BB | opening ranges start behaving like ranges |
| 40–60 BB | postflop play returns |
| 60–100 BB | a cash-shaped stack |
| 100 BB+ | deeper than most of a tournament |
| Depth not recorded | the decision carried no effective stack; not a short one |

The bands are data rather than query semantics: they live in a table a caller
can replace (`fpdb_3_legacy/stack_depth_buckets.py`), and the same table
generates both the Python band and the SQL the panel groups by, so a histogram
built in either place tiles the same way.

`Stack depth band` is also available as an ordinary filter and breakdown in the
Research Browser, next to `SPR band`, for questions the packaged studies do not
ask.

### The mixed-depth warning

When a tournament study's headline covers both the commitment bands (25 BB and
below) and the deeper ones, the dashboard says so above the panel and names the
bands it is averaging. The warning disappears when stack depth is the breakdown
axis — showing the bands apart is not averaging them — or when a cross-filter
narrows the question to one band.

It is not a precision footnote. It means the number on screen is the mean of
two different games.

## Postflop: SPR as well as depth

The single-raised-pot studies break down by **SPR band** as well as by stack
depth, because the two answer different questions: the stack says what kind of
tournament decision this is, and the SPR says whether this particular pot can
still be played. Board suit and pairing, bet sizing and the size faced are
there too, as they are in the cash packs.

## What fpdb does not know about your tournament

fpdb stores hands, blinds, stacks and results. It does not store payouts, field
size at the time of a hand, or how close a table was to a pay jump — so nothing
in this pack reports bubble, final-table or ICM context, and no study infers a
stage from a stack. Twelve big blinds late in a slow structure and twelve big
blinds in a turbo are the same row here, because they are the same row in the
database.

Observed shove and call frequencies are a record of what happened, not a
push/fold solution. A band where you shove 38% of the time is telling you what
you did; it is not saying that 38% was correct.

## Before you trust any of it

Read the sample beside the frequency. Shallow bands fill up quickly in a
turbo and slowly everywhere else, and a 60 BB+ band in a tournament database is
often a handful of early-level hands. Every row carries its denominator, and a
row under the study's minimum says so rather than colouring itself.
