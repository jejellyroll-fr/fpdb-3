"""Qt dashboard for one synchronized Poker Study (#361)."""

from __future__ import annotations

import contextlib
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

from fpdb_3_legacy.GuiDrillDown import SourceHandsPane, live_workers
from fpdb_3_legacy.GuiResearchDistributions import DistributionChartWidget
from fpdb_3_legacy.GuiResearchHandStrength import HandStrengthChartWidget
from fpdb_3_legacy.GuiResearchMatrices import MatrixHeatmapWidget
from fpdb_3_legacy.research_distributions import build_distribution
from fpdb_3_legacy.research_drilldown import SIDE_FIELD, SIDE_HERO
from fpdb_3_legacy.research_matrices import POSITION_LABELS, build_matrix
from fpdb_3_legacy.research_study_dashboard import (
    COMPARISON_FIELD,
    COMPARISON_HERO,
    COMPARISON_HERO_VS_FIELD,
    CrossFilter,
    DashboardComparison,
    StudyDashboardModel,
)
from fpdb_3_legacy.research_study_explorer import StudySelection
from fpdb_3_legacy.research_worker_db import worker_database
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
            with worker_database(self._db) as db:
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
        self._distribution_widgets: dict[str, DistributionChartWidget] = {}
        self._matrix_widgets: dict[str, MatrixHeatmapWidget] = {}
        self._hand_strength_widgets: dict[str, HandStrengthChartWidget] = {}
        self._variable_edits: dict[str, QLineEdit] = {}
        self._replayers: list[Any] = []
        self._stack_note: str | None = None
        self._build_ui()
        self._load_active_panel()

    def _build_ui(self) -> None:  # noqa: C901, PLR0915 - one cohesive dashboard widget tree
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

        # Its own line rather than a clause on the sample text: an answer that
        # averages twelve big blinds with sixty is not a footnote about
        # precision, it is a headline about two different games (#369).
        self.stack_note_label = QLabel("")
        self.stack_note_label.setWordWrap(True)
        self.stack_note_label.setVisible(False)
        self.stack_note_label.setStyleSheet("color: #e5c07b; font-weight: bold;")
        layout.addWidget(self.stack_note_label)

        # Built before the tabs, because adding the first tab fires
        # ``currentChanged`` and the panel that loads immediately re-points
        # the hands pane.
        self.source_hands = SourceHandsPane(self.db, self)
        self.source_hands.hand_activated.connect(self._open_in_replayer)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._panel_changed)
        # Adding the first tab emits ``currentChanged``, and the slot writes
        # the active panel back to the model -- so building the tab strip used
        # to overwrite whichever panel the study declared as its default with
        # whichever one happened to be built first (#369).
        self.tabs.blockSignals(True)
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
            if panel.kind in {"sizing_distribution", "response_distribution"}:
                chart = DistributionChartWidget()
                chart.bin_clicked.connect(self._distribution_bin_clicked)
                self._distribution_widgets[panel.id] = chart
                page_layout.addWidget(chart)
            elif panel.kind in {"position_matrix", "board_matrix"}:
                if len(panel.group_by) == 1:
                    chart = DistributionChartWidget()
                    chart.bin_clicked.connect(self._distribution_bin_clicked)
                    self._distribution_widgets[panel.id] = chart
                    page_layout.addWidget(chart)
                elif len(panel.group_by) == 2:
                    matrix = MatrixHeatmapWidget()
                    matrix.cell_clicked.connect(self._matrix_cell_clicked)
                    self._matrix_widgets[panel.id] = matrix
                    page_layout.addWidget(matrix)
            elif panel.kind == "hand_strength":
                chart = HandStrengthChartWidget()
                chart.dimension_changed.connect(
                    lambda dimension, panel_id=panel.id: self._hand_strength_dimension_changed(
                        panel_id, dimension,
                    ),
                )
                chart.category_clicked.connect(self._hand_strength_category_clicked)
                self._hand_strength_widgets[panel.id] = chart
                page_layout.addWidget(chart)
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
        self.tabs.blockSignals(False)
        layout.addWidget(self.tabs, 1)
        # The hands live below every panel rather than inside one: a selection
        # made on a chart and a row picked from a table are the same question
        # about the same population, and the reader should not have to find a
        # different place to ask it (#366).
        layout.addWidget(self.source_hands, 1)
        self._render_cross_filters()

    def _refresh_drill_context(self) -> None:
        """Point the hands pane at whatever the dashboard is currently showing.

        Both sides come from the panel's own query, so every narrowing the
        page carries -- the study population, the variables, each visible
        cross-filter -- reaches Hero and Field identically, and they differ in
        the population identity alone.
        """
        panel_id = self.model.state.active_panel
        try:
            context = self.model.drill_context(panel_id)
        except (ValueError, KeyError) as exc:
            self.source_hands.clear(f"Source hands unavailable: {exc}")
            return
        side = SIDE_FIELD if self.model.state.comparison == COMPARISON_FIELD else SIDE_HERO
        self.source_hands.set_context(context, default_side=side)

    def _open_in_replayer(self, hand_id: int) -> None:
        """Double-click a source hand: the existing replayer, unchanged."""
        try:
            from fpdb_3_legacy import GuiReplayer

            replayer = GuiReplayer.GuiReplayer(
                self.conf, self.sql, self.main_window, [int(hand_id)], db=self.db,
            )
            replayer.play_hand(0)
            replayer.raise_()
            replayer.activateWindow()
            self._replayers.append(replayer)
        except Exception as exc:  # noqa: BLE001 - a replayer failure must not break the study.
            self.source_hands.note_label.setText(f"Unable to open hand {hand_id}: {exc}")

    def shutdown_workers(self) -> None:
        """Stop dashboard and source-hand queries before tab destruction.

        ``fpdb.close_tab`` removes a page from the tab widget and calls this
        hook directly; removed child widgets do not receive ``closeEvent``.
        """
        self.source_hands.stop()
        for worker in live_workers(self._workers):
            if worker.isRunning() and not worker.wait(SourceHandsPane.SHUTDOWN_WAIT_MS):
                worker.wait()
        self._workers.clear()

    def close_owned_database(self) -> None:
        """Release the connection created for this tab."""
        if self._owns_db and self.db is not None:
            with contextlib.suppress(Exception):
                self.db.disconnect()
            self._owns_db = False

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming.
        """Delegate native closes to the same hooks used by tab removal."""
        self.shutdown_workers()
        self.close_owned_database()
        super().closeEvent(event)

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
    def _parse_numeric_range(text: str, converter: Any, multiplier: Any = 1) -> Any:
        values = [converter(part.strip()) * multiplier for part in text.split(",") if part.strip()]
        if len(values) == 1:
            return [values[0], values[0]]
        if not values:
            return None
        return [values[0], values[1]]

    @staticmethod
    def _parse_variable(name: str, value: str) -> Any:
        text = value.strip()
        if not text:
            return None
        if name in {"effective_stack_bb", "stake_bb"}:
            multiplier = 100 if name == "effective_stack_bb" else 1
            return GuiStudyDashboard._parse_numeric_range(text, float, multiplier)
        if name == "max_seats":
            return GuiStudyDashboard._parse_numeric_range(text, int)
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
        # Every route into a panel comes through here -- opening a tab,
        # applying a variable, adding or removing a cross-filter -- so the
        # hands pane is re-pointed once, where the panel itself is.
        self._refresh_drill_context()
        self._run_panel(panel_id)

    def _run_panel(self, panel_id: str) -> None:
        fingerprint = self.model.fingerprint(panel_id)
        status, table = self._pages[panel_id]
        if fingerprint in self._results:
            result, self._stack_note = self._results[fingerprint]
            self._render_result(panel_id, result)
            return
        status.setText("Loading panel…")
        self.stack_note_label.setVisible(False)
        table.setRowCount(0)
        if panel_id in self._distribution_widgets:
            self._distribution_widgets[panel_id].clear_distribution()
        if panel_id in self._matrix_widgets:
            self._matrix_widgets[panel_id].clear_matrix()
        if panel_id in self._hand_strength_widgets:
            self._hand_strength_widgets[panel_id].clear_distribution()
        self._serial += 1
        serial = self._serial
        worker = _DashboardWorker(
            self.db,
            # The stack-depth check rides with the panel rather than costing a
            # second round trip: it is one grouped count, and only a
            # tournament study asks for it at all (#369).
            lambda db: (
                self.model.execute_panel(db, panel_id),
                self.model.stack_depth_note(
                    db,
                    panel_id,
                    hero={COMPARISON_HERO: True, COMPARISON_FIELD: False}.get(
                        self.model.state.comparison,
                    ),
                ),
            ),
            serial,
            fingerprint,
            self,
        )
        worker.finished_ok.connect(self._panel_done)
        worker.failed.connect(self._panel_failed)
        # Qt's own slot, not a lambda that calls back into this widget: a
        # queued signal arriving after the dashboard is destroyed does not
        # raise, it takes the process down. The list is pruned here, where
        # the widget is certainly alive.
        worker.finished.connect(worker.deleteLater)
        self._workers = [
            running for running in live_workers(self._workers) if running.isRunning()
        ]
        self._workers.append(worker)
        worker.start()

    def _panel_done(self, payload: Any, serial: int, fingerprint: str) -> None:
        if serial != self._serial or fingerprint != self.model.fingerprint(self.model.state.active_panel):
            return
        panel_id = self.model.state.active_panel
        result, self._stack_note = payload
        self._results[fingerprint] = payload
        self._render_result(panel_id, result)

    def _panel_failed(self, message: str, serial: int, fingerprint: str) -> None:
        if serial != self._serial or fingerprint != self.model.fingerprint(self.model.state.active_panel):
            return
        panel_id = self.model.state.active_panel
        status, table = self._pages[panel_id]
        table.setRowCount(0)
        if panel_id in self._distribution_widgets:
            self._distribution_widgets[panel_id].clear_distribution()
        if panel_id in self._matrix_widgets:
            self._matrix_widgets[panel_id].clear_matrix()
        if panel_id in self._hand_strength_widgets:
            self._hand_strength_widgets[panel_id].clear_distribution()
        self.stack_note_label.setVisible(False)
        status.setText(f"Panel unavailable: {message}")

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
        # Keep the label at index 0 and the stretch spacer at the end. Only
        # buttons created by this method occupy the slots between them.
        while self.filter_row.count() > 2:
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
        self.stack_note_label.setText(self._stack_note or "")
        self.stack_note_label.setVisible(bool(self._stack_note))
        if panel_id in self._matrix_widgets:
            self._render_matrix(panel_id, result, status, table)
            return
        if panel_id in self._hand_strength_widgets:
            self._render_hand_strength(panel_id, result, status, table)
            return
        if panel_id in self._distribution_widgets:
            self._render_distribution(panel_id, result, status, table)
            return
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

    def _render_distribution(
        self,
        panel_id: str,
        result: Any,
        status: QLabel,
        table: QTableWidget,
    ) -> None:
        """Render a real chart while keeping every exact grouped row visible."""
        group_by = self._group_by(panel_id)
        if len(group_by) != 1:
            status.setText("Distribution panels must group by exactly one dimension.")
            table.setRowCount(0)
            return
        dimension = group_by[0]
        chart = self._distribution_widgets[panel_id]
        label_map = POSITION_LABELS if dimension in {"position", "opponent_position"} else None
        if isinstance(result, DashboardComparison):
            hero = build_distribution(
                result.hero,
                dimension,
                min_sample=self.model.state.min_sample,
                label_map=label_map,
            )
            field = build_distribution(
                result.field,
                dimension,
                min_sample=self.model.state.min_sample,
                label_map=label_map,
            )
            chart.set_comparison(hero, field)
            rows = [
                {"side": "Hero", **row}
                for row in hero.as_rows()
            ] + [
                {"side": "Field", **row}
                for row in field.as_rows()
            ]
            warnings = [warning for warning in (hero.low_sample_warning, field.low_sample_warning) if warning]
        else:
            series = build_distribution(
                result,
                dimension,
                min_sample=self.model.state.min_sample,
                label_map=label_map,
            )
            chart.set_series(series)
            rows = series.as_rows()
            warnings = [series.low_sample_warning] if series.low_sample_warning else []

        columns = sorted({key for row in rows for key in row})
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, column in enumerate(columns):
                item = QTableWidgetItem(self._display(row.get(column)))
                if column == dimension:
                    item.setData(Qt.ItemDataRole.UserRole, {dimension: row.get(column)})
                table.setItem(row_index, column_index, item)
        table.resizeColumnsToContents()
        sample = self._sample_text(result)
        self.sample_label.setText(sample)
        note = " No matching decisions for this context." if "0 decisions" in sample else ""
        warning_text = f" {' '.join(warnings)}" if warnings else ""
        status.setText(
            f"{sample}.{warning_text}{note} "
            "Bars show share of decisions or response rate; double-click a row to filter."
        )

    def _render_matrix(
        self,
        panel_id: str,
        result: Any,
        status: QLabel,
        table: QTableWidget,
    ) -> None:
        """Render a two-axis visual and keep all numeric cells in the fallback table."""
        group_by = self._group_by(panel_id)
        if len(group_by) != 2:
            status.setText("Matrix panels must group by exactly two dimensions.")
            table.setRowCount(0)
            return
        matrix = self._matrix_widgets[panel_id]
        if isinstance(result, DashboardComparison):
            hero = build_matrix(result.hero, group_by, min_sample=self.model.state.min_sample)
            field = build_matrix(result.field, group_by, min_sample=self.model.state.min_sample)
            matrix.set_comparison(hero, field)
            rows = [
                {"side": "Hero", **row}
                for row in hero.as_rows()
            ] + [
                {"side": "Field", **row}
                for row in field.as_rows()
            ]
            low_sample = len(hero.low_sample_cells) + len(field.low_sample_cells)
        else:
            series = build_matrix(result, group_by, min_sample=self.model.state.min_sample)
            matrix.set_series(series)
            rows = series.as_rows()
            low_sample = len(series.low_sample_cells)

        columns = sorted({key for row in rows for key in row})
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, column in enumerate(columns):
                item = QTableWidgetItem(self._display(row.get(column)))
                if column in group_by:
                    item.setData(Qt.ItemDataRole.UserRole, {column: row.get(column)})
                table.setItem(row_index, column_index, item)
        table.resizeColumnsToContents()
        sample = self._sample_text(result)
        self.sample_label.setText(sample)
        warning = f" {low_sample} populated cells are below the minimum sample." if low_sample else ""
        status.setText(
            f"{sample}.{warning} Numeric labels include sample and numerator; click a cell to filter both axes."
        )

    def _distribution_bin_clicked(self, name: str, value: Any, label: str) -> None:
        self.add_cross_filter(name, value, f"{name.replace('_', ' ').title()}: {label}")

    def _matrix_cell_clicked(
        self,
        row_name: str,
        row_value: Any,
        column_name: str,
        column_value: Any,
        label: str,
    ) -> None:
        """Apply both axes in one refresh so the selected matchup stays atomic."""
        if row_value is None or column_value is None:
            self.context_label.setText(
                "Unknown or unclassified cells stay visible, but cannot create a partial matchup filter."
            )
            return
        try:
            self.model.add_cross_filter(row_name, row_value, f"{row_name}: {label}")
            self.model.add_cross_filter(column_name, column_value, f"{column_name}: {label}")
        except ValueError as exc:
            self.context_label.setText(f"Cannot filter this cell: {exc}")
            return
        self._results.clear()
        self._render_cross_filters()
        self._load_active_panel()

    def _hand_strength_dimension_changed(self, panel_id: str, dimension: str) -> None:
        try:
            self.model.set_panel_dimension(panel_id, dimension)
        except ValueError as exc:
            self.context_label.setText(f"Hand-state dimension error: {exc}")
            return
        self._results.clear()
        self._render_cross_filters()
        self._load_active_panel()

    def _render_hand_strength(
        self,
        panel_id: str,
        result: Any,
        status: QLabel,
        table: QTableWidget,
    ) -> None:
        from fpdb_3_legacy.research_hand_strength import build_hand_strength

        widget = self._hand_strength_widgets[panel_id]
        if isinstance(result, DashboardComparison):
            hero = build_hand_strength(result.hero)
            field = build_hand_strength(result.field)
            widget.set_distribution(hero, field)
            rows = [
                {"side": "Hero", **row}
                for row in hero.as_rows()
            ] + [
                {"side": "Field", **row}
                for row in field.as_rows()
            ]
            warnings = [warning for warning in (hero.known_sample_warning, field.known_sample_warning) if warning]
            overlapping = hero.overlapping or field.overlapping
        else:
            distribution = build_hand_strength(result)
            widget.set_distribution(distribution)
            rows = distribution.as_rows()
            warnings = [distribution.known_sample_warning] if distribution.known_sample_warning else []
            overlapping = distribution.overlapping

        columns = sorted({key for row in rows for key in row})
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setRowCount(len(rows))
        dimension = self.model.panel(panel_id).dimension
        for row_index, row in enumerate(rows):
            for column_index, column in enumerate(columns):
                item = QTableWidgetItem(self._display(row.get(column)))
                if column == "key":
                    filter_name = row.get("filter_name")
                    item.setData(
                        Qt.ItemDataRole.UserRole,
                        ({filter_name: row.get("filter_value")} if filter_name else {}),
                    )
                table.setItem(row_index, column_index, item)
        table.resizeColumnsToContents()
        sample = self._sample_text(result)
        self.sample_label.setText(sample)
        overlap = " Categories overlap; shares do not sum to 100%." if overlapping else ""
        warning_text = f" {' '.join(warnings)}" if warnings else ""
        status.setText(
            f"{sample}.{warning_text}{overlap} "
            f"Dimension: {dimension}. Bars use classified decisions only; click a category to filter."
        )

    def _hand_strength_category_clicked(self, name: str, value: Any, label: str) -> None:
        if not name:
            self.context_label.setText("This unclassified category has no safe query filter.")
            return
        self.add_cross_filter(name, value, f"{name.replace('_', ' ').title()}: {label}")

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
            return [
                cell.as_dict(total_opportunities=result.total_opportunities)
                for cell in result.every_cell()
            ]
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
        if hasattr(result, "classified") and hasattr(result, "total") and hasattr(result, "coverage_bp"):
            return (
                f"{result.classified}/{result.total} classified decisions "
                f"({result.coverage_bp / 100:.1f}% coverage; {result.unclassified} unknown)"
            )
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
