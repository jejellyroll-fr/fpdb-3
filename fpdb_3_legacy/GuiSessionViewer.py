#!/usr/bin/env python
from __future__ import annotations

# Copyright 2008-2011 Steffen Schaumburg
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
import sys
import traceback
from datetime import datetime
from importlib import import_module
from time import gmtime, strftime, time
from typing import Any

mpl = import_module("matplotlib")
np = import_module("numpy")
FigureCanvas = getattr(import_module("matplotlib.backends.backend_qt5agg"), "FigureCanvas")
Figure = getattr(import_module("matplotlib.figure"), "Figure")
FuncFormatter = getattr(import_module("matplotlib.ticker"), "FuncFormatter")
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QSplitter,
    QTableView,
    QVBoxLayout,
)

from fpdb_3_legacy import Database, Filters, GuiHandViewer
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.localized_formats import currency_symbol, format_currency, format_datetime, format_number
from fpdb_3_legacy.loggingFpdb import get_logger

# import L10n
# _ = L10n.get_translation()


# import Charset


log = get_logger("gui_session_viewer")
DEBUG = False

try:
    calluse = not "matplotlib" in sys.modules
    if calluse:
        try:
            mpl.use("qt5agg")
        except ValueError as e:
            log.exception(f"error importing matplotlib: {e}")
except ImportError as inst:
    log.exception("Failed to load numpy and/or matplotlib in Session Viewer")
    log.exception(f"ImportError: {inst.args}")


class GuiSessionViewer(QSplitter):
    def __init__(self, config, querylist, mainwin, owner, colors, debug=True) -> None:
        QSplitter.__init__(self, mainwin)
        self.debug = debug
        self.conf = config
        self.sql = querylist
        self.window = mainwin
        self.owner: Any = owner
        self.colors = colors

        self.liststore: Any = None

        self.MYSQL_INNODB = 2
        self.PGSQL = 3
        self.SQLITE = 4

        self.fig: Any = None
        self.canvas: Any = None
        self.ax: Any = None
        self.graphBox: Any = None

        # create new db connection to avoid conflicts with other threads
        self.db = Database.Database(self.conf, sql=self.sql)
        self.cursor = self.db.cursor

        settings = {}
        settings.update(self.conf.get_db_parameters())
        settings.update(self.conf.get_import_parameters())
        settings.update(self.conf.get_default_paths())

        # text used on screen stored here so that it can be configured
        self.filterText = {"handhead": _("Hand Breakdown for all levels listed above")}

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
            "Seats": True,
            "SeatSep": False,
            "Dates": True,
            "Groups": False,
            "GroupsAll": False,
            "Button1": True,
            "Button2": False,
        }

        self.filters = Filters.Filters(self.db, display=filters_display)
        self.filters.registerButton1Name("_Refresh")
        self.filters.registerButton1Callback(self.refreshStats)

        scroll = QScrollArea()
        scroll.setObjectName("filterSidebar")
        scroll.setWidget(self.filters)

        self.columns = [
            (1.0, "SID"),
            (1.0, "Hands"),
            (0.5, "Start"),
            (0.5, "End"),
            (1.0, "Rate"),
            (1.0, "Open"),
            (1.0, "Close"),
            (1.0, "Low"),
            (1.0, "High"),
            (1.0, "Range"),
            (1.0, "Profit"),
        ]

        self.detailFilters: list[Any] = []

        self.stats_frame = QFrame()
        self.stats_frame.setObjectName("statsSurface")
        self.stats_frame.setLayout(QVBoxLayout())
        self.view: Any = None
        heading = QLabel(self.filterText["handhead"])
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stats_frame.layout().addWidget(heading)

        self.main_vbox = QSplitter(Qt.Orientation.Vertical)

        self.graphBox = QFrame()
        self.graphBox.setObjectName("graphCanvasPanel")
        self.graphBox.setStyleSheet(f"background-color: {self.colors['background']}")
        self.graphBox.setLayout(QVBoxLayout())

        self.addWidget(scroll)
        self.addWidget(self.main_vbox)
        self.setStretchFactor(0, 0)
        self.setStretchFactor(1, 1)
        self.main_vbox.addWidget(self.graphBox)
        self.main_vbox.addWidget(self.stats_frame)

    def refreshStats(self, checkState) -> None:
        log.warning(f"GuiSessionViewer.refreshStats called with checkState: {checkState}")
        if self.view:
            self.stats_frame.layout().removeWidget(self.view)
            self.view.setParent(None)
        self.fillStatsFrame(self.stats_frame)

    def fillStatsFrame(self, frame) -> None:
        sites = self.filters.getSites()
        heroes = self.filters.getHeroes()
        siteids = self.filters.getSiteIds()
        games = self.filters.getGames()
        currencies = self.filters.getCurrencies()
        limits = self.filters.getLimits()
        seats = self.filters.getSeats()
        sitenos = []
        playerids = []

        log.warning(f"GuiSessionViewer.fillStatsFrame called. sites: {sites}, heroes: {heroes}, siteids: {siteids}, games: {games}, currencies: {currencies}, limits: {limits}, seats: {seats}")

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
                    actual_site_id = self.db.get_player_site_id(pid)
                    if actual_site_id is not None:
                        sitenos.append(actual_site_id)
                        log.warning(f"GuiSessionViewer.fillStatsFrame: Using resolved actual siteId {actual_site_id} for hero playerId {pid}")
                    else:
                        sitenos.append(siteids[site])

        log.warning(f"GuiSessionViewer.fillStatsFrame resolved sitenos: {sitenos}, playerids: {playerids}")

        if not sitenos:
            log.warning("GuiSessionViewer.fillStatsFrame: No sites selected - defaulting to PokerStars (2)")
            sitenos = [2]
        if not games:
            log.warning("GuiSessionViewer.fillStatsFrame: No games found")
            return
        if not currencies:
            log.warning("GuiSessionViewer.fillStatsFrame: No currencies found")
            return
        if not playerids:
            log.warning("GuiSessionViewer.fillStatsFrame: No player ids found")
            return
        if not limits:
            log.warning("GuiSessionViewer.fillStatsFrame: No limits found")
            return

        self.createStatsPane(
            frame,
            playerids,
            sitenos,
            games,
            currencies,
            limits,
            seats,
        )

    def createStatsPane(
        self,
        frame,
        playerids,
        sitenos,
        games,
        currencies,
        limits,
        seats,
    ) -> None:
        starttime = time()

        (results, quotes) = self.generateDatasets(
            playerids,
            sitenos,
            games,
            currencies,
            limits,
            seats,
        )

        if not results or not quotes:
            self.clearGraphData()
            if self.canvas:
                self.canvas.setParent(None)
                self.canvas = None
            from PySide6.QtWidgets import QMessageBox
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle(_("FPDB 3 info"))
            msg.setText("No data found for the selected filters.")
            msg.exec()
            self.db.rollback()
            return

        if DEBUG:
            for x in quotes:
                log.debug(f"start {x[1]}\tend {x[2]}\thigh {x[3]}\tlow {x[4]}")

        self.generateGraph(quotes, currencies)

        self.addTable(frame, results)

        self.db.rollback()
        log.debug(f"Stats page displayed in {time() - starttime:4.2f} seconds")

    def generateDatasets(self, playerids, sitenos, games, currencies, limits, seats):
        log.warning(f"GuiSessionViewer.generateDatasets: playerids: {playerids}, sitenos: {sitenos}, games: {games}, currencies: {currencies}, limits: {limits}, seats: {seats}")
        THRESHOLD = 1800  # Min # of secs between consecutive hands before being considered a new session
        PADDING = 5  # Additional time in minutes to add to a session, session startup, shutdown etc

        q = self.sql.query["sessionStats"]
        start_date, end_date = self.filters.getDates()
        q = q.replace(
            "<datestest>",
            " BETWEEN '" + start_date + "' AND '" + end_date + "'",
        )

        for m in list(self.filters.display.items()):
            if m[0] == "Games" and m[1]:
                if len(games) > 0:
                    gametest = str(tuple(games))
                    gametest = gametest.replace("L", "")
                    gametest = gametest.replace(",)", ")")
                    gametest = gametest.replace("u'", "'")
                    gametest = f"AND gt.category in {gametest}"
                else:
                    gametest = "AND gt.category IS NULL"
        q = q.replace("<game_test>", gametest)

        limittest = self.filters.get_limits_where_clause(limits)
        q = q.replace("<limit_test>", limittest)

        currencytest = str(tuple(currencies))
        currencytest = currencytest.replace(",)", ")")
        currencytest = currencytest.replace("u'", "'")
        currencytest = f"AND gt.currency in {currencytest}"
        q = q.replace("<currency_test>", currencytest)

        if seats:
            q = q.replace(
                "<seats_test>",
                "AND h.seats BETWEEN " + str(seats["from"]) + " AND " + str(seats["to"]),
            )
        else:
            q = q.replace("<seats_test>", "AND h.seats BETWEEN 0 AND 100")

        nametest = str(tuple(playerids))
        nametest = nametest.replace("L", "")
        nametest = nametest.replace(",)", ")")
        q = q.replace("<player_test>", nametest)
        q = q.replace("<ampersand_s>", "%s")

        if DEBUG:
            hands = [
                ("10000", 10),
                ("10000", 20),
                ("10000", 30),
                ("20000", -10),
                ("20000", -20),
                ("20000", -30),
                ("30000", 40),
                ("40000", 0),
                ("50000", -40),
                ("60000", 10),
                ("60000", 30),
                ("60000", -20),
                ("70000", -20),
                ("70000", 10),
                ("70000", 30),
                ("80000", -10),
                ("80000", -30),
                ("80000", 20),
                ("90000", 20),
                ("90000", -10),
                ("90000", -30),
                ("100000", 30),
                ("100000", -50),
                ("100000", 30),
                ("110000", -20),
                ("110000", 50),
                ("110000", -20),
                ("120000", -30),
                ("120000", 50),
                ("120000", -30),
                ("130000", 20),
                ("130000", -50),
                ("130000", 20),
                ("140000", 40),
                ("140000", -40),
                ("150000", -40),
                ("150000", 40),
                ("160000", -40),
                ("160000", 80),
                ("160000", -40),
            ]
        else:
            log.warning(f"GuiSessionViewer.generateDatasets: Executing SQL query:\n{q}")
            self.db.cursor.execute(q)
            hands = self.db.cursor.fetchall()

        hands = list(hands)
        log.warning(f"GuiSessionViewer.generateDatasets: SQL query returned {len(hands)} hands.")

        if not hands:
            return ([], [])

        hands.insert(0, (hands[0][0], 0))

        times = np.array([int(x[0]) for x in hands])
        profits = np.array([float(x[1]) for x in hands])
        # NumPy 2.x: use array methods instead of numpy functions
        diffs = np.diff(times)
        diffs2 = np.append(diffs, THRESHOLD + 1)
        index = np.nonzero(diffs2 > THRESHOLD)
        if len(index[0]) > 0:
            pass
        else:
            index = [[0]]

        first_idx = 1
        quotes = []
        results = []
        # NumPy 2.x: use array method instead of numpy.cumsum()
        cum_sum = (profits.cumsum()) // (100)
        sid = 1

        total_hands = 0
        total_time = 0
        global_open: Any = None
        global_lwm: Any = None
        global_hwm: Any = None

        self.times = []
        for i in range(len(index[0])):
            last_idx = index[0][i]
            hds = last_idx - first_idx + 1
            if hds > 0:
                stime = format_datetime(datetime.fromtimestamp(times[first_idx]))
                etime = format_datetime(datetime.fromtimestamp(times[last_idx]))
                self.times.append(
                    (times[first_idx] - PADDING * 60, times[last_idx] + PADDING * 60),
                )
                minutesplayed = (times[last_idx] - times[first_idx]) // (60)
                minutesplayed = minutesplayed + PADDING
                if minutesplayed == 0:
                    minutesplayed = 1
                hph = hds * 60 / minutesplayed
                end_idx = last_idx + 1
                won = (sum(profits[first_idx:end_idx])) // (100.0)
                hwm = cum_sum[first_idx - 1 : end_idx].max()  # NumPy 2.x: use array method
                lwm = cum_sum[first_idx - 1 : end_idx].min()  # NumPy 2.x: use array method
                open = (sum(profits[:first_idx])) // (100)
                close = (sum(profits[:end_idx])) // (100)

                total_hands = total_hands + hds
                total_time = total_time + minutesplayed
                if global_lwm is None or global_lwm > lwm:
                    global_lwm = lwm
                if global_hwm is None or global_hwm < hwm:
                    global_hwm = hwm
                if global_open is None:
                    global_open = open
                    global_stime = stime

                results.append(
                    [
                        sid,
                        hds,
                        stime,
                        etime,
                        hph,
                        format_number(open),
                        format_number(close),
                        format_number(lwm),
                        format_number(hwm),
                        format_number(hwm - lwm),
                        format_number(won),
                    ],
                )
                quotes.append((sid, open, close, hwm, lwm))
                first_idx = end_idx
                sid = sid + 1
            else:
                log.debug("hds <= 0")
        global_close = close
        global_etime = etime
        results.append([""] * 11)
        results.append(
            [
                ("all"),
                total_hands,
                global_stime,
                global_etime,
                total_hands * 60 // total_time,
                f"{global_open:.2f}",
                f"{global_close:.2f}",
                f"{global_lwm:.2f}",
                f"{global_hwm:.2f}",
                "%.2f" % (global_hwm - global_lwm),
                "%.2f" % (global_close - global_open),
            ],
        )

        return (results, quotes)

    def clearGraphData(self) -> None:
        try:
            try:
                if self.canvas:
                    self.graphBox.layout().removeWidget(self.canvas)
                    self.canvas.setParent(None)
            except (AttributeError, RuntimeError) as e:
                # Handle specific exceptions here if you expect them
                log.exception(f"Error during canvas cleanup: {e}")

            if self.fig is not None:
                self.fig.clear()
            self.fig = None

            if self.canvas is not None:
                self.canvas.destroy()
            self.canvas = None
        except Exception as e:  # intentional broad catch: matplotlib canvas build boundary, log only
            # Catch all other exceptions and log for better debugging
            err = traceback.extract_tb(sys.exc_info()[2])[-1]
            log.exception(f"Error: {err[2]}({err[1]}): {e}")
            raise

    def generateGraph(self, quotes, currencies: list[str] | None = None) -> None:
        self.clearGraphData()
        sitenos = []
        playerids = []

        sites = self.filters.getSites()
        heroes = self.filters.getHeroes()
        siteids = self.filters.getSiteIds()
        limits = self.filters.getLimits()

        log.warning(f"GuiSessionViewer.generateGraph called. quotes count: {len(quotes)}, sites: {sites}, heroes: {heroes}")

        names = ""

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
                        log.warning(f"GuiSessionViewer.generateGraph: Using resolved actual siteId {actual_site_id} for hero '{pname}'")
                    else:
                        sitenos.append(siteids[site])

        log.warning(f"GuiSessionViewer.generateGraph resolved sitenos: {sitenos}, playerids: {playerids}")

        if not sitenos:
            log.warning("GuiSessionViewer.generateGraph: No sites selected")
            self.db.rollback()
            return

        if not playerids:
            log.warning("GuiSessionViewer.generateGraph: No player ids found")
            self.db.rollback()
            return

        if not limits:
            log.warning("GuiSessionViewer.generateGraph: No limits found")
            self.db.rollback()
            return

        bg = self.colors["background"]
        fg = self.colors["foreground"]
        grid = self.colors["grid"]
        line = self.colors.get("line_hands", "#22c55e")
        gain = self.colors.get("line_up", "#22c55e")
        loss = self.colors.get("line_down", "#ef4444")

        self.fig = Figure(figsize=(6.2, 3.2), dpi=100)
        self.fig.patch.set_facecolor(bg)
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setParent(self)

        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor(bg)

        session_ids = np.array([float(q[0]) for q in quotes])
        opens = np.array([float(q[1]) for q in quotes])
        closes = np.array([float(q[2]) for q in quotes])
        highs = np.array([float(q[3]) for q in quotes])
        lows = np.array([float(q[4]) for q in quotes])
        profits = closes - opens
        display_currency = currencies[0] if currencies else "USD"

        session_colors = [gain if value >= 0 else loss for value in profits]
        self.ax.vlines(session_ids, lows, highs, color=grid, linewidth=1.0, alpha=0.38, zorder=1)
        for sid, start, end, color in zip(session_ids, opens, closes, session_colors, strict=False):
            self.ax.plot([sid, sid], [start, end], color=color, linewidth=5.0, alpha=0.78, solid_capstyle="round", zorder=2)
            self.ax.scatter([sid], [end], s=42, color=color, edgecolor=bg, linewidth=1.2, zorder=4)

        self.ax.plot(session_ids, closes, color=line, linewidth=2.8, marker="o", markersize=5.0, zorder=5)
        self.ax.axhline(0, color=grid, linestyle="--", linewidth=1.0, alpha=0.85, zorder=3)

        best_idx = int(np.argmax(closes))
        worst_idx = int(np.argmin(closes))
        for idx, label, offset in ((best_idx, "Best", 10), (worst_idx, "Worst", -18)):
            if best_idx == worst_idx and label == "Worst":
                continue
            self.ax.annotate(
                f"{label} {format_currency(closes[idx], display_currency)}",
                (session_ids[idx], closes[idx]),
                textcoords="offset points",
                xytext=(8, offset),
                color=fg,
                fontsize=8,
                alpha=0.86,
            )

        for sid, close, profit in zip(session_ids, closes, profits, strict=False):
            self.ax.annotate(
                format_currency(profit, display_currency),
                (sid, close),
                textcoords="offset points",
                xytext=(0, 10 if profit >= 0 else -16),
                ha="center",
                color=gain if profit >= 0 else loss,
                fontsize=8,
                fontweight="bold",
                alpha=0.9,
            )

        total = closes[-1] if len(closes) else 0
        self.ax.set_title(
            f"Session profit: {format_currency(total, display_currency)}{names}",
            color=fg,
            fontsize=13,
            fontweight="bold",
            pad=10,
        )
        self.ax.set_xlabel(_("Session"), fontsize=10, color=fg, labelpad=8)
        self.ax.set_ylabel(currency_symbol(display_currency), color=fg, labelpad=8)
        self.ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _position: format_number(value)))
        self.ax.tick_params(axis="x", colors=fg, labelsize=9)
        self.ax.tick_params(axis="y", colors=fg, labelsize=9)
        self.ax.grid(True, color=grid, linestyle=":", linewidth=0.6, alpha=0.6)
        self.ax.set_xticks(session_ids)
        self.ax.margins(x=0.08, y=0.22)

        for spine in ("top", "right"):
            self.ax.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            self.ax.spines[spine].set_color(grid)
            self.ax.spines[spine].set_alpha(0.75)

        self.fig.tight_layout(pad=1.5)
        self.graphBox.layout().addWidget(self.canvas)
        self.canvas.draw()

    def addTable(self, frame, results) -> None:
        colxalign, colheading = list(range(2))

        self.liststore = QStandardItemModel(0, len(self.columns))
        self.liststore.setHorizontalHeaderLabels(
            [column[colheading] for column in self.columns],
        )
        for row in results:
            listrow = [QStandardItem(str(r)) for r in row]
            for item in listrow:
                item.setEditable(False)
            self.liststore.appendRow(listrow)

        self.view = QTableView()
        self.view.setModel(self.liststore)
        self.view.verticalHeader().hide()
        self.view.setSelectionBehavior(QTableView.SelectRows)
        frame.layout().addWidget(self.view)
        self.view.doubleClicked.connect(self.row_activated)

    def row_activated(self, index) -> None:
        if index.row() < len(self.times):
            replayer = None
            for tabobject in self.owner.threads:
                if isinstance(tabobject, GuiHandViewer.GuiHandViewer):
                    replayer = tabobject
                    self.owner.tab_hand_viewer(None)
                    break
            if replayer is None:
                self.owner.tab_hand_viewer(None)
                for tabobject in self.owner.threads:
                    if isinstance(tabobject, GuiHandViewer.GuiHandViewer):
                        replayer = tabobject
                        break
            if replayer is None:
                return
            reformat = lambda t: strftime("%Y-%m-%d %H:%M:%S+00:00", gmtime(t))
            handids = replayer.get_hand_ids_from_date_range(
                reformat(self.times[index.row()][0]),
                reformat(self.times[index.row()][1]),
            )
            log.debug(f"handids: {handids}")

            replayer.reload_hands(handids)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    # Launch the session viewer GUI like the original
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
        "line_showdown": "b",
        "line_nonshowdown": "m",
        "line_ev": "orange",
        "line_hands": "c",
    }

    i = GuiSessionViewer(config, sql, None, None, colors)
    main_window = QMainWindow()
    main_window.setCentralWidget(i)
    main_window.show()
    main_window.resize(1400, 800)
    app.exec()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
