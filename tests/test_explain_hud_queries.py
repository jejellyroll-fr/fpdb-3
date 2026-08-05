"""Tests for the plan review in tools/explain_hud_queries.

The tool itself needs a PostgreSQL database to run against, so what is checked
here is the part that decides what a plan is telling you -- against plan text
of the shape PostgreSQL actually emits.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "tools" / "explain_hud_queries.py"
spec = importlib.util.spec_from_file_location("explain_hud_queries", TOOL)
explain_hud_queries = importlib.util.module_from_spec(spec)
sys.modules["explain_hud_queries"] = explain_hud_queries
spec.loader.exec_module(explain_hud_queries)

review = explain_hud_queries.review


def test_a_sequential_scan_over_hudcache_is_flagged() -> None:
    """The join that the compound index cannot serve is the whole question."""
    plan = [
        "Seq Scan on hudcache hc  (cost=0.00..91234.00 rows=2100000 width=520)",
        "  Filter: ((gametypeid + 0) = ANY (...))",
    ]

    findings = review(plan)

    assert any("sequential scan over hudcache" in f for f in findings)


def test_a_sequential_scan_over_a_lookup_table_is_not_flagged() -> None:
    """Gametypes is small and is supposed to be scanned; saying so is noise."""
    assert review(["Seq Scan on gametypes gt2  (cost=0.00..1.30 rows=30 width=8)"]) == []


def test_an_index_scan_is_not_flagged() -> None:
    plan = ["Index Scan using hudcache_playerid_idx on hudcache hc  (cost=0.42..8.44 rows=1 width=520)"]

    assert review(plan) == []


def test_a_bad_row_estimate_is_flagged() -> None:
    """A planner that expects 12 rows and gets 40000 picks the wrong join."""
    plan = ["Nested Loop  (cost=0.85..123.45 rows=12 width=8) (actual time=0.02..812.33 rows=40000 loops=1)"]

    findings = review(plan)

    assert any("row estimate off by" in f for f in findings)


def test_a_good_row_estimate_is_not_flagged() -> None:
    plan = ["Hash Join  (cost=0.85..123.45 rows=900 width=8) (actual time=0.02..3.10 rows=1000 loops=1)"]

    assert review(plan) == []


def test_blocks_read_from_disk_are_flagged() -> None:
    findings = review(["Buffers: shared hit=12 read=8140"])

    assert any("8140 blocks read from disk" in f for f in findings)


def test_an_all_cache_hit_is_not_flagged() -> None:
    assert review(["Buffers: shared hit=12043 read=0"]) == []


def test_an_empty_plan_says_nothing() -> None:
    assert review([]) == []
