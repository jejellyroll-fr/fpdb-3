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
#


# This code once was in GuiReplayer.py and was split up in this and the former by zarturo.


# import L10n
# _ = L10n.get_translation()
from __future__ import print_function
from __future__ import division

import contextlib
import os
from past.utils import old_div
#import L10n
#_ = L10n.get_translation()

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy,
                             QSplitter, QVBoxLayout, QWidget, QFileDialog, QMessageBox)
import contextlib
from time import time
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvas
from matplotlib.font_manager import FontProperties
from numpy import cumsum
import Database
import Filters
import Charset

class GuiGraphViewer(QSplitter):

    def __init__(self, querylist, config, parent, colors, debug=True):
        QSplitter.__init__(self, parent)
        self.sql = querylist
        self.conf = config
        self.debug = debug
        self.parent = parent
        self.colors = colors
        self.db = Database.Database(self.conf, sql=self.sql)

        filters_display = {
            "Heroes": True,
            "Sites": True,
            "Games": True,
            "Currencies": True,
            "Limits": True,
            "LimitSep": True,
            "LimitType": True,
            "Type": True,
            "UseType": 'ring',
            "Seats": False,
            "SeatSep": False,
            "Dates": True,
            "GraphOps": True,
            "Groups": False,
            "Button1": True,
            "Button2": True
        }

        self.filters = Filters.Filters(self.db, display=filters_display)
        self.filters.registerButton1Name("Refresh Graph")
        self.filters.registerButton1Callback(self.generateGraph)
        self.filters.registerButton2Name("Export to File")
        self.filters.registerButton2Callback(self.exportGraph)

        scroll = QScrollArea()
        scroll.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
        scroll.setWidget(self.filters)
        self.addWidget(scroll)

        frame = QFrame()
        frame.setStyleSheet(f'background-color: {self.colors["background"]}')
        self.graphBox = QVBoxLayout()
        
        frame.setLayout(self.graphBox)
        self.addWidget(frame)
        self.setStretchFactor(0, 0)
        self.setStretchFactor(1, 1)

        self.fig = None
        self.canvas = None
        self.exportFile = None

        self.db.rollback()

    def clearGraphData(self):
        with contextlib.suppress(Exception):
            if self.canvas:
                self.graphBox.removeWidget(self.canvas)
        if self.fig is not None:
            self.fig.clear()
        self.fig = Figure(figsize=(5.0, 4.0), dpi=100)
        self.fig.patch.set_facecolor(self.colors['background'])
        if self.canvas is not None:
            self.canvas.destroy()

        self.canvas = FigureCanvas(self.fig)
        self.canvas.setParent(self)

    def generateGraph(self, widget):
        self.clearGraphData()

        sitenos = []
        playerids = []
        winnings = []
        sites = self.filters.getSites()
        heroes = self.filters.getHeroes()
        siteids = self.filters.getSiteIds()
        limits = self.filters.getLimits()
        games = self.filters.getGames()
        currencies = self.filters.getCurrencies()
        graphops = self.filters.getGraphOps()
        display_in = "$" if "$" in graphops else "BB"
        names = ""



        for site in sites:
            sitenos.append(siteids[site])
            _hname = Charset.to_utf8(heroes[site])
            result = self.db.get_player_id(self.conf, site, _hname)
            if result is not None:
                playerids.append(int(result))
                names = names + "\n" + _hname + " on " + site

        if not sitenos:
            print("No sites selected - defaulting to PokerStars")
            self.db.rollback()
            return

        if not playerids:
            print("No player ids found")
            self.db.rollback()
            return

        if not limits:
            print("No limits found")
            self.db.rollback()
            return
        #debug
        #print("currencies selcted:", self.filters.getCurrencies())

        self.ax = self.fig.add_subplot(111)

        starttime = time()
        (green, blue, red, orange) = self.getRingProfitGraph(playerids, sitenos, limits, games, currencies, display_in)
        print(f"Graph generated in: {time() - starttime}")

        self.ax.set_xlabel("Hands", color=self.colors['foreground'])
        self.ax.set_facecolor(self.colors['background'])
        self.ax.tick_params(axis='x', colors=self.colors['foreground'])
        self.ax.tick_params(axis='y', colors=self.colors['foreground'])
        self.ax.spines['left'].set_color(self.colors['foreground'])
        self.ax.spines['right'].set_color(self.colors['foreground'])
        self.ax.spines['top'].set_color(self.colors['foreground'])
        self.ax.spines['bottom'].set_color(self.colors['foreground'])
        self.ax.spines.left.set_position(('data', 0))
        self.ax.spines.top.set_color('none')
        self.ax.spines.right.set_color('none')
        self.ax.spines.bottom.set_position(('data', 0))
        self.ax.xaxis.set_ticks_position('bottom')
        self.ax.yaxis.set_ticks_position('left')

        self.ax.set_ylabel(display_in, color=self.colors['foreground'])
        self.ax.grid(color=self.colors['grid'], linestyle=':', linewidth=0.2)
        if green is None or len(green) == 0:
            self.plotGraph()
        else:
            self.ax.set_title(f"Profit graph for ring games{names}", color=self.colors['foreground'])

            if 'showdown' in graphops:
                print("blue max:", blue.max())
                self.ax.plot(blue, color=self.colors['line_showdown'], label=('Showdown') + ' (%s): %.2f' % (display_in, blue[-1]))

            if 'nonshowdown' in graphops:
                self.ax.plot(red, color=self.colors['line_nonshowdown'], label=('Non-showdown') + ' (%s): %.2f' % (display_in, red[-1]))
            if 'ev' in graphops:
                self.ax.plot(orange, color=self.colors['line_ev'], label=('All-in EV') + ' (%s): %.2f' % (display_in, orange[-1]))
            self.ax.plot(green, color=self.colors['line_hands'], label=('Hands') + ': %d\n' % len(green) + ('Profit') + ': (%s): %.2f' % (display_in, green[-1]))

            handles, labels = self.ax.get_legend_handles_labels()
            handles = handles[-1:] + handles[:-1]
            labels = labels[-1:] + labels[:-1]

            legend = self.ax.legend(handles, labels, loc='upper left', fancybox=True, shadow=True, prop=FontProperties(size='smaller'), facecolor=self.colors['background'], labelcolor=self.colors['foreground'])
            legend.set_draggable(state=1)

        self.graphBox.addWidget(self.canvas)
        self.canvas.draw()

    def plotGraph(self):
        self.ax.set_title("No Data for Player(s) Found")
        green = [0., 0., 0., 0., 500., 1000., 900., 800.,
                 700., 600., 500., 400., 300., 200., 100., 0.,
                 500., 1000., 1000., 1000., 1000., 1000., 1000., 1000.,
                 1000., 1000., 1000., 1000., 1000., 1000., 875., 750.,
                 625., 500., 375., 250., 125., 0., 0., 0.,
                 0., 500., 1000., 900., 800., 700., 600., 500.,
                 400., 300., 200., 100., 0., 500., 1000., 1000.]
        self.ax.plot(green, color=self.colors['line_hands'], linewidth=0.5, label=('Hands') + ': %d\n' % len(green) + ('Profit') + ': %.2f' % green[-1])

    def getRingProfitGraph(self, names, sites, limits, games, currencies, units):
        if units == '$':
            tmp = self.sql.query['getRingProfitAllHandsPlayerIdSiteInDollars']
        elif units == 'BB':
            tmp = self.sql.query['getRingProfitAllHandsPlayerIdSiteInBB']

        start_date, end_date = self.filters.getDates()

        nametest = str(tuple(names))
        sitetest = str(tuple(sites))

        for m in list(self.filters.display.items()):
            if m[0] == 'Games' and m[1]:
                if len(games) > 0:
                    gametest = str(tuple(games))
                    gametest = gametest.replace("L", "")
                    gametest = gametest.replace(",)",")")
                    gametest = gametest.replace("u'","'")
                    gametest = "and gt.category in %s" % gametest
                else:
                    gametest = "and gt.category IS NULL"
        tmp = tmp.replace("<game_test>", gametest)

        limittest = self.filters.get_limits_where_clause(limits)

        currencytest = str(tuple(currencies))
        currencytest = currencytest.replace(",)",")")
        currencytest = currencytest.replace("u'","'")
        currencytest = "AND gt.currency in %s" % currencytest

        if type == 'ring':
            limittest = limittest + " and gt.type = 'ring' "
        elif type == 'tour':
            limittest = limittest + " and gt.type = 'tour' "

        tmp = tmp.replace("<player_test>", nametest)
        tmp = tmp.replace("<site_test>", sitetest)
        tmp = tmp.replace("<startdate_test>", start_date)
        tmp = tmp.replace("<enddate_test>", end_date)
        tmp = tmp.replace("<limit_test>", limittest)
        tmp = tmp.replace("<currency_test>", currencytest)
        tmp = tmp.replace(",)", ")")

        #debug
        #print("Final SQL Request:")
        #print(tmp)

        self.db.cursor.execute(tmp)
        winnings = self.db.cursor.fetchall()
        self.db.rollback()

        #debug
        #print("winning data :")
        #print(winnings)

        if len(winnings) == 0:
            #print("Aucune donnée de gains trouvée")
            return (None, None, None, None)
        


        green = [0, *[float(x[1]) for x in winnings]]
        blue = [0, *[float(x[1]) if x[2] == True  else 0.0 for x in winnings]]
        red = [0]
        red.extend([float(x[1]) if x[2] == False else 0.0 for x in winnings])
        orange = [0]
        orange.extend([float(x[3]) for x in winnings])
        greenline = cumsum(green)
        blueline = cumsum(blue)
        redline = cumsum(red)
        orangeline = cumsum(orange)

        # print("Data :")
        # print("Green:", green[:10])  # show only the first 10 results
        # print("Blue:", blue[:10])
        # print("Red:", red[:10])
        # print("Orange:", orange[:10])

        # print("sum :")
        # print("Greenline:", greenline[:10])
        # print("Blueline:", blueline[:10])
        # print("Redline:", redline[:10])
        # print("Orangeline:", orangeline[:10])

        return (greenline / 100, blueline / 100, redline / 100, orangeline / 100)

    def exportGraph(self):
        if self.fig is None:
            return
        path = f'{os.getcwd()}/graph.png'
        self.fig.savefig(path)
        msg = QMessageBox()
        msg.setWindowTitle("FPDB 3 info")
        mess = f"Your graph is saved in {path}"
        msg.setText(mess)
        msg.exec()
