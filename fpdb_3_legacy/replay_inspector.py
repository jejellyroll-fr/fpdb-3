"""The replayer's side inspector: the decision analysis and the action history (#872).

The decision panel used to be painted over the table, next to a painted
action timeline. Both now live in one panel beside the table, which stays
whole:

- at the top, the decision at the step shown: its key figures as tiles (the
  call, the required equity, the pot odds), the other rows below, and the
  advanced calculations folded away until asked for;
- below, the hand's actions so far grouped by street, the step shown
  highlighted; a click seeks the replayer to that step.

The content comes from ``replayer_panel`` (a :class:`DecisionPanel`) and from
the replayer's timeline rows. Nothing here computes poker figures. The panel
is part of a post-session review screen (``docs/fair-play.md``): neutral
colours, no "do this" signal.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.replayer_panel import DecisionPanel, PanelRow, PanelSection

__all__ = ["INSPECTOR_COLLAPSED_WIDTH", "INSPECTOR_MIN_WIDTH", "ReplayInspector", "TimelineRow"]

INSPECTOR_MIN_WIDTH = 300
INSPECTOR_COLLAPSED_WIDTH = 40
_TILES_PER_ROW = 3

# Qt's largest widget size: what lifts a maximum width set while collapsed.
_QWIDGETSIZE_MAX = (1 << 24) - 1


@dataclass(frozen=True)
class TimelineRow:
    """One line of the history: a street heading, an action or a result, and the step it seeks."""

    index: int
    kind: str  # "street", "action" or "result"
    text: str
    color: str = ""  # the action's colour, as on the table


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            _clear(item.layout())


class ReplayInspector(QFrame):
    """The panel beside the table: the decision at the step shown, then the actions so far."""

    seek_requested = Signal(int)
    detailed_toggled = Signal(bool)
    collapsed_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("replayInspector")
        self.setMinimumWidth(INSPECTOR_MIN_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._collapsed = False
        self._detailed = False
        self._detail_widgets: list[QWidget] = []
        self._timeline_rows: list[TimelineRow] = []
        self.advanced_button: QToolButton | None = None
        self._dark = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())
        # Body: the decision over the history, the split between them adjustable.
        self.body = QSplitter(Qt.Orientation.Vertical)
        self.body.setObjectName("inspectorBody")
        self.body.setChildrenCollapsible(False)
        self.body.setHandleWidth(6)
        self.body.addWidget(self._build_decision())
        self.body.addWidget(self._build_history())
        self.body.setStretchFactor(0, 3)
        self.body.setStretchFactor(1, 2)
        # The decision first: about three fifths of the height, the history the rest.
        self.body.setSizes([600, 400])
        outer.addWidget(self.body, 1)
        self._sync_collapse_button()

    def _build_header(self) -> QWidget:
        """The panel's name, the step shown, and the fold button."""
        header = QWidget()
        header.setObjectName("inspectorHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 10, 10, 10)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        self.title_label = QLabel(_("Action inspector"))
        self.title_label.setObjectName("inspectorTitle")
        self.step_label = QLabel("")
        self.step_label.setObjectName("inspectorMuted")
        titles.addWidget(self.title_label)
        titles.addWidget(self.step_label)
        header_layout.addLayout(titles, 1)
        self.collapse_button = QToolButton()
        self.collapse_button.setObjectName("inspectorToggle")
        self.collapse_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.collapse_button.setToolTip(_("Hide or show the inspector"))
        self.collapse_button.clicked.connect(lambda: self.set_collapsed(not self._collapsed))
        header_layout.addWidget(self.collapse_button, 0, Qt.AlignmentFlag.AlignTop)
        return header

    def _build_decision(self) -> QScrollArea:
        """The decision at the step, scrolling when it is taller than its part of the panel."""
        self.decision_scroll = QScrollArea()
        self.decision_scroll.setObjectName("inspectorDecisionScroll")
        self.decision_scroll.setWidgetResizable(True)
        self.decision_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.decision_scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.decision_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.decision = QWidget()
        self.decision.setObjectName("inspectorDecision")
        self.decision_layout = QVBoxLayout(self.decision)
        self.decision_layout.setContentsMargins(14, 12, 14, 12)
        self.decision_layout.setSpacing(6)
        self.decision_scroll.setWidget(self.decision)
        return self.decision_scroll

    def _build_history(self) -> QWidget:
        """The actions so far, by street; a click seeks the replayer."""
        history = QWidget()
        history.setObjectName("inspectorHistory")
        history_layout = QVBoxLayout(history)
        history_layout.setContentsMargins(10, 8, 10, 8)
        history_layout.setSpacing(4)
        history_head = QHBoxLayout()
        self.history_title = QLabel(_("Action history"))
        self.history_title.setObjectName("inspectorSection")
        self.history_hint = QLabel(_("Click an action to go back to it"))
        self.history_hint.setObjectName("inspectorMuted")
        history_head.addWidget(self.history_title)
        history_head.addStretch()
        history_head.addWidget(self.history_hint)
        history_layout.addLayout(history_head)
        self.timeline = QListWidget()
        self.timeline.setObjectName("inspectorTimeline")
        # The replayer's arrow keys must keep stepping the hand, not this list.
        self.timeline.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.timeline.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.timeline.setWordWrap(True)
        self.timeline.itemClicked.connect(self._timeline_clicked)
        history_layout.addWidget(self.timeline, 1)
        return history

    # --- collapsing -------------------------------------------------------

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        """Fold the inspector to a thin strip with its button, or open it again."""
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self.body.setVisible(not collapsed)
        self.title_label.setVisible(not collapsed)
        self.step_label.setVisible(not collapsed)
        if collapsed:
            self.setMinimumWidth(INSPECTOR_COLLAPSED_WIDTH)
            self.setMaximumWidth(INSPECTOR_COLLAPSED_WIDTH)
        else:
            self.setMaximumWidth(_QWIDGETSIZE_MAX)
            self.setMinimumWidth(INSPECTOR_MIN_WIDTH)
        self._sync_collapse_button()
        self.collapsed_changed.emit(collapsed)

    def _sync_collapse_button(self) -> None:
        self.collapse_button.setText("⟨" if self._collapsed else "⟩")

    # --- the decision -----------------------------------------------------

    @property
    def detailed(self) -> bool:
        return self._detailed

    def set_detailed(self, detailed: bool) -> None:
        """Show or fold the advanced calculations, without rebuilding the panel."""
        self._detailed = detailed
        for widget in self._detail_widgets:
            widget.setVisible(detailed)
        toggle = self.advanced_button
        if toggle is not None:
            toggle.blockSignals(True)
            toggle.setChecked(detailed)
            toggle.blockSignals(False)
            self._label_advanced(toggle)

    def set_panel(self, panel: DecisionPanel, step: str, *, detailed: bool) -> None:
        """Show the decision at the step: its headline, each section's tiles and rows."""
        self.step_label.setText(step)
        self._detailed = detailed
        self._detail_widgets = []
        self.advanced_button = None
        _clear(self.decision_layout)

        headline = QLabel(panel.headline)
        headline.setObjectName("inspectorHeadline")
        headline.setWordWrap(True)
        self.decision_layout.addWidget(headline)
        if panel.hint:
            hint = QLabel(panel.hint)
            hint.setObjectName("inspectorMuted")
            hint.setWordWrap(True)
            self.decision_layout.addWidget(hint)
        for section in panel.sections:
            self._add_section(section)
        if self._detail_widgets:
            self.advanced_button = self._advanced_toggle()
            self.decision_layout.addWidget(self.advanced_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.decision_layout.addStretch(1)
        self.set_detailed(detailed)

    def _advanced_toggle(self) -> QToolButton:
        toggle = QToolButton()
        toggle.setObjectName("inspectorAdvanced")
        toggle.setCheckable(True)
        toggle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle.toggled.connect(self._advanced_toggled)
        return toggle

    def _label_advanced(self, toggle: QToolButton) -> None:
        toggle.setText(
            "▴ " + _("Hide the advanced calculations")
            if toggle.isChecked()
            else "▾ " + _("Show the advanced calculations")
        )

    def _advanced_toggled(self, checked: bool) -> None:
        self.set_detailed(checked)
        self.detailed_toggled.emit(checked)

    def _add_section(self, section: PanelSection) -> None:
        card = QFrame()
        card.setObjectName("inspectorCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        title = QLabel(section.title)
        title.setObjectName("inspectorSection")
        title.setWordWrap(True)
        if section.tooltip:
            title.setToolTip(section.tooltip)
        layout.addWidget(title)

        tiles = [row for row in section.rows if row.key and not row.detail]
        if tiles:
            grid = QGridLayout()
            grid.setHorizontalSpacing(6)
            grid.setVerticalSpacing(6)
            for position, row in enumerate(tiles):
                grid.addWidget(self._tile(row), position // _TILES_PER_ROW, position % _TILES_PER_ROW)
            layout.addLayout(grid)
        for row in section.rows:
            if row.key and not row.detail:
                continue
            widget = self._row(row)
            if row.detail:
                self._detail_widgets.append(widget)
            layout.addWidget(widget)
        self.decision_layout.addWidget(card)

    @staticmethod
    def _tile(row: PanelRow) -> QFrame:
        tile = QFrame()
        tile.setObjectName("inspectorTileAccent" if row.accent else "inspectorTile")
        tile.setToolTip(row.tooltip)
        layout = QVBoxLayout(tile)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(1)
        label = QLabel(row.label)
        label.setObjectName("inspectorTileLabel")
        label.setWordWrap(True)
        value = QLabel(row.value)
        value.setObjectName("inspectorTileValueAccent" if row.accent else "inspectorTileValue")
        layout.addWidget(label)
        layout.addWidget(value)
        return tile

    @staticmethod
    def _row(row: PanelRow) -> QWidget:
        if row.is_note:
            note = QLabel(row.label)
            note.setObjectName("inspectorNote")
            note.setWordWrap(True)
            return note
        widget = QWidget()
        widget.setObjectName("inspectorRow")
        widget.setToolTip(row.tooltip)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 1, 0, 1)
        label = QLabel(row.label)
        label.setObjectName("inspectorMuted" if row.muted else "inspectorLabel")
        label.setWordWrap(True)
        value = QLabel(row.value)
        value.setObjectName("inspectorMuted" if row.muted else "inspectorValue")
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(label, 1)
        layout.addWidget(value, 0)
        return widget

    # --- the history ------------------------------------------------------

    def set_timeline(self, rows: Sequence[TimelineRow]) -> None:
        """The actions so far, by street; the last one is the step shown, and is kept in view."""
        self._timeline_rows = list(rows)
        self.timeline.clear()
        number = 0
        for row in rows:
            if row.kind == "street":
                item = QListWidgetItem(row.text.upper())
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                font = item.font()
                font.setBold(True)
                font.setPointSizeF(max(7.0, font.pointSizeF() - 1.5))
                item.setFont(font)
                item.setData(Qt.ItemDataRole.UserRole + 1, "street")
            else:
                number += 1
                item = QListWidgetItem(f"{number:02d}   {row.text}")
                item.setData(Qt.ItemDataRole.UserRole + 1, row.kind)
                if row.color:
                    # The table's action colours are made for a dark felt: darkened on a light panel.
                    color = QColor(row.color)
                    item.setForeground(QBrush(color if self._dark else color.darker(190)))
            item.setData(Qt.ItemDataRole.UserRole, row.index)
            self.timeline.addItem(item)
        if self.timeline.count():
            self.timeline.setCurrentRow(self.timeline.count() - 1)
        self._keep_current_in_view()

    def _keep_current_in_view(self) -> None:
        item = self.timeline.currentItem()
        if item is not None:
            self.timeline.scrollToItem(item, QListWidget.ScrollHint.PositionAtBottom)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._keep_current_in_view()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self._keep_current_in_view()

    @property
    def timeline_rows(self) -> list[TimelineRow]:
        return list(self._timeline_rows)

    def _timeline_clicked(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(index, int):
            self.seek_requested.emit(index)

    # --- theme --------------------------------------------------------------

    def apply_theme(self, colors: dict[str, str]) -> None:
        """Style the panel from the replayer's palette: panel, border, text, muted, accent, accent_soft."""
        panel, border = colors["panel"], colors["border"]
        text, muted = colors["text"], colors["muted"]
        accent, accent_soft = colors["accent"], colors["accent_soft"]
        tile, row_bg = colors.get("tile", panel), colors.get("row", panel)
        self._dark = colors.get("dark", "1") == "1"
        self.setStyleSheet(
            f"""
            #replayInspector {{ background: {panel}; border: 1px solid {border}; border-radius: 10px; }}
            #replayInspector QWidget {{ background: transparent; color: {text}; }}
            #inspectorHeader {{ border-bottom: 1px solid {border}; }}
            #inspectorTitle {{ font-weight: 700; font-size: 13px; }}
            #inspectorMuted {{ color: {muted}; font-size: 11px; }}
            #inspectorHeadline {{ font-weight: 700; font-size: 14px; }}
            #inspectorSection {{ color: {accent}; font-weight: 700; font-size: 11px; }}
            #inspectorCard {{ border: 1px solid {border}; border-radius: 8px; }}
            #inspectorTile, #inspectorTileAccent {{ background: {tile}; border: 1px solid {border}; border-radius: 7px; }}
            #inspectorTileAccent {{ border-color: {accent}; background: {accent_soft}; }}
            #inspectorTileLabel {{ color: {muted}; font-size: 10px; }}
            #inspectorTileValue {{ font-weight: 700; font-size: 17px; }}
            #inspectorTileValueAccent {{ color: {accent}; font-weight: 700; font-size: 17px; }}
            #inspectorLabel {{ color: {muted}; font-size: 12px; }}
            #inspectorValue {{ font-weight: 600; font-size: 12px; }}
            #inspectorNote {{ color: {muted}; font-size: 11px; font-style: italic; }}
            #inspectorAdvanced {{ color: {accent}; font-weight: 700; font-size: 11px; border: none; padding: 4px 0; }}
            #inspectorToggle {{ color: {accent}; border: 1px solid {border}; border-radius: 4px; padding: 2px 7px; }}
            #inspectorTimeline {{ border: none; font-size: 12px; }}
            #inspectorTimeline::item {{ background: {row_bg}; border-radius: 5px; padding: 5px 7px; margin: 2px 0; }}
            #inspectorTimeline::item:selected {{ background: {accent_soft}; border: 1px solid {accent}; }}
            QSplitter::handle {{ background: {border}; }}
            """
        )
