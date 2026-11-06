"""starting_hands_view.py

Affiche l'onglet 'Analyse des Mains' :
- Pour le Hold'em : Grille interactive 13x13 avec coloration thermique (VPIP ou Profit).
- Pour l'Omaha : Analyses catégorielles (suitedness, paires) représentées par des graphiques Matplotlib.

La grille sert aussi de **navigateur de ranges filtré** (#301) : les mêmes 169
cellules affichent la range d'un jeu de filtres analytics (fréquence, échantillon,
profit, profit ajusté EV), une cellule double-cliquée demande les mains
correspondantes, et les mains dont les cartes n'ont jamais été montrées restent
hors de la grille au lieu d'être réparties dans les classes.
"""

from __future__ import annotations

import re
from typing import Any

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.holdem_classes import grid_labels
from fpdb_3_legacy.holdem_ranges import DEFAULT_VIEW, METRICS, RangeCell, RangeMatrix
from fpdb_3_legacy.holdem_ranges import metric as range_metric
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.localized_formats import format_currency, format_number
from fpdb_3_legacy.ring_stats.styles import get_theme_palette


class HoldemGridCell(QFrame):
    """Cellule individuelle de la grille 13x13 pour le Texas Hold'em.

    Deux lectures la remplissent : le rapport de mains historique
    (:meth:`update_stats`) et un range analytics filtré (:meth:`update_range`).
    La seconde n'affiche pas seulement un nombre : elle porte les comptes bruts
    dans son infobulle et se signale quand l'échantillon est trop mince pour
    être coloré comme s'il voulait dire quelque chose.
    """

    activated = Signal(str)

    def __init__(self, hand_text: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("handCell")
        self.hand_text = hand_text
        self.range_cell: RangeCell | None = None
        self.range_view: str = DEFAULT_VIEW
        self.range_total: int = 0
        self.range_scale: float = 0.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        self.label = QLabel(hand_text)
        self.label.setObjectName("handCellText")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

        self.setToolTip(_("Hand: {0}\nNo statistics available").format(hand_text))
        c = get_theme_palette()
        self.set_color(c.get("window", "#2d3748"))  # Couleur du thème par défaut

    def set_color(self, hex_color: str) -> None:
        """Modifie la couleur de fond de la cellule."""
        self.setStyleSheet(f"QFrame#handCell {{ background-color: {hex_color}; }}")

    def update_stats(self, n: int, profit: float, vpip: float, color_by: str = "profit") -> None:
        """Met à jour les statistiques de la cellule et son infobulle."""
        self.setToolTip(
            _("<b>Hand: {0}</b><br/>Hands: {1}<br/>VPIP: {2}%<br/>Profit: {3}").format(
                self.hand_text,
                format_number(n, 0),
                format_number(vpip, 1),
                format_currency(profit, 'EUR', show_plus=profit > 0)
            )
        )

        c = get_theme_palette()
        color_up = c.get("graph_up", "#48bb78")
        color_down = c.get("graph_down", "#f56565")
        accent = c.get("accent", "#319795")
        bg_card = c.get("sidebar", "#1a202c")

        if n > 0:
            if color_by == "vpip":
                # Coloration par VPIP % (dégradé bleu/vert du thème)
                alpha = min(1.0, 0.05 + (vpip / 100.0))
                color = self._interpolate_color(bg_card, accent, alpha)
            else:
                # Coloration par Profit
                if profit > 0:
                    # Dégradé de vert
                    alpha = min(1.0, 0.15 + (profit / 20.0))
                    color = self._interpolate_color(bg_card, color_up, alpha)
                elif profit < 0:
                    # Dégradé de rouge
                    alpha = min(1.0, 0.15 + (abs(profit) / 20.0))
                    color = self._interpolate_color(bg_card, color_down, alpha)
                else:
                    color = c.get("border", "#4a5568")
        else:
            color = bg_card

        self.set_color(color)

    def update_range(self, cell: RangeCell, view: str, total_opportunities: int, scale: float = 0.0) -> None:
        """Affiche une cellule de range filtrée : la valeur, sa couleur et ses comptes.

        Une cellule sous le seuil d'échantillon reste au fond du thème : la
        colorer reviendrait à la présenter comme une lecture, alors que le
        nombre qu'elle porte est le seul fait disponible.
        """
        self.range_cell = cell
        self.range_view = view
        self.range_total = total_opportunities
        self.range_scale = scale
        self.setToolTip(cell.tooltip(view, total_opportunities))
        self.set_color(self._range_color(cell, view, scale))

    def _range_color(self, cell: RangeCell, view: str, scale: float) -> str:
        """La couleur d'une cellule selon la vue active et la mise à l'échelle de la grille."""
        c = get_theme_palette()
        background = c.get("sidebar", "#1a202c")
        if not cell.opportunities or not cell.sample_sufficient:
            return background
        value = cell.metric_value(view)
        if value is None:
            return background
        unit = range_metric(view).unit
        if unit == "cents":
            if not value:
                return c.get("border", "#4a5568")
            colour = c.get("graph_up" if value > 0 else "graph_down", "#48bb78")
            span = max(abs(scale), 1.0)
            return self._interpolate_color(background, colour, min(1.0, 0.15 + abs(value) / span))
        # Une fréquence ou un compte se lit contre le reste de la grille, jamais
        # contre une échelle absolue : un 8 % de 3-bet n'est pas un 8 % de VPIP.
        span = max(scale, 1.0)
        return self._interpolate_color(background, c.get("accent", "#319795"), min(1.0, 0.15 + value / span))

    def mouseDoubleClickEvent(self, event: Any) -> None:
        """Un double-clic demande les mains de la cellule."""
        self.activated.emit(self.hand_text)
        super().mouseDoubleClickEvent(event)

    def _interpolate_color(self, hex1: str, hex2: str, factor: float) -> str:
        """Calcule une couleur interpolée entre deux couleurs hexa."""
        try:
            h1 = hex1.lstrip("#")
            h2 = hex2.lstrip("#")
            r1, g1, b1 = int(h1[0:2], 16), int(h1[2:4], 16), int(h1[4:6], 16)
            r2, g2, b2 = int(h2[0:2], 16), int(h2[2:4], 16), int(h2[4:6], 16)

            r = int(r1 + factor * (r2 - r1))
            g = int(g1 + factor * (g2 - g1))
            b = int(b1 + factor * (b2 - b1))

            return f"#{r:02x}{g:02x}{b:02x}"
        except (AttributeError, IndexError, TypeError, ValueError):
            return hex2


class OmahaChartsWidget(pg.GraphicsLayoutWidget):
    """Tracés pyqtgraph pour analyser les statistiques d'Omaha par catégorie."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.plot1 = self.addPlot(title="Couleurs")
        self.plot2 = self.addPlot(title="Configuration")
        self.update_style()

    def update_style(self) -> None:
        c = get_theme_palette()
        bg_color = c.get("sidebar", "#1a202c")
        text_color = c.get("text", "#edf2f7")
        grid_color = c.get("grid", "#4a5568")

        self.setBackground(bg_color)

        for p in (self.plot1, self.plot2):
            axis_pen = pg.mkPen(color=grid_color, width=1)
            p.getAxis("left").setPen(axis_pen)
            p.getAxis("bottom").setPen(axis_pen)
            p.getAxis("left").setTextPen(pg.mkPen(color=text_color))
            p.getAxis("bottom").setTextPen(pg.mkPen(color=text_color))

    def plot_omaha_analysis(self, suitedness: dict[str, int], pairs: dict[str, int], variant_title: str) -> None:
        self.plot1.clear()
        self.plot2.clear()
        self.update_style()

        c = get_theme_palette()
        text_color = c.get("text", "#edf2f7")
        accent = c.get("accent", "#319795")
        accent_soft = c.get("accent_soft", "#4fd1c5")

        self.plot1.setTitle(f"<span style='color:{text_color}; font-size:9pt; font-weight:bold;'>Couleurs ({variant_title})</span>")
        self.plot2.setTitle(f"<span style='color:{text_color}; font-size:9pt; font-weight:bold;'>Configuration ({variant_title})</span>")

        # 1. Graphe de Suitedness
        if suitedness:
            labels = list(suitedness.keys())
            values = list(suitedness.values())
            x = list(range(len(labels)))
            bg1 = pg.BarGraphItem(x=x, height=values, width=0.5, brush=pg.mkBrush(color=accent), pen=pg.mkPen(color=accent))
            self.plot1.addItem(bg1)
            ticks1 = [(i, label) for i, label in enumerate(labels)]
            self.plot1.getAxis("bottom").setTicks([ticks1])

        # 2. Graphe des Paires
        if pairs:
            labels = list(pairs.keys())
            values = list(pairs.values())
            x = list(range(len(labels)))
            bg2 = pg.BarGraphItem(x=x, height=values, width=0.5, brush=pg.mkBrush(color=accent_soft), pen=pg.mkPen(color=accent_soft))
            self.plot2.addItem(bg2)
            ticks2 = [(i, label) for i, label in enumerate(labels)]
            self.plot2.getAxis("bottom").setTicks([ticks2])


class StartingHandsTab(QWidget):
    """Onglet d'analyse des starting hands (Hold'em / Omaha)."""

    #: Une cellule double-cliquée demande ses mains : le parent décide où les
    #: ouvrir, l'onglet ne fait pas d'entrée/sortie de base de données.
    cell_activated = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(12, 12, 12, 12)

        # Titre dynamique de l'onglet
        self.title_label = QLabel(_("Starting Hands Analysis"))
        c = get_theme_palette()
        self.title_label.setStyleSheet(
            f"font-size: 12px; font-weight: bold; text-transform: uppercase; color: {c.get('muted_text', '#a0aec0')};"
        )
        self.main_layout.addWidget(self.title_label)

        # Conteneur principal qui changera dynamiquement selon le jeu
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addWidget(self.container, 1)

        # Composants pré-créés pour Hold'em et Omaha
        self.holdem_grid_widget = QWidget()
        holdem_main_layout = QVBoxLayout(self.holdem_grid_widget)
        holdem_main_layout.setContentsMargins(0, 0, 0, 0)

        # Toggle de coloration Hold'em
        toggle_layout = QHBoxLayout()
        toggle_lbl = QLabel(_("Color the grid by:"))
        toggle_lbl.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {c.get('muted_text', '#a0aec0')};")
        toggle_layout.addWidget(toggle_lbl)

        self.color_by_combo = QComboBox()
        self.color_by_combo.addItems(["Profit Net (€)", "VPIP (%)"])
        self.color_by_combo.currentIndexChanged.connect(self.on_color_by_changed)
        self.color_by_combo.setMaximumWidth(150)
        toggle_layout.addWidget(self.color_by_combo)

        range_lbl = QLabel(_("Filtered range:"))
        range_lbl.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {c.get('muted_text', '#a0aec0')};")
        toggle_layout.addWidget(range_lbl)

        self.range_view_combo = QComboBox()
        for view_name, spec in METRICS.items():
            self.range_view_combo.addItem(_(spec.label), view_name)
        self.range_view_combo.setCurrentIndex(list(METRICS).index(DEFAULT_VIEW))
        self.range_view_combo.currentIndexChanged.connect(self.on_range_view_changed)
        self.range_view_combo.setMaximumWidth(190)
        toggle_layout.addWidget(self.range_view_combo)

        sample_lbl = QLabel(_("min sample:"))
        sample_lbl.setStyleSheet(f"font-size: 11px; color: {c.get('muted_text', '#a0aec0')};")
        toggle_layout.addWidget(sample_lbl)
        self.min_sample_spin = QSpinBox()
        self.min_sample_spin.setRange(0, 100000)
        self.min_sample_spin.setValue(0)
        self.min_sample_spin.valueChanged.connect(self.on_min_sample_changed)
        self.min_sample_spin.setMaximumWidth(90)
        toggle_layout.addWidget(self.min_sample_spin)
        toggle_layout.addStretch()
        holdem_main_layout.addLayout(toggle_layout)

        # Grille Hold'em
        self.holdem_grid_container = QWidget()
        self.holdem_grid = QGridLayout(self.holdem_grid_container)
        self.holdem_grid.setSpacing(1)
        self.holdem_grid.setContentsMargins(0, 8, 0, 0)
        self.holdem_cells: dict[str, HoldemGridCell] = {}
        self._build_holdem_grid()
        holdem_main_layout.addWidget(self.holdem_grid_container)

        # La légende et la ligne des mains non montrées : un range filtré ne se
        # lit pas sans savoir ce que la couleur veut dire, ni ce qui manque.
        self.range_legend = QLabel("")
        self.range_legend.setObjectName("rangeLegend")
        self.range_legend.setWordWrap(True)
        self.range_legend.setStyleSheet(f"font-size: 10px; color: {c.get('muted_text', '#a0aec0')};")
        holdem_main_layout.addWidget(self.range_legend)

        self.range_unknown = QLabel("")
        self.range_unknown.setObjectName("rangeUnknown")
        self.range_unknown.setWordWrap(True)
        self.range_unknown.setStyleSheet(f"font-size: 10px; color: {c.get('muted_text', '#a0aec0')};")
        holdem_main_layout.addWidget(self.range_unknown)

        self.omaha_widget = QWidget()
        omaha_layout = QVBoxLayout(self.omaha_widget)
        self.omaha_canvas = OmahaChartsWidget(self.omaha_widget)
        omaha_layout.addWidget(self.omaha_canvas)

        self.active_mode: str | None = None  # 'holdem' ou 'omaha'
        self.holdem_hand_stats: dict[str, dict[str, Any]] = {}
        self.holdem_color_by = "profit"
        # Un range analytics filtré remplace la lecture historique quand il est
        # fourni ; ``None`` veut dire "la grille vient d'un rapport de mains".
        self.range_matrix: RangeMatrix | None = None

    def _build_holdem_grid(self) -> None:
        """Construit la grille 13x13 depuis la définition unique des 169 classes.

        Les libellés ne sont pas recomposés ici : ``holdem_classes`` est ce qui
        nomme les classes côté moteur, et une seconde composition de libellés
        dans un widget est exactement la facon dont une cellule finit par
        designer autre chose que la population qu'elle affiche.
        """
        for row, labels in enumerate(grid_labels()):
            for col, hand in enumerate(labels):
                cell = HoldemGridCell(hand)
                cell.activated.connect(self.on_holdem_cell_activated)
                self.holdem_grid.addWidget(cell, row, col)
                self.holdem_cells[hand] = cell

    def on_color_by_changed(self, index: int) -> None:
        """Change la coloration de la grille Hold'em."""
        self.holdem_color_by = "vpip" if index == 1 else "profit"
        self.redraw_holdem_grid()

    def on_range_view_changed(self, _index: int) -> None:
        """Change la mesure affichée par la range filtrée."""
        self.redraw_holdem_grid()

    def on_min_sample_changed(self, value: int) -> None:
        """Re-marque les cellules sous le seuil, sans redemander la base."""
        if self.range_matrix is not None:
            self.range_matrix = self.range_matrix.remarked(value)
        self.redraw_holdem_grid()

    def on_holdem_cell_activated(self, hand_text: str) -> None:
        """Relaye la demande de drill-down d'une cellule."""
        self.cell_activated.emit(hand_text)

    @property
    def range_view(self) -> str:
        """La vue active de la grille filtrée."""
        current = self.range_view_combo.currentData() if hasattr(self, "range_view_combo") else None
        return str(current or DEFAULT_VIEW)

    def update_range_data(self, matrix: RangeMatrix, view: str | None = None) -> None:
        """Affiche un range analytics filtré (#301) dans la grille 13x13.

        La matrice vient du modèle, qui la tient d'une requête : l'onglet ne
        calcule rien, il affiche. Le seuil d'échantillon est celui du module,
        re-marqué avec la valeur du champ de saisie.
        """
        self._set_mode("holdem")
        if view is not None and hasattr(self, "range_view_combo"):
            index = self.range_view_combo.findData(view)
            if index >= 0:
                self.range_view_combo.setCurrentIndex(index)
        self.range_matrix = matrix.remarked(self.min_sample_spin.value())
        self.redraw_holdem_grid()

    def redraw_holdem_grid(self) -> None:
        """Redessine la grille Hold'em : range filtrée si fournie, sinon rapport de mains."""
        if self.range_matrix is not None:
            self._redraw_range_grid(self.range_matrix)
            return
        for hand, cell in self.holdem_cells.items():
            stat = self.holdem_hand_stats.get(hand)
            if stat:
                cell.update_stats(stat.get("n", 0), stat.get("net", 0.0), stat.get("vpip", 0.0), self.holdem_color_by)
            else:
                cell.update_stats(0, 0.0, 0.0, self.holdem_color_by)
        self.range_legend.setText("")
        self.range_unknown.setText("")

    def _redraw_range_grid(self, matrix: RangeMatrix) -> None:
        """Peint les 169 cellules d'un range, puis sa légende et ses mains manquantes."""
        view = self.range_view
        spec = range_metric(view)
        values = [value for row in matrix.values(view) for value in row if value is not None]
        scale = max((abs(value) for value in values), default=0.0)
        for row in matrix.grid():
            for cell in row:
                widget = self.holdem_cells.get(cell.label)
                if widget is not None:
                    widget.update_range(cell, view, matrix.total_opportunities, scale)
        below = matrix.sample_below_threshold()
        legend = [f"{spec.label} ({spec.unit}) - {spec.definition}"]
        legend.append("* below the sample threshold" if below else "no cell is below the sample threshold")
        legend.extend(matrix.notes)
        self.range_legend.setText("\n".join(legend))
        self.range_unknown.setText(
            _("{0} decisions in this selection have no known hole cards and are not in the grid")
            .format(matrix.unknown_opportunities()),
        )

    def update_holdem_data(self, hand_stats: dict[str, dict]) -> None:
        """Affiche la grille de Hold'em et met à jour ses cellules avec les statistiques."""
        self._set_mode("holdem")
        self.range_matrix = None
        self.holdem_hand_stats = hand_stats
        self.redraw_holdem_grid()

    def update_omaha_data(self, hand_stats: list[dict], variant: str = "omaha4") -> None:
        """Affiche et génère les graphiques d'analyse Omaha à partir de la liste des mains."""
        self._set_mode("omaha")

        # Dénomination selon la variante Omaha
        if variant == "omaha5":
            variant_title = "Omaha 5-Card"
            self.title_label.setText(_("Omaha 5-Card Texture Analysis"))
            pairs_counts = {"Quads": 0, "Trips": 0, "Double Paired": 0, "Single Paired": 0, "No Pair": 0}
        elif variant == "omaha6":
            variant_title = "Omaha 6-Card"
            self.title_label.setText(_("Omaha 6-Card Texture Analysis"))
            pairs_counts = {"Quads": 0, "Trips": 0, "Double Paired": 0, "Single Paired": 0, "No Pair": 0}
        else:
            variant_title = "Omaha 4-Card"
            self.title_label.setText(_("Omaha 4-Card Texture Analysis"))
            pairs_counts = {"Double Paired": 0, "Single Paired": 0, "No Pair": 0}

        # Agrégation statistique des mains Omaha
        suitedness_counts = {"Double Suited": 0, "Single Suited": 0, "Rainbow": 0, "Autre": 0}

        for row in hand_stats:
            hand_str = str(row.get("hand", ""))
            n = row.get("n", 0)

            # 1. Analyse de suitedness (ds, ss, r)
            if "ds" in hand_str:
                suitedness_counts["Double Suited"] += n
            elif "ss" in hand_str:
                suitedness_counts["Single Suited"] += n
            elif "r" in hand_str or "rainbow" in hand_str:
                suitedness_counts["Rainbow"] += n
            else:
                suitedness_counts["Autre"] += n

            # 2. Analyse des paires (détection de doublons dans la chaîne des hauteurs)
            match = re.match(r"^([AKQJT98765432]+)", hand_str)
            if match:
                ranks_part = match.group(1)
                counts: dict[str, int] = {}
                for char in ranks_part:
                    counts[char] = counts.get(char, 0) + 1

                vals = list(counts.values())
                if variant in ("omaha5", "omaha6"):
                    if 4 in vals:
                        pairs_counts["Quads"] += n
                    elif 3 in vals:
                        pairs_counts["Trips"] += n
                    elif vals.count(2) == 2:
                        pairs_counts["Double Paired"] += n
                    elif 2 in vals:
                        pairs_counts["Single Paired"] += n
                    else:
                        pairs_counts["No Pair"] += n
                else:
                    if vals.count(2) == 2:
                        pairs_counts["Double Paired"] += n
                    elif 2 in vals:
                        pairs_counts["Single Paired"] += n
                    else:
                        pairs_counts["No Pair"] += n

        # Nettoyage des catégories vides
        suitedness_counts = {k: v for k, v in suitedness_counts.items() if v > 0}
        pairs_counts = {k: v for k, v in pairs_counts.items() if v > 0}

        self.omaha_canvas.plot_omaha_analysis(suitedness_counts, pairs_counts, variant_title)

    def _set_mode(self, mode: str) -> None:
        """Bascule l'affichage entre Hold'em et Omaha."""
        if self.active_mode == mode:
            return

        self.active_mode = mode

        # Vider le layout du conteneur
        while self.container_layout.count() > 0:
            item = self.container_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        # Ajouter le widget correspondant
        if mode == "holdem":
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(self.holdem_grid_widget)
            self.container_layout.addWidget(scroll)
            self.title_label.setText(_("Hold'em Starting Hand Grid"))
        elif mode == "omaha":
            self.container_layout.addWidget(self.omaha_widget)
            # Sera mis à jour par la méthode update_omaha_data
            self.title_label.setText(_("Omaha Texture Analysis"))

    def refresh_theme(self, colors=None, theme_colors=None) -> None:
        if self.active_mode == "omaha":
            self.omaha_canvas.update_style()
        elif self.active_mode == "holdem":
            self.redraw_holdem_grid()
