"""The Import ▸ From Another Tracker wizard, page by page (#612).

The scan runs for real on a folder built from the shipped corpus; the import
runs against a fake importer, so no database is touched. The configuration is
the repository's shipped file, read only.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QWizard  # noqa: E402 - after the Qt availability probe

from fpdb_3_legacy.Configuration import Config  # noqa: E402
from fpdb_3_legacy.GuiTrackerMigration import GuiTrackerMigration  # noqa: E402
from fpdb_3_legacy.Importer import FileImportResult  # noqa: E402
from fpdb_3_legacy.tracker_migration import ExportScan  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CASH = ROOT / "regression-test-files" / "cash"


class FakeLock:
    def __init__(self, free: bool = True) -> None:
        self.free = free
        self.held = False

    def acquire(self, wait=False, source=None) -> bool:
        self.held = self.free
        return self.free

    def release(self) -> None:
        self.held = False


class FakeImporter:
    """What BulkImportThread and the wizard call, recording the settings it was given."""

    def __init__(self) -> None:
        self.calls: dict[str, object] = {}
        self.sources: list[tuple[str, str]] = []
        self.filelist: dict[str, object] = {}
        self.file_results: dict[str, FileImportResult] = {}
        self.database = SimpleNamespace(getHandCount=lambda: 0)
        self.closed = False

    def __getattr__(self, name):
        if name.startswith("set") or name == "clearFileList":
            return lambda *args, **kwargs: self.calls.__setitem__(name, args)
        raise AttributeError(name)

    def addBulkImportImportFileOrDir(self, path, site="auto"):
        self.sources.append((path, site))
        self.filelist[path] = None
        return True

    def set_progress_callbacks(self, start_cb, update_cb, end_cb) -> None:
        self.callbacks = (start_cb, update_cb, end_cb)

    def runImport(self):
        start, update, end = self.callbacks
        start(2)
        update("a.txt", "0")
        update("b.txt", "12")
        end()
        self.file_results = {
            "a.txt": FileImportResult("Winamax", stored=12, duplicates=3),
            "b.txt": FileImportResult("PokerStars.COM", stored=30),
        }
        return (42, 3, 0, 0, 0, 1.0)

    def close(self) -> None:
        self.closed = True


@pytest.fixture(scope="module")
def config():
    return Config(file=str(ROOT / "HUD_config.xml"))


@pytest.fixture
def archive(tmp_path):
    for room in ("Stars", "Winamax"):
        for path in sorted(p for p in (CASH / room).rglob("*.txt") if p.stat().st_size)[:2]:
            shutil.copy(path, tmp_path / f"{room}-{path.name}")
    for path in sorted((CASH / "TheBigGame").rglob("*.txt"))[:1]:
        shutil.copy(path, tmp_path / path.name)
    return tmp_path


def open_wizard(qtbot, config, importer, lock):
    wizard = GuiTrackerMigration({"global_lock": lock}, config, importer=importer)
    qtbot.addWidget(wizard)
    wizard.show()
    return wizard


def advance_to_scan(qtbot, wizard, folder: Path) -> None:
    wizard.next()  # tracker -> source
    wizard.source_page.folder.setText(str(folder))
    assert wizard.button(QWizard.WizardButton.NextButton).isEnabled()
    wizard.next()  # source -> scan
    qtbot.waitUntil(lambda: wizard.scan_page.scan is not None, timeout=10000)


@pytest.mark.qt
def test_the_source_page_shows_the_chosen_tracker_s_steps(qtbot, config) -> None:
    wizard = open_wizard(qtbot, config, FakeImporter(), FakeLock())
    wizard.tracker_page.group.button(1).setChecked(True)  # Holdem Manager 3

    wizard.next()

    assert "Holdem Manager 3" in wizard.source_page.steps.text()
    assert not wizard.source_page.isComplete()  # no folder yet


@pytest.mark.qt
def test_the_scan_lists_rooms_and_unreadable_files_before_importing(qtbot, config, archive) -> None:
    importer = FakeImporter()
    wizard = open_wizard(qtbot, config, importer, FakeLock())

    advance_to_scan(qtbot, wizard, archive)

    rooms = {wizard.scan_page.rooms.item(r, 0).text(): wizard.scan_page.rooms.item(r, 1).text() for r in range(2)}
    assert rooms == {"PokerStars.COM": "2", "Winamax": "2"}
    assert wizard.scan_page.unsupported.count() == 1
    assert wizard.scan_page.isComplete()
    assert importer.sources == []  # nothing imported yet


@pytest.mark.qt
def test_a_folder_with_nothing_readable_cannot_be_imported(qtbot, config, tmp_path) -> None:
    (tmp_path / "notes.txt").write_text("not a hand history", encoding="utf-8")
    wizard = open_wizard(qtbot, config, FakeImporter(), FakeLock())

    advance_to_scan(qtbot, wizard, tmp_path)

    assert not wizard.scan_page.isComplete()


@pytest.mark.qt
def test_the_import_never_moves_the_tracker_s_files_and_ends_with_a_summary(qtbot, config, archive) -> None:
    importer, lock = FakeImporter(), FakeLock()
    wizard = open_wizard(qtbot, config, importer, lock)
    advance_to_scan(qtbot, wizard, archive)

    wizard.next()  # scan -> import
    qtbot.waitUntil(wizard.import_page.isComplete, timeout=10000)

    scanned = sorted(path for files in wizard.scan_page.scan.rooms.values() for path in files)
    assert sorted(path for path, _site in importer.sources) == scanned  # what the preview showed, no more
    assert {site for _path, site in importer.sources} == {"auto"}
    assert importer.calls["setMoveImportedFiles"] == (False,)
    assert importer.calls["setMoveFailedFiles"] == (False,)
    assert not lock.held  # released once the import ended

    wizard.next()  # import -> summary
    table = wizard.summary_page.rooms
    assert [(table.item(r, 0).text(), table.item(r, 3).text()) for r in range(table.rowCount())] == [
        ("PokerStars.COM", "30"),
        ("Winamax", "12"),
    ]
    assert "42 hands" in wizard.summary_page.headline.text()
    assert "1 files were left out" in wizard.summary_page.headline.text()


@pytest.mark.qt
def test_a_running_import_elsewhere_blocks_this_one(qtbot, config, archive) -> None:
    importer = FakeImporter()
    wizard = open_wizard(qtbot, config, importer, FakeLock(free=False))
    advance_to_scan(qtbot, wizard, archive)

    wizard.next()

    assert "Another import is running" in wizard.import_page.current.text()
    assert not wizard.import_page.isComplete()
    assert importer.sources == []


@pytest.mark.qt
def test_closing_the_wizard_closes_its_importer(qtbot, config) -> None:
    importer = FakeImporter()
    wizard = open_wizard(qtbot, config, importer, FakeLock())

    wizard.reject()

    assert importer.closed


@pytest.mark.qt
def test_a_symlink_in_the_archive_is_neither_shown_nor_imported(qtbot, config, archive, tmp_path_factory) -> None:
    outside = tmp_path_factory.mktemp("outside")
    source = next(p for p in sorted((CASH / "Winamax").rglob("*.txt")) if p.stat().st_size)
    target = outside / "elsewhere.txt"
    shutil.copy(source, target)
    try:
        (archive / "link.txt").symlink_to(target)
    except OSError:
        pytest.skip("symlinks are not available here")
    importer = FakeImporter()
    wizard = open_wizard(qtbot, config, importer, FakeLock())
    advance_to_scan(qtbot, wizard, archive)

    wizard.next()
    qtbot.waitUntil(wizard.import_page.isComplete, timeout=10000)

    imported = [Path(path).name for path, _site in importer.sources]
    assert "link.txt" not in imported and "elsewhere.txt" not in imported
    assert len(imported) == 4


@pytest.mark.qt
def test_a_scan_the_user_moved_past_cannot_overwrite_the_current_one(qtbot, config, archive, tmp_path) -> None:
    wizard = open_wizard(qtbot, config, FakeImporter(), FakeLock())
    advance_to_scan(qtbot, wizard, archive)
    first = wizard.scan_page.thread

    wizard.back()  # to the source page: another folder
    second_folder = tmp_path / "second"
    second_folder.mkdir()
    shutil.copy(next(p for p in sorted((CASH / "GGPoker").rglob("*.txt")) if p.stat().st_size), second_folder)
    wizard.source_page.folder.setText(str(second_folder))
    wizard.next()
    qtbot.waitUntil(lambda: wizard.scan_page.scan is not None, timeout=10000)

    # The first folder's scan answers late: it must not replace the second folder's preview.
    first.scanned.emit(ExportScan(rooms={"PokerStars.COM": ["late.txt"] * 9}))

    assert set(wizard.scan_page.scan.rooms) == {"GGPoker"}
    assert wizard.scan_page.rooms.item(0, 0).text() == "GGPoker"
