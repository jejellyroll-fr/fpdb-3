#!/usr/bin/env python3
from __future__ import annotations
"""Regression test for the draw-game starting-hand bug.

For draw games the hero's *original* dealt cards (the DEAL street) must be
preserved even when the hero reveals their hand at showdown. A prior bug had
``DrawHand.__init__`` call ``readShowdownActions`` *before* ``readAction``, so
``addShownCards`` could not resolve the last draw street and fell back to
``DEAL`` — overwriting the starting hand with the showdown holding. The hand
replayer (and the stored card1..card20 columns) then showed an incomplete
starting hand (e.g. only 2 of 5 cards).

See Hand.DrawHand.__init__ / Hand.addShownCards.
"""

import logging
import os
import sys

logging.disable(logging.CRITICAL)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock GUI deps only when PySide6 is unavailable (mirrors other parser tests).
try:
    import PySide6  # noqa: F401
except ImportError:
    from unittest.mock import MagicMock

    for _m in ("PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"):
        sys.modules[_m] = MagicMock()

import Configuration
import Hand as LegacyHand
from PokerStarsToFpdb import PokerStars


FIVE_CARD_DRAW_HH = """PokerStars Hand #35839231732:  5 Card Draw Limit ($0.05/$0.10 USD) - 2009/11/25 19:17:00 ET
Table 'Test' 6-max Seat #1 is the button
Seat 1: francois712 ($0.47 in chips)
Seat 2: Hero ($2.84 in chips)
Seat 3: Jana50 ($3.90 in chips)
Hero: posts small blind $0.05
Jana50: posts big blind $0.10
*** DEALING HANDS ***
Dealt to Hero [Ac Jd 5h 8s Kc]
francois712: folds
Hero: calls $0.05
Jana50: checks
Hero: discards 2
Jana50: stands pat
*** DRAW ***
Dealt to Hero [Ac Jd Kc] [2h 7s]
Hero: bets $0.10
Jana50: calls $0.10
*** SHOW DOWN ***
Hero: shows [Ac Jd Kc 2h 7s] (a pair)
Jana50: mucks hand
Hero collected $0.38 from pot
*** SUMMARY ***
Total pot $0.40 | Rake $0.02
"""


# A real PokerStars 5-Card Draw hand WITHOUT a "*** DRAW ***" separator: the
# post-draw "Dealt to Hero [kept] [drawn]" line is inline in the DEALING HANDS
# section, and the hand does NOT reach showdown. The post-draw line used to
# overwrite the initial deal on the DEAL street, leaving only the 2 drawn cards.
FIVE_CARD_DRAW_NO_SEPARATOR_HH = """PokerStars Game #35839231732:  5 Card Draw Limit ($0.10/$0.20 USD) - 2009/11/25 14:17:57 ET
Table 'Laodica IV' 6-max Seat #3 is the button
Seat 1: francois 712 ($0.47 in chips)
Seat 2: vatt110 ($2.38 in chips)
Seat 3: dantho ($2.82 in chips)
Seat 4: Hero ($2.94 in chips)
Seat 5: Jana50 ($4 in chips)
Seat 6: Postman15 ($1.86 in chips)
Hero: posts small blind $0.05
Jana50: posts big blind $0.10
*** DEALING HANDS ***
Dealt to Hero [Ad 2c Ts 4s Tc]
Postman15: folds
francois 712: folds
vatt110: folds
dantho: folds
Hero: calls $0.05
Jana50: checks
Hero: discards 2 cards [2c 4s]
Dealt to Hero [Ad Ts Tc] [Ac Jc]
Jana50: discards 1 card
Hero: bets $0.20
Jana50: folds
Uncalled bet ($0.20) returned to Hero
Hero collected $0.19 from pot
*** SUMMARY ***
Total pot $0.20 | Rake $0.01
Seat 4: Hero (small blind) collected ($0.19)
"""


# Badugi is a 4-card game. join_holecards(street=...) used to slice fixed 5-slot
# blocks, exposing a trailing "0x" placeholder (rendered as a 5th card back) in
# the hand viewer.
BADUGI_HH = """PokerStars Hand #99999999999:  Badugi Limit ($0.10/$0.25 USD) - 2010/09/05 14:33:00 ET
Table 'Test' 6-max Seat #3 is the button
Seat 1: villain1 ($10 in chips)
Seat 2: Hero ($10 in chips)
Seat 3: villain2 ($10 in chips)
Hero: posts small blind $0.10
villain2: posts big blind $0.25
*** DEALING HANDS ***
Dealt to Hero [3h Tc Kc Ad]
villain1: folds
Hero: calls $0.15
villain2: checks
*** FIRST DRAW ***
Hero: discards 1 card [Kc]
Dealt to Hero [3h Tc Ad] [2s]
villain2: stands pat
Hero: bets $0.10
villain2: folds
Uncalled bet ($0.10) returned to Hero
Hero collected $0.55 from pot
*** SUMMARY ***
Total pot $0.60 | Rake $0.05
"""


def _build_hand(hand_text=FIVE_CARD_DRAW_HH, category="fivedraw"):
    config = Configuration.Config()
    hhc = PokerStars(config, in_path="-", sitename="PokerStars", autostart=False)
    gametype = {
        "type": "ring",
        "base": "draw",
        "category": category,
        "limitType": "fl",
        "sb": "0.05",
        "bb": "0.10",
        "currency": "USD",
        "mix": "none",
    }
    return LegacyHand.DrawHand(config, hhc, "PokerStars", gametype, hand_text)


def test_badugi_starting_hand_has_four_cards():
    """Badugi DEAL street must expose exactly 4 cards (no trailing '0x' back)."""
    hand = _build_hand(BADUGI_HH, category="badugi")

    deal = hand.join_holecards("Hero", asList=True, street="DEAL")
    assert deal == ["3h", "Tc", "Kc", "Ad"], deal
    assert len(deal) == 4
    assert "0x" not in deal


def test_deal_street_keeps_deal_when_draw_has_no_separator():
    """Inline draw line (no '*** DRAW ***') must not overwrite the starting hand."""
    hand = _build_hand(FIVE_CARD_DRAW_NO_SEPARATOR_HH)

    deal = hand.join_holecards("Hero", asList=True, street="DEAL")
    assert deal == ["Ad", "2c", "Ts", "4s", "Tc"], (
        f"Starting hand overwritten by drawn cards: {deal}"
    )
    assert "0x" not in deal

    # The drawn cards must still be recorded on the draw street.
    drawone = hand.join_holecards("Hero", asList=True, street="DRAWONE")
    assert set(drawone) == {"Ad", "Ts", "Tc", "Ac", "Jc"}, drawone


def test_draw_round_is_split_into_its_own_street():
    """Without a '*** DRAW ***' marker, the draw round must still become DRAWONE.

    The discard and the post-draw betting belong to DRAWONE (not DEAL); otherwise
    the replayer never transitions past DEAL and the hand is not updated after the
    draw.
    """
    hand = _build_hand(FIVE_CARD_DRAW_NO_SEPARATOR_HH)

    deal_actions = [a[1] for a in hand.actions.get("DEAL", [])]
    drawone_actions = [a[1] for a in hand.actions.get("DRAWONE", [])]

    # First betting round stays on DEAL; no draw actions leak into it.
    assert "discards" not in deal_actions
    # The draw + second betting round live on DRAWONE.
    assert "discards" in drawone_actions
    assert "bets" in drawone_actions

    # The hero's discard on DRAWONE carries the discarded cards (for the animation).
    hero_discard = next(
        a for a in hand.actions["DRAWONE"] if a[0] == hand.hero and a[1] == "discards"
    )
    assert len(hero_discard) > 3 and hero_discard[3] == "2c 4s", hero_discard


def test_deal_street_keeps_original_starting_hand():
    """The DEAL street must hold the 5 originally dealt cards, not the showdown hand."""
    hand = _build_hand()

    deal = hand.join_holecards("Hero", asList=True, street="DEAL")
    assert deal == ["Ac", "Jd", "5h", "8s", "Kc"], (
        f"Starting hand corrupted by showdown cards: {deal}"
    )
    # No hidden ('0x') placeholders should remain on the starting hand.
    assert "0x" not in deal


def test_final_draw_street_holds_showdown_hand():
    """The post-draw street holds the final 5-card holding shown at showdown."""
    hand = _build_hand()

    drawone = hand.join_holecards("Hero", asList=True, street="DRAWONE")
    assert set(drawone) == {"Ac", "Jd", "Kc", "2h", "7s"}, drawone


def test_full_card_storage_is_complete():
    """card1..card5 (DEAL) and card6..card10 (DRAWONE) must both be fully populated."""
    hand = _build_hand()

    all20 = hand.join_holecards("Hero", asList=True)
    assert all20[0:5] == ["Ac", "Jd", "5h", "8s", "Kc"]      # DEAL
    assert set(all20[5:10]) == {"Ac", "Jd", "Kc", "2h", "7s"}  # DRAWONE
    assert "0x" not in all20[0:10]


if __name__ == "__main__":
    test_deal_street_keeps_original_starting_hand()
    test_deal_street_keeps_deal_when_draw_has_no_separator()
    test_draw_round_is_split_into_its_own_street()
    test_badugi_starting_hand_has_four_cards()
    test_final_draw_street_holds_showdown_hand()
    test_full_card_storage_is_complete()
    print("✅ All draw starting-hand regression tests passed")
