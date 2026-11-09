"""Non-regression: SwC text histories keep "stands pat" and "discards" actions.

re_Action already matched `` stands pat`` and `` discards``, but readAction had
no branch for them, so both fell into the "Unimplemented" debug path and were
dropped from the imported hand -- the draw-round record was missing from the
text import (the native tap decodes them separately via the dealer's
draw messages, parse_native_dealer_draw). Other rooms' parsers call
Hand.addStandsPat / addDiscard; SwC now does too.
"""

from __future__ import annotations

from pathlib import Path

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.SealsWithClubsToFpdb import SealsWithClubs

DRAW_HAND = """SwCPoker Hand #305160001:  Hold'em No Limit (0.02/0.04) - 2026/11/08 19:00:00 UTC
Table 'No-Rake Micro Stakes NLHE #1'(299672900) 6-max (Real Money) Seat #1 is the button
Seat 1: Player0 (10 in chips)
Seat 2: Hero (10 in chips)
Player0: posts small blind 0.02
Hero: posts big blind 0.04
*** HOLE CARDS ***
Dealt to Hero [2h 5d 8s 9c Kd]
Player0: raises 0.04 to 0.08
Hero: calls 0.08
*** DRAW ONE ***
Player0: discards 1
Hero: stands pat
*** DRAW TWO ***
Player0: stands pat
Hero: discards 2
*** DRAW THREE ***
Player0: checks
Hero: bets 0.08
Player0: folds
Uncalled bet (0.08) returned to Hero
*** SHOW DOWN ***
Hero: doesn't show hand
Hero collected 0.16 from pot
*** SUMMARY ***
Total pot 0.16 | Rake 0
Seat 1: Player0 folded on the River
Seat 2: Hero (button) collected (0.16)
"""


def _parse(tmp_path: Path, text: str):
    path = tmp_path / "swc_draw.txt"
    path.write_text(text, encoding="utf-8")
    hhc = SealsWithClubs(config=Config(), in_path=str(path), autostart=True)
    assert hhc.numErrors == 0, hhc.parsing_issues
    hands = hhc.getProcessedHands()
    assert len(hands) == 1
    return hands[0]


def test_stands_pat_and_discards_are_recorded(tmp_path: Path) -> None:
    hand = _parse(tmp_path, DRAW_HAND)
    # The draw streets are not FLOP/TURN/RIVER, so the modern marker regex
    # leaves everything in PREFLOP; what matters is that the actions survive.
    preflop = hand.actions["PREFLOP"]
    assert any(a[0] == "Player0" and a[1] == "discards" and a[2] == 1 for a in preflop)
    assert any(a[0] == "Hero" and a[1] == "stands pat" for a in preflop)
    assert any(a[0] == "Player0" and a[1] == "stands pat" for a in preflop)
    assert any(a[0] == "Hero" and a[1] == "discards" and a[2] == 2 for a in preflop)
    # No action was dropped as "Unimplemented".
    atypes = {a[1] for a in preflop}
    assert "stands pat" in atypes
    assert "discards" in atypes


def test_holdem_hand_has_no_stand_pat(tmp_path: Path) -> None:
    """Ordinary hands are unchanged: no stand-pat/discards actions appear."""
    text = DRAW_HAND.replace("Player0: discards 1\nHero: stands pat\n", "").replace(
        "Player0: stands pat\nHero: discards 2\n", ""
    )
    hand = _parse(tmp_path, text)
    assert not any(a[1] in ("stands pat", "discards") for a in hand.actions["PREFLOP"])
