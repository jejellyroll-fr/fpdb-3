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
import contextlib
import sys
from datetime import datetime
from time import time
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QSplitter,
    QTableView,
    QVBoxLayout,
)

from fpdb_3_legacy import Database, Filters, GuiHandViewer, gui_empty_state
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.localized_formats import format_currency, format_datetime, format_number
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.ring_stats.base import DbWorker
from fpdb_3_legacy.session_analytics import SessionMetrics, build_sessions, summarize_sessions
from fpdb_3_legacy.table_export import install_table_export

log = get_logger("gui_session_viewer")
DEBUG = False


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

        self.canvas: Any = None
        self.graphBox: Any = None
        self._db_worker: DbWorker | None = None
        self.session_metrics: list[SessionMetrics] = []

        # create new db connection to avoid conflicts with other threads
        self.db = Database.Database(self.conf, sql=self.sql)
        self.cursor = self.db.cursor

        settings = {}
        settings.update(self.conf.get_db_parameters())
        settings.update(self.conf.get_import_parameters())

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
            (1.0, "Session"),
            (1.0, "Hands"),
            (1.0, "BB hands"),
            (0.5, "Start"),
            (0.5, "End"),
            (1.0, "Duration"),
            (1.0, "Hands/hour"),
            (1.0, "Profit"),
            (1.0, "Profit (BB)"),
            (1.0, "bb/100"),
            (1.0, "All-in EV"),
            (1.0, "All-in EV (BB)"),
            (1.0, "EV bb/100"),
            (1.0, "EV difference"),
            (1.0, "Peak"),
            (1.0, "Low"),
            (1.0, "Max drawdown"),
            (1.0, "BB/hour"),
            (1.0, "Currency/hour"),
        ]

        self.detailFilters: list[Any] = []

        self.stats_frame = QFrame()
        self.stats_frame.setObjectName("statsSurface")
        self.stats_frame.setLayout(QVBoxLayout())
        self.view: Any = None
        self.plot_widget: Any = None
        self.times: list[tuple[int, ...]] = []
        heading = QLabel(self.filterText["handhead"])
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stats_frame.layout().addWidget(heading)
        self.summary_label = QLabel()
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stats_frame.layout().addWidget(self.summary_label)

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

    def close_owned_database(self) -> None:
        """Release the connection created for this tab."""
        with contextlib.suppress(Exception):
            self.db.disconnect()

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

        log.warning(
            f"GuiSessionViewer.fillStatsFrame called. sites: {sites}, heroes: {heroes}, siteids: {siteids}, games: {games}, currencies: {currencies}, limits: {limits}, seats: {seats}"
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
                    actual_site_id = self.db.get_player_site_id(pid)
                    if actual_site_id is not None:
                        sitenos.append(actual_site_id)
                        log.warning(
                            f"GuiSessionViewer.fillStatsFrame: Using resolved actual siteId {actual_site_id} for hero playerId {pid}"
                        )
                    else:
                        sitenos.append(siteids[site])

        log.warning(f"GuiSessionViewer.fillStatsFrame resolved sitenos: {sitenos}, playerids: {playerids}")

        missing = gui_empty_state.missing_filter_reason(
            sites=sites,
            playerids=playerids,
            limits=limits,
            games=games,
            currencies=currencies,
        )
        if missing is not None:
            self.session_metrics = []
            self.times = []
            self.summary_label.clear()
            self.clearGraphData()
            gui_empty_state.show_no_data(self, missing, context="Session viewer", db=self.db)
            self.db.rollback()
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
        q = self.build_session_query(playerids, sitenos, games, currencies, limits, seats)

        # Disconnect any previously running worker for this tab
        if self._db_worker is not None:
            with contextlib.suppress(Exception):
                self._db_worker.finished.disconnect()

        self._db_worker = DbWorker(self.db, "sessionStats", q)

        def _on_query_finished(name, results_rows, colnames):
            hands = list(results_rows) if results_rows else []
            log.warning(f"GuiSessionViewer DbWorker finished: returned {len(hands)} hands.")
            if not hands:
                self.session_metrics = []
                self.times = []
                self.summary_label.setText("")
                self.clearGraphData()
                if self.canvas:
                    self.canvas.setParent(None)
                    self.canvas = None
                gui_empty_state.show_no_data(self, context="Session viewer", db=self.db)
                with contextlib.suppress(Exception):
                    self.db.rollback()
                return

            (results, quotes) = self.process_session_hands(hands)
            if not results or not quotes:
                self.clearGraphData()
                if self.canvas:
                    self.canvas.setParent(None)
                    self.canvas = None
                gui_empty_state.show_no_data(self, context="Session viewer", db=self.db)
                with contextlib.suppress(Exception):
                    self.db.rollback()
                return

            if DEBUG:
                for x in quotes:
                    log.debug(f"start {x[1]}\tend {x[2]}\thigh {x[3]}\tlow {x[4]}")

            self.generateGraph(quotes, currencies)
            self.addTable(frame, results)
            with contextlib.suppress(Exception):
                self.db.rollback()
            log.warning(f"[PERF] GuiSessionViewer Stats page displayed in {time() - starttime:4.2f} seconds")

        def _on_query_error(err_msg):
            log.error(f"GuiSessionViewer DbWorker error: {err_msg}")
            self.session_metrics = []
            self.times = []
            self.summary_label.clear()
            self.clearGraphData()
            gui_empty_state.show_no_data(self, context="Session viewer", db=self.db)

        self._db_worker.finished.connect(_on_query_finished)
        self._db_worker.error.connect(_on_query_error)
        self._db_worker.start()

    def build_session_query(self, playerids, sitenos, games, currencies, limits, seats) -> str:
        q = self.sql.query["sessionStats"]
        start_date, end_date = self.filters.getDates()
        q = q.replace(
            "<datestest>",
            " BETWEEN '" + start_date + "' AND '" + end_date + "'",
        )

        gametest = ""
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

        if currencies:
            currencytest = str(tuple(currencies))
            currencytest = currencytest.replace(",)", ")")
            currencytest = currencytest.replace("u'", "'")
            currencytest = f"AND gt.currency in {currencytest}"
        else:
            currencytest = "AND 1=0"
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
        return q.replace("<ampersand_s>", "%s")

    def generateDatasets(self, playerids, sitenos, games, currencies, limits, seats):
        q = self.build_session_query(playerids, sitenos, games, currencies, limits, seats)
        self.db.cursor.execute(q)
        hands = self.db.cursor.fetchall()
        return self.process_session_hands(hands)

    def process_session_hands(self, hands: list):
        self.session_metrics = build_sessions(list(hands))
        self.times = [session.hand_ids for session in self.session_metrics]
        if not self.session_metrics:
            self.summary_label.setText("")
            return ([], [])

        summary = summarize_sessions(self.session_metrics)
        duration = self._format_duration(summary["duration_seconds"])
        summary_text = _(
            "Sessions: {sessions} · Hands: {hands} · Playing time: {duration} · Profit: {profit_bb} BB · bb/100: {bb100} · BB/hour: {bb_hour} · BB hands: {bb_hands}/{hands}"
        ).format(
            sessions=format_number(summary["sessions"], 0),
            hands=format_number(summary["hands"], 0),
            duration=duration,
            profit_bb=self._format_optional_number(summary["profit_bb"]),
            bb100=self._format_optional_number(summary["bb_per_100"]),
            bb_hour=self._format_optional_number(summary["bb_per_hour"]),
            bb_hands=format_number(summary["bb_hands"], 0),
        )
        if summary["currency"] is not None:
            summary_text += " · " + _("Profit: {profit} · Currency/hour: {hour}").format(
                profit=format_currency(summary["profit_minor"] / 100, summary["currency"], show_plus=True),
                hour=format_currency(summary["currency_per_hour"], summary["currency"], show_plus=True),
            )
        else:
            summary_text += " · " + _("Native-currency totals omitted (multiple currencies)")
        self.summary_label.setText(summary_text)

        results = []
        quotes = []
        for session in self.session_metrics:
            start = format_datetime(datetime.fromtimestamp(session.start_timestamp))
            end = format_datetime(datetime.fromtimestamp(session.end_timestamp))
            currency = session.currency
            results.append(
                [
                    str(session.number),
                    format_number(session.hands, 0),
                    format_number(session.bb_hands, 0),
                    start,
                    end,
                    self._format_duration(session.duration_seconds),
                    format_number(session.hands * 3600 / session.duration_seconds, 0),
                    format_currency(session.profit_minor / 100, currency, show_plus=True),
                    self._format_optional_number(session.profit_bb),
                    self._format_optional_number(session.bb_per_100),
                    format_currency(session.all_in_ev_minor / 100, currency, show_plus=True),
                    self._format_optional_number(session.all_in_ev_bb),
                    self._format_optional_number(session.ev_bb_per_100),
                    format_currency(session.ev_difference_minor / 100, currency, show_plus=True),
                    format_currency(session.peak_minor / 100, currency, show_plus=True),
                    format_currency(session.low_minor / 100, currency, show_plus=True),
                    format_currency(session.max_drawdown_minor / 100, currency),
                    self._format_optional_number(session.bb_per_hour),
                    format_currency(session.currency_per_hour or 0, currency, show_plus=True),
                ]
            )
            bb_result = session.profit_bb if session.bb_hands == session.hands else None
            quotes.append(
                (
                    session.number,
                    0.0,
                    bb_result if bb_result is not None else float("nan"),
                    max(0.0, bb_result) if bb_result is not None else float("nan"),
                    min(0.0, bb_result) if bb_result is not None else float("nan"),
                )
            )
        return (results, quotes)

    @staticmethod
    def _format_duration(seconds: int) -> str:
        minutes = max(1, seconds // 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return _("{hours}h {minutes}m").format(hours=hours, minutes=minutes)
        return _("{minutes}m").format(minutes=minutes)

    @staticmethod
    def _format_optional_number(value: float | None) -> str:
        return format_number(value, show_plus=True) if value is not None else "—"

    def clearGraphData(self) -> None:
        with contextlib.suppress(Exception):
            if self.plot_widget is not None:
                self.graphBox.layout().removeWidget(self.plot_widget)
                self.plot_widget.setParent(None)
                self.plot_widget = None

    def generateGraph(self, quotes, _currencies: list[str] | None = None) -> None:
        self.clearGraphData()
        sitenos = []
        playerids = []

        sites = self.filters.getSites()
        heroes = self.filters.getHeroes()
        siteids = self.filters.getSiteIds()
        limits = self.filters.getLimits()

        log.warning(
            f"GuiSessionViewer.generateGraph called. quotes count: {len(quotes)}, sites: {sites}, heroes: {heroes}"
        )

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
                        log.warning(
                            f"GuiSessionViewer.generateGraph: Using resolved actual siteId {actual_site_id} for hero '{pname}'"
                        )
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
        gain = self.colors.get("line_up", "#22c55e")
        loss = self.colors.get("line_down", "#ef4444")

        session_ids = np.array([float(q[0]) for q in quotes])
        opens = np.array([float(q[1]) for q in quotes])
        closes = np.array([float(q[2]) for q in quotes])
        highs = np.array([float(q[3]) for q in quotes])
        lows = np.array([float(q[4]) for q in quotes])
        profits = closes - opens
        session_colors = [gain if value >= 0 else loss if np.isfinite(value) else grid for value in profits]

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground(bg)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)

        valid_profits = profits[np.isfinite(profits)]
        total = float(valid_profits.sum()) if len(valid_profits) else 0.0
        excluded_sessions = sum(session.bb_hands < session.hands for session in self.session_metrics)
        excluded_note = f" · {excluded_sessions} sessions with incomplete BB data omitted" if excluded_sessions else ""
        self.plot_widget.setTitle(
            f"<span style='color:{fg}; font-size:11pt; font-weight:bold;'>Session results: {format_number(total, show_plus=True)} BB{excluded_note}{names}</span>"
        )
        self.plot_widget.setLabel("bottom", _("Session"), **{"color": fg, "font-size": "9pt"})
        self.plot_widget.setLabel("left", _("Session result (BB)"), **{"color": fg, "font-size": "9pt"})

        axis_pen = pg.mkPen(color=grid, width=1)
        self.plot_widget.getAxis("left").setPen(axis_pen)
        self.plot_widget.getAxis("bottom").setPen(axis_pen)
        self.plot_widget.getAxis("left").setTextPen(pg.mkPen(color=fg))
        self.plot_widget.getAxis("bottom").setTextPen(pg.mkPen(color=fg))

        self.plot_widget.addLine(y=0, pen=pg.mkPen(color=grid, width=1, style=Qt.PenStyle.DashLine))

        for sid, start, end, low, high, color in zip(
            session_ids, opens, closes, lows, highs, session_colors, strict=False
        ):
            if not np.isfinite(end):
                continue
            self.plot_widget.plot([sid, sid], [low, high], pen=pg.mkPen(color=color, width=1.5))
            self.plot_widget.plot([sid, sid], [start, end], pen=pg.mkPen(color=color, width=4.0))

        valid = np.isfinite(closes)
        self.plot_widget.plot(
            session_ids[valid],
            closes[valid],
            pen=None,
            symbol="o",
            symbolSize=6,
            symbolBrush=pg.mkBrush(color=gain),
        )

        ticks = [(sid, str(int(sid))) for sid in session_ids]
        self.plot_widget.getAxis("bottom").setTicks([ticks])

        self.graphBox.layout().addWidget(self.plot_widget)

    def addTable(self, frame, results) -> None:
        colxalign, colheading = list(range(2))

        self.liststore = QStandardItemModel(0, len(self.columns))
        self.liststore.setHorizontalHeaderLabels(
            [column[colheading] for column in self.columns],
        )
        numeric_values = []
        for session in self.session_metrics:
            numeric_values.append(
                [
                    session.number,
                    session.hands,
                    session.bb_hands,
                    session.start_timestamp,
                    session.end_timestamp,
                    session.duration_seconds,
                    session.hands * 3600 / session.duration_seconds,
                    session.profit_minor,
                    session.profit_bb if session.profit_bb is not None else float("-inf"),
                    session.bb_per_100 if session.bb_per_100 is not None else float("-inf"),
                    session.all_in_ev_minor,
                    session.all_in_ev_bb if session.all_in_ev_bb is not None else float("-inf"),
                    session.ev_bb_per_100 if session.ev_bb_per_100 is not None else float("-inf"),
                    session.ev_difference_minor,
                    session.peak_minor,
                    session.low_minor,
                    session.max_drawdown_minor,
                    session.bb_per_hour if session.bb_per_hour is not None else float("-inf"),
                    session.currency_per_hour if session.currency_per_hour is not None else float("-inf"),
                ]
            )
        for row_index, row in enumerate(results):
            listrow = [QStandardItem(str(r)) for r in row]
            for item in listrow:
                item.setEditable(False)
            for item, value in zip(listrow, numeric_values[row_index], strict=True):
                item.setData(value, Qt.ItemDataRole.UserRole)
            self.liststore.appendRow(listrow)

        self.view = QTableView()
        proxy = QSortFilterProxyModel(self.view)
        proxy.setSourceModel(self.liststore)
        proxy.setSortRole(Qt.ItemDataRole.UserRole)
        self.view.setModel(proxy)
        self.view.setSortingEnabled(True)
        self.view.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        install_table_export(self.view)
        self.view.verticalHeader().hide()
        self.view.setSelectionBehavior(QTableView.SelectRows)
        frame.layout().addWidget(self.view)
        self.view.doubleClicked.connect(self.row_activated)

    def row_activated(self, index) -> None:
        model = self.view.model() if self.view is not None else None
        source_index = model.mapToSource(index) if isinstance(model, QSortFilterProxyModel) else index
        row = source_index.row()
        if 0 <= row < len(self.times):
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
            handids = list(self.times[row])
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
