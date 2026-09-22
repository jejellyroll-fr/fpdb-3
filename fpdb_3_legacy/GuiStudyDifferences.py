"""Qt discovery page for the largest observed Hero-versus-Field gaps (#365)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.GuiResearchBrowser import _worker_database
from fpdb_3_legacy.research_differences import (
    DifferenceFilters,
    DifferenceReport,
    DifferenceRow,
    DifferenceSelection,
    build_difference_report,
)
from fpdb_3_legacy.research_studies import StudyRegistry, builtin_studies
from fpdb_3_legacy.research_study_explorer import StudyExplorerModel
from fpdb_3_legacy.ring_stats.styles import get_theme_palette


class _SortableItem(QTableWidgetItem):
    """Keep display text while sorting numeric difference columns numerically."""

    _SORT_ROLE = Qt.ItemDataRole.UserRole + 1

    def __init__(self, text: str, sort_value: Any = None) -> None:
        super().__init__(text)
        if sort_value is not None:
            self.setData(self._SORT_ROLE, sort_value)

    def __lt__(self, other: QTableWidgetItem) -> bool:
        left = self.data(self._SORT_ROLE)
        right = other.data(self._SORT_ROLE)
        if left is not None and right is not None:
            return left < right
        return super().__lt__(other)


class _DifferencesWorker(QThread):
    """Run the bounded comparison outside the Qt event loop."""

    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, db: Any, task: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._task = task

    def run(self) -> None:
        try:
            with _worker_database(self._db) as db:
                report = self._task(db)
        except Exception as exc:  # noqa: BLE001 - worker boundary reports failures in the UI.
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(report)


class GuiStudyDifferences(QWidget):
    """Show reviewable differences without pretending they are poker verdicts."""

    study_requested = Signal(object)

    def __init__(
        self,
        config: Any = None,
        querylist: Any = None,
        mainwin: Any = None,
        db: Any = None,
        *,
        registry: StudyRegistry | None = None,
        state_path: str | Path | None = None,
    ) -> None:
        super().__init__()
        self.conf = config
        self.sql = querylist
        self.main_window = mainwin
        self.registry = registry or builtin_studies()
        self.state_path = state_path
        if db is None:
            from fpdb_3_legacy.Database import Database

            self.db = Database(config, sql=querylist)
        else:
            self.db = db
        self._worker: _DifferencesWorker | None = None
        self._report: DifferenceReport | None = None
        self._build_ui()

    def _build_ui(self) -> None:  # noqa: PLR0915 - one cohesive discovery page
        colors = get_theme_palette()
        muted = colors.get("muted_text", "#a0aec0")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)

        title = QLabel("Research · Biggest Differences vs Field")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)
        subtitle = QLabel(
            "Find the spots where your observed frequency differs most from the field, then open the study and inspect hands."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {muted};")
        layout.addWidget(subtitle)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Game"))
        self.game_combo = QComboBox()
        self.game_combo.addItem("Any", None)
        self.game_combo.addItem("Hold'em", "holdem")
        self.game_combo.addItem("Omaha", "omaha")
        controls.addWidget(self.game_combo)
        controls.addWidget(QLabel("Min Hero opportunities"))
        self.hero_sample_spin = QSpinBox()
        self.hero_sample_spin.setRange(0, 1_000_000)
        self.hero_sample_spin.setValue(20)
        controls.addWidget(self.hero_sample_spin)
        controls.addWidget(QLabel("Min Field opportunities"))
        self.field_sample_spin = QSpinBox()
        self.field_sample_spin.setRange(0, 1_000_000)
        self.field_sample_spin.setValue(20)
        controls.addWidget(self.field_sample_spin)
        self.include_low_sample = QCheckBox("Show low-sample leads")
        self.include_low_sample.setToolTip("Keep small samples visible, clearly marked for review.")
        self.include_low_sample.setChecked(False)
        controls.addWidget(self.include_low_sample)
        self.run_button = QPushButton("Find differences")
        self.run_button.clicked.connect(self.run_report)
        controls.addWidget(self.run_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.status_label = QLabel(
            "No result yet. The default minimum keeps very small samples out of the ranking."
        )
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {muted};")
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["Spot", "Context", "You", "Field", "Gap", "Your sample", "Field sample", "Review"]
        )
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.itemDoubleClicked.connect(self._open_selected)
        # The spot and the context are the two columns a reader picks a row
        # by, and both were being truncated to "SRP · PFR …" while the empty
        # space sat to the right of the last column (#371). They take the
        # slack; the numbers keep the width their own contents need.
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(False)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.open_button = QPushButton("Open selected study")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_selected)
        actions.addWidget(self.open_button)
        actions.addStretch(1)
        layout.addLayout(actions)

    def _context_filters(self) -> dict[str, Any]:
        return {"game": self.game_combo.currentData()}

    def run_report(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self.run_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.table.setRowCount(0)
        self.status_label.setText("Comparing curated study panels in the background…")
        settings = DifferenceFilters(
            context_filters=self._context_filters(),
            min_hero_sample=self.hero_sample_spin.value(),
            min_field_sample=self.field_sample_spin.value(),
            include_low_sample=self.include_low_sample.isChecked(),
        )
        worker = _DifferencesWorker(
            self.db,
            lambda db: build_difference_report(db, self.registry, settings),
            self,
        )
        worker.finished_ok.connect(self._report_done)
        worker.failed.connect(self._report_failed)
        # Qt's own slot rather than a lambda calling back into this widget: a
        # queued signal that reaches a bound method after the widget has been
        # destroyed does not raise, it takes the process down (#370).
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def _report_done(self, report: DifferenceReport) -> None:
        self._worker = None
        self._report = report
        self.run_button.setEnabled(True)
        self._render_report(report)

    def _report_failed(self, message: str) -> None:
        self._worker = None
        self.run_button.setEnabled(True)
        self.status_label.setText(f"Comparison unavailable: {message}")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming.
        """Wait for the comparison worker before Qt destroys the page."""
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.wait(30_000)
        self._worker = None
        super().closeEvent(event)

    def _render_report(self, report: DifferenceReport) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(report.rows))
        for row_index, row in enumerate(report.rows):
            values = (
                row.spot,
                row.context,
                self._format_frequency(row.hero_value_bp),
                self._format_frequency(row.field_value_bp),
                self._format_gap(row.gap_bp),
                str(row.hero_sample),
                str(row.field_sample),
                "Review sample" if row.low_sample else "Open study",
            )
            numeric_sort_values = {
                2: row.hero_value_bp,
                3: row.field_value_bp,
                4: row.score,
                5: row.hero_sample,
                6: row.field_sample,
            }
            for column, value in enumerate(values):
                item = _SortableItem(value, numeric_sort_values.get(column))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row)
                self.table.setItem(row_index, column, item)
        self.table.setSortingEnabled(True)
        # ``build_difference_report`` already sorted by review score. Make the
        # initial table order explicit after re-enabling Qt sorting; otherwise
        # QTableWidget applies its default Spot-column ordering (#365).
        self.table.sortItems(4, Qt.SortOrder.DescendingOrder)
        self.status_label.setText(
            f"{len(report.rows)} differences from {report.panels_executed} grouped panels "
            f"({report.candidates_evaluated} curated candidates). {report.heuristic_description} "
            f"Low-sample groups encountered: {report.low_sample_groups}."
        )
        self.open_button.setEnabled(bool(report.rows))

    @staticmethod
    def _format_frequency(value_bp: int) -> str:
        return f"{value_bp / 100:.1f}%"

    @staticmethod
    def _format_gap(value_bp: int) -> str:
        sign = "+" if value_bp > 0 else ""
        return f"{sign}{value_bp / 100:.1f} pp"

    def _selected_row(self) -> DifferenceRow | None:
        item = self.table.item(self.table.currentRow(), 0)
        if item is None:
            return None
        row = item.data(Qt.ItemDataRole.UserRole)
        return row if isinstance(row, DifferenceRow) else None

    def _open_selected(self, *_args: Any) -> None:
        row = self._selected_row()
        if row is None:
            return
        explorer = StudyExplorerModel(self.registry, self.state_path)
        selection = explorer.open_study(row.study_id, context_filters=row.context_filters)
        self.study_requested.emit(
            DifferenceSelection(
                selection=selection,
                panel_id=row.panel_id,
                cross_filters=row.cross_filters,
                row=row,
            )
        )


__all__ = ["GuiStudyDifferences"]
