#!/usr/bin/env python3

"""
Tests for specific error cases in PokerStars parsing.
These tests verify handling of problematic hands identified in import reports.
"""

import os
import sys
import unittest

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Configuration import Config
from PokerStarsToFpdb import PokerStars


class TestPokerStarsErrorCases(unittest.TestCase):
    """Tests for error cases in PokerStars parsing"""

    def setUp(self):
        """Test setup"""
        self.config = Config()
        self.regression_files_dir = os.path.join(
            os.path.dirname(__file__), "..", "regression-test-files", "cash", "Stars"
        )

    def test_cancelled_hand_regex(self):
        """Test: Cancelled hand detection regex works"""
        # Create minimal parser instance
        parser = PokerStars(self.config, "dummy")

        cancelled_text = "Hand cancelled"
        self.assertTrue(parser.re_cancelled.search(cancelled_text))

        normal_text = "Hand completed"
        self.assertFalse(parser.re_cancelled.search(normal_text))

    def test_empty_card_regex(self):
        """Test: Empty card detection regex works"""
        parser = PokerStars(self.config, "dummy")

        empty_card_text = "*** TURN *** [3c Jd 6d] []"
        self.assertTrue(parser.re_empty_card.search(empty_card_text))

        normal_card_text = "*** TURN *** [3c Jd 6d] [5s]"
        self.assertFalse(parser.re_empty_card.search(normal_card_text))

    def test_cancelled_hand_draw_file(self):
        """Test: Draw file with cancelled hand"""
        file_path = "Draw/3-Draw-Limit-USD-1-2-200809.Hand.cancelled.txt"
        full_path = os.path.join(self.regression_files_dir, file_path)

        with open(full_path) as f:
            content = f.read()

        parser = PokerStars(self.config, "dummy")
        self.assertTrue(parser.re_cancelled.search(content), f"Regex should detect cancelled hand in {file_path}")

    def test_cancelled_hand_flop_file(self):
        """Test: Flop file with cancelled hand"""
        file_path = "Flop/LO8-6max-USD-0.05-0.10-20090315.Hand-cancelled.txt"
        full_path = os.path.join(self.regression_files_dir, file_path)

        with open(full_path) as f:
            content = f.read()

        parser = PokerStars(self.config, "dummy")
        self.assertTrue(parser.re_cancelled.search(content), f"Regex should detect cancelled hand in {file_path}")

    def test_blank_card_plo_file(self):
        """Test: PLO file with empty card"""
        file_path = "Flop/6-Card-PLO-6max-USD-0.10-0.25-202208.empty.turncard.txt"
        full_path = os.path.join(self.regression_files_dir, file_path)

        with open(full_path) as f:
            content = f.read()

        parser = PokerStars(self.config, "dummy")
        self.assertTrue(parser.re_empty_card.search(content), f"Regex should detect empty card in {file_path}")

    def test_partial_hand_plo_file(self):
        """Test: PLO file with partial hand"""
        file_path = "Flop/PLO-6max-USD-2.00-4.00-201403.2.partial.txt"
        full_path = os.path.join(self.regression_files_dir, file_path)

        with open(full_path) as f:
            content = f.read()

        self.assertIn("*** FLOP ***", content, f"File {file_path} should contain a flop")

        lines = content.split("\n")
        incomplete_found = any(
            line.startswith("*** FLOP ***") and i > 0 and (line.endswith(" [") or line.endswith(" "))
            for i, line in enumerate(lines)
        )

        self.assertTrue(
            incomplete_found or "*** FLOP *** [Js 3d " in content, f"File {file_path} should have incomplete data"
        )

    def test_partial_hand_observed_file(self):
        """Test: PLO file with observed partial hand"""
        file_path = "Flop/PLO-6max-USD-200-400-201510.partial.observed.txt"
        full_path = os.path.join(self.regression_files_dir, file_path)

        with open(full_path) as f:
            content = f.read()

        self.assertIn("*** FLOP ***", content, f"File {file_path} should contain a flop")


if __name__ == "__main__":
    unittest.main()
