"""Tests for the Opponents Report (head-to-head vs hero).

Covers the pure heuristic helpers (no GUI / no DB required) and a light
structural check of the ``opponentsReport`` SQL query for every backend.
"""

import pytest

from fpdb_3_legacy.GuiOpponentsReport import (
    DEFAULT_THRESHOLDS,
    build_leak_metrics,
    calibrate_thresholds,
    classify_player_type,
    compute_metrics,
    pct,
    percentile,
    pick_exploit,
)


# ---------------------------------------------------------------------------
# pct
# ---------------------------------------------------------------------------
def test_pct_guards_division_by_zero():
    assert pct(5, 0) == 0.0
    assert pct(None, None) == 0.0


def test_pct_basic():
    assert pct(24, 100) == pytest.approx(24.0)


# ---------------------------------------------------------------------------
# classify_player_type
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("vpip", "pfr", "expected"),
    [
        (48, 12, "Loose Passive"),
        (45, 28, "LAG"),
        (28, 20, "TAG"),
        (28, 10, "Calling Station"),
        (18, 14, "TAG (Tight)"),
        (18, 5, "Weak Tight"),
        (12, 11, "NIT"),
        (8, 4, "Rock"),
    ],
)
def test_classify_player_type(vpip, pfr, expected):
    assert classify_player_type(vpip, pfr) == expected


# ---------------------------------------------------------------------------
# compute_metrics
# ---------------------------------------------------------------------------
def _raw(**overrides):
    raw = {
        "opp_id": 7,
        "pname": "RegA",
        "hds": 200,
        "hero_net_bb": -340.0,
        "opp_net_bb": 340.0,
        "vpip_opp": 200,
        "vpip": 48,
        "pfr_opp": 200,
        "pfr": 40,
        "tb_opp": 100,
        "tb": 20,
        "f3b_opp": 50,
        "f3b": 10,
        "saw_f": 80,
        "sd": 20,
        "cb_opp": 40,
        "cb": 30,
        "f_cb_opp": 40,
        "f_cb": 10,
        "cb2_opp": 40,
        "cb2": 12,
        "f_cb2_opp": 40,
        "f_cb2": 26,
        "cb3_opp": 40,
        "cb3": 25,
        "bbsteal_opp": 100,
        "bbsteal_fold": 70,
        "river_aggr": 5,
        "river_seen": 50,
        "wmsd": 12,
        "postflop_aggr": 30,
        "postflop_seen": 120,
        "last_seen": "2024-01-01 12:00:00",
    }
    raw.update(overrides)
    return raw


def test_compute_metrics_percentages():
    m = compute_metrics(_raw())
    assert m["vpip"] == pytest.approx(24.0)
    assert m["pfr"] == pytest.approx(20.0)
    assert m["three_bet"] == pytest.approx(20.0)
    assert m["fold_to_3bet"] == pytest.approx(20.0)
    assert m["hds"] == 200
    # opponent winrate vs hero in bb/100
    assert m["opp_bb_per_100"] == pytest.approx(170.0)
    assert m["profile"] == classify_player_type(m["vpip"], m["pfr"])
    assert "danger" in m
    assert "exploit" in m


def test_compute_metrics_hero_bb_per_100():
    # hero loses 340 bb over 200 shared hands => -170 bb/100
    m = compute_metrics(_raw(hero_net_bb=-340.0, hds=200))
    assert m["hero_bb_per_100"] == pytest.approx(-170.0)


def test_compute_metrics_zero_hands_safe():
    m = compute_metrics(_raw(hds=0))
    assert m["hero_bb_per_100"] == 0.0
    assert m["opp_bb_per_100"] == 0.0


# ---------------------------------------------------------------------------
# Leak Buster integration (build_leak_metrics + compute_metrics)
# ---------------------------------------------------------------------------
def test_build_leak_metrics_maps_aliases():
    lm = build_leak_metrics(_raw())
    assert lm["fold_bb_vs_steal"] == pytest.approx(70.0)  # 70/100
    assert lm["cbet_turn"] == pytest.approx(30.0)  # cb2 12/40
    assert lm["fold_to_turn_cbet"] == pytest.approx(65.0)  # f_cb2 26/40
    assert lm["river_aggr_freq"] == pytest.approx(10.0)  # 5/50
    assert lm["river_bet_freq"] == pytest.approx(62.5)  # cb3 25/40
    assert lm["wsd"] == pytest.approx(60.0)  # wmsd 12 / sd 20


def test_compute_metrics_exposes_leaks():
    m = compute_metrics(_raw())
    assert "leaks" in m
    assert isinstance(m["leaks"], list)
    # The fixture opponent over-folds BB vs steal (70%) -> leak detected.
    titles = {leak["title"] for leak in m["leaks"]}
    assert "Overfolds BB vs steal" in titles
    # Primary exploit comes from the LeakDetector engine.
    assert m["exploit"] != "—"
    assert m["exploit_score"] > 0.0


def test_compute_metrics_no_leak_when_balanced():
    m = compute_metrics(
        _raw(
            bbsteal_opp=100,
            bbsteal_fold=50,
            f3b_opp=50,
            f3b=25,
            cb_opp=40,
            cb=24,
            cb2_opp=40,
            cb2=22,
            f_cb2_opp=40,
            f_cb2=18,
            cb3_opp=40,
            cb3=8,
            saw_f=80,
            sd=22,
            wmsd=14,
            river_aggr=20,
            river_seen=50,
        )
    )
    assert m["leaks"] == []
    assert m["exploit"] == "—"


# ---------------------------------------------------------------------------
# compute_danger
# ---------------------------------------------------------------------------
def test_danger_within_bounds():
    m = compute_metrics(_raw(opp_net_bb=2000.0))
    assert 0.0 <= m["danger"] <= 10.0


def test_danger_scales_with_sample():
    low = compute_metrics(_raw(hds=20))
    high = compute_metrics(_raw(hds=400))
    # Same per-hand profile but larger sample => higher confidence/danger.
    assert high["danger"] >= low["danger"]


def test_danger_winning_reg_more_dangerous_than_losing_fish():
    reg = compute_metrics(
        _raw(hds=300, opp_net_bb=600.0, vpip=66, pfr=60, vpip_opp=300, pfr_opp=300)
    )  # 22/20 reg, winning
    fish = compute_metrics(
        _raw(hds=300, opp_net_bb=-600.0, vpip=150, pfr=30, vpip_opp=300, pfr_opp=300)
    )  # 50/10 losing fish
    assert reg["danger"] > fish["danger"]


# ---------------------------------------------------------------------------
# pick_exploit
# ---------------------------------------------------------------------------
def test_exploit_fold_to_3bet():
    label, score = pick_exploit(
        {
            "f3b_opp": 40,
            "fold_to_3bet": 80.0,
            "f_cb_opp": 0,
            "fold_to_cbet": 0.0,
            "saw_f": 0,
            "wtsd": 0.0,
            "postflop_aggr_freq": 0.0,
            "vpip": 22.0,
            "pfr": 20.0,
        }
    )
    assert label == "3-bet light"
    assert score > 1.0


def test_exploit_value_thin_for_station():
    label, score = pick_exploit(
        {
            "f3b_opp": 0,
            "fold_to_3bet": 0.0,
            "f_cb_opp": 0,
            "fold_to_cbet": 0.0,
            "saw_f": 50,
            "wtsd": 28.0,
            "postflop_aggr_freq": 20.0,
            "vpip": 45.0,
            "pfr": 12.0,
        }
    )
    assert label == "Value thin"
    assert score > 0.0


def test_exploit_none_when_no_leak():
    label, score = pick_exploit(
        {
            "f3b_opp": 5,
            "fold_to_3bet": 50.0,
            "f_cb_opp": 5,
            "fold_to_cbet": 40.0,
            "saw_f": 10,
            "wtsd": 27.0,
            "postflop_aggr_freq": 30.0,
            "vpip": 22.0,
            "pfr": 18.0,
        }
    )
    assert label == "—"
    assert score == 0.0


def test_exploit_requires_min_opportunities():
    # High fold-to-3bet but too few opportunities -> not flagged.
    label, _ = pick_exploit(
        {
            "f3b_opp": 3,
            "fold_to_3bet": 90.0,
            "f_cb_opp": 0,
            "fold_to_cbet": 0.0,
            "saw_f": 0,
            "wtsd": 0.0,
            "postflop_aggr_freq": 0.0,
            "vpip": 22.0,
            "pfr": 20.0,
        }
    )
    assert label != "3-bet light"


# ---------------------------------------------------------------------------
# percentile
# ---------------------------------------------------------------------------
def test_percentile_empty_returns_none():
    assert percentile([], 50) is None


def test_percentile_basic():
    data = [10, 20, 30, 40]
    assert percentile(data, 0) == pytest.approx(10.0)
    assert percentile(data, 100) == pytest.approx(40.0)
    assert percentile(data, 50) == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# calibrate_thresholds
# ---------------------------------------------------------------------------
def test_calibrate_falls_back_on_small_population():
    rows = [compute_metrics(_raw()) for _ in range(3)]
    assert calibrate_thresholds(rows) == DEFAULT_THRESHOLDS


def test_calibrate_never_relaxes_below_floor():
    # A pool of tight, low-fold players must not lower the fold-to-3bet floor.
    rows = []
    for _ in range(12):
        rows.append(
            compute_metrics(_raw(f3b_opp=50, f3b=10, vpip=40, pfr=36, vpip_opp=200, pfr_opp=200))
        )  # fold_to_3bet=20%, gap small
    t = calibrate_thresholds(rows)
    assert t["fold_to_3bet"] >= DEFAULT_THRESHOLDS["fold_to_3bet"]
    assert t["station_gap"] >= DEFAULT_THRESHOLDS["station_gap"]


def test_calibrate_tightens_on_loose_pool():
    # A pool where everyone over-folds to 3bet raises the cutoff above the floor.
    rows = []
    for _ in range(12):
        rows.append(compute_metrics(_raw(f3b_opp=100, f3b=85)))  # fold_to_3bet=85%
    t = calibrate_thresholds(rows)
    assert t["fold_to_3bet"] > DEFAULT_THRESHOLDS["fold_to_3bet"]


def test_calibrated_thresholds_affect_exploit():
    # Legacy ``pick_exploit`` helper (kept for the calibration plumbing):
    # a player folding 70% to 3bet is flagged under the default floor (65)...
    metrics = {
        "f3b_opp": 40,
        "fold_to_3bet": 70.0,
        "f_cb_opp": 0,
        "fold_to_cbet": 0.0,
        "saw_f": 0,
        "wtsd": 0.0,
        "postflop_aggr_freq": 0.0,
        "vpip": 22.0,
        "pfr": 20.0,
    }
    assert pick_exploit(metrics)[0] == "3-bet light"
    # ...but not when the pool cutoff is raised to 80.
    label, _ = pick_exploit(metrics, {**DEFAULT_THRESHOLDS, "fold_to_3bet": 80.0})
    assert label != "3-bet light"


def test_compute_metrics_flags_fold_to_3bet_leak():
    # New LeakDetector path: 70% fold to 3bet over a sufficient sample.
    m = compute_metrics(_raw(f3b_opp=50, f3b=35))
    titles = {leak["title"] for leak in m["leaks"]}
    assert "Overfolds to 3-bets" in titles


# ---------------------------------------------------------------------------
# SQL structure
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("backend", ["mysql", "postgresql", "sqlite"])
def test_opponents_report_query_present(backend):
    import fpdb_3_legacy.SQL as SQL

    sql = SQL.Sql(db_server=backend)
    assert "opponentsReport" in sql.query
    q = sql.query["opponentsReport"]
    for placeholder in (
        "<player_test>",
        "<site_test>",
        "<game_test>",
        "<currency_test>",
        "<gtbigBlind_test>",
        "<datestest>",
        "<minhands>",
        "<maxopponents>",
    ):
        assert placeholder in q
    # Driven from the hero's hands (indexed playerId) then joined to opponents.
    assert "from HandsPlayers hphero" in q
    assert "where hphero.playerId in <player_test>" in q
    assert "opp.handId = hphero.handId" in q
    assert "not in <player_test>" in q
    assert "limit <maxopponents>" in q
    # Leak Buster columns (turn/river cbet, steal defense, river aggression).
    for column in (
        "street2CBChance",
        "street2CBDone",
        "foldToStreet2CBChance",
        "foldToStreet2CBDone",
        "street3CBChance",
        "street3CBDone",
        "foldBbToStealChance",
        "foldedBbToSteal",
        "street3Aggr",
        "street3Seen",
    ):
        assert column in q
    for alias in ("cb2_opp", "cb2", "f_cb2_opp", "f_cb2", "cb3_opp", "cb3",
                  "bbsteal_opp", "bbsteal_fold", "river_aggr", "river_seen"):
        assert alias in q
