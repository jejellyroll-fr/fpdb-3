"""Currency contracts for the PartyPoker converter."""

from __future__ import annotations

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
