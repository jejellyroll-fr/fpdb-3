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


def test_the_cash_out_summary_separates_the_payout_from_the_pot() -> None:
    """A player insures an all-in and takes the payout instead of the pot."""
    from fpdb_3_legacy.Configuration import Config

    path = CASH / "PLO-6max-USD-0.10-0.25-202602.cash.out.txt"
    hands = PartyPoker(config=Config(), in_path=str(path), autostart=True).getProcessedHands()

    assert len(hands) == 1
    hand = hands[0]
    assert hand.handid == "1770659766668"
    assert hand.hero == "Hero"
    assert "Player2" in hand.shown
    assert "Hero" in hand.shown

    # The summary reports what left the table, which is two different kinds of
    # money here. Player2's 23.01 is an insurance payout that never sat in the
    # pot, and Hero's 41.47 is the 38.50 pot plus the 2.97 of his own bet that
    # Player2, all-in for less, could not call. Recording either as pot winnings
    # is what GGPoker's readCollectPot calls out: "cashouts are separate
    # transactions that don't affect the main pot distribution".
    assert hand.cashedOut is True
    assert hand.cashOutAmounts["Player2"] == Decimal("23.01")
    assert "Player2" not in dict(hand.collected)  # insurance, not the pot
    assert ["Hero", "38.50"] in hand.collected
    assert hand.pot.returned["Hero"] == Decimal("2.97")
    assert hand.totalpot - hand.rake == Decimal("38.50")  # the announced Main Pot


def test_consecutive_modern_hands_are_split_and_parsed() -> None:
    """The modern export concatenates hands; each one must survive the split."""
    from fpdb_3_legacy.Configuration import Config

    path = CASH / "PLO-6max-USD-0.10-0.25-202607.multi.hand.split.txt"

    # allHandsAsList consumes the observed text, so split on a parser of its
    # own rather than on the one that has already processed the file.
    splitter = PartyPoker(config=Config(), in_path=str(path), autostart=False)
    splitter.obs = _read(path)
    assert len(splitter.allHandsAsList()) == 4

    parser = PartyPoker(config=Config(), in_path=str(path), autostart=True)
    hands = {hand.handid: hand for hand in parser.getProcessedHands()}
    assert set(hands) == {"1784559729098", "1784559699067", "1784559686726", "1784559652796"}

    showdown = hands["1784559729098"]
    assert showdown.hero == "Hero"
    assert ["Player1", "1.09"] in showdown.collected
    assert "Player1" in showdown.shown

    # Everyone folds to the big blind: no board, and the summary's "collected
    # $0.35" is the whole 0.10 + 0.25 of blinds, including the 0.15 of his own
    # big blind nobody called. The pot is the announced 0.20.
    walk = hands["1784559652796"]
    assert all(not cards for cards in walk.board.values())
    assert ["Hero", "0.20"] in walk.collected
    assert walk.pot.returned["Hero"] == Decimal("0.15")


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
