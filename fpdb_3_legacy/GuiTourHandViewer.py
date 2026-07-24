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
from functools import partial
from io import StringIO
from typing import Any

from PySide6.QtCore import QCoreApplication, QSortFilterProxyModel, Qt
from PySide6.QtGui import QPainter, QPixmap, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QScrollArea,
    QSplitter,
    QTableView,
    QVBoxLayout,
)

from fpdb_3_legacy import SQL, Card, Configuration, Database, Deck, Filters, GuiReplayer, Hand, gui_empty_state
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.localized_formats import format_number
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("gui_tour_hand_viewer")


class TourHandViewer(QSplitter):
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
            "Games": False,  # cash game
            "Tourney": True,
            "TourneyCat": True,
            "TourneyLim": True,
            "TourneyBuyin": True,
            "Currencies": True,
            "Limits": False,
            "LimitSep": True,
            "LimitType": True,
            "Type": True,
            "UseType": "tour",
            "Seats": False,
            "SeatSep": True,
            "Dates": True,
            "Groups": False,
            "Button1": True,
            "Button2": False,
        }

        self.filters = Filters.Filters(self.db, display=filters_display)
        self.filters.registerButton1Name(_("Load Hands"))
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
            "Stakes": 0,
            "Players": 1,
            "Pos": 2,
            "Street0": 3,
            "Action0": 4,
            "Street1-4": 5,
            "Action1-4": 6,
            "Won": 7,
            "Bet": 8,
            "Net": 9,
            "Game": 10,
            "HandId": 11,
            "Total Pot": 12,
            "Rake": 13,
            "SiteHandNo": 14,
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
                "Stakes",
                "Nb Players",
                "Position",
                "Hands",
                "Preflop Action",
                "Board",
                "Postflop Action",
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

        # debug
        # print("Filtered SQL query:", q)

        c = self.db.get_cursor()
        c.execute(q)
        return [r[0] for r in c.fetchall()]

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
        self.hands = {}
        self.model.removeRows(0, self.model.rowCount())
        if len(handids) == 0:
            gui_empty_state.show_no_data(
                self,
                context="Tournament hand viewer",
                db=self.db,
                tables=("Hands", "Tourneys"),
            )
            return
        progress = QProgressDialog("Loading hands", "Abort", 0, len(handids), self)
        progress.setValue(0)
        progress.show()
        try:
            for idx, handid in enumerate(handids):
                if progress.wasCanceled():
                    break
                self.hands[handid] = self.importhand(handid)
                self.addHandRow(handid, self.hands[handid])

                progress.setValue(idx + 1)
                if idx % 10 == 0:
                    QCoreApplication.processEvents()
                    self.view.resizeColumnsToContents()
        finally:
            progress.close()
        self.view.resizeColumnsToContents()

    def addHandRow(self, handid, hand) -> None:
        hero = hand.hero or self.filters.get_hero_for_site(hand.sitename, hand)
        if not hero:
            log.warning(f"Hero not found for site: {hand.sitename}")
            return

        log.debug(f"Processing hand: {handid} for hero: {hero}")
        log.debug(f"completed info from hand: {hand!s}")

        won = 0
        if hero in list(hand.collectees.keys()):
            won = hand.collectees[hero]
        log.debug(f"Hero winnings (won): {won}")

        bet = 0
        if hero in list(hand.pot.committed.keys()):
            bet = hand.pot.committed[hero]
        log.debug(f"Hero committed (bet): {bet}")

        net = won
        log.debug(f"Net calculated (won): {net}")

        pos = hand.get_player_position(hero)
        log.debug(f"Hero position: {pos}")

        nbplayers = len(hand.players)
        log.debug(f"Number of players in hand: {nbplayers}")

        totalpot = hand.totalpot
        log.debug(f"Total pot: {totalpot}")

        rake = (totalpot / nbplayers) - net
        log.debug(f"Rake: {rake}")

        sitehandid = hand.handid
        log.debug(f"Site hand ID: {sitehandid}")

        gt = hand.gametype["category"]
        log.debug(f"Game type: {gt}")

        row = []
        if hand.gametype["base"] == "hold":
            board = []
            board.extend(hand.board.get("FLOP", []))
            board.extend(hand.board.get("TURN", []))
            board.extend(hand.board.get("RIVER", []))
            log.debug(f"Board cards: {board}")

            pre_actions = hand.get_actions_short(hero, "PREFLOP")
            log.debug(f"Preflop actions for hero: {pre_actions}")

            post_actions = ""
            if "F" not in pre_actions:  # if player hasn't folded preflop
                post_actions = hand.get_actions_short_streets(
                    hero,
                    "FLOP",
                    "TURN",
                    "RIVER",
                )
            log.debug(f"Postflop actions for hero: {post_actions}")

            row = [
                hand.getStakesAsString(),
                str(nbplayers),
                pos,
                hand.join_holecards(hero),
                pre_actions,
                " ".join(board),
                post_actions,
                format_number(won),
                format_number(bet),
                format_number(net),
                gt,
                str(handid),
                format_number(totalpot),
                format_number(rake),
                str(sitehandid),
            ]
        elif hand.gametype["base"] == "stud":
            third = " ".join(hand.holecards["THIRD"][hero][0]) + " " + " ".join(hand.holecards["THIRD"][hero][1])
            later_streets = []
            later_streets.extend(hand.holecards["FOURTH"][hero][0])
            later_streets.extend(hand.holecards["FIFTH"][hero][0])
            later_streets.extend(hand.holecards["SIXTH"][hero][0])
            later_streets.extend(hand.holecards["SEVENTH"][hero][0])

            pre_actions = hand.get_actions_short(hero, "THIRD")
            post_actions = ""
            if "F" not in pre_actions:
                post_actions = hand.get_actions_short_streets(
                    hero,
                    "FOURTH",
                    "FIFTH",
                    "SIXTH",
                    "SEVENTH",
                )

            log.debug(
                f"Stud hand details: Third: {third}, Later streets: {later_streets}",
            )

            row = [
                hand.getStakesAsString(),
                str(nbplayers),
                pos,
                third,
                pre_actions,
                " ".join(later_streets),
                post_actions,
                format_number(won),
                format_number(bet),
                format_number(net),
                gt,
                str(handid),
                format_number(totalpot),
                format_number(rake),
            ]
        elif hand.gametype["base"] == "draw":
            row = [
                hand.getStakesAsString(),
                str(nbplayers),
                pos,
                hand.join_holecards(hero, street="DEAL"),
                hand.get_actions_short(hero, "DEAL"),
                None,
                None,
                format_number(won),
                format_number(bet),
                format_number(net),
                gt,
                str(handid),
                format_number(totalpot),
                format_number(rake),
            ]

        numeric_sort_values = {
            self.colnum["Won"]: won,
            self.colnum["Bet"]: bet,
            self.colnum["Net"]: net,
            self.colnum["Total Pot"]: totalpot,
            self.colnum["Rake"]: rake,
        }

        modelrow = [QStandardItem(str(r)) for r in row]
        for index, item in enumerate(modelrow):
            item.setEditable(False)
            if index in (self.colnum["Street0"], self.colnum["Street1-4"]):
                cards = item.data(Qt.ItemDataRole.DisplayRole)
                item.setData(self.render_cards(cards), Qt.ItemDataRole.DecorationRole)
                item.setData("", Qt.ItemDataRole.DisplayRole)
                item.setData(cards, Qt.ItemDataRole.UserRole + 1)
            if index in numeric_sort_values:
                item.setData(float(numeric_sort_values[index]), Qt.ItemDataRole.UserRole)
        log.debug(f"Row added to model: {row}")
        self.model.appendRow(modelrow)

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

        if not card_filter:
            return True

        hcs = self.model.data(
            self.model.index(rownum, self.colnum["Street0"]),
            Qt.ItemDataRole.UserRole + 1,
        ).split(" ")

        if "0x" in hcs:  # if cards are unknown return True
            return True

        gt = self.model.data(self.model.index(rownum, self.colnum["Game"]))

        if gt not in ("holdem", "omahahi", "omahahilo"):
            return True

        # Holdem: Compare the real start cards to the selected filter (ie. AhKh = AKs)
        value1 = Card.card_map[hcs[0][0]]
        value2 = Card.card_map[hcs[1][0]]
        idx = Card.twoStartCards(value1, hcs[0][1], value2, hcs[1][1])
        abbr = Card.twoStartCardString(idx)

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

    # Launch the tournament hand viewer GUI like the original
    config = Configuration.Config()

    settings = {}

    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())

    from PySide6.QtWidgets import QMainWindow

    app = QApplication([])
    sql = SQL.Sql(db_server=settings["db-server"])
    main_window = QMainWindow()

    # create tour viewer
    tour_viewer = TourHandViewer(config, sql, main_window)

    main_window.setCentralWidget(tour_viewer)

    main_window.show()
    main_window.resize(1400, 800)
    app.exec()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
