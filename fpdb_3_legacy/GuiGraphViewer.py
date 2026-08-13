#!/usr/bin/env python
from __future__ import annotations

# Copyright 2010-2011 Maxime Grandchamp
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
#
# This code once was in GuiReplayer.py and was split up in this and the former by zarturo.
# import L10n
# _ = L10n.get_translation()
import contextlib
import os
from time import time
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
)

from fpdb_3_legacy import Database, Filters, gui_empty_state
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.localized_formats import currency_symbol, format_number
from fpdb_3_legacy.loggingFpdb import get_logger

# import L10n
# _ = L10n.get_translation()


# import Charset

log = get_logger("gui_graph_viewer")


class GuiGraphViewer(QSplitter):
    def __init__(self, querylist, config, parent, colors, debug=True) -> None:
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
            "Games": True,
            "Currencies": True,
            "Limits": True,
            "LimitSep": True,
            "LimitType": True,
            "Type": True,
            "UseType": "ring",
            "Seats": False,
            "SeatSep": False,
            "Dates": True,
            "GraphOps": True,
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
        scroll.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
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
        self.exportFile = None

        self.db.rollback()

    def clearGraphData(self) -> None:
        with contextlib.suppress(Exception):
            if self.plot_widget:
                self.graphBox.removeWidget(self.plot_widget)
                self.plot_widget.setParent(None)
                self.plot_widget = None

    def generateGraph(self, widget) -> None:
        self.clearGraphData()

        sitenos = []
        playerids = []
        # winnings = []
        sites = self.filters.getSites()
        heroes = self.filters.getHeroes()
        siteids = self.filters.getSiteIds()
        limits = self.filters.getLimits()
        games = self.filters.getGames()
        currencies = self.filters.getCurrencies()
        graphops = self.filters.getGraphOps()
        display_currency = currencies[0] if currencies else "USD"
        display_in = currency_symbol(display_currency) if "$" in graphops else "BB"
        names = ""

        log.debug(
            f"GuiGraphViewer.generateGraph called. Sites selected: {sites}, Heroes config: {heroes}, siteids: {siteids}, limits: {limits}, games: {games}, currencies: {currencies}, graphops: {graphops}"
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
                        log.debug(f"GuiGraphViewer: Using resolved actual siteId {actual_site_id} for hero '{pname}'")
                    else:
                        sitenos.append(siteids[site])

        log.debug(f"GuiGraphViewer.generateGraph resolved sitenos: {sitenos}, playerids: {playerids}, names: {names!r}")

        missing = gui_empty_state.missing_filter_reason(sites=sites, playerids=playerids, limits=limits)
        if missing is not None:
            gui_empty_state.show_no_data(self, missing, context="Ring profit graph", db=self.db)
            self.db.rollback()
            return
        # debug
        # log.debug("currencies selcted:", self.filters.getCurrencies())

        starttime = time()
        (green, blue, red, orange) = self.getRingProfitGraph(
            playerids,
            sitenos,
            limits,
            games,
            currencies,
            display_in,
        )
        log.debug(f"Graph generated in: {time() - starttime}")

        if green is None or len(green) == 0:
            gui_empty_state.show_no_data(self, context="Ring profit graph", db=self.db)
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
        self.plot_widget.setTitle(f"<span style='color:{fg_color}; font-size:11pt; font-weight:bold;'>Profit graph for ring games{names}</span>")
        self.plot_widget.setLabel("bottom", "Hands", **{"color": fg_color, "font-size": "9pt"})
        self.plot_widget.setLabel("left", display_in, **{"color": fg_color, "font-size": "9pt"})

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
            color_map = {
                "c": "#22c55e",
                "b": "#00a2ff",
                "m": "#f43f5e",
                "g": "#22c55e",
                "r": "#f43f5e",
                "orange": "#ff9f43",
            }
        else:
            color_map = {
                "c": "#15803d",
                "b": "#1d4ed8",
                "m": "#be123c",
                "g": "#15803d",
                "r": "#be123c",
                "orange": "#d97706",
            }

        def get_modern_color(key: str, fallback: str) -> str:
            val = self.colors.get(key, fallback)
            return color_map.get(val, val)

        if "showdown" in graphops and len(blue) > 0:
            self.plot_widget.plot(
                blue,
                pen=pg.mkPen(color=get_modern_color("line_showdown", "b"), width=1.8),
                name=_("Showdown") + f" ({display_in}): {format_number(blue[-1])}",
            )

        if "nonshowdown" in graphops and len(red) > 0:
            self.plot_widget.plot(
                red,
                pen=pg.mkPen(color=get_modern_color("line_nonshowdown", "m"), width=1.8),
                name=_("Non-showdown") + f" ({display_in}): {format_number(red[-1])}",
            )

        if "ev" in graphops and len(orange) > 0:
            self.plot_widget.plot(
                orange,
                pen=pg.mkPen(color=get_modern_color("line_ev", "orange"), width=1.8, style=Qt.PenStyle.DashLine),
                name=("All-in EV") + f" ({display_in}): {format_number(orange[-1])}",
            )

        hand_count = max(len(green) - 1, 0)
        self.plot_widget.plot(
            green,
            pen=pg.mkPen(color=get_modern_color("line_hands", "c"), width=2.5),
            name=_("Hands")
            + f": {format_number(hand_count, 0)} | "
            + _("Profit")
            + f": ({display_in}): {format_number(green[-1])}",
        )

        self.graphBox.addWidget(self.plot_widget)

    def getRingProfitGraph(self, names, sites, limits, games, currencies, units):
        log.warning(
            f"GuiGraphViewer.getRingProfitGraph: names: {names}, sites: {sites}, limits: {limits}, games: {games}, currencies: {currencies}, units: {units}"
        )
        # ``units`` is the display symbol: "BB" for big-blind mode, otherwise a
        # (possibly localized) currency symbol like "$", "€" or "£". Selecting
        # the query on the literal "$" broke every non-USD currency, so decide
        # on BB-vs-currency instead: the "InDollars" query returns raw monetary
        # amounts regardless of currency, and ``units`` only labels the axis.
        if units == "BB":
            tmp = self.sql.query["getRingProfitAllHandsPlayerIdSiteInBB"]
        else:
            tmp = self.sql.query["getRingProfitAllHandsPlayerIdSiteInDollars"]

        start_date, end_date = self.filters.getDates()

        nametest = str(tuple(names))
        sitetest = str(tuple(sites))

        gametest = ""

        for m in list(self.filters.display.items()):
            if m[0] == "Games" and m[1]:
                if len(games) > 0:
                    gametest = str(tuple(games))
                    gametest = gametest.replace("L", "")
                    gametest = gametest.replace(",)", ")")
                    gametest = gametest.replace("u'", "'")
                    gametest = f"and gt.category in {gametest}"
                else:
                    gametest = "and gt.category IS NULL"

        tmp = tmp.replace("<game_test>", gametest)

        limittest = self.filters.get_limits_where_clause(limits)

        # An empty currency selection would build "gt.currency in ()", which is
        # invalid SQL: the failed execute aborts the transaction and every later
        # query fails until restart. Match no rows instead (handled as no data).
        if currencies:
            currencytest = str(tuple(currencies))
            currencytest = currencytest.replace(",)", ")")
            currencytest = currencytest.replace("u'", "'")
            currencytest = f"AND gt.currency in {currencytest}"
        else:
            currencytest = "AND 1=0"

        game_type = self.filters.getType()

        if game_type == "ring":
            limittest = limittest + " and gt.type = 'ring' "
        elif game_type == "tour":
            limittest = limittest + " and gt.type = 'tour' "

        tmp = tmp.replace("<player_test>", nametest)
        tmp = tmp.replace("<site_test>", sitetest)
        tmp = tmp.replace("<startdate_test>", start_date)
        tmp = tmp.replace("<enddate_test>", end_date)
        tmp = tmp.replace("<limit_test>", limittest)
        tmp = tmp.replace("<currency_test>", currencytest)
        tmp = tmp.replace(",)", ")")

        log.warning(f"GuiGraphViewer.getRingProfitGraph: Executing SQL query:\n{tmp}")

        try:
            self.db.cursor.execute(tmp)
            winnings = self.db.cursor.fetchall()
        except Exception:
            # Roll back so a single malformed query can't leave the connection
            # in an aborted transaction that blanks every subsequent graph.
            log.exception("getRingProfitGraph: query failed; rolling back")
            self.db.rollback()
            return (None, None, None, None)
        self.db.rollback()

        log.warning(f"GuiGraphViewer.getRingProfitGraph: SQL query returned {len(winnings)} records.")

        if len(winnings) == 0:
            return (None, None, None, None)

        green = np.array([0.0, *[float(x[1]) for x in winnings]])
        blue = np.array([0.0, *[float(x[1]) if x[2] else 0.0 for x in winnings]])
        red = np.array([0.0, *[float(x[1]) if not x[2] else 0.0 for x in winnings]])
        orange = np.array([0.0, *[float(x[3]) if x[3] is not None else 0.0 for x in winnings]])
        # NumPy 2.x: use array method instead of numpy.cumsum()
        greenline = green.cumsum()
        blueline = blue.cumsum()
        redline = red.cumsum()
        orangeline = orange.cumsum()

        # log.debug("Data :")
        # log.debug("Green:", green[:10])  # show only the first 10 results
        # log.debug("Blue:", blue[:10])
        # log.debug("Red:", red[:10])
        # log.debug("Orange:", orange[:10])

        # log.debug("sum :")
        # log.debug("Greenline:", greenline[:10])
        # log.debug("Blueline:", blueline[:10])
        # log.debug("Redline:", redline[:10])
        # log.debug("Orangeline:", orangeline[:10])

        return (greenline / 100, blueline / 100, redline / 100, orangeline / 100)

    def exportGraph(self) -> None:
        if self.plot_widget is None:
            return
        path = f"{os.getcwd()}/graph.png"
        pixmap = self.plot_widget.grab()
        pixmap.save(path)
        msg = QMessageBox()
        msg.setWindowTitle(_("FPDB 3 info"))
        mess = f"Your graph is saved in {path}"
        msg.setText(mess)
        msg.exec()
