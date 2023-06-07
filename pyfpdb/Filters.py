#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2008-2011 Steffen Schaumburg
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


from __future__ import print_function
from __future__ import division
import itertools
from ast import Pass

from dataclasses import replace
from past.utils import old_div
#import L10n
#_ = L10n.get_translation()
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
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = logging.getLogger("filter")

class Filters(QWidget):
    def __init__(self, db, display=None):
        """
        Initializes a Filters widget.

        Args:
            db (Database): The database object to filter.
            display (dict): A dictionary of display settings.

        Attributes:
            db (Database): The database object to filter.
            cursor (Cursor): The database cursor.
            sql (SQL): The SQL object for querying the database.
            conf (Config): The configuration object for the database.
            display (dict): A dictionary of display settings.
            gameName (dict): A dictionary of game names.
            currencyName (dict): A dictionary of currency names.
            filterText (dict): A dictionary of filter text strings.
            day_start (float): The start time of the day in hours (e.g. 9.5 for 9:30 AM).
            callback (dict): A dictionary of callbacks for filter actions.

        Returns:
            None
        """
        if display is None:
            display = {}
        QWidget.__init__(self, None)
        self.db = db
        self.cursor = db.cursor
        self.sql = db.sql
        self.conf = db.config
        self.display = display

        # Dictionary of game names
        self.gameName = {"27_1draw"  : ("Single Draw 2-7 Lowball")
                        ,"27_3draw"  : ("Triple Draw 2-7 Lowball")
                        ,"a5_3draw"  : ("Triple Draw A-5 Lowball")
                        ,"5_studhi"   : ("5 Card Stud")
                        ,"badugi"    : ("Badugi")
                        ,"badacey"   : ("Badacey")
                        ,"badeucey"  : ("Badeucey")
                        ,"drawmaha"  : ("2-7 Drawmaha")
                        ,"a5_1draw"  : ("A-5 Single Draw")
                        ,"27_razz"   : ("2-7 Razz")
                        ,"fivedraw"  : ("5 Card Draw")
                        ,"holdem"    : ("Hold'em")
                        ,"6_holdem"    : ("Hold'em")
                        ,"omahahi"   : ("Omaha")
                        ,"fusion"    : ("Fusion")
                        ,"omahahilo" : ("Omaha Hi/Lo")
                        ,"razz"      : ("Razz")
                        ,"studhi"    : ("7 Card Stud")
                        ,"studhilo"  : ("7 Card Stud Hi/Lo")
                        ,"5_omahahi" : ("5 Card Omaha")
                        ,"5_omaha8"  : ("5 Card Omaha Hi/Lo")
                        ,"cour_hi"   : ("Courchevel")
                        ,"cour_hilo" : ("Courchevel Hi/Lo")
                        ,"2_holdem"  : ("Double hold'em")
                        ,"irish"     : ("Irish")
                        ,"6_omahahi" : ("6 Card Omaha")
                        }
        # Dictionary of currency names
        self.currencyName = {"USD" : ("US Dollar")
                            ,"EUR" : ("Euro")
                            ,"T$"  : ("Tournament Dollar")
                            ,"play": ("Play Money")
                            }

        # text used on screen stored here so that it can be configured
        self.filterText = {'limitsall':('All'), 'limitsnone':('None'), 'limitsshow':('Show Limits')
                          ,'gamesall':('All'), 'gamesnone':('None')
                          ,'positionsall':('All'), 'positionsnone':('None')
                          ,'currenciesall':('All'), 'currenciesnone':('None')
                          ,'seatsbetween':('Between:'), 'seatsand':('And:'), 'seatsshow':('Show Number of Players')
                          ,'playerstitle':('Hero:'), 'sitestitle':(('Sites')+':'), 'gamestitle':(('Games')+':'), 'tourneytitle':(('Tourney')+':'),'tourneycat':(('King of game')+':')
                          ,'limitstitle':('Limits:'), 'positionstitle':('Positions:'), 'seatstitle':('Number of Players:'),'tourneylim':(('Betting limit')+':')
                          ,'groupstitle':('Grouping:'), 'posnshow':('Show Position Stats'),'tourneybuyin':(('Buyin')+':')
                          ,'datestitle':('Date:'), 'currenciestitle':(('Currencies')+':')
                          ,'groupsall':('All Players'), 'cardstitle':(('Hole Cards')+':')
                          ,'limitsFL':'FL', 'limitsNL':'NL', 'limitsPL':'PL', 'limitsCN':'CAP', 'ring':('Ring'), 'tour':('Tourney'), 'limitsHP':'HP'
                          }
        
        # Get the general parameters from the configuration object
        gen = self.conf.get_general_params()
        self.day_start = 0

        # Set the day start time to the value specified in the configuration
        if 'day_start' in gen:
            self.day_start = float(gen['day_start'])

        # Set the layout of the widget
        self.setLayout(QVBoxLayout())

        # Set the callback dictionary
        self.callback = {}

        # Set the style sheet for the widget
        self.setStyleSheet("QPushButton {padding-left:5;padding-right:5;padding-top:2;padding-bottom:2;}")

        # Call the make_filter function to create the filter
        self.make_filter()
        
    def make_filter(self):
        """
        Initializes the filter GUI with the appropriate widgets and layouts.

        Returns:
            None
        """
        # Initialize dictionaries
        self.siteid = {}
        self.cards = {}

        # Get db site id for filtering later
        for site in self.conf.get_supported_sites():
            self.cursor.execute(self.sql.query['getSiteId'], (site,))
            result = self.db.cursor.fetchall()
            if len(result) == 1:
                self.siteid[site] = result[0][0]
            else:
                log.debug(("Either 0 or more than one site matched for %s"), site)

        # For use in date ranges.
        self.start_date = QDateEdit(QDate(1970, 1, 1))
        self.end_date = QDateEdit(QDate(2100, 1, 1))

        # For use in groups etc
        self.cbGroups = {}
        self.phands = None

        # Initialize playerFrame and fill with widgets
        playerFrame = QGroupBox(self.filterText['playerstitle'])
        self.leHeroes = {}
        self.fillPlayerFrame(playerFrame, self.display)
        self.layout().addWidget(playerFrame)

        # Initialize sitesFrame and fill with widgets
        sitesFrame = QGroupBox(self.filterText['sitestitle'])
        self.cbSites = {}
        self.fillSitesFrame(sitesFrame)
        self.layout().addWidget(sitesFrame)

        # Initialize gamesFrame and fill with widgets
        gamesFrame = QGroupBox(self.filterText['gamestitle'])
        self.layout().addWidget(gamesFrame)
        self.cbGames = {}
        self.fillGamesFrame(gamesFrame)

        # Initialize tourneyFrame and fill with widgets
        tourneyFrame = QGroupBox(self.filterText['tourneytitle'])
        self.layout().addWidget(tourneyFrame)
        self.cbTourney = {}
        self.fillTourneyTypesFrame(tourneyFrame)

        # Initialize tourneyCatFrame and fill with widgets
        tourneyCatFrame = QGroupBox(self.filterText['tourneycat'])
        self.layout().addWidget(tourneyCatFrame)
        self.cbTourneyCat = {}
        self.fillTourneyCatFrame(tourneyCatFrame)

        # Initialize tourneyLimFrame and fill with widgets
        tourneyLimFrame = QGroupBox(self.filterText['tourneylim'])
        self.layout().addWidget(tourneyLimFrame)
        self.cbTourneyLim = {}
        self.fillTourneyLimFrame(tourneyLimFrame)

        # Initialize tourneyBuyinFrame and fill with widgets
        tourneyBuyinFrame = QGroupBox(self.filterText['tourneybuyin'])
        self.layout().addWidget(tourneyBuyinFrame)
        self.cbTourneyBuyin = {}
        self.fillTourneyBuyinFrame(tourneyBuyinFrame)

        # Initialize currenciesFrame and fill with widgets
        currenciesFrame = QGroupBox(self.filterText['currenciestitle'])
        self.layout().addWidget(currenciesFrame)
        self.cbCurrencies = {}
        self.fillCurrenciesFrame(currenciesFrame)

        # Initialize limitsFrame and fill with widgets
        limitsFrame = QGroupBox(self.filterText['limitstitle'])
        self.layout().addWidget(limitsFrame)
        self.cbLimits = {}
        self.rb = {}  # radio buttons for ring/tour
        self.type = None  # ring/tour
        self.fillLimitsFrame(limitsFrame, self.display)

        # Initialize positionsFrame and fill with widgets
        positionsFrame = QGroupBox(self.filterText['positionstitle'])
        self.layout().addWidget(positionsFrame)
        self.cbPositions = {}
        self.fillPositionsFrame(positionsFrame, self.display)

        # Initialize graphopsFrame and fill with widgets
        graphopsFrame = QGroupBox(("Graphing Options:"))
        self.layout().addWidget(graphopsFrame)
        self.cbGraphops = {}

        self.fillGraphOpsFrame(graphopsFrame)

        # Initialize seatsFrame and fill with widgets
        seatsFrame = QGroupBox(self.filterText['seatstitle'])
        self.layout().addWidget(seatsFrame)
        self.sbSeats = {}
        self.fillSeatsFrame(seatsFrame)

        # Initialize groupsFrame and fill with widgets
        groupsFrame = QGroupBox(self.filterText['groupstitle'])
        self.layout().addWidget(groupsFrame)
        self.fillGroupsFrame(groupsFrame, self.display)

        # Initialize dateFrame and fill with widgets
        dateFrame = QGroupBox(self.filterText['datestitle'])
        self.layout().addWidget(dateFrame)
        self.fillDateFrame(dateFrame)

        # Initialize cardsFrame and fill with widgets
        cardsFrame = QGroupBox(self.filterText['cardstitle'])
        self.layout().addWidget(cardsFrame)
        self.fillHoleCardsFrame(cardsFrame)

        # Initialize Buttons
        self.Button1 = QPushButton("Unnamed 1")
        self.Button2 = QPushButton("Unnamed 2")
        self.layout().addWidget(self.Button1)
        self.layout().addWidget(self.Button2)

        # Hide widgets based on display preferences
        if "Heroes" not in self.display or self.display["Heroes"] is False:
            playerFrame.hide()
        if "Sites" not in self.display or self.display["Sites"] is False:
            sitesFrame.hide()
        if "Games" not in self.display or self.display["Games"] is False:
            gamesFrame.hide()
        if "Tourney" not in self.display or self.display["Tourney"] is False:
            tourneyFrame.hide()
        if "King of game" not in self.display or self.display["King of game"] is False:
            tourneyCatFrame.hide()
        if "Betting limit" not in self.display or self.display["Betting limit"] is False:
            tourneyLimFrame.hide()
        if "Buyin" not in self.display or self.display["Buyin"] is False:
            tourneyBuyinFrame.hide()
        if "Currencies" not in self.display or self.display["Currencies"] is False:
            currenciesFrame.hide()
        if "Limits" not in self.display or self.display["Limits"] is False:
            limitsFrame.hide()
        if "Positions" not in self.display or self.display["Positions"] is False:
            positionsFrame.hide()
        if "Seats" not in self.display or self.display["Seats"] is False:
            seatsFrame.hide()
        if "Groups" not in self.display or self.display["Groups"] is False:
            groupsFrame.hide()
        if "Dates" not in self.display or self.display["Dates"] is False:
            dateFrame.hide()
        if "GraphOps" not in self.display or self.display["GraphOps"] is False:
            graphopsFrame.hide()
        if "Cards" not in self.display or self.display["Cards"] is False:
            cardsFrame.hide()
        if "Button1" not in self.display or self.display["Button1"] is False:
            self.Button1.hide()
        if "Button2" not in self.display or self.display["Button2"] is False:
            self.Button2.hide()

        # Release any locks on db
        self.db.rollback()


    def getNumHands(self):
        """
        Returns the number of hands.

        If self.phands is not None, returns the value of self.phands.
        Otherwise, returns 0.
        """
        return self.phands.value() if self.phands else 0
    def getNumTourneys(self):
        """
        Returns the number of tourneys.
        """
        #TODO: implement for mtt
        return 0


    

    def getSites(self):
        """Returns a list of selected sites.

        This method returns a list of sites that have been selected in the UI.

        Returns:
            list: A list of selected sites.
        """
        # List comprehension to filter selected sites using isChecked() method
        return [s for s in self.cbSites if self.cbSites[s].isChecked()]

    
    def getPositions(self):
        """
        Returns a list of checked positions from the cbPositions dictionary.

        Args:
            self: The object instance.

        Returns:
            A list of positions that have been checked.
        """
        # Use a list comprehension to loop through the cbPositions dictionary and return
        # only the positions where the isChecked() method returns True.
        return [p for p in self.cbPositions if self.cbPositions[p].isChecked()]


    def getTourneyCat(self):
        """
        Returns a list of all checked categories in the self.cbTourneyCat dictionary.
        """
        # Create a list comprehension that iterates over all keys in self.cbTourneyCat
        # and checks if the corresponding value is checked. If it is, add it to the list.
        return [g for g in self.cbTourneyCat if self.cbTourneyCat[g].isChecked()]

    def getTourneyLim(self):
        """Get a list of checked items in the cbTourneyLim checkbox group.

        Returns:
            A list of the checked items in the cbTourneyLim checkbox group.
        """
        # List comprehension that filters items in cbTourneyLim where isChecked is True
        return [g for g in self.cbTourneyLim if self.cbTourneyLim[g].isChecked()] 

    def getTourneyBuyin(self):
        """
        Returns a list of selected tournament buy-ins.

        Returns:
            list: A list of selected tournament buy-ins.
        """
        # Get all tournament buy-ins that are checked.
        return [g for g in self.cbTourneyBuyin if self.cbTourneyBuyin[g].isChecked()]

    def getTourneyTypes(self):
        """
        Get a list of tournament types that are selected in the checkbox group.

        Returns:
        list: A list of tournament types that are selected in the checkbox group.
        """
        # Use a list comprehension to filter the tournament types based on whether their corresponding checkbox is checked
        return [g for g in self.cbTourney if self.cbTourney[g].isChecked()]

    def getGames(self):
        """
        Returns a list of games that have been selected (checked) in the cbGames dictionary.
        """
        # use list comprehension to create a list of checked games
        return [g for g in self.cbGames if self.cbGames[g].isChecked()]


    def getCards(self):
        """Returns the list of cards in the deck."""
        return self.cards

    def getCurrencies(self):
        """
        Returns a list of selected currencies from a list of currencies.

        Args:
            self: The object instance.

        Returns:
            A list of selected currencies.
        """
        # Get all currencies that are checked
        return [c for c in self.cbCurrencies if self.cbCurrencies[c].isChecked()]


    def getSiteIds(self):
        """
        Returns the site ID of the object.
        """
        return self.siteid

    def getHeroes(self):
        """
        Returns a dictionary of hero sites and the currently selected hero from the dropdown menu.
        """
        #print(dict([(site, str(self.heroList.currentText())) for site in self.leHeroes]))
        # Return a dictionary with site and currently selected hero for each line edit
        return dict([(site, str(self.heroList.currentText())) for site in self.leHeroes])
    
    def getGraphOps(self):
        """
        Returns a list of all checked graph ops from a dictionary of graph ops.

        Args:
            self (object): The current object.

        Returns:
            list: A list of all checked graph ops.
        """
        # List comprehension to iterate through all graph ops and append any checked ones to a new list
        return [g for g in self.cbGraphops if self.cbGraphops[g].isChecked()]


    def getLimits(self):
        """
        Returns a list of checked limits.

        This method iterates through the dictionary of limit checkboxes and checks which ones are checked.
        It then returns a list of the names of the checked limits.

        Returns:
            list: A list of checked limit names.
        """
        # Return a list of the names of the checked limits
        return [l for l in self.cbLimits if self.cbLimits[l].isChecked()]

    def getType(self):
        """
        Returns the type of the object.
        """
        return self.type

    def getSeats(self):
        """
        Returns a dictionary containing the values of the 'from' and 'to' keys from the 'sbSeats' dictionary.

        Args:
            self (object): The object calling the method.

        Returns:
            dict: A dictionary containing the values of the 'from' and 'to' keys from the 'sbSeats' dictionary.
        """
        result = {}

        # Get the value of the 'from' key from the 'sbSeats' dictionary, if it exists.
        if 'from' in self.sbSeats:
            result['from'] = self.sbSeats['from'].value()

        # Get the value of the 'to' key from the 'sbSeats' dictionary, if it exists.
        if 'to' in self.sbSeats:
            result['to'] = self.sbSeats['to'].value()

        return result


    def getGroups(self):
        """
        Returns a list of the names of all checked groups.

        :return: A list of strings representing the names of all checked groups.
        """
        # List comprehension that filters checked groups and returns their names
        return [g for g in self.cbGroups if self.cbGroups[g].isChecked()]


    def getDates(self):
        """
        Returns tuple of adjusted start and end dates as strings in UTC format.

        The adjusted start and end dates have the user-defined start of day offset applied.

        Returns:
            Tuple of two strings: adjusted start date and adjusted end date.
        """
        # Get user-defined start of day in seconds
        offset = int(self.day_start * 3600)

        # Get start and end dates as date objects
        t1 = self.start_date.date()
        t2 = self.end_date.date()

        # Add offset to start and end dates
        adj_t1 = QDateTime(t1).addSecs(offset)
        adj_t2 = QDateTime(t2).addSecs(offset + 24 * 3600 - 1)

        # Convert adjusted start and end dates to UTC strings
        return (adj_t1.toUTC().toString("yyyy-MM-dd HH:mm:ss"), adj_t2.toUTC().toString("yyyy-MM-dd HH:mm:ss"))

    def registerButton1Name(self, title):
        """
        Sets the text of Button1 to the given title.

        Args:
            title (str): The text to set Button1 to.
        """
        # Set the text of Button1 to the title argument.
        self.Button1.setText(title)

    def registerButton1Callback(self, callback):
        """
        Register a callback function for Button1.

        Args:
            callback: The function to be called when Button1 is clicked.
        """
        # Connect the callback to Button1's clicked signal
        self.Button1.clicked.connect(callback)

        # Enable Button1
        self.Button1.setEnabled(True)

        # Store the callback function in the dictionary
        self.callback['button1'] = callback

    def registerButton2Name(self, title):
        """
        Sets the text of Button2 to the given title.

        Args:
            title (str): The title to set as the text of Button2.
        """
        # Set the text of Button2 to the given title
        self.Button2.setText(title)


    def registerButton2Callback(self, callback):
        """
        Registers a callback function to be called when Button2 is clicked.

        Args:
            callback: The function to be called when Button2 is clicked.
        """
        # Connect the Button2 clicked signal to the provided callback function
        self.Button2.clicked.connect(callback)

        # Enable Button2 to make it clickable
        self.Button2.setEnabled(True)

        # Store the provided callback function in a dictionary for later use
        self.callback['button2'] = callback


    def registerCardsCallback(self, callback):
        """
        Registers a callback function for when new cards are added.

        Args:
            callback: The function to call when new cards are added.
        """
        # Set the callback function for the 'cards' key in the callback dictionary.
        self.callback['cards'] = callback

    def __set_tourney_type_select(self, w, tourneyType):
        """
        Sets the value of the selected tourney type in the GUI.

        Args:
            w: A PyQt ComboBox widget.
            tourneyType: A string representing the selected tourney type.
        """
        self.tourneyTypes[tourneyType] = w.get_active()  # Set the selected tourney type in self.tourneyTypes
        log.debug("self.tourney_types[%s] set to %s", tourneyType, self.tourneyTypes[tourneyType])  # Log the updated value

    def createTourneyTypeLine(self, hbox, tourneyType):
        """
        Creates a checkbox for the given tourney type and adds it to the given hbox layout.
        The checkbox is connected to a function that sets the tourney type select.

        :param hbox: The QHBoxLayout to add the checkbox to.
        :param tourneyType: The tourney type to create a checkbox for.
        """
        # Create the checkbox
        cb = QCheckBox(str(tourneyType))
        # Connect it to the set_tourney_type_select function with the tourneyType argument already set
        cb.clicked.connect(partial(self.__set_tourney_type_select, tourneyType=tourneyType))
        # Add the checkbox to the hbox layout
        hbox.addWidget(cb)
        # Set the checkbox to be checked by default
        cb.setChecked(True)


    def createCardsWidget(self, grid):
        """
        Adds card buttons to a grid layout.

        Args:
            grid: The QGridLayout to add the card buttons to.
        """
        # Set spacing to 0 to remove any gaps between the buttons.
        grid.setSpacing(0)

        # Loop through all possible cards on the grid.
        for i, j in itertools.product(range(13), range(13)):
            # Get the card abbreviation for the current position.
            abbr = Card.card_map_abbr[j][i]

            # Create a new button for the card.
            b = QPushButton("")

            # Set the button style.
            import platform
            if platform.system == "Darwin":
                # On macOS, add a 6 pixel margin to the button to match the system style.
                b.setStyleSheet("QPushButton {border-width:0;margin:6;padding:0;}")
            else:
                # On other platforms, don't add any margin.
                b.setStyleSheet("QPushButton {border-width:0;margin:0;padding:0;}")

            # Connect the button click event to the __toggle_card_select method.
            b.clicked.connect(partial(self.__toggle_card_select, widget=b, card=abbr))

            # Initialize the card state to False and toggle it.
            self.cards[abbr] = False  # NOTE: This is flipped in __toggle_card_select below
            self.__toggle_card_select(False, widget=b, card=abbr)

            # Add the button to the grid.
            grid.addWidget(b, j, i)


    def createCardsControls(self, hbox):
        """
        Creates checkboxes for selecting card types and adds them to the given QHBoxLayout.

        Parameters:
        hbox (QHBoxLayout): The QHBoxLayout to which the checkboxes will be added.
        """

        # The different types of card selections
        selections = ["All", "Suited", "Off Suit"]

        # Create a checkbox for each selection and add them to the QHBoxLayout
        for s in selections:
            cb = QCheckBox(s)
            cb.clicked.connect(self.__set_cards)
            hbox.addWidget(cb)


    def __card_select_bgcolor(self, card, selected):
        """
        Returns the background color of a card based on whether it is selected or not.

        Args:
        - card (str): A string representing the card.
        - selected (bool): A boolean indicating whether the card is selected.

        Returns:
        - A string representing the background color of the card.
        """
        # Define the different colors for each suit and selected/unselected state
        s_on  = "red"
        s_off = "orange"
        o_on  = "white"
        o_off = "lightgrey"
        p_on  = "blue"
        p_off = "lightblue"

        # Check the suit and length of the card to determine its color
        if len(card) == 2:
            return p_on if selected else p_off
        if card[2] == 's':
            return s_on if selected else s_off
        if card[2] == 'o':
            return o_on if selected else o_off

    def __toggle_card_select(self, checkState, widget, card):
        """
        Toggles the selection state of a card and updates its font and background color.

        Args:
        - checkState (int): The new state of the widget (not used in the function).
        - widget (QtWidgets.QPushButton): The widget to update.
        - card (str): A string representing the card.

        Returns:
        - None
        """

        # Set the font size of the widget to 10 points
        font = widget.font()
        font.setPointSize(10)
        widget.setFont(font)

        # Set the text of the widget to the card string
        widget.setText(card)

        # Toggle the state of the card in the dictionary of cards
        self.cards[card] = not self.cards[card]

        # Get the background color for the card based on its current state
        bg_color = self.__card_select_bgcolor(card, self.cards[card])

        # Set the background color of the widget to the calculated color
        widget.setStyleSheet(f"background-color: {bg_color};")

        # If a callback function for cards exists, call it with the card string
        if 'cards' in self.callback:
            self.callback['cards'](card)

    def __set_cards(self, checkState):
        """
        This method sets the cards for the current game based on the given `checkState`.
        Args:
            checkState: A boolean value that determines whether to check if cards are valid or not.
        """
        pass


    def __set_checkboxes(self, checkState, checkBoxes, setState):
        """
        Check or uncheck all checkboxes in the given dictionary.

        Args:
            checkState (Qt.CheckState): The state to set the checkboxes to.
            checkBoxes (dict): A dictionary of checkbox widgets to set the state of.
            setState (bool): Whether to set the checkboxes to the given state or not.
        """
        # Loop over all checkbox widgets in the dictionary
        for checkbox in list(checkBoxes.values()):
            # Set the checkbox state to the given state
            checkbox.setChecked(setState)


    def __select_limit(self, checkState, limit):
        """
        Selects the checkbox for the given limit.

        Args:
            checkState: The state to set for the checkbox.
            limit: The limit for which to select the checkbox.
        """
        # Iterate through all the checkbox items.
        for l, checkbox in list(self.cbLimits.items()):
            # If the limit matches the current checkbox's limit, set its state to the given checkState.
            if l.endswith(limit):
                checkbox.setChecked(checkState)


    def fillPlayerFrame(self, frame, display):
        vbox = QVBoxLayout(frame)

        self.heroList = QComboBox()
        self.heroList.setStyleSheet("background-color: #455364")

        for site in self.conf.get_supported_sites():
            player = self.conf.supported_sites[site].screen_name
            _pname = player

            self.leHeroes[site] = QLineEdit(_pname)

            if os.name == 'nt':
                icoPath = os.path.dirname(__file__)
                icoPath = icoPath + "\\"
            else:
                icoPath = ""

            site_icons = {
                "PokerStars": 'ps.svg',
                "PartyPoker": 'party.png',
                "Merge": 'merge.png',
                "iPoker": 'ipoker.png',
                "Cake": 'cake.png',
                "Entraction": 'entraction.png',
                "BetOnline": 'betonline.png',
                "Microgaming": 'microgaming.png',
                "Bovada": 'bovada.png',
                "Enet": 'enet.png',
                "SealsWithClubs": 'swc.png',
                "WinningPoker": 'winning.png',
                "GGPoker": 'gg.png',
                "Pacific": 'pacific.png',
                "KingsClub": 'kingsclub.png',
                "Unibet": 'unibet.png',
                "Winamax": 'wina.svg',
            }

            if site in site_icons:
                completPlayer = _pname
                self.heroList.addItem(QIcon(f'{icoPath}{site_icons[site]}'), completPlayer)
            else:
                completPlayer = f"{_pname} on {site}"
                self.heroList.addItem(completPlayer)

            vbox.addWidget(self.heroList)

            names = self.db.get_player_names(self.conf, self.siteid[site])
            completer = QCompleter([n[0] for n in names])
            self.leHeroes[site].setCompleter(completer)

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
        for count,game in enumerate(result, start=0):
            game = str(result[count])
            if game == "(None,)":
                game = "(\"None\",)"
                game = game.replace("(","")
                game = game.replace(",","")
                game = game.replace(")","")
            else:
                game = game.replace("(","")
                game = game.replace(",","")
                game = game.replace(")","")
            
            print(game)
            if game != '"None"':
                self.gameList.insertItem(count,game)
            else:
                self.gameList.insertItem(count,game)
        #vbox1.addWidget(self.gameList)
        
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
            print(("INFO: No games returned from database"))
            log.info(("No games returned from database"))

    def fillTourneyCatFrame(self, frame):
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)
        
        req = self.cursor.execute("SELECT DISTINCT category FROM TourneyTypes")
        result = req.fetchall()
        print(result)
        self.gameList = QComboBox()
        self.gameList.setStyleSheet("background-color: #455364")   
        for count,game in enumerate(result, start=0):
            game = str(result[count])
            if game == "(None,)":
                game = "(\"None\",)"
                game = game.replace("(","")
                game = game.replace(",","")
                game = game.replace(")","")
            else:
                game = game.replace("(","")
                game = game.replace(",","")
                game = game.replace(")","")
            
            print(game)
            if game != '"None"':
                self.gameList.insertItem(count,game)
            else:
                self.gameList.insertItem(count,game)
        #vbox1.addWidget(self.gameList)
        
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
            print(("INFO: No games returned from database"))
            log.info(("No games returned from database"))

    def fillTourneyLimFrame(self, frame):
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)
        
        req = self.cursor.execute("SELECT DISTINCT limitType FROM TourneyTypes")
        result = req.fetchall()
        print(result)
        self.gameList = QComboBox()
        self.gameList.setStyleSheet("background-color: #455364")   
        for count,game in enumerate(result, start=0):
            game = str(result[count])
            if game == "(None,)":
                game = "(\"None\",)"
                game = game.replace("(","")
                game = game.replace(",","")
                game = game.replace(")","")
            else:
                game = game.replace("(","")
                game = game.replace(",","")
                game = game.replace(")","")
            
            print(game)
            if game != '"None"':
                self.gameList.insertItem(count,game)
            else:
                self.gameList.insertItem(count,game)
        #vbox1.addWidget(self.gameList)
        
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
            print(("INFO: No games returned from database"))
            log.info(("No games returned from database"))

    def fillTourneyBuyinFrame(self, frame):
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)
        
        req = self.cursor.execute("SELECT DISTINCT buyin FROM TourneyTypes")
        result = req.fetchall()
        print(result)
        self.gameList = QComboBox()
        self.gameList.setStyleSheet("background-color: #455364")   
        for count,game in enumerate(result, start=0):
            game = str(result[count])
            if game == "(None,)":
                game = "(\"None\",)"
                game = game.replace("(","")
                game = game.replace(",","")
                game = game.replace(")","")
            else:
                game = game.replace("(","")
                game = game.replace(",","")
                game = game.replace(")","")
            
            print(game)
            if game != '"None"':
                self.gameList.insertItem(count,game)
            else:
                self.gameList.insertItem(count,game)
        #vbox1.addWidget(self.gameList)
        
        if len(result) >= 1:
            for line in result:
                if str(line) == "(None,)":
                    self.cbTourneyBuyin[line[0]] = QCheckBox("None")
                    self.cbTourneyBuyin[line[0]].setChecked(True)
                    vbox1.addWidget(self.cbTourneyBuyin[line[0]])
                else:
                    self.cbTourneyBuyin[line[0]] = QCheckBox(str(line[0]*0.01))
                    self.cbTourneyBuyin[line[0]].setChecked(True)
                    vbox1.addWidget(self.cbTourneyBuyin[line[0]])


        else:
            print(("INFO: No games returned from database"))
            log.info(("No games returned from database"))

    def fillGamesFrame(self, frame):
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.cursor.execute(self.sql.query['getGames'])
        result = self.db.cursor.fetchall()
        print(result)
        self.gameList = QComboBox()
        self.gameList.setStyleSheet("background-color: #455364")   
        for count,game in enumerate(result, start=0):
            game = str(result[count])
            game = game.replace("(","")
            game = game.replace(",","")
            game = game.replace(")","")
            print(game)
            self.gameList.insertItem(count,game)
        #vbox1.addWidget(self.gameList)

        if len(result) >= 1:
            for line in sorted(result, key = lambda game: self.gameName[game[0]]):
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
            print(("INFO: No games returned from database"))
            log.info(("No games returned from database"))

    def fillTourneyFrame(self, frame):
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.cursor.execute(self.sql.query['getTourneyNames'])
        result = self.db.cursor.fetchall()
        print(result)
        self.gameList = QComboBox()
        self.gameList.setStyleSheet("background-color: #455364")   
        for count,game in enumerate(result, start=0):
            game = str(result[count])
            game = game.replace("(","")
            game = game.replace(",","")
            game = game.replace(")","")
            #print(game)
            self.gameList.insertItem(count,game)
            #self.cbTourney.addItem(game)
        print(type(self.cbTourney))
        #vbox1.addWidget(self.gameList)





    def fillPositionsFrame(self, frame, display):
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        # the following is not the fastest query (as it querys a table with potentialy a lot of data), so dont execute it if not necessary
        if "Positions" not in display or display["Positions"] is False:
            return
        
        #This takes too long if there are a couple of 100k hands in the DB
        #self.cursor.execute(self.sql.query['getPositions'])
        #result = self.db.cursor.fetchall()
        result = [[0], [1], [2], [3], [4], [5], [6], [7], ['S'], ['B']]
        res_count = len(result)
        
        if res_count > 0:     
            v_count = 0
            COL_COUNT = 4           #Number of columns
            hbox = None
            for line in result:
                if v_count == 0:    #start a new line when the vertical count is 0
                    hbox = QHBoxLayout()
                    vbox1.addLayout(hbox)
                    
                line_str = str(line[0])
                self.cbPositions[line_str] = QCheckBox(line_str)
                self.cbPositions[line_str].setChecked(True)
                hbox.addWidget(self.cbPositions[line_str])
                
                v_count += 1
                if v_count == COL_COUNT:    #set the counter to 0 if the line is full
                    v_count = 0
            
            dif = res_count % COL_COUNT    
            while dif > 0:          #fill the rest of the line with empy boxes, so that every line contains COL_COUNT elements
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
            print(("INFO") + ": " + ("No positions returned from database"))
            log.info(("No positions returned from database"))

    def fillHoleCardsFrame(self, frame):
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        grid = QGridLayout()
        vbox1.addLayout(grid)
        self.createCardsWidget(grid)

        # Additional controls for bulk changing card selection
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
                # There is only one currency. Select it, even if it's Play Money.
                self.cbCurrencies[line[0]].setChecked(True)
        else:
            log.info(("No currencies returned from database"))

    def fillLimitsFrame(self, frame, display):
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        self.cursor.execute(self.sql.query['getCashLimits'])
        # selects  limitType, bigBlind
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
                if i < old_div((len(result)+1),2):
                    vbox2.addLayout(hbox)
                else:
                    vbox3.addLayout(hbox)
                if True:  #line[0] == 'ring':
                    name = str(line[2])+line[1]
                    limits_found.add(line[1])
                    self.cbLimits[name] = QCheckBox(name)
                    self.cbLimits[name].setChecked(True)
                    hbox.addWidget(self.cbLimits[name])
                types_found.add(line[0])      # type is ring/tour
                self.type = line[0]        # if only one type, set it now
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
            print(("INFO: No games returned from database"))
            log.info(("No games returned from database"))

        if "Type" in display and display["Type"] and 'ring' in types_found and 'tour' in types_found:
            # rb1 = QRadioButton(frame, self.filterText['ring'])
            # rb1.clicked.connect(self.__set_limit_select)
            # rb2 = QRadioButton(frame, self.filterText['tour'])
            # rb2.clicked.connect(self.__set_limit_select)
            # top_hbox.addWidget(rb1)
            # top_hbox.addWidget(rb2)
            #
            # self.rb['ring'] = rb1
            # self.rb['tour'] = rb2
            # #print "about to set ring to true"
            # rb1.setChecked(True)
            # # set_active doesn't seem to call this for some reason so call manually:
            # self.__set_limit_select(rb1)
            self.type = 'ring'

    def fillGraphOpsFrame(self, frame):
        vbox1 = QVBoxLayout()
        frame.setLayout(vbox1)

        hbox1 = QHBoxLayout()
        vbox1.addLayout(hbox1)

        label = QLabel(("Show Graph In:"))
        hbox1.addWidget(label)

        self.cbGraphops['$'] = QRadioButton("$$", frame)
        hbox1.addWidget(self.cbGraphops['$'])
        self.cbGraphops['$'].setChecked(True)

        self.cbGraphops['BB'] = QRadioButton("BB", frame)
        hbox1.addWidget(self.cbGraphops['BB'])

        self.cbGraphops['showdown'] = QCheckBox(("Showdown Winnings"))
        vbox1.addWidget(self.cbGraphops['showdown'])

        self.cbGraphops['nonshowdown'] = QCheckBox(("Non-Showdown Winnings"))
        vbox1.addWidget(self.cbGraphops['nonshowdown'])

        self.cbGraphops['ev'] = QCheckBox(("EV"))
        vbox1.addWidget(self.cbGraphops['ev'])

    def fillSeatsFrame(self, frame):
        hbox = QHBoxLayout()
        frame.setLayout(hbox)

        lbl_from = QLabel(self.filterText['seatsbetween'])
        lbl_to   = QLabel(self.filterText['seatsand'])

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
        self.sbSeats['to']   = adj2

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
        """Accepts a list of limits and returns a formatted SQL where clause starting with AND.
            Sql statement MUST link to gameType table and use the alias gt for that table."""
        where = ""
        lims = [int(x[0:-2]) for x in limits if len(x) > 2 and x[-2:] == 'fl']
        potlims = [int(x[0:-2]) for x in limits if len(x) > 2 and x[-2:] == 'pl']
        nolims = [int(x[0:-2]) for x in limits if len(x) > 2 and x[-2:] == 'nl']
        capnolims = [int(x[0:-2]) for x in limits if len(x) > 2 and x[-2:] == 'cn']
        hpnolims = [int(x[0:-2]) for x in limits if len(x) > 2 and x[-2:] == 'hp']

        where          = "AND ( "

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
        """ Returnes given query with replaced placeholders by the filter values from self.
        
            List of Placeholders that are replaced and some infos how the statement has to look like:
            (whole clause means it starts with AND and contains the whole clause)
        
            Placeholders      table & alias or field     SQL usage          coresponding filter Name
            <player_test>     Players.Id                in <player_test>   Heroes
            <game_test>       GameType gt               whole clause       Game
            <limit_test>      GameType gt               whole clause       Limits, LimitSep, LimitType
            <position_test>   HandsPlayers hp           whole clause       Positions
        """
        
        if '<game_test>' in query:
            games = self.getGames()    

            if len(games) > 0:
                gametest = str(tuple(games))
                gametest = gametest.replace("L", "")
                gametest = gametest.replace(",)",")")
                gametest = gametest.replace("u'","'")
                gametest = "and gt.category in %s" % gametest
            else:
                gametest = "and gt.category IS NULL"
            query = query.replace('<game_test>', gametest)
            
        if '<limit_test>' in query:  #copyed from GuiGraphView
            limits = self.getLimits()
            limittest = self.get_limits_where_clause(limits)
            query = query.replace('<limit_test>', limittest)
            
        if '<player_test>' in query: #copyed from GuiGraphView
            sites = self.getSites()
            heroes = self.getHeroes()
            siteids = self.getSiteIds()
            sitenos = []
            playerids = []

            for site in sites:
                sitenos.append(siteids[site])
                _hname = Charset.to_utf8(heroes[site])
                result = self.db.get_player_id(self.conf, site, _hname)
                if result is not None:
                    playerids.append(str(result))
            
            query = query.replace('<player_test>', '(' + ','.join(playerids) + ')')
            
        if '<position_test>' in query:
            positions = self.getPositions()
            
            positiontest = "AND hp.position in ('" + "','".join(positions) + "')"   #values must be set in '' because they can be strings as well as numbers
            query = query.replace('<position_test>', positiontest)

        return query

    def __calendar_dialog(self, checkState, dateEdit):
        d = QDialog()
        d.setWindowTitle(('Pick a date'))

        vb = QVBoxLayout()
        d.setLayout(vb)
        cal = QCalendarWidget()
        vb.addWidget(cal)

        btn = QPushButton(('Done'))
        btn.clicked.connect(partial(self.__get_date, dlg=d, calendar=cal, dateEdit=dateEdit))

        vb.addWidget(btn)

        d.exec_()

    def __clear_start_date(self, checkState):
        self.start_date.setDate(QDate(1970,1,1))

    def __clear_end_date(self, checkState):
        self.end_date.setDate(QDate(2100,1,1))

    def __get_date(self, checkState, dlg, calendar, dateEdit):
        newDate = calendar.selectedDate()
        dateEdit.setDate(newDate)

        # if the opposite date is set, and now the start date is later
        # than the end date, modify the one we didn't just set to be
        # the same as the one we did just set
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

if __name__ == '__main__':
    config = Configuration.Config(file = "HUD_config.test.xml")
    db = Database.Database(config)

    qdict = SQL.Sql(db_server = 'sqlite')

    filters_display = { "Heroes"    : False,
                        "Sites"     : False,
                        "Games"     : False,
                        "Cards"     : True,
                        "Currencies": False,
                        "Limits"    : False,
                        "LimitSep"  : False,
                        "LimitType" : False,
                        "Type"      : False,
                        "UseType"   : 'ring',
                        "Seats"     : False,
                        "SeatSep"   : False,
                        "Dates"     : False,
                        "GraphOps"  : False,
                        "Groups"    : False,
                        "Button1"   : False,
                        "Button2"   : False
                          }

    from PyQt5.QtWidgets import QMainWindow, QApplication
    app = QApplication([])
    i = Filters(db, display = filters_display)
    main_window = QMainWindow()
    main_window.setCentralWidget(i)
    main_window.show()
    app.exec_()
