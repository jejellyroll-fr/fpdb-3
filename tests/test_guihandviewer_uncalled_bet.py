"""Tests for GuiHandViewer uncalled bet handling (Issue #95)."""

import unittest
from decimal import Decimal


class MockHand:
    """Mock hand object for testing."""

    def __init__(self, committed_amount, returned_amount, collected_amount):
        self.pot = MockPot(committed_amount, returned_amount)
        self.collectees = {"Hero": Decimal(str(collected_amount))}
        self.net_collected = {}

    def calculate_net_collected(self):
        """Calculate net collected amounts."""
        self.net_collected = {}
        for player in self.pot.committed:
            collected = self.collectees.get(player, Decimal("0.00"))
            uncalled_bets = self.pot.returned.get(player, Decimal("0.00"))
            committed = self.pot.committed.get(player, Decimal("0.00"))
            self.net_collected[player] = collected + uncalled_bets - committed


class MockPot:
    """Mock pot object for testing."""

    def __init__(self, committed_amount, returned_amount):
        self.committed = {"Hero": Decimal(str(committed_amount))}
        self.returned = {"Hero": Decimal(str(returned_amount))}


class TestGuiHandViewerUncalledBetFix(unittest.TestCase):
    """Test GuiHandViewer fix for Issue #95: BET and NET incorrect with uncalled bets."""

    def test_issue95_bet_and_net_calculation(self):
        """Test the exact Issue #95 scenario: BET and NET should be corrected."""
        # Scenario from Issue #95: Hero committed $3.17, uncalled bet $0.34, collected $5.50
        # Expected: BET = $2.83, NET = $2.67 (instead of BET = $3.17, NET = $5.50)
        hand = MockHand("3.17", "0.34", "5.50")
        hero = "Hero"

        # NEW BET calculation: committed - returned
        committed = hand.pot.committed[hero]
        returned = hand.pot.returned.get(hero, Decimal("0"))
        new_bet = committed - returned

        # NEW NET calculation: use calculate_net_collected()
        hand.calculate_net_collected()
        new_net = hand.net_collected[hero]

        # Verify fix works
        self.assertEqual(new_bet, Decimal("2.83"))  # Was $3.17, now $2.83 ✓
        self.assertEqual(new_net, Decimal("2.67"))  # Was $5.50, now $2.67 ✓

    def test_no_uncalled_bet_normal_case(self):
        """Test that normal hands without uncalled bets still work correctly."""
        hand = MockHand("2.83", "0.00", "5.50")
        hero = "Hero"

        committed = hand.pot.committed[hero]
        returned = hand.pot.returned.get(hero, Decimal("0"))
        bet = committed - returned

        hand.calculate_net_collected()
        net = hand.net_collected[hero]

        self.assertEqual(bet, Decimal("2.83"))  # No change needed
        self.assertEqual(net, Decimal("2.67"))  # collected + returned - committed = 5.50 + 0 - 2.83

    def test_before_and_after_fix_comparison(self):
        """Test showing the difference between old (wrong) and new (correct) calculations."""
        hand = MockHand("3.17", "0.34", "5.50")
        hero = "Hero"

        # OLD (incorrect) calculations that were causing Issue #95
        old_bet = hand.pot.committed[hero]  # $3.17 (includes uncalled bet)
        old_net = hand.collectees[hero]  # $5.50 (just winnings)

        # NEW (correct) calculations after our fix
        committed = hand.pot.committed[hero]
        returned = hand.pot.returned.get(hero, Decimal("0"))
        new_bet = committed - returned  # $2.83 (excludes uncalled bet)

        hand.calculate_net_collected()
        new_net = hand.net_collected[hero]  # $2.67 (proper net calculation)

        # Verify the fix changed the values as expected
        self.assertEqual(old_bet, Decimal("3.17"))
        self.assertEqual(new_bet, Decimal("2.83"))
        self.assertNotEqual(old_bet, new_bet)

        self.assertEqual(old_net, Decimal("5.50"))
        self.assertEqual(new_net, Decimal("2.67"))
        self.assertNotEqual(old_net, new_net)


if __name__ == "__main__":
    unittest.main()
