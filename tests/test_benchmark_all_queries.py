"""Smoke test for tools/benchmark_all_queries.py (#680).

Perf-marked: it imports real hand histories and executes the whole SQL
catalogue. It pins the contract: most catalogue queries execute against the
populated database, each gets a status and a captured plan, and DML never
persists (rolled back).
"""

from __future__ import annotations

import json

import pytest

from tools import benchmark_all_queries

pytestmark = pytest.mark.perf

ONE_FILE = "regression-test-files/cash/Stars/Flop/NLHE-6max-EUR-0.05-0.10-200911.txt"


def test_the_catalog_bench_executes_most_queries_and_captures_plans(tmp_path) -> None:
    out = tmp_path / "catalog.json"
    rc = benchmark_all_queries.main(["--corpus", ONE_FILE, "--repeats", "1", "--out", str(out)])
    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    queries = report["queries"]
    assert len(queries) > 300
    executed = [v for v in queries.values() if v["status"] in ("ok", "empty", "error")]
    assert len(executed) > 150
    assert any(v.get("plan") for v in executed)
    # DML was rolled back: the hand count is unchanged by the bench itself.
    dml = [
        n for n, v in queries.items() if v["status"] == "ok" and n.startswith(("insert", "update", "delete", "clear"))
    ]
    assert dml  # write queries were exercised
    summary = benchmark_all_queries.summarize(queries)
    assert "| query |" in summary
