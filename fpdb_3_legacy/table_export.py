"""Reusable clipboard and delimited-file exports for Qt item views."""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable, Sequence
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QTableView

from fpdb_3_legacy.i18n import gettext as _

_NUMERIC_CELL = re.compile(
    r"^[+-]?(?:\d+(?:[.,]\d+)?|\d{1,3}(?:[ ,.'’]\d{3})+(?:[.,]\d+)?)(?:\s*(?:[%€$£¥¢]|BB|bb))?$"
)


def spreadsheet_safe_value(value: str) -> str:
    """Prevent spreadsheet formula evaluation without changing formatted numbers."""
    stripped = value.lstrip()
    if not stripped or stripped[0] not in "=+-@":
        return value
    if stripped[0] in "+-" and _NUMERIC_CELL.fullmatch(stripped):
        return value
    return "'" + value


def append_extension(path: str | Path, extension: str) -> str:
    """Ensure the selected export path has the requested suffix."""
    result = str(path)
    return result if result.lower().endswith(f".{extension.lower()}") else f"{result}.{extension}"


def serialize_rows(rows: Iterable[Sequence[str]], *, delimiter: str) -> str:
    """Serialize rows with CSV escaping, including for clipboard TSV."""
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=delimiter, lineterminator="\n")
    writer.writerows([spreadsheet_safe_value(value) for value in row] for row in rows)
    return stream.getvalue()


def visible_column_order(view: QTableView) -> list[int]:
    """Return visible model columns in the order currently shown by the view."""
    header = view.horizontalHeader()
    return [
        header.logicalIndex(visual)
        for visual in range(header.count())
        if not view.isColumnHidden(header.logicalIndex(visual))
    ]


def table_text(
    view: QTableView,
    *,
    include_headers: bool = False,
    whole_table: bool = False,
    delimiter: str = "\t",
) -> str:
    """Build displayed-value text for a selection or the visible whole table."""
    model = view.model()
    if model is None:
        return ""
    include_row_headers = bool(view.property("fpdb_export_vertical_headers"))

    visible = visible_column_order(view)
    selection = view.selectionModel()
    selected = set(selection.selectedIndexes()) if selection is not None else set()
    if whole_table:
        row_numbers = list(range(model.rowCount()))
        columns = visible
    else:
        if not selected:
            return ""
        selected_rows = [index.row() for index in selected]
        selected_columns = [visible.index(index.column()) for index in selected if index.column() in visible]
        if not selected_columns:
            return ""
        first_row, last_row = min(selected_rows), max(selected_rows)
        first_column, last_column = min(selected_columns), max(selected_columns)
        row_numbers = list(range(first_row, last_row + 1))
        columns = visible[first_column : last_column + 1]

    rows: list[list[str]] = []
    if include_headers:
        horizontal_headers = [
            str(model.headerData(column, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) or "")
            for column in columns
        ]
        rows.append(([""] if include_row_headers else []) + horizontal_headers)

    for row in row_numbers:
        values: list[str] = []
        if include_row_headers:
            row_header = model.headerData(row, Qt.Orientation.Vertical, Qt.ItemDataRole.DisplayRole)
            values.append("" if row_header is None else str(row_header))
        for column in columns:
            index = model.index(row, column)
            if not whole_table and index not in selected:
                values.append("")
                continue
            value = index.data(Qt.ItemDataRole.DisplayRole)
            values.append("" if value is None else str(value))
        rows.append(values)

    return serialize_rows(rows, delimiter=delimiter)


def copy_table_selection(
    view: QTableView,
    *,
    include_headers: bool = False,
    whole_table: bool = False,
) -> str:
    """Copy a rectangular, displayed-value TSV representation to the clipboard."""
    text = table_text(view, include_headers=include_headers, whole_table=whole_table)
    if text:
        QApplication.clipboard().setText(text)
    return text


def write_table(view: QTableView, path: str | Path, *, delimiter: str, include_headers: bool = True) -> None:
    """Write the currently visible, sorted table using the standard CSV writer."""
    text = table_text(view, include_headers=include_headers, whole_table=True, delimiter=delimiter)
    Path(path).write_text(text, encoding="utf-8", newline="")


def confirm_overwrite(view: QTableView, path: str | Path) -> bool:
    """Ask before replacing the final export path, including an appended suffix."""
    if not Path(path).exists():
        return True
    answer = QMessageBox.question(
        view,
        _("Confirm overwrite"),
        _("The file already exists:\n%s\nDo you want to replace it?") % path,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


def install_table_export(view: QTableView) -> None:
    """Install copy shortcuts and an export context menu on a table view.

    Exports intentionally use displayed values: this avoids silently mixing raw
    database values with localized display formatting.
    """
    if getattr(view, "_fpdb_table_export_installed", False):
        return
    view._fpdb_table_export_installed = True
    view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    copy_action = QAction(_("Copy"), view)
    copy_action.setShortcut(QKeySequence.StandardKey.Copy)
    copy_action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
    copy_action.triggered.connect(lambda: copy_table_selection(view))
    view.addAction(copy_action)

    def export_file(delimiter: str, extension: str, label: str) -> None:
        path, _selected_filter = QFileDialog.getSaveFileName(
            view,
            _("Export displayed values"),
            f"{label.lower()}-export.{extension}",
            f"{label} (*.{extension})",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not path:
            return
        path = append_extension(path, extension)
        if not confirm_overwrite(view, path):
            return
        try:
            write_table(view, path, delimiter=delimiter)
        except OSError as exc:
            QMessageBox.warning(view, _("Export failed"), str(exc))

    def show_menu(position) -> None:
        from PySide6.QtWidgets import QMenu

        menu = QMenu(view)
        for label, headers, whole in (
            (_("Copy"), False, False),
            (_("Copy with headers"), True, False),
            (_("Copy entire table"), False, True),
            (_("Copy entire table with headers"), True, True),
        ):
            action = menu.addAction(label)
            action.triggered.connect(
                lambda _checked=False, headers=headers, whole=whole: copy_table_selection(
                    view,
                    include_headers=headers,
                    whole_table=whole,
                )
            )
        menu.addSeparator()
        for label, delimiter, extension in (("CSV", ",", "csv"), ("TSV", "\t", "tsv")):
            action = menu.addAction(_("Export displayed values as %s…") % label)
            action.triggered.connect(
                lambda _checked=False, delimiter=delimiter, extension=extension, label=label: export_file(
                    delimiter,
                    extension,
                    label,
                )
            )
        menu.exec(view.viewport().mapToGlobal(position))

    view.customContextMenuRequested.connect(show_menu)
