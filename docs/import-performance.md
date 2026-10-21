# Import performance (#443)

How fast a bulk import goes, where the time goes, and how to measure it.

```bash
python tools/benchmark_import.py                 # sequential
python tools/benchmark_import.py --workers 4     # with equity workers
python tools/benchmark_import.py --files 'regression-test-files/cash/Stars/Flop/*.txt' --repeats 3
```

The tool imports a fixed corpus into a fresh SQLite database in a temporary
directory, configured from a copy of the repository's `HUD_config.xml`, and
splits the time into three phases:

| Phase | What it covers |
| --- | --- |
| parse | the converter reading the file into hands (`HandHistoryConverter.start`) |
| derive | player and gametype lookups and the derived statistics, all-in equity included (`Hand.prepInsert`, `Hand.assembleHand`) |
| workers | with `--workers`: starting them, handing them the files, collecting their results |
| write | everything else: the inserts, the caches, auto notes |

The default corpus is the cash hand histories of six rooms in
`regression-test-files/` (PokerStars, Winamax, GGPoker, PartyPoker, iPoker,
888): 198 files and 723 hands, Hold'em and Omaha, full ring and short-handed.

## Results

Apple M-series, 10 cores, SQLite, best of two runs:

| Version | Total | Hands/s | parse | derive | write |
| --- | --- | --- | --- | --- | --- |
| before #443 | 14.85 s | 48.7 | 1.27 s | 8.72 s | 4.86 s |
| auto-notes lookup fixed | 10.72 s | 67.5 | 1.18 s | 8.23 s | 1.30 s |
| + 4 equity workers | 6.66 s | 108.6 | 1.39 s | 3.74 s | 1.49 s (+ 0.04 s workers) |

## Where the time went

**Parsing was never the bottleneck**: about a tenth of the import.

**Auto notes walked the whole configuration.** Each rule switch looked the
`<autonotes>` element up with `getElementsByTagName`, a recursive walk of the
whole `HUD_config.xml`, about ten times per hand: a third of the import. It is
a direct child of the root, which is now the only place looked at.

**Exact all-in equity is most of what is left.** The stored `allInEV` comes from
an exhaustive `poker_eval` enumeration. It takes about 50 ms for a Hold'em
preflop all-in and up to half a second for a multiway Omaha one, which is 63 %
of the import once auto notes are fixed. Almost no two requests repeat, so a
cache does not help, and `poker_eval` holds the GIL, so threads do not either.
Switching to Monte Carlo would be fast, but it would change the stored values.

## Equity workers

`fpdb_3_legacy/import_prefetch.py`: worker processes parse the files ahead of
the import and derive their hands, which computes those equities, and hand the
results back. The import itself is unchanged: sequential, one writer, the same
batching. When it reaches a hand, the equity is usually known already.

- **Output.** Exhaustive enumeration is deterministic, so the database is the
  same with or without workers; `tests/test_import_prefetch.py` imports the
  same files both ways and compares every table, timestamps aside.
- **No waiting.** The import uses a worker's result only if the worker has
  finished the file; otherwise it computes the file as before. Waiting rarely
  pays: the import parses and derives the file again anyway, so for a file
  without an expensive all-in the wait is pure loss (measured: waiting for the
  files a worker had started was no faster, within noise). The import publishes
  the place of the file it has reached, and workers skip every file up to it:
  they never compute a file twice, and nothing is computed after the import.
- **The setting.** `threads` sets the number of workers: 1 is none, -1 every
  core but one, up to four (more cost more in start-up and memory than they
  save here). The bulk import window and its command line
  (`GuiBulkImport.py -x`) use -1. Auto-import never starts workers: the HUD
  waits on its latency. The setting used to open database connections that
  nothing wrote through; it no longer does.
- **Configuration.** Workers read a copy of the in-memory configuration in a
  private temporary directory, never the user's file, because building a
  configuration may migrate and save it.
- **Packaged builds.** In a bundle `sys.executable` is fpdb itself, so
  multiprocessing starts each worker as `fpdb --multiprocessing-fork ...` and,
  on macOS and Linux, its resource tracker as `fpdb -B -c "...resource_tracker..."`.
  `subprocess_launch.dispatch_multiprocessing` runs both before the GUI, from
  `fpdb.pyw` and from PyOxidizer's run command; `multiprocessing.freeze_support()`
  would only handle workers, and only on Windows. It works in an emulation of a
  frozen launch, but has not been checked on a built bundle yet, so the bundles
  still import sequentially (the guard in `Importer._start_equity_prefetch`).
  To lift it: build a bundle, bulk import a few files with `threads=-1` through
  `fpdb --run-module fpdb_3_legacy.GuiBulkImport -x -C <throwaway config>`, and
  check that the workers run and that no fpdb process is left behind.
