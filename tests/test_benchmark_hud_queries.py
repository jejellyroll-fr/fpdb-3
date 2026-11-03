"""Smoke test for tools/benchmark_hud_queries.py (#680).

Perf-marked: it imports real hand histories and runs every HUD query case, so
it belongs to explicit benchmark runs. It pins the contract: a report with the
same dataset on every backend, percentile timings per query case, and a
captured query plan for the heavy queries.
"""

from __future__ import annotations

import json

import pytest

from tools import benchmark_hud_queries

pytestmark = pytest.mark.perf

ONE_FILE = "regression-test-files/cash/Stars/Flop/NLHE-6max-EUR-0.05-0.10-200911.txt"


def test_the_query_bench_reports_percentiles_and_plans(tmp_path) -> None:
    out = tmp_path / "qbench.json"
    rc = benchmark_hud_queries.main(["--corpus", ONE_FILE, "--repeats", "2", "--out", str(out)])
    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["dataset"]["hands"] > 0
    for case in ("aggregated_per_hand", "aggregated_batch_6", "session_per_hand", "hand_construction"):
        assert case in report["cases"]
        wall = report["cases"][case]["wall"]
        assert wall["count"] == 2
        assert wall["p95"] >= wall["p50"] >= 0
    for plan in ("aggregated_per_hand", "session_per_hand"):
        assert report["plans"][plan]
    assert "| query case |" in benchmark_hud_queries.format_markdown(report)
