#!/usr/bin/env python
# -*- coding: utf-8 -*-

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

# Note that this now contains the replayer only! The list of hands has been moved to GuiHandViewer by zarturo.

from __future__ import print_function
from __future__ import division
from ast import Return
from builtins import str
from builtins import range
from builtins import object
from collections import defaultdict
from unicodedata import decimal, name
from past.utils import old_div
import L10n
_ = L10n.get_translation()

from functools import partial

import json
import Hand
import Card
import Configuration
import Database
import SQL
import Deck

from PyQt5.QtCore import (QPoint, QRect, Qt, QTimer)
from PyQt5.QtGui import (QColor, QImage, QPainter)
from PyQt5.QtWidgets import (QHBoxLayout, QPushButton, QSlider, QVBoxLayout,
                             QWidget)

from math import pi, cos, sin
from decimal_wrapper import Decimal
import numpy as np
from matplotlib import pyplot as plt
import copy
import os

CARD_HEIGHT = 70
CARD_WIDTH = 50

class GuiReplayer(QWidget):
    """A Replayer to replay hands."""
    def __init__(self, config, querylist, mainwin, handlist):
        QWidget.__init__(self, None)
        self.setFixedSize(982, 680)
        self.conf = config
        self.main_window = mainwin
        self.sql = querylist
        self.newpot = Decimal()
        self.db = Database.Database(self.conf, sql=self.sql)
        self.states = [] # List with all table states.
        self.handlist = handlist
        self.handidx = 0

        self.setWindowTitle("FPDB Hand Replayer")
        
        self.replayBox = QVBoxLayout()
        
        self.setLayout(self.replayBox)

        self.replayBox.addStretch()

        self.buttonBox = QHBoxLayout()
        self.prevButton = QPushButton("Prev")
        self.prevButton.clicked.connect(self.prev_clicked)
        self.prevButton.setFocusPolicy(Qt.NoFocus)
        self.startButton = QPushButton("Start")
        self.startButton.clicked.connect(self.start_clicked)
        self.startButton.setFocusPolicy(Qt.NoFocus)
        self.endButton = QPushButton("End")
        self.endButton.clicked.connect(self.end_clicked)
        self.endButton.setFocusPolicy(Qt.NoFocus)
        self.playPauseButton = QPushButton("Play")
        self.playPauseButton.clicked.connect(self.play_clicked)
        self.playPauseButton.setFocusPolicy(Qt.NoFocus)
        self.nextButton = QPushButton("Next")
        self.nextButton.clicked.connect(self.next_clicked)
        self.nextButton.setFocusPolicy(Qt.NoFocus)

        self.replayBox.addLayout(self.buttonBox)

        self.stateSlider = QSlider(Qt.Horizontal)
        self.stateSlider.valueChanged.connect(self.slider_changed)
        self.stateSlider.setFocusPolicy(Qt.NoFocus)

        self.replayBox.addWidget(self.stateSlider, False)

        self.playing = False

        self.tableImage = None
        self.playerBackdrop = None
        
        self.cardImages = None
        self.deck_inst = Deck.Deck(self.conf, height=CARD_HEIGHT, width=CARD_WIDTH)
        self.show()

    def renderCards(self, painter, cards, x, y):
        for card in cards:
            cardIndex = Card.encodeCard(card)
            painter.drawPixmap(QPoint(x, y), self.cardImages[cardIndex])
            x += self.cardwidth

    
    def paintEvent(self, event):

        

        if self.tableImage is None or self.playerBackdrop is None:
            try:
                self.playerBackdrop = QImage(os.path.join(self.conf.graphics_path, "playerbackdrop.png"))
                self.tableImage = QImage(os.path.join(self.conf.graphics_path, "TableR.png"))
            except:
                return
        if self.cardImages is None:
            self.cardwidth = CARD_WIDTH
            self.cardheight = CARD_HEIGHT
            self.cardImages = [None] * 53
            suits = ('s', 'h', 'd', 'c')
            ranks = (14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2)
            for j in range(0, 13):
                for i in range(0, 4):
                    index = Card.cardFromValueSuit(ranks[j], suits[i])
                    self.cardImages[index] = self.deck_inst.card(suits[i], ranks[j])
            self.cardImages[0] = self.deck_inst.back()

        if not event.rect().intersects(QRect(0, 0, self.tableImage.width(), self.tableImage.height())):
            return

        painter = QPainter(self)
       
        painter.drawImage(QPoint(100,200), self.tableImage)
        
        

        if len(self.states) == 0:
            return
 
        state = self.states[self.stateSlider.value()]


        communityLeft = int(old_div(self.tableImage.width(), 2) - 2.5 * self.cardwidth)
        communityTop = int(old_div(self.tableImage.height(), 2) - 1.75 * self.cardheight)
   

        convertx = lambda x: int(x * self.tableImage.width() * 0.8) + old_div(self.tableImage.width(), 2)
        converty = lambda y: int(y * self.tableImage.height() * 0.6) + old_div(self.tableImage.height(), 2)

        painter.drawText(QRect(-40,0,600,40),Qt.AlignCenter,self.info)
        
        for player in list(state.players.values()):
            print(len(list(state.players.values())))
            playerx = convertx(player.x)
            
            playery = converty(player.y)
            print('playerx',playerx,'playery',playery, player.name)
            
            painter.drawImage(QPoint(playerx - old_div(self.playerBackdrop.width(), 2), playery - 3), self.playerBackdrop)
            
            if player.action=="folds":
                painter.setPen(QColor("red"))
            else:
                painter.setPen(QColor("white"))
                x = playerx - self.cardwidth * len(player.holecards) // 2
                self.renderCards(painter, player.holecards,
                                 x, playery - self.cardheight)

            painter.drawText(QRect(playerx - 100, playery, 200, 20),
                             Qt.AlignCenter,
                             '%s %s%.2f' % (player.name,
                                            self.currency,
                                            player.stack))

            if player.justacted:
                
                painter.setPen(QColor("yellow"))
                
                painter.drawText(QRect(playerx - 50, playery + 15, 100, 20), Qt.AlignCenter, player.action)
                painter.drawText(QRect(old_div(self.tableImage.width(), 2) - 100,
                                       old_div(self.tableImage.height(), 2) - 20,
                                       200,
                                       40),
                                 Qt.AlignCenter,
                                'Pot: %s%.2f' % (self.currency, state.newpot)) 
            else:
                painter.setPen(QColor("white"))
            if player.chips != 0:
                painter.drawText(QRect(convertx(player.x * .65) - 100,
                                       converty(player.y * 0.65),
                                       200,
                                       20),
                                 Qt.AlignCenter,
                                 '%s%.2f' % (self.currency, player.chips))
                
            
                            

        painter.setPen(QColor("white"))
        

         




                
            # new_pot = state.pot
            # print (state.pot)
            # if  player.chips != 0 :
            #     print ('init', new_pot)
            #     new_pot = new_pot + player.chips
            #     painter.drawText(QRect(old_div(self.tableImage.width(), 2) - 100,
            #                        old_div(self.tableImage.height(), 2) - 20,
            #                        200,
            #                        40),
            #                  Qt.AlignCenter,
            #                  'Pot: %s%.2f' % (self.currency, new_pot))
            #     print ('1-pot state:', new_pot,'player action:', player.name,  player.action, 'player chips:', player.chips, player.stack, player.justacted, 'pot odds:' ,pot_odds)  
                
            #     print ('act', new_pot)  
            #     if player.action=='bets' or player.action=='raises' :
            #         pot_odds = (1/(((new_pot+player.chips)/player.chips)+1))*100
            #         painter.drawText(QRect(old_div(self.tableImage.width(), 2) - 100,
            #                        old_div(self.tableImage.height(), 2) - 20,
            #                        200,
            #                        70),
            #                  Qt.AlignCenter,
            #                  'Pot odds: %s%.2f' % (percent, pot_odds))
            #         print ('2-pot state:', new_pot,'player chips:', player.chips, player.stack, player.justacted,'pot odds:' ,pot_odds)
            # state.pot = new_pot    
                
            
        for street in state.renderBoard:
            x = communityLeft
            if street.startswith('TURN'):
                x += 3 * self.cardwidth
            elif street.startswith('RIVER'):
                x += 4 * self.cardwidth
            y = communityTop
            if street.endswith('1'): # Run it twice streets
                y -= 0.5 * self.cardheight
            elif street.endswith('2'):
                y += 0.5 * self.cardheight
            self.renderCards(painter, state.board[street], x, y)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Left:
            self.stateSlider.setValue(max(0, self.stateSlider.value() - 1))
        elif event.key() == Qt.Key_Right:
            self.stateSlider.setValue(min(self.stateSlider.maximum(), self.stateSlider.value() + 1))
        elif event.key() == Qt.Key_Up:
            if self.handidx < len(self.handlist) - 1:
                self.play_hand(self.handidx + 1)
        elif event.key() == Qt.Key_Down:
            if self.handidx > 0:
                self.play_hand(self.handidx - 1)
        else:
            QWidget.keyPressEvent(self, event)

    def play_hand(self, handidx):
        self.handidx = handidx
        hand = Hand.hand_factory(self.handlist[handidx], self.conf, self.db)
        # hand.writeHand()  # Print handhistory to stdout -> should be an option in the GUI
        self.currency = hand.sym

        self.states = []

        #info for drawing (game, limite, site ...)
        print (hand)
        print(hand.gametype)
        info_gen = hand.gametype['category']
        if info_gen == "omahahilo":
            info_gen = "Omaha Hi/Lo"
        elif info_gen == "27_1draw":
            info_gen = "Single Draw 2-7 Lowball"
        elif info_gen == "27_3draw":
            info_gen = "Triple Draw 2-7 Lowball"
        elif info_gen == "a5_3draw":
            info_gen = "Triple Draw A-5 Lowball"
        elif info_gen == "5_studhi":
            info_gen = "5 Card Stud"   
        elif info_gen == "badugi":
            info_gen = "Badugi"
        elif info_gen == "badacey":
            info_gen = "Badacey"
        elif info_gen == "badeucey":
            info_gen = "Badeucey"
        elif info_gen == "drawmaha":
            info_gen = "2-7 Drawmaha"        
        elif info_gen == "a5_1draw":
            info_gen = "A-5 Single Draw"
        elif info_gen == "27_razz":
            info_gen = "2-7 Razz"
        elif info_gen == "fivedraw":
            info_gen = "5 Card Draw"
        elif info_gen == "holdem":
            info_gen = "Hold'em"   
        elif info_gen == "6_holdem":
            info_gen = "Hold'em"
        elif info_gen == "omahahi":
            info_gen = "Omaha"
        elif info_gen == "razz":
            info_gen = "Razz"
        elif info_gen == "studhi":
            info_gen = "7 Card Stud"  
        elif info_gen == "studhilo":
            info_gen = "7 Card Stud Hi/Lo"
        elif info_gen == "5_omahahi":
            info_gen = "5 Card Omaha"
        elif info_gen == "5_omaha8":
            info_gen = "5 Card Omaha Hi/Lo"
        elif info_gen == "cour_hi":
            info_gen = "Courchevel"   
        elif info_gen == "cour_hilo":
            info_gen = "Courchevel Hi/Lo"
        elif info_gen == "2_holdem":
            info_gen = "Double hold'em"
        elif info_gen == "irish":
            info_gen = "Irish"
        elif info_gen == "6_omahahi":
            info_gen = "6 Card Omaha"                                               
        else:
            info_gen = "unknown"
        limit_info = hand.gametype['limitType']
        if limit_info == "fl":
            limit_info = "Fixed Limit"
        elif limit_info == "nl":
            limit_info = "No Limit"
        elif limit_info == "pl":
            limit_info = "Pot Limit"
        elif limit_info == "cn":
            limit_info = "Cap No Limit"
        elif limit_info == "cp":
            limit_info = "Cap Pot Limit"
        else:
            limit_info = "unknown"
        print(limit_info)
        self.info = str(limit_info)+" "+str(info_gen)+ " "+str(hand.gametype['bb']) + str(hand.gametype['currency']) +" hand played on "+str(hand.sitename)

        
        
        state = TableState(hand)
        
        #print (state)
        seenStreets = []
        for street in hand.allStreets:
            if state.called > 0:
                for player in list(state.players.values()):
                    if player.stack == 0:
                        state.allin = True
                        break
            if not hand.actions[street] and not state.allin:
                break
            seenStreets.append(street)
            state = copy.deepcopy(state)
            state.startPhase(street)
            self.states.append(state)
            for action in hand.actions[street]:
                state = copy.deepcopy(state)
                state.updateForAction(action)
                self.states.append(state)
                
        state = copy.deepcopy(state)
        state.endHand(hand.collectees, hand.pot.returned)
        self.states.append(state)

        # Clear and repopulate the row of buttons
        for idx in reversed(list(range(self.buttonBox.count()))):
            self.buttonBox.takeAt(idx).widget().setParent(None)
        self.buttonBox.addWidget(self.prevButton)
        self.prevButton.setEnabled(self.handidx > 0)
        self.buttonBox.addWidget(self.startButton)
        for street in hand.allStreets[1:]:
            btn = QPushButton(street.capitalize())
            self.buttonBox.addWidget(btn)
            btn.clicked.connect(partial(self.street_clicked, street=street))
            btn.setEnabled(street in seenStreets)
            btn.setFocusPolicy(Qt.NoFocus)
        self.buttonBox.addWidget(self.endButton)
        self.buttonBox.addWidget(self.playPauseButton)
        self.buttonBox.addWidget(self.nextButton)
        self.nextButton.setEnabled(self.handidx < len(self.handlist) - 1)

        self.stateSlider.setMaximum(len(self.states) - 1)
        self.stateSlider.setValue(0)
        self.update()

    def increment_state(self):
        if self.stateSlider.value() == self.stateSlider.maximum():
            self.playing = False
            self.playPauseButton.setText("Play")

        if self.playing:
            self.stateSlider.setValue(self.stateSlider.value() + 1)
    
    def slider_changed(self, value):
        self.update()

    def importhand(self, handid=1):

        h = Hand.hand_factory(handid, self.conf, self.db)
        
        return h

    def play_clicked(self, checkState):
        self.playing = not self.playing
        if self.playing:
            self.playPauseButton.setText("Pause")
            self.playTimer = QTimer()
            self.playTimer.timeout.connect(self.increment_state)
            self.playTimer.start(1000)
        else:
            self.playPauseButton.setText("Play")
            self.playTimer = None

    def start_clicked(self, checkState):
        self.stateSlider.setValue(0)

    def end_clicked(self, checkState):
        self.stateSlider.setValue(self.stateSlider.maximum())

    def prev_clicked(self, checkState):
        self.play_hand(self.handidx - 1)

    def next_clicked(self, checkState):
        self.play_hand(self.handidx + 1)

    def street_clicked(self, checkState, street):
        for i, state in enumerate(self.states):
            if state.street == street:
                self.stateSlider.setValue(i)
                break

# ICM code originally grabbed from http://svn.gna.org/svn/pokersource/trunk/icm-calculator/icm-webservice.py
# Copyright (c) 2008 Thomas Johnson <tomfmason@gmail.com>

class ICM(object):
    def __init__(self, stacks, payouts):
        self.stacks = stacks
        self.payouts = payouts
        self.equities = []
        self.prepare()
    def prepare(self):
        total = sum(self.stacks)
        for k in self.stacks:
            self.equities.append(round(Decimal(str(self.getEquities(total, k, 0))), 4))
   
    def getEquities(self, total, player, depth):
        D = Decimal
        eq = D(self.stacks[player]) // total * D(str(self.payouts[depth]))
        if(depth + 1 < len(self.payouts)):
            i=0
            for stack in self.stacks:
                if i != player and stack > 0.0:
                    self.stacks[i] = 0.0
                    eq += self.getEquities((total - stack), player, (depth + 1)) * (old_div(stack, D(total)))
                    self.stacks[i] = stack
                i += 1
        return eq

class TableState(object):
    def __init__(self, hand):
        self.pot = Decimal(0)
        self.street = None
        self.board = hand.board
        self.renderBoard = set()
        self.bet = Decimal(0)
        self.called = Decimal(0)
        self.gametype = hand.gametype['category']
        self.gamebase = hand.gametype['base']
        self.allin = False
        self.allinThisStreet = False
        self.newpot = Decimal()
        # NOTE: Need a useful way to grab payouts
        #self.icm = ICM(stacks,payouts)
        #print icm.equities

        self.players = {}
        # print ('hand.players', hand.players)
        # print (type(hand.players))
        # print (type(self.players))
        # for name, chips, seat in hand.players[-1]:
        #     self.players.append(Player(name, chips, seat))
        #     #  self.players[name] = Player(hand, name, chips, seat)
        for items in hand.players:
            # print (items)
            # print ('type', (type(items)))
            # print (items[0])
            # print (items[1])
            # print (items[2])
            # print (items[3])
            
            self.players[items[1]] = Player(hand, items[1],items[2],int(items[0]))
            print (self.players[items[1]])


    def startPhase(self, phase):
        self.street = phase
        self.newpot = self.newpot
        if phase in ("BLINDSANTES", "PREFLOP", "DEAL"):
            return

        self.renderBoard.add(phase)

        for player in list(self.players.values()):
            player.justacted = False
            if player.chips > self.called:
                player.stack += player.chips - self.called
                player.chips = self.called
            self.pot += player.chips
            
            player.chips = Decimal(0)
            if phase in ("THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"):
                player.holecards = player.streetcards[self.street]
        self.bet = Decimal(0)
        self.called = Decimal(0)
        self.allinThisStreet = False

    def updateForAction(self, action):
        for player in list(self.players.values()):
            player.justacted = False

        player = self.players[action[0]]
        player.action = action[1]
        player.justacted = True
        if action[1] == "folds" or action[1] == "checks":
            pass
        elif action[1] == "raises" or action[1] == "bets":
            if self.allinThisStreet:
                self.called = Decimal(self.bet)
            else:
                self.called = Decimal(0)
            diff = self.bet - player.chips
            self.bet += action[2]
            player.chips += action[2] + diff
            player.stack -= action[2] + diff
            self.newpot += action[2] + diff
        elif action[1] == "big blind":
            self.bet = action[2]
            player.chips += action[2]
            player.stack -= action[2]
            self.newpot += action[2]
        elif action[1] == "calls" or action[1] == "small blind" or action[1] == "secondsb":
            player.chips += action[2]
            player.stack -= action[2]
            self.called = max(self.called, player.chips)
            self.newpot += action[2] 
        elif action[1] == "both":
            player.chips += action[2]
            player.stack -= action[2]
            self.newpot += action[2] 
        elif action[1] == "ante":
            self.pot += action[2]
            player.stack -= action[2]
            self.newpot += action[2]
        elif action[1] == "discards":
            player.action += " " + str(action[2])
            if len(action) > 3:
                # Must be hero as we have discard information.  Update holecards now.
                player.holecards = player.streetcards[self.street]
        elif action[1] == "stands pat":
            pass
        elif action[1] == "bringin":
            player.chips += action[2]
            player.stack -= action[2]
            self.newpot += action[2]
        else:
            print("unhandled action: " + str(action))

        if player.stack == 0:
            self.allinThisStreet = True

    def endHand(self, collectees, returned):
        self.pot = Decimal(0)
        for player in list(self.players.values()):
            player.justacted = False
            player.chips = Decimal(0)
            if self.gamebase == 'draw':
                player.holecards = player.streetcards[self.street]
        for name,amount in list(collectees.items()):
            player = self.players[name]
            player.chips += amount
            player.action = "collected"
            player.justacted = True
        for name, amount in list(returned.items()):
            self.players[name].stack += amount

class Player(object):
    def __init__(self, hand, name, stack, seat):
        self.stack     = Decimal(stack)
        self.chips     = Decimal(0)
        self.seat      = seat
        self.name      = name
        self.action    = None
        self.justacted = False
        self.holecards = hand.join_holecards(name, asList=True)
        self.streetcards = {}
        if hand.gametype['base'] == 'draw':
            for street in hand.actionStreets[1:]:
                self.streetcards[street] = hand.join_holecards(name, asList=True, street=street)
            self.holecards = self.streetcards[hand.actionStreets[1]]
        elif hand.gametype['base'] == 'stud':
            for i, street in enumerate(hand.actionStreets[1:]):
                self.streetcards[street] = self.holecards[:i + 3]
            self.holecards = self.streetcards[hand.actionStreets[1]]
        print('seat',seat)
        self.x         = 0.5 * cos(2 * self.seat * pi // hand.maxseats)
        self.y         = 0.8 * sin(2 * self.seat * pi // hand.maxseats)

if __name__ == '__main__':
    config = Configuration.Config()
    db = Database.Database(config)
    sql = SQL.Sql(db_server = config.get_db_parameters()['db-server'])

    from PyQt5.QtWidgets import QApplication
    app = QApplication([])
    handlist = [10, 39, 40, 72, 369, 390]
    replayer = GuiReplayer(config, sql, None, handlist)
    replayer.play_hand(0)

    app.exec_()
