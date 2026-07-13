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
from decimal import Decimal
from functools import partial
from io import StringIO
from typing import Any

from PySide6.QtCore import QCoreApplication, QSortFilterProxyModel, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPixmap, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableView,
    QVBoxLayout,
)

from fpdb_3_legacy import SQL, Card, Configuration, Database, Deck, Filters, GuiReplayer, Hand
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("gui_hand_viewer")


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

        scroll = QScrollArea()
        scroll.setObjectName("filterSidebar")
        scroll.setWidget(self.filters)
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
        _flag_tips = {
            "AI": "went all-in",
            "SD": "saw showdown",
            "RIT": "run it twice/three",
            "CO$": "EV cashout",
        }
        for cb in (self.flagAllIn, self.flagShowdown, self.flagRunItTwice, self.flagCashout):
            cb.setToolTip(_("Filter: ") + _flag_tips[cb.text()])
            cb.stateChanged.connect(lambda _state: self.loadHands(None))
            self.pagerBox.addWidget(cb)
        self.handsVBox.addLayout(self.pagerBox)
        self._update_pager()

        self.view.resizeColumnsToContents()
        self.view.setSortingEnabled(True)

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
            extra.append("h.runItTwice = 1")
        if getattr(self, "flagAllIn", None) and self.flagAllIn.isChecked():
            extra.append("hp.wentAllIn = 1")
        if getattr(self, "flagShowdown", None) and self.flagShowdown.isChecked():
            extra.append("hp.sawShowdown = 1")
        if getattr(self, "flagCashout", None) and self.flagCashout.isChecked():
            extra.append("EXISTS (SELECT 1 FROM HandsCashout hco WHERE hco.handId = h.id)")
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
        c.execute(q)
        result = [r[0] for r in c.fetchall()]
        log.info("Load Hands matched %d hand(s) for dates %s..%s", len(result), start, end)
        return result

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
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle(_("FPDB 3 info"))
            msg.setText(_("No data found for the selected filters."))
            msg.exec()
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

        sym = getattr(hand, "sym", "") or ""
        won = hand.collectees.get(hero, 0)
        if not hasattr(hand, "net_collected") or not hand.net_collected:
            hand.calculate_net_collected()
        bet = 0
        if hero in hand.pot.committed:
            bet = hand.pot.committed[hero] - hand.pot.returned.get(hero, Decimal("0"))
        net = hand.net_collected.get(hero, 0)
        pos = hand.get_player_position(hero)
        nbplayers = len(hand.players)
        totalpot = hand.totalpot
        rake = hand.rake if hand.rake is not None else Decimal("0.00")
        sitehandid = hand.handid
        base = hand.gametype["base"]
        category = hand.gametype.get("category", "")

        # Hero cards, board run(s) and per-street action depend on the game base.
        board_runs = []
        if base == "hold":
            holestr = hand.join_holecards(hero)
            single = (
                list(hand.board.get("FLOP", []))
                + list(hand.board.get("TURN", []))
                + list(hand.board.get("RIVER", []))
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
            pre_actions = hand.get_actions_short(hero, "PREFLOP")
            post_actions = "" if "F" in pre_actions else hand.get_actions_short_streets(hero, "FLOP", "TURN", "RIVER")
        elif base == "stud":
            holestr = " ".join(hand.holecards["THIRD"][hero][0]) + " " + " ".join(hand.holecards["THIRD"][hero][1])
            later = []
            for s in ("FOURTH", "FIFTH", "SIXTH", "SEVENTH"):
                later.extend(hand.holecards[s][hero][0])
            board_runs = [later] if later else []
            pre_actions = hand.get_actions_short(hero, "THIRD")
            post_actions = (
                "" if "F" in pre_actions else hand.get_actions_short_streets(hero, "FOURTH", "FIFTH", "SIXTH", "SEVENTH")
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
            "Won": f"{won:.2f}",
            "Bet": f"{bet:.2f}",
            "Net": f"{net:.2f}",
            "Game": self._format_game(hand),
            "HandId": str(handid),
            "Total Pot": f"{totalpot:.2f}",
            "Rake": f"{rake:.2f}",
            "SiteHandNo": str(sitehandid),
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
            if name in ("Won", "Net"):
                try:
                    v = float(values[name])
                    item.setData(f"{sym}{v:.2f}", Qt.ItemDataRole.DisplayRole)
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
    _POSITION_NAMES = {"S": "SB", "B": "BB", "0": "BTN", "1": "CO", "2": "HJ", "3": "LJ", "4": "MP", "5": "MP", "6": "UTG", "7": "UTG"}

    def _format_game(self, hand) -> str:
        cat = hand.gametype.get("category", "")
        lim = hand.gametype.get("limitType", "")
        return f"{self._LIMIT_NAMES.get(lim, str(lim).upper())}{self._GAME_NAMES.get(cat, cat)}"

    def _format_position(self, pos) -> str:
        return self._POSITION_NAMES.get(str(pos), str(pos))

    def _format_datetime(self, hand) -> str:
        st = getattr(hand, "startTime", None)
        if not st:
            return ""
        try:
            return st.strftime("%Y-%m-%d %H:%M")
        except (AttributeError, ValueError):
            return str(st)

    def _hand_flags(self, hand) -> str:
        flags = []
        try:
            rit = int(hand.runItTimes)
        except (TypeError, ValueError):
            rit = 0
        if rit >= 2:
            flags.append(f"RIT×{rit}")
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
        sym = getattr(hand, "sym", "") or ""
        try:
            lines.append(f"Won {sym}{float(won):.2f}  ·  Net {sym}{float(net):.2f}")
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

            self.replayer = GuiReplayer.GuiReplayer(
                self.config,
                self.sql,
                self.main_window,
                handlist,
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
