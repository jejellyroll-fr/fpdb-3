"""A lottery tournament's hands and summary, imported together, describe one tournament.

Real 2026 files (anonymised: the hero is "Hero", the opponents alice and bob)
showed three ways the summary and the hands drifted apart:

* Unibet summaries name the hero with the account token the hand histories
  carry ("Hero[Unibet_...] finished"); the hand converter strips it, the
  summary converter did not, so the result went to a player with no hands;
* a Winamax summary whose game came from its Levels line -- every recent one --
  had no tournament name, so an Expresso was never recognised as a lottery;
* WinamaxSummary reset the lottery flag and multiplier after parsing, and the
  hands' multiplier of 1 outvoted the summary's when the two were merged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden

REPO = Path(__file__).resolve().parent.parent
EXPRESSO_HANDS = REPO / "tests" / "fixtures" / "hands" / "winamax" / "expresso_2026.txt"
EXPRESSO_SUMMARY = REPO / "regression-test-files" / "summaries" / "Winamax" / "NLHE-EUR-Expresso-1-202604.lottery.txt"
POWER_SPIN_HANDS = REPO / "tests" / "fixtures" / "hands" / "unibet" / "power_spin_2026.txt"
MANUAL_SPIN_HANDS = REPO / "tests" / "fixtures" / "hands" / "unibet" / "manual_export_power_spin_025_2026.txt"
MANUAL_SPIN_SUMMARIES = REPO / "tests" / "fixtures" / "summaries" / "unibet" / "manual_export_power_spin_025_2026.txt"
POWER_SPIN_SUMMARY = (
    REPO / "regression-test-files" / "summaries" / "Unibet" / "NLHE-EUR-PowerSpin-10-202605.lottery.txt"
)

TOURNEY_TYPES = "SELECT buyin, fee, maxSeats, sng, lottery, multiplier FROM TourneyTypes"
TOURNEYS = "SELECT siteTourneyNo, tourneyName, entries, prizepool FROM Tourneys"
RESULTS = (
    "SELECT p.name, tp.rank, tp.winnings FROM TourneysPlayers tp JOIN Players p ON p.id = tp.playerId "
    "WHERE tp.rank IS NOT NULL ORDER BY tp.rank"
)
PLAYER_NAMES = "SELECT name FROM Players ORDER BY name"
HERO_HANDS = (
    "SELECT COUNT(*) FROM HandsPlayers hp JOIN Players p ON p.id = hp.playerId "
    "JOIN Hands h ON h.id = hp.handId WHERE p.name = 'Hero' AND h.tourneyId IS NOT NULL"
)


def _import(directory: Path, *files: Path, unibet_hero: str | None = None):
    config = golden.build_config(directory)
    if unibet_hero:
        config.supported_sites["Unibet"].screen_name = unibet_hero
    Database(config).recreate_tables()
    db = Database(config)
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    for path in files:
        assert importer.addImportFile(str(path), "auto"), f"{path.name} was not recognised"
    importer.runImport()
    # The importer closes its connection when it is done.
    return Database(config)


def _rows(db, statement: str) -> list[tuple]:
    cursor = db.get_cursor()
    cursor.execute(statement)
    return [tuple(row) for row in cursor.fetchall()]


@pytest.mark.parametrize(
    "files",
    [(EXPRESSO_HANDS, EXPRESSO_SUMMARY), (EXPRESSO_SUMMARY, EXPRESSO_HANDS)],
    ids=["hands-first", "summary-first"],
)
def test_expresso_is_one_lottery_tournament(tmp_path: Path, files: tuple[Path, Path]) -> None:
    db = _import(tmp_path, *files)

    # 0.93 + 0.07 for a 3 prize pool: a x3 lottery, whatever came first.
    assert _rows(db, TOURNEY_TYPES) == [(93, 7, 3, 1, 1, 3)]
    assert _rows(db, TOURNEYS) == [(1096056742, "Expresso", 3, 300)]
    assert _rows(db, RESULTS) == [("Hero", 1, 300)]


def test_power_spin_result_goes_to_the_hands_player(tmp_path: Path) -> None:
    db = _import(tmp_path, POWER_SPIN_HANDS, POWER_SPIN_SUMMARY)

    # A 30 EUR pool for a 10 EUR spin: a x3 lottery sit-and-go (#729).
    assert _rows(db, TOURNEY_TYPES) == [(930, 70, 3, 1, 1, 3)]
    assert _rows(db, TOURNEYS) == [(83499742, None, 3, 3000)]
    assert _rows(db, RESULTS) == [("Hero", 1, 3000), ("bob", 2, 0), ("alice", 3, 0)]
    # One hero, whose hands and result are the same player's.
    assert _rows(db, PLAYER_NAMES) == [("Hero",), ("alice",), ("bob",)]
    assert _rows(db, HERO_HANDS) == [(8,)]


def test_a_manual_export_holds_several_power_spins(tmp_path: Path) -> None:
    # The History tab's export (#729): a banner, then every tournament of the
    # period. Its summaries name the hero by account token alone, so the
    # configured screen name links them to the hands.
    db = _import(tmp_path, MANUAL_SPIN_HANDS, MANUAL_SPIN_SUMMARIES, unibet_hero="Hero")

    # 0.23 + 0.02 for a 0.50 pool: a x2 lottery.
    assert _rows(db, TOURNEY_TYPES) == [(23, 2, 3, 1, 1, 2)]
    assert sorted(_rows(db, TOURNEYS)) == [(89646001, None, 3, 50), (89646054, None, 3, 50)]
    hero_results = _rows(
        db,
        "SELECT t.siteTourneyNo, tp.rank FROM TourneysPlayers tp JOIN Players p ON p.id = tp.playerId "
        "JOIN Tourneys t ON t.id = tp.tourneyId WHERE p.name = 'Hero' ORDER BY t.siteTourneyNo",
    )
    assert hero_results == [(89646001, 3), (89646054, 1)]
