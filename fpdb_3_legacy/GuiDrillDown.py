"""The "Source hands" pane: both sides of a comparison, openable (#366).

One widget, two hosts. The research browser puts it behind a comparison row
and the study dashboard puts it under the panels, because the question is the
same in both places -- *which hands made this difference* -- and answering it
twice would be two chances to answer it differently.

The pane never merges the two sides. It offers up to four explicit hand sets
(your population, your actions, the field's population, the field's actions),
loads one page of one of them at a time, off the Qt thread, and says where
that page sits in the whole. A double-click hands the hand id back to the
host, which owns the replayer.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.research_drilldown import (
    DEFAULT_PAGE_SIZE,
    SIDE_DRILL_COLUMNS,
    SIDE_HERO,
    DrillContext,
    DrillCounts,
    DrillTarget,
    drill_counts,
    has_numerator,
    run_side_drill,
)
from fpdb_3_legacy.research_worker_db import worker_database
from fpdb_3_legacy.ring_stats.styles import get_theme_palette

log = get_logger("gui_drilldown")


def _target_labels() -> dict[str, str]:
    """The four button names, translated here rather than in the model.

    The model names its targets in plain English so a CLI and the tests read
    the same words; the translation belongs to the widget that draws them, and
    a catalogue cannot extract a string it only sees at run time.
    """
    return {
        "hero_population": _("Your population"),
        "hero_numerator": _("Your actions"),
        "field_population": _("Field population"),
        "field_numerator": _("Field actions"),
    }


class _SideDrillWorker(QThread):
    """One page of one side's hands, off the event loop."""

    finished_ok = Signal(object, int)
    failed = Signal(str, int)

    def __init__(
        self,
        db: Any,
        context: DrillContext,
        side: str,
        numerator_only: bool,
        limit: int,
        offset: int,
        serial: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._context = context
        self._side = side
        self._numerator_only = numerator_only
        self._limit = limit
        self._offset = offset
        self._serial = serial

    @property
    def serial(self) -> int:
        return self._serial

    def run(self) -> None:
        try:
            with worker_database(self._db) as db:
                page = run_side_drill(
                    db,
                    self._context,
                    self._side,
                    numerator_only=self._numerator_only,
                    limit=self._limit,
                    offset=self._offset,
                )
        except Exception as exc:  # noqa: BLE001 - worker boundary reports errors via signal.
            log.exception("Source hands page failed")
            self.failed.emit(str(exc), self._serial)
            return
        self.finished_ok.emit(page, self._serial)


class _CountsWorker(QThread):
    """The four hand-set sizes, for a host that has no comparison row to read."""

    finished_ok = Signal(object, int)
    failed = Signal(str, int)

    def __init__(self, db: Any, context: DrillContext, serial: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._context = context
        self._serial = serial

    @property
    def serial(self) -> int:
        return self._serial

    def run(self) -> None:
        try:
            with worker_database(self._db) as db:
                counts = drill_counts(db, self._context)
        except Exception as exc:  # noqa: BLE001 - worker boundary reports errors via signal.
            log.exception("Source hands counts failed")
            self.failed.emit(str(exc), self._serial)
            return
        self.finished_ok.emit(counts, self._serial)


class SourceHandsPane(QWidget):
    """Hero and Field source hands, separately selectable and paged."""

    hand_activated = Signal(int)

    def __init__(self, db: Any, parent: QWidget | None = None, *, page_size: int = DEFAULT_PAGE_SIZE) -> None:
        super().__init__(parent)
        self.db = db
        self._page_size = page_size
        self._context: DrillContext | None = None
        self._counts: DrillCounts | None = None
        self._targets: tuple[DrillTarget, ...] = ()
        self._target: DrillTarget | None = None
        self._offset = 0
        self._serial = 0
        self._counts_serial = 0
        # Every worker started, retired when Qt says it finished. A
        # superseded one still runs to completion -- its result is dropped by
        # the serial check -- and would otherwise stay a child of this pane
        # for the tab's whole life.
        self._workers: list[QThread] = []
        self._page: Any = None
        self._build_ui()

    # -- construction --------------------------------------------------------

    def _build_ui(self) -> None:
        colors = get_theme_palette()
        muted = colors.get("muted_text", "#a0aec0")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 0, 0, 0)

        self.title_label = QLabel(_("Source hands"))
        self.title_label.setStyleSheet(
            f"font-weight: bold; color: {muted}; font-size: 11px; text-transform: uppercase;",
        )
        layout.addWidget(self.title_label)

        self.context_label = QLabel("")
        self.context_label.setWordWrap(True)
        self.context_label.setStyleSheet(f"color: {muted}; font-size: 11px;")
        layout.addWidget(self.context_label)

        self.targets_row = QHBoxLayout()
        self.targets_row.setSpacing(4)
        layout.addLayout(self.targets_row)
        self._target_buttons: dict[str, QPushButton] = {}

        self.table = QTableWidget()
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.itemDoubleClicked.connect(self._emit_hand)
        layout.addWidget(self.table, 1)

        paging = QHBoxLayout()
        self.previous_button = QPushButton(_("◀ Previous"))
        self.previous_button.clicked.connect(lambda: self._step(-1))
        self.next_button = QPushButton(_("Next ▶"))
        self.next_button.clicked.connect(lambda: self._step(1))
        paging.addWidget(self.previous_button)
        paging.addWidget(self.next_button)
        paging.addStretch(1)
        layout.addLayout(paging)

        self.note_label = QLabel(_("Select a row to see the hands behind both sides of it."))
        self.note_label.setWordWrap(True)
        self.note_label.setStyleSheet(f"color: {muted}; font-size: 11px;")
        layout.addWidget(self.note_label)

        self.coverage_label = QLabel("")
        self.coverage_label.setWordWrap(True)
        self.coverage_label.setStyleSheet(f"color: {muted}; font-size: 11px;")
        layout.addWidget(self.coverage_label)
        self._set_paging_enabled(previous=False, next_page=False)

    # -- the public API ------------------------------------------------------

    def clear(self, message: str = "") -> None:
        """Forget the current row; a pending page will not be rendered."""
        self._serial += 1
        self._counts_serial += 1
        self._context = None
        self._counts = None
        self._targets = ()
        self._target = None
        self._page = None
        self._offset = 0
        self._render_targets()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.context_label.setText("")
        self.coverage_label.setText("")
        self.note_label.setText(message or _("Select a row to see the hands behind both sides of it."))
        self._set_paging_enabled(previous=False, next_page=False)

    def set_context(
        self,
        context: DrillContext,
        counts: DrillCounts | None = None,
        *,
        default_side: str = SIDE_HERO,
        default_numerator: bool = False,
    ) -> None:
        """Show one row's four hand sets and open one of them.

        ``counts`` is the sizes the caller already has on screen -- a rendered
        comparison row knows all four, and asking the database for what is
        already displayed would be four queries for nothing. Without it the
        pane counts them itself, on a worker.

        ``default_side`` is which set opens first. A study reading the field
        opens on the field, so the pane agrees with the page around it; the
        other three sets stay one click away either way.
        """
        self._serial += 1
        self._counts_serial += 1
        self._context = context
        self._offset = 0
        self._page = None
        self.context_label.setText(context.label)
        self._counts = counts
        self._targets = self._targets_for(context, counts)
        self._target = self._default_target(default_side, default_numerator)
        self._render_targets()
        if counts is None:
            self._start_counts(context)
        self._load()

    def _default_target(self, side: str, numerator_only: bool) -> DrillTarget | None:
        if not self._targets:
            return None
        for target in self._targets:
            if target.side == side and target.numerator_only == numerator_only:
                return target
        return self._targets[0]

    @property
    def current_target(self) -> DrillTarget | None:
        """Which of the four sets is on screen, for the host and the tests."""
        return self._target

    @property
    def page(self) -> Any:
        """The last rendered page, or ``None`` before the first one."""
        return self._page

    def select_target(self, side: str, *, numerator_only: bool = False) -> None:
        """Open one named set; the host uses this to deep-link into a side."""
        for target in self._targets:
            if target.side == side and target.numerator_only == numerator_only:
                self._choose(target)
                return
        raise KeyError(f"No drill target for side {side!r} (numerator_only={numerator_only})")

    # -- targets -------------------------------------------------------------

    @staticmethod
    def _targets_for(context: DrillContext, counts: DrillCounts | None) -> tuple[DrillTarget, ...]:
        with_numerator = has_numerator(context.side_query(SIDE_HERO, numerator_only=True))
        known = counts or DrillCounts(
            hero_population=0, hero_numerator=0, field_population=0, field_numerator=0,
        )
        targets = known.targets(with_numerator=with_numerator)
        if counts is not None:
            return targets
        # No sizes yet: offer the sets without pretending to know how big
        # they are. A count of zero shown before counting reads as "no hands".
        return tuple(
            DrillTarget(side=target.side, numerator_only=target.numerator_only, count=None, label=target.label)
            for target in targets
        )

    def _render_targets(self) -> None:
        while self.targets_row.count():
            item = self.targets_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._target_buttons = {}
        labels = _target_labels()
        for target in self._targets:
            count = "" if target.count is None else f" ({target.count:,})"
            button = QPushButton(f"{labels.get(target.id, target.label)}{count}")
            button.setCheckable(True)
            button.setChecked(self._target is not None and target.id == self._target.id)
            button.setToolTip(
                _("These hands use the same filters as the other side; only the population differs."),
            )
            button.clicked.connect(lambda _checked=False, chosen=target: self._choose(chosen))
            self._target_buttons[target.id] = button
            self.targets_row.addWidget(button)
        self.targets_row.addStretch(1)

    def _choose(self, target: DrillTarget) -> None:
        self._target = target
        self._offset = 0
        for target_id, button in self._target_buttons.items():
            button.setChecked(target_id == target.id)
        self._load()

    # -- loading -------------------------------------------------------------

    def _start_counts(self, context: DrillContext) -> None:
        self._counts_serial += 1
        worker = _CountsWorker(self.db, context, self._counts_serial, self)
        worker.finished_ok.connect(self._counts_done)
        worker.failed.connect(self._counts_failed)
        self._start(worker)

    def _counts_done(self, counts: Any, serial: int) -> None:
        if serial != self._counts_serial or self._context is None:
            return  # A newer row superseded this one; its sizes are not ours.
        self._counts = counts
        chosen = self._target
        self._targets = self._targets_for(self._context, counts)
        if chosen is not None:
            self._target = next(
                (target for target in self._targets if target.id == chosen.id),
                self._targets[0] if self._targets else None,
            )
        self._render_targets()

    def _counts_failed(self, message: str, serial: int) -> None:
        if serial != self._counts_serial:
            return
        log.warning("Source hands counts unavailable: %s", message)

    def _start(self, worker: QThread) -> None:
        worker.finished.connect(lambda worker=worker: self._retire(worker))
        self._workers.append(worker)
        worker.start()

    def _retire(self, worker: QThread) -> None:
        if worker in self._workers:
            self._workers.remove(worker)
        worker.deleteLater()

    def _load(self) -> None:
        if self._context is None or self._target is None:
            return
        self._serial += 1
        self.note_label.setText(_("Loading hands…"))
        self._set_paging_enabled(previous=False, next_page=False)
        worker = _SideDrillWorker(
            self.db,
            self._context,
            self._target.side,
            self._target.numerator_only,
            self._page_size,
            self._offset,
            self._serial,
            self,
        )
        worker.finished_ok.connect(self._page_done)
        worker.failed.connect(self._page_failed)
        self._start(worker)

    def _step(self, direction: int) -> None:
        offset = self._offset + direction * self._page_size
        self._offset = max(offset, 0)
        self._load()

    def _page_done(self, page: Any, serial: int) -> None:
        if serial != self._serial:
            return  # A stale page never replaces a newer selection.
        self._page = page
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(page.rows))
        self.table.setColumnCount(len(SIDE_DRILL_COLUMNS))
        self.table.setHorizontalHeaderLabels([_(column.heading) for column in SIDE_DRILL_COLUMNS])
        for row_index, row in enumerate(page.rows):
            for column_index, column in enumerate(SIDE_DRILL_COLUMNS):
                value = row.get(column.key)
                item = QTableWidgetItem("" if value is None else str(value))
                if column.key == "handId":
                    item.setData(Qt.ItemDataRole.UserRole, int(row["handId"]))
                self.table.setItem(row_index, column_index, item)
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        self.note_label.setText(f"{self._target_text()} — {page.page_note}")
        self.coverage_label.setText(page.card_coverage_note)
        self._set_paging_enabled(previous=page.has_previous, next_page=page.has_more)

    def _page_failed(self, message: str, serial: int) -> None:
        if serial != self._serial:
            return
        self.table.setRowCount(0)
        self.coverage_label.setText("")
        self.note_label.setText(message)
        self._set_paging_enabled(previous=False, next_page=False)

    def _target_text(self) -> str:
        if self._target is None:
            return ""
        return _target_labels().get(self._target.id, self._target.label)

    def _set_paging_enabled(self, *, previous: bool, next_page: bool) -> None:
        self.previous_button.setEnabled(previous)
        self.next_button.setEnabled(next_page)

    # -- the replayer --------------------------------------------------------

    def _emit_hand(self, item: QTableWidgetItem) -> None:
        id_item = self.table.item(item.row(), 0)
        if id_item is None:
            return
        hand_id = id_item.data(Qt.ItemDataRole.UserRole)
        if hand_id is None:
            text = id_item.text().strip()
            if not text.isdigit():
                return
            hand_id = int(text)
        self.hand_activated.emit(int(hand_id))

    def stop(self) -> None:
        """Stop waiting for any page; the hosts call this when they close."""
        self._serial += 1
        self._counts_serial += 1
        for worker in list(self._workers):
            if worker.isRunning():
                worker.wait(2000)


__all__ = ["SourceHandsPane"]
