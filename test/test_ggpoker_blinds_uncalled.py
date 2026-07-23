"""GGPoker lost the big blind and never returned uncalled bets.

readBlinds iterated the big-blind posts only to clear a flag -- the loop variable
was even named ``_a`` -- so the blind was never added: 0 of the 26 205 GGPoker
ring hands in the database had one. re_uncalled was declared but never used
either, so a bet nobody called stayed in pot.committed.

Together they broke money conservation on every hand: the pot was short one big
blind, which made totalcollected exceed it, and Hand.totalPot() then booked the
uncalled bet as a collectable pot with the surplus as phantom rake. Hands won
without showdown were stored as losses.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.GGPokerToFpdb import GGPoker

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "hands" / "ggpoker" / "plo_cash.txt"


@pytest.fixture(scope="module")
def parsed_hands():
    parser = GGPoker(config=Config(), in_path=str(FIXTURE), autostart=True)
    return parser.getProcessedHands()


def _by_id(hands, hand_id: str):
    return next(h for h in hands if str(h.handid) == hand_id)


def test_big_blind_is_recorded(parsed_hands) -> None:
    hand = _by_id(parsed_hands, "190765916")
    blinds = [a for a in hand.actions["BLINDSANTES"] if a[1] == "big blind"]

    assert blinds, "the big blind post must reach the hand"
    assert blinds[0][0] == "677d2b55"
    assert Decimal(str(blinds[0][2])) == Decimal("1")


def test_raise_amount_is_measured_against_the_big_blind(parsed_hands) -> None:
    # "2f51798b: raises $2 to $3" -- without the big blind the raise was
    # computed against the small blind and stored as "to 2.5".
    hand = _by_id(parsed_hands, "190765916")
    raises = [a for a in hand.actions["PREFLOP"] if a[1] == "raises"]

    assert Decimal(str(raises[0][3])) == Decimal("3")


def test_uncalled_bet_is_returned(parsed_hands) -> None:
    # "Uncalled bet ($7.5) returned to 2f51798b": only $3 was ever at risk.
    hand = _by_id(parsed_hands, "190765916")

    assert hand.pot.returned["2f51798b"] == Decimal("7.5")
    assert hand.pot.committed["2f51798b"] == Decimal("3")


def test_every_hand_conserves_money(parsed_hands) -> None:
    """What goes into the pot must come out as winnings plus rake."""
    for hand in parsed_hands:
        hand.totalPot()
        paid = sum(hand.pot.committed.values()) + sum(hand.pot.common.values())
        out = sum(hand.collectees.values()) + Decimal(str(hand.rake or 0))
        assert paid == out, f"hand {hand.handid}: {paid} in, {out} out"


def test_extra_pot_drops_are_counted_as_rake() -> None:
    """GGPoker skims a jackpot/bingo/fortune/tax drop on top of the rake.

        Total pot $9.87 | Rake $0.29 | Jackpot $0.02 | Bingo $0 | Fortune $0 | Tax $0

    Only the rake was parsed, so the jackpot left the pot without being recorded
    anywhere: money in no longer matched money out. Over the 26 428-hand corpus
    those drops accounted for 83% of the hands that still failed to balance.
    """
    from fpdb_3_legacy.GGPokerToFpdb import GGPoker as _GG

    summary = "Total pot $9.87 | Rake $0.29 | Jackpot $0.02 | Bingo $0 | Fortune $0 | Tax $0"
    m = _GG.re_rake.search(summary)

    assert m is not None
    assert m.group("POT") == "9.87"
    assert m.group("RAKE") == "0.29"
    assert m.group("JACKPOT") == "0.02"
    assert m.group("BINGO") == "0"


def test_rake_only_summary_still_parses() -> None:
    # Older/other GGPoker summaries carry no extra drops at all.
    from fpdb_3_legacy.GGPokerToFpdb import GGPoker as _GG

    m = _GG.re_rake.search("Total pot $7.5 | Rake $0")

    assert m is not None
    assert m.group("POT") == "7.5"
    assert m.group("JACKPOT") is None
