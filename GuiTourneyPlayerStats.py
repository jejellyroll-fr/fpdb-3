#!/usr/bin/env python
# -*- coding: utf-8 -*-

from time import time
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QMainWindow,
    QScrollArea,
    QSplitter,
    QTableView,
    QVBoxLayout,
)

# import Charset
import Filters

from loggingFpdb import get_logger

log = get_logger("tourplayerstats")

colalias, colshow, colheading, colxalign, colformat, coltype = 0, 1, 2, 3, 4, 5


class GuiTourneyPlayerStats(QSplitter):
    def __init__(self, config, db, sql, mainwin, debug=True):
        super().__init__(mainwin)
        self.conf = config
        self.db = db
        self.cursor = self.db.cursor
        self.sql = sql
        self.main_window = mainwin
        self.debug = debug

        self.liststore = []
        self.listcols = []

        filters_display = {
            "Heroes": True,
            "Sites": True,
            "Seats": True,
            "Dates": True,
            "Button2": True,
        }

        self.stats_frame = None
        self.stats_vbox = None
        self.detailFilters = []

        self.filters = Filters.Filters(self.db, display=filters_display)
        self.filters.registerButton2Name("_Refresh Stats")
        self.filters.registerButton2Callback(self.refreshStats)

        scroll = QScrollArea()
        scroll.setWidget(self.filters)
        scroll.setWidgetResizable(True)

        self.columns = [
            ["siteName", True, "Site", 0.0, "%s", "str"],
            ["category", True, "Cat.", 0.0, "%s", "str"],
            ["limitType", True, "Limit", 0.0, "%s", "str"],
            ["currency", True, "Curr.", 0.0, "%s", "str"],
            ["buyIn", True, "BuyIn", 1.0, "%3.2f", "str"],
            ["fee", True, "Fee", 1.0, "%3.2f", "str"],
            ["maxSeats", True, "Seats", 0.0, "%s", "str"],
            ["knockout", True, "KO", 0.0, "%s", "str"],
            ["reEntry", True, "ReEntry", 0.0, "%s", "str"],
            ["playerName", False, "Name", 0.0, "%s", "str"],
            ["tourneyCount", True, "#", 1.0, "%1.0f", "str"],
            ["itm", True, "ITM%", 1.0, "%3.2f", "str"],
            ["_1st", False, "1st", 1.0, "%1.0f", "str"],
            ["_2nd", True, "2nd", 1.0, "%1.0f", "str"],
            ["_3rd", True, "3rd", 1.0, "%1.0f", "str"],
            ["unknownRank", True, "Rank?", 1.0, "%1.0f", "str"],
            ["spent", True, "Spent", 1.0, "%3.2f", "str"],
            ["won", True, "Won", 1.0, "%3.2f", "str"],
            ["net", True, "Net", 1.0, "%3.2f", "str"],
            ["roi", True, "ROI%", 1.0, "%3.2f", "str"],
            ["profitPerTourney", True, "$/Tour", 1.0, "%3.2f", "str"],
        ]

        self.stats_frame = QFrame()
        self.stats_frame.setLayout(QVBoxLayout())

        self.stats_vbox = QSplitter(Qt.Vertical)
        self.stats_frame.layout().addWidget(self.stats_vbox)

        self.addWidget(scroll)
        self.addWidget(self.stats_frame)
        self.setStretchFactor(0, 0)
        self.setStretchFactor(1, 1)

    def addGrid(self, vbox, query_name, numTourneys, tourneyTypes, playerids, sitenos, seats):
        grid = 0

        query = self.sql.query[query_name]
        query = self.refineQuery(query, numTourneys, tourneyTypes, playerids, sitenos, seats)
        self.cursor.execute(query)
        result = self.cursor.fetchall()
        colnames = [desc[0] for desc in self.cursor.description]

        view = QTableView()
        model = QStandardItemModel(0, len(self.columns))
        view.setModel(model)
        view.verticalHeader().hide()
        vbox.addWidget(view)
        self.liststore.append(model)
        self.listcols.append([])

        # Create Header
        for col, column in enumerate(self.columns):
            s = column[colheading]
            self.listcols[grid].append(s)
        model.setHorizontalHeaderLabels(self.listcols[grid])

        # Fullfill
        for row_data in result:
            treerow = []
            for col, column in enumerate(self.columns):
                if column[colalias] in colnames:
                    value = row_data[colnames.index(column[colalias])]
                else:
                    value = None
                if column[colalias] == "siteName":
                    if row_data[colnames.index("speed")] != "Normal":
                        if (
                            row_data[colnames.index("speed")] == "Hyper"
                            and row_data[colnames.index("siteName")] == "Full Tilt Poker"
                        ):
                            value = value + " " + "Super Turbo"
                        else:
                            value = value + " " + row_data[colnames.index("speed")]
                if column[colalias] in ["knockout", "reEntry"]:
                    value = "Yes" if row_data[colnames.index(column[colalias])] == 1 else "No"
                item = QStandardItem("")
                if value is not None and value != -999:
                    item = QStandardItem(column[colformat] % value)
                item.setEditable(False)
                item.setTextAlignment(Qt.AlignRight)
                treerow.append(item)
            model.appendRow(treerow)

        view.resizeColumnsToContents()
        view.setSortingEnabled(True)

    def createStatsTable(self, vbox, tourneyTypes, playerids, sitenos, seats):
        startTime = time()

        numTourneys = self.filters.getNumTourneys()
        self.addGrid(
            vbox,
            "tourneyPlayerDetailedStats",
            numTourneys,
            tourneyTypes,
            playerids,
            sitenos,
            seats,
        )

        log.info(f"Stats page displayed in {time() - startTime:4.2f} seconds")

    def fillStatsFrame(self, vbox):
        tourneyTypes = self.filters.getTourneyTypes()
        sites = self.filters.getSites()
        heroes = self.filters.getHeroes()
        siteids = self.filters.getSiteIds()
        seats = self.filters.getSeats()
        # dates = self.filters.getDates()
        sitenos = []
        playerids = []

        # Selected site
        for site in sites:
            sitenos.append(siteids[site])
            _hname = heroes.get(site, "")
            if not _hname:
                raise ValueError(f"Hero name not found for site {site}")
            result = self.db.get_player_id(self.conf, site, _hname)
            if result is not None:
                playerids.append(int(result))

        if not sitenos:
            # print("No sites selected - defaulting to PokerStars")
            sitenos = [2]
        if not playerids:
            # print("No player ids found")
            return

        self.createStatsTable(vbox, tourneyTypes, playerids, sitenos, seats)

    def refineQuery(self, query, numTourneys, tourneyTypes, playerids, sitenos, seats):
        having = ""

        if playerids:
            nametest = str(tuple(playerids))
            nametest = nametest.replace(",)", ")")
        else:
            nametest = "1 = 2"
        pname = "p.name"

        query = query.replace("<nametest>", nametest)
        query = query.replace("<playerName>", pname)
        query = query.replace("<havingclause>", having)

        if sitenos:
            sitetest = str(tuple(sitenos))
            sitetest = sitetest.replace(",)", ")")
            sitetest = "and tt.siteId in %s" % sitetest
        else:
            sitetest = "and tt.siteId IS NULL"
        query = query.replace("<sitetest>", sitetest)

        if seats:
            query = query.replace("<seats_test>", "between " + str(seats["from"]) + " and " + str(seats["to"]))
            query = query.replace("<groupbyseats>", ",h.seats")
            query = query.replace("<orderbyseats>", ",h.seats")
        else:
            query = query.replace("<seats_test>", "between 0 and 100")
            query = query.replace("<groupbyseats>", "")
            query = query.replace("<orderbyseats>", "")

        flagtest = ""
        if self.detailFilters:
            for f in self.detailFilters:
                if len(f) == 3:
                    flagtest += " and %s between %s and %s " % (f[0], str(f[1]), str(f[2]))
        query = query.replace("<flagtest>", flagtest)

        if self.db.backend == self.db.MYSQL_INNODB:
            query = query.replace("<signed>", "signed ")
        else:
            query = query.replace("<signed>", "")

        start_date, end_date = self.filters.getDates()
        query = query.replace("<startdate_test>", start_date)
        query = query.replace("<enddate_test>", end_date)

        return query

    def refreshStats(self):
        for i in reversed(range(self.stats_frame.layout().count())):
            widgetToRemove = self.stats_frame.layout().itemAt(i).widget()
            self.stats_frame.layout().removeWidget(widgetToRemove)
            widgetToRemove.setParent(None)

        self.liststore = []
        self.listcols = []
        self.stats_vbox = QSplitter(Qt.Vertical)
        self.stats_frame.layout().addWidget(self.stats_vbox)
        self.fillStatsFrame(self.stats_vbox)


if __name__ == "__main__":
    import Configuration

    config = Configuration.Config()

    settings = {}
    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())

    from PyQt5.QtWidgets import QApplication, QMainWindow
    import SQL
    import Database

    app = QApplication([])
    sql = SQL.Sql(db_server=settings["db-server"])
    db = Database.Database(config, sql)
    main_window = QMainWindow()
    i = GuiTourneyPlayerStats(config, db, sql, main_window)
    main_window.setCentralWidget(i)
    main_window.show()
    main_window.resize(1400, 800)
    app.exec_()
