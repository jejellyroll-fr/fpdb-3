"""The workbench's non-table presentations (#331).

The Research browser draws one thing well: a table of grouped rows. Three of the
questions the workbench offers are not tables -- a 13x13 grid, a composition,
and two money columns that only mean something together -- and each needs its
own widget with its own honesty rules:

* a **grid** cell under the sample threshold stays uncoloured and says so in its
  tooltip, because colouring it would present a count as a reading (#301);
* a **composition** states its coverage: the decisions whose cards nobody saw
  are counted apart rather than distributed across the categories (#302);
* a **money** table carries realized and EV-adjusted side by side with the
  difference named, so "luck" is a column and not a footnote (#300).

Qt only: every number comes from the Qt-free models (``holdem_ranges``,
``hand_state_composition``, ``analytics_profit``, ``research_views``), so these
widgets can be checked offscreen against the same golden corpus the models are.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import holdem_ranges
from fpdb_3_legacy.hand_state_composition import Composition
from fpdb_3_legacy.holdem_classes import grid_labels
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.ring_stats.styles import get_theme_palette
from fpdb_3_legacy.ring_stats.views.starting_hands_view import HoldemGridCell

BP = 100
"""Frequencies arrive in basis points; a screen shows per cent."""

RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


def _percent(bp: Any) -> str:
    return "n/a" if bp is None else f"{float(bp) / BP:.1f}%"


def _money(cents: Any) -> str:
    return "n/a" if cents is None else f"{float(cents) / 100:.2f}"


class RangeGridWidget(QWidget):
    """A filtered population on the 13x13 grid, with its legend and its gaps."""

    cell_activated = Signal(str)

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._matrix: holdem_ranges.RangeMatrix | None = None
        self._view = holdem_ranges.DEFAULT_VIEW

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        controls = QHBoxLayout()
        controls.addWidget(QLabel(_("Colour by:")))
        self.view_combo = QComboBox()
        for name, metric in holdem_ranges.METRICS.items():
            self.view_combo.addItem(_(metric.label), name)
            self.view_combo.setItemData(
                self.view_combo.count() - 1, _(metric.definition), Qt.ItemDataRole.ToolTipRole,
            )
        controls.addWidget(self.view_combo)
        controls.addStretch()
        layout.addLayout(controls)

        self.legend = QLabel("")
        self.legend.setWordWrap(True)
        layout.addWidget(self.legend)

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setSpacing(1)
        self._cells: dict[str, HoldemGridCell] = {}
        # The 169 labels come from the model that names the classes, never from
        # a second composition here: a grid that renames a class shows another
        # population than the query it claims to draw.
        for row, labels in enumerate(grid_labels()):
            for col, hand in enumerate(labels):
                cell = HoldemGridCell(hand)
                cell.activated.connect(self.cell_activated)
                grid.addWidget(cell, row, col)
                self._cells[hand] = cell
        layout.addWidget(grid_host, 1)

        self.unknown = QLabel("")
        self.unknown.setWordWrap(True)
        layout.addWidget(self.unknown)

        self.view_combo.currentIndexChanged.connect(self._on_view_changed)
        # The combo is inserted in the model's own order, whose first entry is
        # not the default reading: without this the control says "Action
        # frequency" while the cells and the legend say "Occurrences".
        self._select_view_item(holdem_ranges.DEFAULT_VIEW)

    def _select_view_item(self, view: str) -> None:
        """Move the combo to a view without re-entering the change handler."""
        index = self.view_combo.findData(view)
        if index < 0 or index == self.view_combo.currentIndex():
            return
        blocked = self.view_combo.blockSignals(True)
        self.view_combo.setCurrentIndex(index)
        self.view_combo.blockSignals(blocked)

    def _on_view_changed(self) -> None:
        self.set_view(str(self.view_combo.currentData()))

    def set_view(self, view: str) -> None:
        """Re-colour the current grid in another reading of the same numbers."""
        self._view = view
        self._select_view_item(view)
        if self._matrix is not None:
            self._paint(self._matrix)

    def set_matrix(self, matrix: holdem_ranges.RangeMatrix, view: str | None = None) -> None:
        """Draw a matrix. Nothing here computes: the model already did."""
        self._matrix = matrix
        if view is not None:
            self._view = view
        self._select_view_item(self._view)
        self._paint(matrix)

    def set_matrix_clear(self) -> None:
        """Clear the grid when its dashboard panel is waiting for a result."""
        self._matrix = None
        for cell in self._cells.values():
            cell.setToolTip("")
            cell.set_color(get_theme_palette().get("sidebar", "#1a202c"))
        self.legend.setText("")
        self.unknown.setText("")

    def _paint(self, matrix: holdem_ranges.RangeMatrix) -> None:
        spec = holdem_ranges.metric(self._view)
        values = [value for row in matrix.values(self._view) for value in row if value is not None]
        scale = max((abs(value) for value in values), default=0.0)
        for row in matrix.grid():
            for cell in row:
                widget = self._cells.get(cell.label)
                if widget is not None:
                    widget.update_range(cell, self._view, matrix.total_opportunities, scale)
        below = matrix.sample_below_threshold()
        legend = [f"{_(spec.label)} ({spec.unit}) — {_(spec.definition)}"]
        legend.append(
            _("Cells without enough of a sample stay uncoloured; hover one to read its count.")
            if below
            else _("No cell is below the sample threshold."),
        )
        legend.extend(matrix.notes)
        self.legend.setText("\n".join(legend))
        unknown = matrix.unknown_opportunities()
        drawn = matrix.total_opportunities - unknown
        share = _percent(round(drawn * 10000 / matrix.total_opportunities)) if matrix.total_opportunities else "n/a"
        self.unknown.setText(
            _(
                "{decisions} decisions in this selection have no known hole cards and are not in "
                "the grid; {share} of the decisions are drawn.",
            ).format(decisions=unknown, share=share),
        )


class CompositionWidget(QWidget):
    """One population's composition over one hand-state dimension."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.headline = QLabel("")
        self.headline.setWordWrap(True)
        layout.addWidget(self.headline)
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels([_("Category"), _("Decisions"), _("Share")])
        self.table.verticalHeader().hide()
        layout.addWidget(self.table, 1)
        self.notes = QLabel("")
        self.notes.setWordWrap(True)
        layout.addWidget(self.notes)

    def set_composition(self, composition: Composition) -> None:
        self.headline.setText(
            _("{label}: {classified} classified decisions of {total} ({share} covered)").format(
                label=composition.label,
                classified=composition.classified,
                total=composition.total,
                share=_percent(composition.coverage_bp),
            ),
        )
        self.table.setRowCount(len(composition.rows))
        for row, entry in enumerate(composition.rows):
            label = entry.label + (" *" if entry.flagged else "")
            for column, text in enumerate((label, str(entry.decisions), _percent(entry.share_bp))):
                item = QTableWidgetItem(text)
                if column:
                    item.setTextAlignment(RIGHT)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        notes = list(composition.notes)
        if composition.unclassified:
            notes.insert(
                0,
                _("{n} decisions are counted apart: their cards were never known.").format(
                    n=composition.unclassified,
                ),
            )
        self.notes.setText("\n".join(notes))


class MoneyWidget(QWidget):
    """Realized and EV-adjusted money, side by side, with the difference named."""

    COLUMNS = (
        ("group", "Seat"),
        ("opportunities", "Decisions"),
        ("hands", "Hands"),
        ("realized", "Realized"),
        ("ev_adjusted", "EV-adjusted"),
        ("luck", "Luck"),
        ("bb_per_100", "bb/100"),
        ("ev_bb_per_100", "EV bb/100"),
    )

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.headline = QLabel("")
        self.headline.setWordWrap(True)
        layout.addWidget(self.headline)
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels([_(heading) for _key, heading in self.COLUMNS])
        self.table.verticalHeader().hide()
        layout.addWidget(self.table, 1)
        self.notes = QLabel("")
        self.notes.setWordWrap(True)
        layout.addWidget(self.notes)

    def set_report(self, report: Any) -> None:
        from fpdb_3_legacy import research_labels as rlabels

        total = report.total
        self.headline.setText(
            _("Realized {realized} over {hands} hands; EV-adjusted {ev} ({luck} of it luck).").format(
                realized=_money(total.realized_cents),
                hands=total.hands,
                ev=_money(total.ev_adjusted_cents),
                luck=_money(total.all_in_luck_cents),
            ),
        )
        self.table.setRowCount(len(report.rows))
        for row, entry in enumerate(report.rows):
            values = {
                "group": ", ".join(
                    f"{rlabels.dimension_label(name)}={value}" for name, value in sorted(entry.group.items())
                ),
                "opportunities": str(entry.opportunities),
                "hands": str(entry.hands),
                "realized": _money(entry.realized_cents),
                "ev_adjusted": _money(entry.ev_adjusted_cents),
                "luck": _money(entry.all_in_luck_cents),
                "bb_per_100": "n/a" if entry.bb_per_100 is None else f"{entry.bb_per_100:.2f}",
                "ev_bb_per_100": "n/a" if entry.ev_bb_per_100 is None else f"{entry.ev_bb_per_100:.2f}",
            }
            for column, (key, _heading) in enumerate(self.COLUMNS):
                item = QTableWidgetItem(values[key])
                if column:
                    item.setTextAlignment(RIGHT)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.notes.setText("\n".join(report.notes))
