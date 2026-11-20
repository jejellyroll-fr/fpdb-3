#!/usr/bin/env python
"""Tourney Stats tab: a tournament results overview in the spirit of PokerTracker.

Top to bottom, for the tournaments the filters select:

* summary cards (tournaments, buy-ins, net won, ROI, ITM, average finish...);
* the running net won, ROI% and ITM% after each tournament;
* a results table grouped by description, buy-in, date or tournament.

Double-clicking a group narrows the whole page to it (cards and curves
included) and lists its tournaments in place; a breadcrumb leads back.
Double-clicking a tournament opens its hands in a Tourney Viewer tab.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from time import time
from typing import Any

from PySide6.QtCore import QEvent, QModelIndex, QSortFilterProxyModel, Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QShortcut, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import Filters, GuiTourHandViewer, gui_empty_state
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.localized_formats import format_currency, format_date, format_number, format_utc_datetime
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.table_export import install_table_export
from fpdb_3_legacy.tourney_results import (
    BY_BUYIN,
    BY_DATE,
    BY_DESCRIPTION,
    BY_TOURNAMENT,
    TOURNEY_RESULTS_QUERY,
    Group,
    Summary,
    TourneyResult,
    group_key,
    group_results,
    main_currency,
    result_from_row,
    running_curves,
    summarize,
)

log = get_logger("gui_tourney_player_stats")

# Tournament tabs still have data when only summaries were imported.
_TOURNEY_TABLES = ("Hands", "Tourneys")

colalias, colshow, colheading, colxalign, colformat, coltype = 0, 1, 2, 3, 4, 5
_MONEY_COLUMNS = {"buyIn", "fee", "spent", "won", "bounties", "net", "profitPerTourney"}
_PERCENT_COLUMNS = {"itm", "roi"}
_COUNT_COLUMNS = {"tourneyCount", "_1st", "_2nd", "_3rd", "unknownRank"}

# Item data roles of the results model.
_SORT_ROLE = Qt.ItemDataRole.UserRole
_KEY_ROLE = Qt.ItemDataRole.UserRole + 1
_TONE_ROLE = Qt.ItemDataRole.UserRole + 2

_ALIGN_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
_ALIGN_LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

# Group cells that have no value when no result of the group is known.
_MONEY_KEYS = {"avg_cost", "cashes", "roi", "net", "won", "bounties", "per_tourney"}

# Player stats of the "by description" view shown until the header menu says otherwise.
_DEFAULT_STATS = {"vpip", "pfr", "three_bet"}

# Width of one summary card; the cards wrap to as many columns as fit.
_CARD_MIN_WIDTH = 130


def _palette() -> dict[str, str]:
    """The active theme's colours; plain defaults when no theme is loaded."""
    try:
        from fpdb_3_legacy.ThemeManager import ThemeManager

        return ThemeManager().get_legacy_palette()
    except Exception:  # noqa: BLE001 - a theme problem must not hide the results
        return {
            "surface_panel": "#1f262d",
            "window_text": "#edf2f7",
            "muted_text": "#a0aec0",
            "grid": "#3a444e",
            "border": "#46515c",
            "graph_up": "#22c55e",
            "graph_down": "#ef4444",
            "graph_showdown": "#14a8ff",
            "graph_purple": "#a78bfa",
            "graph_ev": "#f59e3d",
        }


def _tone(value: float | None) -> str:
    if value is None or abs(value) < 0.005:
        return ""
    return "up" if value > 0 else "down"


def _repolish(widget: QWidget) -> None:
    """Re-apply the stylesheet after a dynamic property used by a selector changed."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


def _money_lines(totals: dict[str, Summary], attribute: str, *, show_plus: bool = False) -> str:
    """One amount per currency: amounts in different currencies are never added."""
    return "\n".join(
        format_currency(getattr(summary, attribute), currency, show_plus=show_plus)
        for currency, summary in totals.items()
    )


def _percent(value: float | None) -> str:
    return "–" if value is None else f"{format_number(value)}%"


def _number(value: float | None, decimals: int = 0) -> str:
    return "–" if value is None else format_number(value, decimals)


@dataclass
class _Scope:
    """One drill-down step: the group double-clicked, in the view it was shown in."""

    mode: str
    key: tuple[Any, ...]
    label: str
    # The row search of that view, put back when the step is left: it was
    # typed against its rows, which the tournaments below need not share.
    search: str = ""


@dataclass(frozen=True)
class _Column:
    """One column of the results table."""

    key: str
    title: str
    tooltip: str = ""
    align: Qt.AlignmentFlag = _ALIGN_RIGHT
    hidden: bool = False
    # False when the values would not describe the rows shown: never displayed then.
    available: bool = True


class _ToneDelegate(QStyledItemDelegate):
    """Draws gains and losses in the theme's up/down colours.

    A model foreground loses to the application stylesheet's item colour, so
    the text of a toned cell is painted here, over the styled background.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.colors: dict[str, QColor] = {}

    def paint(self, painter, option, index) -> None:
        tone = index.data(_TONE_ROLE)
        color = self.colors.get(tone) if tone else None
        if color is None or option.state & QStyle.StateFlag.State_Selected:
            super().paint(painter, option, index)
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)
        rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt, widget)
        painter.save()
        painter.setPen(color)
        painter.setFont(opt.font)
        painter.drawText(rect.adjusted(4, 0, -4, 0), int(opt.displayAlignment), text)
        painter.restore()


class _KpiCard(QFrame):
    """A small labelled figure of the overview."""

    def __init__(self, title: str, tooltip: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("kpiCard")
        self.setToolTip(tooltip)
        self.setMinimumWidth(_CARD_MIN_WIDTH - 10)
        # Preferred, not Fixed: the cards of a row take the height of the tallest one.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        self.title = QLabel(title)
        self.title.setObjectName("kpiTitle")
        self.value = QLabel("–")
        self.value.setObjectName("kpiValue")
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.note = QLabel()
        self.note.setObjectName("mutedLabel")
        self.note.hide()
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.note)

    def set_note(self, text: str) -> None:
        self.note.setText(text)
        self.note.setVisible(bool(text))

    def set_value(self, text: str, tone: str = "", tooltip: str | None = None) -> None:
        self.value.setText(text)
        if self.value.property("tone") != tone:
            self.value.setProperty("tone", tone)
            _repolish(self.value)
        if tooltip is not None:
            self.value.setToolTip(tooltip)


class _KpiStrip(QWidget):
    """Summary cards that wrap to the width available."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(8)
        self._cards: list[_KpiCard] = []
        self._hidden: set[int] = set()
        self._columns = 0

    def add_card(self, card: _KpiCard) -> _KpiCard:
        self._cards.append(card)
        self._columns = 0
        self._reflow()
        return card

    def _visible_cards(self) -> list[_KpiCard]:
        # Tracked here: isHidden() is also true for a card not laid out yet.
        return [card for card in self._cards if id(card) not in self._hidden]

    def set_card_visible(self, card: _KpiCard, visible: bool) -> None:
        if (id(card) not in self._hidden) == visible:
            return
        if visible:
            self._hidden.discard(id(card))
        else:
            self._hidden.add(id(card))
        card.setVisible(visible)
        self._columns = 0
        self._reflow()

    def _reflow(self) -> None:
        cards = self._visible_cards()
        if not cards:
            return
        width = max(self.width(), _CARD_MIN_WIDTH)
        widest = max(1, min(len(cards), width // _CARD_MIN_WIDTH))
        # Balanced rows: seven cards on six columns would leave one alone on a row.
        rows = -(-len(cards) // widest)
        columns = -(-len(cards) // rows)
        if columns == self._columns:
            return
        self._columns = columns
        for card in self._cards:
            self._grid.removeWidget(card)
        for index, card in enumerate(cards):
            self._grid.addWidget(card, index // columns, index % columns)
            card.show()
        for column in range(self._grid.columnCount()):
            self._grid.setColumnStretch(column, 1 if column < columns else 0)

    def resizeEvent(self, event) -> None:  # noqa: N802  # pylint: disable=invalid-name  # Qt override
        super().resizeEvent(event)
        self._reflow()


class _ResultsChart(QFrame):  # pylint: disable=too-many-instance-attributes  # widgets + drawn state
    """Running net won, ROI% and ITM% after each tournament.

    PyQtGraph is imported on first use: this tab is created at startup.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("graphCanvasPanel")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 6, 8, 6)
        self._layout.setSpacing(4)

        controls = QHBoxLayout()
        controls.setSpacing(14)
        self.net_box = QCheckBox(_("Net won"))
        self.roi_box = QCheckBox(_("ROI %"))
        self.itm_box = QCheckBox(_("ITM %"))
        self._swatches: dict[str, QLabel] = {}
        for name, box in (("net", self.net_box), ("roi", self.roi_box), ("itm", self.itm_box)):
            box.setChecked(True)
            box.setToolTip(_("Show or hide this curve"))
            box.toggled.connect(self._redraw)
            pair = QHBoxLayout()
            pair.setSpacing(4)
            swatch = QLabel("━━")
            swatch.setObjectName("curveSwatch")
            self._swatches[name] = swatch
            pair.addWidget(box)
            pair.addWidget(swatch)
            controls.addLayout(pair)
        controls.addStretch(1)
        self.readout = QLabel()
        self.readout.setObjectName("mutedLabel")
        controls.addWidget(self.readout)
        self._layout.addLayout(controls)

        self._plot: Any = None
        self._right_view: Any = None
        self._cursor_line: Any = None
        self._results: list[TourneyResult] = []
        self._currency = "USD"
        self._note = ""
        self._curves: Any = None
        self._colors: dict[str, str] = {}
        self._unavailable: QLabel | None = None

    def _ensure_plot(self) -> bool:
        if self._plot is not None:
            return True
        if self._unavailable is not None:
            return False
        try:
            import pyqtgraph as pg
        except ImportError:  # pragma: no cover - pyqtgraph is a dependency
            self._unavailable = QLabel(_("Graphs need the pyqtgraph package."))
            self._layout.addWidget(self._unavailable)
            return False

        plot = pg.PlotWidget()
        plot.setMinimumHeight(120)
        plot.setMenuEnabled(False)
        item = plot.getPlotItem()
        item.showAxis("right")
        item.hideButtons()
        right = pg.ViewBox()
        right.setMenuEnabled(False)
        item.scene().addItem(right)
        item.getAxis("right").linkToView(right)
        right.setXLink(item)

        def sync_views() -> None:
            right.setGeometry(item.vb.sceneBoundingRect())
            right.linkedViewChanged(item.vb, right.XAxis)

        item.vb.sigResized.connect(sync_views)
        plot.scene().sigMouseMoved.connect(self._on_mouse_moved)
        self._plot = plot
        self._right_view = right
        self._layout.addWidget(plot, 1)
        return True

    def set_results(self, results: list[TourneyResult], currency: str | None, note: str = "") -> None:
        self._currency = currency or "USD"
        self._results = [result for result in results if result.currency == self._currency and result.known]
        self._curves = running_curves(self._results)
        self._note = note
        self._colors = _palette()
        self._redraw()

    def _redraw(self) -> None:
        if not self._ensure_plot():
            return
        import pyqtgraph as pg

        c = self._colors or _palette()
        plot = self._plot
        item = plot.getPlotItem()
        item.clear()
        self._right_view.clear()

        plot.setBackground(c["surface_panel"])
        item.showGrid(x=True, y=True, alpha=0.25)
        for axis_name in ("left", "bottom", "right"):
            axis = item.getAxis(axis_name)
            axis.setPen(pg.mkPen(color=c["border"]))
            axis.setTextPen(pg.mkPen(color=c["window_text"]))
        item.setLabel("bottom", _("Tournaments played"), color=c["muted_text"])
        item.setLabel("left", self._currency, color=c["muted_text"])
        item.setLabel("right", "%", color=c["muted_text"])

        for name, color in (("net", c["graph_showdown"]), ("roi", c["graph_purple"]), ("itm", c["graph_ev"])):
            self._swatches[name].setStyleSheet(f"color: {color}; font-weight: 700;")

        curves = self._curves
        if not curves or not curves.net:
            self.readout.setText(self._note)
            return
        x = list(range(1, len(curves.net) + 1))
        item.addLine(y=0, pen=pg.mkPen(color=c["grid"], width=1, style=Qt.PenStyle.DashLine))

        if self.net_box.isChecked():
            item.plot(
                x,
                curves.net,
                pen=pg.mkPen(color=c["graph_showdown"], width=2.5),
                symbol="o" if len(x) == 1 else None,
            )
        for box, values, color in (
            (self.roi_box, curves.roi, c["graph_purple"]),
            (self.itm_box, curves.itm, c["graph_ev"]),
        ):
            if not box.isChecked():
                continue
            self._right_view.addItem(pg.PlotDataItem(x, values, pen=pg.mkPen(color=color, width=1.8)))
        item.getAxis("right").setVisible(self.roi_box.isChecked() or self.itm_box.isChecked())

        self._cursor_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(color=c["muted_text"], width=1))
        self._cursor_line.setVisible(False)
        item.addItem(self._cursor_line, ignoreBounds=True)
        item.enableAutoRange()
        self._right_view.enableAutoRange()
        self.readout.setText(self._note)

    def _on_mouse_moved(self, position) -> None:
        curves = self._curves
        if self._plot is None or not curves or not curves.net:
            return
        item = self._plot.getPlotItem()
        if not item.sceneBoundingRect().contains(position):
            return
        index = round(item.vb.mapSceneToView(position).x()) - 1
        if not 0 <= index < len(curves.net):
            if self._cursor_line is not None:
                self._cursor_line.setVisible(False)
            self.readout.setText(self._note)
            return
        if self._cursor_line is not None:
            self._cursor_line.setPos(index + 1)
            self._cursor_line.setVisible(True)
        result = self._results[index]
        when = format_utc_datetime(result.start) if result.start else ""
        self.readout.setText(
            _("#%(n)s %(when)s · Net %(net)s · ROI %(roi)s · ITM %(itm)s")
            % {
                "n": format_number(index + 1, 0),
                "when": when,
                "net": format_currency(curves.net[index], self._currency),
                "roi": _percent(curves.roi[index]),
                "itm": _percent(curves.itm[index]),
            }
        )


class GuiTourneyPlayerStats(QSplitter):
    def __init__(self, config, db, sql, mainwin, debug=True) -> None:
        super().__init__(mainwin)
        self.conf = config
        self.db = db
        self.cursor = self.db.cursor
        self.sql = sql
        self.main_window = mainwin
        self.debug = debug

        filters_display = {
            "Heroes": True,
            "Sites": True,
            "Seats": True,
            "Dates": True,
            "TourneyFormat": True,
            "UseType": "tour",
            "Button2": True,
        }

        self.detailFilters: list[Any] = []
        self.results: list[TourneyResult] = []
        self.group_mode = BY_DESCRIPTION
        self._scopes: list[_Scope] = []
        self._descriptor_values: dict[tuple[Any, ...], list[str]] = {}
        self._groups: dict[tuple[Any, ...], Group] = {}
        self._row_keys: list[tuple[Any, ...]] = []
        self._columns: list[_Column] = []
        self._table_mode: str | None = None
        # Columns shown or hidden from the header menu, kept across views and reloads.
        self._column_overrides: dict[str, bool] = {}

        self.filters = Filters.Filters(self.db, display=filters_display)
        self.filters.registerButton2Name(_("Refresh Stats"))
        self.filters.registerButton2Callback(self.refreshStats)

        scroll = QScrollArea()
        scroll.setObjectName("filterSidebar")
        scroll.setWidget(self.filters)
        scroll.setWidgetResizable(True)

        # Declarative descriptor columns (stat_registry.py): the ChipEV-by-position
        # curves plus standard rate stats (VPIP/PFR/3Bet/C-bet/...), shown in the
        # "by description" view. Values come from a separate per-(tourneyType,
        # player) aggregation (_merge_chipev_columns). Context-bearing descriptors
        # (e.g. ChipEV/tourney, which needs cnt_tourneys) are excluded: that query
        # does not supply the context column.
        try:
            from fpdb_3_legacy.stat_adapters import GridAdapter
            from fpdb_3_legacy.stat_registry import get_registry

            self._grid_descriptors = [d for d in get_registry().for_scope("tour") if not d.context]
            self._descriptor_specs = GridAdapter().column_specs(self._grid_descriptors)
        except Exception as exc:  # noqa: BLE001 - the base results never depend on them
            log.warning(f"GuiTourneyPlayerStats: descriptor columns unavailable: {exc}")
            self._grid_descriptors = []
            self._descriptor_specs = []

        self.stats_frame = QFrame()
        self.stats_frame.setObjectName("statsSurface")
        frame_layout = QVBoxLayout(self.stats_frame)
        frame_layout.setContentsMargins(12, 10, 12, 10)
        frame_layout.setSpacing(8)

        self._pages = QStackedWidget()
        table_panel = self._build_table_panel()
        self._pages.addWidget(self._build_placeholder())
        self._pages.addWidget(self._build_results_page(table_panel))
        frame_layout.addWidget(self._pages)

        self.addWidget(scroll)
        self.addWidget(self.stats_frame)
        self.setStretchFactor(0, 0)
        self.setStretchFactor(1, 1)

        back = QShortcut(QKeySequence(Qt.Key.Key_Escape), self.stats_frame)
        back.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        back.activated.connect(self._on_escape)
        back_alt = QShortcut(QKeySequence.StandardKey.Back, self.stats_frame)
        back_alt.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        back_alt.activated.connect(self.go_back)
        find = QShortcut(QKeySequence.StandardKey.Find, self.stats_frame)
        find.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        find.activated.connect(self._focus_search)

    # ------------------------------------------------------------------ #
    # Layout                                                              #
    # ------------------------------------------------------------------ #
    def _build_placeholder(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addStretch(1)
        self.placeholder_title = QLabel(_("Tournament results"))
        self.placeholder_title.setObjectName("viewTitle")
        self.placeholder_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_text = QLabel(
            _("Choose a hero and the tournaments to include on the left, then press Refresh Stats.")
        )
        self.placeholder_text.setObjectName("mutedLabel")
        self.placeholder_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_text.setWordWrap(True)
        layout.addWidget(self.placeholder_title)
        layout.addWidget(self.placeholder_text)
        layout.addStretch(2)
        return page

    def _build_results_page(self, table_panel: QWidget) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.title_label = QLabel(_("Tournament results"))
        self.title_label.setObjectName("viewTitle")
        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("mutedLabel")
        header.addWidget(self.title_label)
        header.addSpacing(12)
        header.addWidget(self.subtitle_label, 1)
        layout.addLayout(header)

        self.breadcrumb_bar = QFrame()
        self.breadcrumb_bar.setObjectName("breadcrumbBar")
        crumb_layout = QHBoxLayout(self.breadcrumb_bar)
        crumb_layout.setContentsMargins(8, 4, 8, 4)
        self.back_button = QToolButton()
        self.back_button.setObjectName("breadcrumbBack")
        self.back_button.setText(_("← Back"))
        self.back_button.setToolTip(_("Back to the previous view (Esc)"))
        self.back_button.clicked.connect(self.go_back)
        self.breadcrumb_label = QLabel()
        self.breadcrumb_label.setObjectName("breadcrumbLabel")
        self.breadcrumb_label.setTextFormat(Qt.TextFormat.RichText)
        self.breadcrumb_label.linkActivated.connect(self._on_breadcrumb_link)
        crumb_layout.addWidget(self.back_button)
        crumb_layout.addWidget(self.breadcrumb_label, 1)
        self.breadcrumb_bar.hide()
        layout.addWidget(self.breadcrumb_bar)

        self.kpis = _KpiStrip()
        self.card_count = self.kpis.add_card(_KpiCard(_("Tournaments")))
        self.card_buyins = self.kpis.add_card(_KpiCard(_("Buy-ins"), _("Buy-ins and fees paid")))
        self.card_net = self.kpis.add_card(_KpiCard(_("Net won"), _("Prizes and bounties, less buy-ins and fees")))
        self.card_roi = self.kpis.add_card(_KpiCard(_("ROI"), _("Net won as a share of the buy-ins and fees")))
        self.card_itm = self.kpis.add_card(_KpiCard(_("ITM"), _("Share of the tournaments that paid a prize")))
        self.card_finish = self.kpis.add_card(_KpiCard(_("Avg finish"), _("Average finishing place, when known")))
        self.card_podium = self.kpis.add_card(_KpiCard(_("1st · 2nd · 3rd"), _("Number of 1st, 2nd and 3rd places")))
        self.card_bounties = self.kpis.add_card(_KpiCard(_("Bounties"), _("Part of the winnings paid as bounties")))
        layout.addWidget(self.kpis)

        self.content_splitter = QSplitter(Qt.Orientation.Vertical)
        self.content_splitter.setChildrenCollapsible(False)
        self.chart = _ResultsChart()
        self.content_splitter.addWidget(self.chart)
        self.content_splitter.addWidget(table_panel)
        self.content_splitter.setStretchFactor(0, 2)
        self.content_splitter.setStretchFactor(1, 3)
        # The table gets the larger share from the start, not only of extra space.
        self.content_splitter.setSizes([260, 440])
        layout.addWidget(self.content_splitter, 1)
        return page

    def _build_table_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(0)
        self.mode_buttons = QButtonGroup(self)
        self.mode_buttons.setExclusive(True)
        for mode, label, tip in (
            (BY_DESCRIPTION, _("By description"), _("One row per tournament type")),
            (BY_BUYIN, _("By buy-in"), _("One row per buy-in level")),
            (BY_DATE, _("By date"), _("One row per day played")),
            (BY_TOURNAMENT, _("By tournament"), _("One row per tournament")),
        ):
            button = QToolButton()
            button.setObjectName("segmentButton")
            button.setText(label)
            button.setToolTip(tip)
            button.setCheckable(True)
            button.setProperty("mode", mode)
            button.setChecked(mode == self.group_mode)
            self.mode_buttons.addButton(button)
            toolbar.addWidget(button)
        self.mode_buttons.buttonClicked.connect(self._on_mode_clicked)
        toolbar.addSpacing(12)
        toolbar.addStretch(1)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(_("Filter rows…"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMaximumWidth(260)
        self.search_edit.setToolTip(_("Show only the rows containing this text"))
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(150)
        self._search_timer.timeout.connect(self._apply_search)
        self.search_edit.textChanged.connect(self._search_timer.start)
        toolbar.addWidget(self.search_edit)
        toolbar.addSpacing(8)

        self.open_hands_button = QPushButton(_("Open hands"))
        self.open_hands_button.setToolTip(_("Open the selected tournament's hands in a Tourney Viewer tab (Enter)"))
        self.open_hands_button.clicked.connect(self._open_selected_hands)
        toolbar.addWidget(self.open_hands_button)
        layout.addLayout(toolbar)

        self.model = QStandardItemModel(self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(_SORT_ROLE)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        self.tone_delegate = _ToneDelegate(self.table)
        self.table.setItemDelegate(self.tone_delegate)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(30)
        header = self.table.horizontalHeader()
        header.setSectionsMovable(True)
        header.setHighlightSections(False)
        header.setStretchLastSection(False)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_header_menu)
        install_table_export(self.table)
        self.table.doubleClicked.connect(self._on_row_activated)
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            enter = QShortcut(QKeySequence(key), self.table)
            enter.setContext(Qt.ShortcutContext.WidgetShortcut)
            enter.activated.connect(lambda: self._on_row_activated(self.table.currentIndex()))
        self.table.selectionModel().selectionChanged.connect(self._update_actions)
        layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        self.totals_label = QLabel()
        self.totals_label.setObjectName("totalsLabel")
        self.totals_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.hint_label = QLabel()
        self.hint_label.setObjectName("mutedLabel")
        footer.addWidget(self.totals_label, 1)
        footer.addWidget(self.hint_label)
        layout.addLayout(footer)
        return panel

    # ------------------------------------------------------------------ #
    # Loading                                                             #
    # ------------------------------------------------------------------ #
    def refreshStats(self) -> None:
        """Reload the tournaments for the current filters and redraw the page."""
        start = time()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            loaded = self._load()
        finally:
            QApplication.restoreOverrideCursor()
        if loaded is None:
            return
        results, descriptor_values = loaded
        if not results:
            self.results = []
            self._show_placeholder(_("No tournament matches these filters."))
            gui_empty_state.show_no_data(self, context="Tournament stats", db=self.db, tables=_TOURNEY_TABLES)
            self.db.rollback()
            return

        self.results = results
        self._descriptor_values = descriptor_values
        # Keep the drill-down when its group is still there after the reload.
        kept: list[_Scope] = []
        scoped = results
        for scope in self._scopes:
            narrowed = [result for result in scoped if group_key(scope.mode, result) == scope.key]
            if not narrowed:
                break
            kept.append(scope)
            scoped = narrowed
        if len(kept) != len(self._scopes):
            self._scopes = kept
            if not kept:
                self.group_mode = BY_DESCRIPTION
        self._render()
        log.info(f"Tourney stats page displayed in {time() - start:4.2f} seconds ({len(results)} results)")

    def _selected_players(self) -> tuple[list[int], list[int]] | None:
        """The player ids the filters select and their sites, or None after explaining why there are none."""
        sites = self.filters.getSites()
        siteids = self.filters.getSiteIds()
        playerids: list[int] = []
        sitenos: list[int] = []
        # Every alias of the hero selected, or every player of a hero profile (#434):
        # see Filters.get_selected_players.
        for site, pid in self.filters.get_selected_players():
            playerids.append(pid)
            actual_site_id = self.db.get_player_site_id(pid)
            sitenos.append(actual_site_id if actual_site_id is not None else siteids[site])

        missing = gui_empty_state.missing_filter_reason(sites=sites, playerids=playerids)
        if missing is not None:
            self._show_placeholder(_("Choose a site and a hero on the left, then press Refresh Stats."))
            gui_empty_state.show_no_data(self, missing, context="Tournament stats", db=self.db, tables=_TOURNEY_TABLES)
            self.db.rollback()
            return None
        return playerids, sitenos

    def _load(self) -> tuple[list[TourneyResult], dict[tuple[Any, ...], list[str]]] | None:
        selected = self._selected_players()
        if selected is None:
            return None
        playerids, sitenos = selected
        seats = self.filters.getSeats()
        query = self.refineQuery(TOURNEY_RESULTS_QUERY, 0, [], playerids, sitenos, seats)
        log.debug(f"Tourney stats SQL:\n{query}")
        self.cursor.execute(query)
        rows = self.cursor.fetchall() or []
        columns = [description[0] for description in (self.cursor.description or [])]
        results = []
        for row in rows:
            try:
                results.append(result_from_row(dict(zip(columns, row, strict=False))))
            except (KeyError, TypeError, ValueError) as exc:
                log.warning(f"Tourney stats: skipped an unreadable row ({exc})")
        descriptor_values: dict[tuple[Any, ...], list[str]] = {}
        if results and self._grid_descriptors:
            keys = sorted({(result.tourney_type_id, result.player_id) for result in results})
            merged, _columns = self._merge_chipev_columns(
                "tourneyPlayerDetailedStats",
                [list(key) for key in keys],
                ["tourneyTypeId", "playerId"],
                0,
                [],
                playerids,
                sitenos,
                seats,
            )
            descriptor_values = {(row[0], row[1]): [str(v) for v in row[2:]] for row in merged if len(row) > 2}
        self.db.rollback()
        return results, descriptor_values

    def refineQuery(self, query, numTourneys, tourneyTypes, playerids, sitenos, seats):
        having = ""

        if playerids:
            nametest = str(tuple(playerids))
            nametest = nametest.replace(",)", ")")
        else:
            nametest = "1 = 2"
        pname = "p.name"

        query = query.replace("<nametest>", nametest)
        query = query.replace("<playerName>", pname)
        query = query.replace("<havingclause>", having)

        if sitenos:
            sitetest = str(tuple(sitenos))
            sitetest = sitetest.replace(",)", ")")
            sitetest = f"and tt.siteId in {sitetest}"
        else:
            sitetest = "and tt.siteId IS NULL"
        # Knockouts or freezeouts (#447), on the TourneyTypes tt every query here joins.
        from fpdb_3_legacy.tourney_format import format_condition

        get_format = getattr(self.filters, "getTourneyFormat", None)
        tourney_format = get_format() if callable(get_format) else "all"
        sitetest = " ".join((sitetest, format_condition(tourney_format, self.db.backend == self.db.SQLITE)))
        query = query.replace("<sitetest>", sitetest)

        if seats:
            query = query.replace(
                "<seats_test>",
                "between " + str(seats["from"]) + " and " + str(seats["to"]),
            )
            query = query.replace("<groupbyseats>", ",h.seats")
            query = query.replace("<orderbyseats>", ",h.seats")
        else:
            query = query.replace("<seats_test>", "between 0 and 100")
            query = query.replace("<groupbyseats>", "")
            query = query.replace("<orderbyseats>", "")

        flagtest = ""
        if self.detailFilters:
            for f in self.detailFilters:
                if len(f) == 3:
                    flagtest += f" and {f[0]} between {f[1]!s} and {f[2]!s} "
        query = query.replace("<flagtest>", flagtest)

        if self.db.backend == self.db.MYSQL_INNODB:
            query = query.replace("<signed>", "signed ")
        else:
            query = query.replace("<signed>", "")

        start_date, end_date = self.filters.getDates()
        query = query.replace("<startdate_test>", start_date)
        return query.replace("<enddate_test>", end_date)

    def _merge_chipev_columns(self, query_name, result, colnames, numTourneys, tourneyTypes, playerids, sitenos, seats):
        """Append declarative ChipEV-by-position values to rows keyed by (tourneyTypeId, playerId).

        Runs a separate per-(tourneyType, player) aggregation and joins it onto
        the rows by (tourneyTypeId, playerId). Returns (result, colnames),
        possibly augmented. Best-effort: any failure returns the inputs intact.
        """
        descriptors = getattr(self, "_grid_descriptors", [])
        if query_name != "tourneyPlayerDetailedStats" or not descriptors:
            return result, colnames
        column_indices = {str(name).casefold(): index for index, name in enumerate(colnames)}
        if "tourneytypeid" not in column_indices or "playerid" not in column_indices:
            return result, colnames

        try:
            from fpdb_3_legacy.stat_adapters import GridAdapter

            adapter = GridAdapter()
            query = self.sql.query["tourneyChipEVByPositionGrid"]
            query = query.replace("<chipev_columns>", adapter.select_clause(descriptors))
            query = self.refineQuery(query, numTourneys, tourneyTypes, playerids, sitenos, seats)

            self.cursor.execute(query)
            ev_cols = [d[0] for d in self.cursor.description]
            lookup = {}
            for row in self.cursor.fetchall():
                rd = dict(zip(ev_cols, row, strict=False))
                normalized = {str(name).casefold(): value for name, value in rd.items()}
                lookup[(normalized["tourneytypeid"], normalized["playerid"])] = rd

            tt_idx = column_indices["tourneytypeid"]
            pid_idx = column_indices["playerid"]
            augmented = []
            for row_data in result:
                key = (row_data[tt_idx], row_data[pid_idx])
                ev_row = lookup.get(key, {})
                extra = [descriptor.format(adapter.compute(descriptor, ev_row)) for descriptor in descriptors]
                augmented.append(list(row_data) + extra)
            new_colnames = colnames + [descriptor.name for descriptor in descriptors]
            log.info(f"GuiTourneyPlayerStats: merged {len(descriptors)} ChipEV column(s) for {len(lookup)} group(s)")
            return augmented, new_colnames
        except Exception as exc:  # noqa: BLE001 - best effort, the base grid stands without it
            log.warning(f"GuiTourneyPlayerStats._merge_chipev_columns failed (skipping): {exc}")
            self.db.rollback()
            return result, colnames

    @staticmethod
    def _format_grid_value(alias: str, value: Any, currency: str, fallback_format: str) -> str:
        """Format a tournament-stat cell while leaving its raw sort value separate."""
        if alias in _MONEY_COLUMNS:
            return format_currency(value, currency)
        if alias in _PERCENT_COLUMNS:
            return f"{format_number(value)}%"
        if alias in _COUNT_COLUMNS:
            return format_number(value, 0)
        return fallback_format % value

    # ------------------------------------------------------------------ #
    # Rendering                                                           #
    # ------------------------------------------------------------------ #
    def _show_placeholder(self, text: str) -> None:
        self.placeholder_text.setText(text)
        self._pages.setCurrentIndex(0)

    def scoped_results(self) -> list[TourneyResult]:
        """The results the drill-down narrows the page to."""
        results = self.results
        for scope in self._scopes:
            results = [result for result in results if group_key(scope.mode, result) == scope.key]
        return results

    def _render(self, select_key: tuple[Any, ...] | None = None) -> None:
        results = self.scoped_results()
        self._pages.setCurrentIndex(1)
        self.setUpdatesEnabled(False)
        try:
            self._render_header(results)
            self._render_overview(results)
            self._render_chart(results)
            self._render_table(results, select_key)
            self._render_breadcrumb()
        finally:
            self.setUpdatesEnabled(True)

    def _render_header(self, results: list[TourneyResult]) -> None:
        players = sorted({result.player_name for result in results})
        starts = [result.start for result in results if result.start]
        parts = []
        if players:
            parts.append(", ".join(players[:3]) + ("…" if len(players) > 3 else ""))
        if starts:
            first, last = min(starts), max(starts)
            first_day, last_day = format_date(first), format_date(last)
            parts.append(first_day if first_day == last_day else f"{first_day} – {last_day}")
        self.subtitle_label.setText(" · ".join(parts))

    def _render_overview(self, results: list[TourneyResult]) -> None:
        totals = summarize(results)
        count = sum(summary.count for summary in totals.values())
        unknown = sum(summary.unknown for summary in totals.values())
        known = count - unknown
        self.card_count.set_value(format_number(count, 0))
        self.card_count.set_note(
            _("%s without a result") % format_number(unknown, 0) if unknown else "",
        )
        self.card_count.note.setToolTip(
            _(
                "Imported from their hands only: no prize was recorded. They are left out of "
                "the buy-ins, net won, ROI and ITM rather than counted as losses. "
                "Import the tournament summaries to complete them."
            )
        )
        self.card_buyins.set_value(_money_lines(totals, "cost") if known else "–")
        nets = [summary.net for summary in totals.values()]
        single = len(totals) == 1
        self.card_net.set_value(
            _money_lines(totals, "net", show_plus=True) if known else "–",
            _tone(nets[0]) if single and known else "",
        )
        rois = [summary.roi for summary in totals.values()]
        self.card_roi.set_value(
            "\n".join(_percent(roi) for roi in rois),
            _tone(rois[0]) if single else "",
            "\n".join(f"{currency}: {_percent(s.roi)}" for currency, s in totals.items()) if not single else "",
        )
        cashes = sum(summary.cashes for summary in totals.values())
        self.card_itm.set_value(
            _percent(100.0 * cashes / known if known else None),
            tooltip=_("%(cashes)s cashes in %(count)s tournaments")
            % {"cashes": format_number(cashes, 0), "count": format_number(known, 0)},
        )
        ranked = sum(summary.ranked for summary in totals.values())
        finish_total = sum(summary.finish_total for summary in totals.values())
        self.card_finish.set_value(_number(finish_total / ranked if ranked else None, 2))
        firsts = sum(summary.first for summary in totals.values())
        seconds = sum(summary.second for summary in totals.values())
        thirds = sum(summary.third for summary in totals.values())
        self.card_podium.set_value(
            f"{format_number(firsts, 0)} · {format_number(seconds, 0)} · {format_number(thirds, 0)}"
        )
        has_bounties = any(summary.bounties for summary in totals.values())
        self.kpis.set_card_visible(self.card_bounties, has_bounties)
        if has_bounties:
            self.card_bounties.set_value(_money_lines(totals, "bounties"))

    def _render_chart(self, results: list[TourneyResult]) -> None:
        currency = main_currency(results)
        currencies = {result.currency for result in results}
        note = ""
        if len(currencies) > 1 and currency:
            note = _("Curves show the %(currency)s tournaments only") % {"currency": currency}
        self.chart.set_results(results, currency, note)

    def _columns_for(self, mode: str, groups: list[Group]) -> list[_Column]:
        if mode == BY_TOURNAMENT:
            columns = [
                _Column("start", _("Start"), align=_ALIGN_LEFT),
                _Column("site", _("Site"), align=_ALIGN_LEFT),
                _Column("tourney_no", _("Tournament #"), align=_ALIGN_LEFT),
                _Column("description", _("Description"), align=_ALIGN_LEFT),
                _Column("name", _("Name"), align=_ALIGN_LEFT),
                _Column("player", _("Player"), align=_ALIGN_LEFT),
                _Column("buyin", _("Buy-in"), _("Buy-in + fee")),
                _Column("entries", _("Entrants")),
                _Column("finish", _("Finish")),
                _Column("won", _("Won"), _("Prize and bounties")),
                _Column("bounties", _("Bounties")),
                _Column("net", _("Net won")),
                _Column("hands", _("Hands"), _("Hands stored for this tournament")),
                _Column("end", _("End"), align=_ALIGN_LEFT, hidden=True),
            ]
        else:
            label = {BY_DESCRIPTION: _("Description"), BY_BUYIN: _("Buy-in"), BY_DATE: _("Date")}[mode]
            columns = [
                _Column("label", label, align=_ALIGN_LEFT),
                _Column("site", _("Site"), align=_ALIGN_LEFT),
                _Column("player", _("Player"), align=_ALIGN_LEFT),
                _Column("count", _("Tourneys")),
                _Column("unknown", _("No result"), _("Tournaments imported without their result (no summary)")),
                _Column("avg_cost", _("Avg buy-in"), _("Average buy-in + fee"), hidden=mode == BY_BUYIN),
                _Column("itm", _("ITM %"), _("Share of the tournaments that paid a prize")),
                _Column("cashes", _("Cashes")),
                _Column("roi", _("ROI %")),
                _Column("net", _("Net won")),
                _Column("won", _("Won"), _("Prizes and bounties")),
                _Column("bounties", _("Bounties")),
                _Column("per_tourney", _("Avg profit"), _("Net won per tournament")),
                _Column("avg_finish", _("Avg finish")),
                _Column("first", _("1st")),
                _Column("second", _("2nd")),
                _Column("third", _("3rd")),
                _Column("avg_entries", _("Avg entrants")),
                _Column("hands", _("Hands")),
            ]
            if mode == BY_DESCRIPTION:
                # The player stats are computed per tournament type over the whole filter range:
                # they still describe a row narrowed to some types, not one narrowed to a date or
                # a buy-in, which covers only part of each type's tournaments.
                in_range = all(scope.mode == BY_DESCRIPTION for scope in self._scopes)
                columns.extend(
                    _Column(
                        f"stat:{index}",
                        str(spec[colheading]),
                        _("Over every tournament of this type in the filters")
                        if in_range
                        else _("Not available in this drill-down: computed over every tournament of the type"),
                        hidden=str(spec[colalias]) not in _DEFAULT_STATS,
                        available=in_range,
                    )
                    for index, spec in enumerate(self._descriptor_specs)
                )
        players = {group.player_name for group in groups}
        sites = {group.site for group in groups}
        has_bounties = any(group.summary.bounties for group in groups)
        auto_hidden = set()
        if len(players) <= 1:
            auto_hidden.add("player")
        if len(sites) <= 1 and mode != BY_TOURNAMENT:
            auto_hidden.add("site")
        if not has_bounties:
            auto_hidden.add("bounties")
        if not any(group.summary.unknown for group in groups):
            auto_hidden.add("unknown")
        if not any(result.name for group in groups for result in group.results):
            auto_hidden.add("name")
        return [
            _Column(
                column.key,
                column.title,
                column.tooltip,
                column.align,
                column.hidden or column.key in auto_hidden,
                column.available,
            )
            for column in columns
        ]

    def _group_label(self, mode: str, group: Group) -> tuple[str, Any]:
        """The text and sort value of a group's first cell."""
        if mode == BY_BUYIN:
            currency, cost = group.key
            return format_currency(cost, currency), float(cost)
        if mode == BY_DATE:
            day, _currency = group.key
            first = group.results[0]
            if first.local_day is None:
                return _("Unknown date"), ""
            return format_date(first.local_day), day
        return group.label, group.label

    def _cell(self, mode: str, column: str, group: Group) -> tuple[str, Any, str]:
        """(text, sort value, tone) of one cell."""
        s = group.summary
        cur = s.currency
        if column == "label":
            text, sort = self._group_label(mode, group)
            return text, sort, ""
        if mode == BY_TOURNAMENT:
            return self._tournament_cell(column, group)
        if column.startswith("stat:"):
            index = int(column.split(":", 1)[1])
            extras = self._descriptor_values.get(group.key, [])
            text = extras[index] if index < len(extras) else ""
            return text, _sortable(text), ""
        if not s.known and column in _MONEY_KEYS:
            return "–", -(10**12), ""
        values = {
            "site": (group.site, group.site, ""),
            "player": (group.player_name, group.player_name, ""),
            "count": (format_number(s.count, 0), s.count, ""),
            "unknown": (format_number(s.unknown, 0) if s.unknown else "", s.unknown, ""),
            "avg_cost": (format_currency(s.avg_cost or 0, cur), s.avg_cost or 0, ""),
            "itm": (_percent(s.itm), s.itm if s.itm is not None else -1, ""),
            "cashes": (format_number(s.cashes, 0), s.cashes, ""),
            "roi": (_percent(s.roi), s.roi if s.roi is not None else -(10**9), _tone(s.roi)),
            "net": (format_currency(s.net, cur, show_plus=True), s.net, _tone(s.net)),
            "won": (format_currency(s.won, cur), s.won, ""),
            "bounties": (format_currency(s.bounties, cur) if s.bounties else "", s.bounties, ""),
            "per_tourney": (
                format_currency(s.per_tourney or 0, cur, show_plus=True),
                s.per_tourney or 0,
                _tone(s.per_tourney),
            ),
            "avg_finish": (_number(s.avg_finish, 2), s.avg_finish if s.avg_finish is not None else 10**9, ""),
            "first": (format_number(s.first, 0), s.first, ""),
            "second": (format_number(s.second, 0), s.second, ""),
            "third": (format_number(s.third, 0), s.third, ""),
            "avg_entries": (_number(s.avg_entries, 1), s.avg_entries or 0, ""),
            "hands": (format_number(s.hands, 0), s.hands, ""),
        }
        return values.get(column, ("", "", ""))

    @staticmethod
    def _tournament_cell(column: str, group: Group) -> tuple[str, Any, str]:
        """(text, sort value, tone) of a tournament row.

        A re-entered tournament has one TourneysPlayers row per entry: the row
        adds their costs and winnings up, and shows the best finish.
        """
        r = group.results[0]
        s = group.summary
        cur = s.currency
        entries = len(group.results)
        finishes = [result.finish for result in group.results if result.finish]
        finish = min(finishes) if finishes else None
        buyin = f"{format_currency(r.buy_in, cur)}+{format_currency(r.fee, cur)}"
        if entries > 1:
            buyin = f"{buyin} ×{format_number(entries, 0)}"
        unknown = ("–", -(10**12), "")
        values: dict[str, tuple[str, Any, str]] = {
            "start": (format_utc_datetime(r.start) if r.start else "", r.start.isoformat() if r.start else "", ""),
            "end": (format_utc_datetime(r.end) if r.end else "", r.end.isoformat() if r.end else "", ""),
            "site": (r.site, r.site, ""),
            "tourney_no": (str(r.tourney_no or ""), _sortable(r.tourney_no), ""),
            "description": (r.description, r.description, ""),
            "name": (r.name, r.name, ""),
            "player": (r.player_name, r.player_name, ""),
            "buyin": (buyin, r.cost * entries, ""),
            "entries": (_number(r.entries), r.entries or 0, ""),
            "finish": (_number(finish), finish or 10**9, ""),
            "won": (format_currency(s.won, cur), s.won, "") if s.known else unknown,
            "bounties": (format_currency(s.bounties, cur) if s.bounties else "", s.bounties, ""),
            "net": (format_currency(s.net, cur, show_plus=True), s.net, _tone(s.net)) if s.known else unknown,
            # Every entry is the same tournament: its hands are counted once.
            "hands": (format_number(r.hands, 0), r.hands, ""),
        }
        return values.get(column, ("", "", ""))

    def _render_table(self, results: list[TourneyResult], select_key: tuple[Any, ...] | None) -> None:
        mode = self.group_mode
        groups = group_results(mode, results)
        if mode == BY_TOURNAMENT:
            groups.reverse()  # most recent first, as a results list reads
        self._groups = {group.key: group for group in groups}
        columns = self._columns_for(mode, groups)
        self._columns = columns

        header = self.table.horizontalHeader()
        sort_column = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()

        self.table.setSortingEnabled(False)
        self._fill_model(mode, groups, columns)
        for index, column in enumerate(columns):
            hidden = not column.available or self._column_overrides.get(column.key, column.hidden)
            self.table.setColumnHidden(index, hidden)
        self.table.setSortingEnabled(True)
        self._restore_sort(mode, columns, sort_column, sort_order)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, min(max(self.table.columnWidth(0), 120), 360))
        self._apply_search()

        for button in self.mode_buttons.buttons():
            button.setChecked(button.property("mode") == mode)
        self._select_key(select_key)
        self._render_totals(results)
        self._update_actions()

    def _fill_model(self, mode: str, groups: list[Group], columns: list[_Column]) -> None:
        colors = _palette()
        self.tone_delegate.colors = {"up": QColor(colors["graph_up"]), "down": QColor(colors["graph_down"])}
        self.model.clear()
        self.model.setColumnCount(len(columns))
        for index, column in enumerate(columns):
            item = QStandardItem(column.title)
            item.setToolTip(column.tooltip or column.title)
            self.model.setHorizontalHeaderItem(index, item)

        # The first cell carries the row's position in _row_keys: PySide hands
        # a stored tuple back as a list, so keys are not stored in the model.
        self._row_keys = []
        for group in groups:
            row = []
            for column in columns:
                text, sort, tone = self._cell(mode, column.key, group)
                item = QStandardItem(text)
                item.setData(sort, _SORT_ROLE)
                item.setTextAlignment(column.align)
                item.setEditable(False)
                if tone:
                    item.setData(tone, _TONE_ROLE)
                row.append(item)
            row[0].setData(len(self._row_keys), _KEY_ROLE)
            self._row_keys.append(group.key)
            if mode == BY_DESCRIPTION and group.names:
                row[0].setToolTip(", ".join(name for name, _count in group.names.most_common(3)))
            self.model.appendRow(row)

    def _restore_sort(self, mode: str, columns: list[_Column], sort_column: int, sort_order: Qt.SortOrder) -> None:
        """Keep the user's sort within a view; newest first or most played first on entering one."""
        if self._table_mode == mode and 0 <= sort_column < len(columns):
            self.table.sortByColumn(sort_column, sort_order)
        elif mode in (BY_TOURNAMENT, BY_DATE):
            self.table.sortByColumn(0, Qt.SortOrder.DescendingOrder)
        else:
            count = next(index for index, column in enumerate(columns) if column.key == "count")
            self.table.sortByColumn(count, Qt.SortOrder.DescendingOrder)
        self._table_mode = mode

    def _render_totals(self, results: list[TourneyResult]) -> None:
        totals = summarize(results)
        parts = [_("%s tournaments") % format_number(sum(s.count for s in totals.values()), 0)]
        for currency, summary in totals.items():
            if not summary.known:
                continue
            parts.append(
                _("Net %(net)s · ROI %(roi)s")
                % {"net": format_currency(summary.net, currency, show_plus=True), "roi": _percent(summary.roi)}
            )
        shown, total = self.proxy.rowCount(), self.model.rowCount()
        if shown != total:
            parts.append(_("%(shown)s of %(total)s rows shown") % {"shown": shown, "total": total})
        self.totals_label.setText(" · ".join(parts))
        if self.group_mode == BY_TOURNAMENT:
            self.hint_label.setText(_("Double-click a tournament to open its hands"))
        else:
            self.hint_label.setText(_("Double-click a row to see its tournaments"))

    def _render_breadcrumb(self) -> None:
        if not self._scopes:
            self.breadcrumb_bar.hide()
            return
        link_color = _palette().get("accent_text", "")
        style = f' style="color: {link_color};"' if link_color else ""
        everything = _("All tournaments")
        links = [f'<a href="0"{style}>{everything}</a>']
        for depth, scope in enumerate(self._scopes, start=1):
            label = scope.label.replace("&", "&amp;").replace("<", "&lt;")
            if depth == len(self._scopes):
                links.append(f"<b>{label}</b>")
            else:
                links.append(f'<a href="{depth}"{style}>{label}</a>')
        self.breadcrumb_label.setText("  ›  ".join(links))
        self.breadcrumb_bar.show()

    # ------------------------------------------------------------------ #
    # Interaction                                                         #
    # ------------------------------------------------------------------ #
    def _key_at(self, index: QModelIndex) -> tuple[Any, ...] | None:
        if not index.isValid():
            return None
        position = index.sibling(index.row(), 0).data(_KEY_ROLE)
        keys = self._row_keys
        return keys[position] if isinstance(position, int) and 0 <= position < len(keys) else None

    def _selected_key(self) -> tuple[Any, ...] | None:
        return self._key_at(self.table.currentIndex())

    def _select_key(self, key: tuple[Any, ...] | None) -> None:
        if key is None or self.proxy.rowCount() == 0:
            self.table.clearSelection()
            return
        for row in range(self.proxy.rowCount()):
            index = self.proxy.index(row, 0)
            if self._key_at(index) == key:
                self.table.setCurrentIndex(index)
                self.table.selectRow(row)
                self.table.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
                return

    def set_group_mode(self, mode: str) -> None:
        """Show the results grouped by ``mode``, keeping the drill-down."""
        if mode == self.group_mode:
            return
        self.group_mode = mode
        if self.results:
            results = self.scoped_results()
            self._render_table(results, None)

    def _on_mode_clicked(self, button) -> None:
        self.set_group_mode(button.property("mode"))

    def drill_into(self, key: tuple[Any, ...]) -> None:
        """Narrow the page to one group of the current view and list its tournaments."""
        group = self._groups.get(key)
        if group is None or self.group_mode == BY_TOURNAMENT:
            return
        label, _sort = self._group_label(self.group_mode, group)
        self._scopes.append(_Scope(self.group_mode, key, label, self.search_edit.text()))
        self.group_mode = BY_TOURNAMENT
        self._set_search("")
        self._render()
        if self.proxy.rowCount():
            self.table.selectRow(0)
            self.table.setCurrentIndex(self.proxy.index(0, 0))
        self.table.setFocus()

    def go_back(self) -> None:
        """Leave the last drill-down step, reselecting the group it came from."""
        if not self._scopes:
            return
        scope = self._scopes.pop()
        self.group_mode = scope.mode
        self._set_search(scope.search)
        self._render(select_key=scope.key)
        self.table.setFocus()

    def clear_scope(self, depth: int = 0) -> None:
        """Go back to drill-down ``depth`` (0: every tournament the filters select)."""
        if depth >= len(self._scopes):
            return
        left = self._scopes[depth]
        self._scopes = self._scopes[:depth]
        self.group_mode = left.mode
        self._set_search(left.search)
        self._render(select_key=left.key)

    def _on_breadcrumb_link(self, link: str) -> None:
        if link.isdigit():
            self.clear_scope(int(link))

    def _on_escape(self) -> None:
        if self.search_edit.hasFocus() and self.search_edit.text():
            self.search_edit.clear()
            return
        self.go_back()

    def _focus_search(self) -> None:
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def _set_search(self, text: str) -> None:
        """Put ``text`` in the search box; the next render applies it."""
        self._search_timer.stop()
        blocked = self.search_edit.blockSignals(True)
        self.search_edit.setText(text)
        self.search_edit.blockSignals(blocked)

    def _apply_search(self) -> None:
        self.proxy.setFilterFixedString(self.search_edit.text().strip())
        if self.results:
            self._render_totals(self.scoped_results())

    def _on_row_activated(self, index: QModelIndex) -> None:
        key = self._key_at(index)
        if key is None:
            return
        if self.group_mode == BY_TOURNAMENT:
            group = self._groups.get(key)
            if group is not None:
                result = group.results[0]
                self._open_tourney_hands(result.tourney_id, result.tourney_no)
        else:
            self.drill_into(key)

    def _open_selected_hands(self) -> None:
        key = self._selected_key()
        group = self._groups.get(key) if key is not None else None
        if group is not None and self.group_mode == BY_TOURNAMENT:
            result = group.results[0]
            self._open_tourney_hands(result.tourney_id, result.tourney_no)

    def _update_actions(self, *_args) -> None:
        key = self._selected_key()
        group = self._groups.get(key) if key is not None else None
        enabled = self.group_mode == BY_TOURNAMENT and group is not None and group.results[0].hands > 0
        self.open_hands_button.setEnabled(enabled)
        self.open_hands_button.setVisible(self.group_mode == BY_TOURNAMENT)

    def _show_header_menu(self, position) -> None:
        header = self.table.horizontalHeader()
        menu = QMenu(self)
        for index, column in enumerate(self._columns):
            if index == 0:
                continue
            action = menu.addAction(column.title)
            action.setCheckable(True)
            action.setChecked(not self.table.isColumnHidden(index))
            action.setEnabled(column.available)
            action.setToolTip(column.tooltip)
            action.toggled.connect(lambda checked, i=index, k=column.key: self._set_column_shown(i, k, checked))
        menu.addSeparator()
        fit = menu.addAction(_("Fit columns to contents"))
        fit.triggered.connect(self.table.resizeColumnsToContents)
        menu.exec(header.viewport().mapToGlobal(position))

    def _set_column_shown(self, index: int, key: str, shown: bool) -> None:
        self._column_overrides[key] = not shown
        self.table.setColumnHidden(index, not shown)
        if shown:
            self.table.resizeColumnToContents(index)

    def changeEvent(self, event) -> None:  # noqa: N802  # pylint: disable=invalid-name  # Qt override
        super().changeEvent(event)
        # A theme switch restyles the cards by itself; the curves and tones need redrawing.
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.StyleChange) and self.results:
            QTimer.singleShot(0, self._rerender_colors)

    def _rerender_colors(self) -> None:
        if self.results:
            self._render(select_key=self._selected_key())

    # ------------------------------------------------------------------ #
    # Hands of one tournament                                             #
    # ------------------------------------------------------------------ #
    def _open_tourney_hands(self, tourney_id, tourney_no) -> None:
        """Open a Tourney Hand Viewer tab loaded with one tournament's hands."""
        ph = self.sql.query.get("placeholder", "%s")
        q = "SELECT id FROM Hands WHERE tourneyId = ? ORDER BY startTime, id".replace("?", ph)
        c = self.db.get_cursor()
        c.execute(q, (tourney_id,))
        hand_ids = [r[0] for r in c.fetchall()]
        self.db.rollback()
        if not hand_ids:
            QMessageBox.information(
                self,
                _("Tournament hands"),
                _(
                    "No hands stored for tournament #%s.\n\n"
                    "This tournament was imported from a summary without its hand histories."
                )
                % tourney_no,
            )
            return
        viewer = GuiTourHandViewer.TourHandViewer(self.conf, self.sql, self.main_window)
        # Reveal the same hero/alias chosen in this stats tab before loading, so
        # the viewer doesn't fall back to its default alias and show every hand
        # face-down when the tournament was recorded under another alias
        # (e.g. "Hero" vs the configured screen name "koko_sat").
        self._sync_viewer_hero(viewer)
        self.main_window.threads.append(viewer)
        self.main_window.add_and_display_tab(viewer, f"Tourney #{tourney_no}")
        viewer.reload_hands(hand_ids)

    def _sync_viewer_hero(self, viewer) -> None:
        """Select, in the new viewer, the same hero entry chosen in this stats tab."""
        src = getattr(self.filters, "heroList", None)
        dst = getattr(getattr(viewer, "filters", None), "heroList", None)
        if src is None or dst is None:
            return
        target = src.currentText()
        for i in range(dst.count()):
            if dst.itemText(i) == target:
                dst.setCurrentIndex(i)
                return


def _sortable(value: Any) -> float:
    """A numeric sort value: one type per column, or the proxy cannot order the rows."""
    try:
        return float(str(value).replace("\u202f", "").replace("\xa0", "").replace(",", ".").rstrip("%"))
    except ValueError:
        return float("-inf")


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    import fpdb_3_legacy.Configuration as Configuration

    config = Configuration.Config()

    settings = {}
    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())

    from fpdb_3_legacy import SQL, Database

    app = QApplication([])
    sql = SQL.Sql(db_server=settings["db-server"])
    db = Database.Database(config, sql)
    main_window = QMainWindow()
    i = GuiTourneyPlayerStats(config, db, sql, main_window)
    main_window.setCentralWidget(i)
    main_window.show()
    main_window.resize(1400, 800)
    app.exec()
    return 0


if __name__ == "__main__":
    sys.exit(main())
