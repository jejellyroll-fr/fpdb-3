"""Comprehensive tests for PokerStarsToFpdb.readAction method."""

import unittest
from decimal import Decimal
from unittest.mock import Mock

from PokerStarsToFpdb import PokerStars


class MockConfig:
    """Mock configuration for testing."""

    def get_import_parameters(self) -> dict:
        """Return import parameters for testing."""
        return {
            "saveActions": True,
            "callFpdbHud": False,
            "cacheSessions": False,
            "publicDB": False,
            "importFilters": [
                "holdem",
                "omahahi",
                "omahahilo",
                "studhi",
                "studlo",
                "razz",
                "27_1draw",
                "27_3draw",
                "fivedraw",
                "badugi",
                "baduci",
            ],
            "handCount": 0,
            "fastFold": False,
        }

    def get_site_id(self, sitename: str) -> int:
        """Return the site ID for the given site name."""
        return 32  # PokerStars.COM


class TestPokerStarsReadAction(unittest.TestCase):
    """Test cases for PokerStars readAction method."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.config = MockConfig()
        self.parser = PokerStars(self.config, in_path="dummy")
        self.hand = Mock()
        self.hand.gametype = {"split": False}
        self.hand.communityStreets = ["FLOP", "TURN", "RIVER"]
        self.hand.addFold = Mock()
        self.hand.addCheck = Mock()
        self.hand.addCall = Mock()
        self.hand.addBet = Mock()
        self.hand.addRaiseTo = Mock()
        self.hand.addBlind = Mock()
        self.hand.addDiscard = Mock()
        self.hand.addStandsPat = Mock()
        self.hand.addUncalled = Mock()
        # Allow walk_adjustments attribute assignment
        self.hand.walk_adjustments = {}
        # Configure pot.returned as a real dict (not Mock) for uncalled bet tracking
        self.hand.pot.returned = {}

    def test_readaction_empty_street(self) -> None:
        """Test readAction with empty street."""
        self.hand.streets = {"FLOP": ""}

        self.parser.readAction(self.hand, "FLOP")

        # Should return early without processing
        self.hand.addFold.assert_not_called()
        self.hand.addCheck.assert_not_called()

    def test_readaction_none_street(self) -> None:
        """Test readAction with None street."""
        self.hand.streets = {"FLOP": None}

        self.parser.readAction(self.hand, "FLOP")

        # Should return early without processing
        self.hand.addFold.assert_not_called()
        self.hand.addCheck.assert_not_called()

    def test_readaction_split_game_street_modification(self) -> None:
        """Test street name modification for split games."""
        self.hand.gametype = {"split": True}
        self.hand.streets = {"FLOP2": "Player1: checks"}

        # Mock regex
        self.parser.re_action = Mock()
        mock_match = Mock()
        mock_match.__getitem__ = Mock(side_effect=lambda x: {"ATYPE": " checks", "PNAME": "Player1"}.get(x))
        self.parser.re_action.finditer = Mock(return_value=[mock_match])
        self.parser.re_uncalled = Mock()
        self.parser.re_uncalled.search = Mock(return_value=None)

        self.parser.readAction(self.hand, "FLOP")

        # Should use FLOP2 for split games
        self.parser.re_action.finditer.assert_called_with("Player1: checks")

    def test_readaction_basic_actions(self) -> None:
        """Test readAction with all basic poker actions."""
        street_text = """Player1: folds
Player2: checks
Player3: calls $0.50
Player4: bets $1.00
Player5: raises $0.50 to $2.00"""

        self.hand.streets = {"FLOP": street_text}

        # Mock actions
        actions = [
            {"ATYPE": " folds", "PNAME": "Player1", "BET": None, "BETTO": None, "CARDS": None},
            {"ATYPE": " checks", "PNAME": "Player2", "BET": None, "BETTO": None, "CARDS": None},
            {"ATYPE": " calls", "PNAME": "Player3", "BET": "0.50", "BETTO": None, "CARDS": None},
            {"ATYPE": " bets", "PNAME": "Player4", "BET": "1.00", "BETTO": None, "CARDS": None},
            {"ATYPE": " raises", "PNAME": "Player5", "BET": "0.50", "BETTO": "2.00", "CARDS": None},
        ]

        mock_matches = []
        for action_data in actions:
            mock_match = Mock()
            mock_match.__getitem__ = Mock(side_effect=lambda x, data=action_data: data.get(x))
            mock_matches.append(mock_match)

        self.parser.re_action = Mock()
        self.parser.re_action.finditer = Mock(return_value=mock_matches)
        self.parser.re_uncalled = Mock()
        self.parser.re_uncalled.search = Mock(return_value=None)
        self.parser.clearMoneyString = Mock(side_effect=lambda x: x)
        self.parser._processRaise = Mock()

        self.parser.readAction(self.hand, "FLOP")

        # Verify all action types were processed
        self.hand.addFold.assert_called_with("FLOP", "Player1")
        self.hand.addCheck.assert_called_with("FLOP", "Player2")
        self.hand.addCall.assert_called_with("FLOP", "Player3", "0.50")
        self.hand.addBet.assert_called_with("FLOP", "Player4", "1.00")
        self.parser._processRaise.assert_called()

    def test_readaction_draw_actions(self) -> None:
        """Test readAction with draw-specific actions."""
        street_text = """Player1: discards 2 cards [3h 7c]
Player2: stands pat"""

        self.hand.streets = {"DRAW": street_text}

        actions = [
            {"ATYPE": " discards", "PNAME": "Player1", "BET": "2", "BETTO": None, "CARDS": "[3h 7c]"},
            {"ATYPE": " stands pat", "PNAME": "Player2", "BET": None, "BETTO": None, "CARDS": None},
        ]

        mock_matches = []
        for action_data in actions:
            mock_match = Mock()
            mock_match.__getitem__ = Mock(side_effect=lambda x, data=action_data: data.get(x))
            mock_matches.append(mock_match)

        self.parser.re_action = Mock()
        self.parser.re_action.finditer = Mock(return_value=mock_matches)
        self.parser.re_uncalled = Mock()
        self.parser.re_uncalled.search = Mock(return_value=None)

        self.parser.readAction(self.hand, "DRAW")

        # Verify draw actions were processed
        self.hand.addDiscard.assert_called_with("DRAW", "Player1", "2", "[3h 7c]")
        self.hand.addStandsPat.assert_called_with("DRAW", "Player2", None)

    def test_readaction_uncalled_bet_basic(self) -> None:
        """Test readAction with uncalled bet (non-walk scenario)."""
        street_text = "Player1: bets $5.00\nUncalled bet ($5.00) returned to Player1"

        self.hand.streets = {"RIVER": street_text}
        self.hand.handText = "*** PREFLOP ***\n*** SUMMARY ***\nPlayer2 collected $2.00"

        # Mock action processing
        self.parser.re_action = Mock()
        self.parser.re_action.finditer = Mock(return_value=[])

        # Mock uncalled bet
        uncalled_match = Mock()
        uncalled_match.group = Mock(side_effect=lambda x: {"PNAME": "Player1", "BET": "5.00"}.get(x))
        self.parser.re_uncalled = Mock()
        self.parser.re_uncalled.search = Mock(return_value=uncalled_match)

        # Mock collection (different player)
        collection_match = Mock()
        collection_match.group = Mock(side_effect=lambda x: {"PNAME": "Player2", "POT": "2.00"}.get(x))
        self.parser.re_collect_pot2 = Mock()
        self.parser.re_collect_pot2.search = Mock(return_value=collection_match)

        self.parser.readAction(self.hand, "RIVER")

        # Should add uncalled bet but not create walk adjustment
        self.hand.addUncalled.assert_called_with("RIVER", "Player1", "5.00")
        self.assertEqual(len(self.hand.walk_adjustments), 0)

    def test_readaction_walk_scenario_equal_amounts(self) -> None:
        """Test readAction with walk scenario (uncalled == collected)."""
        street_text = "Uncalled bet ($1.00) returned to Player1"

        self.hand.streets = {"PREFLOP": street_text}
        self.hand.handText = "*** PREFLOP ***\nPlayer1 collected $1.00\n*** SUMMARY ***"

        # Mock action processing
        self.parser.re_action = Mock()
        self.parser.re_action.finditer = Mock(return_value=[])

        # Mock uncalled bet
        uncalled_match = Mock()
        uncalled_match.group = Mock(side_effect=lambda x: {"PNAME": "Player1", "BET": "1.00"}.get(x))
        self.parser.re_uncalled = Mock()
        self.parser.re_uncalled.search = Mock(return_value=uncalled_match)

        # Mock collection (same player, same amount)
        collection_match = Mock()
        collection_match.group = Mock(side_effect=lambda x: {"PNAME": "Player1", "POT": "1.00"}.get(x))
        self.parser.re_collect_pot2 = Mock()
        self.parser.re_collect_pot2.search = Mock(return_value=collection_match)

        self.parser.readAction(self.hand, "PREFLOP")

        # Should add uncalled bet and create walk adjustment
        self.hand.addUncalled.assert_called_with("PREFLOP", "Player1", "1.00")
        self.assertEqual(len(self.hand.walk_adjustments), 1)
        self.assertEqual(self.hand.walk_adjustments["Player1"], Decimal("1.00"))

    def test_readaction_walk_scenario_bb_walk(self) -> None:
        """Test readAction with BB walk scenario (uncalled > collected)."""
        street_text = "Uncalled bet ($2.00) returned to Player1"

        self.hand.streets = {"PREFLOP": street_text}
        self.hand.handText = "*** PREFLOP ***\nPlayer1 collected $0.50\n*** SUMMARY ***"

        # Mock action processing
        self.parser.re_action = Mock()
        self.parser.re_action.finditer = Mock(return_value=[])

        # Mock uncalled bet
        uncalled_match = Mock()
        uncalled_match.group = Mock(side_effect=lambda x: {"PNAME": "Player1", "BET": "2.00"}.get(x))
        self.parser.re_uncalled = Mock()
        self.parser.re_uncalled.search = Mock(return_value=uncalled_match)

        # Mock collection (same player, smaller amount - BB walk)
        collection_match = Mock()
        collection_match.group = Mock(side_effect=lambda x: {"PNAME": "Player1", "POT": "0.50"}.get(x))
        self.parser.re_collect_pot2 = Mock()
        self.parser.re_collect_pot2.search = Mock(return_value=collection_match)

        self.parser.readAction(self.hand, "PREFLOP")

        # Should add uncalled bet and create walk adjustment
        self.hand.addUncalled.assert_called_with("PREFLOP", "Player1", "2.00")
        self.assertEqual(len(self.hand.walk_adjustments), 1)
        self.assertEqual(self.hand.walk_adjustments["Player1"], Decimal("2.00"))

    def test_readaction_not_walk_scenario(self) -> None:
        """Test readAction with not-walk scenario (uncalled < collected)."""
        street_text = "Uncalled bet ($1.00) returned to Player1"

        self.hand.streets = {"PREFLOP": street_text}
        self.hand.handText = "*** PREFLOP ***\nPlayer1 collected $5.00\n*** SUMMARY ***"

        # Mock action processing
        self.parser.re_action = Mock()
        self.parser.re_action.finditer = Mock(return_value=[])

        # Mock uncalled bet
        uncalled_match = Mock()
        uncalled_match.group = Mock(side_effect=lambda x: {"PNAME": "Player1", "BET": "1.00"}.get(x))
        self.parser.re_uncalled = Mock()
        self.parser.re_uncalled.search = Mock(return_value=uncalled_match)

        # Mock collection (same player, larger amount - not a walk)
        collection_match = Mock()
        collection_match.group = Mock(side_effect=lambda x: {"PNAME": "Player1", "POT": "5.00"}.get(x))
        self.parser.re_collect_pot2 = Mock()
        self.parser.re_collect_pot2.search = Mock(return_value=collection_match)

        self.parser.readAction(self.hand, "PREFLOP")

        # Should add uncalled bet but not create walk adjustment
        self.hand.addUncalled.assert_called_with("PREFLOP", "Player1", "1.00")
        self.assertEqual(len(self.hand.walk_adjustments), 0)

    def test_readaction_uncalled_bet_with_commas(self) -> None:
        """Test readAction handles comma-separated amounts in uncalled bets."""
        street_text = "Uncalled bet ($1,500.00) returned to Player1"

        self.hand.streets = {"RIVER": street_text}
        self.hand.handText = "*** PREFLOP ***\nPlayer1 collected $1,500.00\n*** SUMMARY ***"

        # Mock action processing
        self.parser.re_action = Mock()
        self.parser.re_action.finditer = Mock(return_value=[])

        # Mock uncalled bet with comma
        uncalled_match = Mock()
        uncalled_match.group = Mock(side_effect=lambda x: {"PNAME": "Player1", "BET": "1,500.00"}.get(x))
        self.parser.re_uncalled = Mock()
        self.parser.re_uncalled.search = Mock(return_value=uncalled_match)

        # Mock collection with comma
        collection_match = Mock()
        collection_match.group = Mock(side_effect=lambda x: {"PNAME": "Player1", "POT": "1,500.00"}.get(x))
        self.parser.re_collect_pot2 = Mock()
        self.parser.re_collect_pot2.search = Mock(return_value=collection_match)

        self.parser.readAction(self.hand, "RIVER")

        # Should handle comma removal and create walk adjustment
        self.hand.addUncalled.assert_called_with("RIVER", "Player1", "1,500.00")
        self.assertEqual(len(self.hand.walk_adjustments), 1)
        self.assertEqual(self.hand.walk_adjustments["Player1"], Decimal("1500.00"))

    def test_readaction_uncalled_bet_player_name_with_spaces(self) -> None:
        """Test readAction handles player names with leading/trailing spaces."""
        street_text = "Uncalled bet ($5.00) returned to  Player1  "

        self.hand.streets = {"TURN": street_text}
        self.hand.handText = "*** PREFLOP ***\n*** SUMMARY ***"

        # Mock action processing
        self.parser.re_action = Mock()
        self.parser.re_action.finditer = Mock(return_value=[])

        # Mock uncalled bet with spaces in player name
        uncalled_match = Mock()
        uncalled_match.group = Mock(side_effect=lambda x: {"PNAME": "  Player1  ", "BET": "5.00"}.get(x))
        self.parser.re_uncalled = Mock()
        self.parser.re_uncalled.search = Mock(return_value=uncalled_match)

        # No collection match
        self.parser.re_collect_pot2 = Mock()
        self.parser.re_collect_pot2.search = Mock(return_value=None)

        self.parser.readAction(self.hand, "TURN")

        # Should strip spaces from player name
        self.hand.addUncalled.assert_called_with("TURN", "Player1", "5.00")

    def test_readaction_no_uncalled_bet(self) -> None:
        """Test readAction when no uncalled bet is found."""
        street_text = "Player1: checks\nPlayer2: checks"

        self.hand.streets = {"FLOP": street_text}

        # Mock action processing
        actions = [
            {"ATYPE": " checks", "PNAME": "Player1", "BET": None, "BETTO": None, "CARDS": None},
            {"ATYPE": " checks", "PNAME": "Player2", "BET": None, "BETTO": None, "CARDS": None},
        ]

        mock_matches = []
        for action_data in actions:
            mock_match = Mock()
            mock_match.__getitem__ = Mock(side_effect=lambda x, data=action_data: data.get(x))
            mock_matches.append(mock_match)

        self.parser.re_action = Mock()
        self.parser.re_action.finditer = Mock(return_value=mock_matches)

        # No uncalled bet
        self.parser.re_uncalled = Mock()
        self.parser.re_uncalled.search = Mock(return_value=None)

        self.parser.readAction(self.hand, "FLOP")

        # Should process actions but not call addUncalled
        self.hand.addCheck.assert_called()
        self.hand.addUncalled.assert_not_called()

    def test_readaction_existing_walk_adjustments(self) -> None:
        """Test readAction when hand already has walk_adjustments."""
        street_text = "Uncalled bet ($1.00) returned to Player1"

        self.hand.streets = {"PREFLOP": street_text}
        self.hand.handText = "*** PREFLOP ***\nPlayer1 collected $1.00\n*** SUMMARY ***"
        self.hand.walk_adjustments = {"ExistingPlayer": Decimal("0.50")}

        # Mock action processing
        self.parser.re_action = Mock()
        self.parser.re_action.finditer = Mock(return_value=[])

        # Mock walk scenario
        uncalled_match = Mock()
        uncalled_match.group = Mock(side_effect=lambda x: {"PNAME": "Player1", "BET": "1.00"}.get(x))
        self.parser.re_uncalled = Mock()
        self.parser.re_uncalled.search = Mock(return_value=uncalled_match)

        collection_match = Mock()
        collection_match.group = Mock(side_effect=lambda x: {"PNAME": "Player1", "POT": "1.00"}.get(x))
        self.parser.re_collect_pot2 = Mock()
        self.parser.re_collect_pot2.search = Mock(return_value=collection_match)

        self.parser.readAction(self.hand, "PREFLOP")

        # Should add to existing walk_adjustments
        self.assertEqual(len(self.hand.walk_adjustments), 2)
        self.assertEqual(self.hand.walk_adjustments["ExistingPlayer"], Decimal("0.50"))
        self.assertEqual(self.hand.walk_adjustments["Player1"], Decimal("1.00"))


if __name__ == "__main__":
    unittest.main()
