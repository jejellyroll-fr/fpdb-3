"""Tests for the shared "no data" popup used by every stats/graph tab."""

import sqlite3
from types import SimpleNamespace

import pytest

from fpdb_3_legacy import gui_empty_state
from fpdb_3_legacy.gui_empty_state import NoDataReason


class FakeDb:
    """Just enough of Database for the empty-database probe."""

    def __init__(self, conn) -> None:
        self.conn = conn
        self.rollbacks = 0

    def get_cursor(self):
        return self.conn.cursor()

    def rollback(self) -> None:
        self.rollbacks += 1


@pytest.fixture
def empty_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE Hands (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE Tourneys (id INTEGER PRIMARY KEY)")
    return FakeDb(conn)


@pytest.fixture
def populated_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE Hands (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE Tourneys (id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO Hands (id) VALUES (1)")
    return FakeDb(conn)


class FakeMessageBox:
    """Captures what would have been shown instead of opening a modal dialog."""

    shown: list[tuple[str, str]] = []

    class Icon:
        Information = "information"

    def __init__(self, parent=None) -> None:
        self.text = ""
        self.informative = ""

    def setIcon(self, icon) -> None:  # noqa: N802 - Qt API
        pass

    def setWindowTitle(self, title) -> None:  # noqa: N802 - Qt API
        pass

    def setText(self, text) -> None:  # noqa: N802 - Qt API
        self.text = text

    def setInformativeText(self, text) -> None:  # noqa: N802 - Qt API
        self.informative = text

    def exec(self) -> None:
        FakeMessageBox.shown.append((self.text, self.informative))


class FakeQApplication:
    @staticmethod
    def instance():
        return FakeQApplication


@pytest.fixture
def captured_popup(monkeypatch):
    """Force the "a GUI is running" branch without opening a real dialog."""
    FakeMessageBox.shown = []
    monkeypatch.setattr(gui_empty_state, "QMessageBox", FakeMessageBox)
    monkeypatch.setattr(gui_empty_state, "QApplication", FakeQApplication)
    return FakeMessageBox.shown


def test_missing_filter_reason_reports_the_first_empty_filter() -> None:
    assert gui_empty_state.missing_filter_reason(sites=[], playerids=[]) is NoDataReason.NO_SITE
    assert gui_empty_state.missing_filter_reason(sites=["Winamax"], playerids=[]) is NoDataReason.NO_HERO
    assert gui_empty_state.missing_filter_reason(sites=["W"], playerids=[1], limits=[]) is NoDataReason.NO_LIMIT
    assert gui_empty_state.missing_filter_reason(sites=["W"], playerids=[1], games=[]) is NoDataReason.NO_GAME
    assert gui_empty_state.missing_filter_reason(sites=["W"], playerids=[1], currencies=[]) is NoDataReason.NO_CURRENCY


def test_missing_filter_reason_ignores_filters_a_tab_does_not_use() -> None:
    """``None`` means "not applicable" - only an empty collection is a reason."""
    assert gui_empty_state.missing_filter_reason(sites=["Winamax"], playerids=[1]) is None
    assert gui_empty_state.missing_filter_reason(sites=["Winamax"], playerids=[1], limits=["NL10"]) is None


def test_database_is_empty(empty_db, populated_db) -> None:
    assert gui_empty_state.database_is_empty(empty_db) is True
    assert gui_empty_state.database_is_empty(populated_db) is False
    # Hands empty but Tourneys filled: a tournament tab still has data.
    empty_db.conn.execute("INSERT INTO Tourneys (id) VALUES (1)")
    assert gui_empty_state.database_is_empty(empty_db, ("Hands", "Tourneys")) is False


def test_database_is_empty_is_unknown_when_the_probe_fails(empty_db) -> None:
    assert gui_empty_state.database_is_empty(empty_db, ("NoSuchTable",)) is None


def test_no_rows_becomes_empty_database_when_nothing_was_imported(empty_db, captured_popup) -> None:
    reason = gui_empty_state.show_no_data(None, db=empty_db)

    assert reason is NoDataReason.EMPTY_DATABASE
    text, hint = captured_popup[0]
    assert "no hands yet" in text
    assert "Bulk Import" in hint


def test_no_rows_stays_no_rows_when_the_database_has_hands(populated_db, captured_popup) -> None:
    reason = gui_empty_state.show_no_data(None, db=populated_db)

    assert reason is NoDataReason.NO_ROWS
    assert "No hand matches the selected filters." in captured_popup[0][0]


def test_a_filter_reason_is_never_masked_by_the_empty_database_check(empty_db, captured_popup) -> None:
    """An unticked site is the user's actual problem, even on an empty database."""
    reason = gui_empty_state.show_no_data(None, NoDataReason.NO_SITE, db=empty_db)

    assert reason is NoDataReason.NO_SITE
    assert "No site is selected" in captured_popup[0][0]


def test_every_reason_has_a_headline_and_an_action(captured_popup) -> None:
    for reason in NoDataReason:
        gui_empty_state.show_no_data(None, reason)
    assert len(captured_popup) == len(NoDataReason)
    for text, hint in captured_popup:
        assert text.strip()
        assert hint.strip()


def test_ring_profit_graph_reports_an_unticked_site(empty_db, monkeypatch) -> None:
    """The graph tab used to log "defaulting to PokerStars" and draw nothing."""
    from fpdb_3_legacy.GuiGraphViewer import GuiGraphViewer

    reported = []
    monkeypatch.setattr(gui_empty_state, "show_no_data", lambda *a, **kw: reported.append(a[1]))
    viewer = SimpleNamespace(
        clearGraphData=lambda: None,
        db=empty_db,
        conf=None,
        filters=SimpleNamespace(
            getSites=list,
            getHeroes=dict,
            getSiteIds=dict,
            getLimits=list,
            getGames=list,
            getCurrencies=list,
            getGraphOps=list,
        ),
    )

    GuiGraphViewer.generateGraph(viewer, None)

    assert reported == [NoDataReason.NO_SITE]


def test_ring_stats_controller_emits_the_reason(empty_db) -> None:
    """The cash stats tab kept its stale content when a filter was empty."""
    from fpdb_3_legacy.ring_stats.controller import RingStatsController

    controller = RingStatsController(
        SimpleNamespace(cursor=None, backend=4),
        SimpleNamespace(get_gui_cash_stat_params=list),
        sql=None,
    )
    emitted = []
    controller.no_data_found.connect(emitted.append)
    filters = SimpleNamespace(
        getSites=lambda: ["Winamax"],
        getHeroes=dict,
        getSiteIds=dict,
        getLimits=list,
        getSeats=dict,
        getGroups=dict,
        getDates=lambda: ("", ""),
        getGames=list,
        getCurrencies=list,
        getNumHands=lambda: 0,
    )

    controller.refresh_all(filters)

    assert emitted == [NoDataReason.NO_HERO.value]


def test_headless_callers_only_log(empty_db, monkeypatch) -> None:
    """No QApplication (tests, CLI): report the reason without touching Qt."""

    class NoQApplication:
        @staticmethod
        def instance():
            return None

    monkeypatch.setattr(gui_empty_state, "QApplication", NoQApplication)

    assert gui_empty_state.show_no_data(None, db=empty_db) is NoDataReason.EMPTY_DATABASE
