"""A PokerTracker summary is identified under the room it names (#700).

PokerTracker is the file's format, not a room. Under that name, every summary of an
export logged "Database ID for PokerTracker not found" and "Could not determine site
ID for PokerTracker", though each one was stored under the right room.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from fpdb_3_legacy.IdentifySite import IdentifySite
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.tracker_migration import scan_folder

EXPORT = Path(__file__).parent / "fixtures" / "pokertracker_export"
ROOMS = {"GG Poker": "GGPoker", "Winamax": "Winamax", "iPoker Network": "iPoker"}
A_MICROGAMING_HAND_FILE = "regression-test-files/cash/PokerTracker/Flop/NLHE-EUR-0.05-0.10-201111.Microgaming.txt"
SITE_LOOKUP_LINES = ("Database ID for", "Could not determine site ID")


def _summary(folder: str) -> Path:
    return next((EXPORT / folder).glob("*Summary.txt"))


def _site_lookup_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.getMessage().startswith(SITE_LOOKUP_LINES)]


def _importer(config, database) -> Importer:
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = database
    importer.setCallHud(False)
    return importer


@pytest.mark.parametrize(("folder", "room"), ROOMS.items())
def test_a_summary_is_identified_under_the_room_it_names(legacy_config, folder, room) -> None:
    found = IdentifySite(legacy_config).idSite(str(_summary(folder)), _summary(folder).read_text("utf-8"), "utf-8")

    assert (found.site.name, found.site.filter_name, found.ftype) == (room, "PokerTracker", "summary")


def test_the_site_line_is_read_from_a_windows_file(legacy_config) -> None:
    text = _summary("Winamax").read_text("utf-8").replace("\n", "\r\n")

    assert IdentifySite(legacy_config).idSite("summary.txt", text, "utf-8").site.name == "Winamax"


def test_an_export_imports_under_its_rooms_without_a_site_lookup_failing(fresh_db, legacy_config, caplog) -> None:
    importer = _importer(legacy_config, fresh_db)

    with caplog.at_level(logging.WARNING):
        assert importer.addBulkImportImportFileOrDir(str(EXPORT))
        importer.runImport()

    cursor = fresh_db.get_cursor()
    cursor.execute(
        "SELECT s.name, COUNT(*) FROM Tourneys t JOIN TourneyTypes tt ON tt.id = t.tourneyTypeId "
        "JOIN Sites s ON s.id = tt.siteId GROUP BY s.name"
    )
    assert dict(cursor.fetchall()) == dict.fromkeys(ROOMS.values(), 1)
    assert {result.site for result in importer.file_results.values()} == set(ROOMS.values())
    assert _site_lookup_lines(caplog) == []


def test_a_summary_naming_an_unknown_room_still_fails_visibly(fresh_db, legacy_config, tmp_path) -> None:
    path = tmp_path / "T#1 - Summary.txt"
    path.write_text(_summary("Winamax").read_text("utf-8").replace("Site: Winamax", "Site: Nowhere"), encoding="utf-8")
    importer = _importer(legacy_config, fresh_db)

    assert importer.addImportFile(str(path))
    *_counts, errors, _seconds = importer.runImport()

    assert errors == 1
    assert importer.file_results[str(path)].site == "PokerTracker"
    cursor = fresh_db.get_cursor()
    cursor.execute("SELECT COUNT(*) FROM Tourneys")
    assert cursor.fetchone()[0] == 0


def test_a_hand_file_is_added_without_looking_its_format_up_as_a_site(fresh_db, legacy_config, caplog) -> None:
    importer = _importer(legacy_config, fresh_db)

    with caplog.at_level(logging.WARNING):
        assert importer.addImportFile(A_MICROGAMING_HAND_FILE)

    assert importer.filelist[A_MICROGAMING_HAND_FILE].site.name == "PokerTracker"
    assert _site_lookup_lines(caplog) == []


def test_the_scan_previews_what_the_import_records(legacy_config) -> None:
    scan = scan_folder(legacy_config, str(EXPORT))

    assert {room: len(files) for room, files in scan.rooms.items()} == dict.fromkeys(ROOMS.values(), 1)
    assert not scan.unsupported
