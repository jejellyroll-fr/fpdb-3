"""The Results calendar tab (#827): calendar, period table, curves, hand review, loading off the GUI thread."""

from __future__ import annotations

import contextlib
import sqlite3
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import pytz

from fpdb_3_legacy import GuiResultsViewer as results_module
from fpdb_3_legacy import hud_day
from fpdb_3_legacy import period_results as pr
from fpdb_3_legacy.sql_queries_cash_profit import cash_profit_queries

pytestmark = pytest.mark.qt

NEW_YORK = pytz.timezone("America/New_York")
COLORS = {
    "background": "#101418",
    "foreground": "#e2e8f0",
    "grid": "#475569",
    "line_up": "#22c55e",
    "line_down": "#f43f5e",
    "line_showdown": "#00a2ff",
    "line_nonshowdown": "#f43f5e",
    "line_ev": "#ff9f43",
    "line_hands": "#22c55e",
}


@pytest.fixture(autouse=True)
def new_york(monkeypatch) -> None:
    monkeypatch.setattr(
        hud_day,
        "local_offset",
        lambda utc: pytz.utc.localize(utc).astimezone(NEW_YORK).utcoffset() or timedelta(0),
    )


ROWS = [
    (1, datetime(2026, 11, 9, 20, 0), 100, 60, True, 10, "USD"),  # Monday the 9th
    (2, datetime(2026, 11, 9, 21, 0), -30, -30, False, 10, "USD"),
    (3, datetime(2026, 11, 12, 20, 0), 50, 50, False, 10, "USD"),  # Thursday the 12th
    (4, datetime(2026, 10, 30, 20, 0), -80, -80, True, 10, "USD"),  # October
]


@pytest.fixture
def viewer(qtbot):
    db = MagicMock()
    db.get_player_site_id.return_value = 2
    config = MagicMock()
    config.get_db_parameters.return_value = {"db-server": "sqlite", "db-backend": 4}
    config.get_import_parameters.return_value = {}
    config.get_default_paths.return_value = {}
    sql = MagicMock()
    sql.query = {"periodResultsHands": "SELECT 1"}
    owner = MagicMock()
    owner.threads = []
    with patch("fpdb_3_legacy.Database.Database", return_value=db):
        page = results_module.GuiResultsViewer(config, sql, None, owner, colors=COLORS)
    qtbot.addWidget(page)
    return page


def _calendar_texts(page) -> dict[tuple[int, int], str]:
    calendar = page.calendar
    return {
        (row, column): calendar.item(row, column).text()
        for row in range(calendar.rowCount())
        for column in range(calendar.columnCount())
        if calendar.item(row, column) is not None
    }


def _find_cell(page, period: tuple[str, date]) -> tuple[int, int]:
    calendar = page.calendar
    for row in range(calendar.rowCount()):
        for column in range(calendar.columnCount()):
            item = calendar.item(row, column)
            if item is not None and item.data(results_module.PERIOD_ROLE) == period:
                return row, column
    raise AssertionError(period)


def test_the_calendar_opens_on_the_month_of_the_last_hand(viewer) -> None:
    viewer._show_results(pr.Results.build(ROWS))

    assert viewer.month == (2026, 11)
    assert [viewer.unit_box.itemData(i) for i in range(viewer.unit_box.count())] == [pr.UNIT_BB, "USD"]
    row, column = _find_cell(viewer, (pr.DAY, date(2026, 11, 9)))
    text = viewer.calendar.item(row, column).text()
    assert text.startswith("9\n")
    assert text.split("\n")[1] == "+7.00"  # +7 BB that day; the unit is in the month's title
    assert "2 hands" in viewer.calendar.item(row, column).toolTip()
    assert "BB" in viewer.month_label.text()
    week_row, week_column = _find_cell(viewer, (pr.WEEK, date(2026, 11, 9)))
    assert week_column == 7
    assert "+12" in viewer.calendar.item(week_row, week_column).text()
    assert "Hands: 4" in viewer.summary_label.text()


def test_moving_the_month_shows_the_other_days(viewer) -> None:
    viewer._show_results(pr.Results.build(ROWS))
    viewer._move_month(-1)

    assert viewer.month == (2026, 10)
    row, column = _find_cell(viewer, (pr.DAY, date(2026, 10, 30)))
    assert "-8" in viewer.calendar.item(row, column).text()


def test_the_table_lists_the_chosen_periods(viewer) -> None:
    viewer._show_results(pr.Results.build(ROWS))

    assert viewer.model.rowCount() == 3  # three days played
    viewer.granularity_box.setCurrentIndex(viewer.granularity_box.findData(pr.WEEK))
    assert viewer.model.rowCount() == 2
    viewer.granularity_box.setCurrentIndex(viewer.granularity_box.findData(pr.MONTH))
    assert viewer.model.rowCount() == 2
    starts = {viewer.model.item(row, 0).data(results_module.PERIOD_ROLE) for row in range(2)}
    assert starts == {(pr.MONTH, date(2026, 10, 1)), (pr.MONTH, date(2026, 11, 1))}


def test_selecting_a_day_draws_its_curves_and_reviews_its_hands(viewer) -> None:
    viewer._show_results(pr.Results.build(ROWS))
    assert viewer.plot_widget is not None  # every hand of the range before a selection
    row, column = _find_cell(viewer, (pr.DAY, date(2026, 11, 9)))

    viewer._calendar_clicked(row, column)

    assert viewer.selected == (pr.DAY, date(2026, 11, 9))
    assert [hand.hand_id for hand in viewer._selected_hands()] == [1, 2]
    assert viewer.plot_widget is not None
    assert viewer.review_button.isEnabled()

    class FakeHandViewer:
        def __init__(self) -> None:
            self.loaded: list[int] = []

        def reload_hands(self, hand_ids) -> None:
            self.loaded = list(hand_ids)

    hand_viewer = FakeHandViewer()
    viewer.owner.threads = [hand_viewer]
    with patch.object(results_module.GuiHandViewer, "GuiHandViewer", FakeHandViewer):
        viewer.review_hands()
    assert hand_viewer.loaded == [1, 2]


def test_selecting_a_table_row_selects_its_period(viewer) -> None:
    viewer._show_results(pr.Results.build(ROWS))
    viewer.granularity_box.setCurrentIndex(viewer.granularity_box.findData(pr.MONTH))
    index = next(
        viewer.proxy.index(row, 0)
        for row in range(viewer.proxy.rowCount())
        if viewer.proxy.index(row, 0).data(results_module.PERIOD_ROLE) == (pr.MONTH, date(2026, 10, 1))
    )

    viewer._row_clicked(index)

    assert viewer.selected == (pr.MONTH, date(2026, 10, 1))
    assert viewer.month == (2026, 10)
    assert [hand.hand_id for hand in viewer._selected_hands()] == [4]


def test_money_curves_follow_the_unit(viewer) -> None:
    viewer._show_results(pr.Results.build(ROWS))
    viewer.unit_box.setCurrentIndex(viewer.unit_box.findData("USD"))

    assert viewer.unit == "USD"
    row, column = _find_cell(viewer, (pr.DAY, date(2026, 11, 9)))
    assert "0.70" in viewer.calendar.item(row, column).text()


def test_no_results_clears_the_tab(viewer) -> None:
    viewer._show_results(pr.Results.build(ROWS))
    viewer._show_results(None)

    assert viewer.model.rowCount() == 0
    assert viewer.plot_widget is None
    assert not viewer.review_button.isEnabled()
    assert viewer.unit_box.count() == 0


def test_a_missing_filter_shows_no_data_without_loading(viewer) -> None:
    viewer.filters = MagicMock()
    viewer.filters.getSites.return_value = []
    viewer.filters.get_selected_players.return_value = []
    with (
        patch.object(results_module, "ResultsLoader") as loader,
        patch.object(results_module.gui_empty_state, "show_no_data") as show_no_data,
    ):
        viewer.refresh()

    show_no_data.assert_called_once()
    loader.assert_not_called()


class SqliteOwner:
    """What ResultsLoader needs of a Database: a connection for its thread."""

    def __init__(self) -> None:
        self.connection = sqlite3.connect(":memory:", check_same_thread=False)

    @contextlib.contextmanager
    def worker_connection(self):
        yield self.connection


def test_the_loader_reads_and_sums_off_the_gui_thread(qtbot) -> None:
    owner = SqliteOwner()
    query = (
        "SELECT 7, '2026-11-09 20:00:00', 100, NULL, 1, 10, 'usd' "
        "UNION ALL SELECT 8, '2026-11-10 20:00:00', -20, -20, 0, 10, 'usd'"
    )
    loader = results_module.ResultsLoader(owner, query, 0.0)

    with qtbot.waitSignal(loader.loaded, timeout=10_000) as signal:
        loader.start()
    qtbot.waitUntil(loader.isFinished, timeout=10_000)

    results = signal.args[0]
    assert [hand.hand_id for hand in results.hands] == [7, 8]
    assert results.hands[0].all_in_ev_minor == 100
    assert [day.start for day in results.periods[pr.DAY]] == [date(2026, 11, 9), date(2026, 11, 10)]


def test_a_failed_load_reports_its_error(qtbot) -> None:
    loader = results_module.ResultsLoader(SqliteOwner(), "SELECT * FROM NoSuchTable", 0.0)

    with qtbot.waitSignal(loader.error, timeout=10_000) as signal:
        loader.start()
    qtbot.waitUntil(loader.isFinished, timeout=10_000)

    assert "NoSuchTable" in signal.args[0]


def test_a_superseded_load_does_not_touch_the_tab(viewer) -> None:
    viewer.sql.query = cash_profit_queries()
    viewer.filters = MagicMock()
    viewer.filters.getSites.return_value = {"PokerStars": True}
    viewer.filters.getLimits.return_value = ["all"]
    viewer.filters.getGames.return_value = ["holdem"]
    viewer.filters.getCurrencies.return_value = ["USD"]
    viewer.filters.get_selected_players.return_value = [("PokerStars", 8)]
    viewer.filters.getDates.return_value = ("2026-01-01 00:00:00", "2026-12-31 23:59:59")
    viewer.filters.get_limits_where_clause.return_value = ""
    viewer.filters.getSeats.return_value = None
    viewer.filters.day_start = 0.0
    viewer.filters.display = {"Games": True}
    with patch.object(results_module, "ResultsLoader") as loader_class:
        viewer.refresh()
        first_loaded = loader_class.return_value.loaded.connect.call_args.args[0]
        viewer.refresh()
        second_loaded = loader_class.return_value.loaded.connect.call_args.args[0]

    first_loaded(pr.Results.build(ROWS))
    assert viewer.results is None
    second_loaded(pr.Results.build(ROWS))
    assert viewer.results is not None
    query = loader_class.call_args.args[1]
    assert "hp.playerId in (8)" in query
    assert "gt.category in ('holdem')" in query
    assert "gt.currency in ('USD')" in query
