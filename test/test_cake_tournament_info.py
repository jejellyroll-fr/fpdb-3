"""Cake tournament hands must carry their tournament number and buy-in.

determineGameType reads "T9541472" out of the header, but readHandInfo only
copied the date, hand id and table onto the hand: every Cake tournament hand was
stored with no tourNo, so it belonged to no tournament and its buy-in was lost.
"""

from __future__ import annotations

import glob
from pathlib import Path

import pytest

from fpdb_3_legacy.CakeToFpdb import Cake
from fpdb_3_legacy.Configuration import Config

TOUR_FILES = sorted(glob.glob("regression-test-files/tour/Cake/**/*.txt", recursive=True))


@pytest.fixture(scope="module")
def config() -> Config:
    return Config()


def _first_hand(config: Config, path: str):
    hands = Cake(config=config, in_path=path, autostart=True).getProcessedHands()
    return hands[0] if hands else None


@pytest.mark.skipif(not TOUR_FILES, reason="no Cake tournament fixtures found")
@pytest.mark.parametrize("path", TOUR_FILES, ids=lambda p: Path(p).name)
def test_every_tournament_hand_knows_its_tournament(config: Config, path: str) -> None:
    hand = _first_hand(config, path)
    if hand is None:  # a fixture that is a partial hand on purpose
        pytest.skip("no complete hand in this fixture")

    assert hand.gametype["type"] == "tour"
    assert hand.tourNo, "tourNo must be read from the T<number> in the header"
    assert str(hand.tourNo).isdigit()


def test_the_buyin_and_fee_are_read_from_the_header(config: Config) -> None:
    # "... -- CASH -- $15 + $1.5 -- 10 Max -- Table 5 ..."
    hand = _first_hand(config, "regression-test-files/tour/Cake/Flop/NLHE-10max-15-USD-201204.new.format.txt")

    assert hand.tourNo == "10965119"
    assert (hand.buyin, hand.fee) == (1500, 150)
    assert hand.buyinCurrency == "USD"


def test_the_simple_header_falls_back_to_the_prize_in_the_name(config: Config) -> None:
    """"$1 NLH Short Stack" states no buy-in structure, only the stake."""
    hand = _first_hand(config, "regression-test-files/tour/Cake/Flop/NLHE-USD-1-STT-201103.max.seats.txt")

    assert hand.tourNo == "9541472"
    assert (hand.buyin, hand.fee) == (100, 0)
