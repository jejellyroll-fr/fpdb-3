"""Results calendar: cash results per day, week and month (#827).

A calendar of the month with what each day and week won, the list of days,
weeks or months of the filtered range, and the four profit curves (net, all-in
EV, showdown, non-showdown) of the period selected. Its hands open in the Hand
Viewer.

The hands are read and summed off the GUI thread (:class:`ResultsLoader`); the
sums themselves live in :mod:`period_results`, which has no Qt.

The idea, the period aggregation and the four curves come from thecrawler1's
Results viewer (thecrawler1/fpdb-3, branch ``personal``), rewritten here on
fpdb's own filters, hand viewer and graph widgets.
"""

from __future__ import annotations

import contextlib
from datetime import date
from time import time
from typing import Any

import pyqtgraph as pg
from PySide6.QtCore import QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import Database, Filters, GuiHandViewer, gui_empty_state
from fpdb_3_legacy import period_results as pr
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.localized_formats import _locale_copy, format_currency, format_date, format_number
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.ring_stats.base import DbWorker
from fpdb_3_legacy.table_export import install_table_export

log = get_logger("gui_results_viewer")

#: Role holding a cell's raw value, so the period table sorts numbers as numbers.
SORT_ROLE = Qt.ItemDataRole.UserRole + 1
#: Role holding the period (granularity, start) a calendar cell or table row stands for.
PERIOD_ROLE = Qt.ItemDataRole.UserRole + 2


class ResultsLoader(DbWorker):
    """Reads the hero's cash hands and sums them per period, off the GUI thread.

    A DbWorker, so that a superseded load is kept alive until its thread ends
    (#652); it only needs its own ``run``, which also does the sums.
    """

    loaded = Signal(object)

    def __init__(self, db: Any, query_sql: str, day_start: float) -> None:
        super().__init__(db, "periodResultsHands", query_sql)
        self.day_start = day_start

    def _fetch(self, connection: Any) -> list[Any]:
        cursor = connection.cursor()
        try:
            cursor.execute(self.query_sql)
            return list(cursor.fetchall())
        finally:
            with contextlib.suppress(Exception):
                cursor.close()

    def run(self) -> None:
        started = time()
        try:
            db = self.db_or_cursor
            acquire = getattr(db, "worker_connection", None)
            if callable(acquire):
                with acquire() as connection:
                    rows = self._fetch(connection if connection is not None else db.connection)
            else:
                rows = self._fetch(db.connection)
            results = pr.Results.build(rows, self.day_start)
        except Exception as error:  # noqa: BLE001 - Qt worker boundary reports DB-driver errors through its signal.
            log.exception("Results calendar: loading the hands failed")
            self.error.emit(str(error))
            return
        log.info(f"Results calendar: {len(results.hands)} hands loaded in {time() - started:.3f}s")
        self.loaded.emit(results)


def period_label(granularity: str, start: date) -> str:
    """How a day, week or month is named on screen."""
    if granularity == pr.WEEK:
        return _("Week of {date}").format(date=format_date(start))
    if granularity == pr.MONTH:
        return f"{_locale_copy().standaloneMonthName(start.month)} {start.year}"
    return format_date(start)


def money_text(amounts: dict[str, float]) -> str:
    """Amounts in minor units per currency, one after the other."""
    if not amounts:
        return "—"
    return " · ".join(
        format_currency(amounts[currency] / 100, currency, show_plus=True) for currency in sorted(amounts)
    )


def value_text(value: float | None, unit: str) -> str:
    if value is None:
        return "—"
    if unit == pr.UNIT_BB:
        return format_number(value, show_plus=True) + " BB"
    return format_currency(value, unit, show_plus=True)


def cell_text(value: float | None) -> str:
    """A calendar cell's result: the unit is in the month's title, the hand count in the tooltip."""
    return format_number(value, show_plus=True) if value is not None else "—"


def optional_number(value: float | None) -> str:
    return format_number(value, show_plus=True) if value is not None else "—"


class GuiResultsViewer(QSplitter):
    """The Results calendar tab."""

    def __init__(self, config: Any, querylist: Any, mainwin: Any, owner: Any, colors: dict[str, str]) -> None:
        QSplitter.__init__(self, mainwin)
        self.conf = config
        self.sql = querylist
        self.owner = owner
        self.colors = colors
        self.db = Database.Database(self.conf, sql=self.sql)

        self.results: pr.Results | None = None
        self.selected: tuple[str, date] | None = None
        self.month: tuple[int, int] = (date.today().year, date.today().month)
        self._loader: ResultsLoader | None = None
        self._generation = 0

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
            "Button1": True,
            "Button2": False,
        }
        self.filters = Filters.Filters(self.db, display=filters_display)
        self.filters.registerButton1Name(_("Refresh"))
        self.filters.registerButton1Callback(self.refresh)

        scroll = QScrollArea()
        scroll.setObjectName("filterSidebar")
        scroll.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        scroll.setWidget(self.filters)
        self.addWidget(scroll)

        self.addWidget(self._build_results_pane())
        self.setStretchFactor(0, 0)
        self.setStretchFactor(1, 1)
        self.db.rollback()

    # -- layout ---------------------------------------------------------

    def _build_results_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel(_("Period:")))
        self.granularity_box = QComboBox()
        for granularity, label in ((pr.DAY, _("Days")), (pr.WEEK, _("Weeks")), (pr.MONTH, _("Months"))):
            self.granularity_box.addItem(label, granularity)
        self.granularity_box.currentIndexChanged.connect(self._granularity_changed)
        toolbar.addWidget(self.granularity_box)

        toolbar.addWidget(QLabel(_("Unit:")))
        self.unit_box = QComboBox()
        self.unit_box.currentIndexChanged.connect(self._unit_changed)
        toolbar.addWidget(self.unit_box)

        toolbar.addStretch(1)
        self.status_label = QLabel()
        toolbar.addWidget(self.status_label)
        self.review_button = QPushButton(_("Review hands"))
        self.review_button.setToolTip(_("Open the hands of the selected period in the Hand Viewer"))
        self.review_button.setEnabled(False)
        self.review_button.clicked.connect(self.review_hands)
        toolbar.addWidget(self.review_button)
        layout.addLayout(toolbar)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.summary_label)

        vertical = QSplitter(Qt.Orientation.Vertical)
        horizontal = QSplitter(Qt.Orientation.Horizontal)
        horizontal.addWidget(self._build_calendar())
        horizontal.addWidget(self._build_period_table())
        horizontal.setStretchFactor(0, 1)
        horizontal.setStretchFactor(1, 1)
        vertical.addWidget(horizontal)

        self.graph_frame = QFrame()
        self.graph_frame.setObjectName("graphSurface")
        self.graph_frame.setStyleSheet(f"background-color: {self.colors['background']}")
        self.graph_box = QVBoxLayout(self.graph_frame)
        self.plot_widget: Any = None
        vertical.addWidget(self.graph_frame)
        vertical.setStretchFactor(0, 1)
        vertical.setStretchFactor(1, 1)
        layout.addWidget(vertical, 1)
        return pane

    def _build_calendar(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        self.previous_button = QPushButton("◀")
        self.previous_button.setToolTip(_("Previous month"))
        self.previous_button.clicked.connect(lambda: self._move_month(-1))
        self.next_button = QPushButton("▶")
        self.next_button.setToolTip(_("Next month"))
        self.next_button.clicked.connect(lambda: self._move_month(1))
        self.month_label = QLabel()
        self.month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.month_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.month_label.setToolTip(_("Click to select the whole month"))
        self.month_label.mousePressEvent = lambda _event: self._select_month()
        header.addWidget(self.previous_button)
        header.addWidget(self.month_label, 1)
        header.addWidget(self.next_button)
        layout.addLayout(header)

        self.calendar = QTableWidget(6, 8)
        locale = _locale_copy()
        weekdays = [locale.standaloneDayName(day, locale.FormatType.ShortFormat) for day in range(1, 8)]
        self.calendar.setHorizontalHeaderLabels([*weekdays, _("Week")])
        self.calendar.verticalHeader().setVisible(False)
        self.calendar.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.calendar.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.calendar.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.calendar.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.calendar.cellClicked.connect(self._calendar_clicked)
        self.calendar.cellDoubleClicked.connect(lambda _row, _column: self.review_hands())
        layout.addWidget(self.calendar, 1)
        return box

    def _build_period_table(self) -> QTableView:
        self.columns = [
            _("Period"),
            _("Hands"),
            _("Profit"),
            _("All-in EV"),
            _("Profit (BB)"),
            _("All-in EV (BB)"),
            _("BB/100"),
            _("EV BB/100"),
            _("Showdown (BB)"),
            _("Non-showdown (BB)"),
        ]
        self.model = QStandardItemModel(0, len(self.columns))
        self.model.setHorizontalHeaderLabels(self.columns)
        self.proxy = QSortFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(SORT_ROLE)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.DescendingOrder)  # the latest period first
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.clicked.connect(self._row_clicked)
        self.table.doubleClicked.connect(lambda _index: self.review_hands())
        install_table_export(self.table)
        return self.table

    # -- tab lifecycle --------------------------------------------------

    def close_owned_database(self) -> None:
        """Release the connection created for this tab."""
        with contextlib.suppress(Exception):
            self.db.disconnect()

    def shutdown_workers(self) -> None:
        """Forget a load still running, so it cannot touch a closed tab."""
        self._invalidate_loader()

    def _invalidate_loader(self) -> None:
        self._generation += 1
        loader = self._loader
        self._loader = None
        if loader is not None:
            with contextlib.suppress(Exception):
                loader.loaded.disconnect()
            with contextlib.suppress(Exception):
                loader.error.disconnect()

    # -- loading --------------------------------------------------------

    def refresh(self, _checked: Any = None) -> None:
        sites = self.filters.getSites()
        limits = self.filters.getLimits()
        games = self.filters.getGames()
        currencies = self.filters.getCurrencies()
        playerids = [pid for _site, pid in self.filters.get_selected_players()]
        missing = gui_empty_state.missing_filter_reason(
            sites=sites,
            playerids=playerids,
            limits=limits,
            games=games,
            currencies=currencies,
        )
        if missing is not None:
            self._invalidate_loader()
            self._show_results(None)
            gui_empty_state.show_no_data(self, missing, context="Results calendar", db=self.db)
            self.db.rollback()
            return

        query = self.build_query(playerids, limits, games, currencies, self.filters.getSeats())
        self._invalidate_loader()
        generation = self._generation
        loader = ResultsLoader(self.db, query, float(getattr(self.filters, "day_start", 0.0) or 0.0))
        self._loader = loader

        def loaded(results: pr.Results) -> None:
            if self._generation != generation:
                return
            self._loader = None
            self.status_label.clear()
            if not results.hands:
                self._show_results(None)
                gui_empty_state.show_no_data(self, context="Results calendar", db=self.db)
                return
            self._show_results(results)

        def failed(message: str) -> None:
            if self._generation != generation:
                return
            self._loader = None
            self.status_label.clear()
            log.error(f"Results calendar: {message}")
            self._show_results(None)
            gui_empty_state.show_no_data(self, context="Results calendar", db=self.db)

        loader.loaded.connect(loaded)
        loader.error.connect(failed)
        self.status_label.setText(_("Loading…"))
        loader.start()

    def build_query(
        self,
        playerids: list[int],
        limits: Any,
        games: list[str],
        currencies: list[str],
        seats: dict[str, int] | None,
    ) -> str:
        query = self.sql.query["periodResultsHands"]
        start_date, end_date = self.filters.getDates()
        players = ", ".join(str(int(pid)) for pid in playerids)
        query = query.replace("<player_test>", f"({players})")
        query = query.replace("<startdate_test>", start_date)
        query = query.replace("<enddate_test>", end_date)
        query = query.replace("<limit_test>", self.filters.get_limits_where_clause(limits))
        if self.filters.display.get("Games"):
            if games:
                quoted = ", ".join("'" + str(game).replace("'", "''") + "'" for game in games)
                query = query.replace("<game_test>", f"AND gt.category in ({quoted})")
            else:
                query = query.replace("<game_test>", "AND gt.category IS NULL")
        else:
            query = query.replace("<game_test>", "")
        if currencies:
            quoted = ", ".join("'" + str(currency).replace("'", "''") + "'" for currency in currencies)
            query = query.replace("<currency_test>", f"AND gt.currency in ({quoted})")
        else:
            query = query.replace("<currency_test>", "AND 1=0")
        if seats:
            seats_test = f"AND h.seats BETWEEN {int(seats['from'])} AND {int(seats['to'])}"
        else:
            seats_test = ""
        return query.replace("<seats_test>", seats_test)

    # -- display --------------------------------------------------------

    @property
    def granularity(self) -> str:
        return self.granularity_box.currentData() or pr.DAY

    @property
    def unit(self) -> str:
        return self.unit_box.currentData() or pr.UNIT_BB

    def _show_results(self, results: pr.Results | None) -> None:
        self.results = results
        self.selected = None
        previous_unit = self.unit_box.currentData()
        self.unit_box.blockSignals(True)
        self.unit_box.clear()
        if results is not None:
            for unit in pr.display_units(results.hands):
                self.unit_box.addItem(_("Big blinds") if unit == pr.UNIT_BB else unit, unit)
            index = self.unit_box.findData(previous_unit)
            self.unit_box.setCurrentIndex(max(index, 0))
            last = results.last_day()
            if last is not None:
                self.month = (last.year, last.month)
        self.unit_box.blockSignals(False)
        self._redraw()

    def _redraw(self) -> None:
        self._fill_summary()
        self._fill_calendar()
        self._fill_table()
        self._draw_curves()
        self.review_button.setEnabled(self.results is not None and bool(self._selected_hands()))

    def _granularity_changed(self, _index: int) -> None:
        # The selection keeps its meaning (a day stays a day); the table lists other periods.
        self._fill_table()

    def _unit_changed(self, _index: int) -> None:
        self._redraw()

    def _fill_summary(self) -> None:
        results = self.results
        overall = pr.total(results.periods[pr.DAY]) if results is not None else None
        if overall is None:
            self.summary_label.clear()
            return
        days = results.periods[pr.DAY]
        winning = sum(1 for day in days if day.profit_bb > 0)
        text = _(
            "Hands: {hands} · Profit: {profit} · All-in EV: {ev} · BB/100: {bb100} · EV BB/100: {ev100} · "
            "Days played: {days} ({winning} winning)"
        ).format(
            hands=format_number(overall.hands, 0),
            profit=money_text(overall.profit_minor) + " / " + optional_number(overall.profit_bb) + " BB",
            ev=money_text(overall.all_in_ev_minor) + " / " + optional_number(overall.all_in_ev_bb) + " BB",
            bb100=optional_number(overall.bb_per_100),
            ev100=optional_number(overall.ev_bb_per_100),
            days=format_number(len(days), 0),
            winning=format_number(winning, 0),
        )
        self.summary_label.setText(text)

    def _tint(self, value: float | None) -> QBrush | None:
        if value is None or value == 0:
            return None
        color = QColor(self.colors.get("line_up" if value > 0 else "line_down", "#22c55e" if value > 0 else "#f43f5e"))
        if not color.isValid():
            color = QColor("#22c55e" if value > 0 else "#f43f5e")
        color.setAlpha(70)
        return QBrush(color)

    def _fill_calendar(self) -> None:
        year, month = self.month
        locale = _locale_copy()
        title = f"{locale.standaloneMonthName(month)} {year}"
        self.calendar.clearContents()
        self.calendar.clearSelection()
        results = self.results
        unit = self.unit
        days = results.by_start(pr.DAY) if results is not None else {}
        weeks = results.by_start(pr.WEEK) if results is not None else {}
        months = results.by_start(pr.MONTH) if results is not None else {}
        month_result = months.get(date(year, month, 1))
        if month_result is not None:
            title += "  " + value_text(pr.period_value(month_result, unit), unit)
        self.month_label.setText(f"<b>{title}</b>")

        grid = pr.month_weeks(year, month)
        self.calendar.setRowCount(len(grid))
        for row, week in enumerate(grid):
            for column, day in enumerate(week):
                period = days.get(day)
                value = pr.period_value(period, unit) if period is not None else None
                text = str(day.day)
                if period is not None:
                    text += "\n" + cell_text(value)
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setData(PERIOD_ROLE, (pr.DAY, day))
                if day.month != month:
                    item.setForeground(QBrush(QColor(self.colors.get("grid", "#888888"))))
                brush = self._tint(value)
                if brush is not None:
                    item.setBackground(brush)
                if period is not None:
                    item.setToolTip(self._period_tooltip(period))
                self.calendar.setItem(row, column, item)
            week_start = week[0]
            week_period = weeks.get(week_start)
            week_value = pr.period_value(week_period, unit) if week_period is not None else None
            item = QTableWidgetItem(cell_text(week_value) if week_period is not None else "")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setData(PERIOD_ROLE, (pr.WEEK, week_start))
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            brush = self._tint(week_value)
            if brush is not None:
                item.setBackground(brush)
            if week_period is not None:
                item.setToolTip(self._period_tooltip(week_period))
            self.calendar.setItem(row, 7, item)

    def _period_tooltip(self, period: pr.PeriodResult) -> str:
        return "\n".join(
            [
                period_label(period.granularity, period.start),
                _("{hands} hands").format(hands=format_number(period.hands, 0)),
                _("Profit: {profit}").format(profit=money_text(period.profit_minor)),
                _("All-in EV: {ev}").format(ev=money_text(period.all_in_ev_minor)),
                _("BB/100: {bb100}").format(bb100=optional_number(period.bb_per_100)),
            ],
        )

    @staticmethod
    def _cell(text: str, sort_value: Any) -> QStandardItem:
        item = QStandardItem(text)
        item.setData(sort_value, SORT_ROLE)
        item.setEditable(False)
        return item

    def _fill_table(self) -> None:
        self.table.setSortingEnabled(False)
        self.model.removeRows(0, self.model.rowCount())
        if self.results is None:
            self.table.setSortingEnabled(True)
            return
        granularity = self.granularity
        unit = self.unit
        for period in self.results.periods[granularity]:
            money_currency = unit if unit != pr.UNIT_BB else None
            profit_sort = period.money(money_currency) if money_currency else period.profit_bb
            ev_sort = period.all_in_ev_minor.get(money_currency, 0.0) if money_currency else period.all_in_ev_bb
            row = [
                self._cell(period_label(granularity, period.start), period.start.toordinal()),
                self._cell(format_number(period.hands, 0), period.hands),
                self._cell(money_text(period.profit_minor), profit_sort),
                self._cell(money_text(period.all_in_ev_minor), ev_sort),
                self._cell(optional_number(period.profit_bb if period.bb_hands else None), period.profit_bb),
                self._cell(optional_number(period.all_in_ev_bb if period.bb_hands else None), period.all_in_ev_bb),
                self._cell(optional_number(period.bb_per_100), period.bb_per_100 or 0.0),
                self._cell(optional_number(period.ev_bb_per_100), period.ev_bb_per_100 or 0.0),
                self._cell(optional_number(period.showdown_bb if period.bb_hands else None), period.showdown_bb),
                self._cell(
                    optional_number(period.nonshowdown_bb if period.bb_hands else None),
                    period.nonshowdown_bb,
                ),
            ]
            row[0].setData((granularity, period.start), PERIOD_ROLE)
            brush = self._tint(pr.period_value(period, unit))
            if brush is not None:
                row[2].setBackground(brush)
                row[4].setBackground(brush)
            self.model.appendRow(row)
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()

    # -- selection ------------------------------------------------------

    def _move_month(self, step: int) -> None:
        self.month = pr.shift_month(*self.month, step)
        self._fill_calendar()

    def _select(self, granularity: str, start: date) -> None:
        self.selected = (granularity, start)
        if granularity != pr.WEEK:
            self.month = (start.year, start.month)
            self._fill_calendar()
        self._draw_curves()
        self.review_button.setEnabled(bool(self._selected_hands()))

    def _select_month(self) -> None:
        year, month = self.month
        self._select(pr.MONTH, date(year, month, 1))

    def _calendar_clicked(self, row: int, column: int) -> None:
        item = self.calendar.item(row, column)
        period = item.data(PERIOD_ROLE) if item is not None else None
        if period:
            granularity, start = period
            self.selected = (granularity, start)
            self._draw_curves()
            self.review_button.setEnabled(bool(self._selected_hands()))

    def _row_clicked(self, index: Any) -> None:
        source = self.proxy.mapToSource(index)
        period = self.model.item(source.row(), 0).data(PERIOD_ROLE)
        if period:
            self._select(*period)

    def _selected_hands(self) -> list[pr.HandResult]:
        results = self.results
        if results is None:
            return []
        if self.selected is None:
            return list(results.hands)
        granularity, start = self.selected
        return results.hands_between(start, pr.period_end(start, granularity))

    def _selection_title(self) -> str:
        if self.selected is None:
            return _("All hands of the filtered dates")
        return period_label(*self.selected)

    # -- curves ---------------------------------------------------------

    def _clear_plot(self) -> None:
        if self.plot_widget is not None:
            with contextlib.suppress(Exception):
                self.graph_box.removeWidget(self.plot_widget)
                self.plot_widget.setParent(None)
            self.plot_widget = None

    def _draw_curves(self) -> None:
        self._clear_plot()
        hands = self._selected_hands()
        if not hands:
            return
        unit = self.unit
        curves = pr.build_curves(hands, unit)
        if not curves.hands:
            return
        background = self.colors["background"]
        foreground = self.colors["foreground"]
        self.graph_frame.setStyleSheet(f"background-color: {background}")

        plot = pg.PlotWidget()
        plot.setBackground(background)
        plot.showGrid(x=True, y=True, alpha=0.3)
        plot.setTitle(
            f"<span style='color:{foreground}; font-size:11pt; font-weight:bold;'>{self._selection_title()}</span>",
        )
        plot.setLabel("bottom", _("Hands"), color=foreground)
        plot.setLabel("left", _("Big blinds") if unit == pr.UNIT_BB else unit, color=foreground)
        plot.getAxis("left").setTextPen(pg.mkPen(color=foreground))
        plot.getAxis("bottom").setTextPen(pg.mkPen(color=foreground))
        plot.addLegend(offset=(10, 10), labelTextColor=foreground)
        plot.addLine(y=0, pen=pg.mkPen(color=self.colors.get("grid", "#94a3b8"), style=Qt.PenStyle.DashLine))

        styles = {
            "nonshowdown": (_("Non-showdown"), "line_nonshowdown", "#f43f5e", Qt.PenStyle.SolidLine, 1.8),
            "showdown": (_("Showdown"), "line_showdown", "#00a2ff", Qt.PenStyle.SolidLine, 1.8),
            "ev": (_("All-in EV"), "line_ev", "#ff9f43", Qt.PenStyle.DashLine, 1.8),
            "net": (_("Net profit"), "line_hands", "#22c55e", Qt.PenStyle.SolidLine, 2.5),
        }
        for name, (label, key, fallback, style, width) in styles.items():
            color = QColor(self.colors.get(key, fallback))
            if not color.isValid():
                color = QColor(fallback)
            plot.plot(
                list(getattr(curves, name)),
                pen=pg.mkPen(color=color, width=width, style=style),
                name=f"{label}: {value_text(curves.final(name), unit)}",
            )
        self.plot_widget = plot
        self.graph_box.addWidget(plot)

    # -- hand review ----------------------------------------------------

    def review_hands(self) -> None:
        """Open the selected period's hands in the Hand Viewer."""
        hand_ids = [hand.hand_id for hand in self._selected_hands()]
        if not hand_ids:
            return
        viewer = self._hand_viewer()
        if viewer is not None:
            viewer.reload_hands(hand_ids)

    def _hand_viewer(self) -> Any:
        threads = getattr(self.owner, "threads", None)
        open_viewer = getattr(self.owner, "tab_hand_viewer", None)
        if threads is None or not callable(open_viewer):
            return None
        for tab in threads:
            if isinstance(tab, GuiHandViewer.GuiHandViewer):
                notebook = getattr(self.owner, "nb", None)
                if notebook is not None:
                    with contextlib.suppress(Exception):
                        notebook.setCurrentWidget(tab)
                return tab
        open_viewer(None)
        for tab in threads:
            if isinstance(tab, GuiHandViewer.GuiHandViewer):
                return tab
        return None
