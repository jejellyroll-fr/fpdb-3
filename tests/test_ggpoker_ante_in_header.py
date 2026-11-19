"""GGPoker tournament headers that carry the ante inside the stakes.

Newer GG files write the level as ``Level5(100/200(20))``: the ante sits in its
own parentheses after the big blind. re_game_info expected the closing paren
right after the big blind, so every such hand failed with
"determineGameType not found" and the whole file landed in "failed files".
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.GGPokerToFpdb import GGPoker

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "hands" / "ggpoker" / "mtt_ante_in_header.txt"

NEW_HEADER = (
    "Poker Hand #TM6622828917: Tournament #323740070, $3 Step to $215 Zodiac Mystery Bounty King, "
    "$3M GTD Hold'em No Limit - Level5(100/200(20)) - 2026/11/04 13:22:01"
)


def test_the_header_with_an_ante_matches():
    m = GGPoker.re_game_info.search(NEW_HEADER)

    assert m is not None
    assert m.group("TOURNO") == "323740070"
    assert m.group("TOURNAME") == "$3 Step to $215 Zodiac Mystery Bounty King, $3M GTD"
    assert (m.group("SB"), m.group("BB"), m.group("ANTE")) == ("100", "200", "20")
    assert m.group("DATETIME") == "2026/11/04 13:22:01"


@pytest.mark.parametrize(
    "header",
    [
        "Poker Hand #TM247771977: Tournament #5259595, Daily Special $250 Hold'em No Limit - Level2 (60/120) - "
        "2020/06/02 19:17:33",
        "Poker Hand #TM599808286: Tournament #25313424, L-03: $52.50 Bounty Hunters Main Event Hold'em No Limit "
        "- Level1(100/200) - 2021/04/04 16:06:27",
    ],
)
def test_headers_without_an_ante_still_match(header):
    m = GGPoker.re_game_info.search(header)

    assert m is not None
    assert m.group("ANTE") is None


def test_a_hand_with_the_new_header_is_imported():
    parser = GGPoker(config=Config(), in_path=str(FIXTURE), autostart=True)
    hands = parser.getProcessedHands()

    assert len(hands) == 1
    hand = hands[0]
    hand.totalPot()
    assert hand.tourNo == "25313424"
    assert hand.gametype["type"] == "tour"
    assert hand.gametype["category"] == "holdem"
    assert hand.gametype["limitType"] == "nl"
    assert (hand.gametype["sb"], hand.gametype["bb"]) == ("100", "200")
    assert hand.totalpot == Decimal("3350")


PLO5_FIXTURE = FIXTURE.parent / "plo5_mtt_omaha5.txt"


@pytest.mark.parametrize(("word", "category"), [("Omaha5", "5_omahahi"), ("Omaha6", "6_omahahi")])
def test_the_omaha5_and_omaha6_game_names_match(word, category):
    """GG names five- and six-card Omaha tournaments "Omaha5"/"Omaha6", not "PLO-5"."""
    header = (
        f"Poker Hand #TM1: Tournament #2, PLO-5 Bounty $3.20 {word} Pot Limit - Level6(150/300) - 2026/11/10 19:00:00"
    )

    m = GGPoker.re_game_info.search(header)

    assert m is not None
    assert m.group("GAME") == word
    assert GGPoker.games[word] == ("hold", category)


def test_a_five_card_omaha_tournament_is_imported():
    parser = GGPoker(config=Config(), in_path=str(PLO5_FIXTURE), autostart=True)
    hands = parser.getProcessedHands()

    assert len(hands) == 2
    assert parser.numErrors == 0
    for hand in hands:
        assert hand.gametype["category"] == "5_omahahi"
        assert hand.gametype["limitType"] == "pl"
        assert len(hand.holecards["PREFLOP"]["Hero"][1]) == 5
