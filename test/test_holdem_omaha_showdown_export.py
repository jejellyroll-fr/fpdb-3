import io
from decimal import Decimal

import pytest

from fpdb_3_legacy.Hand import HoldemOmahaHand


@pytest.mark.parametrize(
    ("category", "cards"),
    [
        ("holdem", ["As", "Ks"]),
        ("omahahi", ["As", "Ks", "Qs", "Js"]),
        ("5_omahahi", ["As", "Ks", "Qs", "Js", "Ts"]),
        ("6_omahahi", ["As", "Ks", "Qs", "Js", "Ts", "9s"]),
    ],
)
def test_showdown_uses_game_card_count_and_seat_order(category: str, cards: list[str]) -> None:
    hand = HoldemOmahaHand.__new__(HoldemOmahaHand)
    hand.players = [(1, "alice", Decimal("100")), (2, "bob", Decimal("100"))]
    hand.gametype = {"category": category}
    hand.holeStreets = ["PREFLOP"]
    hand.holecards = {"PREFLOP": {"alice": ([], cards)}}
    hand.shown = {"alice"}
    hand.mucked = {"bob"}
    hand.showdownStrings = {"alice": "a winning hand"}
    output = io.StringIO()

    hand._write_showdown(output)

    assert output.getvalue() == (
        "*** SHOW DOWN ***\n"
        f"alice: shows [{' '.join(cards)}] (a winning hand)\n"
        "bob: mucks hand\n"
    )


def test_showdown_omits_incomplete_shown_hand() -> None:
    hand = HoldemOmahaHand.__new__(HoldemOmahaHand)
    hand.players = [(1, "alice", Decimal("100"))]
    hand.gametype = {"category": "holdem"}
    hand.holeStreets = ["PREFLOP"]
    hand.holecards = {"PREFLOP": {"alice": ([], ["As"])}}
    hand.shown = {"alice"}
    hand.mucked = set()
    hand.showdownStrings = {}
    output = io.StringIO()

    hand._write_showdown(output)

    assert output.getvalue() == ""
