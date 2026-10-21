"""A bulk import with equity workers writes the database a sequential one writes (#443).

Most of a bulk import's time went to the exact equity of each all-in. Worker
processes now compute those ahead of the import, which stays sequential with a
single writer; the database must not depend on whether they did.
"""

from __future__ import annotations

import re
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from fpdb_3_legacy import equity, import_prefetch
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden

REPO = Path(__file__).resolve().parent.parent
STARS = REPO / "regression-test-files/cash/Stars/Flop"
# Multiway and heads-up preflop all-ins in Omaha, the costliest equities, and
# Hold'em around them.
FILES = (
    STARS / "6-Card-PLO-6max-USD-0.10-0.25-202201.multiway.allin.deadcards.txt",
    STARS / "PLO-6max-USD-200-400-201505.rit.leaves.table.txt",
    STARS / "NLHE-FR-USD-0.01-0.02-201005.microgrind.txt",
    REPO / "regression-test-files/cash/iPoker/Flop/PLO-USD-0.01-0.02-201108.Sample.txt",
)
# When each import ran: Files records it per file, Hands per hand, auto notes
# per note. Set to one value before the comparison, in a transaction rolled back after.
CLEAR_TIMES = (
    "DELETE FROM Files",
    "UPDATE Hands SET importTime = '1970-01-01 00:00:00'",
    "UPDATE PlayerAutoNotes SET createdTs = '1970-01-01 00:00:00', updatedTs = '1970-01-01 00:00:00'",
)
INSERT = re.compile(r'INSERT INTO "(\w+)"')


def _import(directory: Path, threads: int) -> Path:
    directory.mkdir()
    config = golden.build_config(directory)
    Database(config).recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": threads}, config=config, sql=None)
    importer.database = Database(config)
    for path in FILES:
        importer.addImportFile(str(path), "auto")
    importer.runImport()
    importer.database.disconnect()
    return directory / "golden.sqlite3"


def _tables(database: Path) -> dict[str, list[str]]:
    """Every row of every table, as SQLite dumps it, timestamps aside."""
    connection = sqlite3.connect(database)
    try:
        for statement in CLEAR_TIMES:
            connection.execute(statement)
        tables: dict[str, list[str]] = {}
        for line in connection.iterdump():
            match = INSERT.match(line)
            if match:
                tables.setdefault(match.group(1), []).append(line)
        connection.rollback()
    finally:
        connection.close()
    return {table: sorted(rows) for table, rows in tables.items()}


@pytest.mark.skipif(equity.load_poker_eval() is None, reason="the equity engine is not installed")
def test_a_parallel_import_writes_the_same_database(tmp_path, monkeypatch) -> None:
    received: list[int] = []
    remember = equity.remember_exact
    monkeypatch.setattr(equity, "remember_exact", lambda results: (received.append(len(results)), remember(results)))
    # The import never waits for a worker; here it does, so that the workers'
    # results are used whatever the runner's speed, which is what is compared.
    before_import = import_prefetch.EquityPrefetch.before_import

    def after_the_worker(self, path):
        future = self._futures.get(path)
        if future is not None:
            future.exception()
        before_import(self, path)

    monkeypatch.setattr(import_prefetch.EquityPrefetch, "before_import", after_the_worker)

    sequential = _tables(_import(tmp_path / "sequential", threads=1))
    assert not received, "a sequential import started workers"
    parallel = _tables(_import(tmp_path / "parallel", threads=2))

    assert sum(received) > 0, "the workers supplied no equity, so the comparison proves nothing"
    assert any(row for row in sequential["HandsPlayers"]), "nothing was imported"
    assert parallel.keys() == sequential.keys()
    for table, rows in sequential.items():
        assert parallel[table] == rows, table
    assert not equity._known_exact, "the workers' results outlived the import"


def test_a_known_exact_result_is_not_computed_again() -> None:
    class NoEngine:
        def poker_eval(self, **_kwargs):
            raise AssertionError("computed again")

    pockets = [["Ah", "Kh"], ["2c", "2d"]]
    known = equity.EquityResult(
        players=(equity.PlayerEquity(Decimal("0.5"), 1, 0, 1), equity.PlayerEquity(Decimal("0.5"), 1, 0, 1)),
        samples=2,
        exhaustive=True,
    )
    equity.remember_exact({("holdem", (("Ah", "Kh"), ("2c", "2d")), ("__",) * 5, ()): known})
    try:
        assert equity.calculate_equity("holdem", pockets, [], backend=NoEngine()) is known
        with pytest.raises(AssertionError, match="computed again"):
            equity.calculate_equity("holdem", pockets, [], backend=NoEngine(), iterations=100)
    finally:
        equity.forget_exact()


@pytest.mark.skipif(equity.load_poker_eval() is None, reason="the equity engine is not installed")
def test_a_worker_records_what_the_import_computes(monkeypatch) -> None:
    # What _start_worker sets, without the logging switch it makes in a worker.
    monkeypatch.setattr(import_prefetch, "_worker_config", golden.build_config(REPO / "unused"))
    recorded = import_prefetch.exact_equities(
        import_prefetch.PrefetchJob(str(FILES[0]), "PokerStars", "PokerStars", False)
    )

    assert recorded
    for key, result in recorded.items():
        game, pockets, board, dead = key
        again = equity.calculate_equity(game, [list(pocket) for pocket in pockets], list(board), dead=list(dead))
        assert again == result


def test_a_file_a_worker_cannot_parse_gives_nothing() -> None:
    job = import_prefetch.PrefetchJob(str(FILES[0]), "NoSuchSite", "NoSuchSite", False)

    assert import_prefetch.exact_equities(job) == {}


@pytest.mark.parametrize(
    ("threads", "cores", "workers"),
    [(1, 8, 0), (None, 8, 0), (3, 8, 3), (-1, 8, 4), (-1, 3, 2), (0, 1, 0)],
)
def test_the_threads_setting_gives_the_workers(monkeypatch, threads, cores, workers) -> None:
    monkeypatch.setattr(import_prefetch.os, "cpu_count", lambda: cores)

    assert import_prefetch.worker_count(threads) == workers


@pytest.fixture
def importer(tmp_path) -> Importer:
    config = golden.build_config(tmp_path)
    Database(config).recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 2}, config=config, sql=None)
    for path in FILES:
        importer.addImportFile(str(path), "auto")
    return importer


def test_auto_import_starts_no_worker(importer) -> None:
    importer.setMode("auto")

    assert importer._start_equity_prefetch() is None


def test_a_packaged_build_starts_no_worker(importer, monkeypatch) -> None:
    """The bundles do not set up multiprocessing; a spawned worker could start the app again."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    assert importer._start_equity_prefetch() is None


def test_no_writer_connection_is_opened_for_the_threads(importer) -> None:
    assert importer.writerdbs == []


def test_a_worker_skips_a_file_the_import_has_reached(monkeypatch) -> None:
    """The import computes such a file itself; the worker must not do it a second time."""
    import multiprocessing

    reached = multiprocessing.get_context("spawn").Value("i", 3)
    monkeypatch.setattr(import_prefetch, "_worker_reached", reached)
    monkeypatch.setattr(import_prefetch, "_worker_config", object())  # parsing would fail on it
    job = import_prefetch.PrefetchJob(str(FILES[0]), "PokerStars", "PokerStars", False, order=3)

    assert import_prefetch.exact_equities(job) == {}
