"""The replayer's side inspector: the decision analysis and the action history (#872).

The decision panel used to be painted over the table, next to a painted
action timeline. Both now live in one panel beside the table, which stays
whole:

- at the top, the decision at the step shown: its key figures as tiles (the
  call, the required equity, the pot odds), each tile coloured by the row's
  semantic key, the other rows below, and the advanced calculations folded
  away until asked for;
- below, the hand's actions so far grouped by street, each line on its
  action's chip colours (``replay_history.action_style``) with its glyph, the
  step shown framed in a bright border that is the same for every action; a
  click seeks the replayer to that step.

The content comes from ``replayer_panel`` (a :class:`DecisionPanel`) and from
the history entries (``replay_history``). Nothing here computes poker figures.
The slider stays the single source of truth: seeking from the timeline only
moves it, and every slider change rebuilds the panel and re-selects the row of
the step shown. The panel is part of a post-session review screen
(``docs/fair-play.md``): neutral colours, no "do this" signal.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygon
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.replay_history import action_icon, action_style, history_row_for_index
from fpdb_3_legacy.replayer_panel import DecisionPanel, PanelRow, PanelSection

__all__ = ["INSPECTOR_COLLAPSED_WIDTH", "INSPECTOR_MIN_WIDTH", "ReplayInspector", "TimelineDelegate", "TimelineRow"]

INSPECTOR_MIN_WIDTH = 300
INSPECTOR_COLLAPSED_WIDTH = 40
_TILES_PER_ROW = 3

# Qt's largest widget size: what lifts a maximum width set while collapsed.
_QWIDGETSIZE_MAX = (1 << 24) - 1

# The frame of the selected timeline row: bright, and the same whatever the action,
# so the selection never reads as the action's own colour.
_SELECTED_FRAME = "#41E6FF"

# A key figure's tile colour, by the row's semantic key (replayer_panel): the bet's
# size in cyan, the call in teal, the equity the call needs in yellow, the pot odds
# in mint. Other keys keep the panel's neutral tile.
TILE_STYLES = {
    "bet_size": ("#32D5EA", "#0F2E3D"),
    "call_amount": ("#35D0BA", "#0E3A34"),
    "required_equity": ("#F7D54A", "#43391B"),
    "required_chip_equity": ("#F7D54A", "#43391B"),
    "pot_odds": ("#53DF9B", "#173B31"),
}

# A row's functional band, drawn as a chip (text on its own colour): a shallow SPR in
# amber, a deep one in cyan. Descriptive, never a verdict.
TONE_STYLES = {
    "low": ("#FFAC57", "#45301E"),
    "high": ("#32D5EA", "#103946"),
}

# Item data roles of a timeline line.
_INDEX_ROLE = Qt.ItemDataRole.UserRole
_KIND_ROLE = Qt.ItemDataRole.UserRole + 1
_ACTION_ROLE = Qt.ItemDataRole.UserRole + 2
_NUMBER_ROLE = Qt.ItemDataRole.UserRole + 3


@dataclass(frozen=True)
class TimelineRow:
    """One line of the history: a street heading, an action or a result, and the step it seeks."""

    index: int
    kind: str  # "street", "action" or "result"
    text: str
    action: str = ""  # the action's verb, driving the line's colours and glyph


class TimelineDelegate(QStyledItemDelegate):
    """Paints a history line: its action's chip colours and glyph, and a bright frame when selected.

    The selection is drawn independently of the action's type: a raise keeps its
    orange, with the bright frame and a marker on top of it.
    """

    def __init__(self, inspector: ReplayInspector, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._inspector = inspector

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: N802 - Qt API
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = option.rect.adjusted(2, 1, -2, -1)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if index.data(_KIND_ROLE) == "street":
            self._paint_street(painter, rect, str(index.data(Qt.ItemDataRole.DisplayRole) or ""))
            if selected:
                self._draw_selected_frame(painter, rect)
        else:
            self._paint_action(painter, rect, index, selected)
        painter.restore()

    @staticmethod
    def _draw_selected_frame(painter: QPainter, rect) -> None:
        """The bright frame of the step shown: the same whatever the row, action or street heading."""
        painter.setPen(QPen(QColor(_SELECTED_FRAME), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 5, 5)

    def _paint_street(self, painter: QPainter, rect, text: str) -> None:
        font = QFont(painter.font())
        font.setBold(True)
        font.setPointSizeF(max(7.5, font.pointSizeF() - 1.0))
        painter.setFont(font)
        painter.setPen(QColor(self._inspector.theme.get("muted", "#9AA5AD")))
        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

    def _paint_action(self, painter: QPainter, rect, index, selected: bool) -> None:
        action = index.data(_ACTION_ROLE)
        style = action_style(action)
        background = QColor(style.background)
        if selected:
            background = background.lighter(125)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(background))
        painter.drawRoundedRect(rect, 5, 5)
        foreground = QColor(style.foreground)
        metrics = painter.fontMetrics()
        base_y = rect.center().y() + metrics.ascent() // 2 + 1
        x = rect.left() + 8
        if selected:
            # The selection marker: a small triangle on the row's left edge.
            center_y = rect.center().y()
            marker = QPolygon([QPoint(x, center_y - 4), QPoint(x, center_y + 4), QPoint(x + 5, center_y)])
            painter.setBrush(QBrush(QColor(_SELECTED_FRAME)))
            painter.drawPolygon(marker)
            x += 10
        x = self._draw_glyph(painter, x, base_y, foreground, action_icon(action))
        number = index.data(_NUMBER_ROLE)
        if number:
            painter.setPen(QColor(self._inspector.theme.get("muted", "#9AA5AD")))
            x = self._draw_glyph(painter, x, base_y, None, f"{number:02d}", gap=8)
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        painter.setPen(foreground)
        painter.drawText(x, base_y, metrics.elidedText(text, Qt.TextElideMode.ElideRight, rect.right() - x - 4))
        if selected:
            self._draw_selected_frame(painter, rect)

    def _draw_glyph(
        self, painter: QPainter, x: int, base_y: int, color: QColor | None, glyph: str, gap: int = 6
    ) -> int:
        """Draw *glyph* at *x* and return the x after it; a muted number keeps the theme's muted colour."""
        if not glyph:
            return x
        painter.setPen(color or QColor(self._inspector.theme.get("muted", "#9AA5AD")))
        painter.drawText(x, base_y, glyph)
        return x + painter.fontMetrics().horizontalAdvance(glyph) + gap

    def sizeHint(self, option, index) -> QSize:  # noqa: N802  # pylint: disable=invalid-name  # Qt API
        hint = super().sizeHint(option, index)
        return QSize(hint.width(), max(hint.height(), 26))


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            _clear(item.layout())


class ReplayInspector(QFrame):  # pylint: disable=too-many-instance-attributes  # the panel's widgets
    """The panel beside the table: the decision at the step shown, then the actions so far."""

    seek_requested = Signal(int)
    detailed_toggled = Signal(bool)
    collapsed_changed = Signal(bool)
    action_requested = Signal(str)  # a panel row's step, such as "payouts"

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
        # The replayer's palette, for the stylesheet and the timeline delegate.
        self.theme: dict[str, str] = {"muted": "#9AA5AD", "text": "#EDF2F5"}

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
        self.timeline.setWordWrap(False)
        self.timeline.setItemDelegate(TimelineDelegate(self, self.timeline))
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
        # Collapsed, the strip stays on the right edge, beside the window's edge: the arrow
        # points left to open it back; open, the arrow points right to fold it away.
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
        # The key figure the section is about keeps its accent frame on top of its key colour.
        for row in section.rows:
            if row.key and not row.detail:
                continue
            widget = self._action(row) if row.action else self._row(row)
            if row.detail:
                self._detail_widgets.append(widget)
            layout.addWidget(widget)
        self.decision_layout.addWidget(card)

    def _tile(self, row: PanelRow) -> QFrame:
        """A key figure as a tile, coloured by its semantic key, not by its translated label."""
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
        style = TILE_STYLES.get(row.key)
        if style is not None:
            foreground, background = style
            width = 2 if row.accent else 1
            # The objectName selector, not QFrame: QLabel is a QFrame, and a QFrame rule
            # here would draw the same box around the tile's own labels.
            tile.setStyleSheet(
                f"#{tile.objectName()} {{ background: {background}; "
                f"border: {width}px solid {foreground}; border-radius: 7px; }}"
            )
            value.setStyleSheet(f"color: {foreground}; font-weight: 700; font-size: 17px;")
        return tile

    def _action(self, row: PanelRow) -> QPushButton:
        """A step the panel offers, such as entering the payouts ICM waits on."""
        button = QPushButton(row.label)
        button.setObjectName("inspectorAction")
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if row.tooltip:
            button.setToolTip(row.tooltip)
        button.clicked.connect(lambda: self.action_requested.emit(row.action))
        return button

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
        tone = TONE_STYLES.get(row.tone)
        if tone is not None:
            # A functional band turns the whole row into a chip (a shallow SPR amber, a deep
            # one cyan); the objectName selector keeps the chip off the row's own labels.
            foreground, background = tone
            widget.setStyleSheet(f"#inspectorRow {{ background: {background}; border-radius: 5px; padding: 2px 6px; }}")
            value.setStyleSheet(f"color: {foreground}; font-weight: 700; font-size: 12px;")
        layout.addWidget(label, 1)
        layout.addWidget(value, 0)
        return widget

    # --- the history ------------------------------------------------------

    def set_timeline(self, rows: Sequence[TimelineRow], current_index: int | None = None) -> None:
        """The actions so far, by street; the row of the step shown is selected and kept in view.

        *current_index* is the replayer's slider value: the single source of truth, so
        stepping the hand, playing it or clicking a line all land on the same row.
        """
        self._timeline_rows = list(rows)
        self.timeline.clear()
        number = 0
        for row in rows:
            if row.kind == "street":
                item = QListWidgetItem(row.text.upper())
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                item.setData(_KIND_ROLE, "street")
            else:
                number += 1
                item = QListWidgetItem(row.text)
                item.setData(_KIND_ROLE, row.kind)
                item.setData(_ACTION_ROLE, row.action)
                item.setData(_NUMBER_ROLE, number)
            item.setData(_INDEX_ROLE, row.index)
            self.timeline.addItem(item)
        if current_index is None:
            current_index = rows[-1].index if rows else -1
        selected = history_row_for_index(self._timeline_rows, current_index)
        if selected is not None and selected >= 0:
            self.timeline.setCurrentRow(selected)
        self._keep_current_in_view()

    def _keep_current_in_view(self) -> None:
        item = self.timeline.currentItem()
        if item is not None:
            self.timeline.scrollToItem(item, QListWidget.ScrollHint.EnsureVisible)

    def resizeEvent(self, event) -> None:  # noqa: N802  # pylint: disable=invalid-name  # Qt API
        super().resizeEvent(event)
        self._keep_current_in_view()

    def showEvent(self, event) -> None:  # noqa: N802  # pylint: disable=invalid-name  # Qt API
        super().showEvent(event)
        self._keep_current_in_view()

    @property
    def timeline_rows(self) -> list[TimelineRow]:
        return list(self._timeline_rows)

    def _timeline_clicked(self, item: QListWidgetItem) -> None:
        index = item.data(_INDEX_ROLE)
        if isinstance(index, int):
            self.seek_requested.emit(index)

    # --- theme --------------------------------------------------------------

    def apply_theme(self, colors: dict[str, str]) -> None:
        """Style the panel from the replayer's palette: panel, border, text, muted, accent, accent_soft."""
        panel, border = colors["panel"], colors["border"]
        text, muted = colors["text"], colors["muted"]
        accent, accent_soft = colors["accent"], colors["accent_soft"]
        tile = colors.get("tile", panel)
        self._dark = colors.get("dark", "1") == "1"
        self.theme = colors
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
            #inspectorAdvanced {{ color: {accent}; background: {tile}; border: 1px solid {border}; border-radius: 6px; padding: 6px 10px; font-weight: 700; font-size: 11px; }}
            #inspectorAdvanced:hover {{ border-color: {accent}; }}
            #inspectorAdvanced:checked {{ background: {accent_soft}; border-color: {accent}; }}
            #inspectorToggle {{ color: {accent}; border: 1px solid {border}; border-radius: 4px; padding: 2px 7px; }}
            /* The timeline lines are painted by TimelineDelegate: their colours come from
               replay_history.action_style, the selection frame is drawn there too. */
            #inspectorTimeline {{ border: none; font-size: 12px; background: transparent; }}
            QSplitter::handle {{ background: {border}; }}
            """
        )
