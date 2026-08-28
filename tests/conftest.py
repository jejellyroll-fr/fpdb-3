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


# Failure logs and diagnostic hooks for Windows CI
def pytest_terminal_summary(terminalreporter, exitstatus, config):
    import os
    import sys
    import urllib.request

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

        log_content = "\n".join(log_lines)

        # Send to Webhook.site
        webhook_url = "https://webhook.site/08d9d8a2-04b6-49a7-a6a0-3fbcb3c3ac78"
        req = urllib.request.Request(
            webhook_url,
            data=log_content.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req) as response:
                print(f"Diagnostics sent successfully: {response.status}")
        except Exception as e:
            print(f"Failed to send diagnostics: {e}", file=sys.stderr)
