#!/usr/bin/env python3
"""Test script for the iPoker parser."""

import logging

import pytest

from PokerTrackerToFpdb import PokerTracker

# Logging configuration
logging.basicConfig(level=logging.DEBUG, format="%(name)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)


@pytest.mark.parametrize("file_path", ["regression-test-files/cash/iPoker/Flop/6+Holdem-EUR-0.25-0.50-201702.txt"])
def test_ipoker_file(file_path) -> bool | None:
    """Test one iPoker file."""
    try:
        # Read the file
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(file_path, encoding="cp1252") as f:
                content = f.read()

        # Create the parser
        from Configuration import Config

        config = Config()
        parser = PokerTracker(config, autostart=False)
        parser.readFile(file_path)

        # Test site detection
        site_match = parser.re_Site.search(content)
        if not site_match:
            return False

        # Test game type detection
        try:
            parser.determineGameType(content)
        except Exception:
            return False

        # Test hand splitting
        hands = parser.allHandsAsList()

        return len(hands) > 0

    except Exception:
        import traceback

        traceback.print_exc()
        return False
