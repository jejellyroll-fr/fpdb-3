"""Qt dashboard for one synchronized Poker Study (#361)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.GuiResearchBrowser import _worker_database
from fpdb_3_legacy.research_study_dashboard import (
    COMPARISON_FIELD,
    COMPARISON_HERO,
    COMPARISON_HERO_VS_FIELD,
    CrossFilter,
    DashboardComparison,
    StudyDashboardModel,
)
from fpdb_3_legacy.research_study_explorer import StudySelection
from fpdb_3_legacy.ring_stats.styles import get_theme_palette


class _DashboardWorker(QThread):
    """Execute one lazy panel away from the Qt event loop."""

    finished_ok = Signal(object, int, str)
    failed = Signal(str, int, str)

    def __init__(self, db: Any, task: Any, serial: int, fingerprint: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._task = task
        self._serial = serial
        self._fingerprint = fingerprint

    def run(self) -> None:
        try:
            with _worker_database(self._db) as db:
                result = self._task(db)
        except Exception as exc:  # noqa: BLE001 - worker boundary reports failures in the UI.
            self.failed.emit(str(exc), self._serial, self._fingerprint)
            return
        self.finished_ok.emit(result, self._serial, self._fingerprint)


class GuiStudyDashboard(QWidget):
    """A study page whose panels all inherit the same canonical population."""

    def __init__(
        self,
        config: Any = None,
        querylist: Any = None,
        mainwin: Any = None,
        db: Any = None,
        *,
        selection: StudySelection | None = None,
        model: StudyDashboardModel | None = None,
    ) -> None:
        super().__init__()
        if model is None and selection is None:
            raise ValueError("GuiStudyDashboard needs a StudySelection or StudyDashboardModel")
        self.conf = config
        self.sql = querylist
        self.main_window = mainwin
        self.model = model or StudyDashboardModel(selection)  # type: ignore[arg-type]
        if db is None:
            from fpdb_3_legacy.Database import Database

            self.db = Database(config, sql=querylist)
            self._owns_db = True
        else:
            self.db = db
            self._owns_db = False
        self._serial = 0
        self._workers: list[_DashboardWorker] = []
        self._results: dict[str, Any] = {}
        self._pages: dict[str, tuple[QLabel, QTableWidget]] = {}
        self._variable_edits: dict[str, QLineEdit] = {}
        self._build_ui()
        self._load_active_panel()

    def _build_ui(self) -> None:  # noqa: PLR0915 - one cohesive dashboard widget tree
        colors = get_theme_palette()
        muted = colors.get("muted_text", "#a0aec0")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)

        self.title_label = QLabel(self.model.study.title)
        self.title_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(self.title_label)
        path = "  ›  ".join(self._segment_label(segment) for segment in self.model.study.path)
        self.breadcrumb_label = QLabel(f"{path}  ›  {self.model.study.title}" if path else self.model.study.title)
        self.breadcrumb_label.setStyleSheet(f"color: {muted}; font-size: 11px;")
        layout.addWidget(self.breadcrumb_label)
        self.context_label = QLabel(self._context_text())
        self.context_label.setWordWrap(True)
        self.context_label.setStyleSheet(f"color: {muted};")
        layout.addWidget(self.context_label)

        if self.model.study.variables:
            variables_box = QGroupBox("Study variables")
            variables_layout = QFormLayout(variables_box)
            for name in self.model.study.variables:
                edit = QLineEdit()
                edit.setText(str(self.model.state.variable_values.get(name, "")))
                edit.setPlaceholderText("Any")
                edit.setToolTip("This choice is applied to every compatible panel.")
                self._variable_edits[name] = edit
                variables_layout.addRow(name.replace("_", " ").title(), edit)
            apply_variables = QPushButton("Apply variables")
            apply_variables.clicked.connect(self._apply_variables)
            variables_layout.addRow(apply_variables)
            layout.addWidget(variables_box)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Compare"))
        self.comparison_combo = QComboBox()
        self.comparison_combo.addItem("Hero only", COMPARISON_HERO)
        self.comparison_combo.addItem("Field only", COMPARISON_FIELD)
        self.comparison_combo.addItem("Hero vs Field", COMPARISON_HERO_VS_FIELD)
        self.comparison_combo.setCurrentIndex(self.comparison_combo.findData(self.model.state.comparison))
        self.comparison_combo.currentIndexChanged.connect(self._comparison_changed)
        controls.addWidget(self.comparison_combo)
        self.sample_label = QLabel(self._sample_threshold_text())
        self.sample_label.setStyleSheet("font-weight: bold;")
        controls.addWidget(self.sample_label)
        controls.addStretch(1)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        controls.addWidget(self.refresh_button)
        layout.addLayout(controls)

        self.filter_row = QHBoxLayout()
        self.filter_row.addWidget(QLabel("Active cross-filters:"))
        self.filter_row.addStretch(1)
        layout.addLayout(self.filter_row)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._panel_changed)
        for panel in self.model.study.panels:
            page = QWidget()
            page.setProperty("panel_id", panel.id)
            page_layout = QVBoxLayout(page)
            status = QLabel("Not loaded yet — this panel is loaded when opened.")
            status.setWordWrap(True)
            table = QTableWidget()
            table.setSortingEnabled(True)
            table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.verticalHeader().hide()
            table.itemDoubleClicked.connect(self._row_double_clicked)
            page_layout.addWidget(status)
            page_layout.addWidget(table, 1)
            self._pages[panel.id] = (status, table)
            index = self.tabs.addTab(page, panel.title)
            try:
                compiled = self.model.panel(panel.id)
            except (ValueError, KeyError) as exc:
                self.tabs.setTabEnabled(index, False)
                self.tabs.setTabToolTip(index, str(exc))
                status.setText(f"Unavailable: {exc}")
                continue
            if not compiled.available:
                self.tabs.setTabEnabled(index, False)
                self.tabs.setTabToolTip(index, compiled.unavailable_reason or "Panel unavailable")
                status.setText(f"Unavailable: {compiled.unavailable_reason}")
        self._render_cross_filters()

    @staticmethod
    def _segment_label(segment: str) -> str:
        return segment.replace("-", " ").title()

    def _context_text(self) -> str:
        filters = self.model.base_filters
        context = ", ".join(f"{name}={value}" for name, value in sorted(filters.items()))
        variables = ", ".join(
            f"{name}={value}" for name, value in sorted(self.model.state.variable_values.items())
        )
        return f"Population: {context or 'all matching hands'}" + (f" · Variables: {variables}" if variables else "")

    def _sample_threshold_text(self) -> str:
        minimum = self.model.state.min_sample
        return f"Minimum sample: {minimum}" if minimum else "Minimum sample: none"

    def _comparison_changed(self) -> None:
        comparison = str(self.comparison_combo.currentData())
        self.model.set_comparison(comparison)
        self.refresh()

    def _apply_variables(self) -> None:
        try:
            for name, edit in self._variable_edits.items():
                self.model.set_variable(name, self._parse_variable(name, edit.text()))
        except ValueError as exc:
            self.context_label.setText(f"Variable error: {exc}")
            return
        self.refresh()

    @staticmethod
    def _parse_variable(name: str, value: str) -> Any:
        text = value.strip()
        if not text:
            return None
        if name in {"effective_stack_bb", "stake_bb"} and "," in text:
            values = [float(part.strip()) for part in text.split(",") if part.strip()]
            if len(values) == 1:
                return [values[0], None]
            return [values[0], values[1]]
        if name == "in_position" and text.casefold() in {"true", "yes", "1"}:
            return True
        if name == "in_position" and text.casefold() in {"false", "no", "0"}:
            return False
        return text

    def _panel_changed(self, index: int) -> None:
        if index < 0:
            return
        page = self.tabs.widget(index)
        if page is None:
            return
        panel_id = str(page.property("panel_id") or "")
        if panel_id in self.model.panel_ids():
            self.model.set_active_panel(panel_id)
            self._load_active_panel()

    def _load_active_panel(self) -> None:
        panel_id = self.model.state.active_panel
        index = self.tabs.indexOf(self._pages[panel_id][0].parentWidget())
        if index >= 0 and self.tabs.currentIndex() != index:
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(index)
            self.tabs.blockSignals(False)
        self._run_panel(panel_id)

    def _run_panel(self, panel_id: str) -> None:
        fingerprint = self.model.fingerprint(panel_id)
        status, table = self._pages[panel_id]
        if fingerprint in self._results:
            self._render_result(panel_id, self._results[fingerprint])
            return
        status.setText("Loading panel…")
        table.setRowCount(0)
        self._serial += 1
        serial = self._serial
        worker = _DashboardWorker(
            self.db,
            lambda db: self.model.execute_panel(db, panel_id),
            serial,
            fingerprint,
            self,
        )
        worker.finished_ok.connect(self._panel_done)
        worker.failed.connect(self._panel_failed)
        worker.finished.connect(lambda worker=worker: self._retire_worker(worker))
        self._workers.append(worker)
        worker.start()

    def _panel_done(self, result: Any, serial: int, fingerprint: str) -> None:
        if serial != self._serial:
            return
        panel_id = self.model.state.active_panel
        self._results[fingerprint] = result
        self._render_result(panel_id, result)

    def _panel_failed(self, message: str, serial: int, fingerprint: str) -> None:
        if serial != self._serial:
            return
        panel_id = self.model.state.active_panel
        status, table = self._pages[panel_id]
        table.setRowCount(0)
        status.setText(f"Panel unavailable: {message}")

    def _retire_worker(self, worker: _DashboardWorker) -> None:
        if worker in self._workers:
            self._workers.remove(worker)
        worker.deleteLater()

    def refresh(self) -> None:
        self._serial += 1
        self.model.invalidate_cache()
        self._results.clear()
        self.context_label.setText(self._context_text())
        self._render_cross_filters()
        self._load_active_panel()

    def add_cross_filter(self, name: str, value: Any, label: str | None = None) -> CrossFilter:
        cross_filter = self.model.add_cross_filter(name, value, label)
        self._results.clear()
        self._render_cross_filters()
        self._load_active_panel()
        return cross_filter

    def remove_cross_filter(self, name: str) -> None:
        self.model.remove_cross_filter(name)
        self._results.clear()
        self._render_cross_filters()
        self._load_active_panel()

    def _render_cross_filters(self) -> None:
        while self.filter_row.count() > 1:
            item = self.filter_row.takeAt(1)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for cross_filter in self.model.state.cross_filters:
            button = QPushButton(f"{cross_filter.label} ×")
            button.clicked.connect(lambda _checked=False, name=cross_filter.name: self.remove_cross_filter(name))
            self.filter_row.insertWidget(self.filter_row.count() - 1, button)

    def _render_result(self, panel_id: str, result: Any) -> None:
        status, table = self._pages[panel_id]
        rows = self._rows(result)
        columns = sorted({key for row in rows for key in row})
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, column in enumerate(columns):
                item = QTableWidgetItem(self._display(row.get(column)))
                if column in self._group_by(panel_id):
                    item.setData(Qt.ItemDataRole.UserRole, {column: row.get(column)})
                table.setItem(row_index, column_index, item)
        table.resizeColumnsToContents()
        sample = self._sample_text(result)
        self.sample_label.setText(sample)
        note = " No matching hands for this context." if "0 decisions" in sample else ""
        status.setText(f"{sample}.{note} Double-click a grouped value to add a temporary cross-filter.")

    def _row_double_clicked(self, item: QTableWidgetItem) -> None:
        group = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(group, dict) or not group:
            return
        name, value = next(iter(group.items()))
        self.add_cross_filter(name, value, f"{name}: {value}")

    def _group_by(self, panel_id: str) -> tuple[str, ...]:
        return self.model.panel_query(panel_id).group_by

    @classmethod
    def _rows(cls, result: Any) -> list[dict[str, Any]]:
        if isinstance(result, DashboardComparison):
            return [
                {"side": "Hero", **row}
                for row in cls._single_rows(result.hero)
            ] + [
                {"side": "Field", **row}
                for row in cls._single_rows(result.field)
            ]
        return cls._single_rows(result)

    @classmethod
    def _single_rows(cls, result: Any) -> list[dict[str, Any]]:
        if hasattr(result, "as_dicts"):
            return list(result.as_dicts())
        if hasattr(result, "every_cell"):
            return [cell.as_dict() for cell in result.every_cell()]
        if hasattr(result, "rows"):
            rows = result.rows
            return [row.as_dict() if hasattr(row, "as_dict") else dict(row) for row in rows]
        if hasattr(result, "total") and hasattr(result.total, "as_dict"):
            rows = [row.as_dict() if hasattr(row, "as_dict") else dict(row) for row in result.rows]
            rows.append({"row": "total", **result.total.as_dict()})
            return rows
        return []

    @staticmethod
    def _sample_text(result: Any) -> str:
        if isinstance(result, DashboardComparison):
            return f"Hero: {GuiStudyDashboard._sample_text(result.hero)} · Field: {GuiStudyDashboard._sample_text(result.field)}"
        if hasattr(result, "total_opportunities"):
            return f"{result.total_opportunities} decisions"
        if hasattr(result, "total") and hasattr(result.total, "opportunities"):
            return f"{result.total.opportunities} decisions"
        if hasattr(result, "total_matches"):
            return f"{result.total_matches} matching hands"
        return "Result loaded"

    @staticmethod
    def _display(value: Any) -> str:
        if value is None:
            return "—"
        if isinstance(value, float):
            return f"{value:g}"
        return str(value)


__all__ = ["GuiStudyDashboard"]
