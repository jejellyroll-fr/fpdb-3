"""table_view.py

Contient l'onglet 'Tableaux de Statistiques' qui regroupe la table récapitulative
des limites de jeu et la table détaillée du breakdown des mains.
"""

from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTableView, QLabel, QSplitter, QComboBox
from fpdb_3_legacy.ring_stats.styles import get_theme_palette


class StatsTableView(QWidget):
    """Onglet regroupant les tableaux détaillés réorganisés dans un QSplitter."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        # Sélecteur de groupe de statistiques (Presets)
        preset_layout = QHBoxLayout()
        preset_layout.setContentsMargins(0, 0, 0, 4)
        self.preset_label = QLabel("Groupe de statistiques :")
        from fpdb_3_legacy.ring_stats.styles import get_theme_palette
        c = get_theme_palette()
        muted = c.get('muted_text', '#a0aec0')
        self.preset_label.setStyleSheet(f"font-weight: bold; color: {muted}; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;")
        preset_layout.addWidget(self.preset_label)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "Essentiel",
            "Préflop détaillé",
            "Postflop détaillé",
            "Showdown & Gains",
            "Tout afficher"
        ])
        self.preset_combo.currentIndexChanged.connect(self.apply_preset)
        self.preset_combo.setMinimumWidth(180)
        preset_layout.addWidget(self.preset_combo)
        preset_layout.addStretch()
        layout.addLayout(preset_layout)

        # Splitter vertical pour héberger les deux tableaux
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(self.splitter)

        # 1. Tableau du haut (Niveaux / Limites de jeu)
        self.summary_table = QTableView()
        self.summary_table.setSortingEnabled(True)
        self.summary_table.verticalHeader().hide()
        self.splitter.addWidget(self.summary_table)

        # 2. Séparateur avec titre pour le breakdown des mains
        self.separator_widget = QWidget()
        sep_layout = QVBoxLayout(self.separator_widget)
        sep_layout.setContentsMargins(0, 8, 0, 8)
        self.separator_label = QLabel("Répartition détaillée des mains (Hand Breakdown)")
        self.separator_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.separator_label.setStyleSheet(f"font-weight: bold; text-transform: uppercase; color: {muted}; font-size: 11px;")
        sep_layout.addWidget(self.separator_label)
        self.splitter.addWidget(self.separator_widget)

        # 3. Tableau du bas (Détail par main de départ)
        self.hand_table = QTableView()
        self.hand_table.setSortingEnabled(True)
        self.hand_table.verticalHeader().hide()
        self.splitter.addWidget(self.hand_table)

        # Ajustement des proportions du splitter
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setStretchFactor(2, 4)

    def set_summary_model(self, model) -> None:
        """Assigne le modèle de données du tableau récapitulatif des limites."""
        self.summary_table.setModel(model)
        self._polish_table(self.summary_table)
        self.apply_preset()

    def set_hand_model(self, model) -> None:
        """Assigne le modèle de données du tableau de breakdown des mains."""
        self.hand_table.setModel(model)
        self._polish_table(self.hand_table)
        self.apply_preset()

    def apply_preset(self) -> None:
        """Filtre les colonnes à afficher en fonction du preset sélectionné."""
        preset_name = self.preset_combo.currentText()

        presets = {
            "Essentiel": {
                "game", "hand", "plposition", "pname", "n", "vpip", "pfr", "pf3", "net", "bbper100"
            },
            "Préflop détaillé": {
                "game", "hand", "plposition", "pname", "n", "vpip", "pfr", "rfi", "steals",
                "raisetosteal", "foldsbtosteal", "foldbbtosteal", "pf3", "pf4", "pff3", "pff4", "car0"
            },
            "Postflop détaillé": {
                "game", "hand", "plposition", "pname", "n", "conbet", "aggfac", "aggfrq", "flopen",
                "tnopen", "rvopen", "flafq", "tuafq", "rvafq", "fl3", "tn3", "rv3"
            },
            "Showdown & Gains": {
                "game", "hand", "plposition", "pname", "n", "saw_f", "sawsd", "wtsdwsf", "wmsf", "wmsd",
                "net", "bbper100", "rake", "variance", "stddev"
            }
        }

        preset_cols = presets.get(preset_name, set())

        for table in (self.summary_table, self.hand_table):
            model = table.model()
            if not model:
                continue

            for col in range(model.columnCount()):
                header_item = model.horizontalHeaderItem(col)
                if not header_item:
                    continue
                alias = header_item.data(Qt.ItemDataRole.UserRole + 10)
                if not alias:
                    continue

                # Affiche toujours la colonne si "Tout afficher" ou si l'alias fait partie du preset
                if preset_name == "Tout afficher" or alias in preset_cols:
                    table.setColumnHidden(col, False)
                else:
                    table.setColumnHidden(col, True)

            # Recalculer les largeurs après masquage
            table.resizeColumnsToContents()
            table.resizeColumnToContents(0)
            table.resizeRowsToContents()

    def _polish_table(self, table: QTableView) -> None:
        """Applique des finitions esthétiques de dimensions de colonnes sur le tableau."""
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)

    def refresh_theme(self, colors=None, theme_colors=None) -> None:
        """Force la mise à jour des couleurs et bordures lors d'un changement de thème."""
        c = get_theme_palette()
        muted = c.get('muted_text', '#a0aec0')
        self.preset_label.setStyleSheet(f"font-weight: bold; color: {muted}; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;")
        self.separator_label.setStyleSheet(f"font-weight: bold; text-transform: uppercase; color: {muted}; font-size: 11px;")
        self.summary_table.update()
        self.hand_table.update()
