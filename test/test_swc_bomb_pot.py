"""SwC bomb pots, single and double board.

A bomb pot takes an ante from everyone and deals straight to the flop. On a
"Double Board" table two runouts are dealt and the pot is split between them,
and the client names each board in its street header. The single-board street
regexes match none of those headers, so PREFLOP used to swallow the whole hand:
no board, no postflop action, no showdown -- the hand imported as a stub.

The two-board samples here are synthetic: they follow the header spellings this
codebase already parses for other rooms (PokerStarsToFpdb / GGPokerToFpdb use
FIRST/SECOND, WinningToFpdb also accepts a trailing run number), and have not
been checked against a captured SwC double-board hand. The single-board bomb pot
below is taken verbatim from a real SwC hand history.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.DerivedStats import DerivedStats
from fpdb_3_legacy.SealsWithClubsToFpdb import SealsWithClubs

# A real bomb pot: antes only, no blind, action opens on the flop.
SINGLE_BOARD_BOMB_POT = """SwCPoker Hand #301461450:  Omaha Pot Limit (0.04/0.08) - 2026/09/08 9:03:10 UTC
Table 'No-Rake Micro Stakes PLO Double Board Bomb Pots #1'(299672838) 8-max (Real Money) Seat #1 is the button
Seat 1: Folded74Dice (1.92 in chips)
Seat 3: ThirstyMan (6.12 in chips)
Seat 5: edinapoker (12.38 in chips)
Folded74Dice: posts the ante 0.12
ThirstyMan: posts the ante 0.12
edinapoker: posts the ante 0.12
*** HOLE CARDS ***
Dealt to edinapoker [2h Jc Ac 4c]
*** FLOP *** [5d 9d 3h]
ThirstyMan: checks
edinapoker: checks
Folded74Dice: bets 0.24
ThirstyMan: folds
edinapoker: folds
Uncalled bet (0.24) returned to Folded74Dice
*** SHOW DOWN ***
Folded74Dice: doesn't show hand
Folded74Dice collected 0.36 from pot
*** SUMMARY ***
Total pot 0.36 | Rake 0
Board [5d 9d 3h]
Seat 1: Folded74Dice (button) collected (0.36)
Seat 3: ThirstyMan folded on the Flop
Seat 5: edinapoker folded on the Flop
"""

# A real hand with blinds and no ante, to pin down that "has antes" alone is not
# what marks a bomb pot.
ORDINARY_BLINDS_HAND = """SwCPoker Hand #301457958:  Omaha Pot Limit (0.02/0.04) - 2026/09/08 8:52:04 UTC
Table 'No-Rake Micro Stakes PLO Double Board Bomb Pots #1'(299672838) 8-max (Real Money) Seat #5 is the button
Seat 1: Folded74Dice (1.20 in chips)
Seat 5: edinapoker (4.02 in chips)
edinapoker: posts small blind 0.02
Folded74Dice: posts big blind 0.04
*** HOLE CARDS ***
Dealt to edinapoker [As 2h 7s Ah]
edinapoker: raises 0.10 to 0.12
Folded74Dice: folds
Uncalled bet (0.08) returned to edinapoker
*** SHOW DOWN ***
edinapoker: doesn't show hand
edinapoker collected 0.08 from pot
*** SUMMARY ***
Total pot 0.08 | Rake 0
Seat 1: Folded74Dice (big blind) folded before Flop
Seat 5: edinapoker (button) (small blind) collected (0.08)
"""

DOUBLE_BOARD_FIRST_SECOND = """SwCPoker Hand #301461500:  Omaha Pot Limit (0.02/0.04) - 2026/09/08 9:20:00 UTC
Table 'No-Rake Micro Stakes PLO Double Board Bomb Pots #1'(299672838) 8-max (Real Money) Seat #1 is the button
Seat 1: Folded74Dice (3 in chips)
Seat 5: edinapoker (14 in chips)
Folded74Dice: posts the ante 0.12
edinapoker: posts the ante 0.12
*** HOLE CARDS ***
Dealt to edinapoker [5s 5h 5c Jd]
*** FIRST FLOP *** [2d Td 8d]
*** SECOND FLOP *** [7c 4h Ks]
edinapoker: checks
Folded74Dice: checks
*** FIRST TURN *** [2d Td 8d] [Ts]
*** SECOND TURN *** [7c 4h Ks] [9h]
edinapoker: bets 0.12
Folded74Dice: calls 0.12
*** FIRST RIVER *** [2d Td 8d Ts] [Kd]
*** SECOND RIVER *** [7c 4h Ks 9h] [2c]
edinapoker: checks
Folded74Dice: checks
*** SHOW DOWN ***
edinapoker: shows [5s 5h 5c Jd] (two pair, Tens and Fives)
Folded74Dice: shows [5d 7s Ah 9s] (a pair of Nines)
edinapoker collected 0.24 from pot
Folded74Dice collected 0.24 from pot
*** SUMMARY ***
Total pot 0.48 | Rake 0
Board [2d Td 8d Ts Kd]
Board [7c 4h Ks 9h 2c]
Seat 1: Folded74Dice (button) showed [5d 7s Ah 9s] and won (0.24) with a pair of Nines
Seat 5: edinapoker showed [5s 5h 5c Jd] and won (0.24) with two pair, Tens and Fives
"""

_NUMBERED = {
    "*** FIRST FLOP ***": "*** FLOP 1 ***",
    "*** SECOND FLOP ***": "*** FLOP 2 ***",
    "*** FIRST TURN ***": "*** TURN 1 ***",
    "*** SECOND TURN ***": "*** TURN 2 ***",
    "*** FIRST RIVER ***": "*** RIVER 1 ***",
    "*** SECOND RIVER ***": "*** RIVER 2 ***",
}


def _numbered(text: str) -> str:
    for first_second, numbered in _NUMBERED.items():
        text = text.replace(first_second, numbered)
    return text


def _parse(tmp_path: Path, hand_text: str):
    path = tmp_path / "swc.txt"
    path.write_text(hand_text, encoding="utf-8")
    hhc = SealsWithClubs(config=Config(), in_path=str(path), autostart=False)
    hhc.start()
    assert hhc.numErrors == 0, hhc.parsing_issues
    assert hhc.numPartial == 0, hhc.parsing_issues
    hands = hhc.getProcessedHands()
    assert len(hands) == 1
    return hands[0]


def test_ante_only_hand_is_flagged_as_a_bomb_pot(tmp_path: Path) -> None:
    hand = _parse(tmp_path, SINGLE_BOARD_BOMB_POT)
    # 3 x 0.12 of ante, in cents.
    assert hand.bombPot == 36
    assert hand.totalpot == hand.totalcollected


def test_blinds_hand_is_not_a_bomb_pot(tmp_path: Path) -> None:
    hand = _parse(tmp_path, ORDINARY_BLINDS_HAND)
    assert hand.bombPot == 0


def test_bomb_pot_ante_is_not_counted_twice(tmp_path: Path) -> None:
    """The antes are the pot; they must not also be added as room-seeded money."""
    hand = _parse(tmp_path, SINGLE_BOARD_BOMB_POT)
    assert getattr(hand.pot, "stp", 0) == 0
    assert hand.totalpot == Decimal("0.36")


@pytest.mark.parametrize("naming", ["first_second", "numbered"])
def test_double_board_yields_two_complete_boards(tmp_path: Path, naming: str) -> None:
    text = DOUBLE_BOARD_FIRST_SECOND if naming == "first_second" else _numbered(DOUBLE_BOARD_FIRST_SECOND)
    hand = _parse(tmp_path, text)

    assert hand.runItTimes == 2
    assert hand.board["FLOP"] == ["2d", "Td", "8d"]
    assert hand.board["TURN"] == ["Ts"]
    assert hand.board["RIVER"] == ["Kd"]
    assert hand.board["FLOP2"] == ["7c", "4h", "Ks"]
    assert hand.board["TURN2"] == ["9h"]
    assert hand.board["RIVER2"] == ["2c"]

    # Both runs reach the Boards table as full five-card boards.
    assert DerivedStats().getBoardsList(hand) == [
        ["2d", "Td", "8d", "Ts", "Kd"],
        ["7c", "4h", "Ks", "9h", "2c"],
    ]


@pytest.mark.parametrize("naming", ["first_second", "numbered"])
def test_double_board_bets_each_street_once(tmp_path: Path, naming: str) -> None:
    """One betting round per street, not one per board."""
    text = DOUBLE_BOARD_FIRST_SECOND if naming == "first_second" else _numbered(DOUBLE_BOARD_FIRST_SECOND)
    hand = _parse(tmp_path, text)

    assert [a[0] for a in hand.actions["FLOP"]] == ["edinapoker", "Folded74Dice"]
    assert [a[1] for a in hand.actions["TURN"]] == ["bets", "calls"]
    assert [a[0] for a in hand.actions["RIVER"]] == ["edinapoker", "Folded74Dice"]
    for extra in ("FLOP2", "TURN2", "RIVER2"):
        assert hand.actions.get(extra, []) == []

    assert hand.totalpot == hand.totalcollected


def test_double_board_bomb_pot_is_both_flagged_and_split(tmp_path: Path) -> None:
    """bombPot plus two boards is what tells a bomb pot from a run-it-twice."""
    hand = _parse(tmp_path, DOUBLE_BOARD_FIRST_SECOND)
    assert hand.bombPot == 24
    assert hand.runItTimes == 2


def test_single_board_hand_is_left_on_the_plain_streets(tmp_path: Path) -> None:
    """The double-board path must not engage for an ordinary hand."""
    hand = _parse(tmp_path, SINGLE_BOARD_BOMB_POT)
    assert hand.runItTimes == 0
    assert hand.board["FLOP"] == ["5d", "9d", "3h"]
    assert not hand.board.get("FLOP2")


# A real hand. Three 0.12 antes make 0.36; on the one board that was written,
# Folded74Dice's two pair beats edinapoker's pair outright -- yet the room paid
# 0.27 and 0.09. That resolves only as two boards of 0.18: the written one won
# outright, and a second, unwritten one chopped. The SwC text history drops the
# second board of a double board while its payouts still reflect both.
DOUBLE_BOARD_PAYOUT_ONE_BOARD_WRITTEN = """SwCPoker Hand #301461492:  Omaha Pot Limit (0.04/0.08) - 2026/09/08 9:18:14 UTC
Table 'No-Rake Micro Stakes PLO Double Board Bomb Pots #1'(299672838) 8-max (Real Money) Seat #1 is the button
Seat 1: Folded74Dice (3.22 in chips)
Seat 5: edinapoker (14.32 in chips)
Seat 6: Perombo (4 in chips)
Folded74Dice: posts the ante 0.12
edinapoker: posts the ante 0.12
Perombo: posts the ante 0.12
*** HOLE CARDS ***
Dealt to edinapoker [9h Td 5s 7d]
*** FLOP *** [3d 2h 9c]
edinapoker: checks
Folded74Dice: checks
*** TURN *** [3d 2h 9c] [6d]
edinapoker: checks
Folded74Dice: checks
*** RIVER *** [3d 2h 9c 6d] [Ah]
edinapoker: checks
Folded74Dice: checks
*** SHOW DOWN ***
edinapoker: shows [9h Td 5s 7d] (a pair of Nines)
Folded74Dice: shows [Th 4s 3c 9s] (two pair, Nines and Threes)
Folded74Dice collected 0.27 from pot
edinapoker collected 0.09 from pot
*** SUMMARY ***
Total pot 0.36 | Rake 0
Board [3d 2h 9c 6d Ah]
Seat 1: Folded74Dice (button) showed [Th 4s 3c 9s] and won (0.27) with two pair, Nines and Threes
Seat 5: edinapoker showed [9h Td 5s 7d] and won (0.09) with a pair of Nines
Seat 6: Perombo
"""


def test_unequal_bomb_pot_payout_reports_the_missing_board(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        hand = _parse(tmp_path, DOUBLE_BOARD_PAYOUT_ONE_BOARD_WRITTEN)

    assert hand.bombPot == 36
    # The money the room actually paid is kept as written; only the cards are lost.
    assert hand.collectees["Folded74Dice"] == Decimal("0.27")
    assert hand.collectees["edinapoker"] == Decimal("0.09")
    assert hand.totalpot == hand.totalcollected
    assert "the history omitted the second board" in caplog.text
    assert "301461492" in caplog.text


def test_no_second_board_is_claimed_for_the_missing_one(tmp_path: Path) -> None:
    """Better a board fpdb knows it is missing than board one stored twice."""
    hand = _parse(tmp_path, DOUBLE_BOARD_PAYOUT_ONE_BOARD_WRITTEN)
    assert hand.runItTimes == 0
    assert DerivedStats().getBoardsList(hand) == [["3d", "2h", "9c", "6d", "Ah"]]


def test_an_even_bomb_pot_chop_is_not_reported(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Equal payouts are an ordinary chop; two boards won outright look identical."""
    even = DOUBLE_BOARD_PAYOUT_ONE_BOARD_WRITTEN.replace(
        "Folded74Dice collected 0.27 from pot\nedinapoker collected 0.09 from pot",
        "Folded74Dice collected 0.18 from pot\nedinapoker collected 0.18 from pot",
    ).replace("and won (0.27)", "and won (0.18)").replace("and won (0.09)", "and won (0.18)")
    with caplog.at_level("WARNING"):
        _parse(tmp_path, even)
    assert "the history omitted the second board" not in caplog.text


def test_side_pot_payouts_are_not_reported(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An all-in explains unequal payouts without any second board."""
    all_in = DOUBLE_BOARD_PAYOUT_ONE_BOARD_WRITTEN.replace(
        "edinapoker: checks\nFolded74Dice: checks\n*** TURN ***",
        "edinapoker: bets 0.12 and is all-in\nFolded74Dice: calls 0.12\n*** TURN ***",
    )
    with caplog.at_level("WARNING"):
        _parse(tmp_path, all_in)
    assert "the history omitted the second board" not in caplog.text
