"""Regression tests for uncalled-bet accounting in reports."""

from decimal import Decimal

from fpdb_3_legacy.Hand import Hand, Pot


def test_uncalled_bet_is_removed_once_from_bet_and_net() -> None:
    pot = Pot()
    pot.addPlayer("Hero")
    pot.addMoney("Hero", Decimal("5.24"))
    pot.removeMoney("Hero", Decimal("1.65"))

    hand = Hand.__new__(Hand)
    hand.pot = pot
    hand.collectees = {"Hero": Decimal("3.59")}
    hand.calculate_net_collected()

    assert pot.committed["Hero"] == Decimal("3.59")
    assert pot.returned["Hero"] == Decimal("1.65")
    assert hand.net_collected["Hero"] == Decimal("0.00")


def test_multiple_uncalled_returns_are_accumulated() -> None:
    pot = Pot()
    pot.addPlayer("Hero")
    pot.addMoney("Hero", Decimal("10.00"))
    pot.removeMoney("Hero", Decimal("1.25"))
    pot.removeMoney("Hero", Decimal("0.75"))

    assert pot.committed["Hero"] == Decimal("8.00")
    assert pot.returned["Hero"] == Decimal("2.00")
