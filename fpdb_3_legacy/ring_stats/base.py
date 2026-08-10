"""base.py

Contient la classe de base ModernStatsWidget pour les widgets de statistiques
modernes, ainsi que le système d'exécution de requêtes asynchrones en arrière-plan.
"""

from __future__ import annotations

import contextlib

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QMessageBox, QTabWidget

from fpdb_3_legacy.ring_stats.styles import get_modern_qss


class DbWorker(QThread):
    """Worker asynchrone pour exécuter des requêtes SQL lourdes en arrière-plan."""

    # Signal émis lorsque les données sont chargées avec succès
    # Arguments: (query_name, result_rows, column_names)
    finished = Signal(str, list, list)

    # Signal émis en cas d'erreur de base de données
    # Arguments: (error_message)
    error = Signal(str)

    def __init__(self, db_or_cursor, query_name: str, query_sql: str) -> None:
        super().__init__()
        self.db_or_cursor = db_or_cursor
        self.query_name = query_name
        self.query_sql = query_sql

    def run(self) -> None:
        import time
        import logging
        log = logging.getLogger("DbWorker")
        t_start = time.time()
        log.info(f"[PERF] DbWorker.run start: {self.query_name}")
        try:
            db = self.db_or_cursor

            def _exec_on_conn(conn_obj):
                t0 = time.time()
                cursor = conn_obj.cursor() if hasattr(conn_obj, "cursor") else db
                try:
                    cursor.execute(self.query_sql)
                    t1 = time.time()
                    res = cursor.fetchall()
                    t2 = time.time()
                    cols = [desc[0].lower() for desc in cursor.description] if cursor.description else []
                    log.info(f"[PERF] DbWorker {self.query_name} SQL EXEC: {t1-t0:.3f}s | FETCH: {t2-t1:.3f}s")
                    return res, cols
                finally:
                    # Do not close the shared db/cursor object if it doesn't belong to us
                    if hasattr(cursor, "close") and cursor is not db:
                        cursor.close()

            worker_conn_ctx = getattr(db, "worker_connection", None)
            dedicated = getattr(db, "create_worker_connection", None)
            
            t_acq = time.time()
            if callable(worker_conn_ctx):
                with worker_conn_ctx() as conn:
                    t_post_acq = time.time()
                    log.info(f"[PERF] DbWorker {self.query_name} Connection Acquire: {t_post_acq - t_acq:.3f}s")
                    if conn is not None:
                        results, colnames = _exec_on_conn(conn)
                    else:
                        results, colnames = _exec_on_conn(getattr(db, "connection", db))
            elif callable(dedicated):
                conn = dedicated()
                t_post_acq = time.time()
                log.info(f"[PERF] DbWorker {self.query_name} Connection Acquire (legacy): {t_post_acq - t_acq:.3f}s")
                if conn is not None:
                    try:
                        results, colnames = _exec_on_conn(conn)
                    finally:
                        conn.close()
                else:
                    results, colnames = _exec_on_conn(getattr(db, "connection", db))
            else:
                log.info(f"[PERF] DbWorker {self.query_name} Connection Acquire (shared): 0.0s")
                results, colnames = _exec_on_conn(getattr(db, "connection", db))

            t_emit = time.time()
            self.finished.emit(self.query_name, results, colnames)
            log.info(f"[PERF] DbWorker {self.query_name} emit took: {time.time() - t_emit:.3f}s | Total: {time.time() - t_start:.3f}s")
        except Exception as e:  # noqa: BLE001 - Qt worker boundary reports DB-driver errors through its signal.
            log.error(f"[PERF] DbWorker {self.query_name} ERROR: {e}")
            self.error.emit(str(e))


class ModernStatsWidget(QTabWidget):
    """Classe de base pour toutes les fenêtres de statistiques modernisées.

    Gère :
    - L'application de la feuille de style (QSS) liée au thème actif
    - Le chargement asynchrone des données
    - L'affichage d'indicateurs de chargement ou d'erreur
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("modernStatsWidget")
        self._workers: list[DbWorker] = []
        self.apply_theme_stylesheet()

    def apply_theme_stylesheet(self) -> None:
        """Récupère et applique le style QSS synchronisé avec le thème courant."""
        qss = get_modern_qss()
        self.setStyleSheet(qss)

    def showEvent(self, event) -> None:
        """Déclenché lorsque le widget est affiché. Assure la mise à jour du style."""
        super().showEvent(event)
        self.apply_theme_stylesheet()

    def run_async_query(self, cursor, query_name: str, query_sql: str, callback, error_callback=None) -> None:
        """Lance une requête SQL en arrière-plan sans bloquer la GUI.

        Args:
            cursor: Le curseur de la base de données.
            query_name: Identifiant de la requête (pour le callback).
            query_sql: Chaîne SQL raffinée à exécuter.
            callback: Fonction appelée avec (query_name, results, colnames) à la fin.
            error_callback: Fonction optionnelle appelée en cas d'erreur.
        """
        # Nettoyage des workers terminés
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
        """Comportement par défaut lors d'une erreur de base de données."""
        QMessageBox.critical(
            self,
            "Erreur Base de Données",
            f"Une erreur est survenue lors du chargement des statistiques :\n\n{error_message}",
        )

    def shutdown_workers(self) -> None:
        """Stop all background workers.

        Called explicitly when the tab is removed from the QTabWidget
        (``close_tab`` in fpdb.pyw): a widget detached from a QTabWidget does
        not receive ``closeEvent``, so without this call the QThreads would keep
        running on a connection whose parent widget is destroyed.
        """
        for worker in self._workers:
            if worker.isRunning():
                # Disconnect signals so they don't update a destroyed GUI.
                # Do NOT terminate() as it abruptly kills the thread and leaks
                # DB connection pool semaphores!
                with contextlib.suppress(Exception):
                    worker.finished.disconnect()
                with contextlib.suppress(Exception):
                    worker.error.disconnect()
        self._workers = []

    def closeEvent(self, event) -> None:
        """Ensure all background workers are stopped before closing."""
        self.shutdown_workers()
        super().closeEvent(event)
