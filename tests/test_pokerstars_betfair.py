"""PokerStars on Betfair: a PokerStars skin with its own room and folders (#733).

Betfair's 2026 client writes native PokerStars hand histories and tournament
summaries under ``%LOCALAPPDATA%\\Betfair.UK\\HandHistory`` and
``\\TournSummary`` (PokerTracker 4.19's documentation). Nothing in the files
names the skin, so the folder is what files them under their own room.

No real Betfair export is public yet: these tests run PokerStars' own fixtures
from a Betfair folder.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import fpdb_3_legacy.DetectInstalledSites as detect_module
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.DetectInstalledSites import PokerStarsDetector
from fpdb_3_legacy.PokerStarsToFpdb import POKERSTARS_SKIN_IDS, SITE_POKERSTARS_BETFAIR, PokerStars

ROOT = Path(__file__).resolve().parents[1]
CASH_HAND = ROOT / "regression-test-files/cash/Stars/Flop/2025-NL-uncalled-bet.txt"
SUMMARY = ROOT / "regression-test-files/summaries/Stars/6+Holdem-3max-STT-USD-1.00-201907.txt"
SKIN = "PokerStars on Betfair"


def _parser() -> PokerStars:
    return PokerStars.__new__(PokerStars)


# ---------------------------------------------------------------------------
# The skin's identity
# ---------------------------------------------------------------------------


def test_the_skin_has_its_own_site_id() -> None:
    assert POKERSTARS_SKIN_IDS[SKIN] == SITE_POKERSTARS_BETFAIR == 143


@pytest.mark.parametrize(
    "path",
    [
        r"C:\Users\alice\AppData\Local\Betfair.UK\HandHistory\alice\HH20260917 Table.txt",
        "/home/alice/.wine/drive_c/users/alice/AppData/Local/Betfair.UK/TournSummary/alice/TS20260917.txt",
    ],
)
def test_the_betfair_folder_names_the_skin(path: str) -> None:
    assert _parser()._detectSkinByPath(path) == (SKIN, 143)


@pytest.mark.parametrize(
    "path",
    [
        r"C:\Users\alice\AppData\Local\PokerStars.FR\HandHistory\alice\HH.txt",
        # "Betfair" in a screen name or a Windows user is not Betfair's client.
        r"C:\Users\alice\AppData\Local\PokerStars.FR\HandHistory\BetfairGrinder\HH.txt",
        r"C:\Users\betfair.uk.fan\AppData\Local\PokerStars.FR\HandHistory\alice\HH.txt",
    ],
)
def test_pokerstars_own_folders_are_unchanged(path: str) -> None:
    assert _parser()._detectSkinByPath(path) == ("PokerStars.FR", 33)


def test_the_room_policy_is_pokerstars() -> None:
    from fpdb_3_legacy import hud_room_policy

    assert hud_room_policy.capabilities_at(SKIN) == hud_room_policy.capabilities_at("PokerStars.FR")
    assert hud_room_policy.why_not("dynamic_hud", SKIN)


# ---------------------------------------------------------------------------
# Hands and summaries go through the PokerStars converters unchanged
# ---------------------------------------------------------------------------


@pytest.fixture
def importer(tmp_path):
    from fpdb_3_legacy.Database import Database
    from fpdb_3_legacy.Importer import Importer

    shutil.copyfile(ROOT / "HUD_config.xml", tmp_path / "HUD_config.xml")
    config = Config(file=str(tmp_path / "HUD_config.xml"))
    params = config.get_db_parameters()
    params.update(
        {
            "db-server": "sqlite",
            "db-backend": 4,
            "db-databaseName": str(tmp_path / "betfair.sqlite3"),
            "db-path": "",
        }
    )
    config.get_db_parameters = lambda: params
    schema = Database(config)
    schema.recreate_tables()
    schema.close_connection()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.setCallHud(False)
    yield importer
    importer.close()


def _betfair_copy(tmp_path: Path, folder: str, source: Path) -> Path:
    target = tmp_path / "AppData" / "Local" / "Betfair.UK" / folder / "alice" / source.name
    target.parent.mkdir(parents=True)
    shutil.copyfile(source, target)
    return target


def test_hands_from_the_betfair_folder_are_filed_under_the_skin(importer, tmp_path) -> None:
    importer.addImportFile(str(_betfair_copy(tmp_path, "HandHistory", CASH_HAND)), "auto")
    stored, _dups, _partial, _skipped, errors, _time = importer.runImport()

    assert stored >= 1
    assert errors == 0
    cursor = importer.database.get_cursor()
    cursor.execute(
        "SELECT DISTINCT s.name FROM Hands h JOIN Gametypes g ON h.gametypeId = g.id JOIN Sites s ON g.siteId = s.id"
    )
    assert [row[0] for row in cursor.fetchall()] == [SKIN]


def test_summaries_from_the_betfair_folder_are_filed_under_the_skin(importer, tmp_path) -> None:
    importer.addImportFile(str(_betfair_copy(tmp_path, "TournSummary", SUMMARY)), "auto")
    importer.runImport()

    cursor = importer.database.get_cursor()
    cursor.execute("SELECT DISTINCT s.name FROM TourneyTypes t JOIN Sites s ON t.siteId = s.id")
    assert [row[0] for row in cursor.fetchall()] == [SKIN]


def test_an_older_database_gains_the_sites_row(importer) -> None:
    database = importer.database
    cursor = database.get_cursor()
    cursor.execute("DELETE FROM Sites WHERE id = 143")
    database.commit()

    database.ensure_sites_rows()

    cursor.execute("SELECT name, code FROM Sites WHERE id = 143")
    assert cursor.fetchall() == [(SKIN, "PS")]


# ---------------------------------------------------------------------------
# Folder detection
# ---------------------------------------------------------------------------


@pytest.fixture
def detector() -> PokerStarsDetector:
    config = MagicMock()
    config.os_family = "Win7"
    return PokerStarsDetector(config)


def _windows_paths(local: Path, elsewhere: Path) -> dict[str, str]:
    return {
        "local_appdata": str(local),
        "appdata": str(elsewhere),
        "program_files": str(elsewhere),
        "program_files_x86": str(elsewhere),
    }


def test_the_betfair_client_folder_is_found_on_windows(detector, tmp_path) -> None:
    local = tmp_path / "AppData" / "Local"
    (local / "Betfair.UK" / "HandHistory" / "alice").mkdir(parents=True)
    (local / "Betfair.UK" / "TournSummary" / "alice").mkdir(parents=True)
    detector.platform = "Windows"

    with patch.object(detect_module, "get_windows_paths", return_value=_windows_paths(local, tmp_path / "x")):
        found = detector._detect_variant(SKIN)
        everything = detector.detect()

    assert found["detected"]
    assert found["variant"] == SKIN
    assert found["heroname"] == "alice"
    assert Path(found["hhpath"]) == local / "Betfair.UK" / "HandHistory" / "alice"
    assert Path(found["tspath"]) == local / "Betfair.UK" / "TournSummary" / "alice"
    assert [variant["variant"] for variant in detector.all_detected_variants] == [SKIN]
    assert everything["variant"] == SKIN


def test_histories_written_without_a_player_folder_are_still_found(detector, tmp_path) -> None:
    local = tmp_path / "AppData" / "Local"
    history = local / "Betfair.UK" / "HandHistory"
    history.mkdir(parents=True)
    (history / "HH20260917 Table.txt").write_text("PokerStars Hand #1:", encoding="utf-8")
    detector.platform = "Windows"

    with patch.object(detect_module, "get_windows_paths", return_value=_windows_paths(local, tmp_path / "x")):
        found = detector._detect_variant(SKIN)

    assert found["detected"]
    assert Path(found["hhpath"]) == history
    assert found["heroname"] == ""


def test_the_betfair_client_folder_is_found_under_wine(detector, tmp_path) -> None:
    users = tmp_path / ".wine" / "drive_c" / "users"
    (users / "alice" / "AppData" / "Local" / "Betfair.UK" / "HandHistory" / "alice").mkdir(parents=True)
    detector.platform = "Linux"
    paths: dict[str, Any] = {
        "wine_drive_c": str(tmp_path / ".wine" / "drive_c"),
        "wine_program_files": str(tmp_path / "pf"),
        "wine_program_files_x86": str(tmp_path / "pf86"),
        "wine_users": str(users),
    }

    with patch.object(detect_module, "get_linux_paths", return_value=paths):
        found = detector._detect_variant(SKIN)

    assert found["detected"]
    assert found["heroname"] == "alice"


def test_no_betfair_client_means_no_betfair_variant(detector, tmp_path) -> None:
    detector.platform = "Windows"
    with patch.object(detect_module, "get_windows_paths", return_value=_windows_paths(tmp_path, tmp_path)):
        assert detector._detect_variant(SKIN)["detected"] is False
