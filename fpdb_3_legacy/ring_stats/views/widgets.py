"""widgets.py

Widgets graphiques réutilisables pour les vues statistiques de FPDB :
- KpiCard : Carte KPI avec titre, valeur et jauge de progression
- GapMeter : Jauge visuelle comparant le VPIP et le PFR
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from fpdb_3_legacy.ring_stats.styles import get_theme_palette


class KpiCard(QFrame):
    """Carte statistique au style moderne pour afficher des métriques clés."""

    def __init__(self, title: str, value: str, trend: str = "", value_type: str = "normal", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("kpiCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(4)

        # Titre de la stat
        self.title_label = QLabel(title)
        self.title_label.setObjectName("kpiTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # Valeur principale
        self.value_label = QLabel(value)
        if value_type == "green":
            self.value_label.setObjectName("kpiValueGreen")
        elif value_type == "red":
            self.value_label.setObjectName("kpiValueRed")
        else:
            self.value_label.setObjectName("kpiValue")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

        # Tendance optionnelle (ex: +3% ou flèche)
        if trend:
            self.trend_label = QLabel(trend)
            c = get_theme_palette()
            self.trend_label.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {c.get('muted_text', '#a0aec0')};")
            layout.addWidget(self.trend_label)

    def set_value(self, value: str, value_type: str = "normal") -> None:
        """Met à jour la valeur affichée et adapte son style CSS."""
        self.value_label.setText(value)
        if value_type == "green":
            self.value_label.setObjectName("kpiValueGreen")
        elif value_type == "red":
            self.value_label.setObjectName("kpiValueRed")
        else:
            self.value_label.setObjectName("kpiValue")
        # Forcer le rafraîchissement de la feuille de style
        self.value_label.style().unpolish(self.value_label)
        self.value_label.style().polish(self.value_label)


class GapMeter(QWidget):
    """Jauge visuelle représentant la différence (le 'gap') entre VPIP et PFR."""

    def __init__(self, vpip: float = 0.0, pfr: float = 0.0, parent=None) -> None:
        super().__init__(parent)
        self.vpip = vpip
        self.pfr = pfr
        self.setMinimumHeight(24)
        self.setMaximumHeight(30)

    def set_values(self, vpip: float, pfr: float) -> None:
        """Met à jour les valeurs de VPIP et PFR et redessine le widget."""
        self.vpip = max(0.0, min(100.0, vpip))
        self.pfr = max(0.0, min(100.0, pfr))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Dimensions
        w = self.width()
        h = self.height()
        r = 6.0  # Rayon des coins arrondis

        c = get_theme_palette()
        border_color = QColor(c.get("border", "#4a5568"))
        bg_color = QColor(c.get("base", "#1a202c"))
        pfr_color = QColor(c.get("accent", "#319795"))  # Couleur de l'accent (PFR)
        gap_color = QColor(c.get("graph_ev", "#f59e3d"))  # Couleur d'attente/passive (VPIP - PFR)

        # 1. Dessiner le fond (piste vide 100%)
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(QBrush(bg_color))
        rect_bg = QRectF(0, 4, w - 1, h - 8)
        painter.drawRoundedRect(rect_bg, r, r)

        # S'assurer que le VPIP n'est pas inférieur au PFR
        actual_vpip = max(self.vpip, self.pfr)

        # 2. Dessiner le PFR (première partie de la barre)
        if self.pfr > 0:
            pfr_width = (self.pfr / 100.0) * (w - 2)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(pfr_color))
            # Dessiner le rectangle PFR (arrondi à gauche)
            rect_pfr = QRectF(1, 5, pfr_width, h - 10)
            painter.drawRoundedRect(rect_pfr, r, r)

        # 3. Dessiner le Gap (VPIP - PFR, partie passive)
        gap_val = actual_vpip - self.pfr
        if gap_val > 0:
            pfr_width = (self.pfr / 100.0) * (w - 2)
            gap_width = (gap_val / 100.0) * (w - 2)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(gap_color))
            # Dessiner le rectangle de gap
            rect_gap = QRectF(1 + pfr_width, 5, gap_width, h - 10)
            painter.drawRoundedRect(rect_gap, r, r)

        # 4. Afficher du texte d'aide si assez grand
        if w > 150:
            painter.setPen(QColor(c.get("text", "#edf2f7")))
            font = painter.font()
            font.setPointSize(9)
            font.setBold(True)
            painter.setFont(font)

            pfr_text = f"PFR: {self.pfr:.1f}%"
            gap_text = f"Gap: {gap_val:.1f}%"

            # Positionnement du texte
            painter.drawText(10, h - 9, pfr_text)
            painter.drawText(w - 70, h - 9, gap_text)
