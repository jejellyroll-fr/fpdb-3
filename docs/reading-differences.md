# Reading differences responsibly

The Study Explorer will tell you that you fold to flop c-bets 53% of the time
and the field folds 39%. That is a fact about your database. Everything you do
with it after that is an inference, and this page is about which inferences the
number supports.

## What "Field" is

**The field is what the other players in your own database did.** Not a
solution, not a population average for your stake, not a theoretically correct
frequency. If you play one table of a soft game, the field is that table. If
you have imported six months of a tough game, the field is that.

fpdb has no solver and no theoretical baseline, and does not pretend to one. A
gap against the field says *you and the people you play differ here*. Which of
you is wrong is a poker question, and the software does not have an opinion.

Three consequences worth holding on to:

* **A field that folds too much makes you look like a maniac.** Your 55%
  c-bet is not aggressive; their 38% fold is passive. Same gap, opposite
  reading.
* **The field includes every style at once.** It is a mean over nits, stations
  and maniacs. Nobody plays the field's frequency, and matching it is not a
  goal.
* **You are not in the field.** The two sides are the same query with the
  population identity flipped, so your own hands never dilute the baseline you
  are compared against.

## A large gap is a review candidate, not a leak

*Biggest Differences vs Field* ranks rows by |gap| × the smaller sample. That
ranking is a **review priority**, and the page says so on screen: it is not EV
loss, not statistical significance, and not a list of mistakes. It is "these
are the spots where you and the people you play most visibly disagree — go and
look".

A gap is worth opening. It is not worth acting on until you have found out
*why* it is there. Sometimes the answer is "because I play better than them",
which is a gap you keep.

## Samples matter, and the page shows you both

Every row carries two samples: yours and the field's. The smaller one is the
one that limits the row.

* Under a hundred decisions, a frequency moves several points on the strength
  of a handful of hands.
* Your sample is almost always much smaller than the field's — the field is
  five opponents per hand and you are one.
* A row flagged as low sample is a *lead*, not a reading. It is shown because
  hiding it would be its own kind of lie, and marked because a precise-looking
  percentage over nineteen hands invites a conclusion it cannot support.

## Four things that explain a frequency gap without anyone playing badly

Before "I fold too much", check whether the population is comparing like with
like. Each of these has a panel or a cross-filter in the study.

**Composition.** You are one player with one range; the field is everybody. If
you only enter this spot with a tight range and the field enters it with
everything, your continuation frequency *should* differ.

**Position.** Aggregate the seats and you have averaged two different games.
Break the spot down by position before concluding anything from the headline —
the position matrix is one tab away.

**Stack depth.** Especially in tournaments: twelve big blinds and sixty are not
the same decision. A tournament study warns you on screen when a headline
averages depths that play differently, and the stack-depth panel splits them.

**Board and sizing.** A gap in "fold to c-bet" often lives entirely in one
texture or one size. Cross-filter to it and the rest of the gap frequently
disappears — which tells you something far more useful than the headline did.

## What the source hands are for

The hands behind a row are not decoration; they are the step that turns a
number into a read. Open your own population, then the field's, and look at
what the decisions actually were. A difference you cannot see in the hands is
usually a difference in who was dealt in rather than in how anybody played.

Hole cards are shown only where the database recorded them, so the field's
cards are mostly unknown and the pane says so. That is a limit of the data, not
a bug: you learn an opponent's cards at showdown and nowhere else.

## The short version

* Field = observed, not optimal.
* Gap = a place to look, not a verdict.
* The smaller sample is the one that counts.
* Composition, position, stack and texture explain a lot of gaps.
* Open the hands before you change anything.

---

See also: [Study Explorer quick start](study-explorer-quick-start.md) ·
[Reading the visualizations](study-visualizations.md)
