import os
import sys
from unittest.mock import MagicMock

import pytest

# Mock GUI dependencies only if not installed
try:
    import PySide6  # noqa: F401 -- availability probe
    # PySide6 is installed, no mock needed!
except ImportError:
    pyside_mock = MagicMock()
    pyside_mock.__version__ = "6.5.0"
    sys.modules["PySide6"] = pyside_mock

    qtcore_mock = MagicMock()
    qtcore_mock.__version__ = "6.5.0"
    qtcore_mock.qVersion.return_value = "6.5.0"
    sys.modules["PySide6.QtCore"] = qtcore_mock

    qtgui_mock = MagicMock()
    qtgui_mock.__version__ = "6.5.0"
    sys.modules["PySide6.QtGui"] = qtgui_mock

    qtwidgets_mock = MagicMock()
    qtwidgets_mock.__version__ = "6.5.0"
    sys.modules["PySide6.QtWidgets"] = qtwidgets_mock

    qtest_mock = MagicMock()
    qtest_mock.__version__ = "6.5.0"
    sys.modules["PySide6.QtTest"] = qtest_mock

    qtuitools_mock = MagicMock()
    qtuitools_mock.__version__ = "6.5.0"
    sys.modules["PySide6.QtUiTools"] = qtuitools_mock

    qtsvg_mock = MagicMock()
    qtsvg_mock.__version__ = "6.5.0"
    sys.modules["PySide6.QtSvg"] = qtsvg_mock

    # Bind sub-modules to PySide6 mock to satisfy attribute access (e.g. PySide6.QtCore)
    pyside_mock.QtCore = qtcore_mock
    pyside_mock.QtGui = qtgui_mock
    pyside_mock.QtWidgets = qtwidgets_mock
    pyside_mock.QtTest = qtest_mock
    pyside_mock.QtUiTools = qtuitools_mock
    pyside_mock.QtSvg = qtsvg_mock

@pytest.fixture
def legacy_config(tmp_path):
    """Real config instance with SQLite file-based database parameters overridden."""
    from fpdb_3_legacy.Configuration import Config
    config_path = "HUD_config.test.xml" if os.path.exists("HUD_config.test.xml") else "HUD_config.xml"
    cfg = Config(file=config_path)
    db_file = tmp_path / "test_db.sqlite3"
    db_params = cfg.get_db_parameters()
    db_params["db-host"] = "localhost"
    db_params["db-server"] = "sqlite"
    db_params["db-port"] = 5432
    db_params["db-name"] = str(db_file)
    db_params["db-user"] = "test"
    db_params["db-password"] = "test"
    db_params["db-backend"] = 4  # SQLite file-based
    db_params["db-databaseName"] = str(db_file)
    db_params["db-path"] = ""
    cfg.get_db_parameters = lambda: db_params
    return cfg

@pytest.fixture
def fresh_db(legacy_config):
    """Jetable SQLite :memory: database with a fresh schema, cleaned up on teardown."""
    from fpdb_3_legacy.Database import Database
    db = Database(legacy_config)
    db.recreate_tables()
    yield db
    db.disconnect()

@pytest.fixture
def importer(legacy_config, fresh_db):
    """Importer instance set up with the fresh in-memory database."""
    from fpdb_3_legacy.Importer import Importer
    # Initialize the Importer with settings
    imp = Importer(
        caller=None,
        settings={"testData": False, "threads": 1},
        config=legacy_config,
        sql=None
    )
    imp.database = fresh_db
    return imp


# Failure logs and diagnostic hooks for Windows CI. They stay in the job's own
# log: failure tracebacks are never sent to a service outside the repository.
def pytest_terminal_summary(terminalreporter, exitstatus, config):
    import os
    import sys

    if os.environ.get("GITHUB_ACTIONS") and sys.platform == "win32" and exitstatus != 0:
        log_lines = []
        log_lines.append(f"Pytest Session Finished with exit status: {exitstatus}")

        # Capture error stats (setup/teardown/collection errors)
        errors = terminalreporter.stats.get('error', [])
        log_lines.append(f"Total setup/collection/teardown errors: {len(errors)}")
        for rep in errors:
            log_lines.append(f"ERROR/COLLECT in {getattr(rep, 'nodeid', 'unknown')}:")
            log_lines.append(str(getattr(rep, 'longrepr', 'No traceback info')))
            log_lines.append("="*80)

        # Capture failure stats (test failures)
        failures = terminalreporter.stats.get('failed', [])
        log_lines.append(f"Total test failures: {len(failures)}")
        for rep in failures:
            log_lines.append(f"FAIL in {getattr(rep, 'nodeid', 'unknown')}:")
            log_lines.append(str(getattr(rep, 'longrepr', 'No traceback info')))
            log_lines.append("="*80)

        terminalreporter.section("Windows CI diagnostics")
        for line in log_lines:
            terminalreporter.write_line(line)


# Collect on the main thread only, as fpdb and the HUD do (#707). Left to
# Python, a collection runs on whichever thread crosses the threshold: a worker
# such as HudReadWorker then destroyed widgets of the main thread, and the Qt
# suite deadlocked on it. Between tests, on the main thread, the policy of
# fpdb_3_legacy.main_thread_gc runs instead of its timer.
def pytest_sessionstart():
    import gc

    gc.disable()


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown():
    import gc

    from fpdb_3_legacy.main_thread_gc import collect_if_due

    gc.disable()  # in case a test turned it back on
    collect_if_due()


# --- Windows the Qt tests leave behind (#765) -----------------------------------------
#
# The whole Qt suite shares one process and one QApplication. A dialog a test
# builds and never closes stays alive for the rest of the run, and every
# ``QApplication.setStyleSheet`` (a theme change) re-polishes all the widgets
# alive. The HUD editor has about 1,200 widgets: with a hundred of them left
# over, the two theme test files took 93 of the 96 minutes of the Qt step.
#
# Only the windows of these classes are disposed. Deleting every top-level
# widget crashes: combo-box popups, pyqtgraph's menus and the views of the
# stats tabs are owned elsewhere, and some tests keep a window across tests.
LEAKY_WINDOWS = frozenset({"ModernHudPreferences", "HudDesignCanvas", "_CanvasChip"})

# What a healthy run leaves alive at the end is about 7,000 widgets; before the
# fix it was 110,000. The ceiling sits between, with room for new tests.
MAX_WIDGETS_ALIVE = 20_000


def _qt_widgets():
    """QApplication and the shiboken module, once PySide6 is really loaded."""
    if isinstance(sys.modules.get("PySide6"), MagicMock):
        return None
    widgets = sys.modules.get("PySide6.QtWidgets")
    if widgets is None or isinstance(widgets, MagicMock):
        return None
    app = widgets.QApplication.instance()
    return (app, sys.modules["shiboken6"]) if app is not None and "shiboken6" in sys.modules else None


def _top_levels(app, shiboken):
    return {shiboken.getCppPointer(w)[0]: w for w in app.topLevelWidgets()}


@pytest.fixture(autouse=True)
def _dispose_leaked_windows():
    """Close the HUD editor windows a test opened and did not close."""
    qt = _qt_widgets()
    before = _top_levels(*qt).keys() if qt else frozenset()
    yield
    qt = _qt_widgets()
    if qt is None:
        return
    app, shiboken = qt
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QWidget

    disposed = False
    for pointer, window in _top_levels(app, shiboken).items():
        if pointer in before or not any(cls.__name__ in LEAKY_WINDOWS for cls in type(window).__mro__):
            continue
        # Qt's own parent(): some windows keep their owner in a ``parent`` attribute.
        if QWidget.parent(window) is None:
            window.hide()
            window.deleteLater()
            disposed = True
    if disposed:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session):
    """Fail the run when widgets pile up again, before the CI slows to a crawl."""
    qt = _qt_widgets()
    if qt is None:
        return
    alive = len(qt[0].allWidgets())
    if alive > MAX_WIDGETS_ALIVE:
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            reporter.write_line(
                f"{alive} widgets are still alive after the tests (the limit is {MAX_WIDGETS_ALIVE}): "
                "a test leaves windows open. Every theme change re-polishes them all and the Qt "
                "suite slows down; close or delete them at the end of the test (#765).",
                red=True,
            )
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
