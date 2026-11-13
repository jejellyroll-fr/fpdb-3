"""Unit tests for non-Qt business logic, formatting, and analysis functions in Gui*.py modules."""

from __future__ import annotations

from fpdb_3_legacy import GuiAutoNoteRules, GuiOpponentsReport, GuiStatsInfo, GuiTourneyPlayerStats

# ---------------------------------------------------------------------------
# GuiStatsInfo Tests
# ---------------------------------------------------------------------------


def test_stats_data_structure() -> None:
    """Verify the Stats Guide groups its generated entries by category, each complete."""
    grouped = GuiStatsInfo._grouped_stats()
    assert "Preflop" in grouped
    assert "Flop / 4th street" in grouped

    for category, stats in grouped.items():
        assert isinstance(category, str)
        assert isinstance(stats, list)
        for stat in stats:
            for key in ("name", "title", "abbr", "description", "detail", "formula", "sql"):
                assert key in stat, f"{stat['name']} lacks {key}"


def test_stats_data_search_filtering() -> None:
    """Verify the guide's search finds a stat by name, abbreviation or title."""
    found = [
        stat
        for stats in GuiStatsInfo._grouped_stats().values()
        for stat in stats
        if GuiStatsInfo._matches(stat, "vpip")
    ]

    assert len(found) > 0
    assert any(s["name"] == "vpip" and s["abbr"] == "v" for s in found)


# ---------------------------------------------------------------------------
# GuiOpponentsReport Tests
# ---------------------------------------------------------------------------


def test_pct_helper() -> None:
    """Verify pct calculation and zero division protection."""
    assert GuiOpponentsReport.pct(5, 20) == 25.0
    assert GuiOpponentsReport.pct(0, 100) == 0.0
    assert GuiOpponentsReport.pct(10, 0) == 0.0
    assert GuiOpponentsReport.pct(None, None) == 0.0


def test_format_preflop_rates() -> None:
    """Verify format_preflop_rates output formatting."""
    formatted = GuiOpponentsReport.format_preflop_rates(22.5, 18.2, 7.1)
    assert "/" in formatted


def test_percentile_calculation() -> None:
    """Verify percentile function with linear interpolation."""
    assert GuiOpponentsReport.percentile([], 50) is None
    assert GuiOpponentsReport.percentile([42.0], 90) == 42.0

    data = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert GuiOpponentsReport.percentile(data, 0) == 10.0
    assert GuiOpponentsReport.percentile(data, 100) == 50.0
    assert GuiOpponentsReport.percentile(data, 50) == 30.0


def test_calibrate_thresholds_fallback() -> None:
    """Verify calibrate_thresholds falls back to defaults for small populations."""
    small_pop = [{"fold_to_3bet": 40.0} for _ in range(5)]
    thresholds = GuiOpponentsReport.calibrate_thresholds(small_pop)
    assert thresholds == GuiOpponentsReport.DEFAULT_THRESHOLDS


def test_calibrate_thresholds_large_population() -> None:
    """Verify threshold calibration on sufficient opponent populations."""
    large_pop = [{"fold_to_3bet": float(i * 5)} for i in range(20)]
    thresholds = GuiOpponentsReport.calibrate_thresholds(large_pop)
    assert "fold_to_3bet" in thresholds
    assert thresholds["fold_to_3bet"] >= GuiOpponentsReport.DEFAULT_THRESHOLDS["fold_to_3bet"]


def test_classify_player_type() -> None:
    """Verify player style classification based on VPIP/PFR ratios."""
    assert GuiOpponentsReport.classify_player_type(45.0, 30.0) == "LAG"
    assert GuiOpponentsReport.classify_player_type(45.0, 10.0) == "Loose Passive"
    assert GuiOpponentsReport.classify_player_type(28.0, 20.0) == "TAG"
    assert GuiOpponentsReport.classify_player_type(28.0, 10.0) == "Calling Station"
    assert GuiOpponentsReport.classify_player_type(18.0, 14.0) == "TAG (Tight)"
    assert GuiOpponentsReport.classify_player_type(18.0, 5.0) == "Weak Tight"
    assert GuiOpponentsReport.classify_player_type(10.0, 10.0) == "NIT"
    assert GuiOpponentsReport.classify_player_type(8.0, 2.0) == "Rock"


def test_clamp_helper() -> None:
    """Verify clamp numerical bounding."""
    assert GuiOpponentsReport.clamp(50.0, 0.0, 100.0) == 50.0
    assert GuiOpponentsReport.clamp(-10.0, 0.0, 100.0) == 0.0
    assert GuiOpponentsReport.clamp(150.0, 0.0, 100.0) == 100.0


def test_compute_metrics() -> None:
    """Verify raw SQL row aggregation into computed metrics."""
    raw = {
        "opp_id": 1,
        "pname": "Villain1",
        "hds": 200,
        "hero_net_bb": 50.0,
        "opp_net_bb": -50.0,
        "vpip": 50,
        "vpip_opp": 200,
        "pfr": 30,
        "pfr_opp": 200,
        "tb": 10,
        "tb_opp": 100,
        "f3b": 15,
        "f3b_opp": 20,
        "f_cb": 12,
        "f_cb_opp": 20,
        "saw_f": 50,
        "sd": 15,
        "postflop_aggr": 30,
        "postflop_seen": 60,
    }
    metrics = GuiOpponentsReport.compute_metrics(raw)
    assert metrics["opp_id"] == 1
    assert metrics["pname"] == "Villain1"
    assert metrics["hds"] == 200
    assert metrics["vpip"] == 25.0
    assert metrics["pfr"] == 15.0
    assert metrics["profile"] == "Calling Station"
    assert metrics["hero_bb_per_100"] == 25.0
    assert metrics["opp_bb_per_100"] == -25.0


# ---------------------------------------------------------------------------
# GuiTourneyPlayerStats Tests
# ---------------------------------------------------------------------------


def test_tourney_player_stats_column_constants() -> None:
    """Verify column metadata set definitions in GuiTourneyPlayerStats."""
    assert "buyIn" in GuiTourneyPlayerStats._MONEY_COLUMNS
    assert "fee" in GuiTourneyPlayerStats._MONEY_COLUMNS
    assert "net" in GuiTourneyPlayerStats._MONEY_COLUMNS
    assert "itm" in GuiTourneyPlayerStats._PERCENT_COLUMNS
    assert "roi" in GuiTourneyPlayerStats._PERCENT_COLUMNS
    assert "tourneyCount" in GuiTourneyPlayerStats._COUNT_COLUMNS


# ---------------------------------------------------------------------------
# GuiAutoNoteRules Tests
# ---------------------------------------------------------------------------


def test_autonoterules_presets_existence() -> None:
    """Verify GuiAutoNoteRules provides AutoNoteRulesDialog class and rule helpers."""
    assert hasattr(GuiAutoNoteRules, "AutoNoteRulesDialog")
    assert callable(GuiAutoNoteRules.configured_rule_summary)
