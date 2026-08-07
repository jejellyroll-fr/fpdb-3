"""Unit tests for Replayer Push Equity, Call Equity, and Pot Odds metrics."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

from fpdb_3_legacy.GuiReplayer import GuiReplayer, ReplayPlayer


class _FakeEquityBackend:
    def poker_eval(self, **kwargs):
        return {
            "info": (1000, 0, 1),
            "eval": [
                {"ev": 600, "winhi": 550, "tiehi": 100, "losehi": 350},
                {"ev": 400, "winhi": 350, "tiehi": 100, "losehi": 550},
            ],
        }


def test_hero_decision_metrics_pot_odds_and_equities(monkeypatch) -> None:
    replayer = GuiReplayer.__new__(GuiReplayer)
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
    replayer = GuiReplayer.__new__(GuiReplayer)
    replayer.Heroes = "Hero"
    replayer.currency_code = "USD"
    replayer.replay_model = cast(Any, SimpleNamespace(hand=SimpleNamespace(gametype={"category": "holdem"})))

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


def test_hero_decision_metrics_supports_stud_and_draw() -> None:
    replayer = GuiReplayer.__new__(GuiReplayer)
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

