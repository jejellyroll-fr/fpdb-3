#!/usr/bin/env python3
"""Test script for the iPoker parser."""

import logging
from pathlib import Path

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
    """A PMU / iPoker FR table's size is only in the session header: it must still read 6-max, not 10.

    The file is synthetic, shaped as PMU writes a session: ``<tablesize>`` sits in the
    session's ``<general>``, which splitting the file into hands leaves behind.
    """
    file_path = str(
        Path(__file__).resolve().parents[1]
        / "regression-test-files/cash/iPoker/Flop/NLHE-6max-EUR-0.01-0.02-202607.tablesize.in.session.header.xml"
    )

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

    # Every hand, not only the first: the first fragment of the split still carries the
    # session header, the others do not.
    from fpdb_3_legacy.Hand import HoldemOmahaHand

    assert len(hands) == 2
    for hand_text in hands:
        hand = HoldemOmahaHand(config, parser, parser.sitename, gametype, hand_text)
        parser.readHandInfo(hand)
        assert hand.maxseats == 6


def test_first_hand_of_a_session_takes_its_own_gamecode_as_hand_id() -> None:
    """The bare ``code="..."`` pattern also matched ``<session sessioncode>``.

    Every iPoker file opens with a session tag, so the first hand of each file
    was stored under the session code instead of its own gamecode -- all nine
    corpus files were affected.
    """
    import re
    from pathlib import Path

    from fpdb_3_legacy.iPoker.base import iPoker

    path = Path(__file__).resolve().parents[1] / (
        "regression-test-files/cash/iPoker/Flop/LHE-10max-USD-0.10-0.20-201107.player.sitting.out.xml"
    )
    text = path.read_text(encoding="utf-8", errors="ignore")
    first_fragment = iPoker.re_split_hands.split(text)[0]

    session_code = re.search(r'sessioncode="(\d+)"', first_fragment).group(1)
    game_code = re.search(r'gamecode="(\d+)"', first_fragment).group(1)
    parsed = iPoker.re_hand_info.search(first_fragment).group("HID")

    assert parsed == game_code
    assert parsed != session_code
