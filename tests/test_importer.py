"""What the importer does with the files it is given.

Importer is the entry point of everything a player brings into fpdb: hand
histories, tournament summaries, whole directories. Its counts are what the
GUI reports back, and a file it silently drops is a hand that never existed.

Each test drives the real importer against a throwaway SQLite database.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
HAND = ROOT / "tests/fixtures/hands/pokerstars/holdem/5card_omaha.txt"
SUMMARY_DIR = ROOT / "regression-test-files/summaries/Stars"


def staged(tmp_path: Path, source: Path, name: str | None = None) -> Path:
    """Copy a fixture into the test's own directory before importing it."""
    target = tmp_path / (name or source.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, target)
    return target


def counts(db: Any, table: str) -> int:
    cursor = db.get_cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    return cursor.fetchone()[0]


# --------------------------------------------------------------------------
# Importing a hand history
# --------------------------------------------------------------------------


def test_a_hand_history_is_stored_and_counted(importer, fresh_db, tmp_path) -> None:
    importer.addImportFile(str(staged(tmp_path, HAND)), "PokerStars")

    stored, duplicates, partial, skipped, errors, _ = importer.runImport()

    assert (stored, duplicates, partial, skipped, errors) == (1, 0, 0, 0, 0)
    assert counts(fresh_db, "Hands") == 1


def test_the_same_file_imported_twice_is_counted_as_a_duplicate(importer, fresh_db, tmp_path) -> None:
    # Re-importing a directory is routine; counting the hands again would
    # double every statistic derived from them.
    source = staged(tmp_path, HAND)
    importer.addImportFile(str(source), "PokerStars")
    importer.runImport()

    importer.clearFileList()
    importer.addImportFile(str(source), "PokerStars")
    stored, duplicates, *_ = importer.runImport()

    assert (stored, duplicates) == (0, 1)
    assert counts(fresh_db, "Hands") == 1


def test_a_file_that_is_not_a_hand_history_is_never_queued(importer, tmp_path) -> None:
    stranger = tmp_path / "shopping-list.txt"
    stranger.write_text("milk, eggs, a new mouse\n", encoding="utf-8")

    importer.addImportFile(str(stranger), "PokerStars")

    assert importer.filelist == {}
    assert importer.runImport()[:5] == (0, 0, 0, 0, 0)


def test_clearing_the_list_leaves_nothing_to_import(importer, tmp_path) -> None:
    importer.addImportFile(str(staged(tmp_path, HAND)), "PokerStars")

    importer.clearFileList()

    assert importer.filelist == {}


# --------------------------------------------------------------------------
# Importing a tournament summary
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def summary_file() -> Path:
    return sorted(SUMMARY_DIR.glob("*.txt"))[0]


def test_a_summary_creates_its_tournament(importer, fresh_db, tmp_path, summary_file) -> None:
    importer.addImportFile(str(staged(tmp_path, summary_file)), "PokerStars")

    importer.runImport()

    assert counts(fresh_db, "Tourneys") == 1
    assert counts(fresh_db, "TourneyTypes") == 1


def test_a_summary_records_every_player_it_lists(importer, fresh_db, tmp_path, summary_file) -> None:
    importer.addImportFile(str(staged(tmp_path, summary_file)), "PokerStars")

    importer.runImport()

    assert counts(fresh_db, "TourneysPlayers") > 1


# --------------------------------------------------------------------------
# Directories
# --------------------------------------------------------------------------


def test_a_directory_is_imported_whole(importer, fresh_db, tmp_path) -> None:
    folder = tmp_path / "histories"
    staged(folder, HAND)
    staged(folder, HAND, "another.txt")

    importer.addImportDirectory(str(folder), site="PokerStars")

    assert len(importer.filelist) == 2
    importer.runImport()
    assert counts(fresh_db, "Hands") >= 1


def test_removing_a_directory_takes_its_files_off_the_list(importer, tmp_path) -> None:
    folder = tmp_path / "histories"
    staged(folder, HAND)
    importer.addImportDirectory(str(folder), site="PokerStars")

    importer.removeImportDirectory(str(folder))

    assert importer.filelist == {}


def test_a_path_that_is_a_directory_is_recognised_as_one(importer, tmp_path) -> None:
    # The bulk-import button hands over whatever the user picked, file or folder.
    folder = tmp_path / "histories"
    staged(folder, HAND)

    importer.addBulkImportImportFileOrDir(str(folder), site="PokerStars")

    assert len(importer.filelist) == 1


def test_a_path_that_is_a_file_is_recognised_as_one(importer, tmp_path) -> None:
    source = staged(tmp_path, HAND)

    importer.addBulkImportImportFileOrDir(str(source), site="PokerStars")

    assert str(source) in importer.filelist


# --------------------------------------------------------------------------
# Moving files once they are dealt with
# --------------------------------------------------------------------------


def test_an_imported_file_is_moved_where_it_was_asked_to_go(importer, tmp_path) -> None:
    source = staged(tmp_path / "inbox", HAND)
    destination = tmp_path / "imported"
    importer.setMoveImportedFiles(enabled=True, target_dir=str(destination))
    importer.addImportFile(str(source), "PokerStars")

    importer.runImport()

    assert not source.exists()
    assert [path.name for path in destination.iterdir()] == [HAND.name]


def test_a_file_is_left_alone_when_moving_is_off(importer, tmp_path) -> None:
    source = staged(tmp_path / "inbox", HAND)
    importer.setMoveImportedFiles(enabled=False, target_dir=str(tmp_path / "imported"))
    importer.addImportFile(str(source), "PokerStars")

    importer.runImport()

    assert source.exists()


# --------------------------------------------------------------------------
# Around the import
# --------------------------------------------------------------------------


def test_the_report_is_produced_after_an_import(importer, tmp_path) -> None:
    importer.addImportFile(str(staged(tmp_path, HAND)), "PokerStars")
    importer.runImport()

    report = importer.get_hand_data_report()

    assert isinstance(report, str)


def test_post_import_runs_without_an_import_having_happened(importer) -> None:
    # The GUI calls it unconditionally when a run ends.
    assert importer.runPostImport() is None


def test_no_converter_is_cached_unless_caching_was_asked_for(importer, tmp_path) -> None:
    # It answers "nothing cached" rather than raising, which it used to do.
    source = staged(tmp_path, HAND)
    importer.addImportFile(str(source), "PokerStars")
    importer.runImport()

    assert importer.getCachedHHC(str(source)) is None


def test_a_cached_converter_is_kept_once_caching_is_on(importer, tmp_path) -> None:
    source = staged(tmp_path, HAND)
    importer.setFakeCacheHHC(True)
    importer.addImportFile(str(source), "PokerStars")

    importer.runImport()

    assert importer.getCachedHHC(str(source)) is not None


@pytest.mark.parametrize(
    ("setter", "key", "value"),
    [
        ("setHandCount", "handCount", 25),
        ("setQuiet", "quiet", True),
        ("setThreads", "threads", 2),
        ("setDropIndexes", "dropIndexes", "auto"),
        ("setDropHudCache", "dropHudCache", "auto"),
        ("setStarsArchive", "starsArchive", True),
        ("setFTPArchive", "ftpArchive", True),
        ("setFakeCacheHHC", "cacheHHC", True),
    ],
)
def test_each_setting_reaches_the_settings(importer, setter, key, value) -> None:
    getattr(importer, setter)(value)

    assert importer.settings[key] == value


@pytest.mark.parametrize(
    ("setter", "attribute", "value"),
    [("setCallHud", "callHud", False), ("setCacheSessions", "cacheSessions", True)],
)
def test_the_hud_and_session_switches_are_held_on_the_importer(importer, setter, attribute, value) -> None:
    # These two live on the instance rather than in settings, and Hand reads
    # them from there when deciding whether to feed the HUD and the caches.
    getattr(importer, setter)(value)

    assert getattr(importer, attribute) == value
