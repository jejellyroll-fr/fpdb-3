"""Regression tests for Hand.totalPot() side-pot splitting.

A side pot is cut at each distinct commitment level. When the smallest
commitment was fractional, totalPot used to slice it into one 1.00 pot per whole
unit plus the remainder: the totals came out right, but the pot *count* grew
with the stakes. A $1,835.50 all-in produced 1,836 pots, each one costing a
poker-eval board evaluation and a HandsPots row, and a $500k play-money hand was
far worse.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from fpdb_3_legacy.Hand import Hand, Pot


def _hand(committed: dict[str, str], collected: str, game_type: str = "ring"):
    pot = Pot()
    for name, amount in committed.items():
        pot.addPlayer(name)
        pot.addMoney(name, Decimal(amount))
    return SimpleNamespace(
        pot=pot,
        gametype={"type": game_type},
        totalpot=None,
        totalcollected=Decimal(collected),
        rake=None,
        handid="26063988000",
        sitename="Full Tilt Poker",
    )


def test_fractional_all_in_makes_one_side_pot_per_level() -> None:
    # FTP hand 26063988000: BB folds for 50, the other two are all in for 1835.50.
    hand = _hand({"Player1": "50", "Hero": "1835.50", "Player3": "1835.50"}, collected="3718")

    total = Hand.totalPot(hand)

    assert hand.pot.pots == [
        (Decimal("150"), {"Player1", "Hero", "Player3"}),
        (Decimal("3571.00"), {"Hero", "Player3"}),
    ]
    assert total == Decimal("3721.00")
    assert hand.rake == Decimal("3.00")


def test_whole_number_commitments_are_unchanged() -> None:
    hand = _hand({"Player1": "10", "Hero": "30", "Player3": "30"}, collected="70")

    total = Hand.totalPot(hand)

    assert hand.pot.pots == [
        (Decimal("30"), {"Player1", "Hero", "Player3"}),
        (Decimal("40"), {"Hero", "Player3"}),
    ]
    assert total == Decimal("70")


def test_a_deep_play_money_pot_does_not_explode() -> None:
    """The pot count follows the players, not the size of the stacks."""
    hand = _hand({"Hero": "500000.50", "Villain": "500000.50"}, collected="1000001")

    Hand.totalPot(hand)

    assert len(hand.pot.pots) == 1


def test_the_uncalled_part_of_a_bet_is_returned_not_potted() -> None:
    hand = _hand({"Hero": "100.50", "Villain": "40"}, collected="80")

    total = Hand.totalPot(hand)

    assert hand.pot.pots == [(Decimal("80"), {"Hero", "Villain"})]
    assert hand.pot.returned["Hero"] == Decimal("60.50")
    assert total == Decimal("80")
