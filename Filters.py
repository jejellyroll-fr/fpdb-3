#!/usr/bin/env python
"""Filters module for FPDB data filtering interface.

Provides a comprehensive filtering system for poker data analysis with support for:
- Site selection (PokerStars, Winamax, etc.)
- Game variants (Hold'em, Omaha, Stud, etc.)
- Date ranges and player selection
- Betting limits and position filters
- Modern UI with qt_material theme integration
"""

import itertools
import os
from functools import partial
from typing import Any

from past.utils import old_div
from PyQt5.QtCore import QDate, QDateTime
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QCalendarWidget,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import Card
import Configuration
import Database
import SQL
from loggingFpdb import get_logger

if __name__ == "__main__":
    Configuration.set_logfile("fpdb-log.txt")
log = get_logger("filter")

# Constants for UI thresholds
MIN_ITEMS_FOR_CONTROLS = 2  # Minimum number of items to show control buttons


class Filters(QWidget):
    """Main filtering widget for FPDB data analysis.

    Provides comprehensive filtering capabilities for poker data including:
    - Site and game selection
    - Date range filtering
    - Player and position filters
    - Betting limits and currency selection
    """

    def __init__(self, db: Any, display: dict[str, Any] | None = None) -> None:
        """Initialize the Filters widget.

        Args:
            db: Database connection object
            display: Dictionary controlling which filter sections to display
        """
        if display is None:
            display = {}
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

        self.gameName = {
            "27_1draw": ("Single Draw 2-7 Lowball"),
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
            "6_omahahi": ("6 Card Omaha"),
        }

        self.currencyName = {
            "USD": ("US Dollar"),
            "EUR": ("Euro"),
            "T$": ("Tournament Dollar"),
            "play": ("Play Money"),
        }

        self.filterText = {
            "limitsall": ("All"),
            "limitsnone": ("None"),
            "limitsshow": ("Show Limits"),
            "gamesall": ("All"),
            "gamesnone": ("None"),
            "positionsall": ("All"),
            "positionsnone": ("None"),
            "currenciesall": ("All"),
            "currenciesnone": ("None"),
            "seatsbetween": ("Between:"),
            "seatsand": ("And:"),
            "seatsshow": ("Show Number of Players"),
            "playerstitle": ("Hero:"),
            "sitestitle": (("Sites") + ":"),
            "gamestitle": (("Games") + ":"),
            "tourneytitle": (("Tourney") + ":"),
            "tourneycat": (("Category") + ":"),
            "limitstitle": ("Limits:"),
            "positionstitle": ("Positions:"),
            "seatstitle": ("Number of Players:"),
            "tourneylim": (("Limit Type") + ":"),
            "groupstitle": ("Grouping:"),
            "posnshow": ("Show Position Stats"),
            "tourneybuyin": (("Buyin") + ":"),
            "datestitle": ("Date:"),
            "currenciestitle": (("Currencies") + ":"),
            "groupsall": ("All Players"),
            "cardstitle": (("Hole Cards") + ":"),
            "limitsFL": "FL",
            "limitsNL": "NL",
            "limitsPL": "PL",
            "limitsCN": "CAP",
            "ring": ("Ring"),
            "tour": ("Tourney"),
            "limitsHP": "HP",
        }

        gen = self.conf.get_general_params()
        self.day_start = 0

        if "day_start" in gen:
            self.day_start = float(gen["day_start"])

        self.setLayout(QVBoxLayout())

        self.callback = {}

        # Style is managed by qt_material applied at application level
        # We only add specific adjustments if necessary
        self.setStyleSheet(self.get_filter_specific_styles())
        self.make_filter()

    def get_filter_specific_styles(self) -> str:
        """Specific styles for filters that complement the qt_material theme."""
        return """
            /* Specific adjustments for filters */
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                margin-top: 1ex;
                padding-top: 15px;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 10px 0 10px;
            }

            /* Improved spacing for controls */
            QCheckBox {
                spacing: 8px;
                padding: 3px;
            }

            QRadioButton {
                spacing: 8px;
                padding: 3px;
            }

            /* Buttons with improved padding */
            QPushButton {
                padding: 8px 16px;
                font-weight: 500;
                min-height: 18px;
            }

            /* Input controls with consistent padding */
            QComboBox, QDateEdit, QSpinBox, QLineEdit {
                padding: 6px 12px;
                min-width: 100px;
            }
        """

    def make_filter(self) -> None:  # noqa: PLR0912, C901
        """Create all filter widgets based on display configuration.

        This method is complex by design as it handles multiple filter types
        and their conditional display logic.
        """
        self.siteid = {}
        self.cards = {}
        self.type = None

        for site in self.conf.get_supported_sites():
            self.cursor.execute(self.sql.query["getSiteId"], (site,))
            result = self.db.cursor.fetchall()
            if len(result) == 1:
                self.siteid[site] = result[0][0]
            else:
                log.debug("Either 0 or more than one site matched for %s", site)

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

    def set_default_hero(self) -> None:
        """Set the default hero selection to the first available hero."""
        if self.heroList and self.heroList.count() > 0:
            self.heroList.setCurrentIndex(0)
            self.update_filters_for_hero()

    def create_player_frame(self) -> QGroupBox:
        """Create the player selection frame."""
        player_frame = QGroupBox("🎭 " + self.filterText["playerstitle"])
        player_frame.setToolTip("Select the poker player (hero) to analyze")
        self.leHeroes = {}
        self.fillPlayerFrame(player_frame, self.display)
        return player_frame

    def create_sites_frame(self) -> QGroupBox:
        """Create the sites selection frame."""
        sites_frame = QGroupBox("🌐 " + self.filterText["sitestitle"])
        sites_frame.setToolTip("Filter by poker sites (PokerStars, Winamax, etc.)")
        self.cbSites = {}
        self.fillSitesFrame(sites_frame)
        return sites_frame

    def create_games_frame(self) -> QGroupBox:
        """Create the games selection frame."""
        games_frame = QGroupBox("🃏 " + self.filterText["gamestitle"])
        games_frame.setToolTip("Filter by poker game variants (Hold'em, Omaha, Stud, etc.)")
        self.fillGamesFrame(games_frame)
        return games_frame

    def create_tourney_frame(self) -> QGroupBox:
        """Create the tournament type selection frame."""
        tourney_frame = QGroupBox("🏆 " + self.filterText["tourneytitle"])
        tourney_frame.setToolTip("Filter by tournament type (Ring games vs Tournaments)")
        self.cbTourney = {}
        self.fillTourneyTypesFrame(tourney_frame)
        return tourney_frame

    def create_tourney_cat_frame(self) -> QGroupBox:
        """Create the tournament category selection frame."""
        tourney_cat_frame = QGroupBox(self.filterText["tourneycat"])
        self.cbTourneyCat = {}
        self.fillTourneyCatFrame(tourney_cat_frame)
        return tourney_cat_frame

    def create_tourney_lim_frame(self) -> QGroupBox:
        """Create the tournament limit selection frame."""
        tourney_lim_frame = QGroupBox(self.filterText["tourneylim"])
        self.cbTourneyLim = {}
        self.fillTourneyLimFrame(tourney_lim_frame)
        return tourney_lim_frame

    def create_tourney_buyin_frame(self) -> QGroupBox:
        """Create the tournament buyin selection frame."""
        tourney_buyin_frame = QGroupBox(self.filterText["tourneybuyin"])
        self.cbTourneyBuyin = {}
        self.fillTourneyBuyinFrame(tourney_buyin_frame)
        return tourney_buyin_frame

    def create_currencies_frame(self) -> QGroupBox:
        """Create the currencies selection frame."""
        currencies_frame = QGroupBox("💱 " + self.filterText["currenciestitle"])
        currencies_frame.setToolTip("Filter by currency (USD, EUR, Play Money, etc.)")
        self.fillCurrenciesFrame(currencies_frame)
        return currencies_frame

    def create_limits_frame(self) -> QGroupBox:
        """Create the limits selection frame."""
        limits_frame = QGroupBox("💰 " + self.filterText["limitstitle"])
        limits_frame.setToolTip("Filter by betting limits and stake levels")
        self.fillLimitsFrame(limits_frame, self.display)
        return limits_frame

    def create_positions_frame(self) -> QGroupBox:
        """Create the positions selection frame."""
        positions_frame = QGroupBox("📍 " + self.filterText["positionstitle"])
        positions_frame.setToolTip("Filter by table positions (Button, Small Blind, Big Blind, etc.)")
        self.fillPositionsFrame(positions_frame, self.display)
        return positions_frame

    def create_graph_ops_frame(self) -> QGroupBox:
        """Create the graph options frame."""
        graphops_frame = QGroupBox("Graphing Options:")
        self.cbGraphops = {}
        self.fillGraphOpsFrame(graphops_frame)
        return graphops_frame

    def create_seats_frame(self) -> QGroupBox:
        """Create the seats selection frame."""
        seats_frame = QGroupBox(self.filterText["seatstitle"])
        self.sbSeats = {}
        self.fillSeatsFrame(seats_frame)
        return seats_frame

    def create_groups_frame(self) -> QGroupBox:
        """Create the groups selection frame."""
        groups_frame = QGroupBox(self.filterText["groupstitle"])
        self.fillGroupsFrame(groups_frame, self.display)
        return groups_frame

    def create_date_frame(self) -> QGroupBox:
        """Create the date range selection frame."""
        date_frame = QGroupBox("📅 " + self.filterText["datestitle"])
        date_frame.setToolTip("Filter by date range for your poker sessions")
        self.fillDateFrame(date_frame)
        return date_frame

    def create_cards_frame(self) -> QGroupBox:
        """Create the hole cards selection frame."""
        cards_frame = QGroupBox("🎴 " + self.filterText["cardstitle"])
        cards_frame.setToolTip("Filter by starting hole cards (AA, AK, etc.)")
        self.fillHoleCardsFrame(cards_frame)
        return cards_frame

    def create_buttons(self) -> QWidget:
        """Create action buttons widget."""
        button_frame = QWidget()
        button_layout = QVBoxLayout(button_frame)
        if self.display.get("Button1", False):
            self.Button1 = QPushButton("Unnamed 1")
            button_layout.addWidget(self.Button1)
        if self.display.get("Button2", False):
            self.Button2 = QPushButton("Unnamed 2")
            button_layout.addWidget(self.Button2)
        return button_frame

    def getNumHands(self) -> int:
        """Get the number of hands filter value."""
        return self.phands.value() if self.phands else 0

    def getNumTourneys(self) -> int:
        """Get the number of tournaments filter value."""
        return 0

    def getGraphOps(self) -> list[str]:
        """Get selected graph options."""
        return [g for g in self.cbGraphops if self.cbGraphops[g].isChecked()]

    def getSites(self) -> list[str]:
        """Get selected sites."""
        return [s for s in self.cbSites if self.cbSites[s].isChecked() and self.cbSites[s].isEnabled()]

    def getPositions(self) -> list[str]:
        """Get selected positions."""
        return [p for p in self.cbPositions if self.cbPositions[p].isChecked() and self.cbPositions[p].isEnabled()]

    def getTourneyCat(self) -> list[str]:
        """Get selected tournament categories."""
        return [g for g in self.cbTourneyCat if self.cbTourneyCat[g].isChecked()]

    def getTourneyLim(self) -> list[str]:
        """Get selected tournament limits."""
        return [g for g in self.cbTourneyLim if self.cbTourneyLim[g].isChecked()]

    def getTourneyBuyin(self) -> list[str]:
        """Get selected tournament buyins."""
        return [g for g in self.cbTourneyBuyin if self.cbTourneyBuyin[g].isChecked()]

    def getTourneyTypes(self) -> list[str]:
        """Get selected tournament types."""
        return [g for g in self.cbTourney if self.cbTourney[g].isChecked()]

    def getGames(self) -> list[str]:
        """Get selected games."""
        return [g for g in self.cbGames if self.cbGames[g].isChecked() and self.cbGames[g].isEnabled()]

    def getCards(self) -> dict[str, Any]:
        """Get selected cards filter."""
        return self.cards

    def getCurrencies(self) -> list[str]:
        """Get selected currencies."""
        return [c for c in self.cbCurrencies if self.cbCurrencies[c].isChecked() and self.cbCurrencies[c].isEnabled()]

    def getSiteIds(self) -> dict[str, int]:
        """Get site IDs mapping."""
        return self.siteid

    def getHeroes(self) -> dict[str, str]:
        """Get selected heroes."""
        if selected_text := self.heroList.currentText():
            hero = selected_text.split(" on ")[0]
            site = selected_text.split(" on ")[1]
            return {site: hero}
        return {}


    def getLimits(self) -> list[str]:
        """Get selected limits."""
        return [
            limit for limit in self.cbLimits if self.cbLimits[limit].isChecked() and self.cbLimits[limit].isEnabled()
        ]

    def getType(self) -> str | None:
        """Get filter type."""
        return self.type

    def getSeats(self) -> dict[str, Any]:
        """Get seats filter configuration."""
        result = {}
        if "from" in self.sbSeats:
            result["from"] = self.sbSeats["from"].value()
        if "to" in self.sbSeats:
            result["to"] = self.sbSeats["to"].value()
        return result

    def getGroups(self) -> list[str]:
        """Get selected groups."""
        return [g for g in self.cbGroups if self.cbGroups[g].isChecked()]

    def getDates(self) -> tuple[str, str]:
        """Get date range filter."""
        offset = int(self.day_start * 3600)
        t1 = self.start_date.date()
        t2 = self.end_date.date()
        adj_t1 = QDateTime(t1).addSecs(offset)
        adj_t2 = QDateTime(t2).addSecs(offset + 24 * 3600 - 1)
        return (
            adj_t1.toUTC().toString("yyyy-MM-dd HH:mm:ss"),
            adj_t2.toUTC().toString("yyyy-MM-dd HH:mm:ss"),
        )

    def fillCardsFrame(self, frame: QGroupBox) -> None:
        """Fill the cards frame with controls."""
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
            for s in ["s", "o"]:
                if i >= j:
                    hand = f"{i}{j}{s}"
                    self.cards[hand] = False

    def registerButton1Name(self, title: str) -> None:
        """Register button 1 name."""
        self.Button1.setText(title)

    def registerButton1Callback(self, callback: Any) -> None:
        """Register button 1 callback."""
        self.Button1.clicked.connect(callback)
        self.Button1.setEnabled(True)
        self.callback["button1"] = callback

    def registerButton2Name(self, title: str) -> None:
        """Register button 2 name."""
        self.Button2.setText(title)

    def registerButton2Callback(self, callback: Any) -> None:
        """Register button 2 callback."""
        self.Button2.clicked.connect(callback)
        self.Button2.setEnabled(True)
        self.callback["button2"] = callback

    def registerCardsCallback(self, callback: Any) -> None:
        """Register cards callback."""
        self.callback["cards"] = callback

    def __set_tourney_type_select(self, w: QCheckBox, tourney_type: str) -> None:
        """Set tourney type selection."""
        self.tourneyTypes[tourney_type] = w.get_active()
        log.debug(
            "self.tourney_types[%s] set to %s",
            tourney_type,
            self.tourneyTypes[tourney_type],
        )

    def createTourneyTypeLine(self, hbox: QHBoxLayout, tourney_type: str) -> None:
        """Create tournament type line."""
        cb = QCheckBox(str(tourney_type))
        cb.clicked.connect(
            partial(self.__set_tourney_type_select, tourney_type=tourney_type),
        )
        hbox.addWidget(cb)
        cb.setChecked(True)

    def createCardsWidget(self, grid: QGridLayout) -> None:
        """Create the cards selection widget."""
        grid.setSpacing(0)
        for i in range(13):
            for j in range(13):
                abbr = Card.card_map_abbr[j][i]
                b = QPushButton("")
                import platform

                if platform.system() == "Darwin":
                    b.setStyleSheet("QPushButton {border-width:0;margin:6;padding:0;}")
                else:
                    b.setStyleSheet("QPushButton {border-width:0;margin:0;padding:0;}")
                b.clicked.connect(
                    partial(self.__toggle_card_select, widget=b, card=abbr),
                )
                self.cards[abbr] = False
                self.__toggle_card_select(_check_state=False, widget=b, card=abbr)
                grid.addWidget(b, j, i)

    def createCardsControls(self, hbox: QHBoxLayout) -> None:
        """Create cards control buttons."""
        selections = ["All", "Suited", "Off Suit"]
        for s in selections:
            cb = QCheckBox(s)
            cb.clicked.connect(self.__set_cards)
            hbox.addWidget(cb)

    def __card_select_bgcolor(self, card: str, selected: bool) -> str | None:  # noqa: FBT001
        """Get card selection background color."""
        pair_card_length = 2  # Length of pocket pair cards (e.g., "AA", "KK")
        s_on = "red"
        s_off = "orange"
        o_on = "white"
        o_off = "lightgrey"
        p_on = "blue"
        p_off = "lightblue"
        if len(card) == pair_card_length:
            return p_on if selected else p_off
        if card[2] == "s":
            return s_on if selected else s_off
        if card[2] == "o":
            return o_on if selected else o_off
        return None

    def __toggle_card_select(self, _check_state: bool, widget: QCheckBox, card: str) -> None:  # noqa: FBT001
        """Toggle card selection."""
        font = widget.font()
        font.setPointSize(10)
        widget.setFont(font)
        widget.setText(card)
        self.cards[card] = not self.cards[card]
        if "cards" in self.callback:
            self.callback["cards"](card)

    def __set_cards(self, _check_state: bool) -> None:  # noqa: FBT001
        """Set cards selection state."""

    def __set_checkboxes(self, _check_state: bool, check_boxes: dict[str, QCheckBox], set_state: bool) -> None:  # noqa: FBT001
        """Set checkbox states."""
        for checkbox in list(check_boxes.values()):
            checkbox.setChecked(set_state)

    def __select_limit(self, _check_state: bool, limit: str) -> None:  # noqa: FBT001
        """Select specific limit type."""
        for limit_key, checkbox in list(self.cbLimits.items()):
            if limit_key.endswith(limit):
                checkbox.setChecked(True)

    def fillPlayerFrame(self, frame: QGroupBox, display: dict[str, Any]) -> None:  # noqa: PLR0915, C901, PLR0912
        """Fill the player selection frame with hero selection controls."""
        vbox = QVBoxLayout()
        frame.setLayout(vbox)
        self.heroList = QComboBox()
        self.heroList.setStyleSheet("background-color: #455364")

        from pathlib import Path
        ico_path = str(Path(__file__).parent) + "\\" if os.name == "nt" else ""

        for _count, site in enumerate(self.conf.get_supported_sites(), start=1):
            player = self.conf.supported_sites[site].screen_name
            _pname = player
            self.leHeroes[site] = QLineEdit(_pname)

            icon_file = ""
            if site == "PokerStars":
                icon_file = "icons/ps.svg"
            elif site == "Full Tilt Poker":
                icon_file = "icons/ft.svg"
            elif site == "Everleaf":
                icon_file = "icons/everleaf.png"
            elif site == "Boss":
                icon_file = "icons/boss.ico"
            elif site == "PartyPoker":
                icon_file = "icons/party.png"
            elif site == "Merge":
                icon_file = "icons/merge.png"
            elif site == "PKR":
                icon_file = "icons/pkr.png"
            elif site == "iPoker":
                icon_file = "icons/ipoker.png"
            elif site == "Cake":
                icon_file = "icons/cake.jpg"
            elif site == "Entraction":
                icon_file = "icons/entraction.png"
            elif site == "BetOnline":
                icon_file = "icons/betonline.png"
            elif site == "Microgaming":
                icon_file = "icons/microgaming.png"
            elif site == "Bovada":
                icon_file = "icons/bovada.png"
            elif site == "Enet":
                icon_file = "icons/enet.png"
            elif site == "SealsWithClubs":
                icon_file = "icons/swc.png"
            elif site == "WinningPoker":
                icon_file = "icons/winning.png"
            elif site == "GGPoker":
                icon_file = "icons/gg.png"
            elif site == "Pacific":
                icon_file = "icons/pacific.png"
            elif site == "KingsClub":
                icon_file = "icons/kingsclub.png"
            elif site == "Unibet":
                icon_file = "icons/unibet.png"
            elif site == "Winamax":
                icon_file = "icons/wina.svg"
            else:
                icon_file = ""

            if icon_file:
                self.heroList.addItem(QIcon(ico_path + icon_file), f"{_pname} on {site}")
            else:
                self.heroList.addItem(f"{_pname} on {site}")

        vbox.addWidget(self.heroList)
        self.heroList.currentTextChanged.connect(self.update_filters_for_hero)

        if display.get("GroupsAll"):
            hbox = QHBoxLayout()
            vbox.addLayout(hbox)
            self.cbGroups["allplayers"] = QCheckBox(self.filterText["groupsall"])
            hbox.addWidget(self.cbGroups["allplayers"])

            lbl = QLabel("Min # Hands:")
            hbox.addWidget(lbl)

            self.phands = QSpinBox()
            self.phands.setMaximum(int(1e5))
            hbox.addWidget(self.phands)

        refresh_button = QPushButton("Refresh Filters")
        refresh_button.clicked.connect(self.update_filters_for_hero)
        vbox.addWidget(refresh_button)

    def fillSitesFrame(self, frame: QGroupBox) -> None:
        """Fill the sites frame with site selection checkboxes."""
        vbox = QVBoxLayout()
        frame.setLayout(vbox)

        for site in self.conf.get_supported_sites():
            self.cbSites[site] = QCheckBox(site)
            self.cbSites[site].setChecked(True)
            vbox.addWidget(self.cbSites[site])

    def fillTourneyTypesFrame(self, frame: QGroupBox) -> None:
        """Fill the tournament types frame with tournament selection controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.cursor.execute("SELECT DISTINCT tourneyName FROM Tourneys")
        result = self.cursor.fetchall()
        log.debug("Select distint tourney name %s", result)
        self.gameList = QComboBox()
        self.gameList.setStyleSheet("background-color: #455364")
        for count, _game in enumerate(result, start=0):
            game = str(_game)
            if game == "(None,)":
                game = '("None",)'
                game = game.replace("(", "")
                game = game.replace(",", "")
                game = game.replace(")", "")
            else:
                game = game.replace("(", "")
                game = game.replace(",", "")
                game = game.replace(")", "")

            log.debug("game %s", game)
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
            log.debug("No games returned from database")

    def fillTourneyCatFrame(self, frame: QGroupBox) -> None:
        """Fill the tournament category frame with category selection controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.cursor.execute("SELECT DISTINCT category FROM TourneyTypes")
        result = self.cursor.fetchall()
        log.debug("show category from tourney %s", result)
        self.gameList = QComboBox()
        self.gameList.setStyleSheet("background-color: #455364")
        for count, _game in enumerate(result, start=0):
            game = str(_game)
            if game == "(None,)":
                game = '("None",)'
                game = game.replace("(", "")
                game = game.replace(",", "")
                game = game.replace(")", "")
            else:
                game = game.replace("(", "")
                game = game.replace(",", "")
                game = game.replace(")", "")

            log.debug(" game %s", game)
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
            log.debug("No games returned from database")

    def fillTourneyLimFrame(self, frame: QGroupBox) -> None:
        """Fill the tournament limits frame with limit type selection controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.cursor.execute("SELECT DISTINCT limitType FROM TourneyTypes")
        result = self.cursor.fetchall()
        log.debug("show limit from from tourney %s", result)
        self.gameList = QComboBox()
        self.gameList.setStyleSheet("background-color: #455364")
        for count, _game in enumerate(result, start=0):
            game = str(_game)
            if game == "(None,)":
                game = '("None",)'
                game = game.replace("(", "")
                game = game.replace(",", "")
                game = game.replace(")", "")
            else:
                game = game.replace("(", "")
                game = game.replace(",", "")
                game = game.replace(")", "")

            log.debug("game %s", game)
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
            log.debug("No games returned from database")

    def fillTourneyBuyinFrame(self, frame: QGroupBox) -> None:
        """Fill the tournament buyin frame with buyin selection controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.cursor.execute("SELECT DISTINCT buyin, fee FROM TourneyTypes")
        result = self.cursor.fetchall()

        if len(result) >= 1:
            for _count, (buyin, fee) in enumerate(result):
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

    def fillGamesFrame(self, frame: QGroupBox) -> None:
        """Fill the games frame with game variant selection controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.cursor.execute(self.sql.query["getGames"])
        result = self.db.cursor.fetchall()
        log.debug("get games %s", result)
        self.gameList = QComboBox()
        self.gameList.setStyleSheet("background-color: #455364")
        for count, _game in enumerate(result, start=0):
            game = str(_game)
            game = game.replace("(", "")
            game = game.replace(",", "")
            game = game.replace(")", "")
            log.debug("game %s", game)
            self.gameList.insertItem(count, game)

        if len(result) >= 1:
            for line in sorted(result, key=lambda game: self.gameName[game[0]]):
                self.cbGames[line[0]] = QCheckBox(self.gameName[line[0]])
                self.cbGames[line[0]].setChecked(True)
                vbox1.addWidget(self.cbGames[line[0]])

            if len(result) >= MIN_ITEMS_FOR_CONTROLS:
                hbox = QHBoxLayout()
                vbox1.addLayout(hbox)
                hbox.addStretch()

                btn_all = QPushButton(self.filterText["gamesall"])
                btn_all.clicked.connect(
                    partial(
                        self.__set_checkboxes,
                        checkBoxes=self.cbGames,
                        setState=True,
                    ),
                )
                hbox.addWidget(btn_all)

                btn_none = QPushButton(self.filterText["gamesnone"])
                btn_none.clicked.connect(
                    partial(
                        self.__set_checkboxes,
                        checkBoxes=self.cbGames,
                        setState=False,
                    ),
                )
                hbox.addWidget(btn_none)
                hbox.addStretch()
        else:
            log.debug("No games returned from database")

    def fillTourneyFrame(self, frame: QGroupBox) -> None:
        """Fill the tournament frame with tournament selection controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.cursor.execute(self.sql.query["getTourneyNames"])
        result = self.db.cursor.fetchall()
        log.debug("get tourney name %s", result)
        self.gameList = QComboBox()
        self.gameList.setStyleSheet("background-color: #455364")
        for count, _game in enumerate(result, start=0):
            game = str(_game)
            game = game.replace("(", "")
            game = game.replace(",", "")
            game = game.replace(")", "")
            self.gameList.insertItem(count, game)

    def fillPositionsFrame(self, frame: QGroupBox, _display: dict[str, Any]) -> None:
        """Fill the positions frame with position selection controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        result = [[0], [1], [2], [3], [4], [5], [6], [7], ["S"], ["B"]]
        res_count = len(result)

        if res_count > 0:
            v_count = 0
            col_count = 4
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
                if v_count == col_count:
                    v_count = 0

            dif = res_count % col_count
            while dif > 0:
                fillbox = QVBoxLayout()
                hbox.addLayout(fillbox)
                dif -= 1

            if res_count > 1:
                hbox = QHBoxLayout()
                vbox1.addLayout(hbox)
                hbox.addStretch()

                btn_all = QPushButton(self.filterText["positionsall"])
                btn_all.clicked.connect(
                    partial(
                        self.__set_checkboxes,
                        checkBoxes=self.cbPositions,
                        setState=True,
                    ),
                )
                hbox.addWidget(btn_all)

                btn_none = QPushButton(self.filterText["positionsnone"])
                btn_none.clicked.connect(
                    partial(
                        self.__set_checkboxes,
                        checkBoxes=self.cbPositions,
                        setState=False,
                    ),
                )
                hbox.addWidget(btn_none)
                hbox.addStretch()
        else:
            log.debug("No positions returned from database")

    def fillHoleCardsFrame(self, frame: QGroupBox) -> None:
        """Fill the hole cards frame with card selection controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        grid = QGridLayout()
        vbox1.addLayout(grid)
        self.createCardsWidget(grid)

        hbox = QHBoxLayout()
        vbox1.addLayout(hbox)
        self.createCardsControls(hbox)

    def fillCurrenciesFrame(self, frame: QGroupBox) -> None:
        """Fill the currencies frame with currency selection controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.cursor.execute(self.sql.query["getCurrencies"])
        result = self.db.cursor.fetchall()
        if len(result) >= 1:
            for line in result:
                cname = self.currencyName[line[0]] if line[0] in self.currencyName else line[0]
                self.cbCurrencies[line[0]] = QCheckBox(cname)
                self.cbCurrencies[line[0]].setChecked(True)
                vbox1.addWidget(self.cbCurrencies[line[0]])

            if len(result) >= MIN_ITEMS_FOR_CONTROLS:
                hbox = QHBoxLayout()
                vbox1.addLayout(hbox)
                hbox.addStretch()

                btn_all = QPushButton(self.filterText["currenciesall"])
                btn_all.clicked.connect(
                    partial(
                        self.__set_checkboxes,
                        checkBoxes=self.cbCurrencies,
                        setState=True,
                    ),
                )
                hbox.addWidget(btn_all)

                btn_none = QPushButton(self.filterText["currenciesnone"])
                btn_none.clicked.connect(
                    partial(
                        self.__set_checkboxes,
                        checkBoxes=self.cbCurrencies,
                        setState=False,
                    ),
                )
                hbox.addWidget(btn_none)
                hbox.addStretch()
            else:
                self.cbCurrencies[line[0]].setChecked(True)
        else:
            log.info("No currencies returned from database")

    def fillLimitsFrame(self, frame: QGroupBox, display: dict[str, Any]) -> None:
        """Fill the limits frame with betting limit selection controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.cursor.execute(self.sql.query["getCashLimits"])
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
                if "UseType" in self.display and line[0] != self.display["UseType"]:
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
            if "LimitSep" in display and display["LimitSep"] and len(result) >= MIN_ITEMS_FOR_CONTROLS:
                hbox = QHBoxLayout()
                vbox1.addLayout(hbox)
                hbox.addStretch()

                btn_all = QPushButton(self.filterText["limitsall"])
                btn_all.clicked.connect(
                    partial(
                        self.__set_checkboxes,
                        checkBoxes=self.cbLimits,
                        setState=True,
                    ),
                )
                hbox.addWidget(btn_all)

                btn_none = QPushButton(self.filterText["limitsnone"])
                btn_none.clicked.connect(
                    partial(
                        self.__set_checkboxes,
                        checkBoxes=self.cbLimits,
                        setState=False,
                    ),
                )
                hbox.addWidget(btn_none)

                if "LimitType" in display and display["LimitType"] and len(limits_found) > 1:
                    for limit in limits_found:
                        btn = QPushButton(self.filterText["limits" + limit.upper()])
                        btn.clicked.connect(partial(self.__select_limit, limit=limit))
                        hbox.addWidget(btn)

                hbox.addStretch()
        else:
            log.debug("No games returned from database")

        if "Type" in display and display["Type"] and "ring" in types_found and "tour" in types_found:
            self.type = "ring"

    def fillGraphOpsFrame(self, frame: QGroupBox) -> None:
        """Fill the graph operations frame with graph option controls."""
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        hbox1 = QHBoxLayout()
        vbox1.addLayout(hbox1)

        label = QLabel("Show Graph In:")
        hbox1.addWidget(label)

        self.cbGraphops["$"] = QRadioButton("$$", frame)
        hbox1.addWidget(self.cbGraphops["$"])
        self.cbGraphops["$"].setChecked(True)

        self.cbGraphops["BB"] = QRadioButton("BB", frame)
        hbox1.addWidget(self.cbGraphops["BB"])

        self.cbGraphops["showdown"] = QCheckBox("Showdown Winnings")
        vbox1.addWidget(self.cbGraphops["showdown"])

        self.cbGraphops["nonshowdown"] = QCheckBox("Non-Showdown Winnings")
        vbox1.addWidget(self.cbGraphops["nonshowdown"])

        self.cbGraphops["ev"] = QCheckBox("EV")
        vbox1.addWidget(self.cbGraphops["ev"])

    def fillSeatsFrame(self, frame: QGroupBox) -> None:
        """Fill the seats frame with seat range selection controls."""
        hbox = QHBoxLayout()
        frame.setLayout(hbox)

        lbl_from = QLabel(self.filterText["seatsbetween"])
        lbl_to = QLabel(self.filterText["seatsand"])

        adj1 = QSpinBox()
        adj1.setRange(2, 10)
        adj1.setValue(2)
        adj1.valueChanged.connect(partial(self.__seats_changed, "from"))

        adj2 = QSpinBox()
        adj2.setRange(2, 10)
        adj2.setValue(10)
        adj2.valueChanged.connect(partial(self.__seats_changed, "to"))

        hbox.addStretch()
        hbox.addWidget(lbl_from)
        hbox.addWidget(adj1)
        hbox.addWidget(lbl_to)
        hbox.addWidget(adj2)
        hbox.addStretch()

        self.sbSeats["from"] = adj1
        self.sbSeats["to"] = adj2

    def fillGroupsFrame(self, frame: QGroupBox, display: dict[str, Any]) -> None:
        """Fill the groups frame with grouping option controls."""
        vbox = QVBoxLayout()
        frame.setLayout(vbox)

        self.cbGroups["limits"] = QCheckBox(self.filterText["limitsshow"])
        vbox.addWidget(self.cbGroups["limits"])

        self.cbGroups["posn"] = QCheckBox(self.filterText["posnshow"])
        vbox.addWidget(self.cbGroups["posn"])

        if display.get("SeatSep"):
            self.cbGroups["seats"] = QCheckBox(self.filterText["seatsshow"])
            vbox.addWidget(self.cbGroups["seats"])

    def fillDateFrame(self, frame: QGroupBox) -> None:
        """Fill the date frame with date range selection controls."""
        table = QGridLayout()
        frame.setLayout(table)

        lbl_start = QLabel("From:")
        btn_start = QPushButton("Cal")
        btn_start.clicked.connect(
            partial(self.__calendar_dialog, date_edit=self.start_date),
        )
        clr_start = QPushButton("Reset")
        clr_start.clicked.connect(self.__clear_start_date)

        lbl_end = QLabel("To:")
        btn_end = QPushButton("Cal")
        btn_end.clicked.connect(partial(self.__calendar_dialog, date_edit=self.end_date))
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

    def get_limits_where_clause(self, limits: list[str]) -> str:
        """Generate WHERE clause for limits filtering."""
        limit_suffix_length = 2  # Length of limit type suffix (e.g., "fl", "pl", "nl")
        where = ""
        lims = [
            int(x[0:-limit_suffix_length]) for x in limits
            if len(x) > limit_suffix_length and x[-limit_suffix_length:] == "fl"
        ]
        potlims = [
            int(x[0:-limit_suffix_length]) for x in limits
            if len(x) > limit_suffix_length and x[-limit_suffix_length:] == "pl"
        ]
        nolims = [
            int(x[0:-limit_suffix_length]) for x in limits
            if len(x) > limit_suffix_length and x[-limit_suffix_length:] == "nl"
        ]
        capnolims = [
            int(x[0:-limit_suffix_length]) for x in limits
            if len(x) > limit_suffix_length and x[-limit_suffix_length:] == "cn"
        ]
        hpnolims = [
            int(x[0:-limit_suffix_length]) for x in limits
            if len(x) > limit_suffix_length and x[-limit_suffix_length:] == "hp"
        ]

        where = "AND ( "

        if lims:
            clause = "(gt.limitType = 'fl' and gt.bigBlind in ({}))".format(",".join(map(str, lims)))
        else:
            clause = "(gt.limitType = 'fl' and gt.bigBlind in (-1))"
        where = where + clause
        if potlims:
            clause = "or (gt.limitType = 'pl' and gt.bigBlind in ({}))".format(",".join(map(str, potlims)))
        else:
            clause = "or (gt.limitType = 'pl' and gt.bigBlind in (-1))"
        where = where + clause
        if nolims:
            clause = "or (gt.limitType = 'nl' and gt.bigBlind in ({}))".format(",".join(map(str, nolims)))
        else:
            clause = "or (gt.limitType = 'nl' and gt.bigBlind in (-1))"
        where = where + clause
        if hpnolims:
            clause = "or (gt.limitType = 'hp' and gt.bigBlind in ({}))".format(",".join(map(str, hpnolims)))
        else:
            clause = "or (gt.limitType = 'hp' and gt.bigBlind in (-1))"
        where = where + clause
        if capnolims:
            clause = "or (gt.limitType = 'cp' and gt.bigBlind in ({}))".format(",".join(map(str, capnolims)))
        else:
            clause = "or (gt.limitType = 'cp' and gt.bigBlind in (-1))"
        return where + clause + " )"

    def replace_placeholders_with_filter_values(self, query: str) -> str:
        """Replace query placeholders with actual filter values."""
        if "<game_test>" in query:
            games = self.getGames()
            gametest = f"AND gt.category IN {str(tuple(games)).replace(',)', ')')}" if games else ""
            query = query.replace("<game_test>", gametest)

        if "<limit_test>" in query:
            limits = self.getLimits()
            limittest = self.get_limits_where_clause(limits) if limits else ""
            query = query.replace("<limit_test>", limittest)

        if "<player_test>" in query:
            heroes = self.getHeroes()
            if heroes:
                hero_ids = self.get_hero_ids(heroes)
                player_test = f"AND hp.playerId IN ({','.join(map(str, hero_ids))})"
            else:
                player_test = ""
            query = query.replace("<player_test>", player_test)

        if "<position_test>" in query:
            positions = self.getPositions()
            if positions:
                formatted_positions = [f"'{position}'" for position in positions]
                positiontest = f"AND hp.position IN ({','.join(formatted_positions)})"
            else:
                positiontest = ""
            query = query.replace("<position_test>", positiontest)

        return query

    def get_hero_ids(self, heroes: list[str]) -> list[int]:
        """Get hero IDs from hero names."""
        hero_ids = []
        site_ids = self.getSiteIds()
        for site, hero in heroes.items():
            site_id = site_ids.get(site)
            if site_id is not None:
                self.cursor.execute(self.sql.query["getPlayerId"], (site_id, hero))
                result = self.cursor.fetchone()
                if result:
                    hero_ids.append(result[0])
        return hero_ids

    def __calendar_dialog(self, _check_state: Any, date_edit: QDateEdit) -> None:
        """Open calendar dialog for date selection."""
        d = QDialog()
        d.setWindowTitle("Pick a date")

        vb = QVBoxLayout()
        d.setLayout(vb)
        cal = QCalendarWidget()
        vb.addWidget(cal)

        btn = QPushButton("Done")
        btn.clicked.connect(
            partial(self.__get_date, dlg=d, calendar=cal, date_edit=date_edit),
        )
        vb.addWidget(btn)
        d.exec_()

    def __clear_start_date(self, _check_state: Any) -> None:
        """Clear start date filter."""
        self.start_date.setDate(QDate(1970, 1, 1))

    def __clear_end_date(self, _check_state: Any) -> None:
        """Clear end date filter."""
        self.end_date.setDate(QDate(2100, 1, 1))

    def __get_date(self, _check_state: bool, dlg: QDialog, calendar: QCalendarWidget, date_edit: QDateEdit) -> None:  # noqa: FBT001
        """Handle date selection from calendar."""
        new_date = calendar.selectedDate()
        date_edit.setDate(new_date)

        if date_edit == self.start_date:
            end = self.end_date.date()
            if new_date > end:
                self.end_date.setDate(new_date)
        else:
            start = self.start_date.date()
            if new_date < start:
                self.start_date.setDate(new_date)
        dlg.accept()

    def __seats_changed(self, _value: int, which: str) -> None:
        """Handle seats value change."""
        seats_from = self.sbSeats["from"].value()
        seats_to = self.sbSeats["to"].value()
        if seats_from > seats_to:
            if which == "from":
                self.sbSeats["to"].setValue(seats_from)
            else:
                self.sbSeats["from"].setValue(seats_to)

    def setGames(self, games: list[str]) -> None:
        """Set games filter."""
        self.games = games

    def update_filters_for_hero(self) -> None:
        """Update all filters when hero selection changes."""
        if self.heroList and self.heroList.count() > 0:
            selected_text = self.heroList.currentText()
            if " on " in selected_text:
                selected_hero, selected_site = selected_text.split(" on ")
                self.update_sites_for_hero(selected_hero, selected_site)
                self.update_games_for_hero(selected_hero, selected_site)
                self.update_limits_for_hero(selected_hero, selected_site)
                self.update_positions_for_hero(selected_hero, selected_site)
                self.update_currencies_for_hero(selected_hero, selected_site)

    def update_sites_for_hero(self, _hero: str, site: str) -> None:
        """Update sites filter for selected hero and site."""
        for s, checkbox in self.cbSites.items():
            checkbox.setChecked(s == site)
            checkbox.setEnabled(s == site)

    def update_games_for_hero(self, hero: str, site: str) -> None:
        """Update games filter for selected hero and site."""
        site_id = self.siteid[site]
        usetype = self.display.get("UseType", "")
        log.debug("Game type for hero %s on site %s: %s", hero, site, usetype)

        if usetype == "tour":
            self.cursor.execute(
                self.sql.query["getCategoryBySiteAndPlayer"],
                (site_id, hero),
            )
        else:  # ring games
            self.cursor.execute(
                self.sql.query["getCategoryBySiteAndPlayerRing"],
                (site_id, hero),
            )

        games = [row[0] for row in self.cursor.fetchall()]
        log.debug("Available games for hero %s on site %s: %s", hero, site, games)

        for game, checkbox in self.cbGames.items():
            if game in games:
                checkbox.setChecked(True)
                checkbox.setEnabled(True)
            else:
                checkbox.setChecked(False)
                checkbox.setEnabled(False)

        # update
        self.games = games

    def update_limits_for_hero(self, _hero: str, site: str) -> None:
        """Update limits filter for selected hero and site."""
        query = self.sql.query["getCashLimits"].replace("%s", str(self.siteid[site]))
        self.cursor.execute(query)
        limits = [f"{row[2]}{row[1]}" for row in self.cursor.fetchall()]
        for limit, checkbox in self.cbLimits.items():
            if limit in limits:
                checkbox.setChecked(True)
                checkbox.setEnabled(True)
            else:
                checkbox.setChecked(False)
                checkbox.setEnabled(False)

    def update_positions_for_hero(self, hero: str, site: str) -> None:
        """Update positions filter for selected hero and site."""
        site_id = self.siteid[site]
        self.cursor.execute(
            self.sql.query["getPositionByPlayerAndHandid"],
            (hero, f"{site_id}%"),
        )
        positions = [str(row[0]) for row in self.cursor.fetchall()]
        for position, checkbox in self.cbPositions.items():
            if position in positions:
                checkbox.setChecked(True)
                checkbox.setEnabled(True)
            else:
                checkbox.setChecked(False)
                checkbox.setEnabled(False)

    def getBuyIn(self) -> list[str]:
        """Get selected tournament buyins."""
        selected_buyins = []
        for value, checkbox in self.cbTourneyBuyin.items():
            if checkbox.isChecked() and value != "None":
                buyin, fee = map(int, value.split(","))
                total = buyin + fee
                selected_buyins.append(total)
        return selected_buyins

    def update_currencies_for_hero(self, hero: str, site: str) -> None:
        """Update currencies filter for selected hero and site."""
        site_id = self.siteid[site]
        # debug
        log.debug("executed request for %s on %s (site_id: %s)", hero, site, site_id)
        self.cursor.execute(
            self.sql.query["getCurrencyBySiteAndPlayer"],
            (site_id, hero),
        )
        currencies = [row[0] for row in self.cursor.fetchall()]
        # debug
        log.debug("currencies found for %s on %s: %s", hero, site, currencies)

        for currency, checkbox in self.cbCurrencies.items():
            if currency in currencies:
                checkbox.setChecked(True)
                checkbox.setEnabled(True)
            else:
                checkbox.setChecked(False)
                checkbox.setEnabled(False)

            # manage tour 'T$' on  'ring'
            if currency == "T$" and self.getType() == "ring":
                checkbox.setChecked(False)
                checkbox.setEnabled(False)
            # debug
            log.debug(
                "Devise %s - Checked: %s, Activated: %s on %s",
                currency,
                checkbox.isChecked(),
                checkbox.isEnabled(),
                site,
            )


if __name__ == "__main__":
    config = Configuration.Config(file="HUD_config.test.xml")
    db = Database.Database(config)

    qdict = SQL.Sql(db_server="sqlite")

    filters_display = {
        "Heroes": False,
        "Sites": False,
        "Games": False,
        "Cards": True,
        "Currencies": True,
        "Limits": True,
        "LimitSep": False,
        "LimitType": False,
        "Type": False,
        "UseType": "ring",
        "Seats": False,
        "SeatSep": False,
        "Dates": False,
        "GraphOps": False,
        "Groups": False,
        "Button1": False,
        "Button2": False,
    }

    from PyQt5.QtWidgets import QApplication, QMainWindow

    app = QApplication([])
    i = Filters(db, display=filters_display)
    main_window = QMainWindow()
    main_window.setCentralWidget(i)
    main_window.show()
    app.exec_()
