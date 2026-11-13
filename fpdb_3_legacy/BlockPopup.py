#!/usr/bin/env python3
"""HUD popup that renders PokerTracker 4 popup groups (info popups, push charts).

Tranche 3 of the ``.pt4hud`` popup import: takes the text/stat grids extracted by
:func:`fpdb_3_legacy.pt4hud.extract_popup_groups` (stored in a JSON sidecar) and
renders them as a coloured grid, reproducing PT4's popup groups (e.g. SMK_Call
push ranges, the multi-stat "Tools" popup).

:func:`build_block_popup_widget` is independent of the HUD framework so it can be
unit-tested headlessly; :class:`BlockPopup` wraps it for the legacy HUD popup
system.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from fpdb_3_legacy import Stats
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.Popup import Popup

log = get_logger("hud")


def load_block_popup(source: str, group_name: str) -> dict | None:
    """Return the popup-group dict named ``group_name`` from a JSON sidecar."""
    with open(source, encoding="utf-8") as fh:
        data = json.load(fh)
    for group in data.get("popup_groups", []):
        if group.get("name") == group_name:
            return group
    return None


def build_block_popup_widget(
    group: dict,
    cell_px: int = 24,
    parent: QWidget | None = None,
    value_of: Callable[[dict], str | None] | None = None,
) -> QWidget:
    """Build a coloured grid widget for a popup group (text + stat cells).

    ``value_of`` gives the text a cell shows instead of its own, or None to keep
    it: the HUD passes the player's value of a cell that names an fpdb stat.
    """
    container = QWidget(parent)
    outer = QVBoxLayout(container)
    outer.setContentsMargins(2, 2, 2, 2)
    outer.setSpacing(2)

    title = QLabel(group.get("name", ""), container)
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    tf = QFont()
    tf.setBold(True)
    title.setFont(tf)
    outer.addWidget(title)

    grid_host = QWidget(container)
    grid = QGridLayout(grid_host)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(1)
    font = QFont()
    font.setPointSize(8)

    # Dense grids (push/fold charts) get uniform fixed-width cells so a single
    # long cell (e.g. a "Live Min Stack BB" legend label) can't blow out one
    # column; stat popups keep their natural label widths.
    dense = int(group.get("cols", 1)) >= 10
    for cell in group.get("cells", []):
        shown = value_of(cell) if value_of is not None else None
        lab = QLabel(str(cell.get("text", "")) if shown is None else shown, grid_host)
        lab.setFont(font)
        # Fixed height keeps the grid's total height deterministic so the scroll
        # area sizes the frame correctly (a min-height under-estimate clipped the
        # bottom rows of tall matrices).
        lab.setFixedHeight(cell_px)
        if dense:
            lab.setFixedWidth(cell_px + 22)
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fg = cell.get("fg") or "#e6f0ee"
        bg = cell.get("bg") or ""
        weight = "600" if cell.get("kind") == "stat" else "400"
        style = f"color:{fg};font-weight:{weight};padding:1px 5px;"
        if bg:
            style += f"background:{bg};"
        lab.setStyleSheet(style)
        grid.addWidget(lab, int(cell.get("row", 0)), int(cell.get("col", 0)))

    # Keep the grid at the top at its natural size; without the trailing stretch a
    # resizing scroll area stretches grid_host and pushes the cells down/around,
    # leaving a large empty gap above the matrix (so it scrolled to the wrong place).
    outer.addWidget(grid_host)
    outer.addStretch(1)
    return container


class BlockPopup(Popup):
    """HUD popup that displays an imported PT4 popup group as a coloured grid."""

    def create(self) -> None:  # type: ignore[override]
        super().create()
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        self.setLayout(layout)
        group = self._load_group()
        if group:
            layout.addWidget(build_block_popup_widget(group, parent=self, value_of=self._stat_value))
        else:
            layout.addWidget(QLabel("No popup group data"))

    def _player_id(self) -> int | None:
        stat_dict = getattr(self, "stat_dict", None) or {}
        for player_id, stats in stat_dict.items():
            if isinstance(stats, dict) and stats.get("seat") == getattr(self, "seat", None):
                return int(player_id)
        return None

    def _stat_value(self, cell: dict) -> str | None:
        """The player's value of a cell that names an fpdb stat (#782); None otherwise.

        Cells imported from PT4 hold PT4's own text and keep it; a stat put in
        the grid from the editor's catalogue carries its fpdb name as ``stat``.
        """
        stat = cell.get("stat") if cell.get("kind") == "stat" else None
        player_id = self._player_id() if stat else None
        if not stat or player_id is None:
            return None
        number = Stats.do_stat(self.stat_dict, player=player_id, stat=stat, hand_instance=self.hand_instance)
        return str(number[1]) if number else "--"

    def _load_group(self) -> dict | None:
        params = getattr(self.pop, "pu_class_params", None) or {}
        source = params.get("source")
        group_name = params.get("group")
        if source and group_name:
            try:
                return load_block_popup(source, group_name)
            except Exception:
                log.exception("BlockPopup: failed to load group %s from %s", group_name, source)
        return None
