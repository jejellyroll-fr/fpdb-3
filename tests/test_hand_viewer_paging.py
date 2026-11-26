"""The Hand Viewer's bounded hand cache, hand-number search and abortable paging."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy import GuiHandViewer as viewer_module
from fpdb_3_legacy.GuiHandViewer import GuiHandViewer
from fpdb_3_legacy.hand_viewer_paging import (
    MIN_CACHE_SIZE,
    HandCache,
    cache_limit,
    hand_positions,
    locate_hand,
    search_numbers,
)
from fpdb_3_legacy.plot_performance import enable_large_curve_rendering

# -- the cache ------------------------------------------------------------------


def test_the_cache_keeps_a_few_pages_and_never_fewer_than_its_floor() -> None:
    assert cache_limit(100) == MIN_CACHE_SIZE
    assert cache_limit(25) == MIN_CACHE_SIZE
    assert cache_limit(250) == 750


def test_trim_forgets_the_hands_used_least_recently() -> None:
    cache = HandCache((hand_id, f"hand {hand_id}") for hand_id in range(1, 6))
    cache.touch(1)  # used again: now the most recent

    cache.trim(3)

    assert list(cache) == [4, 5, 1]


def test_trim_never_forgets_the_page_on_screen() -> None:
    cache = HandCache((hand_id, hand_id) for hand_id in range(1, 6))

    cache.trim(2, keep=[1, 2, 3])

    assert list(cache) == [1, 2, 3]


def test_touching_an_uncached_hand_does_nothing() -> None:
    cache = HandCache({1: "a"})
    cache.touch(99)
    assert list(cache) == [1]


# -- what the user types ----------------------------------------------------------


@pytest.mark.parametrize(
    ("typed", "numbers"),
    [
        ("#259417328402", [259417328402]),  # PokerStars, as in the hand history
        ("RC1234567", [1234567]),  # GGPoker: the letter prefix is not stored
        ("  4242 ", [4242]),
        ("", []),
        ("abc", []),
        ("0", []),
        ("9" * 30, []),  # beyond BIGINT: could never match, and PostgreSQL would reject it
    ],
)
def test_search_numbers(typed: str, numbers: list[int]) -> None:
    assert search_numbers(typed) == numbers


def test_a_winamax_number_is_searched_the_way_winamax_hands_are_stored() -> None:
    # WinamaxToFpdb stores f"{int(HID1[:14])}{int(HID2)}".
    numbers = search_numbers("#20231123456789012-345-1700000000")

    assert numbers[0] == int("20231123456789345")


# -- where the hand is ------------------------------------------------------------


def test_a_room_hand_number_wins_over_an_fpdb_id() -> None:
    positions = hand_positions([10, 20, 30, 40, 50])
    # 500 is hand 20's room number and also hand 40's fpdb id... in a database
    # with 500 hands; the room number is what a user copies.
    matches = [(40, 123456), (20, 500)]

    assert locate_hand(matches, [500], positions, page_size=2) == (20, 0)


def test_an_fpdb_id_is_found_when_no_room_number_matches() -> None:
    positions = hand_positions([10, 20, 30, 40, 50])

    assert locate_hand([(50, 777)], [50], positions, page_size=2) == (50, 2)


def test_a_hand_outside_the_loaded_hands_is_not_located() -> None:
    positions = hand_positions([10, 20])

    assert locate_hand([(99, 123)], [123], positions, page_size=100) is None


# -- the viewer -------------------------------------------------------------------


class _Progress:  # pylint: disable=invalid-name  # stands in for QProgressDialog
    """A QProgressDialog stand-in that aborts once ``cancel_at`` hands are loaded."""

    cancel_at: int | None = None

    def __init__(self, *_args) -> None:
        self.value = 0

    def setValue(self, value: int) -> None:
        self.value = value

    def show(self) -> None:
        pass

    def close(self) -> None:
        pass

    def wasCanceled(self) -> bool:
        return self.cancel_at is not None and self.value >= self.cancel_at


class _Model:  # pylint: disable=invalid-name  # stands in for QStandardItemModel
    def __init__(self) -> None:
        self.rows: list = []

    def rowCount(self) -> int:
        return len(self.rows)

    def removeRows(self, _start: int, _count: int) -> None:
        self.rows = []


def _viewer(monkeypatch, hand_ids, page_size=2):
    monkeypatch.setattr(viewer_module, "QProgressDialog", _Progress)
    monkeypatch.setattr(viewer_module, "QCoreApplication", SimpleNamespace(processEvents=lambda: None))
    _Progress.cancel_at = None
    viewer = GuiHandViewer.__new__(GuiHandViewer)  # pylint: disable=no-value-for-parameter
    viewer.all_handids = list(hand_ids)
    viewer.page = 0
    viewer.page_size = page_size
    viewer.colnum = {"HandId": 0}
    viewer.hands = HandCache()
    viewer._positions = None  # pylint: disable=protected-access
    viewer._loading = False  # pylint: disable=protected-access
    viewer.sent_heroes = {}
    viewer.model = _Model()
    viewer.view = MagicMock()
    viewer._select_hand_row = lambda _hand_id: True
    viewer.pageLabel = MagicMock()
    viewer.prevPageButton = MagicMock()
    viewer.nextPageButton = MagicMock()
    viewer.hand_search_status = MagicMock()
    viewer.imported = []

    def importhand(hand_id):
        viewer.imported.append(hand_id)
        return SimpleNamespace(id=hand_id)

    viewer.importhand = importhand
    monkeypatch.setattr(viewer, "addHandRow", lambda hand_id, _hand: viewer.model.rows.append(hand_id))
    viewer._result_colors = dict  # pylint: disable=protected-access
    return viewer


def test_paging_keeps_the_cache_bounded(monkeypatch) -> None:
    viewer = _viewer(monkeypatch, range(1, 1001), page_size=100)

    for page in range(10):
        assert viewer.render_page(page)

    assert len(viewer.hands) == cache_limit(100)
    assert viewer.model.rows == list(range(901, 1001))
    assert all(hand_id in viewer.hands for hand_id in viewer.model.rows)


def test_cancelling_a_page_size_change_keeps_the_displayed_hands_cached(monkeypatch) -> None:
    viewer = _viewer(monkeypatch, range(1, 501), page_size=500)
    viewer.render_page(0)
    viewer.page_size_combo = MagicMock()
    viewer.page_size_combo.currentData.return_value = 25
    viewer.page_size_combo.findData.side_effect = lambda size: size
    _Progress.cancel_at = 1

    viewer._page_size_changed(0)

    assert viewer.page_size == 500
    assert viewer.model.rows == list(range(1, 501))
    assert all(hand_id in viewer.hands for hand_id in viewer.model.rows)
    viewer.page_size_combo.setCurrentIndex.assert_called_once_with(500)


def test_a_page_seen_recently_is_not_rebuilt(monkeypatch) -> None:
    viewer = _viewer(monkeypatch, range(1, 7))
    viewer.render_page(0)
    viewer.render_page(1)
    viewer.imported.clear()

    viewer.render_page(0)

    assert not viewer.imported


def test_aborting_a_page_leaves_the_page_shown_before(monkeypatch) -> None:
    viewer = _viewer(monkeypatch, range(1, 7))
    viewer.render_page(0)
    _Progress.cancel_at = 1

    viewer.next_page()

    assert viewer.page == 0
    assert viewer.model.rows == [1, 2]


def test_aborting_new_hands_leaves_the_hands_shown_before(monkeypatch) -> None:
    viewer = _viewer(monkeypatch, [1, 2, 3])
    viewer.render_page(0)
    _Progress.cancel_at = 1

    viewer.reload_hands([7, 8, 9], heroes={7: "alice"})

    assert viewer.all_handids == [1, 2, 3]
    assert viewer.model.rows == [1, 2]
    assert viewer.sent_heroes == {}
    assert 7 not in viewer.hands


def test_a_stale_view_refreshes_its_hand_list(monkeypatch) -> None:
    viewer = _viewer(monkeypatch, [1, 2, 3])
    viewer.render_page(0)
    viewer._stale = True
    viewer.filters = SimpleNamespace(getDates=lambda: ("start", "end"), end_read_transaction=MagicMock())
    viewer.get_hand_ids_from_date_range = lambda *_dates: [7, 8, 9]

    assert viewer.refresh_if_stale() is True

    assert viewer.all_handids == [7, 8, 9]
    assert viewer.model.rows == [7, 8]
    assert viewer._stale is False
    viewer.filters.end_read_transaction.assert_called_once_with()


def test_import_invalidates_a_loaded_empty_result_set() -> None:
    viewer = GuiHandViewer.__new__(GuiHandViewer)  # pylint: disable=no-value-for-parameter
    viewer._has_loaded_hand_query = True
    viewer.all_handids = []
    viewer.hand_search_status = MagicMock()

    viewer.mark_stale()

    assert viewer._stale is True


def test_a_loaded_empty_result_set_refreshes_after_an_import(monkeypatch) -> None:
    viewer = _viewer(monkeypatch, [])
    viewer._has_loaded_hand_query = True
    viewer._stale = True
    viewer.filters = SimpleNamespace(getDates=lambda: ("start", "end"), end_read_transaction=MagicMock())
    viewer.get_hand_ids_from_date_range = lambda *_dates: []
    viewer.db = None
    monkeypatch.setattr(viewer_module.gui_empty_state, "show_no_data", lambda *_args, **_kwargs: None)

    assert viewer.refresh_if_stale() is True

    assert viewer.all_handids == []
    assert viewer._stale is False
    viewer.filters.end_read_transaction.assert_called_once_with()


def test_an_external_selection_ends_its_refresh_transaction(monkeypatch) -> None:
    viewer = _viewer(monkeypatch, [1, 2, 3])
    viewer._external_hand_selection = True
    viewer._stale = True
    viewer.filters = SimpleNamespace(end_read_transaction=MagicMock())

    assert viewer.refresh_if_stale() is True

    viewer.filters.end_read_transaction.assert_called_once_with()


def test_import_does_not_load_an_untouched_empty_viewer() -> None:
    viewer = GuiHandViewer.__new__(GuiHandViewer)  # pylint: disable=no-value-for-parameter
    viewer._has_loaded_hand_query = False
    viewer.all_handids = []
    viewer.hand_search_status = MagicMock()

    viewer.mark_stale()

    assert getattr(viewer, "_stale", False) is False


def test_stale_refresh_follows_selected_hand_after_its_id_is_returned_as_text(monkeypatch) -> None:
    viewer = _viewer(monkeypatch, [1, 2, 3, 4])
    viewer.render_page(0)
    viewer._stale = True
    viewer.filters = SimpleNamespace(getDates=lambda: ("start", "end"), end_read_transaction=MagicMock())
    viewer.get_hand_ids_from_date_range = lambda *_dates: [7, 8, 9, 10]
    selected = MagicMock()
    selected.siblingAtColumn.return_value.data.return_value = "9"
    viewer.view.selectionModel.return_value.selectedRows.return_value = [selected]

    assert viewer.refresh_if_stale() is True

    assert viewer.page == 1
    assert viewer.model.rows == [9, 10]
    viewer.filters.end_read_transaction.assert_called_once_with()


def test_cancelling_a_stale_refresh_keeps_the_current_page_and_stale_flag(monkeypatch) -> None:
    viewer = _viewer(monkeypatch, [1, 2, 3])
    viewer.render_page(0)
    viewer._stale = True
    viewer.filters = SimpleNamespace(getDates=lambda: ("start", "end"), end_read_transaction=MagicMock())
    viewer.get_hand_ids_from_date_range = lambda *_dates: [7, 8, 9]
    _Progress.cancel_at = 1

    assert viewer.refresh_if_stale() is False

    assert viewer.all_handids == [1, 2, 3]
    assert viewer.model.rows == [1, 2]
    assert viewer._stale is True
    viewer.filters.end_read_transaction.assert_called_once_with()


def test_a_refused_stale_query_keeps_the_current_page_and_stale_flag(monkeypatch) -> None:
    viewer = _viewer(monkeypatch, [1, 2, 3])
    viewer.render_page(0)
    viewer._stale = True
    viewer.filters = SimpleNamespace(getDates=lambda: ("start", "end"), end_read_transaction=MagicMock())

    def refused_query(*_dates):
        viewer._last_hand_query_ok = False
        return []

    viewer.get_hand_ids_from_date_range = refused_query

    assert viewer.refresh_if_stale() is False

    assert viewer.all_handids == [1, 2, 3]
    assert viewer.model.rows == [1, 2]
    assert viewer._stale is True
    viewer.filters.end_read_transaction.assert_called_once_with()


def test_the_rows_on_screen_stay_usable_while_new_hands_load(monkeypatch) -> None:
    # The table stays clickable during processEvents(): a right-click or a
    # double-click on a row shown before must still find its hand (Codex, #859).
    viewer = _viewer(monkeypatch, [1, 2, 3])
    viewer.render_page(0)
    readable_during_load = []

    def importhand(hand_id):
        readable_during_load.append(all(shown in viewer.hands for shown in viewer.model.rows))
        return SimpleNamespace(id=hand_id)

    viewer.importhand = importhand

    viewer.reload_hands([7, 8, 9])

    assert readable_during_load == [True, True]
    assert viewer.model.rows == [7, 8]
    assert list(viewer.hands) == [7, 8]


def test_the_replayer_reaches_the_hands_the_cache_forgot(monkeypatch) -> None:
    # Up/Down in the replayer walk its hand list: it must hold every loaded
    # hand, not only the few pages the cache still keeps (Codex, #859).
    viewer = _viewer(monkeypatch, range(1, 1001), page_size=100)
    for page in range(5):
        viewer.render_page(page)
    assert 1 not in viewer.hands
    replayer = MagicMock()
    monkeypatch.setattr(viewer_module.GuiReplayer, "GuiReplayer", replayer)
    viewer.colnum = {"HandId": 0}
    viewer.config = viewer.sql = viewer.main_window = viewer.db = None
    index = MagicMock()
    index.sibling.return_value.data.return_value = "450"

    viewer.row_activated(index)

    assert replayer.call_args.args[3] == list(range(1, 1001))
    replayer.return_value.play_hand.assert_called_once_with(449)


class _Cursor:
    def __init__(self, rows_by_number) -> None:
        self.rows_by_number = rows_by_number
        self.rows: list = []
        self.queries: list = []

    def execute(self, query, params) -> None:
        self.queries.append((query, params))
        self.rows = self.rows_by_number.get(params[0], [])

    def fetchall(self):
        return self.rows


def _searchable(monkeypatch, rows_by_number):
    viewer = _viewer(monkeypatch, range(1, 7))
    viewer.render_page(0)
    cursor = _Cursor(rows_by_number)
    viewer.db = SimpleNamespace(
        sql=SimpleNamespace(
            query={
                "placeholder": "?",
                "handsMatchingNumber": "SELECT id, siteHandNo FROM Hands WHERE siteHandNo = %s OR id = %s",
            }
        ),
        get_cursor=lambda: cursor,
        rollback=lambda: None,
    )
    viewer.selected = []
    viewer._select_hand_row = lambda hand_id: viewer.selected.append(hand_id) or True  # pylint: disable=protected-access
    return viewer, cursor


def test_search_jumps_to_the_page_of_a_hand_never_shown(monkeypatch) -> None:
    viewer, cursor = _searchable(monkeypatch, {555: [(5, 555)]})

    assert viewer.find_hand("#555")

    assert viewer.page == 2
    assert viewer.model.rows == [5, 6]
    assert viewer.selected == [5]
    assert cursor.queries[0] == ("SELECT id, siteHandNo FROM Hands WHERE siteHandNo = ? OR id = ?", (555, 555))


def test_search_says_when_the_hand_is_outside_the_loaded_hands(monkeypatch) -> None:
    viewer, _cursor = _searchable(monkeypatch, {555: [(99, 555)]})

    assert not viewer.find_hand("555")

    assert viewer.page == 0
    assert "not among the loaded hands" in viewer.hand_search_status.setText.call_args.args[0]


def test_search_for_an_unknown_number(monkeypatch) -> None:
    viewer, _cursor = _searchable(monkeypatch, {})

    assert not viewer.find_hand("123")
    assert viewer.hand_search_status.setText.call_args.args[0] == "Hand not found"


# -- graphs -----------------------------------------------------------------------


def test_large_curves_are_clipped_and_downsampled_by_peaks() -> None:
    item = MagicMock()
    widget = MagicMock()
    widget.getPlotItem.return_value = item

    enable_large_curve_rendering(widget)

    item.setClipToView.assert_called_once_with(True)
    item.setDownsampling.assert_called_once_with(auto=True, mode="peak")
