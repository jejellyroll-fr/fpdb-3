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
import tempfile
from decimal import Decimal

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.iPokerToFpdb import iPoker


def _fixtures(kind: str) -> list[str]:
    """Every iPoker fixture of that kind. The corpus mixes .txt and .xml, and
    globbing only .txt left the newer XML exports untested."""
    return sorted(
        glob.glob(f"regression-test-files/{kind}/iPoker/**/*.txt", recursive=True)
        + glob.glob(f"regression-test-files/{kind}/iPoker/**/*.xml", recursive=True),
    )


TOUR_FILES = _fixtures("tour")
CASH_FILES = _fixtures("cash")


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


@pytest.fixture(scope="module")
def isolated_config():
    """Config whose database is a throwaway SQLite file.

    Parsing a tournament hand with autostart stores its TourneySummary, so a
    bare Config() would write into the user's own database.
    """
    from fpdb_3_legacy.Database import Database

    cfg = Config()
    db_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
    db_file.close()
    params = cfg.get_db_parameters().copy()
    params.update(
        {
            "db-backend": Database.SQLITE,
            "db-server": "sqlite",
            "db-databaseName": db_file.name,
            "db-host": "",
            "db-user": "",
            "db-password": "",
        },
    )
    cfg.get_db_parameters = lambda: params
    database = Database(cfg)
    database.recreate_tables()
    database.close_connection()
    yield cfg
    os.unlink(db_file.name)


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


def test_the_parenthesised_tournament_number_is_read(config) -> None:
    """Newer exports write "Hyper Turbo (500 Chips) (#16727068)".

    Neither the trailing-digits pattern nor the comma split found the number
    there, so the tournament check gave up and the hand was demoted to a ring
    game - a sit'n'go imported as a cash hand.
    """
    filepath = "regression-test-files/tour/iPoker/Flop/NLHE-USD-SNG-100-5-201610.new.tourno.format.xml"
    game_type, parser = _detect_type(config, filepath)

    assert game_type == "tour"
    assert parser.tinfo["tourNo"] == "16727068"


def test_the_hand_keeps_the_number_parsed_from_the_table_name(isolated_config) -> None:
    """readTourneyResults must not blank a tourNo readHandInfo already resolved.

    _parse_tournament_data only looked at <tournamentcode>; exports without that
    element ended up overwriting the number from <tablename> with None, and the
    hand was stored attached to no tournament at all.
    """
    filepath = "regression-test-files/tour/iPoker/Flop/NLHE-USD-MTT-Freeroll-201107.txt"
    parser = iPoker(isolated_config, in_path=filepath, autostart=True)

    hands = parser.getProcessedHands()

    assert hands
    assert all(hand.tourNo == "611669111" for hand in hands)


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
