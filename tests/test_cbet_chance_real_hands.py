"""C-bet chances on parsed PokerStars hands (issue #791).

The last preflop raiser used to get a c-bet opportunity on every postflop
street, even when the hand was won preflop and no flop was dealt.
"""

from __future__ import annotations

from fpdb_3_legacy.DerivedStats import DerivedStats
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

HEADER = """PokerStars Hand #{number}:  Hold'em No Limit ($0.05/$0.10 USD) - 2024/01/01 12:00:00 ET
Table 'TestCB' 6-max Seat #3 is the button
Seat 1: alice ($10 in chips)
Seat 2: bob ($10 in chips)
Seat 3: carol ($10 in chips)
alice: posts small blind $0.05
bob: posts big blind $0.10
*** HOLE CARDS ***
"""

WON_PREFLOP = (
    HEADER.format(number=100000000791)
    + """carol: raises $0.20 to $0.30
alice: folds
bob: folds
Uncalled bet ($0.20) returned to carol
carol collected $0.25 from pot
*** SUMMARY ***
Total pot $0.25 | Rake $0
Seat 1: alice (small blind) folded before Flop
Seat 2: bob (big blind) folded before Flop
Seat 3: carol (button) collected ($0.25)


"""
)

WON_ON_FLOP = (
    HEADER.format(number=100000000792)
    + """carol: raises $0.20 to $0.30
alice: folds
bob: calls $0.20
*** FLOP *** [2c 7d Kh]
bob: checks
carol: bets $0.40
bob: folds
Uncalled bet ($0.40) returned to carol
carol collected $0.65 from pot
*** SUMMARY ***
Total pot $0.65 | Rake $0
Board [2c 7d Kh]
Seat 1: alice (small blind) folded before Flop
Seat 2: bob (big blind) folded on the Flop
Seat 3: carol (button) collected ($0.65)


"""
)


class _Config:
    def get_import_parameters(self) -> dict:
        return {
            "saveActions": True,
            "callFpdbHud": False,
            "cacheSessions": False,
            "publicDB": False,
            "importFilters": [],
            "handCount": 0,
            "fastFold": False,
            "ringFilter": True,
            "tourneyFilter": True,
        }

    def get_site_id(self, _sitename: str) -> int:
        return 32


def _hands_players(text: str) -> dict:
    parser = PokerStars(config=_Config())

    def read_file() -> bool:
        parser.obs = text
        parser.index = 0
        return True

    parser.readFile = read_file
    hand = parser.processHand(parser.allHandsAsList()[0])
    stats = DerivedStats()
    stats.getStats(hand)
    return stats.getHandsPlayers()


def test_hand_won_preflop_gives_no_cbet_chance() -> None:
    carol = _hands_players(WON_PREFLOP)["carol"]
    assert not carol["street1CBChance"]
    assert not carol["street2CBChance"]
    assert not carol["street3CBChance"]


def test_hand_won_on_the_flop_gives_a_flop_chance_only() -> None:
    players = _hands_players(WON_ON_FLOP)
    carol = players["carol"]
    assert carol["street1CBChance"]
    assert carol["street1CBDone"]
    assert not carol["street2CBChance"]
    assert not carol["street3CBChance"]
    assert players["bob"]["foldToStreet1CBChance"]
    assert players["bob"]["foldToStreet1CBDone"]
