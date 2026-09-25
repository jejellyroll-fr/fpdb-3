"""Tests for Hand Viewer splash-pot filtering and display."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from PySide6.QtWidgets import QMessageBox

from fpdb_3_legacy import analytics_lifecycle
from fpdb_3_legacy.Filters import POSITION_FILTER_VALUES
from fpdb_3_legacy.GuiHandViewer import GuiHandViewer


def test_splash_filter_conditions_include_legacy_null_rows() -> None:
    selector = MagicMock()
    viewer = SimpleNamespace(flagSplashPot=selector)

    selector.currentData.return_value = "all"
    assert GuiHandViewer._splash_filter_condition(viewer) is None

    selector.currentData.return_value = "only"
    assert GuiHandViewer._splash_filter_condition(viewer) == "h.splashPot > 0"

    selector.currentData.return_value = "exclude"
    assert GuiHandViewer._splash_filter_condition(viewer) == "(h.splashPot = 0 OR h.splashPot IS NULL)"


def test_splash_display_contains_drop_and_hero_share() -> None:
    display = GuiHandViewer._format_splash(20, 0.20, "EUR")

    assert "0.20" in display
    assert "won" in display


def test_position_filter_includes_native_unknown_position() -> None:
    assert 9 in POSITION_FILTER_VALUES


class _Check:
    def __init__(self, checked: bool) -> None:
        self.checked = checked

    def isChecked(self) -> bool:
        return self.checked


class _Cursor:
    def __init__(self) -> None:
        self.query = ""

    def execute(self, query: str) -> None:
        self.query = query

    def fetchall(self):
        return [(101,)]


def _query_viewer(**flags):
    cursor = _Cursor()
    viewer = SimpleNamespace(
        db=SimpleNamespace(
            sql=SimpleNamespace(
                query={
                    "handsInRangeSessionFilter": """
                        select distinct h.id from Hands h
                        join Gametypes gt on h.gametypeId = gt.id
                        join HandsPlayers hp on h.id = hp.handId
                        where h.startTime <datetest>
                        <game_test><limit_test><player_test><position_test>
                    """
                }
            ),
            get_cursor=lambda: cursor,
        ),
        filters=SimpleNamespace(replace_placeholders_with_filter_values=lambda query: query),
        flagBombPot=_Check(flags.get("bomb", False)),
        flagDoubleBoard=_Check(flags.get("double", False)),
        flagRunItTwice=_Check(False),
        flagAllIn=_Check(False),
        flagShowdown=_Check(False),
        flagCashout=_Check(False),
        _splash_filter_condition=lambda: None,
        _analytics_filter_warning=lambda _filters: "",
    )
    return viewer, cursor


def test_bomb_and_double_board_filters_use_distinct_storage_semantics() -> None:
    bomb_viewer, bomb_cursor = _query_viewer(bomb=True)
    assert GuiHandViewer.get_hand_ids_from_date_range(bomb_viewer, "start", "end") == [101]
    assert "select distinct h.id" in bomb_cursor.query.lower()
    assert "h.bombPot > 0" in bomb_cursor.query

    double_viewer, double_cursor = _query_viewer(double=True)
    GuiHandViewer.get_hand_ids_from_date_range(double_viewer, "start", "end")
    assert "h.bombPot > 0 AND (SELECT COUNT(*) FROM Boards" in double_cursor.query


def test_analytics_filter_warns_and_does_not_query_when_subsystem_is_stale(monkeypatch) -> None:
    viewer, cursor = _query_viewer()
    viewer._advanced_filter_values = lambda: {"preflop": "rfi"}
    viewer._analytics_filter_warning = lambda filters: GuiHandViewer._analytics_filter_warning(viewer, filters)
    monkeypatch.setattr(
        analytics_lifecycle,
        "subsystem_statuses",
        lambda _db: {
            "action_events": SimpleNamespace(
                name="action_events", recorded_version=0, code_version=1, is_stale=True,
            ),
            "situations": SimpleNamespace(
                name="situations", recorded_version=0, code_version=1, is_stale=True,
            ),
        },
    )
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: warnings.append(_args[-1]))

    assert GuiHandViewer.get_hand_ids_from_date_range(viewer, "start", "end") == []
    assert cursor.query == ""
    assert "Rebuild Analytics Data" in warnings[0]
    assert "No hands were queried" in warnings[0]


def test_preflop_all_in_does_not_require_derived_analytics(monkeypatch) -> None:
    viewer, cursor = _query_viewer()
    viewer._advanced_filter_values = lambda: {"preflop": "all_in"}
    viewer._analytics_filter_warning = lambda filters: GuiHandViewer._analytics_filter_warning(viewer, filters)

    def unexpected_status_read(_db):
        raise AssertionError("historical all-in columns must not require analytics lifecycle data")

    monkeypatch.setattr(analytics_lifecycle, "subsystem_statuses", unexpected_status_read)

    assert GuiHandViewer.get_hand_ids_from_date_range(viewer, "start", "end") == [101]
    assert "AAI.street = -1 OR (AAI.street = 0 AND gt.category <> 'aof_omaha')" in cursor.query
    assert "AAI.allIn IS TRUE" in cursor.query


def test_hand_flags_do_not_call_bomb_pots_run_it_twice() -> None:
    bomb = SimpleNamespace(runItTimes=2, bombPot=1, actions={}, shown=False)
    rit = SimpleNamespace(runItTimes=2, bombPot=0, actions={}, shown=False)

    assert GuiHandViewer._hand_flags(None, bomb) == "BOMB 2xB"
    assert GuiHandViewer._hand_flags(None, rit) == "RIT×2"
