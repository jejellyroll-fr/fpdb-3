#!/usr/bin/env python3
"""Regression tests for iPoker tournament vs ring game detection.

iPoker tournaments whose XML has no <tournamentcode> tag (the majority format)
were misdetected as ring games: determineGameType set type="tour" from the
<tournamentname>/<place> markers, but _process_standard_tournament_info then
returned False (it required TOURNO from <tournamentcode> and a non-empty
<totalbuyin>), so _handle_ring_game_logic demoted them back to "ring".

The fix: fall back TOURNO to the tourNo already parsed from <tablename>, read the
total buy-in with the permissive re_buyin, and stop requiring TOTBUYIN to
classify a hand that is already known to be a tournament.
"""

from __future__ import annotations

import glob
import os
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.iPokerToFpdb import iPoker

TOUR_FILES = sorted(glob.glob("regression-test-files/tour/iPoker/**/*.txt", recursive=True))
CASH_FILES = sorted(glob.glob("regression-test-files/cash/iPoker/**/*.txt", recursive=True))


def _detect_type(config, filepath):
    """Run determineGameType on the first hand of an iPoker file."""
    with open(filepath, encoding="cp1252") as fh:
        content = fh.read()
    parser = iPoker(config, in_path=filepath, autostart=False)
    parser.whole_file = content
    first_hand = content.split("</game>")[0] + "</game>"
    gametype = parser.determineGameType(first_hand)
    return (gametype or {}).get("type"), parser


@pytest.fixture(scope="module")
def config():
    return Config()


@pytest.mark.skipif(not TOUR_FILES, reason="no iPoker tournament fixtures found")
@pytest.mark.parametrize("filepath", TOUR_FILES, ids=lambda p: os.path.basename(p))
def test_tournament_files_detected_as_tour(config, filepath):
    """Every iPoker tournament fixture must be classified as a tournament."""
    game_type, parser = _detect_type(config, filepath)
    assert game_type == "tour", f"{os.path.basename(filepath)} misdetected as {game_type!r}"
    # tourNo must be parsed even without a <tournamentcode> tag.
    assert (parser.tinfo or {}).get("tourNo"), "tourNo should be parsed from the table name"


@pytest.mark.skipif(not CASH_FILES, reason="no iPoker cash fixtures found")
@pytest.mark.parametrize("filepath", CASH_FILES, ids=lambda p: os.path.basename(p))
def test_cash_files_not_detected_as_tour(config, filepath):
    """Ring games must not be promoted to tournaments by the relaxed check."""
    game_type, _ = _detect_type(config, filepath)
    assert game_type != "tour", f"{os.path.basename(filepath)} wrongly detected as tour"


def test_tournament_results_keep_decimal_multiplier(config) -> None:
    parser = iPoker(config, autostart=False)
    parser.whole_file = """
<tournamentcode>826763510</tournamentcode>
<tournamentname>Twister 0.20€</tournamentname>
<buyin>0,20€</buyin>
<rewarddrawn>0,80€</rewarddrawn>
<win>1,20€</win>
"""

    result = parser._parse_tournament_data(parser.whole_file)

    assert result["buyin_amount"] == Decimal("0.20")
    assert result["hero_winnings"] == Decimal("1.20")
    assert result["multiplier"] == Decimal("4")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
