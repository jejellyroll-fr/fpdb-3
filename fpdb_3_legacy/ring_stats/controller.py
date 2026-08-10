"""controller.py

Le contrôleur du package ring_stats.
Gère l'extraction asynchrone des données de la base de données, la construction
des QStandardItemModels conformes à l'ancien comportement, et le calcul
des statistiques pour le tableau de bord, les positions et les cartes.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QStandardItem, QStandardItemModel

from fpdb_3_legacy import Card, gui_empty_state
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.ring_stats.base import DbWorker
from fpdb_3_legacy.ring_stats.styles import get_theme_palette

log = get_logger("ring_stats_controller")

def debug_log(msg: str) -> None:
    """Route detailed diagnostics through the configured logger."""
    log.debug(msg)

colalias, colheading, colshowsumm, colshowposn, colformat, coltype, colxalign = (
    0, 1, 2, 3, 4, 5, 6
)
ranks = {
    "x": 0, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
    "T": 10, "J": 11, "Q": 12, "K": 13, "A": 14
}
fast_names = {
    "PokerStars": "Zoom", "PokerStars.COM": "Zoom", "PokerStars.FR": "Zoom",
    "PokerStars.IT": "Zoom", "PokerStars.ES": "Zoom", "PokerStars.PT": "Zoom",
    "PokerStars.EU": "Zoom", "Bovada": "Zone", "PacificPoker": "Snap",
    "Winamax": "Go Fast"
}
_WINNINGS_ALIASES = frozenset({"net", "bbper100", "profitperhand", "evbb100", "bb100", "profit100"})
_MAX_DETAIL_ROWS = 1000

# Textes d'aide pour les infobulles des colonnes
onlinehelp = {
    "Game": _("Game type (Hold'em, Omaha, etc.)"),
    "Hand": _("Starting cards (Hole cards)"),
    "Posn": _("Position at the table"),
    "Name": _("Player name"),
    "Hds": _("Number of hands played"),
    "Seats": _("Number of seats at the table"),
    "VPIP": _("Voluntarily put money in pot preflop"),
    "PFR": _("Preflop raise"),
    "PF3": _("% Preflop 3-bet"),
    "Flop3B": _("% Flop 3-bet"),
    "Turn3B": _("% Turn 3-bet"),
    "Rivr3B": _("% River 3-bet"),
    "Flop4B": _("% Flop 4-bet"),
    "Turn4B": _("% Turn 4-bet"),
    "Rivr4B": _("% River 4-bet"),
    "FOpen": _("% Flop open bet"),
    "TOpen": _("% Turn open bet"),
    "ROpen": _("% River open bet"),
    "PF4": _("% Preflop 4-bet"),
    "PFF3": _("% Fold to preflop 3-bet"),
    "PFF4": _("% Fold to preflop 4-bet"),
    "AggFac": _("Postflop aggression factor"),
    "AggFreq": _("Postflop aggression frequency"),
    "ContBet": _("% Continuation Bet"),
    "RFI": _("% Raise First In"),
    "RST": _("% Re-steal"),
    "Steals": _("% Steal attempt"),
    "SucSt": _("% Steal success"),
    "fSB": _("% Small Blind fold to steal"),
    "fBB": _("% Big Blind fold to steal"),
    "CARpre": _("% Call Raise preflop"),
    "Saw_F": _("% Flops seen"),
    "SawSD": _("% Showdowns seen"),
    "WtSDwsF": _("% Went to showdown after seeing flop"),
    "W$wsF": _("% Won money after seeing flop"),
    "W$SD": _("% Won money at showdown"),
    "FlAFq": _("Flop aggression frequency"),
    "TuAFq": _("Turn aggression frequency"),
    "RvAFq": _("River aggression frequency"),
    "Net($)": _("Total net profit"),
    "bb/100": _("Big Blinds won per 100 hands"),
    "Profit/Hnd": _("Profit per hand"),
    "Rake($)": _("Rake paid"),
    "bbxr/100": _("Big Blinds won per 100 hands excluding rake"),
    "ProfitHndXR": _("Profit per hand excluding rake"),
    "Variance": _("Measure of uncertainty"),
    "Std. Dev.": _("Measure of uncertainty")
}


class RingStatsController(QObject):
    """Contrôleur centralisant l'accès aux données et leur formatage."""

    # Signaux pour communiquer avec les fenêtres de visualisation
    summary_model_ready = Signal(QStandardItemModel)
    hand_model_ready = Signal(QStandardItemModel)
    dashboard_data_ready = Signal(dict, object)
    position_data_ready = Signal(dict)
    # Carries a NoDataReason value so the view can explain *why* it is empty.
    no_data_found = Signal(str)

    def __init__(self, db, config, sql) -> None:
        super().__init__()
        self.db = db
        self.cursor = db.cursor
        self.conf = config
        self.sql = sql
        self.columns = config.get_gui_cash_stat_params()
        self._workers: list[DbWorker] = []

        # Force synchronous mode only in test suites (pytest/unittest)
        import sys

        self.async_mode = "pytest" not in sys.modules and "unittest" not in sys.modules

        self._last_summary_stats: dict[str, Any] | None = None
        self._last_profit_data: tuple[Any, Any, Any, Any] | None = None

    def shutdown_workers(self) -> None:
        """Stop all DbWorker threads started by this controller.

        Called when the host tab is closed: QThreads must not outlive their
        parent widget.
        """
        for worker in self._workers:
            if worker.isRunning():
                worker.terminate()
                worker.wait()
        self._workers = []

    def refresh_all(self, filter_widget) -> None:
        """Lance l'ensemble des requêtes asynchrones en fonction des filtres appliqués."""
        debug_log("refresh_all called!")
        # 1. Extraction des filtres
        sites = filter_widget.getSites()
        heroes = filter_widget.getHeroes()
        siteids = filter_widget.getSiteIds()
        limits = filter_widget.getLimits()
        seats = filter_widget.getSeats()
        groups = filter_widget.getGroups()
        dates = filter_widget.getDates()
        games = filter_widget.getGames()
        currencies = filter_widget.getCurrencies()
        num_hands = filter_widget.getNumHands()

        debug_log(f"Filters: sites={sites}, heroes={heroes}, limits={limits}, seats={seats}, groups={groups}, dates={dates}, games={games}, currencies={currencies}")

        # Reset states
        self._last_summary_stats = None
        self._last_profit_data = None

        # Résolution des ids de joueurs et sites
        sitenos = []
        playerids = []
        for site in sites:
            _hname = heroes.get(site, "")
            if not _hname:
                continue
            result = self.db.get_player_id(self.conf, site, _hname)
            pids = [int(result)] if result is not None else self.db.get_hero_player_ids(site)
            for pid in pids:
                if pid not in playerids:
                    playerids.append(pid)
                    actual_site_id = self.db.get_player_site_id(pid)
                    if actual_site_id is not None:
                        sitenos.append(actual_site_id)
                    else:
                        sitenos.append(siteids[site])

        debug_log(f"Resolved playerids: {playerids}, sitenos: {sitenos}")

        missing = gui_empty_state.missing_filter_reason(sites=sites, playerids=playerids, limits=limits)
        if missing is not None:
            # Report which filter is empty instead of returning silently: the
            # tab used to keep its previous content with no explanation.
            debug_log(f"Filtres incomplets ou invalides: {missing.value}")
            self.no_data_found.emit(missing.value)
            return

        # Paramètres pour affiner les requêtes
        filter_params = (filter_widget, playerids, sitenos, limits, seats, groups, dates, games, currencies, num_hands)

        # 2. Lancer la requête pour le tableau résumé (summary grid)
        sql_summary = self._get_refined_sql("playerDetailedStats", False, *filter_params)
        self._run_query("summary", sql_summary, self._on_summary_query_finished)

        # 3. Lancer la requête pour le détail des mains (hand detailed stats)
        if "allplayers" not in groups:
            sql_hands = self._get_refined_sql("playerDetailedStats", True, *filter_params)
            self._run_query("hands", sql_hands, self._on_hands_query_finished)

        # 4. Lancer la requête spécifique pour le Poker Table (Heatmap de position)
        sql_positions = self._get_refined_sql("playerDetailedStats", False, *filter_params, force_position=True)
        self._run_query("positions", sql_positions, self._on_positions_query_finished)

        # 5. Lancer la requête chronologique de profit
        sql_profit = self._get_refined_sql_profit(playerids, sitenos, limits, dates, games, currencies, filter_widget)
        self._run_query("profit", sql_profit, self._on_profit_query_finished)

    def _run_query(self, query_name: str, sql: str, callback) -> None:
        """Lance une requête asynchrone à l'aide d'un DbWorker (ou synchrone en test)."""
        debug_log(f"_run_query: name={query_name}, async_mode={self.async_mode}")
        debug_log(f"SQL for {query_name}:\n{sql}")
        # Nettoyer les anciens workers
        self._workers = [w for w in self._workers if not w.isFinished()]

        worker = DbWorker(self.db, query_name, sql)
        worker.finished.connect(callback)

        def on_error(err):
            log.error(f"DbWorker error for {query_name}: {err}")
            debug_log(f"DbWorker error for {query_name}: {err}")

        worker.error.connect(on_error)
        self._workers.append(worker)

        if self.async_mode:
            worker.start()
        else:
            worker.run()

    def _on_summary_query_finished(self, name: str, result: list, colnames: list) -> None:
        """Callback appelé lorsque la requête récapitulative est terminée."""
        debug_log(f"_on_summary_query_finished: returned {len(result) if result else 0} rows")
        if not result:
            self._last_summary_stats = {}
            self._last_profit_data = ([], [], [], [])
            self.no_data_found.emit(gui_empty_state.NoDataReason.NO_ROWS.value)
            return

        # Créer le modèle standard de données
        colshow = colshowposn if "posn" in self._last_groups else colshowsumm
        cols_to_show = [x for x in self.columns if x[colshow]]

        model = QStandardItemModel(0, len(cols_to_show))
        for col, column in enumerate(cols_to_show):
            header_item = QStandardItem(column[colheading])
            header_item.setData(column[colalias], Qt.ItemDataRole.UserRole + 10)
            model.setHorizontalHeaderItem(col, header_item)
        model.setSortRole(Qt.ItemDataRole.UserRole)

        # Remplir le modèle
        self._populate_model(model, result, colnames, cols_to_show, holecards=False)
        self.summary_model_ready.emit(model)

        # Calculer le global VPIP, PFR, hands, net pour le Tableau de Bord
        self._last_summary_stats = self._calculate_dashboard_kpis(result, colnames)
        self._check_and_emit_dashboard()

    def _on_profit_query_finished(self, name: str, result: list, colnames: list) -> None:
        """Callback appelé lorsque la requête chronologique de profit est terminée."""
        debug_log(f"_on_profit_query_finished: returned {len(result) if result else 0} rows")
        import numpy as np

        if not result:
            self._last_profit_data = ([], [], [], [])
            self._check_and_emit_dashboard()
            return

        try:
            green = np.array([0.0, *[float(x[1]) for x in result]])
            blue = np.array([0.0, *[float(x[1]) if x[2] else 0.0 for x in result]])
            red = np.array([0.0, *[float(x[1]) if not x[2] else 0.0 for x in result]])
            orange = np.array([0.0, *[float(x[3]) if x[3] is not None else 0.0 for x in result]])

            greenline = green.cumsum() / 100.0
            blueline = blue.cumsum() / 100.0
            redline = red.cumsum() / 100.0
            orangeline = orange.cumsum() / 100.0

            self._last_profit_data = (greenline, blueline, redline, orangeline)
        except Exception as e:
            log.error(f"Error processing profit data: {e}")
            self._last_profit_data = ([], [], [], [])

        self._check_and_emit_dashboard()

    def _check_and_emit_dashboard(self) -> None:
        if self._last_summary_stats is not None and self._last_profit_data is not None:
            self.dashboard_data_ready.emit(self._last_summary_stats, self._last_profit_data)

    def _on_hands_query_finished(self, name: str, result: list, colnames: list) -> None:
        """Callback appelé lorsque la requête détaillée par main est terminée."""
        debug_log(f"_on_hands_query_finished: returned {len(result) if result else 0} rows")
        if not result:
            return

        colshow = colshowposn if "posn" in self._last_groups else colshowsumm
        cols_to_show = [x for x in self.columns if x[colshow]]

        model = QStandardItemModel(0, len(cols_to_show))
        for col, column in enumerate(cols_to_show):
            alias = column[colalias]
            if alias == "game":
                heading = next(x for x in self.columns if x[colalias] == "hand")[colheading]
                actual_alias = "hand"
            else:
                heading = column[colheading]
                actual_alias = alias
            header_item = QStandardItem(heading)
            header_item.setData(actual_alias, Qt.ItemDataRole.UserRole + 10)
            model.setHorizontalHeaderItem(col, header_item)
        model.setSortRole(Qt.ItemDataRole.UserRole)

        # Attacher les catégories de jeu actives au modèle pour détection
        categories = set()
        cat_idx = colnames.index("category") if "category" in colnames else -1
        if cat_idx != -1:
            for row in result:
                if row[cat_idx]:
                    categories.add(str(row[cat_idx]))
        model.setProperty("categories", list(categories))

        # Limiter le nombre de lignes à charger dans la table détail pour préserver la réactivité
        rows_to_load = result
        if len(result) > _MAX_DETAIL_ROWS:
            rows_to_load = result[:_MAX_DETAIL_ROWS]

        self._populate_model(model, rows_to_load, colnames, cols_to_show, holecards=True)
        self.hand_model_ready.emit(model)

    def _on_positions_query_finished(self, name: str, result: list, colnames: list) -> None:
        """Callback pour l'affichage de la table de poker positionnelle."""
        position_stats = {}

        vpip_idx = colnames.index("vpip") if "vpip" in colnames else -1
        pfr_idx = colnames.index("pfr") if "pfr" in colnames else -1
        net_idx = colnames.index("net") if "net" in colnames else -1
        currency_idx = colnames.index("currency") if "currency" in colnames else -1
        pos_idx = colnames.index("plposition") if "plposition" in colnames else -1

        for row in result:
            if pos_idx != -1:
                db_pos = str(row[pos_idx])
                # Laisser la vue mapper les chiffres de sièges de manière dynamique,
                # mais uniformiser les blinds et le bouton.
                pos_label = db_pos
                if db_pos == "S":
                    pos_label = "SB"
                elif db_pos in ("B", "9", "8"):
                    pos_label = "BB"
                elif db_pos == "0":
                    pos_label = "Btn"

                vpip = float(row[vpip_idx]) if vpip_idx != -1 and row[vpip_idx] is not None and row[vpip_idx] != -999 else 0.0
                pfr = float(row[pfr_idx]) if pfr_idx != -1 and row[pfr_idx] is not None and row[pfr_idx] != -999 else 0.0
                net = float(row[net_idx]) if net_idx != -1 and row[net_idx] is not None else 0.0

                position_stats[pos_label] = {
                    "vpip": vpip,
                    "pfr": pfr,
                    "net": net,
                    "currency": str(row[currency_idx]) if currency_idx != -1 and row[currency_idx] else "EUR",
                }

        debug_log(f"_on_positions_query_finished: resolved {len(position_stats)} positions: {list(position_stats.keys())}")
        self.position_data_ready.emit(position_stats)

    def _populate_model(self, model: QStandardItemModel, result: list, colnames: list, cols_to_show: list, holecards: bool) -> None:
        """Remplit le QStandardItemModel en conservant le formatage et les tooltips d'origine."""
        hgametypeid_idx = colnames.index("hgametypeid") if "hgametypeid" in colnames else -1
        c_palette = get_theme_palette()
        color_up = QColor(c_palette.get("graph_up", "#48bb78"))
        color_down = QColor(c_palette.get("graph_down", "#f56565"))
        color_neutral = QColor(c_palette.get("text", "#edf2f7"))

        for sqlrow in range(len(result)):
            treerow: list[QStandardItem] = []
            for col, column in enumerate(cols_to_show):
                value = None
                sortValue = -1e9

                if column[colalias] in colnames:
                    value = result[sqlrow][colnames.index(column[colalias])]
                    if column[colalias] == "plposition":
                        if value == "B":
                            value = "BB"
                        elif value == "S":
                            value = "SB"
                        elif value == "0":
                            value = "Btn"
                elif column[colalias] == "game":
                    if holecards:
                        cat_idx = colnames.index("category")
                        value = Card.decodeStartHandValue(result[sqlrow][cat_idx], result[sqlrow][hgametypeid_idx])
                    else:
                        # Formatage d'une ligne de limite de jeu
                        minbb = result[sqlrow][colnames.index("minbigblind")]
                        maxbb = result[sqlrow][colnames.index("maxbigblind")]
                        value = (
                            result[sqlrow][colnames.index("limittype")] + " " +
                            result[sqlrow][colnames.index("category")].title() + " " +
                            result[sqlrow][colnames.index("name")] + " " +
                            result[sqlrow][colnames.index("currency")] + " "
                        )
                        if 100 * int(minbb // 100.0) != minbb:
                            value += f"{minbb // 100.0:.2f}"
                        else:
                            value += f"{minbb // 100.0:.0f}"
                        if minbb != maxbb:
                            if 100 * int(maxbb // 100.0) != maxbb:
                                value += f" - {maxbb // 100.0:.2f}"
                            else:
                                value += f" - {maxbb // 100.0:.0f}"
                        ante = result[sqlrow][colnames.index("ante")]
                        if ante > 0:
                            value += f" ante: {ante // 100.0:.2f}"
                        if result[sqlrow][colnames.index("fast")] == 1:
                            value += " " + fast_names.get(result[sqlrow][colnames.index("name")], "Fast")

                # Valeur par défaut
                item = QStandardItem("")
                if value is not None and value != -999:
                    item = QStandardItem(column[colformat] % value)

                    # Déterminer la valeur de tri (sortValue)
                    if column[colalias] == "game" and holecards:
                        cat_idx = colnames.index("category")
                        if result[sqlrow][cat_idx] == "holdem":
                            sortValue = (
                                1000 * ranks.get(value[0], 0) +
                                10 * ranks.get(value[1], 0) +
                                (1 if len(value) == 3 and value[2] == "s" else 0)
                            )
                        else:
                            sortValue = -1
                    elif column[colalias] in ("game", "pname"):
                        sortValue = value
                    elif column[colalias] == "plposition":
                        order_list = ["BB", "SB", "Btn", "1", "2", "3", "4", "5", "6", "7"]
                        sortValue = order_list.index(value) if value in order_list else 99
                    else:
                        sortValue = float(value)

                item.setData(sortValue, Qt.ItemDataRole.UserRole)
                item.setEditable(False)

                # Appliquer la couleur vert/rouge sur les profits
                if column[colalias] in _WINNINGS_ALIASES and value is not None and value != -999:
                    try:
                        v = float(value)
                        item.setForeground(QBrush(color_up if v > 0 else color_down if v < 0 else color_neutral))
                    except (TypeError, ValueError):
                        pass

                # Alignements des cellules (à droite sauf pour la colonne 0)
                if col != 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

                # Tooltip d'aide en survol
                if column[colalias] != "game" and len(treerow) > 0:
                    desc_heading = column[colheading]
                    help_text = onlinehelp.get(desc_heading, desc_heading)
                    item.setToolTip(f"<big>{desc_heading} pour {treerow[0].text()}</big><br/><i>{help_text}</i>")

                treerow.append(item)
            model.appendRow(treerow)

    def _calculate_dashboard_kpis(self, result: list, colnames: list) -> dict:
        """Calcule les KPIs totaux du joueur en agrégeant les lignes de résultats."""
        hands_idx = colnames.index("n") if "n" in colnames else -1
        net_idx = colnames.index("net") if "net" in colnames else -1
        vpip_idx = colnames.index("vpip") if "vpip" in colnames else -1
        pfr_idx = colnames.index("pfr") if "pfr" in colnames else -1
        pf3_idx = colnames.index("pf3") if "pf3" in colnames else -1
        agg_idx = colnames.index("aggfac") if "aggfac" in colnames else -1
        currency_idx = colnames.index("currency") if "currency" in colnames else -1

        total_hands = 0
        total_net = 0.0
        weighted_vpip = 0.0
        weighted_pfr = 0.0
        weighted_pf3 = 0.0
        weighted_agg = 0.0
        currencies: set[str] = set()

        for row in result:
            h = int(row[hands_idx]) if hands_idx != -1 and row[hands_idx] is not None else 0
            if h <= 0:
                continue
            total_hands += h
            total_net += float(row[net_idx]) if net_idx != -1 and row[net_idx] is not None else 0.0
            if currency_idx != -1 and row[currency_idx]:
                currencies.add(str(row[currency_idx]))

            # Agrégation pondérée par le nombre de mains
            weighted_vpip += (float(row[vpip_idx]) if vpip_idx != -1 and row[vpip_idx] is not None and row[vpip_idx] != -999 else 0.0) * h
            weighted_pfr += (float(row[pfr_idx]) if pfr_idx != -1 and row[pfr_idx] is not None and row[pfr_idx] != -999 else 0.0) * h
            weighted_pf3 += (float(row[pf3_idx]) if pf3_idx != -1 and row[pf3_idx] is not None and row[pf3_idx] != -999 else 0.0) * h
            weighted_agg += (float(row[agg_idx]) if agg_idx != -1 and row[agg_idx] is not None and row[agg_idx] != -999 else 0.0) * h

        return {
            "hands": total_hands,
            "net": total_net,
            "vpip": (weighted_vpip / total_hands) if total_hands > 0 else 0.0,
            "pfr": (weighted_pfr / total_hands) if total_hands > 0 else 0.0,
            "pf3": (weighted_pf3 / total_hands) if total_hands > 0 else 0.0,
            "aggfac": (weighted_agg / total_hands) if total_hands > 0 else 0.0,
            "currency": next(iter(currencies)) if len(currencies) == 1 else "EUR",
        }

    def _get_refined_sql(self, query: str, holecards: bool, filter_widget, playerids, sitenos, limits, seats, groups, dates, games, currencies, num_hands, force_position: bool = False) -> str:
        """Adapte et affine la requête SQL brute en injectant les filtres actifs."""
        self._last_groups = groups

        tmp = self.sql.query[query]
        having = ""
        colshow = colshowsumm
        if "posn" in groups or force_position:
            colshow = colshowposn

        pname_column = next(x for x in self.columns if x[0] == "pname")
        if "allplayers" in groups:
            nametest = "(hp.playerId)"
            if holecards or "posn" in groups or force_position:
                pname = "'all players'"
                pname_column[colshow] = False
                if num_hands:
                    nametest = "(-1)"
            else:
                pname = "p.name"
                pname_column[colshow] = True
                if num_hands:
                    having = f" and count(1) > {num_hands:d} "
        else:
            nametest = str(tuple(playerids)).replace("L", "").replace(",)", ")") if playerids else "1 = 2"
            pname = "p.name"
            pname_column[colshow] = False

        tmp = tmp.replace("<player_test>", nametest)
        tmp = tmp.replace("<playerName>", pname)
        tmp = tmp.replace("<havingclause>", having)

        # Filtre sur les jeux
        gametest = ""
        if len(games) > 0:
            gametest = str(tuple(games)).replace("L", "").replace(",)", ")").replace("u'", "'")
            gametest = f"and gt.category in {gametest}"
        else:
            gametest = "and gt.category IS NULL"
        tmp = tmp.replace("<game_test>", gametest)

        # Filtre devises
        currencytest = str(tuple(currencies)).replace(",)", ")").replace("u'", "'")
        currencytest = f"AND gt.currency in {currencytest}"
        tmp = tmp.replace("<currency_test>", currencytest)

        # Filtre sites
        sitetest = ""
        if len(sitenos) > 0:
            sitetest = str(tuple(sitenos)).replace("L", "").replace(",)", ")").replace("u'", "'")
            sitetest = f"and gt.siteId in {sitetest}"
        else:
            sitetest = "and gt.siteId IS NULL"
        tmp = tmp.replace("<site_test>", sitetest)

        # Filtre sièges
        if seats:
            tmp = tmp.replace("<seats_test>", f"between {seats['from']} and {seats['to']}")
            if "seats" in groups:
                tmp = tmp.replace("<groupbyseats>", ",h.seats")
                tmp = tmp.replace("<orderbyseats>", ",h.seats")
            else:
                tmp = tmp.replace("<groupbyseats>", "")
                tmp = tmp.replace("<orderbyseats>", "")
        else:
            tmp = tmp.replace("<seats_test>", "between 0 and 100")
            tmp = tmp.replace("<groupbyseats>", "")
            tmp = tmp.replace("<orderbyseats>", "")

        bbtest = filter_widget.get_limits_where_clause(limits)
        tmp = tmp.replace("<gtbigBlind_test>", bbtest)

        if holecards:
            tmp = tmp.replace("<hgametypeId>", "hp.startcards")
            tmp = tmp.replace(
                "<orderbyhgametypeId>",
                ",case when floor((hp.startcards-1)/13) >= mod((hp.startcards-1),13) then hp.startcards + 0.1 "
                " else 13*mod((hp.startcards-1),13) + floor((hp.startcards-1)/13) + 1 "
                " end desc ",
            )
        else:
            tmp = tmp.replace("<orderbyhgametypeId>", "")
            groupLevels = "limits" not in groups
            if groupLevels:
                tmp = tmp.replace("<hgametypeId>", "p.name")
            else:
                tmp = tmp.replace("<hgametypeId>", "h.gametypeId")

        # Flag tests
        flagtest = ""
        # dates
        tmp = tmp.replace("<datestest>", f" between '{dates[0]}' and '{dates[1]}'")
        tmp = tmp.replace("<flagtest>", flagtest)
        tmp = tmp.replace("<cardstest>", "")

        # Position (groupement)
        plposition_column = next(x for x in self.columns if x[0] == "plposition")
        if "posn" in groups or force_position:
            tmp = tmp.replace("<position>", "hp.position")
            plposition_column[colshow] = True
        else:
            tmp = tmp.replace("<position>", "gt.base")
            plposition_column[colshow] = False

        if self.db.backend == 2:  # MySQL InnoDB
            tmp = tmp.replace("<signed>", "signed ")
        else:
            tmp = tmp.replace("<signed>", "")

        return tmp

    def _get_refined_sql_profit(self, playerids, sitenos, limits, dates, games, currencies, filter_widget) -> str:
        """Formate la requête chronologique de profit avec les filtres actifs."""
        tmp = self.sql.query["getRingProfitAllHandsPlayerIdSiteInDollars"]
        nametest = str(tuple(playerids)).replace("L", "").replace(",)", ")") if playerids else "1 = 2"
        sitetest = str(tuple(sitenos)).replace("L", "").replace(",)", ")") if sitenos else "1 = 2"

        gametest = ""
        if len(games) > 0:
            gametest = str(tuple(games)).replace("L", "").replace(",)", ")").replace("u'", "'")
            gametest = f"and gt.category in {gametest}"
        else:
            gametest = "and gt.category IS NULL"

        currencytest = str(tuple(currencies)).replace(",)", ")").replace("u'", "'")
        currencytest = f"AND gt.currency in {currencytest}"

        bbtest = filter_widget.get_limits_where_clause(limits)

        tmp = tmp.replace("<player_test>", nametest)
        tmp = tmp.replace("<site_test>", sitetest)
        tmp = tmp.replace("<startdate_test>", dates[0])
        tmp = tmp.replace("<enddate_test>", dates[1])
        tmp = tmp.replace("<limit_test>", bbtest)
        tmp = tmp.replace("<game_test>", gametest)
        tmp = tmp.replace("<currency_test>", currencytest)
        tmp = tmp.replace(",)", ")")
        return tmp
