"""Unit tests for Replayer Push Equity, Call Equity, and Pot Odds metrics."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

from fpdb_3_legacy.GuiReplayer import GuiReplayer, ReplayPlayer, best_low_hand, stud_hilo_winners


def test_stud_hilo_evaluation_identifies_high_and_low_winners() -> None:
    hero = ReplayPlayer("Hero", 1, Decimal(0), Decimal(0), "calls", False, ["5s", "6d", "7d", "8s", "4s", "Kd", "5h"])
    villain = ReplayPlayer("Player5", 5, Decimal(0), Decimal(0), "calls", False, ["2h", "Ac", "As", "7c", "Ks", "4c", "8h"])
    high, low, cards = stud_hilo_winners([hero, villain])

    assert high == {"Hero"}
    assert low == {"Player5"}
    assert cards["Hero"] == {"4s", "5s", "6d", "7d", "8s"}
    assert cards["Player5"] == {"2h", "4c", "7c", "8h", "Ac"}


def test_stud_hilo_low_requires_five_distinct_cards_eight_or_lower() -> None:
    rank, cards = best_low_hand(["As", "2d", "3c", "4h", "9s", "Kd", "Qh"])
    assert rank is None
    assert cards == frozenset()


def test_hero_decision_metrics_pot_odds_and_equities(monkeypatch) -> None:
    replayer = cast(Any, GuiReplayer).__new__(GuiReplayer)  # pylint: disable=no-value-for-parameter
    replayer.Heroes = "Hero"
    replayer.currency_code = "USD"

    hand = SimpleNamespace(gametype={"category": "holdem", "base": "hold"})
    replayer.replay_model = cast(Any, SimpleNamespace(hand=hand))

    # Hero facing a $5 call into a $15 pot ($20 pot after call -> 25% pot odds, 3:1 ratio)
    frame = cast(Any, SimpleNamespace(
        players=[
            ReplayPlayer("Hero", 1, Decimal(0), Decimal(10), "calls", False, ["As", "Ah"]),
            ReplayPlayer("Villain", 2, Decimal(0), Decimal(15), "bets", False, ["Ks", "Kh"]),
        ],
        pot=Decimal(15),
        board={"FLOP": ["2c", "3d", "4h"]},
        render_board={"FLOP"},
    ))

    monkeypatch.setattr("fpdb_3_legacy.GuiReplayer.calculate_equity", lambda *args, **kwargs: SimpleNamespace(
        players=[SimpleNamespace(equity=Decimal("0.60")), SimpleNamespace(equity=Decimal("0.40"))]
    ))

    metrics = replayer._hero_decision_metrics(frame, 0)

    assert metrics["facing_call"] is True
    assert metrics["call_amount"] == Decimal(5)
    assert metrics["pot_odds_pct"] == Decimal(25)  # 5 / 20 * 100
    assert metrics["pot_odds_ratio"] == Decimal(3)  # 15 / 5 = 3:1
    assert metrics["call_equity_pct"] == Decimal(60)
    assert metrics["call_edge_pts"] == Decimal(35)  # 60 - 25 = 35
    assert metrics["push_equity_pct"] == Decimal(60)


def test_hero_odds_summary_formatted_string(monkeypatch) -> None:
    replayer = cast(Any, GuiReplayer).__new__(GuiReplayer)  # pylint: disable=no-value-for-parameter
    replayer.Heroes = "Hero"
    replayer.currency_code = "USD"
    replayer.replay_model = cast(Any, SimpleNamespace(hand=SimpleNamespace(gametype={"category": "holdem"})))
    replayer.states = [
        SimpleNamespace(players={}),
        SimpleNamespace(players={1: SimpleNamespace(name="Hero", justacted=True, action="calls")}),
    ]

    frame = cast(Any, SimpleNamespace(
        players=[
            ReplayPlayer("Hero", 1, Decimal(0), Decimal(10), "calls", False, ["As", "Ah"]),
            ReplayPlayer("Villain", 2, Decimal(0), Decimal(15), "bets", False, ["Ks", "Kh"]),
        ],
        pot=Decimal(15),
        board={"FLOP": ["2c", "3d", "4h"]},
        render_board={"FLOP"},
    ))

    monkeypatch.setattr("fpdb_3_legacy.GuiReplayer.calculate_equity", lambda *args, **kwargs: SimpleNamespace(
        players=[SimpleNamespace(equity=Decimal("0.60")), SimpleNamespace(equity=Decimal("0.40"))]
    ))

    summary = replayer._hero_odds_summary(frame, 0)

    assert "Hero call $5.00" in summary
    assert "pot odds 25.0% (3.0:1)" in summary
    assert "Call Eq 60.0%" in summary
    assert "edge +35.0 pts" in summary
    assert "Push Eq 60.0%" in summary

    replayer.states[1].players[1].name = "Villain"
    assert replayer._hero_odds_summary(frame, 0) == ""


def test_hero_decision_metrics_supports_stud_and_draw() -> None:
    replayer = cast(Any, GuiReplayer).__new__(GuiReplayer)  # pylint: disable=no-value-for-parameter
    replayer.Heroes = "Hero"
    replayer.currency_code = "USD"
    # Stud/Draw gametypes: studhi, 7stud8, razz, 27_3draw, badugi
    hand = SimpleNamespace(gametype={"category": "studhi", "base": "stud"})
    replayer.replay_model = cast(Any, SimpleNamespace(hand=hand))

    frame = cast(Any, SimpleNamespace(
        players=[
            ReplayPlayer("Hero", 1, Decimal(0), Decimal(20), "calls", False, ["As", "Kd", "Qc", "Jh", "Ts"]),
            ReplayPlayer("Villain", 2, Decimal(0), Decimal(40), "bets", False, ["2s", "3d", "4c", "5h", "7s"]),
        ],
        pot=Decimal(60),
        board={},
        render_board=set(),
    ))

    metrics = replayer._hero_decision_metrics(frame, 0)

    # Pot Odds are computed from chips & pot regardless of variant
    assert metrics["facing_call"] is True
    assert metrics["call_amount"] == Decimal(20)
    assert metrics["pot_odds_pct"] == Decimal(25)  # 20 / (60 + 20) = 25%
    assert metrics["pot_odds_ratio"] == Decimal(3)  # 60 / 20 = 3:1
