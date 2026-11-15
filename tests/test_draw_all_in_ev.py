"""Draw games: the all-in EV after the last draw, and five-card high hands (#831).

After the last draw every hand is complete, so the showdown result is the
equity, as on a hold'em river. Before it, the equity depends on draws
poker-eval does not play, and no EV is stored. The hands are real PokerStars
hands from the regression files, anonymized.
"""

from __future__ import annotations

import pytest

import fpdb_3_legacy.equity as equity_module
from fpdb_3_legacy import Card
from fpdb_3_legacy.import_prefetch import _PlaceholderIds

pytestmark = pytest.mark.skipif(equity_module.load_poker_eval() is None, reason="pypoker-eval is not installed")

# All-in after the only draw: Bob's kings beat Alice's queen high.
FIVE_CARD_DRAW_ALL_IN_AFTER_THE_DRAW = """PokerStars Game #35839278018:  5 Card Draw Limit ($0.10/$0.20 USD) - 2009/11/25 14:18:59 ET
Table 'Laodica IV' 6-max Seat #5 is the button
Seat 1: Alice ($0.37 in chips)
Seat 2: Bob ($2.38 in chips)
Seat 3: Carol ($2.82 in chips)
Seat 4: Hero ($2.73 in chips)
Seat 5: Dave ($3.85 in chips)
Seat 6: Erin ($2.28 in chips)
Erin: posts small blind $0.05
Alice: posts big blind $0.10
*** DEALING HANDS ***
Dealt to Hero [2c 4h 9c Qs 3d]
Bob: raises $0.10 to $0.20
Carol: folds
Hero: folds
Dave: folds
Erin: folds
Alice: calls $0.10
Alice: discards 1 card
Bob: discards 3 cards
Alice: bets $0.17 and is all-in
Bob: calls $0.17
*** SHOW DOWN ***
Alice: shows [Qh Jh 9d 6c Tc] (high card Queen)
Bob: shows [Ks 7h Ad Kd 8h] (a pair of Kings)
Bob collected $0.76 from pot
*** SUMMARY ***
Total pot $0.79 | Rake $0.03
Seat 1: Alice (big blind) showed [Qh Jh 9d 6c Tc] and lost with high card Queen
Seat 2: Bob showed [Ks 7h Ad Kd 8h] and won ($0.76) with a pair of Kings
Seat 3: Carol folded before the Draw (didn't bet)
Seat 4: Hero folded before the Draw (didn't bet)
Seat 5: Dave (button) folded before the Draw (didn't bet)
Seat 6: Erin (small blind) folded before the Draw



"""

# Player4 is all-in before the draw: the hands shown are not the ones held then.
FIVE_CARD_DRAW_ALL_IN_BEFORE_THE_DRAW = """PokerStars Game #64146221551:  5 Card Draw Limit ($0.10/$0.20 USD) - 2011/07/04 21:56:59 WET [2011/07/04 16:56:59 ET]
Table 'Pulova' 6-max Seat #3 is the button
Seat 1: Player1 ($1.52 in chips)
Seat 3: Hero ($2.35 in chips)
Seat 4: Player3 ($7.33 in chips)
Seat 5: Player4 ($0.15 in chips)
Seat 6: Player5 ($0.19 in chips)
Player3: posts small blind $0.05
Player4: posts big blind $0.10
*** DEALING HANDS ***
Dealt to Hero [Qd 7h 6c 6h Th]
Player5: folds
Player1: folds
Hero: raises $0.10 to $0.20
Player3: calls $0.15
Player4: calls $0.05 and is all-in
Player3: discards 2 cards
Player4: discards 2 cards
Hero: discards 2 cards [7h Th]
Dealt to Hero [Qd 6c 6h] [4h Td]
Player3: checks
Hero: checks
*** SHOW DOWN ***
Player3: shows [2h Kh Qs Ad Ks] (a pair of Kings)
Hero: mucks hand
Player3 collected $0.10 from side pot
Player4: mucks hand
Player3 collected $0.43 from main pot
*** SUMMARY ***
Total pot $0.55 Main pot $0.43. Side pot $0.10. | Rake $0.02
Seat 1: Player1 folded before the Draw (didn't bet)
Seat 3: Hero (button) mucked [Qd 4h 6c 6h Td]
Seat 4: Player3 (small blind) showed [2h Kh Qs Ad Ks] and won ($0.53) with a pair of Kings
Seat 5: Player4 (big blind) mucked [Kc 9c 9s Qc 4c]
Seat 6: Player5 folded before the Draw (didn't bet)



"""

# All-in after the third draw, three-way: Alice's 8-6 low wins.
TRIPLE_DRAW_ALL_IN_AFTER_THE_LAST_DRAW = """PokerStars Game #35839959625:  Triple Draw 2-7 Lowball Limit ($0.10/$0.20 USD) - 2009/11/25 14:33:33 ET
Table 'Theodora VI' 6-max Seat #4 is the button
Seat 1: Hero ($3.32 in chips)
Seat 2: Dave ($3.85 in chips)
Seat 3: Erin ($7.09 in chips)
Seat 4: Alice ($0.67 in chips)
Seat 5: Bob ($1.89 in chips)
Seat 6: Carol ($4.34 in chips)
Bob: posts small blind $0.05
Carol: posts big blind $0.10
*** DEALING HANDS ***
Dealt to Hero [Jd As 8h 3s 7c]
Hero: calls $0.10
Dave: folds
Erin: folds
Alice: calls $0.10
Bob: calls $0.05
Carol: checks
*** FIRST DRAW ***
Bob: discards 2 cards
Carol: discards 1 card
Hero: discards 1 card [Jd]
Dealt to Hero [As 8h 3s 7c] [4h]
Alice: discards 2 cards
Bob: checks
Carol: bets $0.10
Hero: calls $0.10
Alice: raises $0.10 to $0.20
Bob: calls $0.20
Carol: calls $0.10
Hero: calls $0.10
*** SECOND DRAW ***
Bob: discards 1 card
Carol: discards 1 card
Hero: discards 1 card [8h]
Dealt to Hero [As 3s 7c 4h] [8d]
Alice: stands pat
Bob: checks
Carol: checks
Hero: checks
Alice: bets $0.20
Bob: calls $0.20
Carol: calls $0.20
Hero: calls $0.20
*** THIRD DRAW ***
Bob: discards 1 card
Carol: discards 1 card
Hero: stands pat on [As 3s 7c 4h 8d]
Alice: stands pat
Bob: checks
Carol: checks
Hero: checks
Alice: bets $0.17 and is all-in
Bob: calls $0.17
Carol: folds
Hero: calls $0.17
*** SHOW DOWN ***
Alice: shows [5c 6c 4d 2h 8c] (Lo: 8,6,5,4,2)
Bob: mucks hand
Hero: mucks hand
Alice collected $2.39 from pot
*** SUMMARY ***
Total pot $2.51 | Rake $0.12
Seat 1: Hero mucked [4h As 8d 3s 7c]
Seat 2: Dave folded before the Draw (didn't bet)
Seat 3: Erin folded before the Draw (didn't bet)
Seat 4: Alice (button) showed [5c 6c 4d 2h 8c] and won ($2.39) with Lo: 8,6,5,4,2
Seat 5: Bob (small blind) mucked [4c 3d 9c 7h 6h]
Seat 6: Carol (big blind) folded after the 3rd Draw



"""


def _derive(tmp_path, text: str):
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

    path = tmp_path / "draw.txt"
    path.write_text(text, encoding="utf-8")
    parser = PokerStars(config=Config(file="HUD_config.xml"), in_path=str(path), autostart=True)
    (hand,) = parser.getProcessedHands()
    hand.prepInsert(_PlaceholderIds())
    hand.assembleHand()
    return hand


def _all_in_ev(hand) -> dict[str, int]:
    return {name: row["allInEV"] for name, row in hand.handsplayers.items() if row["allInEVCalculated"]}


def test_five_card_draw_all_in_after_the_draw_stores_the_showdown_result(tmp_path) -> None:
    hand = _derive(tmp_path, FIVE_CARD_DRAW_ALL_IN_AFTER_THE_DRAW)

    # Each put in $0.37 of a $0.79 pot raked $0.03: Bob takes all $0.76.
    assert _all_in_ev(hand) == {"Alice": -37, "Bob": 39}


def test_triple_draw_all_in_after_the_last_draw_stores_the_showdown_result(tmp_path) -> None:
    hand = _derive(tmp_path, TRIPLE_DRAW_ALL_IN_AFTER_THE_LAST_DRAW)

    # Three put in $0.67 each of a $2.51 pot raked $0.12; Carol folded.
    assert _all_in_ev(hand) == {"Alice": 172, "Bob": -67, "Hero": -67}


def test_an_all_in_before_the_draw_stores_no_ev(tmp_path) -> None:
    hand = _derive(tmp_path, FIVE_CARD_DRAW_ALL_IN_BEFORE_THE_DRAW)

    assert _all_in_ev(hand) == {}


@pytest.mark.parametrize("category", ["fivedraw", "5_studhi"])
def test_five_card_high_games_rank_all_five_cards(category: str) -> None:
    # "holdem", their former evaluation, called AKQ83 against AKQ72 a tie.
    engine = equity_module.load_poker_eval()
    assert engine is not None
    game = Card.games[category][1]

    assert engine.winners(
        game=game, pockets=[["As", "Ks", "Qd", "7c", "2h"], ["Ah", "Kh", "Qc", "8d", "3s"]], board=[]
    ) == {"hi": [1]}


def test_five_card_stud_deals_the_cards_still_to_come() -> None:
    # On fourth street each player holds four cards: the fifth is dealt.
    result = equity_module.calculate_equity(
        Card.games["5_studhi"][1], [["As", "Ad", "7c", "2h"], ["Kh", "Kd", "Qc", "8d"]], iterations=None
    )

    assert result.exhaustive
    assert 0.8 < result.players[0].equity < 1
