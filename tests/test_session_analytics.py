from __future__ import annotations

import math

from fpdb_3_legacy.session_analytics import build_session_graph_quotes, build_sessions, summarize_sessions


def test_session_metrics_normalize_each_hand_by_its_own_blind() -> None:
    sessions = build_sessions(
        [
            (3, 1_200, 200, 250, 100, "USD"),
            (1, 1_000, 100, 50, 100, "USD"),
            (2, 1_100, -50, -50, 200, "USD"),
        ]
    )

    assert len(sessions) == 1
    session = sessions[0]
    assert session.hand_ids == (1, 2, 3)
    assert session.profit_minor == 250
    assert session.profit_bb == 2.75
    assert session.bb_per_100 == 2.75 / 3 * 100
    assert session.all_in_ev_bb == 2.75
    assert session.ev_bb_per_100 == 2.75 / 3 * 100
    assert session.ev_difference_minor == 0


def test_session_duration_hourly_rates_and_drawdown() -> None:
    session = build_sessions(
        [
            (1, 1_000, 100, 100, 100, "EUR"),
            (2, 1_100, -250, -200, 100, "EUR"),
            (3, 1_200, 100, 100, 100, "EUR"),
        ]
    )[0]

    assert session.duration_seconds == 500
    assert session.max_drawdown_minor == 250
    assert session.peak_minor == 100
    assert session.low_minor == -150
    assert session.bb_per_hour == -0.5 / (500 / 3600)
    assert session.currency_per_hour == -0.5 / (500 / 3600)


def test_fixed_limit_sessions_show_bb_metrics_as_unavailable() -> None:
    session = build_sessions([(1, 1_000, 250, 300, -1, "USD")])[0]

    assert session.profit_minor == 250
    assert session.bb_hands == 0
    assert session.profit_bb is None
    assert session.bb_per_100 is None
    assert session.all_in_ev_bb is None
    assert session.ev_bb_per_100 is None
    assert session.bb_per_hour is None


def test_mixed_known_and_unknown_blinds_use_only_valid_hands_for_rates() -> None:
    sessions = build_sessions(
        [
            (1, 1_000, 200, 100, 100, "USD"),
            (2, 1_100, -500, -250, -1, "USD"),
        ]
    )

    session = sessions[0]
    assert session.hands == 2
    assert session.bb_hands == 1
    assert session.profit_bb == 2
    assert session.bb_per_100 == 200
    assert session.bb_per_hour is None
    summary = summarize_sessions(sessions)
    assert summary["bb_hands"] == 1
    assert summary["bb_per_100"] == 200
    assert summary["bb_per_hour"] is None


def test_sessions_split_after_gap_and_currency_change() -> None:
    sessions = build_sessions(
        [
            (1, 1_000, 100, 100, 100, "USD"),
            (2, 1_100, 100, 100, 100, "USD"),
            (3, 3_000, 100, 100, 100, "USD"),
            (4, 3_100, 100, 100, 100, "EUR"),
        ]
    )

    assert [session.hand_ids for session in sessions] == [(1, 2), (3,), (4,)]
    summary = summarize_sessions(sessions)
    assert summary["currency"] is None
    assert "profit_minor" not in summary
    assert summary["hands"] == 4
    assert summary["profit_bb"] == 4


def test_homogeneous_currency_summary_includes_native_totals() -> None:
    sessions = build_sessions(
        [
            (1, 1_000, 100, 100, 100, "USD"),
            (2, 1_100, -50, 0, 100, "USD"),
        ]
    )

    summary = summarize_sessions(sessions)
    assert summary["currency"] == "USD"
    assert summary["profit_minor"] == 50
    assert summary["currency_per_hour"] == 0.5 / (400 / 3600)


def test_empty_rows_have_no_sessions() -> None:
    assert build_sessions([]) == []
    assert summarize_sessions([])["hands"] == 0


def test_session_graph_quotes_are_cumulative_and_skip_incomplete_blinds() -> None:
    sessions = build_sessions(
        [
            (1, 1_000, 500, 500, 100, "USD"),
            (2, 3_000, 1_000, 1_000, 100, "USD"),
            (3, 3_100, -1_000, -1_000, 100, "USD"),
            (4, 5_000, -200, -200, 100, "USD"),
            (5, 7_000, 250, 250, -1, "USD"),
            (6, 9_000, 100, 100, 100, "USD"),
        ]
    )

    quotes = build_session_graph_quotes(sessions)

    assert quotes[0] == (1, 0, 5, 5, 0)
    assert quotes[1] == (2, 5, 5, 15, 5)
    assert quotes[2] == (3, 5, 3, 5, 3)
    assert quotes[3][0:2] == (4, 3)
    assert all(math.isnan(value) for value in quotes[3][2:])
    assert quotes[4] == (5, 3, 4, 4, 3)
