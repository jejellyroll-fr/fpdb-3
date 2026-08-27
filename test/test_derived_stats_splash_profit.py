"""Regression coverage for normalizing splash money into total profit."""

from decimal import Decimal
from types import SimpleNamespace

from fpdb_3_legacy.DerivedStats import DerivedStats


def test_live_capture_splash_is_included_in_total_profit() -> None:
    stats = DerivedStats.__new__(DerivedStats)
    stats.handsplayers = {
        "hero": {
            "winnings": 100,
            "totalProfit": 0,
        },
    }
    hand = SimpleNamespace(
        pot=SimpleNamespace(committed={"hero": Decimal("1.00")}, common={"hero": Decimal("0")}, stp=0),
        splashWinnings={"hero": Decimal("0.20")},
        players=["hero"],
        rake=Decimal("0"),
        totalpot=Decimal("1.00"),
    )

    stats._assemblePlayerContributions(hand)

    assert stats.handsplayers["hero"]["totalProfit"] == 20


def test_hand_history_stp_is_not_added_twice() -> None:
    stats = DerivedStats.__new__(DerivedStats)
    stats.handsplayers = {"hero": {"winnings": 120, "totalProfit": 0}}
    hand = SimpleNamespace(
        pot=SimpleNamespace(committed={"hero": Decimal("1.00")}, common={"hero": Decimal("0")}, stp=Decimal("0.20")),
        splashWinnings={"hero": Decimal("0.20")},
        players=["hero"],
        rake=Decimal("0"),
        totalpot=Decimal("1.20"),
    )

    stats._assemblePlayerContributions(hand)

    assert stats.handsplayers["hero"]["totalProfit"] == 20
