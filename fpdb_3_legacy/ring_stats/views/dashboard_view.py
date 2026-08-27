"""dashboard_view.py

Affiche l'onglet principal 'Tableau de Bord' avec les KPI Cards, la jauge de Gap,
et le graphique de profit cumulé Matplotlib.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.localized_formats import format_currency, format_number
from fpdb_3_legacy.ring_stats.styles import get_theme_palette
from fpdb_3_legacy.ring_stats.views.widgets import GapMeter, KpiCard


class ProfitGraphWidget(pg.PlotWidget):
    """Widget pyqtgraph performant pour le graphique de profit cumulé."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.showGrid(x=True, y=True, alpha=0.3)
        self.update_style()

    def update_style(self) -> None:
        """Adapte les couleurs au thème courant de l'application."""
        c = get_theme_palette()
        bg_color = c.get("sidebar", "#1a202c")
        text_color = c.get("text", "#edf2f7")
        grid_color = c.get("grid", "#4a5568")

        self.setBackground(bg_color)
        self.setTitle(f"<span style='color:{text_color}; font-size:10pt; font-weight:bold;'>Évolution du Profit</span>")
        self.setLabel("left", "Profit ($ / BB)", **{"color": text_color, "font-size": "8pt"})
        self.setLabel("bottom", "Mains Jouées", **{"color": text_color, "font-size": "8pt"})
        axis_pen = pg.mkPen(color=grid_color, width=1)
        self.getAxis("left").setPen(axis_pen)
        self.getAxis("bottom").setPen(axis_pen)
        self.getAxis("left").setTextPen(pg.mkPen(color=text_color))
        self.getAxis("bottom").setTextPen(pg.mkPen(color=text_color))

    def plot_profit_data(self, profits: tuple[np.ndarray, ...] | list[float], hands: list[int]) -> None:
        """Trace les courbes de profit cumulé, dont le net hors splash."""
        self.clear()
        self.update_style()

        if not profits:
            return

        c = get_theme_palette()
        color_up = c.get("graph_up", "#48bb78")
        color_down = c.get("graph_down", "#f56565")
        border_color = c.get("border", "#4a5568")

        if isinstance(profits, tuple) and len(profits) in (4, 5):
            green, blue, red, ev = profits[:4]
            nosplash = profits[4] if len(profits) == 5 else np.array([])
        else:
            green = np.cumsum(profits)
            blue = np.array([])
            red = np.array([])
            ev = np.array([])
            nosplash = np.array([])

        if len(green) == 0:
            return

        x = np.arange(len(green))

        # Ajouter la légende
        legend = self.addLegend(offset=(10, 10))
        legend.setBrush(pg.mkBrush(color=c.get("sidebar", "#1a202c")))
        legend.setPen(pg.mkPen(color=border_color))

        # Ligne zéro
        self.addLine(y=0, pen=pg.mkPen(color=border_color, width=1, style=Qt.PenStyle.DashLine))

        # 1. Net Profit (Vert)
        self.plot(x, green, pen=pg.mkPen(color=color_up, width=2), name="Net Profit")

        # 2. Showdown Profit (Bleu)
        if len(blue) > 0:
            self.plot(x, blue, pen=pg.mkPen(color=c.get("graph_showdown", "#3182ce"), width=1.5, style=Qt.PenStyle.DashLine), name="Showdown")

        # 3. Non-Showdown Profit (Rouge)
        if len(red) > 0:
            self.plot(x, red, pen=pg.mkPen(color=color_down, width=1.5, style=Qt.PenStyle.DashLine), name="Non-Showdown")

        # 4. All-In EV (Orange)
        if len(ev) > 0 and not np.all(ev == 0):
            self.plot(x, ev, pen=pg.mkPen(color=c.get("graph_ev", "#dd6b20"), width=1.5), name="All-In EV")

        if len(nosplash) > 0 and not np.array_equal(nosplash, green):
            self.plot(x, nosplash, pen=pg.mkPen(color=c.get("graph_no_splash", "#ed8936"), width=1.5, style=Qt.PenStyle.DashLine), name="Net profit excluding splash")


class DashboardTab(QWidget):
    """Onglet Dashboard principal."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # Layout principal
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # 1. Grille des KPI Cards (Top)
        kpi_container = QWidget()
        self.kpi_layout = QGridLayout(kpi_container)
        self.kpi_layout.setContentsMargins(0, 0, 0, 0)
        self.kpi_layout.setSpacing(12)

        # KPI Cards individuelles
        self.card_hands = KpiCard("Mains Jouées", "0")
        self.card_net = KpiCard("Profit Net", "0.00 €", value_type="normal")
        self.card_vpip = KpiCard("VPIP", "0.0%")
        self.card_pfr = KpiCard("PFR", "0.0%")
        self.card_3bet = KpiCard("3Bet", "0.0%")
        self.card_agg = KpiCard("Agression (AF)", "0.00")

        # Placement dans la grille (2 lignes, 3 colonnes)
        self.kpi_layout.addWidget(self.card_hands, 0, 0)
        self.kpi_layout.addWidget(self.card_net, 0, 1)
        self.kpi_layout.addWidget(self.card_vpip, 0, 2)
        self.kpi_layout.addWidget(self.card_pfr, 1, 0)
        self.kpi_layout.addWidget(self.card_3bet, 1, 1)
        self.kpi_layout.addWidget(self.card_agg, 1, 2)

        layout.addWidget(kpi_container)

        # 2. Section GapMeter
        gap_box = QVBoxLayout()
        gap_box.setSpacing(4)
        self.gap_label = QLabel(_("Preflop Profile (VPIP vs PFR)"))
        c = get_theme_palette()
        self.gap_label.setStyleSheet(f"font-size: 11px; font-weight: bold; text-transform: uppercase; color: {c.get('muted_text', '#a0aec0')};")
        self.gap_meter = GapMeter(0.0, 0.0)
        gap_box.addWidget(self.gap_label)
        gap_box.addWidget(self.gap_meter)

        layout.addLayout(gap_box)

        # 3. Graphique de Profit
        self.canvas = ProfitGraphWidget(self)
        layout.addWidget(self.canvas, 1)  # Prend tout l'espace disponible verticalement

    def update_data(self, summary_stats: dict, profits: list[float]) -> None:
        """Met à jour les KPI cards, la jauge de gap, et redessine le graphique."""
        # 1. Mise à jour des cartes KPI
        hands = summary_stats.get("hands", 0)
        self.card_hands.set_value(format_number(hands, 0))

        net_profit = summary_stats.get("net", 0.0)
        currency = str(summary_stats.get("currency", "EUR"))
        net_val_str = format_currency(net_profit, currency, show_plus=net_profit > 0)
        value_type = "green" if net_profit > 0 else "red" if net_profit < 0 else "normal"
        self.card_net.set_value(net_val_str, value_type=value_type)

        vpip = summary_stats.get("vpip", 0.0)
        self.card_vpip.set_value(f"{format_number(vpip, 1)}%")

        pfr = summary_stats.get("pfr", 0.0)
        self.card_pfr.set_value(f"{format_number(pfr, 1)}%")

        pf3 = summary_stats.get("pf3", 0.0)
        self.card_3bet.set_value(f"{format_number(pf3, 1)}%")

        agg = summary_stats.get("aggfac", 0.0)
        self.card_agg.set_value(format_number(agg, 2))

        # 2. Mise à jour du GapMeter
        self.gap_meter.set_values(vpip, pfr)

        # 3. Mise à jour du graphique de profit
        self.canvas.plot_profit_data(profits, list(range(len(profits))))

    def refresh_theme(self, colors=None, theme_colors=None) -> None:
        """Force la mise à jour graphique lors d'un changement de thème."""
        c = get_theme_palette()
        muted = c.get('muted_text', '#a0aec0')
        self.gap_label.setStyleSheet(f"font-size: 11px; font-weight: bold; text-transform: uppercase; color: {muted};")
        self.canvas.update_style()
        self.gap_meter.update()
