"""A hand run twice labels its shared streets FIRST, and the betting is there.

GGPoker writes "*** FIRST FLOP ***" for the single, shared flop of a hand that
will be run twice. markStreets captured it as FLOP1 while FLOP kept at most the
board, and readAction only ever visits FLOP/TURN/RIVER -- so every post-flop bet
was dropped. Players were recorded as having paid their pre-flop chips and
nothing more: hand 537421857 showed 0.71 put in for a 9.71 pot.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.GGPokerToFpdb import GGPoker

HAND_FILE = Path(
    "/Users/jde/Documents/github/fpdb-new/SortedHands/GGpoker/2026/cg/plo-session/"
    "GG20260118-2024 - PLOYellow8 - 0.02 - 0.05 - 7max.txt",
)

pytestmark = pytest.mark.skipif(not HAND_FILE.exists(), reason="local GGPoker history not present")


@pytest.fixture(scope="module")
def run_twice_hand():
    hands = GGPoker(config=Config(), in_path=str(HAND_FILE), autostart=True).getProcessedHands()
    hand = next(h for h in hands if str(h.handid) == "537421857")
    hand.totalPot()
    return hand


def test_the_shared_streets_carry_their_betting(run_twice_hand) -> None:
    assert len(run_twice_hand.actions["FLOP"]) == 6  # was 0
    assert len(run_twice_hand.actions["TURN"]) == 2  # was 0


def test_players_are_charged_what_they_put_in(run_twice_hand) -> None:
    committed = run_twice_hand.pot.committed

    assert committed["Hero"] == Decimal("4.72")  # was 0.22, the pre-flop call alone
    assert committed["fcc56e17"] == Decimal("4.72")


def test_the_hand_balances(run_twice_hand) -> None:
    paid = sum(run_twice_hand.pot.committed.values()) + sum(run_twice_hand.pot.common.values())
    out = sum(run_twice_hand.collectees.values()) + Decimal(str(run_twice_hand.rake or 0))

    assert paid == Decimal("9.71")  # the pot the summary states
    assert paid == out
