"""Hold'em all-in EV: the main pot and each side pot evaluated apart (#836).

A short stack all-in can only win what each opponent matched of its stake.
Each pot is evaluated among the players who can win it, with the board of the
street its money went in. The hands are PokerStars hands, parsed and derived.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

import fpdb_3_legacy.equity as equity_module
from fpdb_3_legacy import derived_stats_allin
from fpdb_3_legacy.import_prefetch import _PlaceholderIds

pytestmark = pytest.mark.skipif(equity_module.load_poker_eval() is None, reason="pypoker-eval is not installed")

# Stakes $10 / $100 / $100, all in on the river, no rake: Short's aces win the
# $30 main pot, Bob's kings the $180 side pot.
THREE_WAY_RIVER_ALL_IN_WITH_A_SIDE_POT = """PokerStars Hand #250000000001:  Hold'em No Limit ($1/$2 USD) - 2024/07/14 20:38:43 CET [2024/07/14 14:38:43 ET]
Table 'Sidepot' 6-max Seat #3 is the button
Seat 1: Short ($10 in chips)
Seat 2: Bob ($100 in chips)
Seat 3: Carol ($100 in chips)
Short: posts small blind $1
Bob: posts big blind $2
*** HOLE CARDS ***
Carol: calls $2
Short: calls $1
Bob: checks
*** FLOP *** [2c 7d 9h]
Short: checks
Bob: checks
Carol: checks
*** TURN *** [2c 7d 9h] [Js]
Short: checks
Bob: checks
Carol: checks
*** RIVER *** [2c 7d 9h Js] [3s]
Short: bets $8 and is all-in
Bob: raises $90 to $98 and is all-in
Carol: calls $98 and is all-in
*** SHOW DOWN ***
Bob: shows [Kd Kh] (a pair of Kings)
Carol: shows [Qc Qd] (a pair of Queens)
Bob collected $180 from side pot
Short: shows [As Ah] (a pair of Aces)
Short collected $30 from main pot
*** SUMMARY ***
Total pot $210 Main pot $30. Side pot $180. | Rake $0
Board [2c 7d 9h Js 3s]
Seat 1: Short (small blind) showed [As Ah] and won ($30) with a pair of Aces
Seat 2: Bob (big blind) showed [Kd Kh] and won ($180) with a pair of Kings
Seat 3: Carol (button) showed [Qc Qd] and lost with a pair of Queens



"""

# Short is all-in on the flop; Bob and Carol play on and get all in on the turn.
# The main pot is decided on the flop, the side pot on the turn.
SHORT_ALL_IN_ON_THE_FLOP_SIDE_POT_ON_THE_TURN = """PokerStars Hand #250000000002:  Hold'em No Limit ($1/$2 USD) - 2024/07/14 20:40:43 CET [2024/07/14 14:40:43 ET]
Table 'Sidepot' 6-max Seat #3 is the button
Seat 1: Short ($10 in chips)
Seat 2: Bob ($100 in chips)
Seat 3: Carol ($100 in chips)
Short: posts small blind $1
Bob: posts big blind $2
*** HOLE CARDS ***
Carol: calls $2
Short: calls $1
Bob: checks
*** FLOP *** [2c 7d 9h]
Short: bets $8 and is all-in
Bob: calls $8
Carol: calls $8
*** TURN *** [2c 7d 9h] [Js]
Bob: bets $90 and is all-in
Carol: calls $90 and is all-in
*** RIVER *** [2c 7d 9h Js] [3s]
*** SHOW DOWN ***
Bob: shows [Kd Kh] (a pair of Kings)
Carol: shows [Qc Qd] (a pair of Queens)
Bob collected $180 from side pot
Short: shows [As Ah] (a pair of Aces)
Short collected $30 from main pot
*** SUMMARY ***
Total pot $210 Main pot $30. Side pot $180. | Rake $0
Board [2c 7d 9h Js 3s]
Seat 1: Short (small blind) showed [As Ah] and won ($30) with a pair of Aces
Seat 2: Bob (big blind) showed [Kd Kh] and won ($180) with a pair of Kings
Seat 3: Carol (button) showed [Qc Qd] and lost with a pair of Queens



"""

# Heads up, a single pot: the EV is the equity of the whole net pot.
HEADS_UP_FLOP_ALL_IN = """PokerStars Hand #250000000003:  Hold'em No Limit ($1/$2 USD) - 2024/07/14 20:42:43 CET [2024/07/14 14:42:43 ET]
Table 'Sidepot' 6-max Seat #1 is the button
Seat 1: Alice ($100 in chips)
Seat 2: Bob ($150 in chips)
Alice: posts small blind $1
Bob: posts big blind $2
*** HOLE CARDS ***
Alice: calls $1
Bob: checks
*** FLOP *** [2c 7d 9h]
Bob: bets $98 and is all-in
Alice: calls $98 and is all-in
*** TURN *** [2c 7d 9h] [Js]
*** RIVER *** [2c 7d 9h Js] [3s]
*** SHOW DOWN ***
Bob: shows [Kd Kh] (a pair of Kings)
Alice: shows [As Ah] (a pair of Aces)
Alice collected $197 from pot
*** SUMMARY ***
Total pot $200 | Rake $3
Board [2c 7d 9h Js 3s]
Seat 1: Alice (button) (small blind) showed [As Ah] and won ($197) with a pair of Aces
Seat 2: Bob (big blind) showed [Kd Kh] and lost with a pair of Kings



"""


def _derive(tmp_path, text: str):
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

    path = tmp_path / "hand.txt"
    path.write_text(text, encoding="utf-8")
    parser = PokerStars(config=Config(file="HUD_config.xml"), in_path=str(path), autostart=True)
    (hand,) = parser.getProcessedHands()
    hand.prepInsert(_PlaceholderIds())
    hand.assembleHand()
    return hand


def _record_equity_calls(monkeypatch) -> list[tuple]:
    calls: list[tuple] = []
    real = derived_stats_allin.calculate_equity

    def recording(game, pockets, board, **kwargs):
        result = real(game, pockets, board, **kwargs)
        calls.append((pockets, list(board), [player.equity for player in result.players]))
        return result

    monkeypatch.setattr(derived_stats_allin, "calculate_equity", recording)
    return calls


def test_short_stack_with_the_best_hand_wins_only_the_main_pot(tmp_path, monkeypatch) -> None:
    calls = _record_equity_calls(monkeypatch)

    hand = _derive(tmp_path, THREE_WAY_RIVER_ALL_IN_WITH_A_SIDE_POT)

    board = ["2c", "7d", "9h", "Js", "3s"]
    assert calls == [
        ([["As", "Ah"], ["Kd", "Kh"], ["Qc", "Qd"]], board, [1, 0, 0]),
        ([["Kd", "Kh"], ["Qc", "Qd"]], board, [1, 0]),
    ]
    ev = {name: hand.handsplayers[name]["allInEV"] for name in ("Short", "Bob", "Carol")}
    # The $30 main pot for $10, not the whole $210 pot; the $180 side pot for $100.
    assert ev == {"Short": 2000, "Bob": 8000, "Carol": -10000}
    # The EV of a river all-in is the result (both in cents).
    assert {name: hand.handsplayers[name]["totalProfit"] for name in ev} == ev


def test_side_pot_of_a_later_all_in_keeps_the_main_pot_on_the_earlier_street(tmp_path, monkeypatch) -> None:
    calls = _record_equity_calls(monkeypatch)

    hand = _derive(tmp_path, SHORT_ALL_IN_ON_THE_FLOP_SIDE_POT_ON_THE_TURN)

    (main_pockets, main_board, main_equity), (side_pockets, side_board, side_equity) = calls
    # The main pot with the flop Short went all-in on, the side pot with the turn.
    assert (main_pockets, main_board) == ([["As", "Ah"], ["Kd", "Kh"], ["Qc", "Qd"]], ["2c", "7d", "9h"])
    assert (side_pockets, side_board) == ([["Kd", "Kh"], ["Qc", "Qd"]], ["2c", "7d", "9h", "Js"])
    main, side = Decimal(30), Decimal(180)
    expected = {
        "Short": main_equity[0] * main - 10,
        "Bob": main_equity[1] * main + side_equity[0] * side - 100,
        "Carol": main_equity[2] * main + side_equity[1] * side - 100,
    }
    for name, profit in expected.items():
        assert hand.handsplayers[name]["allInEV"] == int(100 * profit)
        assert hand.handsplayers[name]["allInEVCalculated"] is True
    # Short's flop equity is far from the river result, and only the main pot.
    assert 0 < hand.handsplayers["Short"]["allInEV"] < 2000


def test_single_pot_all_in_ev_is_the_equity_of_the_whole_net_pot(tmp_path, monkeypatch) -> None:
    calls = _record_equity_calls(monkeypatch)

    hand = _derive(tmp_path, HEADS_UP_FLOP_ALL_IN)

    ((pockets, board, (alice_equity, bob_equity)),) = calls
    assert (pockets, board) == ([["As", "Ah"], ["Kd", "Kh"]], ["2c", "7d", "9h"])
    assert hand.handsplayers["Alice"]["allInEV"] == int(100 * (alice_equity * 197 - 100))
    assert hand.handsplayers["Bob"]["allInEV"] == int(100 * (bob_equity * 197 - 100))
