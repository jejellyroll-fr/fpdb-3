"""Navigating the Tourney Stats tab: views, drill-down, breadcrumb, search, hands."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QWidget

from fpdb_3_legacy import GuiTourneyPlayerStats as module
from fpdb_3_legacy.tourney_results import BY_BUYIN, BY_DATE, BY_DESCRIPTION, BY_TOURNAMENT, TourneyResult

pytestmark = pytest.mark.qt


class _Filters(QWidget):
    def registerButton2Name(self, *_args) -> None:  # noqa: N802 - Filters API
        pass

    def registerButton2Callback(self, *_args) -> None:  # noqa: N802 - Filters API
        pass


def _result(tourney_id: int, tourney_type_id: int, prize: float | None, day: int) -> TourneyResult:
    return TourneyResult(
        tourney_id=tourney_id,
        tourney_no=1000 + tourney_id,
        tourney_type_id=tourney_type_id,
        player_id=7,
        player_name="alice",
        site="Winamax",
        currency="EUR",
        buy_in=0.23 if tourney_type_id == 1 else 0.45,
        fee=0.02 if tourney_type_id == 1 else 0.05,
        prize=prize,
        bounties=0.0,
        finish=1 if prize else 3,
        max_seats=3,
        speed="Hyper" if tourney_type_id == 1 else "Normal",
        category="holdem",
        limit_type="nl",
        sng=True,
        hands=10 if tourney_id != 4 else 0,
        start=datetime(2026, 6, day, 12, tourney_id),
    )


RESULTS = [
    _result(1, 1, 0.75, 20),
    _result(2, 1, 0.0, 20),
    _result(3, 1, 0.75, 21),
    _result(4, 2, None, 21),
]


@pytest.fixture
def tab(qtbot):
    with patch.object(module.Filters, "Filters", lambda *_a, **_k: _Filters()):
        page = module.GuiTourneyPlayerStats(MagicMock(), MagicMock(), MagicMock(), None)
    qtbot.addWidget(page)
    page._grid_descriptors = []
    page._descriptor_specs = []
    page.results = list(RESULTS)
    page._render()
    page.resize(1200, 800)
    page.show()
    yield page
    page.close()
    page.deleteLater()


def _column(page, key: str) -> int:
    return next(index for index, column in enumerate(page._columns) if column.key == key)


def _texts(page, key: str) -> list[str]:
    column = _column(page, key)
    return [page.proxy.index(row, column).data() for row in range(page.proxy.rowCount())]


def test_the_page_opens_on_the_descriptions_with_the_overview(tab) -> None:
    assert tab.group_mode == BY_DESCRIPTION
    assert tab.proxy.rowCount() == 2
    assert tab.card_count.value.text() == "4"
    assert tab.card_count.note.isVisibleTo(tab)  # one tournament has no result
    assert tab.card_net.value.property("tone") == "up"
    assert not tab.breadcrumb_bar.isVisibleTo(tab)
    # The type whose only tournament has no result shows no money, not a lost buy-in.
    assert "–" in _texts(tab, "net")


def test_double_clicking_a_description_lists_its_tournaments_in_place(tab) -> None:
    hyper = next(row for row in range(tab.proxy.rowCount()) if tab._key_at(tab.proxy.index(row, 0))[0] == 1)

    tab._on_row_activated(tab.proxy.index(hyper, 0))

    assert tab.group_mode == BY_TOURNAMENT
    assert tab.proxy.rowCount() == 3
    assert tab.breadcrumb_bar.isVisibleTo(tab)
    assert tab.card_count.value.text() == "3"
    assert not tab.card_count.note.isVisibleTo(tab)
    # Newest first.
    assert _texts(tab, "tourney_no")[0] == "1003"


def test_back_returns_to_the_group_it_came_from(tab) -> None:
    key = tab._key_at(tab.proxy.index(0, 0))
    tab.drill_into(key)

    tab.go_back()

    assert tab.group_mode == BY_DESCRIPTION
    assert tab._selected_key() == key
    assert not tab.breadcrumb_bar.isVisibleTo(tab)


def test_views_regroup_within_the_drill_down_and_the_breadcrumb_clears_it(tab) -> None:
    tab.drill_into((1, 7))
    tab.set_group_mode(BY_DATE)
    assert tab.proxy.rowCount() == 2  # the 20th and the 21st

    tab.drill_into(tab._key_at(tab.proxy.index(0, 0)))
    assert len(tab._scopes) == 2

    tab._on_breadcrumb_link("0")
    assert tab._scopes == []
    assert tab.group_mode == BY_DESCRIPTION
    assert tab.card_count.value.text() == "4"


def test_buy_in_levels_sort_by_amount(tab) -> None:
    tab.set_group_mode(BY_BUYIN)
    tab.table.sortByColumn(0, module.Qt.SortOrder.AscendingOrder)

    assert [tab._key_at(tab.proxy.index(row, 0)) for row in range(tab.proxy.rowCount())] == [
        ("EUR", 0.25),
        ("EUR", 0.5),
    ]


def test_the_search_filters_rows_and_says_so(tab) -> None:
    tab.set_group_mode(BY_TOURNAMENT)
    tab.search_edit.setText("1002")
    tab._apply_search()

    assert tab.proxy.rowCount() == 1
    assert "1" in tab.totals_label.text() and "4" in tab.totals_label.text()


def test_a_tournament_opens_its_hands_and_one_without_hands_cannot(tab) -> None:
    tab.set_group_mode(BY_TOURNAMENT)
    opened = []
    tab._open_tourney_hands = lambda tourney_id, tourney_no: opened.append(tourney_id)

    for row in range(tab.proxy.rowCount()):
        index = tab.proxy.index(row, 0)
        tab.table.setCurrentIndex(index)
        tab.table.selectRow(row)
        if tab._key_at(index)[0] == 4:
            assert not tab.open_hands_button.isEnabled()
        else:
            assert tab.open_hands_button.isEnabled()

    tab._on_row_activated(tab.proxy.index(0, 0))
    assert len(opened) == 1


def test_a_hidden_column_stays_hidden_across_views(tab) -> None:
    cashes = _column(tab, "cashes")
    tab._set_column_shown(cashes, "cashes", False)

    tab.set_group_mode(BY_DATE)

    assert tab.table.isColumnHidden(_column(tab, "cashes"))
