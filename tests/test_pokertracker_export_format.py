"""What PokerTracker 4's *Export Hands* writes today, read back (#616).

iPoker comes out as ``GAME #`` text, with a table line that carries a number, a ``Table Info:``
line and a time marked ``/GMT``. Each tournament adds a ``PokerTracker 4 Tournament Summary`` file.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.Exceptions import FpdbParseError
from fpdb_3_legacy.IdentifySite import IdentifySite
from fpdb_3_legacy.Importer import FileImportResult
from fpdb_3_legacy.PokerTrackerSummary import PokerTrackerSummary
from fpdb_3_legacy.PokerTrackerToFpdb import PokerTracker
from fpdb_3_legacy.tracker_migration import _room, summarize

ROOT = Path(__file__).resolve().parents[1]


def _cash_hand(table: str = "Oslo, 560234179", opponent: str = "bob") -> str:
    return f"""GAME #9149549605 Version:26.7.1.25 Uncalled:Y Omaha PL €0.01/€0.02 2026-11-01 21:55:45/GMT
Table Info: Size: 6, Blinds: 0.01/0.02
Table {table}
Seat 1: alice (€2.00 in chips)
Seat 5: {opponent} (€6.07 in chips)  DEALER
{opponent}: Post SB €0.01
alice: Post BB €0.02
*** HOLE CARDS ***
Dealt to alice [C9 H5 H9 S9]
{opponent}: Fold
*** SUMMARY ***
Total pot €0.03 Rake €0.00
alice: wins €0.03
"""


SUMMARY = """PokerTracker 4 Tournament Summary
Site: {site}
Game: Holdem
Tournament #: 1145730368
Started: 2026/08/07 17:30:00
Finished: 2026/08/07 18:32:15
Buyin: €0.11
Bounty: €0.11
BountyVal: €0.11
Fee: €0.03
Prize Pool: €48.84
Initial Stack: 0
Table Type: MTT (6 max) Semi-Turbo PROGBOUNT
Tourney Type: No Limit
Players: 2

Place: 1, Player: alice, Won: €0.54,
Place: 2, Player: bob, Won: €0.00,
"""


@pytest.fixture(scope="module")
def config() -> Config:
    return Config(file=str(ROOT / "HUD_config.xml"))


def _parse(config, tmp_path, text: str) -> list:
    path = tmp_path / "export.txt"
    path.write_text(text, encoding="utf-8")
    return PokerTracker(config=config, in_path=str(path), autostart=True).getProcessedHands()


def test_a_cash_table_line_carrying_a_number_parses(config, tmp_path) -> None:
    hands = _parse(config, tmp_path, _cash_hand())

    assert len(hands) == 1
    assert hands[0].tablename == "Oslo"
    assert hands[0].sitename == "iPoker"


def test_a_table_info_line_is_not_the_table_name(config, tmp_path) -> None:
    assert _parse(config, tmp_path, _cash_hand("Oslo"))[0].tablename == "Oslo"


def test_a_header_marked_gmt_is_not_shifted(config, tmp_path) -> None:
    start = _parse(config, tmp_path, _cash_hand())[0].startTime

    assert start.replace(tzinfo=None) == datetime.datetime(2026, 11, 1, 21, 55, 45)


@pytest.mark.parametrize("opponent", ["maria01", "bet365fan", "skywalker"])
def test_a_player_name_does_not_choose_the_room(config, tmp_path, opponent) -> None:
    text = _cash_hand(opponent=opponent)

    assert _parse(config, tmp_path, text)[0].sitename == "iPoker"
    assert IdentifySite(config).detectiPokerSkin(text) == "iPoker"


def test_the_table_name_still_chooses_the_room(config) -> None:
    text = _cash_hand("Saratov, 560234179")

    assert PokerTracker(config=config, autostart=False).detectiPokerSkin(text) == "FDJ Poker"
    assert IdentifySite(config).detectiPokerSkin(text) == "FDJ Poker"


@pytest.mark.parametrize("site", ["iPoker", "GG Poker", "Winamax"])
def test_a_tournament_summary_of_each_exported_room_matches(site) -> None:
    match = PokerTrackerSummary.re_tourney_info.search(SUMMARY.format(site=site))

    assert match is not None
    assert PokerTrackerSummary.site_name_map[match.group("SITE")]


def test_a_summary_file_is_previewed_under_the_room_it_names(config, tmp_path) -> None:
    path = tmp_path / "T#1 - Summary.txt"
    path.write_text(SUMMARY.format(site="GG Poker"), encoding="utf-8")
    found = IdentifySite(config).idSite(str(path), path.read_text(encoding="utf-8"), "utf-8")

    assert _room(found, str(path)) == "GGPoker"


def test_summaries_join_their_room_and_are_not_counted_as_hands() -> None:
    results = {
        "hands.txt": FileImportResult("Winamax", stored=10),
        "T#1 - Summary.txt": FileImportResult("Winamax", summaries=1, is_summary_file=True),
        "T#2 - Summary.txt": FileImportResult("PokerTracker", errors=1, is_summary_file=True),
    }

    rooms = {room.site: room for room in summarize(results, SimpleNamespace(supported_sites={}))}

    assert (rooms["Winamax"].files, rooms["Winamax"].stored, rooms["Winamax"].tournament_summaries) == (2, 10, 1)
    # A summary whose room fpdb cannot place stays visible, with its error.
    assert (rooms["PokerTracker"].stored, rooms["PokerTracker"].errors) == (0, 1)


def test_an_unknown_room_in_a_header_is_still_refused(config, tmp_path) -> None:
    path = tmp_path / "export.txt"
    path.write_text("Some Other Poker Game #1: Hold'em NL $0.50/$1 01/01/2011 12:01:23\n", encoding="utf-8")
    parser = PokerTracker(config=config, autostart=False)

    with pytest.raises(FpdbParseError):
        parser.determineGameType(path.read_text(encoding="utf-8"))
