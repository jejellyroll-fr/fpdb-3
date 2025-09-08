"""Tests for PokerStars _processRaise method."""

import unittest
from unittest.mock import MagicMock, Mock

from PokerStarsToFpdb import PokerStars


class TestPokerStarsProcessRaise(unittest.TestCase):
    """Test the _processRaise method of PokerStars parser."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = Mock()
        self.parser = PokerStars(self.config)
        self.mock_hand = MagicMock()
        self.street = "PREFLOP"
        self.pname = "Player1"

    def test_process_raise_with_betto(self):
        """Test _processRaise when BETTO is present (raise to amount)."""
        mock_action = {"BETTO": "$50.00", "BET": None}

        self.parser.clearMoneyString = Mock(return_value="50.00")

        self.parser._processRaise(mock_action, self.mock_hand, self.street, self.pname)

        self.mock_hand.addRaiseTo.assert_called_once_with(self.street, self.pname, "50.00")
        self.mock_hand.addCallandRaise.assert_not_called()
        self.parser.clearMoneyString.assert_called_once_with("$50.00")

    def test_process_raise_with_bet(self):
        """Test _processRaise when BET is present (call and raise amount)."""
        mock_action = {"BETTO": None, "BET": "$25.00"}

        self.parser.clearMoneyString = Mock(return_value="25.00")

        self.parser._processRaise(mock_action, self.mock_hand, self.street, self.pname)

        self.mock_hand.addCallandRaise.assert_called_once_with(self.street, self.pname, "25.00")
        self.mock_hand.addRaiseTo.assert_not_called()
        self.parser.clearMoneyString.assert_called_once_with("$25.00")

    def test_process_raise_betto_priority(self):
        """Test that BETTO takes priority when both BETTO and BET are present."""
        mock_action = {"BETTO": "$100.00", "BET": "$50.00"}

        self.parser.clearMoneyString = Mock(return_value="100.00")

        self.parser._processRaise(mock_action, self.mock_hand, self.street, self.pname)

        self.mock_hand.addRaiseTo.assert_called_once_with(self.street, self.pname, "100.00")
        self.mock_hand.addCallandRaise.assert_not_called()
        self.parser.clearMoneyString.assert_called_once_with("$100.00")

    def test_process_raise_neither_betto_nor_bet(self):
        """Test _processRaise when neither BETTO nor BET is present."""
        mock_action = {"BETTO": None, "BET": None}

        self.parser._processRaise(mock_action, self.mock_hand, self.street, self.pname)

        self.mock_hand.addRaiseTo.assert_not_called()
        self.mock_hand.addCallandRaise.assert_not_called()

    def test_process_raise_different_streets(self):
        """Test _processRaise on different streets."""
        mock_action = {"BETTO": "$30.00", "BET": None}

        self.parser.clearMoneyString = Mock(return_value="30.00")

        for street in ["PREFLOP", "FLOP", "TURN", "RIVER"]:
            with self.subTest(street=street):
                self.mock_hand.reset_mock()
                self.parser.clearMoneyString.reset_mock()

                self.parser._processRaise(mock_action, self.mock_hand, street, self.pname)

                self.mock_hand.addRaiseTo.assert_called_once_with(street, self.pname, "30.00")

    def test_process_raise_different_players(self):
        """Test _processRaise with different player names."""
        mock_action = {"BETTO": "$40.00", "BET": None}

        self.parser.clearMoneyString = Mock(return_value="40.00")

        for pname in ["Player1", "Hero", "Villain", "Player_123"]:
            with self.subTest(pname=pname):
                self.mock_hand.reset_mock()
                self.parser.clearMoneyString.reset_mock()

                self.parser._processRaise(mock_action, self.mock_hand, self.street, pname)

                self.mock_hand.addRaiseTo.assert_called_once_with(self.street, pname, "40.00")

    def test_process_raise_money_clearing(self):
        """Test that money strings are properly cleared."""
        test_cases = [("$10.50", "10.50"), ("€25.75", "25.75"), ("£100", "100"), ("1,250.00", "1250.00")]

        for raw_amount, expected_cleared in test_cases:
            with self.subTest(raw_amount=raw_amount):
                mock_action = {"BETTO": raw_amount, "BET": None}

                self.parser.clearMoneyString = Mock(return_value=expected_cleared)
                self.mock_hand.reset_mock()

                self.parser._processRaise(mock_action, self.mock_hand, self.street, self.pname)

                self.parser.clearMoneyString.assert_called_once_with(raw_amount)
                self.mock_hand.addRaiseTo.assert_called_once_with(self.street, self.pname, expected_cleared)

    def test_process_raise_bet_money_clearing(self):
        """Test that BET money strings are properly cleared."""
        mock_action = {"BETTO": None, "BET": "$15.25"}

        self.parser.clearMoneyString = Mock(return_value="15.25")

        self.parser._processRaise(mock_action, self.mock_hand, self.street, self.pname)

        self.parser.clearMoneyString.assert_called_once_with("$15.25")
        self.mock_hand.addCallandRaise.assert_called_once_with(self.street, self.pname, "15.25")


if __name__ == "__main__":
    unittest.main()
