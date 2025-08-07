"""Test module for Winamax parser error handling."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from Exceptions import FpdbHandPartial, FpdbParseError
from WinamaxToFpdb import Winamax


class MockConfig:
    """Mock configuration class for testing."""

    def get_import_parameters(self) -> dict[str, Any]:
        """Return empty import parameters dict."""
        return {}


@pytest.fixture
def config_mock() -> MockConfig:
    """Create a mock configuration instance."""
    return MockConfig()


@pytest.fixture
def parser(config_mock: MockConfig) -> Winamax:
    """Create a Winamax parser instance for testing."""
    return Winamax(config_mock, autostart=False)


def test_incomplete_hand_header(parser: Winamax) -> None:
    """Test incomplete hand."""
    incomplete_header = """
Winamax Poker - Tournament "Test Tourney" buyIn: 10€+1€ -
HandId: #123-456-789 - Holdem no limit (10/20) - 2024/01/01 10:00:00 UTC
Table: 'Table Name' 6-max
Seat 1: PlayerA (1500)
*** HOLE CARDS ***
Dealt to PlayerA [Ah Kh]
PlayerA: bets 40
"""

    with pytest.raises((FpdbHandPartial, FpdbParseError)):
        parser.determineGameType(incomplete_header)


def test_hand_missing_summary(parser: Winamax) -> None:
    """Test missing summary."""
    hand_no_summary = """
Winamax Poker - Tournament "Test Tourney" buyIn: 10€+1€ - HandId: #123-456-789 - Holdem no limit (10/20) - \
2024/01/01 10:00:00 UTC
Table: 'Table Name' 6-max (real money) Seat #1 is the button
Seat 1: PlayerA (1500)
Seat 2: PlayerB (1500)
PlayerB: posts small blind 10
PlayerA: posts big blind 20
*** HOLE CARDS ***
Dealt to PlayerA [Ac Ad]
PlayerB: folds
Uncalled bet (10) returned to PlayerA
PlayerA collected 20 from pot
PlayerA: doesn't show hand
"""  # Fin abrupte, absence de la section SUMMARY

    # Ajout de l'attribut handid pour éviter l'AttributeError
    mock_hand = type(
        "obj",
        (object,),
        {"handText": hand_no_summary, "handid": "#123-456-789"},
    )()
    with pytest.raises(FpdbHandPartial):
        parser.readPlayerStacks(mock_hand)


def test_hand_with_invalid_action(parser: Winamax) -> None:
    """Test hand with invalid action."""
    hand_bad_action = """
Winamax Poker - Tournament "Test Tourney" buyIn: 10€+1€ - HandId: #123-456-789 - \
Holdem no limit (10/20) - 2024/01/01 10:00:00 UTC
Table: 'Table Name' 6-max (real money) Seat #1 is the button
Seat 1: PlayerA (1500)
Seat 2: PlayerB (1500)
PlayerB: posts small blind 10
PlayerA: posts big blind 20
*** HOLE CARDS ***
Dealt to PlayerA [Ac Ad]
PlayerB: raises to ??€  # Action invalide
PlayerA: folds
PlayerB collected 40 from pot
*** SUMMARY ***
Total pot 40 | No rake
Seat 1: PlayerA (big blind) folded before Flop
Seat 2: PlayerB (small blind) collected (40)
"""

    with pytest.raises((FpdbParseError, FpdbHandPartial)):
        parser.determineGameType(hand_bad_action)
