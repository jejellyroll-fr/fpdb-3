"""Unit tests for the replayer's hand equity and pot odds metrics (one equity, not Call/Push Eq: #872)."""

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
    low_rank, low_cards = best_low_hand(villain.holecards)
    assert low_rank == (8, 7, 4, 2, 1)
    assert low_cards == {"2h", "Ac", "4c", "7c", "8h"}
    assert cards["Player5"] == low_cards


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
    assert metrics["hand_equity_pct"] == Decimal(60)
    assert metrics["equity_diff_pts"] == Decimal(35)  # 60 - 25 = 35
    # One equity for the hand: no separate call and push figures that were never priced apart.
    assert "call_equity_pct" not in metrics
    assert "push_equity_pct" not in metrics


def test_equity_says_whether_every_board_was_enumerated(monkeypatch) -> None:
    replayer = cast(Any, GuiReplayer).__new__(GuiReplayer)  # pylint: disable=no-value-for-parameter
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
        players=[SimpleNamespace(equity=Decimal("0.60")), SimpleNamespace(equity=Decimal("0.40"))], exhaustive=True
    ))

    metrics = replayer._hero_decision_metrics(frame, 0)

    assert metrics["equity_exhaustive"] is True
    assert metrics["pot_before_call"] == Decimal(15)
    assert metrics["final_pot"] == Decimal(20)


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


def _fusion_replayer(monkeypatch) -> tuple[Any, list[tuple[str, list[list[str]], list[str]]]]:
    replayer = cast(Any, GuiReplayer).__new__(GuiReplayer)  # pylint: disable=no-value-for-parameter
    replayer.Heroes = "Hero"
    replayer.currency_code = "USD"
    hand = SimpleNamespace(gametype={"category": "fusion", "base": "hold"}, holeStreets=["PREFLOP", "FLOP", "TURN"])
    replayer.replay_model = cast(Any, SimpleNamespace(hand=hand))
    calls: list[tuple[str, list[list[str]], list[str]]] = []

    def engine(game, pockets, board, **_kwargs):
        calls.append((game, pockets, board))
        return SimpleNamespace(players=[SimpleNamespace(equity=Decimal("0.30")), SimpleNamespace(equity=Decimal("0.70"))])

    monkeypatch.setattr("fpdb_3_legacy.GuiReplayer.calculate_equity", engine)
    return replayer, calls


def _fusion_frame(*streets: str) -> Any:
    board = {"FLOP": ["2s", "5s", "8s"], "TURN": ["9s"], "RIVER": []}
    return cast(Any, SimpleNamespace(
        players=[
            # Final pockets: the replay players hold all four from the start.
            ReplayPlayer("Hero", 1, Decimal(0), Decimal(10), "calls", False, ["As", "Kd", "Qc", "Jh"]),
            ReplayPlayer("Villain", 2, Decimal(0), Decimal(15), "bets", False, ["Td", "Tc", "3h", "4h"]),
        ],
        pot=Decimal(15),
        board={street: board[street] for street in streets},
        render_board=set(streets),
    ))


def test_fusion_flop_equity_holds_only_the_cards_dealt_so_far(monkeypatch) -> None:
    # On the flop the turn's hole card is not dealt yet: the engine gets the
    # three cards each player holds and deals the fourth itself (#818).
    replayer, calls = _fusion_replayer(monkeypatch)

    metrics = replayer._hero_decision_metrics(_fusion_frame("FLOP"), 0)

    assert calls == [("fusion", [["As", "Kd", "Qc"], ["Td", "Tc", "3h"]], ["2s", "5s", "8s"])]
    assert metrics["pot_odds_pct"] == Decimal(25)
    assert metrics["hand_equity_pct"] == Decimal(30)


def test_fusion_equity_from_the_turn_holds_all_four_hole_cards(monkeypatch) -> None:
    replayer, calls = _fusion_replayer(monkeypatch)

    metrics = replayer._hero_decision_metrics(_fusion_frame("FLOP", "TURN"), 0)

    assert calls == [("fusion", [["As", "Kd", "Qc", "Jh"], ["Td", "Tc", "3h", "4h"]], ["2s", "5s", "8s", "9s"])]
    assert metrics["hand_equity_pct"] == Decimal(30)


def _draw_replayer(monkeypatch) -> tuple[Any, list[tuple[str, list[list[str]], list[str]]]]:
    replayer = cast(Any, GuiReplayer).__new__(GuiReplayer)  # pylint: disable=no-value-for-parameter
    replayer.Heroes = "Hero"
    replayer.currency_code = "USD"
    replayer.replay_model = cast(
        Any, SimpleNamespace(hand=SimpleNamespace(gametype={"category": "27_3draw", "base": "draw"}))
    )
    calls: list[tuple[str, list[list[str]], list[str]]] = []

    def engine(game, pockets, board, **_kwargs):
        calls.append((game, pockets, board))
        return SimpleNamespace(players=[SimpleNamespace(equity=Decimal(1)), SimpleNamespace(equity=Decimal(0))])

    monkeypatch.setattr("fpdb_3_legacy.GuiReplayer.calculate_equity", engine)
    return replayer, calls


def _draw_frame(street: str) -> Any:
    return cast(
        Any,
        SimpleNamespace(
            players=[
                ReplayPlayer("Hero", 1, Decimal(0), Decimal(10), "calls", False, ["7c", "5d", "4h", "3s", "2c"]),
                ReplayPlayer("Villain", 2, Decimal(0), Decimal(15), "bets", False, ["8c", "6d", "5h", "4s", "2d"]),
            ],
            pot=Decimal(15),
            board={},
            render_board=set(),
            street=street,
        ),
    )


def test_draw_equity_waits_for_the_last_draw(monkeypatch) -> None:
    # Before the third draw the hands shown are not the ones that will play:
    # their showdown is not the equity (#831).
    replayer, calls = _draw_replayer(monkeypatch)

    metrics = replayer._hero_decision_metrics(_draw_frame("DRAWTWO"), 0)

    assert not calls
    assert metrics["hand_equity_pct"] is None
    assert metrics["pot_odds_pct"] == Decimal(25)


def test_draw_equity_after_the_last_draw_is_the_showdown(monkeypatch) -> None:
    replayer, calls = _draw_replayer(monkeypatch)

    metrics = replayer._hero_decision_metrics(_draw_frame("DRAWTHREE"), 0)

    assert calls == [("lowball27", [["7c", "5d", "4h", "3s", "2c"], ["8c", "6d", "5h", "4s", "2d"]], [])]
    assert metrics["hand_equity_pct"] == Decimal(100)
