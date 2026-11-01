"""Closing an importer tab gives back what it took (#347).

The two importer tabs each build their own ``Importer``, which opens one
database connection for itself and one per writer thread. Every open of the tab
builds a new one, and until #347 nothing released them: a session that opened
and closed Bulk Import ten times held ten importers' worth of connections until
it exited.

The tests go through the hooks ``close_tab`` calls rather than through the
importer directly, because the subject is that *closing the tab* releases the
connections. A widget removed from a QTabWidget is never sent ``closeEvent``,
which is the whole reason these hooks exist.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock

from fpdb_3_legacy import Importer
from fpdb_3_legacy.GuiAutoImport import GuiAutoImport
from fpdb_3_legacy.GuiBulkImport import GuiBulkImport

ROOT = Path(__file__).parents[1]


def _uninitialised(cls):
    """Allocate a tab without running ``__init__``.

    A real one builds widgets and needs a QApplication; these tests exercise
    two hooks that touch nothing but plain attributes, so the instance is
    allocated and those attributes are set by hand.
    """
    return cls.__new__(cls)


def _idle_auto_import():
    """An auto-import tab that was opened and never started."""
    tab = _uninitialised(GuiAutoImport)
    tab.importer = MagicMock(name="importer")
    tab.import_thread = None
    tab.importtimer = None
    tab.doAutoImportBool = False
    tab.config_observer = None
    return tab


def _running_auto_import():
    """An auto-import tab in the middle of a cycle it cannot finish in time."""
    tab = _idle_auto_import()
    tab.doAutoImportBool = True
    tab.importtimer = MagicMock(name="importtimer")
    tab.import_thread = MagicMock(name="import_thread")
    tab.import_thread.isRunning.return_value = True
    tab._cancel_swc_attach = MagicMock(name="_cancel_swc_attach")
    tab._stop_import_worker = MagicMock(name="_stop_import_worker", return_value=False)
    tab._finalize_auto_import_stop = MagicMock(name="_finalize_auto_import_stop")
    tab.settings = {"global_lock": MagicMock(name="global_lock")}
    tab.pipe_to_hud = None
    return tab


def _bulk_import(*, importing: bool = False):
    tab = _uninitialised(GuiBulkImport)
    tab.importer = MagicMock(name="importer")
    tab.settings = {"global_lock": MagicMock(name="global_lock")}
    if importing:
        tab.import_thread = MagicMock(name="import_thread")
        tab.import_thread.isRunning.return_value = True
        tab.import_thread.wait.return_value = False
    return tab


# --- Auto Import -------------------------------------------------------------


def test_closing_an_idle_auto_import_tab_closes_its_importer() -> None:
    tab = _idle_auto_import()

    tab.shutdown_workers()
    tab.close_owned_database()

    tab.importer.close.assert_called_once_with()


def test_closing_an_auto_import_tab_unregisters_the_config_observer() -> None:
    """Otherwise the next config change calls into a deleted Qt object.

    ``_teardown_config_observer`` existed, but only on ``closeEvent``, which a
    tab close never delivers -- so on this path it had never run.
    """
    tab = _idle_auto_import()
    tab._teardown_config_observer = MagicMock(name="_teardown_config_observer")

    tab.shutdown_workers()

    tab._teardown_config_observer.assert_called_once_with()


def test_a_running_auto_import_is_stopped_before_the_tab_goes() -> None:
    tab = _running_auto_import()
    tab._stop_import_worker.return_value = True
    tab.import_thread.isRunning.return_value = False

    tab.shutdown_workers()

    assert tab.doAutoImportBool is False
    assert tab.importtimer is None
    tab._cancel_swc_attach.assert_called_once_with()
    tab._finalize_auto_import_stop.assert_called_once_with()


def test_an_overrunning_auto_import_is_cleaned_up_once_it_ends() -> None:
    """The tab goes, the cleanup does not.

    Closing the connections underneath a running worker would hand it a dead
    handle, so the tab leaves them alone -- but leaving it at that held the
    global lock for the rest of the session. The import is adopted instead, and
    everything it owes is settled when it really finishes.
    """
    tab = _running_auto_import()
    lock = tab.settings["global_lock"]
    Importer._orphaned_imports.clear()

    tab.shutdown_workers()
    tab.close_owned_database()

    # Nothing yet: the worker is still using the importer.
    tab._finalize_auto_import_stop.assert_not_called()
    tab.importer.close.assert_not_called()
    lock.release.assert_not_called()

    tab.import_thread.isRunning.return_value = False
    Importer.reap_orphaned_imports()

    tab.importer.close.assert_called_once_with()
    lock.release.assert_called_once_with()


# --- Bulk Import -------------------------------------------------------------


def test_closing_a_bulk_import_tab_closes_its_importer() -> None:
    tab = _bulk_import()

    tab.shutdown_workers()
    tab.close_owned_database()

    tab.importer.close.assert_called_once_with()


def test_a_bulk_import_tab_that_never_imported_has_no_thread_to_wait_for() -> None:
    # ``import_thread`` only exists once an import has been started, so the
    # hooks must not assume the attribute is there.
    tab = _bulk_import()

    tab.shutdown_workers()  # must not raise

    assert not hasattr(tab, "import_thread")


def test_an_overrunning_bulk_import_is_cleaned_up_once_it_ends() -> None:
    tab = _bulk_import(importing=True)
    lock = tab.settings["global_lock"]
    Importer._orphaned_imports.clear()

    tab.shutdown_workers()
    tab.close_owned_database()

    tab.import_thread.wait.assert_called_once()
    tab.importer.close.assert_not_called()
    lock.release.assert_not_called()

    tab.import_thread.isRunning.return_value = False
    Importer.reap_orphaned_imports()

    tab.importer.close.assert_called_once_with()
    lock.release.assert_called_once_with()


# --- the order close_tab relies on -------------------------------------------


def test_the_main_window_stops_the_workers_before_closing_the_database() -> None:
    """Order is the contract: a worker still running holds the importer.

    ``close_owned_database`` refuses to close while a worker runs, so calling
    it first would mean never closing anything.
    """
    tree = ast.parse((ROOT / "fpdb_3_legacy" / "fpdb.pyw").read_text())
    close_tab = next(
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "close_tab"
    )
    hooks = [
        node.value
        for node in ast.walk(close_tab)
        if isinstance(node, ast.Constant) and node.value in ("shutdown_workers", "close_owned_database")
    ]

    assert hooks == ["shutdown_workers", "close_owned_database"]


# --- an import that outlives its tab (#347, Codex P1) ------------------------


class _FakeThread:
    """A worker whose running state the test drives."""

    def __init__(self, *, running: bool = True) -> None:
        self.running = running

    def isRunning(self) -> bool:  # noqa: N802 - Qt's spelling
        return self.running


def _adopted():
    """Adopt one import, and hand back the pieces the cleanup must release."""
    Importer._orphaned_imports.clear()
    thread = _FakeThread()
    importer = MagicMock(name="importer")
    lock = MagicMock(name="global_lock")
    return thread, importer, lock


def test_an_import_that_outlives_its_tab_still_releases_the_global_lock() -> None:
    """The lock is the reason this exists.

    Connections leaked until the process ended; a global lock held past the tab
    blocks every later import and every database-maintenance action for the
    rest of the session.
    """
    thread, importer, lock = _adopted()

    Importer.adopt_orphaned_import(thread, lambda: (importer.close(), lock.release()))
    Importer.reap_orphaned_imports()
    lock.release.assert_not_called()  # still running: nothing may be touched yet

    thread.running = False
    Importer.reap_orphaned_imports()

    importer.close.assert_called_once_with()
    lock.release.assert_called_once_with()


def test_cleanup_runs_at_once_when_the_worker_already_finished() -> None:
    # It can finish between the tab's bounded wait and the adoption.
    _, importer, lock = _adopted()

    Importer.adopt_orphaned_import(_FakeThread(running=False), lambda: (importer.close(), lock.release()))

    lock.release.assert_called_once_with()
    assert not Importer._orphaned_imports


def test_an_adopted_import_is_cleaned_up_only_once() -> None:
    thread, importer, lock = _adopted()
    Importer.adopt_orphaned_import(thread, lambda: (importer.close(), lock.release()))
    thread.running = False

    Importer.reap_orphaned_imports()
    Importer.reap_orphaned_imports()

    lock.release.assert_called_once_with()


def test_a_cleanup_that_fails_does_not_keep_the_import_adopted() -> None:
    thread, _importer, _lock = _adopted()

    def _explode() -> None:
        msg = "the database went away"
        raise RuntimeError(msg)

    Importer.adopt_orphaned_import(thread, _explode)
    thread.running = False
    Importer.reap_orphaned_imports()  # must not raise

    assert not Importer._orphaned_imports


def test_the_adopted_thread_is_kept_referenced_while_it_runs() -> None:
    # Dropping the last reference to a running QThread destroys it mid-run.
    thread, importer, lock = _adopted()

    Importer.adopt_orphaned_import(thread, lambda: (importer.close(), lock.release()))

    assert thread in Importer._orphaned_imports


def test_an_overrunning_auto_import_is_adopted_rather_than_abandoned() -> None:
    tab = _running_auto_import()
    tab.settings = {"global_lock": MagicMock(name="global_lock")}
    tab.pipe_to_hud = None
    Importer._orphaned_imports.clear()

    tab.shutdown_workers()

    assert tab.import_thread in Importer._orphaned_imports
    tab.importer.close.assert_not_called()  # not yet: the worker still holds it


def test_an_overrunning_bulk_import_disconnects_the_slots_it_leaves_behind() -> None:
    # import_finished and import_error also release the lock; if one of them
    # still ran, the release would happen twice -- and release() is not
    # idempotent, so the second raises.
    tab = _bulk_import(importing=True)
    tab.settings = {"global_lock": MagicMock(name="global_lock")}
    Importer._orphaned_imports.clear()

    tab.shutdown_workers()

    tab.import_thread.finished.disconnect.assert_called_once_with(tab.import_finished)
    tab.import_thread.error.disconnect.assert_called_once_with(tab.import_error)
