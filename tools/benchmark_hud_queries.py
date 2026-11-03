"""Per-query performance bench of the HUD read path on all three backends (#680).

    python tools/benchmark_hud_queries.py --dsn sqlite --corpus 'regression-test-files/cash/Stars/**/*.txt'
    FPDB_BENCH_DSN="postgresql://fpdb:fpdb@127.0.0.1:5432/fpdb_bench" python tools/benchmark_hud_queries.py --corpus ...
    python tools/benchmark_hud_queries.py --dsn mysql://fpdb:fpdb@127.0.0.1:3306/fpdb_bench ...

The same corpus is imported into a fresh database on every backend, so the
data is constant across runs and the numbers compare backends, not datasets.
Each HUD query case is then executed ``--repeats`` times against real hand ids,
with per-statement timings (db_profile) and the server-side query plan
(EXPLAIN QUERY PLAN / EXPLAIN ANALYZE) captured for the heavy queries.

Query cases:
  aggregated_per_hand   get_stats_from_hand (the big HudCache aggregate, one hand)
  aggregated_batch      get_stats_from_hands (6 hands, one batched aggregate)
  session_per_hand      get_stats_from_hand with stat_range S (session path)
  table_info_many / site_hand_no_many / positions_many / seat_players_many
  cards_many / common_cards_many / min_stack_many   the batched reads from #680
  hand_construction     Hand.hand_factory (the per-hand object build)

Results (percentiles + round trips + plans) go to --out as JSON; a markdown
table is printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from time import perf_counter

os.environ.setdefault("FPDB_LATENCY_PROFILE", "1")
os.environ.setdefault("FPDB_DB_PROFILE", "1")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tools.benchmark_hud_live import (  # noqa: E402
    _corpus_files,
    _hud_params,
    _make_config,
    _table_hands,
)

DEFAULT_CORPUS = (
    "regression-test-files/cash/Stars/**/*.txt",
    "regression-test-files/cash/FTP/**/*.txt",
    "regression-test-files/cash/Winning/**/*.txt",
    "regression-test-files/cash/PartyPoker/**/*.txt",
)


def _percentiles(samples: list[float]) -> dict:
    if not samples:
        return {"count": 0, "mean": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    ordered = sorted(samples)

    def pct(q: float) -> float:
        rank = q * (len(ordered) - 1)
        low = int(rank)
        high = min(low + 1, len(ordered) - 1)
        return ordered[low] * (1 - (rank - low)) + ordered[high] * (rank - low)

    return {
        "count": len(ordered),
        "mean": sum(ordered) / len(ordered),
        "p50": pct(0.50),
        "p95": pct(0.95),
        "p99": pct(0.99),
        "max": ordered[-1],
    }


def _run_case(fn, repeats: int) -> dict:
    from fpdb_3_legacy import db_profile

    profile = db_profile.get_profile()
    walls: list[float] = []
    for _ in range(repeats):
        profile.reset()
        started = perf_counter()
        fn()
        walls.append(perf_counter() - started)
        # keep the last iteration's per-statement breakdown
        statements = {
            name: {"calls": s.calls, "seconds": s.seconds} for name, s in profile.by_statement.items() if s.calls
        }
    return {"wall": _percentiles(walls), "statements": statements}


def _explain(db, sql: str, params: tuple) -> str:
    """Server-side plan for one statement, per backend dialect."""
    backend = db.backend
    from fpdb_3_legacy.Database import Database

    if backend == Database.PGSQL:
        prefix = "EXPLAIN (ANALYZE, BUFFERS, TIMING OFF) "
    elif backend == Database.MYSQL_INNODB:
        prefix = "EXPLAIN ANALYZE "
    else:
        prefix = "EXPLAIN QUERY PLAN "
    try:
        c = db.connection.cursor()
        c.execute(prefix + sql, params)
        rows = c.fetchall()
        c.close()
        return "\n".join(str(row[0]) for row in rows)
    except Exception as exc:
        return f"<explain failed: {exc}>"


def _aggregated_sql_and_params(db, hand_id, hud_params, hero_id: int = -1, num_seats: int = 6):
    from fpdb_3_legacy.table_info import TableInfo

    info = TableInfo.coerce(db.get_table_info(hand_id))
    handinfo = db.get_gameinfo_from_hid(hand_id)
    seats_min, seats_max = db._seat_bounds(
        hud_params["seats_style"], hud_params["seats_cust_nums_low"], hud_params["seats_cust_nums_high"], num_seats
    )
    h_seats_min, h_seats_max = db._seat_bounds(
        hud_params["h_seats_style"],
        hud_params["h_seats_cust_nums_low"],
        hud_params["h_seats_cust_nums_high"],
        num_seats,
    )
    db.init_hud_stat_vars(hud_params["hud_days"], hud_params["h_hud_days"])
    stylekey = db._style_key(hud_params["stat_range"], hero=False)
    h_stylekey = db._style_key(hud_params["h_stat_range"], hero=True)
    sql_text = db._inject_hud_chipev_columns(db.sql.query["get_stats_from_hand_aggregated"])
    subs = (
        hand_id,
        hero_id,
        stylekey,
        hud_params["agg_bb_mult"],
        hud_params["agg_bb_mult"],
        handinfo["gametypeId"],
        seats_min,
        seats_max,
        hero_id,
        h_stylekey,
        hud_params["h_agg_bb_mult"],
        hud_params["h_agg_bb_mult"],
        handinfo["gametypeId"],
        h_seats_min,
        h_seats_max,
    )
    return sql_text, subs, info, handinfo


def _collect_cases(config, db, repeats: int) -> dict:
    table_hands = _table_hands(db)
    all_hands = [h for hands in table_hands.values() for h in hands]
    if len(all_hands) < 8:
        raise SystemExit("corpus too small: need at least 8 hands")
    # one hand per distinct table when possible, else the latest hands
    sample = [hands[-1] for hands in list(table_hands.values())[:6]] or all_hands[:6]
    primary = all_hands[-1]
    params_a = _hud_params("A")
    params_s = _hud_params("S")
    return _run_all_cases(db, config, sample, primary, params_a, params_s, all_hands, repeats)


def _run_all_cases(db, config, sample, primary, params_a, params_s, all_hands, repeats: int) -> dict:
    from fpdb_3_legacy import Hand

    cases: dict[str, dict] = {}

    cases["aggregated_per_hand"] = _run_case(
        lambda: db.get_stats_from_hand(primary, "ring", params_a, -1, 6, poker_game="holdem"), repeats
    )
    cases["aggregated_batch_6"] = _run_case(
        lambda: db.get_stats_from_hands(sample, "ring", params_a, -1, 6, poker_game="holdem"), repeats
    )
    cases["session_per_hand"] = _run_case(
        lambda: db.get_stats_from_hand(primary, "ring", params_s, -1, 6, poker_game="holdem"), repeats
    )
    cases["table_info_many_8"] = _run_case(lambda: db.get_table_info_many(all_hands[-8:]), repeats)
    cases["site_hand_no_many_8"] = _run_case(lambda: db.get_site_hand_no_many(all_hands[-8:]), repeats)
    cases["positions_many_8"] = _run_case(lambda: db.get_hand_positions_many(all_hands[-8:]), repeats)
    cases["seat_players_many_8"] = _run_case(lambda: db.get_seat_players_many(all_hands[-8:]), repeats)
    cases["cards_many_8"] = _run_case(lambda: db.get_cards_many(all_hands[-8:]), repeats)
    cases["common_cards_many_8"] = _run_case(lambda: db.get_common_cards_many(all_hands[-8:]), repeats)
    cases["min_stack_many_8"] = _run_case(lambda: db.get_table_min_stack_bb_many(all_hands[-8:]), repeats)
    cases["hand_construction"] = _run_case(lambda: Hand.hand_factory(primary, config, db), repeats)
    return cases


def _collect_plans(db, primary, sample, params_a) -> dict:
    plans: dict[str, str] = {}
    sql_text, subs, _info, handinfo = _aggregated_sql_and_params(db, primary, params_a)
    plans["aggregated_per_hand"] = _explain(db, sql_text, subs)
    batched = db._batched_aggregated_sql(sql_text, len(sample))
    if batched is not None:
        gametype_id = handinfo["gametypeId"]
        seats_min, seats_max = db._seat_bounds("A", 1, 10, 6)
        bsubs = (
            *sample,
            -1,
            db._style_key("A", hero=False),
            1000,
            1000,
            gametype_id,
            seats_min,
            seats_max,
            -1,
            db._style_key("A", hero=True),
            1000,
            1000,
            gametype_id,
            seats_min,
            seats_max,
        )
        plans["aggregated_batch_6"] = _explain(db, batched, bsubs)
    session_q = db.sql.query["get_stats_from_hand_session"]
    if getattr(db, "db_server", "") == "mysql":
        session_q = session_q.replace("<signed>", "signed ")
    else:
        session_q = session_q.replace("<signed>", "")
    db.init_hud_stat_vars(30, 90)
    ssubs = (db.hand_1day_ago, primary, -1, 0, 10, -1, 0, 10)
    plans["session_per_hand"] = _explain(db, session_q, ssubs)
    return plans


def bench_queries(config, db, repeats: int, out: str | None) -> dict:
    table_hands = _table_hands(db)
    all_hands = [h for hands in table_hands.values() for h in hands]
    sample = [hands[-1] for hands in list(table_hands.values())[:6]] or all_hands[:6]
    primary = all_hands[-1]
    params_a = _hud_params("A")
    cases = _collect_cases(config, db, repeats)
    plans = _collect_plans(db, primary, sample, params_a)

    c = db.connection.cursor()
    c.execute("SELECT COUNT(*) FROM Hands")
    hands_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM HudCache")
    hudcache_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM Players")
    players_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM HandsPlayers")
    hp_count = c.fetchone()[0]
    c.close()

    report = {
        "backend": {0: "sqlite?", 2: "mysql", 3: "postgresql", 4: "sqlite"}.get(db.backend, str(db.backend)),
        "db_server": getattr(db, "db_server", ""),
        "dataset": {
            "hands": hands_count,
            "hudcache_rows": hudcache_count,
            "players": players_count,
            "hands_players_rows": hp_count,
            "tables": len(table_hands),
        },
        "repeats": repeats,
        "cases": cases,
        "plans": plans,
    }
    if out:
        with open(out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
    return report


def format_markdown(report: dict) -> str:
    lines = [
        f"backend: {report['backend']} ({report['db_server']}), dataset: {report['dataset']}, "
        f"repeats: {report['repeats']}",
        "",
        "| query case | n | mean ms | p50 | p95 | p99 | max | statements/iter |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, case in report["cases"].items():
        w = case["wall"]
        total_calls = sum(s["calls"] for s in case["statements"].values())
        lines.append(
            f"| {name} | {w['count']} | {w['mean'] * 1000:.2f} | {w['p50'] * 1000:.2f} "
            f"| {w['p95'] * 1000:.2f} | {w['p99'] * 1000:.2f} | {w['max'] * 1000:.2f} | {total_calls} |"
        )
    return "\n".join(lines)


def _populate(config, files) -> int:
    """Create a fresh schema in config's database and import ``files`` into it."""
    from fpdb_3_legacy.Database import Database
    from fpdb_3_legacy.Importer import Importer

    schema = Database(config)
    schema.recreate_tables()
    schema.close_connection()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.setCallHud(True)
    for path in files:
        importer.addImportFile(str(path), "auto")
    stored, _d, _p, _s, _e, _t = importer.runImport()
    importer.close()
    return stored


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--dsn", default=os.environ.get("FPDB_BENCH_DSN", ""), help="sqlite (default) | postgresql://... | mysql://..."
    )
    parser.add_argument("--corpus", nargs="+", default=list(DEFAULT_CORPUS), help="glob(s) of hand history files")
    parser.add_argument("--repeats", type=int, default=15)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    files: list[Path] = []
    for pattern in args.corpus:
        files.extend(_corpus_files(pattern, 10_000))
    files = list(dict.fromkeys(files))
    print(f"corpus: {len(files)} files", file=sys.stderr)

    with tempfile.TemporaryDirectory(prefix="fpdb-query-bench-", ignore_cleanup_errors=True) as root:
        workdir = Path(root)
        if args.dsn:
            os.environ["FPDB_BENCH_DSN"] = args.dsn
        config = _make_config(workdir, workdir / "bench.sqlite3")
        db_file = workdir / "bench.sqlite3"
        if not args.dsn:
            params = config.get_db_parameters()
            params.update({"db-server": "sqlite", "db-backend": 4, "db-databaseName": str(db_file), "db-path": ""})
            config.get_db_parameters = lambda: params
        stored = _populate(config, files)
        print(f"imported {stored} hands", file=sys.stderr)
        if not stored:
            raise SystemExit("corpus import stored 0 hands")

        from fpdb_3_legacy.Database import Database

        db = Database(config)
        report = bench_queries(config, db, args.repeats, args.out)
        db.close_connection()

    print(format_markdown(report))
    if args.out:
        print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
