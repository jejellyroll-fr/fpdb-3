"""starting_hands_view.py

Affiche l'onglet 'Analyse des Mains' :
- Pour le Hold'em : Grille interactive 13x13 avec coloration thermique (VPIP ou Profit).
- Pour l'Omaha : Analyses catégorielles (suitedness, paires) représentées par des graphiques Matplotlib.
"""

from __future__ import annotations
import re
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QScrollArea, QFrame, QComboBox
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from fpdb_3_legacy.ring_stats.styles import get_theme_palette


class HoldemGridCell(QFrame):
    """Cellule individuelle de la grille 13x13 pour le Texas Hold'em."""

    def __init__(self, hand_text: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("handCell")
        self.hand_text = hand_text
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        
        self.label = QLabel(hand_text)
        self.label.setObjectName("handCellText")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)
        
        self.setToolTip(f"Main : {hand_text}\nAucune statistique disponible")
        c = get_theme_palette()
        self.set_color(c.get("window", "#2d3748"))  # Couleur du thème par défaut

    def set_color(self, hex_color: str) -> None:
        """Modifie la couleur de fond de la cellule."""
        self.setStyleSheet(f"QFrame#handCell {{ background-color: {hex_color}; }}")

    def update_stats(self, n: int, profit: float, vpip: float, color_by: str = "profit") -> None:
        """Met à jour les statistiques de la cellule et son infobulle."""
        self.setToolTip(
            f"<b>Main : {self.hand_text}</b><br/>"
            f"Nombre de mains : {n:,}<br/>"
            f"VPIP : {vpip:.1f}%<br/>"
            f"Profit : {profit:+.2f} €"
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

    def _interpolate_color(self, hex1: str, hex2: str, factor: float) -> str:
        """Calcule une couleur interpolée entre deux couleurs hexa."""
        try:
            h1 = hex1.lstrip('#')
            h2 = hex2.lstrip('#')
            r1, g1, b1 = int(h1[0:2], 16), int(h1[2:4], 16), int(h1[4:6], 16)
            r2, g2, b2 = int(h2[0:2], 16), int(h2[2:4], 16), int(h2[4:6], 16)
            
            r = int(r1 + factor * (r2 - r1))
            g = int(g1 + factor * (g2 - g1))
            b = int(b1 + factor * (b2 - b1))
            
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex2


class OmahaChartsCanvas(FigureCanvas):
    """Tracés Matplotlib pour analyser les statistiques d'Omaha par catégorie."""

    def __init__(self, parent=None) -> None:
        self.fig = Figure(figsize=(6, 4), dpi=100)
        super().__init__(self.fig)
        self.setParent(parent)
        self.update_style()

    def update_style(self) -> None:
        c = get_theme_palette()
        self.fig.patch.set_facecolor(c.get("sidebar", "#1a202c"))
        self.draw()

    def plot_omaha_analysis(self, suitedness: dict[str, int], pairs: dict[str, int], variant_title: str) -> None:
        self.fig.clear()
        self.update_style()
        
        c = get_theme_palette()
        text_color = c.get("text", "#edf2f7")
        accent = c.get("accent", "#319795")
        accent_soft = c.get("accent_soft", "#4fd1c5")
        orange = c.get("graph_ev", "#f59e3d")
        color_down = c.get("graph_down", "#f56565")
        
        # 2 Graphiques côte à côte : Répartition des couleurs (Suits) et des Paires
        ax1 = self.fig.add_subplot(121)
        ax2 = self.fig.add_subplot(122)
        
        for ax in (ax1, ax2):
            ax.set_facecolor(c.get("sidebar", "#1a202c"))
            for spine in ax.spines.values():
                spine.set_color(c.get("border", "#4a5568"))
            ax.tick_params(colors=text_color, labelsize=8)

        # 1. Graphe de Suitedness
        if suitedness:
            labels = list(suitedness.keys())
            values = list(suitedness.values())
            colors = [accent, accent_soft, orange, color_down][:len(labels)]
            ax1.pie(values, labels=labels, autopct='%1.1f%%', colors=colors, 
                    textprops={'color': text_color, 'fontsize': 8})
            ax1.set_title(f"Couleurs ({variant_title})", color=text_color, fontsize=9, fontweight='bold')
        else:
            ax1.text(0.5, 0.5, "Aucune donnée", color=text_color, ha='center')

        # 2. Graphe des Paires
        if pairs:
            labels = list(pairs.keys())
            values = list(pairs.values())
            colors = [accent, accent_soft, orange, color_down, c.get("graph_purple", "#9f7aea")][:len(labels)]
            ax2.bar(labels, values, color=colors, alpha=0.85)
            ax2.set_title(f"Configuration ({variant_title})", color=text_color, fontsize=9, fontweight='bold')
            ax2.set_ylabel("Mains", color=text_color, fontsize=8)
            ax2.tick_params(axis='x', rotation=30)
        else:
            ax2.text(0.5, 0.5, "Aucune donnée", color=text_color, ha='center')
            
        self.fig.tight_layout()
        self.draw()


class StartingHandsTab(QWidget):
    """Onglet d'analyse des starting hands (Hold'em / Omaha)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 12, 12, 12)
        
        # Titre dynamique de l'onglet
        self.title_label = QLabel("Analyse des Mains de Départ")
        c = get_theme_palette()
        self.title_label.setStyleSheet(f"font-size: 12px; font-weight: bold; text-transform: uppercase; color: {c.get('muted_text', '#a0aec0')};")
        self.layout.addWidget(self.title_label)

        # Conteneur principal qui changera dynamiquement selon le jeu
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.container, 1)

        # Composants pré-créés pour Hold'em et Omaha
        self.holdem_grid_widget = QWidget()
        holdem_main_layout = QVBoxLayout(self.holdem_grid_widget)
        holdem_main_layout.setContentsMargins(0, 0, 0, 0)

        # Toggle de coloration Hold'em
        toggle_layout = QHBoxLayout()
        toggle_lbl = QLabel("Colorer la grille par :")
        toggle_lbl.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {c.get('muted_text', '#a0aec0')};")
        toggle_layout.addWidget(toggle_lbl)
        
        self.color_by_combo = QComboBox()
        self.color_by_combo.addItems(["Profit Net (€)", "VPIP (%)"])
        self.color_by_combo.currentIndexChanged.connect(self.on_color_by_changed)
        self.color_by_combo.setMaximumWidth(150)
        toggle_layout.addWidget(self.color_by_combo)
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

        self.omaha_widget = QWidget()
        omaha_layout = QVBoxLayout(self.omaha_widget)
        self.omaha_canvas = OmahaChartsCanvas(self.omaha_widget)
        omaha_layout.addWidget(self.omaha_canvas)

        self.active_mode = None  # 'holdem' ou 'omaha'
        self.holdem_hand_stats = {}
        self.holdem_color_by = "profit"

    def _build_holdem_grid(self) -> None:
        """Construit statiquement la grille 13x13 pour le Texas Hold'em."""
        ranks = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
        for row in range(13):
            for col in range(13):
                c1 = ranks[row]
                c2 = ranks[col]
                
                if row < col:
                    # Suited (en haut à droite)
                    hand = f"{c1}{c2}s"
                elif row > col:
                    # Offsuit (en bas à gauche)
                    hand = f"{c2}{c1}o"
                else:
                    # Paire (diagonale)
                    hand = f"{c1}{c2}"

                cell = HoldemGridCell(hand)
                self.holdem_grid.addWidget(cell, row, col)
                self.holdem_cells[hand] = cell

    def on_color_by_changed(self, index: int) -> None:
        """Change la coloration de la grille Hold'em."""
        self.holdem_color_by = "vpip" if index == 1 else "profit"
        self.redraw_holdem_grid()

    def redraw_holdem_grid(self) -> None:
        """Redessine la grille Hold'em avec la coloration active."""
        for hand, cell in self.holdem_cells.items():
            stat = self.holdem_hand_stats.get(hand)
            if stat:
                cell.update_stats(stat.get("n", 0), stat.get("net", 0.0), stat.get("vpip", 0.0), self.holdem_color_by)
            else:
                cell.update_stats(0, 0.0, 0.0, self.holdem_color_by)

    def update_holdem_data(self, hand_stats: dict[str, dict]) -> None:
        """Affiche la grille de Hold'em et met à jour ses cellules avec les statistiques."""
        self._set_mode("holdem")
        self.holdem_hand_stats = hand_stats
        self.redraw_holdem_grid()

    def update_omaha_data(self, hand_stats: list[dict], variant: str = "omaha4") -> None:
        """Affiche et génère les graphiques d'analyse Omaha à partir de la liste des mains."""
        self._set_mode("omaha")
        
        # Dénomination selon la variante Omaha
        if variant == "omaha5":
            variant_title = "Omaha 5-Card"
            self.title_label.setText("Analyses des textures d'Omaha 5-Card")
            pairs_counts = {"Quads": 0, "Trips": 0, "Double Paired": 0, "Single Paired": 0, "No Pair": 0}
        elif variant == "omaha6":
            variant_title = "Omaha 6-Card"
            self.title_label.setText("Analyses des textures d'Omaha 6-Card")
            pairs_counts = {"Quads": 0, "Trips": 0, "Double Paired": 0, "Single Paired": 0, "No Pair": 0}
        else:
            variant_title = "Omaha 4-Card"
            self.title_label.setText("Analyses des textures d'Omaha 4-Card")
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
                counts = {}
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
            self.title_label.setText("Grille Hold'em (Hold'em starting hand grid)")
        elif mode == "omaha":
            self.container_layout.addWidget(self.omaha_widget)
            # Sera mis à jour par la méthode update_omaha_data
            self.title_label.setText("Analyses des textures d'Omaha")

    def refresh_theme(self, colors=None, theme_colors=None) -> None:
        if self.active_mode == "omaha":
            self.omaha_canvas.update_style()
        elif self.active_mode == "holdem":
            self.redraw_holdem_grid()
