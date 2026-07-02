"""Unit tests for the GraphAdapter (cumulative ChipEV-by-position curves)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from fpdb_3_legacy import stat_registry as sr
from fpdb_3_legacy.stat_adapters import GraphAdapter


@pytest.fixture()
def registry():
    reg = sr.StatRegistry()
    reg.load_directory(sr.default_stats_dir())
    return reg


class TestSelectFragments:
    def test_per_event_case_not_summed(self, registry):
        adapter = GraphAdapter()
        frags = adapter.select_fragments(registry.get("chipev_3h_sb"))
        assert frags == [
            'CASE WHEN h.seats = 3 AND hp.position = \'S\' THEN hp.allInEV ELSE 0 END AS "chipev_3h_sb__allInEV"',
        ]
        assert "SUM(" not in frags[0]

    def test_select_clause_covers_five_curves(self, registry):
        adapter = GraphAdapter()
        clause = adapter.select_clause(registry.series_for_scope("tour"))
        assert clause.count("CASE WHEN") == 5


class TestSeriesValues:
    def test_cumulative_sum_scaled(self, registry):
        adapter = GraphAdapter()
        d = registry.get("chipev_3h_sb")
        # Three SB hands at the 3-handed table: allInEV stored x100.
        rows = [
            {"chipev_3h_sb__allInEV": 10000},   # +100 chips
            {"chipev_3h_sb__allInEV": -5000},   # -50 chips
            {"chipev_3h_sb__allInEV": 2500},    # +25 chips
        ]
        assert adapter.series_values(d, rows) == pytest.approx([100.0, 50.0, 75.0])

    def test_non_matching_event_contributes_zero(self, registry):
        adapter = GraphAdapter()
        d = registry.get("chipev_3h_sb")
        # A hand at another position is gated to 0 by the SQL CASE -> flat curve.
        rows = [
            {"chipev_3h_sb__allInEV": 10000},
            {"chipev_3h_sb__allInEV": 0},
            {"chipev_3h_sb__allInEV": 0},
        ]
        assert adapter.series_values(d, rows) == pytest.approx([100.0, 100.0, 100.0])

    def test_empty_rows(self, registry):
        adapter = GraphAdapter()
        assert adapter.series_values(registry.get("chipev_3h_sb"), []) == []

    def test_all_five_curves_independent(self, registry):
        adapter = GraphAdapter()
        curves = registry.series_for_scope("tour")
        # One row where only the BTN curve has value; others should stay flat at 0.
        row = {
            "chipev_3h_btn__allInEV": 30000,
            "chipev_3h_sb__allInEV": 0,
            "chipev_3h_bb__allInEV": 0,
            "chipev_hu_sb__allInEV": 0,
            "chipev_hu_bb__allInEV": 0,
        }
        results = {d.name: adapter.series_values(d, [row]) for d in curves}
        assert results["chipev_3h_btn"] == pytest.approx([300.0])
        assert results["chipev_3h_sb"] == pytest.approx([0.0])
