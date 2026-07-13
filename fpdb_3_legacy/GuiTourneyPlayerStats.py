#!/usr/bin/env python
from __future__ import annotations

from time import time
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

# import Charset
from fpdb_3_legacy import Filters, GuiTourHandViewer
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("gui_tourney_player_stats")

colalias, colshow, colheading, colxalign, colformat, coltype = 0, 1, 2, 3, 4, 5


class GuiTourneyPlayerStats(QSplitter):
    def __init__(self, config, db, sql, mainwin, debug=True) -> None:
        super().__init__(mainwin)
        self.conf = config
        self.db = db
        self.cursor = self.db.cursor
        self.sql = sql
        self.main_window = mainwin
        self.debug = debug

        self.liststore: list[Any] = []
        self.listcols: list[list[str]] = []

        filters_display = {
            "Heroes": True,
            "Sites": True,
            "Seats": True,
            "Dates": True,
            "UseType": "tour",
            "Button2": True,
        }

        self.stats_frame = None
        self.stats_vbox = None
        self.detailFilters: list[Any] = []

        self.filters = Filters.Filters(self.db, display=filters_display)
        self.filters.registerButton2Name(_("Refresh Stats"))
        self.filters.registerButton2Callback(self.refreshStats)

        scroll = QScrollArea()
        scroll.setObjectName("filterSidebar")
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

        # Declarative descriptor columns (stat_registry.py): the ChipEV-by-position
        # curves plus standard rate stats (VPIP/PFR/3Bet/C-bet/...). Values are
        # merged in by addGrid from a separate per-(tourneyType,player)
        # aggregation; here we only declare the columns. Pre-formatted strings,
        # hence the "%s" format. Context-bearing descriptors (e.g. ChipEV/tourney,
        # which needs cnt_tourneys) are excluded — the merge query does not
        # supply that context column.
        try:
            from fpdb_3_legacy.stat_adapters import GridAdapter
            from fpdb_3_legacy.stat_registry import get_registry

            self._grid_descriptors = [d for d in get_registry().for_scope("tour") if not d.context]
            self.columns.extend(GridAdapter().column_specs(self._grid_descriptors))
        except Exception as exc:
            log.warning(f"GuiTourneyPlayerStats: descriptor columns unavailable: {exc}")
            self._grid_descriptors = []

        self.stats_frame = QFrame()
        self.stats_frame.setObjectName("statsSurface")
        self.stats_frame.setLayout(QVBoxLayout())

        self.stats_vbox = QSplitter(Qt.Orientation.Vertical)
        self.stats_frame.layout().addWidget(self.stats_vbox)

        self.addWidget(scroll)
        self.addWidget(self.stats_frame)
        self.setStretchFactor(0, 0)
        self.setStretchFactor(1, 1)

    def addGrid(
        self,
        vbox,
        query_name,
        numTourneys,
        tourneyTypes,
        playerids,
        sitenos,
        seats,
    ) -> None:
        grid = 0

        query = self.sql.query[query_name]
        query = self.refineQuery(
            query,
            numTourneys,
            tourneyTypes,
            playerids,
            sitenos,
            seats,
        )
        log.info(f"addGrid (Tourney): executing query '{query_name}'")
        log.info(f"addGrid (Tourney) refined SQL:\n{query}")
        self.cursor.execute(query)
        result = self.cursor.fetchall()
        log.info(f"addGrid (Tourney): fetched {len(result)} rows from database")
        if len(result) == 0:
            from PySide6.QtWidgets import QMessageBox
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle(_("FPDB 3 info"))
            msg.setText("No data found for the selected filters.")
            msg.exec()
            raise ValueError("No data found")
        colnames = [desc[0] for desc in self.cursor.description]

        # Merge declarative ChipEV-by-position values into the rows, keyed by
        # (tourneyTypeId, playerId). Best-effort: never break the base grid.
        result, colnames = self._merge_chipev_columns(
            query_name, result, colnames, numTourneys, tourneyTypes, playerids, sitenos, seats,
        )

        view = QTableView()
        model = QStandardItemModel(0, len(self.columns))
        view.setModel(model)
        view.verticalHeader().hide()
        vbox.addWidget(view)
        self.liststore.append(model)
        self.listcols.append([])

        # Create Header
        for _col, column in enumerate(self.columns):
            s = str(column[colheading])
            self.listcols[grid].append(s)
        model.setHorizontalHeaderLabels(self.listcols[grid])

        # Fullfill
        for row_data in result:
            treerow = []
            for _col, column in enumerate(self.columns):
                value = row_data[colnames.index(column[colalias])] if column[colalias] in colnames else None
                if column[colalias] == "siteName" and row_data[colnames.index("speed")] != "Normal":
                    if (
                        row_data[colnames.index("speed")] == "Hyper"
                        and row_data[colnames.index("siteName")] == "Full Tilt Poker"
                    ):
                        value = f"{value} Super Turbo"
                    else:
                        value = f"{value} {row_data[colnames.index('speed')]}"
                if column[colalias] in ["knockout", "reEntry"]:
                    value = "Yes" if row_data[colnames.index(column[colalias])] == 1 else "No"
                item = QStandardItem("")
                if value is not None and value != -999:
                    item = QStandardItem(column[colformat] % value)
                item.setEditable(False)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight)
                treerow.append(item)
            # Stash the drill-down keys on the first cell so a double-click can
            # resolve the row back to its tournament type + player.
            if treerow and "tourneyTypeId" in colnames and "playerId" in colnames:
                ttid = row_data[colnames.index("tourneyTypeId")]
                pid = row_data[colnames.index("playerId")]
                treerow[0].setData((ttid, pid), Qt.ItemDataRole.UserRole)
            model.appendRow(treerow)

        view.resizeColumnsToContents()
        view.setSortingEnabled(True)
        view.doubleClicked.connect(self._on_stats_double_clicked)

    # ------------------------------------------------------------------ #
    # Drill-down: stats row -> tournaments -> hands in a Tourney Viewer    #
    # ------------------------------------------------------------------ #
    def _on_stats_double_clicked(self, index) -> None:
        """Drill down from an aggregated stats row to its individual tournaments."""
        keys = index.sibling(index.row(), 0).data(Qt.ItemDataRole.UserRole)
        if not keys:
            return
        tourney_type_id, player_id = keys
        tournaments = self._fetch_tournaments(tourney_type_id, player_id)
        if not tournaments:
            QMessageBox.information(self, "Tournaments", "No tournaments found for this row.")
            return
        if len(tournaments) == 1:
            row = tournaments[0]
            self._open_tourney_hands(row[0], row[1])
        else:
            self._show_tournaments_dialog(tournaments)

    def _fetch_tournaments(self, tourney_type_id, player_id):
        """Return the hero's tournaments for a tourney type, with hand counts.

        Each row: (tourneyId, siteTourneyNo, startTime, rank, winnings, handCount).
        """
        ph = self.sql.query.get("placeholder", "%s")
        q = (
            "SELECT t.id, t.siteTourneyNo, t.startTime, tp.rank, tp.winnings/100.0, "
            "(SELECT COUNT(*) FROM Hands h WHERE h.tourneyId = t.id) "
            "FROM TourneysPlayers tp "
            "JOIN Tourneys t ON t.id = tp.tourneyId "
            "WHERE t.tourneyTypeId = ? AND tp.playerId = ? "
            "ORDER BY t.startTime, t.siteTourneyNo"
        ).replace("?", ph)
        c = self.db.get_cursor()
        c.execute(q, (tourney_type_id, player_id))
        return c.fetchall()

    def _show_tournaments_dialog(self, tournaments) -> None:
        """List the individual tournaments; double-click one to load its hands."""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Tournaments ({len(tournaments)}) — double-click to load hands")
        dialog.resize(560, 420)
        layout = QVBoxLayout(dialog)

        headers = ["Tourney No", "Date", "Rank", "Winnings", "Hands"]
        table = QTableWidget(len(tournaments), len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().hide()
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        for r, (tid, tno, start, rank, winnings, hands) in enumerate(tournaments):
            cells = [
                str(tno) if tno is not None else "",
                str(start) if start is not None else "",
                str(rank) if rank not in (None, 0) else "",
                f"{winnings:.2f}" if winnings is not None else "",
                str(hands),
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                # Carry the tourneyId/number/hand-count on the first cell of the row.
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, (tid, tno, hands))
                table.setItem(r, col, item)
        table.resizeColumnsToContents()
        layout.addWidget(table)

        def _on_row_double_clicked(row: int, _col: int) -> None:
            item = table.item(row, 0)
            if item is None:
                return
            data = item.data(Qt.ItemDataRole.UserRole)
            if not data:
                return
            tid, tno, hands = data
            self._open_tourney_hands(tid, tno, dialog=dialog)

        table.cellDoubleClicked.connect(_on_row_double_clicked)
        dialog.exec()

    def _open_tourney_hands(self, tourney_id, tourney_no, dialog=None) -> None:
        """Open a Tourney Hand Viewer tab loaded with one tournament's hands."""
        ph = self.sql.query.get("placeholder", "%s")
        q = "SELECT id FROM Hands WHERE tourneyId = ? ORDER BY startTime, id".replace("?", ph)
        c = self.db.get_cursor()
        c.execute(q, (tourney_id,))
        hand_ids = [r[0] for r in c.fetchall()]
        if not hand_ids:
            QMessageBox.information(
                self,
                "Tournament hands",
                f"No hands stored for tournament #{tourney_no}.\n\n"
                "This tournament was imported from a summary without its hand histories.",
            )
            return
        viewer = GuiTourHandViewer.TourHandViewer(self.conf, self.sql, self.main_window)
        # Reveal the same hero/alias chosen in this stats tab before loading, so
        # the viewer doesn't fall back to its default alias and show every hand
        # face-down when the tournament was recorded under another alias
        # (e.g. "Hero" vs the configured screen name "jeje_sat").
        self._sync_viewer_hero(viewer)
        self.main_window.threads.append(viewer)
        self.main_window.add_and_display_tab(viewer, f"Tourney #{tourney_no}")
        viewer.reload_hands(hand_ids)
        if dialog is not None:
            dialog.accept()

    def _sync_viewer_hero(self, viewer) -> None:
        """Select, in the new viewer, the same hero entry chosen in this stats tab."""
        src = getattr(self.filters, "heroList", None)
        dst = getattr(getattr(viewer, "filters", None), "heroList", None)
        if src is None or dst is None:
            return
        target = src.currentText()
        for i in range(dst.count()):
            if dst.itemText(i) == target:
                dst.setCurrentIndex(i)
                return

    def createStatsTable(self, vbox, tourneyTypes, playerids, sitenos, seats) -> None:
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

    def fillStatsFrame(self, vbox) -> None:
        tourneyTypes = self.filters.getTourneyTypes()
        sites = self.filters.getSites()
        heroes = self.filters.getHeroes()
        siteids = self.filters.getSiteIds()
        seats = self.filters.getSeats()
        # dates = self.filters.getDates()
        sitenos = []
        playerids = []

        log.info(f"fillStatsFrame (Tourney): sites={sites}, heroes={heroes}, tourneyTypes={tourneyTypes}, seats={seats}")

        # Selected site
        for site in sites:
            _hname = heroes.get(site, "")
            if not _hname:
                log.info(f"fillStatsFrame (Tourney): site '{site}' has no selected hero, skipping")
                continue
            # Plot the hero the user selected, resolved variant-aware:
            # get_player_id maps a "PokerStars" selection to the hero's
            # "PokerStars.FR" account, so data imported under a site skin still
            # shows. Fall back to the site's hero-flagged players if unresolved.
            result = self.db.get_player_id(self.conf, site, _hname)
            pids = [int(result)] if result is not None else self.db.get_hero_player_ids(site)
            for pid in pids:
                if pid not in playerids:
                    playerids.append(pid)
                    actual_site_id = self.db.get_player_site_id(pid)
                    if actual_site_id is not None:
                        sitenos.append(actual_site_id)
                        log.info(f"fillStatsFrame (Tourney): Using resolved actual siteId {actual_site_id} for player ID {pid}")
                    else:
                        sitenos.append(siteids[site])

        if not sitenos:
            log.warning("fillStatsFrame (Tourney): No sites selected")
            sitenos = [2]
        if not playerids:
            log.warning("fillStatsFrame (Tourney): No player ids found")
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
            sitetest = f"and tt.siteId in {sitetest}"
        else:
            sitetest = "and tt.siteId IS NULL"
        query = query.replace("<sitetest>", sitetest)

        if seats:
            query = query.replace(
                "<seats_test>",
                "between " + str(seats["from"]) + " and " + str(seats["to"]),
            )
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
                    flagtest += f" and {f[0]} between {f[1]!s} and {f[2]!s} "
        query = query.replace("<flagtest>", flagtest)

        if self.db.backend == self.db.MYSQL_INNODB:
            query = query.replace("<signed>", "signed ")
        else:
            query = query.replace("<signed>", "")

        start_date, end_date = self.filters.getDates()
        query = query.replace("<startdate_test>", start_date)
        return query.replace("<enddate_test>", end_date)

    def _merge_chipev_columns(self, query_name, result, colnames, numTourneys, tourneyTypes, playerids, sitenos, seats):
        """Append declarative ChipEV-by-position values to the detailed-stats rows.

        Runs a separate per-(tourneyType, player) aggregation and joins it onto
        the grid rows by (tourneyTypeId, playerId). Returns (result, colnames),
        possibly augmented. Best-effort: any failure returns the inputs intact.
        """
        descriptors = getattr(self, "_grid_descriptors", [])
        if query_name != "tourneyPlayerDetailedStats" or not descriptors:
            return result, colnames
        if "tourneyTypeId" not in colnames or "playerId" not in colnames:
            return result, colnames

        try:
            from fpdb_3_legacy.stat_adapters import GridAdapter

            adapter = GridAdapter()
            query = self.sql.query["tourneyChipEVByPositionGrid"]
            query = query.replace("<chipev_columns>", adapter.select_clause(descriptors))
            query = self.refineQuery(query, numTourneys, tourneyTypes, playerids, sitenos, seats)

            self.cursor.execute(query)
            ev_cols = [d[0] for d in self.cursor.description]
            lookup = {}
            for row in self.cursor.fetchall():
                rd = dict(zip(ev_cols, row, strict=False))
                lookup[(rd["tourneyTypeId"], rd["playerId"])] = rd

            tt_idx = colnames.index("tourneyTypeId")
            pid_idx = colnames.index("playerId")
            augmented = []
            for row_data in result:
                key = (row_data[tt_idx], row_data[pid_idx])
                ev_row = lookup.get(key, {})
                extra = [descriptor.format(adapter.compute(descriptor, ev_row)) for descriptor in descriptors]
                augmented.append(list(row_data) + extra)
            new_colnames = colnames + [descriptor.name for descriptor in descriptors]
            log.info(f"GuiTourneyPlayerStats: merged {len(descriptors)} ChipEV column(s) for {len(lookup)} group(s)")
            return augmented, new_colnames
        except Exception as exc:
            log.warning(f"GuiTourneyPlayerStats._merge_chipev_columns failed (skipping): {exc}")
            self.db.rollback()
            return result, colnames

    def refreshStats(self) -> None:
        if self.stats_frame is None or self.stats_frame.layout() is None:
            return
        layout = self.stats_frame.layout()
        for i in reversed(range(layout.count())):
            widgetToRemove = layout.itemAt(i).widget()
            if widgetToRemove is not None:
                layout.removeWidget(widgetToRemove)
                widgetToRemove.setParent(None)

        self.liststore = []
        self.listcols = []
        self.stats_vbox = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(self.stats_vbox)
        try:
            self.fillStatsFrame(self.stats_vbox)
        except ValueError as e:
            if str(e) == "No data found":
                self.db.rollback()
                return
            else:
                raise


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    # Launch the tournament player stats GUI like the original
    import fpdb_3_legacy.Configuration as Configuration

    config = Configuration.Config()

    settings = {}
    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())


    from fpdb_3_legacy import SQL, Database

    app = QApplication([])
    sql = SQL.Sql(db_server=settings["db-server"])
    db = Database.Database(config, sql)
    main_window = QMainWindow()
    i = GuiTourneyPlayerStats(config, db, sql, main_window)
    main_window.setCentralWidget(i)
    main_window.show()
    main_window.resize(1400, 800)
    app.exec()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
