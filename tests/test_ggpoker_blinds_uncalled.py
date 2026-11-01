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


# --- straddles ---------------------------------------------------------------
#
# GGPoker restates a straddler's running total on every line rather than the
# increment, and prints their blind alongside it. Charging both, and every rung
# of a re-straddle ladder, made those players pay several times over.


def _hand_from_text(text: str):
    import tempfile
    from pathlib import Path as _P

    tmp = _P(tempfile.mkdtemp()) / "hand.txt"
    tmp.write_text(text, encoding="utf-8")
    return GGPoker(config=Config(), in_path=str(tmp), autostart=True).getProcessedHands()[0]


_STRADDLE_HAND = """Poker Hand #OM313718456: PLO ($0.01/$0.02) - 2022/07/10 21:30:00
Table 'PLOWhite1' 6-max Seat #5 is the button
Seat 1: sb_str ($10 in chips)
Seat 2: bb_p ($10 in chips)
Seat 3: caller ($10 in chips)
sb_str: posts small blind $0.01
bb_p: posts big blind $0.02
sb_str: straddle $0.04
sb_str: straddle $0.08
sb_str: straddle $0.16
*** HOLE CARDS ***
Dealt to sb_str [7s Jd Qs Qh]
caller: folds
bb_p: calls $0.14
*** FLOP *** [Tc 9h 3h]
bb_p: checks
sb_str: checks
*** TURN *** [Tc 9h 3h] [4d]
bb_p: checks
sb_str: checks
*** RIVER *** [Tc 9h 3h 4d] [6s]
bb_p: checks
sb_str: checks
*** SHOWDOWN ***
sb_str collected $0.31 from pot
*** SUMMARY ***
Total pot $0.32 | Rake $0.01 | Jackpot $0 | Bingo $0
Board [Tc 9h 3h 4d 6s]
"""


def test_restraddle_counts_only_the_final_total() -> None:
    # $0.04 -> $0.08 -> $0.16 by one seat: the ladder is not cumulative.
    hand = _hand_from_text(_STRADDLE_HAND)

    assert hand.pot.committed["sb_str"] == Decimal("0.16")


def test_a_straddler_is_not_charged_their_blind_twice(parsed_hands=None) -> None:
    # sb_str posts the small blind and then straddles: the straddle is the total.
    hand = _hand_from_text(_STRADDLE_HAND)
    small_blinds = [a for a in hand.actions["BLINDSANTES"] if a[1] == "small blind"]

    assert small_blinds == [], "the straddle already covers the straddler's blind"


def test_straddled_hand_conserves_money() -> None:
    hand = _hand_from_text(_STRADDLE_HAND)
    hand.totalPot()
    paid = sum(hand.pot.committed.values()) + sum(hand.pot.common.values())
    out = sum(hand.collectees.values()) + Decimal(str(hand.rake or 0))

    assert paid == out
