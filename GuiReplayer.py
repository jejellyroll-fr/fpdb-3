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

from collections import defaultdict
from unicodedata import decimal, name
from past.utils import old_div
# import L10n
# _ = L10n.get_translation()

from functools import partial
import xml.dom.minidom

import json
import Hand
import Card
import Configuration
import Database
import SQL
import Deck
import Filters
import Charset

from PyQt5.QtCore import (QPoint, QRect, Qt, QTimer, QRectF)
from PyQt5.QtGui import (QColor, QImage, QPainter, QTextDocument)
from PyQt5.QtWidgets import (QHBoxLayout, QPushButton, QSlider, QVBoxLayout, QCheckBox,
                             QWidget)

from math import pi, cos, sin
from decimal_wrapper import Decimal
import numpy as np
from matplotlib import pyplot as plt
import copy
import os

CARD_HEIGHT = 90
CARD_WIDTH = 70


class GuiReplayer(QWidget):
    """A Replayer to replay hands."""

    def __init__(self, config, querylist, mainwin, handlist):
        QWidget.__init__(self, None)
        self.resize(1800, 1080)
        self.setMinimumSize(800, 600)
        self.conf = config
        self.main_window = mainwin
        self.sql = querylist
        self.newpot = Decimal()
        self.db = Database.Database(self.conf, sql=self.sql)
        self.states = []  # List with all table states.
        self.handlist = handlist
        self.handidx = 0
        self.Heroes = ""
        self.setWindowTitle("FPDB Hand Replayer")

        self.replayBox = QVBoxLayout()

        self.setLayout(self.replayBox)

        self.replayBox.addStretch()
        self.buttonBox2 = QHBoxLayout()
        self.buttonBox = QHBoxLayout()
        self.showCards = QCheckBox("Hide Cards")
        self.showCards.setChecked(True)
        self.buttonBox2.addWidget(self.showCards)
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
        self.replayBox.addLayout(self.buttonBox2)

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
            x += int(self.cardwidth / 2) - 15

    def renderboardCards(self, painter, cards, x, y):
        for card in cards:
            cardIndex = Card.encodeCard(card)
            painter.drawPixmap(QPoint(x, y), self.cardImages[cardIndex])
            x += self.cardwidth

    def paintEvent(self, event):
        hand = Hand.hand_factory(self.handlist[self.handidx], self.conf, self.db)
        if self.tableImage is None or self.playerBackdrop is None:
            try:
                self.playerBackdrop = QImage(os.path.join(self.conf.graphics_path, "playerbackdrop.png"))
                self.tableImage = QImage(os.path.join(self.conf.graphics_path, "TableR.png"))
                self.dealer = QImage(os.path.join(self.conf.graphics_path, "dealer.png"))
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
        # table position
        painter.drawImage(QPoint(200, 200), self.tableImage)

        # initial state
        if len(self.states) == 0:
            return

        state = self.states[self.stateSlider.value()]

        # communityLeft = int(old_div(self.tableImage.width(), 2) - 2.5 * self.cardwidth)
        # communityTop = int(old_div(self.tableImage.height(), 2) - 1.75 * self.cardheight)

        # convertx = lambda x: int(x * self.tableImage.width() * 0.8) + old_div(self.tableImage.width(), 2)
        # converty = lambda y: int(y * self.tableImage.height() * 0.6) + old_div(self.tableImage.height(), 2)
        # paint hand infos
        painter.drawText(QRect(-40, 0, 600, 80), Qt.AlignCenter, self.info)
        #
        nb_player = len(list(state.players.values()))
        #find hero in site
        path = os.path.join(Configuration.Config().config_path, "HUD_config.xml")
        print(path)
        doc = xml.dom.minidom.parse(path)
        for site_node in doc.getElementsByTagName("site"):
            if site_node.getAttribute("site_name") == str(hand.sitename):
                print(site_node.getAttribute("screen_name"))
                self.Heroes = site_node.getAttribute("screen_name")

        print("list players:", (list(state.players.values())))
        #print("list players:", self.Heroes)
        if nb_player == 2:
            # set 2 player
            print('nb player :', nb_player)
            i = 0
            for player in list(state.players.values()):
                #print(player.holecards)
                print(hand.gametype["category"])
                if player.name == list(state.players.values())[0].name:
                    print("round", i, "player", player.name)
                    # draw player bloc
                    painter.drawImage(QPoint(635, 790), self.playerBackdrop)
                    if player.action == "folds":
                        painter.setPen(QColor("red"))
                    else:
                        painter.setPen(QColor("white"))
                        # if check box hide cards and hero

                        if not self.showCards.isChecked():
                            # draw player's card
                            self.renderCards(painter, player.holecards, 660, 700)
                        elif self.showCards.isChecked():
                            if player.name == self.Heroes:

                                self.renderCards(painter, player.holecards, 660, 700)
                            else:
                                if hand.gametype["category"] == "omahahi" or "omahahilo" or "badugi" or "badacey" or "badeucey" or "irish" or "fusion" :
                                    self.renderCards(painter, ['0', '0', '0', '0'], 660, 700)
                                elif hand.gametype["category"] == "5_omahahi" or "5_omaha8" or "cour_hi" or "cour_hilo" or "27_1draw" or "27_3draw" or "a5_3draw" or "a5_1draw" or "drawmaha":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0'], 660, 700)
                                elif hand.gametype["category"] == "6_omahahi":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0', '0'], 660, 700)
                                elif hand.gametype["category"] == "holdem" or "6_holdem":
                                    self.renderCards(painter, ['0', '0'], 660, 700)
                                elif hand.gametype["category"] == "2_holdem":
                                    self.renderCards(painter, ['0', '0', '0'], 660, 700)
                                else:
                                    self.renderCards(painter, player.holecards, 660, 700)
                    # draw player's stack
                    painter.drawText(QRect(605, 790, 200, 20),
                                     Qt.AlignCenter,
                                     '%s %s%.2f' % (player.name,
                                                    self.currency,
                                                    player.stack))
                    if player.justacted:
                        painter.setPen(QColor("yellow"))
                        # draw player's actions
                        painter.drawText(QRect(605, 807, 200, 20), Qt.AlignCenter, player.action)
                        # draw pot
                        painter.drawText(QRect(380, 480, 200, 40), Qt.AlignCenter,
                                         'Pot: %s%.2f' % (self.currency, state.newpot))
                    else:
                        painter.setPen(QColor("white"))
                    if player.chips != 0:
                        # draw player's bet
                        painter.drawText(QRect(605, 670, 200, 20),
                                         Qt.AlignCenter,
                                         '%s%.2f' % (self.currency, player.chips))
                elif player.name == list(state.players.values())[1].name:
                    print("round", i, "player", player.name)
                    # draw player bloc
                    painter.drawImage(QPoint(1090, 490), self.playerBackdrop)
                    if player.action == "folds":
                        painter.setPen(QColor("red"))
                    else:
                        painter.setPen(QColor("white"))
                        # if check box hide cards and hero

                        if not self.showCards.isChecked():
                            # draw player's card
                            self.renderCards(painter, player.holecards, 1115, 400)
                        elif self.showCards.isChecked():
                            if player.name == self.Heroes:
                                self.renderCards(painter, player.holecards, 1115, 400)
                            else:
                                if hand.gametype["category"] == "omahahi" or "omahahilo" or "badugi" or "badacey" or "badeucey" or "irish" or "fusion":
                                    self.renderCards(painter, ['0', '0', '0', '0'], 1115, 400)
                                elif hand.gametype["category"] == "5_omahahi" or "5_omaha8" or "cour_hi" or "cour_hilo" or "27_1draw" or "27_3draw" or "a5_3draw" or "a5_1draw" or "drawmaha":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0'], 1115, 400)
                                elif hand.gametype["category"] == "6_omahahi":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0', '0'], 1115, 400)
                                elif hand.gametype["category"] == "holdem" or "6_holdem":
                                    self.renderCards(painter, ['0', '0'], 1115, 400)
                                elif hand.gametype["category"] == "2_holdem":
                                    self.renderCards(painter, ['0', '0', '0'], 1115, 400)
                                else:
                                    self.renderCards(painter, player.holecards, 1115, 400)

                    # draw player's info
                    painter.drawText(QRect(1070, 490, 200, 20),
                                     Qt.AlignCenter,
                                     '%s %s%.2f' % (player.name,
                                                    self.currency,
                                                    player.stack))
                    if player.justacted:
                        painter.setPen(QColor("yellow"))
                        # draw player's actions
                        painter.drawText(QRect(1070, 507, 200, 20), Qt.AlignCenter, player.action)
                        # draw bet pot
                        painter.drawText(QRect(380, 480, 200, 40),Qt.AlignCenter,
                                         'Pot: %s%.2f' % (self.currency, state.newpot))
                    else:
                        painter.setPen(QColor("white"))
                    if player.chips != 0:
                        # draw player's bet
                        painter.drawText(QRect(930, 490, 200, 20),
                                         Qt.AlignCenter,
                                         '%s%.2f' % (self.currency, player.chips))
                else:
                    pass
                i += 1
        elif nb_player == 3:
            print('nb player :', nb_player)
            i = 0
            for player in list(state.players.values()):
                #print(player.holecards)
                print(hand.gametype["category"])
                if player.name == list(state.players.values())[0].name:
                    if hand.get_player_position(player.name) == "S":
                        painter.drawImage(QPoint(530, 650), self.dealer.scaled(40, 40, Qt.KeepAspectRatio))
                    print("round", i, "player", player.name)
                    # draw player bloc

                    painter.drawImage(QPoint(635, 790), self.playerBackdrop)
                    if player.action == "folds":
                        painter.setPen(QColor("red"))
                    else:
                        painter.setPen(QColor("white"))
                        # if check box hide cards and hero
                        # show known cards or not
                        if not self.showCards.isChecked():

                            # draw player's card
                            self.renderCards(painter, player.holecards, 660, 700)
                        elif self.showCards.isChecked():
                            if player.name == self.Heroes:


                                self.renderCards(painter, player.holecards, 660, 700)
                            else:
                                if hand.gametype["category"] == "omahahi" or "omahahilo" or "badugi" or "badacey" or "badeucey" or "irish" or "fusion":
                                    self.renderCards(painter, ['0', '0', '0', '0'], 660, 700)
                                elif hand.gametype["category"] == "5_omahahi" or "5_omaha8" or "cour_hi" or "cour_hilo" or "27_1draw" or "27_3draw" or "a5_3draw" or "a5_1draw" or "drawmaha":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0'], 660, 700)
                                elif hand.gametype["category"] == "6_omahahi":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0', '0'], 660, 700)
                                elif hand.gametype["category"] == "holdem" or "6_holdem":
                                    self.renderCards(painter, ['0', '0'], 660, 700)
                                elif hand.gametype["category"] == "2_holdem":
                                    self.renderCards(painter, ['0', '0', '0'], 660, 700)
                                else:
                                    self.renderCards(painter, player.holecards, 660, 700)
                    # draw player's stack
                    painter.drawText(QRect(605, 790, 200, 20),
                                     Qt.AlignCenter,
                                     '%s %s%.2f' % (player.name,
                                                    self.currency,
                                                    player.stack))

                    if player.justacted:
                        painter.setPen(QColor("yellow"))
                        # draw player's actions
                        painter.drawText(QRect(605, 807, 200, 20), Qt.AlignCenter, player.action)
                        # draw pot
                        painter.drawText(QRect(380, 480, 200, 40), Qt.AlignCenter,
                                         'Pot: %s%.2f' % (self.currency, state.newpot))
                    else:
                        painter.setPen(QColor("white"))
                    if player.chips != 0:
                        # draw player's bet
                        painter.drawText(QRect(605, 670, 200, 20),
                                         Qt.AlignCenter,
                                         '%s%.2f' % (self.currency, player.chips))
                elif player.name == list(state.players.values())[1].name:
                    if hand.get_player_position(player.name) == "S":
                        painter.drawImage(QPoint(990, 570), self.dealer.scaled(40, 40, Qt.KeepAspectRatio)) #ok
                    print("round", i, "player", player.name)
                    # draw player bloc
                    painter.drawImage(QPoint(1090, 490), self.playerBackdrop)
                    if player.action == "folds":
                        painter.setPen(QColor("red"))
                    else:
                        painter.setPen(QColor("white"))
                        # if check box hide cards and hero

                        if not self.showCards.isChecked():
                            # draw player's card
                            self.renderCards(painter, player.holecards, 1115, 400)
                        elif self.showCards.isChecked():
                            if player.name == self.Heroes:
                                self.renderCards(painter, player.holecards, 1115, 400)
                            else:
                                if hand.gametype["category"] == "omahahi" or "omahahilo" or "badugi" or "badacey" or "badeucey" or "irish" or "fusion":
                                    self.renderCards(painter, ['0', '0', '0', '0'], 1115, 400)
                                elif hand.gametype["category"] == "5_omahahi" or "5_omaha8" or "cour_hi" or "cour_hilo" or "27_1draw" or "27_3draw" or "a5_3draw" or "a5_1draw" or "drawmaha":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0'], 1115, 400)
                                elif hand.gametype["category"] == "6_omahahi":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0', '0'], 1115, 400)
                                elif hand.gametype["category"] == "holdem" or "6_holdem":
                                    self.renderCards(painter, ['0', '0'], 1115, 400)
                                elif hand.gametype["category"] == "2_holdem":
                                    self.renderCards(painter, ['0', '0', '0'], 1115, 400)
                                else:
                                    self.renderCards(painter, player.holecards, 1115, 400)

                    # draw player's info
                    painter.drawText(QRect(1070, 490, 200, 20),
                                     Qt.AlignCenter,
                                     '%s %s%.2f' % (player.name,
                                                    self.currency,
                                                    player.stack))
                    if player.justacted:
                        painter.setPen(QColor("yellow"))
                        # draw player's actions
                        painter.drawText(QRect(1070, 507, 200, 20), Qt.AlignCenter, player.action)
                        # draw bet pot
                        painter.drawText(QRect(380, 480, 200, 40),Qt.AlignCenter,
                                         'Pot: %s%.2f' % (self.currency, state.newpot))
                    else:
                        painter.setPen(QColor("white"))
                    if player.chips != 0:
                        # draw player's bet
                        painter.drawText(QRect(930, 490, 200, 20),
                                         Qt.AlignCenter,
                                         '%s%.2f' % (self.currency, player.chips))
                elif player.name == list(state.players.values())[2].name:
                    if hand.get_player_position(player.name) == "S":
                        painter.drawImage(QPoint(450, 320), self.dealer.scaled(40, 40, Qt.KeepAspectRatio))
                    print(list(state.players.values())[2])
                    # draw player bloc
                    painter.drawImage(QPoint(160, 490), self.playerBackdrop)
                    if player.action == "folds":
                        painter.setPen(QColor("red"))
                    else:
                        painter.setPen(QColor("white"))
                        # if check box hide cards and hero

                        if not self.showCards.isChecked():
                            # draw player's card
                            self.renderCards(painter, player.holecards, 185, 400)
                        elif self.showCards.isChecked():
                            if player.name == self.Heroes:
                                self.renderCards(painter, player.holecards, 185, 400)
                            else:
                                if hand.gametype["category"] == "omahahi" or "omahahilo" or "badugi" or "badacey" or "badeucey" or "irish" or "fusion":
                                    self.renderCards(painter, ['0', '0', '0', '0'], 185, 400)
                                elif hand.gametype["category"] == "5_omahahi" or "5_omaha8" or "cour_hi" or "cour_hilo" or "27_1draw" or "27_3draw" or "a5_3draw" or "a5_1draw" or "drawmaha":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0'], 185, 400)
                                elif hand.gametype["category"] == "6_omahahi":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0', '0'], 185, 400)
                                elif hand.gametype["category"] == "holdem" or "6_holdem":
                                    self.renderCards(painter, ['0', '0'], 185, 400)
                                elif hand.gametype["category"] == "2_holdem":
                                    self.renderCards(painter, ['0', '0', '0'], 185, 400)
                                else:
                                    self.renderCards(painter, player.holecards, 185, 400)


                    # draw player's info
                    painter.drawText(QRect(140, 490, 200, 20),
                                     Qt.AlignCenter,
                                     '%s %s%.2f' % (player.name,
                                                    self.currency,
                                                    player.stack))
                    if player.justacted:
                        painter.setPen(QColor("yellow"))
                        # draw player's actions
                        painter.drawText(QRect(140, 507, 200, 20), Qt.AlignCenter, player.action)
                        # draw bet pot
                        painter.drawText(QRect(380, 480, 200, 40),Qt.AlignCenter,
                                         'Pot: %s%.2f' % (self.currency, state.newpot))
                    else:
                        painter.setPen(QColor("white"))
                    if player.chips != 0:
                        # draw player's bet
                        painter.drawText(QRect(260, 490, 200, 20),
                                         Qt.AlignCenter,
                                         '%s%.2f' % (self.currency, player.chips))
                else:
                    pass
                i += 1
        elif nb_player == 4:
            print('nb player :', nb_player)
            i = 0
            for player in list(state.players.values()):
                # print(player.holecards)
                print(hand.gametype["category"])
                if player.name == list(state.players.values())[0].name:
                    if hand.get_player_position(player.name) == "S":
                        painter.drawImage(QPoint(530, 650), self.dealer.scaled(40, 40, Qt.KeepAspectRatio))
                    print("round", i, "player", player.name)
                    # draw player bloc
                    painter.drawImage(QPoint(635, 790), self.playerBackdrop)
                    if player.action == "folds":
                        painter.setPen(QColor("red"))
                    else:
                        painter.setPen(QColor("white"))
                        # if check box hide cards and hero

                        if not self.showCards.isChecked():
                            # draw player's card
                            self.renderCards(painter, player.holecards, 660, 700)
                        elif self.showCards.isChecked():
                            if player.name == self.Heroes:

                                self.renderCards(painter, player.holecards, 660, 700)
                            else:
                                if hand.gametype[
                                    "category"] == "omahahi" or "omahahilo" or "badugi" or "badacey" or "badeucey" or "irish" or "fusion":
                                    self.renderCards(painter, ['0', '0', '0', '0'], 660, 700)
                                elif hand.gametype[
                                    "category"] == "5_omahahi" or "5_omaha8" or "cour_hi" or "cour_hilo" or "27_1draw" or "27_3draw" or "a5_3draw" or "a5_1draw" or "drawmaha":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0'], 660, 700)
                                elif hand.gametype["category"] == "6_omahahi":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0', '0'], 660, 700)
                                elif hand.gametype["category"] == "holdem" or "6_holdem":
                                    self.renderCards(painter, ['0', '0'], 660, 700)
                                elif hand.gametype["category"] == "2_holdem":
                                    self.renderCards(painter, ['0', '0', '0'], 660, 700)
                                else:
                                    self.renderCards(painter, player.holecards, 660, 700)
                    # draw player's stack
                    painter.drawText(QRect(605, 790, 200, 20),
                                     Qt.AlignCenter,
                                     '%s %s%.2f' % (player.name,
                                                    self.currency,
                                                    player.stack))

                    if player.justacted:
                        painter.setPen(QColor("yellow"))
                        # draw player's actions
                        painter.drawText(QRect(605, 807, 200, 20), Qt.AlignCenter, player.action)
                        # draw pot
                        painter.drawText(QRect(380, 480, 200, 40), Qt.AlignCenter,
                                         'Pot: %s%.2f' % (self.currency, state.newpot))
                    else:
                        painter.setPen(QColor("white"))
                    if player.chips != 0:
                        # draw player's bet
                        painter.drawText(QRect(605, 670, 200, 20),
                                         Qt.AlignCenter,
                                         '%s%.2f' % (self.currency, player.chips))
                elif player.name == list(state.players.values())[1].name:
                    if hand.get_player_position(player.name) == "S":
                        painter.drawImage(QPoint(990, 570), self.dealer.scaled(40, 40, Qt.KeepAspectRatio))  # ok
                    print("round", i, "player", player.name)
                    # draw player bloc
                    painter.drawImage(QPoint(1090, 490), self.playerBackdrop)
                    if player.action == "folds":
                        painter.setPen(QColor("red"))
                    else:
                        painter.setPen(QColor("white"))
                        # if check box hide cards and hero

                        if not self.showCards.isChecked():
                            # draw player's card
                            self.renderCards(painter, player.holecards, 1115, 400)
                        elif self.showCards.isChecked():
                            if player.name == self.Heroes:
                                self.renderCards(painter, player.holecards, 1115, 400)
                            else:
                                if hand.gametype[
                                    "category"] == "omahahi" or "omahahilo" or "badugi" or "badacey" or "badeucey" or "irish" or "fusion":
                                    self.renderCards(painter, ['0', '0', '0', '0'], 1115, 400)
                                elif hand.gametype[
                                    "category"] == "5_omahahi" or "5_omaha8" or "cour_hi" or "cour_hilo" or "27_1draw" or "27_3draw" or "a5_3draw" or "a5_1draw" or "drawmaha":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0'], 1115, 400)
                                elif hand.gametype["category"] == "6_omahahi":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0', '0'], 1115, 400)
                                elif hand.gametype["category"] == "holdem" or "6_holdem":
                                    self.renderCards(painter, ['0', '0'], 1115, 400)
                                elif hand.gametype["category"] == "2_holdem":
                                    self.renderCards(painter, ['0', '0', '0'], 1115, 400)
                                else:
                                    self.renderCards(painter, player.holecards, 1115, 400)

                    # draw player's info
                    painter.drawText(QRect(1070, 490, 200, 20),
                                     Qt.AlignCenter,
                                     '%s %s%.2f' % (player.name,
                                                    self.currency,
                                                    player.stack))
                    if player.justacted:
                        painter.setPen(QColor("yellow"))
                        # draw player's actions
                        painter.drawText(QRect(1070, 507, 200, 20), Qt.AlignCenter, player.action)
                        # draw bet pot
                        painter.drawText(QRect(380, 480, 200, 40),Qt.AlignCenter,
                                         'Pot: %s%.2f' % (self.currency, state.newpot))
                    else:
                        painter.setPen(QColor("white"))
                    if player.chips != 0:
                        # draw player's bet
                        painter.drawText(QRect(930, 490, 200, 20),
                                         Qt.AlignCenter,
                                         '%s%.2f' % (self.currency, player.chips))
                elif player.name == list(state.players.values())[2].name:
                    if hand.get_player_position(player.name) == "S":
                        painter.drawImage(QPoint(850, 320), self.dealer.scaled(40, 40, Qt.KeepAspectRatio))
                    print(list(state.players.values())[2])
                    # draw player bloc
                    painter.drawImage(QPoint(635, 220), self.playerBackdrop) #
                    if player.action == "folds":
                        painter.setPen(QColor("red"))
                    else:
                        painter.setPen(QColor("white"))
                        # if check box hide cards and hero

                        if not self.showCards.isChecked():
                            # draw player's card
                            self.renderCards(painter, player.holecards, 655, 130) #ok
                        elif self.showCards.isChecked():
                            if player.name == self.Heroes:
                                self.renderCards(painter, player.holecards, 655, 130)
                            else:
                                if hand.gametype[
                                    "category"] == "omahahi" or "omahahilo" or "badugi" or "badacey" or "badeucey" or "irish" or "fusion":
                                    self.renderCards(painter, ['0', '0', '0', '0'], 655, 130)
                                elif hand.gametype[
                                    "category"] == "5_omahahi" or "5_omaha8" or "cour_hi" or "cour_hilo" or "27_1draw" or "27_3draw" or "a5_3draw" or "a5_1draw" or "drawmaha":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0'], 655, 130)
                                elif hand.gametype["category"] == "6_omahahi":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0', '0'], 655, 130)
                                elif hand.gametype["category"] == "holdem" or "6_holdem":
                                    self.renderCards(painter, ['0', '0'], 655, 130)
                                elif hand.gametype["category"] == "2_holdem":
                                    self.renderCards(painter, ['0', '0', '0'], 655, 130)
                                else:
                                    self.renderCards(painter, player.holecards, 655, 130)

                    # draw player's info
                    painter.drawText(QRect(605, 220, 200, 20),
                                     Qt.AlignCenter,
                                     '%s %s%.2f' % (player.name,
                                                    self.currency,
                                                    player.stack))
                    if player.justacted:
                        painter.setPen(QColor("yellow"))
                        # draw player's actions
                        painter.drawText(QRect(605, 237, 200, 20), Qt.AlignCenter, player.action)
                        # draw bet pot
                        painter.drawText(QRect(380, 480, 200, 40),Qt.AlignCenter,
                                         'Pot: %s%.2f' % (self.currency, state.newpot))
                    else:
                        painter.setPen(QColor("white"))
                    if player.chips != 0:
                        # draw player's bet
                        painter.drawText(QRect(605, 294, 200, 20),
                                         Qt.AlignCenter,
                                         '%s%.2f' % (self.currency, player.chips))
                elif player.name == list(state.players.values())[3].name:
                    if hand.get_player_position(player.name) == "S":
                        painter.drawImage(QPoint(450, 320), self.dealer.scaled(40, 40, Qt.KeepAspectRatio))
                    print(list(state.players.values())[2])
                    # draw player bloc
                    painter.drawImage(QPoint(160, 490), self.playerBackdrop)
                    if player.action == "folds":
                        painter.setPen(QColor("red"))
                    else:
                        painter.setPen(QColor("white"))
                        # if check box hide cards and hero

                        if not self.showCards.isChecked():
                            # draw player's card
                            self.renderCards(painter, player.holecards, 185, 400)
                        elif self.showCards.isChecked():
                            if player.name == self.Heroes:
                                self.renderCards(painter, player.holecards, 185, 400)
                            else:
                                if hand.gametype[
                                    "category"] == "omahahi" or "omahahilo" or "badugi" or "badacey" or "badeucey" or "irish" or "fusion":
                                    self.renderCards(painter, ['0', '0', '0', '0'], 185, 400)
                                elif hand.gametype[
                                    "category"] == "5_omahahi" or "5_omaha8" or "cour_hi" or "cour_hilo" or "27_1draw" or "27_3draw" or "a5_3draw" or "a5_1draw" or "drawmaha":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0'], 185, 400)
                                elif hand.gametype["category"] == "6_omahahi":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0', '0'], 185, 400)
                                elif hand.gametype["category"] == "holdem" or "6_holdem":
                                    self.renderCards(painter, ['0', '0'], 185, 400)
                                elif hand.gametype["category"] == "2_holdem":
                                    self.renderCards(painter, ['0', '0', '0'], 185, 400)
                                else:
                                    self.renderCards(painter, player.holecards, 185, 400)

                    # draw player's info
                    painter.drawText(QRect(140, 490, 200, 20),
                                     Qt.AlignCenter,
                                     '%s %s%.2f' % (player.name,
                                                    self.currency,
                                                    player.stack))
                    if player.justacted:
                        painter.setPen(QColor("yellow"))
                        # draw player's actions
                        painter.drawText(QRect(140, 507, 200, 20), Qt.AlignCenter, player.action)
                        # draw bet pot
                        painter.drawText(QRect(380, 480, 200, 40),Qt.AlignCenter,
                                         'Pot: %s%.2f' % (self.currency, state.newpot))
                    else:
                        painter.setPen(QColor("white"))
                    if player.chips != 0:
                        # draw player's bet
                        painter.drawText(QRect(260, 490, 200, 20),
                                         Qt.AlignCenter,
                                         '%s%.2f' % (self.currency, player.chips))
                else:
                    pass
                i += 1
        elif nb_player == 5:
            print('nb player :', nb_player)
            i = 0
            for player in list(state.players.values()):
                # print(player.holecards)
                print(hand.gametype["category"])
                if player.name == list(state.players.values())[0].name:
                    if hand.get_player_position(player.name) == "S":
                        painter.drawImage(QPoint(530, 650), self.dealer.scaled(40, 40, Qt.KeepAspectRatio))
                    print("round", i, "player", player.name)
                    # draw player bloc
                    painter.drawImage(QPoint(635, 790), self.playerBackdrop)
                    if player.action == "folds":
                        painter.setPen(QColor("red"))
                    else:
                        painter.setPen(QColor("white"))
                        # if check box hide cards and hero

                        if not self.showCards.isChecked():
                            # draw player's card
                            self.renderCards(painter, player.holecards, 660, 700)
                        elif self.showCards.isChecked():
                            if player.name == self.Heroes:

                                self.renderCards(painter, player.holecards, 660, 700)
                            else:
                                if hand.gametype[
                                    "category"] == "omahahi" or "omahahilo" or "badugi" or "badacey" or "badeucey" or "irish" or "fusion":
                                    self.renderCards(painter, ['0', '0', '0', '0'], 660, 700)
                                elif hand.gametype[
                                    "category"] == "5_omahahi" or "5_omaha8" or "cour_hi" or "cour_hilo" or "27_1draw" or "27_3draw" or "a5_3draw" or "a5_1draw" or "drawmaha":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0'], 660, 700)
                                elif hand.gametype["category"] == "6_omahahi":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0', '0'], 660, 700)
                                elif hand.gametype["category"] == "holdem" or "6_holdem":
                                    self.renderCards(painter, ['0', '0'], 660, 700)
                                elif hand.gametype["category"] == "2_holdem":
                                    self.renderCards(painter, ['0', '0', '0'], 660, 700)
                                else:
                                    self.renderCards(painter, player.holecards, 660, 700)
                    # draw player's stack
                    painter.drawText(QRect(605, 790, 200, 20),
                                     Qt.AlignCenter,
                                     '%s %s%.2f' % (player.name,
                                                    self.currency,
                                                    player.stack))

                    if player.justacted:
                        painter.setPen(QColor("yellow"))
                        # draw player's actions
                        painter.drawText(QRect(605, 807, 200, 20), Qt.AlignCenter, player.action)
                        # draw pot
                        painter.drawText(QRect(380, 480, 200, 40), Qt.AlignCenter,
                                         'Pot: %s%.2f' % (self.currency, state.newpot))
                    else:
                        painter.setPen(QColor("white"))
                    if player.chips != 0:
                        # draw player's bet
                        painter.drawText(QRect(605, 670, 200, 20),
                                         Qt.AlignCenter,
                                         '%s%.2f' % (self.currency, player.chips))
                elif player.name == list(state.players.values())[1].name:
                    if hand.get_player_position(player.name) == "S":
                        painter.drawImage(QPoint(990, 570), self.dealer.scaled(40, 40, Qt.KeepAspectRatio))  # ok
                    print("round", i, "player", player.name)
                    # draw player bloc
                    painter.drawImage(QPoint(1090, 490), self.playerBackdrop)
                    if player.action == "folds":
                        painter.setPen(QColor("red"))
                    else:
                        painter.setPen(QColor("white"))
                        # if check box hide cards and hero

                        if not self.showCards.isChecked():
                            # draw player's card
                            self.renderCards(painter, player.holecards, 1115, 400)
                        elif self.showCards.isChecked():
                            if player.name == self.Heroes:
                                self.renderCards(painter, player.holecards, 1115, 400)
                            else:
                                if hand.gametype[
                                    "category"] == "omahahi" or "omahahilo" or "badugi" or "badacey" or "badeucey" or "irish" or "fusion":
                                    self.renderCards(painter, ['0', '0', '0', '0'], 1115, 400)
                                elif hand.gametype[
                                    "category"] == "5_omahahi" or "5_omaha8" or "cour_hi" or "cour_hilo" or "27_1draw" or "27_3draw" or "a5_3draw" or "a5_1draw" or "drawmaha":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0'], 1115, 400)
                                elif hand.gametype["category"] == "6_omahahi":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0', '0'], 1115, 400)
                                elif hand.gametype["category"] == "holdem" or "6_holdem":
                                    self.renderCards(painter, ['0', '0'], 1115, 400)
                                elif hand.gametype["category"] == "2_holdem":
                                    self.renderCards(painter, ['0', '0', '0'], 1115, 400)
                                else:
                                    self.renderCards(painter, player.holecards, 1115, 400)

                    # draw player's info
                    painter.drawText(QRect(1070, 490, 200, 20),
                                     Qt.AlignCenter,
                                     '%s %s%.2f' % (player.name,
                                                    self.currency,
                                                    player.stack))
                    if player.justacted:
                        painter.setPen(QColor("yellow"))
                        # draw player's actions
                        painter.drawText(QRect(1070, 507, 200, 20), Qt.AlignCenter, player.action)
                        # draw bet pot
                        painter.drawText(QRect(380, 480, 200, 40),Qt.AlignCenter,
                                         'Pot: %s%.2f' % (self.currency, state.newpot))
                    else:
                        painter.setPen(QColor("white"))
                    if player.chips != 0:
                        # draw player's bet
                        painter.drawText(QRect(930, 490, 200, 20),
                                         Qt.AlignCenter,
                                         '%s%.2f' % (self.currency, player.chips))
                elif player.name == list(state.players.values())[3].name:
                    if hand.get_player_position(player.name) == "S":
                        painter.drawImage(QPoint(660, 320), self.dealer.scaled(40, 40, Qt.KeepAspectRatio))
                    print(list(state.players.values())[2])
                    # draw player bloc
                    painter.drawImage(QPoint(500, 220), self.playerBackdrop) #ok
                    if player.action == "folds":
                        painter.setPen(QColor("red"))
                    else:
                        painter.setPen(QColor("white"))
                        # if check box hide cards and hero

                        if not self.showCards.isChecked():
                            # draw player's card
                            self.renderCards(painter, player.holecards, 520, 130) #ok
                        elif self.showCards.isChecked():
                            if player.name == self.Heroes:
                                self.renderCards(painter, player.holecards, 520, 130)
                            else:
                                if hand.gametype[
                                    "category"] == "omahahi" or "omahahilo" or "badugi" or "badacey" or "badeucey" or "irish" or "fusion":
                                    self.renderCards(painter, ['0', '0', '0', '0'], 520, 130)
                                elif hand.gametype[
                                    "category"] == "5_omahahi" or "5_omaha8" or "cour_hi" or "cour_hilo" or "27_1draw" or "27_3draw" or "a5_3draw" or "a5_1draw" or "drawmaha":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0'], 520, 130)
                                elif hand.gametype["category"] == "6_omahahi":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0', '0'], 520, 130)
                                elif hand.gametype["category"] == "holdem" or "6_holdem":
                                    self.renderCards(painter, ['0', '0'], 520, 130)
                                elif hand.gametype["category"] == "2_holdem":
                                    self.renderCards(painter, ['0', '0', '0'], 520, 130)
                                else:
                                    self.renderCards(painter, player.holecards, 520, 130)

                    # draw player's info
                    painter.drawText(QRect(480, 220, 200, 20),
                                     Qt.AlignCenter,
                                     '%s %s%.2f' % (player.name,
                                                    self.currency,
                                                    player.stack))
                    if player.justacted:
                        painter.setPen(QColor("yellow"))
                        # draw player's actions
                        painter.drawText(QRect(480, 237, 200, 20), Qt.AlignCenter, player.action)
                        # draw bet pot
                        painter.drawText(QRect(380, 480, 200, 40),Qt.AlignCenter,
                                         'Pot: %s%.2f' % (self.currency, state.newpot))
                    else:
                        painter.setPen(QColor("white"))
                    if player.chips != 0:
                        # draw player's bet
                        painter.drawText(QRect(500, 294, 200, 20),
                                         Qt.AlignCenter,
                                         '%s%.2f' % (self.currency, player.chips))
                elif player.name == list(state.players.values())[2].name:
                    if hand.get_player_position(player.name) == "S":
                        painter.drawImage(QPoint(950, 350), self.dealer.scaled(40, 40, Qt.KeepAspectRatio))
                    print(list(state.players.values())[2])
                    # draw player bloc
                    painter.drawImage(QPoint(750, 220), self.playerBackdrop) #ok
                    if player.action == "folds":
                        painter.setPen(QColor("red"))
                    else:
                        painter.setPen(QColor("white"))
                        # if check box hide cards and hero

                        if not self.showCards.isChecked():
                            # draw player's card
                            self.renderCards(painter, player.holecards, 770, 130) #ok
                        elif self.showCards.isChecked():
                            if player.name == self.Heroes:
                                self.renderCards(painter, player.holecards, 770, 130)
                            else:
                                if hand.gametype[
                                    "category"] == "omahahi" or "omahahilo" or "badugi" or "badacey" or "badeucey" or "irish" or "fusion":
                                    self.renderCards(painter, ['0', '0', '0', '0'], 770, 130)
                                elif hand.gametype[
                                    "category"] == "5_omahahi" or "5_omaha8" or "cour_hi" or "cour_hilo" or "27_1draw" or "27_3draw" or "a5_3draw" or "a5_1draw" or "drawmaha":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0'], 770, 130)
                                elif hand.gametype["category"] == "6_omahahi":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0', '0'], 770, 130)
                                elif hand.gametype["category"] == "holdem" or "6_holdem":
                                    self.renderCards(painter, ['0', '0'], 770, 130)
                                elif hand.gametype["category"] == "2_holdem":
                                    self.renderCards(painter, ['0', '0', '0'], 770, 130)
                                else:
                                    self.renderCards(painter, player.holecards, 770, 130)

                    # draw player's info
                    painter.drawText(QRect(730, 220, 200, 20),
                                     Qt.AlignCenter,
                                     '%s %s%.2f' % (player.name,
                                                    self.currency,
                                                    player.stack))
                    if player.justacted:
                        painter.setPen(QColor("yellow"))
                        # draw player's actions
                        painter.drawText(QRect(730, 237, 200, 20), Qt.AlignCenter, player.action)
                        # draw bet pot
                        painter.drawText(QRect(380, 480, 200, 40),Qt.AlignCenter,
                                         'Pot: %s%.2f' % (self.currency, state.newpot))
                    else:
                        painter.setPen(QColor("white"))
                    if player.chips != 0:
                        # draw player's bet
                        painter.drawText(QRect(730, 294, 200, 20),
                                         Qt.AlignCenter,
                                         '%s%.2f' % (self.currency, player.chips))
                elif player.name == list(state.players.values())[4].name:
                    if hand.get_player_position(player.name) == "S":
                        painter.drawImage(QPoint(450, 320), self.dealer.scaled(40, 40, Qt.KeepAspectRatio))
                    print(list(state.players.values())[2])
                    # draw player bloc
                    painter.drawImage(QPoint(160, 490), self.playerBackdrop)
                    if player.action == "folds":
                        painter.setPen(QColor("red"))
                    else:
                        painter.setPen(QColor("white"))
                        # if check box hide cards and hero

                        if not self.showCards.isChecked():
                            # draw player's card
                            self.renderCards(painter, player.holecards, 185, 400)
                        elif self.showCards.isChecked():
                            if player.name == self.Heroes:
                                self.renderCards(painter, player.holecards, 185, 400)
                            else:
                                if hand.gametype[
                                    "category"] == "omahahi" or "omahahilo" or "badugi" or "badacey" or "badeucey" or "irish" or "fusion":
                                    self.renderCards(painter, ['0', '0', '0', '0'], 185, 400)
                                elif hand.gametype[
                                    "category"] == "5_omahahi" or "5_omaha8" or "cour_hi" or "cour_hilo" or "27_1draw" or "27_3draw" or "a5_3draw" or "a5_1draw" or "drawmaha":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0'], 185, 400)
                                elif hand.gametype["category"] == "6_omahahi":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0', '0'], 185, 400)
                                elif hand.gametype["category"] == "holdem" or "6_holdem":
                                    self.renderCards(painter, ['0', '0'], 185, 400)
                                elif hand.gametype["category"] == "2_holdem":
                                    self.renderCards(painter, ['0', '0', '0'], 185, 400)
                                else:
                                    self.renderCards(painter, player.holecards, 185, 400)

                    # draw player's info
                    painter.drawText(QRect(140, 490, 200, 20),
                                     Qt.AlignCenter,
                                     '%s %s%.2f' % (player.name,
                                                    self.currency,
                                                    player.stack))
                    if player.justacted:
                        painter.setPen(QColor("yellow"))
                        # draw player's actions
                        painter.drawText(QRect(140, 507, 200, 20), Qt.AlignCenter, player.action)
                        # draw bet pot
                        painter.drawText(QRect(380, 480, 200, 40),Qt.AlignCenter,
                                         'Pot: %s%.2f' % (self.currency, state.newpot))
                    else:
                        painter.setPen(QColor("white"))
                    if player.chips != 0:
                        # draw player's bet
                        painter.drawText(QRect(260, 490, 200, 20),
                                         Qt.AlignCenter,
                                         '%s%.2f' % (self.currency, player.chips))
                else:
                    pass
                i += 1
        elif nb_player == 6:
            print('nb player :', nb_player)
            i = 0
            for player in list(state.players.values()):
                # print(player.holecards)
                print(hand.gametype["category"])
                if player.name == list(state.players.values())[0].name:
                    if hand.get_player_position(player.name) == "S":
                        painter.drawImage(QPoint(650, 650), self.dealer.scaled(40, 40, Qt.KeepAspectRatio))
                    print("round", i, "player", player.name)
                    # draw player bloc
                    painter.drawImage(QPoint(750, 790), self.playerBackdrop)
                    if player.action == "folds":
                        painter.setPen(QColor("red"))
                    else:
                        painter.setPen(QColor("white"))
                        # if check box hide cards and hero

                        if not self.showCards.isChecked():
                            # draw player's card
                            self.renderCards(painter, player.holecards, 770, 700)
                        elif self.showCards.isChecked():
                            if player.name == self.Heroes:

                                self.renderCards(painter, player.holecards, 770, 700)
                            else:
                                if hand.gametype[
                                    "category"] == "omahahi" or "omahahilo" or "badugi" or "badacey" or "badeucey" or "irish" or "fusion":
                                    self.renderCards(painter, ['0', '0', '0', '0'], 770, 700)
                                elif hand.gametype[
                                    "category"] == "5_omahahi" or "5_omaha8" or "cour_hi" or "cour_hilo" or "27_1draw" or "27_3draw" or "a5_3draw" or "a5_1draw" or "drawmaha":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0'], 770, 700)
                                elif hand.gametype["category"] == "6_omahahi":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0', '0'], 770, 700)
                                elif hand.gametype["category"] == "holdem" or "6_holdem":
                                    self.renderCards(painter, ['0', '0'], 770, 700)
                                elif hand.gametype["category"] == "2_holdem":
                                    self.renderCards(painter, ['0', '0', '0'], 770, 700)
                                else:
                                    self.renderCards(painter, player.holecards, 770, 700)
                    # draw player's stack
                    painter.drawText(QRect(730, 790, 200, 20),
                                     Qt.AlignCenter,
                                     '%s %s%.2f' % (player.name,
                                                    self.currency,
                                                    player.stack))

                    if player.justacted:
                        painter.setPen(QColor("yellow"))
                        # draw player's actions
                        painter.drawText(QRect(730, 807, 200, 20), Qt.AlignCenter, player.action)
                        # draw pot
                        
                        painter.drawText(QRect(380, 480, 200, 40), Qt.AlignCenter,
                                         'Pot: %s%.2f' % (self.currency, state.newpot))
                    else:
                        painter.setPen(QColor("white"))
                    if player.chips != 0:
                        # draw player's bet
                        painter.drawText(QRect(730, 670, 200, 20),
                                         Qt.AlignCenter,
                                         '%s%.2f' % (self.currency, player.chips))
                elif player.name == list(state.players.values())[1].name:
                    if hand.get_player_position(player.name) == "S":
                        painter.drawImage(QPoint(990, 570), self.dealer.scaled(40, 40, Qt.KeepAspectRatio))  # ok
                    print("round", i, "player", player.name)
                    # draw player bloc
                    painter.drawImage(QPoint(1090, 490), self.playerBackdrop)
                    if player.action == "folds":
                        painter.setPen(QColor("red"))
                    else:
                        painter.setPen(QColor("white"))
                        # if check box hide cards and hero

                        if not self.showCards.isChecked():
                            # draw player's card
                            self.renderCards(painter, player.holecards, 1115, 400)
                        elif self.showCards.isChecked():
                            if player.name == self.Heroes:
                                self.renderCards(painter, player.holecards, 1115, 400)
                            else:
                                if hand.gametype[
                                    "category"] == "omahahi" or "omahahilo" or "badugi" or "badacey" or "badeucey" or "irish" or "fusion":
                                    self.renderCards(painter, ['0', '0', '0', '0'], 1115, 400)
                                elif hand.gametype[
                                    "category"] == "5_omahahi" or "5_omaha8" or "cour_hi" or "cour_hilo" or "27_1draw" or "27_3draw" or "a5_3draw" or "a5_1draw" or "drawmaha":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0'], 1115, 400)
                                elif hand.gametype["category"] == "6_omahahi":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0', '0'], 1115, 400)
                                elif hand.gametype["category"] == "holdem" or "6_holdem":
                                    self.renderCards(painter, ['0', '0'], 1115, 400)
                                elif hand.gametype["category"] == "2_holdem":
                                    self.renderCards(painter, ['0', '0', '0'], 1115, 400)
                                else:
                                    self.renderCards(painter, player.holecards, 1115, 400)

                    # draw player's info
                    painter.drawText(QRect(1070, 490, 200, 20),
                                     Qt.AlignCenter,
                                     '%s %s%.2f' % (player.name,
                                                    self.currency,
                                                    player.stack))
                    if player.justacted:
                        painter.setPen(QColor("yellow"))
                        # draw player's actions
                        painter.drawText(QRect(1070, 507, 200, 20), Qt.AlignCenter, player.action)
                        # draw bet pot
                        
                        painter.drawText(QRect(380, 480, 200, 40),Qt.AlignCenter,
                                         'Pot: %s%.2f' % (self.currency, state.newpot))
                    else:
                        painter.setPen(QColor("white"))
                    if player.chips != 0:
                        # draw player's bet
                        painter.drawText(QRect(930, 490, 200, 20),
                                         Qt.AlignCenter,
                                         '%s%.2f' % (self.currency, player.chips))
                elif player.name == list(state.players.values())[3].name:
                    if hand.get_player_position(player.name) == "S":
                        painter.drawImage(QPoint(660, 320), self.dealer.scaled(40, 40, Qt.KeepAspectRatio))
                    print("round", i, "player", player.name)
                    print(list(state.players.values())[2])
                    # draw player bloc
                    painter.drawImage(QPoint(500, 220), self.playerBackdrop) #ok
                    if player.action == "folds":
                        painter.setPen(QColor("red"))
                    else:
                        painter.setPen(QColor("white"))
                        # if check box hide cards and hero

                        if not self.showCards.isChecked():
                            # draw player's card
                            self.renderCards(painter, player.holecards, 520, 130) #ok
                        elif self.showCards.isChecked():
                            if player.name == self.Heroes:
                                self.renderCards(painter, player.holecards, 520, 130)
                            else:
                                if hand.gametype[
                                    "category"] == "omahahi" or "omahahilo" or "badugi" or "badacey" or "badeucey" or "irish" or "fusion":
                                    self.renderCards(painter, ['0', '0', '0', '0'], 520, 130)
                                elif hand.gametype[
                                    "category"] == "5_omahahi" or "5_omaha8" or "cour_hi" or "cour_hilo" or "27_1draw" or "27_3draw" or "a5_3draw" or "a5_1draw" or "drawmaha":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0'], 520, 130)
                                elif hand.gametype["category"] == "6_omahahi":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0', '0'], 520, 130)
                                elif hand.gametype["category"] == "holdem" or "6_holdem":
                                    self.renderCards(painter, ['0', '0'], 520, 130)
                                elif hand.gametype["category"] == "2_holdem":
                                    self.renderCards(painter, ['0', '0', '0'], 520, 130)
                                else:
                                    self.renderCards(painter, player.holecards, 520, 130)

                    # draw player's info
                    painter.drawText(QRect(480, 220, 200, 20),
                                     Qt.AlignCenter,
                                     '%s %s%.2f' % (player.name,
                                                    self.currency,
                                                    player.stack))
                    if player.justacted:
                        painter.setPen(QColor("yellow"))
                        # draw player's actions
                        painter.drawText(QRect(480, 237, 200, 20), Qt.AlignCenter, player.action)
                        # draw bet pot
                        painter.drawText(QRect(380, 480, 200, 40),Qt.AlignCenter,
                                         'Pot: %s%.2f' % (self.currency, state.newpot))
                    else:
                        painter.setPen(QColor("white"))
                    if player.chips != 0:
                        # draw player's bet
                        painter.drawText(QRect(500, 294, 200, 20),
                                         Qt.AlignCenter,
                                         '%s%.2f' % (self.currency, player.chips))
                elif player.name == list(state.players.values())[2].name:
                    if hand.get_player_position(player.name) == "S":
                        painter.drawImage(QPoint(950, 350), self.dealer.scaled(40, 40, Qt.KeepAspectRatio))
                    print("round", i, "player", player.name)
                    print(list(state.players.values())[2])
                    # draw player bloc
                    painter.drawImage(QPoint(750, 220), self.playerBackdrop) #ok
                    if player.action == "folds":
                        painter.setPen(QColor("red"))
                    else:
                        painter.setPen(QColor("white"))
                        # if check box hide cards and hero

                        if not self.showCards.isChecked():
                            # draw player's card
                            self.renderCards(painter, player.holecards, 770, 130) #ok
                        elif self.showCards.isChecked():
                            if player.name == self.Heroes:
                                self.renderCards(painter, player.holecards, 770, 130)
                            else:
                                if hand.gametype[
                                    "category"] == "omahahi" or "omahahilo" or "badugi" or "badacey" or "badeucey" or "irish" or "fusion":
                                    self.renderCards(painter, ['0', '0', '0', '0'], 770, 130)
                                elif hand.gametype[
                                    "category"] == "5_omahahi" or "5_omaha8" or "cour_hi" or "cour_hilo" or "27_1draw" or "27_3draw" or "a5_3draw" or "a5_1draw" or "drawmaha":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0'], 770, 130)
                                elif hand.gametype["category"] == "6_omahahi":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0', '0'], 770, 130)
                                elif hand.gametype["category"] == "holdem" or "6_holdem":
                                    self.renderCards(painter, ['0', '0'], 770, 130)
                                elif hand.gametype["category"] == "2_holdem":
                                    self.renderCards(painter, ['0', '0', '0'], 770, 130)
                                else:
                                    self.renderCards(painter, player.holecards, 770, 130)

                    # draw player's info
                    painter.drawText(QRect(730, 220, 200, 20),
                                     Qt.AlignCenter,
                                     '%s %s%.2f' % (player.name,
                                                    self.currency,
                                                    player.stack))
                    if player.justacted:
                        painter.setPen(QColor("yellow"))
                        # draw player's actions
                        painter.drawText(QRect(730, 237, 200, 20), Qt.AlignCenter, player.action)
                        # draw bet pot
                        painter.drawText(QRect(380, 480, 200, 40),Qt.AlignCenter,
                                         'Pot: %s%.2f' % (self.currency, state.newpot))
                    else:
                        painter.setPen(QColor("white"))
                    if player.chips != 0:
                        # draw player's bet
                        painter.drawText(QRect(730, 294, 200, 20),
                                         Qt.AlignCenter,
                                         '%s%.2f' % (self.currency, player.chips))
                elif player.name == list(state.players.values())[4].name:
                    if hand.get_player_position(player.name) == "S":
                        painter.drawImage(QPoint(450, 320), self.dealer.scaled(40, 40, Qt.KeepAspectRatio))
                    print("round", i, "player", player.name)
                    print(list(state.players.values())[2])
                    # draw player bloc
                    painter.drawImage(QPoint(160, 490), self.playerBackdrop)
                    if player.action == "folds":
                        painter.setPen(QColor("red"))
                    else:
                        painter.setPen(QColor("white"))
                        # if check box hide cards and hero

                        if not self.showCards.isChecked():
                            # draw player's card
                            self.renderCards(painter, player.holecards, 185, 400)
                        elif self.showCards.isChecked():
                            if player.name == self.Heroes:
                                self.renderCards(painter, player.holecards, 185, 400)
                            else:
                                if hand.gametype[
                                    "category"] == "omahahi" or "omahahilo" or "badugi" or "badacey" or "badeucey" or "irish" or "fusion":
                                    self.renderCards(painter, ['0', '0', '0', '0'], 185, 400)
                                elif hand.gametype[
                                    "category"] == "5_omahahi" or "5_omaha8" or "cour_hi" or "cour_hilo" or "27_1draw" or "27_3draw" or "a5_3draw" or "a5_1draw" or "drawmaha":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0'], 185, 400)
                                elif hand.gametype["category"] == "6_omahahi":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0', '0'], 185, 400)
                                elif hand.gametype["category"] == "holdem" or "6_holdem":
                                    self.renderCards(painter, ['0', '0'], 185, 400)
                                elif hand.gametype["category"] == "2_holdem":
                                    self.renderCards(painter, ['0', '0', '0'], 185, 400)
                                else:
                                    self.renderCards(painter, player.holecards, 185, 400)

                    # draw player's info
                    painter.drawText(QRect(140, 490, 200, 20),
                                     Qt.AlignCenter,
                                     '%s %s%.2f' % (player.name,
                                                    self.currency,
                                                    player.stack))
                    if player.justacted:
                        painter.setPen(QColor("yellow"))
                        # draw player's actions
                        painter.drawText(QRect(140, 507, 200, 20), Qt.AlignCenter, player.action)
                        # draw bet pot
                        painter.drawText(QRect(380, 480, 200, 40),Qt.AlignCenter,
                                         'Pot: %s%.2f' % (self.currency, state.newpot))
                    else:
                        painter.setPen(QColor("white"))
                    if player.chips != 0:
                        # draw player's bet
                        painter.drawText(QRect(260, 490, 200, 20),
                                         Qt.AlignCenter,
                                         '%s%.2f' % (self.currency, player.chips))
                elif player.name == list(state.players.values())[5].name:
                    if hand.get_player_position(player.name) == "S":
                        painter.drawImage(QPoint(450, 620), self.dealer.scaled(40, 40, Qt.KeepAspectRatio))
                    print("round", i, "player", player.name)
                    print(list(state.players.values())[2])
                    # draw player bloc
                    painter.drawImage(QPoint(500, 790), self.playerBackdrop)
                    if player.action == "folds":
                        painter.setPen(QColor("red"))
                    else:
                        painter.setPen(QColor("white"))
                        # if check box hide cards and hero

                        if not self.showCards.isChecked():
                            # draw player's card
                            self.renderCards(painter, player.holecards, 520, 700)
                        elif self.showCards.isChecked():
                            if player.name == self.Heroes:
                                self.renderCards(painter, player.holecards, 520, 700)
                            else:
                                if hand.gametype[
                                    "category"] == "omahahi" or "omahahilo" or "badugi" or "badacey" or "badeucey" or "irish" or "fusion":
                                    self.renderCards(painter, ['0', '0', '0', '0'], 520, 700)
                                elif hand.gametype[
                                    "category"] == "5_omahahi" or "5_omaha8" or "cour_hi" or "cour_hilo" or "27_1draw" or "27_3draw" or "a5_3draw" or "a5_1draw" or "drawmaha":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0'], 520, 700)
                                elif hand.gametype["category"] == "6_omahahi":
                                    self.renderCards(painter, ['0', '0', '0', '0', '0', '0'], 520, 700)
                                elif hand.gametype["category"] == "holdem" or "6_holdem":
                                    self.renderCards(painter, ['0', '0'], 520, 700)
                                elif hand.gametype["category"] == "2_holdem":
                                    self.renderCards(painter, ['0', '0', '0'], 520, 700)
                                else:
                                    self.renderCards(painter, player.holecards, 520, 700)

                    # draw player's info
                    painter.drawText(QRect(480, 790, 200, 20),
                                     Qt.AlignCenter,
                                     '%s %s%.2f' % (player.name,
                                                    self.currency,
                                                    player.stack))
                    if player.justacted:
                        painter.setPen(QColor("yellow"))
                        # draw player's actions
                        painter.drawText(QRect(480, 807, 200, 20), Qt.AlignCenter, player.action)
                        # draw bet pot
                        painter.drawText(QRect(380, 480, 200, 40),Qt.AlignCenter,
                                         'Pot: %s%.2f' % (self.currency, state.newpot))
                    else:
                        painter.setPen(QColor("white"))
                    if player.chips != 0:
                        # draw player's bet
                        painter.drawText(QRect(480, 670, 200, 20),
                                         Qt.AlignCenter,
                                         '%s%.2f' % (self.currency, player.chips))
                
                else:
                    pass
                i += 1
        elif nb_player == 7:
            print('nb player :', nb_player)
        elif nb_player == 8:
            print('nb player :', nb_player)
        elif nb_player == 9:
            print('nb player :', nb_player)
        elif nb_player == 10:
            print('nb player :', nb_player)

        painter.setPen(QColor("white"))

        for street in state.renderBoard:
            x = 520
            y = 400
            print("street", street, "value street", state.board[street])
            if street == "FLOP" and state.board[street] != []:
                self.renderboardCards(painter, state.board[street], x, y)
            elif street == "FLOP1" and state.board[street] != []:
                y -= int(self.cardheight / 2)
                self.renderboardCards(painter, state.board[street], x, y)
            elif street == "FLOP2" and state.board[street] != []:
                y += int(self.cardheight / 2)
                self.renderboardCards(painter, state.board[street], x, y)
            elif street == "FLOP3" and state.board[street] != []:
                y += self.cardheight + int(self.cardheight / 2)
                self.renderboardCards(painter, state.board[street], x, y)
            elif street == "TURN" and state.board[street] != []:
                x += 3 * self.cardwidth
                self.renderboardCards(painter, state.board[street], x, y)
            elif street == "TURN1" and state.board[street] != []:
                x += 3 * self.cardwidth
                y -= int(self.cardheight / 2)
                self.renderboardCards(painter, state.board[street], x, y)
            elif street == "TURN2" and state.board[street] != []:
                x += 3 * self.cardwidth
                y += int(self.cardheight / 2)
                self.renderboardCards(painter, state.board[street], x, y)
            elif street == "TURN3" and state.board[street] != []:
                x += 3 * self.cardwidth
                y += self.cardheight + int(self.cardheight / 2)
                self.renderboardCards(painter, state.board[street], x, y)
            elif street == "RIVER" and state.board[street] != []:
                x += 4 * self.cardwidth
                self.renderboardCards(painter, state.board[street], x, y)
            elif street == "RIVER1" and state.board[street] != []:
                x += 4 * self.cardwidth
                y -= int(self.cardheight / 2)
                self.renderboardCards(painter, state.board[street], x, y)
            elif street == "RIVER2" and state.board[street] != []:
                x += 4 * self.cardwidth
                y += int(self.cardheight / 2)
                self.renderboardCards(painter, state.board[street], x, y)
            elif street == "RIVER3" and state.board[street] != []:
                x += 4 * self.cardwidth
                y += self.cardheight + int(self.cardheight / 2)
                self.renderboardCards(painter, state.board[street], x, y)
            else:
                pass
            

        if self.stateSlider.value() == self.stateSlider.maximum():
            if nb_player == 2:
                # set 2 player
                print('nb player :', nb_player)
                i = 0
                for player in list(state.players.values()):
                    #print(player.holecards)
                    print(hand.gametype["category"])
                    if player.name == list(state.players.values())[0].name:
                        self.renderCards(painter, player.holecards, 660, 700)
                    elif player.name == list(state.players.values())[1].name:
                        self.renderCards(painter, player.holecards, 1115, 400)
                    else:
                        pass
                    i += 1
            elif nb_player == 3:
                print('nb player :', nb_player)
                i = 0
                for player in list(state.players.values()):
                    #print(player.holecards)
                    print(hand.gametype["category"])
                    if player.name == list(state.players.values())[0].name:
                        self.renderCards(painter, player.holecards, 660, 700)
                    elif player.name == list(state.players.values())[1].name:
                        self.renderCards(painter, player.holecards, 1115, 400)
                    elif player.name == list(state.players.values())[2].name:
                        self.renderCards(painter, player.holecards, 185, 400)
                    else:
                        pass
                    i += 1
            elif nb_player == 4:
                print('nb player :', nb_player)
                i = 0
                for player in list(state.players.values()):
                    #print(player.holecards)
                    print(hand.gametype["category"])
                    if player.name == list(state.players.values())[0].name:
                        self.renderCards(painter, player.holecards, 660, 700)
                    elif player.name == list(state.players.values())[1].name:
                        self.renderCards(painter, player.holecards, 1115, 400)
                    elif player.name == list(state.players.values())[2].name:
                        self.renderCards(painter, player.holecards, 655, 130)
                    elif player.name == list(state.players.values())[3].name:
                        self.renderCards(painter, player.holecards, 185, 400)
                    else:
                        pass
                    i += 1
            elif nb_player == 5:
                print('nb player :', nb_player)
                i = 0
                for player in list(state.players.values()):
                    #print(player.holecards)
                    print(hand.gametype["category"])
                    if player.name == list(state.players.values())[0].name:
                        self.renderCards(painter, player.holecards, 660, 700)
                    elif player.name == list(state.players.values())[1].name:
                        self.renderCards(painter, player.holecards, 1115, 400)
                    elif player.name == list(state.players.values())[2].name:
                        self.renderCards(painter, player.holecards, 770, 130)
                    elif player.name == list(state.players.values())[3].name:
                        self.renderCards(painter, player.holecards, 520, 130)
                    elif player.name == list(state.players.values())[4].name:
                        self.renderCards(painter, player.holecards, 185, 400)
                    else:
                        pass
                    i += 1
            elif nb_player == 6:
                print('nb player :', nb_player)
                i = 0
                for player in list(state.players.values()):
                    # print(player.holecards)
                    print(hand.gametype["category"])
                    if player.name == list(state.players.values())[0].name:
                        self.renderCards(painter, player.holecards, 770, 700)
                    elif player.name == list(state.players.values())[1].name:
                        self.renderCards(painter, player.holecards, 1115, 400)
                    elif player.name == list(state.players.values())[2].name:
                        self.renderCards(painter, player.holecards, 770, 130)
                    elif player.name == list(state.players.values())[3].name:
                        self.renderCards(painter, player.holecards, 520, 130)
                    elif player.name == list(state.players.values())[4].name:
                        self.renderCards(painter, player.holecards, 185, 400)
                    elif player.name == list(state.players.values())[5].name:
                        self.renderCards(painter, player.holecards, 520, 700)
                    else:
                        pass
                    i += 1
            elif nb_player == 7:
                print('nb player :', nb_player)
            elif nb_player == 8:
                print('nb player :', nb_player)
            elif nb_player == 9:
                print('nb player :', nb_player)
            elif nb_player == 10:
                print('nb player :', nb_player)

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

        # info for drawing (game, limite, site ...)
        print(hand)
        print(hand.gametype)
        info_gen = hand.gametype['category']
        if info_gen == "omahahilo":
            info_gen = "Omaha Hi/Lo"
        elif info_gen == "fusion":
            info_gen = "Fusion"
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
        self.info = str(limit_info) + " " + str(info_gen) + " " + str(hand.gametype['bb']) + str(
            hand.gametype['currency']) + " hand n° " + str(hand.handid)  + " played on " + str(hand.sitename)

        state = TableState(hand)

        # print (state)
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
        eq = D(self.stacks[player]) / total * D(str(self.payouts[depth]))
        if (depth + 1 < len(self.payouts)):
            i = 0
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
        # self.icm = ICM(stacks,payouts)
        # print icm.equities

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

            self.players[items[1]] = Player(hand, items[1], items[2], int(items[0]))
            print(self.players[items[1]])

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
        for name, amount in list(collectees.items()):
            player = self.players[name]
            player.chips += amount
            player.action = "collected"
            player.justacted = True
        for name, amount in list(returned.items()):
            self.players[name].stack += amount


class Player(object):
    def __init__(self, hand, name, stack, seat):
        self.stack = Decimal(stack)
        self.chips = Decimal(0)
        self.seat = seat
        self.name = name
        self.action = None
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
        print('seat', seat)
        self.x = 0.5 * cos(2 * self.seat * pi / hand.maxseats)
        self.y = 0.8 * sin(2 * self.seat * pi / hand.maxseats)


if __name__ == '__main__':
    config = Configuration.Config()
    db = Database.Database(config)
    sql = SQL.Sql(db_server=config.get_db_parameters()['db-server'])

    from PyQt5.QtWidgets import QApplication

    app = QApplication([])
    handlist = [10, 39, 40]
    replayer = GuiReplayer(config, sql, None, handlist)
    replayer.play_hand(0)

    app.exec_()
