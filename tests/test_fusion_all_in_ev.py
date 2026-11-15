"""A real PokerStars Fusion preflop all-in, parsed and derived (#818).

Both players are all-in preflop with two hole cards each; the flop's and the
turn's hole cards are dealt afterwards and only appear in the showdown, listed
in deal order. The all-in EV must come from the two cards held at the time,
with poker-eval dealing the rest.
"""

from __future__ import annotations

import pytest

import fpdb_3_legacy.equity as equity_module
from fpdb_3_legacy import derived_stats_allin
from fpdb_3_legacy.import_prefetch import _PlaceholderIds

pytestmark = pytest.mark.skipif(equity_module.load_poker_eval() is None, reason="pypoker-eval is not installed")

FUSION_PREFLOP_ALLIN = """PokerStars Hand #251488712905:  Fusion Pot Limit (€0.01/€0.02 EUR) - 2024/07/14 20:38:43 CET [2024/07/14 14:38:43 ET]
Table 'Scania' 6-max Seat #5 is the button
Seat 1: Alice (€2.80 in chips)
Seat 2: Carol (€5.84 in chips)
Seat 4: Bob (€1.06 in chips)
Seat 5: Dave (€1.22 in chips)
Seat 6: Hero (€1.98 in chips)
Hero: posts small blind €0.01
Alice: posts big blind €0.02
Bob: posts small & big blinds €0.03
*** HOLE CARDS ***
Dealt to Hero [6h Qc]
Carol: calls €0.02
Bob: raises €0.07 to €0.09
Dave: folds
Hero: folds
Alice: raises €0.21 to €0.30
Carol: folds
Bob: raises €0.63 to €0.93
Alice: raises €1.87 to €2.80 and is all-in
Bob: calls €0.12 and is all-in
Uncalled bet (€1.75) returned to Alice
*** FLOP *** [4d Js 4c]
*** TURN *** [4d Js 4c] [9h]
*** RIVER *** [4d Js 4c 9h] [2s]
*** SHOW DOWN ***
Alice: shows [6d 3h 4s Ks] (three of a kind, Fours)
Bob: shows [7s 3s 5s Ad] (a pair of Fours)
Alice collected €2.01 from pot
*** SUMMARY ***
Total pot €2.14 | Rake €0.13
Board [4d Js 4c 9h 2s]
Seat 1: Alice (big blind) showed [6d 3h 4s Ks] and won (€2.01) with three of a kind, Fours
Seat 2: Carol folded before Flop
Seat 4: Bob showed [7s 3s 5s Ad] and lost with a pair of Fours
Seat 5: Dave (button) folded before Flop (didn't bet)
Seat 6: Hero (small blind) folded before Flop



"""


def _derive(tmp_path):
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

    path = tmp_path / "fusion.txt"
    path.write_text(FUSION_PREFLOP_ALLIN, encoding="utf-8")
    parser = PokerStars(config=Config(file="HUD_config.xml"), in_path=str(path), autostart=True)
    (hand,) = parser.getProcessedHands()
    hand.prepInsert(_PlaceholderIds())
    hand.assembleHand()
    return hand


def test_fusion_preflop_all_in_ev_uses_the_two_cards_held(tmp_path, monkeypatch) -> None:
    calls: list[tuple] = []
    real = derived_stats_allin.calculate_equity

    def recording(game, pockets, board, **kwargs):
        calls.append((game, pockets, list(board), kwargs.get("iterations")))
        return real(game, pockets, board, **kwargs)

    monkeypatch.setattr(derived_stats_allin, "calculate_equity", recording)

    hand = _derive(tmp_path)

    assert calls == [
        ("fusion", [["6d", "3h"], ["7s", "3s"]], [], equity_module.DEFAULT_EQUITY_ITERATIONS),
    ]
    alice, bob = hand.handsplayers["Alice"], hand.handsplayers["Bob"]
    assert alice["allInEVCalculated"] is True
    assert bob["allInEVCalculated"] is True
    # 6d3h against 7s3s is close to a coin flip (about 48% for Alice, sampled):
    # each expects about half the €2.01 net pot back for the €1.05 put in.
    assert -15 < alice["allInEV"] < 5
    assert -15 < bob["allInEV"] < 5
