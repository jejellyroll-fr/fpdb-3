#!/usr/bin/env python
"""The Design canvas of the HUD Preferences editor: one panel, cell by cell.

The canvas draws a panel's items as chips at their grid positions, and, when it
is *editable*, every empty cell too, plus a row of drop targets below the last
row. Everything that changes the panel goes out as a signal: the dialog makes
the change with ``layout_model`` and redraws. The canvas itself only reads the
panel, to show a drop as accepted or refused while it is dragged (#775).

What can be dropped on a cell:

* a chip of the same canvas (:data:`CELL_MIME`): moved onto a free cell,
  swapped with the item on a taken one (``layout_model.move``);
* a stat from Available Stats (:data:`stat_catalog.MIME_TYPE`): added on a free
  cell, refused on a taken one.

The Popup Windows tab uses the same class read-only (``editable=False``), with
its per-row ``+`` / ``−`` buttons.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QDrag, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QWidget,
)

from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.modern_hud_preferences import layout_model
from fpdb_3_legacy.modern_hud_preferences.stat_catalog import MIME_TYPE as STAT_MIME

log = get_logger("modern_hud_preferences.design_canvas")

#: What a chip carries while it is dragged: the id of its item.
CELL_MIME = "application/x-fpdb-hud-cell"

_VALID = "#19e3a0"
_REFUSED = "#e05252"

# Arrow keys -> (row step, column step).
_STEPS = {
    Qt.Key.Key_Left: (0, -1),
    Qt.Key.Key_Right: (0, 1),
    Qt.Key.Key_Up: (-1, 0),
    Qt.Key.Key_Down: (1, 0),
}


class _DropTarget:
    """Drag and drop handling shared by chips and empty cells."""

    canvas: HudDesignCanvas
    row: int
    col: int

    def _target_events(self) -> None:
        self.setAcceptDrops(True)  # type: ignore[attr-defined]

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.canvas.drag_over(self, event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.canvas.drag_over(self, event)

    def dragLeaveEvent(self, _event) -> None:  # noqa: N802 - Qt override
        self.canvas.clear_highlight()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.canvas.drop_on(self, event)


class _CanvasChip(_DropTarget, QFrame):
    """One item of the panel: clicked to select, dragged to move."""

    clicked = Signal()

    def __init__(self, kind: str, item_ref: dict, parent=None, *, canvas: HudDesignCanvas | None = None) -> None:
        super().__init__(parent)
        self.kind = kind
        self.item_ref = item_ref
        self.canvas = canvas  # type: ignore[assignment]
        self.row, self.col = layout_model.position(kind, item_ref) if isinstance(item_ref, dict) else (0, 0)
        self._press: QPoint | None = None
        if canvas is not None and canvas.editable:
            self._target_events()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.clicked.emit()
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if (
            self.canvas is not None
            and self.canvas.editable
            and self._press is not None
            and (event.position().toPoint() - self._press).manhattanLength() >= QApplication.startDragDistance()
        ):
            self._press = None
            self.canvas.start_drag(self)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._press = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self.canvas is not None and self.canvas.editable:
            self.canvas.item_activated.emit(self.item_ref)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self.canvas is not None and self.canvas.editable:
            self.canvas.cell_menu(self.row, self.col).exec(event.globalPos())


class _EmptyCell(_DropTarget, QFrame):
    """A free cell; the cells of the extra row below the panel add a row."""

    def __init__(self, canvas: HudDesignCanvas, row: int, col: int, *, new_row: bool = False) -> None:
        super().__init__()
        self.canvas = canvas
        self.row, self.col = row, col
        self.new_row = new_row
        self.setObjectName("emptyCell")
        self.setMinimumHeight(24)
        self._target_events()
        if new_row:
            self.setToolTip(_("Drop an item here to add a row"))
        self.show_state(None)

    def show_state(self, valid: bool | None) -> None:
        """Plain, or the colour of an accepted or refused drop."""
        if valid is None:
            colour = "#2c3e46" if not self.new_row else "#24343b"
            style = "dashed" if self.new_row else "dotted"
        else:
            colour, style = (_VALID if valid else _REFUSED), "solid"
        self.setStyleSheet(f"QFrame#emptyCell{{border:1px {style} {colour};border-radius:5px;background:transparent;}}")

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.canvas.setFocus()
        super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.canvas.cell_menu(self.row, self.col).exec(event.globalPos())


class HudDesignCanvas(QScrollArea):
    """WYSIWYG canvas for one panel (block), in the manner of PokerTracker 4's editor."""

    item_selected = Signal(object)  # (block_index, kind, item_ref)
    add_to_row = Signal(int)  # row index (read-only canvas: its + button)
    remove_from_row = Signal(int)  # row index (read-only canvas: its − button)
    # Editable canvas: the dialog makes the change.
    item_moved = Signal(object, int, int)  # item_ref, row, col
    stat_dropped = Signal(str, int, int)  # catalogue key, row, col
    item_removed = Signal(object)  # item_ref
    item_activated = Signal(object)  # item_ref (double-click, Enter)
    grid_edit = Signal(str, int)  # layout_model function name, row or column
    drop_refused = Signal(str)  # why, for the status bar

    # kind -> (icon letter, icon colour, chip background). Chip backgrounds are
    # dark theme tints; the type is conveyed by the coloured icon, not a light fill.
    TYPE = {
        "stat": ("S", "#3b6fd4", "#20303c"),
        "text": ("T", "#d79a2e", "#2e2a20"),
        "hline": ("H", "#d7b500", "#2e2a20"),
        "notes": ("N", "#3a9a3a", "#1f2d20"),
    }

    def __init__(self, parent=None, *, editable: bool = False) -> None:
        super().__init__(parent)
        self.editable = editable
        self.setWidgetResizable(True)
        # Transparent so the canvas follows the active theme's background.
        self.setStyleSheet("QScrollArea{background:transparent;border:1px solid #2c3e46;}")
        self._host = QWidget()
        self._host.setStyleSheet("background:transparent;")
        self.setWidget(self._host)
        self._grid = QGridLayout(self._host)
        self._grid.setContentsMargins(6, 6, 6, 6)
        self._grid.setHorizontalSpacing(4)
        self._grid.setVerticalSpacing(4)
        self.block_index = 0
        self.container: dict[str, Any] = {}
        self.chips: list[_CanvasChip] = []
        self.cells: list[_EmptyCell] = []
        self.selected_ref: Any = None
        self._highlighted: _DropTarget | None = None
        # A chip of this canvas being dragged, and where it was dropped: the move
        # waits for the drag to end, because the redraw it causes deletes the
        # chip the drag started from.
        self._dragging = False
        self._pending_move: tuple[dict, int, int] | None = None
        # Compact mode packs cells tightly (no icon/row buttons) for dense grids
        # such as 13x13 push-chart popups; off for normal HUD/popup editing.
        self.compact = False
        if editable:
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # --- Drawing --------------------------------------------------------------
    def _clear(self) -> None:
        self.chips = []
        self.cells = []
        self._highlighted = None
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item is None:
                continue
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def set_block(self, block_index: int, block: dict | None) -> None:
        self._clear()
        self.block_index = block_index
        self.container = block if isinstance(block, dict) else {}
        if not block:
            return
        cols = max(1, int(block.get("cols", 1)))
        rows = max(1, int(block.get("rows", 1)))
        items = self._chips_to_draw(block, cols)
        spacing = 1 if self.compact else 4
        self._grid.setHorizontalSpacing(spacing)
        self._grid.setVerticalSpacing(spacing)
        for r, c, span, kind, ref, label in items:
            chip = self._make_chip(kind, label, ref)
            self._grid.addWidget(chip, r, c, 1, max(1, span))
            self.chips.append(chip)
            rows = max(rows, r + 1)
        if self.editable:
            self._draw_empty_cells(rows, cols)
        elif not self.compact:
            # Per-row add/remove buttons in a trailing column (PT4 layout). Dense
            # compact grids (push charts) omit them -- you edit cells, not rows.
            for r in range(rows):
                self._grid.addWidget(self._row_buttons(r), r, cols)
        for c in range(cols):
            self._grid.setColumnStretch(c, 1)
        if self.selected_ref is not None:
            self.select_ref(self.selected_ref)

    def _chips_to_draw(self, block: dict, cols: int) -> list[tuple[int, int, int, str, dict, str]]:
        """``(row, col, span, kind, ref, label)`` of every item the canvas shows."""
        items = []
        for s in block.get("stats", []):
            span = int(s.get("colspan", 1) or 1)
            items.append((s.get("row", 0), s.get("col", 0), span, "stat", s, s.get("stat", "") or "(stat)"))
        for t in block.get("texts", []):
            if not (t.get("label", "") or "").strip() and not self.editable:
                continue  # empty placeholder cell -> leave blank like PT4
            r, c = t["rowcol"]
            items.append((r, c, int(t.get("colspan", 1) or 1), "text", t, t.get("label", "") or _("(label)")))
        for h in block.get("hlines", []):
            r, c = h["rowcol"]
            items.append((r, c, int(h.get("colspan") or cols), "hline", h, _("Horz Line")))
        return items

    def _draw_empty_cells(self, rows: int, cols: int) -> None:
        taken = layout_model.occupancy(self.container)
        for r in range(rows + 1):
            for c in range(cols):
                if (r, c) in taken:
                    continue
                cell = _EmptyCell(self, r, c, new_row=r >= rows)
                self._grid.addWidget(cell, r, c)
                self.cells.append(cell)

    def _make_chip(self, kind: str, label: str, ref: dict) -> _CanvasChip:
        letter, icon_col, _chip_bg = self.TYPE.get(kind, self.TYPE["stat"])
        chip = _CanvasChip(kind, ref, canvas=self)
        chip.setStyleSheet(self._chip_qss(kind, selected=False))
        lay = QHBoxLayout(chip)
        chip.clicked.connect(lambda c=chip: self._select(c))
        if self.editable:
            chip.setToolTip(_("Drag to move; drop on another item to swap them. Double-click to edit."))
        if self.compact:
            # Dense matrix cell: no icon, small centred text, tight padding.
            lay.setContentsMargins(2, 1, 2, 1)
            lay.setSpacing(0)
            name = QLabel(label)
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name.setStyleSheet(
                f"color:#e6f0ee;font-size:8pt;font-weight:700;border:none;background:transparent;"
                f"border-left:3px solid {icon_col};padding-left:3px;",
            )
            name.setMinimumWidth(34)
            lay.addWidget(name)
            return chip
        lay.setContentsMargins(3, 2, 6, 2)
        lay.setSpacing(4)
        icon = QLabel(letter)
        icon.setFixedSize(16, 16)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(f"background:{icon_col};color:white;font-weight:800;border-radius:3px;border:none;")
        name = QLabel(label)
        name.setStyleSheet("color:#e6f0ee;font-weight:600;border:none;background:transparent;")
        lay.addWidget(icon)
        lay.addWidget(name)
        lay.addStretch()
        return chip

    def _chip_qss(self, kind: str, selected: bool, drop: bool | None = None) -> str:
        _letter, _icon, bg = self.TYPE.get(kind, self.TYPE["stat"])
        if drop is not None:
            border = f"2px dashed {_VALID if drop else _REFUSED}"
        else:
            border = f"2px solid {_VALID}" if selected else "1px solid #3a4a52"
        return f"_CanvasChip{{background:{bg};border:{border};border-radius:5px;}}"

    _ROW_BTN_QSS = (
        "QPushButton{color:#e6f0ee;background:#2c3e46;border:1px solid #3d5a52;"
        "border-radius:3px;font-weight:800;padding:0;}"
        "QPushButton:hover{background:#37505a;}"
    )

    def _row_buttons(self, row: int) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(2, 0, 0, 0)
        h.setSpacing(2)
        plus = QPushButton(_("+"))
        plus.setFixedSize(22, 22)
        plus.setStyleSheet(self._ROW_BTN_QSS)
        plus.setToolTip(_("Add an item to this row"))
        plus.clicked.connect(lambda _=False, r=row: self.add_to_row.emit(r))
        minus = QPushButton(_("−"))
        minus.setFixedSize(22, 22)
        minus.setStyleSheet(self._ROW_BTN_QSS)
        minus.setToolTip(_("Remove the last item of this row"))
        minus.clicked.connect(lambda _=False, r=row: self.remove_from_row.emit(r))
        h.addWidget(plus)
        h.addWidget(minus)
        return w

    # --- Selection --------------------------------------------------------------
    def _select(self, chip: _CanvasChip) -> None:
        self.selected_ref = chip.item_ref
        for c in self.chips:
            c.setStyleSheet(self._chip_qss(c.kind, c is chip))
        if self.editable:
            self.setFocus()
        self.item_selected.emit((self.block_index, chip.kind, chip.item_ref))

    def select_ref(self, item_ref) -> None:
        """Highlight the chip matching item_ref (e.g. driven from the table)."""
        self.selected_ref = item_ref
        for c in self.chips:
            nested_ref = c.item_ref.get("_popup_stat") if isinstance(c.item_ref, dict) else None
            c.setStyleSheet(self._chip_qss(c.kind, c.item_ref is item_ref or nested_ref is item_ref))

    def chip_for(self, item_ref) -> _CanvasChip | None:
        return next((chip for chip in self.chips if chip.item_ref is item_ref), None)

    def cell_at(self, row: int, col: int) -> _EmptyCell | None:
        return next((cell for cell in self.cells if (cell.row, cell.col) == (row, col)), None)

    # --- Dragging ---------------------------------------------------------------
    def mime_for(self, item_ref) -> QMimeData:
        """What a drag of this canvas's item carries."""
        mime = QMimeData()
        mime.setData(CELL_MIME, str(id(item_ref)).encode("ascii"))
        return mime

    def start_drag(self, chip: _CanvasChip) -> None:
        drag = QDrag(chip)
        drag.setMimeData(self.mime_for(chip.item_ref))
        drag.setPixmap(chip.grab())
        drag.setHotSpot(QPoint(chip.width() // 2, chip.height() // 2))
        self._dragging, self._pending_move = True, None
        try:
            drag.exec(Qt.DropAction.MoveAction)
        finally:
            self._dragging = False
        self.clear_highlight()
        pending, self._pending_move = self._pending_move, None
        if pending is not None:
            self.item_moved.emit(*pending)

    def _dragged_item(self, mime: QMimeData) -> tuple[str, dict] | None:
        if not mime.hasFormat(CELL_MIME):
            return None
        try:
            wanted = int(bytes(mime.data(CELL_MIME).data()).decode("ascii"))
        except ValueError:
            return None
        chip = next((c for c in self.chips if id(c.item_ref) == wanted), None)
        return (chip.kind, chip.item_ref) if chip is not None else None

    def _dropped_key(self, mime: QMimeData) -> str:
        if not mime.hasFormat(STAT_MIME):
            return ""
        keys = bytes(mime.data(STAT_MIME).data()).decode("utf-8").splitlines()
        return keys[0].strip() if keys else ""

    def judge(self, mime: QMimeData, row: int, col: int) -> tuple[bool, str]:
        """Whether a drop of ``mime`` on ``(row, col)`` would be taken, and why not."""
        dragged = self._dragged_item(mime)
        if dragged is not None:
            kind, ref = dragged
            if kind == "hline":
                col = 0  # a line moves only up and down
            if not layout_model.fits_inside(self.container, kind, ref, col):
                return False, _("The item does not fit: it would leave the panel on the right.")
            if layout_model.preview_move(self.container, ref, row, col) == "refused":
                return False, _("No room there: the items would overlap.")
            return True, ""
        if self._dropped_key(mime):
            if col >= max(1, int(self.container.get("cols", 1) or 1)):
                return False, _("The stat does not fit: it would leave the panel on the right.")
            if not layout_model.can_place(self.container, row, col):
                return False, _("Cell already used: drop the stat on an empty cell.")
            return True, ""
        return False, ""

    def drag_over(self, target: _DropTarget, event) -> None:
        mime = event.mimeData()
        if not (mime.hasFormat(CELL_MIME) or mime.hasFormat(STAT_MIME)):
            event.ignore()
            return
        valid, _why = self.judge(mime, target.row, target.col)
        self._highlight(target, valid)
        event.setDropAction(Qt.DropAction.CopyAction if mime.hasFormat(STAT_MIME) else Qt.DropAction.MoveAction)
        event.accept()

    def _highlight(self, target: _DropTarget, valid: bool) -> None:
        if self._highlighted is not target:
            self.clear_highlight()
        self._highlighted = target
        if isinstance(target, _EmptyCell):
            target.show_state(valid)
        elif isinstance(target, _CanvasChip):
            target.setStyleSheet(self._chip_qss(target.kind, False, drop=valid))

    def clear_highlight(self) -> None:
        target, self._highlighted = self._highlighted, None
        if isinstance(target, _EmptyCell):
            target.show_state(None)
        elif isinstance(target, _CanvasChip):
            target.setStyleSheet(self._chip_qss(target.kind, target.item_ref is self.selected_ref))

    def drop_on(self, target: _DropTarget, event) -> None:
        mime = event.mimeData()
        row, col = target.row, target.col
        valid, why = self.judge(mime, row, col)
        self.clear_highlight()
        if not valid:
            if why:
                self.drop_refused.emit(why)
            event.ignore()
            return
        dragged = self._dragged_item(mime)
        if dragged is not None:
            kind, ref = dragged
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
            target_col = 0 if kind == "hline" else col
            if self._dragging:
                self._pending_move = (ref, row, target_col)
            else:
                self.item_moved.emit(ref, row, target_col)
            return
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        self.stat_dropped.emit(self._dropped_key(mime), row, col)

    # --- Keyboard ----------------------------------------------------------------
    def _selected_item(self) -> tuple[str, dict] | None:
        chip = self.chip_for(self.selected_ref) if self.selected_ref is not None else None
        return (chip.kind, chip.item_ref) if chip is not None else None

    def _neighbour(self, row: int, col: int, step: tuple[int, int]) -> _CanvasChip | None:
        """The nearest chip from ``(row, col)`` in the direction of ``step``."""
        d_row, d_col = step
        best: tuple[int, int, _CanvasChip] | None = None
        for chip in self.chips:
            r, c = chip.row, chip.col
            if d_col:
                if r != row or (c - col) * d_col <= 0:
                    continue
                key = (abs(c - col), 0)
            else:
                if (r - row) * d_row <= 0:
                    continue
                key = (abs(r - row), abs(c - col))
            if best is None or key < best[:2]:
                best = (*key, chip)
        return best[2] if best is not None else None

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt override
        if not self.editable:
            super().keyPressEvent(event)
            return
        selected = self._selected_item()
        key = Qt.Key(event.key())
        if selected is None:
            if key in _STEPS and self.chips:
                self._select(self.chips[0])
                event.accept()
                return
            super().keyPressEvent(event)
            return
        kind, ref = selected
        row, col = layout_model.position(kind, ref)
        if key in _STEPS:
            step = _STEPS[key]
            if event.modifiers() & Qt.KeyboardModifier.AltModifier:
                self._move_by_key(kind, ref, row + step[0], 0 if kind == "hline" else col + step[1])
            else:
                neighbour = self._neighbour(row, col, step)
                if neighbour is not None:
                    self._select(neighbour)
            event.accept()
            return
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.item_removed.emit(ref)
            event.accept()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.item_activated.emit(ref)
            event.accept()
            return
        super().keyPressEvent(event)

    def _move_by_key(self, kind: str, ref: dict, row: int, col: int) -> None:
        if row < 0 or col < 0:
            return
        mime = self.mime_for(ref)
        valid, why = self.judge(mime, row, col)
        if valid:
            self.item_moved.emit(ref, row, col)
        elif why:
            self.drop_refused.emit(why)

    # --- Rows and columns ----------------------------------------------------------
    def cell_menu(self, row: int, col: int) -> QMenu:
        """Insert or delete the row or column of a cell."""
        menu = QMenu(self)
        rows = max(1, int(self.container.get("rows", 1) or 1))
        cols = max(1, int(self.container.get("cols", 1) or 1))
        entries = (
            (_("Insert a row above"), "insert_row", row, True),
            (_("Insert a row below"), "insert_row", row + 1, True),
            (_("Insert a column to the left"), "insert_col", col, True),
            (_("Insert a column to the right"), "insert_col", col + 1, True),
            (
                _("Delete this row"),
                "delete_row",
                row,
                row < rows and rows > 1 and layout_model.row_is_empty(self.container, row),
            ),
            (
                _("Delete this column"),
                "delete_col",
                col,
                cols > 1 and layout_model.col_is_empty(self.container, col),
            ),
        )
        for index, (text, operation, at, enabled) in enumerate(entries):
            if index == 4:
                menu.addSeparator()
            action = menu.addAction(text)
            action.setEnabled(bool(enabled))
            action.setData((operation, at))
            action.triggered.connect(lambda _checked=False, op=operation, i=at: self.grid_edit.emit(op, i))
        return menu
