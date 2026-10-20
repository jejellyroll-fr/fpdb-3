"""The #440 repair brings a pre-fix iPoker database back to a clean import.

Each database here is built for real: the files are imported with the pattern
the converter used before 2026-07-25, which stored the first hand of every
file under its session code, and then imported again with the fixed parser,
which adds that hand a second time under its gamecode. The repaired database
must hold exactly the hands a single clean import holds.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
from pathlib import Path

import pytest

from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.iPoker.base import iPoker
from tests.helpers import analytics_golden as golden
from tools import repair_ipoker_session_ids as repair_tool

REPO = Path(__file__).resolve().parent.parent

# Two cash files and a Twister SNG, each opening with <session sessioncode="...">.
FILES = (
    REPO / "regression-test-files/cash/iPoker/Flop/5CPLO-EUR-2.00-4.00-201905.txt",
    REPO / "regression-test-files/cash/iPoker/Flop/NLHE-EUR-0.01-0.02-201701.new.datetime.format.txt",
    REPO / "tests/fixtures/hands/ipoker/twister/twister_sng.txt",
)
SESSION_CODES = {4002439446, 4096452442, 6231386447}
FIRST_GAMECODES = {3422554295, 3858162574, 5631758947}

# The pattern before db643507f: it also matched <session sessioncode="...">.
PRE_FIX_HAND_INFO = re.compile(
    r'code="(?P<HID>[0-9]+)".*?<general>(.*?<startdate>(?P<DATETIME>[\.a-zA-Z-/: 0-9]+)</startdate>)?',
    re.MULTILINE | re.DOTALL,
)

# Tables keyed on a hand; the repair must leave each with the row count a
# clean import produces.
COUNT_ROWS = {
    "Hands": "SELECT COUNT(*) FROM Hands",
    "HandsPlayers": "SELECT COUNT(*) FROM HandsPlayers",
    "HandsActions": "SELECT COUNT(*) FROM HandsActions",
    "HandsStove": "SELECT COUNT(*) FROM HandsStove",
    "HandsPots": "SELECT COUNT(*) FROM HandsPots",
    "HandsSituations": "SELECT COUNT(*) FROM HandsSituations",
    "Boards": "SELECT COUNT(*) FROM Boards",
}


def _import(config, *, pattern: re.Pattern[str]) -> None:
    original = iPoker.re_hand_info
    iPoker.re_hand_info = pattern
    try:
        db = Database(config)
        importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
        importer.database = db
        for path in FILES:
            importer.addImportFile(str(path), "auto")
        importer.runImport()
    finally:
        iPoker.re_hand_info = original


def _new_database(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    config = golden.build_config(directory)
    Database(config).recreate_tables()
    return config


def _hand_numbers(db) -> list[int]:
    cursor = db.get_cursor()
    cursor.execute("SELECT siteHandNo FROM Hands ORDER BY siteHandNo")
    return [int(row[0]) for row in cursor.fetchall()]


HUD_COUNTS = "SELECT gametypeId, playerId, seats, position, SUM(n), SUM(totalProfit) FROM HudCache GROUP BY 1, 2, 3, 4"


def _hud_counts(db) -> list[tuple]:
    cursor = db.get_cursor()
    cursor.execute(HUD_COUNTS)
    return sorted(tuple(row) for row in cursor.fetchall())


def _row_counts(db) -> dict[str, int]:
    cursor = db.get_cursor()
    counts = {}
    for table, statement in COUNT_ROWS.items():
        cursor.execute(statement)
        counts[table] = int(cursor.fetchone()[0])
    return counts


@pytest.fixture(scope="module")
def templates(tmp_path_factory) -> dict[str, Path]:
    """Three database files, built once and copied by each test."""
    root = tmp_path_factory.mktemp("ipoker440")
    built = {}

    reference = _new_database(root / "reference")
    _import(reference, pattern=iPoker.re_hand_info)
    built["reference"] = root / "reference"

    stale_only = _new_database(root / "stale_only")
    _import(stale_only, pattern=PRE_FIX_HAND_INFO)
    built["stale_only"] = root / "stale_only"

    duplicated = _new_database(root / "duplicated")
    _import(duplicated, pattern=PRE_FIX_HAND_INFO)
    _import(duplicated, pattern=iPoker.re_hand_info)
    built["duplicated"] = root / "duplicated"
    return built


@pytest.fixture
def open_copy(templates, tmp_path):
    """Open a private copy of one template database."""

    def _open(name: str):
        target = tmp_path / name
        shutil.copytree(templates[name], target)
        config = golden.build_config(target)
        return config, Database(config)

    return _open


def test_the_scenario_reproduces_the_bug(open_copy) -> None:
    _config, reference = open_copy("reference")
    _config, duplicated = open_copy("duplicated")

    assert set(_hand_numbers(reference)).isdisjoint(SESSION_CODES)
    assert SESSION_CODES <= set(_hand_numbers(duplicated))
    assert len(_hand_numbers(duplicated)) == len(_hand_numbers(reference)) + len(SESSION_CODES)


def test_duplicates_are_found_without_the_files(open_copy) -> None:
    config, db = open_copy("duplicated")

    found = repair_tool.survey(db, repair_tool.ipoker_sites(config), [])

    assert {d.stale.site_hand_no for d in found.duplicates} == SESSION_CODES
    assert {d.evidence for d in found.duplicates} == {"identical twin"}
    assert found.renames == []
    assert found.ambiguous == []


def test_the_files_name_the_session_codes(open_copy) -> None:
    config, db = open_copy("duplicated")

    found = repair_tool.survey(db, repair_tool.ipoker_sites(config), list(FILES))

    assert {d.stale.site_hand_no for d in found.duplicates} == SESSION_CODES
    assert {d.evidence for d in found.duplicates} == {"session file"}


def test_session_first_games_reads_each_file() -> None:
    assert repair_tool.session_first_games(FILES) == {
        4002439446: {3422554295},
        4096452442: {3858162574},
        6231386447: {5631758947},
    }


def test_removing_the_duplicates_matches_a_clean_import(open_copy) -> None:
    config, db = open_copy("duplicated")
    _ref_config, reference = open_copy("reference")
    found = repair_tool.survey(db, repair_tool.ipoker_sites(config), [])

    changed = repair_tool.repair(db, found, commit=True)

    assert changed["Hands"] == len(SESSION_CODES)
    assert _hand_numbers(db) == _hand_numbers(reference)
    assert _row_counts(db) == _row_counts(reference)
    # Rebuilt from the repaired hands, the HUD cache no longer counts the duplicates (#591).
    assert _hud_counts(db) == _hud_counts(reference)


def test_a_rehearsal_writes_nothing(open_copy) -> None:
    config, db = open_copy("duplicated")
    before = (_hand_numbers(db), _row_counts(db))
    found = repair_tool.survey(db, repair_tool.ipoker_sites(config), [])

    changed = repair_tool.repair(db, found, commit=False)

    assert changed["Hands"] == len(SESSION_CODES)
    assert (_hand_numbers(db), _row_counts(db)) == before


def test_a_lone_stale_hand_is_renumbered_from_the_files(open_copy) -> None:
    config, db = open_copy("stale_only")
    _ref_config, reference = open_copy("reference")

    without_files = repair_tool.survey(db, repair_tool.ipoker_sites(config), [])
    found = repair_tool.survey(db, repair_tool.ipoker_sites(config), list(FILES))
    repair_tool.repair(db, found, commit=True)

    assert without_files.duplicates == [] and without_files.renames == []
    assert {(r.hand.site_hand_no, r.gamecode) for r in found.renames} == {
        (4002439446, 3422554295),
        (4096452442, 3858162574),
        (6231386447, 5631758947),
    }
    assert _hand_numbers(db) == _hand_numbers(reference)


def test_after_renumbering_a_reimport_adds_nothing(open_copy) -> None:
    config, db = open_copy("stale_only")
    found = repair_tool.survey(db, repair_tool.ipoker_sites(config), list(FILES))
    repair_tool.repair(db, found, commit=True)
    hands = _hand_numbers(db)

    _import(config, pattern=iPoker.re_hand_info)

    assert _hand_numbers(Database(config)) == hands


def test_apply_and_rehearse_cannot_be_combined() -> None:
    with pytest.raises(SystemExit):
        repair_tool.build_parser().parse_args(["--apply", "--rehearse"])


def test_the_sqlite_backup_is_a_full_copy(open_copy, tmp_path) -> None:
    _config, db = open_copy("duplicated")
    target = tmp_path / "backup.sqlite3"

    assert repair_tool.backup_sqlite(db, target) == target

    with sqlite3.connect(str(target)) as copy:
        (hands,) = copy.execute("SELECT COUNT(*) FROM Hands").fetchone()
    assert hands == len(_hand_numbers(db))
    with pytest.raises(SystemExit):
        repair_tool.backup_sqlite(db, target)


def test_the_command_line_reports_backs_up_and_repairs(open_copy, monkeypatch, tmp_path, capsys) -> None:
    config, db = open_copy("duplicated")
    _ref_config, reference = open_copy("reference")
    monkeypatch.setattr(repair_tool, "Config", lambda **_kwargs: config)
    monkeypatch.setattr(repair_tool, "Database", lambda _config: db)
    backup = tmp_path / "before.sqlite3"

    assert repair_tool.main([]) == 0
    assert "Dry run" in capsys.readouterr().out
    assert len(_hand_numbers(db)) == len(_hand_numbers(reference)) + len(SESSION_CODES)

    assert repair_tool.main(["--apply", "--backup", str(backup)]) == 0
    out = capsys.readouterr().out
    assert "Backup:" in out and backup.exists()
    assert "were rebuilt" in out
    assert _hand_numbers(db) == _hand_numbers(reference)


def test_aggregates_are_dropped_before_any_hand_is_deleted(open_copy, monkeypatch) -> None:
    config, db = open_copy("duplicated")
    found = repair_tool.survey(db, repair_tool.ipoker_sites(config), [])
    hands_when_invalidated = []
    monkeypatch.setattr(
        repair_tool.analytics_cache,
        "invalidate_aggregates",
        lambda database, _reason="": hands_when_invalidated.append(len(_hand_numbers(database))),
    )
    hands_before = len(_hand_numbers(db))

    repair_tool.repair(db, found, commit=False)
    assert hands_when_invalidated == []

    repair_tool.repair(db, found, commit=True)
    assert hands_when_invalidated == [hands_before]


def test_a_failed_cache_rebuild_leaves_everything_as_it_was(open_copy, monkeypatch) -> None:
    """The deletions and the three rebuilds are one transaction."""
    config, db = open_copy("duplicated")
    before = (_hand_numbers(db), _row_counts(db), _hud_counts(db))
    found = repair_tool.survey(db, repair_tool.ipoker_sites(config), [])
    rebuild = db.rebuild_cache

    def failing(h_start, v_start, table="HudCache", ttid=None, wmid=None, commit=True):
        if table == "PositionsCache":
            raise RuntimeError("connection lost")
        rebuild(h_start, v_start, table, ttid, wmid, commit)

    monkeypatch.setattr(db, "rebuild_cache", failing)

    with pytest.raises(RuntimeError):
        repair_tool.repair(db, found, commit=True)

    assert (_hand_numbers(db), _row_counts(db), _hud_counts(db)) == before
