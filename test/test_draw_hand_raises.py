from decimal import Decimal

from fpdb_3_legacy.Hand import DrawHand


class _PotRecorder:
    def __init__(self) -> None:
        self.added: list[tuple[str, Decimal]] = []

    def addMoney(self, player: str, amount: Decimal) -> None:
        self.added.append((player, amount))


def test_successive_raise_to_actions_keep_total_amount_to_match() -> None:
    hand = DrawHand.__new__(DrawHand)
    hand.lastBet = {"DEAL": Decimal("2")}
    hand.bets = {
        "DEAL": {
            "alice": [Decimal("1")],
            "bob": [Decimal("2")],
        },
    }
    hand.stacks = {"alice": Decimal("100"), "bob": Decimal("100")}
    hand.actions = {"DEAL": []}
    hand.pot = _PotRecorder()
    hand.checkPlayerExists = lambda _player, _source=None: None

    hand.addRaiseTo("DEAL", "alice", "6")
    hand.addRaiseTo("DEAL", "bob", "10")

    assert hand.lastBet["DEAL"] == Decimal("10")
    assert hand.bets["DEAL"]["alice"] == [Decimal("1"), Decimal("5")]
    assert hand.bets["DEAL"]["bob"] == [Decimal("2"), Decimal("8")]
    assert hand.actions["DEAL"] == [
        ("alice", "raises", Decimal("4"), Decimal("6"), Decimal("1"), False),
        ("bob", "raises", Decimal("4"), Decimal("10"), Decimal("4"), False),
    ]
    assert hand.pot.added == [("alice", Decimal("5")), ("bob", Decimal("8"))]
