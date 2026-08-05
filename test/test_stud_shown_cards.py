"""A seven-stud showdown listing six cards must still be recorded.

Rooms do not all print seven cards at showdown: ACR shows six and leaves the
seventh-street card to the deal line. StudHand.addShownCards required more than
six, so those showdowns were dropped entirely -- the player's down cards were
never recorded, and join_holecards then returned his up cards twice over,
building a hand that cannot exist (eight cards, each of them twice).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.WinningToFpdb import Winning

HAND_FILE = Path(
    "/Users/jde/Downloads/AmericasCardroom/handHistory/edinapoker/"
    "HH20260717 CASHID-G35414311T295 TN-Braselton GAMETYPE-7 Stud H{BACKSLASH}L "
    "LIMIT-fixed CUR-REAL OND-F BUYIN-0 MIN-10 MAX-20.txt",
)

pytestmark = pytest.mark.skipif(not HAND_FILE.exists(), reason="local ACR hand history not present")


@pytest.fixture(scope="module")
def stud_hand():
    hands = Winning(config=Config(), in_path=str(HAND_FILE), autostart=True).getProcessedHands()
    return next(h for h in hands if str(h.handid) == "2780605304")


def test_a_six_card_showdown_is_recorded(stud_hand) -> None:
    # "Seat 6: Montlebon showed [7h 6s 8h 4c 5c 5s]" -- six cards, not seven.
    assert "Montlebon" in stud_hand.shown


def test_down_cards_reach_third_street(stud_hand) -> None:
    open_cards, closed_cards = stud_hand.holecards["THIRD"]["Montlebon"]

    assert closed_cards == ["7h", "6s"]  # was [] -- never recorded
    assert open_cards == ["8h"]


def test_the_hand_is_seven_distinct_cards(stud_hand) -> None:
    cards = stud_hand.join_holecards("Montlebon", asList=True)

    assert cards == ["7h", "6s", "8h", "4c", "5c", "5s", "6d"]
    assert len(cards) == len(set(cards))  # was 8 entries, each duplicated


def test_the_hero_is_unaffected(stud_hand) -> None:
    cards = stud_hand.join_holecards("edinapoker", asList=True)

    assert cards == ["Kd", "6h", "Ah", "Kc", "2s", "3h", "2h"]


def test_a_boardless_game_still_builds_its_pots(stud_hand) -> None:
    """Stud deals no community cards, but its pots must still be assembled.

    assembleHandsPots iterates the boards returned by getBoardsList, which is
    empty for stud and draw. The loop therefore ran zero times: no HandsPots row
    was written and, worse, the rake had just been zeroed a few lines above and
    stayed there, so the hand no longer balanced. A boardless game has exactly
    one board -- an empty one.
    """
    stud_hand.totalPot()
    stud_hand.playerIds = {p[1]: i + 1 for i, p in enumerate(stud_hand.players)}
    stud_hand.stats.getStats(stud_hand)
    players = stud_hand.stats.getHandsPlayers()

    assert stud_hand.stats.getBoardsList(stud_hand) == []  # no community cards
    assert players["Montlebon"]["rake"] == 6  # the rake survives, in cents
    total = sum(v["totalProfit"] for v in players.values()) + sum(v["rake"] for v in players.values())
    assert total == 0, "money in must equal money out"
