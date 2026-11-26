"""Results calendar: cash results per day, week, month and year (#827).

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
from decimal import Decimal
from time import time
from typing import Any

import pyqtgraph as pg
from PySide6.QtCore import QDate, QModelIndex, QSignalBlocker, QSortFilterProxyModel, Qt, Signal
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

log = get_logger("results_calendar")

#: Role holding a cell's raw value, so the period table sorts numbers as numbers.
SORT_ROLE = Qt.ItemDataRole.UserRole + 1
#: Role holding the period (granularity, start) a calendar cell or table row stands for.
PERIOD_ROLE = Qt.ItemDataRole.UserRole + 2


class _ResultsSortProxyModel(QSortFilterProxyModel):
    """Sort decimal cells numerically without converting them to floats."""

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:  # noqa: N802  # pylint: disable=invalid-name
        left_value = left.data(self.sortRole())
        right_value = right.data(self.sortRole())
        if isinstance(left_value, tuple) and isinstance(right_value, tuple):
            return left_value < right_value
        if isinstance(left_value, Decimal) or isinstance(right_value, Decimal):
            left_decimal = left_value if isinstance(left_value, Decimal) else Decimal(str(left_value))
            right_decimal = right_value if isinstance(right_value, Decimal) else Decimal(str(right_value))
            return left_decimal < right_decimal
        return super().lessThan(left, right)


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
            results = pr.build_results(rows, self.day_start)
        # Every DB driver raises its own errors: the worker reports any of them through its signal.
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            log.exception("Results calendar: loading the hands failed")
            self.error.emit(str(error))
            return
        log.info(f"Results calendar: {len(results.hands)} hands loaded in {time() - started:.3f}s")
        self.loaded.emit(results)


def period_label(granularity: str, start: date) -> str:
    """How a day, week, month or year is named on screen."""
    if granularity == pr.WEEK:
        return _("Week of {date}").format(date=format_date(start))
    if granularity == pr.MONTH:
        return f"{_locale_copy().standaloneMonthName(start.month)} {start.year}"
    if granularity == pr.YEAR:
        return str(start.year)
    return format_date(start)


def money_text(amounts: dict[str, Decimal]) -> str:
    """Amounts in minor units per currency, one after the other."""
    if not amounts:
        return "—"
    return " · ".join(
        format_currency(amounts[currency] / 100, currency, show_plus=True) for currency in sorted(amounts)
    )


def value_text(value: Decimal | float | None, unit: str) -> str:
    """A result in big blinds or in a currency, with its unit."""
    if value is None:
        return "—"
    if unit == pr.UNIT_BB:
        return format_number(value, show_plus=True) + " BB"
    return format_currency(value, unit, show_plus=True)


def optional_number(value: Decimal | float | None) -> str:
    """A signed number, or a dash when there is none (the calendar cells' unit is in the month's title)."""
    return format_number(value, show_plus=True) if value is not None else "—"


def quoted_list(values: list[str]) -> str:
    """SQL text literals for an ``IN`` list, quotes doubled."""
    return ", ".join("'" + str(value).replace("'", "''") + "'" for value in values)


def table_cell(text: str, sort_value: Any) -> QStandardItem:
    """A read-only cell of the period table, sorted by ``sort_value``."""
    item = QStandardItem(text)
    item.setData(sort_value, SORT_ROLE)
    item.setEditable(False)
    return item


def period_row(period: pr.PeriodResult) -> list[QStandardItem]:
    """The period table's cells for one day, week, month or year."""
    with_bb = period.bb_hands > 0
    # Money sorts by currency and then its exact amount, since amounts in
    # different currencies have no common numeric order without exchange rates.
    profit_sort = tuple(sorted(period.profit_minor.items()))
    ev_sort = tuple(sorted(period.all_in_ev_minor.items()))
    row = [
        table_cell(period_label(period.granularity, period.start), period.start.toordinal()),
        table_cell(format_number(period.hands, 0), period.hands),
        table_cell(money_text(period.profit_minor), profit_sort),
        table_cell(money_text(period.all_in_ev_minor), ev_sort),
        table_cell(optional_number(period.profit_bb if with_bb else None), period.profit_bb),
        table_cell(optional_number(period.all_in_ev_bb if with_bb else None), period.all_in_ev_bb),
        table_cell(optional_number(period.bb_per_100), period.bb_per_100 or Decimal(0)),
        table_cell(optional_number(period.ev_bb_per_100), period.ev_bb_per_100 or Decimal(0)),
        table_cell(format_number(period.vpip_percent) if period.vpip_percent is not None else "—", period.vpip_percent or 0.0),
        table_cell(format_number(period.pfr_percent) if period.pfr_percent is not None else "—", period.pfr_percent or 0.0),
        table_cell(optional_number(period.showdown_bb if with_bb else None), period.showdown_bb),
        table_cell(optional_number(period.nonshowdown_bb if with_bb else None), period.nonshowdown_bb),
    ]
    row[0].setData((period.granularity, period.start), PERIOD_ROLE)
    return row


def period_tooltip(period: pr.PeriodResult) -> str:
    """What a calendar cell tells on hover."""
    return "\n".join(
        [
            period_label(period.granularity, period.start),
            _("{hands} hands").format(hands=format_number(period.hands, 0)),
            _("Profit: {profit}").format(profit=money_text(period.profit_minor)),
            _("All-in EV: {ev}").format(ev=money_text(period.all_in_ev_minor)),
            _("BB/100: {bb100}").format(bb100=optional_number(period.bb_per_100)),
        ],
    )


def make_calendar() -> QTableWidget:
    """A month grid: seven days and the week's result."""
    calendar = QTableWidget(6, 8)
    locale = _locale_copy()
    weekdays = [locale.standaloneDayName(day, locale.FormatType.ShortFormat) for day in range(1, 8)]
    calendar.setHorizontalHeaderLabels([*weekdays, _("Week")])
    calendar.verticalHeader().setVisible(False)
    calendar.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    calendar.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    calendar.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    calendar.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    return calendar


def make_period_table(model: QStandardItemModel, proxy: QSortFilterProxyModel) -> QTableView:
    """The sortable, exportable list of days, weeks, months or years."""
    model.setHorizontalHeaderLabels(
        [
            _("Period"),
            _("Hands"),
            _("Profit"),
            _("All-in EV"),
            _("Profit (BB)"),
            _("All-in EV (BB)"),
            _("BB/100"),
            _("EV BB/100"),
            _("VPIP %"),
            _("PFR %"),
            _("Showdown (BB)"),
            _("Non-showdown (BB)"),
        ],
    )
    proxy.setSourceModel(model)
    proxy.setSortRole(SORT_ROLE)
    table = QTableView()
    table.setModel(proxy)
    table.setSortingEnabled(True)
    table.sortByColumn(0, Qt.SortOrder.DescendingOrder)  # the latest period first
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    install_table_export(table)
    return table


def summary_text(days: tuple[pr.PeriodResult, ...], unit: str) -> str:
    """The line above the calendar: every day of the load put together."""
    overall = pr.total(days)
    if overall is None:
        return ""
    with_bb = overall.bb_hands > 0
    profit_bb = value_text(overall.profit_bb if with_bb else None, pr.UNIT_BB)
    ev_bb = value_text(overall.all_in_ev_bb if with_bb else None, pr.UNIT_BB)
    winning = sum(1 for day in days if (pr.period_value(day, unit) or 0) > 0)
    return _(
        "Hands: {hands} · Profit: {profit} · All-in EV: {ev} · BB/100: {bb100} · EV BB/100: {ev100} · "
        "Days played: {days} ({winning} winning)"
    ).format(
        hands=format_number(overall.hands, 0),
        profit=f"{money_text(overall.profit_minor)} / {profit_bb}",
        ev=f"{money_text(overall.all_in_ev_minor)} / {ev_bb}",
        bb100=optional_number(overall.bb_per_100),
        ev100=optional_number(overall.ev_bb_per_100),
        days=format_number(len(days), 0),
        winning=format_number(winning, 0),
    )


FILTERS_DISPLAY = {
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


class ResultsCalendar(QSplitter):  # pylint: disable=too-many-instance-attributes
    """The Results calendar tab."""

    def __init__(self, config: Any, querylist: Any, owner: Any, colors: dict[str, str]) -> None:
        QSplitter.__init__(self)  # the main window's tab widget takes it
        self.conf = config
        self.sql = querylist
        self.owner = owner
        self.colors = colors
        self.db = Database.Database(self.conf, sql=self.sql)

        self.results: pr.Results | None = None
        self.player_names: dict[int, str] = {}  # the loaded hands' heroes, by player id
        self.selected: tuple[str, date] | None = None
        self.month: tuple[int, int] = (date.today().year, date.today().month)
        self._loader: ResultsLoader | None = None
        self._generation = 0

        self.filters = Filters.Filters(self.db, display=FILTERS_DISPLAY)
        self.filters.registerButton1Name(_("Refresh"))
        self.filters.registerButton1Callback(self.refresh)

        self.granularity_box = QComboBox()
        self.unit_box = QComboBox()
        self.status_label = QLabel()
        self.review_button = QPushButton(_("Review hands"))
        self.summary_label = QLabel()
        self.month_button = QPushButton()
        self.this_year_button = QPushButton(_("This year"))
        self._navigation_buttons = (QPushButton("◀"), QPushButton("▶"))
        self.calendar = make_calendar()
        self.model = QStandardItemModel(0, 12)
        self.proxy = _ResultsSortProxyModel()
        self.table = make_period_table(self.model, self.proxy)
        self.graph_frame = QFrame()
        self.graph_box = QVBoxLayout(self.graph_frame)
        self.plot_widget: Any = None

        scroll = QScrollArea()
        scroll.setObjectName("filterSidebar")
        scroll.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        scroll.setWidget(self.filters)
        self.addWidget(scroll)
        self.addWidget(self._build_results_pane())
        self.setStretchFactor(0, 0)
        self.setStretchFactor(1, 1)
        self._connect_signals()
        self._update_navigation()
        self.db.rollback()

    # -- layout ---------------------------------------------------------

    def _build_results_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel(_("Period:")))
        for granularity, label in (
            (pr.DAY, _("Days")),
            (pr.WEEK, _("Weeks")),
            (pr.MONTH, _("Months")),
            (pr.YEAR, _("Years")),
        ):
            self.granularity_box.addItem(label, granularity)
        toolbar.addWidget(self.granularity_box)
        self.this_year_button.clicked.connect(self.select_this_year)
        toolbar.addWidget(self.this_year_button)
        toolbar.addWidget(QLabel(_("Unit:")))
        toolbar.addWidget(self.unit_box)
        toolbar.addStretch(1)
        toolbar.addWidget(self.status_label)
        self.review_button.setToolTip(_("Open the hands of the selected period in the Hand Viewer"))
        self.review_button.setEnabled(False)
        toolbar.addWidget(self.review_button)
        layout.addLayout(toolbar)

        self.summary_label.setWordWrap(True)
        self.summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.summary_label)

        vertical = QSplitter(Qt.Orientation.Vertical)
        horizontal = QSplitter(Qt.Orientation.Horizontal)
        horizontal.addWidget(self._build_calendar())
        horizontal.addWidget(self.table)
        horizontal.setStretchFactor(0, 1)
        horizontal.setStretchFactor(1, 1)
        vertical.addWidget(horizontal)

        self.graph_frame.setObjectName("graphSurface")
        self.graph_frame.setStyleSheet(f"background-color: {self.colors['background']}")
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
        previous_button, next_button = self._navigation_buttons
        previous_button.clicked.connect(lambda: self.move_period(-1))
        next_button.clicked.connect(lambda: self.move_period(1))
        self.month_button.setFlat(True)
        self.month_button.setToolTip(_("Click to select the whole month"))
        header.addWidget(previous_button)
        header.addWidget(self.month_button, 1)
        header.addWidget(next_button)
        layout.addLayout(header)
        layout.addWidget(self.calendar, 1)
        return box

    def _connect_signals(self) -> None:
        self.granularity_box.currentIndexChanged.connect(self._granularity_changed)
        self.unit_box.currentIndexChanged.connect(self._unit_changed)
        self.review_button.clicked.connect(self.review_hands)
        self.month_button.clicked.connect(self.select_month)
        # The current cell or row, not just a click: the arrow keys move it too.
        self.calendar.cellClicked.connect(self.select_cell)
        self.calendar.currentCellChanged.connect(lambda row, column, _row, _column: self.select_cell(row, column))
        self.calendar.cellDoubleClicked.connect(lambda _row, _column: self.review_hands())
        self.table.clicked.connect(self.select_row)
        self.table.selectionModel().currentRowChanged.connect(lambda current, _previous: self.select_row(current))
        self.table.doubleClicked.connect(lambda _index: self.review_hands())

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
        """Load the hands of the filters' selection, off the GUI thread."""
        playerids = [pid for _site, pid in self.filters.get_selected_players()]
        missing = gui_empty_state.missing_filter_reason(
            sites=self.filters.getSites(),
            playerids=playerids,
            limits=self.filters.getLimits(),
            games=self.filters.getGames(),
            currencies=self.filters.getCurrencies(),
        )
        self._invalidate_loader()
        if missing is not None:
            self._show_nothing(missing)
            self.db.rollback()
            return

        generation = self._generation
        names = self._player_names(playerids)
        loader = ResultsLoader(self.db, self.build_query(playerids), float(getattr(self.filters, "day_start", 0) or 0))
        self._loader = loader
        loader.loaded.connect(lambda results: self._loaded(generation, results, names))
        loader.error.connect(lambda message: self._failed(generation, message))
        self.status_label.setText(_("Loading…"))
        loader.start()

    def _player_names(self, playerids: list[int]) -> dict[int, str]:
        """The screen name of each player whose hands are loaded, for the Hand Viewer."""
        names = {pid: self.db.get_player_name_by_id(pid) for pid in playerids}
        self.db.rollback()
        return {pid: name for pid, name in names.items() if name}

    def _loaded(self, generation: int, results: pr.Results, names: dict[int, str] | None = None) -> None:
        if generation != self._generation:
            return  # superseded by a newer Refresh
        self._loader = None
        self.player_names = dict(names or {})
        self.status_label.clear()
        if results.hands:
            self.show_results(results)
        else:
            self._show_nothing()

    def _failed(self, generation: int, message: str) -> None:
        if generation != self._generation:
            return
        self._loader = None
        self.status_label.clear()
        log.error(f"Results calendar: {message}")
        self._show_nothing()

    def _show_nothing(self, reason: gui_empty_state.NoDataReason = gui_empty_state.NoDataReason.NO_ROWS) -> None:
        self.show_results(None)
        gui_empty_state.show_no_data(self, reason, context="Results calendar", db=self.db)

    def build_query(self, playerids: list[int]) -> str:
        """The ``periodResultsHands`` query for ``playerids`` and the rest of the filters' selection."""
        games = self.filters.getGames()
        currencies = self.filters.getCurrencies()
        seats = self.filters.getSeats()
        start_date, end_date = self.filters.getDates()
        if not self.filters.display.get("Games"):
            game_test = ""
        elif games:
            game_test = f"AND gt.category in ({quoted_list(games)})"
        else:
            game_test = "AND gt.category IS NULL"
        # An empty currency list would be "in ()", invalid SQL: match no hand instead.
        currency_test = f"AND gt.currency in ({quoted_list(currencies)})" if currencies else "AND 1=0"
        seats_test = f"AND h.seats BETWEEN {int(seats['from'])} AND {int(seats['to'])}" if seats else ""
        replacements = {
            "<player_test>": "(" + ", ".join(str(int(pid)) for pid in playerids) + ")",
            "<startdate_test>": start_date,
            "<enddate_test>": end_date,
            "<limit_test>": self.filters.get_limits_where_clause(self.filters.getLimits()),
            "<game_test>": game_test,
            "<currency_test>": currency_test,
            "<seats_test>": seats_test,
        }
        query = self.sql.query["periodResultsHands"]
        for placeholder, value in replacements.items():
            query = query.replace(placeholder, value)
        return query

    # -- display --------------------------------------------------------

    @property
    def granularity(self) -> str:
        """The periods the table lists: day, week, month or year."""
        return self.granularity_box.currentData() or pr.DAY

    @property
    def unit(self) -> str:
        """BB, or the currency the calendar and the curves are shown in."""
        return self.unit_box.currentData() or pr.UNIT_BB

    def show_results(self, results: pr.Results | None) -> None:
        """Show a load's results, or clear the tab with None."""
        self.results = results
        self.selected = None
        previous_unit = self.unit_box.currentData()
        self.unit_box.blockSignals(True)
        self.unit_box.clear()
        if results is not None:
            for unit in pr.display_units(results.hands):
                self.unit_box.addItem(_("Big blinds") if unit == pr.UNIT_BB else unit, unit)
            self.unit_box.setCurrentIndex(max(self.unit_box.findData(previous_unit), 0))
            last = results.last_day()
            if last is not None:
                self.month = (last.year, last.month)
        self.unit_box.blockSignals(False)
        self._redraw()

    def _redraw(self) -> None:
        self._fill_summary()
        self._fill_calendar()
        self._fill_table()
        self._selection_changed()

    def _granularity_changed(self, _index: int) -> None:
        # The selection keeps its meaning (a day stays a day); the table lists other periods.
        self._update_navigation()
        self._fill_calendar()
        self._fill_table()

    def _update_navigation(self) -> None:
        is_year = self.granularity == pr.YEAR
        for button, step in zip(self._navigation_buttons, (-1, 1), strict=True):
            if is_year:
                tooltip = _("Previous year") if step < 0 else _("Next year")
            else:
                tooltip = _("Previous month") if step < 0 else _("Next month")
            button.setToolTip(tooltip)
        self.month_button.setToolTip(
            _("Click to select this year") if is_year else _("Click to select the whole month"),
        )
        self.this_year_button.setVisible(is_year)

    def _unit_changed(self, _index: int) -> None:
        self._redraw()

    def _fill_summary(self) -> None:
        if self.results is None:
            self.summary_label.clear()
            return
        self.summary_label.setText(summary_text(self.results.periods[pr.DAY], self.unit))

    def _tint(self, value: Decimal | float | None) -> QBrush | None:
        """A pale green for a win, a pale red for a loss, nothing for zero."""
        if not value:
            return None
        key, fallback = ("line_up", "#22c55e") if value > 0 else ("line_down", "#f43f5e")
        color = QColor(self.colors.get(key, fallback))
        if not color.isValid():
            color = QColor(fallback)
        color.setAlpha(70)
        return QBrush(color)

    def _calendar_item(self, text: str, period: pr.PeriodResult | None, key: tuple[str, date]) -> QTableWidgetItem:
        """A calendar cell for ``key``, tinted by its result when ``period`` was played."""
        value = pr.period_value(period, self.unit) if period is not None else None
        item = QTableWidgetItem(text if period is None else f"{text}\n{optional_number(value)}".strip())
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setData(PERIOD_ROLE, key)
        brush = self._tint(value)
        if brush is not None:
            item.setBackground(brush)
        if period is not None:
            item.setToolTip(period_tooltip(period))
        return item

    def _fill_calendar(self) -> None:
        year, month = self.month
        results = self.results
        days = results.by_start(pr.DAY) if results is not None else {}
        weeks = results.by_start(pr.WEEK) if results is not None else {}
        month_result = results.by_start(pr.MONTH).get(date(year, month, 1)) if results is not None else None
        if self.granularity == pr.YEAR:
            year_result = results.by_start(pr.YEAR).get(date(year, 1, 1)) if results is not None else None
            title = str(year)
            if year_result is not None:
                title += "  " + value_text(pr.period_value(year_result, self.unit), self.unit)
        else:
            title = f"{_locale_copy().standaloneMonthName(month)} {year}"
            if month_result is not None:
                title += "  " + value_text(pr.period_value(month_result, self.unit), self.unit)
        self.month_button.setText(title)

        # Refilling moves no one's selection: the current cell's signals stay quiet meanwhile.
        blocker = QSignalBlocker(self.calendar)
        self.calendar.clearContents()
        self.calendar.clearSelection()
        grid = pr.month_weeks(year, month)
        self.calendar.setRowCount(len(grid))
        outside = QBrush(QColor(self.colors.get("grid", "#888888")))
        for row, week in enumerate(grid):
            for column, day in enumerate(week):
                item = self._calendar_item(str(day.day), days.get(day), (pr.DAY, day))
                if day.month != month:
                    item.setForeground(outside)
                self.calendar.setItem(row, column, item)
            item = self._calendar_item("", weeks.get(week[0]), (pr.WEEK, week[0]))
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            self.calendar.setItem(row, 7, item)
        blocker.unblock()

    def _fill_table(self) -> None:
        blocker = QSignalBlocker(self.table.selectionModel())  # a refill is not a selection
        self.table.setSortingEnabled(False)
        self.model.removeRows(0, self.model.rowCount())
        periods = self.results.periods[self.granularity] if self.results is not None else ()
        for period in periods:
            row = period_row(period)
            brush = self._tint(pr.period_value(period, self.unit))
            if brush is not None:
                row[2].setBackground(brush)
                row[4].setBackground(brush)
            self.model.appendRow(row)
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        blocker.unblock()

    # -- selection ------------------------------------------------------

    def move_month(self, step: int) -> None:
        """Show the month ``step`` months away in the calendar."""
        self.month = pr.shift_month(*self.month, step)
        self._fill_calendar()

    def move_period(self, step: int) -> None:
        """Move the calendar one month, or one year in yearly grouping."""
        if self.granularity == pr.YEAR:
            self.month = (self.month[0] + step, self.month[1])
            self._fill_calendar()
            return
        self.move_month(step)

    def select_period(self, granularity: str, start: date) -> None:
        """Select a day, week, month or year for curves and hand review."""
        self.selected = (granularity, start)
        target_month = (start.year, 1) if granularity == pr.YEAR else (start.year, start.month)
        if granularity != pr.WEEK and target_month != self.month:
            self.month = target_month
            self._fill_calendar()
        self._selection_changed()

    def select_month(self) -> None:
        """Select the year in yearly mode, otherwise the shown month."""
        year, month = self.month
        if self.granularity == pr.YEAR:
            self.select_period(pr.YEAR, date(year, 1, 1))
        else:
            self.select_period(pr.MONTH, date(year, month, 1))

    def select_this_year(self) -> None:
        """Set the date filter to this calendar year and reload the results."""
        year = date.today().year
        self.filters.start_date.setDate(QDate(year, 1, 1))
        self.filters.end_date.setDate(QDate(year, 12, 31))
        self.month = (year, 1)
        self.refresh()

    def select_cell(self, row: int, column: int) -> None:
        """Select the day or week of a calendar cell."""
        item = self.calendar.item(row, column)
        period = item.data(PERIOD_ROLE) if item is not None else None
        if period:
            granularity, start = period
            self.selected = (granularity, start)
            self._selection_changed()

    def select_row(self, index: Any) -> None:
        """Select the period of a row of the table."""
        if not index.isValid():
            return
        item = self.model.item(self.proxy.mapToSource(index).row(), 0)
        period = item.data(PERIOD_ROLE) if item is not None else None
        if period:
            self.select_period(*period)

    def _selection_changed(self) -> None:
        self._draw_curves()
        self.review_button.setEnabled(bool(self.selected_hands()))

    def selected_hands(self) -> list[pr.HandResult]:
        """The selected period's hands, or every hand when nothing is selected."""
        if self.results is None:
            return []
        if self.selected is None:
            return list(self.results.hands)
        granularity, start = self.selected
        return self.results.hands_between(start, pr.period_end(start, granularity))

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
        hands = self.selected_hands()
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
                [float(value) for value in getattr(curves, name)],
                pen=pg.mkPen(color=color, width=width, style=style),
                name=f"{label}: {value_text(float(curves.final(name)), unit)}",
            )
        self.plot_widget = plot
        self.graph_box.addWidget(plot)

    # -- hand review ----------------------------------------------------

    def review_hands(self) -> None:
        """Open the selected period's hands in the Hand Viewer, each with its hero."""
        hands = self.selected_hands()
        if not hands:
            return
        viewer = self._hand_viewer()
        if viewer is not None:
            viewer.reload_hands([hand.hand_id for hand in hands], heroes=self.hand_heroes(hands))

    def hand_heroes(self, hands: list[pr.HandResult]) -> dict[int, str]:
        """Each hand's hero by hand id: the player the hand was loaded for, on that hand's site."""
        heroes = {}
        for hand in hands:
            name = self.player_names.get(hand.player_id) if hand.player_id is not None else None
            if name:
                heroes[hand.hand_id] = name
        return heroes

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
