"""Raise first in counts only a raise into an unopened pot (#796).

raisedFirstIn used to be set for the first raise of the hand, after limpers too,
while raiseFirstInChance only counts unopened pots. HudCache sums cannot take the
intersection, so every RFI (per position, rfi_total, the reports, gp_2x/gp_os)
was inflated by the isolation raises.
"""

from __future__ import annotations

from fpdb_3_legacy import Stats
from fpdb_3_legacy.DerivedStats import DerivedStats
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

HEADER = """PokerStars Hand #{number}:  Hold'em No Limit ($0.05/$0.10 USD) - 2024/01/01 12:00:00 ET
Table 'TestRFI' 6-max Seat #1 is the button
Seat 1: alice ($10 in chips)
Seat 2: bob ($10 in chips)
Seat 3: carol ($10 in chips)
Seat 4: dave ($10 in chips)
bob: posts small blind $0.05
carol: posts big blind $0.10
*** HOLE CARDS ***
"""

SUMMARY = """*** SUMMARY ***
Total pot $0.45 | Rake $0


"""

UNOPENED = (
    HEADER.format(number=100000000796)
    + """dave: raises $0.20 to $0.30
alice: folds
bob: folds
carol: folds
Uncalled bet ($0.20) returned to dave
dave collected $0.25 from pot
"""
    + SUMMARY
)

AFTER_A_LIMP = (
    HEADER.format(number=100000000797)
    + """dave: calls $0.10
alice: raises $0.30 to $0.40
bob: folds
carol: folds
dave: folds
Uncalled bet ($0.30) returned to alice
alice collected $0.35 from pot
"""
    + SUMMARY
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
    stats = DerivedStats()
    stats.getStats(parser.processHand(parser.allHandsAsList()[0]))
    return stats.getHandsPlayers()


def test_a_raise_into_an_unopened_pot_is_raise_first_in() -> None:
    dave = _hands_players(UNOPENED)["dave"]
    assert dave["raiseFirstInChance"]
    assert dave["raisedFirstIn"]


def test_a_raise_after_a_limper_is_not_raise_first_in() -> None:
    players = _hands_players(AFTER_A_LIMP)
    assert players["dave"]["raiseFirstInChance"]  # first to act, into an unopened pot
    assert not players["dave"]["raisedFirstIn"]  # and limped
    assert not players["alice"]["raiseFirstInChance"]  # the pot was open when alice acted
    assert not players["alice"]["raisedFirstIn"]  # so her isolation raise is no RFI
    assert players["alice"]["street0Aggr"]  # though it is still a preflop raise


def test_gp_opens_never_exceed_their_opportunities() -> None:
    for text in (UNOPENED, AFTER_A_LIMP):
        for row in _hands_players(text).values():
            assert row.get("cnt_gp_2x", 0) + row.get("cnt_gp_os", 0) <= row.get("cnt_gp_open_opp", 0)


def test_rfi_total_reads_the_raise_first_in_counters() -> None:
    result = Stats.rfi_total({1: {"rfi_0": 3, "rfi_opp_0": 12, "pfr": 9, "pfr_opp": 20}}, 1)
    assert result[1] == "25.0"
    assert result[4] == "(3/12)"
