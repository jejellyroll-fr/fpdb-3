"""Finding a hand by number in a real Hand Viewer, with its real table and pages."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QApplication

pytestmark = pytest.mark.qt


@pytest.fixture
def viewer(monkeypatch):
    if QApplication.instance() is None:
        QApplication([])
    from fpdb_3_legacy.GuiHandViewer import GuiHandViewer

    conf = MagicMock()
    conf.get_db_parameters.return_value = {"db-backend": "sqlite", "db-server": "sqlite", "db-database": ":memory:"}
    with patch("fpdb_3_legacy.Database.Database", return_value=MagicMock()):
        widget = GuiHandViewer(conf, MagicMock(), None)
    widget.filters = MagicMock()
    widget.filters.getCards.return_value = {}
    widget.importhand = lambda hand_id: SimpleNamespace(id=hand_id)

    def add_row(hand_id, _hand) -> None:
        row = [QStandardItem("") for _column in range(len(widget.colnum))]
        row[widget.colnum["HandId"]] = QStandardItem(str(hand_id))
        widget.model.appendRow(row)

    monkeypatch.setattr(widget, "addHandRow", add_row)
    yield widget
    widget.deleteLater()


def _shown_ids(widget) -> list[int]:
    column = widget.colnum["HandId"]
    return [int(widget.filterModel.index(row, column).data()) for row in range(widget.filterModel.rowCount())]


def test_a_search_opens_the_page_of_the_hand_and_selects_it(viewer) -> None:
    viewer.reload_hands(list(range(1001, 1251)))  # three pages of 100
    # Room hand number 9000000123 is fpdb hand 1234, on the third page.
    viewer._hands_matching = lambda numbers: [(1234, 9000000123)] if 9000000123 in numbers else []

    assert viewer.find_hand("#9000000123")

    assert viewer.page == 2
    assert _shown_ids(viewer) == list(range(1201, 1251))
    selected = viewer.view.selectionModel().selectedRows(viewer.colnum["HandId"])
    assert [int(index.data()) for index in selected] == [1234]
    assert "page 3" in viewer.hand_search_status.text()
