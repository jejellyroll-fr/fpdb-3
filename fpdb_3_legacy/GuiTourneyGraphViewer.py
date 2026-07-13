#!/usr/bin/env python
from __future__ import annotations

# Copyright 2008-2011 Carl Gherardi
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
# In the "official" distribution you can find the license in agpl-3.0.txt.
import os
import sys
from time import time

from PySide6.QtWidgets import QFrame, QMessageBox, QScrollArea, QSplitter, QVBoxLayout

from fpdb_3_legacy import Database, Filters
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger

# import Charset


log = get_logger("gui_tourney_graph_viewer")

try:
    calluse = "matplotlib" not in sys.modules
    import matplotlib as mpl

    if calluse:
        try:
            mpl.use("qt5agg")
        except ValueError as e:
            log.exception(f"Matplotlib use error: {e}")
    from matplotlib.backends.backend_qt5agg import FigureCanvas
    from matplotlib.figure import Figure
    from numpy import cumsum
except ImportError as inst:
    log.exception(
        "Failed to load libs for graphing, graphing will not function. Please install numpy and matplotlib if you want to use graphs.",
    )
    log.exception(
        "This is of no consequence for other parts of the program, e.g., import and HUD are NOT affected by this problem.",
    )
    log.exception(f"ImportError: {inst.args}")


class GuiTourneyGraphViewer(QSplitter):
    def __init__(self, querylist, config, parent, colors, debug=True) -> None:
        """Constructor for GraphViewer."""
        QSplitter.__init__(self, parent)
        self.sql = querylist
        self.conf = config
        self.debug = debug
        self.parent = parent
        self.colors = colors
        self.db = Database.Database(self.conf, sql=self.sql)

        filters_display = {
            "Heroes": True,
            "Sites": True,
            "Games": False,  # cash game
            "Tourney": True,
            "TourneyCat": True,
            "TourneyLim": True,
            "TourneyBuyin": True,
            "Currencies": True,
            "Limits": False,
            "LimitSep": True,
            "LimitType": True,
            "Type": True,
            "UseType": "tour",
            "Seats": False,
            "SeatSep": True,
            "Dates": True,
            "Groups": False,
            "Button1": True,
            "Button2": True,
        }

        self.filters = Filters.Filters(self.db, display=filters_display)
        self.filters.registerButton1Name(_("Refresh Graph"))
        self.filters.registerButton1Callback(self.generateGraph)
        self.filters.registerButton2Name(_("Export to File"))
        self.filters.registerButton2Callback(self.exportGraph)

        scroll = QScrollArea()
        scroll.setObjectName("filterSidebar")
        scroll.setWidget(self.filters)
        self.addWidget(scroll)

        self.graphFrame = QFrame()
        self.graphFrame.setObjectName("graphSurface")
        self.graphFrame.setStyleSheet(f"background-color: {self.colors['background']}")
        self.graphBox = QVBoxLayout()
        self.graphFrame.setLayout(self.graphBox)
        self.addWidget(self.graphFrame)
        self.setStretchFactor(0, 0)
        self.setStretchFactor(1, 1)

        self.fig = None
        self.canvas = None

        self.db.rollback()
        self.exportFile = None

    def clearGraphData(self) -> None:
        try:
            if self.canvas:
                self.graphBox.removeWidget(self.canvas)
                self.canvas.setParent(None)
        except (AttributeError, RuntimeError) as e:
            # Handle specific exceptions related to widget removal
            log.exception(f"Error removing widget: {e}")

        if self.fig is not None:
            self.fig.clear()
            self.fig = None

        if self.canvas is not None:
            self.canvas.destroy()
            self.canvas = None

        # Declarative ChipEV-by-position curves, recomputed on each generate.
        self.chipev_curves = []

    def generateGraph(self, widget) -> None:
        self.clearGraphData()

        sitenos = []
        playerids = []

        sites = self.filters.getSites()
        heroes = self.filters.getHeroes()
        siteids = self.filters.getSiteIds()

        games = self.filters.getGames()
        names = ""

        log.warning(f"GuiTourneyGraphViewer.generateGraph called. Sites selected: {sites}, Heroes config: {heroes}, siteids: {siteids}, games: {games}")

        for site in sites:
            _hname = heroes.get(site, "")
            if not _hname:
                continue
            # Plot the hero the user selected, resolved variant-aware:
            # get_player_id maps a "PokerStars" selection to the hero's
            # "PokerStars.FR" account, so data imported under a site skin still
            # shows. Fall back to the site's hero-flagged players if unresolved.
            result = self.db.get_player_id(self.conf, site, _hname)
            pids = [int(result)] if result is not None else self.db.get_hero_player_ids(site)
            for pid in pids:
                if pid not in playerids:
                    playerids.append(pid)
                    pname = self.db.get_player_name_by_id(pid) or _hname
                    names = names + "\n" + pname + " on " + site

                    actual_site_id = self.db.get_player_site_id(pid)
                    if actual_site_id is not None:
                        sitenos.append(actual_site_id)
                        log.warning(f"GuiTourneyGraphViewer: Using resolved actual siteId {actual_site_id} for hero '{pname}'")
                    else:
                        sitenos.append(siteids[site])

        log.warning(f"GuiTourneyGraphViewer.generateGraph resolved sitenos: {sitenos}, playerids: {playerids}, names: {names!r}")

        if not sitenos:
            log.warning("GuiTourneyGraphViewer.generateGraph: No sites selected")
            self.db.rollback()
            return

        if not playerids:
            log.warning("GuiTourneyGraphViewer.generateGraph: No player ids found")
            self.db.rollback()
            return

        starttime = time()
        green = self.getData(playerids, sitenos, games)
        log.info(f"Graph generated in: {time() - starttime}")

        if green is None or len(green) == 0:
            from PySide6.QtWidgets import QMessageBox
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle(_("FPDB 3 info"))
            msg.setText("No data found for the selected filters.")
            msg.exec()
            self.db.rollback()
            return

        bg_color = self.colors["background"]
        fg_color = self.colors["foreground"]

        # Update frame style to match current theme
        self.graphFrame.setStyleSheet(f"background-color: {bg_color}")

        # Helper to determine if theme is dark
        def is_dark_color(hex_color: str) -> bool:
            hex_color = hex_color.lstrip('#')
            if len(hex_color) == 3:
                hex_color = ''.join(c*2 for c in hex_color)
            try:
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
                return (0.299 * r + 0.587 * g + 0.114 * b) < 128
            except Exception:
                return True

        is_dark = is_dark_color(bg_color)

        self.fig = Figure(figsize=(5.0, 4.0), dpi=100)
        self.fig.patch.set_facecolor(bg_color)
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setParent(self)

        self.ax = self.fig.add_subplot(111)

        # Configure axes backgrounds and grid
        self.ax.set_facecolor(bg_color)

        grid_color = "#334155" if is_dark else "#cbd5e1"
        self.ax.grid(True, color=grid_color, linestyle=":", linewidth=0.6, alpha=0.7)

        # Position spines at standard outer edges, hide top and right
        border_color = "#2d3741" if is_dark else "#cbd5e1"
        self.ax.spines["left"].set_color(border_color)
        self.ax.spines["bottom"].set_color(border_color)
        self.ax.spines["top"].set_visible(False)
        self.ax.spines["right"].set_visible(False)
        self.ax.spines["left"].set_position(("outward", 0))
        self.ax.spines["bottom"].set_position(("outward", 0))
        self.ax.xaxis.set_ticks_position("bottom")
        self.ax.yaxis.set_ticks_position("left")

        # Tick colors and sizes
        self.ax.tick_params(axis="x", colors=fg_color, labelsize=9)
        self.ax.tick_params(axis="y", colors=fg_color, labelsize=9)

        # Labels
        self.ax.set_xlabel("Tournaments", color=fg_color, labelpad=8, fontsize=10, fontweight="semibold")
        self.ax.set_ylabel("$", color=fg_color, labelpad=8, fontsize=10, fontweight="semibold")

        # Title
        title_color = "#ffffff" if is_dark else "#0f172a"
        self.ax.set_title(
            "Tournament Results" + names,
            color=title_color,
            pad=15,
            fontsize=12,
            fontweight="bold",
        )

        # Zero baseline
        zero_color = "#475569" if is_dark else "#94a3b8"
        self.ax.axhline(0, color=zero_color, linestyle="--", linewidth=1.0, alpha=0.7)

        # Modern green line color based on theme
        # Modern green line color based on theme
        if is_dark:
            line_hands_color = "#22c55e"
            if "line_hands" in self.colors:
                val = self.colors["line_hands"]
                if val not in ("c", "g"):
                    line_hands_color = val
        else:
            line_hands_color = "#15803d"
            if "line_hands" in self.colors:
                val = self.colors["line_hands"]
                if val not in ("c", "g"):
                    line_hands_color = val

        self.ax.plot(
            green,
            color=line_hands_color,
            linewidth=2.5,
            label="Tournaments: %d\nProfit: $%.2f" % (len(green), green[-1]),
        )

        # ChipEV-by-position curves (declarative; see stat_registry.py).
        # Plotted on a secondary y-axis because they are measured in tournament
        # chips, not the profit currency of the main line.
        chipev_curves = getattr(self, "chipev_curves", [])
        if chipev_curves:
            # Avoid green: the main profit line is green, so curves use a
            # distinct palette (orange/blue/purple/red/teal/yellow).
            curve_palette = ["#ff9f43", "#54a0ff", "#a55eea", "#fc5c65", "#00d2d3", "#fed330"]
            ax_ev = self.ax.twinx()
            ax_ev.set_ylabel("ChipEV (chips)", color=fg_color, labelpad=8, fontsize=9)
            ax_ev.tick_params(axis="y", colors=fg_color, labelsize=8)
            ax_ev.spines["top"].set_visible(False)
            for idx, (label, values) in enumerate(chipev_curves):
                ax_ev.plot(
                    values,
                    color=curve_palette[idx % len(curve_palette)],
                    linewidth=1.5,
                    linestyle="-",
                    alpha=0.9,
                    label="%s: %.0f" % (label, values[-1]),
                )
            # Merge the secondary-axis legend entries into the main legend.
            ev_handles, ev_labels = ax_ev.get_legend_handles_labels()
            main_handles, main_labels = self.ax.get_legend_handles_labels()
            self.ax.legend_handles_extra = (main_handles + ev_handles, main_labels + ev_labels)

        legend_face = "#20272d" if is_dark else "#f8fafc"
        legend_edge = "#2d3741" if is_dark else "#e2e8f0"

        legend_args = dict(
            loc="upper left",
            fancybox=True,
            frameon=True,
            facecolor=legend_face,
            edgecolor=legend_edge,
            labelcolor=fg_color,
            framealpha=0.9,
        )
        extra = getattr(self.ax, "legend_handles_extra", None)
        if extra:
            legend = self.ax.legend(extra[0], extra[1], **legend_args)
        else:
            legend = self.ax.legend(**legend_args)
        for text in legend.get_texts():
            text.set_fontsize(8.5)
            text.set_fontweight("semibold")

        self.graphBox.addWidget(self.canvas)
        self.canvas.draw()

    def getData(self, names, sites, Tourneys):
        tmp = self.sql.query["tourneyGraphType"]
        start_date, end_date = self.filters.getDates()
        tourneys = self.filters.getTourneyTypes()
        tourneysCat = self.filters.getTourneyCat()
        tourneysLim = self.filters.getTourneyLim()
        tourneysBuyin = self.filters.getTourneyBuyin()

        log.warning(f"GuiTourneyGraphViewer.getData: names: {names}, sites: {sites}, Tourneys: {Tourneys}")
        log.warning(f"GuiTourneyGraphViewer.getData filters: start_date: {start_date}, end_date: {end_date}, tourneys: {tourneys}, tourneysCat: {tourneysCat}, tourneysLim: {tourneysLim}, tourneysBuyin: {tourneysBuyin}")

        currencies = {"EUR": "EUR", "USD": "USD", "NA": "NA", "": "T$"}
        currencytest = str(tuple(currencies.values()))
        currencytest = currencytest.replace(",)", ")")
        currencytest = currencytest.replace("u'", "'")
        currencytest = f"AND tt.currency in {currencytest}"

        nametest = str(tuple(names))
        sitetest = str(tuple(sites))
        tourneystest = str(tuple(tourneys))

        def make_in_clause_sql(values, field_type="str"):
            if not values:
                return None

            if len(values) == 1:
                val = values[0]
                return f"('{val}')" if field_type == "str" else f"({val})"

            if field_type == "str":
                return str(tuple(values))
            return str(tuple(int(v) for v in values))

        currencytest = f"AND tt.currency in {make_in_clause_sql(currencies.values(), 'str')}"
        tourneysCattest = make_in_clause_sql(tourneysCat, "str")
        tourneysLimtest = make_in_clause_sql(tourneysLim, "str")

        buyins = [int(b.split(",")[0]) for b in tourneysBuyin if b != "None"]
        tourneysBuyintest = make_in_clause_sql(buyins, "int")

        tourneystest = tourneystest.replace("None", '"None"')

        def apply_filters(query):
            """Substitute the shared tourney filter placeholders into a query."""
            query = query.replace("<player_test>", nametest)
            query = query.replace("<site_test>", sitetest)
            query = query.replace("<startdate_test>", start_date)
            query = query.replace("<enddate_test>", end_date)
            query = query.replace("<currency_test>", currencytest)
            query = query.replace("AND tt.category in <tourney_cat>", f"AND tt.category in {tourneysCattest}" if tourneysCattest else "")
            query = query.replace("AND tt.limitType in <tourney_lim>", f"AND tt.limitType in {tourneysLimtest}" if tourneysLimtest else "")
            query = query.replace("AND tt.buyin in <tourney_buyin>", f"AND tt.buyin in {tourneysBuyintest}" if tourneysBuyintest else "")
            query = query.replace("<tourney_test>", tourneystest)
            return query.replace(",)", ")")

        tmp = apply_filters(tmp)

        log.warning(f"GuiTourneyGraphViewer.getData: Executing SQL query:\n{tmp}")

        self.db.cursor.execute(tmp)
        winnings = self.db.cursor.fetchall()
        self.db.rollback()

        log.warning(f"GuiTourneyGraphViewer.getData: SQL query returned {len(winnings)} records.")

        # Declarative ChipEV-by-position curves (best-effort: never break the
        # main profit line if anything goes wrong here).
        self.chipev_curves = self.getChipEVCurves(apply_filters)

        if len(winnings) == 0:
            return None

        green = [float(x[1]) for x in winnings]
        greenline = cumsum(green)
        return (greenline) // (100)

    def getChipEVCurves(self, apply_filters):
        """Compute the cumulative ChipEV-by-position curves for the hero.

        Returns a list of ``(label, values)`` tuples, one per descriptor whose
        ``series`` is cumulative, or ``[]`` if there are none or on any error.
        The curves are derived entirely from declarative descriptors, so adding
        a new position curve is a descriptor file, not code here.
        """
        try:
            from fpdb_3_legacy.stat_adapters import GraphAdapter
            from fpdb_3_legacy.stat_registry import get_registry

            descriptors = get_registry().series_for_scope("tour")
            if not descriptors:
                return []

            adapter = GraphAdapter(alias="hp")
            query = self.sql.query["tourneyChipEVByPosition"]
            query = query.replace("<chipev_columns>", adapter.select_clause(descriptors))
            query = apply_filters(query)

            self.db.cursor.execute(query)
            rows = self.db.cursor.fetchall()
            colnames = [d[0] for d in self.db.cursor.description]
            self.db.rollback()

            row_dicts = [dict(zip(colnames, r, strict=False)) for r in rows]
            curves = []
            for descriptor in descriptors:
                values = adapter.series_values(descriptor, row_dicts)
                if values and any(v != 0 for v in values):
                    curves.append((descriptor.label, values))
            log.info(f"GuiTourneyGraphViewer: computed {len(curves)} ChipEV-by-position curve(s)")
            return curves
        except Exception as exc:
            log.warning(f"GuiTourneyGraphViewer.getChipEVCurves failed (skipping curves): {exc}")
            self.db.rollback()
            return []

    def exportGraph(self) -> None:
        if self.fig is None:
            return

        path = os.getcwd()
        path = path + "/graph.png"
        self.fig.savefig(path)
        msg = QMessageBox()
        msg.setWindowTitle(_("FPDB 3 info"))
        mess = "Your graph is saved in " + path
        msg.setText(mess)
        msg.exec()


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    # Launch the tournament graph viewer GUI like the original
    import fpdb_3_legacy.Configuration as Configuration

    config = Configuration.Config()

    settings = {}

    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())

    from PySide6.QtWidgets import QApplication, QMainWindow

    app = QApplication([])
    import fpdb_3_legacy.SQL as SQL

    sql = SQL.Sql(db_server=settings["db-server"])

    colors = {
        "background": "#19232D",
        "foreground": "#9DA9B5",
        "grid": "#4D4D4D",
        "line_up": "g",
        "line_down": "r",
    }

    i = GuiTourneyGraphViewer(sql, config, None, colors)
    main_window = QMainWindow()
    main_window.setCentralWidget(i)
    main_window.show()
    main_window.resize(1400, 800)
    app.exec()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
