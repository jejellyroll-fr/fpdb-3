"""Qt matrix and heatmap widgets for Research (#363)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.table_export import install_table_export

from .research_matrices import MatrixCell, MatrixSeries
from .ring_stats.styles import get_theme_palette


class MatrixHeatmapWidget(QWidget):
    """A numeric, clickable heatmap that never hides the exact sample."""

    cell_clicked = Signal(str, object, str, object, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hero: MatrixSeries | None = None
        self._field: MatrixSeries | None = None
        self._row_values: tuple[Any, ...] = ()
        self._column_values: tuple[Any, ...] = ()
        self._cells: dict[tuple[Any, Any], MatrixCell] = {}
        self._field_cells: dict[tuple[Any, Any], MatrixCell] = {}

        palette = get_theme_palette()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        self.summary_label = QLabel("No matrix loaded")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(f"color: {palette.get('muted_text', '#a0aec0')};")
        layout.addWidget(self.summary_label)
        self.table = QTableWidget()
        # Matrix categories are rendered in the vertical header, not as cells.
        self.table.setProperty("fpdb_export_vertical_headers", True)
        install_table_export(self.table)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self.table.verticalHeader().setVisible(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(54)
        self.table.cellClicked.connect(self._cell_clicked)
        layout.addWidget(self.table)

    def set_series(self, series: MatrixSeries) -> None:
        self._hero = series
        self._field = None
        self._row_values = series.rows
        self._column_values = series.columns
        self._cells = {(cell.row_key, cell.column_key): cell for cell in series.cells}
        self._field_cells = {}
        self._render()

    def set_comparison(self, hero: MatrixSeries, field: MatrixSeries) -> None:
        self._hero = hero
        self._field = field
        self._row_values = tuple(dict.fromkeys((*hero.rows, *field.rows)))
        self._column_values = tuple(dict.fromkeys((*hero.columns, *field.columns)))
        self._cells = {(cell.row_key, cell.column_key): cell for cell in hero.cells}
        self._field_cells = {(cell.row_key, cell.column_key): cell for cell in field.cells}
        self._render()

    def clear_matrix(self) -> None:
        self._hero = None
        self._field = None
        self._row_values = ()
        self._column_values = ()
        self._cells = {}
        self._field_cells = {}
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.summary_label.setText("No matrix loaded")

    def click_cell(self, row_index: int, column_index: int) -> None:
        """Activate a cell programmatically for keyboard and UI tests."""
        if 0 <= row_index < len(self._row_values) and 0 <= column_index < len(self._column_values):
            self._cell_clicked(row_index, column_index)

    def _render(self) -> None:
        self.table.clear()
        self.table.setRowCount(len(self._row_values))
        self.table.setColumnCount(len(self._column_values))
        if not self._row_values or not self._column_values:
            self.summary_label.setText("No classified cells for this context.")
            return

        label_cells = {**self._field_cells, **self._cells}
        row_labels = [self._label_for(label_cells, row) for row in self._row_values]
        column_labels = [self._label_for(label_cells, column, axis="column") for column in self._column_values]
        self.table.setVerticalHeaderLabels(row_labels)
        self.table.setHorizontalHeaderLabels(column_labels)
        max_value = self._max_value()
        for row_index, row_key in enumerate(self._row_values):
            for column_index, column_key in enumerate(self._column_values):
                hero = self._cells.get((row_key, column_key))
                field = self._field_cells.get((row_key, column_key))
                cell = hero or field or self._empty_cell(row_key, column_key)
                item = QTableWidgetItem(self._cell_text(hero, field, cell))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setToolTip(self._tooltip(hero, field, cell))
                item.setData(Qt.ItemDataRole.AccessibleTextRole, self._tooltip(hero, field, cell))
                item.setBackground(self._background(hero, field, max_value))
                if self._field is not None:
                    gap = (hero.metric_value if hero else 0) - (field.metric_value if field else 0)
                    sample_cell = hero or field
                    if gap and sample_cell is not None and sample_cell.sample_sufficient:
                        item.setForeground(QColor("#68d391" if gap > 0 else "#fc8181"))
                self.table.setItem(row_index, column_index, item)

        warnings = len(self._low_sample_cells())
        comparison = "Hero / Field / Gap" if self._field is not None else "one population"
        cell_guide = "Cells show H / F then gap." if self._field is not None else "Cells show measure and sample size."
        unknown = " Unknown cells are shown separately." if self._has_unknown() else ""
        warning_text = f" {warnings} low-sample cells." if warnings else ""
        self.summary_label.setText(
            f"{comparison}; {cell_guide} Hover for exact values and sample; "
            f"click to filter the matchup.{warning_text}{unknown}"
        )

    def _cell_clicked(self, row_index: int, column_index: int) -> None:
        if not (0 <= row_index < len(self._row_values) and 0 <= column_index < len(self._column_values)):
            return
        row_key = self._row_values[row_index]
        column_key = self._column_values[column_index]
        cell = self._cells.get((row_key, column_key)) or self._field_cells.get((row_key, column_key))
        if cell is None:
            return
        self.cell_clicked.emit(
            cell.filter_names[0],
            cell.row_key,
            cell.filter_names[1],
            cell.column_key,
            f"{cell.row_label} × {cell.column_label}",
        )

    def _empty_cell(self, row_key: Any, column_key: Any) -> MatrixCell:
        template = next(iter(self._cells.values()), None)
        if template is None:
            template = next(iter(self._field_cells.values()), None)
        if template is None:
            raise RuntimeError("matrix has no vocabulary template")
        return MatrixCell(
            row_key=row_key,
            column_key=column_key,
            row_label=str(row_key),
            column_label=str(column_key),
            opportunities=0,
            actions=0,
            value=None,
            unit=template.unit,
            frequency_bp=0 if template.frequency_bp is not None else None,
            filter_names=template.filter_names,
            min_sample=template.min_sample,
        )

    @staticmethod
    def _label_for(cells: dict[tuple[Any, Any], MatrixCell], key: Any, axis: str = "row") -> str:
        for cell in cells.values():
            if (cell.row_key if axis == "row" else cell.column_key) == key:
                return cell.row_label if axis == "row" else cell.column_label
        return "Unknown / unclassified" if key is None else str(key)

    def _cell_text(self, hero: MatrixCell | None, field: MatrixCell | None, fallback: MatrixCell) -> str:
        if self._field is None:
            return f"{fallback.metric_label}\nn={fallback.opportunities}"
        hero_text = hero.metric_label if hero else "—"
        field_text = field.metric_label if field else "—"
        gap = (hero.metric_value if hero else 0) - (field.metric_value if field else 0)
        gap_unit = " pp" if fallback.percentage is not None else ""
        return f"H {hero_text} · F {field_text}\nΔ {gap:+.1f}{gap_unit}"

    def _tooltip(self, hero: MatrixCell | None, field: MatrixCell | None, cell: MatrixCell) -> str:
        lines = [f"{cell.row_label} × {cell.column_label}"]
        for label, side in (("Hero", hero), ("Field", field)):
            if side is None:
                continue
            low = " — low sample" if not side.sample_sufficient and side.opportunities else ""
            lines.append(
                f"{label}: {side.exact_metric_label}; opportunities={side.opportunities}; "
                f"numerator={side.actions}{low}",
            )
        lines.append("Click to add both axis values as Study cross-filters.")
        return "\n".join(lines)

    def _max_value(self) -> float:
        values = [cell.metric_value for cell in (*self._cells.values(), *self._field_cells.values())]
        return max(values, default=1.0)

    def _background(
        self,
        hero: MatrixCell | None,
        field: MatrixCell | None,
        max_value: float,
    ) -> QColor:
        if self._field is not None:
            gap = (hero.metric_value if hero else 0) - (field.metric_value if field else 0)
            strength = min(1.0, abs(gap) / max(max_value, 1.0))
            base = QColor("#2f855a" if gap >= 0 else "#c05640")
        else:
            strength = min(1.0, (hero.metric_value if hero else 0) / max(max_value, 1.0))
            base = QColor("#2c7a7b")
        sample_cell = hero or field
        if sample_cell is not None and not sample_cell.sample_sufficient and sample_cell.opportunities:
            base = QColor("#718096")
            strength = 0.35
        base.setAlpha(80 + int(150 * strength))
        return base

    def _low_sample_cells(self) -> tuple[MatrixCell, ...]:
        cells = [cell for cell in (*self._cells.values(), *self._field_cells.values()) if cell.opportunities]
        return tuple(cell for cell in cells if not cell.sample_sufficient)

    def _has_unknown(self) -> bool:
        return any(
            cell.is_unknown and cell.opportunities
            for cell in (*self._cells.values(), *self._field_cells.values())
        )


__all__ = ["MatrixHeatmapWidget"]
