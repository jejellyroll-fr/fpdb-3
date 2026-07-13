from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.DerivedStats import DerivedStats
from fpdb_3_legacy.equity import (
    EquityUnavailableError,
    calculate_equity,
    expected_pot_share,
    load_poker_eval,
)
from fpdb_3_legacy.HandDataReporter import HandDataReporter


class FakePokerEval:
    def __init__(self) -> None:
        self.arguments = None

    def poker_eval(self, **kwargs) -> dict:
        self.arguments = kwargs
        return {
            "info": (2000, 0, 1),
            "eval": [
                {"ev": 825, "winhi": 1600, "tiehi": 100, "losehi": 300},
                {"ev": 175, "winhi": 300, "tiehi": 100, "losehi": 1600},
            ],
        }


def test_calculate_equity_normalizes_backend_permille() -> None:
    backend = FakePokerEval()

    result = calculate_equity(
        "holdem",
        [["As", "Ah"], ["Ks", "Kh"]],
        ["2c", "3d", "4h"],
        iterations=2000,
        backend=backend,
    )

    assert result.samples == 2000
    assert result.exhaustive is False
    assert [player.equity for player in result.players] == [Decimal("0.825"), Decimal("0.175")]
    assert result.players[0].wins == 1600
    assert result.players[0].ties == 100
    assert backend.arguments["iterations"] == 2000
    assert backend.arguments["board"] == ["2c", "3d", "4h", "__", "__"]


def test_calculate_equity_rejects_duplicate_cards_before_calling_backend() -> None:
    with pytest.raises(ValueError, match="more than once"):
        calculate_equity("holdem", [["As", "Ah"], ["As", "Kh"]], backend=FakePokerEval())


def test_calculate_equity_reports_missing_optional_backend(monkeypatch) -> None:
    monkeypatch.setattr("fpdb_3_legacy.equity.load_poker_eval", lambda: None)

    with pytest.raises(EquityUnavailableError, match="not installed"):
        calculate_equity("holdem", [["As", "Ah"], ["Ks", "Kh"]])


def test_expected_pot_share_uses_net_pot() -> None:
    assert expected_pot_share(Decimal("0.4"), Decimal("100"), Decimal("5")) == Decimal("38.0")


@pytest.mark.parametrize(
    ("equity", "pot", "rake"),
    [(Decimal("1.1"), Decimal("10"), Decimal(0)), (Decimal("0.5"), Decimal("10"), Decimal("11"))],
)
def test_expected_pot_share_rejects_invalid_inputs(equity: Decimal, pot: Decimal, rake: Decimal) -> None:
    with pytest.raises(ValueError):
        expected_pot_share(equity, pot, rake)


def test_native_backend_enumerates_missing_turn_and_river() -> None:
    backend = load_poker_eval()
    if backend is None:
        pytest.skip("optional pypoker-eval backend is not installed")

    result = calculate_equity(
        "holdem",
        [["As", "Ah"], ["Ks", "Kh"]],
        ["2c", "3d", "4h"],
        backend=backend,
    )

    assert result.exhaustive is True
    assert result.samples == 990
    assert result.players[0].equity == Decimal("0.912")
    assert result.players[1].equity == Decimal("0.087")


def test_derived_stats_stores_expected_all_in_profit_x100(monkeypatch) -> None:
    backend = FakePokerEval()
    monkeypatch.setattr("fpdb_3_legacy.DerivedStats.pokereval", backend)
    stats = DerivedStats()
    stats.handsplayers = {
        "hero": {"sawShowdown": True, "wentAllIn": True, "allInEV": 0},
        "villain": {"sawShowdown": True, "wentAllIn": True, "allInEV": 0},
    }
    hand = SimpleNamespace(
        handid="all-in-1",
        gametype={"base": "hold"},
        totalpot=Decimal("200"),
        rake=Decimal(0),
        pot=SimpleNamespace(
            committed={"hero": Decimal("100"), "villain": Decimal("100")},
            common={},
        ),
    )

    stats.getAllInEV(
        hand,
        "holdem",
        ["hero", "villain"],
        {"FLOP": {"allin": True, "board": [["2c", "3d", "4h"]]}},
        {},
        {"hero": {"hole": ["As", "Ah"]}, "villain": {"hole": ["Ks", "Kh"]}},
    )

    assert stats.handsplayers["hero"]["allInEV"] == 6500
    assert stats.handsplayers["villain"]["allInEV"] == -6500


def test_hand_report_exposes_readable_all_in_ev() -> None:
    hand = SimpleNamespace(
        handid="reported-all-in",
        players=[(1, "hero", Decimal("100"))],
        handsplayers={"hero": {"allInEV": 6500}},
        gametype={"currency": "USD", "limitType": "nl", "category": "holdem"},
    )

    data = HandDataReporter("detailed")._extract_hand_data(hand)

    assert data["players"]["hero"]["all_in_ev_x100"] == 6500
    assert data["players"]["hero"]["all_in_ev"] == "65"


def test_boards_dict_detects_real_all_in_and_accumulates_board() -> None:
    hand = SimpleNamespace(
        handid="board-all-in",
        board={"FLOP": ["2c", "3d", "4h"], "TURN": ["5s"], "RIVER": ["6c"]},
        actions={
            "PREFLOP": [("hero", "calls", Decimal("2"), False)],
            "FLOP": [("villain", "raises", Decimal("98"), Decimal("100"), Decimal(0), True)],
            "TURN": [],
            "RIVER": [],
        },
    )

    boards = DerivedStats().getBoardsDict(
        hand,
        "holdem",
        {"PREFLOP": 0, "FLOP": 1, "TURN": 2, "RIVER": 3},
    )

    assert boards["PREFLOP"] == {"board": [[]], "allin": False}
    assert boards["FLOP"] == {"board": [["2c", "3d", "4h"]], "allin": True}
    assert boards["TURN"] == {"board": [["2c", "3d", "4h", "5s"]], "allin": False}
    assert boards["RIVER"] == {"board": [["2c", "3d", "4h", "5s", "6c"]], "allin": False}
