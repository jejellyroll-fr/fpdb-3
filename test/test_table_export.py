from __future__ import annotations

import csv
import io
import os

import pytest
from PySide6.QtCore import QItemSelectionModel, QSortFilterProxyModel, Qt
from PySide6.QtGui import QKeySequence, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QApplication, QTableView

from fpdb_3_legacy import table_export
from fpdb_3_legacy.table_export import install_table_export, serialize_rows, table_text, write_table


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app


def _view(qapp) -> tuple[QTableView, QStandardItemModel]:
    view = QTableView()
    model = QStandardItemModel(2, 3, view)
    model.setHorizontalHeaderLabels(["Player", "Note", "Profit"])
    model.setItem(0, 0, QStandardItem("Élodie"))
    model.setItem(0, 1, QStandardItem("call"))
    model.setItem(0, 2, QStandardItem("1,25 €"))
    model.setItem(1, 0, QStandardItem("Alice"))
    model.setItem(1, 1, QStandardItem("raise"))
    model.setItem(1, 2, QStandardItem("-2,00 €"))
    view.setModel(model)
    return view, model


def test_copy_selection_is_rectangular_and_preserves_display_text(qapp) -> None:
    view, model = _view(qapp)
    selection = view.selectionModel()
    selection.select(model.index(0, 0), QItemSelectionModel.SelectionFlag.Select)
    selection.select(model.index(0, 2), QItemSelectionModel.SelectionFlag.Select)
    selection.select(model.index(1, 2), QItemSelectionModel.SelectionFlag.Select)

    assert table_text(view, include_headers=True) == (
        "Player\tNote\tProfit\n"
        "Élodie\t\t1,25 €\n"
        "\t\t-2,00 €\n"
    )


def test_full_export_uses_visible_column_order_and_current_proxy_sort(qapp) -> None:
    view, model = _view(qapp)
    proxy = QSortFilterProxyModel(view)
    proxy.setSourceModel(model)
    view.setModel(proxy)
    view.sortByColumn(0, Qt.SortOrder.AscendingOrder)
    view.horizontalHeader().moveSection(2, 0)
    view.setColumnHidden(1, True)

    assert table_text(view, whole_table=True, include_headers=True) == (
        "Profit\tPlayer\n"
        "-2,00 €\tAlice\n"
        "1,25 €\tÉlodie\n"
    )


def test_delimited_writer_escapes_quotes_newlines_and_unicode() -> None:
    text = serialize_rows(
        [["Player", "Note"], ["Zoë", 'said "call, then fold"\nnext line']],
        delimiter=",",
    )

    assert list(csv.reader(io.StringIO(text, newline=""))) == [
        ["Player", "Note"],
        ["Zoë", 'said "call, then fold"\nnext line'],
    ]


def test_csv_export_writes_visible_data_with_headers(tmp_path, qapp) -> None:
    view, _model = _view(qapp)
    view.setColumnHidden(1, True)
    path = tmp_path / "report.csv"

    write_table(view, path, delimiter=",")

    with path.open(encoding="utf-8", newline="") as csv_file:
        assert list(csv.reader(csv_file)) == [
            ["Player", "Profit"],
            ["Élodie", "1,25 €"],
            ["Alice", "-2,00 €"],
        ]


def test_tsv_export_writes_visible_data_with_headers(tmp_path, qapp) -> None:
    view, _model = _view(qapp)
    view.setColumnHidden(1, True)
    path = tmp_path / "report.tsv"

    write_table(view, path, delimiter="\t")

    assert path.read_text(encoding="utf-8") == (
        "Player\tProfit\n"
        "Élodie\t1,25 €\n"
        "Alice\t-2,00 €\n"
    )


def test_installed_copy_shortcut_uses_shared_export(qapp, monkeypatch) -> None:
    view, model = _view(qapp)
    selection = view.selectionModel()
    for column in range(model.columnCount()):
        selection.select(model.index(0, column), QItemSelectionModel.SelectionFlag.Select)
    install_table_export(view)
    copy_action = next(action for action in view.actions() if action.text() == "Copy")
    copied_text = []

    class Clipboard:
        def setText(self, value: str) -> None:
            copied_text.append(value)

    class FakeApplication:
        @staticmethod
        def clipboard() -> Clipboard:
            return Clipboard()

    monkeypatch.setattr(table_export, "QApplication", FakeApplication)

    assert copy_action.shortcut() == QKeySequence.StandardKey.Copy
    assert len(selection.selectedIndexes()) == 3
    copy_action.trigger()

    assert copied_text == ["Élodie\tcall\t1,25 €\n"]


def test_matrix_export_includes_vertical_row_headers(qapp) -> None:
    view, model = _view(qapp)
    model.setVerticalHeaderLabels(["BTN", "BB"])
    view.setProperty("fpdb_export_vertical_headers", True)

    assert table_text(view, whole_table=True, include_headers=True) == (
        "\tPlayer\tNote\tProfit\n"
        "BTN\tÉlodie\tcall\t1,25 €\n"
        "BB\tAlice\traise\t-2,00 €\n"
    )


def test_matrix_selection_includes_vertical_header_for_selected_rows(qapp) -> None:
    view, model = _view(qapp)
    model.setVerticalHeaderLabels(["BTN", "BB"])
    view.setProperty("fpdb_export_vertical_headers", True)
    selection = view.selectionModel()
    selection.select(model.index(1, 2), QItemSelectionModel.SelectionFlag.Select)

    assert table_text(view, include_headers=True) == (
        "\tProfit\n"
        "BB\t-2,00 €\n"
    )


def test_regular_table_export_does_not_include_vertical_headers(qapp) -> None:
    view, model = _view(qapp)
    model.setVerticalHeaderLabels(["row one", "row two"])

    assert table_text(view, whole_table=True, include_headers=True).startswith("Player\tNote\tProfit\n")
