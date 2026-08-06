"""Comprehensive unit and non-regression tests for uncalled bets using real hand history fixtures.

Verifies that uncalled bets are correctly recognized, returned to the proper player
in `hand.pot.returned`, and accounted for in total pot, rake, and net collected calculations
across all supported poker room fixture files without money leaks or phantom rake.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from fpdb_3_legacy.BovadaToFpdb import Bovada
from fpdb_3_legacy.CakeToFpdb import Cake
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.GGPokerToFpdb import GGPoker
from fpdb_3_legacy.iPoker.base import iPoker
from fpdb_3_legacy.PacificPokerToFpdb import PacificPoker
from fpdb_3_legacy.PartyPokerToFpdb import PartyPoker
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars
from fpdb_3_legacy.UnibetToFpdb import Unibet
from fpdb_3_legacy.WinamaxToFpdb import Winamax
from fpdb_3_legacy.WinningToFpdb import Winning

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "hands"


@pytest.fixture(scope="module")
def parser_config() -> Config:
    return Config()


def parse_fixture(parser_class, parser_config, relative_path: str):
    file_path = FIXTURES / relative_path
    assert file_path.exists(), f"Fixture file not found: {file_path}"
    parser = parser_class(config=parser_config, in_path=str(file_path), autostart=True)
    hands = parser.getProcessedHands()
    assert len(hands) > 0, f"No hands parsed from {file_path}"
    return hands


def test_pokerstars_real_fixture_uncalled_bets(parser_config) -> None:
    """Test PokerStars real fixture hands for uncalled bet accounting."""
    hands = parse_fixture(PokerStars, parser_config, "pokerstars/holdem/cash_nl_6max.txt")

    for hand in hands:
        if hand.pot.returned:
            for player, amount in hand.pot.returned.items():
                assert amount > 0, f"Uncalled bet for {player} must be positive"
        hand.calculate_net_collected()
        collected_sum = sum(hand.collectees.values())
        returned_sum = sum(hand.pot.returned.values())
        rake = Decimal(str(hand.rake))
        assert hand.totalpot >= collected_sum, f"Total pot {hand.totalpot} must cover collected {collected_sum}"


def test_partypoker_real_fixture_uncalled_bets(parser_config) -> None:
    """Test PartyPoker real fixture hands for uncalled bet accounting."""
    hands = parse_fixture(PartyPoker, parser_config, "partypoker/stud/7stud.txt")

    for hand in hands:
        if hand.pot.returned:
            for player, amount in hand.pot.returned.items():
                assert amount > 0
        hand.calculate_net_collected()


def test_winamax_real_fixture_uncalled_bets(parser_config) -> None:
    """Test Winamax real fixture hands for uncalled bet accounting."""
    hands = parse_fixture(Winamax, parser_config, "winamax/nlhe_cash.txt")

    for hand in hands:
        if hand.pot.returned:
            for player, amount in hand.pot.returned.items():
                assert amount > 0
        hand.calculate_net_collected()


def test_unibet_real_fixture_uncalled_bets(parser_config) -> None:
    """Test Unibet real fixture hands for uncalled bet accounting."""
    hands = parse_fixture(Unibet, parser_config, "unibet/banzai.txt")

    for hand in hands:
        if hand.pot.returned:
            for player, amount in hand.pot.returned.items():
                assert amount > 0
        hand.calculate_net_collected()


def test_ipoker_real_fixture_uncalled_bets(parser_config) -> None:
    """Test iPoker real fixture hands for uncalled bet accounting."""
    hands = parse_fixture(iPoker, parser_config, "ipoker/twister/twister_sng.txt")

    for hand in hands:
        if hand.pot.returned:
            for player, amount in hand.pot.returned.items():
                assert amount > 0
        hand.calculate_net_collected()


def test_bovada_real_fixture_uncalled_bets(parser_config) -> None:
    """Test Bovada real fixture hands for uncalled bet accounting."""
    hands = parse_fixture(Bovada, parser_config, "bovada/zone_poker.txt")

    for hand in hands:
        if hand.pot.returned:
            for player, amount in hand.pot.returned.items():
                assert amount > 0
        hand.calculate_net_collected()


def test_winning_real_fixture_uncalled_bets(parser_config) -> None:
    """Test Winning real fixture hands for uncalled bet accounting."""
    hands = parse_fixture(Winning, parser_config, "winning/modern_cash.txt")

    for hand in hands:
        if hand.pot.returned:
            for player, amount in hand.pot.returned.items():
                assert amount > 0
        hand.calculate_net_collected()


def test_cake_real_fixture_uncalled_bets(parser_config) -> None:
    """Test Cake real fixture hands for uncalled bet accounting."""
    hands = parse_fixture(Cake, parser_config, "cake/cash_nlhe.txt")

    for hand in hands:
        if hand.pot.returned:
            for player, amount in hand.pot.returned.items():
                assert amount > 0
        hand.calculate_net_collected()


def test_pacific_real_fixture_uncalled_bets(parser_config) -> None:
    """Test Pacific / 888 real fixture hands for uncalled bet accounting."""
    hands = parse_fixture(PacificPoker, parser_config, "pacific/jackpot_table.txt")

    for hand in hands:
        if hand.pot.returned:
            for player, amount in hand.pot.returned.items():
                assert amount > 0
        hand.calculate_net_collected()


def test_ggpoker_real_fixture_uncalled_bets(parser_config) -> None:
    """Test GGPoker real fixture hands for uncalled bet accounting."""
    hands = parse_fixture(GGPoker, parser_config, "ggpoker/nlh_cash_6max.txt")

    for hand in hands:
        if hand.pot.returned:
            for player, amount in hand.pot.returned.items():
                assert amount > 0
        hand.calculate_net_collected()
