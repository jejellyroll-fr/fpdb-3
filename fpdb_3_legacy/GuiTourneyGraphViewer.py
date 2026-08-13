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
import contextlib
import os
import sys
from time import time
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QMessageBox, QScrollArea, QSplitter, QVBoxLayout

from fpdb_3_legacy import Database, Filters, gui_empty_state
from fpdb_3_legacy.Filters import parse_tourney_buyin_key
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.localized_formats import currency_symbol, format_currency, format_number
from fpdb_3_legacy.loggingFpdb import get_logger

# import Charset


log = get_logger("gui_tourney_graph_viewer")

# A tournament tab still has something to show when only summaries were
# imported, so "empty database" means no hands *and* no tournaments.
_TOURNEY_TABLES = ("Hands", "Tourneys")



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

        self.plot_widget: Any = None

        self.db.rollback()
        self.exportFile = None

    def close_owned_database(self) -> None:
        """Release the connection created for this tab."""
        with contextlib.suppress(Exception):
            self.db.disconnect()

    def clearGraphData(self) -> None:
        with contextlib.suppress(Exception):
            if self.plot_widget:
                self.graphBox.removeWidget(self.plot_widget)
                self.plot_widget.setParent(None)
                self.plot_widget = None

        # Declarative ChipEV-by-position curves, recomputed on each generate.
        self.chipev_curves: list[Any] = []

    def generateGraph(self, widget) -> None:
        self.clearGraphData()

        sitenos = []
        playerids = []

        sites = self.filters.getSites()
        heroes = self.filters.getHeroes()
        siteids = self.filters.getSiteIds()

        games = self.filters.getGames()
        currencies = self.filters.getCurrencies()
        names = ""

        log.debug(
            f"GuiTourneyGraphViewer.generateGraph called. Sites selected: {sites}, Heroes config: {heroes}, siteids: {siteids}, games: {games}"
        )

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
                        log.debug(
                            f"GuiTourneyGraphViewer: Using resolved actual siteId {actual_site_id} for hero '{pname}'"
                        )
                    else:
                        sitenos.append(siteids[site])

        log.debug(
            f"GuiTourneyGraphViewer.generateGraph resolved sitenos: {sitenos}, playerids: {playerids}, names: {names!r}"
        )

        missing = gui_empty_state.missing_filter_reason(sites=sites, playerids=playerids)
        if missing is not None:
            gui_empty_state.show_no_data(
                self,
                missing,
                context="Tournament graph",
                db=self.db,
                tables=_TOURNEY_TABLES,
            )
            self.db.rollback()
            return

        starttime = time()
        green = self.getData(playerids, sitenos, games)
        log.info(f"Graph generated in: {time() - starttime}")

        if green is None or len(green) == 0:
            gui_empty_state.show_no_data(self, context="Tournament graph", db=self.db, tables=_TOURNEY_TABLES)
            self.db.rollback()
            return

        bg_color = self.colors["background"]
        fg_color = self.colors["foreground"]

        # Update frame style to match current theme
        self.graphFrame.setStyleSheet(f"background-color: {bg_color}")

        # Helper to determine if theme is dark
        def is_dark_color(hex_color: str) -> bool:
            hex_color = hex_color.lstrip("#")
            if len(hex_color) == 3:
                hex_color = "".join(c * 2 for c in hex_color)
            try:
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
                return (0.299 * r + 0.587 * g + 0.114 * b) < 128
            except (AttributeError, TypeError, ValueError):
                return True

        is_dark = is_dark_color(bg_color)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground(bg_color)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setTitle(f"<span style='color:{fg_color}; font-size:11pt; font-weight:bold;'>Tournament Results{names}</span>")
        self.plot_widget.setLabel("bottom", "Tournaments", **{"color": fg_color, "font-size": "9pt"})
        display_currency = currencies[0] if currencies else "USD"
        self.plot_widget.setLabel("left", currency_symbol(display_currency), **{"color": fg_color, "font-size": "9pt"})

        border_color = "#2d3741" if is_dark else "#cbd5e1"
        zero_color = "#475569" if is_dark else "#94a3b8"

        axis_pen = pg.mkPen(color=border_color, width=1)
        self.plot_widget.getAxis("left").setPen(axis_pen)
        self.plot_widget.getAxis("bottom").setPen(axis_pen)
        self.plot_widget.getAxis("left").setTextPen(pg.mkPen(color=fg_color))
        self.plot_widget.getAxis("bottom").setTextPen(pg.mkPen(color=fg_color))

        legend = self.plot_widget.addLegend(offset=(10, 10))
        legend.setBrush(pg.mkBrush(color=bg_color))
        legend.setPen(pg.mkPen(color=border_color))

        self.plot_widget.addLine(y=0, pen=pg.mkPen(color=zero_color, width=1, style=Qt.PenStyle.DashLine))

        if is_dark:
            line_hands_color = "#22c55e"
            if "line_hands" in self.colors and self.colors["line_hands"] not in ("c", "g"):
                line_hands_color = self.colors["line_hands"]
        else:
            line_hands_color = "#15803d"
            if "line_hands" in self.colors and self.colors["line_hands"] not in ("c", "g"):
                line_hands_color = self.colors["line_hands"]

        self.plot_widget.plot(
            green,
            pen=pg.mkPen(color=line_hands_color, width=2.5),
            name=f"Tournaments: {format_number(len(green), 0)} | Profit: {format_currency(green[-1], display_currency)}",
        )

        chipev_curves = getattr(self, "chipev_curves", [])
        if chipev_curves:
            curve_palette = ["#ff9f43", "#54a0ff", "#a55eea", "#fc5c65", "#00d2d3", "#fed330"]
            for idx, (label, values) in enumerate(chipev_curves):
                self.plot_widget.plot(
                    values,
                    pen=pg.mkPen(color=curve_palette[idx % len(curve_palette)], width=1.5),
                    name=f"{label}: {format_number(values[-1], 0)}",
                )

        self.graphBox.addWidget(self.plot_widget)

    def getData(self, names, sites, Tourneys):
        tmp = self.sql.query["tourneyGraphType"]
        start_date, end_date = self.filters.getDates()
        tourneys = self.filters.getTourneyTypes()
        tourneysCat = self.filters.getTourneyCat()
        tourneysLim = self.filters.getTourneyLim()
        tourneysBuyin = self.filters.getTourneyBuyin()

        log.debug(f"GuiTourneyGraphViewer.getData: names: {names}, sites: {sites}, Tourneys: {Tourneys}")
        log.debug(
            f"GuiTourneyGraphViewer.getData filters: start_date: {start_date}, end_date: {end_date}, tourneys: {tourneys}, tourneysCat: {tourneysCat}, tourneysLim: {tourneysLim}, tourneysBuyin: {tourneysBuyin}"
        )

        currencies = self.filters.getCurrencies()

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

        currency_values = make_in_clause_sql(currencies, "str")
        currencytest = f"AND tt.currency in {currency_values}" if currency_values else ""
        tourneysCattest = make_in_clause_sql(tourneysCat, "str")
        tourneysLimtest = make_in_clause_sql(tourneysLim, "str")

        buyin_conditions = []
        for buyin_value in tourneysBuyin:
            if buyin_value == "None":
                continue
            buyin, fee, currency = parse_tourney_buyin_key(buyin_value)
            escaped_currency = currency.replace("'", "''")
            buyin_conditions.append(f"(tt.buyin = {buyin} AND tt.fee = {fee} AND tt.currency = '{escaped_currency}')")
        tourneysBuyintest = f"AND ({' OR '.join(buyin_conditions)})" if buyin_conditions else ""

        tourneystest = tourneystest.replace("None", '"None"')

        def apply_filters(query):
            """Substitute the shared tourney filter placeholders into a query."""
            query = query.replace("<player_test>", nametest)
            query = query.replace("<site_test>", sitetest)
            query = query.replace("<startdate_test>", start_date)
            query = query.replace("<enddate_test>", end_date)
            query = query.replace("<currency_test>", currencytest)
            query = query.replace(
                "AND tt.category in <tourney_cat>", f"AND tt.category in {tourneysCattest}" if tourneysCattest else ""
            )
            query = query.replace(
                "AND tt.limitType in <tourney_lim>", f"AND tt.limitType in {tourneysLimtest}" if tourneysLimtest else ""
            )
            query = query.replace("AND tt.buyin in <tourney_buyin>", tourneysBuyintest)
            query = query.replace("<tourney_test>", tourneystest)
            return query.replace(",)", ")")

        tmp = apply_filters(tmp)

        log.debug(f"GuiTourneyGraphViewer.getData: Executing SQL query:\n{tmp}")

        self.db.cursor.execute(tmp)
        winnings = self.db.cursor.fetchall()
        self.db.rollback()

        log.debug(f"GuiTourneyGraphViewer.getData: SQL query returned {len(winnings)} records.")

        # Declarative ChipEV-by-position curves (best-effort: never break the
        # main profit line if anything goes wrong here).
        self.chipev_curves = self.getChipEVCurves(apply_filters)

        if len(winnings) == 0:
            return None

        green = np.array([float(x[1]) for x in winnings])
        greenline = green.cumsum()
        return greenline / 100.0

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
        if self.plot_widget is None:
            return

        path = os.getcwd() + "/graph.png"
        pixmap = self.plot_widget.grab()
        pixmap.save(path)
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
