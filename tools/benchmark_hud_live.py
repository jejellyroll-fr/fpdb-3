"""Benchmark the live HUD read path at several table counts (#680).

    python tools/benchmark_hud_live.py                          # 1,2,4,6,8 tables, aggregate stats, fresh SQLite
    python tools/benchmark_hud_live.py --tables 1,2 --repeats 5 --stat-range S
    python tools/benchmark_hud_live.py --import-concurrent      # auto-import writing while the HUD reads
    python tools/benchmark_hud_live.py --out report.json

The benchmark imports a fixed corpus of regression files into a fresh SQLite
database (with the HUD cache enabled, so HudCache is populated the way a real
database is), then replays HUD batches the way HudReadWorker does: each round
submits one HudBatchReadRequest with the newest hand of every open table plus
the read context of every open table, and HudReadService.read_batch does the
same work it does in production. No Qt is involved, so the numbers are the
database-and-Python cost of one HUD refresh round, which is what scales with
table count.

For every (table count, stat range, import-concurrent) configuration the run
reports count / mean / p50 / p95 / p99 / max for each latency metric collected
by fpdb_3_legacy.latency_profile (batch total, per-phase, query execute vs
fetch vs Python aggregation, session rows, HudCache writes, import transaction
and commit), plus the round-trip count from db_profile. Percentiles, not
averages, are the point: the reported freezes are multi-second pauses.

Set FPDB_BENCH_DSN="postgresql://user:pass@host/dbname" (or mysql://...) to run
the same workload against a server database instead of the local SQLite file.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path
from time import perf_counter

# Before any fpdb import: the modules under test read these at import time.
os.environ.setdefault("FPDB_LATENCY_PROFILE", "1")
os.environ.setdefault("FPDB_DB_PROFILE", "1")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

DEFAULT_CORPUS = "regression-test-files/cash/Stars/Flop/*.txt"
DEFAULT_TABLES = (1, 2, 4, 6, 8)


def _corpus_files(pattern: str, limit: int) -> list[Path]:
    import glob

    files = sorted(glob.glob(str(REPO / pattern)))
    if not files:
        raise SystemExit(f"no corpus files matched {pattern}")
    return [Path(f) for f in files[:limit]]


def _make_config(workdir: Path, db_file: Path):
    from fpdb_3_legacy.Configuration import Config

    config_file = workdir / "HUD_config.xml"
    shutil.copyfile(REPO / "HUD_config.xml", config_file)
    config = Config(file=str(config_file))
    params = config.get_db_parameters()
    dsn = os.environ.get("FPDB_BENCH_DSN", "")
    if dsn.startswith("postgresql://") or dsn.startswith("postgres://"):
        user_pass, rest = dsn.split("://", 1)[1].split("@", 1)
        user, password = user_pass.split(":", 1)
        host_db = rest.split("/", 1)
        host_port = host_db[0].split(":", 1)
        params.update(
            {
                "db-server": "postgresql",
                "db-backend": 3,
                "db-host": host_port[0],
                "db-port": int(host_port[1]) if len(host_port) > 1 else 5432,
                "db-name": host_db[1] if len(host_db) > 1 else "fpdb",
                "db-databaseName": host_db[1] if len(host_db) > 1 else "fpdb",
                "db-path": "",
                "db-user": user,
                "db-password": password,
            }
        )
    elif dsn.startswith("mysql://"):
        user_pass, rest = dsn.split("://", 1)[1].split("@", 1)
        user, password = user_pass.split(":", 1)
        host_db = rest.split("/", 1)
        host_port = host_db[0].split(":", 1)
        params.update(
            {
                "db-server": "mysql",
                "db-backend": 2,
                "db-host": host_port[0],
                "db-port": int(host_port[1]) if len(host_port) > 1 else 3306,
                "db-name": host_db[1] if len(host_db) > 1 else "fpdb",
                "db-databaseName": host_db[1] if len(host_db) > 1 else "fpdb",
                "db-path": "",
                "db-user": user,
                "db-password": password,
            }
        )
    else:
        params.update(
            {
                "db-server": "sqlite",
                "db-backend": 4,
                "db-databaseName": str(db_file),
                "db-path": "",
            }
        )
    config.get_db_parameters = lambda: params
    return config


def build_database(workdir: Path, files: list[Path]):
    """Import ``files`` into a fresh database and return (config, Database)."""
    from fpdb_3_legacy.Database import Database
    from fpdb_3_legacy.Importer import Importer

    config = _make_config(workdir, workdir / "benchmark.sqlite3")
    schema = Database(config)
    schema.recreate_tables()
    schema.close_connection()

    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.setCallHud(True)  # populate HudCache the way a live session does
    for path in files:
        importer.addImportFile(str(path), "auto")
    stored, _dups, _partial, _skipped, _errs, _ttime = importer.runImport()
    importer.close()
    if not stored:
        raise SystemExit("corpus import stored 0 hands; cannot benchmark the HUD read path")

    db = Database(config)
    return config, db


def _table_hands(db) -> dict[str, list[str]]:
    """Every cash table in the database with its hand ids, oldest first."""
    placeholder = db.sql.query["placeholder"]
    c = db.connection.cursor()
    c.execute("SELECT DISTINCT tableName FROM Hands WHERE tableName IS NOT NULL ORDER BY tableName")
    tables = [row[0] for row in c.fetchall()]
    result: dict[str, list[str]] = {}
    for table in tables:
        c.execute(f"SELECT id FROM Hands WHERE tableName = {placeholder} ORDER BY id", (table,))
        result[table] = [str(row[0]) for row in c.fetchall()]
    c.close()
    return {table: hands for table, hands in result.items() if hands}


def _hud_params(stat_range: str) -> dict:
    from fpdb_3_legacy.database_hud_stats import _DEFAULT_HUD_PARAMS

    return dict(_DEFAULT_HUD_PARAMS, stat_range=stat_range, h_stat_range=stat_range)


def _contexts(db, table_hands: dict[str, list[str]], tables: list[str], last_index: int):
    from fpdb_3_legacy.hud_read_service import HudTableReadContext, hud_poker_game, hud_temp_key
    from fpdb_3_legacy.table_info import TableInfo

    contexts = []
    for table in tables:
        hand_id = table_hands[table][max(0, min(last_index, len(table_hands[table]) - 1)) % len(table_hands[table])]
        info = TableInfo.coerce(db.get_table_info(hand_id))
        contexts.append(
            HudTableReadContext(
                temp_key=hud_temp_key(db.get_table_info(hand_id)),
                last_hand_id=hand_id,
                hud_params=_hud_params(CURRENT_STAT_RANGE[0]),
                poker_game=hud_poker_game(info.poker_game),
                game_type=info.game_type,
                site_id=info.site_id,
                num_seats=info.num_seats,
            )
        )
    return tuple(contexts)


CURRENT_STAT_RANGE = ["A"]


def _import_loop(stop: threading.Event, config, files: list[Path], errors: list) -> None:
    """Keep auto-importing files on a second connection while the HUD reads."""
    from fpdb_3_legacy.Importer import Importer

    try:
        importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
        importer.setCallHud(False)
        index = 0
        while not stop.is_set():
            importer.clearFileList()
            importer.addImportFile(str(files[index % len(files)]), "auto")
            importer.runImport()
            index += 1
        importer.close()
    except Exception as exc:  # surfaced by the caller
        errors.append(exc)


def bench_config(
    config, db, table_hands, n_tables: int, stat_range: str, repeats: int, import_files: list[Path] | None
):
    """Run ``repeats`` HUD batch rounds over ``n_tables`` tables and collect metrics."""
    from fpdb_3_legacy import db_profile, latency_profile
    from fpdb_3_legacy.hud_read_service import HudBatchReadRequest, HudReadService

    CURRENT_STAT_RANGE[0] = stat_range
    tables = sorted(table_hands)[:n_tables]
    if len(tables) < n_tables:
        raise SystemExit(f"corpus has only {len(tables)} tables; cannot simulate {n_tables}")
    service = HudReadService(config, db)
    params = _hud_params(stat_range)

    profile = latency_profile.get_profile()
    profile.reset()
    db_profile.get_profile().reset()

    stop = threading.Event()
    errors: list = []
    writer = None
    if import_files:
        writer = threading.Thread(target=_import_loop, args=(stop, config, import_files, errors), daemon=True)
        writer.start()

    walls: list[float] = []
    # Tables in the corpus may hold few hands; cycle through them so any repeat
    # count can be measured on a small corpus.
    rounds = repeats
    try:
        for i in range(rounds):
            hand_ids = tuple(table_hands[t][(i + 1) % len(table_hands[t])] for t in tables)
            contexts = _contexts(db, table_hands, tables, i)
            request = HudBatchReadRequest(
                sequence=i + 1,
                hand_ids=hand_ids,
                hud_params=params,
                tables=contexts,
            )
            started = perf_counter()
            service.read_batch(request)
            walls.append(perf_counter() - started)
    finally:
        stop.set()
        if writer is not None:
            writer.join(timeout=30)
    if errors:
        raise errors[0]

    for index, wall in enumerate(walls):
        profile.record("bench_batch_wall", wall)
    return {
        "tables": n_tables,
        "stat_range": stat_range,
        "import_concurrent": import_files is not None,
        "rounds": rounds,
        "latency": profile.snapshot()["metrics"],
        "round_trips": {
            "total_calls": db_profile.get_profile().total.calls,
            "total_seconds": db_profile.get_profile().total.seconds,
            "by_scope": {
                name: {"entries": s.entries, "queries": s.queries, "seconds": s.seconds}
                for name, s in db_profile.get_profile().by_scope.items()
            },
        },
    }


def format_markdown(results: list[dict]) -> str:
    lines = [
        "| tables | stat range | import concurrent | rounds | batch wall p50 (ms) | batch wall p95 (ms) | batch wall max (ms) | query execute p99 (ms) | round trips |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for result in results:
        latency = result["latency"]
        wall = latency.get("bench_batch_wall", {})
        execute = latency.get("hud_query_execute", {})

        def ms(stats, key):
            return f"{stats.get(key, 0.0) * 1000:.1f}"

        lines.append(
            f"| {result['tables']} | {result['stat_range']} | {result['import_concurrent']} | {result['rounds']} "
            f"| {ms(wall, 'p50')} | {ms(wall, 'p95')} | {ms(wall, 'max')} | {ms(execute, 'p99')} "
            f"| {result['round_trips']['total_calls']} |"
        )
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--corpus", default=DEFAULT_CORPUS, help="glob of hand history files used to populate the database"
    )
    parser.add_argument("--corpus-limit", type=int, default=40, help="max corpus files to import")
    parser.add_argument("--tables", type=str, default=",".join(str(t) for t in DEFAULT_TABLES))
    parser.add_argument(
        "--stat-range", default="A,S", help="comma-separated stat ranges to benchmark (A=all hands, S=session)"
    )
    parser.add_argument("--repeats", type=int, default=10, help="HUD batch rounds per configuration")
    parser.add_argument(
        "--import-concurrent", action="store_true", help="run auto-import on a second connection during the reads"
    )
    parser.add_argument("--out", default=None, help="write the full JSON report here")
    args = parser.parse_args(argv)

    files = _corpus_files(args.corpus, args.corpus_limit)
    table_counts = [int(t) for t in args.stat_range and args.tables.split(",")]
    stat_ranges = [s.strip() for s in args.stat_range.split(",")]

    with tempfile.TemporaryDirectory(prefix="fpdb-hud-live-bench-", ignore_cleanup_errors=True) as root:
        workdir = Path(root)
        config, db = build_database(workdir, files)
        table_hands = _table_hands(db)
        print(
            f"populated {sum(len(v) for v in table_hands.values())} hands over {len(table_hands)} tables",
            file=sys.stderr,
        )

        results = []
        for n_tables in table_counts:
            for stat_range in stat_ranges:
                for concurrent in [False, True] if args.import_concurrent else [False]:
                    result = bench_config(
                        config,
                        db,
                        table_hands,
                        n_tables,
                        stat_range,
                        args.repeats,
                        files if concurrent else None,
                    )
                    results.append(result)
                    wall = result["latency"].get("bench_batch_wall", {})
                    print(
                        f"tables={n_tables} range={stat_range} import={'on' if concurrent else 'off'}: "
                        f"batch wall p50={wall.get('p50', 0) * 1000:.1f}ms p95={wall.get('p95', 0) * 1000:.1f}ms "
                        f"max={wall.get('max', 0) * 1000:.1f}ms round_trips={result['round_trips']['total_calls']}",
                        file=sys.stderr,
                    )
        db.close_connection()

    report = {"results": results, "markdown": format_markdown(results)}
    print(format_markdown(results))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
