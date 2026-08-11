"""base.py

Contains the ModernStatsWidget base class for statistics widgets
modern components, as well as the asynchronous background query execution system.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QMessageBox, QTabWidget

from fpdb_3_legacy.ring_stats.styles import get_modern_qss


class DbWorker(QThread):
    """Asynchronous worker for executing heavy SQL queries in the background."""

    # Signal emitted when data is loaded successfully
    # Arguments: (query_name, result_rows, column_names)
    finished = Signal(str, list, list)

    # Signal emitted when a database error occurs
    # Arguments: (error_message)
    error = Signal(str)

    def __init__(self, cursor, query_name: str, query_sql: str) -> None:
        super().__init__()
        self.cursor = cursor
        self.query_name = query_name
        self.query_sql = query_sql

    def run(self) -> None:
        try:
            self.cursor.execute(self.query_sql)
            results = self.cursor.fetchall()
            colnames = [desc[0].lower() for desc in self.cursor.description] if self.cursor.description else []
            self.finished.emit(self.query_name, results, colnames)
        except Exception as e:  # noqa: BLE001 - Qt worker boundary reports DB-driver errors through its signal.
            self.error.emit(str(e))


class ModernStatsWidget(QTabWidget):
    """Base class for all modernized statistics windows.

    Handles:
    - Applying the stylesheet (QSS) for the active theme
    - Asynchronous data loading
    - Displaying loading or error indicators
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("modernStatsWidget")
        self._workers: list[DbWorker] = []
        self.apply_theme_stylesheet()

    def apply_theme_stylesheet(self) -> None:
        """Retrieve and apply the QSS style synchronized with the current theme."""
        qss = get_modern_qss()
        self.setStyleSheet(qss)

    def showEvent(self, event) -> None:
        """Called when the widget is shown. Ensures the style is updated."""
        super().showEvent(event)
        self.apply_theme_stylesheet()

    def run_async_query(self, cursor, query_name: str, query_sql: str, callback, error_callback=None) -> None:
        """Run a SQL query in the background without blocking the GUI.

        Args:
            cursor: Database cursor.
            query_name: Query identifier (for the callback).
            query_sql: Refined SQL statement to execute.
            callback: Function called with (query_name, results, colnames) on completion.
            error_callback: Optional function called on error.
        """
        # Clean up completed workers
        self._workers = [w for w in self._workers if not w.isFinished()]

        worker = DbWorker(cursor, query_name, query_sql)
        worker.finished.connect(callback)

        if error_callback:
            worker.error.connect(error_callback)
        else:
            worker.error.connect(self.handle_db_error)

        self._workers.append(worker)
        worker.start()

    def handle_db_error(self, error_message: str) -> None:
        """Default behavior when a database error occurs."""
        QMessageBox.critical(
            self,
            "Database Error",
            f"Une erreur est survenue lors du chargement des statistiques :\n\n{error_message}",
        )

    def closeEvent(self, event) -> None:
        """Ensure all background workers are stopped before closing."""
        for worker in self._workers:
            if worker.isRunning():
                worker.terminate()
                worker.wait()
        super().closeEvent(event)
