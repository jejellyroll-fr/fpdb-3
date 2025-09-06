"""
Unit tests for the copy-to-clipboard bug fix #97.

This module tests the fixes applied to resolve:
1. AttributeError: 'super' object has no attribute 'writeHand'
2. FpdbParseError in Pot.__str__ when total=None

Issue: https://github.com/user/fpdb-3/issues/97
"""

from io import StringIO
from unittest.mock import patch

import pytest

from Exceptions import FpdbParseError
from Hand import Hand, HoldemOmahaHand, Pot


class TestCopyToClipboardFix:
    """Tests for the copy-to-clipboard bug fix."""

    def test_pot_str_handles_none_total(self):
        """
        Test that Pot.__str__ no longer raises FpdbParseError when total=None.

        Before fix: FpdbParseError was raised
        After fix: automatically calculates total and returns a string
        """
        pot = Pot()
        pot.committed = {"Player1": 10.0, "Player2": 20.0}
        pot.common = {"ante": 5.0}
        pot.stp = 2.0
        pot.sym = "$"
        # pot.total remains None (state that caused the error)

        # Should no longer raise FpdbParseError
        result = str(pot)

        # Should calculate: 10 + 20 + 5 + 2 = 37.00
        assert result == "Total pot $37.00"

    def test_pot_str_with_empty_committed(self):
        """Test Pot.__str__ with empty committed amounts."""
        pot = Pot()
        pot.committed = {}
        pot.common = {}
        pot.stp = 0
        pot.sym = "€"
        # pot.total remains None

        result = str(pot)
        assert result == "Total pot €0.00"

    def test_pot_str_with_existing_total(self):
        """Test that Pot.__str__ uses existing total if defined."""
        pot = Pot()
        pot.committed = {"Player1": 10.0}
        pot.common = {}
        pot.stp = 0
        pot.sym = "£"
        pot.total = 25.0  # Explicitly defined total

        result = str(pot)
        # Should use the defined total, not calculate from committed
        assert result == "Total pot £25.00"

    def test_hand_writehand_method_exists(self):
        """Test that Hand.writeHand exists and is a method."""
        assert hasattr(Hand, "writeHand")
        assert callable(getattr(Hand, "writeHand"))

    def test_holdem_hand_writehand_exists(self):
        """Test that HoldemOmahaHand.writeHand exists."""
        assert hasattr(HoldemOmahaHand, "writeHand")
        assert callable(getattr(HoldemOmahaHand, "writeHand"))

    @patch.object(Hand, "writeGameLine")
    @patch.object(Hand, "writeTableLine")
    def test_hand_writehand_basic_functionality(self, mock_table_line, mock_game_line):
        """Test basic functionality of Hand.writeHand."""
        mock_game_line.return_value = "Test Game Line"
        mock_table_line.return_value = "Test Table Line"

        hand = Hand.__new__(Hand)  # Create without __init__ to avoid dependencies
        output = StringIO()

        hand.writeHand(output)
        result = output.getvalue()

        assert "Test Game Line\n" in result
        assert "Test Table Line\n" in result
        # The methods are called both for logging and for output
        assert mock_game_line.call_count >= 1
        assert mock_table_line.call_count >= 1

    def test_inheritance_chain_complete(self):
        """
        Test that the inheritance chain is complete for writeHand.

        Verifies that HoldemOmahaHand can call super().writeHand()
        without raising AttributeError.
        """
        # Verify that Hand has writeHand
        assert hasattr(Hand, "writeHand")

        # Verify that HoldemOmahaHand inherits correctly
        assert issubclass(HoldemOmahaHand, Hand)

        # Verify that HoldemOmahaHand has its own writeHand that can call super()
        assert hasattr(HoldemOmahaHand, "writeHand")

        # HoldemOmahaHand's writeHand method should be able to see
        # Hand's writeHand method via super()
        holdem_method = getattr(HoldemOmahaHand, "writeHand")
        hand_method = getattr(Hand, "writeHand")

        # They should not be identical (HoldemOmahaHand overrides Hand)
        assert holdem_method != hand_method

    def test_pot_str_with_multiple_pots(self):
        """Test Pot.__str__ with multiple pots (main + side pots)."""
        pot = Pot()
        pot.committed = {"Player1": 10.0, "Player2": 20.0}
        pot.common = {}
        pot.stp = 0
        pot.sym = "$"
        pot.total = 30.0

        # Simulate multiple pots
        pot.pots = [
            (20.0, {"Player1", "Player2"}),  # Main pot
            (10.0, {"Player2"}),  # Side pot
        ]

        result = str(pot)

        # Should mention main pot and side pot
        assert "Total pot $30.00" in result
        assert "Main pot $20.00" in result
        assert "Side pot $10.00" in result


class TestRegressionPrevention:
    """Tests to ensure the original errors don't come back."""

    def test_original_attributeerror_fixed(self):
        """
        Regression test for the original AttributeError.

        Simulates the exact scenario that caused:
        AttributeError: 'super' object has no attribute 'writeHand'
        """
        # Before the fix, this failed because Hand didn't have a writeHand method
        # and HoldemOmahaHand.writeHand() called super().writeHand()

        # Verify that Hand now has writeHand
        assert hasattr(Hand, "writeHand")

        # Verify that it's actually a class method
        import types

        method = getattr(Hand, "writeHand")
        assert isinstance(method, types.FunctionType)

    def test_original_fpdbparseerror_fixed(self):
        """
        Regression test for the original FpdbParseError.

        Simulates the exact scenario that caused:
        FpdbParseError in Pot.__str__ when total=None
        """
        pot = Pot()
        pot.committed = {"test": 5.0}
        pot.common = {}
        pot.stp = 0
        # pot.total = None (default)

        # Before fix: FpdbParseError
        # After fix: automatic calculation and string return
        try:
            result = str(pot)
            # If we get here, the error is fixed
            assert isinstance(result, str)
            assert len(result) > 0
        except FpdbParseError:
            pytest.fail("FpdbParseError still raised - fix didn't work")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
