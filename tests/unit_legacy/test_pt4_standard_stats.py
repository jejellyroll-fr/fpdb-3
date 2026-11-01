"""The curated standard-stats descriptor library (stats.d/pt4_standard.toml)."""

from __future__ import annotations

import pytest

from fpdb_3_legacy import stat_registry as sr


@pytest.fixture()
def registry():
    reg = sr.StatRegistry()
    reg.load_directory(sr.default_stats_dir())
    return reg


STANDARD = [
    "vpip",
    "pfr",
    "rfi",
    "three_bet",
    "four_bet",
    "steal",
    "fold_bb_to_steal",
    "cbet_flop",
    "cbet_turn",
    "fold_to_cbet_flop",
    "wtsd",
    "wsd",
]


class TestStandardLibraryLoads:
    def test_all_standard_stats_present(self, registry):
        for name in STANDARD:
            assert name in registry, name

    def test_standard_stats_are_rates_not_curves(self, registry):
        # Percentages must not be cumulative graph curves.
        for name in STANDARD:
            assert registry.get(name).series is None

    def test_standard_stats_apply_to_ring_and_tour(self, registry):
        d = registry.get("vpip")
        assert d.applies_to("ring") and d.applies_to("tour")

    def test_standard_fact_inputs_are_declared_boolean(self, registry):
        for name in STANDARD:
            descriptor = registry.get(name)
            assert descriptor.boolean_inputs == descriptor.inputs

    def test_series_still_only_chipev(self, registry):
        # Adding the standard library must not change the cumulative curve set.
        assert {d.name for d in registry.series_for_scope("tour")} == {
            "chipev_3h_btn",
            "chipev_3h_sb",
            "chipev_3h_bb",
            "chipev_hu_sb",
            "chipev_hu_bb",
        }


class TestStandardComputation:
    def test_vpip_ratio(self, registry):
        d = registry.get("vpip")
        assert d.compute({"street0VPI": 68, "street0VPIChance": 100}) == pytest.approx(68.0)

    def test_three_bet_ratio(self, registry):
        d = registry.get("three_bet")
        assert d.compute({"street0_3BDone": 1, "street0_3BChance": 8}) == pytest.approx(12.5)

    def test_zero_opportunity_renders_placeholder(self, registry):
        d = registry.get("four_bet")
        assert d.format(d.compute({"street0_4BDone": 0, "street0_4BChance": 0})) == "-"


class TestAdvancedStats:
    """Float and Fold-to-Squeeze: computed by DerivedStats, surfaced via grid."""

    def test_present(self, registry):
        for name in ("float_turn", "float_river", "fold_to_squeeze"):
            assert name in registry, name

    def test_columns_match_native_definitions(self, registry):
        # Same raw columns FPDB's get_stats_from_hand_aggregated aggregates.
        assert registry.get("float_turn").inputs == ("flg_t_float", "flg_t_float_opp")
        assert registry.get("float_river").inputs == ("flg_r_float", "flg_r_float_opp")
        assert registry.get("fold_to_squeeze").inputs == (
            "street0_FoldToSqueezeDone",
            "street0_FoldToSqueezeChance",
        )

    def test_float_turn_ratio(self, registry):
        d = registry.get("float_turn")
        assert d.compute({"flg_t_float": 3, "flg_t_float_opp": 10}) == pytest.approx(30.0)
