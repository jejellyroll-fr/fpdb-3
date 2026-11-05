"""What a real failure leaves in the crash file of a process that really runs Qt.

Each failure happens in a spawned process, under the offscreen platform: it has to
be real, and installing the hooks or faulthandler here would take them away from
the test run. Nothing is mocked around the failure, because whether PySide6 hands a
slot's exception to ``sys.excepthook`` is the very thing being checked.

The real ``fpdb.pyw`` runs on a throwaway HOME, so the player's own configuration is
never touched. The real HUD does not run here: it would collide on port 5555 with a
HUD already running. ``test_HUD_main.py`` checks that it enables its file.
"""

from __future__ import annotations

import contextlib
import faulthandler
import multiprocessing
import os
import runpy
import sys
import threading
from pathlib import Path

import pytest

from fpdb_3_legacy.hud_diagnostics import MAIN_CRASH_LOG_NAME, enable_crash_log

pytestmark = pytest.mark.qt

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_spawned(target: object, *args: object) -> int | None:
    process = multiprocessing.get_context("spawn").Process(target=target, args=args)
    process.start()
    process.join(240)
    if process.exitcode is None:
        process.kill()
        process.join()
        pytest.fail(f"{target} did not finish")
    return process.exitcode


def _raise_from_qt_with_the_log_enabled(log_dir: str, errors_file: str) -> None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
    from PySide6.QtWidgets import QApplication, QPushButton

    class Worker(QObject):
        started = Signal()

        @Slot()
        def fail(self) -> None:
            raise ValueError("in a slot on a worker thread")

    def fail_in_a_slot() -> None:
        raise ValueError("in a slot on table bob")

    def fail_in_a_click() -> None:
        raise ValueError("in a click")

    enable_crash_log(log_dir, MAIN_CRASH_LOG_NAME)
    app = QApplication([])
    button = QPushButton()
    button.clicked.connect(fail_in_a_click)

    worker_thread = QThread()
    worker = Worker()
    worker.moveToThread(worker_thread)
    worker.started.connect(worker.fail)
    worker_thread.start()

    QTimer.singleShot(0, fail_in_a_slot)
    QTimer.singleShot(0, button.click)
    QTimer.singleShot(0, worker.started.emit)
    # Reached only if the app kept running through all three.
    QTimer.singleShot(500, app.quit)
    # What fpdb and the HUD do on start: the previous hook has to keep writing there.
    with Path(errors_file).open("w", encoding="utf-8") as errors, contextlib.redirect_stderr(errors):
        assert app.exec() == 0

    worker_thread.quit()
    worker_thread.wait()


def test_a_real_exception_in_a_qt_slot_reaches_the_crash_file(tmp_path: Path) -> None:
    errors_file = tmp_path / "errors.txt"

    assert _run_spawned(_raise_from_qt_with_the_log_enabled, str(tmp_path), str(errors_file)) == 0

    written = (tmp_path / MAIN_CRASH_LOG_NAME).read_text(encoding="utf-8")
    errors = errors_file.read_text(encoding="utf-8")
    for message in ("in a slot on table bob", "in a click", "in a slot on a worker thread"):
        assert f"ValueError: {message}" in written
        assert f"ValueError: {message}" in errors
    assert written.count("--- uncaught exception ") == 3


def _run_real_fpdb(failure: str) -> None:
    """Run ``fpdb.pyw`` as the app runs it, and fail as soon as its event loop runs."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    sys.path[:0] = [str(REPO_ROOT), str(REPO_ROOT / "fpdb_3_legacy")]
    sys.argv = ["fpdb"]
    import PySide6.QtWidgets as qt_widgets
    from PySide6.QtCore import QTimer

    # A first run asks questions, and no one is there to answer them. Answering
    # also keeps the failure out of a modal box opened before the first paint,
    # where PySide6 defers it instead of calling sys.excepthook: see the PR of #699.
    qt_widgets.QDialog.exec = lambda _self: 0
    qt_widgets.QMessageBox.exec = lambda _self: 0
    qt_widgets.QMessageBox.question = staticmethod(lambda *_args: qt_widgets.QMessageBox.StandardButton.No)

    def fail() -> None:
        if failure == "slot":
            raise ValueError("in a slot of fpdb")
        if failure == "thread":

            def fail_in_a_thread() -> None:
                raise ValueError("in a thread of fpdb")

            thread = threading.Thread(target=fail_in_a_thread)
            thread.start()
            thread.join()
        if failure == "native":
            faulthandler._sigsegv()

    class App(qt_widgets.QApplication):
        def exec(self) -> int:
            if failure == "main":
                raise ValueError("on the main thread of fpdb")
            QTimer.singleShot(0, fail)
            QTimer.singleShot(500, self.quit)
            return super().exec()

    qt_widgets.QApplication = App
    # multiprocessing catches what leaves its target before the interpreter can
    # hand it to sys.excepthook, so do what the interpreter does for fpdb.pyw.
    try:
        runpy.run_path(str(REPO_ROOT / "fpdb_3_legacy" / "fpdb.pyw"), run_name="__main__")
    except ValueError:
        sys.excepthook(*sys.exc_info())
        os._exit(1)
    # The app's own teardown is not under test.
    os._exit(0)


@pytest.fixture
def throwaway_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.delenv("FPDB_SESSION_ID", raising=False)
    return tmp_path


def _log_dir(home: Path) -> Path:
    return home / ("fpdb" if sys.platform == "win32" else ".fpdb") / "log"


def test_real_fpdb_keeps_its_failures_across_restarts(throwaway_home: Path) -> None:
    assert _run_spawned(_run_real_fpdb, "slot") == 0
    errors_file = _log_dir(throwaway_home) / "fpdb-errors.txt"
    assert _run_spawned(_run_real_fpdb, "thread") == 0
    assert _run_spawned(_run_real_fpdb, "main") != 0
    assert _run_spawned(_run_real_fpdb, "native") not in (None, 0)
    # The next start empties the error file, which is why this file exists.
    assert _run_spawned(_run_real_fpdb, "none") == 0

    assert "in a slot of fpdb" not in errors_file.read_text(encoding="utf-8")
    written = (_log_dir(throwaway_home) / MAIN_CRASH_LOG_NAME).read_text(encoding="utf-8")
    assert written.count("--- started ") == 5
    assert written.count("--- uncaught exception ") == 3
    assert "ValueError: in a slot of fpdb" in written
    assert "ValueError: in a thread of fpdb" in written
    assert "ValueError: on the main thread of fpdb" in written
    assert "Fatal Python error: Segmentation fault" in written or "Windows fatal exception" in written


@pytest.mark.skipif(sys.platform == "win32", reason="chmod does not make a directory read-only on Windows")
def test_real_fpdb_runs_with_a_log_directory_it_cannot_write(throwaway_home: Path) -> None:
    log_dir = _log_dir(throwaway_home)
    log_dir.mkdir(parents=True)
    log_dir.chmod(0o555)
    try:
        assert _run_spawned(_run_real_fpdb, "slot") == 0
    finally:
        log_dir.chmod(0o755)
