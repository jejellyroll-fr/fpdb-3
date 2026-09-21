"""GuiResearchBrowser.py

The multidimensional research browser (issue #303), made usable by someone who
does not speak the analytics engine's vocabulary (issue #329).

Three panes -- filters, results, hands -- over the analytics query engine, with
saved presets and a drill-down into the matching hands.

The widget deliberately contains as little analytics as possible: it reads
``fpdb_3_legacy.research_browser`` (which is Qt-free and fully tested offscreen)
and renders what that model answers. Everything the user can express -- metric,
filters, groupings, presets -- is engine vocabulary, so a query built here
compiles through the same code path the CLI uses, and the SQL is parameterized
by construction.

#329 changed what the controls *look like*, not what they mean:

* every filter is labelled in poker language and offers the closed domain it
  has as a selector instead of a free-text token;
* booleans are tri-state -- *Any* is the default and compiles to no filter at
  all, so an untouched control can no longer silently mean "No" (#329's
  acceptance criterion, and the reason ``hero`` starts at *Any*);
* the breakdown is a structured add/remove control, not a comma-separated
  string, though the string form stays available in Expert mode and remains the
  single source the query is built from;
* the active question is stated in plain language before it runs;
* the first-open screen explains itself, offers example questions, and says so
  when the analytics tables need rebuilding.

Expert mode keeps the full engine vocabulary -- internal filter names, the free
text Group by field, raw metric names -- so simplifying the default flow never
removes power.

Threading follows the ring-stats pattern: queries run on a worker QThread,
never on the Qt event loop. Every query carries a serial number; a finished
query whose serial is no longer current is dropped instead of overwriting a
newer result -- the stale-result race the issue names. Cancellation bumps
the serial and clears the wait, which ends the wait promptly without
touching the worker the engine runs on.
"""

from __future__ import annotations

import contextlib
from typing import Any, Final

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import research_browser as rb
from fpdb_3_legacy import research_labels as rlabels
from fpdb_3_legacy import research_presets as presets_lib
from fpdb_3_legacy import research_views as rviews
from fpdb_3_legacy.analytics_query import DIMENSIONS, KNOWN_METRICS
from fpdb_3_legacy.GuiResearchViews import CompositionWidget, MoneyWidget, RangeGridWidget
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.ring_stats.styles import get_theme_palette

log = get_logger("gui_research_browser")

# The three values a boolean filter can hold. ``None`` is *Any* -- the value the
# engine skips -- and it is the default, which is the whole point of #329.
_ANY: Any = None
_TRUE: Any = True
_FALSE: Any = False


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
    """One analytics task on its own thread; the UI stays responsive.

    The task is a callable taking a database, so one worker serves a single
    preset query and the several queries a grid, a composition or a money
    report needs. From the widget's point of view they are the same thing:
    work that must not run on the Qt event loop.
    """

    finished_ok = Signal(object, int)  # result, emitting query serial
    failed = Signal(str, int)

    def __init__(self, db: Any, task: Any, serial: int, parent=None) -> None:
        super().__init__(parent)
        self._db = db
        self._task = task
        self._serial = serial

    @property
    def serial(self) -> int:
        return self._serial

    def run(self) -> None:
        try:
            with _worker_database(self._db) as db:
                result = self._task(db)
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


#: The filters the form opens with. Hero says who the question is about;
#: game and limit stop the first answer silently averaging two games (#355).
_DEFAULT_FILTERS: Final[tuple[str, ...]] = ("hero", "game", "limit", "primary_situation")


class _ChoiceCombo(QComboBox):
    """A compact multi-select: one item per choice, toggled in place (#329).

    A ``QComboBox`` rather than a list because the filter pane is 320 pixels
    wide and most domains have fewer than a dozen values. The chosen tokens are
    sent to the engine unchanged; only the item *text* carries the tick, so the
    control can never invent a value the engine does not know.
    """

    toggled = Signal()

    def __init__(self, choices, parent=None) -> None:
        super().__init__(parent)
        self._choices = tuple(choices)
        self._selected: list[str] = []
        for choice in self._choices:
            self.addItem(choice.label, choice.value)
        self.setToolTip(_("Add or remove one of the known values."))
        # ``activated[int]`` names the index overload explicitly: the plain
        # ``activated`` also has a text overload PySide may pick instead.
        self.activated[int].connect(self._toggle)
        # Nothing is chosen yet, and the control has to say so. Left as Qt
        # builds it, a combo shows its first item: a filter just added read as
        # "Situation = open raise" while the query carried no situation at all,
        # so a question that had been narrowed on screen ran against every
        # decision in the database and answered something else entirely (#353).
        self.setPlaceholderText(_("Choose one or more…"))
        self.sync()

    def _toggle(self, index: int) -> None:
        if index < 0:
            return
        value = self.itemData(index)
        if value in self._selected:
            self._selected.remove(value)
        else:
            self._selected.append(value)
        self.sync()
        self.toggled.emit()

    def sync(self) -> None:
        """Re-render the item texts from the selection (no signal is emitted)."""
        for index, choice in enumerate(self._choices):
            mark = "✔" if choice.value in self._selected else "＋"
            self.setItemText(index, f"{mark} {choice.label}")
        self.setCurrentIndex(-1)

    def values(self) -> list[str]:
        return list(self._selected)

    def set_values(self, values) -> None:
        self._selected = [str(value) for value in values]
        self.sync()


class _FilterRow(QWidget):
    """One filter's input row: the labelled picker, the value widget, the remove.

    Which value widget is built depends on the filter's ``value_kind`` *and* on
    the mode:

    * ``bool``  -> a tri-state combo (Any / Yes / No) in both modes;
    * ``range`` -> two number fields, unit-labelled;
    * ``set``/``flags`` with a closed domain -> a choice selector in Beginner
      mode and the raw comma-separated field in Expert mode;
    * anything else -> the raw field, because the domain really is open.
    """

    changed = Signal()
    removed = Signal(object)

    def __init__(self, spec: rb.FilterSpec, expert: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.spec = spec
        self._expert = expert
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 2)

        # The engine name only shows in Expert mode: #329 is explicit that the
        # internal vocabulary belongs there and not in the default surface.
        self.name_label = QLabel(spec.name if expert else spec.label)
        tooltip = f"{spec.label}: {spec.user_description}" if spec.user_description else spec.label
        if spec.description:
            tooltip += f"\n\n{'Engine filter' if expert else 'Engine name'}: {spec.name} ({spec.description})"
        self.name_label.setToolTip(tooltip)
        self.name_label.setMinimumWidth(150)
        layout.addWidget(self.name_label)

        self.value_edit: QWidget
        self.any_combo: QComboBox | None = None
        self.choice_combo: _ChoiceCombo | None = None
        if spec.value_kind == "bool":
            self._build_bool_widget(layout)
        elif spec.value_kind == "range":
            self._build_range_widget(layout)
        else:
            self._build_text_widget(layout)
        layout.addStretch()

        self.remove_button = QLabel("✕")
        self.remove_button.setToolTip(_("Remove this filter"))
        self.remove_button.setStyleSheet("color: #e06c75; font-weight: bold;")
        self.remove_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_button.mousePressEvent = lambda _event: self.removed.emit(self)  # type: ignore[assignment]
        layout.addWidget(self.remove_button)

    # -- widget construction -------------------------------------------------

    def _build_bool_widget(self, layout: QHBoxLayout) -> None:
        """Any / Yes / No: an untouched control states no condition at all."""
        combo = QComboBox()
        for label, value in ((_("Any"), _ANY), (_("Yes"), _TRUE), (_("No"), _FALSE)):
            combo.addItem(label, value)
        combo.setCurrentIndex(0)
        combo.currentIndexChanged.connect(lambda _: self.changed.emit())
        combo.setToolTip(_("Any leaves the condition out of the query entirely."))
        self.any_combo = combo
        self.value_edit = combo
        layout.addWidget(combo)

    def _build_range_widget(self, layout: QHBoxLayout) -> None:
        unit = self.spec.unit
        low = QDoubleSpinBox()
        low.setRange(-10_000_000, 10_000_000)
        low.setDecimals(2)
        low.setSpecialValueText(" ")
        high = QDoubleSpinBox()
        high.setRange(-10_000_000, 10_000_000)
        high.setDecimals(2)
        high.setSpecialValueText(" ")
        for spin in (low, high):
            if unit:
                spin.setSuffix(f" {unit}")
            spin.valueChanged.connect(lambda _: self.changed.emit())
        self.low_spin = low
        self.high_spin = high
        layout.addWidget(QLabel(_("from")))
        layout.addWidget(low)
        layout.addWidget(QLabel(_("to")))
        layout.addWidget(high)

    def _build_text_widget(self, layout: QHBoxLayout) -> None:
        edit = QLineEdit()
        self.value_edit = edit
        if not self._expert and self.spec.choices:
            # A closed domain: the selector is the control, and the field is a
            # read-only echo of the tokens it holds.
            edit.setReadOnly(True)
            combo = _ChoiceCombo(self.spec.choices)
            combo.toggled.connect(self._on_choice_toggled)
            self.choice_combo = combo
            layout.addWidget(combo)
        elif not self._expert and self.spec.examples:
            edit.setPlaceholderText(_("e.g. {example}").format(example=self.spec.examples[0]))
        edit.editingFinished.connect(self.changed.emit)
        layout.addWidget(edit)

    def _on_choice_toggled(self) -> None:
        if self.choice_combo is not None and isinstance(self.value_edit, QLineEdit):
            self.value_edit.setText(", ".join(self.choice_combo.values()))
        self.changed.emit()

    # -- value ---------------------------------------------------------------

    def value(self) -> Any:
        """The filter value as the engine vocabulary, or None to skip.

        ``None`` means *no filter*: the engine's ``compile_filters`` skips it,
        and that is exactly what an untouched control must produce.
        """
        kind = self.spec.value_kind
        if kind == "bool":
            combo = self.any_combo
            if combo is None:
                raise TypeError("a boolean filter must use the tri-state selector")
            return combo.currentData()
        if kind == "range":
            low = self.low_spin.value()
            high = self.high_spin.value()
            out_low = None if low == self.low_spin.minimum() else low
            out_high = None if high == self.high_spin.minimum() else high
            if out_low is None and out_high is None:
                return None
            return [out_low, out_high]
        edit = self.value_edit
        if not isinstance(edit, QLineEdit):
            raise TypeError("a text filter must use a line edit")
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

    def set_value(self, value: Any) -> None:
        """Write one engine value back into the control (preset load, mode switch)."""
        kind = self.spec.value_kind
        if kind == "bool":
            combo = self.any_combo
            if combo is None:
                raise TypeError("a boolean filter must use the tri-state selector")
            index = 0
            if value is True:
                index = combo.findData(True)
            elif value is False:
                index = combo.findData(False)
            combo.setCurrentIndex(max(index, 0))
            return
        if kind == "range":
            low, high = (value if isinstance(value, (list, tuple)) else (None, None))
            if low is not None:
                self.low_spin.setValue(float(low))
            if high is not None:
                self.high_spin.setValue(float(high))
            return
        edit = self.value_edit
        if not isinstance(edit, QLineEdit):
            raise TypeError("a text filter must use a line edit")
        tokens = [str(part) for part in value] if isinstance(value, (list, tuple)) else [str(value)]
        edit.setText(", ".join(tokens))
        if self.choice_combo is not None:
            self.choice_combo.set_values(tokens)


class _BreakdownPicker(QWidget):
    """The structured "Break down by" control (#329).

    The engine vocabulary stays the value: the picker holds dimension *names*
    and renders their labels, so switching the list around can never produce a
    dimension the query engine does not know. Adding is a combo of the
    dimensions that make sense to break a result down by; removing is the ✕ on
    the dimension's own chip.
    """

    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._dimensions: list[str] = []
        self._expert = False
        self._rows = QVBoxLayout()
        self._rows.setContentsMargins(0, 2, 0, 0)
        self._rows.setSpacing(2)

        self.add_combo = QComboBox()
        self.add_combo.setToolTip(_("Choose a dimension to split the result by."))
        self.add_button = QLabel(_("＋ Add breakdown"))
        self.add_button.setStyleSheet("font-weight: bold; color: #98c379;")
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.setToolTip(_("Add the selected dimension to the breakdown."))
        self.add_button.mousePressEvent = lambda _event: self._add_current()  # type: ignore[assignment]

        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 0, 0, 0)
        add_row.addWidget(self.add_combo, 1)
        add_row.addWidget(self.add_button)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)
        self._rows_container = QWidget()
        self._rows_container.setLayout(self._rows)
        outer.addWidget(self._rows_container)
        outer.addLayout(add_row)
        self.refresh_choices()

    # -- the dimension list ---------------------------------------------------

    def dimensions(self) -> tuple[str, ...]:
        return tuple(self._dimensions)

    def set_dimensions(self, names) -> None:
        """Replace the list without notifying: the caller owns the change."""
        known = [str(name) for name in names if str(name) in DIMENSIONS]
        if known == self._dimensions:
            return
        self._dimensions = known
        self._render()

    def set_expert(self, expert: bool) -> None:
        """Expert mode offers every dimension; Beginner mode the common ones."""
        self._expert = expert
        self.refresh_choices()

    def refresh_choices(self) -> None:
        specs = [
            spec
            for spec in rb.DIMENSION_SPECS
            if self._expert or spec.beginner or spec.name in self._dimensions
        ]
        self.add_combo.clear()
        for spec in specs:
            if spec.name in self._dimensions:
                continue
            self.add_combo.addItem(spec.label, spec.name)
        self.add_combo.setEnabled(self.add_combo.count() > 0)

    def _add_current(self) -> None:
        name = self.add_combo.currentData()
        if not name or name in self._dimensions:
            return
        self._dimensions.append(name)
        self._render()
        self.changed.emit()

    def _remove(self, name: str) -> None:
        if name in self._dimensions:
            self._dimensions.remove(name)
            self._render()
            self.changed.emit()

    def _render(self) -> None:
        while self._rows.count():
            item = self._rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for name in self._dimensions:
            chip = QWidget()
            chip_layout = QHBoxLayout(chip)
            chip_layout.setContentsMargins(0, 0, 0, 0)
            chip_layout.setSpacing(4)
            label = QLabel(f"[ {rlabels.dimension_label(name)} ]")
            label.setStyleSheet("color: #61afef;")
            close = QLabel("✕")
            close.setStyleSheet("color: #e06c75; font-weight: bold;")
            close.setCursor(Qt.CursorShape.PointingHandCursor)
            close.setToolTip(_("Remove this breakdown"))
            close.mousePressEvent = lambda _event, name=name: self._remove(name)  # type: ignore[assignment]
            chip_layout.addWidget(label)
            chip_layout.addWidget(close)
            chip_layout.addStretch()
            self._rows.addWidget(chip)
        self._rows_container.setVisible(bool(self._dimensions))
        self.refresh_choices()


class GuiResearchBrowser(QWidget):
    """The three-pane research browser tab (issues #303 and #329)."""

    def __init__(self, config, querylist, mainwin, db=None) -> None:
        super().__init__()
        self.conf = config
        self.main_window = mainwin
        self.sql = querylist
        self._spec_cache: dict[str, rb.FilterSpec] = {}
        self._scope: Any = None
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
        self._last_result: Any = None
        self._filter_rows: list[_FilterRow] = []
        self._current_query: Any = None
        self._current_group: dict[str, Any] = {}
        self._expert = False
        self._has_run = False
        self._syncing_breakdown = False
        self._builtins: Any = None
        # The view the workbench is answering (#331). ``None`` is the landing
        # state: the controls are the two default filters and a plain table is
        # what a query returns, which is exactly what the tab did before views
        # existed.
        self._active_view: rviews.ViewSpec | None = None

        self._build_ui()
        self._refresh_presets()
        self._add_default_filters()
        self._refresh_empty_state()
        self._update_summary()

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

    def _build_view_row(self, filters_layout: QVBoxLayout, muted: str) -> None:
        """Which question the workbench is answering (#331).

        Above everything else on purpose: the view is the question, and the
        filters below it are how that question is narrowed. ``None`` is the
        landing state -- nothing chosen yet -- so the first thing a reader sees
        is still the explanation of what this tab is.
        """
        row = QHBoxLayout()
        label = QLabel(_("View"))
        label.setStyleSheet(f"font-weight: bold; color: {muted}; font-size: 11px; text-transform: uppercase;")
        row.addWidget(label)
        self.view_combo = QComboBox()
        self.view_combo.addItem(_("Ask your own question"), None)
        for spec in rviews.VIEWS:
            self.view_combo.addItem(_(spec.label), spec.id)
            self.view_combo.setItemData(
                self.view_combo.count() - 1, _(spec.question), Qt.ItemDataRole.ToolTipRole,
            )
        self.view_combo.setToolTip(_("Pick one of the answers this workbench knows how to show."))
        row.addWidget(self.view_combo, 1)
        filters_layout.addLayout(row)
        self.view_question = QLabel("")
        self.view_question.setWordWrap(True)
        self.view_question.setStyleSheet(f"color: {muted}; font-size: 11px;")
        filters_layout.addWidget(self.view_question)
        self.view_combo.currentIndexChanged.connect(self.on_view_changed)

    def _build_filters_pane(self, muted: str) -> QWidget:
        """Pane 1: the mode, the filter list, the metric, the breakdown, presets."""
        filters_pane = QWidget()
        filters_layout = QVBoxLayout(filters_pane)
        filters_layout.setContentsMargins(0, 0, 4, 0)

        self._build_view_row(filters_layout, muted)
        self._build_mode_row(filters_layout)
        title = QLabel(_("Filters"))
        title.setStyleSheet(f"font-weight: bold; color: {muted}; font-size: 11px; text-transform: uppercase;")
        filters_layout.addWidget(title)
        self._build_filter_picker_row(filters_layout)

        self.filter_rows_widget = QWidget()
        self.filter_rows_layout = QVBoxLayout(self.filter_rows_widget)
        self.filter_rows_layout.setContentsMargins(0, 4, 0, 0)
        filters_layout.addWidget(self.filter_rows_widget, 1)

        self._build_breakdown_controls(filters_layout)

        buttons_layout = QHBoxLayout()
        self._build_run_buttons(buttons_layout, muted)
        filters_layout.addLayout(buttons_layout)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(f"color: {muted}; font-size: 11px; font-style: italic;")
        self.summary_label.setToolTip(_("The question the controls above currently ask."))
        filters_layout.addWidget(self.summary_label)

        preset_layout = QHBoxLayout()
        self.preset_combo = QComboBox()
        # Searchable (#330): typing filters the shipped library instead of
        # scrolling forty entries. ``NoInsert`` keeps whatever is typed from
        # becoming a new item.
        self.preset_combo.setEditable(True)
        self.preset_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        # Connected once: ``_refresh_presets`` rewrites the items and must not
        # add a second connection each time (which would run a preset twice).
        self.preset_combo.currentIndexChanged.connect(self._apply_preset)
        preset_layout.addWidget(self.preset_combo, 1)
        self._build_preset_buttons(preset_layout, muted)
        filters_layout.addLayout(preset_layout)

        self.preset_note = QLabel("")
        self.preset_note.setWordWrap(True)
        self.preset_note.setStyleSheet(f"color: {muted}; font-size: 11px;")
        filters_layout.addWidget(self.preset_note)
        return filters_pane

    def _build_mode_row(self, filters_layout: QVBoxLayout) -> None:
        """Beginner or Expert: which vocabulary the controls speak (#329)."""
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel(_("Mode")))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(_("Beginner"), False)
        self.mode_combo.addItem(_("Expert"), True)
        self.mode_combo.setToolTip(
            _("Beginner shows poker labels and selects values from the known list.\n"
              "Expert shows the engine names and accepts arbitrary values."),
        )
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_combo, 1)
        filters_layout.addLayout(mode_row)

    def _build_filter_picker_row(self, filters_layout: QVBoxLayout) -> None:
        """The group and filter pickers that add a filter row."""
        add_layout = QHBoxLayout()
        self.filter_group_combo = QComboBox()
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
        self._fill_group_picker()
        self._fill_filter_picker()

    def _build_breakdown_controls(self, filters_layout: QVBoxLayout) -> None:
        """The metric, the structured breakdown and the expert text field."""
        self.metric_combo = QComboBox()
        self.metric_combo.addItems(list(KNOWN_METRICS))
        self.metric_combo.setCurrentText("fold_frequency")
        self.metric_combo.currentTextChanged.connect(lambda _: self._update_summary())
        filters_layout.addWidget(QLabel(_("Metric")))
        filters_layout.addWidget(self.metric_combo)

        filters_layout.addWidget(QLabel(_("Break down by")))
        self.breakdown_picker = _BreakdownPicker()
        self.breakdown_picker.changed.connect(self._on_breakdown_changed)
        filters_layout.addWidget(self.breakdown_picker)

        self.group_edit = QLineEdit()
        self.group_edit.setPlaceholderText(_("e.g. street, response"))
        self.group_edit.setToolTip(_("Comma-separated group-by dimensions (engine vocabulary)"))
        self.group_edit.textChanged.connect(self._on_group_text_changed)
        self.group_edit.setVisible(False)  # Expert mode only.
        filters_layout.addWidget(self.group_edit)

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

    def _open_help(self, topic: str = "research") -> None:
        """Open a user guide from the Help affordance (#334).

        Guarded: a missing document must log and do nothing, never raise into a
        window the user is working in.
        """
        try:
            from fpdb_3_legacy import help_links

            opened = help_links.open_help(topic)
        except Exception:  # intentional broad catch: Help must not break the pane
            log.exception("Could not open the help topic %r", topic)
            return
        if not opened:
            log.info("Help for %s is documented in docs/%s", topic, topic)

    def _build_preset_buttons(self, preset_layout: QHBoxLayout, muted: str) -> None:
        """Save/Delete beside the preset picker."""
        self.help_button = QLabel(_("?"))
        self.help_button.setToolTip(_("Open the Research Browser quick start"))
        self.help_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.help_button.setStyleSheet(f"color: {muted}; font-weight: bold;")
        self.help_button.mousePressEvent = lambda _event: self._open_help()  # type: ignore[assignment]
        preset_layout.addWidget(self.help_button)
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
        """Pane 2: the onboarding empty state, then the result table."""
        results_pane = QWidget()
        results_layout = QVBoxLayout(results_pane)
        results_layout.setContentsMargins(4, 0, 4, 0)

        self.empty_state = self._build_empty_state(muted)
        results_layout.addWidget(self.empty_state)

        self.sample_label = QLabel("")
        self.sample_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.elapsed_label = QLabel("")
        self.elapsed_label.setStyleSheet(f"color: {muted}; font-size: 11px;")
        head = QHBoxLayout()
        head.addWidget(self.sample_label)
        head.addStretch()
        head.addWidget(self.elapsed_label)
        results_layout.addLayout(head)

        # What the active view says in one line, and how to read it (#331).
        # Hidden until a view is chosen, so the landing state stays the plain
        # tab it was.
        self.view_note = QLabel("")
        self.view_note.setWordWrap(True)
        self.view_note.setStyleSheet("font-size: 12px;")
        self.view_note.setVisible(False)
        results_layout.addWidget(self.view_note)
        self.result_table = QTableWidget()
        self.result_table.setSortingEnabled(True)
        self.result_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.result_table.verticalHeader().hide()
        self.result_table.itemDoubleClicked.connect(self._on_result_clicked)
        self.result_table.cellClicked.connect(self._show_row_group)

        # One page per shape of answer (#331): the table every view has always
        # had, then the grid, the composition and the money report. Each holds
        # its own widget, so switching a view backwards and forwards loses
        # nothing and reruns nothing.
        table_page = QWidget()
        table_layout = QVBoxLayout(table_page)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.addWidget(self.result_table)
        self.result_stack = QStackedWidget()
        self.result_stack.addWidget(table_page)
        self.range_grid = RangeGridWidget()
        self.range_grid.cell_activated.connect(self._load_cell_hands)
        self.result_stack.addWidget(self.range_grid)
        self.composition_view = CompositionWidget()
        self.result_stack.addWidget(self.composition_view)
        self.money_view = MoneyWidget()
        self.result_stack.addWidget(self.money_view)
        results_layout.addWidget(self.result_stack, 1)
        self.result_note = QLabel("")
        self.result_note.setStyleSheet(f"color: {muted}; font-size: 11px;")
        self.result_note.setWordWrap(True)
        results_layout.addWidget(self.result_note)
        return results_pane

    def _build_empty_state(self, muted: str) -> QWidget:
        """The first-open screen: what this is, and what to do next (#329)."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel(_("Ask a poker question"))
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        explanation = QLabel(
            _(
                "The Research Browser answers questions about the hands in your database. "
                "Pick a question below, change any value that should be different for you, "
                "then press Run. The sample size is always shown, and every row can be "
                "opened as the hands behind it.",
            ),
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        self.stale_note = QLabel("")
        self.stale_note.setWordWrap(True)
        self.stale_note.setStyleSheet("color: #e5c07b; font-size: 11px;")
        self.stale_note.setVisible(False)
        layout.addWidget(self.stale_note)

        layout.addWidget(QLabel(_("Try one of these:")))
        self.example_container = QWidget()
        self.example_layout = QVBoxLayout(self.example_container)
        self.example_layout.setContentsMargins(8, 0, 0, 0)
        self.example_layout.setSpacing(2)
        layout.addWidget(self.example_container)

        self.advanced_link = QLabel(_("Open the advanced query builder (Expert mode)"))
        self.advanced_link.setStyleSheet("color: #61afef; text-decoration: underline;")
        self.advanced_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.advanced_link.setToolTip(_("Show the engine's own filter names and free-text values."))
        self.advanced_link.mousePressEvent = lambda _event: self._open_advanced_mode()  # type: ignore[assignment]
        layout.addWidget(self.advanced_link)
        layout.addStretch()
        return panel

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
        """The two filters almost every question starts with.

        ``hero`` starts at *Any*, so the default query covers the whole
        population instead of silently meaning "opponents only".

        ``game`` and ``limit`` are here because a database holds more than one
        of each: without them the first answer a reader ever sees averages
        Hold'em with Omaha and micro stakes with high ones, and says nothing
        about it (#355). Both start empty, so the default question is still the
        whole database -- but the control is on screen, with this database's own
        values in it, rather than waiting to be discovered.
        """
        for name in _DEFAULT_FILTERS:
            self._append_filter_row(self._spec(name))

    # -- mode and labels -----------------------------------------------------

    def _on_mode_changed(self) -> None:
        """Rebuild the controls in the other vocabulary, keeping the query."""
        expert = bool(self.mode_combo.currentData())
        if expert == self._expert:
            return
        self._expert = expert
        captured = [(row.spec.name, row.value()) for row in self._filter_rows]
        for row in list(self._filter_rows):
            self._remove_filter_row(row)
        for name, value in captured:
            self._append_filter_row(self._spec(name))
            if value is not None:
                self._filter_rows[-1].set_value(value)
        self.breakdown_picker.set_expert(expert)
        self.group_edit.setVisible(expert)
        self._fill_group_picker()
        self._fill_filter_picker()
        self._update_summary()

    def _open_advanced_mode(self) -> None:
        """The first-run shortcut into the full engine vocabulary."""
        self.mode_combo.setCurrentIndex(self.mode_combo.count() - 1)
        self._on_mode_changed()

    def _expert_mode(self) -> bool:
        return self._expert

    # -- filter rows ---------------------------------------------------------

    def _fill_group_picker(self) -> None:
        """The filter groups, labelled in poker language in Beginner mode."""
        current = self.filter_group_combo.currentData()
        self.filter_group_combo.blockSignals(True)
        self.filter_group_combo.clear()
        for group in rb.FILTER_GROUPS:
            label = group if self._expert else rlabels.FILTER_GROUP_LABELS.get(group, group)
            self.filter_group_combo.addItem(label, group)
        if current:
            index = self.filter_group_combo.findData(current)
            if index >= 0:
                self.filter_group_combo.setCurrentIndex(index)
        self.filter_group_combo.blockSignals(False)

    def _fill_filter_picker(self) -> None:
        group = self.filter_group_combo.currentData() or self.filter_group_combo.currentText()
        self.filter_picker.clear()
        for spec in rb.FILTER_SPECS:
            if spec.group != group:
                continue
            if not self._expert and spec.expert_only:
                continue
            self.filter_picker.addItem(spec.name if self._expert else spec.label, spec)
        if self.filter_picker.count() and self.filter_picker.currentIndex() < 0:
            self.filter_picker.setCurrentIndex(0)

    def _add_picked_filter(self) -> None:
        spec = self.filter_picker.currentData()
        if spec is not None:
            self._append_filter_row(self._spec(spec.name))

    def _spec(self, name: str) -> rb.FilterSpec:
        """A filter's spec, with the values this database holds (#355).

        ``game``, ``limit``, ``currency`` and ``site`` ship with no choices, so
        they rendered as an empty box in which the reader had to guess that the
        stored token is ``omahahi``. The values are in the database; they are
        read once per pane and kept, because they only change on an import.
        """
        if name in self._spec_cache:
            return self._spec_cache[name]
        try:
            spec = rb.spec_for_database(self.db, name)
        except Exception:  # noqa: BLE001 - free text is a fallback, not a failure
            log.debug("Could not build the picker for filter %r", name, exc_info=True)
            spec = rb.filter_spec(name)
        self._spec_cache[name] = spec
        return spec

    def _append_filter_row(self, spec: rb.FilterSpec) -> None:
        row = _FilterRow(spec, expert=self._expert)
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
        """Filters changed: the next run uses them, and the summary says so.

        Live queries are not re-run automatically -- the sample size is the
        user's call -- but the question is restated immediately.
        """
        self._update_summary()

    # -- the breakdown -------------------------------------------------------

    def _on_group_text_changed(self) -> None:
        """The expert text field is the source; the picker mirrors it."""
        parsed = [part.strip() for part in self.group_edit.text().split(",") if part.strip()]
        self._syncing_breakdown = True
        try:
            self.breakdown_picker.set_dimensions(parsed)
        finally:
            self._syncing_breakdown = False
        self._update_summary()

    def _on_breakdown_changed(self) -> None:
        """The picker changed: write the canonical dimension list back."""
        if self._syncing_breakdown:
            return
        self.group_edit.setText(", ".join(self.breakdown_picker.dimensions()))
        self._update_summary()

    def _update_summary(self) -> None:
        """Restate the active question in the language the controls use."""
        summary = rb.describe_preset(self.current_preset())
        self.summary_label.setText(summary)

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
        spec = self._active_view
        # The view decides *which queries* answer the question; the controls
        # decide the population they run over. Remembering the population here
        # -- once, off the event loop's critical path -- is what lets a grid
        # cell or a result row drill into the same hands the answer counted.
        if spec is None or spec.kind == rviews.TABLE:
            self._current_query = rb.preset_to_query(preset)
        else:
            # ``replace_filters``: the builder was filled from the view and is
            # now the whole truth. Merging the view's own filters back in would
            # undo a filter the user deleted, and the summary above the table --
            # which reads those same controls -- would describe another query.
            self._current_query = rviews.query(spec, preset["filters"], replace_filters=True)
        self._start_task(self._task_for(preset))

    def _task_for(self, preset: dict[str, Any]) -> Any:
        """The work the active view needs, as one callable for the worker."""
        spec = self._active_view
        filters = dict(preset["filters"])
        if spec is None or spec.kind == rviews.TABLE:
            return lambda db: rb.execute_preset(db, preset)
        if spec.kind == rviews.GRID:
            return lambda db: rviews.range_matrix(db, spec, extra_filters=filters, replace_filters=True)
        if spec.kind == rviews.COMPOSITION:
            return lambda db: rviews.hand_composition(db, spec, extra_filters=filters, replace_filters=True)
        if spec.kind == rviews.MONEY:
            return lambda db: rviews.money_report(db, spec, extra_filters=filters, replace_filters=True)
        # The hands view is not a question of its own: it is every hand the
        # controls' query selects, which is the ungrouped form of it.
        return lambda db: rb.execute_preset(db, {**preset, "group_by": ()})

    def _start_task(self, task: Any) -> None:
        # A finished worker is only retired here, at replacement time: the
        # signal between its ``run`` end and ``finished_ok`` delivery still
        # names the live widget, and dropping the reference earlier would
        # garbage-collect the thread mid-emission and eat the callback.
        if self._worker is not None and not self._worker.isRunning():
            self._worker.deleteLater()
            self._worker = None
        self._query_serial += 1
        self.cancel_button.setVisible(True)
        self._has_run = True
        self.empty_state.setVisible(False)
        self.sample_label.setText(_("Running…"))
        self.result_note.setText("")
        worker = _QueryWorker(self.db, self._with_scope(task), self._query_serial, self)
        worker.finished_ok.connect(self._on_query_done)
        worker.failed.connect(self._on_query_failed)
        self._worker = worker
        worker.start()

    def _with_scope(self, task: Any) -> Any:
        """The view's work and the population's scope, on the same worker (#355).

        The scope costs one grouped query. It runs beside the answer rather
        than on the UI thread, because a warning is not worth a frozen window.
        """
        query = self._current_query

        def _run(db: Any) -> tuple[Any, Any]:
            return task(db), rb.population_scope(db, query)

        return _run

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
        payload, self._scope = result
        self._render(payload)
        self._append_scope_note()

    def _on_query_failed(self, message: str, serial: int) -> None:
        if serial != self._query_serial:
            return
        self.cancel_button.setVisible(False)
        if self._worker is not None and self._worker.serial == serial:
            self._worker.deleteLater()
            self._worker = None
        self.sample_label.setText("")
        self.result_note.setText(message)
        self.view_note.setVisible(False)

    # -- views ---------------------------------------------------------------

    def on_view_changed(self) -> None:
        """A view was chosen: load its question into the controls, then run it.

        A view is a starting point rather than a mode. Choosing one fills the
        controls with the question it asks, and everything below stays
        editable, so "fold to a three-bet for this one player" is the shipped
        view plus one value -- not a second feature.
        """
        view_id = self.view_combo.currentData()
        if view_id is None:
            self._active_view = None
            self.view_question.setText("")
            self.view_note.setVisible(False)
            # Leaving a shaped view with a task outstanding: the answer on its
            # way is a grid, a composition or a money report, and the table
            # renderer would read attributes those objects do not have. The
            # check is for a pending worker rather than a *running* one -- a
            # thread that has finished but whose result has not been delivered
            # yet is exactly the case that would still be rendered.
            if self._worker is not None:
                self._cancel_query()
            return
        spec = rviews.view(str(view_id))
        self._active_view = spec
        self.view_question.setText(f"{spec.question}\n{spec.how_to_read}")
        if spec.kind == rviews.HANDS:
            # The hands view is the drill-down, so it needs no question of its
            # own: it shows every hand the controls already select.
            self.run_query()
            return
        self._fill_builder(rviews.preset(spec))
        self.run_query()

    def _load_cell_hands(self, label: str) -> None:
        """A grid cell asked for its hands: the drill-down, narrowed by class."""
        if self._current_query is None:
            return
        self._load_drill({"starting_hand": label})

    # -- rendering -----------------------------------------------------------

    def _render(self, result: Any) -> None:
        """Draw a finished task in the presentation its view asks for."""
        spec = self._active_view
        kind = spec.kind if spec is not None else rviews.TABLE
        if kind == rviews.GRID and spec is not None:
            self._render_range(result, spec)
        elif kind == rviews.COMPOSITION and spec is not None:
            self._render_composition(result)
        elif kind == rviews.MONEY and spec is not None:
            self._render_money(result)
        else:
            self._render_result(result)
            if spec is not None:
                self._show_view_summary(spec)

    def _analytics_not_built_note(self) -> str:
        """Why an empty answer may not mean an empty database (#351).

        A database imported before the analytics layers existed holds its hands
        and its actions but none of the rows derived from them, and every
        question then answers "0 decisions" -- which reads as "you have no such
        hands" rather than "this database cannot answer anything yet". The
        difference is recorded in the analytics meta table, so it can simply be
        asked rather than guessed at.
        """
        db = getattr(self, "db", None)
        if db is None:
            return ""
        try:
            from fpdb_3_legacy.analytics_lifecycle import subsystem_statuses

            statuses = subsystem_statuses(db)
        except Exception:  # noqa: BLE001 - a note must never cost a result its display
            log.debug("Could not read the analytics subsystem status", exc_info=True)
            return ""

        # Named rather than summarised, and never claimed to explain *this*
        # zero: one stale subsystem the question does not read would otherwise
        # tell a reader their perfectly legitimate empty answer is a fault.
        never = [name for name, status in statuses.items() if status.recorded_version == 0 and status.is_stale]
        older = [
            name
            for name, status in statuses.items()
            if 0 < status.recorded_version < status.code_version
        ]
        if never:
            return _(
                "The analytics data for {names} has never been built. A question that reads it "
                "answers zero until it is: Database -> Rebuild Analytics Data.",
            ).format(names=", ".join(never))
        if older:
            return _(
                "The analytics data for {names} was derived by older rules, so a question that "
                "reads it may answer zero: Database -> Rebuild Analytics Data.",
            ).format(names=", ".join(older))
        return ""

    def _append_scope_note(self) -> None:
        """Say when an answer averages populations that should be asked apart.

        Appended to whatever note the view already wrote, so every view carries
        it: a mixture is a property of the question, not of the shape the
        answer is drawn in (#355).
        """
        scope = getattr(self, "_scope", None)
        warning = scope.describe() if scope is not None else ""
        if not warning:
            return
        existing = self.result_note.text()
        self.result_note.setText(f"{existing}  {warning}" if existing else warning)

    def _note_when_empty(self, total: Any, default: str = "") -> str:
        """The note under an answer, saying the one thing a zero cannot say.

        Used by every view rather than by the table alone: a range grid, a
        composition and a money report all answer zero on an unbuilt database,
        and a reader who lands on one of the other three would be told nothing.
        """
        if total:
            return default
        warning = self._analytics_not_built_note()
        return warning or default

    def _show_view_summary(self, spec: rviews.ViewSpec) -> None:
        """State what the table says in one line, and how to read it."""
        summary = rviews.summarize(self._last_result, spec)
        text = summary.value_text
        if summary.notes:
            text = f"{text} — " + " ".join(summary.notes)
        self.view_note.setText(text)
        self.view_note.setVisible(True)

    def _render_range(self, matrix: Any, spec: rviews.ViewSpec) -> None:
        self.result_stack.setCurrentWidget(self.range_grid)
        self.range_grid.set_matrix(matrix)
        self.sample_label.setText(f"{matrix.total_opportunities} decisions")
        self.elapsed_label.setText("")
        self.result_note.setText(
            self._note_when_empty(
                matrix.total_opportunities,
                _("Double-click a cell to load the hands behind it."),
            ),
        )
        self.view_note.setText(
            _("{question} — {how}").format(question=spec.question, how=spec.how_to_read),
        )
        self.view_note.setVisible(True)

    def _render_composition(self, composition: Any) -> None:
        self.result_stack.setCurrentWidget(self.composition_view)
        self.composition_view.set_composition(composition)
        self.sample_label.setText(f"{composition.total} decisions")
        self.elapsed_label.setText("")
        self.result_note.setText(self._note_when_empty(composition.total))
        self.view_note.setVisible(False)

    def _render_money(self, report: Any) -> None:
        self.result_stack.setCurrentWidget(self.money_view)
        self.money_view.set_report(report)
        self.sample_label.setText(f"{report.total.hands} hands")
        self.elapsed_label.setText("")
        self.result_note.setText(self._note_when_empty(report.total.hands))
        self.view_note.setVisible(False)

    def _render_result(self, result: Any) -> None:
        self.result_stack.setCurrentIndex(0)
        self._last_result = result
        self._has_run = True
        self.empty_state.setVisible(False)
        self.sample_label.setText(result.sample_text)
        self.elapsed_label.setText(f"{result.elapsed_ms:.0f} ms")
        columns = result.columns
        if result.empty_reason is not None:
            self.result_table.setRowCount(0)
            self.result_table.setColumnCount(len(columns))
            self._set_result_headers(columns)
            self.result_note.setText(self._note_when_empty(0, result.empty_reason))
            return
        rows = result.rows
        self.result_table.setRowCount(len(rows))
        self.result_table.setColumnCount(len(columns))
        self._set_result_headers(columns)
        for r, row in enumerate(rows):
            group = {col.key: row.get(col.key) for col in columns if col.source == "dimension"}
            for c, col in enumerate(columns):
                value = row.get(col.key)
                text = "" if value is None else str(value)
                if col.source == "dimension" and value is not None:
                    # A seat reads -1 here while this pane's own filter offers
                    # SB for the same value: the table was asking the reader to
                    # translate (#355). The raw value still travels in UserRole,
                    # so the drill-down keeps filtering on what was stored.
                    text = rb.value_label(col.key, value)
                elif col.key == "frequency_bp" and value is not None:
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

    def _set_result_headers(self, columns) -> None:
        """Write the result headings, and explain the honest ones.

        The engine's words stay -- ``decisions`` and ``numerator`` are the pair
        the analytics epic refuses to hide -- but Beginner mode says what they
        mean in the tooltip rather than leaving a user to guess.
        """
        self.result_table.setHorizontalHeaderLabels([col.heading for col in columns])
        explanations = {
            "denominator": _("Every decision the question applies to: the sample size."),
            "numerator": _("How many of those decisions the metric counted."),
            "value": _("The measurement itself, over the sample above."),
        }
        for index, col in enumerate(columns):
            item = self.result_table.horizontalHeaderItem(index)
            if item is None:
                continue
            if col.source in explanations:
                item.setToolTip(explanations[col.source])
            elif col.source == "dimension":
                item.setToolTip(rlabels.dimension_label(col.key))

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
            rendered = ", ".join(
                f"{rlabels.dimension_label(key)}={value}" for key, value in sorted(group.items())
            )
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
        # Retire the finished worker the way the query path does. Leaving it
        # set kept a dead QThread referenced by the widget for the tab's whole
        # life, and made the attribute useless as "a drill is running" --
        # anything waiting on it waited for ever, a failed drill included.
        if self._drill_worker is not None and self._drill_worker.serial == serial:
            self._drill_worker.deleteLater()
            self._drill_worker = None
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
        if self._drill_worker is not None and self._drill_worker.serial == serial:
            self._drill_worker.deleteLater()
            self._drill_worker = None
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

    # -- the empty state -----------------------------------------------------

    def _refresh_empty_state(self) -> None:
        """Fill the first-open screen: example questions and the rebuild note."""
        while self.example_layout.count():
            item = self.example_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for question in rb.example_questions():
            link = QLabel(f"• {question.name}")
            link.setStyleSheet("color: #61afef;")
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.setToolTip(question.description)
            link.mousePressEvent = lambda _event, preset=question.preset: self._load_example(preset)  # type: ignore[assignment]
            self.example_layout.addWidget(link)
        self.stale_note.setText(self._stale_message())
        self.stale_note.setVisible(bool(self.stale_note.text()))

    def _stale_message(self) -> str:
        """Whether the analytics tables need a rebuild, stated plainly.

        A database imported before the analytics layers existed has no rows to
        answer these questions with; saying so is the difference between an
        empty result and an unexplained one.
        """
        try:
            from fpdb_3_legacy.analytics_lifecycle import stale_subsystems

            stale = stale_subsystems(self.db)
        except Exception:  # noqa: BLE001 - a database without the meta table has nothing to say.
            return ""
        if not stale:
            return ""
        return _(
            "These questions need the analytics tables rebuilt before they can answer: {subsystems}. "
            "Rebuild them from the database menu, then run a question.",
        ).format(subsystems=", ".join(stale))

    def _load_example(self, preset: Any) -> None:
        """A first-run question: fill the builder with it and run it."""
        self._fill_builder(dict(preset))
        self.run_query()

    # -- presets -------------------------------------------------------------

    def _refresh_presets(self) -> None:
        """Rebuild the picker: the shipped library first, then the user's own.

        Built-in presets are read-only data from the package directory and user
        presets from the config directory, so a save can shadow a built-in but
        can never overwrite the shipped definition (#330).
        """
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        builtins = self._builtin_presets()
        if builtins:
            self._add_header(_("-- built-in presets --"))
            for category in presets_lib.categories(builtins):
                self._add_header(self._category_label(category))
                for preset in builtins:
                    if preset.category != category:
                        continue
                    self.preset_combo.addItem(
                        f"    {preset.name}",
                        {"kind": "builtin", "id": preset.id, "preset": preset.query},
                    )
                    self._set_item_tooltip(self.preset_combo.count() - 1, self._builtin_tooltip(preset))
        try:
            stored = self.presets.load()
        except ValueError as exc:
            log.warning("Presets not loaded: %s", exc)
            stored = {}
        self._add_header(_("-- saved presets --"))
        for name in sorted(stored):
            self.preset_combo.addItem(name, {"kind": "user", "name": name, "preset": stored[name]})
        self.preset_combo.setCurrentIndex(0)
        self.preset_combo.blockSignals(False)
        self.preset_combo.setEditText("")

    def _builtin_presets(self):
        """The shipped library, or nothing when it is explicitly disabled."""
        if self._builtins is None:
            try:
                self._builtins = presets_lib.builtin_presets()
            except ValueError as exc:
                log.warning("Shipped presets not loaded: %s", exc)
                self._builtins = ()
        return self._builtins

    @staticmethod
    def _category_label(category: str) -> str:
        return f"-- {category.title()} --"

    def _builtin_tooltip(self, preset: Any) -> str:
        hint = _("Adjust: {variables}").format(variables=", ".join(preset.variables)) if preset.variables else ""
        minimum = _("Aim for at least {n} decisions.").format(n=preset.min_sample) if preset.min_sample else ""
        return "\n\n".join(part for part in (preset.description, hint, minimum) if part)

    def _add_header(self, text: str) -> None:
        """A non-selectable section header inside the preset picker."""
        self.preset_combo.addItem(text, None)
        model = self.preset_combo.model()
        item = model.item(self.preset_combo.count() - 1) if hasattr(model, "item") else None
        if item is not None:
            item.setEnabled(False)

    def _set_item_tooltip(self, index: int, text: str) -> None:
        model = self.preset_combo.model()
        item = model.item(index) if hasattr(model, "item") else None
        if item is not None:
            item.setToolTip(text)

    def _fill_builder(self, preset: dict[str, Any]) -> None:
        """Put a preset into the controls, without running it."""
        try:
            clean = rb.validate_preset(preset)
        except ValueError as exc:
            QMessageBox.warning(self, _("Research browser"), str(exc))
            return
        self.metric_combo.setCurrentText(clean["metric"])
        self.group_edit.setText(", ".join(clean["group_by"]))
        for row in list(self._filter_rows):
            self._remove_filter_row(row)
        for name, value in clean["filters"].items():
            try:
                spec = rb.filter_spec(name)
            except ValueError:
                continue
            self._append_filter_row(spec)
            self._filter_rows[-1].set_value(value)
        self._update_summary()

    @staticmethod
    def _set_row_value(row: _FilterRow, value: Any) -> None:
        row.set_value(value)

    def _apply_preset(self) -> None:
        entry = self.preset_combo.currentData()
        if not isinstance(entry, dict) or not entry.get("preset"):
            return
        self._fill_builder(dict(entry["preset"]))
        self._describe_loaded_preset(entry)
        self.run_query()

    def _describe_loaded_preset(self, entry: dict[str, Any]) -> None:
        """Say which question is loaded and what to make your own (#330)."""
        note = ""
        if entry.get("kind") == "builtin":
            preset = presets_lib.find_preset(self._builtin_presets(), entry.get("id", ""))
            if preset is not None:
                parts = [preset.description]
                if preset.variables:
                    parts.append(
                        _("Adjust {variables} for your own game.").format(
                            variables=", ".join(preset.variables),
                        ),
                    )
                if preset.min_sample:
                    parts.append(_("Aim for at least {n} decisions.").format(n=preset.min_sample))
                note = " ".join(part for part in parts if part)
        self.preset_note.setText(note)

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(self, _("Save preset"), _("Name:"))
        if not ok or not name.strip():
            return
        name = name.strip()
        # A shipped preset is never overwritten: saving under its name keeps
        # the built-in intact and stores the user's version beside it.
        saved_as = name
        if presets_lib.is_builtin_name(self._builtin_presets(), name):
            saved_as = f"{name} (mine)"
        preset = self.current_preset()
        try:
            self.presets.save(saved_as, preset)
        except ValueError as exc:
            QMessageBox.warning(self, _("Research browser"), str(exc))
            return
        self._refresh_presets()
        index = self.preset_combo.findText(saved_as)
        if index >= 0:
            self.preset_combo.setCurrentIndex(index)
        if saved_as != name:
            self.preset_note.setText(
                _("Saved as \"{saved}\". The built-in preset \"{original}\" is unchanged.").format(
                    saved=saved_as, original=name,
                ),
            )

    def _delete_preset(self) -> None:
        entry = self.preset_combo.currentData()
        if not isinstance(entry, dict) or entry.get("kind") != "user":
            # A built-in is not the user's to delete.
            return
        self.presets.delete(entry["name"])
        self._refresh_presets()

    # -- lifecycle -----------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming.
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(2000)
        if self._drill_worker is not None and self._drill_worker.isRunning():
            self._drill_worker.wait(2000)
        if self._owns_db and self.db is not None:
            with contextlib.suppress(Exception):
                self.db.disconnect()
        super().closeEvent(event)
