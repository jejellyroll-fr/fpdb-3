import os
import sys
import unittest
from unittest.mock import Mock

# Add the parent directory to the path to import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PokerStarsToFpdb import PokerStars


class TestAddCollectPotWithAdjustment(unittest.TestCase):
    """Test cases for the _addCollectPotWithAdjustment method."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = Mock()
        self.parser = PokerStars(self.config, "PokerStars", "USD")

    def _create_mock_hand(self, pot_stp=0):
        """Create a mock hand object for testing."""
        hand = Mock()
        hand.pot = Mock()
        hand.pot.stp = pot_stp
        hand.addCollectPot = Mock()
        return hand

    def _create_mock_match(self, pot_amount, player_name):
        """Create a mock regex match object."""
        match = Mock()
        match.group = Mock(side_effect=lambda x: pot_amount if x == "POT" else player_name)
        match.__getitem__ = Mock(side_effect=lambda x: pot_amount if x == "POT" else player_name)
        return match

    def test_no_adjustments_normal_collect(self):
        """Test normal pot collection without any Bovada adjustments."""
        hand = self._create_mock_hand()
        match = self._create_mock_match("$10.50", "Player1")
        adjustments = (False, False, 0, 0)

        # Mock clearMoneyString to return clean amount
        self.parser.clearMoneyString = Mock(return_value="10.50")

        self.parser._addCollectPotWithAdjustment(hand, match, adjustments)

        # Verify addCollectPot called with original pot amount
        hand.addCollectPot.assert_called_once_with(player="Player1", pot="10.50")

    def test_bovada_uncalled_v1_adjustment_applied(self):
        """Test Bovada uncalled v1 adjustment when conditions are met."""
        hand = self._create_mock_hand(pot_stp=5.0)  # hand.pot.stp = 5.0
        match = self._create_mock_match("$15.00", "Player2")
        adjustments = (True, False, 10.0, 2.0)  # bovada_uncalled_v1=True, blindsantes=10.0, adjustment=2.0

        # Mock clearMoneyString to return clean amount
        self.parser.clearMoneyString = Mock(return_value="15.00")

        self.parser._addCollectPotWithAdjustment(hand, match, adjustments)

        # Pot (15.0) == blindsantes (10.0) + hand.pot.stp (5.0), so adjustment should be applied
        # Final pot = 15.0 - 2.0 = 13.0
        hand.addCollectPot.assert_called_once_with(player="Player2", pot="13.0")

    def test_bovada_uncalled_v1_no_adjustment_when_condition_not_met(self):
        """Test Bovada uncalled v1 doesn't adjust when pot != blindsantes + stp."""
        hand = self._create_mock_hand(pot_stp=5.0)  # hand.pot.stp = 5.0
        match = self._create_mock_match("$20.00", "Player3")
        adjustments = (True, False, 10.0, 2.0)  # bovada_uncalled_v1=True, blindsantes=10.0, adjustment=2.0

        # Mock clearMoneyString to return clean amount
        self.parser.clearMoneyString = Mock(return_value="20.00")

        self.parser._addCollectPotWithAdjustment(hand, match, adjustments)

        # Pot (20.0) != blindsantes (10.0) + hand.pot.stp (5.0), so no adjustment
        hand.addCollectPot.assert_called_once_with(player="Player3", pot="20.00")

    def test_bovada_uncalled_v2_doubles_pot(self):
        """Test Bovada uncalled v2 doubles the pot amount."""
        hand = self._create_mock_hand()
        match = self._create_mock_match("$7.50", "Player4")
        adjustments = (False, True, 0, 0)  # bovada_uncalled_v2=True

        # Mock clearMoneyString to return clean amount
        self.parser.clearMoneyString = Mock(return_value="7.50")

        self.parser._addCollectPotWithAdjustment(hand, match, adjustments)

        # Pot should be doubled: 7.5 * 2 = 15.0
        hand.addCollectPot.assert_called_once_with(player="Player4", pot="15.0")

    def test_bovada_uncalled_v1_takes_precedence_over_v2(self):
        """Test that bovada_uncalled_v1 condition takes precedence over v2."""
        hand = self._create_mock_hand(pot_stp=3.0)  # hand.pot.stp = 3.0
        match = self._create_mock_match("$8.00", "Player5")
        adjustments = (True, True, 5.0, 1.5)  # Both v1 and v2 are True

        # Mock clearMoneyString to return clean amount
        self.parser.clearMoneyString = Mock(return_value="8.00")

        self.parser._addCollectPotWithAdjustment(hand, match, adjustments)

        # Pot (8.0) == blindsantes (5.0) + hand.pot.stp (3.0), so v1 adjustment applied
        # Final pot = 8.0 - 1.5 = 6.5 (not doubled)
        hand.addCollectPot.assert_called_once_with(player="Player5", pot="6.5")

    def test_complex_pot_amount_with_currency_symbol(self):
        """Test handling of complex pot amounts with currency symbols."""
        hand = self._create_mock_hand()
        match = self._create_mock_match("€125.75", "PlayerEur")
        adjustments = (False, True, 0, 0)  # bovada_uncalled_v2=True

        # Mock clearMoneyString to handle currency conversion
        self.parser.clearMoneyString = Mock(return_value="125.75")

        self.parser._addCollectPotWithAdjustment(hand, match, adjustments)

        # Verify clearMoneyString was called with the currency amount
        self.parser.clearMoneyString.assert_called_once_with("€125.75")

        # Pot should be doubled: 125.75 * 2 = 251.5
        hand.addCollectPot.assert_called_once_with(player="PlayerEur", pot="251.5")

    def test_zero_pot_amount(self):
        """Test handling of zero pot amount."""
        hand = self._create_mock_hand(pot_stp=0)
        match = self._create_mock_match("$0.00", "Player6")
        adjustments = (True, False, 0.0, 0.5)  # bovada_uncalled_v1=True

        # Mock clearMoneyString to return clean amount
        self.parser.clearMoneyString = Mock(return_value="0.00")

        self.parser._addCollectPotWithAdjustment(hand, match, adjustments)

        # Pot (0.0) == blindsantes (0.0) + hand.pot.stp (0.0), so adjustment applied
        # Final pot = 0.0 - 0.5 = -0.5
        hand.addCollectPot.assert_called_once_with(player="Player6", pot="-0.5")

    def test_decimal_calculations_precision(self):
        """Test decimal precision in calculations."""
        hand = self._create_mock_hand(pot_stp=2.25)
        match = self._create_mock_match("$5.75", "Player7")
        adjustments = (True, False, 3.50, 0.33)  # bovada_uncalled_v1=True

        # Mock clearMoneyString to return clean amount
        self.parser.clearMoneyString = Mock(return_value="5.75")

        self.parser._addCollectPotWithAdjustment(hand, match, adjustments)

        # Pot (5.75) == blindsantes (3.50) + hand.pot.stp (2.25), so adjustment applied
        # Final pot = 5.75 - 0.33 = 5.42
        hand.addCollectPot.assert_called_once_with(player="Player7", pot="5.42")

    def test_large_pot_amounts(self):
        """Test handling of large pot amounts."""
        hand = self._create_mock_hand()
        match = self._create_mock_match("$9999.99", "HighRoller")
        adjustments = (False, True, 0, 0)  # bovada_uncalled_v2=True

        # Mock clearMoneyString to return clean amount
        self.parser.clearMoneyString = Mock(return_value="9999.99")

        self.parser._addCollectPotWithAdjustment(hand, match, adjustments)

        # Pot should be doubled: 9999.99 * 2 = 19999.98
        hand.addCollectPot.assert_called_once_with(player="HighRoller", pot="19999.98")

    def test_player_name_with_special_characters(self):
        """Test handling of player names with special characters."""
        hand = self._create_mock_hand()
        match = self._create_mock_match("$12.34", "Player_123-ABC")
        adjustments = (False, False, 0, 0)  # No adjustments

        # Mock clearMoneyString to return clean amount
        self.parser.clearMoneyString = Mock(return_value="12.34")

        self.parser._addCollectPotWithAdjustment(hand, match, adjustments)

        # Verify player name is passed correctly
        hand.addCollectPot.assert_called_once_with(player="Player_123-ABC", pot="12.34")

    def test_floating_point_edge_case(self):
        """Test floating point comparison edge case."""
        hand = self._create_mock_hand(pot_stp=1.1)
        match = self._create_mock_match("$3.30", "Player8")
        # blindsantes + pot_stp = 2.2 + 1.1 = 3.3, but floating point precision means 3.30 != 3.3
        adjustments = (True, False, 2.2, 0.1)  # bovada_uncalled_v1=True

        # Mock clearMoneyString to return clean amount
        self.parser.clearMoneyString = Mock(return_value="3.30")

        self.parser._addCollectPotWithAdjustment(hand, match, adjustments)

        # Due to floating point precision, condition is not met, so no adjustment
        hand.addCollectPot.assert_called_once_with(player="Player8", pot="3.30")


if __name__ == "__main__":
    unittest.main()
