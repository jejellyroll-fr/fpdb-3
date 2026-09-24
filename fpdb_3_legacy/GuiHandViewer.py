#!/usr/bin/env python
from __future__ import annotations

# Copyright 2010-2011 Maxime Grandchamp
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
# In the "official" distribution you can find the license in agpl-3.0.txt.
#
# This code once was in GuiReplayer.py and was split up in this and the former by zarturo.
# import L10n
# _ = L10n.get_translation()
import contextlib
from decimal import Decimal
from functools import partial
from io import StringIO
from typing import Any

from PySide6.QtCore import QCoreApplication, QSortFilterProxyModel, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDoubleValidator,
    QIntValidator,
    QPainter,
    QPixmap,
    QStandardItem,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import SQL, Card, Configuration, Database, Deck, Filters, GuiReplayer, Hand, gui_empty_state
from fpdb_3_legacy.hand_viewer_filters import build_filter_clauses
from fpdb_3_legacy.holdem_classes import RANKS, grid_labels
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.localized_formats import format_currency, format_datetime, format_number
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("gui_hand_viewer")


class StartingHandPickerDialog(QDialog):
    """A multi-select 13x13 Hold'em class picker with common shortcuts."""

    def __init__(self, selected: set[str] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Starting-hand range"))
        self._buttons: dict[str, QPushButton] = {}
        self._selected = set(selected or ())
        layout = QVBoxLayout(self)
        shortcuts = QHBoxLayout()
        for label, predicate in (
            (_("Pairs"), lambda hand: len(hand) == 2),
            (_("Suited"), lambda hand: hand.endswith("s")),
            (_("Offsuit"), lambda hand: hand.endswith("o")),
            (_("Broadway"), lambda hand: hand[0] in "AKQJT" and hand[1] in "AKQJT"),
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, match=predicate: self._select_matching(match))
            shortcuts.addWidget(button)
        clear = QPushButton(_("Clear"))
        clear.clicked.connect(lambda: self._select_matching(lambda _hand: False))
        shortcuts.addWidget(clear)
        invert = QPushButton(_("Invert"))
        invert.clicked.connect(self._invert)
        shortcuts.addWidget(invert)
        layout.addLayout(shortcuts)

        grid = QGridLayout()
        grid.setSpacing(2)
        grid.addWidget(QLabel(""), 0, 0)
        for column, rank in enumerate(RANKS, start=1):
            grid.addWidget(QLabel(rank), 0, column)
            grid.addWidget(QLabel(rank), column, 0)
        for row, hand_labels in enumerate(grid_labels(), start=1):
            for column, hand in enumerate(hand_labels, start=1):
                button = QPushButton(hand)
                button.setCheckable(True)
                button.setChecked(hand in self._selected)
                button.setFixedSize(42, 28)
                button.toggled.connect(lambda checked, value=hand: self._set_selected(value, checked))
                self._buttons[hand] = button
                grid.addWidget(button, row, column)
        layout.addLayout(grid)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        controls.accepted.connect(self.accept)
        controls.rejected.connect(self.reject)
        layout.addWidget(controls)

    def _set_selected(self, hand: str, selected: bool) -> None:
        if selected:
            self._selected.add(hand)
        else:
            self._selected.discard(hand)

    def _select_matching(self, predicate) -> None:
        self._selected = {hand for hand in self._buttons if predicate(hand)}
        for hand, button in self._buttons.items():
            button.setChecked(hand in self._selected)

    def _invert(self) -> None:
        self._select_matching(lambda hand: hand not in self._selected)

    def selected_hands(self) -> set[str]:
        return set(self._selected)


class GuiHandViewer(QSplitter):
    def __init__(self, config, querylist, mainwin) -> None:
        QSplitter.__init__(self, mainwin)
        self.config = config
        self.main_window = mainwin
        self.sql = querylist
        self.replayer: Any = None

        self.db = Database.Database(self.config, sql=self.sql)

        filters_display = {
            "Heroes": True,
            "Sites": True,
            "Games": True,
            "Currencies": False,
            "Limits": True,
            "LimitSep": True,
            "LimitType": True,
            "Positions": True,
            "Type": True,
            "UseType": "ring",
            "Seats": False,
            "SeatSep": False,
            "Dates": True,
            "Cards": False,
            "Groups": False,
            "GroupsAll": False,
            "Button1": True,
            "Button2": False,
        }

        self.filters = Filters.Filters(self.db, display=filters_display)
        self.filters.registerButton1Name("Load Hands")
        self.filters.registerButton1Callback(self.loadHands)
        self.filters.registerCardsCallback(self.filter_cards_cb)

        self._starting_hands: set[str] = set()
        self.filterPanel = QWidget()
        self.filterPanelLayout = QVBoxLayout(self.filterPanel)
        self.filterPanelLayout.setContentsMargins(0, 0, 0, 0)
        self.filterPanelLayout.addWidget(self.filters)
        self.advancedFilters = self._build_advanced_filters()
        self.filterPanelLayout.addWidget(self.advancedFilters)
        self.filterPanelLayout.addStretch(1)

        scroll = QScrollArea()
        scroll.setObjectName("filterSidebar")
        scroll.setWidget(self.filterPanel)
        # Without this the scroll area leaves the filter widget at a collapsed
        # height, squashing list-heavy frames (e.g. the CATEGORY checkboxes) to a
        # few pixels tall. Matches GuiTourneyPlayerStats.
        scroll.setWidgetResizable(True)

        self.handsFrame = QFrame()
        self.handsFrame.setObjectName("handsSurface")
        self.handsVBox = QVBoxLayout()
        self.handsFrame.setLayout(self.handsVBox)

        self.addWidget(scroll)
        self.addWidget(self.handsFrame)
        self.setStretchFactor(0, 0)
        self.setStretchFactor(1, 1)

        self.deck_instance = Deck.Deck(self.config, height=42, width=30)
        self.cardImages = self.init_card_images()

        # !Dict of colnames and their column idx in the model/ListStore
        self.colnum = {
            "Date": 0,
            "Flags": 1,
            "Stakes": 2,
            "Players": 3,
            "Pos": 4,
            "Street0": 5,
            "Action0": 6,
            "Street1-4": 7,
            "Action1-4": 8,
            "Combo": 9,
            "Won": 10,
            "Bet": 11,
            "Net": 12,
            "Game": 13,
            "HandId": 14,
            "Total Pot": 15,
            "Rake": 16,
            "SiteHandNo": 17,
            "Splash": 18,
        }
        self.view = QTableView()
        self.view.setSelectionBehavior(QTableView.SelectRows)
        self.handsVBox.addWidget(self.view)
        self.model = QStandardItemModel(0, len(self.colnum), self.view)
        self.filterModel = QSortFilterProxyModel()
        self.filterModel.setSourceModel(self.model)
        self.filterModel.setSortRole(Qt.ItemDataRole.UserRole)

        self.view.setModel(self.filterModel)
        self.view.verticalHeader().hide()
        self.model.setHorizontalHeaderLabels(
            [
                "Date",
                "Flags",
                "Stakes",
                "Nb Players",
                "Position",
                "Hands",
                "Preflop Action",
                "Board",
                "Postflop Action",
                "Made hand",
                "Won",
                "Bet",
                "Net",
                "Game",
                "HandId",
                "Total Pot",
                "Rake",
                "SiteHandId",
                "Splash",
            ],
        )

        self.view.doubleClicked.connect(self.row_activated)
        setattr(self.view, "contextMenuEvent", self.contextMenu)

        def resize_rows(_index, start, end) -> None:
            for row in range(start, end + 1):
                self.view.resizeRowToContents(row)

        self.filterModel.rowsInserted.connect(
            resize_rows,
        )
        setattr(self.filterModel, "filterAcceptsRow", lambda row, sourceParent: self.is_row_in_card_filter(row))

        # Pagination state: the full list of hand ids is kept and only one page
        # is reconstructed/rendered at a time (each hand is rebuilt from the DB,
        # which is expensive on large databases such as GGPoker).
        self.all_handids: list[Any] = []
        self.page = 0
        self.page_size = 100

        self.pagerBox = QHBoxLayout()
        self.prevPageButton = QPushButton(_("◀ Prev"))
        self.nextPageButton = QPushButton(_("Next ▶"))
        self.pageLabel = QLabel("")
        self.prevPageButton.clicked.connect(self.prev_page)
        self.nextPageButton.clicked.connect(self.next_page)
        self.pagerBox.addWidget(self.prevPageButton)
        self.pagerBox.addWidget(self.nextPageButton)
        self.pagerBox.addWidget(self.pageLabel)
        self.pagerBox.addStretch(1)
        # Flag filters (applied at the SQL level on the next Load Hands).
        self.flagAllIn = QCheckBox("AI")
        self.flagShowdown = QCheckBox("SD")
        self.flagRunItTwice = QCheckBox("RIT")
        self.flagCashout = QCheckBox("CO$")
        self.flagBombPot = QCheckBox("Bomb")
        self.flagDoubleBoard = QCheckBox("2xB")
        _flag_tips = {
            "AI": "went all-in",
            "SD": "saw showdown",
            "RIT": "run it twice/three",
            "CO$": "EV cashout",
            "Bomb": "bomb pot",
            "2xB": "double board",
        }
        for cb in (
            self.flagAllIn,
            self.flagShowdown,
            self.flagRunItTwice,
            self.flagCashout,
            self.flagBombPot,
            self.flagDoubleBoard,
        ):
            cb.setToolTip(_("Filter: ") + _flag_tips[cb.text()])
            cb.stateChanged.connect(lambda _state: self.loadHands(None))
            self.pagerBox.addWidget(cb)
        self.flagSplashPot = QComboBox()
        self.flagSplashPot.addItem(_("All hands"), "all")
        self.flagSplashPot.addItem(_("Splash pots only"), "only")
        self.flagSplashPot.addItem(_("Exclude splash pots"), "exclude")
        self.flagSplashPot.setToolTip(_("Filter: splash pot"))
        self.flagSplashPot.currentIndexChanged.connect(lambda _index: self.loadHands(None))
        self.pagerBox.addWidget(self.flagSplashPot)
        self.handsVBox.addLayout(self.pagerBox)
        self._update_pager()

        self.view.resizeColumnsToContents()
        self.view.setSortingEnabled(True)

    def _build_advanced_filters(self) -> QGroupBox:
        group = QGroupBox(_("Advanced review filters"))
        grid = QGridLayout(group)
        self.startingHandButton = QPushButton(_("Choose hands…"))
        self.startingHandSummary = QLabel(_("All starting hands"))
        self.startingHandButton.clicked.connect(self._choose_starting_hands)
        grid.addWidget(QLabel(_("Hold'em starting hand")), 0, 0)
        grid.addWidget(self.startingHandButton, 0, 1)
        grid.addWidget(self.startingHandSummary, 0, 2)

        self.exactCard1 = QComboBox()
        self.exactCard2 = QComboBox()
        cards = [f"{rank}{suit}" for rank in "AKQJT98765432" for suit in "shdc"]
        for selector in (self.exactCard1, self.exactCard2):
            selector.addItem(_("Any card"), None)
            for card in cards:
                selector.addItem(card, card)
        grid.addWidget(QLabel(_("Exact known cards")), 1, 0)
        exact_layout = QHBoxLayout()
        exact_layout.addWidget(self.exactCard1)
        exact_layout.addWidget(self.exactCard2)
        grid.addLayout(exact_layout, 1, 1, 1, 2)

        self.preflopFilter = QComboBox()
        for label, value in (
            (_("Any"), ""),
            (_("VPIP"), "vpip"),
            (_("Did not VPIP"), "not_vpip"),
            (_("RFI"), "rfi"),
            (_("Limp"), "limp"),
            (_("Call open"), "call_open"),
            (_("3-bet"), "three_bet"),
            (_("4-bet"), "four_bet"),
            (_("Squeeze"), "squeeze"),
            (_("Faced open"), "faced_open"),
            (_("Faced 3-bet"), "faced_three_bet"),
            (_("Went all-in"), "all_in"),
        ):
            self.preflopFilter.addItem(label, value)
        grid.addWidget(QLabel(_("Preflop")), 2, 0)
        grid.addWidget(self.preflopFilter, 2, 1, 1, 2)

        self.postflopFilter = QComboBox()
        for label, value in (
            (_("Any"), ""),
            (_("Saw flop"), "saw_flop"),
            (_("Saw turn"), "saw_turn"),
            (_("Saw river"), "saw_river"),
            (_("Bet"), "bet"),
            (_("Called"), "call"),
            (_("Raised"), "raise"),
            (_("Checked"), "check"),
            (_("Folded"), "fold"),
            (_("Continuation bet"), "cbet"),
            (_("Faced c-bet"), "faced_cbet"),
            (_("Check-raise"), "check_raise"),
            (_("Showdown"), "showdown"),
        ):
            self.postflopFilter.addItem(label, value)
        grid.addWidget(QLabel(_("Postflop")), 3, 0)
        grid.addWidget(self.postflopFilter, 3, 1, 1, 2)

        self.potMinBB = QLineEdit()
        self.potMinBB.setPlaceholderText(_("min BB"))
        self.potMaxBB = QLineEdit()
        self.potMaxBB.setPlaceholderText(_("max BB"))
        self.netMinBB = QLineEdit()
        self.netMinBB.setPlaceholderText(_("min BB"))
        self.netMaxBB = QLineEdit()
        self.netMaxBB.setPlaceholderText(_("max BB"))
        self.stackMinBB = QLineEdit()
        self.stackMinBB.setPlaceholderText(_("min BB"))
        self.stackMaxBB = QLineEdit()
        self.stackMaxBB.setPlaceholderText(_("max BB"))
        self.playersMin = QLineEdit()
        self.playersMin.setPlaceholderText(_("min"))
        self.playersMax = QLineEdit()
        self.playersMax.setPlaceholderText(_("max"))
        for widget in (
            self.potMinBB,
            self.potMaxBB,
            self.netMinBB,
            self.netMaxBB,
            self.stackMinBB,
            self.stackMaxBB,
        ):
            widget.setValidator(QDoubleValidator(-1_000_000, 1_000_000, 4, widget))
        for widget in (self.playersMin, self.playersMax):
            widget.setValidator(QIntValidator(0, 100, widget))
        for row, label, low, high in (
            (4, _("Final pot (BB)"), self.potMinBB, self.potMaxBB),
            (5, _("Net result (BB)"), self.netMinBB, self.netMaxBB),
            (6, _("Effective stack (BB)"), self.stackMinBB, self.stackMaxBB),
            (7, _("Players in hand"), self.playersMin, self.playersMax),
        ):
            bounds = QHBoxLayout()
            bounds.addWidget(low)
            bounds.addWidget(high)
            grid.addWidget(QLabel(label), row, 0)
            grid.addLayout(bounds, row, 1, 1, 2)

        self.sizingBucketFilter = QComboBox()
        self.sizingBucketFilter.addItem(_("Any sizing"), "")
        for label, value in (
            (_("Under 25% pot"), "under_25"),
            (_("25–50% pot"), "25_50"),
            (_("50–75% pot"), "50_75"),
            (_("75–100% pot"), "75_100"),
            (_("100–150% pot"), "100_150"),
            (_("Over 150% pot"), "over_150"),
        ):
            self.sizingBucketFilter.addItem(label, value)
        grid.addWidget(QLabel(_("Bet / raise sizing")), 8, 0)
        grid.addWidget(self.sizingBucketFilter, 8, 1, 1, 2)

        self.applyAdvancedFilters = QPushButton(_("Apply review filters"))
        self.applyAdvancedFilters.clicked.connect(lambda: self.loadHands(None))
        grid.addWidget(self.applyAdvancedFilters, 9, 0, 1, 3)
        return group

    def _choose_starting_hands(self) -> None:
        dialog = StartingHandPickerDialog(self._starting_hands, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._starting_hands = dialog.selected_hands()
            count = len(self._starting_hands)
            self.startingHandSummary.setText(
                _("All starting hands") if not count else _("{} classes selected").format(count)
            )

    @staticmethod
    def _optional_number(widget, cast):
        text = widget.text().strip()
        if not text:
            return None
        if cast is float:
            text = text.replace(",", ".")
        return cast(text)

    def _advanced_filter_values(self) -> dict[str, Any]:
        values = {
            "starting_hands": sorted(self._starting_hands),
            "exact_card_1": self.exactCard1.currentData(),
            "exact_card_2": self.exactCard2.currentData(),
            "preflop": self.preflopFilter.currentData(),
            "postflop": self.postflopFilter.currentData(),
            "pot_min_bb": self._optional_number(self.potMinBB, float),
            "pot_max_bb": self._optional_number(self.potMaxBB, float),
            "net_min_bb": self._optional_number(self.netMinBB, float),
            "net_max_bb": self._optional_number(self.netMaxBB, float),
            "stack_min_bb": self._optional_number(self.stackMinBB, float),
            "stack_max_bb": self._optional_number(self.stackMaxBB, float),
            "sizing_bucket": self.sizingBucketFilter.currentData(),
            "players_min": self._optional_number(self.playersMin, int),
            "players_max": self._optional_number(self.playersMax, int),
        }
        for minimum, maximum, label in (
            ("pot_min_bb", "pot_max_bb", "final pot"),
            ("net_min_bb", "net_max_bb", "net result"),
            ("stack_min_bb", "stack_max_bb", "effective stack"),
            ("players_min", "players_max", "players in hand"),
        ):
            low, high = values[minimum], values[maximum]
            if low is not None and high is not None and low > high:
                raise ValueError(_("The minimum cannot exceed the maximum for {}.").format(label))
        return values

    def close_owned_database(self) -> None:
        """Release the connection created for this tab."""
        with contextlib.suppress(Exception):
            if self.replayer is not None:
                self.replayer.close()
                self.replayer = None
        with contextlib.suppress(Exception):
            self.db.disconnect()

    def init_card_images(self):
        suits = ("s", "h", "d", "c")
        ranks = (14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2)

        card_images = [0] * 53
        for j in range(13):
            for i in range(4):
                loc = Card.cardFromValueSuit(ranks[j], suits[i])
                card_image = self.deck_instance.card(suits[i], ranks[j])
                card_images[loc] = card_image
        back_image = self.deck_instance.back()
        card_images[0] = back_image
        return card_images

    def loadHands(self, checkState) -> None:
        hand_ids = self.get_hand_ids_from_date_range(
            self.filters.getDates()[0],
            self.filters.getDates()[1],
        )
        # ! print(hand_ids)
        self.reload_hands(hand_ids)

    def get_hand_ids_from_date_range(self, start, end):
        q = self.db.sql.query["handsInRangeSessionFilter"]
        q = q.replace("<datetest>", "between '" + start + "' and '" + end + "'")

        # Apply filters
        q = self.filters.replace_placeholders_with_filter_values(q)

        # Flag filters (AI / SD / RIT) appended as extra WHERE conditions.
        extra = []
        if getattr(self, "flagRunItTwice", None) and self.flagRunItTwice.isChecked():
            # RIT only: a bomb-pot double board also stores multiple boards but is
            # not "run it twice", so exclude it here.
            extra.append("h.runItTwice = 1 AND h.bombPot = 0")
        if getattr(self, "flagAllIn", None) and self.flagAllIn.isChecked():
            extra.append("hp.wentAllIn = 1")
        if getattr(self, "flagShowdown", None) and self.flagShowdown.isChecked():
            extra.append("hp.sawShowdown = 1")
        if getattr(self, "flagCashout", None) and self.flagCashout.isChecked():
            extra.append("EXISTS (SELECT 1 FROM HandsCashout hco WHERE hco.handId = h.id)")
        if getattr(self, "flagBombPot", None) and self.flagBombPot.isChecked():
            extra.append("h.bombPot > 0")
        if getattr(self, "flagDoubleBoard", None) and self.flagDoubleBoard.isChecked():
            # In FPDB a true double-board hand is a bomb pot with two stored
            # boards. A shared-flop run-it-twice also has two Boards rows, but
            # is deliberately excluded from this filter.
            extra.append("h.bombPot > 0 AND (SELECT COUNT(*) FROM Boards b WHERE b.handId = h.id) >= 2")
        splash_condition = self._splash_filter_condition()
        if splash_condition:
            extra.append(splash_condition)
        placeholder = getattr(self.db.sql, "query", {}).get("placeholder", "%s")
        try:
            advanced_values = self._advanced_filter_values() if hasattr(self, "_advanced_filter_values") else {}
        except ValueError as exc:
            QMessageBox.warning(self, _("Invalid review filter"), str(exc))
            return []
        advanced, advanced_params = build_filter_clauses(advanced_values, placeholder)
        extra.extend(advanced)
        if extra:
            q = q + " AND " + " AND ".join(extra)

        # Diagnostic: log the fully-assembled query and the active filter state so
        # missing-hands issues (e.g. a category excluded by date/game/limit/position)
        # can be traced. Enable DEBUG logging for "gui_hand_viewer" to see it.
        log.debug("Load Hands SQL:\n%s", q)
        log.debug(
            "Load Hands filters | dates=%s..%s games=%s limits=%s positions=%s",
            start,
            end,
            sorted(self.filters.getGames()) if hasattr(self.filters, "getGames") else "?",
            self.filters.getLimits() if hasattr(self.filters, "getLimits") else "?",
            self.filters.getPositions() if hasattr(self.filters, "getPositions") else "?",
        )

        c = self.db.get_cursor()
        if advanced_params:
            c.execute(q, advanced_params)
        else:
            c.execute(q)
        result = [r[0] for r in c.fetchall()]
        log.info("Load Hands matched %d hand(s) for dates %s..%s", len(result), start, end)
        return result

    def _splash_filter_condition(self) -> str | None:
        """Return the SQL condition for the selected splash-pot mode."""
        mode = "all"
        selector = getattr(self, "flagSplashPot", None)
        if selector is not None and hasattr(selector, "currentData"):
            mode = selector.currentData() or "all"
        return {
            "only": "h.splashPot > 0",
            "exclude": "(h.splashPot = 0 OR h.splashPot IS NULL)",
        }.get(mode)

    def rankedhand(self, hand, game):
        ranks = {
            "0": 0,
            "2": 2,
            "3": 3,
            "4": 4,
            "5": 5,
            "6": 6,
            "7": 7,
            "8": 8,
            "9": 9,
            "T": 10,
            "J": 11,
            "Q": 12,
            "K": 13,
            "A": 14,
        }
        suits = {"x": 0, "s": 1, "c": 2, "d": 3, "h": 4}

        if game == "holdem":
            card1 = ranks[hand[0]]
            card2 = ranks[hand[3]]
            suit1 = suits[hand[1]]
            suit2 = suits[hand[4]]
            if card1 < card2:
                (card1, card2) = (card2, card1)
                (suit1, suit2) = (suit2, suit1)
            if suit1 == suit2:
                suit1 += 4
            return card1 * 14 * 14 + card2 * 14 + suit1
        return 0

    def reload_hands(self, handids) -> None:
        self.hands: dict[Any, Any] = {}
        self.all_handids = list(handids)
        self.page = 0
        self.model.removeRows(0, self.model.rowCount())
        if len(self.all_handids) == 0:
            self._update_pager()
            gui_empty_state.show_no_data(self, context="Hand viewer", db=self.db)
            return
        self.render_page()

    def page_count(self) -> int:
        if not self.all_handids:
            return 1
        return (len(self.all_handids) + self.page_size - 1) // self.page_size

    def render_page(self) -> None:
        """Reconstruct and display only the current page of hands."""
        self.model.removeRows(0, self.model.rowCount())
        start = self.page * self.page_size
        page_ids = self.all_handids[start : start + self.page_size]
        progress = QProgressDialog("Loading hands", "Abort", 0, len(page_ids), self)
        progress.setValue(0)
        progress.show()
        try:
            for idx, handid in enumerate(page_ids):
                if progress.wasCanceled():
                    break
                try:
                    if handid not in self.hands:
                        self.hands[handid] = self.importhand(handid)
                    self.addHandRow(handid, self.hands[handid])
                except Exception as e:  # noqa: BLE001 - skip a bad hand, keep loading the rest.
                    log.exception(f"Skipping hand {handid}: {e}")
                    self.hands.pop(handid, None)
                progress.setValue(idx + 1)
                if idx % 25 == 0:
                    QCoreApplication.processEvents()
        finally:
            progress.close()
        self.view.resizeColumnsToContents()
        self._update_pager()

    def _update_pager(self) -> None:
        total = len(self.all_handids)
        pages = self.page_count()
        self.pageLabel.setText(f"Page {self.page + 1}/{pages}  ·  {total} hands")
        self.prevPageButton.setEnabled(self.page > 0)
        self.nextPageButton.setEnabled(self.page < pages - 1)

    def prev_page(self) -> None:
        if self.page > 0:
            self.page -= 1
            self.render_page()

    def next_page(self) -> None:
        if self.page < self.page_count() - 1:
            self.page += 1
            self.render_page()

    def addHandRow(self, handid, hand) -> None:
        hero = hand.hero or self.filters.get_hero_for_site(hand.sitename, hand)
        if not hero:
            log.warning(f"Hero not found for site: {hand.sitename}")
            return

        won = hand.collectees.get(hero, 0)
        if not hasattr(hand, "net_collected") or not hand.net_collected:
            hand.calculate_net_collected()
        bet = 0
        if hero in hand.pot.committed:
            # Pot.removeMoney already removes uncalled bets from committed.
            bet = hand.pot.committed[hero]
        net = hand.net_collected.get(hero, 0)
        pos = hand.get_player_position(hero)
        nbplayers = len(hand.players)
        totalpot = hand.totalpot
        rake = hand.rake if hand.rake is not None else Decimal("0.00")
        sitehandid = hand.handid
        currency = str(hand.gametype.get("currency", "USD"))
        splash = getattr(hand, "splashPot", 0) or 0
        splash_won = (getattr(hand, "splashWinnings", {}) or {}).get(hero, 0) or 0
        base = hand.gametype["base"]
        category = hand.gametype.get("category", "")

        # Hero cards, board run(s) and per-street action depend on the game base.
        board_runs = []
        if base == "hold":
            holestr = hand.join_holecards(hero)
            single = (
                list(hand.board.get("FLOP", [])) + list(hand.board.get("TURN", [])) + list(hand.board.get("RIVER", []))
            )
            runs = []
            for run in (1, 2, 3):
                rc = (
                    list(hand.board.get(f"FLOP{run}", []))
                    + list(hand.board.get(f"TURN{run}", []))
                    + list(hand.board.get(f"RIVER{run}", []))
                )
                if rc:
                    runs.append(rc)
            board_runs = runs if runs else ([single] if single else [])
            # The street the first decision is taken on, which is not preflop
            # in every game: All-in or Fold deals the flop first and has no
            # preflop at all, so its whole first round belongs in this column.
            first_street = hand.actionStreets[1] if len(hand.actionStreets) > 1 else "PREFLOP"
            pre_actions = hand.get_actions_short(hero, first_street)
            later_streets = [s for s in ("FLOP", "TURN", "RIVER") if s != first_street]
            post_actions = "" if "F" in pre_actions else hand.get_actions_short_streets(hero, *later_streets)
        elif base == "stud":
            holestr = " ".join(hand.holecards["THIRD"][hero][0]) + " " + " ".join(hand.holecards["THIRD"][hero][1])
            later = []
            for s in ("FOURTH", "FIFTH", "SIXTH", "SEVENTH"):
                later.extend(hand.holecards[s][hero][0])
            board_runs = [later] if later else []
            pre_actions = hand.get_actions_short(hero, "THIRD")
            post_actions = (
                ""
                if "F" in pre_actions
                else hand.get_actions_short_streets(hero, "FOURTH", "FIFTH", "SIXTH", "SEVENTH")
            )
        else:  # draw
            holestr = hand.join_holecards(hero, street="DEAL")
            pre_actions = hand.get_actions_short(hero, "DEAL")
            post_actions = ""

        combo = (getattr(hand, "showdownStrings", {}) or {}).get(hero, "") or ""

        values = {
            "Date": self._format_datetime(hand),
            "Flags": self._hand_flags(hand),
            "Stakes": hand.getStakesAsString(),
            "Players": str(nbplayers),
            "Pos": self._format_position(pos),
            "Street0": holestr,
            "Action0": pre_actions,
            "Street1-4": "",
            "Action1-4": post_actions,
            "Combo": combo,
            "Won": format_number(won),
            "Bet": format_number(bet),
            "Net": format_number(net),
            "Game": self._format_game(hand),
            "HandId": str(handid),
            "Total Pot": format_number(totalpot),
            "Rake": format_number(rake),
            "SiteHandNo": str(sitehandid),
            "Splash": self._format_splash(splash, splash_won, currency),
        }

        ordered = sorted(self.colnum.items(), key=lambda kv: kv[1])
        modelrow = [QStandardItem(str(values.get(name, ""))) for name, _idx in ordered]

        try:
            net_f = float(net)
        except (TypeError, ValueError):
            net_f = 0.0
        win_color, lose_color, neutral = QColor("#3fb56b"), QColor("#d66b6b"), QColor("#c4cdd4")

        for name, idx in ordered:
            item = modelrow[idx]
            item.setEditable(False)
            if name == "Street0":
                item.setData(self.render_cards(holestr), Qt.ItemDataRole.DecorationRole)
                item.setData("", Qt.ItemDataRole.DisplayRole)
                item.setData(holestr, Qt.ItemDataRole.UserRole + 1)
            elif name == "Street1-4":
                flat = " ".join(c for run in board_runs for c in run)
                item.setData(self.render_boards(board_runs), Qt.ItemDataRole.DecorationRole)
                item.setData("", Qt.ItemDataRole.DisplayRole)
                item.setData(flat, Qt.ItemDataRole.UserRole + 1)
            elif name in ("Bet", "Net", "Won", "Total Pot", "Rake"):
                try:
                    item.setData(float(values[name]), Qt.ItemDataRole.UserRole)
                except (TypeError, ValueError):
                    pass
            elif name == "Splash":
                try:
                    item.setData(float(Decimal(str(splash)) / 100), Qt.ItemDataRole.UserRole)
                except (TypeError, ValueError, ArithmeticError):
                    pass
            if name in ("Won", "Net"):
                try:
                    v = float(values[name])
                    currency = str(hand.gametype.get("currency", "USD"))
                    item.setData(format_currency(v, currency), Qt.ItemDataRole.DisplayRole)
                    item.setForeground(QBrush(win_color if v > 0 else lose_color if v < 0 else neutral))
                except (TypeError, ValueError):
                    pass
            elif name == "Flags":
                item.setForeground(QBrush(QColor("#ffd34d")))
            elif name == "Game":
                # Keep the raw category for the card filter / sorting.
                item.setData(category, Qt.ItemDataRole.UserRole)

        # Subtle row tint by result.
        if net_f > 0:
            tint = QColor(40, 90, 60, 60)
        elif net_f < 0:
            tint = QColor(90, 45, 45, 60)
        else:
            tint = None
        tip = self._hand_tooltip(hand, hero, won, net)
        for item in modelrow:
            if tint is not None:
                item.setBackground(QBrush(tint))
            item.setToolTip(tip)

        self.model.appendRow(modelrow)

    _GAME_NAMES = {
        "holdem": "HE",
        "6_holdem": "6HE",
        "omahahi": "O",
        "omahahilo": "O8",
        "5_omahahi": "5O",
        "5_omaha8": "5O8",
        "6_omahahi": "6O",
        "cour_hi": "C",
        "cour_hilo": "C8",
        "razz": "Razz",
        "studhi": "Stud",
        "studhilo": "Stud8",
        "27_1draw": "27SD",
        "27_3draw": "27TD",
        "a5_3draw": "A5TD",
        "badugi": "Badugi",
        "fusion": "Fusion",
    }
    _LIMIT_NAMES = {"nl": "NL", "pl": "PL", "fl": "FL", "cn": "CN", "cp": "CP"}
    _POSITION_NAMES = {
        "S": "SB",
        "B": "BB",
        "0": "BTN",
        "1": "CO",
        "2": "HJ",
        "3": "LJ",
        "4": "MP",
        "5": "MP",
        "6": "UTG",
        "7": "UTG",
        "8": "Other",
        "9": "Unknown",
    }

    def _format_game(self, hand) -> str:
        cat = hand.gametype.get("category", "")
        lim = hand.gametype.get("limitType", "")
        return f"{self._LIMIT_NAMES.get(lim, str(lim).upper())}{self._GAME_NAMES.get(cat, cat)}"

    def _format_position(self, pos) -> str:
        return self._POSITION_NAMES.get(str(pos), str(pos))

    @staticmethod
    def _format_splash(splash, splash_won, currency: str) -> str:
        """Format the room drop and, when present, the hero's collected share."""
        try:
            drop_text = format_currency(Decimal(str(splash)) / 100, currency)
            if splash_won:
                won_text = format_currency(splash_won, currency)
                return f"{drop_text} ({won_text} won)"
            return drop_text
        except (TypeError, ValueError, ArithmeticError):
            return ""

    def _format_datetime(self, hand) -> str:
        st = getattr(hand, "startTime", None)
        if not st:
            return ""
        try:
            return format_datetime(st)
        except (AttributeError, TypeError, ValueError):
            return str(st)

    def _hand_flags(self, hand) -> str:
        flags: list[str] = []
        try:
            rit = int(hand.runItTimes)
        except (TypeError, ValueError):
            rit = 0
        bomb_pot = bool(getattr(hand, "bombPot", 0))
        if rit >= 2 and bomb_pot:
            flags.extend(("BOMB", "2xB"))
        elif rit >= 2:
            flags.append(f"RIT×{rit}")
        elif bomb_pot:
            flags.append("BOMB")
        cashed = bool(getattr(hand, "cashedOut", False))
        allin = False
        for acts in hand.actions.values():
            for a in acts:
                if len(a) > 1 and a[1] == "cashout":
                    cashed = True
                if a and isinstance(a[-1], bool) and a[-1]:
                    allin = True
        if cashed:
            flags.append("CO$")
        if allin:
            flags.append("AI")
        if getattr(hand, "shown", None):
            flags.append("SD")
        return " ".join(flags)

    def render_boards(self, runs):
        """Render one or more run boards stacked vertically (run-it-twice/three)."""
        runs = [r for r in runs if r] or [["0x"]]
        card_width, card_height, gap = 30, 42, 3
        max_cards = max(len(r) for r in runs)
        width = card_width * max_cards
        height = card_height * len(runs) + gap * (len(runs) - 1)
        pixbuf = QPixmap(width, height)
        pixbuf.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixbuf)
        y = 0
        for run in runs:
            x = 0
            for c in run:
                painter.drawPixmap(x, y, self.cardImages[Card.encodeCard(c)])
                x += card_width
            y += card_height + gap
        painter.end()
        return pixbuf

    def _hand_tooltip(self, hand, hero, won, net) -> str:
        lines = [
            f"{hand.sitename} #{hand.handid}",
            f"{self._format_game(hand)} {hand.getStakesAsString()}",
        ]
        combo = (getattr(hand, "showdownStrings", {}) or {}).get(hero)
        if combo:
            lines.append(f"Hero: {combo}")
        currency = str(hand.gametype.get("currency", "USD"))
        try:
            lines.append(f"Won {format_currency(won, currency)}  ·  Net {format_currency(net, currency)}")
        except (TypeError, ValueError):
            pass
        return "\n".join(lines)

    def copyHandToClipboard(self, checkState, hand) -> None:
        handText = StringIO()
        hand.writeHand(handText)
        QApplication.clipboard().setText(handText.getvalue())

    def contextMenu(self, event) -> None:
        index = self.view.currentIndex()
        if index.row() < 0:
            return
        hand = self.hands[int(index.sibling(index.row(), self.colnum["HandId"]).data())]
        m = QMenu()
        copyAction = m.addAction(_("Copy to clipboard"))
        if copyAction is not None:
            copyAction.triggered.connect(partial(self.copyHandToClipboard, hand=hand))
        m.move(event.globalPosition().toPoint())
        m.exec()

    def filter_cards_cb(self, card) -> None:
        if hasattr(self, "hands"):
            self.filterModel.invalidateFilter()

    def is_row_in_card_filter(self, rownum):
        """Returns true if the cards of the given row are in the card filter."""
        # Does work but all cards that should NOT be displayed have to be clicked.
        card_filter = self.filters.getCards()

        # if the filter is not active, show all hands
        if not card_filter:
            return True

        hcs = self.model.data(
            self.model.index(rownum, self.colnum["Street0"]),
            Qt.ItemDataRole.UserRole + 1,
        ).split(" ")

        if "0x" in hcs:  # if cards are unknown return True
            return True

        gt = self.model.data(self.model.index(rownum, self.colnum["Game"]), Qt.ItemDataRole.UserRole)

        if gt not in ("holdem", "omahahi", "omahahilo"):
            return True

        # Holdem: Compare the real start cards to the selected filter (ie. AhKh = AKs)
        value1 = Card.card_map[hcs[0][0]]
        value2 = Card.card_map[hcs[1][0]]
        idx = Card.twoStartCards(value1, hcs[0][1], value2, hcs[1][1])
        abbr = Card.twoStartCardString(idx)

        # if the filter is active, only show hands that are in it.
        return card_filter.get(abbr, False)

    def row_activated(self, index) -> None:
        try:
            hand_id = int(index.sibling(index.row(), self.colnum["HandId"]).data())
            handlist = sorted(self.hands.keys())
            hand_index = handlist.index(hand_id)

            if getattr(self, "replayer", None) is not None and self.replayer.isVisible():
                self.replayer.handlist = handlist
                self.replayer.play_hand(hand_index)
                self.replayer.raise_()
                self.replayer.activateWindow()
                return

            self.replayer = GuiReplayer.GuiReplayer(
                self.config,
                self.sql,
                self.main_window,
                handlist,
                db=self.db,
            )
            self.replayer.play_hand(hand_index)
            self.replayer.raise_()
            self.replayer.activateWindow()
        except Exception as exc:
            log.exception("Unable to open hand replayer")
            QMessageBox.critical(self, "FPDB Replayer", f"Unable to open hand replayer:\n{exc}")

    def importhand(self, handid=1):
        h = Hand.hand_factory(handid, self.config, self.db)

        # Safely get the hero for this hand's sitename
        h.hero = self.filters.get_hero_for_site(h.sitename, h)
        if h.hero is None:
            log.warning(f"No hero found for site {h.sitename}")
        return h

    def render_cards(self, cardstring):
        card_width = 30
        card_height = 42
        if cardstring is None or cardstring == "":
            cardstring = "0x"
        cardstring = cardstring.replace("'", "")
        cardstring = cardstring.replace("[", "")
        cardstring = cardstring.replace("]", "")
        cardstring = cardstring.replace("'", "")
        cardstring = cardstring.replace(",", "")
        cards = [Card.encodeCard(c) for c in cardstring.split(" ")]
        n_cards = len(cards)

        pixbuf = QPixmap(card_width * n_cards, card_height)
        painter = QPainter(pixbuf)
        x = 0  # x coord where the next card starts in pixbuf
        for card in cards:
            painter.drawPixmap(x, 0, self.cardImages[card])
            x += card_width
        return pixbuf


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    # Launch the hand viewer GUI like the original
    config = Configuration.Config()

    settings = {}

    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())

    from PySide6.QtWidgets import QMainWindow

    app = QApplication([])
    sql = SQL.Sql(db_server=settings["db-server"])
    main_window = QMainWindow()
    i = GuiHandViewer(config, sql, main_window)
    main_window.setCentralWidget(i)
    main_window.show()
    main_window.resize(1400, 800)
    app.exec()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
