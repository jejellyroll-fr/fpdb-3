"""Bringing hands over from PokerTracker 4 or Holdem Manager 3 (#612).

A tracker's archive folder mixes rooms. These tests build one from the shipped
corpus and hold what the wizard relies on: every file is either sorted into its
room or listed as unsupported, the hero is checked against the screen name fpdb
will use, and the importer keeps per-file results so the summary can be told
room by room. The configuration is the repository's shipped file, read only.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.IdentifySite import FPDBFile, IdentifySite
from fpdb_3_legacy.Importer import FileImportResult, Importer, is_valid_import_file
from fpdb_3_legacy.tracker_migration import TRACKERS, configured_hero, scan_folder, summarize

ROOT = Path(__file__).resolve().parents[1]
CASH = ROOT / "regression-test-files" / "cash"


@pytest.fixture(scope="module")
def config():
    return Config(file=str(ROOT / "HUD_config.xml"))


def corpus(room: str, count: int = 2) -> list[Path]:
    files = sorted(p for p in (CASH / room).rglob("*.txt") if p.stat().st_size > 0)
    return files[:count]


@pytest.fixture
def archive(tmp_path):
    """A tracker archive: three rooms, one unreadable room, and the usual clutter."""
    for room in ("Stars", "Winamax", "GGPoker"):
        target = tmp_path / room.lower()
        target.mkdir()
        for path in corpus(room):
            shutil.copy(path, target / path.name)
    for path in corpus("TheBigGame"):
        shutil.copy(path, tmp_path / path.name)
    (tmp_path / "empty.txt").write_text("", encoding="utf-8")
    (tmp_path / ".DS_Store").write_bytes(b"\0\0")
    (tmp_path / "backup.zip").write_bytes(b"PK\x03\x04")
    return tmp_path


def test_a_mixed_archive_is_sorted_by_room(config, archive) -> None:
    scan = scan_folder(config, str(archive))

    assert {room: len(files) for room, files in scan.rooms.items()} == {
        "PokerStars.COM": 2,
        "Winamax": 2,
        "GGPoker": 2,
    }
    assert scan.file_count == 6


def test_a_file_no_parser_reads_is_listed_not_dropped(config, archive) -> None:
    scan = scan_folder(config, str(archive))

    assert sorted(Path(p).name for p in scan.unsupported) == sorted(p.name for p in corpus("TheBigGame"))


def test_empty_hidden_and_archive_files_are_neither_imported_nor_reported(config, archive) -> None:
    scan = scan_folder(config, str(archive))
    named = {Path(p).name for p in scan.unsupported} | {Path(p).name for f in scan.rooms.values() for p in f}

    assert not {"empty.txt", ".DS_Store", "backup.zip"} & named


def test_an_empty_folder_holds_nothing_to_import(config, tmp_path) -> None:
    scan = scan_folder(config, str(tmp_path))

    assert scan.rooms == {} and scan.unsupported == [] and scan.file_count == 0


def test_the_hero_found_in_the_files_is_reported_per_room(config, tmp_path) -> None:
    identifier = IdentifySite(config)
    hero_file = next(p for p in sorted((CASH / "iPoker").rglob("*.txt")) if _hero_of(identifier, p))
    shutil.copy(hero_file, tmp_path / hero_file.name)

    scan = scan_folder(config, str(tmp_path))

    (room,) = scan.rooms
    assert scan.heroes[room] == {_hero_of(IdentifySite(config), hero_file)}


def _hero_of(identifier, path: Path) -> str | None:
    identifier.clear_filelist()
    identifier.processFile(str(path))
    found = identifier.get_fobj(str(path))
    hero = getattr(found, "hero", "-") if found else "-"
    return None if hero in ("-", "Hero") else hero


@pytest.mark.parametrize(
    ("screen_name", "expected"),
    [
        ("", None),
        ("YOUR SCREEN NAME HERE", None),
        ("YOUR_SCREEN_NAME", None),
        ("  jdoe ", "jdoe"),
    ],
)
def test_a_placeholder_screen_name_counts_as_not_set(screen_name, expected) -> None:
    config = SimpleNamespace(supported_sites={"Winamax": SimpleNamespace(screen_name=screen_name)})

    assert configured_hero(config, "Winamax") == expected
    assert configured_hero(config, "Unknown room") is None


def test_the_summary_is_told_room_by_room_busiest_first() -> None:
    config = SimpleNamespace(supported_sites={"Winamax": SimpleNamespace(screen_name="jdoe")})
    results = {
        "a.txt": FileImportResult("Winamax", stored=10, duplicates=1),
        "b.txt": FileImportResult("Winamax", stored=5, partial=1),
        "c.txt": FileImportResult("PokerStars.COM", stored=40, errors=2),
        "d.txt": FileImportResult(None, errors=1),
    }

    rooms = summarize(results, config)

    assert [(r.site, r.hero, r.files, r.stored, r.duplicates, r.partial, r.errors) for r in rooms] == [
        ("PokerStars.COM", None, 1, 40, 0, 0, 2),
        ("Winamax", "jdoe", 2, 15, 1, 1, 0),
        ("?", None, 1, 0, 0, 0, 1),
    ]


def test_the_importer_keeps_each_file_s_result(tmp_path) -> None:
    """``Importer.file_results`` is what the summary reads; a file that blows up counts as an error."""
    importer = Importer.__new__(Importer)
    importer.settings = {}
    importer.mode = "bulk"
    importer.database = MagicMock()
    importer.database.getHandCount.return_value = 0
    importer.progress_start_cb = importer.progress_update_cb = importer.progress_end_cb = MagicMock()
    importer._start_equity_prefetch = lambda: None
    importer.logImport = MagicMock()
    importer._relocate_processed_file = MagicMock()
    good, bad = FPDBFile(str(tmp_path / "good.txt")), FPDBFile(str(tmp_path / "bad.txt"))
    good.site = SimpleNamespace(name="Winamax")
    bad.site = SimpleNamespace(name="PokerStars.COM")
    importer.filelist = {good.path: good, bad.path: bad}

    def despatch(fpdbfile):
        if fpdbfile is bad:
            raise ValueError("unreadable hand")
        return (7, 2, 1, 0, 0, 0.1, "Winamax")

    importer._import_despatch = despatch

    assert importer.importFiles(None) == (7, 2, 1, 0, 1)
    assert importer.file_results == {
        good.path: FileImportResult("Winamax", stored=7, duplicates=2, partial=1),
        bad.path: FileImportResult("PokerStars.COM", errors=1),
    }


def test_the_validity_rule_is_the_importer_s() -> None:
    assert Importer._is_valid_import_file(Importer.__new__(Importer), "hands.txt")
    assert not is_valid_import_file("hands.zip")
    assert not is_valid_import_file(".hidden.txt")


def test_every_tracker_says_where_its_hand_histories_are() -> None:
    assert [t.key for t in TRACKERS] == ["pt4", "hm3"]
    for tracker in TRACKERS:
        assert len(tracker.steps) == 3
        assert "archive" in tracker.steps[0]
