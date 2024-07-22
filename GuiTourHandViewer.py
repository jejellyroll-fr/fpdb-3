from functools import partial
import Hand
import Card
import Configuration
import Database
import SQL
import Filters
import Deck

from PyQt5.QtCore import QCoreApplication, QSortFilterProxyModel, Qt
from PyQt5.QtGui import QPainter, QPixmap, QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import QApplication, QFrame, QMenu, QProgressDialog, QScrollArea, QSplitter, QTableView, QVBoxLayout

from io import StringIO
import GuiReplayer


class GuiHandViewer(QSplitter):
    def __init__(self, config, querylist, mainwin):
        QSplitter.__init__(self, mainwin)
        self.config = config
        self.main_window = mainwin
        self.sql = querylist
        self.replayer = None

        self.db = Database.Database(self.config, sql=self.sql)

        self.setup_filters()

        scroll = QScrollArea()
        scroll.setWidget(self.filters)

        self.handsFrame = QFrame()
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
            'Stakes': 0,
            'Players': 1,
            'Pos': 2,
            'Street0': 3,
            'Action0': 4,
            'Street1-4': 5,
            'Action1-4': 6,
            'Won': 7,
            'Bet': 8,
            'Net': 9,
            'Game': 10,
            'HandId': 11,
            'Total Pot': 12,
            'Rake': 13,
            'SiteHandNo': 14
        }
        self.view = QTableView()
        self.view.setSelectionBehavior(QTableView.SelectRows)
        self.handsVBox.addWidget(self.view)
        self.model = QStandardItemModel(0, len(self.colnum), self.view)
        self.filterModel = QSortFilterProxyModel()
        self.filterModel.setSourceModel(self.model)
        self.filterModel.setSortRole(Qt.UserRole)

        self.view.setModel(self.filterModel)
        self.view.verticalHeader().hide()
        self.model.setHorizontalHeaderLabels(
            ['Stakes', 'Nb Players', 'Position', 'Hands', 'Preflop Action', 'Board', 'Postflop Action',
             'Won', 'Bet', 'Net', 'Game', 'HandId', 'Total Pot', 'Rake', 'SiteHandId'])

        self.view.doubleClicked.connect(self.row_activated)
        self.view.contextMenuEvent = self.contextMenu
        self.filterModel.rowsInserted.connect(
            lambda index, start, end: [self.view.resizeRowToContents(r) for r in range(start, end + 1)])
        self.filterModel.filterAcceptsRow = lambda row, sourceParent: self.is_row_in_card_filter(row)

        self.view.resizeColumnsToContents()
        self.view.setSortingEnabled(True)

    def setup_filters(self):
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
            "Seats": False,
            "SeatSep": False,
            "Dates": True,
            "Cards": False,
            "Groups": False,
            "GroupsAll": False,
            "Button1": True,
            "Button2": False
        }
        self.filters = Filters.Filters(self.db, display=filters_display)
        self.filters.registerButton1Name("Load Hands")
        self.filters.registerButton1Callback(self.loadHands)
        self.filters.registerCardsCallback(self.filter_cards_cb)
        
        # update games for default hero and site
        heroes = self.filters.getHeroes()
        sites = self.filters.getSites()
        
        default_hero = next(iter(heroes.values())) if heroes else None
        default_site = next(iter(sites)) if sites else None
        
        if default_hero and default_site:
            self.filters.update_games_for_hero(default_hero, default_site)

    def init_card_images(self):
        suits = ('s', 'h', 'd', 'c')
        ranks = (14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2)

        card_images = [0] * 53
        for j in range(0, 13):
            for i in range(0, 4):
                loc = Card.cardFromValueSuit(ranks[j], suits[i])
                card_image = self.deck_instance.card(suits[i], ranks[j])
                card_images[loc] = card_image
        back_image = self.deck_instance.back()
        card_images[0] = back_image
        return card_images

    def loadHands(self, checkState):
        hand_ids = self.get_hand_ids_from_date_range(self.filters.getDates()[0], self.filters.getDates()[1])
        self.reload_hands(hand_ids)

    def get_hand_ids_from_date_range(self, start, end):
        q = """
        SELECT DISTINCT h.id, h.startTime, tt.buyin, tt.fee, p.name, tt.siteId, tt.category
        FROM Hands h
        JOIN Tourneys t ON h.tourneyId = t.id
        JOIN TourneyTypes tt ON t.tourneyTypeId = tt.id
        JOIN TourneysPlayers tp ON t.id = tp.tourneyId
        JOIN Players p ON tp.playerId = p.id
        WHERE h.startTime BETWEEN ? AND ?
        """


        hero_filter = self.filters.getHeroes()
        if hero_filter:
            hero_names = ", ".join(f"'{h}'" for h in hero_filter.values())
            q += f" AND p.name IN ({hero_names})"

        site_filter = self.filters.getSites()
        if site_filter:
            site_ids = ", ".join(str(self.filters.siteid[s]) for s in site_filter)
            q += f" AND tt.siteId IN ({site_ids})"

        category_filter = self.filters.getGames()
        if category_filter:
            categories = ", ".join(f"'{c}'" for c in category_filter)
            q += f" AND tt.category IN ({categories})"

        selected_buyins = self.filters.getBuyIn()
        if selected_buyins:
            buyins_str = ', '.join(map(str, selected_buyins))
            q += f" AND (tt.buyin + tt.fee) IN ({buyins_str})"

        #print(f"Buy-ins sélectionnés (incluant les frais) : {selected_buyins}")

        #print("Requête SQL filtrée :", q)
        
        c = self.db.get_cursor()
        c.execute(q, (start, end))
        results = c.fetchall()
        for row in results[:10]:  # show 10 first results
            print(row)
        return [r[0] for r in results]

    def rankedhand(self, hand, game):
        ranks = {'0': 0, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, 'T': 10, 'J': 11, 'Q': 12,
                 'K': 13, 'A': 14}
        suits = {'x': 0, 's': 1, 'c': 2, 'd': 3, 'h': 4}

        if game == 'holdem':
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
        else:
            return 0

    def reload_hands(self, handids):
        self.hands = {}
        self.model.removeRows(0, self.model.rowCount())
        if len(handids) == 0:
            return
        progress = QProgressDialog("Loading hands", "Abort", 0, len(handids), self)
        progress.setValue(0)
        progress.show()
        for idx, handid in enumerate(handids):
            if progress.wasCanceled():
                break
            self.hands[handid] = self.importhand(handid)
            self.addHandRow(handid, self.hands[handid])

            progress.setValue(idx + 1)
            if idx % 10 == 0:
                QCoreApplication.processEvents()
                self.view.resizeColumnsToContents()
        self.view.resizeColumnsToContents()

    def addHandRow(self, handid, hand):
        hero = self.filters.getHeroes()[hand.sitename]
        won = 0
        nbplayers = len(hand.players)
        if hero in list(hand.collectees.keys()):
            won = hand.collectees[hero]
        bet = 0
        if hero in list(hand.pot.committed.keys()):
            bet = hand.pot.committed[hero]
        net = won - bet
        pos = hand.get_player_position(hero)
        gt = hand.gametype['category']
        row = []
        totalpot = hand.totalpot
        rake = hand.rake
        sitehandid = hand.handid
        if hand.gametype['base'] == 'hold':
            board = []
            board.extend(hand.board['FLOP'])
            board.extend(hand.board['TURN'])
            board.extend(hand.board['RIVER'])

            pre_actions = hand.get_actions_short(hero, 'PREFLOP')
            post_actions = ''
            if 'F' not in pre_actions:  # if player hasen't folded preflop
                post_actions = hand.get_actions_short_streets(hero, 'FLOP', 'TURN', 'RIVER')

            row = [hand.getStakesAsString(), str(nbplayers), pos, hand.join_holecards(hero), pre_actions, ' '.join(board), post_actions,
                   str(won), str(bet), str(net), gt, str(handid), str(totalpot), str(rake), str(sitehandid)]
        elif hand.gametype['base'] == 'stud':
            third = " ".join(hand.holecards['THIRD'][hero][0]) + " " + " ".join(hand.holecards['THIRD'][hero][1])
            # ugh - fix the stud join_holecards function so we can retrieve sanely
            later_streets = []
            later_streets.extend(hand.holecards['FOURTH'][hero][0])
            later_streets.extend(hand.holecards['FIFTH'][hero][0])
            later_streets.extend(hand.holecards['SIXTH'][hero][0])
            later_streets.extend(hand.holecards['SEVENTH'][hero][0])

            pre_actions = hand.get_actions_short(hero, 'THIRD')
            post_actions = ''
            if 'F' not in pre_actions:
                post_actions = hand.get_actions_short_streets(hero, 'FOURTH', 'FIFTH', 'SIXTH', 'SEVENTH')

            row = [hand.getStakesAsString(), str(nbplayers), pos, third, pre_actions, ' '.join(later_streets), post_actions, str(won),
                   str(bet), str(net), gt, str(handid), str(totalpot), str(rake)]
        elif hand.gametype['base'] == 'draw':
            row = [hand.getStakesAsString(), str(nbplayers), pos, hand.join_holecards(hero, street='DEAL'),
                   hand.get_actions_short(hero, 'DEAL'), None, None,
                   str(won), str(bet), str(net), gt, str(handid), str(totalpot), str(rake)]

        modelrow = [QStandardItem(r) for r in row]
        for index, item in enumerate(modelrow):
            item.setEditable(False)
            if index in (self.colnum['Street0'], self.colnum['Street1-4']):
                cards = item.data(Qt.DisplayRole)
                item.setData(self.render_cards(cards), Qt.DecorationRole)
                item.setData("", Qt.DisplayRole)
                item.setData(cards, Qt.UserRole + 1)
            if index in (self.colnum['Bet'], self.colnum['Net'], self.colnum['Won']):
                item.setData(float(item.data(Qt.DisplayRole)), Qt.UserRole)
        self.model.appendRow(modelrow)

    def copyHandToClipboard(self, checkState, hand):
        handText = StringIO()
        hand.writeHand(handText)
        QApplication.clipboard().setText(handText.getvalue())

    def contextMenu(self, event):
        index = self.view.currentIndex()
        if index.row() < 0:
            return
        hand = self.hands[int(index.sibling(index.row(), self.colnum['HandId']).data())]
        m = QMenu()
        copyAction = m.addAction('Copy to clipboard')
        copyAction.triggered.connect(partial(self.copyHandToClipboard, hand=hand))
        m.move(event.globalPos())
        m.exec_()

    def filter_cards_cb(self, card):
        if hasattr(self, 'hands'):
            self.filterModel.invalidateFilter()

    def is_row_in_card_filter(self, rownum):
        """ Returns true if the cards of the given row are in the card filter """
        # Does work but all cards that should NOT be displayed have to be clicked.
        card_filter = self.filters.getCards()
        hcs = self.model.data(self.model.index(rownum, self.colnum['Street0']), Qt.UserRole + 1).split(' ')

        if '0x' in hcs:  # if cards are unknown return True
            return True

        gt = self.model.data(self.model.index(rownum, self.colnum['Game']))

        if gt not in ('holdem', 'omahahi', 'omahahilo'):
            return True

        # Holdem: Compare the real start cards to the selected filter (ie. AhKh = AKs)
        value1 = Card.card_map[hcs[0][0]]
        value2 = Card.card_map[hcs[1][0]]
        idx = Card.twoStartCards(value1, hcs[0][1], value2, hcs[1][1])
        abbr = Card.twoStartCardString(idx)

        # Debug output to trace unexpected keys
        if abbr not in card_filter:
            print(f"Unexpected key in card filter: {abbr}")

        return card_filter.get(abbr, True)  # Default to True if key is not found

    def row_activated(self, index):
        handlist = list(sorted(self.hands.keys()))
        self.replayer = GuiReplayer.GuiReplayer(self.config, self.sql, self.main_window, handlist)
        index = handlist.index(int(index.sibling(index.row(), self.colnum['HandId']).data()))
        self.replayer.play_hand(index)

    def importhand(self, handid=1):
        h = Hand.hand_factory(handid, self.config, self.db)

        # Safely get the hero for this hand's sitename
        heroes = self.filters.getHeroes()
        h.hero = heroes.get(h.sitename, None)
        if h.hero is None:
            print(f"No hero found for site {h.sitename}")
        return h

    def render_cards(self, cardstring):
        card_width = 30
        card_height = 42
        if cardstring is None or cardstring == '':
            cardstring = "0x"
        cardstring = cardstring.replace("'", "")
        cardstring = cardstring.replace("[", "")
        cardstring = cardstring.replace("]", "")
        cardstring = cardstring.replace("'", "")
        cardstring.replace(",", "")
        cards = [Card.encodeCard(c) for c in cardstring.split(' ')]
        n_cards = len(cards)

        pixbuf = QPixmap(card_width * n_cards, card_height)
        painter = QPainter(pixbuf)
        x = 0  # x coord where the next card starts in pixbuf
        for card in cards:
            painter.drawPixmap(x, 0, self.cardImages[card])
            x += card_width
        return pixbuf


class TourHandViewer(GuiHandViewer):
    def __init__(self, config, querylist, mainwin):
        super().__init__(config, querylist, mainwin)

    def setup_filters(self):
        filters_display = {
            "Heroes": True,
            "Sites": True,
            "Games": False, # cash game
            "Tourney": True,
            "TourneyCat": True,
            "TourneyLim": True,
            "TourneyBuyin": True,
            "Currencies": True,
            "Limits": False,
            "LimitSep": True,
            "LimitType": True,
            "Type": True,
            "UseType": 'tour',
            "Seats": False,
            "SeatSep": True,
            "Dates": True,
            "Groups": False,
            "Button1": True,
            "Button2": False
        }
        self.filters = Filters.Filters(self.db, display=filters_display)
        self.filters.registerButton1Name("Load Hands")
        self.filters.registerButton1Callback(self.loadHands)
        self.filters.registerCardsCallback(self.filter_cards_cb)
        
        # update games for default hero and site
        heroes = self.filters.getHeroes()
        sites = self.filters.getSites()
        
        default_hero = next(iter(heroes.values())) if heroes else None
        default_site = next(iter(sites)) if sites else None
        
        if default_hero and default_site:
            self.filters.update_games_for_hero(default_hero, default_site)


if __name__ == "__main__":
    config = Configuration.Config()

    settings = {}

    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())

    from PyQt5.QtWidgets import QMainWindow

    app = QApplication([])
    sql = SQL.Sql(db_server=settings['db-server'])
    main_window = QMainWindow()
    
    # create tour viewer
    tour_viewer = TourHandViewer(config, sql, main_window)
    
    main_window.setCentralWidget(tour_viewer)
    
    main_window.show()
    main_window.resize(1400, 800)
    app.exec_()
