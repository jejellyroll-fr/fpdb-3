"""The Import ▸ From Another Tracker wizard, page by page (#612).

The scan runs for real on a folder built from the shipped corpus; the import
runs against a fake importer, so no database is touched. The configuration is
the repository's shipped file, read only.
"""

from __future__ import annotations

import shutil
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QMainWindow, QWizard  # noqa: E402 - after the Qt availability probe

from fpdb_3_legacy import Importer  # noqa: E402
from fpdb_3_legacy.Configuration import Config  # noqa: E402
from fpdb_3_legacy.GuiTrackerMigration import GuiTrackerMigration, ScanThread  # noqa: E402
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


class SlowScan(ScanThread):
    """A scan that runs until the test lets it go."""

    def __init__(self, release: threading.Event) -> None:
        super().__init__(None, "")
        self.release = release

    def run(self) -> None:
        self.release.wait(10)


@pytest.mark.qt
def test_a_scan_that_outlives_the_wizard_is_kept_until_it_finishes(qtbot, config) -> None:
    wizard = open_wizard(qtbot, config, FakeImporter(), FakeLock())
    release = threading.Event()
    slow = SlowScan(release)
    wizard.scan_page.running.append(slow)
    slow.start()

    wizard.scan_page.stop(wait_ms=20)  # the bounded wait runs out

    assert slow.isRunning()
    assert slow in Importer._orphaned_imports  # held, so it is not destroyed while running
    assert slow not in wizard.scan_page.running
    release.set()
    assert slow.wait(5000)
    Importer.reap_orphaned_imports()
    assert slow not in Importer._orphaned_imports


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.refreshed = 0

    def refresh_after_import(self) -> None:
        self.refreshed += 1


@pytest.mark.qt
def test_open_stats_tabs_are_refreshed_once_the_import_ends(qtbot, config, archive) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    wizard = GuiTrackerMigration({"global_lock": FakeLock()}, config, parent=window, importer=FakeImporter())
    wizard.show()
    advance_to_scan(qtbot, wizard, archive)

    wizard.next()
    qtbot.waitUntil(wizard.import_page.isComplete, timeout=10000)

    assert window.refreshed == 1


IPOKER_EXPORT = ROOT / "tests" / "fixtures" / "pokertracker_ipoker_rooms"


@pytest.mark.qt
def test_the_import_waits_for_the_room_of_each_unplaced_ipoker_hero(qtbot, config) -> None:
    # The shipped file enables several iPoker rooms and names no screen name: nothing places these heroes.
    importer = FakeImporter()
    wizard = open_wizard(qtbot, config, importer, FakeLock())

    advance_to_scan(qtbot, wizard, IPOKER_EXPORT)

    page = wizard.scan_page
    assert sorted(page.room_choices) == ["alice", "bob"]
    assert page.room_question.isVisibleTo(wizard)
    assert not wizard.button(QWizard.WizardButton.NextButton).isEnabled()

    page.room_choices["alice"].setCurrentIndex(page.room_choices["alice"].findData("PMU Poker"))
    assert not wizard.button(QWizard.WizardButton.NextButton).isEnabled()

    page.room_choices["bob"].setCurrentIndex(page.room_choices["bob"].findData("FDJ Poker"))
    assert wizard.button(QWizard.WizardButton.NextButton).isEnabled()

    wizard.next()  # scan -> import
    qtbot.waitUntil(wizard.import_page.isComplete, timeout=10000)

    assert importer.calls["setIpokerRooms"] == ({"alice": "PMU Poker", "bob": "FDJ Poker"},)


@pytest.mark.qt
def test_the_screen_name_warning_does_not_name_the_network_while_the_user_is_asked(qtbot, config) -> None:
    wizard = open_wizard(qtbot, config, FakeImporter(), FakeLock())

    advance_to_scan(qtbot, wizard, IPOKER_EXPORT)

    assert "Set your screen name" not in wizard.scan_page.status.text()


@pytest.mark.qt
def test_going_back_forgets_the_question_of_the_previous_scan(qtbot, config, tmp_path) -> None:
    (tmp_path / "notes.txt").write_text("not a hand history", encoding="utf-8")
    wizard = open_wizard(qtbot, config, FakeImporter(), FakeLock())
    advance_to_scan(qtbot, wizard, IPOKER_EXPORT)

    wizard.back()
    wizard.source_page.folder.setText(str(tmp_path))
    wizard.next()
    qtbot.waitUntil(lambda: wizard.scan_page.scan is not None, timeout=10000)

    assert not wizard.scan_page.room_choices
    assert not wizard.scan_page.room_question.isVisibleTo(wizard)


# --- PokerTracker 4's database as the source (#814) ---------------------------------


@pytest.fixture
def own_config(tmp_path_factory):
    """A configuration whose file sits in a folder of its own: the wizard writes its PT4 marks there."""
    folder = tmp_path_factory.mktemp("config")
    shutil.copy(ROOT / "HUD_config.xml", folder / "HUD_config.xml")
    return Config(file=str(folder / "HUD_config.xml"))


@pytest.fixture
def fake_pt4(monkeypatch):
    """Stands in for reading the PT4 database: writes two corpus files where the wizard asks."""
    from fpdb_3_legacy import GuiTrackerMigration as module
    from fpdb_3_legacy.pt4_database import DatabaseExport

    calls: list[dict] = []

    def export_pt4(database, password, folder, marks):
        calls.append({"database": database, "password": password, "folder": folder, "marks": dict(marks)})

        def run(thread):
            thread.reading.emit(0, 3)
            for room in ("Stars", "Winamax"):
                source = next(p for p in sorted((CASH / room).rglob("*.txt")) if p.stat().st_size)
                shutil.copy(source, Path(folder) / f"cash-{room}-00001.txt")
            export = DatabaseExport(folder, marks={"cash": 99, "tourney": 7}, repaired=1)
            export.hands[("cash", "PokerStars")] = 2
            export.hands[("cash", "Winamax")] = 1
            return export

        return run

    monkeypatch.setattr(module, "export_pt4", export_pt4)
    return calls


def advance_to_database_scan(qtbot, wizard, password: str = "secret") -> None:
    wizard.next()  # tracker (PT4) -> source
    wizard.source_page.from_database.setChecked(True)
    wizard.source_page.password.setText(password)
    assert wizard.button(QWizard.WizardButton.NextButton).isEnabled()
    wizard.next()  # source -> scan
    qtbot.waitUntil(lambda: wizard.scan_page.scan is not None, timeout=10000)


@pytest.mark.qt
def test_the_database_is_offered_for_pokertracker_4_only(qtbot, config) -> None:
    wizard = open_wizard(qtbot, config, FakeImporter(), FakeLock())
    wizard.next()
    page = wizard.source_page

    assert page.source_choice.isVisibleTo(wizard)
    page.from_database.setChecked(True)
    assert page.database_box.isVisibleTo(wizard)
    assert not page.folder_box.isVisibleTo(wizard)
    assert page.isComplete()  # PT4's defaults; a password may be empty (trust authentication)
    assert page.password.echoMode() == page.password.EchoMode.Password
    page.host.clear()
    assert not page.isComplete()

    wizard.back()
    wizard.tracker_page.group.button(1).setChecked(True)  # Holdem Manager 3
    wizard.next()
    assert not page.source_choice.isVisibleTo(wizard)
    assert not page.uses_database()
    assert page.folder_box.isVisibleTo(wizard)


@pytest.mark.qt
def test_the_database_is_read_scanned_and_imported_like_a_folder(qtbot, own_config, fake_pt4) -> None:
    importer = FakeImporter()
    wizard = open_wizard(qtbot, own_config, importer, FakeLock())

    advance_to_database_scan(qtbot, wizard)

    (call,) = fake_pt4
    assert call["password"] == "secret"
    assert call["database"].database == "PT4 DB"
    assert call["marks"] == {}  # nothing imported from this database yet
    status = wizard.scan_page.status.text()
    assert "3 hands and 0 tournament summaries read from the database" in status
    assert "wrong character set" in status
    assert wizard.scan_page.isComplete()

    wizard.next()  # scan -> import
    qtbot.waitUntil(wizard.import_page.isComplete, timeout=10000)

    assert {str(Path(path).parent) for path, _site in importer.sources} == {call["folder"]}
    assert importer.calls["setMoveImportedFiles"] == (False,)
    from fpdb_3_legacy import pt4_database

    assert pt4_database.load_marks(own_config, call["database"]) == {"cash": 99, "tourney": 7}


@pytest.mark.qt
def test_a_second_import_starts_after_the_first_one(qtbot, own_config, fake_pt4) -> None:
    from fpdb_3_legacy import pt4_database

    pt4_database.save_marks(own_config, pt4_database.Pt4Database(), {"cash": 50, "tourney": 3})
    wizard = open_wizard(qtbot, own_config, FakeImporter(), FakeLock())

    advance_to_database_scan(qtbot, wizard)
    assert fake_pt4[-1]["marks"] == {"cash": 50, "tourney": 3}

    wizard.back()
    wizard.source_page.only_new.setChecked(False)
    wizard.next()
    qtbot.waitUntil(lambda: wizard.scan_page.scan is not None, timeout=10000)
    assert fake_pt4[-1]["marks"] == {}


@pytest.mark.qt
def test_closing_the_wizard_removes_what_it_wrote_from_the_database(qtbot, own_config, fake_pt4) -> None:
    wizard = open_wizard(qtbot, own_config, FakeImporter(), FakeLock())
    advance_to_database_scan(qtbot, wizard)
    folder = Path(fake_pt4[-1]["folder"])
    assert any(folder.iterdir())

    wizard.reject()

    assert not folder.exists()


@pytest.mark.qt
def test_a_database_that_cannot_be_read_says_why(qtbot, own_config, monkeypatch) -> None:
    from fpdb_3_legacy import GuiTrackerMigration as module

    def refused(*_args):
        def run(_thread):
            raise RuntimeError('password authentication failed for user "postgres"')

        return run

    monkeypatch.setattr(module, "export_pt4", refused)
    wizard = open_wizard(qtbot, own_config, FakeImporter(), FakeLock())
    wizard.next()
    wizard.source_page.from_database.setChecked(True)
    wizard.next()

    qtbot.waitUntil(lambda: "could not be read" in wizard.scan_page.status.text(), timeout=10000)
    assert "password authentication failed" in wizard.scan_page.status.text()
    assert not wizard.scan_page.isComplete()
