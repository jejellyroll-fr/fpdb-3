import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Exceptions import FpdbHandPartial, FpdbParseError
from Hand import HoldemOmahaHand
from WinamaxToFpdb import Winamax


# Mock simple de config
class MockConfig:
    def get_import_parameters(self):
        return {}


@pytest.fixture
def config_mock():
    return MockConfig()


@pytest.fixture
def parser(config_mock):
    return Winamax(config_mock, autostart=False)


def test_incomplete_hand_header(parser):
    """
    Teste une main avec un en-tête incomplet (section *** SUMMARY *** manquante).
    On s'attend à ce que determineGameType ou readHandInfo lève FpdbHandPartial ou FpdbParseError.
    """
    incomplete_header = """
Winamax Poker - Tournament "Test Tourney" buyIn: 10€+1€ - HandId: #123-456-789 - Holdem no limit (10/20) - 2024/01/01 10:00:00 UTC
Table: 'Table Name' 6-max
Seat 1: PlayerA (1500)
*** HOLE CARDS ***
Dealt to PlayerA [Ah Kh]
PlayerA: bets 40
"""  # Fin tronquée, absence de *** SUMMARY ***

    with pytest.raises((FpdbHandPartial, FpdbParseError)):
        gametype = parser.determineGameType(incomplete_header)
        mock_hand = type(
            "obj", (object,), {"handText": incomplete_header, "gametype": gametype},
        )()
        parser.readHandInfo(mock_hand)


def test_hand_missing_summary(parser):
    """
    Teste une main complète mais sans la section *** SUMMARY ***.
    L'appel à readPlayerStacks devrait lever une FpdbHandPartial.
    """
    hand_no_summary = """
Winamax Poker - Tournament "Test Tourney" buyIn: 10€+1€ - HandId: #123-456-789 - Holdem no limit (10/20) - 2024/01/01 10:00:00 UTC
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
        "obj", (object,), {"handText": hand_no_summary, "handid": "#123-456-789"},
    )()
    with pytest.raises(FpdbHandPartial):
        parser.readPlayerStacks(mock_hand)


def test_hand_with_invalid_action(parser, config_mock):
    """
    Teste une main contenant une ligne d'action malformée.
    On s'attend à ce que l'une des étapes (lecture des infos ou action) lève FpdbParseError ou FpdbHandPartial.
    """
    hand_bad_action = """
Winamax Poker - Tournament "Test Tourney" buyIn: 10€+1€ - HandId: #123-456-789 - Holdem no limit (10/20) - 2024/01/01 10:00:00 UTC
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
        gametype = parser.determineGameType(hand_bad_action)
        hhc_mock = type("obj", (object,), {"siteId": 15})()
        hand_obj = HoldemOmahaHand(
            config_mock,
            hhc_mock,
            "Winamax",
            gametype,
            hand_bad_action,
            builtFrom="Test",
        )
        parser.readHandInfo(hand_obj)
        parser.readPlayerStacks(hand_obj)
        parser.compilePlayerRegexs(hand_obj)
        parser.markStreets(hand_obj)
        parser.readAction(hand_obj, "PREFLOP")
