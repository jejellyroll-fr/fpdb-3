"""__init__.py

Entry point for the ring_stats package.
Exports the modernized GuiRingPlayerStats class, inheriting from QSplitter to
maintain full backward compatibility with fpdb.pyw while hosting
l'architecture d'onglets asynchrones.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from fpdb_3_legacy import Card, Database, Filters, gui_empty_state
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.ring_stats.base import ModernStatsWidget
from fpdb_3_legacy.ring_stats.controller import RingStatsController
from fpdb_3_legacy.ring_stats.views.dashboard_view import DashboardTab
from fpdb_3_legacy.ring_stats.views.positional_view import PositionalTab
from fpdb_3_legacy.ring_stats.views.starting_hands_view import StartingHandsTab
from fpdb_3_legacy.ring_stats.views.table_view import StatsTableView

log = get_logger("ring_stats_main")

colalias, colheading, colshowsumm, colshowposn, colformat, coltype, colxalign = (0, 1, 2, 3, 4, 5, 6)


class GuiRingPlayerStats(QSplitter):
    """Modern main Cash Game statistics widget (Ring Player Stats).

    Preserves the original behavior (splitter with filters on the left)
    mais remplace les tableaux bruts de droite par un QTabWidget moderne
    contenant les tableaux de bord, graphes, heatmaps de positions et starting hands.
    """

    def __init__(self, config, querylist, mainwin, debug=True) -> None:
        super().__init__(Qt.Orientation.Horizontal)
        self.debug = debug
        self.conf = config
        self.main_window = mainwin
        self.sql = querylist

        # Initialize the database
        self.db = Database.Database(self.conf, sql=self.sql)
        self.cursor = self.db.cursor

        # Original detailed filters
        self.handtests: list[list[Any]] = [
            ["gt.maxSeats", "Size of Table", 2, 10],
            ["h.playersVpi", "Players who VPI", 0, 10],
            ["h.playersAtStreet1", "Players at Flop", 0, 10],
            ["h.playersAtStreet2", "Players at Turn", 0, 10],
            ["h.playersAtStreet3", "Players at River", 0, 10],
            ["h.playersAtStreet4", "Players at Street7", 0, 10],
            ["h.playersAtShowdown", "Players at Showdown", 0, 10],
            ["h.street0Raises", "Bets to See Flop", 0, 5],
            ["h.street1Raises", "Bets to See Turn", 0, 5],
            ["h.street2Raises", "Bets to See River", 0, 5],
            ["h.street3Raises", "Bets to See Street7", 0, 5],
            ["h.street4Raises", "Bets to See Showdown", 0, 5],
        ]
        self.cardstests: list[list[Any]] = [
            [Card.DATABASE_FILTERS["pair"], "Pocket pairs"],
            [Card.DATABASE_FILTERS["suited"], "Suited"],
            [Card.DATABASE_FILTERS["suited_connectors"], "Suited connectors"],
            [Card.DATABASE_FILTERS["offsuit"], "Offsuit"],
            [Card.DATABASE_FILTERS["offsuit_connectors"], "Offsuit connectors"],
        ]
        self.detailFilters: list[tuple[str, int, int]] = []
        self.cardsFilters: list[str] = []
        self.columns = self.conf.get_gui_cash_stat_params()

        # 1. Filter sidebar (left)
        filters_display = {
            "Heroes": True,
            "Sites": True,
            "Games": True,
            "Currencies": True,
            "Limits": True,
            "LimitSep": True,
            "LimitType": True,
            "Type": True,
            "UseType": "ring",
            "Seats": True,
            "SeatSep": True,
            "Dates": True,
            "Groups": True,
            "GroupsAll": True,
            "Button1": True,
            "Button2": True,
        }
        self.filters = Filters.Filters(self.db, display=filters_display)
        self.filters.registerButton1Name("Filters")
        self.filters.registerButton1Callback(self.showDetailFilter)
        self.filters.registerButton2Name("Refresh Stats")
        self.filters.registerButton2Callback(self.refreshStats)

        self.columns_button = QPushButton(_("Columns"))
        self.columns_button.clicked.connect(self.showColumnConfig)
        filters_layout = self.filters.layout()
        if filters_layout is None:
            raise RuntimeError("ring-stat filters were created without a layout")
        filters_layout.addWidget(self.columns_button)

        sidebar_scroll = QScrollArea()
        sidebar_scroll.setObjectName("filterSidebar")
        sidebar_scroll.setWidget(self.filters)
        self.addWidget(sidebar_scroll)

        # 2. Modernized statistics display area (right)
        self.stats_tabs = ModernStatsWidget(self)

        # Tab 1: Dashboard
        self.dashboard_tab = DashboardTab(self.stats_tabs)
        self.stats_tabs.addTab(self.dashboard_tab, _("Dashboard"))

        # Tab 2: Detailed tables
        self.table_tab = StatsTableView(self.stats_tabs)
        self.stats_tabs.addTab(self.table_tab, _("Stats Tables"))

        # Tab 3: Position heatmap
        self.position_tab = PositionalTab(self.stats_tabs)
        self.stats_tabs.addTab(self.position_tab, _("Position Heatmap"))

        # Onglet 4 : Starting Hands
        self.hands_tab = StartingHandsTab(self.stats_tabs)
        self.stats_tabs.addTab(self.hands_tab, _("Starting Hands"))

        self.addWidget(self.stats_tabs)

        # Configure stretch factors
        self.setStretchFactor(0, 0)
        self.setStretchFactor(1, 1)

        # 3. Controller
        self.controller = RingStatsController(self.db, self.conf, self.sql)
        self.controller.dashboard_data_ready.connect(self.dashboard_tab.update_data)
        self.controller.summary_model_ready.connect(self.table_tab.set_summary_model)
        self.controller.hand_model_ready.connect(self.table_tab.set_hand_model)
        self.controller.hand_model_ready.connect(self.update_hands_tab_data)
        self.controller.position_data_ready.connect(self.position_tab.update_position_data)
        self.controller.no_data_found.connect(self.handle_no_data_found)

    def handle_no_data_found(self, reason: str = "") -> None:
        """Explique pourquoi l'onglet est vide (filtre incomplet, base vide, ...)."""
        try:
            no_data_reason = gui_empty_state.NoDataReason(reason)
        except ValueError:
            no_data_reason = gui_empty_state.NoDataReason.NO_ROWS
        gui_empty_state.show_no_data(self, no_data_reason, context="Ring player stats", db=self.db)
        self.db.rollback()

    def refreshStats(self, checkState=None) -> None:
        """Called when filters are refreshed."""
        # Force stylesheet updates to adapt to a theme change
        self._apply_theme()

        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        is_sync = not getattr(self.controller, "async_mode", True)
        if is_sync:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        try:
            # Start reloading the queries
            self.controller.refresh_all(self.filters)
        finally:
            if is_sync:
                QApplication.restoreOverrideCursor()

    def refresh_theme(self, colors=None, theme_colors=None) -> None:
        """Called by ThemeManager.apply_legacy_polish() when the theme changes.

        Reapply the QSS stylesheet to the tab container and propagate color
        updates to all child tabs.
        """
        self._apply_theme()

    def _apply_theme(self) -> None:
        """Reapply theme styles to all components."""
        self.stats_tabs.apply_theme_stylesheet()
        self.dashboard_tab.refresh_theme()
        self.position_tab.refresh_theme()
        self.hands_tab.refresh_theme()
        self.table_tab.refresh_theme()

    def update_hands_tab_data(self, model: QStandardItemModel) -> None:
        """Intercept the detailed hand model to update the starting-hand grid/graph."""
        hand_stats = {}
        omaha_rows = []

        # Find the column containing the starting cards (Hand)
        hand_col_idx = 0
        try:
            hand_heading = next(x for x in self.columns if x[0] == "hand")[1]
            for col in range(model.columnCount()):
                header_item = model.horizontalHeaderItem(col)
                if header_item and header_item.text() == hand_heading:
                    hand_col_idx = col
                    break
        except (AttributeError, IndexError, StopIteration, TypeError, ValueError):
            log.debug("Unable to resolve starting-hand column", exc_info=True)
            hand_col_idx = 0

        categories = model.property("categories") or []
        log.info("Active categories for hands tab: %s", categories)

        # Determine the Omaha variant
        variant = "omaha4"
        if any(cat in categories for cat in ["5_omahahi", "5_omahalo"]):
            variant = "omaha5"
        elif any(cat in categories for cat in ["6_omahahi", "6_omahalo"]):
            variant = "omaha6"

        is_holdem = True
        if categories:
            if not any("holdem" in cat for cat in categories):
                is_holdem = False
        else:
            # Check the game type on the first row as a fallback
            if model.rowCount() > 0:
                first_item = model.item(0, hand_col_idx)
                first_game_name = first_item.text() if first_item else ""
                # Omaha usually contains suffixes such as ss, ds, or four-digit numbers
                if any(suffix in first_game_name.lower() for suffix in ["ss", "ds", "rainbow"]):
                    is_holdem = False
                else:
                    parts = first_game_name.split()
                    if parts and len(parts[0]) > 3:
                        is_holdem = False

        if is_holdem:
            for row in range(model.rowCount()):
                item_hand = model.item(row, hand_col_idx)
                hand_text = item_hand.text() if item_hand else ""
                if not hand_text:
                    continue
                # Extract values
                try:
                    n = float(model.item(row, 1).text()) if model.item(row, 1) else 0
                    vpip = float(model.item(row, 2).text().replace("%", "")) if model.item(row, 2) else 0.0
                    net = (
                        float(model.item(row, model.columnCount() - 2).text().replace("€", "").replace(" ", ""))
                        if model.item(row, model.columnCount() - 2)
                        else 0.0
                    )
                except (ValueError, TypeError, AttributeError):
                    n = 0
                    vpip = 0.0
                    net = 0.0

                hand_stats[hand_text] = {"n": n, "net": net, "vpip": vpip}
            self.hands_tab.update_holdem_data(hand_stats)
        else:
            for row in range(model.rowCount()):
                item_hand = model.item(row, hand_col_idx)
                hand_text = item_hand.text() if item_hand else ""
                if not hand_text:
                    continue
                try:
                    n = float(model.item(row, 1).text()) if model.item(row, 1) else 0
                except (ValueError, TypeError):
                    n = 0
                omaha_rows.append({"hand": hand_text, "n": n})
            self.hands_tab.update_omaha_data(omaha_rows, variant)

    def showColumnConfig(self) -> None:
        """Display the column configuration dialog."""
        dialog = QDialog(self.main_window)
        dialog.setWindowTitle(_("Column Configuration"))
        layout = QVBoxLayout(dialog)

        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Column", "Summary", "Position"])
        table.verticalHeader().setVisible(False)
        table.setRowCount(len(self.columns))

        for row, col in enumerate(self.columns):
            item_name = QTableWidgetItem(col[colheading])
            item_name.setFlags(item_name.flags() ^ Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, 0, item_name)

            item_summ = QTableWidgetItem()
            item_summ.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            item_summ.setCheckState(Qt.CheckState.Checked if col[colshowsumm] else Qt.CheckState.Unchecked)
            table.setItem(row, 1, item_summ)

            item_posn = QTableWidgetItem()
            item_posn.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            item_posn.setCheckState(Qt.CheckState.Checked if col[colshowposn] else Qt.CheckState.Unchecked)
            table.setItem(row, 2, item_posn)

        table.resizeColumnsToContents()
        layout.addWidget(table)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            for row in range(len(self.columns)):
                summary_item = table.item(row, 1)
                position_item = table.item(row, 2)
                if summary_item is None or position_item is None:
                    raise RuntimeError(f"column configuration row {row} is incomplete")
                self.columns[row][colshowsumm] = summary_item.checkState() == Qt.CheckState.Checked
                self.columns[row][colshowposn] = position_item.checkState() == Qt.CheckState.Checked

            self.conf.save_gui_cash_stats()
            self.conf.save()
            self.refreshStats(None)

    def showDetailFilter(self, checkState) -> None:
        """Display advanced filters (Pocket Pairs, Suited Connectors, etc.)."""
        detailDialog = QDialog(self.main_window)
        detailDialog.setWindowTitle(_("Detailed Filters"))

        handbox = QVBoxLayout()
        detailDialog.setLayout(handbox)

        label = QLabel(_("Hand Filters:"))
        handbox.addWidget(label)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        grid = QGridLayout()
        handbox.addLayout(grid)
        for row, htest in enumerate(self.handtests):
            cb = QCheckBox()
            lbl_from = QLabel(htest[1])
            lbl_tween = QLabel(_("between"))
            lbl_to = QLabel(_("and"))
            sb1 = QSpinBox()
            sb1.setRange(0, 10)
            sb1.setValue(htest[2])
            sb2 = QSpinBox()
            sb2.setRange(2, 10)
            sb2.setValue(htest[3])

            for df in self.detailFilters:
                if df[0] == htest[0]:
                    cb.setChecked(True)
                    break

            grid.addWidget(cb, row, 0)
            grid.addWidget(lbl_from, row, 1, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(lbl_tween, row, 2)
            grid.addWidget(sb1, row, 3)
            grid.addWidget(lbl_to, row, 4)
            grid.addWidget(sb2, row, 5)

            htest[4:7] = [cb, sb1, sb2]

        label = QLabel(_("Restrict to hand types:"))
        handbox.addWidget(label)
        for ctest in self.cardstests:
            hbox = QHBoxLayout()
            handbox.addLayout(hbox)
            cb = QCheckBox()
            if ctest[0] in self.cardsFilters:
                cb.setChecked(True)
            label = QLabel(ctest[1])
            hbox.addWidget(cb)
            hbox.addWidget(label)
            ctest[2:3] = [cb]

        btnBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        handbox.addWidget(btnBox)
        btnBox.accepted.connect(detailDialog.accept)
        btnBox.rejected.connect(detailDialog.reject)

        if detailDialog.exec():
            self.detailFilters = []
            for ht in self.handtests:
                if ht[4].isChecked():
                    self.detailFilters.append((ht[0], ht[5].value(), ht[6].value()))
                ht[2], ht[3] = ht[5].value(), ht[6].value()
            self.cardsFilters = []
            for ct in self.cardstests:
                if ct[2].isChecked():
                    self.cardsFilters.append(ct[0])
            self.refreshStats(None)
