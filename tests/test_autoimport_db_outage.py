"""Tests for the auto-import tab while the database is unreachable.

A wedged import cycle used to be invisible: ``do_import`` logged "deferring this
iteration" at debug level and returned, every interval, forever, so the importer
looked like it had simply decided to stop. Pressing Stop then called
``wait()`` with no timeout on the UI thread and froze the window.

The cycle now reports an unreachable database to the GUI, says so once per
outage rather than once per interval, and Stop gives up on a worker that will
not finish.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

# GuiAutoImport uses legacy-style bare imports, so the package directory must be
# importable directly.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fpdb_3_legacy")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _make_gui():
    """A headless GuiAutoImport with the Importer mocked out, plus GUI stubs.

    ``cli=True`` skips the widget construction, so the progress bar and status
    label the outage path writes to are stubbed in here.
    """
    from fpdb_3_legacy import GuiAutoImport

    settings = {
        "db-host": "localhost",
        "db-user": "fpdb",
        "db-password": "",
        "db-databaseName": "fpdb",
        "global_lock": MagicMock(),
    }
    config = MagicMock()
    config.get_import_parameters.return_value = {"interval": "5"}
    config.get_supported_sites.return_value = []
    config.get_db_parameters.return_value = {}

    with patch.object(GuiAutoImport.Importer, "Importer", return_value=MagicMock()):
        gui = GuiAutoImport.GuiAutoImport(settings, config, cli=True)

    gui.progressBar = MagicMock()
    gui.statusLabel = MagicMock()
    gui.addText = MagicMock()
    return gui


def test_an_unreachable_database_is_announced_once_per_outage() -> None:
    gui = _make_gui()

    gui.import_db_offline()
    gui.import_db_offline()
    gui.import_db_offline()

    assert gui._db_offline is True
    assert gui.addText.call_count == 1, "the outage must not be re-announced every interval"
    assert "unreachable" in gui.statusLabel.setText.call_args[0][0].lower()


def test_the_database_coming_back_is_announced_too() -> None:
    gui = _make_gui()
    gui.import_db_offline()
    gui.addText.reset_mock()

    gui.import_finished()

    assert gui._db_offline is False
    assert gui.addText.call_count == 1
    assert "back" in gui.addText.call_args[0][0].lower()


def test_an_ordinary_cycle_says_nothing() -> None:
    """Only a recovery is worth a line; every other cycle is silent."""
    gui = _make_gui()

    gui.import_finished()

    gui.addText.assert_not_called()


def test_a_wedged_worker_is_reported_after_several_missed_cycles() -> None:
    from fpdb_3_legacy.GuiAutoImport import DEFERRED_CYCLES_BEFORE_WARNING

    gui = _make_gui()
    gui.doAutoImportBool = True
    gui.import_thread = MagicMock()
    gui.import_thread.isRunning.return_value = True

    for _ in range(DEFERRED_CYCLES_BEFORE_WARNING - 1):
        assert gui.do_import() is True
    gui.statusLabel.setText.assert_not_called()

    gui.do_import()

    assert gui._deferred_cycles == DEFERRED_CYCLES_BEFORE_WARNING
    assert "longer" in gui.statusLabel.setText.call_args[0][0].lower()


def test_the_deferral_count_resets_when_a_cycle_starts() -> None:
    gui = _make_gui()
    gui.doAutoImportBool = True
    gui.import_thread = MagicMock()
    gui.import_thread.isRunning.return_value = True
    gui.do_import()
    assert gui._deferred_cycles == 1

    gui.import_thread.isRunning.return_value = False
    with patch("fpdb_3_legacy.GuiAutoImport.AutoImportThread"):
        gui.do_import()

    assert gui._deferred_cycles == 0


def test_worker_reports_an_unreachable_database_instead_of_importing() -> None:
    from fpdb_3_legacy.GuiAutoImport import AutoImportThread

    importer = MagicMock()
    importer.database.ensure_connection.return_value = False
    thread = AutoImportThread(importer)
    seen = []
    thread.db_offline.connect(lambda: seen.append("offline"))
    thread.finished.connect(lambda: seen.append("finished"))

    thread.run()

    assert seen == ["offline"]
    importer.runUpdated.assert_not_called()
    importer.autoSummaryGrab.assert_not_called()


def test_worker_imports_normally_when_the_database_answers() -> None:
    from fpdb_3_legacy.GuiAutoImport import AutoImportThread

    importer = MagicMock()
    importer.database.ensure_connection.return_value = True
    thread = AutoImportThread(importer)
    seen = []
    thread.db_offline.connect(lambda: seen.append("offline"))
    thread.finished.connect(lambda: seen.append("finished"))

    thread.run()

    assert seen == ["finished"]
    importer.runUpdated.assert_called_once()


def test_stop_waits_with_a_timeout_not_forever() -> None:
    """An unbounded wait on the UI thread is what froze the window."""
    from fpdb_3_legacy.GuiAutoImport import STOP_WAIT_MS

    gui = _make_gui()
    gui.import_thread = MagicMock()
    gui.import_thread.isRunning.return_value = True
    gui.import_thread.wait.return_value = True

    assert gui._stop_import_worker() is True
    gui.import_thread.wait.assert_called_once_with(STOP_WAIT_MS)


def test_stop_gives_up_on_a_worker_that_will_not_finish() -> None:
    gui = _make_gui()
    gui.import_thread = MagicMock()
    gui.import_thread.isRunning.return_value = True
    gui.import_thread.wait.return_value = False  # still running when the wait expires

    assert gui._stop_import_worker() is False
    assert "background" in gui.addText.call_args[0][0].lower()


def test_stop_is_immediate_when_no_cycle_is_running() -> None:
    gui = _make_gui()
    gui.import_thread = MagicMock()
    gui.import_thread.isRunning.return_value = False

    assert gui._stop_import_worker() is True
    gui.import_thread.wait.assert_not_called()
    gui.addText.assert_not_called()


def test_stop_defers_cleanup_while_the_worker_is_still_running() -> None:
    """The Importer and global lock stay owned until the worker really exits."""
    from fpdb_3_legacy import GuiAutoImport

    gui = _make_gui()
    gui.startButton = MagicMock()
    gui.startButton.isChecked.return_value = False
    gui.intervalEntry = MagicMock()
    gui.import_thread = MagicMock()
    gui.import_thread.isRunning.return_value = True

    with (
        patch.object(gui, "_stop_import_worker", return_value=False),
        patch.object(gui, "_finalize_auto_import_stop") as finalize,
        patch.object(GuiAutoImport.QTimer, "singleShot") as single_shot,
    ):
        gui.startClicked()

    assert gui._stop_cleanup_pending is True
    gui.importer.autoSummaryGrab.assert_not_called()
    gui.settings["global_lock"].release.assert_not_called()
    finalize.assert_not_called()
    single_shot.assert_called_once_with(250, gui._wait_for_import_worker_stop)


def test_deferred_stop_finishes_after_the_worker_exits() -> None:
    gui = _make_gui()
    gui._stop_cleanup_pending = True
    gui.import_thread = MagicMock()
    gui.import_thread.isRunning.return_value = False

    with patch.object(gui, "_finalize_auto_import_stop") as finalize:
        gui._wait_for_import_worker_stop()

    finalize.assert_called_once_with()
