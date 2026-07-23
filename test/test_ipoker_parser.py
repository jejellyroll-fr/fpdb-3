#!/usr/bin/env python3
"""Test script for the iPoker parser."""

import logging

import pytest

from fpdb_3_legacy.iPoker.base import iPoker

# Logging configuration
logging.basicConfig(level=logging.DEBUG, format="%(name)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)


def test_ipoker_table_title_without_table_name_is_safe() -> None:
    assert iPoker.getTableTitleRe("ring", None) == ""


@pytest.mark.parametrize("file_path", ["regression-test-files/cash/iPoker/Flop/6+Holdem-EUR-0.25-0.50-201702.txt"])
def test_ipoker_file(file_path) -> None:
    """Test one iPoker file."""
    # Read the file
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        with open(file_path, encoding="cp1252") as f:
            content = f.read()

    # Create the parser
    from fpdb_3_legacy.Configuration import Config

    config = Config()
    parser = iPoker(config, in_path=file_path, autostart=False)

    # Test game type detection
    assert parser.determineGameType(content)

    # Test hand splitting
    hands = parser.allHandsAsList()
    assert hands


def test_pmu_poker_tablesize() -> None:
    """Test that PMU Poker tablesize is correctly parsed as 6-max instead of falling back to 10-max."""
    file_path = "/Users/jde/Library/Containers/fr.pmu.poker.macos/Data/Library/Application Support/PMU PLAY/tripsfountain99/History/Data/Tables/5858157850.xml"
    import os

    if not os.path.exists(file_path):
        pytest.skip("PMU Poker table history file not found")

    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.iPoker.base import iPoker

    config = Config()
    parser = iPoker(config, autostart=False)
    parser.in_path = file_path

    # Read the file
    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    # Set the whole_file attribute as done by HandHistoryConverter
    parser.whole_file = content

    # Parse the game type from the header
    gametype = parser.determineGameType(content)
    assert gametype is not None
    assert gametype.get("seats") == "6" or parser.info.get("seats") == "6"

    # Split hands and parse one hand to verify hand.maxseats
    hands = parser.allHandsAsList()
    assert len(hands) > 0

    # Parse the first hand
    hand_text = hands[0]
    from fpdb_3_legacy.Hand import HoldemOmahaHand

    hand = HoldemOmahaHand(config, parser, parser.sitename, gametype, hand_text)

    parser.readHandInfo(hand)
    # The maxseats should be correctly parsed as 6
    assert hand.maxseats == 6
