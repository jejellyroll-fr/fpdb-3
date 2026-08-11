"""dashboard_view.py

Affiche l'onglet principal 'Tableau de Bord' avec les KPI Cards, la jauge de Gap,
and the cumulative-profit Matplotlib chart.
"""

from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.localized_formats import format_currency, format_number
from fpdb_3_legacy.ring_stats.styles import get_theme_palette
from fpdb_3_legacy.ring_stats.views.widgets import GapMeter, KpiCard


class ProfitGraphCanvas(FigureCanvas):
    """Embedded Matplotlib canvas for plotting the cumulative profit curve."""

    def __init__(self, parent=None) -> None:
        self.fig = Figure(figsize=(5, 3), dpi=100)
        self.axes = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        self.update_style()

    def update_style(self) -> None:
        """Adapt Matplotlib chart colors to the application's current theme."""
        c = get_theme_palette()

        # Retrieve theme colors
        bg_color = c.get("sidebar", "#1a202c")
        text_color = c.get("text", "#edf2f7")
        grid_color = c.get("grid", "#4a5568")

        # Application au graphique
        self.fig.patch.set_facecolor(bg_color)
        self.axes.set_facecolor(bg_color)

        self.axes.spines['bottom'].set_color(grid_color)
        self.axes.spines['top'].set_color(grid_color)
        self.axes.spines['right'].set_color(grid_color)
        self.axes.spines['left'].set_color(grid_color)

        self.axes.tick_params(colors=text_color, labelsize=8)
        self.axes.yaxis.set_major_formatter(FuncFormatter(lambda value, _position: format_number(value)))
        self.axes.yaxis.grid(True, color=grid_color, linestyle='--', alpha=0.5)
        self.axes.xaxis.grid(True, color=grid_color, linestyle='--', alpha=0.3)
        self.axes.set_title("Évolution du Profit", color=text_color, fontsize=10, fontweight='bold')
        self.draw()

    def plot_profit_data(self, profits: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | list[float], hands: list[int]) -> None:
        """Plot cumulative profit curves (Net, Showdown, Non-Showdown, EV)."""
        self.axes.clear()
        self.update_style()

        if not profits:
            self.draw()
            return

        c = get_theme_palette()
        color_up = c.get("graph_up", "#48bb78")
        color_down = c.get("graph_down", "#f56565")
        text_color = c.get("text", "#edf2f7")
        border_color = c.get("border", "#4a5568")

        if isinstance(profits, tuple) and len(profits) == 4:
            green, blue, red, ev = profits
        else:
            # Fallback si ce n'est pas un tuple de 4 elements
            green = np.cumsum(profits)
            blue = np.array([])
            red = np.array([])
            ev = np.array([])

        if len(green) == 0:
            self.draw()
            return

        x = np.arange(len(green))

        # 1. Tracer Net Profit (Vert)
        self.axes.plot(x, green, color=color_up, linewidth=2, label="Net Profit")

        # 2. Tracer Showdown Profit (Bleu)
        if len(blue) > 0:
            self.axes.plot(x, blue, color=c.get("graph_showdown", "#3182ce"), linewidth=1.2, linestyle="--", label="Showdown", alpha=0.8)

        # 3. Tracer Non-Showdown Profit (Rouge)
        if len(red) > 0:
            self.axes.plot(x, red, color=color_down, linewidth=1.2, linestyle="--", label="Non-Showdown", alpha=0.8)

        # 4. Tracer All-In EV (Orange)
        if len(ev) > 0 and not np.all(ev == 0):
            self.axes.plot(x, ev, color=c.get("graph_ev", "#dd6b20"), linewidth=1.5, label="All-In EV", alpha=0.9)

        # Fill the area below Net Profit
        self.axes.fill_between(x, green, 0, where=(green >= 0), color=color_up, alpha=0.1, interpolate=True)
        self.axes.fill_between(x, green, 0, where=(green < 0), color=color_down, alpha=0.1, interpolate=True)

        # Reference line at y=0
        self.axes.axhline(0, color=border_color, linestyle='-', linewidth=0.8, alpha=0.7)

        self.axes.set_ylabel("Profit ($ / BB)", color=text_color, fontsize=8)
        self.axes.set_xlabel("Mains Jouées", color=text_color, fontsize=8)

        # Display the legend
        self.axes.legend(loc="upper left", facecolor=c.get("sidebar", "#1a202c"), edgecolor=border_color, labelcolor=text_color, fontsize=8, framealpha=0.6)
        self.draw()


class DashboardTab(QWidget):
    """Onglet Dashboard principal."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # Layout principal
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # 1. KPI card grid (top)
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

        # Grid placement (2 rows, 3 columns)
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
        self.canvas = ProfitGraphCanvas(self)
        layout.addWidget(self.canvas, 1)  # Prend tout l'espace disponible verticalement

    def update_data(self, summary_stats: dict, profits: list[float]) -> None:
        """Update KPI cards and the gap gauge, then redraw the chart."""
        # 1. Update KPI cards
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

        # 2. Update the GapMeter
        self.gap_meter.set_values(vpip, pfr)

        # 3. Update the profit chart
        self.canvas.plot_profit_data(profits, list(range(len(profits))))

    def refresh_theme(self, colors=None, theme_colors=None) -> None:
        """Force a chart update when the theme changes."""
        c = get_theme_palette()
        muted = c.get('muted_text', '#a0aec0')
        self.gap_label.setStyleSheet(f"font-size: 11px; font-weight: bold; text-transform: uppercase; color: {muted};")
        self.canvas.update_style()
        self.gap_meter.update()
