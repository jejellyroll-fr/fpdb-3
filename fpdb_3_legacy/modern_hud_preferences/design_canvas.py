#!/usr/bin/env python
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QWidget,
)

from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.Translations import _

log = get_logger("modern_hud_preferences.design_canvas")

class _CanvasChip(QFrame):
    """A single clickable item chip on the design canvas."""

    clicked = Signal()

    def __init__(self, kind: str, item_ref: dict, parent=None) -> None:
        super().__init__(parent)
        self.kind = kind
        self.item_ref = item_ref

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.clicked.emit()
        super().mousePressEvent(event)


class HudDesignCanvas(QScrollArea):
    """PT4-style WYSIWYG design canvas for one panel (block).

    Renders the panel's items — stats, text labels, horizontal lines — as typed
    coloured chips placed in their grid positions (honouring colspan). Clicking a
    chip selects it; each occupied row carries +/- buttons. Mirrors the
    bottom-left design area of PokerTracker 4's Hud Profile Editor.
    """

    item_selected = Signal(object)  # (block_index, kind, item_ref)
    add_to_row = Signal(int)  # row index
    remove_from_row = Signal(int)  # row index

    # kind -> (icon letter, icon colour, chip background). Chip backgrounds are
    # dark theme tints; the type is conveyed by the coloured icon, not a light fill.
    TYPE = {
        "stat": ("S", "#3b6fd4", "#20303c"),
        "text": ("T", "#d79a2e", "#2e2a20"),
        "hline": ("H", "#d7b500", "#2e2a20"),
        "notes": ("N", "#3a9a3a", "#1f2d20"),
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
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
        self.chips: list[_CanvasChip] = []
        self.selected_ref: Any = None
        # Compact mode packs cells tightly (no icon/row buttons) for dense grids
        # such as 13x13 push-chart popups; off for normal HUD/popup editing.
        self.compact = False

    def _clear(self) -> None:
        self.chips = []
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
        if not block:
            return
        cols = max(1, int(block.get("cols", 1)))
        rows = max(1, int(block.get("rows", 1)))
        items = []  # (row, col, span, kind, ref, label)
        for s in block.get("stats", []):
            items.append(
                (
                    s.get("row", 0),
                    s.get("col", 0),
                    int(s.get("colspan", 1) or 1),
                    "stat",
                    s,
                    s.get("stat", "") or "(stat)",
                )
            )
        for t in block.get("texts", []):
            if not (t.get("label", "") or "").strip():
                continue  # empty placeholder cell -> leave blank like PT4
            r, c = t["rowcol"]
            items.append((r, c, int(t.get("colspan", 1) or 1), "text", t, t["label"]))
        for h in block.get("hlines", []):
            r, c = h["rowcol"]
            items.append((r, c, int(h.get("colspan") or cols), "hline", h, "Horz Line"))
        spacing = 1 if self.compact else 4
        self._grid.setHorizontalSpacing(spacing)
        self._grid.setVerticalSpacing(spacing)
        for r, c, span, kind, ref, label in items:
            chip = self._make_chip(kind, label, ref)
            self._grid.addWidget(chip, r, c, 1, max(1, span))
            self.chips.append(chip)
        # Per-row add/remove buttons in a trailing column (PT4 layout). Dense
        # compact grids (push charts) omit them — you edit cells, not rows.
        if not self.compact:
            for r in range(rows):
                self._grid.addWidget(self._row_buttons(r), r, cols)
        for c in range(cols):
            self._grid.setColumnStretch(c, 1)

    def _make_chip(self, kind: str, label: str, ref: dict) -> _CanvasChip:
        letter, icon_col, _chip_bg = self.TYPE.get(kind, self.TYPE["stat"])
        chip = _CanvasChip(kind, ref)
        chip.setStyleSheet(self._chip_qss(kind, selected=False))
        lay = QHBoxLayout(chip)
        chip.clicked.connect(lambda c=chip: self._select(c))
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

    def _chip_qss(self, kind: str, selected: bool) -> str:
        _letter, _icon, bg = self.TYPE.get(kind, self.TYPE["stat"])
        border = "2px solid #19e3a0" if selected else "1px solid #3a4a52"
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

    def _select(self, chip: _CanvasChip) -> None:
        self.selected_ref = chip.item_ref
        for c in self.chips:
            c.setStyleSheet(self._chip_qss(c.kind, c is chip))
        self.item_selected.emit((self.block_index, chip.kind, chip.item_ref))

    def select_ref(self, item_ref) -> None:
        """Highlight the chip matching item_ref (e.g. driven from the table)."""
        self.selected_ref = item_ref
        for c in self.chips:
            nested_ref = c.item_ref.get("_popup_stat") if isinstance(c.item_ref, dict) else None
            c.setStyleSheet(self._chip_qss(c.kind, c.item_ref is item_ref or nested_ref is item_ref))


# --- Add/Edit Stat Dialog ---
