"""Measure bulk import throughput, split into parse, derive and write (#443).

    python tools/benchmark_import.py                     # the default corpus, fresh SQLite
    python tools/benchmark_import.py --files 'regression-test-files/cash/Stars/Flop/*.txt'
    python tools/benchmark_import.py --repeats 3
    python tools/benchmark_import.py --workers 4         # equity workers, as `threads` sets them

    # A PostgreSQL server, with the network of a LAN or worse in front of it (#705):
    FPDB_BENCH_DSN=postgresql://user:password@host:5432 python tools/benchmark_import.py --postgres --rtt-ms 5

Every run imports into a fresh SQLite database in a temporary directory,
configured from a copy of the repository's HUD_config.xml: nothing outside that
directory is read or written. The corpus is a fixed list of regression files,
so two runs on the same machine import the same hands.

With ``--postgres`` each run creates the database fpdb_import_bench on the server
named by FPDB_BENCH_DSN and drops it afterwards; the role needs CREATEDB, and no
other database is touched. ``--rtt-ms`` puts a local TCP proxy holding every packet
for half that long in each direction in front of the server, so connecting,
transaction control and batches pay what they pay on a network. The report adds
the number of statements the import issued.

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
import asyncio
import gc
import glob
import logging
import multiprocessing
import os
import shutil
import socket
import statistics
import sys
import tempfile
from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import unquote, urlsplit

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
    statements: int | None = None

    @property
    def hands_per_second(self) -> float:
        return self.hands / self.seconds if self.seconds else 0.0


BENCH_DATABASE = "fpdb_import_bench"


@dataclass(frozen=True)
class PostgresServer:
    """Where ``--postgres`` creates its databases."""

    host: str
    port: int
    user: str
    password: str

    @classmethod
    def from_dsn(cls, dsn: str) -> PostgresServer:
        parts = urlsplit(dsn)
        if parts.scheme not in ("postgresql", "postgres") or not parts.hostname or not parts.username:
            msg = "FPDB_BENCH_DSN must look like postgresql://user:password@host:5432"
            raise SystemExit(msg)
        return cls(parts.hostname, parts.port or 5432, unquote(parts.username), unquote(parts.password or ""))

    def _admin(self) -> Any:
        import psycopg

        return psycopg.connect(
            host=self.host, port=self.port, user=self.user, password=self.password, dbname="postgres", autocommit=True
        )

    def create_database(self) -> None:
        """Create BENCH_DATABASE, replacing what a run that was killed may have left."""
        with self._admin() as admin:
            admin.execute("DROP DATABASE IF EXISTS fpdb_import_bench WITH (FORCE)")
            admin.execute("CREATE DATABASE fpdb_import_bench")

    def drop_database(self) -> None:
        with self._admin() as admin:
            admin.execute("DROP DATABASE IF EXISTS fpdb_import_bench WITH (FORCE)")


async def _delay_stream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, delay: float) -> None:
    """Copy one direction of a connection, each chunk arriving ``delay`` seconds after it was read."""
    loop = asyncio.get_running_loop()
    chunks: asyncio.Queue[tuple[float, bytes]] = asyncio.Queue()

    async def deliver() -> None:
        while True:
            due, data = await chunks.get()
            await asyncio.sleep(max(0.0, due - loop.time()))
            if not data:
                writer.close()
                return
            writer.write(data)
            await writer.drain()

    delivery = asyncio.create_task(deliver())
    try:
        while data := await reader.read(65536):
            chunks.put_nowait((loop.time() + delay, data))
    finally:
        chunks.put_nowait((loop.time() + delay, b""))
        await delivery


def _run_delay_proxy(listener: socket.socket, host: str, port: int, rtt_ms: float) -> None:
    """Forward connections from ``listener`` to host:port, adding ``rtt_ms`` to every round trip."""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        upstream_reader, upstream_writer = await asyncio.open_connection(host, port)
        for stream in (writer, upstream_writer):
            stream.get_extra_info("socket").setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        await asyncio.gather(
            _delay_stream(reader, upstream_writer, rtt_ms / 2000.0),
            _delay_stream(upstream_reader, writer, rtt_ms / 2000.0),
            return_exceptions=True,
        )

    async def serve() -> None:
        async with await asyncio.start_server(handle, sock=listener) as server:
            await server.serve_forever()

    asyncio.run(serve())


@contextmanager
def _delayed(server: PostgresServer, rtt_ms: float) -> Iterator[PostgresServer]:
    """``server`` as seen through a proxy adding ``rtt_ms``, in a process of its own.

    Its own process because the import holds the GIL for long stretches, which
    would add to the delay in a thread.
    """
    if rtt_ms <= 0:
        yield server
        return
    with socket.create_server(("127.0.0.1", 0)) as listener:
        proxy = multiprocessing.get_context("spawn").Process(
            target=_run_delay_proxy, args=(listener, server.host, server.port, rtt_ms), daemon=True
        )
        proxy.start()
        try:
            yield replace(server, host="127.0.0.1", port=listener.getsockname()[1])
        finally:
            proxy.terminate()
            proxy.join()


@contextmanager
def _default_connection(server: PostgresServer) -> Iterator[None]:
    """Make ``server`` libpq's default inside the block.

    For a loopback host Database first connects with no host or port, which
    would reach a local server's socket directly and skip the delay proxy.
    """
    settings = {"PGHOST": server.host, "PGPORT": str(server.port), "PGUSER": server.user, "PGPASSWORD": server.password}
    saved = {name: os.environ.get(name) for name in settings}
    os.environ.update(settings)
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


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


def import_once(
    files: Sequence[Path],
    workdir: Path,
    workers: int = 1,
    server: PostgresServer | None = None,
) -> ImportTiming:
    """Import ``files`` into a fresh database: SQLite under ``workdir``, or BENCH_DATABASE on ``server``."""
    from fpdb_3_legacy import db_profile
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.Database import Database
    from fpdb_3_legacy.Importer import Importer

    workdir.mkdir(parents=True, exist_ok=True)
    config_file = workdir / "HUD_config.xml"
    shutil.copyfile(REPO / "HUD_config.xml", config_file)
    config = Config(file=str(config_file))
    params = config.get_db_parameters()
    if server is None:
        params.update(
            {
                "db-server": "sqlite",
                "db-backend": 4,
                "db-databaseName": str(workdir / "benchmark.sqlite3"),
                "db-path": "",
            }
        )
    else:
        params.update(
            {
                "db-server": "postgresql",
                "db-backend": Database.PGSQL,
                "db-databaseName": BENCH_DATABASE,
                "db-host": server.host,
                "db-port": server.port,
                "db-user": server.user,
                "db-password": server.password,
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
    profile = db_profile.get_profile()
    profile.reset()
    started = perf_counter()
    with _timed(phases):
        stored, *_rest = importer.runImport()
    seconds = perf_counter() - started
    statements = profile.total.calls if db_profile.is_enabled() else None
    # Every connection closed, or Windows cannot remove the temporary directory.
    importer.close()
    phases["write"] = seconds - phases["parse"] - phases["derive"] - phases["workers"]
    return ImportTiming(hands=stored, seconds=seconds, phases=dict(phases), statements=statements)


def benchmark(
    files: Sequence[Path],
    repeats: int,
    workers: int = 1,
    server: PostgresServer | None = None,
    rtt_ms: float = 0.0,
) -> list[ImportTiming]:
    timings = []
    # On Windows the import can keep a handle on the database file after every
    # connection the benchmark sees is closed; a directory left behind in the
    # temporary folder must not fail the measurement.
    with tempfile.TemporaryDirectory(prefix="fpdb-import-bench-", ignore_cleanup_errors=True) as root:
        for run in range(repeats):
            workdir = Path(root) / f"run{run}"
            if server is None:
                timings.append(import_once(files, workdir, workers))
                continue
            server.create_database()
            try:
                with _delayed(server, rtt_ms) as reachable, _default_connection(reachable):
                    timings.append(import_once(files, workdir, workers, reachable))
            finally:
                server.drop_database()
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
    if best.statements is not None:
        lines.append(f"  {best.statements} statements")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--files", action="append", help="glob of files to import, relative to the repository")
    parser.add_argument("--repeats", type=int, default=1, help="imports to run; the best is reported")
    parser.add_argument("--workers", type=int, default=1, help="equity worker processes (1: none, -1: automatic)")
    parser.add_argument("--postgres", action="store_true", help="import into the PostgreSQL server of FPDB_BENCH_DSN")
    parser.add_argument("--rtt-ms", type=float, default=0.0, help="with --postgres: add this much to every round trip")
    args = parser.parse_args(argv)

    server = None
    if args.postgres:
        server = PostgresServer.from_dsn(os.environ.get("FPDB_BENCH_DSN", ""))
        # Read when the connection opens: counts the statements for the report.
        os.environ["FPDB_DB_PROFILE"] = "1"
    files = corpus_files(args.files or DEFAULT_CORPUS)
    # The import logs every hand; that would be timed too.
    logging.disable(logging.CRITICAL)
    try:
        timings = benchmark(files, max(1, args.repeats), args.workers, server, args.rtt_ms)
    finally:
        logging.disable(logging.NOTSET)
    print(format_timings(files, timings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
