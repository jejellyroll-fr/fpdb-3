"""GGPoker No Limit Hold'em cash regression — GitHub issue #140.

The reporter imported a NLH 6-max cash file and saw hands with no hero, no
actions, no hole cards, and "Collected amount (x) exceeds total pot (0.01)".
The cause was the one ``test_ggpoker_blinds_uncalled`` covers: the big blind was
never added to the pot and uncalled bets were never returned, so the pot came
out short and ``totalcollected`` overshot it.

That test uses a PLO file, and every GGPoker fixture in the tree was PLO or
Short Deck — the NLH cash format the report was actually about had no coverage
at all. This file closes that gap: three hands at $0.01/$0.02 6-max, two of them
ending on an uncalled bet, which is the shape that broke money conservation.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.GGPokerToFpdb import GGPoker

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "hands" / "ggpoker" / "nlh_cash_6max.txt"

# hand id -> (total pot, collected, rake, hero hole cards)
EXPECTED = {
    "2917912634": (Decimal("0.13"), Decimal("0.12"), Decimal("0.01"), ["Ah", "Kd"]),
    "2917910322": (Decimal("0.77"), Decimal("0.75"), Decimal("0.02"), ["Qs", "Qh"]),
    "2917910182": (Decimal("0.58"), Decimal("0.55"), Decimal("0.03"), ["Jc", "Jd"]),
}


@pytest.fixture(scope="module")
def parsed_hands():
    parser = GGPoker(config=Config(), in_path=str(FIXTURE), autostart=True)
    hands = parser.getProcessedHands()
    for hand in hands:
        hand.totalPot()
    return hands


def _by_id(hands, hand_id: str):
    return next(h for h in hands if str(h.handid) == hand_id)


def test_all_hands_are_parsed(parsed_hands) -> None:
    assert {str(h.handid) for h in parsed_hands} == set(EXPECTED)


def test_gametype_is_nlh_ring(parsed_hands) -> None:
    for hand in parsed_hands:
        assert hand.gametype["category"] == "holdem"
        assert hand.gametype["limitType"] == "nl"
        assert hand.gametype["type"] == "ring"


@pytest.mark.parametrize("hand_id", sorted(EXPECTED))
def test_hero_is_identified(parsed_hands, hand_id: str) -> None:
    """ "No hero found in the hand" was logged for every imported hand."""
    assert _by_id(parsed_hands, hand_id).hero == "Hero"


@pytest.mark.parametrize("hand_id", sorted(EXPECTED))
def test_hero_hole_cards_are_read(parsed_hands, hand_id: str) -> None:
    hand = _by_id(parsed_hands, hand_id)
    _, _, _, expected_cards = EXPECTED[hand_id]

    assert hand.holecards["PREFLOP"][hand.hero][1] == expected_cards


@pytest.mark.parametrize("hand_id", sorted(EXPECTED))
def test_hand_has_actions(parsed_hands, hand_id: str) -> None:
    hand = _by_id(parsed_hands, hand_id)

    assert sum(len(actions) for actions in hand.actions.values()) > 0


@pytest.mark.parametrize("hand_id", sorted(EXPECTED))
def test_money_is_conserved(parsed_hands, hand_id: str) -> None:
    """The reported symptom: collected must never exceed the pot."""
    hand = _by_id(parsed_hands, hand_id)
    expected_pot, expected_collected, expected_rake, _ = EXPECTED[hand_id]

    assert Decimal(str(hand.totalpot)) == expected_pot
    assert Decimal(str(hand.totalcollected)) == expected_collected
    assert Decimal(str(hand.totalcollected)) <= Decimal(str(hand.totalpot))
    assert Decimal(str(hand.rake)) == expected_rake


def test_big_blind_reaches_the_pot(parsed_hands) -> None:
    """The big blind used to be iterated over and dropped, leaving the pot short."""
    hand = _by_id(parsed_hands, "2917912634")
    blinds = [a for a in hand.actions["BLINDSANTES"] if a[1] == "big blind"]

    assert blinds, "the big blind post must reach the hand"
    assert Decimal(str(blinds[0][2])) == Decimal("0.02")


@pytest.mark.parametrize(
    ("hand_id", "returned"),
    [("2917912634", Decimal("0.08")), ("2917910322", Decimal("0.45"))],
)
def test_uncalled_bet_is_returned_to_hero(parsed_hands, hand_id: str, returned: Decimal) -> None:
    hand = _by_id(parsed_hands, hand_id)

    assert hand.pot.returned["Hero"] == returned
