"""GuiRingPlayerStats.py

Point d'entrée redirigeant vers l'implémentation modernisée et modulaire du package ring_stats.
Conserve une compatibilité descendante totale et inclut le lanceur autonome pour les tests.
"""

from __future__ import annotations
import sys
from PySide6.QtWidgets import QApplication, QMainWindow

# Import de la classe modernisée depuis le package ring_stats
from fpdb_3_legacy.ring_stats import GuiRingPlayerStats


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    import fpdb_3_legacy.Configuration as Configuration
    config = Configuration.Config()

    settings = {}
    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())

    app = QApplication([])
    import fpdb_3_legacy.SQL as SQL

    sql = SQL.Sql(db_server=settings["db-server"])
    main_window = QMainWindow()

    # Instanciation de la classe modernisée
    viewer = GuiRingPlayerStats(config, sql, main_window)
    main_window.setCentralWidget(viewer)
    main_window.show()
    main_window.resize(1400, 800)

    # Lancement initial des stats
    viewer.refreshStats()

    app.exec()
    return 0


if __name__ == "__main__":
    sys.exit(main())
