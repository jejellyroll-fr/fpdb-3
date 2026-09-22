# Screenshots and the demo workspace

Every user-facing picture in the guides comes from the **deterministic demo
workspace**: invented hands, invented players, a throwaway database. Nothing the
guides show uses a private hand history or your configuration, so nothing has to
be redacted before it is shared.

## Build the workspace, then the pictures

```sh
python tools/make_demo_workspace.py                 # ~/fpdb-demo (hands, DB, HUDs, presets)
python tools/capture_wiki_screenshots.py \
    --config ~/fpdb-demo/HUD_config.xml \
    --out docs/images
```

The first command is deterministic: the same corpus, the same database, the same
example question per Research view every run. The second renders each screen
with Qt into a PNG — no desktop, no cursor, no window chrome — so a screenshot is
reproducible rather than retaken by hand.

`tools/make_demo_workspace.py --hands 8000` grows the corpus if you want denser
tables in the images.

## Which picture shows which feature

| File | Screen | What it demonstrates |
| --- | --- | --- |
| `research-landing.png` | Research, first open | The guided empty state and the built-in presets |
| `research-summary.png` | Research, Summary view | One question, its population and the sample size |
| `research-table.png` | Research, Table view | A grouped result: denominator, numerator, value per row |
| `research-frequencies.png` | Research, Frequencies view | Frequency rows with both halves of the percentage |
| `research-sizing.png` | Research, Sizing view | Bet sizes across the configured buckets |
| `research-position.png` | Research, Position view | The same question, seat by seat |
| `research-board.png` | Research, Board view | Board texture as a breakdown |
| `research-range.png` | Research, Range view | The 13×13 grid, unknown cells labelled |
| `research-hand-strength.png` | Research, Hand strength view | Air / pair / set / draw composition |
| `research-profit.png` | Research, Profit view | Realized money beside the EV-adjusted result |
| `research-hands.png` | Research, matching hands | The hands behind one row, ready for the replayer |
| `hud-preferences-dynamic-panels.png` | HUD Preferences, Dynamic Panels | The rule editor and its preview |
| `study-explorer-landing.png` | Study Explorer | The spot-first landing page and study hierarchy |
| `study-differences.png` | Biggest Differences vs Field | A review queue of Hero-versus-Field gaps |
| `study-preflop-overview.png` | Study Explorer, Preflop overview | Hero and Field on a preflop spot |
| `study-srp-overview.png` | Study Explorer, SRP overview | Hero and Field on a single-raised pot |
| `study-sizing.png` | Study Explorer, Sizing | Bet-size distributions for the same spot |
| `study-position-matrix.png` | Study Explorer, Position | A two-seat comparison matrix |
| `study-board-heatmap.png` | Study Explorer, Board | Board texture as a cross-filterable heatmap |
| `study-range-grid.png` | Study Explorer, Range | The 13×13 starting-hand grid |
| `study-hand-strength.png` | Study Explorer, Hand strength | Known-card strength composition |
| `study-profit.png` | Study Explorer, Profit | Realized profit beside all-in EV |
| `study-source-hands.png` | Study Explorer, Source hands | Hero and Field hands behind a comparison |
| `hud-preferences.png` | HUD Preferences | The profile bar and the stat-set tabs |
| `hand-viewer.png` | Hand Viewer | A stored hand, its actions and its cards |
| `hand-replayer.png` | Replayer | The same hand, action by action |
| `ring-player-stats.png` | Statistics | The classic per-player reports |
| `opponents-report.png` | Opponents | A table-wide opponents report |
| `session-stats.png` | Session stats | A session's results |
| `graphs.png` | Graphs | Profit over time |
| `auto-notes-workbench.png` | Auto Notes | Rule-driven notes and card miniatures |
| `stats-guide.png` | Stats guide | The in-app reference for stat names |

The Research shots are driven through the real widgets — filling the builder and
running the query is what clicking a preset does — and each view's example
question is read from the workspace's own `demo_examples.json`, so a screenshot
cannot show a question the workspace does not document.

The Study Explorer shots follow the spot-first path: landing page, differences
queue, study overview, visualizations and source hands. They use the same
deterministic workspace, with its fictional Hero deliberately unlike the field
in a few documented tendencies so the review queue has something to show.

## The two pictures that are taken by hand

Two screens need a table to hang from, and a headless grab cannot provide one, so
they are taken against the same workspace and committed beside the others:

| Picture | How to take it |
| --- | --- |
| a live HUD | Launch fpdb on the demo database, sit at a table, let the HUD draw |
| a HUD popup | Click a HUD cell to open its popup |

If you change what a HUD looks like, retake these by hand following the same
instructions the top-level `README.md` gives, so the set stays consistent.

## Where the files go

`--out docs/images` is what the guides and the README reference. The workspace
writes its own copies under `~/fpdb-demo/screenshots/` when you point `--out`
there instead; that directory is disposable and can be regenerated at any time.

## Do not hand-edit these

A screenshot that drifts from the workspace is worse than no screenshot, because
it is a claim nobody re-checks. Regenerate rather than crop: the two commands
above are the whole procedure.
