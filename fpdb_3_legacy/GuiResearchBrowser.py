"""GuiResearchBrowser.py

The multidimensional research browser (issue #303): three panes -- filters,
results, hands -- over the analytics query engine, with saved presets and a
drill-down into the matching hands.

The widget deliberately contains as little analytics as possible: it reads
``fpdb_3_legacy.research_browser`` (which is Qt-free and fully tested
offscreen) and renders what that model answers. Everything the user can
express -- metric, filters, groupings, presets -- is engine vocabulary, so a
query built here compiles through the same code path the CLI uses, and the
SQL is parameterized by construction.

Threading follows the ring-stats pattern: queries run on a worker QThread,
never on the Qt event loop. Every query carries a serial number; a finished
query whose serial is no longer current is dropped instead of overwriting a
newer result -- the stale-result race the issue names. Cancellation bumps
the serial and clears the wait, which ends the wait promptly without
touching the worker the engine runs on.
"""

from __future__ import annotations

import contextlib
from typing import Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import research_browser as rb
from fpdb_3_legacy.analytics_query import DIMENSIONS, KNOWN_METRICS
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.ring_stats.styles import get_theme_palette

log = get_logger("gui_research_browser")


class _WorkerDatabase:
    """Small read-only Database facade around a borrowed DB-API connection."""

    def __init__(self, owner: Any, connection: Any) -> None:
        self.backend = owner.backend
        self.sql = owner.sql
        self._connection = connection

    def get_cursor(self):
        return self._connection.cursor()


@contextlib.contextmanager
def _worker_database(db: Any):
    """Give research workers a dedicated connection when the DB supports it."""
    acquire = getattr(db, "worker_connection", None)
    if callable(acquire):
        with acquire() as connection:
            yield _WorkerDatabase(db, connection)
    else:
        # Lightweight test doubles and legacy adapters may not expose the pool.
        yield db


class _QueryWorker(QThread):
    """One analytics query on its own thread; the UI stays responsive."""

    finished_ok = Signal(object, int)  # result, emitting query serial
    failed = Signal(str, int)

    def __init__(self, db: Any, preset: dict[str, Any], serial: int, parent=None) -> None:
        super().__init__(parent)
        self._db = db
        self._preset = preset
        self._serial = serial

    @property
    def serial(self) -> int:
        return self._serial

    def run(self) -> None:
        try:
            with _worker_database(self._db) as db:
                result = rb.execute_preset(db, self._preset)
        except Exception as exc:  # noqa: BLE001 - worker boundary reports errors via signal.
            log.exception("Research query failed")
            self.failed.emit(str(exc), self.serial)
            return
        self.finished_ok.emit(result, self.serial)


class _DrillWorker(QThread):
    """One drill-down: the hands behind a result row."""

    finished_ok = Signal(object, int)
    failed = Signal(str, int)

    def __init__(self, db: Any, row_query: Any, group: dict[str, Any], numerator: bool, serial: int, parent=None) -> None:
        super().__init__(parent)
        self._db = db
        self._query = row_query
        self._group = group
        self._numerator = numerator
        self._serial = serial

    @property
    def serial(self) -> int:
        return self._serial

    def run(self) -> None:
        try:
            with _worker_database(self._db) as db:
                drill = rb.run_drill_down(db, self._query, group=self._group, numerator_only=self._numerator)
        except Exception as exc:  # noqa: BLE001
            log.exception("Research drill-down failed")
            self.failed.emit(str(exc), self.serial)
            return
        self.finished_ok.emit(drill, self.serial)


class _FilterRow(QWidget):
    """One filter's input row: the picker, the value widget, the remove."""

    changed = Signal()
    removed = Signal(object)

    def __init__(self, spec: rb.FilterSpec, parent=None) -> None:
        super().__init__(parent)
        self.spec = spec
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 2)

        self.name_label = QLabel(spec.name)
        self.name_label.setToolTip(f"{spec.group}: {spec.description}")
        self.name_label.setMinimumWidth(150)
        layout.addWidget(self.name_label)

        self.value_edit: QWidget
        if spec.value_kind == "bool":
            self.value_edit = QCheckBox()
            check = self.value_edit
            assert isinstance(check, QCheckBox)
            check.stateChanged.connect(lambda _: self.changed.emit())
            layout.addWidget(check)
            layout.addStretch()
        elif spec.value_kind == "range":
            low = QDoubleSpinBox()
            low.setRange(-10_000_000, 10_000_000)
            low.setDecimals(2)
            low.setSpecialValueText(" ")
            high = QDoubleSpinBox()
            high.setRange(-10_000_000, 10_000_000)
            high.setDecimals(2)
            high.setSpecialValueText(" ")
            self.low_spin = low
            self.high_spin = high
            low.valueChanged.connect(lambda _: self.changed.emit())
            high.valueChanged.connect(lambda _: self.changed.emit())
            layout.addWidget(QLabel(_("from")))
            layout.addWidget(low)
            layout.addWidget(QLabel(_("to")))
            layout.addWidget(high)
            layout.addStretch()
        else:
            # ``set``, ``flags`` and scalar filters all read a comma-separated
            # text: flags are named, sets are labels or codes, and the engine
            # validates every token when the query is compiled.
            self.value_edit = QLineEdit()
            edit = self.value_edit
            assert isinstance(edit, QLineEdit)
            edit.editingFinished.connect(self.changed.emit)
            layout.addWidget(edit)
        layout.addStretch()
        self.remove_button = QLabel("✕")
        self.remove_button.setToolTip(_("Remove this filter"))
        self.remove_button.setStyleSheet("color: #e06c75; font-weight: bold;")
        self.remove_button.setCursor(Qt.CursorShape.PointingHandCursor)
        from PySide6.QtCore import Signal as _Signal  # noqa: F401  (kept local; mouse events below)

        self.remove_button.mousePressEvent = lambda _event: self.removed.emit(self)  # type: ignore[assignment]
        layout.addWidget(self.remove_button)

    def value(self) -> Any:
        """The filter value as the engine vocabulary, or None to skip."""
        kind = self.spec.value_kind
        if kind == "bool":
            check = self.value_edit
            assert isinstance(check, QCheckBox)
            return bool(check.isChecked())
        if kind == "range":
            low = self.low_spin.value()
            high = self.high_spin.value()
            out_low = None if low == self.low_spin.minimum() else low
            out_high = None if high == self.high_spin.minimum() else high
            if out_low is None and out_high is None:
                return None
            return [out_low, out_high]
        edit = self.value_edit
        assert isinstance(edit, QLineEdit)
        raw = edit.text().strip()
        if not raw:
            return None
        if raw.lower() in ("true", "false"):
            return raw.lower() == "true"
        if "," in raw:
            return [part.strip() for part in raw.split(",") if part.strip()]
        if raw.lstrip("-").isdigit():
            return int(raw)
        return raw


class GuiResearchBrowser(QWidget):
    """The three-pane research browser tab (issue #303)."""

    def __init__(self, config, querylist, mainwin, db=None) -> None:
        super().__init__()
        self.conf = config
        self.main_window = mainwin
        self.sql = querylist
        self.db = db
        if self.db is None:
            from fpdb_3_legacy.Database import Database

            self.db = Database(config, sql=querylist)
        self._owns_db = db is None

        self.presets = rb.ResearchPresets()
        self._query_serial = 0
        self._drill_serial = 0
        self._worker: _QueryWorker | None = None
        self._drill_worker: _DrillWorker | None = None
        self._filter_rows: list[_FilterRow] = []
        self._current_query: Any = None
        self._current_group: dict[str, Any] = {}

        self._build_ui()
        self._refresh_presets()
        self._add_default_filters()

    # -- UI construction ----------------------------------------------------

    def _build_ui(self) -> None:
        c = get_theme_palette()
        muted = c.get("muted_text", "#a0aec0")

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(splitter)
        splitter.addWidget(self._build_filters_pane(muted))
        splitter.addWidget(self._build_results_pane(muted))
        splitter.addWidget(self._build_hands_pane(muted))
        splitter.setSizes([320, 480, 420])

    def _build_filters_pane(self, muted: str) -> QWidget:
        """Pane 1: the filter list, the metric, the groupings, the presets."""
        filters_pane = QWidget()
        filters_layout = QVBoxLayout(filters_pane)
        filters_layout.setContentsMargins(0, 0, 4, 0)
        title = QLabel(_("Filters"))
        title.setStyleSheet(f"font-weight: bold; color: {muted}; font-size: 11px; text-transform: uppercase;")
        filters_layout.addWidget(title)

        add_layout = QHBoxLayout()
        self.filter_group_combo = QComboBox()
        self.filter_group_combo.addItems(rb.FILTER_GROUPS)
        self.filter_group_combo.currentIndexChanged.connect(self._fill_filter_picker)
        self.filter_picker = QComboBox()
        add_layout.addWidget(self.filter_group_combo)
        add_layout.addWidget(self.filter_picker, 1)
        self.add_filter_button = QLabel("+")
        self.add_filter_button.setToolTip(_("Add this filter"))
        self.add_filter_button.setStyleSheet("font-weight: bold; color: #98c379; font-size: 16px;")
        self.add_filter_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_filter_button.mousePressEvent = lambda _event: self._add_picked_filter()  # type: ignore[assignment]
        add_layout.addWidget(self.add_filter_button)
        filters_layout.addLayout(add_layout)

        self.filter_rows_widget = QWidget()
        self.filter_rows_layout = QVBoxLayout(self.filter_rows_widget)
        self.filter_rows_layout.setContentsMargins(0, 4, 0, 0)
        filters_layout.addWidget(self.filter_rows_widget, 1)

        self.metric_combo = QComboBox()
        self.metric_combo.addItems(list(KNOWN_METRICS))
        self.metric_combo.setCurrentText("fold_frequency")
        filters_layout.addWidget(QLabel(_("Metric")))
        filters_layout.addWidget(self.metric_combo)

        self.group_edit = QLineEdit()
        self.group_edit.setPlaceholderText(_("e.g. street, response"))
        self.group_edit.setToolTip(_("Comma-separated group-by dimensions"))
        filters_layout.addWidget(QLabel(_("Group by")))
        filters_layout.addWidget(self.group_edit)

        buttons_layout = QHBoxLayout()
        self._build_run_buttons(buttons_layout, muted)
        filters_layout.addLayout(buttons_layout)

        preset_layout = QHBoxLayout()
        self.preset_combo = QComboBox()
        preset_layout.addWidget(self.preset_combo, 1)
        self._build_preset_buttons(preset_layout, muted)
        filters_layout.addLayout(preset_layout)
        return filters_pane

    def _build_run_buttons(self, buttons_layout: QHBoxLayout, muted: str) -> None:
        """Run and Cancel: the two controls over the query's lifetime."""
        self.run_button = QLabel(_("▶ Run"))
        self.run_button.setStyleSheet("font-weight: bold; color: #98c379; font-size: 14px;")
        self.run_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_button.mousePressEvent = lambda _event: self.run_query()  # type: ignore[assignment]
        self.cancel_button = QLabel(_("■ Cancel"))
        self.cancel_button.setStyleSheet(f"color: {muted};")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.setVisible(False)
        self.cancel_button.mousePressEvent = lambda _event: self._cancel_query()  # type: ignore[assignment]
        buttons_layout.addWidget(self.run_button)
        buttons_layout.addWidget(self.cancel_button)
        buttons_layout.addStretch()

    def _build_preset_buttons(self, preset_layout: QHBoxLayout, muted: str) -> None:
        """Save/Delete beside the preset picker."""
        self.save_preset_button = QLabel(_("Save"))
        self.save_preset_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_preset_button.setStyleSheet(f"color: {muted};")
        self.save_preset_button.mousePressEvent = lambda _event: self._save_preset()  # type: ignore[assignment]
        self.delete_preset_button = QLabel(_("Delete"))
        self.delete_preset_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_preset_button.setStyleSheet(f"color: {muted};")
        self.delete_preset_button.mousePressEvent = lambda _event: self._delete_preset()  # type: ignore[assignment]
        preset_layout.addWidget(self.save_preset_button)
        preset_layout.addWidget(self.delete_preset_button)

    def _build_results_pane(self, muted: str) -> QWidget:
        """Pane 2: the result table with its sample size and its notes."""
        results_pane = QWidget()
        results_layout = QVBoxLayout(results_pane)
        results_layout.setContentsMargins(4, 0, 4, 0)
        self.sample_label = QLabel("")
        self.sample_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.elapsed_label = QLabel("")
        self.elapsed_label.setStyleSheet(f"color: {muted}; font-size: 11px;")
        head = QHBoxLayout()
        head.addWidget(self.sample_label)
        head.addStretch()
        head.addWidget(self.elapsed_label)
        results_layout.addLayout(head)
        self.result_table = QTableWidget()
        self.result_table.setSortingEnabled(True)
        self.result_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.result_table.verticalHeader().hide()
        self.result_table.itemDoubleClicked.connect(self._on_result_clicked)
        self.result_table.cellClicked.connect(self._show_row_group)
        results_layout.addWidget(self.result_table, 1)
        self.result_note = QLabel("")
        self.result_note.setStyleSheet(f"color: {muted}; font-size: 11px;")
        self.result_note.setWordWrap(True)
        results_layout.addWidget(self.result_note)
        return results_pane

    def _build_hands_pane(self, muted: str) -> QWidget:
        """Pane 3: the drill-down hands behind the selected result row."""
        hands_pane = QWidget()
        hands_layout = QVBoxLayout(hands_pane)
        hands_layout.setContentsMargins(4, 0, 0, 0)
        self.drill_title = QLabel(_("Matching hands"))
        self.drill_title.setStyleSheet(f"font-weight: bold; color: {muted}; font-size: 11px; text-transform: uppercase;")
        hands_layout.addWidget(self.drill_title)
        self.drill_mode_combo = QComboBox()
        self.drill_mode_combo.addItems([_("All hands in the population"), _("Only the hands where the metric fired")])
        hands_layout.addWidget(self.drill_mode_combo)
        self.drill_table = QTableWidget()
        self.drill_table.setSortingEnabled(True)
        self.drill_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.drill_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.drill_table.verticalHeader().hide()
        self.drill_table.itemDoubleClicked.connect(self._open_hand)
        hands_layout.addWidget(self.drill_table, 1)
        self.drill_note = QLabel(_("Double-click a result row to load its hands."))
        self.drill_note.setStyleSheet(f"color: {muted}; font-size: 11px;")
        self.drill_note.setWordWrap(True)
        hands_layout.addWidget(self.drill_note)
        return hands_pane

    def _add_default_filters(self) -> None:
        """The two filters almost every question starts with."""
        for name in ("hero", "primary_situation"):
            spec = rb.filter_spec(name)
            self._append_filter_row(spec)

    # -- filter rows ---------------------------------------------------------

    def _fill_filter_picker(self) -> None:
        group = self.filter_group_combo.currentText()
        self.filter_picker.clear()
        for spec in rb.FILTER_SPECS:
            if spec.group == group:
                self.filter_picker.addItem(spec.name, spec)

    def _add_picked_filter(self) -> None:
        spec = self.filter_picker.currentData()
        if spec is not None:
            self._append_filter_row(spec)

    def _append_filter_row(self, spec: rb.FilterSpec) -> None:
        row = _FilterRow(spec)
        row.changed.connect(self._on_filters_changed)
        row.removed.connect(self._remove_filter_row)
        self._filter_rows.append(row)
        self.filter_rows_layout.addWidget(row)

    def _remove_filter_row(self, row: _FilterRow) -> None:
        if row in self._filter_rows:
            self._filter_rows.remove(row)
            row.setParent(None)
            row.deleteLater()

    def _on_filters_changed(self) -> None:
        """Filters changed: the next run uses them. Live queries are not
        re-run automatically -- the sample size is the user's call."""

    # -- the query -----------------------------------------------------------

    def current_preset(self) -> dict[str, Any]:
        """What the panes currently express, as engine vocabulary."""
        filters: dict[str, Any] = {}
        for row in self._filter_rows:
            value = row.value()
            if value is not None:
                filters[row.spec.name] = value
        group_by = tuple(
            part.strip() for part in self.group_edit.text().split(",") if part.strip()
        )
        return {
            "metric": self.metric_combo.currentText(),
            "filters": filters,
            "group_by": group_by,
        }

    def run_query(self) -> None:
        preset = self.current_preset()
        group_by = preset["group_by"]
        unknown = [name for name in group_by if name not in DIMENSIONS]
        if unknown:
            QMessageBox.warning(
                self,
                _("Research browser"),
                _("Unknown group-by dimension(s): {names}. Known: {known}.").format(
                    names=", ".join(unknown), known=", ".join(sorted(DIMENSIONS)),
                ),
            )
            return
        try:
            rb.validate_preset(preset)
        except ValueError as exc:
            QMessageBox.warning(self, _("Research browser"), str(exc))
            return
        self._start_query(preset)

    def _start_query(self, preset: dict[str, Any]) -> None:
        # A finished worker is only retired here, at replacement time: the
        # signal between its ``run`` end and ``finished_ok`` delivery still
        # names the live widget, and dropping the reference earlier would
        # garbage-collect the thread mid-emission and eat the callback.
        if self._worker is not None and not self._worker.isRunning():
            self._worker.deleteLater()
            self._worker = None
        self._query_serial += 1
        self.cancel_button.setVisible(True)
        self.sample_label.setText(_("Running…"))
        self.result_note.setText("")
        worker = _QueryWorker(self.db, preset, self._query_serial, self)
        worker.finished_ok.connect(self._on_query_done)
        worker.failed.connect(self._on_query_failed)
        self._worker = worker
        worker.start()

    def _cancel_query(self) -> None:
        """Stop waiting for the running query; its result will be dropped."""
        self._query_serial += 1
        self.cancel_button.setVisible(False)
        self.sample_label.setText("")
        self.result_note.setText(_("Query cancelled."))
        self._worker = None

    def _on_query_done(self, result: Any, serial: int) -> None:
        """A finished query: render it, unless a newer query superseded it.

        ``_serial`` is the emitting worker's number, delivered with the result
        (the argument Qt drops when the slot is invoked through a wrapper).
        The freshness check therefore reads the serial off the worker object,
        which cannot drift, and falls back to the delivered one.
        """
        if serial != self._query_serial:
            return  # A stale result never replaces a newer query.
        if self._worker is None or self._worker.serial != serial:
            return
        self.cancel_button.setVisible(False)
        self._worker.deleteLater()
        self._worker = None
        self._render_result(result)

    def _on_query_failed(self, message: str, serial: int) -> None:
        if serial != self._query_serial:
            return
        self.cancel_button.setVisible(False)
        if self._worker is not None and self._worker.serial == serial:
            self._worker.deleteLater()
            self._worker = None
        self.sample_label.setText("")
        self.result_note.setText(message)

    # -- rendering -----------------------------------------------------------

    def _render_result(self, result: Any) -> None:
        self.sample_label.setText(result.sample_text)
        self.elapsed_label.setText(f"{result.elapsed_ms:.0f} ms")
        columns = result.columns
        if result.empty_reason is not None:
            self.result_table.setRowCount(0)
            self.result_table.setColumnCount(len(columns))
            self.result_table.setHorizontalHeaderLabels([col.heading for col in columns])
            self.result_note.setText(result.empty_reason)
            return
        rows = result.rows
        self.result_table.setRowCount(len(rows))
        self.result_table.setColumnCount(len(columns))
        self.result_table.setHorizontalHeaderLabels([col.heading for col in columns])
        for r, row in enumerate(rows):
            group = {col.key: row.get(col.key) for col in columns if col.source == "dimension"}
            for c, col in enumerate(columns):
                value = row.get(col.key)
                text = "" if value is None else str(value)
                if col.key == "frequency_bp" and value is not None:
                    text = f"{value / 100:.1f}%"
                item = QTableWidgetItem(text)
                if col.source == "dimension":
                    item.setData(Qt.ItemDataRole.UserRole, group)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.result_table.setItem(r, c, item)
        self.result_table.resizeColumnsToContents()
        self.result_note.setText(
            _("Double-click a row to load its hands. Numerator/denominator are shown per row.")
            if result.query.group_by
            else _("Double-click the row to load its hands.")
        )
        # Remember the query behind the single ungrouped row.
        self._current_query = result.query
        self._current_group = {}
        if rows:
            self._load_drill(group={})

    def _on_result_clicked(self, item: QTableWidgetItem) -> None:
        """Double-click a result row: load the hands behind it."""
        row = item.row()
        group_item = self.result_table.item(row, 0)
        group: dict[str, Any] = group_item.data(Qt.ItemDataRole.UserRole) if group_item else {}
        self._current_group = dict(group or {})
        self._load_drill(group=self._current_group)

    def _show_row_group(self, row: int, _column: int) -> None:
        """Single click: say which slice the row stands for, before the drill."""
        group_item = self.result_table.item(row, 0)
        group: dict[str, Any] = group_item.data(Qt.ItemDataRole.UserRole) if group_item else {}
        if group:
            rendered = ", ".join(f"{key}={value}" for key, value in sorted(group.items()))
            self.result_note.setText(rendered)

    # -- drill-down ----------------------------------------------------------

    def _load_drill(self, group: dict[str, Any]) -> None:
        if self._current_query is None:
            return
        numerator = self.drill_mode_combo.currentIndex() == 1
        self._drill_serial += 1
        self.drill_note.setText(_("Loading hands…"))
        worker = _DrillWorker(self.db, self._current_query, dict(group), numerator, self._drill_serial, self)
        worker.finished_ok.connect(self._on_drill_done)
        worker.failed.connect(self._on_drill_failed)
        self._drill_worker = worker
        worker.start()

    def _on_drill_done(self, drill: Any, serial: int) -> None:
        if serial != self._drill_serial:
            return
        columns = rb.DRILL_COLUMNS
        self.drill_table.setRowCount(len(drill.rows))
        self.drill_table.setColumnCount(len(columns))
        self.drill_table.setHorizontalHeaderLabels([col.heading for col in columns])
        for r, row in enumerate(drill.rows):
            for c, col in enumerate(columns):
                value = row.get(col.key)
                text = "" if value is None else str(value)
                self.drill_table.setItem(r, c, QTableWidgetItem(text))
        self.drill_table.resizeColumnsToContents()
        note = f"{drill.total_matches} hands"
        if drill.truncated:
            note += f" (showing the last {drill.limit})"
        self.drill_note.setText(note)

    def _on_drill_failed(self, message: str, serial: int) -> None:
        if serial != self._drill_serial:
            return
        self.drill_note.setText(message)

    def _open_hand(self, item: QTableWidgetItem) -> None:
        row = item.row()
        id_item = self.drill_table.item(row, 0)
        if id_item is None or not id_item.text().strip():
            return
        try:
            hand_id = int(id_item.text())
        except ValueError:
            return
        self._open_in_replayer([hand_id])

    def _open_in_replayer(self, hand_ids: list[int]) -> None:
        try:
            from fpdb_3_legacy import GuiReplayer

            replayer = GuiReplayer.GuiReplayer(
                self.conf, self.sql, self.main_window, hand_ids, db=self.db,
            )
            replayer.play_hand(0)
            replayer.raise_()
            replayer.activateWindow()
            if not hasattr(self, "replayers"):
                self.replayers: list[Any] = []
            self.replayers.append(replayer)
        except Exception as exc:  # noqa: BLE001 - replayer failures must not break the browser.
            log.exception("Unable to open hand replayer from research browser")
            QMessageBox.critical(self, _("FPDB Replayer"), f"Unable to open hand replayer:\n{exc}")

    # -- presets -------------------------------------------------------------

    def _refresh_presets(self) -> None:
        self.preset_combo.clear()
        try:
            stored = self.presets.load()
        except ValueError as exc:
            log.warning("Presets not loaded: %s", exc)
            stored = {}
        self.preset_combo.addItem(_("-- saved presets --"), None)
        for name in sorted(stored):
            self.preset_combo.addItem(name, stored[name])
        self.preset_combo.currentIndexChanged.connect(self._apply_preset)

    def _apply_preset(self) -> None:
        preset = self.preset_combo.currentData()
        if not preset:
            return
        self.metric_combo.setCurrentText(preset["metric"])
        self.group_edit.setText(", ".join(preset["group_by"]))
        for row in list(self._filter_rows):
            self._remove_filter_row(row)
        for name, value in preset["filters"].items():
            try:
                spec = rb.filter_spec(name)
            except ValueError:
                continue
            self._append_filter_row(spec)
            row = self._filter_rows[-1]
            self._set_row_value(row, value)
        self.run_query()

    @staticmethod
    def _set_row_value(row: _FilterRow, value: Any) -> None:
        kind = row.spec.value_kind
        if kind == "bool":
            check = row.value_edit
            assert isinstance(check, QCheckBox)
            check.setChecked(bool(value))
        elif kind == "range":
            low, high = (value if isinstance(value, (list, tuple)) else (None, None))
            if low is not None:
                row.low_spin.setValue(float(low))
            if high is not None:
                row.high_spin.setValue(float(high))
        else:
            edit = row.value_edit
            assert isinstance(edit, QLineEdit)
            if isinstance(value, (list, tuple)):
                edit.setText(", ".join(str(part) for part in value))
            else:
                edit.setText(str(value))

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(self, _("Save preset"), _("Name:"))
        if not ok or not name.strip():
            return
        preset = self.current_preset()
        try:
            self.presets.save(name.strip(), preset)
        except ValueError as exc:
            QMessageBox.warning(self, _("Research browser"), str(exc))
            return
        self._refresh_presets()
        index = self.preset_combo.findText(name.strip())
        if index >= 0:
            self.preset_combo.setCurrentIndex(index)

    def _delete_preset(self) -> None:
        name = self.preset_combo.currentData()
        if not name:
            return
        self.presets.delete(name)
        self._refresh_presets()

    # -- lifecycle -----------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming.
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(2000)
        if self._drill_worker is not None and self._drill_worker.isRunning():
            self._drill_worker.wait(2000)
        if self._owns_db and self.db is not None:
            try:
                self.db.disconnect()
            except Exception:  # noqa: BLE001
                pass
        super().closeEvent(event)
