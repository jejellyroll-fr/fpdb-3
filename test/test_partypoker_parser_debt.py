"""Currency contracts for the PartyPoker converter."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from fpdb_3_legacy.PartyPokerToFpdb import PartyPoker

ROOT = Path(__file__).resolve().parents[1]
CASH = ROOT / "regression-test-files" / "cash" / "PartyPoker" / "Flop"
TOUR = ROOT / "regression-test-files" / "tour" / "PartyPoker" / "Flop"


def _read(path: Path) -> str:
    for encoding in PartyPoker.codepage:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    msg = f"no codepage of the parser decodes {path}"
    raise AssertionError(msg)


def _game_type(hand_history: str) -> dict:
    return PartyPoker.determineGameType(PartyPoker.__new__(PartyPoker), hand_history)


@pytest.mark.parametrize(
    ("filename", "currency"),
    [
        # Stake line names the currency with a symbol.
        ("NLHE-6max-USD-0.05-0.10-201209.silent.post.both.txt", "USD"),
        ("NLHE-EUR-0.05-0.10-201011.Sample.txt", "EUR"),
        ("NLHE-EUR-6max-0.10-0.25-201112.post.both.txt", "EUR"),
    ],
)
def test_stake_line_symbol_sets_the_ring_currency(filename: str, currency: str) -> None:
    game_type = _game_type(_read(CASH / filename))

    assert game_type["type"] == "ring"
    assert game_type["currency"] == currency


@pytest.mark.parametrize(
    "filename",
    [
        # "0.50/1 Texas Hold'em Game Table (NL)": real money, no symbol stated.
        "NLHE-6max-USD-0.50-1.00-201301.partial.player.names.txt",
        "NLHE-USD-0.01-0.02-20100712.emailedHistory.txt",
    ],
)
def test_real_money_ring_without_a_stake_symbol_is_not_tournament_chips(
    filename: str,
) -> None:
    game_type = _game_type(_read(CASH / filename))

    assert game_type["type"] == "ring"
    # The player stacks are stated in dollars; these are cash games, so their
    # amounts must not be read as tournament chips.
    assert game_type["currency"] == "USD"


def test_tournament_hands_use_tournament_chips() -> None:
    game_type = _game_type(_read(TOUR / "NLHE-USD-MTT-unknownBuyIn-200811.emailedHandHistory.txt"))

    assert game_type["type"] == "tour"
    assert game_type["currency"] == "T$"


def test_play_money_ring_is_not_read_as_a_real_currency() -> None:
    # Derived from a real cash hand: play money tables state the same layout
    # with bare amounts and a Play Money marker. The corpus has no such export.
    real = _read(CASH / "NLHE-6max-USD-0.05-0.10-201209.silent.post.both.txt")
    play = (
        real.replace("$10 USD NL Texas Hold'em", "10 NL Texas Hold'em")
        .replace("(Real Money)", "(Play Money)")
        .replace("$", "")
    )

    game_type = _game_type(play)

    assert game_type["type"] == "ring"
    assert game_type["currency"] == "play"


def test_partypoker_modern_hh_summary_and_splitting() -> None:
    from fpdb_3_legacy.Configuration import Config

    sample_hands = """***** Hand History For Game 1770659766668adeb0h5qfm *****
0.10/0.25 Omaha Hi Game Table (PL) - Mon Feb 09 12:55:26 EST 2026
Table Table 7488952 (Real Money) -- Seat 1 is the button
Total number of players : 4/6
Seat 1: Player4 ($56.64)
Seat 2: Player1 ($19.93)
Seat 3: Player2 ($20.20)
Seat 4: Hero ($25.86)
Player1 posts small blind (0.10)
Player2 posts big blind (0.25)
** Dealing down cards **
Dealt to Hero [ 9c, 7h, 8h, 4d ]
Hero raises 0.85 to 0.85
Player4 folds
Player1 folds
Player2 raises 2.40 to 2.65
Hero calls (1.80)
** Dealing Flop ** : [ Jc, 7d, 6c ]
Player2 bets (5.13)
Hero raises 20.52 to 20.52
Player2 calls (12.42)
Player2 is all-In.
Creating Main Pot with $ 38.50 with Player2, Hero
Player2 Cash-out Premium % is 1.0
Player2 opted for cash-out
Player2 probabilty is 60.37
Player2 Cashout Amount is 23.01
** Dealing Turn ** : [ Ts ]
** Dealing River ** : [ Js ]
** Summary **
Main Pot: $38.50 Rake: $2.0
Board: [ Jc, 7d, 6c, Ts, Js ]
Player4 balance $56.64, didn't bet (folded)
Player1 balance $19.83, lost $0.10 (folded)
Player2 Cashed out balance $23.01, bet $20.20, collected $23.01, net +$2.81[ Tc, Ac, Ad, 4c ] [ two pairs, aces and jacks -- Ac,Ad,Jc,Js,Ts ]
Hero balance $44.16, bet $23.17, collected $41.47, net +$18.30[ 9c, 7h, 8h, 4d ] [ a straight, seven to jack -- Jc,Ts,9c,8h,7d ]

***** Hand History For Game 1784559729098bywbird3xlj *****
0.10/0.25 Omaha Hi Game Table (PL) - Mon Jul 20 11:01:17 EDT 2026
Table Table 7490030 (Real Money) -- Seat 1 is the button
Total number of players : 4/6
Seat 1: Player4 ($113.97)
Seat 2: Player1 ($12.60)
Seat 3: Hero ($51.56)
Seat 4: Player3 ($85.96)
Player1 posts small blind (0.10)
Hero posts big blind (0.25)
** Dealing down cards **
Dealt to Hero [ 7s, Tc, 5c, Jh ]
Player3 folds
Player4 folds
Player1 calls (0.15)
Hero checks
** Dealing Flop ** : [ 8d, 5s, 8h ]
Player1 checks
Hero checks
** Dealing Turn ** : [ 2c ]
Player1 bets (0.32)
Hero calls (0.32)
** Dealing River ** : [ 6s ]
Player1 checks
Hero checks
** Summary **
Main Pot: $1.09 Rake: $0.05
Board: [ 8d, 5s, 8h, 2c, 6s ]
Player4 balance $113.97, didn't bet (folded)
Player1 balance $13.12, bet $0.57, collected $1.09, net +$0.52[ 9s, 4d, 8s, Jc ] [ three of a kind, eights -- Jc,8s,8d,8h,6s ]
Hero balance $50.99, lost $0.57[ 7s, Tc, 5c, Jh ] [ two pairs, eights and fives -- Jh,8d,8h,5c,5s ]
Player3 balance $85.96, didn't bet (folded)
"""

    config = Config()
    parser = PartyPoker(config, autostart=False)
    parser.obs = sample_hands
    parser.in_path = "test.txt"
    parser.readFile = lambda: None

    hands_list = parser.allHandsAsList()
    assert len(hands_list) == 2

    # Process hand 1 (Cashout & Showdown)
    hand1 = parser.processHand(hands_list[0])
    assert hand1.handid == "1770659766668"
    assert hand1.hero == "Hero"
    assert ["Player2", "23.01"] in hand1.collected
    assert ["Hero", "41.47"] in hand1.collected
    assert "Player2" in hand1.shown
    assert "Hero" in hand1.shown

    # Process hand 2
    hand2 = parser.processHand(hands_list[1])
    assert hand2.handid == "1784559729098"
    assert hand2.hero == "Hero"
    assert ["Player1", "1.09"] in hand2.collected
    assert "Player1" in hand2.shown



def test_the_summary_collected_keeps_its_uncalled_bet_out_of_the_pot() -> None:
    """PartyPoker's "collected" is what left the table, not the pot won.

    Every other room reports the pot alone -- PokerStars prints "Uncalled bet
    returned" on its own line and keeps it out of both "collected" and "Total
    pot" -- and Hand.addUncalled removes it from the pot to match. Passing the
    summary figure through unchanged made Hand.totalPot() see more collected
    than the announced pot and build an extra solo pot from the difference,
    inflating the pot by exactly the bet nobody called.

    In this hand Player3 bets 0.13 on the flop, Player6 folds, and the summary
    reads "bet $0.21, collected $0.31, net +$0.1" against "Main Pot: $0.18".
    """
    from fpdb_3_legacy.Configuration import Config

    path = CASH / "NLHE-USD-0.01-0.02-20100712.emailedHistory.txt"
    hand = PartyPoker(config=Config(), in_path=str(path), autostart=True).getProcessedHands()[0]

    assert hand.totalpot == Decimal("0.18")  # the announced pot, not the 0.31 collected
    assert hand.rake == Decimal("0.00")  # the file says "Rake: $0"
    assert hand.collectees["Player3"] == Decimal("0.18")
    assert hand.pot.returned["Player3"] == Decimal("0.13")  # the uncalled flop bet
