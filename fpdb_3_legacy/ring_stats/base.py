"""base.py

Contient la classe de base ModernStatsWidget pour les widgets de statistiques
modernes, ainsi que le système d'exécution de requêtes asynchrones en arrière-plan.
"""

from __future__ import annotations

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
        except Exception as e:
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
            f"Une erreur est survenue lors du chargement des statistiques :\n\n{error_message}"
        )

    def closeEvent(self, event) -> None:
        """S'assure que tous les workers d'arrière-plan sont arrêtés avant fermeture."""
        for worker in self._workers:
            if worker.isRunning():
                worker.terminate()
                worker.wait()
        super().closeEvent(event)
