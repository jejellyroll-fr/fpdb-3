#!/usr/bin/env python3
"""HUD popup that renders PokerTracker 4 range charts (push/fold Nash grids).

Phase C of the ``.pt4hud`` import: takes the 13x13 ``Chart`` grids extracted by
:mod:`fpdb_3_legacy.pt4hud` and renders them as a coloured hand matrix in a HUD
popup, reproducing the look of PT4's range-chart popups.

The grid widget (:func:`build_grid_widget`) is independent of the HUD framework
so it can be unit-tested headlessly; :class:`RangeChartPopup` wraps it for the
legacy HUD popup system.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.Popup import Popup

log = get_logger("hud")

# Grid ranks, strongest first. Suited combos sit in the upper-right triangle
# (row < col), offsuit in the lower-left, pairs on the diagonal.
RANKS = "AKQJT98765432"


def hand_to_rowcol(hand: str) -> tuple[int, int]:
    """Map a hand label ("AA", "AKs", "72o") to its (row, col) in the matrix."""
    a, b = hand[0], hand[1]
    ra, rb = RANKS.index(a), RANKS.index(b)
    if ra == rb:
        return ra, ra  # pair on the diagonal
    hi, lo = (ra, rb) if ra < rb else (rb, ra)  # hi rank = lower index
    suited = hand.endswith("s")
    return (hi, lo) if suited else (lo, hi)


def _contrast_text(fill: str) -> str:
    """Pick black or white text for readability on a ``#rrggbb`` background."""
    try:
        r, g, b = (int(fill[i : i + 2], 16) for i in (1, 3, 5))
    except (ValueError, IndexError):
        return "#000000"
    # perceived luminance (ITU-R BT.601)
    return "#000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 140 else "#ffffff"


def build_grid_widget(chart, cell_px: int = 26, parent: QWidget | None = None) -> QWidget:
    """Build a 13x13 coloured matrix widget for a :class:`pt4hud.Chart`."""
    container = QWidget(parent)
    outer = QVBoxLayout(container)
    outer.setContentsMargins(2, 2, 2, 2)
    outer.setSpacing(2)

    title = QLabel(chart.name, container)
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
    font.setPointSize(7)

    for cell in chart.cells:
        row, col = hand_to_rowcol(cell.hand)
        lab = QLabel(cell.hand, grid_host)
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lab.setFixedSize(cell_px, cell_px)
        lab.setFont(font)
        lab.setStyleSheet(
            f"background:{cell.fill};color:{_contrast_text(cell.fill)};"
            "border:1px solid #00000022;",
        )
        grid.addWidget(lab, row, col)

    # Trailing stretch keeps the grid at the top at its natural size (a resizing
    # scroll area would otherwise stretch it and push the cells around).
    outer.addWidget(grid_host)
    outer.addStretch(1)
    return container


class RangeChartPopup(Popup):
    """HUD popup that displays one or more extracted PT4 range charts.

    Chart data is provided via ``pop.pu_class_params["charts"]`` (a list of
    :class:`pt4hud.Chart`) or, failing that, loaded from a ``.pt4hud`` / JSON
    file at ``pop.pu_class_params["source"]``.
    """

    def create(self) -> None:
        super().create()
        charts = self._load_charts()
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        self.setLayout(layout)

        if not charts:
            layout.addWidget(QLabel("No range charts configured"))
            return
        for chart in charts:
            layout.addWidget(build_grid_widget(chart, parent=self))

    def _load_charts(self) -> list:
        params = getattr(self.pop, "pu_class_params", None) or {}
        if params.get("charts"):
            return params["charts"]
        source = params.get("source")
        if source:
            try:
                return load_charts(source)
            except Exception:
                log.exception("RangeChartPopup: failed to load charts from %s", source)
        return []


def load_charts(source: str) -> list:
    """Load charts from a ``.pt4hud`` binary or a parser ``--json`` export."""
    from fpdb_3_legacy import pt4hud

    if source.endswith(".json"):
        import json

        with open(source, encoding="utf-8") as fh:
            data = json.load(fh)
        return [
            pt4hud.Chart(
                name=c["name"],
                cells=[pt4hud.ChartCell(hand=x["hand"], fill=x["fill"], text=x.get("text", "#000000")) for x in c["cells"]],
            )
            for c in data.get("charts", [])
        ]
    return pt4hud.extract_charts(source)
