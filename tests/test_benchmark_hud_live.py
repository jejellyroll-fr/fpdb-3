"""Smoke test for tools/benchmark_hud_live.py (#680).

Marked perf: it imports real hand histories into a throwaway SQLite database
and replays HUD batches, so it belongs to the explicit benchmark runs, not the
default suite. It pins the contract the investigation doc relies on: every
configuration reports latency percentiles and round-trip counts.
"""

from __future__ import annotations

import json

import pytest

from tools import benchmark_hud_live

pytestmark = pytest.mark.perf


def test_the_benchmark_reports_percentiles_and_round_trips(tmp_path) -> None:
    out = tmp_path / "report.json"
    rc = benchmark_hud_live.main(
        [
            "--tables",
            "1,2",
            "--stat-range",
            "A",
            "--repeats",
            "2",
            "--corpus-limit",
            "4",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert len(payload["results"]) == 2
    for result in payload["results"]:
        wall = result["latency"]["bench_batch_wall"]
        assert wall["count"] == 2
        assert wall["p95"] >= wall["p50"] >= 0
        assert result["round_trips"]["total_calls"] > 0
    assert "| tables |" in payload["markdown"]


def test_a_corpus_with_too_few_tables_is_refused() -> None:
    with pytest.raises(SystemExit, match="cannot simulate"):
        benchmark_hud_live.main(["--tables", "999", "--repeats", "1", "--corpus-limit", "2"])
