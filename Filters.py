#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function
from __future__ import division
import itertools
from ast import Pass

from dataclasses import replace
from past.utils import old_div
import pathlib
import os
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QDate, QDateTime
from PyQt5.QtWidgets import (QCalendarWidget, QCheckBox, QCompleter,
                             QDateEdit, QDialog, QGridLayout,
                             QGroupBox, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QRadioButton,
                             QSpinBox, QVBoxLayout, QWidget, QComboBox)

from time import gmtime, mktime, strftime, strptime
from functools import partial
import logging

import Configuration
import Database
import SQL
import Charset
import Card

if __name__ == "__main__":
    Configuration.set_logfile("fpdb-log.txt")
log = logging.getLogger("filter")

class Filters(QWidget):
    def __init__(self, db, display={}):
        super().__init__(None)
        self.db = db
        self.cursor = db.cursor
        self.sql = db.sql
        self.conf = db.config
        self.display = display
        self.heroList = None
        self.cbSites = {}
        self.cbGames = {}
        self.cbLimits = {}
        self.cbPositions = {}
        self.cbCurrencies = {}
        self.cbGraphops = {}
        self.cbTourney = {}
        self.cbTourneyCat = {}
        self.cbTourneyLim = {}
        self.cbTourneyBuyin = {}

        self.gameName = {"27_1draw": ("Single Draw 2-7 Lowball"),
                         "27_3draw": ("Triple Draw 2-7 Lowball"),
                         "a5_3draw": ("Triple Draw A-5 Lowball"),
                         "5_studhi": ("5 Card Stud"),
                         "badugi": ("Badugi"),
                         "badacey": ("Badacey"),
                         "badeucey": ("Badeucey"),
                         "drawmaha": ("2-7 Drawmaha"),
                         "a5_1draw": ("A-5 Single Draw"),
                         "27_razz": ("2-7 Razz"),
                         "fivedraw": ("5 Card Draw"),
                         "holdem": ("Hold'em"),
                         "6_holdem": ("Hold'em"),
                         "omahahi": ("Omaha"),
                         "fusion": ("Fusion"),
                         "omahahilo": ("Omaha Hi/Lo"),
                         "razz": ("Razz"),
                         "studhi": ("7 Card Stud"),
                         "studhilo": ("7 Card Stud Hi/Lo"),
                         "5_omahahi": ("5 Card Omaha"),
                         "5_omaha8": ("5 Card Omaha Hi/Lo"),
                         "cour_hi": ("Courchevel"),
                         "cour_hilo": ("Courchevel Hi/Lo"),
                         "2_holdem": ("Double hold'em"),
                         "irish": ("Irish"),
                         "6_omahahi": ("6 Card Omaha")}

        self.currencyName = {"USD": ("US Dollar"),
                             "EUR": ("Euro"),
                             "T$": ("Tournament Dollar"),
                             "play": ("Play Money")}

        self.filterText = {'limitsall': ('All'), 'limitsnone': ('None'), 'limitsshow': ('Show Limits'),
                           'gamesall': ('All'), 'gamesnone': ('None'),
                           'positionsall': ('All'), 'positionsnone': ('None'),
                           'currenciesall': ('All'), 'currenciesnone': ('None'),
                           'seatsbetween': ('Between:'), 'seatsand': ('And:'), 'seatsshow': ('Show Number of Players'),
                           'playerstitle': ('Hero:'), 'sitestitle': (('Sites') + ':'), 'gamestitle': (('Games') + ':'), 'tourneytitle': (('Tourney') + ':'), 'tourneycat': (('Category') + ':'), 
                           'limitstitle': ('Limits:'), 'positionstitle': ('Positions:'), 'seatstitle': ('Number of Players:'), 'tourneylim': (('Limit Type') + ':'),
                           'groupstitle': ('Grouping:'), 'posnshow': ('Show Position Stats'), 'tourneybuyin': (('Buyin') + ':'),
                           'datestitle': ('Date:'), 'currenciestitle': (('Currencies') + ':'),
                           'groupsall': ('All Players'), 'cardstitle': (('Hole Cards') + ':'),
                           'limitsFL': 'FL', 'limitsNL': 'NL', 'limitsPL': 'PL', 'limitsCN': 'CAP', 'ring': ('Ring'), 'tour': ('Tourney'), 'limitsHP': 'HP'}

        gen = self.conf.get_general_params()
        self.day_start = 0

        if 'day_start' in gen:
            self.day_start = float(gen['day_start'])

        self.setLayout(QVBoxLayout())

        self.callback = {}

        self.setStyleSheet("QPushButton {padding-left:5;padding-right:5;padding-top:2;padding-bottom:2;}")
        self.make_filter()

    def make_filter(self):
        self.siteid = {}
        self.cards = {}
        self.type = None

        for site in self.conf.get_supported_sites():
            self.cursor.execute(self.sql.query['getSiteId'], (site,))
            result = self.db.cursor.fetchall()
            if len(result) == 1:
                self.siteid[site] = result[0][0]
            else:
                log.debug(("Either 0 or more than one site matched for %s"), site)

        self.start_date = QDateEdit(QDate(1970, 1, 1))
        self.end_date = QDateEdit(QDate(2100, 1, 1))

        self.cbGroups = {}
        self.phands = None

        if self.display.get("Heroes", False):
            self.layout().addWidget(self.create_player_frame())
        if self.display.get("Sites", False):
            self.layout().addWidget(self.create_sites_frame())
        if self.display.get("Games", False):
            self.layout().addWidget(self.create_games_frame())
        if self.display.get("Tourney", False):
            self.layout().addWidget(self.create_tourney_frame())
        if self.display.get("TourneyCat", False):
            self.layout().addWidget(self.create_tourney_cat_frame())
        if self.display.get("TourneyLim", False):
            self.layout().addWidget(self.create_tourney_lim_frame())
        if self.display.get("TourneyBuyin", False):
            self.layout().addWidget(self.create_tourney_buyin_frame())
        if self.display.get("Currencies", False):
            self.layout().addWidget(self.create_currencies_frame())
        if self.display.get("Limits", False):
            self.layout().addWidget(self.create_limits_frame())
        if self.display.get("Positions", False):
            self.layout().addWidget(self.create_positions_frame())
        if self.display.get("GraphOps", False):
            self.layout().addWidget(self.create_graph_ops_frame())
        if self.display.get("Seats", False):
            self.layout().addWidget(self.create_seats_frame())
        if self.display.get("Groups", False):
            self.layout().addWidget(self.create_groups_frame())
        if self.display.get("Dates", False):
            self.layout().addWidget(self.create_date_frame())
        if self.display.get("Cards", False):
            self.layout().addWidget(self.create_cards_frame())
        if self.display.get("Button1", False) or self.display.get("Button2", False):
            self.layout().addWidget(self.create_buttons())

        self.db.rollback()
        self.set_default_hero()

    def set_default_hero(self):
        if self.heroList and self.heroList.count() > 0:
            self.heroList.setCurrentIndex(0)
            self.update_filters_for_hero()

    def create_player_frame(self):
        playerFrame = QGroupBox(self.filterText['playerstitle'])
        self.leHeroes = {}
        self.fillPlayerFrame(playerFrame, self.display)
        return playerFrame

    def create_sites_frame(self):
        sitesFrame = QGroupBox(self.filterText['sitestitle'])
        self.cbSites = {}
        self.fillSitesFrame(sitesFrame)
        return sitesFrame

    def create_games_frame(self):
        gamesFrame = QGroupBox(self.filterText['gamestitle'])
        self.fillGamesFrame(gamesFrame)
        return gamesFrame

    def create_tourney_frame(self):
        tourneyFrame = QGroupBox(self.filterText['tourneytitle'])
        self.cbTourney = {}
        self.fillTourneyTypesFrame(tourneyFrame)
        return tourneyFrame

    def create_tourney_cat_frame(self):
        tourneyCatFrame = QGroupBox(self.filterText['tourneycat'])
        self.cbTourneyCat = {}
        self.fillTourneyCatFrame(tourneyCatFrame)
        return tourneyCatFrame

    def create_tourney_lim_frame(self):
        tourneyLimFrame = QGroupBox(self.filterText['tourneylim'])
        self.cbTourneyLim = {}
        self.fillTourneyLimFrame(tourneyLimFrame)
        return tourneyLimFrame

    def create_tourney_buyin_frame(self):
        tourneyBuyinFrame = QGroupBox(self.filterText['tourneybuyin'])
        self.cbTourneyBuyin = {}
        self.fillTourneyBuyinFrame(tourneyBuyinFrame)
        return tourneyBuyinFrame

    def create_currencies_frame(self):
        currenciesFrame = QGroupBox(self.filterText['currenciestitle'])
        self.fillCurrenciesFrame(currenciesFrame)
        return currenciesFrame

    def create_limits_frame(self):
        limitsFrame = QGroupBox(self.filterText['limitstitle'])
        self.fillLimitsFrame(limitsFrame, self.display)
        return limitsFrame

    def create_positions_frame(self):
        positionsFrame = QGroupBox(self.filterText['positionstitle'])
        self.fillPositionsFrame(positionsFrame, self.display)
        return positionsFrame

    def create_graph_ops_frame(self):
        graphopsFrame = QGroupBox("Graphing Options:")
        self.cbGraphops = {}
        self.fillGraphOpsFrame(graphopsFrame)
        return graphopsFrame

    def create_seats_frame(self):
        seatsFrame = QGroupBox(self.filterText['seatstitle'])
        self.sbSeats = {}
        self.fillSeatsFrame(seatsFrame)
        return seatsFrame

    def create_groups_frame(self):
        groupsFrame = QGroupBox(self.filterText['groupstitle'])
        self.fillGroupsFrame(groupsFrame, self.display)
        return groupsFrame

    def create_date_frame(self):
        dateFrame = QGroupBox(self.filterText['datestitle'])
        self.fillDateFrame(dateFrame)
        return dateFrame

    def create_cards_frame(self):
        cardsFrame = QGroupBox(self.filterText['cardstitle'])
        self.fillHoleCardsFrame(cardsFrame)
        return cardsFrame

    def create_buttons(self):
        button_frame = QWidget()
        button_layout = QVBoxLayout(button_frame)
        if self.display.get("Button1", False):
            self.Button1 = QPushButton("Unnamed 1")
            button_layout.addWidget(self.Button1)
        if self.display.get("Button2", False):
            self.Button2 = QPushButton("Unnamed 2")
            button_layout.addWidget(self.Button2)
        return button_frame

    def getNumHands(self):
        return self.phands.value() if self.phands else 0

    def getNumTourneys(self):
        return 0
    
    def getGraphOps(self):
        return [g for g in self.cbGraphops if self.cbGraphops[g].isChecked()]

    def getSites(self):
        return [s for s in self.cbSites if self.cbSites[s].isChecked() and self.cbSites[s].isEnabled()]

    def getPositions(self):
        return [p for p in self.cbPositions if self.cbPositions[p].isChecked() and self.cbPositions[p].isEnabled()]

    def getTourneyCat(self):
        return [g for g in self.cbTourneyCat if self.cbTourneyCat[g].isChecked()]

    def getTourneyLim(self):
        return [g for g in self.cbTourneyLim if self.cbTourneyLim[g].isChecked()]

    def getTourneyBuyin(self):
        return [g for g in self.cbTourneyBuyin if self.cbTourneyBuyin[g].isChecked()]

    def getTourneyTypes(self):
        return [g for g in self.cbTourney if self.cbTourney[g].isChecked()]

    def getGames(self):
        return [g for g in self.cbGames if self.cbGames[g].isChecked() and self.cbGames[g].isEnabled()]

    def getCards(self):
        return self.cards

    def getCurrencies(self):
        return [c for c in self.cbCurrencies if self.cbCurrencies[c].isChecked() and self.cbCurrencies[c].isEnabled()]

    def getSiteIds(self):
        return self.siteid

    def getHeroes(self):
        if selected_text := self.heroList.currentText():
            hero = selected_text.split(" on ")[0]
            site = selected_text.split(" on ")[1]
            return {site: hero}
        else:
            return {}

    def getGraphOps(self):
        return [g for g in self.cbGraphops if self.cbGraphops[g].isChecked()]

    def getLimits(self):
        return [l for l in self.cbLimits if self.cbLimits[l].isChecked() and self.cbLimits[l].isEnabled()]

    def getType(self):
        return self.type

    def getSeats(self):
        result = {}
        if 'from' in self.sbSeats:
            result['from'] = self.sbSeats['from'].value()
        if 'to' in self.sbSeats:
            result['to'] = self.sbSeats['to'].value()
        return result

    def getGroups(self):
        return [g for g in self.cbGroups if self.cbGroups[g].isChecked()]

    def getDates(self):
        offset = int(self.day_start * 3600)
        t1 = self.start_date.date()
        t2 = self.end_date.date()
        adj_t1 = QDateTime(t1).addSecs(offset)
        adj_t2 = QDateTime(t2).addSecs(offset + 24 * 3600 - 1)
        return (adj_t1.toUTC().toString("yyyy-MM-dd HH:mm:ss"), adj_t2.toUTC().toString("yyyy-MM-dd HH:mm:ss"))

    def fillCardsFrame(self, frame):
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        grid = QGridLayout()
        vbox1.addLayout(grid)
        self.createCardsWidget(grid)

        hbox = QHBoxLayout()
        vbox1.addLayout(hbox)
        self.createCardsControls(hbox)

        self.cards = {}
        for i, j in itertools.product(range(2, 15), range(2, 15)):
            for s in ['s', 'o']:
                if i >= j:
                    hand = f"{i}{j}{s}"
                    self.cards[hand] = False

    def registerButton1Name(self, title):
        self.Button1.setText(title)

    def registerButton1Callback(self, callback):
        self.Button1.clicked.connect(callback)
        self.Button1.setEnabled(True)
        self.callback['button1'] = callback

    def registerButton2Name(self, title):
        self.Button2.setText(title)

    def registerButton2Callback(self, callback):
        self.Button2.clicked.connect(callback)
        self.Button2.setEnabled(True)
        self.callback['button2'] = callback

    def registerCardsCallback(self, callback):
        self.callback['cards'] = callback

    def __set_tourney_type_select(self, w, tourneyType):
        self.tourneyTypes[tourneyType] = w.get_active()
        log.debug("self.tourney_types[%s] set to %s", tourneyType, self.tourneyTypes[tourneyType])

    def createTourneyTypeLine(self, hbox, tourneyType):
        cb = QCheckBox(str(tourneyType))
        cb.clicked.connect(partial(self.__set_tourney_type_select, tourneyType=tourneyType))
        hbox.addWidget(cb)
        cb.setChecked(True)

    def createCardsWidget(self, grid):
        grid.setSpacing(0)
        for i in range(0, 13):
            for j in range(0, 13):
                abbr = Card.card_map_abbr[j][i]
                b = QPushButton("")
                import platform
                if platform.system() == "Darwin":
                    b.setStyleSheet("QPushButton {border-width:0;margin:6;padding:0;}")
                else:
                    b.setStyleSheet("QPushButton {border-width:0;margin:0;padding:0;}")
                b.clicked.connect(partial(self.__toggle_card_select, widget=b, card=abbr))
                self.cards[abbr] = False
                self.__toggle_card_select(False, widget=b, card=abbr)
                grid.addWidget(b, j, i)

    def createCardsControls(self, hbox):
        selections = ["All", "Suited", "Off Suit"]
        for s in selections:
            cb = QCheckBox(s)
            cb.clicked.connect(self.__set_cards)
            hbox.addWidget(cb)

    def __card_select_bgcolor(self, card, selected):
        s_on = "red"
        s_off = "orange"
        o_on = "white"
        o_off = "lightgrey"
        p_on = "blue"
        p_off = "lightblue"
        if len(card) == 2:
            return p_on if selected else p_off
        if card[2] == 's':
            return s_on if selected else s_off
        if card[2] == 'o':
            return o_on if selected else o_off

    def __toggle_card_select(self, checkState, widget, card):
        font = widget.font()
        font.setPointSize(10)
        widget.setFont(font)
        widget.setText(card)
        self.cards[card] = not self.cards[card]
        if 'cards' in self.callback:
            self.callback['cards'](card)

    def __set_cards(self, checkState):
        pass

    def __set_checkboxes(self, checkState, checkBoxes, setState):
        for checkbox in list(checkBoxes.values()):
            checkbox.setChecked(setState)

    def __select_limit(self, checkState, limit):
        for l, checkbox in list(self.cbLimits.items()):
            if l.endswith(limit):
                checkbox.setChecked(True)

    def fillPlayerFrame(self, frame, display):
        vbox = QVBoxLayout()
        frame.setLayout(vbox)
        self.heroList = QComboBox()
        self.heroList.setStyleSheet("background-color: #455364")
        current_directory = str(pathlib.Path(__file__).parent.absolute())

        for count, site in enumerate(self.conf.get_supported_sites(), start=1):
            player = self.conf.supported_sites[site].screen_name
            _pname = player
            self.leHeroes[site] = QLineEdit(_pname)

            if os.name == 'nt':
                icoPath = os.path.dirname(__file__) + "\\icons\\"
            else:
                icoPath = ""

            icon_file = ""
            if site == "PokerStars":
                icon_file = 'ps.svg'
            elif site == "Full Tilt Poker":
                icon_file = 'ft.svg'
            elif site == "Everleaf":
                icon_file = 'everleaf.png'
            elif site == "Boss":
                icon_file = 'boss.ico'
            elif site == "PartyPoker":
                icon_file = 'party.png'
            elif site == "Merge":
                icon_file = 'merge.png'
            elif site == "PKR":
                icon_file = 'pkr.png'
            elif site == "iPoker":
                icon_file = 'ipoker.png'
            elif site == "Cake":
                icon_file = 'cake.png'
            elif site == "Entraction":
                icon_file = 'entraction.png'
            elif site == "BetOnline":
                icon_file = 'betonline.png'
            elif site == "Microgaming":
                icon_file = 'microgaming.png'
            elif site == "Bovada":
                icon_file = 'bovada.png'
            elif site == "Enet":
                icon_file = 'enet.png'
            elif site == "SealsWithClubs":
                icon_file = 'swc.png'
            elif site == "WinningPoker":
                icon_file = 'winning.png'
            elif site == "GGPoker":
                icon_file = 'gg.png'
            elif site == "Pacific":
                icon_file = 'pacific.png'
            elif site == "KingsClub":
                icon_file = 'kingsclub.png'
            elif site == "Unibet":
                icon_file = 'unibet.png'
            elif site == "Winamax":
                icon_file = 'wina.svg'
            else:
                icon_file = ''

            if icon_file:
                self.heroList.addItem(QIcon(icoPath + icon_file), f"{_pname} on {site}")
            else:
                self.heroList.addItem(f"{_pname} on {site}")

        vbox.addWidget(self.heroList)
        self.heroList.currentTextChanged.connect(self.update_filters_for_hero)

        if "GroupsAll" in display and display["GroupsAll"]:
            hbox = QHBoxLayout()
            vbox.addLayout(hbox)
            self.cbGroups['allplayers'] = QCheckBox(self.filterText['groupsall'])
            hbox.addWidget(self.cbGroups['allplayers'])

            lbl = QLabel(('Min # Hands:'))
            hbox.addWidget(lbl)

            self.phands = QSpinBox()
            self.phands.setMaximum(int(1e5))
            hbox.addWidget(self.phands)

        refresh_button = QPushButton("Refresh Filters")
        refresh_button.clicked.connect(self.update_filters_for_hero)
        vbox.addWidget(refresh_button)

    def fillSitesFrame(self, frame):
        vbox = QVBoxLayout()
        frame.setLayout(vbox)

        for site in self.conf.get_supported_sites():
            self.cbSites[site] = QCheckBox(site)
            self.cbSites[site].setChecked(True)
            vbox.addWidget(self.cbSites[site])

    def fillTourneyTypesFrame(self, frame):
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        req = self.cursor.execute("SELECT DISTINCT tourneyName FROM Tourneys")
        result = req.fetchall()
        print(result)
        self.gameList = QComboBox()
        self.gameList.setStyleSheet("background-color: #455364")
        for count, game in enumerate(result, start=0):
            game = str(result[count])
            if game == "(None,)":
                game = "(\"None\",)"
                game = game.replace("(", "")
                game = game.replace(",", "")
                game = game.replace(")", "")
            else:
                game = game.replace("(", "")
                game = game.replace(",", "")
                game = game.replace(")", "")

            print(game)
            if game != '"None"':
                self.gameList.insertItem(count, game)
            else:
                self.gameList.insertItem(count, game)

        if len(result) >= 1:
            for line in result:
                if str(line) == "(None,)":
                    self.cbTourney[line[0]] = QCheckBox("None")
                    self.cbTourney[line[0]].setChecked(True)
                    vbox1.addWidget(self.cbTourney[line[0]])
                else:
                    self.cbTourney[line[0]] = QCheckBox(line[0])
                    self.cbTourney[line[0]].setChecked(True)
                    vbox1.addWidget(self.cbTourney[line[0]])

        else:
            print("INFO: No games returned from database")
            log.info("No games returned from database")

    def fillTourneyCatFrame(self, frame):
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        req = self.cursor.execute("SELECT DISTINCT category FROM TourneyTypes")
        result = req.fetchall()
        print(result)
        self.gameList = QComboBox()
        self.gameList.setStyleSheet("background-color: #455364")
        for count, game in enumerate(result, start=0):
            game = str(result[count])
            if game == "(None,)":
                game = "(\"None\",)"
                game = game.replace("(", "")
                game = game.replace(",", "")
                game = game.replace(")", "")
            else:
                game = game.replace("(", "")
                game = game.replace(",", "")
                game = game.replace(")", "")

            print(game)
            if game != '"None"':
                self.gameList.insertItem(count, game)
            else:
                self.gameList.insertItem(count, game)

        if len(result) >= 1:
            for line in result:
                if str(line) == "(None,)":
                    self.cbTourneyCat[line[0]] = QCheckBox("None")
                    self.cbTourneyCat[line[0]].setChecked(True)
                    vbox1.addWidget(self.cbTourneyCat[line[0]])
                else:
                    self.cbTourneyCat[line[0]] = QCheckBox(line[0])
                    self.cbTourneyCat[line[0]].setChecked(True)
                    vbox1.addWidget(self.cbTourneyCat[line[0]])

        else:
            print("INFO: No games returned from database")
            log.info("No games returned from database")

    def fillTourneyLimFrame(self, frame):
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        req = self.cursor.execute("SELECT DISTINCT limitType FROM TourneyTypes")
        result = req.fetchall()
        print(result)
        self.gameList = QComboBox()
        self.gameList.setStyleSheet("background-color: #455364")
        for count, game in enumerate(result, start=0):
            game = str(result[count])
            if game == "(None,)":
                game = "(\"None\",)"
                game = game.replace("(", "")
                game = game.replace(",", "")
                game = game.replace(")", "")
            else:
                game = game.replace("(", "")
                game = game.replace(",", "")
                game = game.replace(")", "")

            print(game)
            if game != '"None"':
                self.gameList.insertItem(count, game)
            else:
                self.gameList.insertItem(count, game)

        if len(result) >= 1:
            for line in result:
                if str(line) == "(None,)":
                    self.cbTourneyLim[line[0]] = QCheckBox("None")
                    self.cbTourneyLim[line[0]].setChecked(True)
                    vbox1.addWidget(self.cbTourneyLim[line[0]])
                else:
                    self.cbTourneyLim[line[0]] = QCheckBox(line[0])
                    self.cbTourneyLim[line[0]].setChecked(True)
                    vbox1.addWidget(self.cbTourneyLim[line[0]])

        else:
            print("INFO: No games returned from database")
            log.info("No games returned from database")

    def fillTourneyBuyinFrame(self, frame):
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        req = self.cursor.execute("SELECT DISTINCT buyin, fee FROM TourneyTypes")
        result = req.fetchall()

        if len(result) >= 1:
            for count, (buyin, fee) in enumerate(result):
                if buyin is None and fee is None:
                    display_text = "None"
                    value = "None"
                else:
                    total = (buyin + fee) / 100  # Convert to dollars
                    display_text = f"${total:.2f}"
                    value = f"{buyin},{fee}"

                self.cbTourneyBuyin[value] = QCheckBox(display_text)
                self.cbTourneyBuyin[value].setChecked(True)
                vbox1.addWidget(self.cbTourneyBuyin[value])
        else:
            log.info("No buy-ins returned from database")



    def fillGamesFrame(self, frame):
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.cursor.execute(self.sql.query['getGames'])
        result = self.db.cursor.fetchall()
        print(result)
        self.gameList = QComboBox()
        self.gameList.setStyleSheet("background-color: #455364")
        for count, game in enumerate(result, start=0):
            game = str(result[count])
            game = game.replace("(", "")
            game = game.replace(",", "")
            game = game.replace(")", "")
            print(game)
            self.gameList.insertItem(count, game)

        if len(result) >= 1:
            for line in sorted(result, key=lambda game: self.gameName[game[0]]):
                self.cbGames[line[0]] = QCheckBox(self.gameName[line[0]])
                self.cbGames[line[0]].setChecked(True)
                vbox1.addWidget(self.cbGames[line[0]])

            if len(result) >= 2:
                hbox = QHBoxLayout()
                vbox1.addLayout(hbox)
                hbox.addStretch()

                btnAll = QPushButton(self.filterText['gamesall'])
                btnAll.clicked.connect(partial(self.__set_checkboxes,
                                               checkBoxes=self.cbGames,
                                               setState=True))
                hbox.addWidget(btnAll)

                btnNone = QPushButton(self.filterText['gamesnone'])
                btnNone.clicked.connect(partial(self.__set_checkboxes,
                                                checkBoxes=self.cbGames,
                                                setState=False))
                hbox.addWidget(btnNone)
                hbox.addStretch()
        else:
            print("INFO: No games returned from database")
            log.info("No games returned from database")

    def fillTourneyFrame(self, frame):
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.cursor.execute(self.sql.query['getTourneyNames'])
        result = self.db.cursor.fetchall()
        print(result)
        self.gameList = QComboBox()
        self.gameList.setStyleSheet("background-color: #455364")
        for count, game in enumerate(result, start=0):
            game = str(result[count])
            game = game.replace("(", "")
            game = game.replace(",", "")
            game = game.replace(")", "")
            self.gameList.insertItem(count, game)

    def fillPositionsFrame(self, frame, display):
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        result = [[0], [1], [2], [3], [4], [5], [6], [7], ['S'], ['B']]
        res_count = len(result)

        if res_count > 0:
            v_count = 0
            COL_COUNT = 4
            hbox = None
            for line in result:
                if v_count == 0:
                    hbox = QHBoxLayout()
                    vbox1.addLayout(hbox)

                line_str = str(line[0])
                self.cbPositions[line_str] = QCheckBox(line_str)
                self.cbPositions[line_str].setChecked(True)
                hbox.addWidget(self.cbPositions[line_str])

                v_count += 1
                if v_count == COL_COUNT:
                    v_count = 0

            dif = res_count % COL_COUNT
            while dif > 0:
                fillbox = QVBoxLayout()
                hbox.addLayout(fillbox)
                dif -= 1

            if res_count > 1:
                hbox = QHBoxLayout()
                vbox1.addLayout(hbox)
                hbox.addStretch()

                btnAll = QPushButton(self.filterText['positionsall'])
                btnAll.clicked.connect(partial(self.__set_checkboxes,
                                               checkBoxes=self.cbPositions,
                                               setState=True))
                hbox.addWidget(btnAll)

                btnNone = QPushButton(self.filterText['positionsnone'])
                btnNone.clicked.connect(partial(self.__set_checkboxes,
                                                checkBoxes=self.cbPositions,
                                                setState=False))
                hbox.addWidget(btnNone)
                hbox.addStretch()
        else:
            print("INFO: No positions returned from database")
            log.info("No positions returned from database")

    def fillHoleCardsFrame(self, frame):
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        grid = QGridLayout()
        vbox1.addLayout(grid)
        self.createCardsWidget(grid)

        hbox = QHBoxLayout()
        vbox1.addLayout(hbox)
        self.createCardsControls(hbox)

    def fillCurrenciesFrame(self, frame):
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.cursor.execute(self.sql.query['getCurrencies'])
        result = self.db.cursor.fetchall()
        if len(result) >= 1:
            for line in result:
                if line[0] in self.currencyName:
                    cname = self.currencyName[line[0]]
                else:
                    cname = line[0]
                self.cbCurrencies[line[0]] = QCheckBox(cname)
                self.cbCurrencies[line[0]].setChecked(True)
                vbox1.addWidget(self.cbCurrencies[line[0]])

            if len(result) >= 2:
                hbox = QHBoxLayout()
                vbox1.addLayout(hbox)
                hbox.addStretch()

                btnAll = QPushButton(self.filterText['currenciesall'])
                btnAll.clicked.connect(partial(self.__set_checkboxes,
                                               checkBoxes=self.cbCurrencies,
                                               setState=True))
                hbox.addWidget(btnAll)

                btnNone = QPushButton(self.filterText['currenciesnone'])
                btnNone.clicked.connect(partial(self.__set_checkboxes,
                                                checkBoxes=self.cbCurrencies,
                                                setState=False))
                hbox.addWidget(btnNone)
                hbox.addStretch()
            else:
                self.cbCurrencies[line[0]].setChecked(True)
        else:
            log.info("No currencies returned from database")

    def fillLimitsFrame(self, frame, display):
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.cursor.execute(self.sql.query['getCashLimits'])
        result = self.db.cursor.fetchall()
        limits_found = set()
        types_found = set()

        if len(result) >= 1:
            hbox = QHBoxLayout()
            vbox1.addLayout(hbox)
            vbox2 = QVBoxLayout()
            hbox.addLayout(vbox2)
            vbox3 = QVBoxLayout()
            hbox.addLayout(vbox3)
            for i, line in enumerate(result):
                if "UseType" in self.display:
                    if line[0] != self.display["UseType"]:
                        continue
                hbox = QHBoxLayout()
                if i < old_div((len(result) + 1), 2):
                    vbox2.addLayout(hbox)
                else:
                    vbox3.addLayout(hbox)
                if True:
                    name = str(line[2]) + line[1]
                    limits_found.add(line[1])
                    self.cbLimits[name] = QCheckBox(name)
                    self.cbLimits[name].setChecked(True)
                    hbox.addWidget(self.cbLimits[name])
                types_found.add(line[0])
                self.type = line[0]
            if "LimitSep" in display and display["LimitSep"] and len(result) >= 2:
                hbox = QHBoxLayout()
                vbox1.addLayout(hbox)
                hbox.addStretch()

                btnAll = QPushButton(self.filterText['limitsall'])
                btnAll.clicked.connect(partial(self.__set_checkboxes,
                                               checkBoxes=self.cbLimits,
                                               setState=True))
                hbox.addWidget(btnAll)

                btnNone = QPushButton(self.filterText['limitsnone'])
                btnNone.clicked.connect(partial(self.__set_checkboxes,
                                                checkBoxes=self.cbLimits,
                                                setState=False))
                hbox.addWidget(btnNone)

                if "LimitType" in display and display["LimitType"] and len(limits_found) > 1:
                    for limit in limits_found:
                        btn = QPushButton(self.filterText['limits' + limit.upper()])
                        btn.clicked.connect(partial(self.__select_limit, limit=limit))
                        hbox.addWidget(btn)

                hbox.addStretch()
        else:
            print("INFO: No games returned from database")
            log.info("No games returned from database")

        if "Type" in display and display["Type"] and 'ring' in types_found and 'tour' in types_found:
            self.type = 'ring'

    def fillGraphOpsFrame(self, frame):
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        hbox1 = QHBoxLayout()
        vbox1.addLayout(hbox1)

        label = QLabel("Show Graph In:")
        hbox1.addWidget(label)

        self.cbGraphops['$'] = QRadioButton("$$", frame)
        hbox1.addWidget(self.cbGraphops['$'])
        self.cbGraphops['$'].setChecked(True)

        self.cbGraphops['BB'] = QRadioButton("BB", frame)
        hbox1.addWidget(self.cbGraphops['BB'])

        self.cbGraphops['showdown'] = QCheckBox("Showdown Winnings")
        vbox1.addWidget(self.cbGraphops['showdown'])

        self.cbGraphops['nonshowdown'] = QCheckBox("Non-Showdown Winnings")
        vbox1.addWidget(self.cbGraphops['nonshowdown'])

        self.cbGraphops['ev'] = QCheckBox("EV")
        vbox1.addWidget(self.cbGraphops['ev'])

    def fillSeatsFrame(self, frame):
        hbox = QHBoxLayout()
        frame.setLayout(hbox)

        lbl_from = QLabel(self.filterText['seatsbetween'])
        lbl_to = QLabel(self.filterText['seatsand'])

        adj1 = QSpinBox()
        adj1.setRange(2, 10)
        adj1.setValue(2)
        adj1.valueChanged.connect(partial(self.__seats_changed, 'from'))

        adj2 = QSpinBox()
        adj2.setRange(2, 10)
        adj2.setValue(10)
        adj2.valueChanged.connect(partial(self.__seats_changed, 'to'))

        hbox.addStretch()
        hbox.addWidget(lbl_from)
        hbox.addWidget(adj1)
        hbox.addWidget(lbl_to)
        hbox.addWidget(adj2)
        hbox.addStretch()

        self.sbSeats['from'] = adj1
        self.sbSeats['to'] = adj2

    def fillGroupsFrame(self, frame, display):
        vbox = QVBoxLayout()
        frame.setLayout(vbox)

        self.cbGroups['limits'] = QCheckBox(self.filterText['limitsshow'])
        vbox.addWidget(self.cbGroups['limits'])

        self.cbGroups['posn'] = QCheckBox(self.filterText['posnshow'])
        vbox.addWidget(self.cbGroups['posn'])

        if "SeatSep" in display and display["SeatSep"]:
            self.cbGroups['seats'] = QCheckBox(self.filterText['seatsshow'])
            vbox.addWidget(self.cbGroups['seats'])

    def fillDateFrame(self, frame):
        table = QGridLayout()
        frame.setLayout(table)

        lbl_start = QLabel(('From:'))
        btn_start = QPushButton("Cal")
        btn_start.clicked.connect(partial(self.__calendar_dialog, dateEdit=self.start_date))
        clr_start = QPushButton("Reset")
        clr_start.clicked.connect(self.__clear_start_date)

        lbl_end = QLabel(('To:'))
        btn_end = QPushButton("Cal")
        btn_end.clicked.connect(partial(self.__calendar_dialog, dateEdit=self.end_date))
        clr_end = QPushButton("Reset")
        clr_end.clicked.connect(self.__clear_end_date)

        table.addWidget(lbl_start, 0, 0)
        table.addWidget(btn_start, 0, 1)
        table.addWidget(self.start_date, 0, 2)
        table.addWidget(clr_start, 0, 3)

        table.addWidget(lbl_end, 1, 0)
        table.addWidget(btn_end, 1, 1)
        table.addWidget(self.end_date, 1, 2)
        table.addWidget(clr_end, 1, 3)

        table.setColumnStretch(0, 1)

    def get_limits_where_clause(self, limits):
        where = ""
        lims = [int(x[0:-2]) for x in limits if len(x) > 2 and x[-2:] == 'fl']
        potlims = [int(x[0:-2]) for x in limits if len(x) > 2 and x[-2:] == 'pl']
        nolims = [int(x[0:-2]) for x in limits if len(x) > 2 and x[-2:] == 'nl']
        capnolims = [int(x[0:-2]) for x in limits if len(x) > 2 and x[-2:] == 'cn']
        hpnolims = [int(x[0:-2]) for x in limits if len(x) > 2 and x[-2:] == 'hp']

        where = "AND ( "

        if lims:
            clause = "(gt.limitType = 'fl' and gt.bigBlind in (%s))" % (','.join(map(str, lims)))
        else:
            clause = "(gt.limitType = 'fl' and gt.bigBlind in (-1))"
        where = where + clause
        if potlims:
            clause = "or (gt.limitType = 'pl' and gt.bigBlind in (%s))" % (','.join(map(str, potlims)))
        else:
            clause = "or (gt.limitType = 'pl' and gt.bigBlind in (-1))"
        where = where + clause
        if nolims:
            clause = "or (gt.limitType = 'nl' and gt.bigBlind in (%s))" % (','.join(map(str, nolims)))
        else:
            clause = "or (gt.limitType = 'nl' and gt.bigBlind in (-1))"
        where = where + clause
        if hpnolims:
            clause = "or (gt.limitType = 'hp' and gt.bigBlind in (%s))" % (','.join(map(str, hpnolims)))
        else:
            clause = "or (gt.limitType = 'hp' and gt.bigBlind in (-1))"
        where = where + clause
        if capnolims:
            clause = "or (gt.limitType = 'cp' and gt.bigBlind in (%s))" % (','.join(map(str, capnolims)))
        else:
            clause = "or (gt.limitType = 'cp' and gt.bigBlind in (-1))"
        where = where + clause + ' )'

        return where

    def replace_placeholders_with_filter_values(self, query):
        if '<game_test>' in query:
            games = self.getGames()
            if games:
                gametest = f"AND gt.category IN {str(tuple(games)).replace(',)', ')')}"
            else:
                gametest = ""
            query = query.replace('<game_test>', gametest)

        if '<limit_test>' in query:
            limits = self.getLimits()
            if limits:
                limittest = self.get_limits_where_clause(limits)
            else:
                limittest = ""
            query = query.replace('<limit_test>', limittest)

        if '<player_test>' in query:
            heroes = self.getHeroes()
            if heroes:
                hero_ids = self.get_hero_ids(heroes)
                player_test = f"AND hp.playerId IN ({','.join(map(str, hero_ids))})"
            else:
                player_test = ""
            query = query.replace('<player_test>', player_test)

        if '<position_test>' in query:
            positions = self.getPositions()
            if positions:
                formatted_positions = [f"'{position}'" for position in positions]
                positiontest = f"AND hp.position IN ({','.join(formatted_positions)})"
            else:
                positiontest = ""
            query = query.replace('<position_test>', positiontest)

        return query

    def get_hero_ids(self, heroes):
        hero_ids = []
        site_ids = self.getSiteIds()
        for site, hero in heroes.items():
            site_id = site_ids.get(site)
            if site_id is not None:
                self.cursor.execute(self.sql.query['getPlayerId'], (site_id, hero))
                result = self.cursor.fetchone()
                if result:
                    hero_ids.append(result[0])
        return hero_ids

    def __calendar_dialog(self, checkState, dateEdit):
        d = QDialog()
        d.setWindowTitle('Pick a date')

        vb = QVBoxLayout()
        d.setLayout(vb)
        cal = QCalendarWidget()
        vb.addWidget(cal)

        btn = QPushButton('Done')
        btn.clicked.connect(partial(self.__get_date, dlg=d, calendar=cal, dateEdit=dateEdit))
        vb.addWidget(btn)
        d.exec_()

    def __clear_start_date(self, checkState):
        self.start_date.setDate(QDate(1970, 1, 1))

    def __clear_end_date(self, checkState):
        self.end_date.setDate(QDate(2100, 1, 1))

    def __get_date(self, checkState, dlg, calendar, dateEdit):
        newDate = calendar.selectedDate()
        dateEdit.setDate(newDate)

        if dateEdit == self.start_date:
            end = self.end_date.date()
            if newDate > end:
                self.end_date.setDate(newDate)
        else:
            start = self.start_date.date()
            if newDate < start:
                self.start_date.setDate(newDate)
        dlg.accept()

    def __seats_changed(self, value, which):
        seats_from = self.sbSeats['from'].value()
        seats_to = self.sbSeats['to'].value()
        if seats_from > seats_to:
            if which == 'from':
                self.sbSeats['to'].setValue(seats_from)
            else:
                self.sbSeats['from'].setValue(seats_to)

    def setGames(self, games):
        self.games = games

    def update_filters_for_hero(self):
        if self.heroList and self.heroList.count() > 0:
            selected_text = self.heroList.currentText()
            if " on " in selected_text:
                selected_hero, selected_site = selected_text.split(" on ")
                self.update_sites_for_hero(selected_hero, selected_site)
                self.update_games_for_hero(selected_hero, selected_site)
                self.update_limits_for_hero(selected_hero, selected_site)
                self.update_positions_for_hero(selected_hero, selected_site)
                self.update_currencies_for_hero(selected_hero, selected_site)

    def update_sites_for_hero(self, hero, site):
        for s, checkbox in self.cbSites.items():
            checkbox.setChecked(s == site)
            checkbox.setEnabled(s == site)

    def update_games_for_hero(self, hero, site):
        site_id = self.siteid[site]
        usetype = self.display.get("UseType", "")
        print(f"Game type for hero {hero} on site {site}: {usetype}")
        
        if usetype == 'tour':
            query = """
            SELECT DISTINCT tt.category
            FROM TourneyTypes tt
            JOIN Tourneys t ON tt.id = t.tourneyTypeId
            JOIN TourneysPlayers tp ON t.id = tp.tourneyId
            JOIN Players p ON tp.playerId = p.id
            WHERE tt.siteId = ? AND p.name = ?
            """
        else:  # ring games
            query = """
            SELECT DISTINCT gt.category
            FROM GameTypes gt
            JOIN Hands h ON gt.id = h.gametypeId
            JOIN HandsPlayers hp ON h.id = hp.handId
            JOIN Players p ON hp.playerId = p.id
            WHERE gt.siteId = ? AND p.name = ? AND gt.type = 'ring'
            """
        
        print("Query:")
        print(query)

        self.cursor.execute(query, (site_id, hero))
        games = [row[0] for row in self.cursor.fetchall()]
        print(f"Available games for hero {hero} on site {site}: {games}")
        
        for game, checkbox in self.cbGames.items():
            if game in games:
                checkbox.setChecked(True)
                checkbox.setEnabled(True)
            else:
                checkbox.setChecked(False)
                checkbox.setEnabled(False)

        # update
        self.games = games


    def update_limits_for_hero(self, hero, site):
        query = self.sql.query['getCashLimits'].replace("%s", str(self.siteid[site]))
        self.cursor.execute(query)
        limits = [f"{row[2]}{row[1]}" for row in self.cursor.fetchall()]
        for limit, checkbox in self.cbLimits.items():
            if limit in limits:
                checkbox.setChecked(True)
                checkbox.setEnabled(True)
            else:
                checkbox.setChecked(False)
                checkbox.setEnabled(False)

    def update_positions_for_hero(self, hero, site):
        query = "SELECT DISTINCT hp.position FROM HandsPlayers hp JOIN Hands h ON hp.handId = h.id JOIN Players p ON hp.playerId = p.id WHERE p.name = ? AND h.siteHandNo LIKE ?"
        site_id = self.siteid[site]
        self.cursor.execute(query, (hero, f"{site_id}%"))
        positions = [str(row[0]) for row in self.cursor.fetchall()]
        for position, checkbox in self.cbPositions.items():
            if position in positions:
                checkbox.setChecked(True)
                checkbox.setEnabled(True)
            else:
                checkbox.setChecked(False)
                checkbox.setEnabled(False)

    def getBuyIn(self):
        selected_buyins = []
        for value, checkbox in self.cbTourneyBuyin.items():
            if checkbox.isChecked() and value != "None":
                buyin, fee = map(int, value.split(','))
                total = buyin + fee
                selected_buyins.append(total)
        return selected_buyins

    def update_currencies_for_hero(self, hero, site):
        query = """
            SELECT DISTINCT gt.currency
            FROM GameTypes gt
            JOIN Hands h ON gt.id = h.gametypeId
            JOIN HandsPlayers hp ON h.id = hp.handId
            JOIN Players p ON hp.playerId = p.id
            WHERE gt.siteId = ? AND p.name = ?
        """
        site_id = self.siteid[site]
        #debug
        #print(f"executed request for {hero} on {site} (site_id: {site_id})")
        self.cursor.execute(query, (site_id, hero))
        currencies = [row[0] for row in self.cursor.fetchall()]
        #debug
        #print(f"currencies found for {hero} on {site}: {currencies}")
        
        for currency, checkbox in self.cbCurrencies.items():
            if currency in currencies:
                checkbox.setChecked(True)
                checkbox.setEnabled(True)
            else:
                checkbox.setChecked(False)
                checkbox.setEnabled(False)
            
            # manage tour 'T$' on  'ring'
            if currency == 'T$' and self.getType() == 'ring':
                checkbox.setChecked(False)
                checkbox.setEnabled(False)
            #debug
            #print(f"Devise {currency} - Checked: {checkbox.isChecked()}, Activated: {checkbox.isEnabled()} on {site}")

if __name__ == '__main__':
    config = Configuration.Config(file="HUD_config.test.xml")
    db = Database.Database(config)

    qdict = SQL.Sql(db_server='sqlite')

    filters_display = {"Heroes": False,
                       "Sites": False,
                       "Games": False,
                       "Cards": True,
                       "Currencies": False,
                       "Limits": False,
                       "LimitSep": False,
                       "LimitType": False,
                       "Type": False,
                       "UseType": 'ring',
                       "Seats": False,
                       "SeatSep": False,
                       "Dates": False,
                       "GraphOps": False,
                       "Groups": False,
                       "Button1": False,
                       "Button2": False
                       }

    from PyQt5.QtWidgets import QMainWindow, QApplication
    app = QApplication([])
    i = Filters(db, display=filters_display)
    main_window = QMainWindow()
    main_window.setCentralWidget(i)
    main_window.show()
    app.exec_()
