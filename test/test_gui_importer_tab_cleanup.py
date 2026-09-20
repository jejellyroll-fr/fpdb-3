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

from fpdb_3_legacy.GuiAutoImport import GuiAutoImport
from fpdb_3_legacy.GuiBulkImport import GuiBulkImport

ROOT = Path(__file__).parents[1]


def _idle_auto_import():
    """An auto-import tab that was opened and never started."""
    tab = GuiAutoImport.__new__(GuiAutoImport)
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
    return tab


def _bulk_import(*, importing: bool = False):
    tab = GuiBulkImport.__new__(GuiBulkImport)
    tab.importer = MagicMock(name="importer")
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


def test_an_overrunning_auto_import_keeps_its_connections() -> None:
    # The worker still holds the importer. Closing underneath it would hand it
    # a dead handle, which is worse than the connections it keeps.
    tab = _running_auto_import()

    tab.shutdown_workers()
    tab.close_owned_database()

    tab._finalize_auto_import_stop.assert_not_called()
    tab.importer.close.assert_not_called()


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


def test_an_overrunning_bulk_import_keeps_its_connections() -> None:
    tab = _bulk_import(importing=True)

    tab.shutdown_workers()
    tab.close_owned_database()

    tab.import_thread.wait.assert_called_once()
    tab.importer.close.assert_not_called()


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
