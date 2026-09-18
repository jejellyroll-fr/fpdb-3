# Filtered Hold'em range explorer (#301)

The 13x13 grid in the ring-stats tab answers one question in 169 cells: **with
which hands did this population do this?** Each cell is a starting-hand class,
and the numbers in it come from the query engine (`docs/query-engine.md`)
grouped by class, so a cell and its hands are the same population.

```bash
python tools/range_explorer.py --filter hero=true --view sample
python tools/range_explorer.py --metric raise_frequency --filter pot_type=three_bet --view frequency
python tools/range_explorer.py --filter position=btn --metric fold_frequency --view frequency --min-sample 10
python tools/range_explorer.py --filter hero=true --view profit
python tools/range_explorer.py --filter hero=true --cell AA --hand-ids
python tools/range_explorer.py --views
```

In the GUI it is the same grid: the "Filtered range" combo switches the measure,
the min-sample field moves the threshold, the cells' tooltips carry the raw
counts, and a double-clicked cell emits `cell_activated(label)` so the caller can
open its hands.

## One definition of a class, on both sides of the wire

`fpdb_3_legacy/holdem_classes.py` owns the classes and reuses the codebase's
canonical numbering rather than inventing one: `Card.twoStartCards` is the class
id (1..169, the primary key of the `StartCards` table) and
`Card.twoStartCardString` is the label. The engine's `starting_hand_id`
dimension is the same classification in SQL, over the hand-player's `card1` /
`card2`, and a test runs **every one of the 2 809 ordered card pairs** through
both and asserts they agree. That is what makes a grid cell and a filter the same
population instead of two implementations of the same idea.

| Class | Combinations | Written |
| --- | --- | --- |
| pair | 6 | `AA` |
| suited | 4 | `AKs` |
| offsuit | 12 | `AKo` |

169 classes, 1326 combinations: the arithmetic a range share rests on, asserted
in the tests. A label that does not say what it means is refused — `AK` is not
read as `AKo`, because suitedness is half of what the class means, and `KAo` is
not quietly reordered.

## The cards nobody saw

This is the reason the explorer is a module and not a one-liner. A hand history
records the hero's cards and the cards of whoever reached a showdown; everyone
else's hole cards are simply not in the database. Those decisions are counted in
their own cell — `xx`, the unknown class, 170 in the codebase's numbering — and
are **never** spread across the other 169. A range that borrows from hands nobody
saw is a made-up range, and it would make every other cell quietly wrong.

On the golden corpus that is 251 of 326 decisions, and the tests pin it: the grid
of the whole corpus holds 75 known decisions and 251 unknown ones, a player whose
cards never appear gets an all-unknown grid rather than an empty-looking one, and
`--filter hole_cards_known=true` moves every decision into the 169 classes with
nothing left over.

## The four views

| View | Unit | Reads |
| --- | --- | --- |
| `frequency` | bp | the query's own numerator rate in that class |
| `sample` | count | decisions in the class (the cell's sample, not its strength) |
| `profit` | cents | the hand result of the hand-players whose decisions reach it (#300) |
| `ev_adjusted` | cents | the same money with the priced all-in pots marked to equity |

Money follows #300's rule, because it is #300's report underneath: the result of
a hand belongs to the hand, not to each of its decisions. Grouping by a class is
a *decision* split, so **cells never sum to the total** — a hand-player counts in
every class their decisions reach. The matrix says so, checks what must hold
(decisions partition the population exactly; every pair behind the grid is a pair
of the population), and takes its totals from the ungrouped report. A cell below
the sample threshold is marked, not hidden: its count is a fact, the colour is an
interpretation.

## Scope

Hold'em only, deliberately. Two cards of an Omaha hand are not a Hold'em starting
hand, so classifying them would produce a well-formed, meaningless grid: a
population that is not Hold'em is refused by name, with the categories that are
not (`filter game=holdem` narrows it). The check is on the population the filters
select, not on the database.

## Drill-down

`cell_query(query, "AKs")` is the cell as a query of its own — its class *is* a
filter value, so the hands it returns are the hands it counted — and
`cell_hand_ids` is that query's answer, ready for the hand viewer. `--cell
AKs --hand-ids` does the same at the shell, and reports the class's combinations
and its share of all 1326.
