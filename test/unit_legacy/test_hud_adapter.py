"""Unit tests for the HUD adapter and its do_stat integration."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from fpdb_3_legacy import stat_registry as sr
from fpdb_3_legacy.stat_adapters import HudAdapter


@pytest.fixture()
def registry():
    reg = sr.StatRegistry()
    reg.load_directory(sr.default_stats_dir())
    return reg


class TestBucketEncoding:
    def test_button_maps_to_D(self, registry):
        # HudCache stores the button as the 'D' bucket, not '0'.
        pred = HudAdapter().dimension_predicate(registry.get("chipev_3h_btn"))
        assert pred == "hc.seats = 3 AND hc.position = 'D'"

    def test_blinds_keep_letters(self, registry):
        assert HudAdapter().dimension_predicate(registry.get("chipev_hu_sb")) == "hc.seats = 2 AND hc.position = 'S'"
        assert HudAdapter().dimension_predicate(registry.get("chipev_3h_bb")) == "hc.seats = 3 AND hc.position = 'B'"

    def test_select_fragment_bucketed(self, registry):
        # Alias is unquoted: the HUD query is shared across SQLite/MySQL/Postgres.
        frags = HudAdapter().select_fragments(registry.get("chipev_3h_btn"))
        expected = "SUM(CASE WHEN hc.seats = 3 AND hc.position = 'D' THEN hc.allInEV ELSE 0 END) AS chipev_3h_btn__allInEV"
        assert frags == [expected]

    def test_select_clause_leading_comma(self, registry):
        clause = HudAdapter().select_clause(registry.series_for_scope("tour"))
        assert clause.startswith(", ")
        assert clause.count("CASE WHEN hc.seats") == 5


class TestCompute:
    def test_dimensioned_reads_injected_alias_lowercased(self, registry):
        # The HUD query stores keys lower-cased; the injected alias is read back.
        adapter = HudAdapter()
        d = registry.get("chipev_3h_sb")
        player_stats = {"chipev_3h_sb__allinev": 2500}
        assert adapter.compute(d, player_stats) == 25.0

    def test_ratio_over_existing_columns_no_injection(self, registry):
        # A ratio stat over raw HudCache columns works straight from stat_dict.
        reg = sr.StatRegistry()
        reg.add(
            sr.build_descriptor({
                "name": "myvpip",
                "label": "My VPIP",
                "inputs": ["street0VPI", "street0VPIChance"],
                "value": "100 * street0VPI / street0VPIChance",
                "scope": ["ring", "tour"],
                "format": "%3.1f",
            }),
        )
        adapter = HudAdapter()
        d = reg.get("myvpip")
        # stat_dict keys are lower-cased by the HUD aggregation.
        stats = {"street0vpi": 30, "street0vpichance": 100}
        assert adapter.compute(d, stats) == 30.0

    def test_stat_tuple_shape(self, registry):
        adapter = HudAdapter()
        d = registry.get("chipev_3h_sb")
        t = adapter.stat_tuple(d, {"chipev_3h_sb__allinev": 2500})
        assert len(t) == 6
        assert t[0] == 25.0
        assert t[1] == "25"
        assert t[5] == "ChipEV 3-handed SB"


class TestDoStatIntegration:
    def test_descriptor_stat_via_do_stat(self):
        from fpdb_3_legacy import Stats

        stat_dict = {7: {"chipev_3h_sb__allinev": 2500}}
        result = Stats.do_stat(stat_dict, player=7, stat="chipev_3h_sb")
        assert result is not None
        assert result[0] == 25.0
        assert result[5] == "ChipEV 3-handed SB"

    def test_unknown_stat_returns_none(self):
        from fpdb_3_legacy import Stats

        assert Stats.do_stat({7: {}}, player=7, stat="not_a_real_stat_xyz") is None

    def test_native_stat_still_works(self):
        from fpdb_3_legacy import Stats

        # vpip is a native function and must keep precedence over any descriptor.
        stat_dict = {7: {"vpip": 0.25, "screen_name": "x"}}
        result = Stats.do_stat(stat_dict, player=7, stat="vpip")
        assert result is not None
