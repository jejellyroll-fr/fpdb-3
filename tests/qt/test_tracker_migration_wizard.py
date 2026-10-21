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
        self.filelist: dict[str, object] = {}
        self.file_results: dict[str, FileImportResult] = {}
        self.database = SimpleNamespace(getHandCount=lambda: 0)
        self.closed = False

    def __getattr__(self, name):
        if name.startswith("set") or name == "clearFileList":
            return lambda *args, **kwargs: self.calls.__setitem__(name, args)
        raise AttributeError(name)

    def addBulkImportImportFileOrDir(self, path, site="auto"):
        self.calls["source"] = (path, site)
        self.filelist = {"a": None, "b": None}
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
    assert "source" not in importer.calls  # nothing imported yet


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

    assert importer.calls["source"] == (str(archive), "auto")
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
    assert "source" not in importer.calls


@pytest.mark.qt
def test_closing_the_wizard_closes_its_importer(qtbot, config) -> None:
    importer = FakeImporter()
    wizard = open_wizard(qtbot, config, importer, FakeLock())

    wizard.reject()

    assert importer.closed
