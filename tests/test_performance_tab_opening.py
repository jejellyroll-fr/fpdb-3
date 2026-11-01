"""Tests for performance optimizations when creating tabs in FPDB."""

from __future__ import annotations

from unittest.mock import MagicMock

from fpdb_3_legacy.Filters import Filters


class _SignalStub:
    def connect(self, _callback) -> None:
        pass


class _WorkerStub:
    created_with = None

    def __init__(self, cursor, query_name, query_sql) -> None:
        type(self).created_with = (cursor, query_name, query_sql)
        self.finished = _SignalStub()
        self.error = _SignalStub()

    def start(self) -> None:
        pass


def test_filters_uses_isolated_cursor() -> None:
    """Verify Filters creates a dedicated cursor to avoid lock contention on db.cursor."""
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        _app = QApplication([])

    mock_connection = MagicMock()
    mock_dedicated_cursor = MagicMock()
    mock_connection.cursor.return_value = mock_dedicated_cursor

    mock_db = MagicMock()
    mock_db.connection = mock_connection
    mock_db.cursor = MagicMock()
    mock_db.config.get_supported_sites.return_value = []
    mock_db.config.get_general_params.return_value = {}

    filters = Filters(mock_db)

    # Dedicated cursor should be used instead of sharing mock_db.cursor
    assert filters.db_cursor == mock_dedicated_cursor
    assert filters.db_cursor != mock_db.cursor


def test_session_viewer_passes_database_to_db_worker(monkeypatch) -> None:
    """The worker receives the facade so it can open a dedicated connection."""
    from PySide6.QtWidgets import QApplication, QWidget

    import fpdb_3_legacy.GuiSessionViewer as session_viewer_module

    class _FiltersStub(QWidget):
        def __init__(self, *_args, **_kwargs) -> None:
            super().__init__()

        def registerButton1Name(self, _name) -> None:  # noqa: N802 - mirrors Filters API
            pass

        def registerButton1Callback(self, _callback) -> None:  # noqa: N802 - mirrors Filters API
            pass

    _app = QApplication.instance() or QApplication([])
    cursor = object()
    db = MagicMock(cursor=cursor)
    config = MagicMock()
    config.get_db_parameters.return_value = {}
    config.get_import_parameters.return_value = {}
    monkeypatch.setattr(session_viewer_module.Database, "Database", MagicMock(return_value=db))
    monkeypatch.setattr(session_viewer_module.Filters, "Filters", _FiltersStub)
    monkeypatch.setattr(session_viewer_module, "DbWorker", _WorkerStub)

    viewer = session_viewer_module.GuiSessionViewer(
        config,
        MagicMock(),
        None,
        None,
        {"background": "#000000"},
    )
    viewer.build_session_query = MagicMock(return_value="SELECT 1")

    viewer.createStatsPane(MagicMock(), [], [], [], [], [], [])

    assert _WorkerStub.created_with == (db, "sessionStats", "SELECT 1")
    viewer.close()
