"""Bench EVERY query in the SQL catalogue on all three backends (#680).

    python tools/benchmark_all_queries.py --dsn sqlite --corpus 'regression-test-files/cash/Stars/Flop/*.txt'
    python tools/benchmark_all_queries.py --dsn postgresql://fpdb:fpdb@127.0.0.1:5432/fpdb_bench ...
    python tools/benchmark_all_queries.py --dsn mysql://fpdb:fpdb@127.0.0.1:3306/fpdb_bench ...

The same corpus is imported into a fresh database on each backend (constant
data), then every entry of ``Sql(db_server=...).query`` is executed --repeats
times with parameters resolved from real rows of that database (hand id,
player id, gametype id, table name, ... chosen by the column name preceding
each placeholder). DML runs inside a transaction that is always rolled back,
so the bench never changes the data. DDL/PRAGMA/SET and queries still carrying
an unresolved ``<template>`` (assembled at run time by their callers) are
reported as skipped, not executed.

For each executed query the report keeps status (ok/empty/error), rows,
p50/p95/max ms, and the EXPLAIN plan. The markdown output ranks the slowest
queries and lists plans containing sequential scans over the big tables.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter

os.environ.setdefault("FPDB_LATENCY_PROFILE", "1")
os.environ.setdefault("FPDB_DB_PROFILE", "1")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tools.benchmark_hud_live import _corpus_files, _make_config  # noqa: E402
from tools.benchmark_hud_queries import _percentiles  # noqa: E402

DEFAULT_CORPUS = (
    "regression-test-files/cash/Stars/**/*.txt",
    "regression-test-files/cash/FTP/**/*.txt",
    "regression-test-files/cash/Winning/**/*.txt",
    "regression-test-files/cash/PartyPoker/**/*.txt",
)

# Templates that can be given a safe constant; anything else left in the SQL
# marks the query as assembled-by-caller and it is skipped.
TEMPLATE_VALUES = {
    "<playerid_list>": "(1, 2)",
    "<player_ids>": "1, 2",
    "<tuples>": "(1, 1, 1, 1, 1)",
    "<heroSeat>": "",
    "<heroseat>": "",
    "<signed>": "",
    "<chipev_columns>": "",
    "<stat_insert_columns>": "",
    "<stat_select_columns>": "",
    "<group>": "",
    "<groupbyseats>": "",
    "<havingclause>": "",
    "<maxopponents>": "9",
    "<minhands>": "1",
    "<position>": "'B'",
    "<limit_test>": "",
    "<nametest>": "",
    "<playerName>": "",
    "<player_test>": "",
    "<site_test>": "",
    "<sitetest>": "",
    "<game_test>": "",
    "<tourney_cat>": "",
    "<tourney_lim>": "",
    "<tourney_buyin>": "",
    "<datestest>": "",
    "<datetest>": "",
    "<startdate_test>": "",
    "<enddate_test>": "",
    "<flagtest>": "",
    "<cardstest>": "",
    "<currency_test>": "",
    "<gtbigBlind_test>": "",
    "<seats_test>": "",
    "<position_test>": "",
    "<hcgametypeId>": "",
    "<hgametypeId>": "",
    "<orderbyhgametypeId>": "",
    "<orderbyseats>": "",
    "<hero_join>": "",
    "<sessions_join_clause>": "",
    "<tourney_join_clause>": "",
    "<TOURSELECT>": "",
    "<select>": "",
    "<where_clause>": "",
}

SKIP_PREFIXES = (
    "create",
    "drop",
    "alter",
    "pragma",
    "set ",
    "vacuum",
    "analyze",
    "explain",
    "lock tables",
    "unlock tables",
)
BIG_TABLES = ("hudcache", "handsplayers", "hands", "handsactions", "handspoker", "players")


def _context_values(db) -> dict:
    """Real values from the populated database, keyed by the column names the
    heuristic looks for."""
    c = db.connection.cursor()

    def one(sql, default):
        try:
            c.execute(sql)
            row = c.fetchone()
            return row[0] if row and row[0] is not None else default
        except Exception:
            return default

    values = {
        "hand": one("SELECT id FROM Hands ORDER BY id DESC LIMIT 1", 1),
        "player": one("SELECT playerId FROM HandsPlayers ORDER BY handId DESC LIMIT 1", 1),
        "player_name": one("SELECT name FROM Players ORDER BY id LIMIT 1", "Hero"),
        "gametype": one("SELECT gametypeId FROM Hands ORDER BY id DESC LIMIT 1", 1),
        "site": one("SELECT id FROM Sites ORDER BY id LIMIT 1", 1),
        "site_name": one("SELECT name FROM Sites ORDER BY id LIMIT 1", "PokerStars"),
        "table": one("SELECT tableName FROM Hands ORDER BY id DESC LIMIT 1", "Table 1"),
        "site_hand_no": one("SELECT siteHandNo FROM Hands ORDER BY id DESC LIMIT 1", 1),
        "tourney": one("SELECT siteTourneyNo FROM Tourneys ORDER BY id DESC LIMIT 1", 1),
        "file": one("SELECT id FROM Files ORDER BY id DESC LIMIT 1", 1),
        "start": datetime.now() - timedelta(hours=1),
        "end": datetime.now(),
        "stylekey": "d20260101",
    }
    c.close()
    return values


_COLUMN_HINTS = (
    ("handid", "hand"),
    ("h.id", "hand"),
    ("hp.handid", "hand"),
    ("playerid", "player"),
    ("p.id", "player"),
    ("hp.playerid", "player"),
    ("name", "player_name"),
    ("sitename", "site_name"),
    ("tablename", "table"),
    ("sitehandno", "site_hand_no"),
    ("gametypeid", "gametype"),
    ("siteid", "site"),
    ("s.id", "site"),
    ("tourneyno", "tourney"),
    ("sitetourneyno", "tourney"),
    ("tourneyid", "tourney"),
    ("fileid", "file"),
    ("stylekey", "stylekey"),
    ("starttime", "start"),
    ("startdate", "start"),
    ("enddate", "end"),
    ("date", "start"),
    ("seats", 6),
    ("seatno", 1),
    ("position", "B"),
    ("limit", 100),
)


def _insert_columns(sql: str) -> list[str] | None:
    """Column names of an INSERT ... (cols) VALUES (...), in order, else None."""
    match = re.search(r"insert\s+into\s+\w+\s*\(([^)]*)\)\s*values", sql, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return [col.strip().strip("`").strip(chr(34)).lower() for col in match.group(1).split(",")]


def _value_for_column(column: str, ctx: dict):
    for hint, candidate in _COLUMN_HINTS:
        if hint in column:
            return ctx[candidate] if isinstance(candidate, str) and candidate in ctx else candidate
    return 1


def _params_for(sql: str, ph: str, ctx: dict) -> list:
    """One value per placeholder: for INSERT, by column position; else guessed
    from the text preceding the placeholder."""
    columns = _insert_columns(sql)
    params = []
    for index, match in enumerate(re.finditer(re.escape(ph), sql)):
        if columns and index < len(columns):
            params.append(_value_for_column(columns[index], ctx))
            continue
        before = sql[max(0, match.start() - 40) : match.start()].lower()
        params.append(_value_for_column(before, ctx))
    return params


def _prepare(sql: str, db_server: str, ctx: dict) -> tuple[str, list] | None:
    """Substitute templates; None when the query is assembled by its caller."""
    out = sql
    for tpl, value in TEMPLATE_VALUES.items():
        out = out.replace(tpl, value)
    if db_server == "mysql":
        out = out.replace("<signed>", "signed ")
    if re.search(r"<[a-zA-Z_]+>", out):
        return None
    ph = "%s" if db_server in ("mysql", "postgresql") else "?"
    return out, _params_for(out, ph, ctx)


def _is_dml(sql: str) -> bool:
    return bool(re.match(r"\s*(insert|update|delete|replace)\b", sql, re.IGNORECASE))


def _explain(db, sql: str, params: list, analyze: bool) -> str:
    from fpdb_3_legacy.Database import Database

    if db.backend == Database.PGSQL:
        prefix = "EXPLAIN (ANALYZE, BUFFERS, TIMING OFF) " if analyze else "EXPLAIN "
    elif db.backend == Database.MYSQL_INNODB:
        prefix = "EXPLAIN ANALYZE " if analyze else "EXPLAIN "
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


def bench_catalog(db, repeats: int) -> dict:
    from fpdb_3_legacy.Database import Database
    from fpdb_3_legacy.SQL import Sql

    db_server = {Database.SQLITE: "sqlite", Database.PGSQL: "postgresql", Database.MYSQL_INNODB: "mysql"}[db.backend]
    catalogue = Sql(db_server=db_server).query
    ctx = _context_values(db)
    results: dict[str, dict] = {}

    for name, raw_sql in sorted(catalogue.items()):
        if name == "placeholder" or not isinstance(raw_sql, str):
            continue
        sql = raw_sql.strip().rstrip(";")
        if sql.lower().startswith(SKIP_PREFIXES):
            results[name] = {"status": "skipped_ddl"}
            continue
        prepared = _prepare(sql, db_server, ctx)
        if prepared is None:
            results[name] = {"status": "skipped_template"}
            continue
        final_sql, params = prepared
        dml = _is_dml(final_sql)

        status, rows_count, error, walls = _run_one_query(db, final_sql, params, dml, repeats)
        plan = _explain(db, final_sql, params, analyze=(status == "ok" and not dml))
        results[name] = {
            "status": status,
            "rows": rows_count,
            "error": error,
            "wall": _percentiles(walls),
            "plan": plan,
        }
    return results


def _run_one_query(db, final_sql: str, params: list, dml: bool, repeats: int):
    """Execute one catalogue query ``repeats`` times; every attempt runs in a
    fresh transaction that is always rolled back, so DML never persists and a
    failed statement cannot poison the next one (PostgreSQL)."""
    walls: list[float] = []
    status, rows_count, error = "ok", 0, ""
    for _ in range(repeats):
        try:
            db.connection.rollback()
            c = db.connection.cursor()
            started = perf_counter()
            if params:
                c.execute(final_sql, params)
            else:
                c.execute(final_sql)
            if dml:
                # DML cost is the execute; never fetchall on a write.
                walls.append(perf_counter() - started)
            else:
                rows = c.fetchall()
                walls.append(perf_counter() - started)
                rows_count = len(rows)
                if not rows:
                    status = "empty"
            c.close()
        except Exception as exc:
            status = "error"
            error = str(exc)[:200]
            walls.append(0.0)
            break
        finally:
            try:
                db.connection.rollback()
            except Exception:
                pass  # nosec B110 -- best-effort cleanup
    return status, rows_count, error, walls


def summarize(results: dict) -> str:
    executed = {k: v for k, v in results.items() if v["status"] in ("ok", "empty", "error")}
    lines = [
        f"executed: {len(executed)} / {len(results)} "
        f"(skipped ddl: {sum(1 for v in results.values() if v['status'] == 'skipped_ddl')}, "
        f"templates: {sum(1 for v in results.values() if v['status'] == 'skipped_template')})",
        "",
        "| query | status | rows | p50 ms | p95 ms | max ms |",
        "|---|---|---|---|---|---|",
    ]
    ranked = sorted(executed.items(), key=lambda kv: -kv[1]["wall"]["p95"])
    for name, r in ranked[:40]:
        w = r["wall"]
        lines.append(
            f"| {name} | {r['status']} | {r['rows']} | {w['p50'] * 1000:.2f} | {w['p95'] * 1000:.2f} | {w['max'] * 1000:.2f} |"
        )
    lines.append("")
    lines.append("## sequential scans over big tables in captured plans")
    for name, r in executed.items():
        plan = r.get("plan", "")
        for table in BIG_TABLES:
            if re.search(rf"Seq Scan on {table}\b", plan, re.IGNORECASE) or re.search(
                rf"Table scan on {table}\b", plan, re.IGNORECASE
            ):
                lines.append(f"- {name}: {table}")
                break
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dsn", default=os.environ.get("FPDB_BENCH_DSN", ""))
    parser.add_argument("--corpus", nargs="+", default=list(DEFAULT_CORPUS))
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    files: list[Path] = []
    for pattern in args.corpus:
        files.extend(_corpus_files(pattern, 10_000))
    files = list(dict.fromkeys(files))

    with tempfile.TemporaryDirectory(prefix="fpdb-catalog-bench-", ignore_cleanup_errors=True) as root:
        workdir = Path(root)
        if args.dsn:
            os.environ["FPDB_BENCH_DSN"] = args.dsn
        config = _make_config(workdir, workdir / "bench.sqlite3")
        if not args.dsn:
            params = config.get_db_parameters()
            params.update(
                {
                    "db-server": "sqlite",
                    "db-backend": 4,
                    "db-databaseName": str(workdir / "bench.sqlite3"),
                    "db-path": "",
                }
            )
            config.get_db_parameters = lambda: params
        from fpdb_3_legacy.Database import Database
        from fpdb_3_legacy.Importer import Importer

        schema = Database(config)
        schema.recreate_tables()
        schema.close_connection()
        importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
        importer.setCallHud(True)
        for path in files:
            importer.addImportFile(str(path), "auto")
        stored, *_ = importer.runImport()
        importer.close()
        print(f"imported {stored} hands into {args.dsn or 'sqlite'}", file=sys.stderr)

        db = Database(config)
        results = bench_catalog(db, args.repeats)
        db.close_connection()

    report = {
        "backend": args.dsn or "sqlite",
        "dataset_hands": stored,
        "repeats": args.repeats,
        "queries": results,
    }
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
    print(summarize(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
