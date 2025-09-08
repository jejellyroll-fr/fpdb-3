"""Tests for PokerStars _processAction method."""

import unittest
from unittest.mock import MagicMock, Mock

from PokerStarsToFpdb import PokerStars


class TestPokerStarsProcessAction(unittest.TestCase):
    """Test the _processAction method of PokerStars parser."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = Mock()
        self.parser = PokerStars(self.config)
        self.mock_hand = MagicMock()
        self.street = "PREFLOP"

    def test_process_fold_action(self):
        """Test processing a fold action."""
        mock_action = Mock()
        data = {"ATYPE": " folds", "PNAME": "Player1"}
        mock_action.group.side_effect = lambda key: data.get(key)
        mock_action.__getitem__ = Mock(side_effect=lambda key: data.get(key))

        self.parser._processAction(mock_action, self.mock_hand, self.street)

        self.mock_hand.addFold.assert_called_once_with(self.street, "Player1")

    def test_process_check_action(self):
        """Test processing a check action."""
        mock_action = Mock()
        data = {"ATYPE": " checks", "PNAME": "Player2"}
        mock_action.group.side_effect = lambda key: data.get(key)
        mock_action.__getitem__ = Mock(side_effect=lambda key: data.get(key))

        self.parser._processAction(mock_action, self.mock_hand, self.street)

        self.mock_hand.addCheck.assert_called_once_with(self.street, "Player2")

    def test_process_call_action(self):
        """Test processing a call action."""
        mock_action = Mock()
        data = {"ATYPE": " calls", "PNAME": "Player3", "BET": "$10.00"}
        mock_action.group.side_effect = lambda key: data.get(key)
        mock_action.__getitem__ = Mock(side_effect=lambda key: data.get(key))

        self.parser.clearMoneyString = Mock(return_value="10.00")

        self.parser._processAction(mock_action, self.mock_hand, self.street)

        self.mock_hand.addCall.assert_called_once_with(self.street, "Player3", "10.00")
        self.parser.clearMoneyString.assert_called_once_with("$10.00")

    def test_process_raise_action(self):
        """Test processing a raise action."""
        mock_action = Mock()
        data = {"ATYPE": " raises", "PNAME": "Player4"}
        mock_action.group.side_effect = lambda key: data.get(key)
        mock_action.__getitem__ = Mock(side_effect=lambda key: data.get(key))

        self.parser._processRaise = Mock()

        self.parser._processAction(mock_action, self.mock_hand, self.street)

        self.parser._processRaise.assert_called_once_with(mock_action, self.mock_hand, self.street, "Player4")

    def test_process_bet_action(self):
        """Test processing a bet action."""
        mock_action = Mock()
        data = {"ATYPE": " bets", "PNAME": "Player5", "BET": "$25.50"}
        mock_action.group.side_effect = lambda key: data.get(key)
        mock_action.__getitem__ = Mock(side_effect=lambda key: data.get(key))

        self.parser.clearMoneyString = Mock(return_value="25.50")

        self.parser._processAction(mock_action, self.mock_hand, self.street)

        self.mock_hand.addBet.assert_called_once_with(self.street, "Player5", "25.50")
        self.parser.clearMoneyString.assert_called_once_with("$25.50")

    def test_process_discard_action(self):
        """Test processing a discard action."""
        mock_action = Mock()
        data = {"ATYPE": " discards", "PNAME": "Player6", "BET": "2", "CARDS": "[7h 2s]"}
        mock_action.group.side_effect = lambda key: data.get(key)
        mock_action.__getitem__ = Mock(side_effect=lambda key: data.get(key))

        self.parser._processAction(mock_action, self.mock_hand, self.street)

        self.mock_hand.addDiscard.assert_called_once_with(self.street, "Player6", "2", "[7h 2s]")

    def test_process_stands_pat_action(self):
        """Test processing a stands pat action."""
        mock_action = Mock()
        data = {"ATYPE": " stands pat", "PNAME": "Player7", "CARDS": "[Kc Qd Jh Ts 9c]"}
        mock_action.group.side_effect = lambda key: data.get(key)
        mock_action.__getitem__ = Mock(side_effect=lambda key: data.get(key))

        self.parser._processAction(mock_action, self.mock_hand, self.street)

        self.mock_hand.addStandsPat.assert_called_once_with(self.street, "Player7", "[Kc Qd Jh Ts 9c]")

    def test_process_unknown_action(self):
        """Test processing an unknown action type."""
        mock_action = Mock()
        data = {"ATYPE": " unknown", "PNAME": "Player8"}
        mock_action.group.side_effect = lambda key: data.get(key)
        mock_action.__getitem__ = Mock(side_effect=lambda key: data.get(key))

        with self.assertLogs("pokerstars_parser", level="DEBUG") as cm:
            self.parser._processAction(mock_action, self.mock_hand, self.street)

        self.assertIn("Unimplemented readAction", cm.output[0])
        self.assertIn("Player8", cm.output[0])
        self.assertIn("unknown", cm.output[0])

    def test_process_action_different_streets(self):
        """Test processing actions on different streets."""
        mock_action = Mock()
        data = {"ATYPE": " folds", "PNAME": "Player1"}
        mock_action.group.side_effect = lambda key: data.get(key)
        mock_action.__getitem__ = Mock(side_effect=lambda key: data.get(key))

        for street in ["PREFLOP", "FLOP", "TURN", "RIVER"]:
            with self.subTest(street=street):
                self.mock_hand.reset_mock()
                self.parser._processAction(mock_action, self.mock_hand, street)
                self.mock_hand.addFold.assert_called_once_with(street, "Player1")

    def test_process_action_with_special_characters_in_name(self):
        """Test processing action with special characters in player name."""
        mock_action = Mock()
        data = {"ATYPE": " checks", "PNAME": "Player_123-$"}
        mock_action.group.side_effect = lambda key: data.get(key)
        mock_action.__getitem__ = Mock(side_effect=lambda key: data.get(key))

        self.parser._processAction(mock_action, self.mock_hand, self.street)

        self.mock_hand.addCheck.assert_called_once_with(self.street, "Player_123-$")

    def test_process_multiple_actions_sequence(self):
        """Test processing a sequence of different actions."""
        actions_data = [
            (" folds", "Player1", None),
            (" checks", "Player2", None),
            (" calls", "Player3", "$10.00"),
            (" bets", "Player4", "$20.00"),
        ]

        self.parser.clearMoneyString = Mock(side_effect=lambda x: x.replace("$", ""))

        for atype, pname, bet in actions_data:
            mock_action = Mock()
            data = {"ATYPE": atype, "PNAME": pname, "BET": bet}
            mock_action.group.side_effect = lambda key, d=data: d.get(key)
            mock_action.__getitem__ = Mock(side_effect=lambda key, d=data: d.get(key))

            self.parser._processAction(mock_action, self.mock_hand, self.street)

        # Verify all actions were called
        self.mock_hand.addFold.assert_called_once_with(self.street, "Player1")
        self.mock_hand.addCheck.assert_called_once_with(self.street, "Player2")
        self.mock_hand.addCall.assert_called_once_with(self.street, "Player3", "10.00")
        self.mock_hand.addBet.assert_called_once_with(self.street, "Player4", "20.00")


if __name__ == "__main__":
    unittest.main()
