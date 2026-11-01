"""Measure bulk import throughput, split into parse, derive and write (#443).

    python tools/benchmark_import.py                     # the default corpus, fresh SQLite
    python tools/benchmark_import.py --files 'regression-test-files/cash/Stars/Flop/*.txt'
    python tools/benchmark_import.py --repeats 3
    python tools/benchmark_import.py --workers 4         # equity workers, as `threads` sets them

Every run imports into a fresh SQLite database in a temporary directory,
configured from a copy of the repository's HUD_config.xml: nothing outside that
directory is read or written. The corpus is a fixed list of regression files,
so two runs on the same machine import the same hands.

The phases:

* parse  -- the converter reading the file into hands (HandHistoryConverter.start);
* derive -- player and gametype lookups and the derived statistics, all-in
  equity included (Hand.prepInsert and Hand.assembleHand);
* workers -- with ``--workers``: starting them, handing them the files and
  collecting their results (EquityPrefetch);
* write  -- everything else: the inserts, the caches, auto notes.

With ``--workers N`` the import starts N worker processes that compute the
all-in equities ahead of it (fpdb_3_legacy/import_prefetch.py); derive then
mostly measures what is left of it.

Results are recorded in docs/import-performance.md.
"""

from __future__ import annotations

import argparse
import gc
import glob
import logging
import shutil
import statistics
import sys
import tempfile
from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# Six rooms' cash histories: Hold'em and Omaha, full ring and short-handed.
DEFAULT_CORPUS = tuple(
    f"regression-test-files/cash/{room}/Flop/*.txt"
    for room in ("Stars", "Winamax", "GGPoker", "PartyPoker", "iPoker", "PacificPoker")
)


@dataclass(frozen=True)
class ImportTiming:
    """One import of the corpus."""

    hands: int
    seconds: float
    phases: dict[str, float]

    @property
    def hands_per_second(self) -> float:
        return self.hands / self.seconds if self.seconds else 0.0


def corpus_files(patterns: Sequence[str]) -> list[Path]:
    files = sorted({Path(path) for pattern in patterns for path in glob.glob(str(REPO / pattern))})
    if not files:
        msg = f"no file matches {', '.join(patterns)}"
        raise SystemExit(msg)
    return files


@contextmanager
def _timed(phases: dict[str, float]) -> Iterator[None]:
    """Add the time spent in the parse, derive and worker methods to ``phases``."""
    from fpdb_3_legacy.Hand import Hand
    from fpdb_3_legacy.HandHistoryConverter import HandHistoryConverter
    from fpdb_3_legacy.import_prefetch import EquityPrefetch

    targets = (
        (HandHistoryConverter, "start", "parse"),
        (Hand, "prepInsert", "derive"),
        (Hand, "assembleHand", "derive"),
        (EquityPrefetch, "__init__", "workers"),
        (EquityPrefetch, "submit", "workers"),
        (EquityPrefetch, "before_import", "workers"),
        (EquityPrefetch, "close", "workers"),
    )
    originals = [(owner, name, getattr(owner, name)) for owner, name, _phase in targets]

    def wrap(method: Callable[..., Any], phase: str) -> Callable[..., Any]:
        def timed(*args: Any, **kwargs: Any) -> Any:
            started = perf_counter()
            try:
                return method(*args, **kwargs)
            finally:
                phases[phase] += perf_counter() - started

        return timed

    for (owner, name, phase), (_owner, _name, method) in zip(targets, originals, strict=True):
        setattr(owner, name, wrap(method, phase))
    try:
        yield
    finally:
        for owner, name, method in originals:
            setattr(owner, name, method)


def import_once(files: Sequence[Path], workdir: Path, workers: int = 1) -> ImportTiming:
    """Import ``files`` into a fresh SQLite database under ``workdir``."""
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.Database import Database
    from fpdb_3_legacy.Importer import Importer

    workdir.mkdir(parents=True, exist_ok=True)
    config_file = workdir / "HUD_config.xml"
    shutil.copyfile(REPO / "HUD_config.xml", config_file)
    config = Config(file=str(config_file))
    params = config.get_db_parameters()
    params.update(
        {
            "db-server": "sqlite",
            "db-backend": 4,
            "db-databaseName": str(workdir / "benchmark.sqlite3"),
            "db-path": "",
        }
    )
    config.get_db_parameters = lambda: params
    schema = Database(config)
    schema.recreate_tables()
    schema.close_connection()

    importer = Importer(caller=None, settings={"testData": False, "threads": workers}, config=config, sql=None)
    # The throwaway database's ids mean nothing to a HUD that may be running.
    importer.setCallHud(False)
    for path in files:
        importer.addImportFile(str(path), "auto")

    phases: dict[str, float] = defaultdict(float)
    started = perf_counter()
    with _timed(phases):
        stored, *_rest = importer.runImport()
    seconds = perf_counter() - started
    # Every connection closed, or Windows cannot remove the temporary directory.
    importer.close()
    phases["write"] = seconds - phases["parse"] - phases["derive"] - phases["workers"]
    return ImportTiming(hands=stored, seconds=seconds, phases=dict(phases))


def benchmark(files: Sequence[Path], repeats: int, workers: int = 1) -> list[ImportTiming]:
    timings = []
    # On Windows the import can keep a handle on the database file after every
    # connection the benchmark sees is closed; a directory left behind in the
    # temporary folder must not fail the measurement.
    with tempfile.TemporaryDirectory(prefix="fpdb-import-bench-", ignore_cleanup_errors=True) as root:
        for run in range(repeats):
            timings.append(import_once(files, Path(root) / f"run{run}", workers))
        gc.collect()
    return timings


def format_timings(files: Sequence[Path], timings: Sequence[ImportTiming]) -> str:
    best = min(timings, key=lambda timing: timing.seconds)
    lines = [
        f"{len(files)} files, {best.hands} hands, best of {len(timings)} run(s)",
        f"  total   {best.seconds:7.2f} s   {best.hands_per_second:7.1f} hands/s",
    ]
    for phase in ("parse", "derive", "workers", "write"):
        share = best.phases[phase] / best.seconds if best.seconds else 0.0
        lines.append(f"  {phase:<7} {best.phases[phase]:7.2f} s   {share:6.1%}")
    if len(timings) > 1:
        lines.append(f"  median  {statistics.median(timing.seconds for timing in timings):7.2f} s")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--files", action="append", help="glob of files to import, relative to the repository")
    parser.add_argument("--repeats", type=int, default=1, help="imports to run; the best is reported")
    parser.add_argument("--workers", type=int, default=1, help="equity worker processes (1: none, -1: automatic)")
    args = parser.parse_args(argv)

    files = corpus_files(args.files or DEFAULT_CORPUS)
    # The import logs every hand; that would be timed too.
    logging.disable(logging.CRITICAL)
    try:
        timings = benchmark(files, max(1, args.repeats), args.workers)
    finally:
        logging.disable(logging.NOTSET)
    print(format_timings(files, timings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
