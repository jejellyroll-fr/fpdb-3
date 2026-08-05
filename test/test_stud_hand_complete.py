from decimal import Decimal

import pytest

from fpdb_3_legacy.Hand import StudHand


class _PotRecorder:
    def __init__(self) -> None:
        self.added: list[tuple[str, Decimal]] = []

    def addMoney(self, player: str, amount: Decimal) -> None:
        self.added.append((player, amount))


@pytest.mark.parametrize(
    ("committed", "called", "added"),
    [
        (Decimal("0.25"), Decimal("0.00"), Decimal("0.75")),
        (Decimal("0.00"), Decimal("0.25"), Decimal("1.00")),
    ],
)
def test_complete_to_accounts_for_existing_street_commitment(
    committed: Decimal,
    called: Decimal,
    added: Decimal,
) -> None:
    hand = StudHand.__new__(StudHand)
    hand.lastBet = {"THIRD": Decimal("0.25")}
    hand.bets = {"THIRD": {"alice": [committed] if committed else []}}
    hand.stacks = {"alice": Decimal("10.00")}
    hand.actions = {"THIRD": []}
    hand.pot = _PotRecorder()
    hand.checkPlayerExists = lambda _player, _source=None: None

    hand.addComplete("THIRD", "alice", "1.00")

    assert hand.bets["THIRD"]["alice"][-1] == added
    assert hand.stacks["alice"] == Decimal("10.00") - added
    assert hand.actions["THIRD"] == [
        ("alice", "completes", Decimal("0.75"), Decimal("1.00"), called, False),
    ]
    assert hand.lastBet["THIRD"] == Decimal("1.00")
    assert hand.pot.added == [("alice", added)]
