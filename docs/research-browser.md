# The research browser (#303)

The analytics layers each answer one kind of question: the query engine (#297)
answers "how often / how much, grouped how", the profit report (#300) labels
what the money means, the range explorer (#301) draws the grid, the hand-state
composition (#302) counts what players held. The research browser is the
surface that puts **one question, its result and its hands** on one screen:
filters on the left, the result in the middle, the hands behind a row on the
right — built without writing SQL, and openable in the replayer with a
double-click.

## Where it lives

| Piece | File | Qt? |
|---|---|---|
| Model: filter specs, presets, result, drill-down | `fpdb_3_legacy/research_browser.py` | no |
| Tab: the three panes, the worker threads | `fpdb_3_legacy/GuiResearchBrowser.py` | yes |
| Entry point | Cash menu → **Research Browser** (`fpdb.pyw`, `menu_layout.py`) | — |

The model is deliberately Qt-free: the same calls the tab makes are the ones
`tests/test_research_browser.py` exercises against the golden corpus, without
a window. The tab renders what the model answers and forwards what the user
expresses back to it as engine vocabulary — it never builds SQL.

## The three panes

**Filters.** Every filter the engine defines (all ~60 of them, described from
the engine's own tables, grouped: who / seat / street / action / cards /
sizing / board / strength) can be added and removed without restarting the
query definition. Booleans are checkboxes, ranges are two bounds, everything
else is a token list the engine validates at compile time. The metric picker
offers the engine's `KNOWN_METRICS`; "Group by" takes a comma-separated list
of dimension names.

**Results.** The table shows the group keys, then the **denominator**
(decisions), the **numerator**, and the value — a frequency row therefore
always shows both halves of its percentage, and the frequency in percent.
The **sample size** sits above the table (`25 decisions`), computed over the
whole population even when the row list is paged. Single-clicking a row says
which slice it stands for; double-clicking loads its hands.

**Matching hands.** The drill-down of the selected row: by default all the
hands in the row's *population* (the denominator — the hands the question was
asked about), or only the hands where the metric fired (the numerator), with
the switch above the table. Columns are the ones a human scans: hand id,
time, site, game, bb, seats, player name, that player's profit, their cards
when the rows store them, the board, the pot. A truncated list says so, with
the count of everything the query matched. Double-click opens the hand in the
replayer.

## What a preset is (and is not)

A preset is a named question: a metric name, filter names with their values,
group-by dimension names, and an optional description. It is stored as JSON
in `research_presets.json` next to the fpdb config, **never** as SQL — the
format holds engine vocabulary, and `validate_preset` checks every name
against the engine's own tables on the way in *and* on the way out, so a file
edited by hand is read through the same validation a GUI write went through.
One bad entry in the file is named, logged and skipped; the other presets
still load. Saving and deleting rewrite the file atomically.

## Honesty rules carried over

* **Empty states explain.** No rows, or a population that matched nothing:
  the note under the table says *why* ("no matching hands"), and the sample
  size reads `0 decisions` rather than a silent empty table. A metric the
  engine refuses for this population carries the refusal as text.
* **Numerator and denominator are both shown.** A frequency without its
  counts is a claim; here every row carries both.
* **A row is a filter.** The hands behind a grouped row are the population
  query plus the row's group key — the drill-down cannot select a different
  population than the result did, because it *is* the same query.
* **Sample size is the population's.** Paging the rows never shrinks the
  stated totals: the browser counts the ungrouped population separately when
  the result is paged.

## Performance contract

Queries and drill-downs run on worker `QThread`s (the ring-stats pattern) —
the Qt event loop never waits on the database. Every query carries a serial
number; a finished query whose serial is no longer current is **dropped**, so
a slow first answer cannot overwrite a newer one. Cancel stops *waiting*
(bumps the serial, clears the state) rather than killing a thread the engine
is running on. Results are rendered after the worker's own signal was
received, so a fast follow-up query cannot race a slow first render.

## Programmatic use

```python
from fpdb_3_legacy import research_browser as rb

result = rb.execute_preset(db, {
    "metric": "fold_frequency",
    "filters": {"primary_situation": "facing_cbet", "hero": True},
    "group_by": ["street"],
})
print(result.sample_text, result.rows)

drill = rb.run_drill_down(db, result.query, group={"street": "flop"},
                          numerator_only=True, limit=50)
print(drill.total_matches, drill.truncated, drill.rows[0]["handId"])

store = rb.ResearchPresets(directory="/path/to/config/dir")
store.save("hero folds vs cbet by street", {...})
```
