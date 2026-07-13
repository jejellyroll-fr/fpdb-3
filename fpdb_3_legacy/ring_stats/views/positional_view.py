"""positional_view.py

Affiche l'onglet 'Heatmap de Position' avec une table de poker 2D interactive et
des graphiques en barres par position pour comparer les statistiques (VPIP/PFR).
"""

from __future__ import annotations
import math
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont
from PySide6.QtWidgets import QWidget, QVBoxLayout, QSplitter
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from fpdb_3_legacy.ring_stats.styles import get_theme_palette


class PokerTableWidget(QWidget):
    """Dessine une table de poker 2D avec des sièges interactifs."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(400, 250)
        self.position_data: dict[str, dict] = {}
        self.table_size = 6

        # Angles en radians pour chaque configuration (Btn à droite 0.5 rad pour l'esthétique)
        self.angles_by_layout = {
            2: {
                "SB": math.pi / 2,     # Bas
                "BB": 3 * math.pi / 2, # Haut
            },
            6: {
                "SB": 2.5,             # Gauche bas
                "BB": 3.3,             # Gauche haut
                "UTG": 4.1,            # Top gauche
                "MP": 4.9,             # Top milieu/droite
                "CO": 5.7,             # Droite haut
                "Btn": 0.5,            # Droite bas
            },
            9: {
                "SB": 2.2,
                "BB": 2.7,
                "UTG": 3.2,
                "UTG+1": 3.7,
                "MP": 4.2,
                "MP+1": 4.7,
                "HJ": 5.2,
                "CO": 5.7,
                "Btn": 0.5,
            }
        }

    def set_mapped_position_data(self, data: dict[str, dict], table_size: int) -> None:
        """Met à jour les données statistiques par position et redessine la table."""
        self.position_data = data
        self.table_size = table_size
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        c = get_theme_palette()
        text_color = QColor(c.get("text", "#edf2f7"))
        muted_color = QColor(c.get("muted_text", "#a0aec0"))
        border_color = QColor(c.get("border", "#4a5568"))
        bg_color = QColor(c.get("window", "#2d3748"))
        felt_color = QColor(c.get("sidebar_panel", "#1e293b"))
        accent_color = QColor(c.get("accent", "#319795"))
        color_up = QColor(c.get("graph_up", "#48bb78"))
        color_down = QColor(c.get("graph_down", "#f56565"))

        # Dimensions et centre
        w = self.width()
        h = self.height()
        cx, cy = w / 2.0, h / 2.0

        # 1. Dessiner le tapis (feutre de la table) - Ellipse centrale
        table_w, table_h = w * 0.7, h * 0.65
        painter.setPen(QPen(border_color, 4))
        painter.setBrush(QBrush(felt_color))
        rect_table = QRectF(cx - table_w / 2.0, cy - table_h / 2.0, table_w, table_h)
        painter.drawEllipse(rect_table)

        # Ligne décorative interne sur la table
        painter.setPen(QPen(border_color.lighter(120), 1, Qt.PenStyle.DashLine))
        rect_inner = QRectF(cx - table_w * 0.9 / 2.0, cy - table_h * 0.9 / 2.0, table_w * 0.9, table_h * 0.9)
        painter.drawEllipse(rect_inner)

        # Titre au milieu de la table (avec le format détecté)
        painter.setPen(muted_color)
        font = QFont(painter.font())
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        size_lbl = f"{self.table_size}-MAX HEATMAP" if self.table_size > 2 else "HEADS-UP HEATMAP"
        painter.drawText(QRectF(cx - 120, cy - 15, 240, 30), Qt.AlignmentFlag.AlignCenter, size_lbl)

        # 2. Dessiner les sièges autour de la table
        radius_x = table_w / 2.0 + 35
        radius_y = table_h / 2.0 + 25

        # Choisir les sièges à afficher selon la taille de table
        if self.table_size == 2:
            seats_to_show = ["SB", "BB"]
            layout_angles = self.angles_by_layout[2]
        elif self.table_size == 6:
            seats_to_show = ["SB", "BB", "UTG", "MP", "CO", "Btn"]
            layout_angles = self.angles_by_layout[6]
        else:
            seats_to_show = ["SB", "BB", "UTG", "UTG+1", "MP", "MP+1", "HJ", "CO", "Btn"]
            layout_angles = self.angles_by_layout[9]

        for seat in seats_to_show:
            angle = layout_angles.get(seat, 0.0)
            sx = cx + radius_x * math.cos(angle)
            sy = cy + radius_y * math.sin(angle)

            # Récupérer les stats de ce siège
            stats = self.position_data.get(seat)

            # Dessiner la boîte du siège
            seat_w, seat_h = 75, 45
            rect_seat = QRectF(sx - seat_w / 2.0, sy - seat_h / 2.0, seat_w, seat_h)

            if stats:
                painter.setPen(QPen(accent_color, 1.5))
                painter.setBrush(QBrush(bg_color.lighter(110)))
            else:
                painter.setPen(QPen(border_color, 1))
                painter.setBrush(QBrush(bg_color.darker(110)))

            painter.drawRoundedRect(rect_seat, 5, 5)

            # Dessiner le texte du siège
            painter.setPen(text_color)
            font.setPointSize(8)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QRectF(sx - seat_w / 2.0, sy - seat_h / 2.0 + 2, seat_w, 14), Qt.AlignmentFlag.AlignCenter, seat)

            if stats:
                # VPIP / PFR
                vpip = stats.get("vpip", 0.0)
                pfr = stats.get("pfr", 0.0)
                font.setPointSize(7)
                font.setBold(False)
                painter.setFont(font)
                painter.setPen(muted_color)
                painter.drawText(QRectF(sx - seat_w / 2.0, sy - seat_h / 2.0 + 16, seat_w, 12), Qt.AlignmentFlag.AlignCenter, f"{vpip:.0f}/{pfr:.0f}")

                # Profit
                profit = stats.get("net", 0.0)
                profit_text = f"{profit:+.2f}€" if profit != 0 else "0.00€"
                painter.setPen(color_up if profit > 0 else color_down if profit < 0 else text_color)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(QRectF(sx - seat_w / 2.0, sy - seat_h / 2.0 + 28, seat_w, 12), Qt.AlignmentFlag.AlignCenter, profit_text)
            else:
                # Siège vide
                font.setPointSize(7)
                font.setBold(False)
                painter.setFont(font)
                painter.setPen(muted_color.darker(115))
                painter.drawText(QRectF(sx - seat_w / 2.0, sy - seat_h / 2.0 + 20, seat_w, 12), Qt.AlignmentFlag.AlignCenter, "Pas de main")


class PositionalChartCanvas(FigureCanvas):
    """Graphique en barres matplotlib comparant VPIP et PFR par position."""

    def __init__(self, parent=None) -> None:
        self.fig = Figure(figsize=(5, 3), dpi=100)
        self.axes = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        self.update_style()

    def update_style(self) -> None:
        c = get_theme_palette()
        bg_color = c.get("sidebar", "#1a202c")
        text_color = c.get("text", "#edf2f7")
        grid_color = c.get("grid", "#4a5568")

        self.fig.patch.set_facecolor(bg_color)
        self.axes.set_facecolor(bg_color)

        self.axes.spines['bottom'].set_color(grid_color)
        self.axes.spines['top'].set_color(grid_color)
        self.axes.spines['right'].set_color(grid_color)
        self.axes.spines['left'].set_color(grid_color)

        self.axes.tick_params(colors=text_color, labelsize=8)
        self.axes.yaxis.grid(True, color=grid_color, linestyle='--', alpha=0.5)
        self.axes.set_title("VPIP & PFR par Position", color=text_color, fontsize=10, fontweight='bold')
        self.draw()

    def plot_data(self, positions: list[str], vpips: list[float], pfrs: list[float]) -> None:
        self.axes.clear()
        self.update_style()

        if not positions:
            self.draw()
            return

        c = get_theme_palette()
        vpip_color = c.get("accent", "#319795")
        pfr_color = c.get("graph_ev", "#f59e3d")
        text_color = c.get("text", "#edf2f7")

        x = range(len(positions))
        width = 0.35

        # Barres côte à côte
        self.axes.bar([i - width/2 for i in x], vpips, width, label='VPIP', color=vpip_color, alpha=0.85)
        self.axes.bar([i + width/2 for i in x], pfrs, width, label='PFR', color=pfr_color, alpha=0.85)

        self.axes.set_xticks(x)
        self.axes.set_xticklabels(positions, color=text_color)
        self.axes.set_ylabel("%", color=text_color)
        self.axes.legend(facecolor=c.get("sidebar", "#1a202c"), edgecolor=c.get("border", "#4a5568"), labelcolor=text_color, fontsize=8)
        self.draw()


class PositionalTab(QWidget):
    """Onglet d'analyse positionnelle."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        # Splitter vertical pour diviser la table de poker et le graphe
        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter)

        # 1. Widget Table de Poker
        self.poker_table = PokerTableWidget(self)
        splitter.addWidget(self.poker_table)

        # 2. Canvas Graphique de Position
        self.canvas = PositionalChartCanvas(self)
        splitter.addWidget(self.canvas)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

    def detect_table_size(self, position_stats: dict[str, dict]) -> int:
        """Détecte la taille de la table à partir des clés de position présentes dans les données."""
        keys = list(position_stats.keys())

        # Si on voit des clés de full ring
        if any(k in keys for k in ("6", "7", "8", "9", "UTG+1", "MP+1", "HJ")):
            return 9

        # Si on voit des clés de 6-max
        if any(k in keys for k in ("3", "4", "5", "UTG", "MP", "CO")):
            return 6

        # S'il n'y a que SB/BB/Btn et 2 sièges max
        if len(keys) <= 2:
            return 2

        return 6

    def map_positions_to_layout(self, position_stats: dict[str, dict], table_size: int) -> dict[str, dict]:
        """Mappe les clés de position de la base de données vers les positions physiques de la table."""
        mapped = {}

        if table_size == 2:
            # Heads-Up
            for k, val in position_stats.items():
                if k in ("SB", "Btn", "0", "S"):
                    mapped["SB"] = val
                elif k in ("BB", "1", "B", "9", "8"):
                    mapped["BB"] = val
        elif table_size == 6:
            # 6-Max
            for k, val in position_stats.items():
                if k in ("SB", "S"):
                    mapped["SB"] = val
                elif k in ("BB", "B", "9", "8", "4"):
                    mapped["BB"] = val
                elif k == "3":
                    mapped["UTG"] = val
                elif k in ("2", "MP"):
                    mapped["MP"] = val
                elif k in ("1", "CO"):
                    mapped["CO"] = val
                elif k in ("0", "Btn"):
                    mapped["Btn"] = val
        else:
            # 9-Max
            for k, val in position_stats.items():
                if k in ("SB", "S"):
                    mapped["SB"] = val
                elif k in ("BB", "B", "9", "8"):
                    mapped["BB"] = val
                elif k == "7":
                    mapped["UTG"] = val
                elif k == "6":
                    mapped["UTG+1"] = val
                elif k == "5":
                    mapped["MP"] = val
                elif k == "4":
                    mapped["MP+1"] = val
                elif k in ("3", "HJ"):
                    mapped["HJ"] = val
                elif k in ("2", "CO"):
                    mapped["CO"] = val
                elif k in ("0", "Btn"):
                    mapped["Btn"] = val

        return mapped

    def update_position_data(self, position_stats: dict[str, dict]) -> None:
        """Met à jour les composants avec de nouvelles statistiques de position."""
        # 1. Détecter la taille et mapper les positions
        table_size = self.detect_table_size(position_stats)
        mapped_stats = self.map_positions_to_layout(position_stats, table_size)

        # 2. Mettre à jour le widget de table
        self.poker_table.set_mapped_position_data(mapped_stats, table_size)

        # 3. Mettre à jour le graphique barres Matplotlib (ordonné)
        if table_size == 2:
            positions = ["SB", "BB"]
        elif table_size == 6:
            positions = ["SB", "BB", "UTG", "MP", "CO", "Btn"]
        else:
            positions = ["SB", "BB", "UTG", "UTG+1", "MP", "MP+1", "HJ", "CO", "Btn"]

        vpips = []
        pfrs = []
        active_positions = []
        for pos in positions:
            data = mapped_stats.get(pos)
            if data:
                active_positions.append(pos)
                vpips.append(data.get("vpip", 0.0))
                pfrs.append(data.get("pfr", 0.0))

        self.canvas.plot_data(active_positions, vpips, pfrs)

    def refresh_theme(self, colors=None, theme_colors=None) -> None:
        self.poker_table.update()
        self.canvas.update_style()
