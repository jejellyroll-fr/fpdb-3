#!/usr/bin/env python
# -*- coding: utf-8 -*-

#Copyright 2008-2011 Carl Gherardi
#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU Affero General Public License as published by
#the Free Software Foundation, version 3 of the License.
#
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#GNU General Public License for more details.
#
#You should have received a copy of the GNU Affero General Public License
#along with this program. If not, see <http://www.gnu.org/licenses/>.
#In the "official" distribution you can find the license in agpl-3.0.txt.


from __future__ import print_function
from __future__ import division

from past.utils import old_div
import os
import sys
from time import time
from PyQt5.QtWidgets import QFrame, QScrollArea, QSplitter, QVBoxLayout, QMessageBox
import Database
import Filters
import Charset

try:
    calluse = not 'matplotlib' in sys.modules
    import matplotlib
    if calluse:
        try:
            matplotlib.use('qt5agg')
        except ValueError as e:
            print(e)
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qt5agg import FigureCanvas
    from matplotlib.font_manager import FontProperties
    from numpy import arange, cumsum
except ImportError as inst:
    print(("""Failed to load libs for graphing, graphing will not function. Please install numpy and matplotlib if you want to use graphs."""))
    print(("""This is of no consequence for other parts of the program, e.g. import and HUD are NOT affected by this problem."""))
    print("ImportError: %s" % inst.args)

class GuiTourneyGraphViewer(QSplitter):

    def __init__(self, querylist, config, parent, colors, debug=True):
        """Constructor for GraphViewer"""
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
            "Button2": True
        }

        self.filters = Filters.Filters(self.db, display=filters_display)
        self.filters.registerButton1Name("Refresh Graph")
        self.filters.registerButton1Callback(self.generateGraph)
        self.filters.registerButton2Name("Export to File")
        self.filters.registerButton2Callback(self.exportGraph)

        scroll = QScrollArea()
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

        self.db.rollback()
        self.exportFile = None

    def clearGraphData(self):
        try:
            if self.canvas:
                self.graphBox.removeWidget(self.canvas)
        except:
            pass

        if self.fig is not None:
            self.fig.clear()
        self.fig = Figure(figsize=(5.0, 4.0), dpi=100)
        self.fig.patch.set_facecolor(self.colors["background"])
        if self.canvas is not None:
            self.canvas.destroy()

        self.canvas = FigureCanvas(self.fig)
        self.canvas.setParent(self)

    def generateGraph(self, widget):
        self.clearGraphData()

        sitenos = []
        playerids = []

        sites = self.filters.getSites()
        heroes = self.filters.getHeroes()
        siteids = self.filters.getSiteIds()

        games = self.filters.getGames()
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

        self.ax = self.fig.add_subplot(111)
        starttime = time()
        green = self.getData(playerids, sitenos, games)
        print("Graph generated in: %s" % (time() - starttime))

        self.ax.set_xlabel("Tournaments", color=self.colors['foreground'])
        self.ax.set_facecolor(self.colors['background'])
        self.ax.tick_params(axis='x', colors=self.colors['foreground'])
        self.ax.tick_params(axis='y', colors=self.colors['foreground'])
        self.ax.spines['left'].set_color(self.colors['foreground'])
        self.ax.spines['right'].set_color(self.colors['foreground'])
        self.ax.spines['top'].set_color(self.colors['foreground'])
        self.ax.spines['bottom'].set_color(self.colors['foreground'])
        self.ax.set_ylabel("$", color=self.colors['foreground'])
        self.ax.grid(color=self.colors['grid'], linestyle=':', linewidth=0.2)
        if green is None or len(green) == 0:
            self.ax.set_title("No Data for Player(s) Found", color=self.colors['foreground'])
            green = ([0., 0., 0., 0., 500., 1000., 900., 800., 700., 600., 500., 400., 300., 200., 100., 0., 500., 1000., 1000., 1000., 1000., 1000., 1000., 1000., 1000., 1000., 1000., 1000., 1000., 1000., 875., 750., 625., 500., 375., 250., 125., 0., 0., 0., 0., 500., 1000., 900., 800., 700., 600., 500., 400., 300., 200., 100., 0., 500., 1000., 1000.])

            self.ax.plot(green, color='green', label='Tournaments: %d\nProfit: $%.2f' % (len(green), green[-1]))
            self.graphBox.addWidget(self.canvas)
            self.canvas.show()
            self.canvas.draw()
        else:
            self.ax.set_title("Tournament Results" + names, color=self.colors['foreground'])
            self.ax.plot(green, color='green', label='Tournaments: %d\nProfit: $%.2f' % (len(green), green[-1]))
            legend = self.ax.legend(loc='upper left', fancybox=True, shadow=True, prop=FontProperties(size='smaller'), facecolor=self.colors["background"], labelcolor=self.colors['foreground'])
            self.graphBox.addWidget(self.canvas)
            self.canvas.draw()

    def getData(self, names, sites, Tourneys):
        tmp = self.sql.query['tourneyGraphType']
        start_date, end_date = self.filters.getDates()
        tourneys = self.filters.getTourneyTypes()
        tourneysCat = self.filters.getTourneyCat()
        tourneysLim = self.filters.getTourneyLim()
        tourneysBuyin = self.filters.getTourneyBuyin()

        currencies = {'EUR': 'EUR', 'USD': 'USD', '': 'T$'}
        currencytest = str(tuple(currencies.values()))
        currencytest = currencytest.replace(",)", ")")
        currencytest = currencytest.replace("u'", "'")
        currencytest = "AND tt.currency in %s" % currencytest

        nametest = str(tuple(names))
        sitetest = str(tuple(sites))
        tourneystest = str(tuple(tourneys))
        tourneysCattest = str(tuple(tourneysCat))
        tourneysLimtest = str(tuple(tourneysLim))
        tourneysBuyintest = str(tuple(int(buyin.split(',')[0]) for buyin in tourneysBuyin if buyin != "None"))
        tourneystest = tourneystest.replace('None', '"None"')
        tourneysBuyintest = tourneysBuyintest.replace('None', '"None"')

        tmp = tmp.replace("<player_test>", nametest)
        tmp = tmp.replace("<site_test>", sitetest)
        tmp = tmp.replace("<startdate_test>", start_date)
        tmp = tmp.replace("<enddate_test>", end_date)
        tmp = tmp.replace("<currency_test>", currencytest)
        tmp = tmp.replace("<tourney_cat>", tourneysCattest)
        tmp = tmp.replace("<tourney_lim>", tourneysLimtest)
        tmp = tmp.replace("<tourney_buyin>", tourneysBuyintest)
        tmp = tmp.replace("<tourney_test>", tourneystest)
        tmp = tmp.replace(",)", ")")

        print("DEBUG: sql query:", tmp)

        self.db.cursor.execute(tmp)
        winnings = self.db.cursor.fetchall()
        self.db.rollback()

        if len(winnings) == 0:
            return None

        green = [float(x[1]) for x in winnings]
        greenline = cumsum(green)
        return (old_div(greenline, 100))



    def exportGraph(self):
        if self.fig is None:
            return

        else:
            path = os.getcwd()
            path = path + '/graph.png'
            self.fig.savefig(path)
            msg = QMessageBox()
            msg.setWindowTitle("FPDB 3 info")
            mess = "Your graph is saved in " + path
            msg.setText(mess)
            msg.exec()

if __name__ == "__main__":
    import Configuration
    config = Configuration.Config()

    settings = {}

    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())

    from PyQt5.QtWidgets import QApplication, QMainWindow
    app = QApplication([])
    import SQL
    sql = SQL.Sql(db_server=settings['db-server'])

    colors = {
        'background': '#19232D',
        'foreground': '#9DA9B5',
        'grid': '#4D4D4D',
        'line_up': 'g',
        'line_down': 'r'
    }

    i = GuiTourneyGraphViewer(sql, config, None, colors)
    main_window = QMainWindow()
    main_window.setCentralWidget(i)
    main_window.show()
    main_window.resize(1400, 800)
    app.exec_()
